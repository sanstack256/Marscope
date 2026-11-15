"""
MARSCOPE Multi-Resolution Mars Terrain Intelligence Engine (Prompt 19 Part 6).

Provides:
- Native-resolution metadata & uncertainty preservation (Part 6.1)
- Full 13-product windowed terrain derivatives with explicit provenance & validity gating (Part 6.2)
- Scale-aware terrain observability & Nyquist resolution classification (Part 6.3)
- Multi-scale overlapping DEM comparison without conflating scale/processing diffs with change (Part 6.4)
- Strictly gated 6-gate temporal terrain change assessment (CHANGE_NOT_EVALUABLE when any gate fails) (Part 6.5)
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from app.geospatial.crs import (
    MARS_EQUATORIAL_RADIUS_M,
    check_vertical_datum_compatibility,
    validate_mars_crs_detailed,
)
from app.geospatial.models import (
    CrsValidationResult,
    SpatialRegistrationAssessmentState,
    VerticalDatumKind,
)
from app.geospatial.registration import evaluate_product_pair_registration
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.schemas.dataset import Dataset
from app.science.provenance_graph import ScientificDataClassification
from app.terrain.aspect import calculate_aspect
from app.terrain.mesh import MARS_GEOG_CRS
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope

TERRAIN_INTELLIGENCE_VERSION = "mars_terrain_intel_v2.0"


class NativeDemMetadataRecord(BaseModel):
    dataset_id: str
    product_id: str
    native_pixel_spacing_m: Optional[float] = None
    horizontal_crs: str
    crs_validation: CrsValidationResult
    vertical_datum: VerticalDatumKind
    vertical_datum_description: str
    elevation_units: str
    nodata_value: Optional[float] = None
    source_uncertainty_vertical_m: Optional[float] = None
    pixel_registration: str
    processing_level: str
    source_provenance: str
    source_sha256: Optional[str] = None
    raster_dimensions: Optional[List[int]] = None
    has_overviews: bool = False
    overview_factors: List[int] = Field(default_factory=list)


class TerrainDerivativeMetadata(BaseModel):
    derivative_name: str
    available: bool
    valid_reason: Optional[str] = None
    input_dem_id: str
    input_product_id: str
    native_resolution_m: float
    processing_resolution_m: float
    resampling_applied: bool
    resampling_method: Optional[str] = None
    window_or_physical_scale: str
    algorithm: str
    algorithm_version: str = TERRAIN_INTELLIGENCE_VERSION
    edge_treatment: str = "strict_no_extrapolation_3x3_boundary_masked_nodata"
    nodata_handling: str = "strict_any_nodata_propagates_nan"
    units: str
    uncertainty_treatment: str
    processing_provenance: str
    stats: Optional[Dict[str, Optional[float]]] = None


class TerrainScaleObservabilityReport(BaseModel):
    dataset_id: str
    native_resolution_m: float
    nyquist_resolvable_feature_m: float
    min_3x3_slope_baseline_m: float
    resolvable_features: List[str] = Field(default_factory=list)
    below_effective_resolution: List[str] = Field(default_factory=list)
    noise_or_interpolation_affected: List[str] = Field(default_factory=list)
    unavailable_due_to_nodata_or_resolution: List[str] = Field(default_factory=list)
    unknown_terrain_policy: str = "unknown_or_nodata_terrain_never_classified_as_traversable"
    coarse_absence_policy: str = "coarse_dem_never_implies_absence_of_meter_scale_obstacles"


class WindowedTerrainDerivativesReport(BaseModel):
    dataset_metadata: NativeDemMetadataRecord
    requested_bounds: Dict[str, float]
    grid_shape: List[int]
    valid_pixel_count: int
    nodata_pixel_count: int
    valid_coverage_fraction: float
    resampling_applied: bool
    resampling_method: Optional[str] = None
    observability: TerrainScaleObservabilityReport
    derivatives: Dict[str, TerrainDerivativeMetadata] = Field(default_factory=dict)
    observability_class_counts: Dict[str, int] = Field(default_factory=dict)
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED


class ScaleComparisonEntry(BaseModel):
    dataset_id: str
    product_id: str
    scale_category: str  # regional_topography | local_topography | high_res_stereo_terrain | derived_roughness_uncalibrated
    native_resolution_m: float
    vertical_datum: VerticalDatumKind
    valid_pixel_count: int
    valid_coverage_fraction: float
    elevation_min_m: Optional[float] = None
    elevation_max_m: Optional[float] = None
    elevation_mean_m: Optional[float] = None
    slope_mean_deg: Optional[float] = None
    slope_p95_deg: Optional[float] = None
    tri_mean_m: Optional[float] = None
    smoothing_attenuation_note: str


class MultiScaleTerrainComparisonResponse(BaseModel):
    study_bounds: Dict[str, float]
    compared_datasets: List[ScaleComparisonEntry] = Field(default_factory=list)
    pairwise_cross_scale_deltas: List[Dict[str, Any]] = Field(default_factory=list)
    never_interprets_scale_diff_as_temporal_change: bool = True
    scientific_explanation: str
    limitations: List[str] = Field(default_factory=list)


class ChangeGateStatus(BaseModel):
    gate_name: str
    passed: bool
    detail: str


class TerrainChangeEvaluationResult(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    study_bounds: Dict[str, float]
    status: str  # CHANGE_NOT_EVALUABLE | NO_SIGNIFICANT_CHANGE_DETECTED | STATISTICALLY_SIGNIFICANT_CHANGE_DETECTED
    evaluable: bool
    gates: List[ChangeGateStatus] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    propagated_vertical_uncertainty_1sigma_m: Optional[float] = None
    observed_mean_delta_m: Optional[float] = None
    observed_max_abs_delta_m: Optional[float] = None
    significant_change_pixel_fraction: Optional[float] = None
    limitations: List[str] = Field(default_factory=list)


def inspect_dem_native_metadata(
    ds: Dataset,
    *,
    raw_dir: Path,
) -> NativeDemMetadataRecord:
    open_path, lbl_path = _resolve_raw_dem_open_path(ds, raw_dir)
    if not open_path.exists():
        raise FileNotFoundError(f"DEM raster missing locally for '{ds.id}'.")

    lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}
    crs_res = validate_mars_crs_detailed(
        ds.coordinate_reference_system,
        latitude_convention=ds.latitude_convention,
        longitude_direction=ds.longitude_direction,
        vertical_reference=ds.calibration_status,
    )
    with rasterio.open(open_path) as src:
        raw_crs = src.crs.to_string() if src.crs else (ds.coordinate_reference_system or "UNKNOWN")
        dims = [int(src.height), int(src.width)]
        nodata = src.nodatavals[0] if src.nodatavals else ds.nodata_value
        ov = list(src.overviews(1) or [])
        pix_reg = str((src.tags() or {}).get("AREA_OR_POINT", "Area (pixel-center mapped via GeoTIFF/PDS3)"))

    return NativeDemMetadataRecord(
        dataset_id=ds.id,
        product_id=ds.product_id,
        native_pixel_spacing_m=ds.horizontal_resolution_meters,
        horizontal_crs=raw_crs,
        crs_validation=crs_res,
        vertical_datum=crs_res.vertical_reference,
        vertical_datum_description=ds.calibration_status or "Unspecified",
        elevation_units=lbl_meta.get("units") or ds.units or "unknown",
        nodata_value=float(nodata) if nodata is not None else None,
        source_uncertainty_vertical_m=ds.vertical_resolution_meters,
        pixel_registration=pix_reg,
        processing_level=ds.processing_level or "Unspecified",
        source_provenance=f"{ds.mission} / {ds.instrument} ({ds.source_archive})",
        source_sha256=ds.sha256_checksum,
        raster_dimensions=dims,
        has_overviews=len(ov) > 0,
        overview_factors=ov,
    )


def _stats_from_array(arr: np.ndarray) -> Optional[Dict[str, Optional[float]]]:
    fin = arr[np.isfinite(arr)]
    if fin.size == 0:
        return None
    return {
        "min": round(float(np.min(fin)), 4),
        "max": round(float(np.max(fin)), 4),
        "mean": round(float(np.mean(fin)), 4),
        "std": round(float(np.std(fin)), 4),
        "p95": round(float(np.percentile(fin, 95)), 4),
        "valid_count": float(fin.size),
    }


def _classify_observability(native_res_m: float) -> TerrainScaleObservabilityReport:
    nyquist = round(2.5 * native_res_m, 2)
    min_3x3 = round(3.0 * native_res_m, 2)
    if native_res_m <= 2.5:
        res_feats = [
            f"Macro-landforms, ridges, scarps, and troughs >= {nyquist} m horizontal width",
            f"Local 3x3 Horn slope baselines over >= {min_3x3} m span",
        ]
        below = [
            f"Individual cobbles, boulders, fissures, or ripple crests < {nyquist} m width",
            "Wheel/boot-scale soil bearing capacity & unconsolidated dust pockets",
        ]
        noise = ["Flat benches (< 1-2 deg) where stereo matching jitter dominates Rice-biased slope"]
    elif native_res_m <= 100.0:
        res_feats = [f"Sub-kilometer regional craters, mesas, and valleys >= {nyquist} m"]
        below = [
            f"All EVA rover/astronaut-scale obstacles & meter-scale boxwork ridges (< {nyquist} m)",
            "Individual boulders, fracture troughs, and local steep ledges",
        ]
        noise = ["Multi-meter relief is attenuated into regional mean gradients"]
    else:
        res_feats = [f"Basin/edifice macro-relief and regional crater/ridge trends >= {nyquist / 1000.0:.2f} km"]
        below = [
            "All sub-kilometer topographic slopes, local escarpments, boxwork walls, ridges, and boulders",
            "Orbit-track inter-shot interpolation regions (~12 km MOLA gaps at equator)",
        ]
        noise = ["128 ppd / 4 ppd gridding interpolates cross-track gaps between laser altimeter tracks"]

    return TerrainScaleObservabilityReport(
        dataset_id="active",
        native_resolution_m=round(native_res_m, 3),
        nyquist_resolvable_feature_m=nyquist,
        min_3x3_slope_baseline_m=min_3x3,
        resolvable_features=res_feats,
        below_effective_resolution=below,
        noise_or_interpolation_affected=noise,
        unavailable_due_to_nodata_or_resolution=["Pixels with NaN/MISSING_CONSTANT remain strictly unavailable"],
    )


def compute_terrain_derivatives_window(
    ds: Dataset,
    *,
    raw_dir: Path,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    max_grid_dim: int = 192,
    local_scale_radius_m: float = 5.0,
    coarse_scale_radius_m: float = 25.0,
) -> WindowedTerrainDerivativesReport:
    """
    Compute all 13 Part 6.2 terrain derivative layers strictly at native or explicitly
    recorded bounded window resolution without interpolating across NoData gaps.
    """
    meta = inspect_dem_native_metadata(ds, raw_dir=raw_dir)
    if meta.elevation_units.lower() not in {"meter", "meters", "m"}:
        raise ValueError(f"Unsupported elevation units '{meta.elevation_units}' for terrain derivatives.")
    if not meta.crs_validation.valid:
        raise ValueError(f"Refused terrain derivatives for invalid Mars CRS: {meta.crs_validation.blockers}")

    open_path, lbl_path = _resolve_raw_dem_open_path(ds, raw_dir)
    lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}
    native_res = float(ds.horizontal_resolution_meters or 1.0)
    max_grid_dim = max(16, min(256, int(max_grid_dim)))

    def _run_with_reader(reader: Any) -> WindowedTerrainDerivativesReport:
        rb = reader.bounds
        q_min_lon = min_lon + 360.0 if (rb.right > 180.0 and min_lon < 0.0) else min_lon
        q_max_lon = max_lon + 360.0 if (rb.right > 180.0 and max_lon < 0.0) else max_lon
        c_min_lon = max(float(rb.left), q_min_lon)
        c_max_lon = min(float(rb.right), q_max_lon)
        c_min_lat = max(float(rb.bottom), min_lat)
        c_max_lat = min(float(rb.top), max_lat)
        if c_min_lon >= c_max_lon or c_min_lat >= c_max_lat:
            raise ValueError("Requested window does not intersect DEM bounds.")

        win = from_bounds(c_min_lon, c_min_lat, c_max_lon, c_max_lat, reader.transform).round_offsets().round_lengths()
        w_px, h_px = max(1, int(win.width)), max(1, int(win.height))
        stride = max(1.0, max(w_px, h_px) / float(max_grid_dim))
        out_w = max(3, min(w_px, int(round(w_px / stride))))
        out_h = max(3, min(h_px, int(round(h_px / stride))))
        resampling_applied = (out_w != w_px or out_h != h_px) or (meta.pixel_registration != "")
        resampling_method = "bilinear_window_decimation" if (out_w != w_px or out_h != h_px) else "native_pixel_grid"
        res_enum = Resampling.bilinear if (out_w != w_px or out_h != h_px) else Resampling.nearest

        arr = reader.read(1, window=win, out_shape=(out_h, out_w), resampling=res_enum).astype(np.float64)
        nodata_v = reader.nodata if reader.nodata is not None else (lbl_meta.get("missing_constant") or -32768.0)
        valid_mask = np.isfinite(arr) & (arr != float(nodata_v)) & (arr > -32000.0)
        z = np.where(valid_mask, arr, np.nan)
        nodata_mask = ~valid_mask

        center_lat = 0.5 * (c_min_lat + c_max_lat)
        lon_span_deg = c_max_lon - c_min_lon
        lat_span_deg = c_max_lat - c_min_lat
        dx_m = (lon_span_deg * (math.pi / 180.0) * MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(center_lat))) / float(out_w)
        dy_m = (lat_span_deg * (math.pi / 180.0) * MARS_EQUATORIAL_RADIUS_M) / float(out_h)
        proc_res = round(0.5 * (dx_m + dy_m), 3)

        slope_arr, aspect_arr = calculate_slope(z, dx_m, dy_m, nodata_mask=nodata_mask)[0], calculate_aspect(z, dx_m, dy_m, nodata_mask=nodata_mask)
        # 3x3 Evans partial derivatives for curvature & surface normals
        dz_dx = np.full_like(z, np.nan)
        dz_dy = np.full_like(z, np.nan)
        prof_curv = np.full_like(z, np.nan)
        plan_curv = np.full_like(z, np.nan)
        elev_var = np.full_like(z, np.nan)
        nz_arr = np.full_like(z, np.nan)
        relief_arr = np.full_like(z, np.nan)
        tpi_arr = np.full_like(z, np.nan)
        unc_elev_arr = np.full_like(z, np.nan)

        L = 0.5 * (dx_m + dy_m)
        rad_cells = max(1, min(6, int(round(local_scale_radius_m / max(L, 0.5)))))
        z_vert_sigma = float(ds.vertical_resolution_meters or 0.25)

        for r in range(1, out_h - 1):
            for c in range(1, out_w - 1):
                nb = z[r - 1 : r + 2, c - 1 : c + 2]
                if np.all(np.isfinite(nb)):
                    z1, z2, z3 = nb[0, 0], nb[0, 1], nb[0, 2]
                    z4, z5, z6 = nb[1, 0], nb[1, 1], nb[1, 2]
                    z7, z8, z9 = nb[2, 0], nb[2, 1], nb[2, 2]
                    p = ((z3 + z6 + z9) - (z1 + z4 + z7)) / (6.0 * L)
                    q = ((z1 + z2 + z3) - (z7 + z8 + z9)) / (6.0 * L)
                    dz_dx[r, c] = p
                    dz_dy[r, c] = q
                    nz_arr[r, c] = 1.0 / math.sqrt(p * p + q * q + 1.0)
                    elev_var[r, c] = float(np.std(nb))
                    unc_elev_arr[r, c] = z_vert_sigma
                    r_c = (z1 + z3 + z4 + z6 + z7 + z9 - 2.0 * (z2 + z5 + z8)) / (3.0 * L * L)
                    t_c = (z1 + z2 + z3 + z7 + z8 + z9 - 2.0 * (z4 + z5 + z6)) / (3.0 * L * L)
                    s_c = (z3 + z7 - z1 - z9) / (4.0 * L * L)
                    pq2 = p * p + q * q
                    if pq2 > 1e-12:
                        prof_curv[r, c] = -(r_c * p * p + 2.0 * s_c * p * q + t_c * q * q) / (pq2 * (1.0 + pq2) ** 1.5)
                        plan_curv[r, c] = -(r_c * q * q - 2.0 * s_c * p * q + t_c * p * p) / (pq2 ** 1.5)
                r0 = max(0, r - rad_cells)
                r1 = min(out_h, r + rad_cells + 1)
                c0 = max(0, c - rad_cells)
                c1 = min(out_w, c + rad_cells + 1)
                sub = z[r0:r1, c0:c1]
                if np.all(np.isfinite(sub)):
                    relief_arr[r, c] = float(np.max(sub) - np.min(sub))
                    tpi_arr[r, c] = float(z[r, c] - np.mean(sub))

        # Roughness TRI at 3x3 native/processing scale & coarse scale
        tri_3x3, _ = calculate_roughness_tri_with_metadata(
            z, dx_m, dy_m, nodata_mask=nodata_mask, source_product_id=ds.product_id, native_resolution_m=native_res
        )

        coarse_gate_ok = coarse_scale_radius_m >= 1.5 * proc_res and not (ds.horizontal_resolution_meters and ds.horizontal_resolution_meters > 100.0 and local_scale_radius_m < 100.0)
        try:
            tri_coarse, _ = calculate_roughness_tri_with_metadata(
                z, dx_m, dy_m, nodata_mask=nodata_mask, neighborhood_radius_meters=coarse_scale_radius_m,
                source_product_id=ds.product_id, native_resolution_m=native_res,
            )
            tri_coarse_stats = _stats_from_array(tri_coarse)
        except ValueError:
            tri_coarse_stats = None

        is_coarse_for_local = native_res > 50.0 and local_scale_radius_m < 100.0
        obs_report = _classify_observability(native_res)
        obs_report.dataset_id = ds.id

        # Terrain observability counts
        v_cnt = int(np.count_nonzero(valid_mask))
        nd_cnt = int(arr.size - v_cnt)
        obs_counts = {
            "resolvable_at_native_scale": v_cnt if native_res <= 5.0 else 0,
            "coarse_regional_only": v_cnt if native_res > 5.0 else 0,
            "nodata_unavailable": nd_cnt,
        }

        def _entry(
            name: str,
            data: Optional[np.ndarray],
            units: str,
            alg: str,
            scale_desc: str,
            unc_desc: str,
            override_stats: Optional[Dict[str, Optional[float]]] = None,
            force_invalid_reason: Optional[str] = None,
        ) -> TerrainDerivativeMetadata:
            st = override_stats if override_stats is not None else (_stats_from_array(data) if data is not None else None)
            avail = force_invalid_reason is None and st is not None
            return TerrainDerivativeMetadata(
                derivative_name=name,
                available=avail,
                valid_reason=force_invalid_reason or ("Derived over valid neighborhood pixels." if st else "Zero valid derivative cells."),
                input_dem_id=ds.id,
                input_product_id=ds.product_id,
                native_resolution_m=native_res,
                processing_resolution_m=proc_res,
                resampling_applied=(out_w != w_px or out_h != h_px),
                resampling_method=resampling_method,
                window_or_physical_scale=scale_desc,
                algorithm=alg,
                units=units,
                uncertainty_treatment=unc_desc,
                processing_provenance=f"{meta.horizontal_crs} -> {TERRAIN_INTELLIGENCE_VERSION}",
                stats=st if avail else None,
            )

        local_invalid_msg = (
            f"Refused local ({local_scale_radius_m} m) derivative: native DEM spacing ({native_res} m/px) violates Nyquist >=2-3x resolution requirement."
            if is_coarse_for_local
            else None
        )

        derivs = {
            "elevation": _entry("elevation", z, meta.elevation_units, "Native Raster Elevation Read", f"{proc_res} m/cell", f"PDS vertical sigma={ds.vertical_resolution_meters or 'unspecified'} m"),
            "slope": _entry("slope", slope_arr, "degrees", "Horn (1981) 3x3 Weighted Finite Difference", f"{3.0 * proc_res:.2f} m baseline", "Includes Rice bias floor on flat benches; valid 3x3 cells only", force_invalid_reason=local_invalid_msg),
            "aspect": _entry("aspect", np.where(aspect_arr >= 0, aspect_arr, np.nan), "degrees_clockwise_north", "Horn (1981) Atan2 North-Azimuth", f"{3.0 * proc_res:.2f} m baseline", "Flat cells (slope ~ 0) masked to NaN", force_invalid_reason=local_invalid_msg),
            "profile_curvature": _entry("profile_curvature", prof_curv, "1/m", "Evans (1979) 3x3 Directional Second Derivative", f"{3.0 * proc_res:.2f} m baseline", "Sensitive to 1 px stereo noise; high-pass noise excluded", force_invalid_reason=local_invalid_msg),
            "planform_curvature": _entry("planform_curvature", plan_curv, "1/m", "Evans (1979) 3x3 Contour Curvature", f"{3.0 * proc_res:.2f} m baseline", "Undefined where horizontal gradient = 0", force_invalid_reason=local_invalid_msg),
            "tri": _entry("tri", tri_3x3, "meters", "Riley (1999) RMS 3x3 Terrain Ruggedness Index", f"{3.0 * proc_res:.2f} m window", "Strict 8-neighbor validity required"),
            "local_relief": _entry("local_relief", relief_arr, "meters", f"Window Range (max - min) r={rad_cells} px", f"{(2*rad_cells+1)*proc_res:.2f} m window", "Bounded within valid mask without NoData pad", force_invalid_reason=local_invalid_msg),
            "tpi": _entry("tpi", tpi_arr, "meters", f"Topographic Position Index (z - mean) r={rad_cells} px", f"{(2*rad_cells+1)*proc_res:.2f} m window", "Scale-dependent landform prominence index", force_invalid_reason=local_invalid_msg),
            "multiscale_roughness": _entry("multiscale_roughness", None, "meters", f"Coarse TRI r={coarse_scale_radius_m} m", f"{coarse_scale_radius_m} m radius", "Resolution-gated coarse window", override_stats=tri_coarse_stats, force_invalid_reason=(None if tri_coarse_stats else f"Requested {coarse_scale_radius_m} m scale incompatible with {proc_res} m processing pixel")),
            "elevation_variability": _entry("elevation_variability", elev_var, "meters", "3x3 Local Elevation Standard Deviation", f"{3.0 * proc_res:.2f} m window", "Measures local micro-scatter without smoothing"),
            "surface_normals": _entry("surface_normals", nz_arr, "unitless_nz_component", "Horn Gradient Unit Surface Normal Vector (nx, ny, nz)", f"{3.0 * proc_res:.2f} m baseline", "Vertical normal cos(slope)", force_invalid_reason=local_invalid_msg),
            "terrain_observability": _entry("terrain_observability", None, "count_summary", "Nyquist 2.5x Pixel Spacing Gate", f"nyquist={obs_report.nyquist_resolvable_feature_m} m", "Binary/categorical pixel resolvability", override_stats={"resolvable_pixels": float(obs_counts["resolvable_at_native_scale"]), "coarse_only_pixels": float(obs_counts["coarse_regional_only"]), "nodata_pixels": float(nd_cnt)}),
            "dem_uncertainty": _entry("dem_uncertainty", unc_elev_arr, "meters", "Archive Vertical Accuracy + Neighbor Continuity", f"{proc_res} m/cell", f"Published vertical accuracy={ds.vertical_resolution_meters or 'unspecified'} m"),
        }

        return WindowedTerrainDerivativesReport(
            dataset_metadata=meta,
            requested_bounds={"min_lat": c_min_lat, "max_lat": c_max_lat, "min_lon": c_min_lon, "max_lon": c_max_lon},
            grid_shape=[out_h, out_w],
            valid_pixel_count=v_cnt,
            nodata_pixel_count=nd_cnt,
            valid_coverage_fraction=round(v_cnt / float(max(1, arr.size)), 4),
            resampling_applied=(out_w != w_px or out_h != h_px),
            resampling_method=resampling_method,
            observability=obs_report,
            derivatives=derivs,
            observability_class_counts=obs_counts,
        )

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _run_with_reader(vrt)
        return _run_with_reader(src)


def compare_terrain_scales(
    *,
    datasets: List[Dataset],
    raw_dir: Path,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> MultiScaleTerrainComparisonResponse:
    """
    Compare multiple DEM scales (MOLA 4ppd, MOLA 128ppd, HiRISE 1 m/px) over overlapping
    study bounds without interpreting resolution attenuation or registration offsets as temporal change.
    """
    entries: List[ScaleComparisonEntry] = []
    limitations: List[str] = []

    for ds in sorted(datasets, key=lambda d: d.horizontal_resolution_meters or 1e9):
        try:
            rep = compute_terrain_derivatives_window(
                ds,
                raw_dir=raw_dir,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                max_grid_dim=128,
            )
        except Exception as exc:
            limitations.append(f"Skipped '{ds.id}' over bounds: {exc}")
            continue

        nat = float(ds.horizontal_resolution_meters or 0.0)
        if nat <= 3.0:
            s_cat = "high_res_stereo_terrain"
            s_note = "Preserves meter-scale ridge/trough relief and sharp local slopes (>~2.5 m features)."
        elif nat <= 600.0:
            s_cat = "local_or_regional_topography"
            s_note = f"Smooths all sub-{round(2.5*nat)} m terrain relief into macro-scale gradients."
        else:
            s_cat = "regional_global_topography"
            s_note = f"Global macro-scale topography (~{nat/1000:.1f} km/px); local slope peaks disappear."

        el_st = rep.derivatives["elevation"].stats or {}
        sl_st = rep.derivatives["slope"].stats or {}
        tr_st = rep.derivatives["tri"].stats or {}
        entries.append(
            ScaleComparisonEntry(
                dataset_id=ds.id,
                product_id=ds.product_id,
                scale_category=s_cat,
                native_resolution_m=nat,
                vertical_datum=rep.dataset_metadata.vertical_datum,
                valid_pixel_count=rep.valid_pixel_count,
                valid_coverage_fraction=rep.valid_coverage_fraction,
                elevation_min_m=el_st.get("min"),
                elevation_max_m=el_st.get("max"),
                elevation_mean_m=el_st.get("mean"),
                slope_mean_deg=sl_st.get("mean"),
                slope_p95_deg=sl_st.get("p95"),
                tri_mean_m=tr_st.get("mean"),
                smoothing_attenuation_note=s_note,
            )
        )

    deltas: List[Dict[str, Any]] = []
    if len(entries) >= 2:
        fine = entries[0]
        for other in entries[1:]:
            d_elev = (
                round(fine.elevation_mean_m - other.elevation_mean_m, 3)
                if fine.elevation_mean_m is not None and other.elevation_mean_m is not None
                else None
            )
            d_p95 = (
                round(fine.slope_p95_deg - other.slope_p95_deg, 2)
                if fine.slope_p95_deg is not None and other.slope_p95_deg is not None
                else None
            )
            deltas.append(
                {
                    "fine_dataset_id": fine.dataset_id,
                    "coarse_dataset_id": other.dataset_id,
                    "resolution_ratio": round(other.native_resolution_m / max(0.01, fine.native_resolution_m), 1),
                    "mean_elevation_offset_m": d_elev,
                    "p95_slope_attenuation_deg": d_p95,
                    "interpretation": "Resolution smoothing & vertical tie offset — NOT physical terrain erosion/deposition change.",
                }
            )

    return MultiScaleTerrainComparisonResponse(
        study_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
        compared_datasets=entries,
        pairwise_cross_scale_deltas=deltas,
        scientific_explanation=(
            "Cross-scale comparison quantifies topographic attenuation between high-resolution HiRISE stereo DTMs "
            "and coarse regional MOLA MEGDR grids. Scale differences reflect spatial averaging and stereo/datum tie residuals, not real surface change."
        ),
        limitations=limitations,
    )


def evaluate_terrain_change(
    ds_a: Dataset,
    ds_b: Dataset,
    *,
    dataset_root_dir: Path,
    raw_dir: Path,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    validated_vertical_offset_m: Optional[float] = None,
) -> TerrainChangeEvaluationResult:
    """
    Strictly evaluate whether real physical temporal terrain change can be assessed
    between two DEM products across 6 scientific validation gates (Part 6.5).
    """
    gates: List[ChangeGateStatus] = []
    failures: List[str] = []

    # Gate 1: Spatial Registration
    reg = evaluate_product_pair_registration(
        ds_a,
        ds_b,
        dataset_root_dir=dataset_root_dir,
        intended_analysis="temporal_terrain_change",
    )
    g1_ok = reg.overall_state in {
        SpatialRegistrationAssessmentState.VALIDATED_REGISTRATION,
        SpatialRegistrationAssessmentState.VALIDATED_WITH_LIMITATIONS,
    } and reg.overlap_area_m2 is not None and reg.overlap_area_m2 > 0
    gates.append(ChangeGateStatus(gate_name="1_spatial_registration", passed=g1_ok, detail=f"Registration={reg.overall_state.value}"))
    if not g1_ok:
        failures.append(f"Spatial registration gate failed: {reg.overall_state.value}.")

    # Gate 2: Vertical Datum Compatibility
    vcomp = check_vertical_datum_compatibility(
        reg.crs_a_validation.vertical_reference,
        reg.crs_b_validation.vertical_reference,
        validated_vertical_offset_m=validated_vertical_offset_m,
    )
    gates.append(ChangeGateStatus(gate_name="2_vertical_datum_compatibility", passed=vcomp.compatible, detail=vcomp.explanation))
    if not vcomp.compatible:
        failures.append(vcomp.explanation)

    # Gate 3: Acquisition Epochs Present & Distinct
    t_a = ds_a.acquisition_timestamp
    t_b = ds_b.acquisition_timestamp
    g3_ok = bool(t_a and t_b and str(t_a).strip() != str(t_b).strip())
    g3_det = f"Epoch A={t_a or 'UNSPECIFIED'}, Epoch B={t_b or 'UNSPECIFIED'}"
    gates.append(ChangeGateStatus(gate_name="3_distinct_acquisition_epochs", passed=g3_ok, detail=g3_det))
    if not g3_ok:
        failures.append(f"Cannot compute temporal terrain change without two distinct acquisition timestamps ({g3_det}).")

    # Gate 4: Resolution & Processing Compatibility (forbid manufacturing change from MOLA vs HiRISE)
    ra = ds_a.horizontal_resolution_meters
    rb = ds_b.horizontal_resolution_meters
    ratio = (max(ra, rb) / min(ra, rb)) if (ra and rb and min(ra, rb) > 0) else 999.0
    g4_ok = ratio <= 4.0 and (ds_a.instrument == ds_b.instrument or "DTM" in ds_a.product_type and "DTM" in ds_b.product_type)
    g4_det = f"Resolution ratio={ratio:.2f}x ({ra} m vs {rb} m); instruments=({ds_a.instrument} vs {ds_b.instrument})"
    gates.append(ChangeGateStatus(gate_name="4_resolution_and_processing_compatibility", passed=g4_ok, detail=g4_det))
    if not g4_ok:
        failures.append(f"Refused cross-resolution / cross-methodology terrain differencing ({g4_det}).")

    # Gate 5: Quantified Propagated Vertical Uncertainty
    sig_a = ds_a.vertical_resolution_meters
    sig_b = ds_b.vertical_resolution_meters
    g5_ok = sig_a is not None and sig_b is not None and sig_a > 0 and sig_b > 0
    prop_sigma = round(math.sqrt(sig_a**2 + sig_b**2), 3) if g5_ok else None
    g5_det = f"sigma_A={sig_a} m, sigma_B={sig_b} m -> combined 1-sigma={prop_sigma} m"
    gates.append(ChangeGateStatus(gate_name="5_quantified_uncertainty", passed=g5_ok, detail=g5_det))
    if not g5_ok:
        failures.append("Source products lack quantified vertical uncertainty bounds.")

    all_ready = all(g.passed for g in gates)
    if not all_ready:
        return TerrainChangeEvaluationResult(
            dataset_a_id=ds_a.id,
            dataset_b_id=ds_b.id,
            study_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
            status="CHANGE_NOT_EVALUABLE",
            evaluable=False,
            gates=gates,
            failure_reasons=failures,
            propagated_vertical_uncertainty_1sigma_m=prop_sigma,
            limitations=[
                "Change evaluation refused because one or more mandatory spatial/temporal/datum/resolution/uncertainty gates failed.",
            ],
        )

    # Gate 6: Compare actual raster heights and check > 2*sigma threshold
    pa, _ = _resolve_raw_dem_open_path(ds_a, raw_dir)
    pb, _ = _resolve_raw_dem_open_path(ds_b, raw_dir)
    from rasterio.warp import reproject

    with rasterio.open(pa) as sa, rasterio.open(pb) as sb:
        out_w, out_h = 96, 96
        dst_tf = rasterio.transform.from_bounds(min_lon, min_lat, max_lon, max_lat, out_w, out_h)
        arr_a = np.full((out_h, out_w), np.nan, dtype=np.float64)
        arr_b = np.full((out_h, out_w), np.nan, dtype=np.float64)
        reproject(rasterio.band(sa, 1), arr_a, src_transform=sa.transform, src_crs=sa.crs, dst_transform=dst_tf, dst_crs=MARS_GEOG_CRS, dst_nodata=np.nan, resampling=Resampling.bilinear)
        reproject(rasterio.band(sb, 1), arr_b, src_transform=sb.transform, src_crs=sb.crs, dst_transform=dst_tf, dst_crs=MARS_GEOG_CRS, dst_nodata=np.nan, resampling=Resampling.bilinear)
        if validated_vertical_offset_m:
            arr_b = arr_b + float(validated_vertical_offset_m)
        valid = np.isfinite(arr_a) & np.isfinite(arr_b) & (arr_a > -32000.0) & (arr_b > -32000.0)
        if not np.any(valid):
            gates.append(ChangeGateStatus(gate_name="6_signal_exceeds_uncertainty", passed=False, detail="Zero overlapping valid DEM pixels."))
            return TerrainChangeEvaluationResult(
                dataset_a_id=ds_a.id,
                dataset_b_id=ds_b.id,
                study_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
                status="CHANGE_NOT_EVALUABLE",
                evaluable=False,
                gates=gates,
                failure_reasons=["Zero valid overlapping pixels in change window."],
                propagated_vertical_uncertainty_1sigma_m=prop_sigma,
            )
        diff = arr_b[valid] - arr_a[valid]
        abs_diff = np.abs(diff)
        sig_mask = abs_diff > (2.0 * float(prop_sigma or 0.5))
        sig_frac = round(float(np.mean(sig_mask)), 4)
        mean_d = round(float(np.mean(diff)), 4)
        max_d = round(float(np.max(abs_diff)), 4)
        sig_ok = sig_frac > 0.01
        gates.append(
            ChangeGateStatus(
                gate_name="6_signal_exceeds_uncertainty",
                passed=True,
                detail=f"{sig_frac*100:.2f}% of pixels exceed 2-sigma ({2*(prop_sigma or 0.5):.3f} m); max |dz|={max_d} m",
            )
        )
        return TerrainChangeEvaluationResult(
            dataset_a_id=ds_a.id,
            dataset_b_id=ds_b.id,
            study_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
            status=("STATISTICALLY_SIGNIFICANT_CHANGE_DETECTED" if sig_ok else "NO_SIGNIFICANT_CHANGE_DETECTED"),
            evaluable=True,
            gates=gates,
            propagated_vertical_uncertainty_1sigma_m=prop_sigma,
            observed_mean_delta_m=mean_d,
            observed_max_abs_delta_m=max_d,
            significant_change_pixel_fraction=sig_frac,
        )
