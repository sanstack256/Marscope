"""
MARSCOPE Spatial Coverage & Unknown-Data Intelligence Engine
Martian Surface Intelligence & Exploration System

Explicitly distinguishes five spatial coverage states:
  1. outside_source_footprint
  2. inside_footprint_nodata
  3. valid_source_data
  4. insufficient_resolution_for_analysis
  5. derivative_unavailable_invalid_neighborhood

Quantifies covered, uncovered, valid, and no-data surface area on the IAU 2000
Mars reference sphere without ever expanding the requested study region.
"""

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT

from app.geospatial.alignment import FootprintPlanError, plan_clip_to_bounding_box
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, angular_displacement_to_metric
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.models import TerrainCoverageState
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.schemas import CoverageIntelligenceResponse
from app.schemas.dataset import Dataset
from app.schemas.terrain import InsufficientCoverageReport
from app.terrain.aspect import calculate_aspect
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


def mars_spherical_box_area_km2(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> float:
    """
    Calculate surface area in km^2 of a lat/lon bounding box on the IAU 2000 Mars sphere.
    """
    if max_lat <= min_lat or max_lon <= min_lon:
        return 0.0
    r_km = MARS_EQUATORIAL_RADIUS_M / 1000.0
    dlon_rad = math.radians(min(360.0, max_lon - min_lon))
    sin_diff = abs(math.sin(math.radians(max_lat)) - math.sin(math.radians(min_lat)))
    return float((r_km ** 2) * dlon_rad * sin_diff)


def _normalize_bounds_180(bounds: Dict[str, float]) -> Tuple[float, float, float, float]:
    """Normalize (min_lat, max_lat, min_lon, max_lon) into [-180, 180] longitude convention."""
    min_lat = float(bounds["min_lat"])
    max_lat = float(bounds["max_lat"])
    min_lon = float(bounds["min_lon"])
    max_lon = float(bounds["max_lon"])
    if min_lon > 180.0:
        min_lon -= 360.0
    if max_lon > 180.0:
        max_lon -= 360.0
    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon
    return min_lat, max_lat, min_lon, max_lon


def _resolve_raw_dem_open_path(dataset: Dataset, raw_dir: Path) -> Tuple[Path, Optional[Path]]:
    raw_file: Optional[Path] = None
    if dataset.local_file_path:
        p = Path(dataset.local_file_path)
        if p.exists():
            raw_file = p
    if raw_file is None:
        for cand in (
            raw_dir / dataset.product_id.lower(),
            raw_dir / dataset.product_id,
            raw_dir / dataset.product_id.upper(),
        ):
            if cand.exists():
                raw_file = cand
                break
    if raw_file is None and raw_dir.exists():
        target_lower = dataset.product_id.lower()
        for entry in raw_dir.iterdir():
            if entry.is_file() and entry.name.lower() == target_lower:
                raw_file = entry
                break
    if raw_file is None or not raw_file.exists():
        from app.ingestion.bootstrap import load_bootstrap_manifest
        from app.ingestion.gcs_storage import GCSDatasetStore

        gcs_store = GCSDatasetStore.from_env()
        if gcs_store is not None:
            manifest_path = raw_dir.parent / "bootstrap_manifest.json"
            expected_sha = dataset.sha256_checksum
            expected_size = dataset.file_size_bytes
            if manifest_path.exists():
                manifest = load_bootstrap_manifest(manifest_path)
                for entry in manifest.get("products", []):
                    if entry.get("dataset_id") == dataset.id:
                        expected_sha = expected_sha or entry.get("expected_sha256")
                        expected_size = expected_size or entry.get("expected_size_bytes")
                        break
            retrieved = gcs_store.ensure_raw_dataset_on_disk(
                dataset,
                raw_dir,
                expected_sha256=expected_sha,
                expected_size_bytes=expected_size,
            )
            if retrieved is not None and retrieved.exists():
                raw_file = retrieved

    if raw_file is None or not raw_file.exists():
        raise FileNotFoundError(f"Raw DEM file for '{dataset.id}' is not present in {raw_dir}.")

    lbl_path: Optional[Path] = None
    for sfx in (".lbl", ".LBL"):
        cand_l = raw_file.with_suffix(sfx)
        if cand_l.exists():
            lbl_path = cand_l
            break
    open_path = lbl_path if (lbl_path and raw_file.suffix.lower() == ".img") else raw_file
    return open_path, lbl_path


def evaluate_region_coverage_intelligence(
    *,
    dataset: Dataset,
    raw_dir: Path,
    requested_bounds: Dict[str, float],
    roughness_radius_meters: Optional[float] = None,
) -> CoverageIntelligenceResponse:
    """
    Evaluate spatial coverage and unknown-data states for `requested_bounds` against `dataset`.
    Never enlarges `requested_bounds`.
    """
    open_path, lbl_path = _resolve_raw_dem_open_path(dataset, raw_dir)
    lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}

    req_min_lat, req_max_lat, req_min_lon, req_max_lon = _normalize_bounds_180(requested_bounds)
    req_norm = {
        "min_lat": req_min_lat,
        "max_lat": req_max_lat,
        "min_lon": req_min_lon,
        "max_lon": req_max_lon,
    }
    req_area_km2 = mars_spherical_box_area_km2(req_min_lat, req_max_lat, req_min_lon, req_max_lon)

    plan = plan_clip_to_bounding_box(
        source_raster_path=open_path,
        min_lon=req_min_lon,
        min_lat=req_min_lat,
        max_lon=req_max_lon,
        max_lat=req_max_lat,
        output_crs_str="IAU2000:MARS_SPHERE",
    )

    src_bounds = plan["source_bounds"]
    inter_bounds = plan["intersecting_bounds"]

    center_lat = 0.5 * (req_min_lat + req_max_lat)
    ps = plan["source_pixel_size"]
    dx_deg = float(ps["x"])
    dy_deg = float(ps["y"])
    dx_m, dy_m = angular_displacement_to_metric(
        center_lat,
        dx_deg,
        dy_deg,
    )
    suitability = evaluate_dem_resolution_suitability(
        native_resolution_m=dataset.horizontal_resolution_meters or dx_m,
        effective_resolution_m=dx_m,
        dem_available=True,
    )

    state_counts: Dict[str, int] = {s.value: 0 for s in TerrainCoverageState}
    notes: List[str] = []

    has_overlap = bool(plan["overlaps_source"]) and inter_bounds is not None
    avail_px = plan["available_pixel_dimensions"]
    avail_w = int(avail_px["width"])
    avail_h = int(avail_px["height"])

    if not has_overlap or avail_w < 3 or avail_h < 3:
        if not has_overlap:
            reason_msg = (
                f"Requested study bounds {req_norm} do not overlap source DEM footprint {src_bounds}; "
                "requested bounds were NOT enlarged."
            )
            next_act = "Specify study bounds within the source DEM geographic footprint."
        else:
            reason_msg = (
                f"Requested study bounds intersect only {avail_w}x{avail_h} whole source pixels on '{dataset.id}' "
                f"(~{dx_m:.0f} m/pixel), which is smaller than the minimum 3x3 pixel window required for Horn "
                "3x3 slope/aspect and 3x3 TRI roughness derivatives. Requested bounds were NOT enlarged."
            )
            next_act = (
                "Either request a broader regional window (>= 3x3 source pixels) or acquire a higher-resolution "
                "local DEM (HiRISE / CTX) covering the study area."
            )

        cov_area_km2 = (
            mars_spherical_box_area_km2(
                inter_bounds["min_lat"],
                inter_bounds["max_lat"],
                inter_bounds["min_lon"],
                inter_bounds["max_lon"],
            )
            if inter_bounds
            else 0.0
        )
        uncov_area_km2 = max(0.0, req_area_km2 - cov_area_km2)
        n_cells = max(1, avail_w * avail_h)
        if not has_overlap:
            state_counts[TerrainCoverageState.OUTSIDE_SOURCE_FOOTPRINT.value] = n_cells
        else:
            state_counts[TerrainCoverageState.INSUFFICIENT_RESOLUTION_FOR_ANALYSIS.value] = n_cells

        report = InsufficientCoverageReport(
            requested_bounds=req_norm,
            requested_bounds_modified=False,
            source_coverage_bounds=src_bounds,
            intersecting_bounds=inter_bounds,
            requested_pixel_dimensions=plan["requested_pixel_dimensions"],
            available_pixel_dimensions=avail_px,
            source_resolution={
                "dx_deg": dx_deg,
                "dy_deg": dy_deg,
                "dx_meters": round(dx_m, 3),
                "dy_meters": round(dy_m, 3),
            },
            minimum_resolution_requirement={
                "min_width_pixels": 3,
                "min_height_pixels": 3,
                "kernel_size": "3x3",
                "reason": "Horn 3x3 slope/aspect and 3x3 metric TRI require at least 3x3 whole source pixels.",
            },
            insufficient_coverage_reason=reason_msg,
            supported_products=["elevation"] if (has_overlap and (avail_w * avail_h) > 0) else [],
            unsupported_derivative_products=["slope", "aspect", "roughness"],
            next_action=next_act,
        )
        notes.append(reason_msg)
        return CoverageIntelligenceResponse(
            dataset_id=dataset.id,
            source_product_id=dataset.product_id,
            crs="IAU2000:MARS_SPHERE",
            requested_bounds=req_norm,
            requested_bounds_modified=False,
            source_footprint_bounds=src_bounds,
            overlap_bounds=inter_bounds,
            has_spatial_overlap=has_overlap,
            sufficient_for_3x3_derivatives=False,
            requested_area_km2=round(req_area_km2, 4),
            covered_area_km2=round(cov_area_km2, 4),
            uncovered_area_km2=round(uncov_area_km2, 4),
            valid_elevation_area_km2=0.0,
            nodata_elevation_area_km2=0.0,
            valid_derivative_area_km2=0.0,
            valid_elevation_percentage_of_requested=0.0,
            valid_derivative_percentage_of_requested=0.0,
            pixel_counts={
                "width": avail_w,
                "height": avail_h,
                "total_window_pixels": avail_w * avail_h,
                "valid_elevation_pixels": 0,
                "nodata_elevation_pixels": 0,
                "valid_derivative_pixels": 0,
            },
            coverage_state_counts=state_counts,
            derivative_availability={
                "elevation": has_overlap and (avail_w * avail_h > 0),
                "slope": False,
                "aspect": False,
                "roughness": False,
            },
            resolution_suitability=suitability,
            insufficient_coverage_report=report,
            notes=notes,
        )

    # Valid window >= 3x3 pixels: read only the windowed subset
    win = rasterio.windows.Window(**plan["window"])
    rio_crs = rasterio.crs.CRS.from_proj4(
        f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
    )
    with rasterio.open(open_path) as src:
        nodata = src.nodata
        if nodata is None and lbl_meta.get("missing_constant") is not None:
            try:
                nodata = float(lbl_meta["missing_constant"])
            except (TypeError, ValueError):
                nodata = -32768.0
        elif nodata is None:
            nodata = -32768.0

        max_cov_pixels = 2_000_000
        win_px = int(win.width) * int(win.height)
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=rio_crs) as vrt:
                if win_px > max_cov_pixels:
                    from rasterio.enums import Resampling
                    stride = max(2, int(math.ceil(math.sqrt(win_px / float(max_cov_pixels)))))
                    out_h = max(3, int(win.height) // stride)
                    out_w = max(3, int(win.width) // stride)
                    dem_arr = vrt.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.nearest).astype(np.float64)
                    dx_m *= (float(win.width) / float(out_w))
                    dy_m *= (float(win.height) / float(out_h))
                else:
                    dem_arr = vrt.read(1, window=win).astype(np.float64)
        else:
            if win_px > max_cov_pixels:
                from rasterio.enums import Resampling
                stride = max(2, int(math.ceil(math.sqrt(win_px / float(max_cov_pixels)))))
                out_h = max(3, int(win.height) // stride)
                out_w = max(3, int(win.width) // stride)
                dem_arr = src.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.nearest).astype(np.float64)
                dx_m *= (float(win.width) / float(out_w))
                dy_m *= (float(win.height) / float(out_h))
            else:
                dem_arr = src.read(1, window=win).astype(np.float64)

    valid_elev_mask = np.isfinite(dem_arr) & (dem_arr != float(nodata)) & (dem_arr > -32000.0)
    nodata_mask = ~valid_elev_mask
    slope_arr, _ = calculate_slope(dem_arr, dx_m, dy_m, nodata_mask=nodata_mask)
    _ = calculate_aspect(dem_arr, dx_m, dy_m, nodata_mask=nodata_mask)
    tri_arr, _ = calculate_roughness_tri_with_metadata(
        dem_arr,
        dx_m,
        dy_m,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=roughness_radius_meters,
    )

    valid_deriv_mask = np.isfinite(slope_arr) & np.isfinite(tri_arr)
    nodata_inside_mask = ~valid_elev_mask
    deriv_unavail_mask = valid_elev_mask & (~valid_deriv_mask)
    fully_valid_mask = valid_elev_mask & valid_deriv_mask

    total_px = int(dem_arr.size)
    valid_elev_px = int(np.count_nonzero(valid_elev_mask))
    nodata_elev_px = int(np.count_nonzero(nodata_inside_mask))
    valid_deriv_px = int(np.count_nonzero(fully_valid_mask))
    deriv_unavail_px = int(np.count_nonzero(deriv_unavail_mask))

    state_counts[TerrainCoverageState.VALID_SOURCE_DATA.value] = valid_deriv_px
    state_counts[TerrainCoverageState.DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD.value] = deriv_unavail_px
    state_counts[TerrainCoverageState.INSIDE_FOOTPRINT_NODATA.value] = nodata_elev_px

    cov_area_km2 = (
        mars_spherical_box_area_km2(
            inter_bounds["min_lat"],
            inter_bounds["max_lat"],
            inter_bounds["min_lon"],
            inter_bounds["max_lon"],
        )
        if inter_bounds
        else req_area_km2
    )
    uncov_area_km2 = max(0.0, req_area_km2 - cov_area_km2)
    cell_area_km2 = (dx_m * dy_m) / 1e6
    valid_elev_area_km2 = min(cov_area_km2, valid_elev_px * cell_area_km2) if total_px > 0 else 0.0
    if nodata_elev_px == 0:
        valid_elev_area_km2 = cov_area_km2
        nodata_area_km2 = 0.0
    else:
        nodata_area_km2 = max(0.0, cov_area_km2 - valid_elev_area_km2)

    valid_deriv_area_km2 = (
        cov_area_km2 * (valid_deriv_px / total_px) if total_px > 0 else 0.0
    )

    valid_elev_pct = (valid_elev_area_km2 / req_area_km2 * 100.0) if req_area_km2 > 0 else 0.0
    valid_deriv_pct = (valid_deriv_area_km2 / req_area_km2 * 100.0) if req_area_km2 > 0 else 0.0

    if deriv_unavail_px > 0:
        notes.append(
            f"{deriv_unavail_px} of {total_px} window cells have valid elevation but lack a complete 3x3 "
            "valid neighborhood (window boundary or adjacent no-data cell), so slope/aspect/TRI are marked "
            "'derivative_unavailable_invalid_neighborhood'."
        )
    if dx_m >= 1000.0:
        notes.append(
            f"Source pixel spacing is ~{dx_m:.0f} m x {dy_m:.0f} m; suitable for regional elevation and "
            "regional roughness, but insufficient for local human-scale slope or obstacle detection."
        )

    return CoverageIntelligenceResponse(
        dataset_id=dataset.id,
        source_product_id=dataset.product_id,
        crs="IAU2000:MARS_SPHERE",
        requested_bounds=req_norm,
        requested_bounds_modified=False,
        source_footprint_bounds=src_bounds,
        overlap_bounds=inter_bounds,
        has_spatial_overlap=True,
        sufficient_for_3x3_derivatives=(valid_deriv_px > 0),
        requested_area_km2=round(req_area_km2, 4),
        covered_area_km2=round(cov_area_km2, 4),
        uncovered_area_km2=round(uncov_area_km2, 4),
        valid_elevation_area_km2=round(valid_elev_area_km2, 4),
        nodata_elevation_area_km2=round(nodata_area_km2, 4),
        valid_derivative_area_km2=round(valid_deriv_area_km2, 4),
        valid_elevation_percentage_of_requested=round(valid_elev_pct, 2),
        valid_derivative_percentage_of_requested=round(valid_deriv_pct, 2),
        pixel_counts={
            "width": int(dem_arr.shape[1]),
            "height": int(dem_arr.shape[0]),
            "total_window_pixels": total_px,
            "valid_elevation_pixels": valid_elev_px,
            "nodata_elevation_pixels": nodata_elev_px,
            "valid_derivative_pixels": valid_deriv_px,
            "boundary_or_invalid_neighborhood_pixels": deriv_unavail_px,
        },
        coverage_state_counts=state_counts,
        derivative_availability={
            "elevation": valid_elev_px > 0,
            "slope": valid_deriv_px > 0,
            "aspect": valid_deriv_px > 0,
            "roughness": valid_deriv_px > 0,
        },
        resolution_suitability=suitability,
        insufficient_coverage_report=None,
        notes=notes,
    )
