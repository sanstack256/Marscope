"""
MARSCOPE EVA Operational Envelope Schemas
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.evidence_intelligence.schemas import CacheValidityState
from app.routing.schemas import (
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RouteVertex,
    RoutingMode,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ScientificDataClassification,
)


class EnvelopeFeasibilityStatus(str, Enum):
    FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS = "FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS"
    EXCEEDS_CONFIGURED_CONSTRAINTS = "EXCEEDS_CONFIGURED_CONSTRAINTS"
    INCOMPLETE_USER_CONSTRAINTS = "INCOMPLETE_USER_CONSTRAINTS"
    UNVALIDATED_FOR_HUMAN_SAFETY = "UNVALIDATED_FOR_HUMAN_SAFETY"


class SpeedModelMode(str, Enum):
    CONSTANT_USER_SPEED = "CONSTANT_USER_SPEED"
    TOBLER_STYLE_GRADE_APPROXIMATION = "TOBLER_STYLE_GRADE_APPROXIMATION"


class ExplicitResourceSpec(BaseModel):
    resource_name: str = Field(..., min_length=1, description="Explicit supply name (e.g. oxygen_kg, battery_wh)")
    initial_quantity: float = Field(..., ge=0.0)
    unit: str = Field(..., min_length=1, description="Quantity unit: kg, g, L, Wh, kWh, J, kJ, s, min, h")
    consumption_rate: float = Field(..., ge=0.0)
    rate_unit: str = Field(..., min_length=1, description="Rate unit e.g. kg/h, L/min, Wh/h, kJ/s, W")
    reserve_fraction: float = Field(default=0.0, ge=0.0, lt=1.0)
    source_note: Optional[str] = None


class ResourceEvaluationEntry(BaseModel):
    resource_name: str
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
    assumption_classification: ScientificDataClassification = ScientificDataClassification.USER_ASSUMED
    explanation: str


class ResourceBudgetReport(BaseModel):
    overall_status: str  # WITHIN_CONSTRAINTS | EXCEEDS_CONSTRAINTS | UNAVAILABLE
    entries: List[ResourceEvaluationEntry] = Field(default_factory=list)
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
    mission_duration_limit_s: Optional[float] = None
    usable_budget_s: Optional[float] = None
    time_margin_s: Optional[float] = None
    within_time_budget: Optional[bool] = None
    speed_model_used: SpeedModelMode = SpeedModelMode.CONSTANT_USER_SPEED
    speed_model_validation_note: str
    missing_inputs: List[str] = Field(default_factory=list)


class EnergyBudgetBreakdown(BaseModel):
    available: bool
    astronaut_suit_mass_kg: Optional[float] = None
    payload_mass_kg: Optional[float] = None
    total_mass_kg: Optional[float] = None
    mars_gravity_m_s2: float
    surface_weight_n: Optional[float] = None
    outbound_climb_gain_m: float
    outbound_descent_loss_m: float
    return_climb_gain_m: float
    return_descent_loss_m: float
    outbound_climb_work_j: Optional[float] = None
    return_climb_work_j: Optional[float] = None
    total_positive_climb_work_j: Optional[float] = None
    net_gravitational_pe_change_j: Optional[float] = None
    disclaimer: str = (
        "Mechanical gravitational climb work only (W = m * g * sum(dh+)). "
        "NOT astronaut metabolic expenditure or O2 consumption; downhill steps do NOT recover metabolic energy."
    )
    missing_inputs: List[str] = Field(default_factory=list)


class SegmentScheduleItem(BaseModel):
    sequence_index: int
    leg_role: str  # outbound | science_stop | return
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
    return_route_computed: bool
    return_strategy: str  # explicit_computed_reverse_path | symmetric_reverse_corridor | unavailable
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
    feasible_within_usable_budget: Optional[bool] = None
    warnings: List[str] = Field(default_factory=list)


class ConstraintCheckRecord(BaseModel):
    constraint_id: str
    category: str  # terrain | time | return_reserve | resource | evidence | safety_boundary
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
    mission_duration_limit_s: Optional[float] = Field(default=None, gt=0.0)
    return_reserve_fraction: Optional[float] = Field(default=None, ge=0.0, le=0.95)
    operational_overhead_s: float = Field(default=0.0, ge=0.0)
    stop_dwell_seconds: Dict[str, float] = Field(default_factory=dict)
    astronaut_suit_mass_kg: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    payload_mass_kg: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    resources: List[ExplicitResourceSpec] = Field(default_factory=list)
    compute_reverse_return_route: bool = True


class EvaMissionEnvelopeResponse(BaseModel):
    mission_id: str
    mission_name: str
    study_region: str
    dataset_id: str
    source_product_id: str
    route_id: str
    assessment_id: str
    dossier_id: Optional[str] = None
    envelope_status: EnvelopeFeasibilityStatus
    operational_safety_certified: bool = False
    missing_inputs: List[str] = Field(default_factory=list)
    config: MissionConfigRequest
    outbound_summary: Dict[str, Any] = Field(default_factory=dict)
    time_budget: TimeBudgetBreakdown
    energy_budget: EnergyBudgetBreakdown
    resource_budget: ResourceBudgetReport
    return_plan: ReturnPlanReport
    schedule: List[SegmentScheduleItem] = Field(default_factory=list)
    constraints: List[ConstraintCheckRecord] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    cache_validity: CacheValidityState = CacheValidityState.CURRENT
    provenance_graph: ProvenanceDependencyGraph
    created_at_utc: str
    compute_time_ms: float
