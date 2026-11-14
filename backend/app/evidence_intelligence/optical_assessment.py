"""
MARSCOPE Corridor Optical Evidence Assessment
Martian Surface Intelligence & Exploration System

Computes true per-segment optical footprint & valid-pixel coverage via Shapely
union (preventing >1.0 double-counting across overlapping products), constrains
all optical candidates strictly to the assessed corridor polygon, and records
exact Shapely distances to complete route LineString & corridor geometries.
"""

from __future__ import annotations

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
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from app.evidence_intelligence.corridor import MarsLocalFrame
from app.evidence_intelligence.schemas import CorridorSegmentAssessment
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, normalize_longitude_360
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.terrain.optical_analysis import (
    OpticalCandidateFeature,
    RejectedOpticalCandidate,
    analyze_optical_region,
)

MARS_GEOG_CRS = rasterio.crs.CRS.from_proj4(
    f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
)


def _segment_linestring_metric(seg: CorridorSegmentAssessment, frame: MarsLocalFrame) -> LineString:
    if seg.vertices and len(seg.vertices) >= 2:
        pts = [frame.to_metric(v.lon_east, v.lat) for v in seg.vertices]
    else:
        pts = [
            frame.to_metric(seg.start_coord.lon_east, seg.start_coord.lat),
            frame.to_metric(seg.end_coord.lon_east, seg.end_coord.lat),
        ]
    return LineString(pts)


def _segment_polygon_ll(seg: CorridorSegmentAssessment, frame: MarsLocalFrame, width_m: float = 60.0) -> Any:
    if seg.corridor_polygon and len(seg.corridor_polygon) >= 4:
        return Polygon(seg.corridor_polygon)
    line_m = _segment_linestring_metric(seg, frame)
    poly_m = line_m.buffer(0.5 * width_m, cap_style="round", join_style="round")
    return frame.to_lonlat_geom(poly_m)


def _align_geom_to_bounds(geom: Any, bounds: Any) -> Any:
    g_minx, _, g_maxx, _ = geom.bounds
    if bounds.right <= 180.0 + 1e-6 and g_maxx > 180.0 + 1e-6:
        return shapely.transform(geom, lambda xy: np.column_stack([xy[:, 0] - 360.0, xy[:, 1]]))
    if bounds.left >= 180.0 and g_minx < 0.0:
        return shapely.transform(geom, lambda xy: np.column_stack([xy[:, 0] + 360.0, xy[:, 1]]))
    return geom


def _open_ortho_coverage_helper(
    open_path: Path,
    bounds_ll: Dict[str, float],
    grid_h: int = 240,
    grid_w: int = 240,
) -> Tuple[Optional[box], Optional[np.ndarray], Optional[rasterio.Affine]]:
    """
    Open an optical raster (GeoTIFF / PDS3), compute its [0, 360) bounding box,
    and resample a valid-pixel mask onto the shared `bounds_ll` window grid so
    overlapping products can be cleanly OR-unioned without double counting.
    """
    if not open_path.exists():
        return None, None, None

    min_lon = float(bounds_ll["min_lon"])
    max_lon = float(bounds_ll["max_lon"])
    min_lat = float(bounds_ll["min_lat"])
    max_lat = float(bounds_ll["max_lat"])
    if max_lon <= min_lon or max_lat <= min_lat:
        return None, None, None

    dst_transform = rasterio.transform.from_bounds(min_lon, min_lat, max_lon, max_lat, grid_w, grid_h)

    def _inspect(reader: Any) -> Tuple[Optional[box], Optional[np.ndarray], Optional[rasterio.Affine]]:
        rb = reader.bounds
        # Normalize footprint box into [0, 360) if needed
        fb_left = normalize_longitude_360(float(rb.left)) if rb.left < 0 else float(rb.left)
        fb_right = normalize_longitude_360(float(rb.right)) if rb.right < 0 else float(rb.right)
        if fb_right < fb_left:
            fb_right += 360.0
        foot_box = box(fb_left, float(rb.bottom), fb_right, float(rb.top))

        q_min_lon = min_lon - 360.0 if (rb.right <= 180.0 and min_lon > 180.0) else min_lon
        q_max_lon = max_lon - 360.0 if (rb.right <= 180.0 and max_lon > 180.0) else max_lon
        if q_max_lon <= rb.left or q_min_lon >= rb.right or max_lat <= rb.bottom or min_lat >= rb.top:
            return foot_box, np.zeros((grid_h, grid_w), dtype=bool), dst_transform

        win = from_bounds(
            max(rb.left, q_min_lon),
            max(rb.bottom, min_lat),
            min(rb.right, q_max_lon),
            min(rb.top, max_lat),
            reader.transform,
        )
        # Reproject / sample directly into the shared corridor boolean valid grid
        with WarpedVRT(
            reader,
            crs=MARS_GEOG_CRS,
            transform=rasterio.transform.from_bounds(q_min_lon, min_lat, q_max_lon, max_lat, grid_w, grid_h),
            width=grid_w,
            height=grid_h,
            resampling=Resampling.nearest,
        ) as warped:
            arr = warped.read(1).astype(np.float64)
            nodata_val = warped.nodata
            valid = np.isfinite(arr) & (arr > 0.0)
            if nodata_val is not None:
                valid &= ~np.isclose(arr, float(nodata_val), equal_nan=True)
            return foot_box, valid, dst_transform

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _inspect(vrt)
        return _inspect(src)


def assess_corridor_optical_evidence(
    *,
    catalog_service: Any,
    raw_dir: Path,
    ortho_dataset_id: Optional[str],
    ortho_dataset_ids: Optional[List[str]] = None,
    dem_bounds: Dict[str, float],
    segments: List[CorridorSegmentAssessment],
    corridor_width_m: float = 60.0,
    max_candidates: int = 36,
) -> Tuple[
    List[OpticalCandidateFeature],
    List[RejectedOpticalCandidate],
    float,
    str,
    Dict[str, Any],
]:
    """
    Execute corridor-constrained optical analysis across one or more local ortho products,
    compute per-segment unioned footprint + valid-pixel coverage fractions (capped in [0, 1]),
    and filter candidates strictly to the assessed corridor polygon.
    """
    product_ids_ordered: List[str] = []
    for ds_id in [ortho_dataset_id] + list(ortho_dataset_ids or []):
        if ds_id and ds_id not in product_ids_ordered:
            product_ids_ordered.append(ds_id)

    if not product_ids_ordered:
        for seg in segments:
            seg.coverage.optical_footprint_coverage_fraction = 0.0
            seg.coverage.valid_optical_pixel_coverage_fraction = 0.0
            seg.coverage.optical_coverage_fraction = 0.0
            seg.coverage.optical_covered_area_m2 = 0.0
            seg.coverage.optical_contributing_product_ids = []
            seg.coverage.optical_quality_note = "No locally acquired HiRISE orthophoto covering this corridor."
        return (
            [],
            [],
            0.0,
            "No locally acquired HiRISE orthophoto covering this corridor.",
            {"available": False, "dataset_id": None, "dataset_ids": []},
        )

    if not segments:
        return [], [], 0.0, "No route segments available for optical assessment.", {"available": False}

    mean_lat = sum(0.5 * (s.start_coord.lat + s.end_coord.lat) for s in segments) / len(segments)
    mean_lon = sum(0.5 * (s.start_coord.lon_east + s.end_coord.lon_east) for s in segments) / len(segments)
    frame = MarsLocalFrame(mean_lat, mean_lon)

    seg_lines_m = {s.segment_id: _segment_linestring_metric(s, frame) for s in segments}
    seg_polys_ll = {s.segment_id: _segment_polygon_ll(s, frame, corridor_width_m) for s in segments}
    seg_polys_m = {sid: frame.to_metric_geom(poly) for sid, poly in seg_polys_ll.items()}
    overall_poly_m = unary_union(list(seg_polys_m.values()))

    grid_h, grid_w = 240, 240
    union_valid_mask = np.zeros((grid_h, grid_w), dtype=bool)
    shared_transform = None
    footprint_boxes_m: List[Any] = []
    contributing_products: List[Tuple[str, str, box]] = []

    raw_candidates: List[OpticalCandidateFeature] = []
    raw_rejected: List[RejectedOpticalCandidate] = []
    primary_meta: Dict[str, Any] = {}
    notes: List[str] = []

    for idx_ds, ds_id in enumerate(product_ids_ordered):
        ds = catalog_service.get_dataset(ds_id)
        if ds is not None:
            try:
                open_path, _ = _resolve_raw_dem_open_path(ds, raw_dir)
                foot_box, valid_grid, dst_tr = _open_ortho_coverage_helper(
                    open_path, dem_bounds, grid_h=grid_h, grid_w=grid_w
                )
                if foot_box is not None and valid_grid is not None:
                    union_valid_mask |= valid_grid
                    shared_transform = dst_tr
                    foot_m = frame.to_metric_geom(foot_box)
                    footprint_boxes_m.append(foot_m)
                    contributing_products.append((ds.id, ds.product_id, foot_box))
            except Exception:
                pass

        try:
            res = analyze_optical_region(
                catalog_service=catalog_service,
                raw_dir=raw_dir,
                dataset_id=ds_id,
                min_lat=dem_bounds["min_lat"],
                max_lat=dem_bounds["max_lat"],
                min_lon=dem_bounds["min_lon"],
                max_lon=dem_bounds["max_lon"],
                max_candidates=max_candidates,
            )
            if idx_ds == 0:
                primary_meta = {
                    "available": res.available,
                    "dataset_id": res.ortho_dataset_id or ds_id,
                    "source_product_id": res.product_id or ds_id,
                    "native_pixel_scale_m": res.native_pixel_scale_m,
                    "bounds": res.bounds,
                }
            if res.available:
                raw_candidates.extend(res.candidates)
                raw_rejected.extend(res.rejected_candidates)
                notes.append(
                    f"{res.product_id or ds_id} ({res.valid_coverage_fraction * 100:.1f}% window valid)"
                )
            elif res.unavailable_reason:
                notes.append(res.unavailable_reason)
        except Exception as exc:
            notes.append(f"{ds_id} error: {exc}")

    footprint_union_m = unary_union(footprint_boxes_m) if footprint_boxes_m else None

    # Compute exact per-segment footprint + valid pixel coverage using spatial union (<= 1.0)
    corridor_total_area_m2 = 0.0
    corridor_covered_area_m2 = 0.0

    for seg in segments:
        poly_m = seg_polys_m[seg.segment_id]
        poly_ll = seg_polys_ll[seg.segment_id]
        seg_area = max(1e-6, float(poly_m.area))
        corridor_total_area_m2 += seg_area

        if footprint_union_m is not None:
            inter_area = float(poly_m.intersection(footprint_union_m).area)
            foot_cov = min(1.0, max(0.0, inter_area / seg_area))
        else:
            foot_cov = 0.0

        if shared_transform is not None and union_valid_mask.any():
            seg_mask = geometry_mask(
                [poly_ll],
                out_shape=(grid_h, grid_w),
                transform=shared_transform,
                invert=True,
                all_touched=True,
            )
            seg_px = int(np.count_nonzero(seg_mask))
            val_px = int(np.count_nonzero(seg_mask & union_valid_mask))
            px_cov = float(val_px) / float(seg_px) if seg_px > 0 else 0.0
        else:
            px_cov = 0.0

        px_cov = min(1.0, max(0.0, px_cov))
        # Valid optical pixel coverage cannot exceed optical footprint coverage if footprint is tiny/zero
        if foot_cov <= 0.0:
            px_cov = 0.0

        seg_contribs = [
            prod_id
            for (_ds_id, prod_id, fbox) in contributing_products
            if poly_ll.intersects(fbox)
        ]

        seg.coverage.optical_footprint_coverage_fraction = round(foot_cov, 4)
        seg.coverage.valid_optical_pixel_coverage_fraction = round(px_cov, 4)
        seg.coverage.optical_coverage_fraction = round(px_cov, 4)
        seg.coverage.optical_covered_area_m2 = round(seg_area * px_cov, 2)
        seg.coverage.optical_contributing_product_ids = seg_contribs
        seg.coverage.optical_quality_note = (
            f"Segment {seg.segment_id}: {px_cov * 100:.1f}% valid optical pixels across "
            f"{foot_cov * 100:.1f}% footprint ({', '.join(seg_contribs) if seg_contribs else 'none'})."
        )
        corridor_covered_area_m2 += seg_area * px_cov

    corridor_valid_cov = (
        round(min(1.0, corridor_covered_area_m2 / corridor_total_area_m2), 4)
        if corridor_total_area_m2 > 0
        else 0.0
    )

    # Filter & associate every optical candidate strictly inside the assessed corridor polygon
    kept_candidates: List[OpticalCandidateFeature] = []
    seg_cand_map: Dict[str, List[str]] = {s.segment_id: [] for s in segments}

    for cand in raw_candidates:
        pt_m = Point(frame.to_metric(cand.longitude_east, cand.latitude))
        in_corridor = bool(overall_poly_m.contains(pt_m) or overall_poly_m.distance(pt_m) <= 1e-6)
        dist_corridor = 0.0 if in_corridor else float(overall_poly_m.distance(pt_m))

        best_seg_id: Optional[str] = None
        best_route_dist = float("inf")
        for s in segments:
            d = float(seg_lines_m[s.segment_id].distance(pt_m))
            if d < best_route_dist:
                best_route_dist = d
                best_seg_id = s.segment_id

        cand.in_corridor = in_corridor
        cand.distance_from_route_m = round(best_route_dist, 2)
        cand.distance_from_corridor_m = round(dist_corridor, 2)
        cand.nearest_segment_id = best_seg_id
        cand.association_type = "INTERSECTS_CORRIDOR" if in_corridor else "OUTSIDE_CORRIDOR"

        if not in_corridor:
            raw_rejected.append(
                RejectedOpticalCandidate(
                    feature_id=cand.feature_id,
                    latitude=cand.latitude,
                    longitude_east=cand.longitude_east,
                    rejection_reason=(
                        f"Excluded outside assessed corridor polygon "
                        f"({dist_corridor:.1f} m outside corridor boundary)."
                    ),
                    valid_pixel_fraction=cand.valid_pixel_fraction,
                    local_contrast_zscore=cand.local_contrast_zscore,
                )
            )
            continue

        kept_candidates.append(cand)
        if best_seg_id and best_seg_id in seg_cand_map:
            seg_cand_map[best_seg_id].append(cand.feature_id)

    for seg in segments:
        seg.optical_candidate_ids = seg_cand_map.get(seg.segment_id, [])

    kept_candidates = kept_candidates[:max_candidates]
    note = (
        f"Corridor optical evidence ({'; '.join(notes)}): {len(kept_candidates)} in-corridor candidates, "
        f"{len(raw_rejected)} rejected/excluded, area-weighted valid coverage {corridor_valid_cov * 100:.1f}%."
        if notes
        else "No usable optical analysis available."
    )
    meta = {
        **primary_meta,
        "available": bool(primary_meta.get("available") or kept_candidates or corridor_valid_cov > 0),
        "dataset_ids": product_ids_ordered,
        "contributing_product_ids": [p[1] for p in contributing_products],
        "candidate_count": len(kept_candidates),
        "rejected_count": len(raw_rejected),
        "corridor_valid_coverage_fraction": corridor_valid_cov,
        "analysis_note": note,
    }
    return kept_candidates, raw_rejected[:50], corridor_valid_cov, note, meta
