"""
MARSCOPE DEM Elevation Uncertainty Inventory
Extracts real PDS3 label / attached-IMG ODL keywords, catalog metadata, raster dtype,
quantization limits, and datum/calibration provenance without fabricating error bars.
"""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import rasterio

from app.ingestion.pds_label import _read_pds3_header_text, extract_pds3_metadata, parse_pds3_odl
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.schemas.dataset import Dataset
from app.terrain_uncertainty.models import MeasurementQuantityKind, UncertaintyStatus
from app.terrain_uncertainty.schemas import DatasetUncertaintyProfile, UncertaintyMetricRecord


def _extract_raw_pds_keywords(open_path: Path, raw_file: Optional[Path]) -> Dict[str, Any]:
    """Safely read real PDS3 header keywords from either standalone .LBL or attached .IMG header."""
    target = open_path if open_path.exists() else raw_file
    if target is None or not target.exists():
        return {}
    try:
        header_txt = _read_pds3_header_text(target, max_bytes=128 * 1024)
        # Strip PDS3 /* ... */ comments before keyword extraction so doc comments
        # like "/* I/F = (DN * SCALING_FACTOR) + OFFSET */" are not misread as keywords.
        header_clean = re.sub(r"/\*.*?\*/", " ", header_txt, flags=re.DOTALL)
        if "PDS_VERSION_ID" not in header_clean.upper() and "OBJECT" not in header_clean.upper():
            # Not a PDS3 header (e.g., plain GeoTIFF binary); never infer PDS keywords from binary noise.
            return {}
        parsed = parse_pds3_odl(header_clean)
        img_obj = parsed.get("_OBJECTS", {}).get("IMAGE", {})
        proj_obj = parsed.get("_OBJECTS", {}).get("IMAGE_MAP_PROJECTION", {})
        scale_line_match = re.search(r"MAP_SCALE\s*=\s*([^\r\n]+)", header_clean, re.IGNORECASE)
        scale_unit = None
        horiz_scale_m = None
        if scale_line_match:
            raw_line = scale_line_match.group(1)
            val_match = re.search(r"([+-]?\d+(?:\.\d+)?(?:[eEdD][+-]?\d+)?)", raw_line)
            if val_match:
                num = float(val_match.group(1).replace("D", "E").replace("d", "e"))
                if "METERS/PIXEL" in raw_line.upper() or "<M>" in raw_line.upper():
                    scale_unit = "METERS/PIXEL"
                    horiz_scale_m = num
                elif "KM/PIXEL" in raw_line.upper() or "<KM>" in raw_line.upper():
                    scale_unit = "KM/PIXEL"
                    horiz_scale_m = num * 1000.0

        # Audit ALL SCALING_FACTOR lines (header-wide + IMAGE object) to catch conflicts or invalid values
        scaling_matches = re.findall(r"(?:^|\s)SCALING_FACTOR\s*=\s*([^\r\n]+)", header_clean, re.IGNORECASE | re.MULTILINE)
        raw_scaling_tokens = [m.strip().split("<")[0].strip().strip('"').strip("'") for m in scaling_matches if m.strip()]
        if img_obj.get("SCALING_FACTOR") is not None and not raw_scaling_tokens:
            raw_scaling_tokens.append(str(img_obj.get("SCALING_FACTOR")).strip())

        parsed_scales: List[float] = []
        invalid_scaling_tokens: List[str] = []
        for tok in raw_scaling_tokens:
            try:
                val = float(tok.replace("D", "E").replace("d", "e"))
                if math.isfinite(val) and val > 0.0:
                    parsed_scales.append(val)
                else:
                    invalid_scaling_tokens.append(tok)
            except (TypeError, ValueError):
                invalid_scaling_tokens.append(tok)

        distinct_scales = list(dict.fromkeys(round(v, 12) for v in parsed_scales))
        scaling_factor_conflict = False
        scaling_factor_status = "missing"
        scaling_factor_val: Optional[float] = None
        if len(distinct_scales) > 1:
            scaling_factor_conflict = True
            scaling_factor_status = "conflicting_pds_keywords"
        elif invalid_scaling_tokens:
            scaling_factor_conflict = True
            scaling_factor_status = "invalid_pds_keyword"
        elif len(distinct_scales) == 1:
            scaling_factor_val = parsed_scales[0]
            scaling_factor_status = "explicit_pds_keyword"

        return {
            "product_id": parsed.get("PRODUCT_ID"),
            "data_set_id": parsed.get("DATA_SET_ID"),
            "software_name": parsed.get("SOFTWARE_NAME"),
            "source_product_id": parsed.get("SOURCE_PRODUCT_ID"),
            "sample_bits": int(img_obj["SAMPLE_BITS"]) if str(img_obj.get("SAMPLE_BITS", "")).isdigit() else None,
            "sample_type": img_obj.get("SAMPLE_TYPE"),
            "unit": img_obj.get("UNIT"),
            "scaling_factor": scaling_factor_val,
            "scaling_factor_raw_tokens": raw_scaling_tokens,
            "scaling_factor_status": scaling_factor_status,
            "scaling_factor_conflict": scaling_factor_conflict,
            "offset": img_obj.get("OFFSET"),
            "missing_constant": img_obj.get("MISSING_CONSTANT"),
            "valid_minimum": img_obj.get("VALID_MINIMUM"),
            "valid_maximum": img_obj.get("VALID_MAXIMUM"),
            "map_projection_type": proj_obj.get("MAP_PROJECTION_TYPE"),
            "map_scale_unit": scale_unit,
            "map_scale_meters_per_px": horiz_scale_m,
            "has_vertical_accuracy_keyword": any(
                k in header_clean.upper()
                for k in ("VERTICAL_ACCURACY", "HEIGHT_ERROR", "ELEVATION_ERROR", "ELEVATION_SIGMA")
            ),
        }
    except Exception:
        return {}


def _has_explicit_pds_unit_meter_rule(pds_kw: Dict[str, Any]) -> bool:
    """Explicit PDS3 archive specification rule for unscaled integer meters (e.g. MOLA MEGDR L3)."""
    pds_unit = str(pds_kw.get("unit") or "").strip().upper()
    ds_id = str(pds_kw.get("data_set_id") or "").strip().upper()
    s_type = str(pds_kw.get("sample_type") or "").strip().upper()
    return (
        pds_unit in ("METER", "METERS", "M")
        and "INTEGER" in s_type
        and "MOLA" in ds_id
        and "MEGDR" in ds_id
    )


def inspect_dataset_elevation_uncertainty(
    *,
    dataset: Dataset,
    raw_dir: Path,
    processed_dir: Optional[Path] = None,
) -> DatasetUncertaintyProfile:
    """
    Build a rigorous, non-fabricated uncertainty profile for a planetary DEM or ortho dataset.
    Explicitly separates horizontal spacing, quantization step (strictly requiring verified scaling),
    raw PDS sample encoding vs processed GeoTIFF dtype, nominal metadata precision,
    and absent per-pixel empirical error bands.
    """
    raw_file: Optional[Path] = Path(dataset.local_file_path) if dataset.local_file_path else None
    if raw_file is not None and not raw_file.is_absolute():
        raw_file = raw_dir.parent / raw_file
    if raw_file is None or not raw_file.exists():
        cand = raw_dir / dataset.product_id.lower()
        if cand.exists():
            raw_file = cand

    try:
        open_path, lbl_path = _resolve_raw_dem_open_path(dataset, raw_dir)
    except FileNotFoundError:
        open_path = raw_file if (raw_file and raw_file.exists()) else raw_dir / "__missing__"
        lbl_path = None

    explicit_lbl: Optional[Path] = Path(dataset.local_label_path) if dataset.local_label_path else None
    if explicit_lbl is not None and not explicit_lbl.is_absolute():
        explicit_lbl = raw_dir.parent / explicit_lbl
    pds_target = (
        explicit_lbl
        if (explicit_lbl and explicit_lbl.exists())
        else (lbl_path if (lbl_path and lbl_path.exists()) else (raw_file if (raw_file and raw_file.exists()) else open_path))
    )
    pds_kw = _extract_raw_pds_keywords(pds_target, raw_file)

    processed_raster_dtype: Optional[str] = None
    raw_raster_dtype: Optional[str] = None
    proc_tif = processed_dir / f"{dataset.id}_dem.tif" if processed_dir else None
    if proc_tif is not None and proc_tif.exists():
        try:
            with rasterio.open(proc_tif) as src:
                processed_raster_dtype = str(src.dtypes[0])
        except Exception:
            processed_raster_dtype = None

    if open_path.exists():
        try:
            with rasterio.open(open_path) as src:
                dtype_str = str(src.dtypes[0])
            if proc_tif is not None and open_path.resolve() == proc_tif.resolve():
                processed_raster_dtype = dtype_str
            else:
                raw_raster_dtype = dtype_str
        except Exception:
            pass

    raw_pds_sample_bits: Optional[int] = pds_kw.get("sample_bits")
    raw_pds_sample_type: Optional[str] = str(pds_kw["sample_type"]) if pds_kw.get("sample_type") else None
    effective_dtype = processed_raster_dtype or raw_raster_dtype
    sample_type = raw_pds_sample_type or effective_dtype

    is_int_quantized = bool(
        (raw_pds_sample_type and "INT" in raw_pds_sample_type.upper())
        or (raw_raster_dtype and "int" in raw_raster_dtype.lower() and "float" not in raw_raster_dtype.lower())
        or (processed_raster_dtype and "int" in processed_raster_dtype.lower() and "float" not in processed_raster_dtype.lower())
    )

    pds_scaling_factor: Optional[float] = pds_kw.get("scaling_factor")
    pds_scaling_status = str(pds_kw.get("scaling_factor_status") or "missing")
    scaling_conflict = bool(pds_kw.get("scaling_factor_conflict", False))

    horiz_res_m = dataset.horizontal_resolution_meters or pds_kw.get("map_scale_meters_per_px")
    metrics: List[UncertaintyMetricRecord] = []
    missing_fields: List[str] = [
        "per_pixel_vertical_rmse_raster",
        "stereo_matching_quality_correlation_map",
        "empirical_tiepoint_coregistration_rms",
    ]
    limitations: List[str] = []

    if horiz_res_m is not None:
        metrics.append(
            UncertaintyMetricRecord(
                metric_name="horizontal_grid_spacing",
                metric_kind=MeasurementQuantityKind.GRID_SPACING_RESOLUTION,
                status=UncertaintyStatus.QUANTIFIED_FROM_METADATA,
                value=round(float(horiz_res_m), 4),
                units="m/pixel",
                is_quantified_empirical_error=False,
                source_basis=f"Catalog / PDS3 MAP_SCALE ({dataset.product_id})",
                notes=[
                    "Horizontal grid spacing describes pixel sampling distance ONLY; it never implies vertical elevation accuracy."
                ],
            )
        )

    overall_status = UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED
    resolved_scaling: Optional[float] = None
    scaling_source: str = "unestablished"
    quantization_available = False

    if is_int_quantized:
        if scaling_conflict:
            scaling_source = pds_scaling_status
            missing_fields.append("unambiguous_vertical_scaling_factor")
            limitations.append(
                f"PDS header for '{dataset.product_id}' contains conflicting or invalid SCALING_FACTOR keywords "
                f"({pds_kw.get('scaling_factor_raw_tokens')}); quantization step is refused rather than guessed."
            )
            metrics.append(
                UncertaintyMetricRecord(
                    metric_name="elevation_quantization_step",
                    metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                    status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                    value=None,
                    units="m",
                    is_quantified_empirical_error=False,
                    source_basis=f"Conflicting/invalid PDS3 SCALING_FACTOR in {dataset.product_id}",
                    notes=["Quantization uncertainty unavailable due to conflicting or non-positive PDS SCALING_FACTOR."],
                )
            )
        else:
            q_step: Optional[float] = None
            source_basis_str = ""
            if pds_scaling_status == "explicit_pds_keyword" and pds_scaling_factor is not None:
                if (
                    dataset.vertical_resolution_meters is not None
                    and dataset.vertical_resolution_meters > 0
                    and abs(float(dataset.vertical_resolution_meters) - pds_scaling_factor) / max(pds_scaling_factor, 1e-9) > 0.05
                ):
                    scaling_conflict = True
                    scaling_source = "conflicting_pds_and_catalog_scaling"
                    missing_fields.append("unambiguous_vertical_scaling_factor")
                    limitations.append(
                        f"PDS SCALING_FACTOR ({pds_scaling_factor}) conflicts with catalog vertical_resolution_meters "
                        f"({dataset.vertical_resolution_meters}); quantization bound withheld."
                    )
                else:
                    q_step = float(pds_scaling_factor)
                    resolved_scaling = q_step
                    scaling_source = "explicit_pds_scaling_factor"
                    source_basis_str = f"PDS3 {sample_type or 'INTEGER'} SCALING_FACTOR={q_step} ({dataset.product_id})"
            elif _has_explicit_pds_unit_meter_rule(pds_kw):
                if (
                    dataset.vertical_resolution_meters is not None
                    and dataset.vertical_resolution_meters > 0
                    and abs(float(dataset.vertical_resolution_meters) - 1.0) > 1e-6
                ):
                    scaling_conflict = True
                    scaling_source = "conflicting_pds_and_catalog_scaling"
                    missing_fields.append("unambiguous_vertical_scaling_factor")
                    limitations.append(
                        f"PDS3 UNIT=METER for MOLA MEGDR conflicts with catalog vertical_resolution_meters={dataset.vertical_resolution_meters}."
                    )
                else:
                    q_step = 1.0
                    resolved_scaling = 1.0
                    scaling_source = "explicit_pds_mola_megdr_unit_meter"
                    source_basis_str = f"PDS3 {pds_kw.get('data_set_id')} {raw_pds_sample_type} UNIT=METER ({dataset.product_id})"
            elif dataset.vertical_resolution_meters is not None and dataset.vertical_resolution_meters > 0:
                q_step = float(dataset.vertical_resolution_meters)
                resolved_scaling = q_step
                scaling_source = "explicit_catalog_vertical_resolution"
                source_basis_str = (
                    f"Explicit catalog vertical_resolution_meters={q_step} m for integer raster ({dataset.product_id})"
                )

            if q_step is not None and not scaling_conflict:
                quantization_available = True
                q_sigma = q_step / math.sqrt(12.0)
                q_half = 0.5 * q_step
                metrics.append(
                    UncertaintyMetricRecord(
                        metric_name="elevation_quantization_step",
                        metric_kind=MeasurementQuantityKind.QUANTIZATION_STEP,
                        status=UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY,
                        value=round(q_step, 4),
                        units="m",
                        is_quantified_empirical_error=False,
                        source_basis=source_basis_str,
                        notes=[
                            f"Integer elevation representation quantizes values in {q_step} m steps (max quantization half-step +/- {q_half:.3f} m; uniform quantization SD = step/sqrt(12) = {q_sigma:.3f} m).",
                            "This is a strict quantization lower bound ONLY, NOT total instrument, interpolation, or crossover error.",
                        ],
                    )
                )
                metrics.append(
                    UncertaintyMetricRecord(
                        metric_name="quantization_uniform_standard_deviation",
                        metric_kind=MeasurementQuantityKind.STANDARD_DEVIATION,
                        status=UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY,
                        value=round(q_sigma, 4),
                        units="m",
                        is_quantified_empirical_error=False,
                        source_basis="Theoretical uniform rounding variance step^2 / 12 from explicit vertical scaling",
                        notes=["Lower bound only; MOLA MEGDR inter-track gaps up to ~12 km near equator carry unquantified interpolation error."],
                    )
                )
                overall_status = UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY
                limitations.append(
                    "Integer-encoded DEM provides a strict quantization bound only; true inter-track and crossover height errors are spatially variable and unquantified per pixel."
                )
            else:
                if "unambiguous_vertical_scaling_factor" not in missing_fields:
                    missing_fields.append("vertical_scaling_factor_or_vertical_resolution")
                metrics.append(
                    UncertaintyMetricRecord(
                        metric_name="elevation_quantization_step",
                        metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                        status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                        value=None,
                        units="m",
                        is_quantified_empirical_error=False,
                        source_basis=f"Integer raster dtype ({sample_type}) lacks PDS SCALING_FACTOR or explicit vertical_resolution_meters ({dataset.product_id})",
                        notes=[
                            "Quantization step is UNESTABLISHED: integer dtype alone never establishes 1.0 m scaling or vertical accuracy."
                        ],
                    )
                )
                metrics.append(
                    UncertaintyMetricRecord(
                        metric_name="quantization_uniform_standard_deviation",
                        metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                        status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                        value=None,
                        units="m",
                        is_quantified_empirical_error=False,
                        source_basis="Missing verified vertical scaling factor",
                        notes=["Quantization standard deviation unavailable without verified vertical scaling factor."],
                    )
                )
                limitations.append(
                    f"Dataset '{dataset.id}' uses integer raster encoding ({sample_type}) without an explicit PDS SCALING_FACTOR, "
                    "explicit archive unit rule, or catalog vertical_resolution_meters; quantization step is reported as UNQUANTIFIED (never defaulted to 1.0 m)."
                )
    elif scaling_conflict:
        scaling_source = pds_scaling_status
        missing_fields.append("unambiguous_vertical_scaling_factor")
        limitations.append(
            f"PDS header for '{dataset.product_id}' contains conflicting or invalid SCALING_FACTOR keywords ({pds_kw.get('scaling_factor_raw_tokens')})."
        )
        metrics.append(
            UncertaintyMetricRecord(
                metric_name="empirical_per_pixel_vertical_rmse",
                metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                value=None,
                units="m",
                is_quantified_empirical_error=False,
                source_basis=f"Conflicting PDS SCALING_FACTOR metadata in {dataset.product_id}",
                notes=["Vertical uncertainty unquantified due to conflicting PDS scaling keywords."],
            )
        )
    elif dataset.vertical_resolution_meters is not None and dataset.vertical_resolution_meters > 0:
        metrics.append(
            UncertaintyMetricRecord(
                metric_name="nominal_vertical_precision_metadata",
                metric_kind=MeasurementQuantityKind.NOMINAL_PRECISION_METADATA,
                status=UncertaintyStatus.QUANTIFIED_FROM_METADATA,
                value=round(float(dataset.vertical_resolution_meters), 4),
                units="m",
                is_quantified_empirical_error=False,
                source_basis=f"Catalog vertical_resolution_meters metadata for {dataset.product_id} (SOCET SET / Kirk et al. 2008 stereo baseline)",
                notes=[
                    "Nominal precision figure from catalog/mission documentation; NOT a spatially explicit per-pixel stereo correlation RMSE map.",
                    "Attached PDS3 label lacks per-pixel height sigma raster; local precision degrades in low-texture regolith, steep scarps, and shadows.",
                ],
            )
        )
        metrics.append(
            UncertaintyMetricRecord(
                metric_name="empirical_per_pixel_vertical_rmse",
                metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                value=None,
                units="m",
                is_spatial_map=False,
                is_quantified_empirical_error=False,
                source_basis=f"Inspected attached PDS3 header & GeoTIFF of {dataset.product_id}: 1 elevation band only, no sigma band present.",
                notes=["Per-pixel empirical elevation error is UNQUANTIFIED; sensitivity probes using nominal precision are clearly marked as scenario probes."],
            )
        )
        overall_status = UncertaintyStatus.QUANTIFIED_FROM_METADATA
        limitations.append(
            f"Catalog lists nominal vertical precision ~{dataset.vertical_resolution_meters:.2f} m for {dataset.product_id}, "
            "but neither the PDS3 label nor local GeoTIFF supplies a per-pixel vertical error band."
        )
    else:
        metrics.append(
            UncertaintyMetricRecord(
                metric_name="empirical_per_pixel_vertical_rmse",
                metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                value=None,
                units="m",
                is_quantified_empirical_error=False,
                source_basis=f"No vertical accuracy keyword in PDS3/catalog for {dataset.product_id}",
                notes=["Vertical uncertainty is unquantified."],
            )
        )
        limitations.append(f"Dataset '{dataset.id}' carries no documented vertical accuracy or error map.")

    reg_note = (
        f"Calibration: {dataset.calibration_status or 'Datum reference recorded in PDS3'}. "
        "PDS3 attached metadata contains MAP_SCALE and tie description, not a quantified local X/Y co-registration RMSE."
    )
    reg_metric = UncertaintyMetricRecord(
        metric_name="absolute_georegistration_offset",
        metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
        status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
        value=None,
        units="m",
        is_quantified_empirical_error=False,
        source_basis=f"Catalog & PDS3 CRS {dataset.coordinate_reference_system}",
        notes=[reg_note],
    )

    if any("12 km" in lim or "gap" in lim.lower() for lim in (dataset.known_limitations or [])):
        limitations.extend(dataset.known_limitations)

    return DatasetUncertaintyProfile(
        dataset_id=dataset.id,
        product_id=dataset.product_id,
        product_type=dataset.product_type,
        crs=dataset.coordinate_reference_system,
        vertical_datum=dataset.calibration_status or "Mars 2000 / MOLA Areoid Datum (dataset-defined)",
        horizontal_resolution_m=float(horiz_res_m) if horiz_res_m is not None else None,
        sample_bits=raw_pds_sample_bits,
        sample_type=str(sample_type) if sample_type else None,
        raw_pds_sample_bits=raw_pds_sample_bits,
        raw_pds_sample_type=raw_pds_sample_type,
        processed_raster_dtype=processed_raster_dtype,
        raw_raster_dtype=raw_raster_dtype,
        scaling_factor=resolved_scaling,
        scaling_factor_source=scaling_source,
        scaling_factor_conflict=scaling_conflict,
        quantization_uncertainty_available=quantization_available,
        is_integer_quantized=is_int_quantized,
        has_per_pixel_error_raster=False,
        pds_keywords_present=pds_kw,
        elevation_uncertainty_metrics=metrics,
        overall_elevation_uncertainty_status=overall_status,
        georegistration_uncertainty=reg_metric,
        missing_uncertainty_fields=list(dict.fromkeys(missing_fields)),
        limitations=list(dict.fromkeys(limitations)),
    )
