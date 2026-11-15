"""
MARSCOPE Deterministic Routing Sensitivity & Stability Evaluation
Evaluates how terrain uncertainty, constraint bounds, and objective weight variations
affect route selection and constraint feasibility without Monte Carlo noise fabrication.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


SENSITIVITY_POLICY_ID = "MARSCOPE-SENSITIVITY"
SENSITIVITY_POLICY_VERSION = "sensitivity_v2.0"


class SensitivityCategory(str, Enum):
    """Prompt 17 strictly separated sensitivity families (never merged into a single score)."""

    MEASUREMENT_UNCERTAINTY_PROPAGATION = "MEASUREMENT_UNCERTAINTY_PROPAGATION"
    MEASUREMENT_SENSITIVITY_ANALYSIS = "MEASUREMENT_SENSITIVITY_ANALYSIS"
    ALGORITHM_PARAMETER_SENSITIVITY = "ALGORITHM_PARAMETER_SENSITIVITY"
    MISSION_ASSUMPTION_SENSITIVITY = "MISSION_ASSUMPTION_SENSITIVITY"


class SensitivityPolicyConfig(BaseModel):
    """Explicitly versioned configurable policy parameters governing sensitivity sweeps."""

    policy_id: str = SENSITIVITY_POLICY_ID
    policy_version: str = SENSITIVITY_POLICY_VERSION
    unquantified_slope_probe_deg: float = 1.5
    strict_slope_cap_delta_deg: float = -2.0
    relaxed_slope_cap_delta_deg: float = 2.0
    walking_speed_degraded_scale: float = 0.75
    path_change_overlap_threshold: float = 0.90
    allow_parametric_tri_fallback: bool = False


DEFAULT_SENSITIVITY_POLICY = SensitivityPolicyConfig()


class RouteStabilityStatus(str, Enum):
    """Strict epistemic status describing how stable a selected route is across scenario probes."""

    STABLE_ACROSS_EVALUATED_SCENARIOS = "STABLE_ACROSS_EVALUATED_SCENARIOS"
    CHANGES_ACROSS_EVALUATED_SCENARIOS = "CHANGES_ACROSS_EVALUATED_SCENARIOS"
    INSUFFICIENT_SCENARIOS = "INSUFFICIENT_SCENARIOS"
    NOT_EVALUATED = "NOT_EVALUATED"


class SensitivityScenarioConfig(BaseModel):
    """One deterministic scenario perturbation probe belonging to an explicit sensitivity category."""

    scenario_id: str
    label: str
    category: SensitivityCategory = SensitivityCategory.MISSION_ASSUMPTION_SENSITIVITY
    perturbation_parameter: str
    perturbation_description: str
    slope_bias_deg: float = 0.0
    slope_sigma_multiplier: float = 0.0
    tri_sigma_multiplier: float = 0.0
    max_slope_delta_deg: float = 0.0
    science_weight_scale: float = 1.0
    walking_speed_scale: float = 1.0
    uncertainty_penalty_scale: float = 1.0


class ScenarioSensitivityOutcome(BaseModel):
    """Observed routing outcome under a specific deterministic perturbation."""

    scenario_id: str
    label: str
    category: SensitivityCategory = SensitivityCategory.MISSION_ASSUMPTION_SENSITIVITY
    perturbation_parameter: str
    perturbation_description: str
    evaluated: bool = True
    uncertainty_quantified: Optional[bool] = None
    route_found: bool
    path_changed_from_baseline: bool = False
    path_signature_diff_fraction: Optional[float] = None
    total_distance_m: Optional[float] = None
    estimated_time_s: Optional[float] = None
    max_slope_deg: Optional[float] = None
    total_objective_cost: Optional[float] = None
    constraint_status_changed: bool = False
    notes: List[str] = Field(default_factory=list)


class RouteSensitivityReport(BaseModel):
    """Complete deterministic perturbation sensitivity report for a computed route."""

    policy_id: str = SENSITIVITY_POLICY_ID
    policy_version: str = SENSITIVITY_POLICY_VERSION
    policy_config: SensitivityPolicyConfig = Field(default_factory=SensitivityPolicyConfig)
    baseline_route_id: str
    stability_status: RouteStabilityStatus
    evaluated_scenario_count: int
    scenarios_where_path_changed: int
    scenarios_where_infeasible: int
    dominant_sensitivity_driver: Optional[str] = None
    uncertainty_basis_note: str
    category_summaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    scenarios: List[ScenarioSensitivityOutcome] = Field(default_factory=list)


DEFAULT_SENSITIVITY_SCENARIOS: List[SensitivityScenarioConfig] = [
    SensitivityScenarioConfig(
        scenario_id="slope_sigma_upper",
        label="Upper Slope Uncertainty (+1 sigma_slope)",
        category=SensitivityCategory.MEASUREMENT_UNCERTAINTY_PROPAGATION,
        perturbation_parameter="slope_deg + 1.0 * sigma_slope",
        perturbation_description="Evaluates worst-case local slope angle shifted upward by propagated Horn 3x3 1-sigma uncertainty (or labeled as parametric probe when unquantified).",
        slope_sigma_multiplier=1.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="slope_sigma_lower",
        label="Lower Slope Uncertainty (-1 sigma_slope)",
        category=SensitivityCategory.MEASUREMENT_UNCERTAINTY_PROPAGATION,
        perturbation_parameter="max(0, slope_deg - 1.0 * sigma_slope)",
        perturbation_description="Evaluates optimistic local slope angle reduced by propagated 1-sigma uncertainty (or labeled as parametric probe when unquantified).",
        slope_sigma_multiplier=-1.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="roughness_sigma_upper",
        label="Upper TRI Roughness Uncertainty (+1 sigma_TRI)",
        category=SensitivityCategory.MEASUREMENT_UNCERTAINTY_PROPAGATION,
        perturbation_parameter="tri_m + 1.0 * sigma_tri",
        perturbation_description="Increases surface ruggedness cost using propagated Riley TRI 1-sigma (never fabricates +0.25 m delta when TRI sigma is unquantified).",
        tri_sigma_multiplier=1.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="strict_slope_cap",
        label="Conservative Slope Cap (-2.0 deg)",
        category=SensitivityCategory.MISSION_ASSUMPTION_SENSITIVITY,
        perturbation_parameter="max_slope_deg - 2.0",
        perturbation_description="Tightens slope traversability limit by 2.0 deg to test corridor fragility near steep thresholds.",
        max_slope_delta_deg=-2.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="relaxed_slope_cap",
        label="Permissive Slope Cap (+2.0 deg)",
        category=SensitivityCategory.MISSION_ASSUMPTION_SENSITIVITY,
        perturbation_parameter="max_slope_deg + 2.0",
        perturbation_description="Relaxes slope cap by 2.0 deg to reveal nearby marginal bypasses excluded by nominal slope limit.",
        max_slope_delta_deg=2.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="science_weight_zero",
        label="Pure Engineering Cost (Zero Science Bias)",
        category=SensitivityCategory.ALGORITHM_PARAMETER_SENSITIVITY,
        perturbation_parameter="science_weight = 0.0",
        perturbation_description="Removes soft science corridor attraction to test purely engineering/slope-driven routing.",
        science_weight_scale=0.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="science_weight_doubled",
        label="High Science Priority (2x Verified Bonus)",
        category=SensitivityCategory.ALGORITHM_PARAMETER_SENSITIVITY,
        perturbation_parameter="science_weight * 2.0",
        perturbation_description="Doubles soft corridor bonus within strict hard constraints to test detour stability.",
        science_weight_scale=2.0,
    ),
    SensitivityScenarioConfig(
        scenario_id="walking_speed_degraded",
        label="Conservative Locomotion Speed (0.75x)",
        category=SensitivityCategory.MISSION_ASSUMPTION_SENSITIVITY,
        perturbation_parameter="walking_speed * 0.75",
        perturbation_description="Tests time-envelope sensitivity under slower suit locomotion assumptions.",
        walking_speed_scale=0.75,
    ),
]


def summarize_sensitivity_outcomes(
    *,
    baseline_route_id: str,
    outcomes: List[ScenarioSensitivityOutcome],
    uncertainty_basis_note: str,
    policy_config: Optional[SensitivityPolicyConfig] = None,
) -> RouteSensitivityReport:
    """Aggregate scenario outcomes strictly within separated sensitivity categories without collapsing into one confidence number."""
    pol = policy_config or DEFAULT_SENSITIVITY_POLICY
    evaluated_outcomes = [o for o in outcomes if o.evaluated]
    n = len(evaluated_outcomes)
    category_summaries: Dict[str, Dict[str, Any]] = {}
    for cat in SensitivityCategory:
        cat_items = [o for o in outcomes if o.category == cat]
        if not cat_items:
            continue
        cat_eval = [o for o in cat_items if o.evaluated]
        cat_changed = [o for o in cat_eval if o.path_changed_from_baseline or o.constraint_status_changed]
        cat_failed = [o for o in cat_eval if not o.route_found]
        category_summaries[cat.value] = {
            "category": cat.value,
            "scenario_count": len(cat_items),
            "evaluated_count": len(cat_eval),
            "unquantified_or_skipped_count": len(cat_items) - len(cat_eval),
            "changed_count": len(cat_changed),
            "infeasible_count": len(cat_failed),
            "stability_status": (
                RouteStabilityStatus.INSUFFICIENT_SCENARIOS.value
                if not cat_eval
                else (
                    RouteStabilityStatus.CHANGES_ACROSS_EVALUATED_SCENARIOS.value
                    if (cat_changed or cat_failed)
                    else RouteStabilityStatus.STABLE_ACROSS_EVALUATED_SCENARIOS.value
                )
            ),
        }

    if n < 3:
        return RouteSensitivityReport(
            policy_id=pol.policy_id,
            policy_version=pol.policy_version,
            policy_config=pol,
            baseline_route_id=baseline_route_id,
            stability_status=RouteStabilityStatus.INSUFFICIENT_SCENARIOS,
            evaluated_scenario_count=n,
            scenarios_where_path_changed=0,
            scenarios_where_infeasible=0,
            dominant_sensitivity_driver=None,
            uncertainty_basis_note=uncertainty_basis_note,
            category_summaries=category_summaries,
            scenarios=outcomes,
        )

    changed = [o for o in evaluated_outcomes if o.path_changed_from_baseline or o.constraint_status_changed]
    failed = [o for o in evaluated_outcomes if not o.route_found]
    driver: Optional[str] = None
    if failed:
        driver = failed[0].label
    elif changed:
        ranked = sorted(
            changed,
            key=lambda x: x.path_signature_diff_fraction if x.path_signature_diff_fraction is not None else 0.0,
            reverse=True,
        )
        driver = ranked[0].label

    status = (
        RouteStabilityStatus.CHANGES_ACROSS_EVALUATED_SCENARIOS
        if (changed or failed)
        else RouteStabilityStatus.STABLE_ACROSS_EVALUATED_SCENARIOS
    )

    return RouteSensitivityReport(
        policy_id=pol.policy_id,
        policy_version=pol.policy_version,
        policy_config=pol,
        baseline_route_id=baseline_route_id,
        stability_status=status,
        evaluated_scenario_count=n,
        scenarios_where_path_changed=len(changed),
        scenarios_where_infeasible=len(failed),
        dominant_sensitivity_driver=driver,
        uncertainty_basis_note=uncertainty_basis_note,
        category_summaries=category_summaries,
        scenarios=outcomes,
    )
