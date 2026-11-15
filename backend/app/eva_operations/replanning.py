"""
MARSCOPE Dynamic Mission Replanning, State Machine & Dependency Invalidation Engine (Prompt 20 Part 8).

Implements:
  - 14-state MissionWorkflowState machine
  - 15-type traceable MissionEvent ledger
  - Dependency-aware STALE invalidation propagation across terrain, mobility, outbound/return routes,
    time/energy/resource budgets, turnback checkpoints, and science campaign stops
  - Old-vs-new PlanComparisonReport generation
  - Historical plan version preservation (never overwrites prior plans)
  - Explicit operator confirmation gate before replacing the active mission plan
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.eva_operations.return_planning import _polyline_overlap_fraction
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    EvaMissionEnvelopeResponse,
    MissionConfigRequest,
)


class MissionWorkflowState(str, Enum):
    """14 explicit mission operational workflow states (Prompt 20 Part 8.1)."""

    DRAFT = "DRAFT"
    CONFIGURED = "CONFIGURED"
    READY_FOR_MODEL_EVALUATION = "READY_FOR_MODEL_EVALUATION"
    EVALUATION_INCOMPLETE = "EVALUATION_INCOMPLETE"
    ROUTE_COMPUTED = "ROUTE_COMPUTED"
    MISSION_PLAN_REVIEW_REQUIRED = "MISSION_PLAN_REVIEW_REQUIRED"
    EXECUTION_NOT_STARTED = "EXECUTION_NOT_STARTED"
    EXECUTION_IN_PROGRESS = "EXECUTION_IN_PROGRESS"
    PAUSED = "PAUSED"
    REPLANNING_REQUIRED = "REPLANNING_REQUIRED"
    RETURN_RECOMMENDED_BY_CONFIGURED_POLICY = "RETURN_RECOMMENDED_BY_CONFIGURED_POLICY"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    UNKNOWN_STATE = "UNKNOWN_STATE"


class MissionEventType(str, Enum):
    """15 explicit mission operational events triggering invalidation or replanning (Prompt 20 Part 8.2)."""

    START_POSITION_UPDATED = "START_POSITION_UPDATED"
    DESTINATION_UPDATED = "DESTINATION_UPDATED"
    STOP_SEQUENCE_CHANGED = "STOP_SEQUENCE_CHANGED"
    SCIENCE_STOP_DURATION_CHANGED = "SCIENCE_STOP_DURATION_CHANGED"
    HAZARD_MARKED_BY_OPERATOR = "HAZARD_MARKED_BY_OPERATOR"
    OBSTACLE_REVIEW_CHANGED = "OBSTACLE_REVIEW_CHANGED"
    CORRIDOR_BLOCKED = "CORRIDOR_BLOCKED"
    SLOPE_LIMIT_CHANGED = "SLOPE_LIMIT_CHANGED"
    ROUGHNESS_LIMIT_CHANGED = "ROUGHNESS_LIMIT_CHANGED"
    WALKING_SPEED_CHANGED = "WALKING_SPEED_CHANGED"
    RESOURCE_RATE_OR_INVENTORY_CHANGED = "RESOURCE_RATE_OR_INVENTORY_CHANGED"
    RESERVE_POLICY_CHANGED = "RESERVE_POLICY_CHANGED"
    DATASET_UPDATED_OR_REINGESTED = "DATASET_UPDATED_OR_REINGESTED"
    FIELD_OBSERVATION_ADDED = "FIELD_OBSERVATION_ADDED"
    MANUAL_REPLAN_REQUESTED = "MANUAL_REPLAN_REQUESTED"


EVENT_DEPENDENCY_INVALIDATION_MAP: Dict[MissionEventType, List[str]] = {
    MissionEventType.START_POSITION_UPDATED: [
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
        "corridor_evidence",
    ],
    MissionEventType.DESTINATION_UPDATED: [
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
        "corridor_evidence",
    ],
    MissionEventType.STOP_SEQUENCE_CHANGED: [
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
        "corridor_evidence",
        "science_campaign_stops",
    ],
    MissionEventType.SCIENCE_STOP_DURATION_CHANGED: [
        "time_budget",
        "resource_budget",
        "turnback_checkpoints",
        "science_campaign_stops",
    ],
    MissionEventType.HAZARD_MARKED_BY_OPERATOR: [
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.OBSTACLE_REVIEW_CHANGED: [
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.CORRIDOR_BLOCKED: [
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.SLOPE_LIMIT_CHANGED: [
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.ROUGHNESS_LIMIT_CHANGED: [
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.WALKING_SPEED_CHANGED: [
        "mobility_cost_surface",
        "time_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.RESOURCE_RATE_OR_INVENTORY_CHANGED: [
        "resource_budget",
    ],
    MissionEventType.RESERVE_POLICY_CHANGED: [
        "time_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
    MissionEventType.DATASET_UPDATED_OR_REINGESTED: [
        "terrain_features",
        "mobility_cost_surface",
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
        "corridor_evidence",
        "science_campaign_stops",
    ],
    MissionEventType.FIELD_OBSERVATION_ADDED: [
        "corridor_evidence",
        "science_campaign_stops",
    ],
    MissionEventType.MANUAL_REPLAN_REQUESTED: [
        "outbound_route",
        "return_route",
        "time_budget",
        "energy_budget",
        "resource_budget",
        "turnback_checkpoints",
    ],
}


class MissionEventRecord(BaseModel):
    """Immutable, provenance-tagged operational event in the mission ledger (Part 8.2)."""

    event_id: str
    mission_id: str
    event_type: MissionEventType
    recorded_at_utc: str
    operator_id: str = "operator"
    description: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    invalidated_subsystems: List[str] = Field(default_factory=list)
    triggers_replanning: bool = True


class MissionEventIngestRequest(BaseModel):
    """Request payload to record a mission event and propagate dependency invalidation."""

    event_type: MissionEventType
    operator_id: str = Field(default="operator", min_length=1, max_length=80)
    description: str = Field(..., min_length=3, max_length=400)
    client_event_id: Optional[str] = Field(default=None, max_length=120)
    payload: Dict[str, Any] = Field(default_factory=dict)


class MissionReplanRequest(BaseModel):
    """Request payload to compute a candidate revised mission plan without overwriting active plan."""

    operator_id: str = Field(default="operator", min_length=1, max_length=80)
    reason: str = Field(default="Operator-initiated replan evaluation", max_length=300)
    expected_plan_version: Optional[int] = Field(default=None, ge=1)
    updated_config: MissionConfigRequest


class PlanComparisonReport(BaseModel):
    """Detailed old-vs-new plan comparison before operator confirmation (Part 8.5)."""

    comparison_id: str
    mission_id: str
    generated_at_utc: str
    previous_plan_version: int
    candidate_plan_version: int
    trigger_event_ids: List[str] = Field(default_factory=list)
    invalidated_subsystems: List[str] = Field(default_factory=list)
    outbound_distance_delta_m: float
    outbound_climb_gain_delta_m: float
    return_distance_delta_m: float
    return_climb_gain_delta_m: float
    total_mission_time_delta_s: Optional[float] = None
    remaining_time_margin_delta_s: Optional[float] = None
    climb_work_delta_kj: Optional[float] = None
    previous_feasibility_status: str
    candidate_feasibility_status: str
    previous_model_feasibility_status: str
    candidate_model_feasibility_status: str
    previous_ponr_label: Optional[str] = None
    candidate_ponr_label: Optional[str] = None
    route_overlap_fraction: float
    geometry_changed: bool
    requires_operator_approval: bool = True
    approved_by_operator: bool = False
    summary_notes: List[str] = Field(default_factory=list)


class MissionVersionHistoryEntry(BaseModel):
    """Historical snapshot of a mission plan version."""

    plan_version: int
    created_at_utc: str
    status: str  # ACTIVE | SUPERSEDED | CANDIDATE_PENDING_APPROVAL | REJECTED_CANDIDATE
    reason: str
    config: MissionConfigRequest
    envelope: EvaMissionEnvelopeResponse


class MissionOperationalSession(BaseModel):
    """Complete stateful session for a human Marswalk mission (Part 8)."""

    mission_id: str
    linked_campaign_id: Optional[str] = None
    linked_question_id: Optional[str] = None
    integrated_lifecycle_state: Optional[str] = None
    workflow_state: MissionWorkflowState
    active_plan_version: int
    active_config: MissionConfigRequest
    active_envelope: EvaMissionEnvelopeResponse
    stale: bool = False
    stale_subsystems: List[str] = Field(default_factory=list)
    stale_reasons: List[str] = Field(default_factory=list)
    events: List[MissionEventRecord] = Field(default_factory=list)
    plan_history: List[MissionVersionHistoryEntry] = Field(default_factory=list)
    pending_candidate_envelope: Optional[EvaMissionEnvelopeResponse] = None
    pending_candidate_config: Optional[MissionConfigRequest] = None
    pending_comparison: Optional[PlanComparisonReport] = None


def build_plan_comparison_report(
    *,
    mission_id: str,
    prev_env: EvaMissionEnvelopeResponse,
    cand_env: EvaMissionEnvelopeResponse,
    trigger_event_ids: List[str],
    invalidated_subsystems: List[str],
) -> PlanComparisonReport:
    out_d_delta = float(cand_env.outbound_summary.get("horizontal_distance_m", 0.0)) - float(
        prev_env.outbound_summary.get("horizontal_distance_m", 0.0)
    )
    out_g_delta = float(cand_env.outbound_summary.get("elevation_gain_m", 0.0)) - float(
        prev_env.outbound_summary.get("elevation_gain_m", 0.0)
    )
    ret_d_delta = cand_env.return_plan.return_horizontal_distance_m - prev_env.return_plan.return_horizontal_distance_m
    ret_g_delta = cand_env.return_plan.return_elevation_gain_m - prev_env.return_plan.return_elevation_gain_m

    t_delta: Optional[float] = None
    if cand_env.time_budget.total_required_s is not None and prev_env.time_budget.total_required_s is not None:
        t_delta = round(cand_env.time_budget.total_required_s - prev_env.time_budget.total_required_s, 2)

    m_delta: Optional[float] = None
    if cand_env.time_budget.time_margin_s is not None and prev_env.time_budget.time_margin_s is not None:
        m_delta = round(cand_env.time_budget.time_margin_s - prev_env.time_budget.time_margin_s, 2)

    w_delta: Optional[float] = None
    if (
        cand_env.energy_budget.total_positive_climb_work_j is not None
        and prev_env.energy_budget.total_positive_climb_work_j is not None
    ):
        w_delta = round(
            (
                cand_env.energy_budget.total_positive_climb_work_j
                - prev_env.energy_budget.total_positive_climb_work_j
            )
            / 1000.0,
            4,
        )

    tol_m = 12.0
    ov = _polyline_overlap_fraction(
        prev_env.return_plan.return_route_vertices,
        cand_env.return_plan.return_route_vertices,
        tol_m,
    )
    geom_changed = ov < 0.98 or abs(out_d_delta) > 1.0 or abs(ret_d_delta) > 1.0

    notes = [
        f"Outbound horizontal distance change: {out_d_delta:+.1f} m (climb delta: {out_g_delta:+.1f} m).",
        f"Return horizontal distance change: {ret_d_delta:+.1f} m (climb delta: {ret_g_delta:+.1f} m).",
        f"Spatial overlap between previous (v{prev_env.plan_version}) and candidate (v{cand_env.plan_version}) return routes: {ov * 100.0:.1f}%.",
        "Candidate plan requires explicit operator approval before replacing active plan.",
    ]
    if t_delta is not None:
        notes.insert(2, f"Total mission duration change: {t_delta:+.1f} s ({t_delta / 60.0:+.1f} min).")

    prev_ponr = (
        f"{prev_env.return_plan.point_of_no_return_distance_m:.1f} m"
        if prev_env.return_plan.point_of_no_return_distance_m is not None
        else None
    )
    cand_ponr = (
        f"{cand_env.return_plan.point_of_no_return_distance_m:.1f} m"
        if cand_env.return_plan.point_of_no_return_distance_m is not None
        else None
    )

    return PlanComparisonReport(
        comparison_id=f"cmp_{uuid.uuid4().hex[:10]}",
        mission_id=mission_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        previous_plan_version=prev_env.plan_version,
        candidate_plan_version=cand_env.plan_version,
        trigger_event_ids=trigger_event_ids,
        invalidated_subsystems=invalidated_subsystems,
        outbound_distance_delta_m=round(out_d_delta, 2),
        outbound_climb_gain_delta_m=round(out_g_delta, 2),
        return_distance_delta_m=round(ret_d_delta, 2),
        return_climb_gain_delta_m=round(ret_g_delta, 2),
        total_mission_time_delta_s=t_delta,
        remaining_time_margin_delta_s=m_delta,
        climb_work_delta_kj=w_delta,
        previous_feasibility_status=prev_env.envelope_status.value,
        candidate_feasibility_status=cand_env.envelope_status.value,
        previous_model_feasibility_status=prev_env.model_feasibility_status.value,
        candidate_model_feasibility_status=cand_env.model_feasibility_status.value,
        previous_ponr_label=prev_ponr,
        candidate_ponr_label=cand_ponr,
        route_overlap_fraction=ov,
        geometry_changed=geom_changed,
        requires_operator_approval=True,
        approved_by_operator=False,
        summary_notes=notes,
    )
