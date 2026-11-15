"""
MARSCOPE Executable Science Campaign & Terrain-Routed Traverse Planner
Prompt 17: Builds constrained multi-stop Marswalk science plans over genuine
terrain grids, independent return planning, EVA envelopes, alternative trade-offs,
and dependency-signature freshness verification (CURRENT / STALE).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.eva_operations.constraints import evaluate_eva_constraints
from app.eva_operations.energy_budget import evaluate_eva_energy_budget
from app.eva_operations.locomotion import LocomotionModelCategory
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.return_planning import plan_eva_return_route
from app.eva_operations.route_schedule import build_eva_schedule
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    EvaMissionEnvelopeResponse,
    MissionConfigRequest,
)
from app.eva_operations.time_budget import evaluate_eva_time_budget
from app.eva_operations.uncertainty import summarize_eva_uncertainties
from app.evidence_intelligence.schemas import CacheValidityState, CorridorAssessRequest
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.routing.graph import RoutePlanningError
from app.routing.models import UnknownTerrainPolicy
from app.routing.schemas import RouteComputeRequest, RouteCoordinateInput, RouteObjective, RoutingMode
from app.science.investigation.observation_plan import build_observation_action_plan
from app.science.investigation.requirements import evaluate_question_requirements
from app.science.investigation.sampling_plan import build_sampling_protocol
from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignFeasibilityModelState,
    CampaignFreshnessReport,
    CampaignFreshnessState,
    CampaignPlanStatus,
    CampaignRouteCandidate,
    CampaignStopPlan,
    CandidateTargetEvaluation,
    IntegratedMissionLifecycleState,
    RequirementFulfillmentState,
    ScienceCampaignPlan,
    ScienceQuestionDefinition,
    TargetEvaluationRequest,
)
from app.science.investigation.target_evaluation import evaluate_targets_for_question
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)


def _artifact_fingerprint(path_str: Optional[str], catalog_service: Any = None) -> Optional[Dict[str, Any]]:
    if not path_str:
        return None
    p: Optional[Path] = None
    if catalog_service is not None and hasattr(catalog_service, "_resolve_path"):
        p = catalog_service._resolve_path(path_str)
    else:
        p = Path(path_str)
    if p is None or not p.exists() or not p.is_file():
        return {"path": str(path_str), "exists": False}
    st = p.stat()
    info: Dict[str, Any] = {"path": str(p.name), "exists": True, "size_bytes": st.st_size}
    # Full SHA-256 directly for companion labels / manifests / format files <= 10 MB
    if st.st_size <= 10 * 1024 * 1024:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        info["sha256"] = h.hexdigest()
    else:
        info["mtime_ns"] = st.st_mtime_ns
    return info


def compute_dependency_snapshot_and_hash(
    *,
    req: CampaignBuildRequest,
    question: ScienceQuestionDefinition,
    selected_targets: List[CandidateTargetEvaluation],
    catalog_service: Any,
    composition_index: Any,
    recorded_observations: Optional[List[Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Compute a reproducible snapshot + SHA-256 signature tracking raw PDS artifacts,
    companion labels/manifests, processed DEM + .processing.json, composition index
    generation & manifest digest, science question, targets, field observations,
    and transformation algorithm version.
    """
    ds = catalog_service.get_dataset(req.dataset_id) if catalog_service else None
    comp_st = composition_index.get_status() if composition_index else None

    proc_manifest_fp: Optional[Dict[str, Any]] = None
    if ds and ds.processed_file_path and catalog_service and hasattr(catalog_service, "_resolve_path"):
        proc_p = catalog_service._resolve_path(ds.processed_file_path)
        if proc_p is not None:
            cand_json = proc_p.with_name(f"{req.dataset_id}.processing.json")
            if cand_json.exists():
                proc_manifest_fp = _artifact_fingerprint(str(cand_json), None)

    target_ids_set = {t.target_id for t in selected_targets}
    relevant_obs = []
    for obs in (recorded_observations or []):
        tid = getattr(obs, "target_id", None)
        cid = getattr(obs, "campaign_id", None)
        near = False
        if selected_targets and getattr(obs, "latitude", None) is not None and getattr(obs, "longitude_east", None) is not None:
            for t in selected_targets:
                if mars_great_circle_distance_meters(t.latitude, t.longitude_east, float(obs.latitude), float(obs.longitude_east)) <= 500.0:
                    near = True
                    break
        if (tid and tid in target_ids_set) or (req.campaign_id and cid == req.campaign_id) or near:
            relevant_obs.append(
                {
                    "observation_id": getattr(obs, "observation_id", ""),
                    "species": getattr(obs, "species_or_feature", ""),
                    "measured_value": str(getattr(obs, "measured_value", "")),
                    "quality_flag": getattr(obs, "quality_flag", ""),
                }
            )
    relevant_obs.sort(key=lambda o: o["observation_id"])

    morph_fp: Optional[Dict[str, Any]] = None
    if catalog_service and getattr(catalog_service, "catalog_storage_dir", None):
        morph_path = Path(catalog_service.catalog_storage_dir).parent / "processed" / "morphology" / "reviews.json"
        if morph_path.exists():
            morph_fp = _artifact_fingerprint(str(morph_path), None)

    snapshot: Dict[str, Any] = {
        "schema_version": "2.2.0-p22",
        "physics_and_model": {
            "software_version": "2.2.0-p22",
            "algorithm_version": "2.0.0-p18",
            "mars_gravity_mps2": 3.72076,
            "locomotion_category": req.locomotion_category,
            "unknown_terrain_policy": req.unknown_terrain_policy,
            "confirm_default_policies": req.confirm_default_policies,
        },
        "dataset": {
            "dataset_id": req.dataset_id,
            "status": ds.status.value if ds else "missing",
            "sha256": ds.sha256_checksum if ds else None,
            "crs": ds.coordinate_reference_system if ds else None,
            "horizontal_resolution_meters": ds.horizontal_resolution_meters if ds else None,
            "raw_file": _artifact_fingerprint(ds.local_file_path, catalog_service) if ds else None,
            "label_file": _artifact_fingerprint(ds.local_label_path, catalog_service) if ds else None,
            "processed_file": _artifact_fingerprint(ds.processed_file_path, catalog_service) if ds else None,
            "processing_manifest": proc_manifest_fp,
        },
        "morphology_reviews": morph_fp,
        "composition_index": {
            "active_generation_id": getattr(comp_st, "active_generation_id", None) if comp_st else None,
            "source_artifact_digest": getattr(comp_st, "source_artifact_digest", None) if comp_st else None,
            "complete_manifest_digest": getattr(comp_st, "complete_manifest_digest", None) if comp_st else None,
            "checksum_valid": getattr(comp_st, "checksum_valid", None) if comp_st else None,
            "crism_status": getattr(comp_st, "crism_status", None) if comp_st else None,
        },
        "question": {
            "question_id": question.question_id,
            "title": question.title,
            "hypothesis": question.hypothesis,
            "target_phenomena": question.target_phenomena,
            "spec_ids": [s.requirement_id for s in question.required_measurement_specs],
        },
        "targets": [
            {
                "target_id": t.target_id,
                "lat": round(t.latitude, 7),
                "lon": round(t.longitude_east, 7),
                "evidence_state": t.evidence_state.value,
                "evidence_ids": sorted(t.evidence_ids),
                "local_observation_count": t.local_observation_count,
            }
            for t in sorted(selected_targets, key=lambda item: item.target_id)
        ],
        "recorded_observations": relevant_obs,
        "mission_params": {
            "start": req.start.model_dump(mode="json"),
            "destination": req.destination.model_dump(mode="json") if req.destination else None,
            "routing_mode": req.routing_mode.value,
            "constraints": req.constraints.model_dump(mode="json"),
            "walking_speed_mps": req.walking_speed_mps,
            "use_tobler_grade_approximation": req.use_tobler_grade_approximation,
            "mission_duration_limit_s": req.mission_duration_limit_s,
            "return_reserve_fraction": req.return_reserve_fraction,
            "stop_dwell_seconds": req.stop_dwell_seconds,
            "default_stop_dwell_s": req.default_stop_dwell_s,
            "astronaut_suit_mass_kg": req.astronaut_suit_mass_kg,
            "payload_mass_kg": req.payload_mass_kg,
            "resources": [r.model_dump(mode="json") for r in req.resources],
        },
    }
    digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest, snapshot


def evaluate_campaign_freshness(
    *,
    plan: ScienceCampaignPlan,
    question: Optional[ScienceQuestionDefinition],
    target_registry: Any,
    catalog_service: Any,
    composition_search_service: Any,
    composition_index: Any,
    recorded_observations: List[Any],
) -> CampaignFreshnessReport:
    """Re-evaluate upstream dataset, index, question, observations, and target dependencies."""
    reasons: List[str] = []
    if question is None:
        reasons.append(f"Science question '{plan.question.question_id}' was deleted or modified.")
        return CampaignFreshnessReport(
            campaign_id=plan.campaign_id,
            freshness_state=CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED,
            stored_signature=plan.dependency_signature,
            current_signature="question_missing",
            staleness_reasons=reasons,
        )

    stored_target_ids = [sp.target_id for sp in plan.stop_plans]
    current_evals: List[CandidateTargetEvaluation] = []
    if stored_target_ids:
        batch = evaluate_targets_for_question(
            req=TargetEvaluationRequest(
                question_id=question.question_id,
                target_ids=stored_target_ids,
                include_discovered_candidates=True,
                astronaut_latitude=plan.request.start.lat,
                astronaut_longitude=plan.request.start.lon_east,
                max_candidates=max(12, len(stored_target_ids) + 4),
            ),
            question=question,
            catalog_service=catalog_service,
            target_registry=target_registry,
            composition_search_service=composition_search_service,
            composition_index=composition_index,
            recorded_observations=recorded_observations,
        )
        by_id = {t.target_id: t for t in batch.targets}
        for sp in plan.stop_plans:
            if sp.target_id in by_id:
                current_evals.append(by_id[sp.target_id])
            else:
                current_evals = list(plan.request.candidate_targets)
                break

    current_hash, current_snap = compute_dependency_snapshot_and_hash(
        req=plan.request.model_copy(update={"candidate_targets": current_evals or plan.request.candidate_targets}),
        question=question,
        selected_targets=current_evals or plan.request.candidate_targets,
        catalog_service=catalog_service,
        composition_index=composition_index,
        recorded_observations=recorded_observations,
    )

    old_snap = plan.dependency_snapshot or {}
    if old_snap.get("physics_and_model") != current_snap.get("physics_and_model"):
        reasons.append("Algorithm version, Mars gravity/physics constant, locomotion category, or unknown-terrain policy changed.")
    if old_snap.get("morphology_reviews") != current_snap.get("morphology_reviews"):
        reasons.append("Operator morphology obstacle review ledger changed.")
    if old_snap.get("dataset") != current_snap.get("dataset"):
        reasons.append("Upstream terrain dataset status, CRS/resolution, raw/label SHA-256, or processed DEM artifact changed.")
    if old_snap.get("composition_index") != current_snap.get("composition_index"):
        reasons.append("Composition spatial index generation, manifest digest, checksum, or CRISM status changed.")
    if old_snap.get("question") != current_snap.get("question"):
        reasons.append("Science question definition or required measurement specs changed.")
    if old_snap.get("targets") != current_snap.get("targets"):
        reasons.append("Target observation counts, evidence state, or coordinates changed since plan creation.")
    if old_snap.get("recorded_observations") != current_snap.get("recorded_observations"):
        reasons.append("New or modified field observations affect planned targets or campaign provenance.")

    stale = bool(reasons) or (current_hash != plan.dependency_signature)
    return CampaignFreshnessReport(
        campaign_id=plan.campaign_id,
        freshness_state=(
            CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED
            if stale
            else CampaignFreshnessState.CURRENT
        ),
        stored_signature=plan.dependency_signature,
        current_signature=current_hash,
        staleness_reasons=reasons,
    )


def _greedy_nn_order(
    start: RouteCoordinateInput,
    stops: List[CandidateTargetEvaluation],
) -> List[CandidateTargetEvaluation]:
    remaining = list(stops)
    ordered: List[CandidateTargetEvaluation] = []
    cur_lat, cur_lon = start.lat, start.lon_east
    while remaining:
        best_idx = min(
            range(len(remaining)),
            key=lambda i: mars_great_circle_distance_meters(
                cur_lat, cur_lon, remaining[i].latitude, remaining[i].longitude_east
            ),
        )
        chosen = remaining.pop(best_idx)
        ordered.append(chosen)
        cur_lat, cur_lon = chosen.latitude, chosen.longitude_east
    return ordered


def _run_route_and_eva_for_stops(
    *,
    label: str,
    objective: str,
    mode: RoutingMode,
    start: RouteCoordinateInput,
    explicit_destination: Optional[RouteCoordinateInput],
    ordered_stops: List[CandidateTargetEvaluation],
    dwell_map: Dict[str, float],
    req: CampaignBuildRequest,
    routing_service: Any,
    evidence_service: Any,
    eva_operations_service: Optional[Any] = None,
    campaign_id: Optional[str] = None,
    question_id: Optional[str] = None,
    register_session: bool = False,
) -> Tuple[
    CampaignRouteCandidate,
    Optional[Any],
    Optional[Any],
    Optional[EvaMissionEnvelopeResponse],
]:
    if explicit_destination is not None:
        dest_coord = explicit_destination
        waypoint_coords = [
            RouteCoordinateInput(
                lat=s.latitude,
                lon_east=s.longitude_east,
                label=s.name,
                target_id=s.target_id,
            )
            for s in ordered_stops
        ]
    elif ordered_stops:
        last = ordered_stops[-1]
        dest_coord = RouteCoordinateInput(
            lat=last.latitude,
            lon_east=last.longitude_east,
            label=last.name,
            target_id=last.target_id,
        )
        waypoint_coords = [
            RouteCoordinateInput(
                lat=s.latitude,
                lon_east=s.longitude_east,
                label=s.name,
                target_id=s.target_id,
            )
            for s in ordered_stops[:-1]
        ]
    else:
        raise ValueError("Cannot route campaign without at least one target stop or destination.")

    total_dwell_s = sum(dwell_map.get(s.target_id, req.default_stop_dwell_s) for s in ordered_stops)
    try:
        unk_policy = UnknownTerrainPolicy(req.unknown_terrain_policy)
    except Exception:
        unk_policy = UnknownTerrainPolicy.EXCLUDE_UNKNOWN
    out_constraints = req.constraints.model_copy(
        update={
            "walking_speed_m_per_s": req.walking_speed_mps,
            "return_to_start": False,
            "optimize_target_order": req.optimize_stop_order and len(waypoint_coords) > 1,
            "unknown_terrain_policy": unk_policy,
            "operator_unknown_override_reason": req.operator_unknown_override_reason,
        }
    )

    alt_id = f"camp_alt_{mode.value}_{len(ordered_stops)}"
    mode_to_route_obj = {
        RoutingMode.CONSERVATIVE: RouteObjective.LOWEST_SLOPE,
        RoutingMode.SCIENCE_PRIORITY: RouteObjective.SCIENCE_CORRIDOR,
        RoutingMode.BALANCED: RouteObjective.BALANCED_MULTIOBJECTIVE,
    }
    route_obj = mode_to_route_obj.get(mode, RouteObjective.BALANCED_MULTIOBJECTIVE)
    try:
        route = routing_service.compute_route(
            RouteComputeRequest(
                dataset_id=req.dataset_id,
                start=start,
                destination=dest_coord,
                waypoints=waypoint_coords,
                target_ids=[],
                mode=mode,
                objective=route_obj,
                constraints=out_constraints,
            )
        )
    except RoutePlanningError as exc:
        cand = CampaignRouteCandidate(
            alternative_id=alt_id,
            label=label,
            objective=objective,
            routing_mode=mode,
            stop_order_ids=[s.target_id for s in ordered_stops],
            science_dwell_s=total_dwell_s,
            feasible_within_constraints=False,
            scientific_coverage_summary=f"{len(ordered_stops)} planned stop(s)",
            explanation=f"Outbound multi-stop routing failed under configured slope/terrain limits: {exc}",
            failure_reason=str(exc),
        )
        return cand, None, None, None

    usable_s = (
        round(req.mission_duration_limit_s * (1.0 - req.return_reserve_fraction), 1)
        if (req.mission_duration_limit_s is not None and req.return_reserve_fraction is not None)
        else None
    )
    try:
        corridor = evidence_service.assess_corridor(
            CorridorAssessRequest(
                dataset_id=req.dataset_id,
                start=start,
                destination=dest_coord,
                route=route,
                mode=mode,
                selected_target_ids=[s.target_id for s in ordered_stops],
                constraints=out_constraints,
            )
        )
    except ValueError as exc:
        cand = CampaignRouteCandidate(
            alternative_id=alt_id,
            label=label,
            objective=objective,
            routing_mode=mode,
            stop_order_ids=[s.target_id for s in ordered_stops],
            science_dwell_s=total_dwell_s,
            feasible_within_constraints=False,
            scientific_coverage_summary=f"{len(ordered_stops)} planned stop(s)",
            explanation=f"Corridor evidence assessment unavailable outside processed DEM bounds: {exc}",
            failure_reason=str(exc),
        )
        return cand, None, None, None

    stop_dwell_dict = {
        s.target_id: float(dwell_map.get(s.target_id, req.default_stop_dwell_s))
        for s in ordered_stops
    }
    loco_cat = None
    if req.locomotion_category:
        try:
            loco_cat = LocomotionModelCategory(req.locomotion_category)
        except Exception:
            loco_cat = None

    mission_id_for_camp = f"eva_{campaign_id}" if (register_session and campaign_id) else f"eva_{alt_id}"
    cfg = MissionConfigRequest(
        mission_id=mission_id_for_camp,
        mission_name=req.campaign_name,
        dataset_id=req.dataset_id,
        start=start,
        destination=dest_coord,
        mode=mode,
        selected_target_ids=[s.target_id for s in ordered_stops],
        constraints=out_constraints,
        walking_speed_mps=req.walking_speed_mps,
        use_tobler_grade_approximation=req.use_tobler_grade_approximation,
        locomotion_category=loco_cat,
        unknown_terrain_policy=unk_policy,
        operator_unknown_override_reason=req.operator_unknown_override_reason,
        confirm_default_policies=req.confirm_default_policies,
        mission_duration_limit_s=req.mission_duration_limit_s,
        return_reserve_fraction=req.return_reserve_fraction,
        operational_overhead_s=req.operational_overhead_s,
        stop_dwell_seconds=stop_dwell_dict,
        astronaut_suit_mass_kg=req.astronaut_suit_mass_kg,
        payload_mass_kg=req.payload_mass_kg,
        resources=req.resources,
        linked_campaign_id=campaign_id,
        linked_question_id=question_id,
    )

    if eva_operations_service is not None:
        eva_env = eva_operations_service.evaluate_precomputed_route_envelope(
            config=cfg,
            route=route,
            corridor=corridor,
            register_session=register_session,
            integrated_lifecycle_state=IntegratedMissionLifecycleState.EVA_OPERATIONAL_EVALUATION.value,
        )
        return_plan = eva_env.return_plan
        time_budget = eva_env.time_budget
        energy_budget = eva_env.energy_budget
        env_status = eva_env.envelope_status
    else:
        return_plan = plan_eva_return_route(
            routing_service=routing_service,
            dataset_id=req.dataset_id,
            outbound_route=route,
            walking_speed_mps=req.walking_speed_mps,
            use_tobler_grade_approximation=req.use_tobler_grade_approximation,
            stop_dwell_total_s=total_dwell_s,
            operational_overhead_s=req.operational_overhead_s,
            usable_budget_s=usable_s,
            compute_reverse_return_route=True,
        )
        out_const_s = (
            round(route.total_surface_distance_m / req.walking_speed_mps, 1)
            if (req.walking_speed_mps and req.walking_speed_mps > 0)
            else None
        )
        time_budget = evaluate_eva_time_budget(
            outbound_constant_s=out_const_s,
            outbound_tobler_s=route.estimated_duration_seconds,
            return_constant_s=return_plan.return_duration_constant_s,
            return_tobler_s=return_plan.return_duration_tobler_s,
            return_route_computed=return_plan.return_route_computed,
            stop_dwell_seconds=stop_dwell_dict,
            operational_overhead_s=req.operational_overhead_s,
            walking_speed_mps=req.walking_speed_mps,
            use_tobler_grade_approximation=req.use_tobler_grade_approximation,
            mission_duration_limit_s=req.mission_duration_limit_s,
            return_reserve_fraction=req.return_reserve_fraction,
        )
        energy_budget = evaluate_eva_energy_budget(
            outbound_climb_gain_m=route.total_elevation_gain_m,
            outbound_descent_loss_m=route.total_elevation_loss_m,
            return_climb_gain_m=return_plan.return_elevation_gain_m,
            return_descent_loss_m=return_plan.return_elevation_loss_m,
            astronaut_suit_mass_kg=req.astronaut_suit_mass_kg,
            payload_mass_kg=req.payload_mass_kg,
        )
        resource_budget = evaluate_eva_resource_budget(
            resources=req.resources,
            exposure_duration_s=time_budget.total_required_s,
        )
        schedule = build_eva_schedule(
            corridor=corridor,
            return_plan=return_plan,
            walking_speed_mps=req.walking_speed_mps,
            use_tobler_grade_approximation=req.use_tobler_grade_approximation,
            stop_dwell_seconds=stop_dwell_dict,
            operational_overhead_s=req.operational_overhead_s,
            surface_weight_n=energy_budget.surface_weight_n,
        )
        constraints = evaluate_eva_constraints(
            config=cfg,
            route=route,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
            resource_budget=resource_budget,
        )
        any_fail = any(c.status == "FAIL" for c in constraints)
        if any_fail:
            env_status = EnvelopeFeasibilityStatus.EXCEEDS_CONFIGURED_CONSTRAINTS
        elif time_budget.available and energy_budget.available:
            env_status = EnvelopeFeasibilityStatus.FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS
        else:
            env_status = EnvelopeFeasibilityStatus.INCOMPLETE_USER_CONSTRAINTS
        uncertainties, limitations = summarize_eva_uncertainties(
            config=cfg,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
        )
        missing_inputs = list(
            dict.fromkeys(
                time_budget.missing_inputs + energy_budget.missing_inputs + resource_budget.missing_inputs
            )
        )
        eva_env = EvaMissionEnvelopeResponse(
            mission_id=cfg.mission_id or alt_id,
            mission_name=cfg.mission_name,
            study_region=cfg.study_region,
            dataset_id=cfg.dataset_id,
            source_product_id=route.source_product_id,
            route_id=route.route_id,
            assessment_id=corridor.assessment_id,
            linked_campaign_id=campaign_id,
            linked_question_id=question_id,
            envelope_status=env_status,
            operational_safety_certified=False,
            missing_inputs=missing_inputs,
            config=cfg,
            outbound_summary={
                "horizontal_distance_m": route.total_horizontal_distance_m,
                "surface_distance_m": route.total_surface_distance_m,
                "elevation_gain_m": route.total_elevation_gain_m,
                "elevation_loss_m": route.total_elevation_loss_m,
                "max_slope_deg": route.max_slope_deg,
                "mean_slope_deg": route.mean_slope_deg,
            },
            time_budget=time_budget,
            energy_budget=energy_budget,
            resource_budget=resource_budget,
            return_plan=return_plan,
            schedule=schedule,
            constraints=constraints,
            uncertainty_notes=uncertainties,
            limitations=limitations,
            cache_validity=CacheValidityState.CURRENT,
            provenance_graph=ProvenanceDependencyGraph(
                output_id=cfg.mission_id or alt_id,
                classification=ScientificDataClassification.MARSCOPE_DERIVED,
                input_datasets=[req.dataset_id],
                input_product_ids=[route.source_product_id],
                input_variables=["multi_stop_route", "return_route", "eva_constraints"],
                method="campaign_eva_envelope_v2",
                algorithm_version="2.0.0-p18",
                validation_state="analytical_planning_envelope_not_safety_certified",
            ),
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            compute_time_ms=0.0,
        )

    feasible_flag: Optional[bool]
    if env_status == EnvelopeFeasibilityStatus.EXCEEDS_CONFIGURED_CONSTRAINTS or not return_plan.return_route_computed:
        feasible_flag = False
    elif env_status == EnvelopeFeasibilityStatus.FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS:
        feasible_flag = True
    else:
        feasible_flag = None

    ret_dur = (
        return_plan.return_duration_tobler_s
        if req.use_tobler_grade_approximation
        else return_plan.return_duration_constant_s
    )
    out_dur = time_budget.outbound_travel_s
    cand = CampaignRouteCandidate(
        alternative_id=alt_id,
        label=label,
        objective=objective,
        routing_mode=mode,
        stop_order_ids=[s.target_id for s in ordered_stops],
        outbound_route_id=route.route_id,
        outbound_distance_m=route.total_surface_distance_m,
        outbound_elevation_gain_m=route.total_elevation_gain_m,
        max_slope_deg=route.max_slope_deg,
        outbound_duration_s=out_dur,
        science_dwell_s=total_dwell_s,
        return_route_computed=return_plan.return_route_computed,
        return_distance_m=return_plan.return_surface_distance_m,
        return_duration_s=ret_dur,
        total_duration_s=time_budget.total_required_s,
        total_climb_work_j=energy_budget.total_positive_climb_work_j,
        feasible_within_constraints=feasible_flag,
        scientific_coverage_summary=(
            f"{len(ordered_stops)} stop(s) | "
            f"{sum(1 for s in ordered_stops if s.evidence_state.value == 'confirmed_local_observation')} confirmed local"
        ),
        explanation=(
            f"Multi-stop {mode.value} traverse ({route.total_surface_distance_m:.1f} m outbound + "
            f"{return_plan.return_surface_distance_m:.1f} m independent return, max slope {route.max_slope_deg:.1f} deg). "
            f"EVA status: {env_status.value}."
        ),
    )
    return cand, route, return_plan, eva_env


def build_science_campaign_plan(
    *,
    req: CampaignBuildRequest,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    target_registry: Any,
    composition_search_service: Any,
    composition_index: Any,
    imagery_service: Optional[Any],
    routing_service: Any,
    evidence_service: Any,
    recorded_observations: List[Any],
    eva_operations_service: Optional[Any] = None,
    morphology_service: Optional[Any] = None,
    spatial_coverage_service: Optional[Any] = None,
) -> ScienceCampaignPlan:
    t0 = time.perf_counter()

    req_evals = evaluate_question_requirements(
        question=question,
        catalog_service=catalog_service,
        composition_index=composition_index,
        imagery_service=imagery_service,
    )

    # Resolve target evaluations (never invent stops when both candidate_targets and selected_target_ids are empty)
    if req.candidate_targets:
        if req.selected_target_ids:
            by_id = {t.target_id: t for t in req.candidate_targets}
            selected_evals = [by_id[tid] for tid in req.selected_target_ids if tid in by_id]
        else:
            selected_evals = list(req.candidate_targets)
    elif req.selected_target_ids:
        eval_batch = evaluate_targets_for_question(
            req=TargetEvaluationRequest(
                question_id=question.question_id,
                target_ids=req.selected_target_ids,
                include_discovered_candidates=True,
                astronaut_latitude=req.start.lat,
                astronaut_longitude=req.start.lon_east,
                max_candidates=max(12, len(req.selected_target_ids) + 4),
            ),
            question=question,
            catalog_service=catalog_service,
            target_registry=target_registry,
            composition_search_service=composition_search_service,
            composition_index=composition_index,
            recorded_observations=recorded_observations,
            morphology_service=morphology_service,
            spatial_coverage_service=spatial_coverage_service,
        )
        by_id = {t.target_id: t for t in eval_batch.targets}
        selected_evals = [by_id[tid] for tid in req.selected_target_ids if tid in by_id]
    else:
        selected_evals = []

    dep_sig, dep_snap = compute_dependency_snapshot_and_hash(
        req=req,
        question=question,
        selected_targets=selected_evals,
        catalog_service=catalog_service,
        composition_index=composition_index,
        recorded_observations=recorded_observations,
    )
    campaign_id = req.campaign_id or ("camp_" + dep_sig[:12])

    # Guard empty targets AND empty destination -> cannot invent waypoints
    if not selected_evals and req.destination is None:
        return ScienceCampaignPlan(
            campaign_id=campaign_id,
            campaign_name=req.campaign_name,
            question=question,
            dataset_id=req.dataset_id,
            study_region=question.study_region,
            plan_status=CampaignPlanStatus.DATA_INSUFFICIENT,
            feasibility_state=CampaignFeasibilityModelState.BLOCKED_BY_UNKNOWN_INPUTS,
            freshness_state=CampaignFreshnessState.CURRENT,
            dependency_signature=dep_sig,
            dependency_snapshot=dep_snap,
            constraint_evaluation_complete=False,
            evaluated_inputs_and_constraints={
                "max_slope_deg": req.constraints.max_slope_deg,
                "walking_speed_mps": req.walking_speed_mps,
                "mission_duration_limit_s": req.mission_duration_limit_s,
                "return_reserve_fraction": req.return_reserve_fraction,
                "resources_count": len(req.resources),
                "targets_selected": 0,
                "explicit_destination_supplied": False,
            },
            epistemic_classification={
                ScientificDataClassification.DIRECTLY_MEASURED.value: [],
                ScientificDataClassification.MARSCOPE_DERIVED.value: [],
                ScientificDataClassification.MODELLED.value: [],
                ScientificDataClassification.USER_ASSUMED.value: [
                    f"max_slope_deg={req.constraints.max_slope_deg}",
                ],
                ScientificDataClassification.UNVERIFIED.value: [],
                ScientificDataClassification.UNAVAILABLE.value: ["target_stops", "destination_coordinate"],
            },
            request=req,
            requirements_evaluation=req_evals,
            missing_inputs=["No verified targets or explicit destination coordinates selected."],
            uncertainty_and_gaps=[
                "MARSCOPE never fabricates investigation waypoints when both target selection and destination are absent."
            ],
            provenance_graph=ProvenanceDependencyGraph(
                output_id=campaign_id,
                classification=ScientificDataClassification.UNAVAILABLE,
                input_datasets=[req.dataset_id],
                method="campaign_build_v2",
                algorithm_version="2.0.0-p18",
                validation_state="data_insufficient_no_targets",
            ),
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    ordered_stops = _greedy_nn_order(req.start, selected_evals) if req.optimize_stop_order else list(selected_evals)
    dwell_map: Dict[str, float] = {
        t.target_id: float(req.stop_dwell_seconds.get(t.target_id, req.default_stop_dwell_s))
        for t in ordered_stops
    }

    stop_plans: List[CampaignStopPlan] = []
    for idx, tgt in enumerate(ordered_stops):
        stop_id = f"stop_{idx + 1}_{tgt.target_id}"
        dwell_val = float(req.stop_dwell_seconds.get(stop_id, dwell_map[tgt.target_id]))
        dwell_map[tgt.target_id] = dwell_val
        obs_plan = build_observation_action_plan(
            stop_id=stop_id,
            target=tgt,
            question=question,
            requirements=req_evals,
            dwell_s=dwell_val,
        )
        samp_proto = build_sampling_protocol(
            stop_id=stop_id,
            target=tgt,
            question=question,
        )
        stop_plans.append(
            CampaignStopPlan(
                stop_index=idx + 1,
                stop_id=stop_id,
                target_id=tgt.target_id,
                name=tgt.name,
                latitude=tgt.latitude,
                longitude_east=tgt.longitude_east,
                evidence_state=tgt.evidence_state,
                dwell_s=dwell_val,
                heuristic_priority_score=tgt.heuristic_priority_score,
                known_summary=tgt.known_facts[:3],
                unknown_summary=tgt.unknowns_and_gaps[:3],
                observation_plan=obs_plan,
                sampling_protocol=samp_proto,
            )
        )

    primary_cand, primary_route, return_plan, eva_env = _run_route_and_eva_for_stops(
        label=f"Primary ({req.routing_mode.value})",
        objective="Selected Science Campaign Route",
        mode=req.routing_mode,
        start=req.start,
        explicit_destination=req.destination,
        ordered_stops=ordered_stops,
        dwell_map=dwell_map,
        req=req,
        routing_service=routing_service,
        evidence_service=evidence_service,
        eva_operations_service=eva_operations_service,
        campaign_id=campaign_id,
        question_id=question.question_id,
        register_session=True,
    )

    alternatives: List[CampaignRouteCandidate] = [primary_cand]
    if req.include_alternatives and ordered_stops:
        alt_specs: List[Tuple[str, str, RoutingMode, List[CandidateTargetEvaluation]]] = []
        if req.routing_mode != RoutingMode.CONSERVATIVE:
            alt_specs.append(
                ("Conservative Hazard-Averse Corridor", "Minimize slope/uncertainty exposure across all stops", RoutingMode.CONSERVATIVE, ordered_stops)
            )
        if len(ordered_stops) >= 2:
            subset = sorted(ordered_stops, key=lambda s: -(s.heuristic_priority_score or 0.0))[: max(1, len(ordered_stops) - 1)]
            subset_nn = _greedy_nn_order(req.start, subset)
            alt_specs.append(
                ("Time-Saving High-Priority Subset", "Reduced stop count focusing on highest-priority stop(s) if budget is tight", RoutingMode.SCIENCE_PRIORITY, subset_nn)
            )
        for lbl, obj, md, stops_sub in alt_specs:
            alt_c, _, _, _ = _run_route_and_eva_for_stops(
                label=lbl,
                objective=obj,
                mode=md,
                start=req.start,
                explicit_destination=req.destination,
                ordered_stops=stops_sub,
                dwell_map=dwell_map,
                req=req,
                routing_service=routing_service,
                evidence_service=evidence_service,
                eva_operations_service=eva_operations_service,
                campaign_id=campaign_id,
                question_id=question.question_id,
                register_session=False,
            )
            alternatives.append(alt_c)

    essential_missing = any(
        r.essential
        and r.fulfillment_state
        in {
            RequirementFulfillmentState.MISSING_REQUIRED_DATA,
            RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE,
        }
        for r in req_evals
    )
    missing_list = eva_env.missing_inputs if eva_env else ["walking_speed_mps", "mission_duration_limit_s"]
    if (
        primary_route is None
        or return_plan is None
        or not return_plan.return_route_computed
        or (eva_env and eva_env.envelope_status == EnvelopeFeasibilityStatus.EXCEEDS_CONFIGURED_CONSTRAINTS)
    ):
        plan_status = CampaignPlanStatus.INFEASIBLE_UNDER_CONFIGURED_CONSTRAINTS if False else CampaignPlanStatus.INFEASIBLE_UNDER_CONSTRAINTS
        feasibility_state = CampaignFeasibilityModelState.INFEASIBLE_UNDER_CONFIGURED_MODEL
        constraint_complete = eva_env is not None and not missing_list
    elif missing_list or (eva_env and eva_env.envelope_status == EnvelopeFeasibilityStatus.INCOMPLETE_USER_CONSTRAINTS):
        plan_status = CampaignPlanStatus.PARTIAL_MISSING_OBSERVATIONS if essential_missing or primary_cand.feasible_within_constraints is None else CampaignPlanStatus.COMPLETE_CONSTRAINED_PLAN
        feasibility_state = CampaignFeasibilityModelState.INCOMPLETE_CONSTRAINT_EVALUATION
        constraint_complete = False
    elif essential_missing:
        plan_status = CampaignPlanStatus.PARTIAL_MISSING_OBSERVATIONS
        feasibility_state = CampaignFeasibilityModelState.FEASIBLE_UNDER_CONFIGURED_MODEL
        constraint_complete = True
    else:
        plan_status = CampaignPlanStatus.COMPLETE_CONSTRAINED_PLAN
        feasibility_state = CampaignFeasibilityModelState.FEASIBLE_UNDER_CONFIGURED_MODEL
        constraint_complete = True

    evaluated_inputs = {
        "max_slope_deg": req.constraints.max_slope_deg,
        "routing_mode": req.routing_mode.value,
        "walking_speed_mps": req.walking_speed_mps,
        "use_tobler_grade_approximation": req.use_tobler_grade_approximation,
        "mission_duration_limit_s": req.mission_duration_limit_s,
        "return_reserve_fraction": req.return_reserve_fraction,
        "astronaut_suit_mass_kg": req.astronaut_suit_mass_kg,
        "payload_mass_kg": req.payload_mass_kg,
        "resources_configured": [r.resource_name for r in req.resources],
        "independent_return_route_computed": bool(return_plan and return_plan.return_route_computed),
        "constraint_excluded_alternatives": [
            a.label for a in alternatives if a.feasible_within_constraints is False
        ],
    }
    unverified_targets = [
        s.name for s in ordered_stops
        if s.evidence_state.value in {"optical_morphology_candidate_unverified", "manual_waypoint_unverified", "conflicting_evidence"}
    ]
    marscope_derived_items = [
        "outbound_surface_distance_and_elevation_gain" if primary_route else "route_computation_failed",
        "independent_reverse_dijkstra_return_path" if (return_plan and return_plan.return_route_computed) else "return_path_unavailable",
        "corridor_slope_and_tri_roughness",
    ]
    modelled_items = [
        "tobler_grade_duration" if req.use_tobler_grade_approximation else "constant_walking_speed_duration",
        "mechanical_climb_work_energy_budget" if (eva_env and eva_env.energy_budget.available) else "energy_budget_uncomputed",
    ]
    user_assumed_items = [
        f"max_slope_deg={req.constraints.max_slope_deg}",
        f"default_stop_dwell_s={req.default_stop_dwell_s}",
        f"unknown_terrain_policy={req.unknown_terrain_policy}",
        *( [f"walking_speed_mps={req.walking_speed_mps}"] if req.walking_speed_mps is not None else [] ),
        *( [f"mission_duration_limit_s={req.mission_duration_limit_s}"] if req.mission_duration_limit_s is not None else [] ),
        *( [f"return_reserve_fraction={req.return_reserve_fraction}"] if req.return_reserve_fraction is not None else [] ),
    ]
    unavail_items = list(dict.fromkeys(missing_list + ["stop_data_volume_mb (no telemetry bitrate configured)"]))
    epistemic_cls = {
        ScientificDataClassification.DIRECTLY_MEASURED.value: [
            s.target_id for s in ordered_stops if s.evidence_state.value == "confirmed_local_observation"
        ],
        ScientificDataClassification.ARCHIVE_DERIVED.value: [
            s.target_id for s in ordered_stops if s.local_observation_count > 0
        ] if all(hasattr(s, "local_observation_count") for s in ordered_stops) else [],
        ScientificDataClassification.MARSCOPE_DERIVED.value: marscope_derived_items,
        ScientificDataClassification.MODELLED.value: modelled_items,
        ScientificDataClassification.USER_ASSUMED.value: user_assumed_items,
        ScientificDataClassification.UNAVAILABLE.value: unavail_items,
        ScientificDataClassification.UNVERIFIED.value: unverified_targets,
    }

    uncertainty_and_gaps: List[str] = []
    for r in req_evals:
        if r.fulfillment_state != RequirementFulfillmentState.SATISFIED_DIRECT:
            uncertainty_and_gaps.extend(r.limitations_and_gaps)
    if eva_env:
        uncertainty_and_gaps.extend(eva_env.uncertainty_notes)
        uncertainty_and_gaps.extend(eva_env.limitations)
    if primary_cand.failure_reason:
        uncertainty_and_gaps.append(f"Route feasibility block: {primary_cand.failure_reason}")

    justifications: List[str] = [
        f"Campaign designed to investigate '{question.title}' across {len(stop_plans)} terrain-routed stop(s).",
        "Stop selection and sequencing separate confirmed local observations from unverified optical/manual candidates.",
        f"Primary route calculated over actual HiRISE/DEM cell topology ({req.routing_mode.value} policy, max slope {req.constraints.max_slope_deg:.1f} deg) paired with independent reverse-Dijkstra return checks.",
    ]
    if essential_missing:
        justifications.append(
            "Explicitly flagged PARTIAL_MISSING_OBSERVATIONS because regional CRISM/CheMin mineral confirmation remains unestablished in local archives."
        )

    out_vertices = (
        [
            {"lat": v.lat, "lon_east": v.lon_east, "elevation_m": v.elevation_m, "slope_deg": v.slope_deg}
            for v in primary_route.vertices
        ]
        if primary_route is not None
        else []
    )
    out_summary = (
        {
            "horizontal_distance_m": primary_route.total_horizontal_distance_m,
            "surface_distance_m": primary_route.total_surface_distance_m,
            "elevation_gain_m": primary_route.total_elevation_gain_m,
            "elevation_loss_m": primary_route.total_elevation_loss_m,
            "max_slope_deg": primary_route.max_slope_deg,
            "mean_slope_deg": primary_route.mean_slope_deg,
            "source_product_id": primary_route.source_product_id,
        }
        if primary_route is not None
        else {}
    )

    lifecycle_state = (
        IntegratedMissionLifecycleState.MISSION_REVIEW
        if (eva_env is not None and constraint_complete)
        else IntegratedMissionLifecycleState.EVA_OPERATIONAL_EVALUATION
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    if eva_env is not None:
        eva_env.integrated_lifecycle_state = lifecycle_state.value
        if eva_operations_service is not None:
            try:
                sess = eva_operations_service.get_session(eva_env.mission_id)
                if sess is not None:
                    sess.integrated_lifecycle_state = lifecycle_state.value
                    sess.active_envelope.integrated_lifecycle_state = lifecycle_state.value
                    eva_operations_service._save_session(sess)
            except Exception:
                pass

    return ScienceCampaignPlan(
        campaign_id=campaign_id,
        campaign_name=req.campaign_name,
        linked_mission_id=eva_env.mission_id if eva_env else None,
        plan_version=1,
        integrated_lifecycle_state=lifecycle_state,
        operator_approved=False,
        lifecycle_transitions=[
            {
                "timestamp_utc": now_iso,
                "to_state": lifecycle_state.value,
                "reason": "Initial integrated science-to-EVA campaign build completed",
                "operator_approved": False,
            }
        ],
        question=question,
        dataset_id=req.dataset_id,
        study_region=question.study_region,
        plan_status=plan_status,
        feasibility_state=feasibility_state,
        freshness_state=CampaignFreshnessState.CURRENT,
        dependency_signature=dep_sig,
        dependency_snapshot=dep_snap,
        evaluated_inputs_and_constraints=evaluated_inputs,
        epistemic_classification=epistemic_cls,
        constraint_evaluation_complete=constraint_complete,
        operational_safety_certified=False,
        request=req,
        requirements_evaluation=req_evals,
        stop_plans=stop_plans,
        outbound_route_id=primary_route.route_id if primary_route else None,
        outbound_route_summary=out_summary,
        outbound_vertices=out_vertices,
        return_plan=return_plan,
        eva_envelope=eva_env,
        alternatives=alternatives,
        missing_inputs=eva_env.missing_inputs if eva_env else ["walking_speed_mps", "mission_duration_limit_s"],
        uncertainty_and_gaps=list(dict.fromkeys(uncertainty_and_gaps)),
        decision_justification=justifications,
        provenance_graph=ProvenanceDependencyGraph(
            output_id=campaign_id,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[req.dataset_id],
            input_product_ids=[primary_route.source_product_id] if primary_route else [],
            input_variables=["science_question", "target_evaluations", "dem_corridor", "eva_constraints"],
            method="executable_science_campaign_planner_v2",
            algorithm_version="2.0.0-p18",
            parameters={
                "question_id": question.question_id,
                "routing_mode": req.routing_mode.value,
                "stop_count": len(stop_plans),
                "dependency_signature": dep_sig,
            },
            assumptions=list(dict.fromkeys(uncertainty_and_gaps))[:10],
            intermediate_steps=[
                ProvenanceStep(
                    step_id="sci_eval",
                    label="7-State Evidence & Question Requirement Mapping",
                    classification=ScientificDataClassification.ARCHIVE_DERIVED,
                    input_ids=[question.question_id],
                    method="target_registry_plus_composition_index_audit",
                    algorithm_version="2.0.0-p18",
                    output_variable="evaluated_stops",
                ),
                ProvenanceStep(
                    step_id="sci_route_eva",
                    label="Multi-Stop Terrain Routing & Independent Return Envelope",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[req.dataset_id, *(s.target_id for s in stop_plans)],
                    method="terrain_astar_plus_reverse_dijkstra_eva",
                    algorithm_version="2.0.0-p18",
                    output_variable="campaign_plan",
                    output_units="m_and_s",
                ),
            ],
            validation_state="research_and_planning_decision_support_not_safety_certified",
        ),
        compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
    )
