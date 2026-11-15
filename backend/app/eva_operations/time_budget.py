"""
MARSCOPE EVA Time Budget Evaluation (Prompt 20 Extended)
Calculates explicit outbound, dwell, overhead, return, and reserve budgets
without silent defaults, pairing every duration with a versioned locomotion specification
and parameter provenance records.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.eva_operations.locomotion import LocomotionModelCategory
from app.eva_operations.schemas import (
    SpeedModelMode,
    TimeBudgetBreakdown,
    get_locomotion_model_spec,
)
from app.science.provenance_graph import (
    ParameterProvenanceRecord,
    ScientificDataClassification,
)


def evaluate_eva_time_budget(
    *,
    outbound_constant_s: Optional[float],
    outbound_tobler_s: Optional[float],
    return_constant_s: Optional[float],
    return_tobler_s: Optional[float],
    return_route_computed: bool = True,
    stop_dwell_seconds: Dict[str, float],
    operational_overhead_s: float,
    walking_speed_mps: Optional[float],
    use_tobler_grade_approximation: bool,
    mission_duration_limit_s: Optional[float],
    return_reserve_fraction: Optional[float],
    locomotion_category: Optional[LocomotionModelCategory] = None,
    validated_suit_model_source: Optional[str] = None,
    min_valid_slope_deg: float = -45.0,
    max_valid_slope_deg: float = 45.0,
) -> TimeBudgetBreakdown:
    eff_cat = locomotion_category
    if eff_cat is None:
        eff_cat = (
            LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
            if use_tobler_grade_approximation
            else LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED
        )

    missing: List[str] = []
    if walking_speed_mps is None or walking_speed_mps <= 0:
        missing.append("walking_speed_mps")
    if mission_duration_limit_s is None or mission_duration_limit_s <= 0:
        missing.append("mission_duration_limit_s")
    if return_reserve_fraction is None:
        missing.append("return_reserve_fraction")
    if not return_route_computed:
        missing.append("independent_return_route")
    if (
        eff_cat == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL
        and not validated_suit_model_source
    ):
        missing.append("validated_suit_locomotion_dataset")

    if eff_cat == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL:
        mode = SpeedModelMode.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL
    elif (
        eff_cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
        or use_tobler_grade_approximation
    ):
        mode = SpeedModelMode.TOBLER_STYLE_GRADE_APPROXIMATION
    else:
        mode = SpeedModelMode.CONSTANT_USER_SPEED

    loco_spec = get_locomotion_model_spec(
        use_tobler=(mode == SpeedModelMode.TOBLER_STYLE_GRADE_APPROXIMATION),
        category=eff_cat,
        min_valid_slope_deg=min_valid_slope_deg,
        max_valid_slope_deg=max_valid_slope_deg,
    )
    mode_note = (
        f"[{loco_spec.model_id} {loco_spec.model_version} | {loco_spec.classification}] "
        f"{loco_spec.description} {loco_spec.unvalidated_note}"
    )

    stops_s = round(sum(max(0.0, float(v)) for v in stop_dwell_seconds.values()), 1)
    overhead_s = round(max(0.0, float(operational_overhead_s)), 1)

    param_prov: List[ParameterProvenanceRecord] = [
        ParameterProvenanceRecord(
            parameter_name="walking_speed_mps",
            value=walking_speed_mps,
            units="m/s",
            classification=(
                ScientificDataClassification.USER_ASSUMED
                if walking_speed_mps is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type="user_input" if walking_speed_mps is not None else "missing_input",
            validity_domain="(0.0, 5.0] m/s reference surface walking speed",
            confirmed_by_operator=walking_speed_mps is not None,
        ),
        ParameterProvenanceRecord(
            parameter_name="mission_duration_limit_s",
            value=mission_duration_limit_s,
            units="s",
            classification=(
                ScientificDataClassification.USER_ASSUMED
                if mission_duration_limit_s is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type="user_input" if mission_duration_limit_s is not None else "missing_input",
            validity_domain="Total EVA duration ceiling (> 0 s)",
            confirmed_by_operator=mission_duration_limit_s is not None,
        ),
        ParameterProvenanceRecord(
            parameter_name="return_reserve_fraction",
            value=return_reserve_fraction,
            units="fraction",
            classification=(
                ScientificDataClassification.USER_ASSUMED
                if return_reserve_fraction is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type="user_input" if return_reserve_fraction is not None else "missing_input",
            validity_domain="[0.0, 0.95] protected return time reserve fraction",
            confirmed_by_operator=return_reserve_fraction is not None,
        ),
    ]

    if (
        walking_speed_mps is None
        or walking_speed_mps <= 0
        or "validated_suit_locomotion_dataset" in missing
    ):
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
            locomotion_category=eff_cat.value,
            speed_model_validation_note=mode_note,
            locomotion_model=loco_spec,
            parameter_provenance=param_prov,
            missing_inputs=missing,
        )

    use_tob = mode == SpeedModelMode.TOBLER_STYLE_GRADE_APPROXIMATION
    out_s = outbound_tobler_s if use_tob else outbound_constant_s
    ret_s = (
        (return_tobler_s if use_tob else return_constant_s)
        if return_route_computed
        else None
    )

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
        available=bool(
            total_req_s is not None
            and return_route_computed
            and "walking_speed_mps" not in missing
            and "mission_duration_limit_s" not in missing
            and "return_reserve_fraction" not in missing
        ),
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
        locomotion_category=eff_cat.value,
        speed_model_validation_note=mode_note,
        locomotion_model=loco_spec,
        parameter_provenance=param_prov,
        missing_inputs=missing,
    )
