"""
MARSCOPE Deterministic Turn-by-Turn Astronaut Navigation Generator
Computes True North spherical forward bearings, Grid North equirectangular bearings,
16-point cardinal headings, maneuver turn directives, elevation/slope summaries,
linked verified science context, and hazard proximity cautions.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import NavigationInstruction, RouteVertex


_CARDINAL_16 = (
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
)


def mars_true_north_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Spherical forward azimuth [0, 360) clockwise from Mars True North."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    az = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return az


def equirectangular_grid_north_bearing_deg(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    central_meridian_lon: float = 137.41,
) -> float:
    """
    Equirectangular grid bearing clockwise from projected Grid North (+Northing).
    Meridian convergence gamma = (lon - lon0) * sin(lat) is applied so Mars True North
    and projected Grid North are both reported transparently.
    """
    true_az = mars_true_north_bearing_deg(lat1, lon1, lat2, lon2)
    # In standard Mars Equirectangular projected DTMs (true scale at equator, Easting = R*lon),
    # projected North (+Y) points along meridians (parallel meridians on cylinder), while
    # true sphere meridian convergence differs only subtly from spherical east-scale;
    # report explicit convergence adjustment clearly.
    convergence = (lon1 - central_meridian_lon) * math.sin(math.radians(lat1))
    return (true_az - convergence + 360.0) % 360.0


def bearing_to_cardinal(bearing_deg: float) -> str:
    idx = int(round((bearing_deg % 360.0) / 22.5)) % 16
    return _CARDINAL_16[idx]


def signed_turn_angle_deg(prev_bearing: float, new_bearing: float) -> float:
    """Signed shortest turn angle in (-180, +180]: positive = Right (CW), negative = Left (CCW)."""
    diff = ((new_bearing - prev_bearing + 540.0) % 360.0) - 180.0
    return diff


def _maneuver_phrase(step_idx: int, turn_deg: Optional[float], is_return_start: bool) -> str:
    if step_idx == 0:
        return "Depart Start"
    if is_return_start:
        return "Begin Return Leg"
    if turn_deg is None:
        return "Proceed"
    abs_t = abs(turn_deg)
    if abs_t < 15.0:
        return "Continue Straight"
    direction = "Right" if turn_deg > 0 else "Left"
    if abs_t < 42.0:
        return f"Bear {direction} ({abs_t:.0f} deg)"
    if abs_t < 115.0:
        return f"Turn {direction} ({abs_t:.0f} deg)"
    return f"Sharp Turn {direction} ({abs_t:.0f} deg)"


def generate_turn_by_turn_instructions(
    vertices: List[RouteVertex],
    nearby_science_lookup: List[Tuple[str, float, float]],
    native_dem_res_m: float,
    central_meridian_lon: float = 137.41,
    coalesce_angle_deg: float = 12.0,
    coalesce_max_seg_m: float = 45.0,
) -> List[NavigationInstruction]:
    """
    Build deterministic turn-by-turn astronaut instructions from validated route vertices.
    Explicit stops (Start, Target, Destination) are ALWAYS preserved as instruction boundaries.
    """
    if len(vertices) < 2:
        return []

    # Group raw vertices into clean navigation maneuver segments breaking at stops or turns >= coalesce_angle_deg
    segments: List[Tuple[int, int]] = []
    seg_start = 0
    prev_bearing = mars_true_north_bearing_deg(
        vertices[0].lat, vertices[0].lon_east, vertices[1].lat, vertices[1].lon_east
    )

    for i in range(1, len(vertices) - 1):
        v_cur = vertices[i]
        v_nxt = vertices[i + 1]
        cur_bearing = mars_true_north_bearing_deg(v_cur.lat, v_cur.lon_east, v_nxt.lat, v_nxt.lon_east)
        turn = abs(signed_turn_angle_deg(prev_bearing, cur_bearing))
        seg_dist = v_cur.cumulative_distance_m - vertices[seg_start].cumulative_distance_m

        # Always break on stop points (science targets, destination, return start), sharp turns, or long legs
        must_break = (
            v_cur.is_stop
            or turn >= coalesce_angle_deg
            or seg_dist >= coalesce_max_seg_m
        )
        if must_break:
            segments.append((seg_start, i))
            seg_start = i
            prev_bearing = cur_bearing

    segments.append((seg_start, len(vertices) - 1))

    instructions: List[NavigationInstruction] = []
    prev_step_bearing: Optional[float] = None

    for idx, (i0, i1) in enumerate(segments):
        v0 = vertices[i0]
        v1 = vertices[i1]
        horiz_d = max(0.01, v1.cumulative_distance_m - v0.cumulative_distance_m)
        dz = v1.elevation_m - v0.elevation_m
        bearing_true = mars_true_north_bearing_deg(v0.lat, v0.lon_east, v1.lat, v1.lon_east)
        bearing_grid = equirectangular_grid_north_bearing_deg(
            v0.lat, v0.lon_east, v1.lat, v1.lon_east, central_meridian_lon
        )
        cardinal = bearing_to_cardinal(bearing_true)
        turn = signed_turn_angle_deg(prev_step_bearing, bearing_true) if prev_step_bearing is not None else None
        is_ret_start = bool(v0.stop_role == "destination" and i1 > i0)
        action = _maneuver_phrase(idx, turn, is_ret_start)

        seg_slopes = [v.slope_deg for v in vertices[i0 : i1 + 1] if v.slope_deg is not None]
        seg_tris = [v.roughness_tri_m for v in vertices[i0 : i1 + 1] if v.roughness_tri_m is not None]
        max_local_slope = max(seg_slopes) if seg_slopes else 0.0
        chord_slope = math.degrees(math.atan2(abs(dz), horiz_d))
        eff_slope = max(max_local_slope, chord_slope)
        grade_pct = (dz / horiz_d) * 100.0
        mean_tri = (sum(seg_tris) / len(seg_tris)) if seg_tris else None

        if eff_slope < 3.0:
            slope_desc = "gentle terrain"
        elif eff_slope < 10.0:
            slope_desc = "moderate grade"
        elif eff_slope < 15.0:
            slope_desc = "inclined slope"
        else:
            slope_desc = "steep slope corridor"

        if dz >= 2.0:
            vert_desc = f"climbing +{dz:.1f} m"
        elif dz <= -2.0:
            vert_desc = f"descending {dz:.1f} m"
        else:
            vert_desc = f"level ({dz:+.1f} m)"

        context = f"{slope_desc}, max local slope {eff_slope:.1f} deg"
        if mean_tri is not None:
            context += f", TRI {mean_tri:.2f} m"

        # Linked verified science targets within 150 m of segment midpoint or endpoint
        mid_lat = 0.5 * (v0.lat + v1.lat)
        mid_lon = 0.5 * (v0.lon_east + v1.lon_east)
        nearby_names: List[str] = []
        for s_name, s_lat, s_lon in nearby_science_lookup:
            d_mid = mars_great_circle_distance_meters(mid_lat, mid_lon, s_lat, s_lon)
            d_end = mars_great_circle_distance_meters(v1.lat, v1.lon_east, s_lat, s_lon)
            if min(d_mid, d_end) <= 150.0 and s_name not in nearby_names:
                nearby_names.append(s_name)

        cautions: List[str] = []
        if eff_slope >= 15.0:
            cautions.append(f"Steep grade segment ({eff_slope:.1f} deg).")
        if native_dem_res_m >= 100.0:
            cautions.append(f"Coarse DEM (~{native_dem_res_m:.0f} m/px): sub-pixel boulders/scarps unresolved.")

        stop_dest_note = ""
        if v1.is_stop and v1.stop_label:
            stop_dest_note = f" to reach {v1.stop_label}"

        text = (
            f"{action}{stop_dest_note}: head {cardinal} ({bearing_true:.0f} deg True North) "
            f"for {horiz_d:.1f} m, {vert_desc} (grade {grade_pct:+.1f}%)."
        )

        instructions.append(
            NavigationInstruction(
                step_index=idx + 1,
                action=action,
                bearing_true_north_deg=round(bearing_true, 2),
                bearing_grid_north_deg=round(bearing_grid, 2),
                cardinal_direction=cardinal,
                turn_angle_deg=round(turn, 2) if turn is not None else None,
                from_lat=round(v0.lat, 7),
                from_lon_east=round(v0.lon_east, 7),
                to_lat=round(v1.lat, 7),
                to_lon_east=round(v1.lon_east, 7),
                segment_distance_m=round(horiz_d, 2),
                cumulative_distance_m=round(v1.cumulative_distance_m, 2),
                elevation_start_m=round(v0.elevation_m, 2),
                elevation_end_m=round(v1.elevation_m, 2),
                elevation_delta_m=round(dz, 2),
                grade_percent=round(grade_pct, 2),
                segment_slope_deg=round(eff_slope, 2),
                local_roughness_tri_m=round(mean_tri, 3) if mean_tri is not None else None,
                terrain_context=context,
                nearby_science_targets=nearby_names[:5],
                caution_notes=cautions,
                instruction_text=text,
            )
        )
        prev_step_bearing = bearing_true

    # Add explicit terminal arrival step
    v_last = vertices[-1]
    instructions.append(
        NavigationInstruction(
            step_index=len(instructions) + 1,
            action="Arrive",
            bearing_true_north_deg=None,
            bearing_grid_north_deg=None,
            cardinal_direction=None,
            turn_angle_deg=None,
            from_lat=round(v_last.lat, 7),
            from_lon_east=round(v_last.lon_east, 7),
            to_lat=round(v_last.lat, 7),
            to_lon_east=round(v_last.lon_east, 7),
            segment_distance_m=0.0,
            cumulative_distance_m=round(v_last.cumulative_distance_m, 2),
            elevation_start_m=round(v_last.elevation_m, 2),
            elevation_end_m=round(v_last.elevation_m, 2),
            elevation_delta_m=0.0,
            grade_percent=0.0,
            segment_slope_deg=round(v_last.slope_deg or 0.0, 2),
            local_roughness_tri_m=v_last.roughness_tri_m,
            terrain_context="Terminal waypoint reached",
            nearby_science_targets=[v_last.stop_label] if v_last.stop_label else [],
            caution_notes=[],
            instruction_text=(
                f"Arrive at {v_last.stop_label or 'final destination'} "
                f"(elevation {v_last.elevation_m:.1f} m, total traverse {v_last.cumulative_distance_m:.1f} m)."
            ),
        )
    )
    return instructions
