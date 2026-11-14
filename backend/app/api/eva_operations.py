"""
MARSCOPE EVA Operational Envelope API Router
Exposes mission configuration, full operational envelope evaluation, segment
schedules, reverse return-route inspection, unit-aware resource budgets, timeline,
constraints, and provenance graphs.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.eva_operations.schemas import EvaMissionEnvelopeResponse, MissionConfigRequest
from app.services.container import eva_operations_service

router = APIRouter(prefix="/eva-operations", tags=["EVA Operations"])


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
    """Return Prompt 16 independent return analysis, alternatives, and checkpoint-by-checkpoint turnback PONR."""
    m = _get_mission_or_404(mission_id)
    return {
        "mission_id": m.mission_id,
        "return_status": m.return_plan.return_status,
        "return_route_computed": m.return_plan.return_route_computed,
        "return_plan": m.return_plan,
        "turnback_checkpoints": m.return_plan.turnback_checkpoints,
        "return_alternatives": m.return_plan.return_alternatives,
        "point_of_no_return_distance_m": m.return_plan.point_of_no_return_distance_m,
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
        "uncertainty_notes": m.uncertainty_notes,
        "limitations": m.limitations,
    }
