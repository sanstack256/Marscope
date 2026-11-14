"""
MARSCOPE Explicit EVA Return-Route & Route-Aware Turnback Planning Engine
Evaluates independent destination->origin paths, alternative return trajectories,
asymmetric climb costs, and checkpoint-by-checkpoint turnback constraints without
symmetric 2*d/v illusions.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional

from app.eva_operations.schemas import (
    IndependentReturnAlternative,
    ReturnPlanReport,
    ReturnPlanStatus,
    TurnbackCheckpointRecord,
    get_locomotion_model_spec,
)
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.models import RouteObjective
from app.routing.schemas import (
    RouteComputeRequest,
    RouteComputeResponse,
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RouteVertex,
)


def _compute_reversed_symmetric_vertices(outbound_verts: List[RouteVertex]) -> List[RouteVertex]:
    """Reference-only geometry reversing outbound coordinates; NEVER constitutes an independent return plan."""
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
                stop_role="return_start_ref" if idx == 0 else ("return_home_ref" if idx == len(rev) - 1 else None),
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


def _compute_polyline_overlap_fraction(
    verts_a: List[RouteVertex],
    verts_b: List[RouteVertex],
    tolerance_m: float = 12.0,
) -> float:
    """Symmetric nearest-vertex overlap fraction measuring corridor spatial similarity."""
    if not verts_a or not verts_b:
        return 0.0
    hits = 0
    for va in verts_a:
        if any(mars_great_circle_distance_meters(va.lat, va.lon_east, vb.lat, vb.lon_east) <= tolerance_m for vb in verts_b):
            hits += 1
    return round(hits / float(len(verts_a)), 4)


def _select_checkpoint_indices(n_verts: int, max_checkpoints: int = 8) -> List[int]:
    if n_verts <= 2:
        return list(range(n_verts))
    step = max(1, (n_verts - 1) // max_checkpoints)
    idxs = list(range(1, n_verts, step))
    if (n_verts - 1) not in idxs:
        idxs.append(n_verts - 1)
    return idxs[: max_checkpoints + 1]


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
    loco_spec = get_locomotion_model_spec(use_tobler_grade_approximation)
    out_verts = outbound_route.vertices
    if len(out_verts) < 2:
        return ReturnPlanReport(
            return_status=ReturnPlanStatus.RETURN_DATA_UNAVAILABLE,
            return_route_computed=False,
            return_strategy="return_data_unavailable",
            return_strategy_note="Outbound route contains fewer than 2 vertices.",
            return_horizontal_distance_m=0.0,
            return_surface_distance_m=0.0,
            return_elevation_gain_m=0.0,
            return_elevation_loss_m=0.0,
            asymmetric_climb_delta_m=0.0,
            locomotion_model=loco_spec,
            warnings=["Outbound route has fewer than 2 vertices."],
        )

    # Explicit reference-only branch when user disables independent return routing
    if not compute_reverse_return_route:
        ref_verts = _compute_reversed_symmetric_vertices(out_verts)
        r_surf = outbound_route.total_surface_distance_m
        r_horiz = outbound_route.total_horizontal_distance_m
        r_gain = outbound_route.total_elevation_loss_m
        r_loss = outbound_route.total_elevation_gain_m
        d_const = round(r_surf / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
        d_tobler = _estimate_vertex_path_tobler_seconds(ref_verts, walking_speed_mps)
        warnings.append(
            "Independent return computation disabled; reversed outbound path is displayed ONLY as visual reference and does NOT validate return feasibility."
        )
        return ReturnPlanReport(
            return_status=ReturnPlanStatus.REVERSED_OUTBOUND_REFERENCE_ONLY,
            return_route_computed=False,
            return_strategy="reversed_outbound_reference_only",
            return_strategy_note="Reversed outbound trajectory shown for reference only; no independent return path solved.",
            return_route_vertices=ref_verts,
            return_horizontal_distance_m=round(r_horiz, 2),
            return_surface_distance_m=round(r_surf, 2),
            return_elevation_gain_m=round(r_gain, 2),
            return_elevation_loss_m=round(r_loss, 2),
            return_duration_constant_s=d_const,
            return_duration_tobler_s=d_tobler,
            asymmetric_climb_delta_m=round(r_gain - outbound_route.total_elevation_gain_m, 2),
            return_margin_s=None,
            point_of_no_return_distance_m=None,
            turnback_constraint_checkpoint_distance_m=None,
            turnback_ponr_method="unavailable_reference_only",
            overlap_with_outbound_fraction=1.0,
            locomotion_model=loco_spec,
            turnback_checkpoints=[],
            return_alternatives=[],
            feasible_within_usable_budget=None,
            warnings=warnings,
        )

    ret_route: Optional[RouteComputeResponse] = None
    return_alts: List[IndependentReturnAlternative] = []
    checkpoints: List[TurnbackCheckpointRecord] = []
    failure_exc: Optional[str] = None

    # Use fast single-grid independent return + reverse-Dijkstra checkpoint solver when available
    if hasattr(routing_service, "compute_independent_return_with_checkpoints"):
        try:
            (
                ret_route,
                return_alts,
                checkpoints,
            ) = routing_service.compute_independent_return_with_checkpoints(
                dataset_id=dataset_id,
                outbound_route=outbound_route,
                walking_speed_mps=walking_speed_mps,
                use_tobler_grade_approximation=use_tobler_grade_approximation,
                stop_dwell_total_s=stop_dwell_total_s,
                operational_overhead_s=operational_overhead_s,
                usable_budget_s=usable_budget_s,
            )
        except Exception as exc:
            failure_exc = str(exc)
    else:
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
                objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
                algorithm=outbound_route.algorithm,
                constraints=RoutePlanningConstraints(
                    max_slope_deg=outbound_route.effective_slope_limit_deg,
                    walking_speed_m_per_s=walking_speed_mps,
                    return_to_start=False,
                ),
            )
            ret_route = routing_service.compute_route(rev_req)
        except Exception as exc:
            failure_exc = str(exc)

    if ret_route is None or len(ret_route.vertices) < 2:
        err_lower = (failure_exc or "").lower()
        is_missing_data = any(tok in err_lower for tok in ("filenotfound", "not found", "missing", "unavailable"))
        status = ReturnPlanStatus.RETURN_DATA_UNAVAILABLE if is_missing_data else ReturnPlanStatus.RETURN_COMPUTATION_FAILED
        warnings.append(
            f"Independent return route could not be computed ({failure_exc or 'no traversable path returned'}); "
            "refusing to fabricate return feasibility from reversed outbound path."
        )
        return ReturnPlanReport(
            return_status=status,
            return_route_computed=False,
            return_strategy="return_data_unavailable" if is_missing_data else "return_computation_failed",
            return_strategy_note=failure_exc or "No traversable return trajectory exists under active slope and coverage constraints.",
            return_route_vertices=[],
            return_horizontal_distance_m=0.0,
            return_surface_distance_m=0.0,
            return_elevation_gain_m=0.0,
            return_elevation_loss_m=0.0,
            asymmetric_climb_delta_m=0.0,
            turnback_ponr_method="independent_return_failed",
            locomotion_model=loco_spec,
            turnback_checkpoints=checkpoints,
            return_alternatives=[],
            feasible_within_usable_budget=False,
            warnings=warnings,
        )

    r_verts = ret_route.vertices
    r_horiz = float(ret_route.total_horizontal_distance_m)
    r_surf = float(ret_route.total_surface_distance_m)
    r_gain = float(ret_route.total_elevation_gain_m)
    r_loss = float(ret_route.total_elevation_loss_m)
    asym_delta = round(r_gain - float(outbound_route.total_elevation_gain_m), 2)
    overlap_with_out = _compute_polyline_overlap_fraction(r_verts, out_verts)

    d_const = round(r_surf / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
    d_tobler = _estimate_vertex_path_tobler_seconds(r_verts, walking_speed_mps)
    active_ret_s = d_tobler if use_tobler_grade_approximation else d_const

    # If checkpoints were not precomputed by fast reverse-Dijkstra helper, compute checkpoint-by-checkpoint now
    if not checkpoints:
        cum_surf = 0.0
        cum_out_tobler = 0.0
        ref_tobler = math.exp(-3.5 * 0.05)
        vert_out_cum_tobler: List[float] = [0.0]
        for idx in range(1, len(out_verts)):
            h = mars_great_circle_distance_meters(
                out_verts[idx - 1].lat, out_verts[idx - 1].lon_east, out_verts[idx].lat, out_verts[idx].lon_east
            )
            dz = float(out_verts[idx].elevation_m) - float(out_verts[idx - 1].elevation_m)
            cum_surf += math.hypot(h, dz)
            if walking_speed_mps and walking_speed_mps > 0 and h > 1e-6:
                grade_factor = math.exp(-3.5 * abs((dz / h) + 0.05)) / ref_tobler
                slp = float(out_verts[idx].slope_deg) if out_verts[idx].slope_deg is not None else math.degrees(math.atan2(abs(dz), h))
                atten = max(0.35, 1.0 - max(0.0, slp) / 55.0)
                cum_out_tobler += h / (walking_speed_mps * max(0.22, min(1.1, min(grade_factor, atten))))
            vert_out_cum_tobler.append(cum_out_tobler)

        for cp_pos, v_idx in enumerate(_select_checkpoint_indices(len(out_verts))):
            v = out_verts[v_idx]
            out_t = (
                round(vert_out_cum_tobler[v_idx], 1)
                if use_tobler_grade_approximation
                else (round(v.cumulative_distance_m / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None)
            )
            try:
                cp_req = RouteComputeRequest(
                    dataset_id=dataset_id,
                    start=RouteCoordinateInput(lat=v.lat, lon_east=v.lon_east, label=f"Checkpoint-{cp_pos}"),
                    destination=RouteCoordinateInput(lat=out_verts[0].lat, lon_east=out_verts[0].lon_east, label="Origin"),
                    mode=outbound_route.mode,
                    objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
                    algorithm=outbound_route.algorithm,
                    constraints=RoutePlanningConstraints(
                        max_slope_deg=outbound_route.effective_slope_limit_deg,
                        walking_speed_m_per_s=walking_speed_mps,
                        return_to_start=False,
                    ),
                )
                cp_ret = routing_service.compute_route(cp_req)
                cp_c = round(cp_ret.total_surface_distance_m / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
                cp_tob = _estimate_vertex_path_tobler_seconds(cp_ret.vertices, walking_speed_mps)
                active_cp_ret = cp_tob if use_tobler_grade_approximation else cp_c
                rt_time = (
                    round((out_t or 0.0) + (active_cp_ret or 0.0) + operational_overhead_s + (stop_dwell_total_s if v_idx == len(out_verts) - 1 else 0.0), 1)
                    if (out_t is not None and active_cp_ret is not None)
                    else None
                )
                fits = (rt_time <= usable_budget_s) if (rt_time is not None and usable_budget_s is not None) else None
                checkpoints.append(
                    TurnbackCheckpointRecord(
                        checkpoint_index=cp_pos,
                        lat=v.lat,
                        lon_east=v.lon_east,
                        outbound_distance_m=round(v.cumulative_distance_m, 2),
                        outbound_elapsed_s=out_t,
                        return_route_computed=True,
                        independent_return_distance_m=round(cp_ret.total_surface_distance_m, 2),
                        independent_return_elevation_gain_m=round(cp_ret.total_elevation_gain_m, 2),
                        independent_return_duration_constant_s=cp_c,
                        independent_return_duration_tobler_s=cp_tob,
                        estimated_roundtrip_time_s=rt_time,
                        fits_usable_budget=fits,
                        return_differs_from_outbound=_compute_polyline_overlap_fraction(cp_ret.vertices, out_verts[: v_idx + 1]) < 0.85,
                    )
                )
            except Exception as cp_exc:
                checkpoints.append(
                    TurnbackCheckpointRecord(
                        checkpoint_index=cp_pos,
                        lat=v.lat,
                        lon_east=v.lon_east,
                        outbound_distance_m=round(v.cumulative_distance_m, 2),
                        outbound_elapsed_s=out_t,
                        return_route_computed=False,
                        fits_usable_budget=False,
                        failure_reason=str(cp_exc),
                    )
                )

    out_travel_active: Optional[float] = None
    if walking_speed_mps and walking_speed_mps > 0:
        out_travel_active = (
            _estimate_vertex_path_tobler_seconds(out_verts, walking_speed_mps)
            if use_tobler_grade_approximation
            else round(outbound_route.total_surface_distance_m / walking_speed_mps, 1)
        )

    feasible: Optional[bool] = None
    margin_s: Optional[float] = None
    turnback_dist_m: Optional[float] = None
    if usable_budget_s is not None and out_travel_active is not None and active_ret_s is not None:
        total_req = out_travel_active + stop_dwell_total_s + operational_overhead_s + active_ret_s
        margin_s = round(usable_budget_s - total_req, 1)
        feasible = margin_s >= 0.0

    # Derive route-aware turnback checkpoint strictly from contiguous reachable budget-fitting checkpoints
    for cp in checkpoints:
        if not cp.return_route_computed:
            warnings.append(
                f"Turnback from checkpoint {cp.checkpoint_index} ({cp.outbound_distance_m:.1f} m) failed: {cp.failure_reason or 'unreachable'}."
            )
            break
        if usable_budget_s is not None:
            if cp.fits_usable_budget is True:
                turnback_dist_m = cp.outbound_distance_m
            else:
                break
        else:
            turnback_dist_m = cp.outbound_distance_m

    ret_status = ReturnPlanStatus.INDEPENDENT_RETURN_COMPUTED
    if feasible is False:
        ret_status = ReturnPlanStatus.RETURN_CONSTRAINTS_UNSATISFIED
        warnings.append(
            f"Independent return trajectory computed ({r_surf:.1f} m), but combined round-trip duration exceeds usable EVA budget by {abs(margin_s or 0.0):.1f} s."
        )
    if asym_delta > 5.0:
        warnings.append(
            f"Return leg encounters +{asym_delta:.1f} m more elevation gain than outbound traverse; asymmetric climb load governs return reserve."
        )

    return ReturnPlanReport(
        return_status=ret_status,
        return_route_computed=True,
        return_strategy="independent_return_route",
        return_strategy_note=(
            f"Independently solved destination->origin traverse over {dataset_id} "
            f"(spatial overlap with outbound corridor: {overlap_with_out * 100:.1f}%)."
        ),
        return_route_vertices=r_verts,
        return_horizontal_distance_m=round(r_horiz, 2),
        return_surface_distance_m=round(r_surf, 2),
        return_elevation_gain_m=round(r_gain, 2),
        return_elevation_loss_m=round(r_loss, 2),
        return_duration_constant_s=d_const,
        return_duration_tobler_s=d_tobler,
        asymmetric_climb_delta_m=asym_delta,
        return_margin_s=margin_s,
        point_of_no_return_distance_m=turnback_dist_m,
        turnback_constraint_checkpoint_distance_m=turnback_dist_m,
        turnback_ponr_method="checkpoint_independent_reverse_dijkstra",
        overlap_with_outbound_fraction=overlap_with_out,
        locomotion_model=loco_spec,
        turnback_checkpoints=checkpoints,
        return_alternatives=return_alts,
        feasible_within_usable_budget=feasible,
        warnings=warnings,
    )
