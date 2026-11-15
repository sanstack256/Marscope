"""
MARSCOPE Windowed Terrain Feature Extraction & Elevation Profile Engine
Martian Surface Intelligence & Exploration System

Computes physical terrain properties strictly from verified DEM windows:
  - Elevation (meters)
  - Horn 3x3 slope (degrees)
  - Compass aspect [0, 360) clockwise from North (flat cells undefined)
  - Resolution-aware metric Terrain Ruggedness Index (TRI, meters)
  - Spatially explicit elevation gain/loss profiles along 2 points or a
    user-supplied polyline without route optimization.
"""

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
import rasterio
from rasterio.transform import xy as rio_xy
from rasterio.vrt import WarpedVRT

from app.geospatial.alignment import FootprintPlanError, plan_clip_to_bounding_box
from app.geospatial.crs import (
    MARS_EQUATORIAL_RADIUS_M,
    angular_displacement_to_metric,
    normalize_longitude_180,
    normalize_longitude_360,
)
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.coverage import _normalize_bounds_180, _resolve_raw_dem_open_path
from app.mobility.models import TerrainCoverageState
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.schemas import (
    ElevationProfileGapSegment,
    ElevationProfileResponse,
    ElevationProfileSample,
    GeoPoint,
    TerrainFeatureCell,
    TerrainFeaturesWindowResponse,
)
from app.mobility.uncertainty import build_mobility_uncertainty_summary
from app.schemas.dataset import Dataset
from app.schemas.terrain import InsufficientCoverageReport
from app.terrain.aspect import calculate_aspect
from app.terrain.processor import (
    FOOTPRINT_POLICY,
    PROCESSING_VERSION,
    InsufficientDEMCoverageError,
)
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope
from app.terrain.summary import compute_band_stats


def mars_great_circle_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate great-circle surface distance in meters on the IAU 2000 Mars sphere (R = 3,396,190 m).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlon = math.radians(normalize_longitude_180(lon2 - lon1))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(max(0.0, a)), math.sqrt(max(0.0, 1.0 - a)))
    return float(MARS_EQUATORIAL_RADIUS_M * c)


def interpolate_mars_polyline_samples(
    waypoints: Sequence[GeoPoint],
    sample_count: int,
) -> List[Dict[str, float]]:
    """
    Generate `sample_count` evenly spaced coordinate samples along a sequence of >= 2 Mars waypoints.
    Preserves exact start and end coordinates and records cumulative and segment horizontal distances.
    """
    if len(waypoints) < 2:
        raise ValueError("At least 2 waypoints are required to construct an elevation profile.")
    if sample_count < 2:
        raise ValueError("sample_count must be >= 2.")

    seg_lengths: List[float] = []
    cum_wp_dist: List[float] = [0.0]
    for idx in range(len(waypoints) - 1):
        p0 = waypoints[idx]
        p1 = waypoints[idx + 1]
        d = mars_great_circle_distance_meters(p0.lat, p0.lon, p1.lat, p1.lon)
        seg_lengths.append(d)
        cum_wp_dist.append(cum_wp_dist[-1] + d)

    total_dist = cum_wp_dist[-1]
    if total_dist <= 0.0:
        return [
            {
                "sample_index": i,
                "lat": float(waypoints[0].lat),
                "lon_180": normalize_longitude_180(waypoints[0].lon),
                "lon_east": normalize_longitude_360(waypoints[0].lon),
                "cumulative_distance_meters": 0.0,
                "segment_distance_meters": 0.0,
            }
            for i in range(sample_count)
        ]

    samples: List[Dict[str, float]] = []
    step_m = total_dist / float(sample_count - 1)

    for i in range(sample_count):
        target_d = min(total_dist, i * step_m) if i < sample_count - 1 else total_dist
        # Locate active waypoint segment
        seg_idx = 0
        for s_i in range(len(seg_lengths)):
            if cum_wp_dist[s_i + 1] >= target_d or s_i == len(seg_lengths) - 1:
                seg_idx = s_i
                break

        seg_d = seg_lengths[seg_idx]
        frac = (target_d - cum_wp_dist[seg_idx]) / seg_d if seg_d > 0.0 else 0.0
        frac = max(0.0, min(1.0, frac))

        p0 = waypoints[seg_idx]
        p1 = waypoints[seg_idx + 1]
        lat = p0.lat + frac * (p1.lat - p0.lat)
        dlon = normalize_longitude_180(p1.lon - p0.lon)
        lon_180 = normalize_longitude_180(p0.lon + frac * dlon)
        lon_east = normalize_longitude_360(lon_180)
        prev_d = samples[-1]["cumulative_distance_meters"] if samples else 0.0
        samples.append(
            {
                "sample_index": i,
                "lat": float(lat),
                "lon_180": float(lon_180),
                "lon_east": float(lon_east),
                "cumulative_distance_meters": float(target_d),
                "segment_distance_meters": float(target_d - prev_d) if i > 0 else 0.0,
            }
        )
    return samples


def extract_windowed_terrain_features(
    *,
    dataset: Dataset,
    raw_dir: Path,
    requested_bounds: Dict[str, float],
    roughness_radius_meters: Optional[float] = None,
    max_returned_cells: int = 2500,
) -> TerrainFeaturesWindowResponse:
    """
    Extract elevation, Horn 3x3 slope, compass aspect, and metric TRI roughness
    over a bounded study window using rasterio windowed reads.
    Never enlarges `requested_bounds`; raises `InsufficientDEMCoverageError` if
    the requested window contains fewer than 3x3 whole source pixels.
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

    plan = plan_clip_to_bounding_box(
        source_raster_path=open_path,
        min_lon=req_min_lon,
        min_lat=req_min_lat,
        max_lon=req_max_lon,
        max_lat=req_max_lat,
        output_crs_str="IAU2000:MARS_SPHERE",
    )

    center_lat = 0.5 * (req_min_lat + req_max_lat)
    ps = plan["source_pixel_size"]
    dx_deg = float(ps["x"])
    dy_deg = float(ps["y"])
    dx_m, dy_m = angular_displacement_to_metric(
        center_lat,
        dx_deg,
        dy_deg,
    )

    src_bounds = plan["source_bounds"]
    inter_bounds = plan["intersecting_bounds"]
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
        raise InsufficientDEMCoverageError(report)

    win = rasterio.windows.Window(**plan["window"])
    rio_crs = rasterio.crs.CRS.from_proj4(
        f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
    )
    with rasterio.open(open_path) as src:
        is_int_dtype = "int" in str(src.dtypes[0]).lower()
        nodata = src.nodata
        if nodata is None and lbl_meta.get("missing_constant") is not None:
            try:
                nodata = float(lbl_meta["missing_constant"])
            except (TypeError, ValueError):
                nodata = -32768.0
        elif nodata is None:
            nodata = -32768.0

        max_win_pixels = 2_000_000
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=rio_crs) as vrt:
                win_px = int(win.width) * int(win.height)
                if win_px > max_win_pixels:
                    from rasterio.enums import Resampling
                    stride = max(2, int(math.ceil(math.sqrt(win_px / float(max_win_pixels)))))
                    out_h = max(3, int(win.height) // stride)
                    out_w = max(3, int(win.width) // stride)
                    dem_arr = vrt.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.nearest).astype(np.float64)
                    w_left, w_bottom, w_right, w_top = rasterio.windows.bounds(win, vrt.transform)
                    win_transform = rasterio.transform.from_bounds(w_left, w_bottom, w_right, w_top, out_w, out_h)
                    dx_m *= (float(win.width) / float(out_w))
                    dy_m *= (float(win.height) / float(out_h))
                else:
                    dem_arr = vrt.read(1, window=win).astype(np.float64)
                    win_transform = vrt.window_transform(win)
                    w_left, w_bottom, w_right, w_top = rasterio.windows.bounds(win, vrt.transform)
        else:
            win_px = int(win.width) * int(win.height)
            if win_px > max_win_pixels:
                from rasterio.enums import Resampling
                stride = max(2, int(math.ceil(math.sqrt(win_px / float(max_win_pixels)))))
                out_h = max(3, int(win.height) // stride)
                out_w = max(3, int(win.width) // stride)
                dem_arr = src.read(1, window=win, out_shape=(out_h, out_w), resampling=Resampling.nearest).astype(np.float64)
                w_left, w_bottom, w_right, w_top = rasterio.windows.bounds(win, src.transform)
                win_transform = rasterio.transform.from_bounds(w_left, w_bottom, w_right, w_top, out_w, out_h)
                dx_m *= (float(win.width) / float(out_w))
                dy_m *= (float(win.height) / float(out_h))
            else:
                dem_arr = src.read(1, window=win).astype(np.float64)
                win_transform = src.window_transform(win)
                w_left, w_bottom, w_right, w_top = rasterio.windows.bounds(win, src.transform)

    analysis_footprint_bounds = {
        "min_lat": float(w_bottom),
        "max_lat": float(w_top),
        "min_lon": float(w_left),
        "max_lon": float(w_right),
    }

    valid_elev_mask = np.isfinite(dem_arr) & (dem_arr != float(nodata)) & (dem_arr > -32000.0)
    nodata_mask = ~valid_elev_mask
    dem_clean = np.where(valid_elev_mask, dem_arr, np.nan)

    slope_arr, _ = calculate_slope(dem_arr, dx_m, dy_m, nodata_mask=nodata_mask)
    aspect_raw = calculate_aspect(dem_arr, dx_m, dy_m, nodata_mask=nodata_mask)
    aspect_arr = np.where(aspect_raw == -1.0, np.nan, aspect_raw)
    tri_arr, tri_meta = calculate_roughness_tri_with_metadata(
        dem_arr,
        dx_m,
        dy_m,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=roughness_radius_meters,
    )

    elev_stats = compute_band_stats(dem_clean, "meters")
    slope_stats = compute_band_stats(slope_arr, "degrees")
    aspect_stats = compute_band_stats(aspect_arr, "degrees_clockwise_north")
    rough_stats = compute_band_stats(tri_arr, "meters")

    rows, cols = dem_arr.shape
    valid_z_mask = np.isfinite(dem_clean)
    valid_deriv_mask = valid_z_mask & np.isfinite(slope_arr) & np.isfinite(tri_arr)
    nodata_count = int(np.count_nonzero(~valid_z_mask))
    valid_src_count = int(np.count_nonzero(valid_deriv_mask))
    deriv_unavail_count = int(rows * cols) - nodata_count - valid_src_count

    state_counts: Dict[str, int] = {s.value: 0 for s in TerrainCoverageState}
    state_counts[TerrainCoverageState.INSIDE_FOOTPRINT_NODATA.value] = nodata_count
    state_counts[TerrainCoverageState.DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD.value] = deriv_unavail_count
    state_counts[TerrainCoverageState.VALID_SOURCE_DATA.value] = valid_src_count

    cells: List[TerrainFeatureCell] = []
    t_a = float(win_transform.a)
    t_b = float(win_transform.b)
    t_c = float(win_transform.c)
    t_d = float(win_transform.d)
    t_e = float(win_transform.e)
    t_f = float(win_transform.f)

    for r in range(rows):
        if len(cells) >= max_returned_cells:
            break
        for c in range(cols):
            if len(cells) >= max_returned_cells:
                break
            lon_c = t_c + (c + 0.5) * t_a + (r + 0.5) * t_b
            lat_c = t_f + (c + 0.5) * t_d + (r + 0.5) * t_e
            lon_east = normalize_longitude_360(float(lon_c))
            z_val = float(dem_clean[r, c]) if valid_z_mask[r, c] else None
            s_val = float(slope_arr[r, c]) if np.isfinite(slope_arr[r, c]) else None
            a_raw_val = float(aspect_raw[r, c]) if np.isfinite(aspect_raw[r, c]) else None
            a_val = None if (a_raw_val is None or a_raw_val == -1.0) else a_raw_val
            t_val = float(tri_arr[r, c]) if np.isfinite(tri_arr[r, c]) else None

            if z_val is None:
                c_state = TerrainCoverageState.INSIDE_FOOTPRINT_NODATA
                flat_undef = False
            elif s_val is None or t_val is None:
                c_state = TerrainCoverageState.DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD
                flat_undef = False
            else:
                c_state = TerrainCoverageState.VALID_SOURCE_DATA
                flat_undef = (a_raw_val == -1.0)

            cells.append(
                TerrainFeatureCell(
                    row=r,
                    col=c,
                    center_lat=round(float(lat_c), 6),
                    center_lon_east=round(lon_east, 6),
                    coverage_state=c_state,
                    elevation_meters=round(z_val, 4) if z_val is not None else None,
                    slope_deg=round(s_val, 4) if s_val is not None else None,
                    aspect_deg=round(a_val, 4) if a_val is not None else None,
                    aspect_undefined_flat=flat_undef,
                    roughness_tri_meters=round(t_val, 4) if t_val is not None else None,
                )
            )

    suitability = evaluate_dem_resolution_suitability(
        native_resolution_m=dataset.horizontal_resolution_meters or dx_m,
        effective_resolution_m=dx_m,
        dem_available=True,
    )
    uncertainty = build_mobility_uncertainty_summary(
        dataset_id=dataset.id,
        product_id=dataset.product_id,
        dx_meters=dx_m,
        dy_meters=dy_m,
        vertical_units="meters",
        is_integer_dem=is_int_dtype,
        sampling_method="nearest_whole_pixel_window",
    )

    limitations = [
        "Slope and aspect use Horn's (1981) 3x3 finite-difference kernel; a 1-pixel border around the window "
        "and any cell with an invalid neighbor in its 3x3 window has undefined derivatives.",
        "Flat cells (dz/dx = 0 and dz/dy = 0) have undefined compass aspect (reported as null with aspect_undefined_flat=true).",
    ]
    if dx_m >= 1000.0:
        limitations.append(
            f"Coarse orbital resolution (~{dx_m:.0f} m/pixel) characterizes regional topography only; "
            "local human-scale slopes and obstacles are not resolved."
        )

    return TerrainFeaturesWindowResponse(
        dataset_id=dataset.id,
        source_product_id=dataset.product_id,
        processing_version=PROCESSING_VERSION,
        crs="IAU2000:MARS_SPHERE",
        requested_bounds=req_norm,
        requested_bounds_modified=False,
        source_coverage_bounds=src_bounds,
        analysis_footprint_bounds=analysis_footprint_bounds,
        dx_meters=round(dx_m, 4),
        dy_meters=round(dy_m, 4),
        grid_shape={"rows": rows, "cols": cols, "total_cells": rows * cols},
        roughness_window_metadata=tri_meta,
        elevation_stats=elev_stats,
        slope_stats=slope_stats,
        aspect_stats=aspect_stats,
        roughness_stats=rough_stats,
        coverage_state_counts=state_counts,
        cells=cells,
        resolution_suitability=suitability,
        uncertainty=uncertainty,
        provenance={
            "source_dataset_id": dataset.id,
            "source_product_id": dataset.product_id,
            "source_url": dataset.original_product_url,
            "footprint_policy": FOOTPRINT_POLICY,
            "processing_version": PROCESSING_VERSION,
            "slope_algorithm": "Horn (1981) 3x3 weighted central finite difference",
            "aspect_convention": "Degrees clockwise from North [0, 360); flat cells undefined",
            "roughness_algorithm": "Terrain Ruggedness Index (Riley et al., 1999) RMS elevation difference in meters",
        },
        limitations=limitations,
    )


def compute_elevation_profile(
    *,
    dataset: Dataset,
    raw_dir: Path,
    waypoints: Sequence[GeoPoint],
    sample_count: int = 25,
    sampling_method: str = "nearest",
    roughness_radius_meters: Optional[float] = None,
) -> ElevationProfileResponse:
    """
    Compute a spatially explicit elevation profile and cumulative elevation gain/loss
    between two positions or along a user-supplied polyline without route optimization.
    """
    open_path, lbl_path = _resolve_raw_dem_open_path(dataset, raw_dir)
    lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}

    raw_samples = interpolate_mars_polyline_samples(waypoints, sample_count)
    total_horiz_m = raw_samples[-1]["cumulative_distance_meters"] if raw_samples else 0.0
    spacing_m = total_horiz_m / float(max(1, len(raw_samples) - 1))

    rio_crs = rasterio.crs.CRS.from_proj4(
        f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
    )

    with rasterio.open(open_path) as src:
        is_int_dtype = "int" in str(src.dtypes[0]).lower()
        nodata = src.nodata
        if nodata is None and lbl_meta.get("missing_constant") is not None:
            try:
                nodata = float(lbl_meta["missing_constant"])
            except (TypeError, ValueError):
                nodata = -32768.0
        elif nodata is None:
            nodata = -32768.0

        def _sample_on_dataset(reader: Any) -> Tuple[List[ElevationProfileSample], float, float]:
            s_bounds = reader.bounds
            res_x, res_y = reader.res
            mean_lat = float(np.mean([s["lat"] for s in raw_samples])) if raw_samples else -4.6
            dx_m, dy_m = angular_displacement_to_metric(mean_lat, abs(float(res_x)), abs(float(res_y)))

            # Determine a 2-pixel padded window around all in-bounds sample coordinates so we can
            # also evaluate local 3x3 Horn slope/aspect/TRI at each sample without loading the whole globe.
            in_bounds_rows: List[int] = []
            in_bounds_cols: List[int] = []
            sample_rc: List[Optional[Tuple[int, int, float, float]]] = []

            for s in raw_samples:
                lat = s["lat"]
                lon_query = s["lon_180"]
                if s_bounds.right > 180.0 and lon_query < 0.0:
                    lon_query += 360.0
                if not (s_bounds.left <= lon_query <= s_bounds.right and s_bounds.bottom <= lat <= s_bounds.top):
                    sample_rc.append(None)
                    continue
                # Continuous pixel coordinates (r_f, c_f)
                inv_t = ~reader.transform
                c_f = inv_t.a * lon_query + inv_t.b * lat + inv_t.c
                r_f = inv_t.d * lon_query + inv_t.e * lat + inv_t.f
                r_i = int(math.floor(r_f))
                c_i = int(math.floor(c_f))
                if r_i < 0 or r_i >= reader.height or c_i < 0 or c_i >= reader.width:
                    sample_rc.append(None)
                else:
                    sample_rc.append((r_i, c_i, r_f, c_f))
                    in_bounds_rows.append(r_i)
                    in_bounds_cols.append(c_i)

            use_patch_sampling = False
            if in_bounds_rows and in_bounds_cols:
                r0 = max(0, min(in_bounds_rows) - 2)
                r1 = min(int(reader.height), max(in_bounds_rows) + 3)
                c0 = max(0, min(in_bounds_cols) - 2)
                c1 = min(int(reader.width), max(in_bounds_cols) + 3)
                bbox_pixels = (r1 - r0) * (c1 - c0)
                if bbox_pixels > 1_000_000:
                    use_patch_sampling = True
                else:
                    sub_win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
                    sub_dem = reader.read(1, window=sub_win).astype(np.float64)
                    sub_valid = np.isfinite(sub_dem) & (sub_dem != float(nodata)) & (sub_dem > -32000.0)
                    sub_dem_clean = np.where(sub_valid, sub_dem, np.nan)
                    if sub_dem.shape[0] >= 3 and sub_dem.shape[1] >= 3:
                        sub_nodata_mask = ~sub_valid
                        sub_slope, _ = calculate_slope(sub_dem, dx_m, dy_m, nodata_mask=sub_nodata_mask)
                        sub_aspect_raw = calculate_aspect(sub_dem, dx_m, dy_m, nodata_mask=sub_nodata_mask)
                        sub_aspect = np.where(sub_aspect_raw == -1.0, np.nan, sub_aspect_raw)
                        sub_tri, _ = calculate_roughness_tri_with_metadata(
                            sub_dem,
                            dx_m,
                            dy_m,
                            nodata_mask=sub_nodata_mask,
                            neighborhood_radius_meters=roughness_radius_meters,
                        )
                    else:
                        sub_slope = np.full_like(sub_dem, np.nan)
                        sub_aspect = np.full_like(sub_dem, np.nan)
                        sub_tri = np.full_like(sub_dem, np.nan)
            else:
                r0 = c0 = 0
                sub_dem_clean = np.empty((0, 0), dtype=np.float64)
                sub_slope = np.empty((0, 0), dtype=np.float64)
                sub_aspect = np.empty((0, 0), dtype=np.float64)
                sub_tri = np.empty((0, 0), dtype=np.float64)

            prof_samples: List[ElevationProfileSample] = []
            for idx, s in enumerate(raw_samples):
                rc = sample_rc[idx]
                if rc is None:
                    prof_samples.append(
                        ElevationProfileSample(
                            sample_index=idx,
                            lat=round(s["lat"], 6),
                            lon_east=round(s["lon_east"], 6),
                            cumulative_distance_meters=round(s["cumulative_distance_meters"], 3),
                            segment_distance_meters=round(s["segment_distance_meters"], 3),
                            coverage_state=TerrainCoverageState.OUTSIDE_SOURCE_FOOTPRINT,
                        )
                    )
                    continue

                r_i, c_i, r_f, c_f = rc
                if use_patch_sampling:
                    pr0 = max(0, r_i - 2)
                    pr1 = min(int(reader.height), r_i + 3)
                    pc0 = max(0, c_i - 2)
                    pc1 = min(int(reader.width), c_i + 3)
                    pwin = rasterio.windows.Window(pc0, pr0, pc1 - pc0, pr1 - pr0)
                    pdem = reader.read(1, window=pwin).astype(np.float64)
                    pval = np.isfinite(pdem) & (pdem != float(nodata)) & (pdem > -32000.0)
                    pdem_clean = np.where(pval, pdem, np.nan)
                    lr = r_i - pr0
                    lc = c_i - pc0
                    z_raw = pdem_clean[lr, lc]
                    if sampling_method == "bilinear" and np.isfinite(z_raw):
                        r_base = int(math.floor(r_f - 0.5))
                        c_base = int(math.floor(c_f - 0.5))
                        if (
                            0 <= (r_base - pr0)
                            and (r_base - pr0 + 1) < pdem_clean.shape[0]
                            and 0 <= (c_base - pc0)
                            and (c_base - pc0 + 1) < pdem_clean.shape[1]
                        ):
                            q = pdem_clean[r_base - pr0 : r_base - pr0 + 2, c_base - pc0 : c_base - pc0 + 2]
                            if np.all(np.isfinite(q)):
                                dr = (r_f - 0.5) - r_base
                                dc = (c_f - 0.5) - c_base
                                z_raw = float(
                                    q[0, 0] * (1 - dr) * (1 - dc)
                                    + q[0, 1] * (1 - dr) * dc
                                    + q[1, 0] * dr * (1 - dc)
                                    + q[1, 1] * dr * dc
                                )
                    if pdem.shape[0] >= 3 and pdem.shape[1] >= 3 and np.isfinite(z_raw):
                        pnodata = ~pval
                        pslp, _ = calculate_slope(pdem, dx_m, dy_m, nodata_mask=pnodata)
                        pasp_raw = calculate_aspect(pdem, dx_m, dy_m, nodata_mask=pnodata)
                        pasp = np.where(pasp_raw == -1.0, np.nan, pasp_raw)
                        ptri, _ = calculate_roughness_tri_with_metadata(
                            pdem,
                            dx_m,
                            dy_m,
                            nodata_mask=pnodata,
                            neighborhood_radius_meters=roughness_radius_meters,
                        )
                        s_val = float(pslp[lr, lc]) if np.isfinite(pslp[lr, lc]) else None
                        a_val = float(pasp[lr, lc]) if np.isfinite(pasp[lr, lc]) else None
                        t_val = float(ptri[lr, lc]) if np.isfinite(ptri[lr, lc]) else None
                    else:
                        s_val = a_val = t_val = None
                else:
                    lr = r_i - r0
                    lc = c_i - c0
                    z_raw = sub_dem_clean[lr, lc]

                    # Optional bilinear interpolation only if all 4 surrounding pixels are valid
                    if sampling_method == "bilinear" and np.isfinite(z_raw):
                        r_base = int(math.floor(r_f - 0.5))
                        c_base = int(math.floor(c_f - 0.5))
                        if (
                            0 <= (r_base - r0)
                            and (r_base - r0 + 1) < sub_dem_clean.shape[0]
                            and 0 <= (c_base - c0)
                            and (c_base - c0 + 1) < sub_dem_clean.shape[1]
                        ):
                            q = sub_dem_clean[r_base - r0 : r_base - r0 + 2, c_base - c0 : c_base - c0 + 2]
                            if np.all(np.isfinite(q)):
                                dr = (r_f - 0.5) - r_base
                                dc = (c_f - 0.5) - c_base
                                z_raw = float(
                                    q[0, 0] * (1 - dr) * (1 - dc)
                                    + q[0, 1] * (1 - dr) * dc
                                    + q[1, 0] * dr * (1 - dc)
                                    + q[1, 1] * dr * dc
                                )

                    if not np.isfinite(z_raw):
                        s_val = a_val = t_val = None
                    else:
                        s_val = float(sub_slope[lr, lc]) if np.isfinite(sub_slope[lr, lc]) else None
                        a_val = float(sub_aspect[lr, lc]) if np.isfinite(sub_aspect[lr, lc]) else None
                        t_val = float(sub_tri[lr, lc]) if np.isfinite(sub_tri[lr, lc]) else None

                if not np.isfinite(z_raw):
                    prof_samples.append(
                        ElevationProfileSample(
                            sample_index=idx,
                            lat=round(s["lat"], 6),
                            lon_east=round(s["lon_east"], 6),
                            cumulative_distance_meters=round(s["cumulative_distance_meters"], 3),
                            segment_distance_meters=round(s["segment_distance_meters"], 3),
                            coverage_state=TerrainCoverageState.INSIDE_FOOTPRINT_NODATA,
                            source_pixel_row=r_i,
                            source_pixel_col=c_i,
                        )
                    )
                    continue
                cov_state = (
                    TerrainCoverageState.VALID_SOURCE_DATA
                    if (s_val is not None and t_val is not None)
                    else TerrainCoverageState.DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD
                )

                prof_samples.append(
                    ElevationProfileSample(
                        sample_index=idx,
                        lat=round(s["lat"], 6),
                        lon_east=round(s["lon_east"], 6),
                        cumulative_distance_meters=round(s["cumulative_distance_meters"], 3),
                        segment_distance_meters=round(s["segment_distance_meters"], 3),
                        coverage_state=cov_state,
                        elevation_meters=round(float(z_raw), 4),
                        slope_deg=round(s_val, 4) if s_val is not None else None,
                        aspect_deg=round(a_val, 4) if a_val is not None else None,
                        roughness_tri_meters=round(t_val, 4) if t_val is not None else None,
                        source_pixel_row=r_i,
                        source_pixel_col=c_i,
                    )
                )
            return prof_samples, dx_m, dy_m

        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=rio_crs) as vrt:
                prof_samples, dx_m, dy_m = _sample_on_dataset(vrt)
        else:
            prof_samples, dx_m, dy_m = _sample_on_dataset(src)

    # Compute segment-by-segment elevation gain, loss, and contiguous no-data gaps
    pos_gain = 0.0
    neg_loss = 0.0
    eval_horiz_m = 0.0
    valid_elevs: List[float] = []
    seg_slopes: List[float] = []
    gap_segments: List[ElevationProfileGapSegment] = []

    active_gap_start_idx: Optional[int] = None
    active_gap_reason: Optional[TerrainCoverageState] = None

    for idx, samp in enumerate(prof_samples):
        if samp.elevation_meters is not None:
            valid_elevs.append(samp.elevation_meters)
            if active_gap_start_idx is not None:
                prev_idx = idx - 1
                d0 = prof_samples[active_gap_start_idx].cumulative_distance_meters
                d1 = prof_samples[prev_idx].cumulative_distance_meters
                gap_segments.append(
                    ElevationProfileGapSegment(
                        start_sample_index=active_gap_start_idx,
                        end_sample_index=prev_idx,
                        start_distance_meters=round(d0, 3),
                        end_distance_meters=round(d1, 3),
                        gap_length_meters=round(max(0.0, d1 - d0), 3),
                        reason=active_gap_reason or TerrainCoverageState.INSIDE_FOOTPRINT_NODATA,
                    )
                )
                active_gap_start_idx = None
                active_gap_reason = None

            if idx > 0 and prof_samples[idx - 1].elevation_meters is not None:
                dz = samp.elevation_meters - prof_samples[idx - 1].elevation_meters
                samp.segment_elevation_delta_meters = round(dz, 4)
                if dz > 0.0:
                    pos_gain += dz
                elif dz < 0.0:
                    neg_loss += abs(dz)
                seg_d = samp.segment_distance_meters
                eval_horiz_m += seg_d
                if seg_d > 0.0:
                    seg_slp = math.degrees(math.atan(abs(dz) / seg_d))
                    samp.segment_slope_deg = round(seg_slp, 4)
                    seg_slopes.append(seg_slp)
        else:
            if active_gap_start_idx is None:
                active_gap_start_idx = idx
                active_gap_reason = samp.coverage_state

    if active_gap_start_idx is not None:
        prev_idx = len(prof_samples) - 1
        d0 = prof_samples[active_gap_start_idx].cumulative_distance_meters
        d1 = prof_samples[prev_idx].cumulative_distance_meters
        gap_segments.append(
            ElevationProfileGapSegment(
                start_sample_index=active_gap_start_idx,
                end_sample_index=prev_idx,
                start_distance_meters=round(d0, 3),
                end_distance_meters=round(d1, 3),
                gap_length_meters=round(max(0.0, d1 - d0), 3),
                reason=active_gap_reason or TerrainCoverageState.INSIDE_FOOTPRINT_NODATA,
            )
        )

    valid_cnt = len(valid_elevs)
    nodata_cnt = len(prof_samples) - valid_cnt
    complete = (nodata_cnt == 0 and valid_cnt >= 2)

    net_change: Optional[float] = None
    if valid_cnt >= 2 and prof_samples[0].elevation_meters is not None and prof_samples[-1].elevation_meters is not None:
        net_change = round(prof_samples[-1].elevation_meters - prof_samples[0].elevation_meters, 4)
    elif valid_cnt >= 2:
        net_change = round(valid_elevs[-1] - valid_elevs[0], 4)

    suitability = evaluate_dem_resolution_suitability(
        native_resolution_m=dataset.horizontal_resolution_meters or dx_m,
        effective_resolution_m=dx_m,
        dem_available=True,
    )
    uncertainty = build_mobility_uncertainty_summary(
        dataset_id=dataset.id,
        product_id=dataset.product_id,
        dx_meters=dx_m,
        dy_meters=dy_m,
        vertical_units="meters",
        is_integer_dem=is_int_dtype,
        sampling_method=f"{sampling_method}_transect_sampling",
    )

    limitations = [
        "Profile evaluates a straight geodesic transect or user-supplied waypoint sequence directly; "
        "it does NOT perform route optimization or obstacle avoidance.",
    ]
    if dx_m >= 1000.0:
        limitations.append(
            f"Source DEM pixel spacing is ~{dx_m:.0f} m; samples spaced closer than ~{dx_m:.0f} m "
            "may fall within the same source pixel and yield zero apparent intra-pixel elevation change."
        )
    if not complete:
        limitations.append(
            f"{nodata_cnt} of {len(prof_samples)} profile samples lacked valid elevation data; "
            "cumulative gain/loss is summed only across contiguous valid segments."
        )

    return ElevationProfileResponse(
        dataset_id=dataset.id,
        source_product_id=dataset.product_id,
        crs="IAU2000:MARS_SPHERE",
        sampling_method=sampling_method,
        geometry_type="two_point_transect" if len(waypoints) == 2 else "user_supplied_polyline",
        waypoint_count=len(waypoints),
        sample_count=len(prof_samples),
        valid_sample_count=valid_cnt,
        nodata_sample_count=nodata_cnt,
        complete_coverage=complete,
        sample_spacing_meters=round(spacing_m, 3),
        total_horizontal_distance_meters=round(total_horiz_m, 3),
        evaluated_horizontal_distance_meters=round(eval_horiz_m, 3),
        total_positive_elevation_gain_meters=round(pos_gain, 4) if valid_cnt >= 2 else None,
        total_negative_elevation_change_meters=round(neg_loss, 4) if valid_cnt >= 2 else None,
        net_elevation_change_meters=net_change,
        min_elevation_meters=round(min(valid_elevs), 4) if valid_elevs else None,
        max_elevation_meters=round(max(valid_elevs), 4) if valid_elevs else None,
        mean_slope_along_profile_deg=round(float(np.mean(seg_slopes)), 4) if seg_slopes else None,
        max_slope_along_profile_deg=round(float(np.max(seg_slopes)), 4) if seg_slopes else None,
        nodata_gap_segments=gap_segments,
        samples=prof_samples,
        resolution_suitability=suitability,
        uncertainty=uncertainty,
        limitations=limitations,
    )
