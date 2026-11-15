"""
MARSCOPE EVA Operational Envelope Schemas (Prompt 20 Extended)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.evidence_intelligence.schemas import CacheValidityState
from app.eva_operations.environmental_context import EvaEnvironmentalContextReport
from app.eva_operations.locomotion import (
    LocomotionModelCategory,
    LocomotionScenarioComparisonEntry,
)
from app.eva_operations.telemetry import TelemetryIngestResult
from app.routing.models import UnknownTerrainPolicy
from app.routing.schemas import (
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RouteVertex,
    RoutingMode,
)
from app.science.provenance_graph import (
    ParameterProvenanceRecord,
    ProvenanceDependencyGraph,
    ScientificDataClassification,
)


class EnvelopeFeasibilityStatus(str, Enum):
    # Legacy Prompt 15-19 status values (preserved for backwards compatibility)
    FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS = "FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS"
    EXCEEDS_CONFIGURED_CONSTRAINTS = "EXCEEDS_CONFIGURED_CONSTRAINTS"
    INCOMPLETE_USER_CONSTRAINTS = "INCOMPLETE_USER_CONSTRAINTS"
    UNVALIDATED_FOR_HUMAN_SAFETY = "UNVALIDATED_FOR_HUMAN_SAFETY"

    # Prompt 20 Part 2.5 explicit model-governed status semantics
    CALCULATED = "CALCULATED"
    FEASIBLE_UNDER_CONFIGURED_MODEL = "FEASIBLE_UNDER_CONFIGURED_MODEL"
    INFEASIBLE_UNDER_CONFIGURED_MODEL = "INFEASIBLE_UNDER_CONFIGURED_MODEL"
    INCOMPLETE_CONSTRAINT_EVALUATION = "INCOMPLETE_CONSTRAINT_EVALUATION"
    BLOCKED_BY_UNKNOWN_INPUTS = "BLOCKED_BY_UNKNOWN_INPUTS"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNVERIFIED = "UNVERIFIED"


class SpeedModelMode(str, Enum):
    CONSTANT_USER_SPEED = "CONSTANT_USER_SPEED"
    TOBLER_STYLE_GRADE_APPROXIMATION = "TOBLER_STYLE_GRADE_APPROXIMATION"
    MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL = "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL"


class ReturnPlanStatus(str, Enum):
    """Explicit epistemic status distinguishing verified independent returns from references or failures."""

    INDEPENDENT_RETURN_COMPUTED = "INDEPENDENT_RETURN_COMPUTED"
    REVERSED_OUTBOUND_REFERENCE_ONLY = "REVERSED_OUTBOUND_REFERENCE_ONLY"
    RETURN_COMPUTATION_FAILED = "RETURN_COMPUTATION_FAILED"
    RETURN_DATA_UNAVAILABLE = "RETURN_DATA_UNAVAILABLE"
    RETURN_CONSTRAINTS_UNSATISFIED = "RETURN_CONSTRAINTS_UNSATISFIED"


class LocomotionModelSpec(BaseModel):
    """Explicitly versioned planetary EVA locomotion timing specification and validity boundary."""

    model_id: str
    model_version: str
    category: LocomotionModelCategory = LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED
    classification: str  # user_parameterized_reference | unvalidated_terrestrial_heuristic | model_unavailable_without_validated_suit_dataset
    description: str
    applicable_scope: str
    unvalidated_note: str
    min_valid_slope_deg: float = -45.0
    max_valid_slope_deg: float = 45.0


LOCOMOTION_MODEL_CONSTANT = LocomotionModelSpec(
    model_id="MARSCOPE-LOCO-CONST-v2.0",
    model_version="locomotion_v2.0",
    category=LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
    classification="user_parameterized_reference",
    description="Constant user-configured surface walking speed (duration = surface_distance_m / walking_speed_mps).",
    applicable_scope="Nominal sensitivity reference; neglects slope slowdown and fatigue.",
    unvalidated_note="Does NOT account for suited EVA metabolic exertion, slope slow-down, or loose regolith slip.",
)

LOCOMOTION_MODEL_TOBLER_APPROX = LocomotionModelSpec(
    model_id="MARSCOPE-LOCO-TOBLER-1993-v2.0",
    model_version="locomotion_v2.0",
    category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
    classification="unvalidated_terrestrial_heuristic",
    description=(
        "Published Tobler (1993) terrestrial hiking grade formula v(s) = v0 * exp(-3.5*|s + 0.05|) / exp(-0.175) "
        "without undocumented ad-hoc linear slope multipliers or arbitrary speed floors."
    ),
    applicable_scope="Exploratory sensitivity probe comparing uphill vs downhill asymmetry within valid slope bounds.",
    unvalidated_note="NOT calibrated or validated for pressurized Mars suit biomechanics, partial gravity (3.72 m/s^2), or dusty talus.",
)

LOCOMOTION_MODEL_VALIDATED_SUIT_UNAVAILABLE = LocomotionModelSpec(
    model_id="MARSCOPE-LOCO-VALIDATED-SUIT-v2.0",
    model_version="locomotion_v2.0",
    category=LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL,
    classification="model_unavailable_without_validated_suit_dataset",
    description=(
        "Placeholder for an empirical pressurized spacesuit biomechanics model under 3.72076 m/s^2 Martian gravity. "
        "Returns MODEL_UNAVAILABLE unless an authenticated suit locomotion dataset is supplied."
    ),
    applicable_scope="Certified pressurized EVA suit kinematics when backed by empirical chamber/field test datasets.",
    unvalidated_note="No validated pressurized Mars spacesuit locomotion dataset is bundled; MARSCOPE refuses to fabricate suit speed curves.",
)


def get_locomotion_model_spec(
    use_tobler: bool,
    category: Optional[LocomotionModelCategory] = None,
    min_valid_slope_deg: float = -45.0,
    max_valid_slope_deg: float = 45.0,
) -> LocomotionModelSpec:
    eff_cat = category
    if eff_cat is None:
        eff_cat = (
            LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
            if use_tobler
            else LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED
        )
    if eff_cat == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL:
        return LOCOMOTION_MODEL_VALIDATED_SUIT_UNAVAILABLE.model_copy(
            update={
                "min_valid_slope_deg": min_valid_slope_deg,
                "max_valid_slope_deg": max_valid_slope_deg,
            }
        )
    if eff_cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION or use_tobler:
        return LOCOMOTION_MODEL_TOBLER_APPROX.model_copy(
            update={
                "min_valid_slope_deg": min_valid_slope_deg,
                "max_valid_slope_deg": max_valid_slope_deg,
            }
        )
    return LOCOMOTION_MODEL_CONSTANT.model_copy(
        update={
            "min_valid_slope_deg": min_valid_slope_deg,
            "max_valid_slope_deg": max_valid_slope_deg,
        }
    )


class TurnbackCheckpointRecord(BaseModel):
    """Turnback safety verification at one outbound checkpoint using an actual independent C_i -> origin path."""

    checkpoint_index: int
    lat: float
    lon_east: float
    outbound_distance_m: float
    outbound_elapsed_s: Optional[float] = None
    return_route_computed: bool
    independent_return_distance_m: Optional[float] = None
    independent_return_elevation_gain_m: Optional[float] = None
    independent_return_duration_constant_s: Optional[float] = None
    independent_return_duration_tobler_s: Optional[float] = None
    estimated_roundtrip_time_s: Optional[float] = None
    remaining_margin_s: Optional[float] = None
    fits_usable_budget: Optional[bool] = None
    return_differs_from_outbound: bool = False
    failure_reason: Optional[str] = None


class IndependentReturnAlternative(BaseModel):
    """One distinct alternative return corridor evaluated from destination back to origin."""

    alternative_id: str
    objective: str
    strategy_label: str
    horizontal_distance_m: float
    surface_distance_m: float
    elevation_gain_m: float
    max_slope_deg: float
    mean_slope_deg: float
    estimated_time_constant_s: Optional[float] = None
    estimated_time_tobler_s: Optional[float] = None
    spatial_overlap_with_primary_fraction: Optional[float] = None
    overlap_with_outbound_fraction: Optional[float] = None
    vertices: List[RouteVertex] = Field(default_factory=list)


class ExtensibleResourceCategory(str, Enum):
    """11 extensible EVA operational resource categories (Prompt 20 Part 6.1)."""

    OXYGEN_INVENTORY = "oxygen_inventory"
    OXYGEN_CONSUMPTION = "oxygen_consumption"
    CO2_REMOVAL_CAPACITY = "co2_removal_capacity"
    BATTERY_ENERGY = "battery_energy"
    THERMAL_MANAGEMENT_CAPACITY = "thermal_management_capacity"
    COOLING_RESOURCES = "cooling_resources"
    WATER = "water"
    COMMUNICATIONS_CAPACITY = "communications_capacity"
    NAVIGATION_LOCALIZATION_AVAILABILITY = "navigation_localization_availability"
    SCIENTIFIC_INSTRUMENT_CONSUMABLES = "scientific_instrument_consumables"
    PAYLOAD_CONSTRAINTS = "payload_constraints"


class ReservePolicy(BaseModel):
    """Explicit operator-configured reserve rule for a consumable resource (Part 2.4 & Part 6)."""

    policy_id: str = "user_configured_reserve"
    reserve_fraction: float = Field(default=0.20, ge=0.0, le=0.95)
    minimum_absolute_reserve: Optional[float] = Field(default=None, ge=0.0)
    classification: ScientificDataClassification = ScientificDataClassification.USER_ASSUMED
    rationale: str = "Explicit user-configured operational reserve margin."


class ResourceRatePhaseSpec(BaseModel):
    """Optional phase-specific rate for piecewise time integration Q_used = integral Q_dot(t) dt."""

    phase: str = Field(..., description="Phase identifier: outbound | science_stop | return | operational_overhead")
    consumption_rate: float = Field(..., ge=0.0)
    rate_unit: str = Field(..., min_length=1)


class ExplicitResourceSpec(BaseModel):
    resource_name: str = Field(..., min_length=1, description="Explicit supply name (e.g. oxygen_kg, battery_wh)")
    category: Optional[ExtensibleResourceCategory] = None
    initial_quantity: float = Field(..., ge=0.0)
    unit: str = Field(..., min_length=1, description="Quantity unit: kg, g, L, Wh, kWh, J, kJ, s, min, h")
    consumption_rate: float = Field(..., ge=0.0)
    rate_unit: str = Field(..., min_length=1, description="Rate unit e.g. kg/h, L/min, Wh/h, kJ/s, W")
    reserve_fraction: float = Field(default=0.0, ge=0.0, lt=1.0)
    reserve_policy: Optional[ReservePolicy] = None
    phase_rates: List[ResourceRatePhaseSpec] = Field(default_factory=list)
    classification: ScientificDataClassification = ScientificDataClassification.USER_ASSUMED
    source_note: Optional[str] = None


class ResourceEvaluationEntry(BaseModel):
    resource_name: str
    category: Optional[str] = None
    status: str  # WITHIN_LIMIT | EXCEEDS_LIMIT | UNAVAILABLE | UNIT_MISMATCH
    initial_quantity: Optional[float] = None
    unit: str
    normalized_rate_per_second: Optional[float] = None
    exposure_duration_s: Optional[float] = None
    reserve_required: Optional[float] = None
    estimated_consumed: Optional[float] = None
    remaining_after_eva: Optional[float] = None
    margin_above_reserve: Optional[float] = None
    equation_applied: str = "Q_used = Q_dot * t"
    integration_mode: str = "CONSTANT_RATE_Q_DOT_T"  # CONSTANT_RATE_Q_DOT_T | PHASE_INTEGRATED_Q_DOT_T
    reserve_policy_status: str = "EXPLICIT_FRACTION"
    phase_breakdown: Dict[str, float] = Field(default_factory=dict)
    assumption_classification: ScientificDataClassification = ScientificDataClassification.USER_ASSUMED
    explanation: str


class ResourceBudgetReport(BaseModel):
    overall_status: str  # WITHIN_CONSTRAINTS | EXCEEDS_CONSTRAINTS | UNAVAILABLE
    entries: List[ResourceEvaluationEntry] = Field(default_factory=list)
    category_coverage: Dict[str, str] = Field(default_factory=dict)
    missing_inputs: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class TimeBudgetBreakdown(BaseModel):
    available: bool
    outbound_travel_s: Optional[float] = None
    science_stops_s: Optional[float] = None
    operational_overhead_s: float = 0.0
    return_travel_s: Optional[float] = None
    reserve_protected_s: Optional[float] = None
    total_required_s: Optional[float] = None
    mission_duration_limit_s: float | None = None
    usable_budget_s: Optional[float] = None
    time_margin_s: Optional[float] = None
    within_time_budget: Optional[bool] = None
    speed_model_used: SpeedModelMode = SpeedModelMode.CONSTANT_USER_SPEED
    locomotion_category: str = LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED.value
    speed_model_validation_note: str
    locomotion_model: Optional[LocomotionModelSpec] = None
    parameter_provenance: List[ParameterProvenanceRecord] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)


class EnergyBudgetBreakdown(BaseModel):
    available: bool
    astronaut_suit_mass_kg: Optional[float] = None
    payload_mass_kg: Optional[float] = None
    total_mass_kg: Optional[float] = None
    mars_gravity_m_s2: Optional[float] = None
    surface_weight_n: Optional[float] = None
    outbound_climb_gain_m: float
    outbound_descent_loss_m: float
    return_climb_gain_m: float
    return_descent_loss_m: float
    outbound_climb_work_j: Optional[float] = None
    return_climb_work_j: Optional[float] = None
    total_positive_climb_work_j: Optional[float] = None
    net_gravitational_pe_change_j: Optional[float] = None
    parameter_provenance: List[ParameterProvenanceRecord] = Field(default_factory=list)
    disclaimer: str = (
        "Mechanical gravitational climb work only (W = m * g * sum(dh+)). "
        "NOT astronaut metabolic expenditure or O2 consumption; downhill steps do NOT recover metabolic energy."
    )
    missing_inputs: List[str] = Field(default_factory=list)


class SegmentScheduleItem(BaseModel):
    sequence_index: int
    leg_role: str  # outbound | science_stop | return | operational_overhead
    segment_id: Optional[str] = None
    label: str
    start_time_s: Optional[float] = None
    end_time_s: Optional[float] = None
    duration_constant_speed_s: Optional[float] = None
    duration_tobler_approx_s: Optional[float] = None
    distance_m: float
    elevation_gain_m: float
    elevation_loss_m: float
    cumulative_climb_work_j: Optional[float] = None
    vertices: List[RouteCoordinateInput] = Field(default_factory=list)
    corridor_polygon: List[List[float]] = Field(default_factory=list)
    evidence_status: str = "unassessed"


class ReturnPlanReport(BaseModel):
    return_status: ReturnPlanStatus = ReturnPlanStatus.INDEPENDENT_RETURN_COMPUTED
    return_route_computed: bool
    return_strategy: str  # independent_return_route | reversed_outbound_reference_only | return_computation_failed | return_data_unavailable
    return_strategy_note: Optional[str] = None
    return_route_vertices: List[RouteVertex] = Field(default_factory=list)
    return_horizontal_distance_m: float
    return_surface_distance_m: float
    return_elevation_gain_m: float
    return_elevation_loss_m: float
    return_duration_constant_s: Optional[float] = None
    return_duration_tobler_s: Optional[float] = None
    asymmetric_climb_delta_m: float
    return_margin_s: Optional[float] = None
    point_of_no_return_distance_m: Optional[float] = None
    turnback_constraint_checkpoint_distance_m: Optional[float] = None
    turnback_ponr_method: str = "checkpoint_independent_reverse_dijkstra"
    point_of_no_return_explanation: str = ""
    overlap_with_outbound_fraction: Optional[float] = None
    locomotion_model: Optional[LocomotionModelSpec] = None
    turnback_checkpoints: List[TurnbackCheckpointRecord] = Field(default_factory=list)
    return_alternatives: List[IndependentReturnAlternative] = Field(default_factory=list)
    emergency_return_alternatives: List[IndependentReturnAlternative] = Field(default_factory=list)
    outbound_vs_return_asymmetry: Dict[str, Any] = Field(default_factory=dict)
    feasible_within_usable_budget: Optional[bool] = None
    warnings: List[str] = Field(default_factory=list)


class ConstraintCheckRecord(BaseModel):
    constraint_id: str
    category: str  # terrain | time | return_reserve | resource | evidence | safety_boundary | locomotion_model
    status: str  # PASS | FAIL | UNAVAILABLE | UNVALIDATED
    configured_limit: Optional[str] = None
    evaluated_value: Optional[str] = None
    explanation: str


class MissionConfigRequest(BaseModel):
    mission_id: Optional[str] = None
    mission_name: str = "Gale Crater Boxwork EVA Plan"
    study_region: str = "Gale Crater / Mount Sharp"
    dataset_id: str = "hirise_dteec_009149_1750"
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    mode: RoutingMode = RoutingMode.BALANCED
    corridor_width_m: float = Field(default=60.0, ge=10.0, le=500.0)
    target_segment_length_m: Optional[float] = Field(default=None, ge=15.0, le=500.0)
    observation_search_radius_m: float = Field(default=250.0, ge=10.0, le=5000.0)
    selected_target_ids: List[str] = Field(default_factory=list)
    constraints: Optional[RoutePlanningConstraints] = None
    walking_speed_mps: Optional[float] = Field(default=None, gt=0.0, le=5.0)
    use_tobler_grade_approximation: bool = False
    locomotion_category: Optional[LocomotionModelCategory] = None
    locomotion_min_valid_slope_deg: float = Field(default=-45.0, ge=-85.0, le=0.0)
    locomotion_max_valid_slope_deg: float = Field(default=45.0, ge=0.0, le=85.0)
    validated_suit_model_source: Optional[str] = None
    unknown_terrain_policy: UnknownTerrainPolicy = UnknownTerrainPolicy.EXCLUDE_UNKNOWN
    operator_unknown_override_reason: Optional[str] = None
    confirm_default_policies: bool = False
    mission_duration_limit_s: Optional[float] = Field(default=None, gt=0.0)
    return_reserve_fraction: Optional[float] = Field(default=None, ge=0.0, le=0.95)
    operational_overhead_s: float = Field(default=0.0, ge=0.0)
    stop_dwell_seconds: Dict[str, float] = Field(default_factory=dict)
    astronaut_suit_mass_kg: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    payload_mass_kg: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    resources: List[ExplicitResourceSpec] = Field(default_factory=list)
    compute_reverse_return_route: bool = True
    linked_campaign_id: Optional[str] = None
    linked_question_id: Optional[str] = None


class EvaMissionEnvelopeResponse(BaseModel):
    mission_id: str
    mission_name: str
    study_region: str
    dataset_id: str
    source_product_id: str
    route_id: str
    assessment_id: str
    dossier_id: Optional[str] = None
    linked_campaign_id: Optional[str] = None
    linked_question_id: Optional[str] = None
    integrated_lifecycle_state: Optional[str] = None
    envelope_status: EnvelopeFeasibilityStatus
    model_feasibility_status: EnvelopeFeasibilityStatus = EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION
    workflow_state: str = "CONFIGURED"
    plan_version: int = 1
    stale: bool = False
    stale_reasons: List[str] = Field(default_factory=list)
    operational_safety_certified: bool = False
    missing_inputs: List[str] = Field(default_factory=list)
    config: MissionConfigRequest
    outbound_summary: Dict[str, Any] = Field(default_factory=dict)
    locomotion_model: Optional[LocomotionModelSpec] = None
    locomotion_scenarios: List[LocomotionScenarioComparisonEntry] = Field(default_factory=list)
    parameter_provenance: List[ParameterProvenanceRecord] = Field(default_factory=list)
    traversability_analytics: Dict[str, Any] = Field(default_factory=dict)
    time_budget: TimeBudgetBreakdown
    energy_budget: EnergyBudgetBreakdown
    resource_budget: ResourceBudgetReport
    return_plan: ReturnPlanReport
    schedule: List[SegmentScheduleItem] = Field(default_factory=list)
    constraints: List[ConstraintCheckRecord] = Field(default_factory=list)
    environmental_context: Optional[EvaEnvironmentalContextReport] = None
    telemetry_state: Optional[TelemetryIngestResult] = None
    uncertainty_notes: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    cache_validity: CacheValidityState = CacheValidityState.CURRENT
    provenance_graph: ProvenanceDependencyGraph
    created_at_utc: str
    compute_time_ms: float
