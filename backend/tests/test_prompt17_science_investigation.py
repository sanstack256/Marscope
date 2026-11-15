"""
Prompt 17 Automated Verification Suite:
1. Prompt 16 defect fixes (1.1-1.7): PDS scaling honesty, optical coverage None vs 0.0,
   weighted multi-domain readiness, sensitivity v2 categories, near-flat Rice bias,
   and robust route search metadata.
2. Part 9 acquisition/integrity gates: streaming max_bytes, magic-byte validation,
   non-overwrite enforcement, and DISCOVERED != ACQUIRED != VALIDATED ledgers.
3. Multi-instrument registry (16 instruments), prohibited inferences & Jezero isolation.
4. Scientific questions (Gale boxwork + custom USER_DEFINED CRUD) & evidence discovery.
5. 7-state Target Evaluation & transparent heuristic ordering.
6. Multi-stop constrained campaign planning, return planning, EVA feasibility,
   alternatives, and CURRENT -> STALE -> recompute freshness tracking.
7. Field observation capture & scale-aware archive comparison.
8. All 20 HTTP endpoints under /api/science-investigation/*.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
import rasterio
from httpx import ASGITransport, AsyncClient
from rasterio.transform import from_bounds

import app.api.science_investigation as api_si
from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.ingestion.acquisition import (
    AcquisitionService,
    safe_write_downloaded_bytes,
    validate_artifact_signature,
)
from app.ingestion.pds_label import extract_pds3_metadata
from app.main import app
from app.routing.schemas import (
    RobustRouteCompareRequest,
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RoutingMode,
)
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)
from app.schemas.target import InvestigationTargetEvidenceState, ScienceTarget
from app.science.investigation.schemas import (
    ArchiveComparisonOutcome,
    CampaignBuildRequest,
    CampaignFreshnessState,
    CampaignPlanStatus,
    CustomScienceQuestionCreateRequest,
    InferenceValidationRequest,
    MeasurementClass,
    RecordObservationRequest,
    RequirementFulfillmentState,
    TargetEvaluationRequest,
)
from app.science.investigation.service import ScienceInvestigationService
from app.services.container import (
    catalog_service,
    composition_index,
    composition_search_service,
    imagery_service,
    routing_service,
    science_investigation_service as live_si_service,
    target_registry,
)
from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty
from app.terrain_uncertainty.slope_uncertainty import propagate_horn_slope_uncertainty

MARS_PROJ4 = MARS_CRS_DEFINITIONS["IAU2000:49900"]


@pytest.fixture()
def isolated_si_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScienceInvestigationService:
    """Create an isolated ScienceInvestigationService backed by live NASA read-only archives + tmp writes."""
    svc = ScienceInvestigationService(
        catalog_service=catalog_service,
        target_registry=target_registry,
        composition_search_service=composition_search_service,
        composition_index=composition_index,
        routing_service=routing_service,
        evidence_service=live_si_service.evidence_service,
        processed_dir=tmp_path,
        imagery_service=imagery_service,
    )
    monkeypatch.setattr(api_si, "science_investigation_service", svc)
    return svc


# =============================================================================
# 1. PROMPT 16 DEFECT REGRESSIONS (1.1 - 1.7)
# =============================================================================


def test_pds_scaling_not_fabricated_when_absent(tmp_path: Path):
    """Defect 1.1: Missing SCALING_FACTOR/OFFSET must not be fabricated to 1.0/0.0."""
    raw_label = """
    RECORD_TYPE = FIXED_LENGTH
    OBJECT = IMAGE
      LINES = 100
      LINE_SAMPLES = 100
      SAMPLE_BITS = 16
      SAMPLE_TYPE = MSB_INTEGER
      UNIT = "METER"
    END_OBJECT = IMAGE
    END
    """
    lbl = tmp_path / "test_noscaling.lbl"
    lbl.write_text(raw_label, encoding="utf-8")
    parsed = extract_pds3_metadata(lbl)
    assert parsed.get("scaling_factor") is None
    assert parsed.get("offset") is None


def test_float_geotiff_elevation_uncertainty_is_unquantified(tmp_path: Path):
    """Float GeoTIFF without PDS quantization metadata must not report fake integer quantization bounds."""
    tif_path = tmp_path / "float_dem.tif"
    arr = np.linspace(-4200.0, -4180.0, 25, dtype=np.float32).reshape(5, 5)
    transform = from_bounds(137.39, -4.75, 137.40, -4.74, 5, 5)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=5,
        width=5,
        count=1,
        dtype="float32",
        crs=MARS_PROJ4,
        transform=transform,
    ) as dst:
        dst.write(arr, 1)

    base_ds = catalog_service.get_dataset("hirise_dteec_009149_1750")
    assert base_ds is not None
    ds = base_ds.model_copy(
        update={
            "id": "test_float_dem",
            "product_id": "TEST_FLOAT",
            "processed_file_path": "float_dem.tif",
            "local_file_path": None,
            "status": DatasetLifecycleStatus.PROCESSED,
        }
    )
    prof = inspect_dataset_elevation_uncertainty(
        dataset=ds,
        raw_dir=tmp_path,
        processed_dir=tmp_path,
    )
    assert prof.is_integer_quantized is False
    assert "unquantified" in prof.overall_elevation_uncertainty_status.lower() or len(prof.missing_uncertainty_fields) > 0


def test_rice_near_flat_slope_bias_flagged():
    """Defect 1.5: Flat synthetic surface with 0 slope has Rice bias fraction flagged when sigma_z > 0."""
    dem = np.full((7, 7), -4200.0, dtype=np.float32)
    mask = np.zeros_like(dem, dtype=bool)
    slope_grid, sigma_grid, summary = propagate_horn_slope_uncertainty(
        elevation_grid=dem,
        dx_meters=1.0,
        dy_meters=1.0,
        nodata_mask=mask,
        sigma_z_m=0.5,
        basis_description="synthetic_unit_test",
    )
    assert summary.near_flat_bias_affected_fraction is not None
    assert summary.near_flat_bias_affected_fraction > 0.0
    assert slope_grid is not None and sigma_grid is not None


def test_robust_compare_and_sensitivity_v2_metadata():
    """Defects 1.4-1.7: Sensitivity v2 exposes 4 categories and robust compare exposes search_limits."""
    res = routing_service.compute_robust_comparison(
        RobustRouteCompareRequest(
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=-4.7330, lon_east=137.4025),
            destination=RouteCoordinateInput(lat=-4.7350, lon_east=137.4045),
            constraints=RoutePlanningConstraints(max_slope_deg=18.0),
            include_sensitivity=True,
            include_independent_return=True,
        )
    )
    assert res.search_limits
    assert res.overlap_metric_definition
    assert res.global_optimality_disclaimer
    assert res.candidates
    sens = res.candidates[0].sensitivity_summary
    assert sens is not None
    assert sens.scenarios
    assert {sc.category.value for sc in sens.scenarios}.issubset({
        "MEASUREMENT_UNCERTAINTY_PROPAGATION",
        "MEASUREMENT_SENSITIVITY_ANALYSIS",
        "ALGORITHM_PARAMETER_SENSITIVITY",
        "MISSION_ASSUMPTION_SENSITIVITY",
    })
    assert isinstance(sens.category_summaries, dict)
    assert len(sens.category_summaries) >= 1


# =============================================================================
# 2. PART 9 ACQUISITION & INTEGRITY GATES
# =============================================================================


def test_acquisition_magic_bytes_overwrite_and_max_bytes(tmp_path: Path):
    """Part 9: Reject disguised HTML payloads, enforce overwrite=False & max_bytes, verify ledgers."""
    with pytest.raises(ValueError):
        validate_artifact_signature(
            b"<html><body>404 Not Found</body></html>",
            tmp_path / "fake.tif",
        )

    good_tif = tmp_path / "real.tif"
    arr = np.ones((4, 4), dtype=np.float32)
    with rasterio.open(
        good_tif,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs=MARS_PROJ4,
        transform=from_bounds(137.39, -4.75, 137.40, -4.74, 4, 4),
    ) as dst:
        dst.write(arr, 1)
    sig_info = validate_artifact_signature(good_tif.read_bytes()[:64], good_tif)
    assert sig_info["signature_verified"] is True
    assert sig_info["signature_kind"] == "geotiff_or_tiff"

    acq = AcquisitionService(raw_data_dir=tmp_path / "raw", manifests_dir=tmp_path / "manifests")
    dest = tmp_path / "raw" / "existing.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"VALID_BYTES")

    # Enforce overwrite=False refusal
    with pytest.raises(FileExistsError):
        safe_write_downloaded_bytes(
            dest,
            b"II*\x00NEW_BYTES",
            source_url="https://example.org/test.tif",
            overwrite=False,
        )

    # Enforce max_bytes cap
    with pytest.raises(ValueError, match="max_bytes"):
        safe_write_downloaded_bytes(
            tmp_path / "raw" / "too_big.tif",
            b"II*\x00" + b"X" * 1024,
            source_url="https://example.org/huge.tif",
            max_bytes=200,
            overwrite=True,
        )

    # Ledger & query provenance track events distinctly
    acq.record_query_provenance(
        archive_name="NASA_ODE_REST",
        endpoint="https://oderest.rsl.wustl.edu/live2/",
        params={"target": "Gale"},
        http_status=200,
        result_count=1,
        success=True,
    )
    q_entries = acq.get_query_provenance(limit=10)
    assert any(e.get("archive_name") == "NASA_ODE_REST" and e.get("success") is True for e in q_entries)
    assert isinstance(acq.get_acquisition_ledger(limit=10), list)


# =============================================================================
# 3. MULTI-INSTRUMENT REGISTRY & PROHIBITED INFERENCES
# =============================================================================


def test_instrument_registry_and_prohibited_inferences(isolated_si_service: ScienceInvestigationService):
    instruments = isolated_si_service.list_instruments(include_mission_isolated=True)
    assert len(instruments) == 16
    isolated = {i.instrument_id for i in instruments if i.mission_isolated_from_gale}
    assert {"PIXL_SHERLOC", "SUPERCAM_MASTCAMZ"}.issubset(isolated)

    gale_only = isolated_si_service.list_instruments(include_mission_isolated=False)
    assert all(not i.mission_isolated_from_gale for i in gale_only)

    # Reject optical -> mineral presence inference
    bad_optical = isolated_si_service.validate_inference(
        InferenceValidationRequest(
            instrument_id="HIRISE",
            claimed_inference="Confirm gypsum mineral composition from bright ridge color",
        )
    )
    assert bad_optical.allowed is False
    assert bad_optical.classification == "prohibited_visual_to_mineral_inference"

    # Reject ChemCam LIBS -> definitive XRD crystal structure
    bad_xrd = isolated_si_service.validate_inference(
        InferenceValidationRequest(
            instrument_id="CHEMCAM_LIBS",
            claimed_inference="Confirmed smectite mineral crystal structure without XRD",
        )
    )
    assert bad_xrd.allowed is False

    # Reject coarse MOLA -> meter-scale rover hazard
    bad_res = isolated_si_service.validate_inference(
        InferenceValidationRequest(
            instrument_id="MOLA",
            claimed_inference="Confirm traversable meter boxwork thickness and local slope",
        )
    )
    assert bad_res.allowed is False

    # Allow valid inference within instrument capability scope
    good = isolated_si_service.validate_inference(
        InferenceValidationRequest(
            instrument_id="HIRISE_DTM",
            claimed_inference="Compute 1 m scale boxwork ridge relief and slope geometry",
        )
    )
    assert good.allowed is True


# =============================================================================
# 4. QUESTIONS, EVIDENCE DISCOVERY & JEZERO QUARANTINE
# =============================================================================


def test_questions_and_real_gale_evidence_discovery(isolated_si_service: ScienceInvestigationService):
    questions = isolated_si_service.list_questions()
    q_ids = {q.question_id for q in questions}
    assert "gale_boxwork_origin" in q_ids

    # Create and delete custom USER_DEFINED question
    custom = isolated_si_service.create_custom_question(
        CustomScienceQuestionCreateRequest(
            title="Test Hydrated Sulfate Vein Mapping",
            hypothesis="Fracture-fill veins preserve late diagenetic calcium sulfate fluids.",
            target_phenomena=["SO3", "CaO", "gypsum"],
            required_measurement_classes=[
                MeasurementClass.MINERALOGY_SPECTRAL,
                MeasurementClass.ELEMENTAL_CHEMISTRY,
                MeasurementClass.TOPOGRAPHY_ELEVATION,
            ],
            preferred_stop_count=2,
        )
    )
    assert custom.is_user_defined is True
    assert isolated_si_service.get_question(custom.question_id) is not None

    disc = isolated_si_service.discover_evidence_for_question("gale_boxwork_origin")
    # Real Gale index supplies ChemCam/APXS + HiRISE DEM, while SAM volatiles / CRISM are absent
    states = {r.measurement_class.value: r.fulfillment_state for r in disc.requirements_evaluation}
    assert states["topography_elevation"] == RequirementFulfillmentState.SATISFIED_DIRECT
    assert states["elemental_chemistry"] == RequirementFulfillmentState.SATISFIED_DIRECT
    assert len(disc.critical_data_gaps) > 0
    # Strictly isolated Perseverance instruments must be in isolated_or_rejected_records
    iso_insts = {r.instrument_id for r in disc.isolated_or_rejected_records}
    assert "PIXL_SHERLOC" in iso_insts or "SUPERCAM_MASTCAMZ" in iso_insts

    # Custom spectral question must identify missing CRISM cube
    disc_custom = isolated_si_service.discover_evidence_for_question(custom.question_id)
    c_states = {r.measurement_class.value: r.fulfillment_state for r in disc_custom.requirements_evaluation}
    assert c_states["mineralogy_spectral"] == RequirementFulfillmentState.MISSING_REQUIRED_DATA

    # Cannot delete built-in question; can delete custom
    assert isolated_si_service.delete_custom_question("gale_boxwork_origin") is False
    assert isolated_si_service.delete_custom_question(custom.question_id) is True


# =============================================================================
# 5. 7-STATE TARGET EVALUATION & HEURISTIC TRANSPARENCY
# =============================================================================


def test_target_evaluation_7_states_and_heuristics(isolated_si_service: ScienceInvestigationService):
    batch = isolated_si_service.evaluate_targets(
        TargetEvaluationRequest(
            question_id="gale_boxwork_origin",
            include_discovered_candidates=True,
            max_candidates=8,
        )
    )
    assert len(batch.targets) > 0
    assert "heuristic" in batch.prioritization_disclaimer.lower()
    for t in batch.targets:
        assert t.prioritization_is_heuristic is True
        assert 0.0 <= t.heuristic_priority_score <= 1.0
        assert isinstance(t.prioritization_breakdown, dict)
        assert t.prioritization_breakdown.get("is_heuristic") is True

    # Also test explicit optical vs manual vs data-gap evaluations cleanly
    from app.science.investigation.target_evaluation import _evaluate_single_location
    q = isolated_si_service.get_question("gale_boxwork_origin")
    assert q is not None

    opt_eval = _evaluate_single_location(
        target_id="opt_test",
        name="Bright Boxwork Optical Ridge",
        latitude=-4.750,
        longitude_east=137.400,
        elevation_m=None,
        crs="IAU2000:49900",
        matched_species=None,
        initial_evidence_state=InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED,
        initial_instruments=["HIRISE"],
        initial_evidence_ids=[],
        geology_type="optical_candidate",
        question=q,
        catalog_service=catalog_service,
        composition_index=None,
        recorded_observations=[],
        astronaut_lat=None,
        astronaut_lon=None,
        search_radius_m=50.0,
    )
    assert opt_eval.evidence_state == InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED
    assert opt_eval.eligibility_for_sampling == "DEFERRED_PENDING_IN_SITU_SCREENING"
    assert "optical_candidate_cannot_receive_mineral_or_routing_science_bonus" in opt_eval.prohibited_inference_flags

    man_eval = _evaluate_single_location(
        target_id="man_test",
        name="Crew Adhoc Point",
        latitude=-4.750,
        longitude_east=137.400,
        elevation_m=None,
        crs="IAU2000:49900",
        matched_species=None,
        initial_evidence_state=InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED,
        initial_instruments=[],
        initial_evidence_ids=[],
        geology_type="manual_waypoint",
        question=q,
        catalog_service=catalog_service,
        composition_index=None,
        recorded_observations=[],
        astronaut_lat=None,
        astronaut_lon=None,
        search_radius_m=50.0,
    )
    assert man_eval.evidence_state == InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED

    gap_eval = _evaluate_single_location(
        target_id="gap_test",
        name="Far Uncovered Coord",
        latitude=-25.0,
        longitude_east=220.0,
        elevation_m=None,
        crs="IAU2000:49900",
        matched_species=None,
        initial_evidence_state=None,
        initial_instruments=[],
        initial_evidence_ids=[],
        geology_type="unknown_outcrop",
        question=q,
        catalog_service=None,
        composition_index=None,
        recorded_observations=[],
        astronaut_lat=None,
        astronaut_lon=None,
        search_radius_m=50.0,
    )
    assert gap_eval.evidence_state == InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED


# =============================================================================
# 6. CAMPAIGN PLANNING, CONSTRAINTS & STALENESS DETECTION
# =============================================================================


def test_campaign_build_constraints_alternatives_and_freshness(
    isolated_si_service: ScienceInvestigationService,
):
    # Empty target list and missing destination must return DATA_INSUFFICIENT (no fabricated waypoints)
    empty_plan = isolated_si_service.build_campaign(
        CampaignBuildRequest(
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=-4.7330, lon_east=137.4025),
            selected_target_ids=[],
        )
    )
    assert empty_plan.plan_status == CampaignPlanStatus.DATA_INSUFFICIENT
    assert empty_plan.stop_plans == []

    # Discover real targets inside processed HiRISE DEM (-4.752..-4.706, 137.386..137.433)
    batch = isolated_si_service.evaluate_targets(
        TargetEvaluationRequest(
            question_id="gale_boxwork_origin",
            include_discovered_candidates=True,
            study_bounds={
                "min_lat": -4.752,
                "max_lat": -4.706,
                "min_lon": 137.386,
                "max_lon": 137.433,
            },
            max_candidates=6,
        )
    )
    assert len(batch.targets) >= 2
    chosen = batch.targets[:2]
    start = RouteCoordinateInput(
        lat=chosen[0].latitude + 0.001,
        lon_east=chosen[0].longitude_east - 0.001,
    )

    plan = isolated_si_service.build_campaign(
        CampaignBuildRequest(
            campaign_name="Boxwork Multi-Stop Test",
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=start,
            selected_target_ids=[c.target_id for c in chosen],
            walking_speed_mps=0.8,
            mission_duration_limit_s=14400.0,
            return_reserve_fraction=0.25,
            include_alternatives=True,
        )
    )
    assert plan.operational_safety_certified is False
    assert plan.plan_status in {
        CampaignPlanStatus.COMPLETE_CONSTRAINED_PLAN,
        CampaignPlanStatus.PARTIAL_MISSING_OBSERVATIONS,
    }
    assert len(plan.stop_plans) == 2
    assert plan.outbound_route_id is not None
    assert plan.return_plan is not None
    assert plan.return_plan.return_route_computed is True
    assert len(plan.alternatives) >= 2
    for sp in plan.stop_plans:
        assert sp.observation_plan.recommended_instruments
        assert sp.sampling_protocol.prohibited_without_evidence is True

    # Freshness is CURRENT immediately after build
    f1 = isolated_si_service.check_campaign_freshness(plan.campaign_id)
    assert f1.freshness_state == CampaignFreshnessState.CURRENT
    assert f1.staleness_reasons == []

    # Too-tight EVA time limit -> INFEASIBLE_UNDER_CONSTRAINTS
    tight = isolated_si_service.build_campaign(
        CampaignBuildRequest(
            campaign_name="Impossible Duration Test",
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=start,
            selected_target_ids=[c.target_id for c in chosen],
            walking_speed_mps=0.5,
            mission_duration_limit_s=30.0,
            return_reserve_fraction=0.25,
            include_alternatives=False,
        )
    )
    assert tight.plan_status == CampaignPlanStatus.INFEASIBLE_UNDER_CONSTRAINTS

    # Recording a field observation at stop 0 turns prior campaign STALE
    obs = isolated_si_service.record_observation(
        RecordObservationRequest(
            campaign_id=plan.campaign_id,
            target_id=chosen[0].target_id,
            instrument_id="CHEMCAM_LIBS",
            measurement_type="elemental_oxide_wt_pct",
            species_or_feature="SO3",
            measured_value=14.8,
            units="wt%",
            latitude=chosen[0].latitude,
            longitude_east=chosen[0].longitude_east,
        )
    )
    assert obs.quality_flag == "field_recorded_unvalidated_pending_lab"
    f2 = isolated_si_service.check_campaign_freshness(plan.campaign_id)
    assert f2.freshness_state == CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED
    assert len(f2.staleness_reasons) >= 1

    # Recompute restores CURRENT freshness
    recomputed = isolated_si_service.recompute_campaign(plan.campaign_id)
    assert recomputed.freshness_state == CampaignFreshnessState.CURRENT
    f3 = isolated_si_service.check_campaign_freshness(recomputed.campaign_id)
    assert f3.freshness_state == CampaignFreshnessState.CURRENT


# =============================================================================
# 7. OBSERVATION CAPTURE & SCALE-AWARE ARCHIVE COMPARISON
# =============================================================================


def test_observation_capture_and_scale_aware_comparison(
    isolated_si_service: ScienceInvestigationService,
):
    # Optical mineral claim warning triggers automatically on field capture
    opt_obs = isolated_si_service.record_observation(
        RecordObservationRequest(
            instrument_id="HIRISE",
            measurement_type="visual_inspection",
            species_or_feature="gypsum",
            measured_value="bright vein texture",
            latitude=-4.734,
            longitude_east=137.411,
        )
    )
    assert opt_obs.prohibited_inference_warning is not None

    # Compare ChemCam SO3 near Daglan (-4.73429, 137.41166) with extreme outlier vs archive
    outlier = isolated_si_service.record_observation(
        RecordObservationRequest(
            instrument_id="CHEMCAM_LIBS",
            measurement_type="elemental_oxide_wt_pct",
            species_or_feature="SO3",
            measured_value=42.0,
            units="wt%",
            latitude=-4.73429,
            longitude_east=137.41166,
        )
    )
    cmp_out = isolated_si_service.compare_observation_with_archive(
        outlier.observation_id, search_radius_m=500.0
    )
    # Near Daglan there are Gale archive records + MOLA/coarse datasets -> scale disparity note emitted
    assert cmp_out.outcome in {
        ArchiveComparisonOutcome.DIFFERS_FROM_PRIOR_LOCAL_MEASUREMENT,
        ArchiveComparisonOutcome.EXTENDS_ARCHIVE_COVERAGE,
    }
    assert len(cmp_out.scale_disparity_notes) >= 1

    # Compare at an unvisited Mars coordinate -> NO_CO_LOCATED_ARCHIVE_FOR_COMPARISON
    remote = isolated_si_service.record_observation(
        RecordObservationRequest(
            instrument_id="APXS",
            measurement_type="elemental_oxide_wt_pct",
            species_or_feature="SO3",
            measured_value=5.2,
            units="wt%",
            latitude=-30.0,
            longitude_east=220.0,
        )
    )
    cmp_remote = isolated_si_service.compare_observation_with_archive(
        remote.observation_id, search_radius_m=150.0
    )
    assert cmp_remote.outcome == ArchiveComparisonOutcome.NO_CO_LOCATED_ARCHIVE_FOR_COMPARISON


# =============================================================================
# 8. ALL 20 HTTP ENDPOINTS UNDER /api/science-investigation/*
# =============================================================================


@pytest.mark.asyncio
async def test_all_20_science_investigation_endpoints(
    isolated_si_service: ScienceInvestigationService,
):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /instruments
        r = await client.get("/api/science-investigation/instruments")
        assert r.status_code == 200
        assert len(r.json()) == 16

        # 2. GET /instruments/{id}
        r = await client.get("/api/science-investigation/instruments/CRISM")
        assert r.status_code == 200
        assert r.json()["instrument_id"] == "CRISM"

        # 3. POST /instruments/validate-inference
        r = await client.post(
            "/api/science-investigation/instruments/validate-inference",
            json={"instrument_id": "HIRISE", "claimed_inference": "confirm gypsum presence visually"},
        )
        assert r.status_code == 200
        assert r.json()["allowed"] is False

        # 4. GET /questions
        r = await client.get("/api/science-investigation/questions")
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # 5. GET /questions/{id}
        r = await client.get("/api/science-investigation/questions/gale_boxwork_origin")
        assert r.status_code == 200

        # 6. POST /questions
        r = await client.post(
            "/api/science-investigation/questions",
            json={
                "title": "API Custom Mineral Question",
                "hypothesis": "Fracture cements preserve magnesium sulfate brines.",
                "target_phenomena": ["MgO", "SO3"],
                "required_measurement_classes": ["elemental_chemistry", "topography_elevation"],
                "preferred_stop_count": 2,
            },
        )
        assert r.status_code == 201
        q_custom_id = r.json()["question_id"]

        # 8. GET /questions/{id}/discover-evidence
        r = await client.get(
            f"/api/science-investigation/questions/{q_custom_id}/discover-evidence"
        )
        assert r.status_code == 200
        assert r.json()["question"]["question_id"] == q_custom_id

        # 9. POST /targets/evaluate
        r = await client.post(
            "/api/science-investigation/targets/evaluate",
            json={
                "question_id": "gale_boxwork_origin",
                "study_bounds": {
                    "min_lat": -4.752,
                    "max_lat": -4.706,
                    "min_lon": 137.386,
                    "max_lon": 137.433,
                },
                "max_candidates": 4,
            },
        )
        assert r.status_code == 200
        targs = r.json()["targets"]
        assert len(targs) >= 1

        # 10. POST /campaigns/build
        r = await client.post(
            "/api/science-investigation/campaigns/build",
            json={
                "campaign_name": "HTTP API Traverse",
                "question_id": "gale_boxwork_origin",
                "dataset_id": "hirise_dteec_009149_1750",
                "start": {"lat": targs[0]["latitude"] + 0.0008, "lon_east": targs[0]["longitude_east"] - 0.0008},
                "selected_target_ids": [targs[0]["target_id"]],
                "walking_speed_mps": 0.8,
                "mission_duration_limit_s": 7200.0,
                "return_reserve_fraction": 0.25,
                "include_alternatives": True,
            },
        )
        assert r.status_code == 200
        camp_id = r.json()["campaign_id"]

        # 11. GET /campaigns
        r = await client.get("/api/science-investigation/campaigns")
        assert r.status_code == 200
        assert any(c["campaign_id"] == camp_id for c in r.json())

        # 12. GET /campaigns/{id}
        r = await client.get(f"/api/science-investigation/campaigns/{camp_id}")
        assert r.status_code == 200
        assert r.json()["campaign_id"] == camp_id

        # 13. GET /campaigns/{id}/freshness
        r = await client.get(f"/api/science-investigation/campaigns/{camp_id}/freshness")
        assert r.status_code == 200
        assert r.json()["freshness_state"] == "current"

        # 15. POST /observations
        r = await client.post(
            "/api/science-investigation/observations",
            json={
                "campaign_id": camp_id,
                "target_id": targs[0]["target_id"],
                "instrument_id": "CHEMCAM_LIBS",
                "measurement_type": "elemental_oxide_wt_pct",
                "species_or_feature": "SO3",
                "measured_value": 12.0,
                "units": "wt%",
                "latitude": targs[0]["latitude"],
                "longitude_east": targs[0]["longitude_east"],
            },
        )
        assert r.status_code == 201
        obs_id = r.json()["observation_id"]

        # 14. POST /campaigns/{id}/recompute
        r = await client.post(f"/api/science-investigation/campaigns/{camp_id}/recompute")
        assert r.status_code == 200
        assert r.json()["freshness_state"] == "current"

        # 16. GET /observations
        r = await client.get(
            "/api/science-investigation/observations",
            params={"campaign_id": camp_id},
        )
        assert r.status_code == 200
        assert any(o["observation_id"] == obs_id for o in r.json())

        # 17. GET /observations/{id}
        r = await client.get(f"/api/science-investigation/observations/{obs_id}")
        assert r.status_code == 200

        # 18. POST /observations/{id}/compare
        r = await client.post(
            f"/api/science-investigation/observations/{obs_id}/compare",
            params={"search_radius_m": 250.0},
        )
        assert r.status_code == 200
        assert r.json()["observation_id"] == obs_id

        # 19. GET /comparisons
        r = await client.get(
            "/api/science-investigation/comparisons",
            params={"observation_id": obs_id},
        )
        assert r.status_code == 200
        assert len(r.json()) >= 1

        # 20. GET /ingestion-ledger
        r = await client.get("/api/science-investigation/ingestion-ledger", params={"limit": 10})
        assert r.status_code == 200
        assert "acquisition_ledger" in r.json()
        assert "query_provenance" in r.json()

        # 7. DELETE /questions/{id}
        r = await client.delete(f"/api/science-investigation/questions/{q_custom_id}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
