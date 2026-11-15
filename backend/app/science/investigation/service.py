"""
MARSCOPE Science Investigation Orchestrator Service
Prompt 17: Unified API orchestrator for Multi-Instrument Registry, Science Questions,
Evidence Discovery, 7-State Target Evaluation, Constrained Multi-Stop Campaign Planning,
Freshness/Staleness Checking, Crew Observation Capture, and Scale-Aware Archive Comparison.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.science.composition.species import list_all_species
from app.science.investigation.campaign import (
    build_science_campaign_plan,
    evaluate_campaign_freshness,
)
from app.science.investigation.evidence_matching import discover_evidence_for_question
from app.science.investigation.eligibility import evaluate_dataset_eligibility
from app.science.investigation.requirements import _classify_dataset_instrument, _select_reference_dtm
from app.science.investigation.measurement_registry import (
    check_inference_validity,
    get_instrument,
    list_instruments,
)
from app.science.investigation.questions import ScienceQuestionRepository
from app.science.investigation.schemas import (
    ArchiveComparisonOutcome,
    CampaignBuildRequest,
    CampaignFreshnessReport,
    CampaignFreshnessState,
    CampaignSummary,
    CustomScienceQuestionCreateRequest,
    InferenceValidationRequest,
    InferenceValidationResponse,
    InstrumentCapabilityRecord,
    IntegratedMissionLifecycleState,
    ObservationArchiveComparison,
    ObservationLifecycleState,
    QuestionEvidenceDiscoveryResponse,
    RecordedFieldObservation,
    RecordObservationRequest,
    ScienceCampaignPlan,
    ScienceQuestionDefinition,
    TargetEvaluationBatchResponse,
    TargetEvaluationRequest,
)
from app.science.investigation.target_evaluation import evaluate_targets_for_question


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


class ScienceInvestigationService:
    """Persistent orchestrator for Prompt 17 Evidence-Driven Science Campaigns."""

    def __init__(
        self,
        *,
        catalog_service: Any,
        target_registry: Any,
        composition_search_service: Any,
        composition_index: Any,
        routing_service: Any,
        evidence_service: Any,
        processed_dir: Path,
        imagery_service: Optional[Any] = None,
        eva_operations_service: Optional[Any] = None,
        morphology_service: Optional[Any] = None,
        spatial_coverage_service: Optional[Any] = None,
        spatial_registration_service: Optional[Any] = None,
    ) -> None:
        self.catalog_service = catalog_service
        self.target_registry = target_registry
        self.composition_search_service = composition_search_service
        self.composition_index = composition_index
        self.routing_service = routing_service
        self.evidence_service = evidence_service
        self.imagery_service = imagery_service
        self.eva_operations_service = eva_operations_service
        self.morphology_service = morphology_service
        self.spatial_coverage_service = spatial_coverage_service
        self.spatial_registration_service = spatial_registration_service
        self.base_dir = Path(processed_dir) / "science_investigation"
        self.campaigns_dir = self.base_dir / "campaigns"
        self.observations_path = self.base_dir / "observations.json"
        self.comparisons_path = self.base_dir / "comparisons.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)
        self.questions_repo = ScienceQuestionRepository(self.base_dir / "questions.json")

    def attach_integration_services(
        self,
        *,
        eva_operations_service: Optional[Any] = None,
        morphology_service: Optional[Any] = None,
        spatial_coverage_service: Optional[Any] = None,
        spatial_registration_service: Optional[Any] = None,
    ) -> None:
        if eva_operations_service is not None:
            self.eva_operations_service = eva_operations_service
        if morphology_service is not None:
            self.morphology_service = morphology_service
        if spatial_coverage_service is not None:
            self.spatial_coverage_service = spatial_coverage_service
        if spatial_registration_service is not None:
            self.spatial_registration_service = spatial_registration_service

    # ── 1. Multi-Instrument Capability Registry ─────────────────────────────────
    def list_instruments(self, *, include_mission_isolated: bool = True) -> List[InstrumentCapabilityRecord]:
        return list_instruments(include_mission_isolated=include_mission_isolated)

    def get_instrument(self, instrument_id: str) -> Optional[InstrumentCapabilityRecord]:
        return get_instrument(instrument_id)

    def validate_inference(self, req: InferenceValidationRequest) -> InferenceValidationResponse:
        return check_inference_validity(req.instrument_id, req.claimed_inference)

    # ── 2. Scientific Questions Repository ──────────────────────────────────────
    def list_questions(self) -> List[ScienceQuestionDefinition]:
        return self.questions_repo.list_questions()

    def get_question(self, question_id: str) -> Optional[ScienceQuestionDefinition]:
        return self.questions_repo.get_question(question_id)

    def create_custom_question(self, req: CustomScienceQuestionCreateRequest) -> ScienceQuestionDefinition:
        return self.questions_repo.create_custom_question(req)

    def delete_custom_question(self, question_id: str) -> bool:
        return self.questions_repo.delete_custom_question(question_id)

    # ── 3. Evidence Discovery & Requirements ────────────────────────────────────
    def discover_evidence_for_question(self, question_id: str) -> QuestionEvidenceDiscoveryResponse:
        q = self.questions_repo.get_question(question_id)
        if q is None:
            raise KeyError(f"Science question '{question_id}' not found.")
        return discover_evidence_for_question(
            question=q,
            catalog_service=self.catalog_service,
            composition_search_service=self.composition_search_service,
            composition_index=self.composition_index,
            imagery_service=self.imagery_service,
        )

    # ── 4. Multi-Instrument Target Evaluation ───────────────────────────────────
    def evaluate_targets(self, req: TargetEvaluationRequest) -> TargetEvaluationBatchResponse:
        q = self.questions_repo.get_question(req.question_id)
        if q is None:
            raise KeyError(f"Science question '{req.question_id}' not found.")
        return evaluate_targets_for_question(
            req=req,
            question=q,
            catalog_service=self.catalog_service,
            target_registry=self.target_registry,
            composition_search_service=self.composition_search_service,
            composition_index=self.composition_index,
            recorded_observations=self.list_observations(),
            morphology_service=self.morphology_service,
            spatial_coverage_service=self.spatial_coverage_service,
        )

    # ── 5. Science Campaign Planning & Freshness ────────────────────────────────
    def build_campaign(self, req: CampaignBuildRequest) -> ScienceCampaignPlan:
        q = self.questions_repo.get_question(req.question_id)
        if q is None:
            raise KeyError(f"Science question '{req.question_id}' not found.")
        prev_plan: Optional[ScienceCampaignPlan] = None
        if req.campaign_id:
            prev_path = self._campaign_path(req.campaign_id)
            if prev_path.exists():
                prev_plan = self._read_campaign_file(prev_path)
                if req.expected_plan_version is not None and prev_plan.plan_version != req.expected_plan_version:
                    raise LookupError(
                        f"Plan version conflict for campaign '{req.campaign_id}': "
                        f"expected v{req.expected_plan_version}, current active is v{prev_plan.plan_version}."
                    )
        plan = build_science_campaign_plan(
            req=req,
            question=q,
            catalog_service=self.catalog_service,
            target_registry=self.target_registry,
            composition_search_service=self.composition_search_service,
            composition_index=self.composition_index,
            imagery_service=self.imagery_service,
            routing_service=self.routing_service,
            evidence_service=self.evidence_service,
            recorded_observations=self.list_observations(),
            eva_operations_service=self.eva_operations_service,
            morphology_service=self.morphology_service,
            spatial_coverage_service=self.spatial_coverage_service,
        )
        if prev_plan is not None:
            plan = plan.model_copy(
                update={
                    "plan_version": prev_plan.plan_version + 1,
                    "operator_approved": False,
                    "hypothesis_reassessments": list(prev_plan.hypothesis_reassessments),
                    "linked_invalidation_events": list(prev_plan.linked_invalidation_events),
                    "lifecycle_transitions": list(prev_plan.lifecycle_transitions)
                    + [
                        {
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "to_state": plan.integrated_lifecycle_state.value,
                            "reason": f"Recomputed campaign v{prev_plan.plan_version + 1} (operator re-approval required)",
                            "operator_approved": False,
                        }
                    ],
                }
            )
        self._save_campaign(plan)
        return plan

    def _campaign_path(self, campaign_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in campaign_id)
        return self.campaigns_dir / f"{safe_id}.json"

    def _read_campaign_file(self, p: Path) -> ScienceCampaignPlan:
        try:
            return ScienceCampaignPlan.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Corrupted persisted science campaign JSON at '{p.name}': {exc}") from exc

    def _save_campaign(self, plan: ScienceCampaignPlan) -> None:
        _atomic_write_json(self._campaign_path(plan.campaign_id), plan.model_dump_json(indent=2))

    def get_campaign(self, campaign_id: str) -> Optional[ScienceCampaignPlan]:
        p = self._campaign_path(campaign_id)
        if not p.exists():
            return None
        plan = self._read_campaign_file(p)
        fresh = self.check_campaign_freshness(campaign_id, plan=plan)
        if fresh.freshness_state != plan.freshness_state or fresh.staleness_reasons:
            plan = plan.model_copy(
                update={
                    "freshness_state": fresh.freshness_state,
                    "staleness_reasons": fresh.staleness_reasons,
                }
            )
        return plan

    def list_campaigns(self) -> List[CampaignSummary]:
        summaries: List[CampaignSummary] = []
        for path in sorted(self.campaigns_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                plan = self._read_campaign_file(path)
                fresh = self.check_campaign_freshness(plan.campaign_id, plan=plan)
                tot_dist: Optional[float] = None
                out_m = plan.outbound_route_summary.get("surface_distance_m")
                ret_m = plan.return_plan.return_surface_distance_m if plan.return_plan else None
                if out_m is not None:
                    tot_dist = round(float(out_m) + (float(ret_m) if ret_m is not None else 0.0), 2)
                tot_dur = plan.eva_envelope.time_budget.total_required_s if plan.eva_envelope else None
                summaries.append(
                    CampaignSummary(
                        campaign_id=plan.campaign_id,
                        campaign_name=plan.campaign_name,
                        question_id=plan.question.question_id,
                        dataset_id=plan.dataset_id,
                        linked_mission_id=plan.linked_mission_id,
                        plan_version=plan.plan_version,
                        integrated_lifecycle_state=plan.integrated_lifecycle_state,
                        operator_approved=plan.operator_approved,
                        plan_status=plan.plan_status,
                        feasibility_state=plan.feasibility_state,
                        freshness_state=fresh.freshness_state,
                        stop_count=len(plan.stop_plans),
                        total_distance_m=tot_dist,
                        total_duration_s=tot_dur,
                        created_at_utc=plan.created_at_utc,
                    )
                )
            except Exception:
                continue
        return summaries

    def check_campaign_freshness(
        self, campaign_id: str, *, plan: Optional[ScienceCampaignPlan] = None
    ) -> CampaignFreshnessReport:
        if plan is None:
            p = self._campaign_path(campaign_id)
            if not p.exists():
                raise KeyError(f"Science campaign '{campaign_id}' not found.")
            plan = self._read_campaign_file(p)
        q = self.questions_repo.get_question(plan.question.question_id)
        rep = evaluate_campaign_freshness(
            plan=plan,
            question=q,
            target_registry=self.target_registry,
            catalog_service=self.catalog_service,
            composition_search_service=self.composition_search_service,
            composition_index=self.composition_index,
            recorded_observations=self.list_observations(),
        )
        pending_inv = [ev for ev in plan.linked_invalidation_events if not ev.get("resolved")]
        if pending_inv:
            extra_reasons = [
                f"[{ev.get('source_type', 'invalidation')}] {ev.get('description', 'Upstream change')}"
                for ev in pending_inv
            ]
            merged = list(dict.fromkeys(list(rep.staleness_reasons) + extra_reasons))
            return CampaignFreshnessReport(
                campaign_id=rep.campaign_id,
                freshness_state=CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED,
                stored_signature=rep.stored_signature,
                current_signature=rep.current_signature,
                staleness_reasons=merged,
            )
        return rep

    def recompute_campaign(
        self, campaign_id: str, *, expected_plan_version: Optional[int] = None
    ) -> ScienceCampaignPlan:
        existing = self.get_campaign(campaign_id)
        if existing is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        if expected_plan_version is not None and existing.plan_version != expected_plan_version:
            raise LookupError(
                f"Plan version conflict for '{campaign_id}': expected v{expected_plan_version}, actual v{existing.plan_version}."
            )
        req = existing.request.model_copy(
            update={"campaign_id": existing.campaign_id, "expected_plan_version": expected_plan_version}
        )
        new_plan = self.build_campaign(req)
        # Mark previously logged invalidation events as resolved in the recomputed baseline
        if new_plan.linked_invalidation_events:
            resolved_evts = [{**e, "resolved": True} for e in new_plan.linked_invalidation_events]
            new_plan = new_plan.model_copy(update={"linked_invalidation_events": resolved_evts})
            self._save_campaign(new_plan)
        return new_plan

    def approve_campaign(
        self,
        campaign_id: str,
        *,
        operator_id: str = "operator",
        note: str = "",
        expected_plan_version: Optional[int] = None,
    ) -> ScienceCampaignPlan:
        plan = self.get_campaign(campaign_id)
        if plan is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        if expected_plan_version is not None and plan.plan_version != expected_plan_version:
            raise LookupError(
                f"Plan version conflict for '{campaign_id}': expected v{expected_plan_version}, actual v{plan.plan_version}."
            )
        fresh = self.check_campaign_freshness(campaign_id, plan=plan)
        if fresh.freshness_state != CampaignFreshnessState.CURRENT:
            raise ValueError(
                f"Cannot approve stale campaign '{campaign_id}': recompute first ({'; '.join(fresh.staleness_reasons)})."
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        transitions = list(plan.lifecycle_transitions) + [
            {
                "timestamp_utc": now_iso,
                "to_state": IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED.value,
                "reason": note or "Operator approved integrated science-to-EVA mission baseline",
                "operator_id": operator_id,
                "operator_approved": True,
            }
        ]
        updated = plan.model_copy(
            update={
                "operator_approved": True,
                "operator_approved_by": operator_id,
                "operator_approved_at_utc": now_iso,
                "operator_approval_note": note,
                "integrated_lifecycle_state": IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED,
                "lifecycle_transitions": transitions,
            }
        )
        self._save_campaign(updated)
        if self.eva_operations_service is not None and updated.linked_mission_id:
            try:
                sess = self.eva_operations_service.get_session(updated.linked_mission_id)
                if sess is not None:
                    sess.integrated_lifecycle_state = IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED.value
                    sess.active_envelope.integrated_lifecycle_state = (
                        IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED.value
                    )
                    self.eva_operations_service._save_session(sess)
            except Exception:
                pass
        return updated

    # ── 6. Observation Capture & Scale-Aware Archive Comparison ──────────────────
    def _load_observations_map(self) -> Dict[str, RecordedFieldObservation]:
        if not self.observations_path.exists():
            return {}
        try:
            raw = json.loads(self.observations_path.read_text(encoding="utf-8"))
            out: Dict[str, RecordedFieldObservation] = {}
            for item in raw:
                obs = RecordedFieldObservation.model_validate(item)
                out[obs.observation_id] = obs
            return out
        except Exception as exc:
            raise ValueError(
                f"Corrupted persisted observations JSON at '{self.observations_path.name}': {exc}"
            ) from exc

    def _save_observations_map(self, obs_map: Dict[str, RecordedFieldObservation]) -> None:
        _atomic_write_json(
            self.observations_path,
            json.dumps([o.model_dump(mode="json") for o in obs_map.values()], indent=2),
        )

    def _load_comparisons_map(self) -> Dict[str, ObservationArchiveComparison]:
        if not self.comparisons_path.exists():
            return {}
        try:
            raw = json.loads(self.comparisons_path.read_text(encoding="utf-8"))
            out: Dict[str, ObservationArchiveComparison] = {}
            for item in raw:
                c = ObservationArchiveComparison.model_validate(item)
                out[c.comparison_id] = c
            return out
        except Exception as exc:
            raise ValueError(
                f"Corrupted persisted archive comparisons JSON at '{self.comparisons_path.name}': {exc}"
            ) from exc

    def _save_comparisons_map(self, cmp_map: Dict[str, ObservationArchiveComparison]) -> None:
        _atomic_write_json(
            self.comparisons_path,
            json.dumps([c.model_dump(mode="json") for c in cmp_map.values()], indent=2),
        )

    def record_observation(self, req: RecordObservationRequest) -> RecordedFieldObservation:
        obs_map = self._load_observations_map()
        if req.campaign_id and req.expected_plan_version is not None:
            plan = self.get_campaign(req.campaign_id)
            if plan is None:
                raise KeyError(f"Science campaign '{req.campaign_id}' not found.")
            if plan.plan_version != req.expected_plan_version:
                raise LookupError(
                    f"Plan version conflict for campaign '{req.campaign_id}': "
                    f"expected v{req.expected_plan_version}, actual v{plan.plan_version}."
                )

        # Idempotency & duplicate submission prevention
        norm_lon = req.longitude_east % 360.0
        for existing in obs_map.values():
            if req.client_submission_id and existing.client_submission_id == req.client_submission_id:
                return existing
            if (
                existing.campaign_id == req.campaign_id
                and existing.target_id == req.target_id
                and existing.instrument_id == req.instrument_id.upper()
                and existing.species_or_feature == req.species_or_feature
                and str(existing.measured_value) == str(req.measured_value)
                and abs(existing.latitude - req.latitude) < 1e-6
                and abs(existing.longitude_east - norm_lon) < 1e-6
                and req.sol_or_timestamp
                and existing.sol_or_timestamp == req.sol_or_timestamp
            ):
                return existing

        now_utc = datetime.now(timezone.utc).isoformat()
        seed = (
            f"{req.instrument_id}|{req.species_or_feature}|{req.latitude:.6f}|"
            f"{req.longitude_east:.6f}|{req.measured_value}|{now_utc}"
        )
        obs_id = "obs_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]

        # Enforce allowed vs prohibited inference check on the entered measurement claim
        inf_check = check_inference_validity(
            req.instrument_id,
            f"{req.measurement_type} {req.species_or_feature}",
        )
        prohib_warn: Optional[str] = None
        if not inf_check.allowed:
            prohib_warn = inf_check.rationale

        val_state = (
            "EVIDENCE_VALIDATED"
            if (req.calibration_metadata and not prohib_warn)
            else "RECORDED_UNVALIDATED"
        )
        obs_lc_state = (
            ObservationLifecycleState.EVIDENCE_VALIDATED
            if val_state == "EVIDENCE_VALIDATED"
            else ObservationLifecycleState.OBSERVATION_RECORDED
        )

        obs = RecordedFieldObservation(
            observation_id=obs_id,
            campaign_id=req.campaign_id,
            stop_id=req.stop_id,
            target_id=req.target_id,
            instrument_id=req.instrument_id.upper(),
            measurement_type=req.measurement_type,
            species_or_feature=req.species_or_feature,
            measured_value=req.measured_value,
            units=req.units,
            latitude=req.latitude,
            longitude_east=norm_lon,
            coordinate_reference=req.coordinate_reference,
            observer_identity=req.observer_identity,
            calibration_metadata=req.calibration_metadata,
            raw_attachment_ref=req.raw_attachment_ref,
            client_submission_id=req.client_submission_id,
            sol_or_timestamp=req.sol_or_timestamp or now_utc,
            notes=req.notes,
            measurement_scale_m=req.measurement_scale_m,
            quality_flag=req.quality_flag,
            validation_state=val_state,
            lifecycle_state=obs_lc_state,
            prohibited_inference_warning=prohib_warn,
            recorded_at_utc=now_utc,
        )
        obs_map[obs_id] = obs
        self._save_observations_map(obs_map)

        # Synchronize campaign observation lifecycle state and notify linked EVA mission session
        if obs.campaign_id:
            p = self._campaign_path(obs.campaign_id)
            if p.exists():
                plan = self._read_campaign_file(p)
                updated_stops = []
                for sp in plan.stop_plans:
                    if (obs.stop_id and sp.stop_id == obs.stop_id) or (obs.target_id and sp.target_id == obs.target_id):
                        sp = sp.model_copy(
                            update={
                                "observation_plan": sp.observation_plan.model_copy(
                                    update={"observation_lifecycle_state": obs_lc_state}
                                )
                            }
                        )
                    updated_stops.append(sp)
                transitions = list(plan.lifecycle_transitions) + [
                    {
                        "timestamp_utc": now_utc,
                        "to_state": IntegratedMissionLifecycleState.FIELD_OBSERVATION.value,
                        "reason": f"Field observation '{obs_id}' captured ({obs.instrument_id}: {obs.species_or_feature})",
                        "operator_id": obs.observer_identity,
                    }
                ]
                plan = plan.model_copy(
                    update={
                        "stop_plans": updated_stops,
                        "integrated_lifecycle_state": IntegratedMissionLifecycleState.FIELD_OBSERVATION,
                        "lifecycle_transitions": transitions,
                    }
                )
                self._save_campaign(plan)
                if self.eva_operations_service is not None and plan.linked_mission_id:
                    try:
                        from app.eva_operations.replanning import MissionEventIngestRequest, MissionEventType

                        self.eva_operations_service.record_mission_event(
                            plan.linked_mission_id,
                            MissionEventIngestRequest(
                                event_type=MissionEventType.FIELD_OBSERVATION_ADDED,
                                operator_id=obs.observer_identity,
                                description=f"Field observation {obs_id} captured for {obs.species_or_feature}",
                                payload={
                                    "observation_id": obs_id,
                                    "target_id": obs.target_id,
                                    "validation_state": obs.validation_state,
                                    "_from_science_service": True,
                                    "client_event_id": f"obs_evt_{obs_id}",
                                },
                            ),
                        )
                    except Exception:
                        pass
        return obs

    def list_observations(
        self, *, campaign_id: Optional[str] = None, target_id: Optional[str] = None
    ) -> List[RecordedFieldObservation]:
        items = list(self._load_observations_map().values())
        if campaign_id:
            items = [o for o in items if o.campaign_id == campaign_id]
        if target_id:
            items = [o for o in items if o.target_id == target_id]
        items.sort(key=lambda o: o.recorded_at_utc, reverse=True)
        return items

    def get_observation(self, observation_id: str) -> Optional[RecordedFieldObservation]:
        return self._load_observations_map().get(observation_id)

    def compare_observation_with_archive(
        self, observation_id: str, *, search_radius_m: float = 150.0
    ) -> ObservationArchiveComparison:
        obs = self.get_observation(observation_id)
        if obs is None:
            raise KeyError(f"Observation '{observation_id}' not found.")

        same_scale_records: List[Dict[str, Any]] = []
        orbital_context: List[Dict[str, Any]] = []
        scale_notes: List[str] = []

        # 1. Inspect co-located NASA PDS records from CompositionSpatialIndex
        if self.composition_index and self.composition_index.get_status().index_available:
            pad_deg = max(0.01, search_radius_m / 59200.0 + 0.005)
            all_sp = [s.canonical_id for s in list_all_species()]
            hits = self.composition_index.query_evidence(
                species_ids=all_sp,
                located_only=True,
                bbox=(
                    obs.latitude - pad_deg,
                    obs.latitude + pad_deg,
                    (obs.longitude_east - pad_deg) % 360.0,
                    (obs.longitude_east + pad_deg) % 360.0,
                ),
            )[:400]

            for ev in hits:
                if ev.latitude is None or ev.longitude_east is None:
                    continue
                d_m = mars_great_circle_distance_meters(
                    obs.latitude, obs.longitude_east, float(ev.latitude), float(ev.longitude_east)
                )
                if d_m > search_radius_m:
                    continue
                ev_inst = str(getattr(ev, "instrument_id", None) or getattr(ev, "instrument", "")).upper()
                sp_name = (
                    getattr(ev, "canonical_species_id", None)
                    or getattr(ev, "canonical_species_name", None)
                    or getattr(ev, "raw_species_name", "")
                )
                val_num = getattr(ev, "normalized_value", None)
                if val_num is None:
                    val_num = getattr(ev, "raw_value", None)
                unit_str = getattr(ev, "normalized_unit", None) or getattr(ev, "raw_unit", None)
                rec_dict = {
                    "evidence_id": ev.evidence_id,
                    "instrument": getattr(ev, "instrument_id", None) or getattr(ev, "instrument", ""),
                    "species": sp_name,
                    "reported_value": val_num,
                    "unit": unit_str,
                    "evidence_type": getattr(ev.evidence_type, "value", str(ev.evidence_type)),
                    "distance_m": round(d_m, 2),
                    "target_name": ev.target_name,
                }
                if ev_inst in {"CRISM", "THEMIS", "MOLA", "HIRISE", "CTX"}:
                    orbital_context.append(rec_dict)
                else:
                    same_scale_records.append(rec_dict)

        # 2. Inspect covering orbital datasets from Catalog
        if self.catalog_service:
            for ds in self.catalog_service.list_datasets():
                if "perseverance" in ds.mission.lower() or "jezero" in ds.id.lower():
                    continue
                cov = ds.coverage
                if not cov:
                    continue
                lon360 = obs.longitude_east % 360.0
                if cov.min_latitude <= obs.latitude <= cov.max_latitude and (
                    (cov.min_longitude % 360.0) <= lon360 <= (cov.max_longitude % 360.0)
                ):
                    if ds.local_file_path or ds.processed_file_path:
                        orbital_context.append(
                            {
                                "dataset_id": ds.id,
                                "instrument": ds.instrument,
                                "resolution_m": ds.horizontal_resolution_meters,
                                "measurement_domain": ds.product_type,
                            }
                        )

        # 3. Classify comparison rigorously respecting measurement scale
        sp_norm = obs.species_or_feature.strip().lower()
        matching_same_species = [
            r
            for r in same_scale_records
            if r["species"].strip().lower() == sp_norm or sp_norm in r["species"].strip().lower()
        ]
        obs_scale = obs.measurement_scale_m
        scale_label = f"~{obs_scale:g} m in-situ spot" if obs_scale is not None else "unspecified spot scale (None)"

        if orbital_context:
            scale_notes.append(
                f"Observation scale ({scale_label}) compared separately from coarse orbital holdings "
                f"({len(orbital_context)} dataset/orbital record(s) at 1 m–463 m scale) to prevent false contradiction."
            )

        numeric_obs: Optional[float] = None
        try:
            numeric_obs = float(obs.measured_value)
        except (TypeError, ValueError):
            numeric_obs = None

        same_vals = [
            float(r["reported_value"])
            for r in matching_same_species
            if r.get("reported_value") is not None
        ]

        value_summary: Dict[str, Any] = {
            "recorded_species": obs.species_or_feature,
            "recorded_value": obs.measured_value,
            "recorded_units": obs.units,
            "same_scale_match_count": len(matching_same_species),
            "same_scale_total_nearby_count": len(same_scale_records),
            "orbital_context_count": len(orbital_context),
        }
        next_steps: List[str] = []

        if matching_same_species and numeric_obs is not None and same_vals:
            mean_val = sum(same_vals) / len(same_vals)
            min_val, max_val = min(same_vals), max(same_vals)
            delta = numeric_obs - mean_val
            value_summary.update(
                {
                    "archive_mean_value": round(mean_val, 3),
                    "archive_min_value": round(min_val, 3),
                    "archive_max_value": round(max_val, 3),
                    "delta_vs_archive_mean": round(delta, 3),
                }
            )
            tol = max(2.5, 0.25 * max(abs(mean_val), 1.0))
            if abs(delta) <= tol:
                outcome = ArchiveComparisonOutcome.CONSISTENT_WITH_ARCHIVE
                explanation = (
                    f"Recorded {obs.instrument_id} measurement ({obs.species_or_feature}={numeric_obs:g} {obs.units}) "
                    f"is consistent with {len(same_vals)} co-located in-situ archive record(s) within {search_radius_m:.0f} m "
                    f"(archive mean {mean_val:.2f}, range {min_val:.2f}..{max_val:.2f})."
                )
                next_steps.append("Promote observation as corroborating field evidence for target campaign synthesis.")
            elif max_val - min_val > max(5.0, 0.5 * max(abs(mean_val), 1.0)):
                outcome = ArchiveComparisonOutcome.CONFLICT_UNRESOLVED
                explanation = (
                    f"Co-located local records for {obs.species_or_feature} already span {min_val:.2f}..{max_val:.2f}, "
                    f"and new measurement ({numeric_obs:g}) remains divergent (mean {mean_val:.2f})."
                )
                next_steps.append("Collect paired micro-texture (MAHLI) and adjacent matrix baseline measurements to isolate vein vs host rock.")
            else:
                outcome = ArchiveComparisonOutcome.DIFFERS_FROM_PRIOR_LOCAL_MEASUREMENT
                scale_desc = f"~{obs_scale:g} m" if obs_scale is not None else "unspecified"
                explanation = (
                    f"Recorded value ({obs.species_or_feature}={numeric_obs:g}) differs from co-located archive mean "
                    f"({mean_val:.2f}) at {scale_desc} rover measurement scale (delta {delta:+.2f})."
                )
                next_steps.append("Run replicate spot measurement and verify LIBS/APXS calibration target offset.")
        elif matching_same_species:
            outcome = ArchiveComparisonOutcome.CONSISTENT_WITH_ARCHIVE
            explanation = (
                f"Co-located local archive matches qualitative species/feature '{obs.species_or_feature}' "
                f"across {len(matching_same_species)} record(s) within {search_radius_m:.0f} m."
            )
            next_steps.append("Verify numeric abundance if quantitative oxide comparison is desired.")
        elif same_scale_records:
            outcome = ArchiveComparisonOutcome.EXTENDS_ARCHIVE_COVERAGE
            explanation = (
                f"Recorded {obs.instrument_id} observation of '{obs.species_or_feature}' extends existing local archive "
                f"coverage ({len(same_scale_records)} nearby in-situ records did not previously report '{obs.species_or_feature}')."
            )
            next_steps.append("Evaluate complementary XRD/SWIR confirmation before classifying novel mineral phases.")
        elif orbital_context:
            outcome = ArchiveComparisonOutcome.DIFFERS_FROM_ORBITAL_SCALE_EXPECTATION
            explanation = (
                f"No same-scale in-situ records exist within {search_radius_m:.0f} m; comparison against orbital context "
                f"({len(orbital_context)} record(s)) cannot refute sub-meter outcrop heterogeneity due to pixel scale disparity."
            )
            next_steps.append("Anchor this spot with repeat in-situ measurements rather than extrapolating to orbital pixel footprint.")
        else:
            outcome = ArchiveComparisonOutcome.NO_CO_LOCATED_ARCHIVE_FOR_COMPARISON
            explanation = (
                f"Zero verified co-located NASA PDS observations or local raster datasets cover "
                f"({obs.latitude:.4f}, {obs.longitude_east:.4f}E) within {search_radius_m:.0f} m."
            )
            next_steps.append("Observation recorded cleanly as uncorroborated field data until archive validation is acquired.")

        cmp_id = "cmp_" + hashlib.sha256(
            f"{observation_id}|{search_radius_m}|{outcome.value}".encode("utf-8")
        ).hexdigest()[:12]
        cmp = ObservationArchiveComparison(
            comparison_id=cmp_id,
            observation_id=observation_id,
            outcome=outcome,
            search_radius_m=search_radius_m,
            same_scale_archive_records=same_scale_records[:25],
            orbital_context_records=orbital_context[:15],
            scale_disparity_notes=scale_notes,
            value_comparison_summary=value_summary,
            explanation=explanation,
            next_verification_steps=next_steps,
        )
        cmp_map = self._load_comparisons_map()
        cmp_map[cmp_id] = cmp
        self._save_comparisons_map(cmp_map)

        # Mark observation as ARCHIVE_COMPARED and execute linked campaign hypothesis reassessment
        obs_map = self._load_observations_map()
        if observation_id in obs_map:
            impact_label = (
                "CONTRADICTS_OR_DIVERGES"
                if outcome
                in {
                    ArchiveComparisonOutcome.DIFFERS_FROM_PRIOR_LOCAL_MEASUREMENT,
                    ArchiveComparisonOutcome.DIFFERS_FROM_ORBITAL_SCALE_EXPECTATION,
                }
                else ("CONSISTENT" if outcome == ArchiveComparisonOutcome.CONSISTENT_WITH_ARCHIVE else "EXTENDS_OR_NEW")
            )
            obs_map[observation_id] = obs_map[observation_id].model_copy(
                update={
                    "lifecycle_state": ObservationLifecycleState.ARCHIVE_COMPARED,
                    "reassessment_impact": impact_label,
                }
            )
            self._save_observations_map(obs_map)
        if obs.campaign_id:
            self._reassess_campaign_after_observation(obs.campaign_id, obs, cmp)

        return cmp

    def _reassess_campaign_after_observation(
        self,
        campaign_id: str,
        obs: RecordedFieldObservation,
        cmp: ObservationArchiveComparison,
    ) -> None:
        p = self._campaign_path(campaign_id)
        if not p.exists():
            return
        plan = self._read_campaign_file(p)
        divergent = cmp.outcome in {
            ArchiveComparisonOutcome.DIFFERS_FROM_PRIOR_LOCAL_MEASUREMENT,
            ArchiveComparisonOutcome.DIFFERS_FROM_ORBITAL_SCALE_EXPECTATION,
        }
        updated_stops = []
        for sp in plan.stop_plans:
            if (obs.stop_id and sp.stop_id == obs.stop_id) or (obs.target_id and sp.target_id == obs.target_id):
                sp = sp.model_copy(
                    update={
                        "observation_plan": sp.observation_plan.model_copy(
                            update={"observation_lifecycle_state": ObservationLifecycleState.ARCHIVE_COMPARED}
                        )
                    }
                )
            updated_stops.append(sp)

        reassess_entry = {
            "reassessment_id": f"reas_{cmp.comparison_id}",
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "observation_id": obs.observation_id,
            "comparison_id": cmp.comparison_id,
            "outcome": cmp.outcome.value,
            "requires_replan": divergent,
            "summary": cmp.explanation,
            "next_verification_steps": cmp.next_verification_steps,
        }
        new_state = (
            IntegratedMissionLifecycleState.REPLAN_IF_REQUIRED
            if divergent
            else IntegratedMissionLifecycleState.HYPOTHESIS_REASSESSMENT
        )
        transitions = list(plan.lifecycle_transitions) + [
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "to_state": new_state.value,
                "reason": f"Archive comparison '{cmp.outcome.value}' on {obs.observation_id}",
            }
        ]
        plan = plan.model_copy(
            update={
                "stop_plans": updated_stops,
                "integrated_lifecycle_state": new_state,
                "hypothesis_reassessments": list(plan.hypothesis_reassessments) + [reassess_entry],
                "lifecycle_transitions": transitions,
            }
        )
        self._save_campaign(plan)
        if self.eva_operations_service is not None and plan.linked_mission_id:
            try:
                sess = self.eva_operations_service.get_session(plan.linked_mission_id)
                if sess is not None:
                    sess.integrated_lifecycle_state = new_state.value
                    sess.active_envelope.integrated_lifecycle_state = new_state.value
                    self.eva_operations_service._save_session(sess)
            except Exception:
                pass

    def handle_eva_session_event(
        self,
        *,
        campaign_id: str,
        mission_id: str,
        event: Any,
    ) -> None:
        p = self._campaign_path(campaign_id)
        if not p.exists():
            return
        plan = self._read_campaign_file(p)
        evt_entry = {
            "event_id": getattr(event, "event_id", None),
            "source_type": "eva_mission_event",
            "mission_id": mission_id,
            "event_type": getattr(getattr(event, "event_type", None), "value", str(getattr(event, "event_type", ""))),
            "description": getattr(event, "description", "EVA mission event"),
            "recorded_at_utc": getattr(event, "recorded_at_utc", datetime.now(timezone.utc).isoformat()),
            "resolved": False,
        }
        updated = plan.model_copy(
            update={
                "freshness_state": CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED,
                "integrated_lifecycle_state": IntegratedMissionLifecycleState.REPLAN_IF_REQUIRED,
                "linked_invalidation_events": list(plan.linked_invalidation_events) + [evt_entry],
                "staleness_reasons": list(
                    dict.fromkeys(
                        list(plan.staleness_reasons)
                        + [f"[EVA {evt_entry['event_type']}] {evt_entry['description']}"]
                    )
                ),
            }
        )
        self._save_campaign(updated)

    def handle_eva_replan_approved(
        self,
        *,
        campaign_id: str,
        mission_id: str,
        plan_version: int,
        operator_id: str,
        approval_note: str = "",
    ) -> None:
        p = self._campaign_path(campaign_id)
        if not p.exists():
            return
        plan = self._read_campaign_file(p)
        resolved = [{**e, "resolved": True} for e in plan.linked_invalidation_events]
        transitions = list(plan.lifecycle_transitions) + [
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "to_state": IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED.value,
                "reason": f"Linked EVA replan v{plan_version} approved by {operator_id}: {approval_note}".strip(),
                "operator_id": operator_id,
                "operator_approved": True,
            }
        ]
        updated = plan.model_copy(
            update={
                "integrated_lifecycle_state": IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED,
                "linked_invalidation_events": resolved,
                "lifecycle_transitions": transitions,
            }
        )
        self._save_campaign(updated)

    def propagate_external_invalidation(
        self,
        *,
        source_type: str,
        description: str,
        dataset_id: Optional[str] = None,
        question_id: Optional[str] = None,
    ) -> List[str]:
        """Propagate upstream catalog/morphology/CRS/question invalidation across affected campaigns & EVA sessions."""
        affected_campaigns: List[str] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for path in self.campaigns_dir.glob("*.json"):
            try:
                plan = self._read_campaign_file(path)
            except ValueError:
                continue
            matches_ds = bool(dataset_id and (plan.dataset_id == dataset_id or dataset_id in plan.provenance_graph.input_datasets))
            matches_q = bool(question_id and plan.question.question_id == question_id)
            if not (matches_ds or matches_q or (dataset_id is None and question_id is None)):
                continue
            evt_entry = {
                "event_id": f"ext_{hashlib.sha256(f'{source_type}|{description}|{now_iso}'.encode()).hexdigest()[:10]}",
                "source_type": source_type,
                "description": description,
                "dataset_id": dataset_id,
                "question_id": question_id,
                "recorded_at_utc": now_iso,
                "resolved": False,
            }
            updated = plan.model_copy(
                update={
                    "freshness_state": CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED,
                    "integrated_lifecycle_state": IntegratedMissionLifecycleState.CAMPAIGN_FRESHNESS_CHECK,
                    "linked_invalidation_events": list(plan.linked_invalidation_events) + [evt_entry],
                    "staleness_reasons": list(
                        dict.fromkeys(list(plan.staleness_reasons) + [f"[{source_type}] {description}"])
                    ),
                }
            )
            self._save_campaign(updated)
            affected_campaigns.append(plan.campaign_id)
            if self.eva_operations_service is not None and plan.linked_mission_id:
                try:
                    from app.eva_operations.replanning import MissionEventIngestRequest, MissionEventType

                    evt_type = (
                        MissionEventType.OBSTACLE_REVIEW_CHANGED
                        if "morphology" in source_type.lower() or "obstacle" in source_type.lower()
                        else MissionEventType.DATASET_UPDATED_OR_REINGESTED
                    )
                    self.eva_operations_service.record_mission_event(
                        plan.linked_mission_id,
                        MissionEventIngestRequest(
                            event_type=evt_type,
                            operator_id="system_orchestrator",
                            description=description,
                            payload={
                                "source_type": source_type,
                                "dataset_id": dataset_id,
                                "_from_science_service": True,
                            },
                        ),
                    )
                except Exception:
                    pass
        return affected_campaigns

    def get_mission_lifecycle_summary(self, campaign_id: str) -> Dict[str, Any]:
        plan = self.get_campaign(campaign_id)
        if plan is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        fresh = self.check_campaign_freshness(campaign_id, plan=plan)
        eva_session = None
        if self.eva_operations_service is not None and plan.linked_mission_id:
            try:
                sess = self.eva_operations_service.get_session(plan.linked_mission_id)
                if sess is not None:
                    eva_session = {
                        "mission_id": sess.mission_id,
                        "workflow_state": sess.workflow_state.value,
                        "active_plan_version": sess.active_plan_version,
                        "stale": sess.stale,
                        "stale_reasons": sess.stale_reasons,
                        "events_count": len(sess.events),
                        "pending_replan": sess.pending_comparison is not None,
                    }
            except Exception:
                eva_session = None
        return {
            "campaign_id": plan.campaign_id,
            "campaign_name": plan.campaign_name,
            "question_id": plan.question.question_id,
            "dataset_id": plan.dataset_id,
            "linked_mission_id": plan.linked_mission_id,
            "plan_version": plan.plan_version,
            "integrated_lifecycle_state": plan.integrated_lifecycle_state.value,
            "operator_approved": plan.operator_approved,
            "operator_approved_by": plan.operator_approved_by,
            "freshness": fresh.model_dump(mode="json"),
            "eva_session": eva_session,
            "stop_observation_states": [
                {
                    "stop_id": sp.stop_id,
                    "target_id": sp.target_id,
                    "observation_lifecycle_state": sp.observation_plan.observation_lifecycle_state.value,
                    "platform_compatibility": sp.observation_plan.platform_compatibility,
                    "platform_mismatch_disclosed": sp.observation_plan.platform_mismatch_disclosed,
                }
                for sp in plan.stop_plans
            ],
            "hypothesis_reassessments": plan.hypothesis_reassessments,
            "lifecycle_transitions": plan.lifecycle_transitions,
            "linked_invalidation_events": plan.linked_invalidation_events,
        }

    def list_comparisons(self, *, observation_id: Optional[str] = None) -> List[ObservationArchiveComparison]:
        items = list(self._load_comparisons_map().values())
        if observation_id:
            items = [c for c in items if c.observation_id == observation_id]
        items.sort(key=lambda c: c.compared_at_utc, reverse=True)
        return items

    def export_campaign_dossier(self, campaign_id: str) -> Dict[str, Any]:
        """Export a self-contained reproducible unified JSON scientific & engineering dossier (Prompt 21 Part 11.2)."""
        plan = self.get_campaign(campaign_id)
        if plan is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        freshness = self.check_campaign_freshness(campaign_id, plan=plan)
        discovery = self.discover_evidence_for_question(plan.question.question_id)
        observations = self.list_observations(campaign_id=campaign_id)
        obs_ids = {o.observation_id for o in observations}
        comparisons = [c for c in self.list_comparisons() if c.observation_id in obs_ids]

        eva_dossier: Optional[Dict[str, Any]] = None
        if self.eva_operations_service is not None and plan.linked_mission_id:
            try:
                eva_dossier = self.eva_operations_service.export_mission_dossier(plan.linked_mission_id).model_dump(mode="json")
            except Exception:
                eva_dossier = None

        morph_reviews: List[Dict[str, Any]] = []
        if self.morphology_service is not None and getattr(self.morphology_service, "review_store", None) is not None:
            try:
                morph_reviews = [r.model_dump(mode="json") for r in self.morphology_service.review_store.load_all().values()]
            except Exception:
                morph_reviews = []

        core_dossier = {
            "dossier_version": "3.0.0-p21",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "operational_safety_certified": False,
            "campaign_id": plan.campaign_id,
            "linked_mission_id": plan.linked_mission_id,
            "plan_version": plan.plan_version,
            "integrated_lifecycle_state": plan.integrated_lifecycle_state.value,
            "operator_approval": {
                "approved": plan.operator_approved,
                "approved_by": plan.operator_approved_by,
                "approved_at_utc": plan.operator_approved_at_utc,
                "approval_note": plan.operator_approval_note,
            },
            "campaign": plan.model_dump(mode="json"),
            "freshness": freshness.model_dump(mode="json"),
            "evidence_discovery": discovery.model_dump(mode="json"),
            "observation_plans": [sp.observation_plan.model_dump(mode="json") for sp in plan.stop_plans],
            "sampling_protocols": [sp.sampling_protocol.model_dump(mode="json") for sp in plan.stop_plans],
            "recorded_field_observations": [o.model_dump(mode="json") for o in observations],
            "archive_comparisons": [c.model_dump(mode="json") for c in comparisons],
            "hypothesis_reassessments": plan.hypothesis_reassessments,
            "eva_operational_dossier": eva_dossier,
            "morphology_human_reviews": morph_reviews,
            "lifecycle_transitions": plan.lifecycle_transitions,
            "linked_invalidation_events": plan.linked_invalidation_events,
            "epistemic_classification": plan.epistemic_classification,
            "uncertainty_and_gaps": plan.uncertainty_and_gaps,
            "missing_inputs": plan.missing_inputs,
            "provenance_graph": plan.provenance_graph.model_dump(mode="json"),
        }
        digest = hashlib.sha256(
            json.dumps(core_dossier, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        core_dossier["sha256_integrity_digest"] = digest
        return core_dossier

    def inspect_product_detail(self, dataset_id: str, *, question_id: str = "gale_boxwork_origin") -> Dict[str, Any]:
        """Return full Prompt 18 product verification, scaling, CRS/registration, and 17-dim eligibility."""
        ds = self.catalog_service.get_dataset(dataset_id) if self.catalog_service else None
        if ds is None:
            raise KeyError(f"Dataset '{dataset_id}' not found.")
        q = self.questions_repo.get_question(question_id)
        if q is None:
            questions = self.questions_repo.list_questions()
            if not questions:
                raise KeyError(f"Science question '{question_id}' not found.")
            q = questions[0]
        is_gale = "gale" in q.study_region.lower() or "sharp" in q.study_region.lower()
        datasets = list(self.catalog_service.list_datasets())
        ref_dtm = _select_reference_dtm(datasets, is_gale)
        inst_cls = _classify_dataset_instrument(ds)
        ev = evaluate_dataset_eligibility(
            ds=ds,
            inst_cls=inst_cls,
            question=q,
            is_gale=is_gale,
            seen_sha256=set(),
            seen_product_ids=set(),
            reference_dtm=ref_dtm,
        )
        return {
            "dataset": ds.model_dump(mode="json"),
            "classified_instrument": inst_cls,
            "question_id": q.question_id,
            "eligibility_state": ev["eligibility_state"].value,
            "evidence_role": ev["evidence_role"].value,
            "evidence_role_rationale": ev["role_reason"],
            "scientific_relevance": ev["scientific_relevance"],
            "eligibility_dimensions": [d.model_dump(mode="json") for d in ev["dimensions"]],
            "spatial_registration_state": ev["registration_state"].value,
            "spatial_registration_report": ev["registration_report"],
            "uncertainty_summary": ev["uncertainty_summary"],
            "provenance_chain": ev["provenance_chain"],
        }
