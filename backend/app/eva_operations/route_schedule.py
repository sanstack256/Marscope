"""
MARSCOPE EVA Segment-Level Operational Schedule Builder
Links every schedule step to real segment geometry & corridor polygons so
UI timelines synchronize bidirectionally with the 3D terrain viewer.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.evidence_intelligence.schemas import CorridorAssessment
from app.eva_operations.schemas import (
    LocomotionModelSpec,
    ReturnPlanReport,
    ReturnPlanStatus,
    SegmentScheduleItem,
    get_locomotion_model_spec,
)
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import RouteCoordinateInput

LOCOMOTION_SPEED_FLOOR_RATIO = 0.22


def _approx_tobler_for_vertices(
    verts: List[RouteCoordinateInput],
    elev_start: Optional[float],
    elev_end: Optional[float],
    surface_dist_m: float,
    walking_speed_mps: Optional[float],
    mean_slope_deg: Optional[float],
) -> Optional[float]:
    if walking_speed_mps is None or walking_speed_mps <= 0 or surface_dist_m <= 0:
        return None
    dz = (elev_end - elev_start) if (elev_start is not None and elev_end is not None) else 0.0
    horiz = max(0.1, math.sqrt(max(0.01, surface_dist_m * surface_dist_m - dz * dz)))
    ref_tobler = math.exp(-3.5 * 0.05)
    grade_factor = math.exp(-3.5 * abs((dz / horiz) + 0.05)) / ref_tobler
    local_atten = max(0.35, 1.0 - max(0.0, float(mean_slope_deg or 0.0)) / 55.0)
    eff_speed = walking_speed_mps * max(LOCOMOTION_SPEED_FLOOR_RATIO, min(1.1, min(grade_factor, local_atten)))
    return round(surface_dist_m / eff_speed, 1)


def build_eva_schedule(
    *,
    corridor: CorridorAssessment,
    return_plan: ReturnPlanReport,
    walking_speed_mps: Optional[float],
    use_tobler_grade_approximation: bool,
    stop_dwell_seconds: Dict[str, float],
    operational_overhead_s: float,
    surface_weight_n: Optional[float],
) -> List[SegmentScheduleItem]:
    items: List[SegmentScheduleItem] = []
    seq = 0
    cursor_t = 0.0
    cum_climb_j = 0.0

    # Pre-traverse operational overhead if specified
    if operational_overhead_s > 0.0:
        dur = round(float(operational_overhead_s), 1)
        items.append(
            SegmentScheduleItem(
                sequence_index=seq,
                leg_role="operational_overhead",
                segment_id=None,
                label="Ingress / Egress & Suit Checkout Overhead",
                start_time_s=round(cursor_t, 1),
                end_time_s=round(cursor_t + dur, 1),
                duration_constant_speed_s=dur,
                duration_tobler_approx_s=dur,
                distance_m=0.0,
                elevation_gain_m=0.0,
                elevation_loss_m=0.0,
                cumulative_climb_work_j=round(cum_climb_j, 1) if surface_weight_n is not None else None,
                evidence_status="user_configured",
            )
        )
        seq += 1
        cursor_t += dur

    # Outbound corridor segments
    for seg in corridor.segments:
        surf_d = float(seg.surface_distance_m)
        dh = float(seg.elevation_change_m or 0.0)
        gain = max(0.0, dh)
        loss = max(0.0, -dh)
        if surface_weight_n is not None:
            cum_climb_j += surface_weight_n * gain

        d_const = round(surf_d / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
        d_tobler = _approx_tobler_for_vertices(
            seg.vertices or [seg.start_coord, seg.end_coord],
            seg.start_elevation_m,
            seg.end_elevation_m,
            surf_d,
            walking_speed_mps,
            seg.mean_slope_deg,
        )
        active_dur = d_tobler if use_tobler_grade_approximation else d_const

        t_start = round(cursor_t, 1) if active_dur is not None else None
        t_end = round(cursor_t + active_dur, 1) if active_dur is not None else None
        if active_dur is not None:
            cursor_t += active_dur

        ev_status = "unverified_gaps_present" if seg.unverified_area_present else "dem_and_optical_verified"
        verts = seg.vertices if seg.vertices else [seg.start_coord, seg.end_coord]

        items.append(
            SegmentScheduleItem(
                sequence_index=seq,
                leg_role="outbound",
                segment_id=seg.segment_id,
                label=f"Outbound {seg.segment_id}",
                start_time_s=t_start,
                end_time_s=t_end,
                duration_constant_speed_s=d_const,
                duration_tobler_approx_s=d_tobler,
                distance_m=round(surf_d, 2),
                elevation_gain_m=round(gain, 2),
                elevation_loss_m=round(loss, 2),
                cumulative_climb_work_j=round(cum_climb_j, 1) if surface_weight_n is not None else None,
                vertices=verts,
                corridor_polygon=seg.corridor_polygon,
                evidence_status=ev_status,
            )
        )
        seq += 1

    # Science stop dwell entries
    for stop_label, dwell_s in stop_dwell_seconds.items():
        dur = round(max(0.0, float(dwell_s)), 1)
        t_start = round(cursor_t, 1)
        t_end = round(cursor_t + dur, 1)
        cursor_t += dur
        items.append(
            SegmentScheduleItem(
                sequence_index=seq,
                leg_role="science_stop",
                segment_id=None,
                label=f"Science Stop: {stop_label}",
                start_time_s=t_start,
                end_time_s=t_end,
                duration_constant_speed_s=dur,
                duration_tobler_approx_s=dur,
                distance_m=0.0,
                elevation_gain_m=0.0,
                elevation_loss_m=0.0,
                cumulative_climb_work_j=round(cum_climb_j, 1) if surface_weight_n is not None else None,
                evidence_status="user_configured",
            )
        )
        seq += 1

    # Return leg schedule entry — only scheduled as a verified return when independently computed
    if return_plan.return_route_computed and return_plan.return_status != ReturnPlanStatus.REVERSED_OUTBOUND_REFERENCE_ONLY:
        if surface_weight_n is not None:
            cum_climb_j += surface_weight_n * return_plan.return_elevation_gain_m
        d_ret_const = return_plan.return_duration_constant_s
        d_ret_tobler = return_plan.return_duration_tobler_s
        active_ret = d_ret_tobler if use_tobler_grade_approximation else d_ret_const
        t_start = round(cursor_t, 1) if (active_ret is not None and walking_speed_mps) else None
        t_end = round(cursor_t + active_ret, 1) if (active_ret is not None and t_start is not None) else None
        ret_coords = [
            RouteCoordinateInput(lat=v.lat, lon_east=v.lon_east, label=v.stop_label)
            for v in return_plan.return_route_vertices
        ]
        items.append(
            SegmentScheduleItem(
                sequence_index=seq,
                leg_role="return",
                segment_id="RET-001",
                label=f"Return Leg ({return_plan.return_strategy})",
                start_time_s=t_start,
                end_time_s=t_end,
                duration_constant_speed_s=d_ret_const,
                duration_tobler_approx_s=d_ret_tobler,
                distance_m=return_plan.return_surface_distance_m,
                elevation_gain_m=return_plan.return_elevation_gain_m,
                elevation_loss_m=return_plan.return_elevation_loss_m,
                cumulative_climb_work_j=round(cum_climb_j, 1) if surface_weight_n is not None else None,
                vertices=ret_coords,
                corridor_polygon=[],
                evidence_status=return_plan.return_strategy,
            )
        )

    return items
