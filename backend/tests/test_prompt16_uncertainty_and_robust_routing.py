"""
PROMPT 16 VERIFICATION SUITE
Uncertainty-Aware Traversability, Robust Route Optimization,
7-Scale Nyquist Feature Observability, Data Complementarity &
Independent EVA Return Planning Engine.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.evidence_intelligence.schemas import CacheValidityState
from app.eva_operations.return_planning import plan_eva_return_route
from app.eva_operations.schemas import ReturnPlanStatus
from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.main import app
from app.routing.graph import build_terrain_grid_from_dataset
from app.routing.models import RouteObjective, RoutingMode
from app.routing.schemas import (
    RobustRouteCompareRequest,
    RouteComputeRequest,
    RouteCoordinateInput,
    RoutePlanningConstraints,
)
from app.science.complementarity import evaluate_data_complementarity
from app.schemas.dataset import Dataset, DatasetLifecycleStatus
from app.services.container import (
    PROCESSED_DIR,
    RAW_DIR,
    catalog_service,
    evidence_intelligence_service,
    routing_service,
)
from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty
from app.terrain_uncertainty.models import (
    AnalysisScaleCategory,
    FeatureObservabilityState,
    TerrainTraversabilityState,
    UncertaintyStatus,
)
from app.terrain_uncertainty.registration_uncertainty import assess_cross_dataset_registration
from app.terrain_uncertainty.resolution_analysis import evaluate_feature_observability
from app.terrain_uncertainty.roughness_uncertainty import propagate_tri_roughness_uncertainty
from app.terrain_uncertainty.sensitivity import RouteStabilityStatus
from app.terrain_uncertainty.slope_uncertainty import propagate_horn_slope_uncertainty
from app.terrain_uncertainty.uncertainty_propagation import classify_three_state_traversability_grid

MARS_IAU_CRS = CRS.from_proj4(MARS_CRS_DEFINITIONS["IAU2000:49900"])
client = TestClient(app)


def _write_test_geotiff(
    path: Path,
    elev: np.ndarray,
    *,
    dtype: str = "float32",
    nodata: float = -32768.0,
    origin_lon: float = 137.390,
    origin_lat_top: float = -4.740,
    pixel_deg: float = 0.000017,  # ~1.0 m at Mars equator
) -> Path:
    h, w = elev.shape
    transform = from_origin(origin_lon, origin_lat_top, pixel_deg, pixel_deg)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=dtype,
        crs=MARS_IAU_CRS,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(elev.astype(dtype), 1)
    return path


def _make_dataset_stub(
    ds_id: str,
    product_id: str,
    local_path: Path,
    res_m: float = 1.0,
    vertical_res_m: Optional[float] = None,
) -> Dataset:
    template = catalog_service.get_dataset("hirise_dteec_009149_1750")
    assert template is not None
    return template.model_copy(
        update={
            "id": ds_id,
            "product_id": product_id,
            "product_title": f"Synthetic {product_id}",
            "horizontal_resolution_meters": res_m,
            "vertical_resolution_meters": vertical_res_m,
            "coordinate_reference_system": "IAU2000:49900",
            "status": DatasetLifecycleStatus.PROCESSED,
            "local_file_path": str(local_path),
            "local_label_path": None,
            "processed_file_path": str(local_path),
        }
    )


# ---------------------------------------------------------------------------
# 13.1 Elevation & PDS3 Metadata Uncertainty Inspection (Zero Fabrication)
# ---------------------------------------------------------------------------


def test_dataset_uncertainty_never_fabricates_numeric_sigma_without_metadata(tmp_path: Path) -> None:
    arr = np.linspace(-3950.0, -3920.0, 25 * 25, dtype=np.float32).reshape(25, 25)
    f32_path = _write_test_geotiff(tmp_path / "synth_f32.tif", arr, dtype="float32")
    ds_f32 = _make_dataset_stub("synth_f32", "DTEEC_009149_1750_TEST", f32_path, res_m=1.0)

    prof_f32 = inspect_dataset_elevation_uncertainty(
        dataset=ds_f32, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR
    )
    assert prof_f32.overall_elevation_uncertainty_status == UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED
    assert prof_f32.has_per_pixel_error_raster is False
    assert prof_f32.is_integer_quantized is False
    # Must never fabricate a numeric vertical precision value when metadata/error raster is absent
    assert all(
        m.value is None
        for m in prof_f32.elevation_uncertainty_metrics
        if m.metric_name != "horizontal_grid_spacing"
    )
    assert any("per-pixel" in f.lower() or "vertical" in f.lower() or "empirical" in f.lower() for f in prof_f32.missing_uncertainty_fields)

    # Quantized int16 TIFF exposes strict half-LSB quantization floor without inventing stereo error
    int_path = _write_test_geotiff(
        tmp_path / "synth_i16.tif",
        np.round(arr).astype(np.int16),
        dtype="int16",
        nodata=-32768,
    )
    ds_i16 = _make_dataset_stub("synth_i16", "SYNTH_INT16", int_path, res_m=463.0)
    prof_i16 = inspect_dataset_elevation_uncertainty(
        dataset=ds_i16, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR
    )
    assert prof_i16.overall_elevation_uncertainty_status == UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY
    assert prof_i16.is_integer_quantized is True
    assert prof_i16.has_per_pixel_error_raster is False
    assert any(
        m.metric_name == "elevation_quantization_step" and math.isclose(m.value or 0.0, 1.0, rel_tol=1e-6)
        for m in prof_i16.elevation_uncertainty_metrics
    )
    assert any(
        m.metric_name == "quantization_uniform_standard_deviation" and (m.value or 0.0) > 0.28
        for m in prof_i16.elevation_uncertainty_metrics
    )

    # Real local HiRISE Gale Crater DTM check via endpoint
    r = client.get("/api/terrain-uncertainty/dataset/hirise_dteec_009149_1750")
    assert r.status_code == 200, r.text
    real_prof = r.json()
    assert real_prof["dataset_id"] == "hirise_dteec_009149_1750"
    assert real_prof["has_per_pixel_error_raster"] is False
    assert real_prof["overall_elevation_uncertainty_status"] in (
        UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED.value,
        UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY.value,
        UncertaintyStatus.QUANTIFIED_FROM_METADATA.value,
    )


# ---------------------------------------------------------------------------
# 13.2 Analytical Horn 3x3 Slope & TRI Roughness Uncertainty Propagation
# ---------------------------------------------------------------------------


def test_horn_slope_and_tri_uncertainty_propagation_analytical_and_nan_safe() -> None:
    # Planar slope: z = 0.25 * x -> gx = 0.25, gy = 0.0 -> slope = atan(0.25) ~= 14.036 deg
    rows, cols = 15, 15
    dx, dy = 1.0, 1.0
    xs = np.arange(cols, dtype=np.float64)[None, :]
    elev = np.repeat(0.25 * xs, rows, axis=0)
    sigma_z = np.full_like(elev, 0.4)

    slope_deg, slope_sigma_deg, summary = propagate_horn_slope_uncertainty(elev, dx, dy, sigma_z_m=sigma_z)
    center_slope = float(slope_deg[7, 7])
    center_sigma = float(slope_sigma_deg[7, 7])

    assert math.isclose(center_slope, math.degrees(math.atan(0.25)), abs_tol=1e-4)
    # Analytical check for isotropic sigma_z = 0.4 m on Horn 3x3 gx weights sum-squares = 12/64 = 3/16
    expected_var_gx = 0.16 * (12.0 / 64.0)
    g2 = 0.25 ** 2
    expected_sigma_deg = math.degrees(math.sqrt(expected_var_gx) / (1.0 + g2))
    assert math.isclose(center_sigma, expected_sigma_deg, rel_tol=1e-4)
    assert summary.status == UncertaintyStatus.QUANTIFIED_FROM_METADATA

    # Inject a NaN into [7, 7]: the 3x3 stencil [6:9, 6:9] must become NaN cleanly
    elev_nan = elev.copy()
    elev_nan[7, 7] = np.nan
    s_nan, sig_nan, _ = propagate_horn_slope_uncertainty(elev_nan, dx, dy, sigma_z_m=sigma_z)
    assert np.all(np.isnan(s_nan[6:9, 6:9]))
    assert np.all(np.isnan(sig_nan[6:9, 6:9]))
    assert np.isfinite(sig_nan[2, 2])

    # TRI uncertainty propagation: unquantified -> all NaN sigma grid; finite -> propagated sigma grid
    _tri0, tri_sig_none, _m0, tri_sum_none = propagate_tri_roughness_uncertainty(elev, dx, dy, sigma_z_m=None)
    assert tri_sum_none.status == UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED
    assert np.all(np.isnan(tri_sig_none))
    _tri1, tri_sig_fin, _m1, tri_sum_fin = propagate_tri_roughness_uncertainty(elev, dx, dy, sigma_z_m=sigma_z)
    assert tri_sum_fin.status == UncertaintyStatus.QUANTIFIED_FROM_METADATA
    assert np.isfinite(tri_sig_fin[7, 7]) and float(tri_sig_fin[7, 7]) > 0.0

    # Three-state traversability classification: 0=UNKNOWN, 1=EVALUATED, 2=KNOWN_CONSTRAINT_EXCLUSION
    elev_t = np.array([[100.0, 100.0, 100.0, np.nan]], dtype=np.float64)
    slopes = np.array([[5.0, 19.2, 22.5, np.nan]], dtype=np.float64)
    states, breakdown = classify_three_state_traversability_grid(
        elev_t, slopes, max_slope_deg=20.0, dem_resolution_m=1.0
    )
    assert states.tolist() == [[1, 1, 2, 0]]
    assert breakdown.evaluated_cell_count == 2
    assert breakdown.known_exclusion_cell_count == 1
    assert breakdown.unknown_insufficient_cell_count == 1
    assert TerrainTraversabilityState.UNKNOWN_INSUFFICIENTLY_OBSERVED in breakdown.traversability_states_present

    # Coarse DEM (463m MOLA) must NOT classify local traversability -> all UNKNOWN (0)
    states_coarse, bd_coarse = classify_three_state_traversability_grid(
        elev_t, slopes, max_slope_deg=20.0, dem_resolution_m=463.0
    )
    assert np.all(states_coarse == 0)
    assert bd_coarse.unknown_insufficient_cell_count == 4


# ---------------------------------------------------------------------------
# 13.3 7-Scale Nyquist Feature Observability & Negative-Evidence Guard
# ---------------------------------------------------------------------------


def test_seven_scale_observability_prohibits_zero_hazard_absence_claim() -> None:
    records, neg_stmt = evaluate_feature_observability(
        dem_dataset_id="hirise_dteec_009149_1750",
        dem_resolution_m=1.01,
        optical_dataset_id="hirise_esp_018854_1755_red",
        optical_resolution_m=0.25,
    )
    by_cat = {r.category: r for r in records}
    assert len(by_cat) == 7

    assert by_cat[AnalysisScaleCategory.SMALL_OBSTACLE_HAZARD].observability_state == (
        FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
    )
    assert by_cat[AnalysisScaleCategory.SMALL_OBSTACLE_HAZARD].negative_evidence_permitted is False

    assert by_cat[AnalysisScaleCategory.CANDIDATE_BOULDER_FEATURE].observability_state == (
        FeatureObservabilityState.NOT_VALIDATED
    )
    assert by_cat[AnalysisScaleCategory.CANDIDATE_BOULDER_FEATURE].negative_evidence_permitted is False

    assert by_cat[AnalysisScaleCategory.LOCAL_SLOPE].observability_state == (
        FeatureObservabilityState.RESOLVED_FOR_ANALYSIS
    )
    assert neg_stmt.zero_detections_implies_obstacle_free is False
    assert "0.15" in neg_stmt.statement or "0.25" in neg_stmt.statement


def test_corridor_uncertainty_and_complementarity_preserve_quarantine() -> None:
    ds_dem = catalog_service.get_dataset("hirise_dteec_009149_1750")
    assert ds_dem is not None
    reg = assess_cross_dataset_registration(dem_dataset=ds_dem)
    assert reg.overall_status == UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED

    r_cor = client.get(
        "/api/terrain-uncertainty/corridor",
        params={
            "dataset_id": "hirise_dteec_009149_1750",
            "min_lat": -4.753,
            "max_lat": -4.749,
            "min_lon": 137.394,
            "max_lon": 137.398,
            "max_slope_deg": 20.0,
            "grid_size": 65,
        },
    )
    assert r_cor.status_code == 200, r_cor.text
    cor = r_cor.json()
    assert len(cor["observability"]) == 7
    assert cor["negative_evidence"]["zero_detections_implies_obstacle_free"] is False
    bd = cor["traversability_breakdown"]
    assert math.isclose(
        bd["evaluated_fraction"] + bd["known_exclusion_fraction"] + bd["unknown_insufficient_fraction"],
        1.0,
        abs_tol=0.02,
    )

    comp = evaluate_data_complementarity(
        active_dataset_ids=["hirise_dteec_009149_1750", "perseverance_jezero_raw"],
        route_distance_m=500.0,
    )
    assert len(comp.dataset_roles) >= 4
    assert any("quarantined" in c.lower() for c in comp.coverage_caveats)

    r_comp = client.get(
        "/api/terrain-uncertainty/complementarity",
        params={"dataset_ids": "hirise_dteec_009149_1750,perseverance_jezero_raw", "route_distance_m": 450.0},
    )
    assert r_comp.status_code == 200
    assert any("quarantined" in c.lower() for c in r_comp.json()["coverage_caveats"])


# ---------------------------------------------------------------------------
# Hard Constraints vs Soft Science Bonus + 7 Objectives + Decomposition
# ---------------------------------------------------------------------------


def test_soft_science_bonus_never_overrides_hard_slope_constraints(tmp_path: Path) -> None:
    # 25x25 flat grid at 0m with a steep vertical cliff barrier across row 11..13 (cols 0..19)
    elev = np.zeros((25, 25), dtype=np.float32)
    elev[11:14, 0:20] = 60.0  # impassable wall blocking cols 0..19; safe flat gate open on cols 21..24

    tif_path = _write_test_geotiff(tmp_path / "cliff_barrier.tif", elev, dtype="float32")
    ds = _make_dataset_stub("cliff_barrier", "CLIFF_BARRIER_TEST", tif_path, res_m=1.0)

    start = RouteCoordinateInput(lat=-4.740 - 3 * 0.000017, lon_east=137.390 + 5 * 0.000017, label="North")
    dest = RouteCoordinateInput(lat=-4.740 - 21 * 0.000017, lon_east=137.390 + 5 * 0.000017, label="South")
    constraints = RoutePlanningConstraints(max_slope_deg=15.0, snap_radius_m=50.0, max_grid_dim=120)

    grid = build_terrain_grid_from_dataset(
        ds,
        RAW_DIR,
        [(start.lat, start.lon_east), (dest.lat, dest.lon_east)],
        constraints,
        effective_slope_limit_factor=1.0,
    )
    req_sci = RouteComputeRequest(
        dataset_id=ds.id,
        start=start,
        destination=dest,
        mode=RoutingMode.SCIENCE_PRIORITY,
        objective=RouteObjective.SCIENCE_CORRIDOR,
        constraints=constraints,
        exclude_optical_candidates_from_science_bonus=True,
    )
    rt = routing_service.compute_route(
        req_sci,
        override_grid=grid,
        override_dataset_id=ds.id,
        override_product_id=ds.product_id,
    )
    assert rt.max_slope_deg <= 15.0 + 0.1
    assert rt.cost_decomposition is not None
    assert rt.cost_decomposition.unverified_optical_candidates_excluded is True
    assert rt.traversability_summary is not None
    assert rt.traversability_summary.unknown_insufficient_cell_count >= 0
    # Verify route detoured around the eastern open gate instead of crossing cliff
    assert max(v.lon_east for v in rt.vertices) > 137.390 + 18 * 0.000017


# ---------------------------------------------------------------------------
# 13.4 Distinct Candidate Generation & Single-Corridor Bottleneck Detection
# ---------------------------------------------------------------------------


def test_single_corridor_bottleneck_detection_never_fakes_duplicate_alternatives(tmp_path: Path) -> None:
    # 25x25 grid with an impassable cliff across rows 11..13 except a single 2-cell corridor at cols 12..13
    elev = np.zeros((25, 25), dtype=np.float32)
    elev[11:14, 0:11] = 80.0
    elev[11:14, 14:25] = 80.0
    tif_path = _write_test_geotiff(tmp_path / "bottleneck.tif", elev, dtype="float32")
    ds = _make_dataset_stub("bottleneck_ds", "BOTTLENECK_TEST", tif_path, res_m=1.0)

    start = RouteCoordinateInput(lat=-4.740 - 3 * 0.000017, lon_east=137.390 + 12 * 0.000017, label="S")
    dest = RouteCoordinateInput(lat=-4.740 - 21 * 0.000017, lon_east=137.390 + 12 * 0.000017, label="D")
    constraints = RoutePlanningConstraints(max_slope_deg=15.0, snap_radius_m=40.0, max_grid_dim=120)

    grid = build_terrain_grid_from_dataset(
        ds,
        RAW_DIR,
        [(start.lat, start.lon_east), (dest.lat, dest.lon_east)],
        constraints,
        effective_slope_limit_factor=1.0,
    )
    cmp_req = RobustRouteCompareRequest(
        dataset_id=ds.id,
        start=start,
        destination=dest,
        objectives=[
            RouteObjective.BALANCED_MULTIOBJECTIVE,
            RouteObjective.LOWEST_SLOPE,
            RouteObjective.LOWEST_CLIMB_ENERGY,
        ],
        constraints=constraints,
        min_distinct_separation_fraction=0.15,
    )
    res = routing_service.compute_robust_comparison(
        cmp_req,
        override_grid=grid,
        override_dataset_id=ds.id,
        override_product_id=ds.product_id,
    )
    assert res.alternative_generation_status == "SINGLE_CORRIDOR_BOTTLENECK"
    assert res.distinct_candidate_count == 1
    assert res.duplicate_candidates_rejected >= 1


def test_real_hirise_robust_compare_and_sensitivity_endpoints() -> None:
    r_obj = client.get("/api/routing/objectives")
    assert r_obj.status_code == 200
    objs = r_obj.json()["objectives"]
    assert len(objs) == 7

    payload = {
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.749, "lon_east": 137.394, "label": "Start"},
        "destination": {"lat": -4.753, "lon_east": 137.396, "label": "Boxwork"},
        "objectives": [
            "BALANCED_MULTIOBJECTIVE",
            "LOWEST_SLOPE",
            "LOWEST_CLIMB_ENERGY",
            "SHORTEST_TRAVERSABLE",
        ],
        "constraints": {
            "max_slope_deg": 20.0,
            "walking_speed_m_per_s": 0.9,
            "return_to_start": False,
        },
        "include_sensitivity": True,
        "include_independent_return": True,
    }
    r_cmp = client.post("/api/routing/robust-compare", json=payload)
    assert r_cmp.status_code == 200, r_cmp.text
    data = r_cmp.json()
    assert data["distinct_candidate_count"] >= 1
    assert data["recommended_candidate_id"] is not None
    cands = data["candidates"]
    primary = cands[0]
    assert primary["route"]["cost_decomposition"] is not None
    assert primary["route"]["traversability_summary"] is not None
    assert primary["sensitivity_summary"] is not None
    assert primary["sensitivity_summary"]["evaluated_scenario_count"] >= 3

    rid = primary["route"]["route_id"]
    r_sens = client.get(f"/api/routing/{rid}/sensitivity")
    assert r_sens.status_code == 200, r_sens.text
    sens = r_sens.json()
    assert sens["baseline_route_id"] == rid
    assert sens["stability_status"] in (
        RouteStabilityStatus.STABLE_ACROSS_EVALUATED_SCENARIOS.value,
        RouteStabilityStatus.CHANGES_ACROSS_EVALUATED_SCENARIOS.value,
    )


# ---------------------------------------------------------------------------
# 13.5 Independent Return Separation, Turnback PONR & EVA Endpoint
# ---------------------------------------------------------------------------


def test_independent_return_separation_and_asymmetric_ponr(tmp_path: Path) -> None:
    # Asymmetric gentle incline ramp going west -> east (~14.0 deg climb eastbound; downhill westbound)
    elev = np.zeros((25, 25), dtype=np.float32)
    for c in range(25):
        elev[:, c] = float(c) * 0.25

    tif_path = _write_test_geotiff(tmp_path / "asymmetric_ramp.tif", elev, dtype="float32")
    ds = _make_dataset_stub("asym_ramp", "ASYM_RAMP_TEST", tif_path, res_m=1.0)

    start = RouteCoordinateInput(lat=-4.740 - 12 * 0.000017, lon_east=137.390 + 2 * 0.000017, label="Base")
    dest = RouteCoordinateInput(lat=-4.740 - 12 * 0.000017, lon_east=137.390 + 20 * 0.000017, label="Rim")
    constraints = RoutePlanningConstraints(
        max_slope_deg=20.0,
        walking_speed_m_per_s=1.0,
        simplification_epsilon_m=0.0,
        max_grid_dim=120,
    )

    grid = build_terrain_grid_from_dataset(
        ds,
        RAW_DIR,
        [(start.lat, start.lon_east), (dest.lat, dest.lon_east)],
        constraints,
        effective_slope_limit_factor=1.0,
    )
    out_req = RouteComputeRequest(
        dataset_id=ds.id,
        start=start,
        destination=dest,
        mode=RoutingMode.BALANCED,
        objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
        constraints=constraints,
    )
    out_rt = routing_service.compute_route(
        out_req, override_grid=grid, override_dataset_id=ds.id, override_product_id=ds.product_id
    )

    # 1. Opt-out -> explicitly REVERSED_OUTBOUND_REFERENCE_ONLY, return_route_computed=False
    ref_plan = plan_eva_return_route(
        routing_service=routing_service,
        dataset_id=ds.id,
        outbound_route=out_rt,
        walking_speed_mps=1.0,
        use_tobler_grade_approximation=True,
        usable_budget_s=120.0,
        stop_dwell_total_s=0.0,
        operational_overhead_s=0.0,
        compute_reverse_return_route=False,
    )
    assert ref_plan.return_route_computed is False
    assert ref_plan.return_status == ReturnPlanStatus.REVERSED_OUTBOUND_REFERENCE_ONLY
    assert ref_plan.feasible_within_usable_budget is None

    # 2. Independent solver + checkpoint reverse-Dijkstra PONR on asymmetric ramp
    ind_ret, ret_alts, checkpoints = routing_service.compute_independent_return_with_checkpoints(
        dataset_id=ds.id,
        outbound_route=out_rt,
        walking_speed_mps=1.0,
        use_tobler_grade_approximation=True,
        stop_dwell_total_s=0.0,
        operational_overhead_s=0.0,
        usable_budget_s=60.0,
        override_grid=grid,
    )
    # Climbing eastbound (+) vs returning downhill (-): outbound gain >> return gain
    assert out_rt.total_elevation_gain_m > ind_ret.total_elevation_gain_m + 2.0
    assert len(checkpoints) >= 2
    assert any(cp.return_route_computed for cp in checkpoints)

    # 3. Live EVA endpoint evaluation + independent return-analysis API
    eva_eval = client.post(
        "/api/eva-operations/mission/evaluate",
        json={
            "mission_name": "Prompt 16 Live Return Check",
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.394, "label": "Origin"},
            "destination": {"lat": -4.753, "lon_east": 137.396, "label": "Target"},
            "walking_speed_mps": 0.9,
            "mission_duration_limit_s": 14400.0,
            "return_reserve_fraction": 0.25,
            "compute_reverse_return_route": True,
        },
    )
    assert eva_eval.status_code == 200, eva_eval.text
    mid = eva_eval.json()["mission_id"]

    r_ret = client.get(f"/api/eva-operations/mission/{mid}/return-analysis")
    assert r_ret.status_code == 200, r_ret.text
    ret_json = r_ret.json()
    assert ret_json["mission_id"] == mid
    assert ret_json["return_status"] == ReturnPlanStatus.INDEPENDENT_RETURN_COMPUTED.value
    assert ret_json["return_route_computed"] is True
    assert len(ret_json["turnback_checkpoints"]) >= 2


# ---------------------------------------------------------------------------
# Evidence Dependency Trace, Cache Staleness & PNG Uncertainty Overlays
# ---------------------------------------------------------------------------


def test_evidence_dependency_trace_and_prompt16_png_overlays() -> None:
    resp = client.post(
        "/api/evidence-intelligence/corridor/assess",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.394, "label": "Start"},
            "destination": {"lat": -4.753, "lon_east": 137.396, "label": "Dest"},
            "mode": "balanced",
        },
    )
    assert resp.status_code == 200, resp.text
    aid = resp.json()["assessment_id"]

    r_trace = client.get(f"/api/evidence-intelligence/corridor/{aid}/dependency-trace")
    assert r_trace.status_code == 200, r_trace.text
    trace = r_trace.json()
    sig = trace["stored_dependency_signature"]
    for key in (
        "uncertainty_model_version",
        "resolution_policy_version",
        "traversability_model_version",
        "locomotion_model_version",
        "routing_objectives_version",
        "return_planning_version",
        "sensitivity_policy_version",
        "complementarity_registry_version",
    ):
        assert sig.get(key)

    # Verify version mismatch triggers explicit staleness
    corridor_obj = evidence_intelligence_service.get_corridor_assessment(aid)
    assert corridor_obj is not None and corridor_obj.dependency_signature is not None
    sig_obj = corridor_obj.dependency_signature
    stale_sig = sig_obj.model_copy(update={"traversability_model_version": "traversability_v0_stale"})
    status, reasons = evidence_intelligence_service._compare_signature_against_current(stale_sig)
    assert status == CacheValidityState.STALE
    assert any("traversability" in r.lower() for r in reasons)

    # Verify terrain manifest exposes Prompt 16 overlay legends
    r_man = client.get("/api/terrain/mesh/manifest?dataset_id=hirise_dteec_009149_1750&max_lod=1&tile_grid_size=33")
    assert r_man.status_code == 200, r_man.text
    legends = r_man.json().get("overlay_legends", {})
    for overlay in ("uncertainty_status", "traversability_state", "observability", "slope_uncertainty_probe"):
        assert overlay in legends

    # Verify PNG rendering for uncertainty overlays + threshold responsiveness
    r_u = client.get(
        "/api/terrain-uncertainty/overlay.png",
        params={
            "dataset_id": "hirise_dteec_009149_1750",
            "overlay": "traversability_state",
            "min_lat": -4.754,
            "max_lat": -4.748,
            "min_lon": 137.392,
            "max_lon": 137.398,
            "size": 128,
            "max_slope_deg": 8.0,
        },
    )
    assert r_u.status_code == 200
    assert r_u.headers["content-type"] == "image/png"
    img_strict = np.array(Image.open(io.BytesIO(r_u.content)))

    r_u2 = client.get(
        "/api/terrain-uncertainty/overlay.png",
        params={
            "dataset_id": "hirise_dteec_009149_1750",
            "overlay": "traversability_state",
            "min_lat": -4.754,
            "max_lat": -4.748,
            "min_lon": 137.392,
            "max_lon": 137.398,
            "size": 128,
            "max_slope_deg": 35.0,
        },
    )
    assert r_u2.status_code == 200
    img_lenient = np.array(Image.open(io.BytesIO(r_u2.content)))
    assert not np.array_equal(img_strict, img_lenient)

    # Verify default 256x256 rendering for all 4 Prompt 16 overlays via both endpoints
    for ov in ("uncertainty_status", "traversability_state", "observability", "slope_uncertainty_probe"):
        r_ov = client.get(
            "/api/terrain/ortho/hirise_dteec_009149_1750/texture",
            params={
                "overlay": ov,
                "min_lat": -4.754,
                "max_lat": -4.748,
                "min_lon": 137.392,
                "max_lon": 137.398,
                "size": 256,
                "max_slope_deg": 20.0,
            },
        )
        assert r_ov.status_code == 200, f"overlay {ov} failed: {r_ov.text}"
        arr_ov = np.array(Image.open(io.BytesIO(r_ov.content)))
        assert arr_ov.shape == (256, 256, 4)
