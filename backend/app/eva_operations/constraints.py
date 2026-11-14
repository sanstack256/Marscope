"""
MARSCOPE EVA Constraint Evaluator
Checks terrain limits, duration & reserve compliance, return-route feasibility,
resource limits, corridor evidence quality, and explicit safety boundary.
"""

from __future__ import annotations

from typing import List

from app.evidence_intelligence.schemas import CorridorAssessment
from app.eva_operations.schemas import (
    ConstraintCheckRecord,
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
                evaluated_value="Unavailable (missing walking speed / duration limit / reserve)",
                explanation="Cannot verify EVA time envelope without explicit walking speed, duration limit, and return reserve.",
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

    # 3. Return reserve & asymmetric climb check
    if return_plan.feasible_within_usable_budget is None:
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
                    f"PONR {return_plan.point_of_no_return_distance_m} m"
                ),
                explanation=(
                    f"Reverse return strategy '{return_plan.return_strategy}' with asymmetric climb delta {return_plan.asymmetric_climb_delta_m:+.1f} m."
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
    opt_cov = float(corridor.coverage_summary.get("mean_optical_coverage_fraction", 0.0))
    ev_pass = valid_dem >= 0.95 and opt_cov >= 0.50 and route.native_dem_resolution_m <= 2.0
    records.append(
        ConstraintCheckRecord(
            constraint_id="corridor_evidence_completeness",
            category="evidence",
            status="PASS" if ev_pass else "FAIL" if valid_dem < 0.50 else "UNVALIDATED",
            configured_limit="DEM valid >= 95%, Optical >= 50%, DEM <= 2.0 m/px",
            evaluated_value=f"DEM {valid_dem * 100:.1f}%, Optical {opt_cov * 100:.1f}%, Res {route.native_dem_resolution_m:.2f} m/px",
            explanation="Derived from polygon-masked DEM and non-double-counted optical union.",
        )
    )

    # 6. Mandatory unvalidated human life-safety boundary
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
