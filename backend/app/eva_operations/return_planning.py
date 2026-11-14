"""
MARSCOPE Explicit EVA Return-Route & Point-of-No-Return Planning
Evaluates asymmetric climb costs on the return leg and identifies where outbound +
return exposure would exceed the usable EVA time budget.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

from app.eva_operations.schemas import ReturnPlanReport
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.schemas import (
    RouteComputeRequest,
    RouteComputeResponse,
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RouteVertex,
)


def _compute_reversed_symmetric_vertices(outbound_verts: List[RouteVertex]) -> List[RouteVertex]:
    rev = list(reversed(outbound_verts))
    out: List[RouteVertex] = []
    cum = 0.0
    for idx, v in enumerate(rev):
        seg_d = 0.0
        if idx > 0:
            seg_d = mars_great_circle_distance_meters(rev[idx - 1].lat, rev[idx - 1].lon_east, v.lat, v.lon_east)
            cum += seg_d
        out.append(
            RouteVertex(
                seq=idx,
                lat=v.lat,
                lon_east=v.lon_east,
                elevation_m=v.elevation_m,
                slope_deg=v.slope_deg,
                roughness_tri_m=v.roughness_tri_m,
                cumulative_distance_m=round(cum, 3),
                segment_distance_m=round(seg_d, 3),
                is_stop=(idx == 0 or idx == len(rev) - 1),
                stop_role="return_start" if idx == 0 else ("return_home" if idx == len(rev) - 1 else None),
                stop_label=v.stop_label,
            )
        )
    return out


def _estimate_vertex_path_tobler_seconds(
    verts: List[RouteVertex], walking_speed_mps: Optional[float]
) -> Optional[float]:
    if walking_speed_mps is None or walking_speed_mps <= 0 or len(verts) < 2:
        return None
    ref_tobler_flat = math.exp(-3.5 * 0.05)
    total = 0.0
    for i in range(1, len(verts)):
        h = mars_great_circle_distance_meters(
            verts[i - 1].lat, verts[i - 1].lon_east, verts[i].lat, verts[i].lon_east
        )
        dz = float(verts[i].elevation_m) - float(verts[i - 1].elevation_m)
        if h <= 1e-6:
            continue
        slope_tan = dz / h
        grade_factor = math.exp(-3.5 * abs(slope_tan + 0.05)) / ref_tobler_flat
        eff_slp = float(verts[i].slope_deg) if verts[i].slope_deg is not None else math.degrees(math.atan2(abs(dz), h))
        local_atten = max(0.35, 1.0 - max(0.0, eff_slp) / 55.0)
        eff_speed = walking_speed_mps * max(0.22, min(1.1, min(grade_factor, local_atten)))
        total += h / eff_speed
    return round(total, 1)


def plan_eva_return_route(
    *,
    routing_service: Any,
    dataset_id: str,
    outbound_route: RouteComputeResponse,
    walking_speed_mps: Optional[float],
    use_tobler_grade_approximation: bool,
    stop_dwell_total_s: float,
    operational_overhead_s: float,
    usable_budget_s: Optional[float],
    compute_reverse_return_route: bool = True,
) -> ReturnPlanReport:
    warnings: List[str] = []
    out_verts = outbound_route.vertices
    if len(out_verts) < 2:
        return ReturnPlanReport(
            return_route_computed=False,
            return_strategy="unavailable",
            return_horizontal_distance_m=0.0,
            return_surface_distance_m=0.0,
            return_elevation_gain_m=0.0,
            return_elevation_loss_m=0.0,
            asymmetric_climb_delta_m=0.0,
            warnings=["Outbound route has fewer than 2 vertices."],
        )

    ret_route: Optional[RouteComputeResponse] = None
    if compute_reverse_return_route:
        try:
            rev_req = RouteComputeRequest(
                dataset_id=dataset_id,
                start=RouteCoordinateInput(
                    lat=out_verts[-1].lat,
                    lon_east=out_verts[-1].lon_east,
                    label=out_verts[-1].stop_label or "Destination",
                ),
                destination=RouteCoordinateInput(
                    lat=out_verts[0].lat,
                    lon_east=out_verts[0].lon_east,
                    label=out_verts[0].stop_label or "Home / Start",
                ),
                mode=outbound_route.mode,
                algorithm=outbound_route.algorithm,
                constraints=RoutePlanningConstraints(
                    max_slope_deg=outbound_route.effective_slope_limit_deg,
                    walking_speed_m_per_s=walking_speed_mps,
                    return_to_start=False,
                ),
            )
            ret_route = routing_service.compute_route(rev_req)
        except Exception as exc:
            warnings.append(f"Explicit reverse-path computation failed ({exc}); using symmetric reverse corridor vertices.")

    if ret_route is not None and len(ret_route.vertices) >= 2:
        strategy = "explicit_computed_reverse_path"
        r_verts = ret_route.vertices
        r_horiz = float(ret_route.total_horizontal_distance_m)
        r_surf = float(ret_route.total_surface_distance_m)
        r_gain = float(ret_route.total_elevation_gain_m)
        r_loss = float(ret_route.total_elevation_loss_m)
        r_tobler = ret_route.estimated_duration_seconds
    else:
        strategy = "symmetric_reverse_corridor"
        r_verts = _compute_reversed_symmetric_vertices(out_verts)
        r_horiz = float(outbound_route.total_horizontal_distance_m)
        r_surf = float(outbound_route.total_surface_distance_m)
        r_gain = float(outbound_route.total_elevation_loss_m)
        r_loss = float(outbound_route.total_elevation_gain_m)
        r_tobler = _estimate_vertex_path_tobler_seconds(r_verts, walking_speed_mps)

    r_const = round(r_surf / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
    asym_delta = round(r_gain - float(outbound_route.total_elevation_gain_m), 2)
    if asym_delta > 3.0:
        warnings.append(
            f"Asymmetric return climb: return leg climbs +{asym_delta:.1f} m MORE than outbound climb."
        )

    # Compute Point-of-No-Return (PONR) distance along outbound route when speed & budget provided
    ponr_dist_m: Optional[float] = None
    ret_margin_s: Optional[float] = None
    feasible_budget: Optional[bool] = None
    if walking_speed_mps and walking_speed_mps > 0:
        out_dur = (
            outbound_route.estimated_duration_seconds
            if (use_tobler_grade_approximation and outbound_route.estimated_duration_seconds is not None)
            else round(outbound_route.total_surface_distance_m / walking_speed_mps, 1)
        )
        ret_dur = r_tobler if (use_tobler_grade_approximation and r_tobler is not None) else r_const
        if usable_budget_s is not None and ret_dur is not None:
            tot = float(out_dur) + stop_dwell_total_s + operational_overhead_s + float(ret_dur)
            ret_margin_s = round(usable_budget_s - tot, 1)
            feasible_budget = ret_margin_s >= 0.0

            # Walk outbound vertices to identify furthest safe turnback distance within usable_budget_s
            avail_travel = max(0.0, usable_budget_s - stop_dwell_total_s - operational_overhead_s)
            ponr_dist_m = 0.0
            cum_surf = 0.0
            for i in range(1, len(out_verts)):
                h = mars_great_circle_distance_meters(
                    out_verts[i - 1].lat, out_verts[i - 1].lon_east, out_verts[i].lat, out_verts[i].lon_east
                )
                dz = float(out_verts[i].elevation_m) - float(out_verts[i - 1].elevation_m)
                cum_surf += math.hypot(h, dz)
                approx_roundtrip_t = (2.0 * cum_surf) / walking_speed_mps
                if approx_roundtrip_t <= avail_travel:
                    ponr_dist_m = round(float(out_verts[i].cumulative_distance_m), 2)
                else:
                    break

    return ReturnPlanReport(
        return_route_computed=True,
        return_strategy=strategy,
        return_route_vertices=r_verts,
        return_horizontal_distance_m=round(r_horiz, 2),
        return_surface_distance_m=round(r_surf, 2),
        return_elevation_gain_m=round(r_gain, 2),
        return_elevation_loss_m=round(r_loss, 2),
        return_duration_constant_s=r_const,
        return_duration_tobler_s=round(float(r_tobler), 1) if r_tobler is not None else None,
        asymmetric_climb_delta_m=asym_delta,
        return_margin_s=ret_margin_s,
        point_of_no_return_distance_m=ponr_dist_m,
        feasible_within_usable_budget=feasible_budget,
        warnings=warnings,
    )
