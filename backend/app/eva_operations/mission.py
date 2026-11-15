"""
MARSCOPE EVA Operational Envelope Orchestrator Service (Prompt 20 Extended)
Coordinates route computation, polygon-masked corridor evidence assessment,
reverse return-route verification, time/energy/unit-aware resource envelopes,
segment schedules, dynamic mission replanning, conditional telemetry,
environmental/radiation context, sensitivity analysis, and reproducible dossier export.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import uuid

from app.evidence_intelligence.schemas import CacheValidityState, CorridorAssessRequest
from app.eva_operations.constraints import (
    determine_envelope_and_model_status,
    evaluate_eva_constraints,
)
from app.eva_operations.dossier import (
    MissionOperationsDossier,
    build_mission_operations_dossier,
)
from app.eva_operations.energy_budget import evaluate_eva_energy_budget
from app.eva_operations.environmental_context import (
    EvaEnvironmentalContextReport,
    evaluate_eva_environmental_context,
)
from app.eva_operations.locomotion import (
    LocomotionModelCategory,
    compare_locomotion_scenarios,
)
from app.eva_operations.replanning import (
    EVENT_DEPENDENCY_INVALIDATION_MAP as EVENT_INVALIDATION_RULES,
    MissionEventIngestRequest,
    MissionEventRecord,
    MissionOperationalSession,
    MissionReplanRequest,
    MissionVersionHistoryEntry,
    MissionWorkflowState,
    PlanComparisonReport,
    build_plan_comparison_report,
)
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.return_planning import (
    _estimate_vertex_path_tobler_seconds,
    plan_eva_return_route,
)
from app.eva_operations.route_schedule import build_eva_schedule
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    EvaMissionEnvelopeResponse,
    MissionConfigRequest,
)
from app.eva_operations.sensitivity import (
    MissionSensitivityAnalysisReport,
    evaluate_mission_sensitivity,
)
from app.eva_operations.telemetry import (
    ConditionalTelemetryAdapter,
    TelemetryIngestResult,
    TelemetryPacketInput,
)
from app.eva_operations.time_budget import evaluate_eva_time_budget
from app.eva_operations.uncertainty import summarize_eva_uncertainties
from app.mobility.models import UNMEASURED_SOIL_PROPERTIES_DEFAULT
from app.routing.schemas import RouteComputeRequest, RoutePlanningConstraints
from app.science.provenance_graph import (
    ParameterProvenanceRecord,
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)


def _atomic_write_json(target_path: Path, text: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.stem}_", suffix=".tmp", dir=str(target_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(text)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp_name, target_path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


class EvaOperationsService:
    """Manages persistent EVA mission configurations, operational envelope evaluations, replanning, and dossiers."""

    def __init__(
        self,
        *,
        routing_service: Any,
        evidence_service: Any,
        processed_dir: Path,
    ) -> None:
        self.routing_service = routing_service
        self.evidence_service = evidence_service
        self.storage_dir = processed_dir / "eva_operations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._configs: Dict[str, MissionConfigRequest] = {}
        self._missions: Dict[str, EvaMissionEnvelopeResponse] = {}
        self._sessions: Dict[str, MissionOperationalSession] = {}
        self.telemetry_adapter = ConditionalTelemetryAdapter()

    @staticmethod
    def _derive_mission_id(config: MissionConfigRequest) -> str:
        if config.mission_id and config.mission_id.strip():
            return config.mission_id.strip()
        digest = hashlib.sha256(
            config.model_dump_json(exclude={"mission_id"}).encode("utf-8")
        ).hexdigest()[:12]
        return f"eva-{digest}"

    def configure_mission(self, config: MissionConfigRequest) -> Dict[str, object]:
        mid = self._derive_mission_id(config)
        cfg_stored = config.model_copy(update={"mission_id": mid})
        self._configs[mid] = cfg_stored
        _atomic_write_json(
            self.storage_dir / f"{mid}.config.json",
            cfg_stored.model_dump_json(indent=2),
        )
        return {"mission_id": mid, "configured": True, "config": cfg_stored}

    def _compute_envelope_internal(
        self,
        cfg: MissionConfigRequest,
        *,
        plan_version: int = 1,
        workflow_state: MissionWorkflowState = MissionWorkflowState.ROUTE_COMPUTED,
    ) -> EvaMissionEnvelopeResponse:
        t0 = time.perf_counter()
        mid = cfg.mission_id or self._derive_mission_id(cfg)

        # Compute outbound route
        base_constraints = cfg.constraints or RoutePlanningConstraints()
        out_constraints = base_constraints.model_copy(
            update={
                "walking_speed_m_per_s": cfg.walking_speed_mps,
                "return_to_start": False,
                "unknown_terrain_policy": cfg.unknown_terrain_policy,
                "operator_unknown_override_reason": cfg.operator_unknown_override_reason,
            }
        )
        route = self.routing_service.compute_route(
            RouteComputeRequest(
                dataset_id=cfg.dataset_id,
                start=cfg.start,
                destination=cfg.destination,
                mode=cfg.mode,
                target_ids=cfg.selected_target_ids,
                constraints=out_constraints,
            )
        )

        corridor = self.evidence_service.assess_corridor(
            CorridorAssessRequest(
                dataset_id=cfg.dataset_id,
                start=cfg.start,
                destination=cfg.destination,
                route=route,
                mode=cfg.mode,
                corridor_width_m=cfg.corridor_width_m,
                target_segment_length_m=cfg.target_segment_length_m,
                observation_search_radius_m=cfg.observation_search_radius_m,
                selected_target_ids=cfg.selected_target_ids,
                constraints=out_constraints,
            )
        )

        stops_total_s = sum(max(0.0, float(v)) for v in cfg.stop_dwell_seconds.values())
        usable_s = (
            round(cfg.mission_duration_limit_s * (1.0 - cfg.return_reserve_fraction), 1)
            if (cfg.mission_duration_limit_s is not None and cfg.return_reserve_fraction is not None)
            else None
        )

        eff_cat = cfg.locomotion_category or (
            LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
            if cfg.use_tobler_grade_approximation
            else LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED
        )
        use_tob = (
            cfg.use_tobler_grade_approximation
            or eff_cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
        )

        return_plan = plan_eva_return_route(
            routing_service=self.routing_service,
            dataset_id=cfg.dataset_id,
            outbound_route=route,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=use_tob,
            stop_dwell_total_s=stops_total_s,
            operational_overhead_s=cfg.operational_overhead_s,
            usable_budget_s=usable_s,
            compute_reverse_return_route=cfg.compute_reverse_return_route,
            locomotion_category=eff_cat,
            min_valid_slope_deg=cfg.locomotion_min_valid_slope_deg,
            max_valid_slope_deg=cfg.locomotion_max_valid_slope_deg,
        )

        outbound_const_s = (
            round(route.total_surface_distance_m / cfg.walking_speed_mps, 1)
            if (cfg.walking_speed_mps and cfg.walking_speed_mps > 0)
            else None
        )
        outbound_tobler_s = _estimate_vertex_path_tobler_seconds(
            route.vertices,
            cfg.walking_speed_mps,
            min_valid_slope_deg=cfg.locomotion_min_valid_slope_deg,
            max_valid_slope_deg=cfg.locomotion_max_valid_slope_deg,
        )

        time_budget = evaluate_eva_time_budget(
            outbound_constant_s=outbound_const_s,
            outbound_tobler_s=outbound_tobler_s,
            return_constant_s=return_plan.return_duration_constant_s,
            return_tobler_s=return_plan.return_duration_tobler_s,
            return_route_computed=return_plan.return_route_computed,
            stop_dwell_seconds=cfg.stop_dwell_seconds,
            operational_overhead_s=cfg.operational_overhead_s,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=use_tob,
            mission_duration_limit_s=cfg.mission_duration_limit_s,
            return_reserve_fraction=cfg.return_reserve_fraction,
            locomotion_category=eff_cat,
            validated_suit_model_source=cfg.validated_suit_model_source,
            min_valid_slope_deg=cfg.locomotion_min_valid_slope_deg,
            max_valid_slope_deg=cfg.locomotion_max_valid_slope_deg,
        )

        energy_budget = evaluate_eva_energy_budget(
            outbound_climb_gain_m=route.total_elevation_gain_m,
            outbound_descent_loss_m=route.total_elevation_loss_m,
            return_climb_gain_m=return_plan.return_elevation_gain_m,
            return_descent_loss_m=return_plan.return_elevation_loss_m,
            astronaut_suit_mass_kg=cfg.astronaut_suit_mass_kg,
            payload_mass_kg=cfg.payload_mass_kg,
        )

        phase_durations_s: Dict[str, float] = {
            "operational_overhead": cfg.operational_overhead_s,
            "science_stop": stops_total_s,
        }
        if time_budget.outbound_travel_s is not None:
            phase_durations_s["outbound"] = time_budget.outbound_travel_s
        if time_budget.return_travel_s is not None:
            phase_durations_s["return"] = time_budget.return_travel_s

        resource_budget = evaluate_eva_resource_budget(
            resources=cfg.resources,
            exposure_duration_s=time_budget.total_required_s,
            phase_durations_s=phase_durations_s,
        )

        schedule = build_eva_schedule(
            corridor=corridor,
            return_plan=return_plan,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=use_tob,
            stop_dwell_seconds=cfg.stop_dwell_seconds,
            operational_overhead_s=cfg.operational_overhead_s,
            surface_weight_n=energy_budget.surface_weight_n,
            locomotion_category=eff_cat,
            validated_suit_model_source=cfg.validated_suit_model_source,
            min_valid_slope_deg=cfg.locomotion_min_valid_slope_deg,
            max_valid_slope_deg=cfg.locomotion_max_valid_slope_deg,
        )

        constraints = evaluate_eva_constraints(
            config=cfg,
            route=route,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
            resource_budget=resource_budget,
        )

        missing_inputs = list(
            dict.fromkeys(
                time_budget.missing_inputs
                + energy_budget.missing_inputs
                + resource_budget.missing_inputs
            )
        )

        env_status, model_status = determine_envelope_and_model_status(
            config=cfg,
            constraints=constraints,
            time_budget=time_budget,
            energy_budget=energy_budget,
            resource_budget=resource_budget,
        )

        uncertainties, limitations = summarize_eva_uncertainties(
            config=cfg,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
        )

        # Multi-scenario locomotion comparison
        out_segs = []
        for s in schedule:
            if s.leg_role == "outbound":
                dz = s.elevation_gain_m - s.elevation_loss_m
                horiz = max(0.1, math.sqrt(max(0.01, s.distance_m * s.distance_m - dz * dz)))
                out_segs.append(
                    {
                        "horizontal_distance_m": horiz,
                        "elevation_change_m": dz,
                        "slope_deg": math.degrees(math.atan2(abs(dz), horiz)),
                        "roughness_tri_m": 0.0,
                    }
                )
        ret_segs = []
        for s in schedule:
            if s.leg_role == "return":
                dz = s.elevation_gain_m - s.elevation_loss_m
                horiz = max(0.1, math.sqrt(max(0.01, s.distance_m * s.distance_m - dz * dz)))
                ret_segs.append(
                    {
                        "horizontal_distance_m": horiz,
                        "elevation_change_m": dz,
                        "slope_deg": math.degrees(math.atan2(abs(dz), horiz)),
                        "roughness_tri_m": 0.0,
                    }
                )
        loco_scenarios = compare_locomotion_scenarios(
            outbound_segments=out_segs,
            return_segments=ret_segs,
            base_speed_mps=cfg.walking_speed_mps,
            mission_duration_limit_s=cfg.mission_duration_limit_s,
            operational_overhead_s=cfg.operational_overhead_s + stops_total_s,
        )

        # Parameter provenance registry
        param_prov: List[ParameterProvenanceRecord] = (
            list(time_budget.parameter_provenance)
            + list(energy_budget.parameter_provenance)
            + [
                ParameterProvenanceRecord(
                    parameter_name="corridor_width_m",
                    value=cfg.corridor_width_m,
                    units="m",
                    classification=ScientificDataClassification.USER_ASSUMED,
                    source_type="user_input" if cfg.confirm_default_policies else "default_operational_policy",
                    validity_domain="[10.0, 500.0] m corridor assessment width",
                    confirmed_by_operator=cfg.confirm_default_policies,
                ),
                ParameterProvenanceRecord(
                    parameter_name="unknown_terrain_policy",
                    value=cfg.unknown_terrain_policy.value,
                    units="policy_enum",
                    classification=ScientificDataClassification.USER_ASSUMED,
                    source_type="user_input",
                    validity_domain="Explicit routing rule for unobservable/insufficient-evidence terrain cells",
                    confirmed_by_operator=True,
                ),
            ]
        )

        # Traversability & unmeasured material analytics
        trav_analytics: Dict[str, Any] = {
            "native_dem_resolution_m": route.native_dem_resolution_m,
            "minimum_resolvable_feature_width_m": round(3.0 * route.native_dem_resolution_m, 2),
            "unknown_terrain_policy": cfg.unknown_terrain_policy.value,
            "corridor_valid_dem_fraction": float(corridor.uncertainty.corridor_valid_fraction),
            "mean_optical_coverage_fraction": corridor.coverage_summary.get("mean_optical_coverage_fraction"),
            "optical_coverage_status": corridor.coverage_summary.get("optical_coverage_status", "UNAVAILABLE"),
            "unmeasured_soil_properties": dict(UNMEASURED_SOIL_PROPERTIES_DEFAULT),
            "sub_pixel_hazard_disclosure": (
                f"Sub-pixel boulders, scarps, and regolith pockets smaller than "
                f"{3.0 * route.native_dem_resolution_m:.1f} m (~3x DEM posting) cannot be resolved from orbital DEM alone."
            ),
        }

        env_ctx = evaluate_eva_environmental_context(
            study_region=cfg.study_region,
            mission_duration_s=time_budget.total_required_s,
        )
        telem_state = self.telemetry_adapter.get_current_state(mid)

        prov = ProvenanceDependencyGraph(
            output_id=mid,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[cfg.dataset_id],
            input_product_ids=[route.source_product_id],
            input_variables=["route_geometry", "dem_corridor", "user_eva_constraints"],
            input_units=["m", "deg", "s_kg_explicit"],
            input_crs="IAU2000:49900",
            input_resolution_m=route.native_dem_resolution_m,
            method="eva_operational_envelope_v2",
            algorithm_version="eva_envelope_v2",
            parameters={
                "speed_model": time_budget.speed_model_used.value,
                "locomotion_category": eff_cat.value,
                "return_strategy": return_plan.return_strategy,
                "return_status": return_plan.return_status.value,
                "walking_speed_mps": cfg.walking_speed_mps,
                "return_reserve_fraction": cfg.return_reserve_fraction,
                "unknown_terrain_policy": cfg.unknown_terrain_policy.value,
            },
            parameter_provenance=param_prov,
            assumptions=uncertainties + limitations,
            intermediate_steps=[
                ProvenanceStep(
                    step_id="eva-outbound-route",
                    label="Outbound A*/Dijkstra Surface Traverse",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[route.route_id],
                    method=f"{route.algorithm} ({route.mode.value})",
                    algorithm_version="routing_v2_science_aware",
                    output_variable="outbound_traverse_geometry",
                    output_units="m",
                ),
                ProvenanceStep(
                    step_id="eva-corridor-evidence",
                    label="Polygon-Masked Corridor Evidence Assessment",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[corridor.assessment_id],
                    method="terrain_optical_observation_evidence_v2",
                    algorithm_version="terrain_corridor_v3",
                    output_variable="corridor_evidence_summary",
                    output_units="fraction_and_m",
                ),
                ProvenanceStep(
                    step_id="eva-return-and-budgets",
                    label="Return-Route & Time/Energy/Resource Envelope",
                    classification=ScientificDataClassification.USER_ASSUMED,
                    input_ids=["USER_EVA_CONSTRAINTS"],
                    method="explicit_unit_aware_envelope",
                    algorithm_version="eva_envelope_v2",
                    output_variable="eva_operational_envelope",
                    output_units="s_J_and_resource_units",
                ),
            ],
            validation_state="analytical_planning_envelope_not_safety_certified",
        )

        return EvaMissionEnvelopeResponse(
            mission_id=mid,
            mission_name=cfg.mission_name,
            study_region=cfg.study_region,
            dataset_id=cfg.dataset_id,
            source_product_id=route.source_product_id,
            route_id=route.route_id,
            assessment_id=corridor.assessment_id,
            envelope_status=env_status,
            model_feasibility_status=model_status,
            workflow_state=workflow_state.value,
            plan_version=plan_version,
            stale=False,
            stale_reasons=[],
            operational_safety_certified=False,
            missing_inputs=missing_inputs,
            config=cfg,
            outbound_summary={
                "horizontal_distance_m": route.total_horizontal_distance_m,
                "surface_distance_m": route.total_surface_distance_m,
                "elevation_gain_m": route.total_elevation_gain_m,
                "elevation_loss_m": route.total_elevation_loss_m,
                "max_slope_deg": route.max_slope_deg,
                "segment_count": len(corridor.segments),
            },
            locomotion_model=time_budget.locomotion_model,
            locomotion_scenarios=loco_scenarios,
            parameter_provenance=param_prov,
            traversability_analytics=trav_analytics,
            time_budget=time_budget,
            energy_budget=energy_budget,
            resource_budget=resource_budget,
            return_plan=return_plan,
            schedule=schedule,
            constraints=constraints,
            environmental_context=env_ctx,
            telemetry_state=telem_state,
            uncertainty_notes=uncertainties,
            limitations=limitations,
            cache_validity=CacheValidityState.CURRENT,
            provenance_graph=prov,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    def evaluate_mission(self, config: MissionConfigRequest) -> EvaMissionEnvelopeResponse:
        mid = self._derive_mission_id(config)
        cfg = config.model_copy(update={"mission_id": mid})
        self._configs[mid] = cfg
        _atomic_write_json(
            self.storage_dir / f"{mid}.config.json",
            cfg.model_dump_json(indent=2),
        )

        resp = self._compute_envelope_internal(
            cfg,
            plan_version=1,
            workflow_state=MissionWorkflowState.ROUTE_COMPUTED,
        )
        self._missions[mid] = resp
        _atomic_write_json(
            self.storage_dir / f"{mid}.envelope.json",
            resp.model_dump_json(indent=2),
        )

        # Initialize or update stateful MissionOperationalSession
        wf = (
            MissionWorkflowState.EVALUATION_INCOMPLETE
            if resp.model_feasibility_status
            in (
                EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION,
                EnvelopeFeasibilityStatus.BLOCKED_BY_UNKNOWN_INPUTS,
            )
            else MissionWorkflowState.EXECUTION_NOT_STARTED
        )
        resp.workflow_state = wf.value
        session = MissionOperationalSession(
            mission_id=mid,
            workflow_state=wf,
            active_plan_version=1,
            active_config=cfg,
            active_envelope=resp,
            stale=False,
            stale_subsystems=[],
            stale_reasons=[],
            events=[],
            plan_history=[
                MissionVersionHistoryEntry(
                    plan_version=1,
                    created_at_utc=resp.created_at_utc,
                    status="ACTIVE",
                    reason="Initial mission operational envelope evaluation",
                    config=cfg,
                    envelope=resp,
                )
            ],
        )
        self._sessions[mid] = session
        _atomic_write_json(
            self.storage_dir / f"{mid}.session.json",
            session.model_dump_json(indent=2),
        )
        return resp

    def get_mission(self, mission_id: str) -> Optional[EvaMissionEnvelopeResponse]:
        if mission_id in self._missions:
            return self._missions[mission_id]
        path = self.storage_dir / f"{mission_id}.envelope.json"
        if path.exists():
            obj = EvaMissionEnvelopeResponse.model_validate_json(path.read_text(encoding="utf-8"))
            self._missions[mission_id] = obj
            return obj
        return None

    def get_session(self, mission_id: str) -> Optional[MissionOperationalSession]:
        if mission_id in self._sessions:
            return self._sessions[mission_id]
        s_path = self.storage_dir / f"{mission_id}.session.json"
        if s_path.exists():
            sess = MissionOperationalSession.model_validate_json(s_path.read_text(encoding="utf-8"))
            self._sessions[mission_id] = sess
            return sess
        env = self.get_mission(mission_id)
        if env is None:
            return None
        sess = MissionOperationalSession(
            mission_id=mission_id,
            workflow_state=MissionWorkflowState.EXECUTION_NOT_STARTED,
            active_plan_version=env.plan_version,
            active_config=env.config,
            active_envelope=env,
            plan_history=[
                MissionVersionHistoryEntry(
                    plan_version=env.plan_version,
                    created_at_utc=env.created_at_utc,
                    status="ACTIVE",
                    reason="Recovered from persisted envelope",
                    config=env.config,
                    envelope=env,
                )
            ],
        )
        self._sessions[mission_id] = sess
        return sess

    def _save_session(self, session: MissionOperationalSession) -> None:
        self._sessions[session.mission_id] = session
        self._missions[session.mission_id] = session.active_envelope
        _atomic_write_json(
            self.storage_dir / f"{session.mission_id}.session.json",
            session.model_dump_json(indent=2),
        )
        _atomic_write_json(
            self.storage_dir / f"{session.mission_id}.envelope.json",
            session.active_envelope.model_dump_json(indent=2),
        )

    def transition_workflow_state(
        self, mission_id: str, target_state: MissionWorkflowState, reason: str = ""
    ) -> MissionOperationalSession:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        sess.workflow_state = target_state
        sess.active_envelope.workflow_state = target_state.value
        self._save_session(sess)
        return sess

    def record_mission_event(
        self, mission_id: str, req: MissionEventIngestRequest
    ) -> MissionOperationalSession:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        inv = list(EVENT_INVALIDATION_RULES.get(req.event_type, ["outbound_route", "return_route"]))
        evt = MissionEventRecord(
            event_id=f"evt_{uuid.uuid4().hex[:10]}",
            mission_id=mission_id,
            event_type=req.event_type,
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            operator_id=req.operator_id,
            description=req.description,
            payload=req.payload,
            invalidated_subsystems=inv,
            triggers_replanning=True,
        )
        sess.events.append(evt)
        sess.stale = True
        sess.stale_subsystems = list(dict.fromkeys(sess.stale_subsystems + inv))
        reason_msg = f"[{evt.event_type.value}] {evt.description} (invalidates: {', '.join(inv)})"
        if reason_msg not in sess.stale_reasons:
            sess.stale_reasons.append(reason_msg)
        sess.workflow_state = MissionWorkflowState.REPLANNING_REQUIRED
        sess.active_envelope.stale = True
        sess.active_envelope.stale_reasons = list(sess.stale_reasons)
        sess.active_envelope.workflow_state = MissionWorkflowState.REPLANNING_REQUIRED.value
        self._save_session(sess)
        return sess

    def preview_mission_replan(
        self, mission_id: str, req: MissionReplanRequest
    ) -> PlanComparisonReport:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        cand_ver = max([h.plan_version for h in sess.plan_history] or [sess.active_plan_version]) + 1
        cand_cfg = req.updated_config.model_copy(update={"mission_id": mission_id})
        cand_env = self._compute_envelope_internal(
            cand_cfg,
            plan_version=cand_ver,
            workflow_state=MissionWorkflowState.MISSION_PLAN_REVIEW_REQUIRED,
        )
        cmp_report = build_plan_comparison_report(
            mission_id=mission_id,
            prev_env=sess.active_envelope,
            cand_env=cand_env,
            trigger_event_ids=[e.event_id for e in sess.events],
            invalidated_subsystems=sess.stale_subsystems,
        )
        sess.pending_candidate_config = cand_cfg
        sess.pending_candidate_envelope = cand_env
        sess.pending_comparison = cmp_report
        sess.workflow_state = MissionWorkflowState.MISSION_PLAN_REVIEW_REQUIRED
        sess.active_envelope.workflow_state = MissionWorkflowState.MISSION_PLAN_REVIEW_REQUIRED.value
        sess.plan_history.append(
            MissionVersionHistoryEntry(
                plan_version=cand_ver,
                created_at_utc=cand_env.created_at_utc,
                status="CANDIDATE_PENDING_APPROVAL",
                reason=req.reason,
                config=cand_cfg,
                envelope=cand_env,
            )
        )
        self._save_session(sess)
        return cmp_report

    def approve_revised_plan(
        self, mission_id: str, operator_id: str = "operator", approval_note: str = ""
    ) -> MissionOperationalSession:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        if sess.pending_candidate_envelope is None or sess.pending_candidate_config is None:
            raise ValueError(f"No pending candidate replan exists for mission '{mission_id}'.")

        cand_ver = sess.pending_candidate_envelope.plan_version
        for h in sess.plan_history:
            if h.status == "ACTIVE":
                h.status = "SUPERSEDED"
            elif h.plan_version == cand_ver:
                h.status = "ACTIVE"
                if approval_note:
                    h.reason = f"{h.reason} | Approved by {operator_id}: {approval_note}"

        sess.active_plan_version = cand_ver
        sess.active_config = sess.pending_candidate_config
        sess.active_envelope = sess.pending_candidate_envelope
        sess.active_envelope.stale = False
        sess.active_envelope.stale_reasons = []
        sess.active_envelope.workflow_state = MissionWorkflowState.EXECUTION_NOT_STARTED.value
        sess.stale = False
        sess.stale_subsystems = []
        sess.stale_reasons = []
        sess.workflow_state = MissionWorkflowState.EXECUTION_NOT_STARTED
        if sess.pending_comparison is not None:
            sess.pending_comparison.approved_by_operator = True
            sess.pending_comparison.requires_operator_approval = False
        sess.pending_candidate_envelope = None
        sess.pending_candidate_config = None
        self._save_session(sess)
        return sess

    def reject_revised_plan(
        self, mission_id: str, operator_id: str = "operator", rejection_reason: str = ""
    ) -> MissionOperationalSession:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        if sess.pending_candidate_envelope is not None:
            cand_ver = sess.pending_candidate_envelope.plan_version
            for h in sess.plan_history:
                if h.plan_version == cand_ver:
                    h.status = "REJECTED_CANDIDATE"
                    if rejection_reason:
                        h.reason = f"{h.reason} | Rejected by {operator_id}: {rejection_reason}"
        sess.pending_candidate_envelope = None
        sess.pending_candidate_config = None
        sess.pending_comparison = None
        sess.workflow_state = (
            MissionWorkflowState.REPLANNING_REQUIRED
            if sess.stale
            else MissionWorkflowState.EXECUTION_NOT_STARTED
        )
        sess.active_envelope.workflow_state = sess.workflow_state.value
        self._save_session(sess)
        return sess

    def get_sensitivity_report(self, mission_id: str) -> MissionSensitivityAnalysisReport:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        return evaluate_mission_sensitivity(
            envelope=sess.active_envelope,
            config=sess.active_config,
        )

    def export_mission_dossier(self, mission_id: str) -> MissionOperationsDossier:
        sess = self.get_session(mission_id)
        if sess is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        sens = self.get_sensitivity_report(mission_id)
        dossier = build_mission_operations_dossier(
            session=sess,
            sensitivity_report=sens,
        )
        sess.active_envelope.dossier_id = dossier.dossier_id
        _atomic_write_json(
            self.storage_dir / f"{mission_id}.dossier.json",
            dossier.model_dump_json(indent=2),
        )
        self._save_session(sess)
        return dossier

    def get_telemetry_state(self, mission_id: Optional[str] = None) -> TelemetryIngestResult:
        return self.telemetry_adapter.get_current_state(mission_id)

    def connect_telemetry_provider(self, provider_id: str) -> TelemetryIngestResult:
        self.telemetry_adapter.connect_provider(provider_id)
        return self.telemetry_adapter.get_current_state()

    def disconnect_telemetry_provider(self) -> TelemetryIngestResult:
        self.telemetry_adapter.disconnect_provider()
        return self.telemetry_adapter.get_current_state()

    def ingest_telemetry_packet(self, packet: TelemetryPacketInput) -> TelemetryIngestResult:
        return self.telemetry_adapter.ingest_packet(packet)

    def get_environmental_context(self, mission_id: str) -> EvaEnvironmentalContextReport:
        env = self.get_mission(mission_id)
        if env is None:
            raise FileNotFoundError(f"Mission '{mission_id}' not found.")
        if env.environmental_context is not None:
            return env.environmental_context
        return evaluate_eva_environmental_context(
            study_region=env.study_region,
            mission_duration_s=env.time_budget.total_required_s,
        )
