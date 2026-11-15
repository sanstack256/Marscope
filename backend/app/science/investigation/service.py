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
    CampaignSummary,
    CustomScienceQuestionCreateRequest,
    InferenceValidationRequest,
    InferenceValidationResponse,
    InstrumentCapabilityRecord,
    ObservationArchiveComparison,
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
    ) -> None:
        self.catalog_service = catalog_service
        self.target_registry = target_registry
        self.composition_search_service = composition_search_service
        self.composition_index = composition_index
        self.routing_service = routing_service
        self.evidence_service = evidence_service
        self.imagery_service = imagery_service
        self.base_dir = Path(processed_dir) / "science_investigation"
        self.campaigns_dir = self.base_dir / "campaigns"
        self.observations_path = self.base_dir / "observations.json"
        self.comparisons_path = self.base_dir / "comparisons.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)
        self.questions_repo = ScienceQuestionRepository(self.base_dir / "questions.json")

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
        )

    # ── 5. Science Campaign Planning & Freshness ────────────────────────────────
    def build_campaign(self, req: CampaignBuildRequest) -> ScienceCampaignPlan:
        q = self.questions_repo.get_question(req.question_id)
        if q is None:
            raise KeyError(f"Science question '{req.question_id}' not found.")
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
        )
        self._save_campaign(plan)
        return plan

    def _campaign_path(self, campaign_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in campaign_id)
        return self.campaigns_dir / f"{safe_id}.json"

    def _save_campaign(self, plan: ScienceCampaignPlan) -> None:
        _atomic_write_json(self._campaign_path(plan.campaign_id), plan.model_dump_json(indent=2))

    def get_campaign(self, campaign_id: str) -> Optional[ScienceCampaignPlan]:
        p = self._campaign_path(campaign_id)
        if not p.exists():
            return None
        try:
            plan = ScienceCampaignPlan.model_validate_json(p.read_text(encoding="utf-8"))
            fresh = self.check_campaign_freshness(campaign_id, plan=plan)
            if fresh.freshness_state != plan.freshness_state or fresh.staleness_reasons:
                plan = plan.model_copy(
                    update={
                        "freshness_state": fresh.freshness_state,
                        "staleness_reasons": fresh.staleness_reasons,
                    }
                )
            return plan
        except Exception:
            return None

    def list_campaigns(self) -> List[CampaignSummary]:
        summaries: List[CampaignSummary] = []
        for path in sorted(self.campaigns_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                plan = ScienceCampaignPlan.model_validate_json(path.read_text(encoding="utf-8"))
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
            plan = ScienceCampaignPlan.model_validate_json(p.read_text(encoding="utf-8"))
        q = self.questions_repo.get_question(plan.question.question_id)
        return evaluate_campaign_freshness(
            plan=plan,
            question=q,
            target_registry=self.target_registry,
            catalog_service=self.catalog_service,
            composition_search_service=self.composition_search_service,
            composition_index=self.composition_index,
            recorded_observations=self.list_observations(),
        )

    def recompute_campaign(self, campaign_id: str) -> ScienceCampaignPlan:
        existing = self.get_campaign(campaign_id)
        if existing is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        req = existing.request.model_copy(update={"campaign_id": existing.campaign_id})
        return self.build_campaign(req)

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
        except Exception:
            return {}

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
        except Exception:
            return {}

    def _save_comparisons_map(self, cmp_map: Dict[str, ObservationArchiveComparison]) -> None:
        _atomic_write_json(
            self.comparisons_path,
            json.dumps([c.model_dump(mode="json") for c in cmp_map.values()], indent=2),
        )

    def record_observation(self, req: RecordObservationRequest) -> RecordedFieldObservation:
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

        scale_m = req.measurement_scale_m

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
            longitude_east=req.longitude_east % 360.0,
            sol_or_timestamp=req.sol_or_timestamp or now_utc,
            notes=req.notes,
            measurement_scale_m=scale_m,
            quality_flag=req.quality_flag,
            prohibited_inference_warning=prohib_warn,
            recorded_at_utc=now_utc,
        )
        obs_map = self._load_observations_map()
        obs_map[obs_id] = obs
        self._save_observations_map(obs_map)
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
        return cmp

    def list_comparisons(self, *, observation_id: Optional[str] = None) -> List[ObservationArchiveComparison]:
        items = list(self._load_comparisons_map().values())
        if observation_id:
            items = [c for c in items if c.observation_id == observation_id]
        items.sort(key=lambda c: c.compared_at_utc, reverse=True)
        return items

    def export_campaign_dossier(self, campaign_id: str) -> Dict[str, Any]:
        """Export a self-contained reproducible JSON scientific & engineering dossier."""
        plan = self.get_campaign(campaign_id)
        if plan is None:
            raise KeyError(f"Science campaign '{campaign_id}' not found.")
        freshness = self.check_campaign_freshness(campaign_id, plan=plan)
        discovery = self.discover_evidence_for_question(plan.question.question_id)
        observations = self.list_observations(campaign_id=campaign_id)
        obs_ids = {o.observation_id for o in observations}
        comparisons = [c for c in self.list_comparisons() if c.observation_id in obs_ids]
        return {
            "dossier_version": "2.0.0-p18",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "operational_safety_certified": False,
            "campaign": plan.model_dump(mode="json"),
            "freshness": freshness.model_dump(mode="json"),
            "evidence_discovery": discovery.model_dump(mode="json"),
            "recorded_field_observations": [o.model_dump(mode="json") for o in observations],
            "archive_comparisons": [c.model_dump(mode="json") for c in comparisons],
        }

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
