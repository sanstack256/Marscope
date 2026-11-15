"""
MARSCOPE Corridor Terrain Assessment & Morphology Candidate Detection
Martian Surface Intelligence & Exploration System

Uses true rasterio.features.geometry_mask polygon rasterization on a bounded,
convolution-buffered DEM window with explicit Mars CRS verification, ensuring
that zero outside-corridor pixels contaminate corridor terrain metrics or
morphology candidate detection.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from app.evidence_intelligence.corridor import MarsLocalFrame
from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    SegmentCoverageReport,
    TerrainMorphologyCandidate,
)
from app.geospatial.crs import (
    MARS_EQUATORIAL_RADIUS_M,
    angular_displacement_to_metric,
    normalize_longitude_360,
    validate_mars_crs,
)
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import RouteVertex
from app.science.provenance_graph import ScientificDataClassification
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope

MARS_GEOG_CRS = rasterio.crs.CRS.from_proj4(
    f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
)


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


def _align_geom_to_raster_bounds(geom: Any, bounds: Any) -> Any:
    """Shift polygon longitudes (-360 or +360) if needed to match raster lon convention."""
    g_minx, _, g_maxx, _ = geom.bounds
    if bounds.right <= 180.0 + 1e-6 and g_maxx > 180.0 + 1e-6:
        return shapely.transform(geom, lambda xy: np.column_stack([xy[:, 0] - 360.0, xy[:, 1]]))
    if bounds.left >= 180.0 and g_minx < 0.0:
        return shapely.transform(geom, lambda xy: np.column_stack([xy[:, 0] + 360.0, xy[:, 1]]))
    return geom


def _build_corridor_poly_fallback(
    raw_segments: List[Dict[str, Any]], corridor_width_m: float
) -> Any:
    all_verts = [v for s in raw_segments for v in s["vertices"]]
    c_lat = sum(v.lat for v in all_verts) / max(1, len(all_verts))
    c_lon = sum(normalize_longitude_360(v.lon_east) for v in all_verts) / max(1, len(all_verts))
    frame = MarsLocalFrame(c_lat, c_lon)
    line_m = LineString([frame.to_metric(v.lon_east, v.lat) for v in all_verts])
    poly_m = line_m.buffer(0.5 * corridor_width_m, resolution=10, cap_style="round", join_style="round")
    return frame.to_lonlat_geom(poly_m)


def _nearest_segment_id(
    lat: float, lon_east: float, raw_segments: List[Dict[str, Any]], frame: MarsLocalFrame
) -> Optional[str]:
    px, py = frame.to_metric(lon_east, lat)
    from shapely.geometry import Point

    pt = Point(px, py)
    best_id: Optional[str] = None
    best_d = float("inf")
    for seg in raw_segments:
        line_m = LineString([frame.to_metric(v.lon_east, v.lat) for v in seg["vertices"]])
        d = line_m.distance(pt)
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
    optical_coverage_fraction: Optional[float],
    optical_quality_note: str,
    geological_map_coverage: bool,
    spectral_data_available: bool,
    thermal_data_available: bool,
    max_candidates: int = 36,
    require_verified_crs: bool = True,
) -> Tuple[
    List[CorridorSegmentAssessment],
    List[TerrainMorphologyCandidate],
    Dict[str, Any],
]:
    """
    Evaluate polygon-masked DEM metrics along each segment and detect morphology
    candidates strictly inside the assessed corridor polygon.
    """
    if not dem_path.exists():
        raise FileNotFoundError(f"Processed DEM not found at {dem_path}")
    if not raw_segments:
        raise ValueError("Cannot assess corridor terrain without route segments.")

    all_verts: List[RouteVertex] = [v for seg in raw_segments for v in seg["vertices"]]
    mean_lat = sum(v.lat for v in all_verts) / float(len(all_verts))
    mean_lon = sum(normalize_longitude_360(v.lon_east) for v in all_verts) / float(len(all_verts))
    frame = MarsLocalFrame(mean_lat, mean_lon)

    seg_polys_ll: List[Any] = []
    for seg in raw_segments:
        poly_ll = seg.get("corridor_polygon_ll")
        if poly_ll is None and seg.get("corridor_polygon"):
            poly_ll = Polygon(seg["corridor_polygon"])
        if poly_ll is None:
            pts_m = [frame.to_metric(v.lon_east, v.lat) for v in seg["vertices"]]
            poly_m = LineString(pts_m).buffer(0.5 * corridor_width_m, cap_style="round", join_style="round")
            poly_ll = frame.to_lonlat_geom(poly_m)
            seg["corridor_polygon_ll"] = poly_ll
            seg["corridor_area_m2"] = round(float(poly_m.area), 3)
        seg_polys_ll.append(poly_ll)

    overall_corridor_ll = unary_union(seg_polys_ll) if seg_polys_ll else _build_corridor_poly_fallback(raw_segments, corridor_width_m)

    m_lat, m_lon = angular_displacement_to_metric(mean_lat, 1.0, 1.0)
    # Explicit convolution padding (>= 5 m TRI neighborhood + 3 pixels for Horn 3x3 & Laplacian)
    conv_buffer_m = max(10.0, 5.0 + 3.0 * float(native_resolution_m))
    pad_deg_lat = conv_buffer_m / max(1.0, m_lat)
    pad_deg_lon = conv_buffer_m / max(1.0, m_lon)

    c_minx, c_miny, c_maxx, c_maxy = overall_corridor_ll.bounds
    min_lon = c_minx - pad_deg_lon
    max_lon = c_maxx + pad_deg_lon
    min_lat = c_miny - pad_deg_lat
    max_lat = c_maxy + pad_deg_lat

    def _run_on_reader(src: Any, crs_verified: bool, orig_crs_str: str) -> Tuple[
        List[CorridorSegmentAssessment],
        List[TerrainMorphologyCandidate],
        Dict[str, Any],
    ]:
        rb = src.bounds
        q_min_lon = min_lon - 360.0 if (rb.right <= 180.0 and min_lon > 180.0) else min_lon
        q_max_lon = max_lon - 360.0 if (rb.right <= 180.0 and max_lon > 180.0) else max_lon

        c_min_lon = max(rb.left, q_min_lon)
        c_max_lon = min(rb.right, q_max_lon)
        c_min_lat = max(rb.bottom, min_lat)
        c_max_lat = min(rb.top, max_lat)

        if c_max_lon <= c_min_lon or c_max_lat <= c_min_lat:
            raise ValueError(
                f"Route corridor falls completely outside the DEM spatial footprint "
                f"[{rb.left:.4f}..{rb.right:.4f}, {rb.bottom:.4f}..{rb.top:.4f}]."
            )

        win = from_bounds(c_min_lon, c_min_lat, c_max_lon, c_max_lat, src.transform)
        win = win.round_offsets().round_lengths()
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

        dx_deg = abs(float(src.transform.a))
        dy_deg = abs(float(src.transform.e))
        dx_m, dy_m = angular_displacement_to_metric(mean_lat, dx_deg, dy_deg)
        dx_m = max(0.05, dx_m)
        dy_m = max(0.05, dy_m)
        conv_buffer_px = max(3, int(math.ceil(conv_buffer_m / min(dx_m, dy_m))))

        nodata_mask = ~np.isfinite(dem)
        if nodata_val is not None:
            nodata_mask |= np.isclose(dem, float(nodata_val), equal_nan=True)
        nodata_mask |= np.abs(dem) > 1e6

        # Compute derivatives across convolution-buffered array
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

        # True rasterio geometry_mask for the corridor polygon ONLY (never includes buffer pixels)
        corridor_geom_aligned = _align_geom_to_raster_bounds(overall_corridor_ll, rb)
        corridor_mask = geometry_mask(
            [corridor_geom_aligned],
            out_shape=dem.shape,
            transform=win_transform,
            invert=True,
            all_touched=True,
        )

        corridor_pix_total = int(np.count_nonzero(corridor_mask))
        corridor_pix_valid = int(np.count_nonzero(corridor_mask & (~nodata_mask)))
        corridor_valid_frac = (
            float(corridor_pix_valid) / float(corridor_pix_total)
            if corridor_pix_total > 0
            else 0.0
        )

        rows, cols = dem.shape
        row_idx = np.arange(rows, dtype=np.float64)[:, None]
        col_idx = np.arange(cols, dtype=np.float64)[None, :]
        lon_grid_raw = win_transform.c + (col_idx + 0.5) * win_transform.a
        lon_grid = np.where(lon_grid_raw < 0.0, lon_grid_raw + 360.0, lon_grid_raw)
        lat_grid = win_transform.f + (row_idx + 0.5) * win_transform.e

        segment_assessments: List[CorridorSegmentAssessment] = []
        segment_bounds_map: Dict[str, Dict[str, float]] = {}

        for seg in raw_segments:
            seg_id = str(seg["segment_id"])
            verts: List[RouteVertex] = seg["vertices"]
            seg_poly_ll = seg["corridor_polygon_ll"]
            seg_poly_aligned = _align_geom_to_raster_bounds(seg_poly_ll, rb)

            seg_mask = geometry_mask(
                [seg_poly_aligned],
                out_shape=dem.shape,
                transform=win_transform,
                invert=True,
                all_touched=True,
            )
            seg_total_px = int(np.count_nonzero(seg_mask))
            seg_valid_mask = seg_mask & (~nodata_mask)
            seg_valid_px = int(np.count_nonzero(seg_valid_mask))
            valid_frac = float(seg_valid_px) / float(seg_total_px) if seg_total_px > 0 else 0.0

            sb = seg_poly_ll.bounds
            segment_bounds_map[seg_id] = {
                "min_lon": round(float(sb[0]), 6),
                "min_lat": round(float(sb[1]), 6),
                "max_lon": round(float(sb[2]), 6),
                "max_lat": round(float(sb[3]), 6),
            }

            valid_elev = dem[seg_valid_mask]
            s_vals = slope_grid[seg_valid_mask]
            valid_slope = s_vals[np.isfinite(s_vals)]
            t_vals = tri_grid[seg_valid_mask]
            valid_tri = t_vals[np.isfinite(t_vals)]
            c_vals = curv_grid[seg_valid_mask]
            valid_curv = c_vals[np.isfinite(c_vals)]

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
            mean_curv = round(float(np.mean(valid_curv)), 5) if len(valid_curv) else None

            seg_area_m2 = float(seg.get("corridor_area_m2") or 0.0)
            dem_valid_area_m2 = round(seg_area_m2 * valid_frac, 2)

            res_note = (
                f"{native_resolution_m:.2f} m/px DEM; micro-obstacles < {native_resolution_m * 2.0:.1f} m unresolved"
                if native_resolution_m <= 2.0
                else f"{native_resolution_m:.1f} m/px regional DEM (resolution-limited)"
            )
            unverified = valid_frac < 0.95 or optical_coverage_fraction is None or optical_coverage_fraction < 0.5

            cov = SegmentCoverageReport(
                segment_id=seg_id,
                dem_coverage_fraction=round(valid_frac, 4),
                valid_elevation_fraction=round(valid_frac, 4),
                slope_available=len(valid_slope) > 0,
                tri_available=len(valid_tri) > 0,
                optical_coverage_fraction=round(optical_coverage_fraction, 4) if optical_coverage_fraction is not None else None,
                optical_quality_note=optical_quality_note,
                geological_map_coverage=geological_map_coverage,
                geological_coverage_fraction=1.0 if geological_map_coverage else 0.0,
                spectral_data_available=spectral_data_available,
                thermal_data_available=thermal_data_available,
                rover_observation_count=0,
                panorama_available=False,
                source_resolution_m=native_resolution_m,
                unverified_regions_present=unverified,
                segment_corridor_area_m2=round(seg_area_m2, 2),
                dem_valid_area_m2=dem_valid_area_m2,
                spatial_resolution_adequate_for_eva=bool(native_resolution_m <= 2.0),
                validation_status="unvalidated_planning_evidence",
            )

            segment_assessments.append(
                CorridorSegmentAssessment(
                    segment_id=seg_id,
                    segment_index=int(seg["segment_index"]),
                    start_coord=seg["start_coord"],
                    end_coord=seg["end_coord"],
                    vertices=[
                        {
                            "lat": round(v.lat, 7),
                            "lon_east": round(normalize_longitude_360(v.lon_east), 7),
                            "label": v.stop_label,
                            "target_id": v.target_id,
                        }
                        for v in verts
                    ],
                    geometry_geojson=seg.get("geometry_geojson"),
                    corridor_polygon=seg.get("corridor_polygon", []),
                    corridor_area_m2=round(seg_area_m2, 2),
                    cumulative_start_m=seg.get("cumulative_start_m"),
                    cumulative_end_m=seg.get("cumulative_end_m"),
                    geodesic_distance_m=float(seg["geodesic_distance_m"]),
                    horizontal_distance_m=float(seg.get("horizontal_distance_m") or seg["geodesic_distance_m"]),
                    surface_distance_m=float(seg["surface_distance_m"]),
                    three_d_distance_m=float(seg.get("three_d_distance_m") or seg["surface_distance_m"]),
                    straight_line_distance_m=seg.get("straight_line_distance_m"),
                    terrain_pixel_count=seg_total_px,
                    valid_terrain_pixel_count=seg_valid_px,
                    resolution_supportable=bool(seg.get("resolution_supportable", True)),
                    resolution_support_note=seg.get("resolution_support_note"),
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
                        "crs_verified": crs_verified,
                        "source_crs": orig_crs_str,
                        "mask_method": "rasterio.features.geometry_mask(all_touched=True)",
                        "convolution_buffer_m": round(conv_buffer_m, 2),
                        "convolution_buffer_px": conv_buffer_px,
                        "tri_method": tri_meta.get("tri_definition") if isinstance(tri_meta, dict) else "RMS_5m",
                        "tri_physical_radius_m": 5.0,
                        "effective_pixel_spacing_m": round(0.5 * (dx_m + dy_m), 3),
                    },
                )
            )

        # Morphology candidate detection strictly inside corridor_mask
        step_r = max(1, int(round(6.0 / dy_m)))
        step_c = max(1, int(round(6.0 / dx_m)))
        candidates: List[TerrainMorphologyCandidate] = []
        res_status = "adequate" if native_resolution_m <= 2.0 else "resolution_limited"

        for r in range(1, rows - 1, step_r):
            for c in range(1, cols - 1, step_c):
                if not corridor_mask[r, c] or nodata_mask[r, c]:
                    continue
                lat_c = float(lat_grid[r, 0])
                lon_c = float(lon_grid[0, c])

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

                seg_id = _nearest_segment_id(lat_c, lon_c, raw_segments, frame)
                cid = hashlib.sha256(
                    f"{dataset_id}:{morph_type}:{lat_c:.6f}:{lon_c:.6f}".encode()
                ).hexdigest()[:12]
                box_d_lat = (3.0 * dy_m) / max(1.0, m_lat)
                box_d_lon = (3.0 * dx_m) / max(1.0, m_lon)
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
                        detection_method="polygon_masked_dem_morphology_tri_curvature",
                        input_dataset_id=dataset_id,
                        input_product_id=source_product_id,
                        input_resolution_m=native_resolution_m,
                        detection_parameters={
                            "slope_threshold_deg": 18.0,
                            "tri_radius_m": 5.0,
                            "local_relief_threshold_m": 0.75,
                            "convolution_buffer_m": round(conv_buffer_m, 2),
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
                            f"Derived from {native_resolution_m:.2f} m/px DEM inside corridor polygon; features below {native_resolution_m * 2.0:.1f} m are unresolved.",
                            "Morphological classification is geometric only and requires optical/rover verification before operational hazard labeling.",
                        ],
                        provenance={
                            "dataset_id": dataset_id,
                            "source_product_id": source_product_id,
                            "crs_verified": crs_verified,
                        },
                    )
                )

        candidates.sort(
            key=lambda item: item.geometric_measurements.get("salience", 0.0), reverse=True
        )
        candidates = candidates[:max_candidates]

        seg_cand_map: Dict[str, List[str]] = {s.segment_id: [] for s in segment_assessments}
        for cand in candidates:
            if cand.segment_id and cand.segment_id in seg_cand_map:
                seg_cand_map[cand.segment_id].append(cand.candidate_id)
        for seg_obj in segment_assessments:
            seg_obj.morphology_candidate_ids = seg_cand_map.get(seg_obj.segment_id, [])

        corridor_dem_stats = {
            "corridor_valid_fraction": round(corridor_valid_frac, 4),
            "corridor_pixel_count": corridor_pix_total,
            "corridor_valid_pixel_count": corridor_pix_valid,
            "dem_window_bounds": {
                "min_lat": round(min_lat, 6),
                "max_lat": round(max_lat, 6),
                "min_lon": round(min_lon, 6),
                "max_lon": round(max_lon, 6),
            },
            "segment_bounds": segment_bounds_map,
            "dx_m": round(dx_m, 3),
            "dy_m": round(dy_m, 3),
            "convolution_buffer_m": round(conv_buffer_m, 2),
            "convolution_buffer_px": conv_buffer_px,
            "crs_verified": crs_verified,
            "source_crs": orig_crs_str,
        }
        return segment_assessments, candidates, corridor_dem_stats

    with rasterio.open(dem_path) as src:
        orig_crs_str = str(src.crs) if src.crs else "MISSING"
        crs_verified = bool(src.crs and validate_mars_crs(src.crs.to_wkt()))
        if require_verified_crs and not crs_verified:
            raise ValueError(
                f"DEM '{source_product_id}' failed Mars CRS verification (got '{orig_crs_str}'); "
                "refusing silent Earth WGS84 assumption."
            )
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS, resampling=Resampling.nearest) as vrt:
                return _run_on_reader(vrt, crs_verified, orig_crs_str)
        return _run_on_reader(src, crs_verified, orig_crs_str)
