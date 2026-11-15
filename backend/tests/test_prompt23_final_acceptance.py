"""
MARSCOPE Prompt 23 Independent Final Scientific Validation & Acceptance Suite

All synthetic grids, resource fixtures, and isolated readiness configurations in
this module are explicitly labeled `[SYNTHETIC_REFERENCE_FIXTURE]` and are used
strictly to independently verify analytical mathematics, coordinate transforms,
edge-case guards, and epistemic contracts. They do NOT substitute for real NASA
product processing verification.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import numpy as np
import pytest

from app.core import persistence
from app.core.config import settings
from app.core.readiness import evaluate_system_readiness
from app.eva_operations.energy_budget import evaluate_eva_energy_budget
from app.eva_operations.locomotion import (
    LocomotionEvaluationStatus,
    LocomotionModelCategory,
    evaluate_segment_locomotion,
)
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.return_planning import plan_eva_return_route
from app.eva_operations.schemas import ExplicitResourceSpec, ResourceRatePhaseSpec, ReturnPlanStatus
from app.geospatial.crs import (
    CRSError,
    MARS_EQUATORIAL_RADIUS_M,
    MARS_POLAR_RADIUS_M,
    convert_latitude_convention,
    normalize_longitude_180,
    normalize_longitude_360,
    validate_mars_crs,
)
from app.main import app
from app.physics.registry.parameters import get_parameter
from app.routing.graph import TerrainGrid
from app.routing.models import MODE_POLICIES, PathAlgorithm, RoutingMode
from app.routing.pathfinder import solve_grid_leg
from app.routing.schemas import RouteComputeResponse, RouteCoordinateInput, RouteVertex
from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignPlanStatus,
    CampaignStopPlan,
    IntegratedMissionLifecycleState,
    InvestigationTargetEvidenceState,
    ObservationActionPlan,
    RecordObservationRequest,
    SamplingProtocolSpec,
    ScienceCampaignPlan,
)
from app.science.investigation.service import ScienceInvestigationService
from app.science.provenance_graph import ProvenanceDependencyGraph, ScientificDataClassification
from app.science.target_registry import _classify_evidence_state_from_records
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


# ---------------------------------------------------------------------------
# 1. Planetary CRS & Geodesy Independent Reference Checks [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_mars_iau2000_crs_and_latitude_conversion_analytic():
    """Verify exact Mars IAU2000 ellipsoid tan(phi_c) = (b/a)^2 tan(phi_g) & Earth/Moon rejection."""
    assert validate_mars_crs("IAU2000:49900") is True
    assert validate_mars_crs("EPSG:4326") is False
    assert validate_mars_crs("WGS 84") is False
    assert validate_mars_crs("IAU2000:30100") is False  # Moon must be rejected

    ratio_sq = (MARS_POLAR_RADIUS_M / MARS_EQUATORIAL_RADIUS_M) ** 2
    for phi_g in (-45.0, -4.6, 18.4, 45.0):
        expected_phi_c = math.degrees(math.atan(ratio_sq * math.tan(math.radians(phi_g))))
        computed_phi_c = convert_latitude_convention(
            phi_g,
            "Planetographic",
            "Planetocentric",
            MARS_EQUATORIAL_RADIUS_M,
            MARS_POLAR_RADIUS_M,
        )
        assert computed_phi_c == pytest.approx(expected_phi_c, abs=1e-9)
        roundtrip_phi_g = convert_latitude_convention(
            computed_phi_c,
            "Planetocentric",
            "Planetographic",
            MARS_EQUATORIAL_RADIUS_M,
            MARS_POLAR_RADIUS_M,
        )
        assert roundtrip_phi_g == pytest.approx(phi_g, abs=1e-9)

    assert convert_latitude_convention(0.0, "Planetographic", "Planetocentric", MARS_EQUATORIAL_RADIUS_M, MARS_POLAR_RADIUS_M) == 0.0
    assert normalize_longitude_180(222.6) == pytest.approx(-137.4, abs=1e-9)
    assert normalize_longitude_360(-137.4) == pytest.approx(222.6, abs=1e-9)

    with pytest.raises(CRSError):
        convert_latitude_convention(95.0, "Planetographic", "Planetocentric", MARS_EQUATORIAL_RADIUS_M, MARS_POLAR_RADIUS_M)


# ---------------------------------------------------------------------------
# 2. Terrain Derivatives & No-Data Boundary Propagation [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_horn_slope_tri_analytic_and_nodata_propagation():
    """Verify Horn 3x3 slope & Riley 1999 TRI match analytical ground truth and never interpolate across NaN."""
    dx_m, dy_m = 2.0, 2.0
    xs = np.arange(7, dtype=np.float64) * dx_m
    ys = np.arange(7, dtype=np.float64) * dy_m
    # Note image row y goes N->S so elevation decreasing south (-dy) corresponds to positive dz/dy = -0.10
    z_plane = 0.25 * xs[None, :] + 0.10 * ys[:, None]

    slope_deg, _ = calculate_slope(z_plane, dx_meters=dx_m, dy_meters=dy_m, vertical_units="meters")
    expected_deg = math.degrees(math.atan(math.hypot(0.25, 0.10)))
    assert np.all(np.isnan(slope_deg[0, :])) and np.all(np.isnan(slope_deg[-1, :]))
    assert np.all(np.isnan(slope_deg[:, 0])) and np.all(np.isnan(slope_deg[:, -1]))
    np.testing.assert_allclose(slope_deg[1:-1, 1:-1], expected_deg, rtol=0.0, atol=1e-9)

    # Inject a single NaN at (3,3) -> 3x3 stencil around it must all become NaN
    z_gap = z_plane.copy()
    z_gap[3, 3] = np.nan
    slope_gap, _ = calculate_slope(z_gap, dx_meters=dx_m, dy_meters=dy_m, vertical_units="meters")
    assert np.all(np.isnan(slope_gap[2:5, 2:5]))
    assert np.isfinite(slope_gap[1, 1])

    # Analytical TRI check: center=0.0 surrounded by eight 1.0 m neighbors => sqrt(8/8) = 1.0 m
    z_tri = np.ones((5, 5), dtype=np.float64)
    z_tri[2, 2] = 0.0
    tri_arr, meta = calculate_roughness_tri_with_metadata(
        z_tri,
        dx_meters=1.0,
        dy_meters=1.0,
        neighborhood_radius_meters=1.0,
        vertical_units="meters",
    )
    assert tri_arr[2, 2] == pytest.approx(1.0, abs=1e-9)
    assert np.all(np.isnan(tri_arr[0, :])) and np.all(np.isnan(tri_arr[:, 0]))
    assert meta["window_shape_pixels"] == [3, 3]


# ---------------------------------------------------------------------------
# 3. Physics Parameters & Mechanical Work vs Missing Inputs [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_physics_gravity_and_mechanical_climb_work():
    """Verify g_Mars = 3.72076 m/s^2, exact deltaPE = m*g*dh, and strict refusal when suit/payload mass absent."""
    g_param = get_parameter("mars_standard_gravity")
    assert g_param is not None
    assert float(g_param.value) == pytest.approx(3.72076, abs=1e-9)

    unavail = evaluate_eva_energy_budget(
        outbound_climb_gain_m=50.0,
        outbound_descent_loss_m=10.0,
        return_climb_gain_m=10.0,
        return_descent_loss_m=50.0,
        astronaut_suit_mass_kg=None,
        payload_mass_kg=20.0,
    )
    assert unavail.available is False
    assert "astronaut_suit_mass_kg" in unavail.missing_inputs
    assert unavail.total_positive_climb_work_j is None

    eval_ok = evaluate_eva_energy_budget(
        outbound_climb_gain_m=50.0,
        outbound_descent_loss_m=10.0,
        return_climb_gain_m=10.0,
        return_descent_loss_m=50.0,
        astronaut_suit_mass_kg=180.0,
        payload_mass_kg=20.0,
    )
    assert eval_ok.available is True
    assert eval_ok.total_mass_kg == pytest.approx(200.0, abs=1e-9)
    assert eval_ok.outbound_climb_work_j == pytest.approx(200.0 * 3.72076 * 50.0, abs=0.1)
    assert eval_ok.return_climb_work_j == pytest.approx(200.0 * 3.72076 * 10.0, abs=0.1)
    assert eval_ok.total_positive_climb_work_j == pytest.approx(200.0 * 3.72076 * 60.0, abs=0.1)
    assert eval_ok.net_gravitational_pe_change_j == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# 4. Tobler 1993 Grade Approximation & Domain Limits [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_tobler_formula_domain_and_missing_speed():
    """Verify Tobler hiking factor asymmetry, strict domain rejection, and no default walking speed."""
    unavail = evaluate_segment_locomotion(
        segment_index=0,
        horizontal_distance_m=100.0,
        elevation_change_m=0.0,
        slope_deg=0.0,
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        reference_speed_mps=None,
    )
    assert unavail.status == LocomotionEvaluationStatus.MISSING_REFERENCE_SPEED

    v_ref = 1.2
    seg_up = evaluate_segment_locomotion(
        segment_index=0,
        horizontal_distance_m=100.0,
        elevation_change_m=20.0,
        slope_deg=math.degrees(math.atan(0.20)),
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        reference_speed_mps=v_ref,
    )
    seg_down = evaluate_segment_locomotion(
        segment_index=1,
        horizontal_distance_m=100.0,
        elevation_change_m=-20.0,
        slope_deg=math.degrees(math.atan(0.20)),
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        reference_speed_mps=v_ref,
    )
    assert seg_up.status == LocomotionEvaluationStatus.EVALUATED
    assert seg_down.status == LocomotionEvaluationStatus.EVALUATED
    assert seg_up.effective_speed_mps is not None and seg_down.effective_speed_mps is not None
    assert seg_up.effective_speed_mps < seg_down.effective_speed_mps
    assert seg_up.duration_s > seg_down.duration_s

    exceeded = evaluate_segment_locomotion(
        segment_index=2,
        horizontal_distance_m=50.0,
        elevation_change_m=50.0,
        slope_deg=45.0,
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        reference_speed_mps=v_ref,
        min_valid_slope_deg=-25.0,
        max_valid_slope_deg=25.0,
    )
    assert exceeded.status == LocomotionEvaluationStatus.OUTSIDE_LOCOMOTION_VALID_DOMAIN


# ---------------------------------------------------------------------------
# 5. Resource Budget Phase Integration & Edge-Case Hardening [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_resource_budget_phase_integration_and_invalid_input_guards():
    """Verify piecewise phase Q_used = sum(Q_dot_p * dt_p), reserve checks, and malformed phase rejections."""
    o2 = ExplicitResourceSpec(
        resource_name="EVA Suit O2",
        initial_quantity=2.0,
        unit="kg",
        consumption_rate=60.0,  # 0.060 kg/h = 0.0000166667 kg/s -> wait: 60 g/h = 0.06 kg/h
        rate_unit="g/h",
        reserve_fraction=0.25,  # 0.5 kg reserve
        phase_rates=[
            ResourceRatePhaseSpec(phase="traverse", consumption_rate=2.0, rate_unit="g/min"),  # 120 g/h
            ResourceRatePhaseSpec(phase="science_dwell", consumption_rate=30.0, rate_unit="g/h"),
        ],
    )
    ok_rep = evaluate_eva_resource_budget(
        resources=[o2],
        exposure_duration_s=5400.0,  # 1800s traverse + 1800s dwell + 1800s unassigned baseline
        phase_durations_s={"traverse": 1800.0, "science_dwell": 1800.0},
    )
    # 1800s * (2 g/min = 1/30 g/s) = 60 g = 0.060 kg
    # 1800s * (30 g/h = 0.008333 g/s) = 15 g = 0.015 kg
    # 1800s unassigned * (60 g/h) = 30 g = 0.030 kg => total = 0.105 kg
    assert ok_rep.overall_status == "WITHIN_CONSTRAINTS"
    assert ok_rep.entries[0].estimated_consumed == pytest.approx(0.105, abs=1e-4)
    assert ok_rep.entries[0].remaining_after_eva == pytest.approx(1.895, abs=1e-4)

    # Duplicate phase name must be rejected
    dup_spec = ExplicitResourceSpec(
        resource_name="EVA Suit O2",
        initial_quantity=2.0,
        unit="kg",
        consumption_rate=60.0,
        rate_unit="g/h",
        phase_rates=[
            ResourceRatePhaseSpec(phase="traverse", consumption_rate=2.0, rate_unit="g/min"),
            ResourceRatePhaseSpec(phase="traverse", consumption_rate=3.0, rate_unit="g/min"),
        ],
    )
    dup_rep = evaluate_eva_resource_budget(
        resources=[dup_spec],
        exposure_duration_s=3600.0,
        phase_durations_s={"traverse": 1800.0},
    )
    assert dup_rep.overall_status == "UNAVAILABLE"
    assert dup_rep.entries[0].status == "UNAVAILABLE"

    # Phase durations exceeding exposure_duration_s must be rejected
    over_rep = evaluate_eva_resource_budget(
        resources=[o2],
        exposure_duration_s=1000.0,
        phase_durations_s={"traverse": 800.0, "science_dwell": 500.0},
    )
    assert over_rep.overall_status == "UNAVAILABLE"

    # Negative / non-finite / negative phase duration / incompatible family guards
    neg_spec = ExplicitResourceSpec.model_construct(
        resource_name="EVA Suit O2",
        initial_quantity=-1.0,
        unit="kg",
        consumption_rate=10.0,
        rate_unit="g/h",
        reserve_fraction=0.0,
        phase_rates=[],
        classification=ScientificDataClassification.USER_ASSUMED,
    )
    assert evaluate_eva_resource_budget(resources=[neg_spec], exposure_duration_s=600.0).overall_status == "UNAVAILABLE"

    neg_phase_rep = evaluate_eva_resource_budget(
        resources=[o2],
        exposure_duration_s=1000.0,
        phase_durations_s={"traverse": -100.0},
    )
    assert neg_phase_rep.overall_status == "UNAVAILABLE"

    bad_unit = ExplicitResourceSpec(
        resource_name="Battery",
        initial_quantity=500.0,
        unit="Wh",
        consumption_rate=10.0,
        rate_unit="kg/h",
    )
    bad_rep = evaluate_eva_resource_budget(resources=[bad_unit], exposure_duration_s=600.0)
    assert bad_rep.entries[0].status == "UNIT_MISMATCH"
    assert bad_rep.overall_status == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# 6. A* vs Dijkstra Equivalence, No Corner Cutting, & Blocked Return [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def _build_synthetic_grid(traversable_mask: np.ndarray) -> TerrainGrid:
    rows, cols = traversable_mask.shape
    lats = -4.60 - np.arange(rows, dtype=np.float64) * 1e-4
    lons = 137.40 + np.arange(cols, dtype=np.float64) * 1e-4
    elev = np.full((rows, cols), -4500.0, dtype=np.float64)
    slope = np.zeros((rows, cols), dtype=np.float64)
    tri = np.zeros((rows, cols), dtype=np.float64)
    valid = np.ones((rows, cols), dtype=bool)
    zeros = np.zeros((rows, cols), dtype=np.float64)
    return TerrainGrid(
        rows=rows,
        cols=cols,
        lats=lats,
        lons_east=lons,
        dx_m=5.0,
        dy_m=5.0,
        native_resolution_m=1.0,
        elevation_m=elev,
        slope_deg=slope,
        tri_m=tri,
        valid_elev=valid,
        traversable=traversable_mask,
        nodata_adj_penalty=zeros,
        uncertainty_score=zeros,
        science_field=zeros,
        effective_slope_limit_deg=25.0,
    )


def test_p23_astar_dijkstra_no_corner_cutting_and_blocked_return():
    """Verify exact A*=Dijkstra optimality, diagonal wall non-cutting, and explicit blocked return status."""
    # [SYNTHETIC_REFERENCE_FIXTURE]: 5x5 grid with wall at col=2, rows 0..2 AND diagonal corner barrier
    trav = np.ones((5, 5), dtype=bool)
    trav[0:3, 2] = False
    grid = _build_synthetic_grid(trav)
    policy = MODE_POLICIES[RoutingMode.BALANCED]

    res_astar = solve_grid_leg(grid, (0, 0), (0, 4), policy, algorithm=PathAlgorithm.ASTAR)
    res_dijk = solve_grid_leg(grid, (0, 0), (0, 4), policy, algorithm=PathAlgorithm.DIJKSTRA)
    assert res_astar.total_cost == pytest.approx(res_dijk.total_cost, rel=1e-9, abs=1e-9)
    # Path must go down past row 2 (cannot cut corner through blocked col 2)
    assert any(r >= 3 and c == 2 for (r, c) in res_astar.cells)
    for r, c in res_astar.cells:
        assert trav[r, c]

    # Diagonal corner barrier test: (1,1) to (2,2) blocked when (1,2) and (2,1) are both False
    diag_trav = np.ones((4, 4), dtype=bool)
    diag_trav[1, 2] = False
    diag_trav[2, 1] = False
    diag_trav[0, 2] = False
    diag_trav[3, 1] = False  # Separate top-left from bottom-right completely except diagonal? No, sealed!
    diag_grid = _build_synthetic_grid(diag_trav)
    from app.routing.graph import RoutePlanningError

    with pytest.raises(RoutePlanningError):
        solve_grid_leg(diag_grid, (1, 1), (2, 2), policy, algorithm=PathAlgorithm.ASTAR)

    # Independent return planner must report RETURN_ROUTE_BLOCKED if reverse path fails, never fake 2*d/v
    class _FailingReturnRouter:
        def compute_route(self, req):
            raise RuntimeError("Return corridor blocked by steep slope cliff.")

    v0 = RouteVertex(
        seq=0, lat=-4.600, lon_east=137.400, elevation_m=-4500.0, slope_deg=2.0, cumulative_distance_m=0.0, segment_distance_m=0.0
    )
    v1 = RouteVertex(
        seq=1, lat=-4.601, lon_east=137.402, elevation_m=-4490.0, slope_deg=4.0, cumulative_distance_m=120.0, segment_distance_m=120.0
    )
    outbound = RouteComputeResponse.model_construct(
        route_id="syn_out_1",
        dataset_id="syn_dem",
        crs="IAU2000:49900",
        mode=RoutingMode.BALANCED,
        algorithm=PathAlgorithm.ASTAR,
        vertices=[v0, v1],
        total_horizontal_distance_m=120.0,
        total_surface_distance_m=120.4,
        total_elevation_gain_m=10.0,
        total_elevation_loss_m=0.0,
        max_slope_deg=4.0,
        mean_slope_deg=3.0,
    )
    ret_rep = plan_eva_return_route(
        routing_service=_FailingReturnRouter(),
        dataset_id="syn_dem",
        outbound_route=outbound,
        walking_speed_mps=1.0,
        use_tobler_grade_approximation=True,
        stop_dwell_total_s=0.0,
        operational_overhead_s=0.0,
        usable_budget_s=1000.0,
        compute_reverse_return_route=True,
    )
    assert ret_rep.return_status == ReturnPlanStatus.RETURN_COMPUTATION_FAILED
    assert ret_rep.return_route_computed is False


# ---------------------------------------------------------------------------
# 7. Target Registry Epistemic Fix & Investigation Reassessment Idempotency [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_unknown_instrument_downgrade_and_reassessment_dedup(tmp_path: Path):
    """Verify unknown instruments never promote to CONFIRMED_LOCAL_OBSERVATION and duplicate archive comparisons deduplicate."""
    rec = SimpleNamespace(
        evidence_id="ev_unknown_1",
        target_id="t_unknown_1",
        dataset_id="ds_unknown",
        instrument_id="UNKNOWN_ORBITER_X",
        product_id="PROD_1",
        species="SiO2",
        evidence_type="direct_mineral_detection",
    )
    state = _classify_evidence_state_from_records([rec])
    assert state == InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY

    # Check ScienceInvestigationService.compare_observation_with_archive reassessment deduplication
    from app.services.container import (
        catalog_service,
        composition_index,
        composition_search_service,
        evidence_intelligence_service,
        routing_service,
        target_registry,
    )

    svc = ScienceInvestigationService(
        processed_dir=tmp_path,
        catalog_service=catalog_service,
        composition_search_service=composition_search_service,
        composition_index=composition_index,
        routing_service=routing_service,
        evidence_service=evidence_intelligence_service,
        target_registry=target_registry,
    )
    q = svc.list_questions()[0]
    cid = f"camp_p23_{uuid.uuid4().hex[:6]}"
    plan = ScienceCampaignPlan(
        campaign_id=cid,
        campaign_name="P23 Synthetic Dedup Check",
        question=q,
        dataset_id="hirise_dteec_009149_1750",
        study_region="Gale Crater",
        plan_status=CampaignPlanStatus.PARTIAL_MISSING_OBSERVATIONS,
        dependency_signature="p23_sig_001",
        request=CampaignBuildRequest(
            campaign_id=cid,
            question_id=q.question_id,
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=-4.72, lon_east=137.41),
        ),
        provenance_graph=ProvenanceDependencyGraph(
            output_id=cid,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            method="synthetic_test_fixture",
            algorithm_version="1.0",
        ),
        stop_plans=[
            CampaignStopPlan(
                stop_index=0,
                stop_id="stop_1",
                target_id="tgt_1",
                name="Target 1",
                latitude=-4.72,
                longitude_east=137.41,
                evidence_state=InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY,
                dwell_s=300.0,
                observation_plan=ObservationActionPlan(
                    stop_id="stop_1",
                    target_id="tgt_1",
                    target_name="Target 1",
                    expected_dwell_s=300.0,
                    recommended_instruments=["ChemCam_LIBS"],
                    measurements_to_collect=["SiO2 wt%"],
                ),
                sampling_protocol=SamplingProtocolSpec(
                    stop_id="stop_1",
                    target_id="tgt_1",
                    sample_type="bedrock_chip",
                    eligibility_state="DEFERRED_PENDING_IN_SITU_SCREENING",
                    scientific_rationale="Screening required prior to sampling.",
                ),
            )
        ],
    )
    svc._save_campaign(plan)
    obs = svc.record_observation(
        RecordObservationRequest(
            campaign_id=cid,
            stop_id="stop_1",
            target_id="tgt_1",
            instrument_id="ChemCam_LIBS",
            measurement_type="elemental_oxide_wt_pct",
            species_or_feature="SiO2",
            measured_value=48.0,
            units="wt%",
            latitude=-4.72,
            longitude_east=137.41,
            notes="Silica enrichment observed in fracture halo.",
        )
    )
    svc.compare_observation_with_archive(obs.observation_id)
    svc.compare_observation_with_archive(obs.observation_id)
    updated = svc.get_campaign(cid)
    assert updated is not None
    assert len(updated.hypothesis_reassessments) == 1
    assert updated.integrated_lifecycle_state in {
        IntegratedMissionLifecycleState.HYPOTHESIS_REASSESSMENT,
        IntegratedMissionLifecycleState.REPLAN_IF_REQUIRED,
    }


# ---------------------------------------------------------------------------
# 8. Readiness Separation, Contextual Blocking, POSIX Lock Guard & Live API [SYNTHETIC_REFERENCE_FIXTURE]
# ---------------------------------------------------------------------------


def test_p23_readiness_clean_state_separation_contextual_and_lock_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """
    Verify evaluate_system_readiness strictly distinguishes:
      - application_health (HEALTHY when libraries & stores are readable)
      - spatial/mission/data/science readiness (False when local DEMs/index are missing)
      - execution_readiness (always UNAVAILABLE with no live telemetry/certification)
    """
    mock_catalog = SimpleNamespace(
        audit_dataset_readiness=lambda **kwargs: {
            "total_catalog_datasets": 12,
            "mandatory_gale_ready": False,
            "lifecycle_state_counts": {"NOT_ACQUIRED": 12},
            "datasets": [
                {
                    "dataset_id": "hirise_dteec_009149_1750",
                    "lifecycle_state": "NOT_ACQUIRED",
                    "raw_file_exists": False,
                    "processed_artifact_exists": False,
                    "processing_manifest_valid": False,
                }
            ],
        }
    )
    mock_comp = SimpleNamespace(
        get_status=lambda: SimpleNamespace(index_available=False, checksum_valid=False, active_generation_id=None)
    )
    mock_sci = SimpleNamespace(
        list_questions=lambda: [SimpleNamespace(question_id="gale_boxwork_origin")],
        list_instruments=lambda: [SimpleNamespace(instrument_id="APXS")],
        list_campaigns=lambda **kwargs: [],
        list_observations=lambda: [],
    )
    mock_eva = SimpleNamespace(list_sessions=lambda: [])
    mock_morph = SimpleNamespace(review_store=SimpleNamespace(load_all=lambda: {}))
    mock_reg = SimpleNamespace(list_targets=lambda: [])

    clean_res = evaluate_system_readiness(
        catalog_service=mock_catalog,
        composition_index=mock_comp,
        science_investigation_service=mock_sci,
        eva_operations_service=mock_eva,
        morphology_service=mock_morph,
        target_registry=mock_reg,
        settings=settings,
        dataset_id="hirise_dteec_009149_1750",
        question_id="gale_boxwork_origin",
    )
    assert clean_res["application_health"]["healthy"] is True
    assert clean_res["application_health"]["status"] == "HEALTHY"
    assert clean_res["execution_readiness"]["ready"] is False
    assert clean_res["execution_readiness"]["status"] == "UNAVAILABLE"
    assert clean_res["system_readiness_state"] == "READY_WITH_DATA_GAPS"
    assert clean_res["pillars"]["data"]["ready"] is False
    assert clean_res["pillars"]["science"]["ready"] is False
    assert clean_res["pillars"]["science"]["definition_store_ready"] is True
    assert clean_res["pillars"]["spatial"]["ready"] is False
    assert clean_res["pillars"]["spatial"]["libraries_ready"] is True
    assert clean_res["pillars"]["mission"]["ready"] is False
    assert clean_res["pillars"]["mission"]["physics_model_ready"] is True
    assert clean_res["context"]["contextual_ready"] is False
    assert len(clean_res["context"]["contextual_blockers"]) == 2

    # POSIX file lock unavailability guard
    monkeypatch.setattr(persistence, "fcntl", None)
    with pytest.raises(RuntimeError, match="POSIX file locking"):
        with persistence.locked_resource(tmp_path / "state.lock"):
            pass


def test_p23_live_readiness_endpoint_speed_and_honesty():
    """Verify GET /api/health/readiness completes rapidly (< 3s) with contextual params & separates execution."""
    import time

    client = TestClient(app)
    t0 = time.perf_counter()
    res = client.get("/api/health/readiness?verify_checksums=false&dataset_id=nonexistent_dem&question_id=gale_boxwork_origin")
    dt = time.perf_counter() - t0
    assert res.status_code == 200
    assert dt < 3.0
    body = res.json()
    assert body["operational_safety_certified"] is False
    assert body["execution_readiness"]["status"] == "UNAVAILABLE"
    assert body["context"]["contextual_ready"] is False
