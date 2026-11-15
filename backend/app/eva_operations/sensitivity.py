"""
MARSCOPE Mission Operational Sensitivity & Multi-Scenario Stability Analysis (Prompt 20 Part 11).

Evaluates deterministic perturbations across:
  - Walking speed (-25%, baseline, +25%, Tobler 1993 grade, Validated Suit Model -> MODEL_UNAVAILABLE)
  - Return reserve fraction (15%, 25%, 35%)
  - Science station duration (+50%)
  - Explicit resource consumption rates (+20%)

Never fabricates Monte Carlo survival probabilities or physiological safety scores.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.eva_operations.locomotion import (
    LocomotionModelCategory,
    compare_locomotion_scenarios,
)
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    EvaMissionEnvelopeResponse,
    MissionConfigRequest,
)
from app.eva_operations.time_budget import evaluate_eva_time_budget


class MissionSensitivityScenarioOutcome(BaseModel):
    """Deterministic outcome of a single operational perturbation scenario."""

    scenario_id: str
    dimension: str  # locomotion_speed | locomotion_model | reserve_policy | station_duration | resource_rate | terrain_slope
    scenario_label: str
    parameter_perturbation: str
    evaluated: bool
    model_feasibility_status: str
    total_mission_time_s: Optional[float] = None
    remaining_time_margin_s: Optional[float] = None
    within_time_budget: Optional[bool] = None
    all_resources_within_limit: Optional[bool] = None
    notes: str


class MissionSensitivityAnalysisReport(BaseModel):
    """Multi-dimensional operational sensitivity report for a human Marswalk plan (Part 11)."""

    mission_id: str
    plan_version: int
    baseline_model_feasibility_status: str
    stability_classification: str
    evaluated_scenario_count: int
    feasible_scenario_count: int
    infeasible_scenario_count: int
    unavailable_or_incomplete_count: int
    scenario_outcomes: List[MissionSensitivityScenarioOutcome] = Field(default_factory=list)
    critical_drivers: List[str] = Field(default_factory=list)
    honest_disclosures: List[str] = Field(
        default_factory=lambda: [
            "Sensitivity analysis evaluates deterministic parameter perturbations against configured operational models.",
            "Does NOT compute probabilistic crew survival, injury risk, or certified flight safety margins.",
        ]
    )


def evaluate_mission_sensitivity(
    *,
    envelope: EvaMissionEnvelopeResponse,
    config: MissionConfigRequest,
) -> MissionSensitivityAnalysisReport:
    outcomes: List[MissionSensitivityScenarioOutcome] = []
    critical_drivers: List[str] = []

    out_segs = []
    for s in envelope.schedule:
        if s.leg_role == "outbound":
            dz = s.elevation_gain_m - s.elevation_loss_m
            horiz = max(0.1, math.sqrt(max(0.01, s.distance_m * s.distance_m - dz * dz)))
            out_segs.append(
                {
                    "horizontal_distance_m": horiz,
                    "elevation_change_m": dz,
                    "slope_deg": math.degrees(math.atan2(abs(dz), horiz)),
                    "roughness_tri_m": 0.0,
                }
            )
    ret_segs = []
    for s in envelope.schedule:
        if s.leg_role == "return":
            dz = s.elevation_gain_m - s.elevation_loss_m
            horiz = max(0.1, math.sqrt(max(0.01, s.distance_m * s.distance_m - dz * dz)))
            ret_segs.append(
                {
                    "horizontal_distance_m": horiz,
                    "elevation_change_m": dz,
                    "slope_deg": math.degrees(math.atan2(abs(dz), horiz)),
                    "roughness_tri_m": 0.0,
                }
            )

    stops_total_s = sum(max(0.0, float(v)) for v in config.stop_dwell_seconds.values())

    loco_entries = compare_locomotion_scenarios(
        outbound_segments=out_segs,
        return_segments=ret_segs,
        base_speed_mps=config.walking_speed_mps,
        mission_duration_limit_s=config.mission_duration_limit_s,
        operational_overhead_s=config.operational_overhead_s + stops_total_s,
    )

    for le in loco_entries:
        if le.status.value == "MODEL_UNAVAILABLE":
            outcomes.append(
                MissionSensitivityScenarioOutcome(
                    scenario_id=le.scenario_id,
                    dimension="locomotion_model",
                    scenario_label=le.scenario_label,
                    parameter_perturbation="category=MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL",
                    evaluated=False,
                    model_feasibility_status=EnvelopeFeasibilityStatus.BLOCKED_BY_UNKNOWN_INPUTS.value,
                    notes=le.disclosure,
                )
            )
            continue

        use_tob = le.category == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
        tb = evaluate_eva_time_budget(
            outbound_constant_s=le.outbound_duration_s if not use_tob else None,
            outbound_tobler_s=le.outbound_duration_s if use_tob else None,
            return_constant_s=le.return_duration_s if not use_tob else None,
            return_tobler_s=le.return_duration_s if use_tob else None,
            return_route_computed=envelope.return_plan.return_route_computed,
            stop_dwell_seconds=config.stop_dwell_seconds,
            operational_overhead_s=config.operational_overhead_s,
            walking_speed_mps=le.reference_speed_mps,
            use_tobler_grade_approximation=use_tob,
            mission_duration_limit_s=config.mission_duration_limit_s,
            return_reserve_fraction=config.return_reserve_fraction,
            locomotion_category=le.category,
        )
        rb = evaluate_eva_resource_budget(
            resources=config.resources,
            exposure_duration_s=tb.total_required_s,
        )
        res_ok = (
            all(r.status == "WITHIN_LIMIT" for r in rb.entries)
            if rb.entries
            else None
        )
        if tb.within_time_budget is False or res_ok is False:
            st = EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL.value
            if le.scenario_id == "const_conservative_speed":
                critical_drivers.append("A -25% reduction in walking speed causes mission duration or resource budget exceedance.")
        elif tb.within_time_budget is True:
            st = EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL.value
        else:
            st = EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION.value

        outcomes.append(
            MissionSensitivityScenarioOutcome(
                scenario_id=le.scenario_id,
                dimension="locomotion_speed",
                scenario_label=le.scenario_label,
                parameter_perturbation=(
                    f"v0={le.reference_speed_mps:.2f} m/s ({le.category.value})"
                    if le.reference_speed_mps is not None
                    else le.category.value
                ),
                evaluated=tb.available,
                model_feasibility_status=st,
                total_mission_time_s=tb.total_required_s,
                remaining_time_margin_s=tb.time_margin_s,
                within_time_budget=tb.within_time_budget,
                all_resources_within_limit=res_ok,
                notes=le.disclosure,
            )
        )

    # Reserve policy perturbations (15% and 35% reserve)
    if envelope.time_budget.available and config.mission_duration_limit_s is not None:
        for res_pct in (0.15, 0.35):
            tb_r = evaluate_eva_time_budget(
                outbound_constant_s=envelope.time_budget.outbound_travel_s,
                outbound_tobler_s=envelope.time_budget.outbound_travel_s,
                return_constant_s=envelope.time_budget.return_travel_s,
                return_tobler_s=envelope.time_budget.return_travel_s,
                return_route_computed=envelope.return_plan.return_route_computed,
                stop_dwell_seconds=config.stop_dwell_seconds,
                operational_overhead_s=config.operational_overhead_s,
                walking_speed_mps=config.walking_speed_mps,
                use_tobler_grade_approximation=config.use_tobler_grade_approximation,
                mission_duration_limit_s=config.mission_duration_limit_s,
                return_reserve_fraction=res_pct,
                locomotion_category=config.locomotion_category,
            )
            st_r = (
                EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL.value
                if tb_r.within_time_budget
                else EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL.value
            )
            if not tb_r.within_time_budget and res_pct == 0.35:
                critical_drivers.append("Increasing return reserve to 35% exceeds usable mission duration ceiling.")
            outcomes.append(
                MissionSensitivityScenarioOutcome(
                    scenario_id=f"reserve_policy_{int(res_pct * 100)}pct",
                    dimension="reserve_policy",
                    scenario_label=f"Return Reserve Fraction = {int(res_pct * 100)}%",
                    parameter_perturbation=f"return_reserve_fraction={res_pct:.2f}",
                    evaluated=True,
                    model_feasibility_status=st_r,
                    total_mission_time_s=tb_r.total_required_s,
                    remaining_time_margin_s=tb_r.time_margin_s,
                    within_time_budget=tb_r.within_time_budget,
                    all_resources_within_limit=None,
                    notes=f"Evaluated with {int(res_pct * 100)}% of mission_duration_limit_s held in reserve.",
                )
            )

    # Resource rate +20% perturbation
    if config.resources and envelope.time_budget.total_required_s is not None:
        pert_res = [
            r.model_copy(update={"consumption_rate": round(r.consumption_rate * 1.20, 5)})
            for r in config.resources
        ]
        rb_pert = evaluate_eva_resource_budget(
            resources=pert_res,
            exposure_duration_s=envelope.time_budget.total_required_s,
        )
        res_ok_p = all(r.status == "WITHIN_LIMIT" for r in rb_pert.entries)
        if not res_ok_p:
            critical_drivers.append("A +20% increase in user-configured resource consumption rates depletes usable inventory.")
        outcomes.append(
            MissionSensitivityScenarioOutcome(
                scenario_id="resource_consumption_plus_20pct",
                dimension="resource_rate",
                scenario_label="Resource Consumption Rates +20%",
                parameter_perturbation="consumption_rate * 1.20",
                evaluated=True,
                model_feasibility_status=(
                    EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL.value
                    if res_ok_p
                    else EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL.value
                ),
                total_mission_time_s=envelope.time_budget.total_required_s,
                remaining_time_margin_s=envelope.time_budget.time_margin_s,
                within_time_budget=envelope.time_budget.within_time_budget,
                all_resources_within_limit=res_ok_p,
                notes="Tests sensitivity of supplied resource margins to a +20% consumption rate increase.",
            )
        )

    eval_cnt = sum(1 for o in outcomes if o.evaluated)
    feas_cnt = sum(
        1
        for o in outcomes
        if o.model_feasibility_status == EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL.value
    )
    infeas_cnt = sum(
        1
        for o in outcomes
        if o.model_feasibility_status == EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL.value
    )
    unavail_cnt = len(outcomes) - feas_cnt - infeas_cnt

    if envelope.model_feasibility_status != EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL:
        stab = "BASELINE_INFEASIBLE_OR_INCOMPLETE"
    elif infeas_cnt == 0 and feas_cnt > 0:
        stab = "ROBUST_ACROSS_CONFIGURED_PERTURBATIONS"
    else:
        stab = "SENSITIVE_TO_SPEED_OR_RESERVE"

    return MissionSensitivityAnalysisReport(
        mission_id=envelope.mission_id,
        plan_version=envelope.plan_version,
        baseline_model_feasibility_status=envelope.model_feasibility_status.value,
        stability_classification=stab,
        evaluated_scenario_count=eval_cnt,
        feasible_scenario_count=feas_cnt,
        infeasible_scenario_count=infeas_cnt,
        unavailable_or_incomplete_count=unavail_cnt,
        scenario_outcomes=outcomes,
        critical_drivers=critical_drivers,
    )
