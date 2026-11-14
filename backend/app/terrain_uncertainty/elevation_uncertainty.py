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
        parsed = parse_pds3_odl(header_txt)
        img_obj = parsed.get("_OBJECTS", {}).get("IMAGE", {})
        proj_obj = parsed.get("_OBJECTS", {}).get("IMAGE_MAP_PROJECTION", {})
        scale_line_match = re.search(r"MAP_SCALE\s*=\s*([^\r\n]+)", header_txt, re.IGNORECASE)
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
        return {
            "product_id": parsed.get("PRODUCT_ID"),
            "data_set_id": parsed.get("DATA_SET_ID"),
            "software_name": parsed.get("SOFTWARE_NAME"),
            "source_product_id": parsed.get("SOURCE_PRODUCT_ID"),
            "sample_bits": int(img_obj["SAMPLE_BITS"]) if str(img_obj.get("SAMPLE_BITS", "")).isdigit() else None,
            "sample_type": img_obj.get("SAMPLE_TYPE"),
            "unit": img_obj.get("UNIT"),
            "scaling_factor": img_obj.get("SCALING_FACTOR"),
            "offset": img_obj.get("OFFSET"),
            "missing_constant": img_obj.get("MISSING_CONSTANT"),
            "valid_minimum": img_obj.get("VALID_MINIMUM"),
            "valid_maximum": img_obj.get("VALID_MAXIMUM"),
            "map_projection_type": proj_obj.get("MAP_PROJECTION_TYPE"),
            "map_scale_unit": scale_unit,
            "map_scale_meters_per_px": horiz_scale_m,
            "has_vertical_accuracy_keyword": any(
                k in header_txt.upper()
                for k in ("VERTICAL_ACCURACY", "HEIGHT_ERROR", "ELEVATION_ERROR", "ELEVATION_SIGMA")
            ),
        }
    except Exception:
        return {}


def inspect_dataset_elevation_uncertainty(
    *,
    dataset: Dataset,
    raw_dir: Path,
    processed_dir: Optional[Path] = None,
) -> DatasetUncertaintyProfile:
    """
    Build a rigorous, non-fabricated uncertainty profile for a planetary DEM or ortho dataset.
    Explicitly separates horizontal spacing, quantization step, nominal metadata precision,
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

    pds_target = lbl_path if (lbl_path and lbl_path.exists()) else (raw_file if (raw_file and raw_file.exists()) else open_path)
    pds_kw = _extract_raw_pds_keywords(pds_target, raw_file)

    raster_dtype: Optional[str] = None
    proc_tif = processed_dir / f"{dataset.id}_dem.tif" if processed_dir else None
    inspect_raster = proc_tif if (proc_tif and proc_tif.exists()) else (open_path if open_path.exists() else None)
    if inspect_raster is not None:
        try:
            with rasterio.open(inspect_raster) as src:
                raster_dtype = str(src.dtypes[0])
        except Exception:
            raster_dtype = None

    sample_bits = pds_kw.get("sample_bits")
    sample_type = pds_kw.get("sample_type") or raster_dtype
    is_int_quantized = bool(
        (sample_type and "INT" in str(sample_type).upper())
        or ("int" in (raster_dtype or "").lower() and "float" not in (raster_dtype or "").lower())
    )
    # Note: processed GeoTIFF is float32 even when raw MOLA IMG is MSB_INTEGER 16-bit!
    if pds_kw.get("sample_type") and "INTEGER" in str(pds_kw["sample_type"]).upper():
        is_int_quantized = True

    scale_val = 1.0
    try:
        if pds_kw.get("scaling_factor") is not None:
            scale_val = float(pds_kw["scaling_factor"])
    except (TypeError, ValueError):
        scale_val = 1.0

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
    if is_int_quantized:
        q_step = abs(scale_val) if dataset.vertical_resolution_meters is None else float(dataset.vertical_resolution_meters)
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
                source_basis=f"PDS3 {sample_type or 'INTEGER'} SCALING_FACTOR={scale_val} ({dataset.product_id})",
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
                source_basis="Theoretical uniform rounding variance step^2 / 12 from PDS3 integer encoding",
                notes=["Lower bound only; MOLA MEGDR inter-track gaps up to ~12 km near equator carry unquantified interpolation error."],
            )
        )
        overall_status = UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY
        limitations.append(
            "Integer-encoded DEM provides a strict quantization bound only; true inter-track and crossover height errors are spatially variable and unquantified per pixel."
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
        sample_bits=sample_bits,
        sample_type=str(sample_type) if sample_type else None,
        is_integer_quantized=is_int_quantized,
        has_per_pixel_error_raster=False,
        pds_keywords_present=pds_kw,
        elevation_uncertainty_metrics=metrics,
        overall_elevation_uncertainty_status=overall_status,
        georegistration_uncertainty=reg_metric,
        missing_uncertainty_fields=missing_fields,
        limitations=list(dict.fromkeys(limitations)),
    )
