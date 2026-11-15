"""
MARSCOPE EVA Operational Envelope & Human Marswalk Intelligence API Router (Prompt 20 Extended)
Exposes mission configuration, full operational envelope evaluation, segment
schedules, reverse return-route inspection, unit-aware resource budgets, timeline,
constraints, provenance graphs, stateful replanning sessions, event invalidation,
sensitivity analysis, conditional telemetry, environmental context, and dossier export.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.eva_operations.replanning import (
    MissionEventIngestRequest,
    MissionReplanRequest,
    MissionWorkflowState,
)
from app.eva_operations.schemas import EvaMissionEnvelopeResponse, MissionConfigRequest
from app.eva_operations.telemetry import TelemetryPacketInput
from app.services.container import eva_operations_service

router = APIRouter(prefix="/eva-operations", tags=["EVA Operations"])


class WorkflowTransitionRequest(BaseModel):
    target_state: MissionWorkflowState
    reason: str = Field(default="Operator workflow transition", max_length=240)


class PlanApprovalRequest(BaseModel):
    operator_id: str = Field(default="operator", min_length=1, max_length=80)
    note: str = Field(default="", max_length=300)


class TelemetryConnectRequest(BaseModel):
    provider_id: str = Field(..., min_length=2, max_length=120)


def _get_mission_or_404(mission_id: str) -> EvaMissionEnvelopeResponse:
    m = eva_operations_service.get_mission(mission_id)
    if m is None:
        raise HTTPException(
            status_code=404,
            detail=f"EVA mission envelope '{mission_id}' not found.",
        )
    return m


@router.post("/mission/configure")
def configure_eva_mission(config: MissionConfigRequest):
    """Persist an EVA operational mission configuration."""
    return eva_operations_service.configure_mission(config)


@router.post("/mission/evaluate", response_model=EvaMissionEnvelopeResponse)
def evaluate_eva_mission(config: MissionConfigRequest):
    """Evaluate outbound traverse, reverse return plan, time/energy/resource budgets, and constraints."""
    try:
        return eva_operations_service.evaluate_mission(config)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mission/{mission_id}", response_model=EvaMissionEnvelopeResponse)
def get_eva_mission(mission_id: str):
    """Retrieve a previously evaluated EVA mission operational envelope."""
    return _get_mission_or_404(mission_id)


@router.get("/mission/{mission_id}/schedule")
def get_eva_mission_schedule(mission_id: str):
    """Return segment-by-segment EVA operational schedule linked to corridor geometries."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "envelope_status": m.envelope_status,
        "model_feasibility_status": m.model_feasibility_status,
        "speed_model": m.time_budget.speed_model_used,
        "schedule": m.schedule,
    }


@router.get("/mission/{mission_id}/return-route")
def get_eva_mission_return_route(mission_id: str):
    """Return reverse return-route vertices, asymmetric climb cost, and Point-of-No-Return."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "return_plan": m.return_plan,
        "outbound_summary": m.outbound_summary,
    }


@router.get("/mission/{mission_id}/return-analysis")
def get_eva_mission_return_analysis(mission_id: str):
    """Return Prompt 16/20 independent return analysis, alternatives, and checkpoint-by-checkpoint turnback PONR."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "return_status": m.return_plan.return_status,
        "return_route_computed": m.return_plan.return_route_computed,
        "return_plan": m.return_plan,
        "turnback_checkpoints": m.return_plan.turnback_checkpoints,
        "return_alternatives": m.return_plan.return_alternatives,
        "emergency_return_alternatives": m.return_plan.emergency_return_alternatives,
        "point_of_no_return_distance_m": m.return_plan.point_of_no_return_distance_m,
        "point_of_no_return_explanation": m.return_plan.point_of_no_return_explanation,
        "outbound_vs_return_asymmetry": m.return_plan.outbound_vs_return_asymmetry,
        "time_budget": m.time_budget,
        "outbound_summary": m.outbound_summary,
    }


@router.get("/mission/{mission_id}/resource-budget")
def get_eva_mission_resource_budget(mission_id: str):
    """Return explicit mechanical climb work and unit-aware consumable budget evaluations."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "time_budget": m.time_budget,
        "energy_budget": m.energy_budget,
        "resource_budget": m.resource_budget,
    }


@router.get("/mission/{mission_id}/timeline")
def get_eva_mission_timeline(mission_id: str):
    """Return interactive operational timeline buckets with segment coordinates & cumulative metrics."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "time_budget": m.time_budget,
        "timeline": m.schedule,
        "point_of_no_return_distance_m": m.return_plan.point_of_no_return_distance_m,
    }


@router.get("/mission/{mission_id}/constraints")
def get_eva_mission_constraints(mission_id: str):
    """Return structured PASS / FAIL / UNAVAILABLE / UNVALIDATED mission constraints."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "envelope_status": m.envelope_status,
        "model_feasibility_status": m.model_feasibility_status,
        "operational_safety_certified": m.operational_safety_certified,
        "constraints": m.constraints,
        "missing_inputs": m.missing_inputs,
    }


@router.get("/mission/{mission_id}/provenance")
def get_eva_mission_provenance(mission_id: str):
    """Return EVA operational envelope provenance dependency graph and uncertainty notes."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "provenance_graph": m.provenance_graph,
        "parameter_provenance": m.parameter_provenance,
        "uncertainty_notes": m.uncertainty_notes,
        "limitations": m.limitations,
    }


@router.get("/mission/{mission_id}/session")
def get_eva_mission_session(mission_id: str):
    """Retrieve the full stateful MissionOperationalSession including replanning history and events."""
    sess = eva_operations_service.get_session(mission_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"EVA mission session '{mission_id}' not found.")
    return sess


@router.post("/mission/{mission_id}/workflow-state")
def transition_eva_mission_workflow_state(mission_id: str, req: WorkflowTransitionRequest):
    """Transition the operational workflow state of a mission."""
    try:
        return eva_operations_service.transition_workflow_state(
            mission_id, req.target_state, req.reason
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mission/{mission_id}/events")
def record_eva_mission_event(mission_id: str, req: MissionEventIngestRequest):
    """Record a mission operational event and propagate STALE invalidation across dependent subsystems."""
    try:
        return eva_operations_service.record_mission_event(mission_id, req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mission/{mission_id}/replan/preview")
def preview_eva_mission_replan(mission_id: str, req: MissionReplanRequest):
    """Compute a candidate revised mission plan and return a side-by-side PlanComparisonReport without overwriting active plan."""
    try:
        return eva_operations_service.preview_mission_replan(mission_id, req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/mission/{mission_id}/replan/approve")
def approve_eva_mission_replan(mission_id: str, req: PlanApprovalRequest):
    """Explicitly approve a pending candidate replan to become the active mission plan while preserving history."""
    try:
        return eva_operations_service.approve_revised_plan(
            mission_id, operator_id=req.operator_id, approval_note=req.note
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/mission/{mission_id}/replan/reject")
def reject_eva_mission_replan(mission_id: str, req: PlanApprovalRequest):
    """Explicitly reject a pending candidate replan and retain the previous active plan."""
    try:
        return eva_operations_service.reject_revised_plan(
            mission_id, operator_id=req.operator_id, rejection_reason=req.note
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mission/{mission_id}/sensitivity")
def get_eva_mission_sensitivity(mission_id: str):
    """Evaluate multi-dimensional operational sensitivity across speed, model category, reserve, and resource rates."""
    try:
        return eva_operations_service.get_sensitivity_report(mission_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mission/{mission_id}/dossier")
def export_eva_mission_dossier(mission_id: str):
    """Export a complete, SHA-256 checksummed reproducible Mission Operations Dossier."""
    try:
        return eva_operations_service.export_mission_dossier(mission_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mission/{mission_id}/environmental-context")
def get_eva_mission_environmental_context(mission_id: str):
    """Return archive-observed Curiosity RAD/REMS context separated from unavailable live surface weather/radiation."""
    try:
        return eva_operations_service.get_environmental_context(mission_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/telemetry/status")
def get_eva_telemetry_status(mission_id: Optional[str] = None):
    """Return current telemetry adapter state (defaults to TELEMETRY NOT CONNECTED / LIVE CREW STATE UNAVAILABLE)."""
    return eva_operations_service.get_telemetry_state(mission_id)


@router.post("/telemetry/connect")
def connect_eva_telemetry_provider(req: TelemetryConnectRequest):
    """Connect an external telemetry provider without fabricating packets."""
    try:
        return eva_operations_service.connect_telemetry_provider(req.provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/telemetry/disconnect")
def disconnect_eva_telemetry_provider():
    """Disconnect external telemetry provider and return to TELEMETRY NOT CONNECTED."""
    return eva_operations_service.disconnect_telemetry_provider()


@router.post("/telemetry/ingest")
def ingest_eva_telemetry_packet(
    packet: TelemetryPacketInput,
    authorization: Optional[str] = Header(default=None),
    x_operator_token: Optional[str] = Header(default=None),
    x_tracking_token: Optional[str] = Header(default=None),
):
    """Validate and ingest an external telemetry packet (rejects simulated/fake packets or out-of-sequence packets)."""
    ok, code, msg = eva_operations_service.telemetry_adapter.verify_auth(
        authorization_header=authorization,
        x_operator_token=x_operator_token,
        x_tracking_token=x_tracking_token,
    )
    if not ok:
        raise HTTPException(status_code=code, detail=msg)
    try:
        return eva_operations_service.ingest_telemetry_packet(packet)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
