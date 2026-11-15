"""
MARSCOPE Reproducible Mission Operations Dossier Exporter (Prompt 20 Part 13).

Exports a complete, self-contained, SHA-256 checksummed scientific and operational
dossier for a planned human Marswalk mission.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.eva_operations.replanning import MissionOperationalSession
from app.eva_operations.sensitivity import MissionSensitivityAnalysisReport


class MissionOperationsDossier(BaseModel):
    """Complete reproducible Mission Operations Dossier (Prompt 20 Part 13)."""

    dossier_id: str
    dossier_schema_version: str = "p20_mission_dossier_v2.0"
    exported_at_utc: str
    sha256_integrity_digest: str
    mission_id: str
    mission_name: str
    study_region: str
    workflow_state: str
    plan_version: int
    stale: bool
    stale_reasons: List[str] = Field(default_factory=list)
    feasibility_status: str
    model_feasibility_status: str
    feasibility_summary: str
    dataset_provenance: Dict[str, Any]
    configured_mission_inputs: Dict[str, Any]
    parameter_provenance: List[Dict[str, Any]]
    locomotion_model: Optional[Dict[str, Any]] = None
    locomotion_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    traversability_analytics: Dict[str, Any] = Field(default_factory=dict)
    outbound_route_summary: Dict[str, Any]
    return_plan_summary: Dict[str, Any]
    time_budget: Dict[str, Any]
    energy_budget: Dict[str, Any]
    resource_budget: Dict[str, Any]
    schedule: List[Dict[str, Any]]
    constraint_checks: List[Dict[str, Any]]
    environmental_context: Dict[str, Any]
    telemetry_state: Dict[str, Any]
    replanning_history: Dict[str, Any]
    sensitivity_analysis: Dict[str, Any]
    scientific_limitations_and_disclosures: List[str]


def build_mission_operations_dossier(
    *,
    session: MissionOperationalSession,
    sensitivity_report: MissionSensitivityAnalysisReport,
) -> MissionOperationsDossier:
    env = session.active_envelope
    cfg = session.active_config

    dataset_prov = {
        "dataset_id": env.dataset_id,
        "source_product_id": env.source_product_id,
        "route_id": env.route_id,
        "assessment_id": env.assessment_id,
        "provenance_graph": env.provenance_graph.model_dump(),
    }
    outbound_summary = dict(env.outbound_summary)
    ret = env.return_plan
    return_summary = {
        "return_route_computed": ret.return_route_computed,
        "return_strategy": ret.return_strategy,
        "return_status": ret.return_status.value,
        "return_horizontal_distance_m": ret.return_horizontal_distance_m,
        "return_surface_distance_m": ret.return_surface_distance_m,
        "return_elevation_gain_m": ret.return_elevation_gain_m,
        "return_elevation_loss_m": ret.return_elevation_loss_m,
        "return_duration_constant_s": ret.return_duration_constant_s,
        "return_duration_tobler_s": ret.return_duration_tobler_s,
        "overlap_with_outbound_fraction": ret.overlap_with_outbound_fraction,
        "point_of_no_return_distance_m": ret.point_of_no_return_distance_m,
        "point_of_no_return_explanation": ret.point_of_no_return_explanation,
        "outbound_vs_return_asymmetry": ret.outbound_vs_return_asymmetry,
        "return_alternatives_count": len(ret.return_alternatives),
        "emergency_return_alternatives_count": len(ret.emergency_return_alternatives),
        "turnback_checkpoints": [cp.model_dump() for cp in ret.turnback_checkpoints],
    }

    replan_hist = {
        "active_plan_version": session.active_plan_version,
        "workflow_state": session.workflow_state.value,
        "stale": session.stale,
        "stale_subsystems": session.stale_subsystems,
        "stale_reasons": session.stale_reasons,
        "events": [e.model_dump() for e in session.events],
        "plan_versions_preserved": [
            {
                "plan_version": h.plan_version,
                "created_at_utc": h.created_at_utc,
                "status": h.status,
                "reason": h.reason,
                "feasibility_status": h.envelope.envelope_status.value,
                "model_feasibility_status": h.envelope.model_feasibility_status.value,
            }
            for h in session.plan_history
        ],
        "pending_comparison": (
            session.pending_comparison.model_dump() if session.pending_comparison is not None else None
        ),
    }

    disclosures = list(env.uncertainty_notes) + list(env.limitations) + [
        "All operational evaluations are strictly bounded by configured models and user-supplied assumptions; no human survival or flight safety guarantee is claimed.",
    ]

    core_payload = {
        "mission_id": env.mission_id,
        "plan_version": env.plan_version,
        "dataset_provenance": dataset_prov,
        "configured_mission_inputs": cfg.model_dump(),
        "outbound_route_summary": outbound_summary,
        "return_plan_summary": return_summary,
        "time_budget": env.time_budget.model_dump(),
        "energy_budget": env.energy_budget.model_dump(),
        "resource_budget": env.resource_budget.model_dump(),
    }
    digest = hashlib.sha256(
        json.dumps(core_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return MissionOperationsDossier(
        dossier_id=f"dossier_{uuid.uuid4().hex[:10]}",
        exported_at_utc=datetime.now(timezone.utc).isoformat(),
        sha256_integrity_digest=digest,
        mission_id=env.mission_id,
        mission_name=env.mission_name,
        study_region=env.study_region,
        workflow_state=session.workflow_state.value,
        plan_version=session.active_plan_version,
        stale=session.stale,
        stale_reasons=session.stale_reasons,
        feasibility_status=env.envelope_status.value,
        model_feasibility_status=env.model_feasibility_status.value,
        feasibility_summary=(
            f"Envelope status: {env.envelope_status.value} | "
            f"Model status: {env.model_feasibility_status.value}"
        ),
        dataset_provenance=dataset_prov,
        configured_mission_inputs=cfg.model_dump(),
        parameter_provenance=[p.model_dump() for p in env.parameter_provenance],
        locomotion_model=(
            env.locomotion_model.model_dump() if env.locomotion_model is not None else None
        ),
        locomotion_scenarios=[s.model_dump() for s in env.locomotion_scenarios],
        traversability_analytics=env.traversability_analytics,
        outbound_route_summary=outbound_summary,
        return_plan_summary=return_summary,
        time_budget=env.time_budget.model_dump(),
        energy_budget=env.energy_budget.model_dump(),
        resource_budget=env.resource_budget.model_dump(),
        schedule=[s.model_dump() for s in env.schedule],
        constraint_checks=[c.model_dump() for c in env.constraints],
        environmental_context=(
            env.environmental_context.model_dump() if env.environmental_context is not None else {}
        ),
        telemetry_state=(
            env.telemetry_state.model_dump() if env.telemetry_state is not None else {}
        ),
        replanning_history=replan_hist,
        sensitivity_analysis=sensitivity_report.model_dump(),
        scientific_limitations_and_disclosures=disclosures,
    )
