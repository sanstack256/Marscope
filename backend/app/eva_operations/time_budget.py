"""
MARSCOPE EVA Time Budget Model
Explicitly separates outbound travel, science stops, operational overhead,
return travel, and protected safety reserve without silent speed assumptions.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.eva_operations.schemas import SpeedModelMode, TimeBudgetBreakdown


def evaluate_eva_time_budget(
    *,
    outbound_constant_s: Optional[float],
    outbound_tobler_s: Optional[float],
    return_constant_s: Optional[float],
    return_tobler_s: Optional[float],
    stop_dwell_seconds: Dict[str, float],
    operational_overhead_s: float,
    walking_speed_mps: Optional[float],
    use_tobler_grade_approximation: bool,
    mission_duration_limit_s: Optional[float],
    return_reserve_fraction: Optional[float],
) -> TimeBudgetBreakdown:
    missing: List[str] = []
    if walking_speed_mps is None or walking_speed_mps <= 0:
        missing.append("walking_speed_mps")
    if mission_duration_limit_s is None or mission_duration_limit_s <= 0:
        missing.append("mission_duration_limit_s")
    if return_reserve_fraction is None:
        missing.append("return_reserve_fraction")

    mode = (
        SpeedModelMode.TOBLER_STYLE_GRADE_APPROXIMATION
        if use_tobler_grade_approximation
        else SpeedModelMode.CONSTANT_USER_SPEED
    )
    mode_note = (
        "Unvalidated Tobler-style grade speed attenuation applied over DEM chord grades; planning approximation only, not calibrated suit biomechanics."
        if use_tobler_grade_approximation
        else "Exact constant-speed kinematics (distance / walking_speed_mps); no slope speed degradation assumed."
    )

    stops_s = round(sum(max(0.0, float(v)) for v in stop_dwell_seconds.values()), 1)
    overhead_s = round(max(0.0, float(operational_overhead_s)), 1)

    if walking_speed_mps is None or walking_speed_mps <= 0:
        return TimeBudgetBreakdown(
            available=False,
            outbound_travel_s=None,
            science_stops_s=stops_s,
            operational_overhead_s=overhead_s,
            return_travel_s=None,
            reserve_protected_s=None,
            total_required_s=None,
            mission_duration_limit_s=mission_duration_limit_s,
            usable_budget_s=None,
            time_margin_s=None,
            within_time_budget=None,
            speed_model_used=mode,
            speed_model_validation_note=mode_note,
            missing_inputs=missing,
        )

    out_s = outbound_tobler_s if use_tobler_grade_approximation else outbound_constant_s
    ret_s = return_tobler_s if use_tobler_grade_approximation else return_constant_s

    total_req_s: Optional[float] = None
    if out_s is not None and ret_s is not None:
        total_req_s = round(float(out_s) + stops_s + overhead_s + float(ret_s), 1)

    reserve_s: Optional[float] = None
    usable_s: Optional[float] = None
    margin_s: Optional[float] = None
    within_budget: Optional[bool] = None

    if mission_duration_limit_s is not None and return_reserve_fraction is not None:
        reserve_s = round(mission_duration_limit_s * return_reserve_fraction, 1)
        usable_s = round(mission_duration_limit_s - reserve_s, 1)
        if total_req_s is not None:
            margin_s = round(usable_s - total_req_s, 1)
            within_budget = margin_s >= 0.0

    return TimeBudgetBreakdown(
        available=bool(total_req_s is not None and not missing),
        outbound_travel_s=round(float(out_s), 1) if out_s is not None else None,
        science_stops_s=stops_s,
        operational_overhead_s=overhead_s,
        return_travel_s=round(float(ret_s), 1) if ret_s is not None else None,
        reserve_protected_s=reserve_s,
        total_required_s=total_req_s,
        mission_duration_limit_s=mission_duration_limit_s,
        usable_budget_s=usable_s,
        time_margin_s=margin_s,
        within_time_budget=within_budget,
        speed_model_used=mode,
        speed_model_validation_note=mode_note,
        missing_inputs=missing,
    )
