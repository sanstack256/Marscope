"""
MARSCOPE Corridor Terrain Assessment & Morphology Candidate Detection
Martian Surface Intelligence & Exploration System

Extracts windowed DEM metrics (elevation, slope, 5.0 m physical-radius TRI,
local relief, profile curvature) per route segment and detects reproducible,
resolution-checked terrain morphology candidates without fabricating hazards.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    SegmentCoverageReport,
    TerrainMorphologyCandidate,
)
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import RouteVertex
from app.science.provenance_graph import ScientificDataClassification
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


def _meters_per_degree(lat_deg: float) -> Tuple[float, float]:
    m_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
    m_lon = max(1e-6, MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(lat_deg)) * math.pi / 180.0)
    return m_lat, m_lon


def _segment_bounds(vertices: List[RouteVertex], margin_deg_lat: float, margin_deg_lon: float) -> Dict[str, float]:
    lats = [v.lat for v in vertices]
    lons = [v.lon_east for v in vertices]
    return {
        "min_lat": min(lats) - margin_deg_lat,
        "max_lat": max(lats) + margin_deg_lat,
        "min_lon": min(lons) - margin_deg_lon,
        "max_lon": max(lons) + margin_deg_lon,
    }


def _compute_profile_curvature(
    dem: np.ndarray, dx_m: float, dy_m: float, nodata_mask: np.ndarray
) -> np.ndarray:
    """Compute discrete 2nd-order Laplacian curvature (1/m) on valid DEM cells."""
    curv = np.full(dem.shape, np.nan, dtype=np.float32)
    if dem.shape[0] < 3 or dem.shape[1] < 3:
        return curv
    d2z_dx2 = (dem[1:-1, 2:] - 2.0 * dem[1:-1, 1:-1] + dem[1:-1, :-2]) / max(1e-6, dx_m * dx_m)
    d2z_dy2 = (dem[2:, 1:-1] - 2.0 * dem[1:-1, 1:-1] + dem[:-2, 1:-1]) / max(1e-6, dy_m * dy_m)
    valid = (
        ~nodata_mask[1:-1, 1:-1]
        & ~nodata_mask[1:-1, 2:]
        & ~nodata_mask[1:-1, :-2]
        & ~nodata_mask[2:, 1:-1]
        & ~nodata_mask[:-2, 1:-1]
    )
    inner = np.where(valid, -(d2z_dx2 + d2z_dy2), np.nan)
    curv[1:-1, 1:-1] = inner.astype(np.float32)
    return curv


def _nearest_segment_id(
    lat: float, lon_east: float, raw_segments: List[Dict[str, Any]]
) -> Optional[str]:
    best_id: Optional[str] = None
    best_d = float("inf")
    for seg in raw_segments:
        verts: List[RouteVertex] = seg["vertices"]
        mid = verts[len(verts) // 2]
        d = mars_great_circle_distance_meters(lat, lon_east, mid.lat, mid.lon_east)
        if d < best_d:
            best_d = d
            best_id = str(seg["segment_id"])
    return best_id


def assess_corridor_terrain(
    *,
    dem_path: Path,
    dataset_id: str,
    source_product_id: str,
    native_resolution_m: float,
    raw_segments: List[Dict[str, Any]],
    corridor_width_m: float,
    optical_coverage_fraction: float,
    optical_quality_note: str,
    geological_map_coverage: bool,
    spectral_data_available: bool,
    thermal_data_available: bool,
    max_candidates: int = 36,
) -> Tuple[
    List[CorridorSegmentAssessment],
    List[TerrainMorphologyCandidate],
    Dict[str, Any],
]:
    """
    Evaluate windowed DEM metrics along each segment and detect morphology candidates
    across the route corridor.
    """
    if not dem_path.exists():
        raise FileNotFoundError(f"Processed DEM not found at {dem_path}")

    all_verts: List[RouteVertex] = [v for seg in raw_segments for v in seg["vertices"]]
    mean_lat = sum(v.lat for v in all_verts) / float(len(all_verts))
    m_lat, m_lon = _meters_per_degree(mean_lat)
    half_w_m = 0.5 * corridor_width_m
    margin_m = half_w_m + max(15.0, native_resolution_m * 6.0)
    margin_deg_lat = margin_m / m_lat
    margin_deg_lon = margin_m / m_lon

    min_lat = min(v.lat for v in all_verts) - margin_deg_lat
    max_lat = max(v.lat for v in all_verts) + margin_deg_lat
    min_lon = min(v.lon_east for v in all_verts) - margin_deg_lon
    max_lon = max(v.lon_east for v in all_verts) + margin_deg_lon

    with rasterio.open(dem_path) as src:
        win = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
        win = win.round_offsets().round_lengths()
        # Clamp window to raster bounds
        col_off = max(0, int(win.col_off))
        row_off = max(0, int(win.row_off))
        col_end = min(src.width, int(win.col_off + win.width))
        row_end = min(src.height, int(win.row_off + win.height))
        if col_end <= col_off or row_end <= row_off:
            raise ValueError("Route corridor falls completely outside the DEM spatial footprint.")

        clamped_win = rasterio.windows.Window(
            col_off, row_off, col_end - col_off, row_end - row_off
        )
        dem = src.read(1, window=clamped_win).astype(np.float32)
        win_transform = src.window_transform(clamped_win)
        nodata_val = src.nodata

        # Derive metric pixel spacing at corridor latitude
        dx_deg = abs(float(src.transform.a))
        dy_deg = abs(float(src.transform.e))
        dx_m = max(0.05, dx_deg * m_lon)
        dy_m = max(0.05, dy_deg * m_lat)

    nodata_mask = ~np.isfinite(dem)
    if nodata_val is not None:
        nodata_mask |= np.isclose(dem, float(nodata_val), equal_nan=True)
    nodata_mask |= np.abs(dem) > 1e6

    slope_grid, _aspect_grid = calculate_slope(dem, dx_m, dy_m, nodata_mask=nodata_mask)
    tri_grid, tri_meta = calculate_roughness_tri_with_metadata(
        dem,
        dx_m,
        dy_m,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=5.0,
        source_product_id=source_product_id,
        native_resolution_m=native_resolution_m,
    )
    curv_grid = _compute_profile_curvature(dem, dx_m, dy_m, nodata_mask)

    rows, cols = dem.shape
    row_idx = np.arange(rows, dtype=np.float64)[:, None]
    col_idx = np.arange(cols, dtype=np.float64)[None, :]
    # Pixel center coordinates in lon_east, lat
    lon_grid = win_transform.c + (col_idx + 0.5) * win_transform.a
    lat_grid = win_transform.f + (row_idx + 0.5) * win_transform.e

    segment_assessments: List[CorridorSegmentAssessment] = []
    segment_bounds_map: Dict[str, Dict[str, float]] = {}

    for seg in raw_segments:
        seg_id = str(seg["segment_id"])
        verts: List[RouteVertex] = seg["vertices"]
        s_bounds = _segment_bounds(verts, half_w_m / m_lat, half_w_m / m_lon)
        segment_bounds_map[seg_id] = s_bounds

        # Sub-window slice for fast per-segment masking
        in_box = (
            (lat_grid >= s_bounds["min_lat"])
            & (lat_grid <= s_bounds["max_lat"])
            & (lon_grid >= s_bounds["min_lon"])
            & (lon_grid <= s_bounds["max_lon"])
        )
        # Distance to polyline vertices approximation (fast & exact within vertex spacing ~1-5m)
        r_indices, c_indices = np.where(in_box)
        if len(r_indices) == 0:
            valid_frac = 0.0
            valid_elev = np.array([], dtype=np.float32)
            valid_slope = np.array([], dtype=np.float32)
            valid_tri = np.array([], dtype=np.float32)
            valid_curv = np.array([], dtype=np.float32)
        else:
            p_lat = lat_grid[r_indices, 0]
            p_lon = lon_grid[0, c_indices]
            # Vectorized distance in local meters to segment vertices
            min_d2 = np.full(len(p_lat), np.inf, dtype=np.float64)
            for v in verts:
                dy_v = (p_lat - v.lat) * m_lat
                dx_v = (p_lon - v.lon_east) * m_lon
                d2 = dx_v * dx_v + dy_v * dy_v
                min_d2 = np.minimum(min_d2, d2)
            in_corridor = min_d2 <= (half_w_m * half_w_m)
            sel_r = r_indices[in_corridor]
            sel_c = c_indices[in_corridor]
            if len(sel_r) == 0:
                valid_frac = 0.0
                valid_elev = np.array([], dtype=np.float32)
                valid_slope = np.array([], dtype=np.float32)
                valid_tri = np.array([], dtype=np.float32)
                valid_curv = np.array([], dtype=np.float32)
            else:
                seg_nodata = nodata_mask[sel_r, sel_c]
                valid_mask = ~seg_nodata
                valid_frac = float(np.mean(valid_mask))
                valid_elev = dem[sel_r[valid_mask], sel_c[valid_mask]]
                s_vals = slope_grid[sel_r, sel_c]
                valid_slope = s_vals[np.isfinite(s_vals) & valid_mask]
                t_vals = tri_grid[sel_r, sel_c]
                valid_tri = t_vals[np.isfinite(t_vals) & valid_mask]
                c_vals = curv_grid[sel_r, sel_c]
                valid_curv = c_vals[np.isfinite(c_vals) & valid_mask]

        start_elev = round(float(verts[0].elevation_m), 2)
        end_elev = round(float(verts[-1].elevation_m), 2)
        elev_change = round(end_elev - start_elev, 2)
        max_slope = round(float(np.max(valid_slope)), 2) if len(valid_slope) else None
        mean_slope = round(float(np.mean(valid_slope)), 2) if len(valid_slope) else None
        max_tri = round(float(np.max(valid_tri)), 2) if len(valid_tri) else None
        mean_tri = round(float(np.mean(valid_tri)), 2) if len(valid_tri) else None
        local_relief = (
            round(float(np.max(valid_elev) - np.min(valid_elev)), 2)
            if len(valid_elev) >= 2
            else None
        )
        mean_curv = (
            round(float(np.mean(valid_curv)), 5) if len(valid_curv) else None
        )

        res_note = (
            f"{native_resolution_m:.2f} m/px DEM; micro-obstacles < {native_resolution_m * 2.0:.1f} m unresolved"
            if native_resolution_m <= 2.0
            else f"{native_resolution_m:.1f} m/px regional DEM (resolution-limited)"
        )
        unverified = valid_frac < 0.95 or optical_coverage_fraction < 0.5

        cov = SegmentCoverageReport(
            segment_id=seg_id,
            dem_coverage_fraction=round(valid_frac, 4),
            valid_elevation_fraction=round(valid_frac, 4),
            slope_available=len(valid_slope) > 0,
            tri_available=len(valid_tri) > 0,
            optical_coverage_fraction=round(optical_coverage_fraction, 4),
            optical_quality_note=optical_quality_note,
            geological_map_coverage=geological_map_coverage,
            spectral_data_available=spectral_data_available,
            thermal_data_available=thermal_data_available,
            rover_observation_count=0,
            panorama_available=False,
            source_resolution_m=native_resolution_m,
            unverified_regions_present=unverified,
        )

        segment_assessments.append(
            CorridorSegmentAssessment(
                segment_id=seg_id,
                segment_index=int(seg["segment_index"]),
                start_coord=seg["start_coord"],
                end_coord=seg["end_coord"],
                geodesic_distance_m=float(seg["geodesic_distance_m"]),
                surface_distance_m=float(seg["surface_distance_m"]),
                start_elevation_m=start_elev,
                end_elevation_m=end_elev,
                elevation_change_m=elev_change,
                max_slope_deg=max_slope,
                mean_slope_deg=mean_slope,
                max_tri_m=max_tri,
                mean_tri_m=mean_tri,
                tri_physical_radius_m=5.0,
                local_relief_m=local_relief,
                mean_profile_curvature_inv_m=mean_curv,
                source_dem_id=dataset_id,
                source_product_id=source_product_id,
                native_resolution_m=native_resolution_m,
                valid_data_coverage_fraction=round(valid_frac, 4),
                uncertainty_summary=res_note,
                unverified_area_present=unverified,
                coverage=cov,
                provenance={
                    "dem_dataset_id": dataset_id,
                    "source_product_id": source_product_id,
                    "tri_method": tri_meta.get("tri_definition") if isinstance(tri_meta, dict) else "RMS_5m",
                    "tri_physical_radius_m": 5.0,
                    "effective_pixel_spacing_m": round(0.5 * (dx_m + dy_m), 3),
                },
            )
        )

    # Detect corridor-wide morphology candidates on a coarse stride (~5 m spacing) to avoid duplicate per-pixel clutter
    step_r = max(1, int(round(6.0 / dy_m)))
    step_c = max(1, int(round(6.0 / dx_m)))
    candidates: List[TerrainMorphologyCandidate] = []
    res_status = "adequate" if native_resolution_m <= 2.0 else "resolution_limited"

    for r in range(2, rows - 2, step_r):
        for c in range(2, cols - 2, step_c):
            if nodata_mask[r, c]:
                continue
            lat_c = float(lat_grid[r, 0])
            lon_c = float(lon_grid[0, c])
            # Check within corridor width of any route vertex
            min_d = min(
                mars_great_circle_distance_meters(lat_c, lon_c, v.lat, v.lon_east)
                for v in all_verts[:: max(1, len(all_verts) // 40)]
            )
            if min_d > half_w_m * 1.15:
                continue

            patch = dem[max(0, r - 2) : min(rows, r + 3), max(0, c - 2) : min(cols, c + 3)]
            valid_p = patch[~nodata_mask[max(0, r - 2) : min(rows, r + 3), max(0, c - 2) : min(cols, c + 3)]]
            if len(valid_p) < 5:
                continue

            z_c = float(dem[r, c])
            z_mean = float(np.mean(valid_p))
            relief_p = float(np.max(valid_p) - np.min(valid_p))
            s_val = float(slope_grid[r, c]) if np.isfinite(slope_grid[r, c]) else 0.0
            t_val = float(tri_grid[r, c]) if np.isfinite(tri_grid[r, c]) else 0.0
            curv_val = float(curv_grid[r, c]) if np.isfinite(curv_grid[r, c]) else 0.0

            morph_type: Optional[str] = None
            salience = 0.0
            if s_val >= 18.0 and relief_p >= 1.5:
                morph_type = "steep_transition" if s_val < 25.0 else "scarp"
                salience = s_val + relief_p
            elif t_val >= max(1.8, native_resolution_m * 2.0):
                morph_type = "relief_anomaly"
                salience = t_val * 6.0
            elif z_c - z_mean >= 0.85 and curv_val > 0.02:
                morph_type = "ridge_like_landform"
                salience = (z_c - z_mean) * 8.0
            elif z_mean - z_c >= 0.85:
                morph_type = "depression"
                salience = (z_mean - z_c) * 8.0
            elif z_c >= float(np.max(valid_p)) - 1e-4 and (z_c - z_mean) >= 0.75:
                morph_type = "local_peak"
                salience = (z_c - z_mean) * 7.0

            if morph_type is None:
                continue

            seg_id = _nearest_segment_id(lat_c, lon_c, raw_segments)
            cid = hashlib.sha256(
                f"{dataset_id}:{morph_type}:{lat_c:.6f}:{lon_c:.6f}".encode()
            ).hexdigest()[:12]
            box_d_lat = (3.0 * dy_m) / m_lat
            box_d_lon = (3.0 * dx_m) / m_lon
            candidates.append(
                TerrainMorphologyCandidate(
                    candidate_id=f"tm-{cid}",
                    morphology_type=morph_type,
                    segment_id=seg_id,
                    latitude=round(lat_c, 6),
                    longitude_east=round(lon_c, 6),
                    footprint_bounds={
                        "min_lat": round(lat_c - box_d_lat, 6),
                        "max_lat": round(lat_c + box_d_lat, 6),
                        "min_lon": round(lon_c - box_d_lon, 6),
                        "max_lon": round(lon_c + box_d_lon, 6),
                    },
                    detection_method="windowed_dem_morphology_tri_curvature",
                    input_dataset_id=dataset_id,
                    input_product_id=source_product_id,
                    input_resolution_m=native_resolution_m,
                    detection_parameters={
                        "slope_threshold_deg": 18.0,
                        "tri_radius_m": 5.0,
                        "local_relief_threshold_m": 0.75,
                    },
                    geometric_measurements={
                        "elevation_m": round(z_c, 2),
                        "slope_deg": round(s_val, 2),
                        "tri_5m_m": round(t_val, 2),
                        "local_relief_m": round(relief_p, 2),
                        "curvature_inv_m": round(curv_val, 5),
                        "salience": round(salience, 2),
                    },
                    resolution_status=res_status,
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    validation_state="candidate_requiring_interpretation",
                    limitations=[
                        f"Derived from {native_resolution_m:.2f} m/px DEM; features below {native_resolution_m * 2.0:.1f} m are unresolved.",
                        "Morphological classification is geometric only and requires optical/rover verification before operational hazard labeling.",
                    ],
                    provenance={
                        "dataset_id": dataset_id,
                        "source_product_id": source_product_id,
                    },
                )
            )

    candidates.sort(
        key=lambda item: item.geometric_measurements.get("salience", 0.0), reverse=True
    )
    candidates = candidates[:max_candidates]

    # Link candidate IDs back onto segments
    seg_cand_map: Dict[str, List[str]] = {s.segment_id: [] for s in segment_assessments}
    for cand in candidates:
        if cand.segment_id and cand.segment_id in seg_cand_map:
            seg_cand_map[cand.segment_id].append(cand.candidate_id)
    for seg_obj in segment_assessments:
        seg_obj.morphology_candidate_ids = seg_cand_map.get(seg_obj.segment_id, [])

    corridor_dem_stats = {
        "corridor_valid_fraction": round(float(np.mean(~nodata_mask)), 4) if nodata_mask.size else 0.0,
        "dem_window_bounds": {
            "min_lat": round(min_lat, 6),
            "max_lat": round(max_lat, 6),
            "min_lon": round(min_lon, 6),
            "max_lon": round(max_lon, 6),
        },
        "segment_bounds": segment_bounds_map,
        "dx_m": round(dx_m, 3),
        "dy_m": round(dy_m, 3),
    }
    return segment_assessments, candidates, corridor_dem_stats
