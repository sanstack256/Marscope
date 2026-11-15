"""
Pydantic Schemas for Active Marswalk Navigation, State Machine, Turn-by-Turn
Instructions, Obstruction Handling, Replanning, and Turnback Assessment.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


NavigationState = Literal[
    "NOT_CONFIGURED",
    "READY_FOR_OPERATOR_REVIEW",
    "AWAITING_OPERATOR_APPROVAL",
    "ACTIVE",
    "POSITION_UNAVAILABLE",
    "POSITION_STALE",
    "ROUTE_DEVIATION_DETECTED",
    "OBSTRUCTION_REPORTED",
    "REPLANNING_REQUIRED",
    "RETURN_REQUESTED",
    "RETURN_ROUTE_ACTIVE",
    "PAUSED",
    "COMPLETED",
    "ABORTED",
    "EMERGENCY",
]

TurnbackState = Literal[
    "WITHIN_CONFIGURED_PLANNING_CONSTRAINTS",
    "TURNBACK_REVIEW_REQUIRED",
    "RETURN_ROUTE_UNAVAILABLE",
    "RESOURCE_BUDGET_INCOMPLETE",
    "INSUFFICIENT_LOCALIZATION",
    "INSUFFICIENT_TERRAIN_EVIDENCE",
    "INDETERMINATE",
]

NavigationMode = Literal[
    "OPERATOR_SUPERVISED_EVA",
    "MANUAL_WAYPOINT_CHECK",
    "RETURN_TO_BASE",
]


class CreateNavigationSessionRequest(BaseModel):
    route_id: Optional[str] = Field(default=None, max_length=120)
    route_dataset_id: str = Field(..., min_length=1, max_length=160)
    route_crs: str = Field(..., min_length=3, max_length=80)
    navigation_mode: NavigationMode
    return_destination_name: str = Field(..., min_length=2, max_length=160)
    return_destination_lat: float = Field(..., ge=-90.0, le=90.0)
    return_destination_lon: float = Field(..., ge=-180.0, le=360.0)
    deviation_threshold_m: Optional[float] = Field(default=None, gt=0.0, le=5000.0)
    route_payload: Dict[str, Any]
    operational_params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("route_crs")
    @classmethod
    def _validate_mars_crs(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("route_crs is required.")
        return s


class NavigationTransitionRequest(BaseModel):
    target_state: NavigationState
    reason: Optional[str] = Field(default=None, max_length=500)


class ReportObstructionRequest(BaseModel):
    segment_index: Optional[int] = Field(default=None, ge=0)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    location_source: Literal["USER_REPORTED", "OPERATOR_ENTERED", "EXTERNAL_PROVIDER"] = "USER_REPORTED"
    description: str = Field(..., min_length=3, max_length=1000)
    voice_note_id: Optional[str] = Field(default=None, max_length=120)
    attachment_note: Optional[str] = Field(default=None, max_length=500)


class ReplanNavigationRequest(BaseModel):
    avoid_obstruction_id: Optional[str] = Field(default=None, max_length=120)
    strategy: Literal["balanced", "safest", "fastest", "shortest"] = "safest"
    reason: Optional[str] = Field(default=None, max_length=500)


class ApproveReplanRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = Field(default=None, max_length=500)


class NavigationSegmentDetail(BaseModel):
    segment_id: str
    segment_index: int
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    crs: str
    surface_distance_m: float
    start_elevation_m: Optional[float] = None
    end_elevation_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    slope_deg: Optional[float] = None
    roughness_m: Optional[float] = None
    source_dem: str
    effective_resolution_m: Optional[float] = None
    valid_pixel_coverage_pct: Optional[float] = None
    terrain_uncertainty_m: Optional[float] = None
    registration_uncertainty_m: Optional[float] = None
    traversability_evidence_state: str
    candidate_obstacles: List[str] = Field(default_factory=list)
    known_data_gaps: List[str] = Field(default_factory=list)
    limitation_note: str


class NavigationInstructionDetail(BaseModel):
    step_index: int
    segment_id: str
    instruction_text: str
    true_north_bearing_deg: float
    grid_north_bearing_deg: Optional[float] = None
    bearing_reference: str
    heading_status: Literal["USER_ENTERED", "DEVICE_REPORTED", "UNAVAILABLE"] = "UNAVAILABLE"
    distance_m: float
    remaining_distance_m: float
    elevation_change_m: Optional[float] = None
    slope_deg: Optional[float] = None
    support_state: Literal["SUPPORTED", "LIMITED", "UNKNOWN"]
    terrain_limitation: Optional[str] = None
    is_arrival: bool = False


class NavigationProgressDetail(BaseModel):
    progress_status: Literal["AVAILABLE", "PROGRESS UNAVAILABLE"]
    localization_banner: str
    localization_freshness: str
    localization_epistemic_classification: str
    position_timestamp_utc: Optional[str] = None
    position_source: Optional[str] = None
    accuracy_m: Optional[float] = None
    nearest_segment_index: Optional[int] = None
    distance_to_next_waypoint_m: Optional[float] = None
    remaining_route_distance_m: Optional[float] = None
    completed_fraction: Optional[float] = None
    cross_track_deviation_m: Optional[float] = None
    deviation_state: Literal[
        "NOT_CONFIGURED",
        "WITHIN_THRESHOLD",
        "DEVIATION_DETECTED",
        "UNAVAILABLE_ACCURACY_OR_POSITION",
    ]
    deviation_limitation: Optional[str] = None


class TurnbackAssessmentResponse(BaseModel):
    state: TurnbackState
    evaluated_at_utc: str
    outbound_distance_m: Optional[float] = None
    return_distance_m: Optional[float] = None
    return_estimated_duration_s: Optional[float] = None
    configured_max_duration_s: Optional[float] = None
    return_route_available: bool
    return_route_status: str
    resource_budget_status: str
    missing_inputs: List[str] = Field(default_factory=list)
    decision_support_note: str
    return_route_vertices: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class ObstructionReportResponse(BaseModel):
    obstruction_id: str
    nav_session_id: str
    mission_id: str
    reported_by: str
    segment_index: Optional[int] = None
    latitude: float
    longitude: float
    location_source: str
    description: str
    voice_note_id: Optional[str] = None
    attachment_note: Optional[str] = None
    review_state: str
    epistemic_classification: str
    created_at_utc: str


class NavigationSessionResponse(BaseModel):
    nav_session_id: str
    mission_id: str
    astronaut_id: str
    state: NavigationState
    allowed_transitions: List[NavigationState] = Field(default_factory=list)
    navigation_mode: NavigationMode
    route_id: Optional[str] = None
    route_dataset_id: str
    route_crs: str
    return_destination_name: str
    return_destination_lat: float
    return_destination_lon: float
    deviation_threshold_m: Optional[float] = None
    active_segment_index: int
    segments: List[NavigationSegmentDetail] = Field(default_factory=list)
    instructions: List[NavigationInstructionDetail] = Field(default_factory=list)
    progress: NavigationProgressDetail
    turnback: Optional[TurnbackAssessmentResponse] = None
    obstructions: List[ObstructionReportResponse] = Field(default_factory=list)
    candidate_replan: Optional[Dict[str, Any]] = None
    route_limitations: List[str] = Field(default_factory=list)
    approved_by: Optional[str] = None
    approved_at_utc: Optional[str] = None
    last_state_reason: Optional[str] = None
    created_at_utc: str
    updated_at_utc: str
