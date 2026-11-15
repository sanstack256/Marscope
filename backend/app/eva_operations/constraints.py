"""
MARSCOPE EVA Constraint Evaluator (Prompt 20 Part 2.5 Extended)
Checks terrain limits, duration & reserve compliance, return-route feasibility,
resource limits, corridor evidence quality, locomotion model validity, and
explicit safety boundary.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.evidence_intelligence.schemas import CorridorAssessment
from app.eva_operations.locomotion import LocomotionModelCategory
from app.eva_operations.schemas import (
    ConstraintCheckRecord,
    EnergyBudgetBreakdown,
    EnvelopeFeasibilityStatus,
    MissionConfigRequest,
    ResourceBudgetReport,
    ReturnPlanReport,
    TimeBudgetBreakdown,
)
from app.routing.schemas import RouteComputeResponse


def evaluate_eva_constraints(
    *,
    config: MissionConfigRequest,
    route: RouteComputeResponse,
    corridor: CorridorAssessment,
    time_budget: TimeBudgetBreakdown,
    return_plan: ReturnPlanReport,
    resource_budget: ResourceBudgetReport,
) -> List[ConstraintCheckRecord]:
    records: List[ConstraintCheckRecord] = []

    # 1. Terrain slope cap
    slope_ok = route.max_slope_deg <= route.effective_slope_limit_deg + 0.05
    records.append(
        ConstraintCheckRecord(
            constraint_id="terrain_slope_cap",
            category="terrain",
            status="PASS" if slope_ok else "FAIL",
            configured_limit=f"<= {route.effective_slope_limit_deg:.1f} deg",
            evaluated_value=f"peak {route.max_slope_deg:.2f} deg",
            explanation=(
                f"All traversed DEM cells & simplified line-of-sight chords respect {route.effective_slope_limit_deg:.1f} deg cap."
            ),
        )
    )

    # 2. Time budget vs limit
    if time_budget.within_time_budget is None:
        records.append(
            ConstraintCheckRecord(
                constraint_id="eva_usable_time_budget",
                category="time",
                status="UNAVAILABLE",
                configured_limit=(
                    f"{config.mission_duration_limit_s:.0f} s" if config.mission_duration_limit_s else "Unconfigured"
                ),
                evaluated_value="Unavailable (missing walking speed / duration limit / reserve / suit model)",
                explanation="Cannot verify EVA time envelope without explicit walking speed, duration limit, return reserve, and available locomotion model.",
            )
        )
    else:
        records.append(
            ConstraintCheckRecord(
                constraint_id="eva_usable_time_budget",
                category="time",
                status="PASS" if time_budget.within_time_budget else "FAIL",
                configured_limit=f"<= {time_budget.usable_budget_s:.1f} s usable",
                evaluated_value=f"{time_budget.total_required_s:.1f} s required (margin {time_budget.time_margin_s:+.1f} s)",
                explanation=(
                    f"Using {time_budget.speed_model_used.value}: {time_budget.total_required_s:.1f} s vs {time_budget.usable_budget_s:.1f} s usable."
                ),
            )
        )

    # 3. Return reserve & independent return check
    if not return_plan.return_route_computed:
        records.append(
            ConstraintCheckRecord(
                constraint_id="return_reserve_feasibility",
                category="return_reserve",
                status=(
                    "FAIL"
                    if return_plan.return_status.value == "RETURN_COMPUTATION_FAILED"
                    else "UNAVAILABLE"
                ),
                configured_limit="Independent destination->origin return route required",
                evaluated_value=f"{return_plan.return_status.value} ({return_plan.return_strategy})",
                explanation=(
                    return_plan.return_strategy_note
                    or "Independent return path was not computed; reversed outbound trajectory cannot substitute for verified return feasibility."
                ),
            )
        )
    elif return_plan.feasible_within_usable_budget is None:
        records.append(
            ConstraintCheckRecord(
                constraint_id="return_reserve_feasibility",
                category="return_reserve",
                status="UNAVAILABLE",
                configured_limit=(
                    f"{config.return_reserve_fraction * 100:.0f}% reserve" if config.return_reserve_fraction is not None else "Unconfigured"
                ),
                evaluated_value=f"Return +{return_plan.return_elevation_gain_m:.1f} m climb ({return_plan.return_strategy})",
                explanation="Return kinematics require explicit walking speed and duration reserve.",
            )
        )
    else:
        records.append(
            ConstraintCheckRecord(
                constraint_id="return_reserve_feasibility",
                category="return_reserve",
                status="PASS" if return_plan.feasible_within_usable_budget else "FAIL",
                configured_limit=f"Protected reserve {time_budget.reserve_protected_s:.1f} s ({config.return_reserve_fraction * 100:.0f}%)",
                evaluated_value=(
                    f"Return {return_plan.return_surface_distance_m:.1f} m / +{return_plan.return_elevation_gain_m:.1f} m climb; "
                    f"Turnback PONR {return_plan.point_of_no_return_distance_m} m ({return_plan.turnback_ponr_method})"
                ),
                explanation=(
                    f"Independent return status '{return_plan.return_status.value}' with asymmetric climb delta {return_plan.asymmetric_climb_delta_m:+.1f} m."
                ),
            )
        )

    # 4. Explicit unit-aware resources
    if resource_budget.overall_status == "UNAVAILABLE":
        records.append(
            ConstraintCheckRecord(
                constraint_id="explicit_consumable_budget",
                category="resource",
                status="UNAVAILABLE",
                configured_limit="No user supply budgets supplied",
                evaluated_value="UNAVAILABLE",
                explanation="Configure explicit unit-aware O2 / power / cooling supply & rate limits to evaluate resource endurance.",
            )
        )
    else:
        records.append(
            ConstraintCheckRecord(
                constraint_id="explicit_consumable_budget",
                category="resource",
                status="PASS" if resource_budget.overall_status == "WITHIN_CONSTRAINTS" else "FAIL",
                configured_limit=f"{len(resource_budget.entries)} resource spec(s)",
                evaluated_value=resource_budget.overall_status,
                explanation="; ".join(e.explanation for e in resource_budget.entries[:3]),
            )
        )

    # 5. Evidence coverage threshold
    valid_dem = float(corridor.uncertainty.corridor_valid_fraction)
    raw_opt_cov = corridor.coverage_summary.get("mean_optical_coverage_fraction")
    opt_cov: Optional[float] = float(raw_opt_cov) if raw_opt_cov is not None else None
    ev_pass = valid_dem >= 0.95 and opt_cov is not None and opt_cov >= 0.50 and route.native_dem_resolution_m <= 2.0
    opt_label = f"{opt_cov * 100:.1f}%" if opt_cov is not None else f"unverified ({corridor.coverage_summary.get('optical_coverage_status', 'UNAVAILABLE')})"
    records.append(
        ConstraintCheckRecord(
            constraint_id="corridor_evidence_completeness",
            category="evidence",
            status="PASS" if ev_pass else "FAIL" if valid_dem < 0.50 else "UNVALIDATED",
            configured_limit="DEM valid >= 95%, Optical >= 50%, DEM <= 2.0 m/px",
            evaluated_value=f"DEM {valid_dem * 100:.1f}%, Optical {opt_label}, Res {route.native_dem_resolution_m:.2f} m/px",
            explanation="Derived from polygon-masked DEM and non-double-counted optical union (unverified optical never coerced to 0%).",
        )
    )

    # 6. Locomotion model availability check (when Category C is requested)
    if config.locomotion_category == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL:
        has_suit = bool(config.validated_suit_model_source)
        records.append(
            ConstraintCheckRecord(
                constraint_id="locomotion_model_availability",
                category="locomotion_model",
                status="PASS" if has_suit else "UNAVAILABLE",
                configured_limit="Authenticated Mars pressurized suit locomotion dataset required",
                evaluated_value=config.validated_suit_model_source or "MODEL_UNAVAILABLE",
                explanation=(
                    "Validated suit locomotion dataset supplied."
                    if has_suit
                    else "No authenticated pressurized Mars spacesuit locomotion dataset is bundled; MARSCOPE refuses to fabricate suit biomechanics."
                ),
            )
        )

    # 7. Mandatory unvalidated human life-safety boundary
    records.append(
        ConstraintCheckRecord(
            constraint_id="human_life_safety_certification",
            category="safety_boundary",
            status="UNVALIDATED",
            configured_limit="Requires physiological, geotechnical & live hardware certification",
            evaluated_value="NOT CERTIFIED BY MARSCOPE",
            explanation=(
                "MARSCOPE never models astronaut metabolism, suit thermal dissipation, O2 CO2 scrubbers, "
                "or regolith sinkage; mathematical feasibility is NOT EVA flight safety approval."
            ),
        )
    )

    return records


def determine_envelope_and_model_status(
    *,
    config: MissionConfigRequest,
    constraints: List[ConstraintCheckRecord],
    time_budget: TimeBudgetBreakdown,
    energy_budget: EnergyBudgetBreakdown,
    resource_budget: ResourceBudgetReport,
) -> Tuple[EnvelopeFeasibilityStatus, EnvelopeFeasibilityStatus]:
    """Return (legacy_envelope_status, prompt20_model_feasibility_status)."""
    any_fail = any(c.status == "FAIL" for c in constraints)
    if any_fail:
        legacy_status = EnvelopeFeasibilityStatus.EXCEEDS_CONFIGURED_CONSTRAINTS
    elif time_budget.available and energy_budget.available:
        legacy_status = EnvelopeFeasibilityStatus.FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS
    else:
        legacy_status = EnvelopeFeasibilityStatus.INCOMPLETE_USER_CONSTRAINTS

    # Prompt 20 Part 2.5 model feasibility status
    if (
        config.locomotion_category == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL
        and not config.validated_suit_model_source
    ) or "mars_standard_gravity" in energy_budget.missing_inputs:
        model_status = EnvelopeFeasibilityStatus.BLOCKED_BY_UNKNOWN_INPUTS
    elif any_fail:
        model_status = EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL
    elif time_budget.available and energy_budget.available:
        model_status = EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL
    else:
        model_status = EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION

    return legacy_status, model_status
