"""
MARSCOPE Corridor Geometry & Resolution-Driven Route Segmentation
Martian Surface Intelligence & Exploration System

Builds Mars geographic corridors using spherical Mars geometry (IAU2000:49900,
R = 3,396,190.0 m) and local tangent-plane East/North meters.
Segment length is determined from source DEM resolution and requested analysis
scale (never an arbitrary fixed count). Corridor bounds are strictly clipped to
available DEM extent.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from app.evidence_intelligence.schemas import CorridorPolygon
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, normalize_longitude_360
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import RouteCoordinateInput, RouteVertex


def _local_meters_to_latlon(
    east_m: float, north_m: float, origin_lat: float, origin_lon_east: float
) -> Tuple[float, float]:
    m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
    m_per_deg_lon = (
        MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(origin_lat)) * math.pi / 180.0
    )
    lat = origin_lat + (north_m / m_per_deg_lat)
    lon = normalize_longitude_360(origin_lon_east + (east_m / max(1e-6, m_per_deg_lon)))
    return lat, lon


def _latlon_to_local_meters(
    lat: float, lon_east: float, origin_lat: float, origin_lon_east: float
) -> Tuple[float, float]:
    m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
    m_per_deg_lon = (
        MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(origin_lat)) * math.pi / 180.0
    )
    dlon = ((lon_east - origin_lon_east + 180.0) % 360.0) - 180.0
    return dlon * m_per_deg_lon, (lat - origin_lat) * m_per_deg_lat


def build_route_corridor(
    vertices: List[RouteVertex],
    *,
    corridor_width_m: float,
    dem_bounds: Dict[str, float],
) -> CorridorPolygon:
    """Construct left/right corridor boundaries and clipped polygon around route vertices."""
    if len(vertices) < 2:
        raise ValueError("Route must contain at least 2 vertices to construct a corridor.")

    origin_lat = sum(v.lat for v in vertices) / float(len(vertices))
    origin_lon = normalize_longitude_360(
        sum(v.lon_east for v in vertices) / float(len(vertices))
    )
    half_w = 0.5 * float(corridor_width_m)

    xy = [
        _latlon_to_local_meters(v.lat, v.lon_east, origin_lat, origin_lon)
        for v in vertices
    ]

    left_pts: List[List[float]] = []
    right_pts: List[List[float]] = []
    center_pts: List[List[float]] = []
    clipped = False

    min_lat_b = dem_bounds["min_lat"]
    max_lat_b = dem_bounds["max_lat"]
    min_lon_b = normalize_longitude_360(dem_bounds["min_lon"])
    max_lon_b = normalize_longitude_360(dem_bounds["max_lon"])

    def _clip_pt(lat_v: float, lon_v: float) -> List[float]:
        nonlocal clipped
        lat_c = max(min_lat_b, min(max_lat_b, lat_v))
        lon_c = max(min_lon_b, min(max_lon_b, lon_v))
        if abs(lat_c - lat_v) > 1e-8 or abs(lon_c - lon_v) > 1e-8:
            clipped = True
        return [round(lon_c, 7), round(lat_c, 7)]

    for i, (ex, ny) in enumerate(xy):
        if i == 0:
            dx, dy = xy[1][0] - ex, xy[1][1] - ny
        elif i == len(xy) - 1:
            dx, dy = ex - xy[i - 1][0], ny - xy[i - 1][1]
        else:
            dx, dy = xy[i + 1][0] - xy[i - 1][0], xy[i + 1][1] - xy[i - 1][1]
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-6:
            nx, ny_n = 0.0, 1.0
        else:
            # Left normal (-dy, dx)
            nx, ny_n = -dy / seg_len, dx / seg_len

        center_pts.append([round(vertices[i].lon_east, 7), round(vertices[i].lat, 7)])
        l_lat, l_lon = _local_meters_to_latlon(ex + nx * half_w, ny + ny_n * half_w, origin_lat, origin_lon)
        r_lat, r_lon = _local_meters_to_latlon(ex - nx * half_w, ny - ny_n * half_w, origin_lat, origin_lon)
        left_pts.append(_clip_pt(l_lat, l_lon))
        right_pts.append(_clip_pt(r_lat, r_lon))

    ring = left_pts + list(reversed(right_pts)) + [left_pts[0]]
    return CorridorPolygon(
        centerline=center_pts,
        left_boundary=left_pts,
        right_boundary=right_pts,
        polygon_ring=ring,
        clipped_to_dem_footprint=clipped,
        projection=f"Mars_Local_Tangent_Equirectangular(IAU2000:49900, lat0={origin_lat:.5f}, lon0={origin_lon:.5f})",
        corridor_width_m=round(corridor_width_m, 2),
    )


def determine_segment_scale_m(
    native_resolution_m: float,
    requested_scale_m: Optional[float] = None,
) -> float:
    """
    Determine route segmentation length from native DEM resolution (>= 25 * native_res
    for statistical neighborhood support, bounded cleanly to [35 m, 250 m] unless
    explicitly configured above the minimum resolvable threshold).
    """
    min_supported = max(25.0, native_resolution_m * 25.0)
    if requested_scale_m is not None:
        return round(max(min_supported, float(requested_scale_m)), 2)
    if native_resolution_m <= 2.0:
        return 60.0
    if native_resolution_m <= 20.0:
        return max(min_supported, 120.0)
    return max(min_supported, min(1000.0, native_resolution_m * 10.0))


def segment_route_by_scale(
    vertices: List[RouteVertex],
    *,
    segment_scale_m: float,
) -> List[Dict[str, object]]:
    """
    Partition route vertices into contiguous spatial segments matching `segment_scale_m`
    while preserving exact original route vertices without geometric alteration.
    """
    if len(vertices) < 2:
        return []

    segments: List[Dict[str, object]] = []
    seg_start_idx = 0
    accum_m = 0.0

    for i in range(1, len(vertices)):
        v_prev = vertices[i - 1]
        v_curr = vertices[i]
        d = mars_great_circle_distance_meters(v_prev.lat, v_prev.lon_east, v_curr.lat, v_curr.lon_east)
        accum_m += d
        is_last = i == len(vertices) - 1
        if accum_m >= segment_scale_m or is_last:
            sub = vertices[seg_start_idx : i + 1]
            surf_d = sum(
                math.hypot(
                    mars_great_circle_distance_meters(sub[k - 1].lat, sub[k - 1].lon_east, sub[k].lat, sub[k].lon_east),
                    sub[k].elevation_m - sub[k - 1].elevation_m,
                )
                for k in range(1, len(sub))
            )
            segments.append(
                {
                    "segment_index": len(segments),
                    "segment_id": f"SEG-{len(segments) + 1:03d}",
                    "start_coord": RouteCoordinateInput(lat=sub[0].lat, lon_east=sub[0].lon_east),
                    "end_coord": RouteCoordinateInput(lat=sub[-1].lat, lon_east=sub[-1].lon_east),
                    "geodesic_distance_m": round(
                        mars_great_circle_distance_meters(
                            sub[0].lat, sub[0].lon_east, sub[-1].lat, sub[-1].lon_east
                        ),
                        2,
                    ),
                    "horizontal_distance_m": round(accum_m, 2),
                    "surface_distance_m": round(surf_d, 2),
                    "vertices": sub,
                }
            )
            seg_start_idx = i
            accum_m = 0.0

    return segments
