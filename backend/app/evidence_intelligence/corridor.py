"""
MARSCOPE Corridor Polygon Construction & Resolution-Aware Route Segmentation
Martian Surface Intelligence & Exploration System

Constructs true Shapely buffered corridor polygons in a local Mars Equirectangular
metric tangent projection tied to IAU2000:49900, preserves full intermediate
route vertices and GeoJSON geometries per segment, and computes exact metric
corridor areas without arbitrary pixel clamping.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from pyproj import CRS, Transformer
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box

from app.evidence_intelligence.schemas import CorridorPolygon
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, normalize_longitude_360
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import RouteCoordinateInput, RouteVertex


class MarsLocalFrame:
    """Bi-directional metric tangent frame anchored to IAU2000:49900."""

    def __init__(self, center_lat: float, center_lon_east: float) -> None:
        self.center_lat = float(center_lat)
        self.center_lon_east = float(normalize_longitude_360(center_lon_east))
        geog_proj4 = f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
        local_proj4 = (
            f"+proj=eqc +lat_ts={self.center_lat:.6f} +lon_0={self.center_lon_east:.6f} "
            f"+a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +units=m +no_defs"
        )
        self.geog_crs = CRS.from_proj4(geog_proj4)
        self.local_crs = CRS.from_proj4(local_proj4)
        self.local_proj4 = local_proj4
        self._to_m = Transformer.from_crs(self.geog_crs, self.local_crs, always_xy=True)
        self._to_ll = Transformer.from_crs(self.local_crs, self.geog_crs, always_xy=True)

    @staticmethod
    def _unwrap_lon(lon: float, ref_lon: float) -> float:
        delta = (lon - ref_lon + 180.0) % 360.0 - 180.0
        return ref_lon + delta

    def to_metric(self, lon_east: float, lat: float) -> Tuple[float, float]:
        lon_u = self._unwrap_lon(float(lon_east), self.center_lon_east)
        return self._to_m.transform(lon_u, float(lat))

    def to_lonlat(self, x: float, y: float) -> Tuple[float, float]:
        lon, lat = self._to_ll.transform(float(x), float(y))
        return float(normalize_longitude_360(lon)), float(lat)

    def to_metric_geom(self, geom: Any) -> Any:
        def _fn(coords: np.ndarray) -> np.ndarray:
            lons = np.array([self._unwrap_lon(float(x), self.center_lon_east) for x in coords[:, 0]])
            lats = coords[:, 1]
            xs, ys = self._to_m.transform(lons, lats)
            return np.column_stack([xs, ys])

        return shapely.transform(geom, _fn)

    def to_lonlat_geom(self, geom: Any) -> Any:
        def _fn(coords: np.ndarray) -> np.ndarray:
            lons, lats = self._to_ll.transform(coords[:, 0], coords[:, 1])
            lons_n = np.array([normalize_longitude_360(float(v)) for v in lons])
            return np.column_stack([lons_n, lats])

        return shapely.transform(geom, _fn)

    @property
    def projection_label(self) -> str:
        return f"IAU2000:49900 -> Mars Equirectangular Tangent ({self.center_lat:.4f}, {self.center_lon_east:.4f}E)"


def _dem_clip_polygon_metric(
    frame: MarsLocalFrame, dem_bounds: Optional[Dict[str, float]]
) -> Optional[Polygon]:
    if not dem_bounds:
        return None
    min_lon = float(dem_bounds["min_lon"])
    max_lon = float(dem_bounds["max_lon"])
    min_lat = float(dem_bounds["min_lat"])
    max_lat = float(dem_bounds["max_lat"])
    if max_lon <= min_lon:
        # Handle antimeridian/wrap conservatively if needed
        max_lon += 360.0 if max_lon < min_lon else 0.0
    corners_ll = [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat),
    ]
    corners_m = [frame.to_metric(lon, lat) for lon, lat in corners_ll]
    return Polygon(corners_m)


def _sample_side_boundaries(
    verts: List[RouteVertex],
    frame: MarsLocalFrame,
    half_w_m: float,
    dem_bounds: Optional[Dict[str, float]],
) -> Tuple[List[List[float]], List[List[float]], bool]:
    xy = [frame.to_metric(v.lon_east, v.lat) for v in verts]
    left_pts: List[List[float]] = []
    right_pts: List[List[float]] = []
    clipped = False
    n = len(xy)
    for idx in range(n):
        if idx == 0:
            dx = xy[1][0] - xy[0][0]
            dy = xy[1][1] - xy[0][1]
        elif idx == n - 1:
            dx = xy[-1][0] - xy[-2][0]
            dy = xy[-1][1] - xy[-2][1]
        else:
            dx = xy[idx + 1][0] - xy[idx - 1][0]
            dy = xy[idx + 1][1] - xy[idx - 1][1]
        norm = math.hypot(dx, dy)
        if norm < 1e-6:
            nx, ny = 0.0, 1.0
        else:
            nx, ny = -dy / norm, dx / norm
        lx, ly = xy[idx][0] + nx * half_w_m, xy[idx][1] + ny * half_w_m
        rx, ry = xy[idx][0] - nx * half_w_m, xy[idx][1] - ny * half_w_m
        l_lon, l_lat = frame.to_lonlat(lx, ly)
        r_lon, r_lat = frame.to_lonlat(rx, ry)
        if dem_bounds:
            cl_lon = min(max(l_lon, dem_bounds["min_lon"]), dem_bounds["max_lon"])
            cl_lat = min(max(l_lat, dem_bounds["min_lat"]), dem_bounds["max_lat"])
            cr_lon = min(max(r_lon, dem_bounds["min_lon"]), dem_bounds["max_lon"])
            cr_lat = min(max(r_lat, dem_bounds["min_lat"]), dem_bounds["max_lat"])
            if (cl_lon, cl_lat) != (l_lon, l_lat) or (cr_lon, cr_lat) != (r_lon, r_lat):
                clipped = True
            l_lon, l_lat = cl_lon, cl_lat
            r_lon, r_lat = cr_lon, cr_lat
        left_pts.append([round(l_lon, 7), round(l_lat, 7)])
        right_pts.append([round(r_lon, 7), round(r_lat, 7)])
    return left_pts, right_pts, clipped


def _extract_primary_ring(geom: Any) -> List[List[float]]:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        coords = [[round(float(x), 7), round(float(y), 7)] for x, y in geom.exterior.coords]
        if coords and coords[0] != coords[-1]:
            coords.append(list(coords[0]))
        return coords
    if geom.geom_type == "MultiPolygon":
        largest = max(geom.geoms, key=lambda g: g.area)
        coords = [[round(float(x), 7), round(float(y), 7)] for x, y in largest.exterior.coords]
        if coords and coords[0] != coords[-1]:
            coords.append(list(coords[0]))
        return coords
    return []


def build_route_corridor(
    vertices: List[RouteVertex],
    corridor_width_m: float = 60.0,
    dem_bounds: Optional[Dict[str, float]] = None,
) -> CorridorPolygon:
    """
    Build a true Shapely polygon buffer of width `corridor_width_m` around the route
    centerline in Mars metric projection, clipped to DEM bounds when provided.
    """
    if len(vertices) < 2:
        raise ValueError("At least 2 route vertices are required to construct a corridor polygon.")

    center_lat = sum(v.lat for v in vertices) / float(len(vertices))
    center_lon = sum(normalize_longitude_360(v.lon_east) for v in vertices) / float(len(vertices))
    frame = MarsLocalFrame(center_lat, center_lon)

    half_w = 0.5 * float(corridor_width_m)
    line_m = LineString([frame.to_metric(v.lon_east, v.lat) for v in vertices])
    poly_m = line_m.buffer(half_w, quad_segs=12, cap_style="round", join_style="round")

    clipped = False
    clip_box_m = _dem_clip_polygon_metric(frame, dem_bounds)
    if clip_box_m is not None:
        inter = poly_m.intersection(clip_box_m)
        if not inter.is_empty:
            clipped = inter.area < poly_m.area * 0.9999
            poly_m = inter

    corridor_area_m2 = round(float(poly_m.area), 3)
    poly_ll = frame.to_lonlat_geom(poly_m)
    ring = _extract_primary_ring(poly_ll)
    left_pts, right_pts, side_clipped = _sample_side_boundaries(vertices, frame, half_w, dem_bounds)
    centerline = [[round(normalize_longitude_360(v.lon_east), 7), round(v.lat, 7)] for v in vertices]

    return CorridorPolygon(
        centerline=centerline,
        left_boundary=left_pts,
        right_boundary=right_pts,
        polygon_ring=ring,
        clipped_to_dem_footprint=bool(clipped or side_clipped),
        clipped_to_dem_bounds=bool(dem_bounds is not None),
        corridor_area_m2=corridor_area_m2,
        projection=frame.projection_label,
        projection_epsg_or_wkt=frame.local_proj4,
        corridor_width_m=float(corridor_width_m),
        polygon_wkt=poly_ll.wkt,
    )


def determine_segment_scale_info(
    native_resolution_m: float, requested_scale_m: Optional[float] = None
) -> Tuple[float, bool, str]:
    """
    Determine resolution-appropriate segment length scale without forced arbitrary pixel clamping.
    Returns (scale_m, supportable_by_native_dem, note).
    """
    res = max(0.05, float(native_resolution_m))
    if requested_scale_m is not None and requested_scale_m > 0:
        req = float(requested_scale_m)
        min_supportable = max(5.0, res * 2.0)
        supportable = req >= min_supportable
        note = (
            f"Requested {req:.1f} m segment length is supported by {res:.2f} m/px DEM (>= 2px = {min_supportable:.1f} m)."
            if supportable
            else f"Requested {req:.1f} m segment length is finer than 2px of {res:.2f} m/px DEM ({min_supportable:.1f} m); segment marked resolution-unsupported."
        )
        return req, supportable, note

    if res <= 2.0:
        default_scale = 60.0
        return default_scale, True, f"High-resolution {res:.2f} m/px DEM cleanly supports 60.0 m segmentation."
    elif res <= 25.0:
        scale = round(max(60.0, res * 5.0), 1)
        return scale, True, f"Medium-resolution {res:.1f} m/px DEM mapped to {scale:.1f} m (~5px) segments."
    else:
        scale = round(max(60.0, res * 2.0), 1)
        return (
            scale,
            False,
            f"Coarse {res:.1f} m/px regional DEM requires >= {scale:.1f} m (2px) segments and cannot resolve local Marswalk terrain.",
        )


def determine_segment_scale_m(
    native_resolution_m: float, requested_scale_m: Optional[float] = None
) -> float:
    """Scalar wrapper returning segment scale in meters."""
    scale, _, _ = determine_segment_scale_info(native_resolution_m, requested_scale_m)
    return scale


def _interp_vertex(v0: RouteVertex, v1: RouteVertex, frac: float, seq_num: int) -> RouteVertex:
    lon0 = normalize_longitude_360(v0.lon_east)
    lon1 = normalize_longitude_360(v1.lon_east)
    d_lon = (lon1 - lon0 + 180.0) % 360.0 - 180.0
    lat = v0.lat + frac * (v1.lat - v0.lat)
    lon = normalize_longitude_360(lon0 + frac * d_lon)
    elev = v0.elevation_m + frac * (v1.elevation_m - v0.elevation_m)
    cum = v0.cumulative_distance_m + frac * (v1.cumulative_distance_m - v0.cumulative_distance_m)
    return RouteVertex(
        seq=seq_num,
        lat=round(lat, 7),
        lon_east=round(lon, 7),
        elevation_m=round(elev, 3),
        cumulative_distance_m=round(cum, 3),
        segment_distance_m=0.0,
    )


def segment_route_by_scale(
    vertices: List[RouteVertex],
    segment_scale_m: float = 60.0,
    corridor_width_m: float = 60.0,
    dem_bounds: Optional[Dict[str, float]] = None,
    native_resolution_m: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Partition route polyline at `segment_scale_m` boundaries while preserving ALL
    intermediate route vertices, exact GeoJSON LineString, per-segment Shapely corridor
    polygons, metric area, and distinct distance definitions.
    """
    if len(vertices) < 2:
        return []

    _, supportable, support_note = determine_segment_scale_info(native_resolution_m, segment_scale_m)
    center_lat = sum(v.lat for v in vertices) / float(len(vertices))
    center_lon = sum(normalize_longitude_360(v.lon_east) for v in vertices) / float(len(vertices))
    frame = MarsLocalFrame(center_lat, center_lon)
    clip_box_m = _dem_clip_polygon_metric(frame, dem_bounds)
    half_w = 0.5 * float(corridor_width_m)

    # First ensure cumulative distances are consistent along vertices
    cum_list: List[float] = [0.0]
    for i in range(1, len(vertices)):
        d = mars_great_circle_distance_meters(
            vertices[i - 1].lat,
            vertices[i - 1].lon_east,
            vertices[i].lat,
            vertices[i].lon_east,
        )
        cum_list.append(cum_list[-1] + d)
    total_horiz = cum_list[-1]

    buckets: List[Tuple[float, float, List[RouteVertex]]] = []
    cur_start_dist = 0.0
    next_cut = float(segment_scale_m)
    cur_verts: List[RouteVertex] = [vertices[0].model_copy()]

    for i in range(1, len(vertices)):
        v_prev = vertices[i - 1]
        v_curr = vertices[i]
        d_prev = cum_list[i - 1]
        d_curr = cum_list[i]
        seg_len = max(1e-6, d_curr - d_prev)

        while next_cut < d_curr - 1e-3 and next_cut < total_horiz - 1e-3:
            frac = max(0.0, min(1.0, (next_cut - d_prev) / seg_len))
            split_v = _interp_vertex(v_prev, v_curr, frac, seq_num=len(cur_verts))
            cur_verts.append(split_v)
            buckets.append((cur_start_dist, next_cut, cur_verts))
            cur_start_dist = next_cut
            cur_verts = [split_v.model_copy()]
            next_cut += float(segment_scale_m)

        cur_verts.append(v_curr.model_copy())

    if len(cur_verts) >= 2:
        buckets.append((cur_start_dist, total_horiz, cur_verts))
    elif buckets and len(cur_verts) == 1:
        # Append trailing tiny remainder vertex to the final bucket cleanly
        buckets[-1][2].append(cur_verts[0])
        buckets[-1] = (buckets[-1][0], total_horiz, buckets[-1][2])

    raw_segments: List[Dict[str, Any]] = []
    for idx, (d_start, d_end, seg_verts) in enumerate(buckets):
        horiz_d = 0.0
        surf_d = 0.0
        for j in range(1, len(seg_verts)):
            dh = mars_great_circle_distance_meters(
                seg_verts[j - 1].lat,
                seg_verts[j - 1].lon_east,
                seg_verts[j].lat,
                seg_verts[j].lon_east,
            )
            dz = float(seg_verts[j].elevation_m) - float(seg_verts[j - 1].elevation_m)
            horiz_d += dh
            surf_d += math.hypot(dh, dz)

        straight_h = mars_great_circle_distance_meters(
            seg_verts[0].lat,
            seg_verts[0].lon_east,
            seg_verts[-1].lat,
            seg_verts[-1].lon_east,
        )

        pts_m = [frame.to_metric(v.lon_east, v.lat) for v in seg_verts]
        line_m = LineString(pts_m)
        seg_poly_m = line_m.buffer(half_w, quad_segs=10, cap_style="round", join_style="round")
        if clip_box_m is not None:
            inter = seg_poly_m.intersection(clip_box_m)
            if not inter.is_empty:
                seg_poly_m = inter

        seg_area_m2 = round(float(seg_poly_m.area), 3)
        seg_poly_ll = frame.to_lonlat_geom(seg_poly_m)
        seg_ring = _extract_primary_ring(seg_poly_ll)

        start_c = RouteCoordinateInput(
            lat=round(seg_verts[0].lat, 7),
            lon_east=round(normalize_longitude_360(seg_verts[0].lon_east), 7),
            label=f"SEG-{idx + 1:03d}-start",
        )
        end_c = RouteCoordinateInput(
            lat=round(seg_verts[-1].lat, 7),
            lon_east=round(normalize_longitude_360(seg_verts[-1].lon_east), 7),
            label=f"SEG-{idx + 1:03d}-end",
        )
        geom_geojson = {
            "type": "LineString",
            "coordinates": [
                [round(normalize_longitude_360(v.lon_east), 7), round(v.lat, 7), round(float(v.elevation_m), 3)]
                for v in seg_verts
            ],
        }

        raw_segments.append(
            {
                "segment_id": f"SEG-{idx + 1:03d}",
                "segment_index": idx,
                "start_coord": start_c,
                "end_coord": end_c,
                "vertices": seg_verts,
                "geometry_geojson": geom_geojson,
                "corridor_polygon": seg_ring,
                "corridor_polygon_ll": seg_poly_ll,
                "corridor_area_m2": seg_area_m2,
                "cumulative_start_m": round(d_start, 2),
                "cumulative_end_m": round(d_end, 2),
                "geodesic_distance_m": round(horiz_d, 2),
                "horizontal_distance_m": round(horiz_d, 2),
                "surface_distance_m": round(surf_d, 2),
                "three_d_distance_m": round(surf_d, 2),
                "straight_line_distance_m": round(straight_h, 2),
                "resolution_supportable": supportable,
                "resolution_support_note": support_note,
            }
        )

    return raw_segments
