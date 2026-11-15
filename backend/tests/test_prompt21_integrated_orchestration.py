"""
Prompt 21 — Integrated Science-to-Mission Orchestration, End-to-End Unification
& Loose-End Closure Verification Suite (Parts 19.1, 19.2, 19.3).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.eva_operations as api_eva
import app.api.science_investigation as api_si
import app.services.container as container_mod
from app.eva_operations.mission import EvaOperationsService
from app.eva_operations.replanning import MissionWorkflowState
from app.main import app
from app.routing.schemas import RouteCoordinateInput
from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignFreshnessState,
    CampaignPlanStatus,
    IntegratedMissionLifecycleState,
    ObservationLifecycleState,
    RecordObservationRequest,
    TargetEvaluationRequest,
)
from app.science.investigation.service import ScienceInvestigationService
from app.science.provenance_graph import ScientificDataClassification
from app.services.container import (
    catalog_service,
    composition_index,
    composition_search_service,
    imagery_service,
    morphology_service,
    routing_service,
    science_investigation_service as live_si_service,
    spatial_coverage_service,
    spatial_registration_service,
    target_registry,
)


@pytest.fixture()
def isolated_orchestration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ScienceInvestigationService, EvaOperationsService]:
    """Isolated ScienceInvestigationService + EvaOperationsService wired bidirectionally in tmp_path."""
    eva_svc = EvaOperationsService(
        routing_service=routing_service,
        evidence_service=live_si_service.evidence_service,
        processed_dir=tmp_path,
    )
    si_svc = ScienceInvestigationService(
        catalog_service=catalog_service,
        target_registry=target_registry,
        composition_search_service=composition_search_service,
        composition_index=composition_index,
        routing_service=routing_service,
        evidence_service=live_si_service.evidence_service,
        processed_dir=tmp_path,
        imagery_service=imagery_service,
    )
    si_svc.attach_integration_services(
        eva_operations_service=eva_svc,
        morphology_service=morphology_service,
        spatial_coverage_service=spatial_coverage_service,
        spatial_registration_service=spatial_registration_service,
    )
    eva_svc.attach_science_service(si_svc)

    monkeypatch.setattr(api_si, "science_investigation_service", si_svc)
    monkeypatch.setattr(api_eva, "eva_operations_service", eva_svc)
    monkeypatch.setattr(container_mod, "science_investigation_service", si_svc)
    return si_svc, eva_svc


# =============================================================================
# 19.1 FULL END-TO-END INTEGRATED ORCHESTRATION WORKFLOW TEST
# =============================================================================


@pytest.mark.asyncio
async def test_end_to_end_science_to_mission_orchestration_workflow(
    isolated_orchestration: tuple[ScienceInvestigationService, EvaOperationsService],
):
    si_svc, eva_svc = isolated_orchestration
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Discover evidence for Gale boxwork question
        r_disc = await client.get("/api/science-investigation/questions/gale_boxwork_origin/discover-evidence")
        assert r_disc.status_code == 200
        disc = r_disc.json()
        assert disc["question"]["question_id"] == "gale_boxwork_origin"
        assert any(
            req["requirement_id"] == "req_boxwork_mineral_xrd"
            for req in disc["requirements_evaluation"]
        )

        # 2. Evaluate real Gale targets inside processed HiRISE DEM bounds
        r_targs = await client.post(
            "/api/science-investigation/targets/evaluate",
            json={
                "question_id": "gale_boxwork_origin",
                "include_discovered_candidates": True,
                "study_bounds": {
                    "min_lat": -4.752,
                    "max_lat": -4.706,
                    "min_lon": 137.386,
                    "max_lon": 137.433,
                },
                "max_candidates": 6,
            },
        )
        assert r_targs.status_code == 200
        targs_body = r_targs.json()
        assert len(targs_body["targets"]) >= 2
        t0 = targs_body["targets"][0]
        # Prompt 19/21 enrichment verified from real HiRISE raster without fake values
        assert t0["terrain_elevation_m"] is not None
        assert t0["terrain_slope_deg"] is not None
        assert t0["spatial_coverage_category"] in {
            "MULTI_SENSOR_CO_REGISTERED",
            "DEM_ONLY",
            "REGIONAL_LOW_RESOLUTION_ONLY",
            "UNOBSERVED",
        }
        assert t0["scientific_confidence_score"] is None
        assert t0["prioritization_is_heuristic"] is True

        chosen = targs_body["targets"][:2]
        start_coord = {
            "lat": chosen[0]["latitude"] + 0.0008,
            "lon_east": chosen[0]["longitude_east"] - 0.0008,
            "label": "EVA Base",
        }

        # 3. Build integrated campaign linked directly to single Prompt 20 EVA engine
        r_build = await client.post(
            "/api/science-investigation/campaigns/build",
            json={
                "campaign_name": "P21 Integrated Gale Traverse",
                "question_id": "gale_boxwork_origin",
                "dataset_id": "hirise_dteec_009149_1750",
                "start": start_coord,
                "selected_target_ids": [c["target_id"] for c in chosen],
                "walking_speed_mps": 0.75,
                "mission_duration_limit_s": 14400.0,
                "return_reserve_fraction": 0.25,
                "astronaut_suit_mass_kg": 130.0,
                "payload_mass_kg": 12.0,
                "resources": [
                    {
                        "resource_name": "oxygen_kg",
                        "initial_quantity": 4.0,
                        "unit": "kg",
                        "consumption_rate": 0.25,
                        "rate_unit": "kg/h",
                        "reserve_fraction": 0.2,
                    }
                ],
                "include_alternatives": True,
            },
        )
        assert r_build.status_code == 200
        plan = r_build.json()
        cid = plan["campaign_id"]
        mid = plan["linked_mission_id"]
        assert mid is not None
        assert plan["eva_envelope"] is not None
        assert plan["eva_envelope"]["mission_id"] == mid
        assert plan["operational_safety_certified"] is False
        assert plan["integrated_lifecycle_state"] in {
            IntegratedMissionLifecycleState.EVA_OPERATIONAL_EVALUATION.value,
            IntegratedMissionLifecycleState.MISSION_REVIEW.value,
        }
        assert plan["operator_approved"] is False

        # Platform compatibility mismatch honestly disclosed for MSL rover instruments
        obs_plan_0 = plan["stop_plans"][0]["observation_plan"]
        assert obs_plan_0["observation_lifecycle_state"] == ObservationLifecycleState.OBSERVATION_PLANNED.value
        assert obs_plan_0["platform_mismatch_disclosed"] is True
        assert "MSL" in obs_plan_0["platform_disclosure_note"] or "rover" in obs_plan_0["platform_disclosure_note"].lower()

        # Verify EvaOperationsService holds matching linked session
        r_sess = await client.get(f"/api/eva-operations/mission/{mid}/session")
        assert r_sess.status_code == 200
        sess = r_sess.json()
        assert sess["linked_campaign_id"] == cid
        assert sess["linked_question_id"] == "gale_boxwork_origin"

        # 4. Operator approval updates integrated lifecycle cleanly
        r_approve = await client.post(
            f"/api/science-investigation/campaigns/{cid}/approve",
            json={"operator_id": "flight_director", "note": "Verified boxwork terrain and EVA reserve margin"},
        )
        assert r_approve.status_code == 200
        approved_plan = r_approve.json()
        assert approved_plan["operator_approved"] is True
        assert approved_plan["operator_approved_by"] == "flight_director"
        assert approved_plan["integrated_lifecycle_state"] in {
            IntegratedMissionLifecycleState.OPERATOR_APPROVAL.value,
            IntegratedMissionLifecycleState.EXECUTION_NOT_STARTED.value,
        }

        # 5. Unified lifecycle endpoint reports linked EVA + Science states
        r_lc = await client.get(f"/api/science-investigation/campaigns/{cid}/lifecycle")
        assert r_lc.status_code == 200
        lc = r_lc.json()
        assert lc["campaign_id"] == cid
        assert lc["linked_mission_id"] == mid
        assert lc["eva_session"]["mission_id"] == mid
        assert lc["operator_approved"] is True

        # 6. Crew field observation capture (with idempotent client_submission_id)
        obs_payload = {
            "campaign_id": cid,
            "stop_id": plan["stop_plans"][0]["stop_id"],
            "target_id": chosen[0]["target_id"],
            "instrument_id": "CHEMCAM_LIBS",
            "measurement_type": "elemental_oxide_wt_pct",
            "species_or_feature": "SO3",
            "measured_value": 16.2,
            "units": "wt%",
            "latitude": chosen[0]["latitude"],
            "longitude_east": chosen[0]["longitude_east"],
            "coordinate_reference": "IAU2000:49900",
            "observer_identity": "crew_geologist_1",
            "calibration_metadata": "Ti-alloy plate LIBS calibration verified prior to traverse",
            "client_submission_id": "sub-p21-obs-001",
            "expected_plan_version": 1,
        }
        r_obs1 = await client.post("/api/science-investigation/observations", json=obs_payload)
        assert r_obs1.status_code == 201
        obs1 = r_obs1.json()
        oid = obs1["observation_id"]

        # Duplicate client_submission_id must return exact same observation idempotently
        r_obs2 = await client.post("/api/science-investigation/observations", json=obs_payload)
        assert r_obs2.status_code == 201
        assert r_obs2.json()["observation_id"] == oid

        # 7. Archive comparison records hypothesis reassessment & campaign staleness
        r_cmp = await client.post(
            f"/api/science-investigation/observations/{oid}/compare?search_radius_m=500"
        )
        assert r_cmp.status_code == 200

        r_camp_after_cmp = await client.get(f"/api/science-investigation/campaigns/{cid}")
        assert r_camp_after_cmp.status_code == 200
        camp_after_cmp = r_camp_after_cmp.json()
        assert len(camp_after_cmp["hypothesis_reassessments"]) >= 1
        assert camp_after_cmp["freshness_state"] == CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED.value

        # 8. EVA hazard event propagates invalidation back to linked Science Campaign
        r_evt = await client.post(
            f"/api/eva-operations/mission/{mid}/events",
            json={
                "event_type": "HAZARD_MARKED_BY_OPERATOR",
                "operator_id": "eva_lead",
                "description": "Unmapped fracture escarpment along leg 1 corridor",
                "payload": {"client_event_id": "evt-p21-001", "lat": chosen[0]["latitude"]},
            },
        )
        assert r_evt.status_code == 200
        # Duplicate client_event_id is idempotent (event count stays equal to r_evt)
        r_evt_dup = await client.post(
            f"/api/eva-operations/mission/{mid}/events",
            json={
                "event_type": "HAZARD_MARKED_BY_OPERATOR",
                "operator_id": "eva_lead",
                "description": "Unmapped fracture escarpment along leg 1 corridor",
                "payload": {"client_event_id": "evt-p21-001", "lat": chosen[0]["latitude"]},
            },
        )
        assert r_evt_dup.status_code == 200
        assert len(r_evt_dup.json()["events"]) == len(r_evt.json()["events"]) == 2

        r_camp_after_evt = await client.get(f"/api/science-investigation/campaigns/{cid}")
        assert r_camp_after_evt.status_code == 200
        camp_after_evt = r_camp_after_evt.json()
        assert camp_after_evt["integrated_lifecycle_state"] == IntegratedMissionLifecycleState.REPLAN_IF_REQUIRED.value
        assert any(
            e.get("source_type") == "eva_mission_event" and e.get("event_type") == "HAZARD_MARKED_BY_OPERATOR"
            for e in camp_after_evt["linked_invalidation_events"]
        )

        # 9. Recompute science campaign restores CURRENT freshness and increments plan_version
        r_recomp = await client.post(f"/api/science-investigation/campaigns/{cid}/recompute")
        assert r_recomp.status_code == 200
        recomp = r_recomp.json()
        assert recomp["freshness_state"] == CampaignFreshnessState.CURRENT.value
        assert recomp["plan_version"] == 2
        assert recomp["linked_mission_id"] is not None

        # 10. Unified Prompt 21 dossier export includes SHA-256 digest & cross-domain records
        r_ud = await client.get(f"/api/science-investigation/campaigns/{cid}/unified-dossier")
        assert r_ud.status_code == 200
        ud = r_ud.json()
        assert ud["dossier_version"] == "3.0.0-p21"
        assert ud["operational_safety_certified"] is False
        assert len(ud["sha256_integrity_digest"]) == 64
        assert ud["eva_operational_dossier"] is not None
        assert len(ud["recorded_field_observations"]) >= 1
        assert len(ud["archive_comparisons"]) >= 1
        assert len(ud["lifecycle_transitions"]) >= 3


# =============================================================================
# 19.2 CROSS-MODULE CONSISTENCY TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_cross_module_single_eva_engine_and_epistemic_consistency(
    isolated_orchestration: tuple[ScienceInvestigationService, EvaOperationsService],
):
    si_svc, eva_svc = isolated_orchestration
    batch = si_svc.evaluate_targets(
        TargetEvaluationRequest(
            question_id="gale_boxwork_origin",
            study_bounds={"min_lat": -4.752, "max_lat": -4.706, "min_lon": 137.386, "max_lon": 137.433},
            max_candidates=4,
        )
    )
    chosen = batch.targets[:2]
    plan = si_svc.build_campaign(
        CampaignBuildRequest(
            campaign_name="Cross-Module Consistency Check",
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=chosen[0].latitude + 0.0007, lon_east=chosen[0].longitude_east - 0.0007),
            selected_target_ids=[c.target_id for c in chosen],
            walking_speed_mps=0.8,
            mission_duration_limit_s=12000.0,
            return_reserve_fraction=0.25,
        )
    )
    assert plan.linked_mission_id is not None
    sess = eva_svc.get_session(plan.linked_mission_id)
    assert sess is not None

    # Exact identity between campaign EVA envelope and standalone EVA session active envelope
    assert plan.eva_envelope.time_budget.total_required_s == sess.active_envelope.time_budget.total_required_s
    assert plan.eva_envelope.outbound_summary == sess.active_envelope.outbound_summary
    assert plan.eva_envelope.traversability_analytics.get("unmeasured_soil_properties") is not None

    # Canonical epistemic classification keys only (matching ScientificDataClassification)
    valid_keys = {k.value for k in ScientificDataClassification}
    assert set(plan.epistemic_classification.keys()).issubset(valid_keys)

    # XRD/CRISM requirement remains explicitly unsatisfied / missing
    crism_reqs = [r for r in plan.requirements_evaluation if r.requirement_id == "req_boxwork_mineral_xrd"]
    assert crism_reqs and (
        "missing" in crism_reqs[0].fulfillment_state.value.lower()
        or "cannot_be_verified" in crism_reqs[0].fulfillment_state.value.lower()
        or "partial" in crism_reqs[0].fulfillment_state.value.lower()
    )


# =============================================================================
# 19.3 ADVERSARIAL FAILURE, AUTH & CORRUPTION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_adversarial_corruption_version_conflict_and_auth_fail_closed(
    isolated_orchestration: tuple[ScienceInvestigationService, EvaOperationsService],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    si_svc, eva_svc = isolated_orchestration
    # 1. Corrupted JSON persistence refuses silent wipe and raises ValueError
    si_svc.observations_path.write_text("{CORRUPT_JSON", encoding="utf-8")
    with pytest.raises(ValueError, match=r"(?i)corrupted"):
        si_svc._load_observations_map()
    # Restore empty clean store for HTTP tests below
    si_svc.observations_path.write_text("[]", encoding="utf-8")

    # 2. EVA corrupted session refuses silent fallback
    bad_sess = eva_svc.storage_dir / "eva-corrupt.session.json"
    bad_sess.write_text("{BAD_JSON", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupted persisted EVA session"):
        eva_svc.get_session("eva-corrupt")

    # 3. Build a campaign cleanly to test version conflict (409) & auth-gated invalidation
    batch = si_svc.evaluate_targets(
        TargetEvaluationRequest(
            question_id="gale_boxwork_origin",
            study_bounds={"min_lat": -4.752, "max_lat": -4.706, "min_lon": 137.386, "max_lon": 137.433},
            max_candidates=2,
        )
    )
    chosen = batch.targets[:1]
    cid = "camp_p21_adv"
    plan = si_svc.build_campaign(
        CampaignBuildRequest(
            campaign_id=cid,
            campaign_name="Adversarial Version Test",
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=chosen[0].latitude + 0.0005, lon_east=chosen[0].longitude_east - 0.0005),
            selected_target_ids=[chosen[0].target_id],
        )
    )
    # Missing EVA parameters keep constraint_evaluation_complete False
    assert plan.constraint_evaluation_complete is False
    assert len(plan.missing_inputs) >= 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Stale expected_plan_version must fail with 409 Conflict
        r_conflict = await client.post(
            "/api/science-investigation/observations",
            json={
                "campaign_id": cid,
                "instrument_id": "CHEMCAM_LIBS",
                "measurement_type": "oxide",
                "species_or_feature": "SO3",
                "measured_value": 10.0,
                "latitude": chosen[0].latitude,
                "longitude_east": chosen[0].longitude_east,
                "expected_plan_version": 99,
            },
        )
        assert r_conflict.status_code == 409

        # Path-traversal campaign id rejected cleanly with 422
        r_bad_id = await client.get("/api/science-investigation/campaigns/bad..id/lifecycle")
        assert r_bad_id.status_code == 422

        # Orchestration invalidation endpoint fails closed without operator token
        monkeypatch.setenv("MARSCOPE_OPERATOR_TOKEN", "secret-p21-token")
        r_unauth = await client.post(
            "/api/science-investigation/orchestration/invalidate",
            json={
                "source_type": "dem_reprocessed",
                "description": "Updated calibration",
                "dataset_id": "hirise_dteec_009149_1750",
            },
        )
        assert r_unauth.status_code in (401, 403)

        r_auth = await client.post(
            "/api/science-investigation/orchestration/invalidate",
            headers={"X-Mars-Operator-Token": "secret-p21-token"},
            json={
                "source_type": "dem_reprocessed",
                "description": "Updated calibration",
                "dataset_id": "hirise_dteec_009149_1750",
            },
        )
        assert r_auth.status_code == 200
        assert cid in r_auth.json()["affected_campaign_ids"]

    # Confirm invalidation propagated to stored campaign freshness
    after_inv = si_svc.get_campaign(cid)
    assert after_inv is not None
    assert after_inv.freshness_state == CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED
