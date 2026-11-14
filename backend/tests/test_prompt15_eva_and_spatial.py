"""
PROMPT 15 VERIFICATION SUITE — SPATIALLY EXACT MARSWALK INTELLIGENCE & EVA OPERATIONAL ENVELOPE
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.crs import CRS
from rasterio.transform import from_origin
from shapely.geometry import LineString, Polygon

from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    ExplicitResourceSpec,
    SpeedModelMode,
)
from app.evidence_intelligence.corridor import (
    MarsLocalFrame,
    build_route_corridor,
    determine_segment_scale_info,
    segment_route_by_scale,
)
from app.evidence_intelligence.mission_readiness import (
    READINESS_POLICY,
    evaluate_multidomain_readiness,
)
from app.evidence_intelligence.observation_association import associate_corridor_observations
from app.evidence_intelligence.optical_assessment import assess_corridor_optical_evidence
from app.evidence_intelligence.report import EvidenceIntelligenceService
from app.evidence_intelligence.schemas import (
    CacheValidityState,
    CorridorAssessRequest,
    CorridorSegmentAssessment,
    MissionDossierRequest,
    ObservationAssociationType,
    PhysicalEnergyBudget,
    ProductAvailabilityStatus,
    SegmentCoverageReport,
)
from app.evidence_intelligence.terrain_assessment import assess_corridor_terrain
from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.main import app
from app.routing.schemas import RouteCoordinateInput, RouteVertex, RoutingMode
from app.science.provenance_graph import ScientificDataClassification
from app.services.container import (
    PROCESSED_DIR,
    RAW_DIR,
    catalog_service,
    routing_service,
)
from app.terrain.optical_analysis import evaluate_rounded_feature_eligibility

MARS_IAU_WKT = CRS.from_proj4(MARS_CRS_DEFINITIONS["IAU2000:49900"])
EARTH_WGS84 = CRS.from_epsg(4326)

client = TestClient(app)


def _default_cov(seg_id: str) -> SegmentCoverageReport:
    return SegmentCoverageReport(
        segment_id=seg_id,
        dem_coverage_fraction=1.0,
        valid_elevation_fraction=1.0,
        slope_available=True,
        tri_available=True,
        optical_coverage_fraction=0.0,
        optical_quality_note="synthetic test",
        geological_map_coverage=False,
        spectral_data_available=False,
        thermal_data_available=False,
        rover_observation_count=0,
        panorama_available=False,
        unverified_regions_present=False,
    )


def _write_synthetic_dem(
    path: Path,
    elev: np.ndarray,
    *,
    crs: CRS,
    origin_lon: float = 137.390,
    origin_lat_top: float = -4.740,
    pixel_deg: float = 0.000017,  # ~1.0 m at Mars equator
    nodata: float = -32768.0,
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
        dtype=np.float32,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(elev.astype(np.float32), 1)
    return path


def _write_synthetic_ortho(
    path: Path,
    img: np.ndarray,
    *,
    origin_lon: float,
    origin_lat_top: float,
    pixel_deg: float = 0.0000045,  # ~0.27 m/px
    nodata: int = 0,
) -> Path:
    h, w = img.shape
    transform = from_origin(origin_lon, origin_lat_top, pixel_deg, pixel_deg)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=np.uint8,
        crs=MARS_IAU_WKT,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(img.astype(np.uint8), 1)
    return path


def test_synthetic_mars_crs_validation_and_polygon_masking(tmp_path: Path):
    """
    1. Reject non-Mars EPSG:4326 DEMs when require_verified_crs=True.
    2. Prove corridor terrain metrics strictly mask pixels inside the Shapely corridor polygon,
       so steep hazards outside the corridor but inside the DEM convolution buffer are ignored.
    """
    h, w = 80, 80
    flat_with_outside_cliff = np.full((h, w), -3900.0, dtype=np.float32)
    # Place a steep ~75-deg ridge near row 5..8 (north edge, OUTSIDE central corridor, INSIDE window)
    flat_with_outside_cliff[5:10, :] = -3840.0

    earth_dem = _write_synthetic_dem(
        tmp_path / "earth_wgs84.tif", flat_with_outside_cliff, crs=EARTH_WGS84
    )
    mars_dem = _write_synthetic_dem(
        tmp_path / "mars_iau.tif", flat_with_outside_cliff, crs=MARS_IAU_WKT
    )

    # Central horizontal route at row ~45 (far from row 5..10 ridge)
    pixel_deg = 0.000017
    origin_lon = 137.390
    origin_lat_top = -4.740
    route_lat = origin_lat_top - 45 * pixel_deg
    lon_start = origin_lon + 15 * pixel_deg
    lon_end = origin_lon + 65 * pixel_deg

    vertices = [
        RouteVertex(seq=0, lat=route_lat, lon_east=lon_start, elevation_m=-3900.0, cumulative_distance_m=0.0, segment_distance_m=0.0),
        RouteVertex(seq=1, lat=route_lat, lon_east=lon_end, elevation_m=-3900.0, cumulative_distance_m=50.0, segment_distance_m=50.0),
    ]
    raw_segments = segment_route_by_scale(
        vertices,
        segment_scale_m=60.0,
        corridor_width_m=20.0,
        native_resolution_m=1.0,
    )
    assert len(raw_segments) >= 1

    # Non-Mars Earth EPSG:4326 must be explicitly rejected
    with pytest.raises(ValueError, match="Mars CRS|crs"):
        assess_corridor_terrain(
            dem_path=earth_dem,
            dataset_id="earth_bad",
            source_product_id="EARTH_BAD",
            native_resolution_m=1.0,
            raw_segments=raw_segments,
            corridor_width_m=20.0,
            optical_coverage_fraction=0.0,
            optical_quality_note="none",
            geological_map_coverage=False,
            spectral_data_available=False,
            thermal_data_available=False,
            require_verified_crs=True,
        )

    # Verified Mars CRS passes and corridor mask excludes outside cliff
    segs, candidates, summary = assess_corridor_terrain(
        dem_path=mars_dem,
        dataset_id="mars_synth",
        source_product_id="MARS_SYNTH",
        native_resolution_m=1.0,
        raw_segments=raw_segments,
        corridor_width_m=20.0,
        optical_coverage_fraction=0.0,
        optical_quality_note="none",
        geological_map_coverage=False,
        spectral_data_available=False,
        thermal_data_available=False,
        require_verified_crs=True,
    )
    assert summary["corridor_valid_fraction"] == pytest.approx(1.0, rel=1e-3)
    assert summary["convolution_buffer_px"] >= 1
    assert all((s.max_slope_deg or 0.0) < 1.0 for s in segs)
    assert len(candidates) == 0


def test_segment_geometry_completeness_and_resolution_support():
    """Verify full intermediate segment geometry preservation and no silent 25px resolution clamping."""
    v0 = RouteVertex(seq=0, lat=-4.742, lon_east=137.392, elevation_m=-3910.0, cumulative_distance_m=0.0, segment_distance_m=0.0)
    v1 = RouteVertex(seq=1, lat=-4.7423, lon_east=137.3925, elevation_m=-3908.0, cumulative_distance_m=35.0, segment_distance_m=35.0)
    v2 = RouteVertex(seq=2, lat=-4.7428, lon_east=137.3928, elevation_m=-3905.0, cumulative_distance_m=70.0, segment_distance_m=35.0)
    v3 = RouteVertex(seq=3, lat=-4.7433, lon_east=137.3932, elevation_m=-3902.0, cumulative_distance_m=110.0, segment_distance_m=40.0)

    segs = segment_route_by_scale(
        [v0, v1, v2, v3],
        segment_scale_m=60.0,
        corridor_width_m=40.0,
        native_resolution_m=1.0,
    )
    assert len(segs) >= 2
    for s in segs:
        assert len(s["vertices"]) >= 2
        assert s["geometry_geojson"]["type"] == "LineString"
        assert len(s["corridor_polygon"]) >= 4
        assert s["corridor_area_m2"] > 0.0
        assert s["cumulative_end_m"] > s["cumulative_start_m"]

    # Coarse 20 m/px DEM asked for 15 m segments must NOT silently clamp to 500 m
    scale_m, supportable, note = determine_segment_scale_info(
        native_resolution_m=20.0, requested_scale_m=15.0
    )
    assert scale_m == 15.0
    assert supportable is False
    assert "finer than" in note.lower() or "unsupported" in note.lower()


def test_per_segment_overlapping_optical_union_and_cap(tmp_path: Path):
    """
    Create two overlapping synthetic Mars optical GeoTIFFs:
      - Ortho A covers the western/middle area cleanly (seg 1 + overlap zone)
      - Ortho B overlaps on seg 1 + partial seg 2 with zero (nodata) pixels
    Verify:
      - Overlapping optical products NEVER sum > 1.0 (Shapely/raster union capped <= 1.0)
      - Each segment has independent footprint vs valid-pixel coverage fractions
      - Contributing product IDs are recorded per segment
    """
    px_deg = 0.00001
    origin_lon = 137.390
    origin_lat_top = -4.740

    img_a = np.full((60, 60), 140, dtype=np.uint8)
    ortho_a = _write_synthetic_ortho(
        tmp_path / "ortho_a.tif",
        img_a,
        origin_lon=origin_lon,
        origin_lat_top=origin_lat_top,
        pixel_deg=px_deg,
    )

    # Ortho B starts slightly inside Ortho A (overlap) and has lower half zeroed (nodata)
    img_b = np.full((60, 60), 165, dtype=np.uint8)
    img_b[30:, :] = 0
    ortho_b = _write_synthetic_ortho(
        tmp_path / "ortho_b.tif",
        img_b,
        origin_lon=origin_lon + 20 * px_deg,
        origin_lat_top=origin_lat_top,
        pixel_deg=px_deg,
    )

    mock_ds_a = SimpleNamespace(
        id="ortho_a",
        product_id="ORTHO_A",
        product_type="HiRISE_ORTHO",
        local_file_path=str(ortho_a),
        acquired=True,
        native_resolution_m=0.6,
    )
    mock_ds_b = SimpleNamespace(
        id="ortho_b",
        product_id="ORTHO_B",
        product_type="HiRISE_ORTHO",
        local_file_path=str(ortho_b),
        acquired=True,
        native_resolution_m=0.6,
    )

    class _MockCatalog:
        def get_dataset(self, ds_id: str):
            return {"ortho_a": mock_ds_a, "ortho_b": mock_ds_b}.get(ds_id)

        def get_all_datasets(self):
            return [mock_ds_a, mock_ds_b]

    route_lat = origin_lat_top - 15 * px_deg
    seg1 = CorridorSegmentAssessment(
        segment_id="seg-01",
        segment_index=0,
        start_coord=RouteCoordinateInput(lat=route_lat, lon_east=origin_lon + 10 * px_deg),
        end_coord=RouteCoordinateInput(lat=route_lat, lon_east=origin_lon + 45 * px_deg),
        geodesic_distance_m=21.0,
        surface_distance_m=21.0,
        source_dem_id="synth_dem",
        source_product_id="SYNTH_DEM",
        native_resolution_m=1.0,
        valid_data_coverage_fraction=1.0,
        uncertainty_summary="ok",
        coverage=_default_cov("seg-01"),
    )
    seg2 = CorridorSegmentAssessment(
        segment_id="seg-02",
        segment_index=1,
        start_coord=RouteCoordinateInput(lat=route_lat, lon_east=origin_lon + 65 * px_deg),
        end_coord=RouteCoordinateInput(lat=origin_lat_top - 45 * px_deg, lon_east=origin_lon + 95 * px_deg),
        geodesic_distance_m=25.0,
        surface_distance_m=25.0,
        source_dem_id="synth_dem",
        source_product_id="SYNTH_DEM",
        native_resolution_m=1.0,
        valid_data_coverage_fraction=1.0,
        uncertainty_summary="ok",
        coverage=_default_cov("seg-02"),
    )

    dem_bounds = {
        "min_lat": origin_lat_top - 65 * px_deg,
        "max_lat": origin_lat_top + 5 * px_deg,
        "min_lon": origin_lon - 5 * px_deg,
        "max_lon": origin_lon + 105 * px_deg,
    }
    cands, _, mean_cov, _, meta = assess_corridor_optical_evidence(
        catalog_service=_MockCatalog(),
        raw_dir=tmp_path,
        ortho_dataset_id="ortho_a",
        ortho_dataset_ids=["ortho_a", "ortho_b"],
        dem_bounds=dem_bounds,
        segments=[seg1, seg2],
        corridor_width_m=12.0,
    )
    assert meta["available"] is True
    assert 0.0 <= mean_cov <= 1.0
    assert 0.0 <= seg1.coverage.optical_footprint_coverage_fraction <= 1.0
    assert 0.0 <= seg1.coverage.valid_optical_pixel_coverage_fraction <= 1.0
    assert 0.0 <= seg2.coverage.valid_optical_pixel_coverage_fraction <= 1.0
    assert seg1.coverage.valid_optical_pixel_coverage_fraction > seg2.coverage.valid_optical_pixel_coverage_fraction
    assert "ORTHO_A" in seg1.coverage.optical_contributing_product_ids


def test_strtree_observation_association_and_availability(tmp_path: Path):
    """Verify STRtree spatial association, Perseverance Jezero isolation, and local file verification."""
    local_product = tmp_path / "chemcam_sol4501.tab"
    local_product.write_text("SOL 4501 CHEMCAM VERIFIED", encoding="utf-8")

    seg = CorridorSegmentAssessment(
        segment_id="seg-001",
        segment_index=0,
        start_coord=RouteCoordinateInput(lat=-4.749, lon_east=137.394),
        end_coord=RouteCoordinateInput(lat=-4.749, lon_east=137.396),
        geodesic_distance_m=118.0,
        surface_distance_m=118.0,
        source_dem_id="hirise_dteec_009149_1750",
        source_product_id="DTEEC_009149_1750",
        native_resolution_m=1.0,
        valid_data_coverage_fraction=1.0,
        uncertainty_summary="ok",
        coverage=_default_cov("seg-001"),
    )

    obs_raw = [
        {
            "observation_id": "cur-on-route",
            "mission": "Curiosity",
            "instrument": "ChemCam",
            "sol": 4501,
            "lat": -4.749,
            "lon_east": 137.395,
            "product_id": "CCAM_4501",
            "local_file_path": str(local_product),
        },
        {
            "observation_id": "cur-footprint-hit",
            "mission": "Curiosity",
            "instrument": "Mastcam",
            "sol": 4502,
            "spatial_footprint": {
                "min_lat": -4.7492,
                "max_lat": -4.7488,
                "min_lon": 137.3945,
                "max_lon": 137.3955,
            },
            "product_id": "MCAM_4502",
            "archive_url": "https://pds-imaging.jpl.nasa.gov/fake/MCAM_4502",
        },
        {
            "observation_id": "perc-jezero-leak-check",
            "mission": "Perseverance",
            "instrument": "SuperCam",
            "sol": 1000,
            "lat": -4.749,
            "lon_east": 137.395,
            "product_id": "SCAM_1000",
        },
        {
            "observation_id": "unlocated-obs",
            "mission": "Curiosity",
            "instrument": "SAM",
            "product_id": "SAM_UNLOC",
        },
    ]

    associated = associate_corridor_observations(
        observations_raw=obs_raw,
        segments=[seg],
        search_radius_m=200.0,
        study_region="Gale Crater / Mount Sharp",
        corridor_width_m=60.0,
        raw_dir=tmp_path,
        include_unlocated_diagnostics=True,
    )
    by_id = {o.observation_id: o for o in associated}

    assert "perc-jezero-leak-check" not in by_id
    assert by_id["cur-on-route"].association_type == ObservationAssociationType.INTERSECTS_ROUTE
    assert by_id["cur-on-route"].product_available is True
    assert by_id["cur-on-route"].availability_status == ProductAvailabilityStatus.VERIFIED_LOCAL

    assert by_id["cur-footprint-hit"].association_type == ObservationAssociationType.INTERSECTS_ROUTE
    assert by_id["cur-footprint-hit"].product_available is False
    assert by_id["cur-footprint-hit"].availability_status == ProductAvailabilityStatus.URL_UNVERIFIED

    assert by_id["unlocated-obs"].association_type == ObservationAssociationType.UNLOCATED


def test_optical_candidate_eligibility_gates():
    """Verify multi-criteria eligibility logic rejects tiny/noisy artifacts cleanly."""
    ok_res = evaluate_rounded_feature_eligibility(
        native_pixel_scale_m=0.25,
        diameter_px=6.0,
        valid_pixel_fraction=0.95,
        local_contrast_zscore=2.4,
        image_std_dn=12.0,
        boundary_completeness=0.92,
    )
    assert ok_res["eligible"] is True
    assert ok_res["policy_version"] == "rounded_feature_eligibility_v1"

    bad_scale = evaluate_rounded_feature_eligibility(
        native_pixel_scale_m=0.25,
        diameter_px=2.0,
        valid_pixel_fraction=0.95,
        local_contrast_zscore=3.0,
        image_std_dn=12.0,
        boundary_completeness=0.95,
    )
    assert bad_scale["eligible"] is False

    bad_contrast = evaluate_rounded_feature_eligibility(
        native_pixel_scale_m=0.25,
        diameter_px=8.0,
        valid_pixel_fraction=0.95,
        local_contrast_zscore=0.4,
        image_std_dn=12.0,
        boundary_completeness=0.90,
    )
    assert bad_contrast["eligible"] is False


def test_15_domain_readiness_and_cache_invalidation(tmp_path: Path):
    """
    Verify all 15 readiness domains, explicit separation from human safety certification,
    atomic JSON cache persistence, and CURRENT -> STALE detection when inputs mutate.
    """
    (tmp_path / "hirise_dteec_009149_1750_dem.tif").symlink_to(
        PROCESSED_DIR / "hirise_dteec_009149_1750_dem.tif"
    )
    svc = EvidenceIntelligenceService(
        catalog_service=catalog_service,
        routing_service=routing_service,
        raw_dir=RAW_DIR,
        processed_dir=tmp_path,
    )
    req = CorridorAssessRequest(
        dataset_id="hirise_dteec_009149_1750",
        start=RouteCoordinateInput(lat=-4.749, lon_east=137.394),
        destination=RouteCoordinateInput(lat=-4.753, lon_east=137.396),
        mode=RoutingMode.BALANCED,
        corridor_width_m=60.0,
    )
    corridor = svc.assess_corridor(req)
    assert corridor.cache_validity == CacheValidityState.CURRENT
    assert corridor.dependency_signature is not None

    dossier_incomplete = svc.generate_mission_dossier(
        MissionDossierRequest(
            mission_name="Prompt 15 Readiness Test (Incomplete)",
            dataset_id="hirise_dteec_009149_1750",
            start=req.start,
            destination=req.destination,
            mode=RoutingMode.BALANCED,
        )
    )
    assert len(dossier_incomplete.domain_assessments) == 15
    assert dossier_incomplete.operational_safety_certified is False
    assert dossier_incomplete.mathematical_assessment_complete is False

    dossier = svc.generate_mission_dossier(
        MissionDossierRequest(
            mission_name="Prompt 15 Readiness Test",
            dataset_id="hirise_dteec_009149_1750",
            start=req.start,
            destination=req.destination,
            mode=RoutingMode.BALANCED,
            walking_speed_mps=0.85,
            mission_duration_limit_s=14400.0,
            return_reserve_fraction=0.25,
            astronaut_suit_mass_kg=160.0,
            payload_mass_kg=20.0,
        )
    )
    assert len(dossier.domain_assessments) == 15
    assert dossier.operational_safety_certified is False
    assert dossier.mathematical_assessment_complete is True
    assert dossier.readiness_policy_version == READINESS_POLICY["policy_version"]

    # Mutate stored dependency signature in cached JSON -> reload must detect STALE
    corridor_file = svc.corridor_dir / f"{corridor.assessment_id}.json"
    assert corridor_file.exists()
    data = json.loads(corridor_file.read_text(encoding="utf-8"))
    data["dependency_signature"]["dem_file_checksum"] = "tampered_checksum_000"
    corridor_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    svc._corridor_cache.pop(corridor.assessment_id, None)

    reloaded = svc.get_corridor_assessment(corridor.assessment_id)
    assert reloaded is not None
    assert reloaded.cache_validity == CacheValidityState.STALE
    assert any("dem file checksum" in r.lower() for r in reloaded.stale_reasons)


def test_route_decision_explainer_and_trace_endpoint():
    """Verify RouteDecisionExplainer on /api/routing/compute and /api/evidence-intelligence/corridor/{id}/decision-trace."""
    route_res = client.post(
        "/api/routing/compute",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.394},
            "destination": {"lat": -4.753, "lon_east": 137.396},
            "mode": "balanced",
        },
    )
    assert route_res.status_code == 200
    route_data = route_res.json()
    explainer = route_data.get("decision_explainer")
    assert explainer is not None
    assert explainer["dominant_cost_driver"]
    assert "effective_slope_limit_deg" in explainer["hard_constraints"]
    assert "total_cost_breakdown" in explainer

    corr_res = client.post(
        "/api/evidence-intelligence/corridor/assess",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.394},
            "destination": {"lat": -4.754, "lon_east": 137.398},
            "mode": "balanced",
            "corridor_width_m": 60.0,
        },
    )
    assert corr_res.status_code == 200
    assessment_id = corr_res.json()["assessment_id"]

    trace_res = client.get(f"/api/evidence-intelligence/corridor/{assessment_id}/decision-trace")
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["assessment_id"] == assessment_id
    assert trace_data["route_decision_explainer"] is not None
    assert len(trace_data["segment_resolution_checks"]) >= 1


def test_unit_aware_resource_budget_math_and_mismatch():
    """Verify exact Q_used = Q_dot * t dimensional conversions and UNIT_MISMATCH handling."""
    report = evaluate_eva_resource_budget(
        resources=[
            ExplicitResourceSpec(
                resource_name="oxygen_kg",
                initial_quantity=2.0,
                unit="kg",
                consumption_rate=0.5,
                rate_unit="kg/h",
                reserve_fraction=0.25,
            ),
            ExplicitResourceSpec(
                resource_name="battery_wh",
                initial_quantity=500.0,
                unit="Wh",
                consumption_rate=100.0,
                rate_unit="W",
                reserve_fraction=0.2,
            ),
            ExplicitResourceSpec(
                resource_name="bad_unit_mix",
                initial_quantity=10.0,
                unit="kg",
                consumption_rate=50.0,
                rate_unit="W",
                reserve_fraction=0.0,
            ),
        ],
        exposure_duration_s=7200.0,  # 2 hours -> 1.0 kg O2 (margin +0.5 above 0.5kg res), 200 Wh batt (within 400 Wh usable)
    )
    entries = {e.resource_name: e for e in report.entries}
    assert entries["oxygen_kg"].status == "WITHIN_LIMIT"
    assert entries["oxygen_kg"].estimated_consumed == pytest.approx(1.0, rel=1e-4)
    assert entries["oxygen_kg"].margin_above_reserve == pytest.approx(0.5, rel=1e-4)

    assert entries["battery_wh"].status == "WITHIN_LIMIT"
    assert entries["battery_wh"].estimated_consumed == pytest.approx(200.0, rel=1e-4)
    assert entries["battery_wh"].remaining_after_eva == pytest.approx(300.0, rel=1e-4)

    assert entries["bad_unit_mix"].status == "UNIT_MISMATCH"
    assert report.overall_status == "UNAVAILABLE"


def test_eva_envelope_missing_constraints_vs_complete_and_all_9_endpoints():
    """
    Exercise real HiRISE DEM Gale Crater EVA evaluation:
    1. Missing explicit constraints -> INCOMPLETE_USER_CONSTRAINTS (never invented).
    2. Complete explicit constraints -> all 9 /api/eva-operations/* endpoints return 200 with
       explicit W = m*g*dh+ climb work, asymmetric reverse return route, PONR, and Tobler separation.
    """
    # Step 1: Incomplete user inputs must never fabricate speed/limit/mass
    inc_res = client.post(
        "/api/eva-operations/mission/evaluate",
        json={
            "mission_name": "Incomplete Prompt 15 Check",
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.394},
            "destination": {"lat": -4.754, "lon_east": 137.398},
        },
    )
    assert inc_res.status_code == 200
    inc_data = inc_res.json()
    assert inc_data["envelope_status"] == EnvelopeFeasibilityStatus.INCOMPLETE_USER_CONSTRAINTS.value
    assert inc_data["operational_safety_certified"] is False
    assert len(inc_data["missing_inputs"]) >= 4

    # Step 2: Configure + evaluate with full explicit operational limits
    cfg_payload = {
        "mission_name": "Gale Boxwork Full EVA Plan",
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.749, "lon_east": 137.394},
        "destination": {"lat": -4.754, "lon_east": 137.398},
        "mode": "balanced",
        "corridor_width_m": 60.0,
        "walking_speed_mps": 0.85,
        "use_tobler_grade_approximation": True,
        "mission_duration_limit_s": 14400.0,
        "return_reserve_fraction": 0.25,
        "operational_overhead_s": 300.0,
        "astronaut_suit_mass_kg": 160.0,
        "payload_mass_kg": 20.0,
        "resources": [
            {
                "resource_name": "oxygen_kg",
                "initial_quantity": 4.0,
                "unit": "kg",
                "consumption_rate": 0.2,
                "rate_unit": "kg/h",
                "reserve_fraction": 0.25,
            }
        ],
        "compute_reverse_return_route": True,
    }
    cfg_res = client.post("/api/eva-operations/mission/configure", json=cfg_payload)
    assert cfg_res.status_code == 200
    assert cfg_res.json()["configured"] is True

    eval_res = client.post("/api/eva-operations/mission/evaluate", json=cfg_payload)
    assert eval_res.status_code == 200
    ev = eval_res.json()
    mission_id = ev["mission_id"]

    assert ev["operational_safety_certified"] is False
    assert ev["time_budget"]["speed_model_used"] == SpeedModelMode.TOBLER_STYLE_GRADE_APPROXIMATION.value
    assert ev["return_plan"]["return_route_computed"] is True
    assert len(ev["return_plan"]["return_route_vertices"]) >= 2
    assert ev["return_plan"]["point_of_no_return_distance_m"] > 0.0
    assert ev["energy_budget"]["mars_gravity_m_s2"] == pytest.approx(3.72076, rel=1e-4)
    assert ev["energy_budget"]["total_positive_climb_work_j"] >= 0.0
    assert ev["resource_budget"]["overall_status"] == "WITHIN_CONSTRAINTS"

    # Check mechanical work math: W = m * g * sum(dh+)
    total_mass = 180.0
    total_dh = ev["energy_budget"]["outbound_climb_gain_m"] + ev["energy_budget"]["return_climb_gain_m"]
    expected_work = total_mass * 3.72076 * total_dh
    assert math.isclose(ev["energy_budget"]["total_positive_climb_work_j"], expected_work, rel_tol=1e-2)

    # Verify all remaining 7 GET endpoints under /api/eva-operations/*
    for suffix in (
        "",
        "/schedule",
        "/return-route",
        "/resource-budget",
        "/timeline",
        "/constraints",
        "/provenance",
    ):
        r = client.get(f"/api/eva-operations/mission/{mission_id}{suffix}")
        assert r.status_code == 200, f"GET {suffix} failed: {r.text}"
