"""
Prompt 14 Verification Suite — Marswalk Evidence Intelligence, Terrain Hazard
Characterization, Uncertainty-Aware Routing & Mission Readiness.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

from app.evidence_intelligence.corridor import (
    build_route_corridor,
    determine_segment_scale_m,
    segment_route_by_scale,
)
from app.evidence_intelligence.mission_readiness import compute_physical_energy_budget
from app.evidence_intelligence.observation_association import associate_corridor_observations
from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    ReadinessState,
    SegmentCoverageReport,
)
from app.main import app
from app.routing.schemas import RouteCoordinateInput, RouteVertex
from app.services.container import mobility_service
from app.terrain.optical_analysis import analyze_optical_array

client = TestClient(app)


def test_mobility_capability_consistency():
    status = mobility_service.get_status()
    assert status.route_optimization_enabled == status.capabilities["route_optimization"]


def test_corridor_geometry_and_resolution_segmentation():
    vertices = [
        RouteVertex(seq=0, lat=-4.7500, lon_east=137.3940, elevation_m=-4400.0, segment_distance_m=0.0, cumulative_distance_m=0.0),
        RouteVertex(seq=1, lat=-4.7508, lon_east=137.3946, elevation_m=-4398.0, segment_distance_m=58.0, cumulative_distance_m=58.0),
        RouteVertex(seq=2, lat=-4.7516, lon_east=137.3952, elevation_m=-4395.0, segment_distance_m=58.0, cumulative_distance_m=116.0),
        RouteVertex(seq=3, lat=-4.7524, lon_east=137.3958, elevation_m=-4391.0, segment_distance_m=58.0, cumulative_distance_m=174.0),
    ]
    bounds = {"min_lat": -4.76, "max_lat": -4.74, "min_lon": 137.38, "max_lon": 137.41}
    poly = build_route_corridor(vertices, corridor_width_m=60.0, dem_bounds=bounds)
    assert len(poly.left_boundary) == len(vertices)
    assert len(poly.right_boundary) == len(vertices)
    assert poly.polygon_ring[0] == poly.polygon_ring[-1]
    assert "IAU2000:49900" in poly.projection

    scale_hirise = determine_segment_scale_m(1.0)
    scale_mola = determine_segment_scale_m(463.0)
    assert scale_hirise == 60.0
    assert scale_mola > scale_hirise

    segs = segment_route_by_scale(vertices, segment_scale_m=60.0)
    assert len(segs) >= 2
    assert segs[0]["segment_id"] == "SEG-001"


def test_optical_multiscale_taxonomy_and_false_positive_rejection():
    patch = np.full((64, 64), 120.0, dtype=np.float32)
    # Inject a strong bright block aligned to the 16x16 analysis grid
    patch[17:33, 17:33] = 240.0
    # Inject a dark shadow block
    patch[33:49, 33:49] = 15.0
    # Inject a nodata border region that should not generate false-positive edge candidates
    patch[:, :4] = np.nan

    res_hi = analyze_optical_array(
        patch,
        bounds={"min_lat": -4.752, "max_lat": -4.748, "min_lon": 137.393, "max_lon": 137.397},
        ortho_dataset_id="hirise_test",
        product_id="PSP_TEST_025",
        native_pixel_scale_m=0.25,
        max_candidates=12,
    )
    assert res_hi.available is True
    assert len(res_hi.candidates) >= 1
    assert all(c.validation_state == "candidate_requiring_interpretation" for c in res_hi.candidates)

    # At 2.0 m/px, possible_boulder_feature must NOT be emitted
    res_coarse = analyze_optical_array(
        patch,
        bounds={"min_lat": -4.752, "max_lat": -4.748, "min_lon": 137.393, "max_lon": 137.397},
        ortho_dataset_id="ctx_test",
        product_id="CTX_TEST_2M",
        native_pixel_scale_m=2.0,
        max_candidates=12,
    )
    assert all(c.candidate_type != "possible_boulder_feature" for c in res_coarse.candidates)


def test_observation_association_isolates_perseverance_jezero():
    seg = CorridorSegmentAssessment(
        segment_id="SEG-001",
        segment_index=0,
        start_coord=RouteCoordinateInput(lat=-4.750, lon_east=137.394),
        end_coord=RouteCoordinateInput(lat=-4.751, lon_east=137.395),
        geodesic_distance_m=60.0,
        surface_distance_m=60.2,
        source_dem_id="hirise_dteec_009149_1750",
        source_product_id="DTEEC_009149_1750",
        native_resolution_m=1.0,
        valid_data_coverage_fraction=1.0,
        uncertainty_summary="1.0 m/px HiRISE",
        coverage=SegmentCoverageReport(
            segment_id="SEG-001",
            dem_coverage_fraction=1.0,
            valid_elevation_fraction=1.0,
            slope_available=True,
            tri_available=True,
            optical_coverage_fraction=1.0,
            optical_quality_note="ok",
            geological_map_coverage=False,
            spectral_data_available=False,
            thermal_data_available=False,
            rover_observation_count=0,
            panorama_available=False,
            unverified_regions_present=False,
        ),
    )
    raw_obs = [
        {
            "observation_id": "cur-1",
            "mission": "MSL Curiosity",
            "instrument": "ChemCam",
            "sol": 120,
            "latitude": -4.7505,
            "longitude_east": 137.3945,
            "source_file": "cl1_test.tab",
        },
        {
            "observation_id": "m20-leak",
            "mission": "Mars 2020 Perseverance",
            "instrument": "SuperCam",
            "sol": 50,
            "latitude": -4.7505,
            "longitude_east": 137.3945,
            "source_file": "jezero_supercam.tab",
        },
    ]
    assoc = associate_corridor_observations(
        observations_raw=raw_obs,
        segments=[seg],
        search_radius_m=250.0,
        study_region="Gale Crater / Mount Sharp",
    )
    ids = [o.observation_id for o in assoc]
    assert "cur-1" in ids
    assert "m20-leak" not in ids
    assert seg.coverage.rover_observation_count == 1


def test_physical_energy_budget_requires_explicit_mass():
    missing_mass = compute_physical_energy_budget(
        positive_elevation_gain_m=12.0,
        negative_elevation_loss_m=4.0,
        astronaut_suit_mass_kg=None,
        payload_mass_kg=25.0,
    )
    assert missing_mass.available is False
    assert missing_mass.surface_weight_n is None
    assert "astronaut_suit_mass_kg" in (missing_mass.unavailable_reason or "")

    explicit = compute_physical_energy_budget(
        positive_elevation_gain_m=10.0,
        negative_elevation_loss_m=4.0,
        astronaut_suit_mass_kg=180.0,
        payload_mass_kg=20.0,
    )
    assert explicit.available is True
    assert explicit.input_total_mass_kg == 200.0
    assert abs((explicit.surface_weight_n or 0.0) - 200.0 * explicit.mars_gravity_m_s2) < 0.5
    assert (explicit.gravitational_pe_increase_j or 0.0) > 0.0
    assert (explicit.gravitational_pe_decrease_j or 0.0) < 0.0


def test_evidence_intelligence_api_end_to_end_real_hirise():
    payload = {
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.749, "lon_east": 137.394, "label": "Start"},
        "destination": {"lat": -4.753, "lon_east": 137.396, "label": "Dest"},
        "mode": "balanced",
        "corridor_width_m": 60.0,
        "observation_search_radius_m": 250.0,
    }
    resp = client.post("/api/evidence-intelligence/corridor/assess", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    aid = data["assessment_id"]
    assert len(data["segments"]) >= 1
    assert data["crs"] == "IAU2000:49900"

    for sub in ("", "/segments", "/coverage", "/features", "/observations", "/uncertainty", "/provenance"):
        r_sub = client.get(f"/api/evidence-intelligence/corridor/{aid}{sub}")
        assert r_sub.status_code == 200

    cmp_resp = client.post(
        "/api/evidence-intelligence/routes/compare-evidence",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": payload["start"],
            "destination": payload["destination"],
        },
    )
    assert cmp_resp.status_code == 200, cmp_resp.text
    cmp_data = cmp_resp.json()
    assert len(cmp_data["entries"]) == 3
    for entry in cmp_data["entries"]:
        assert entry["composite_risk_score"] is None
        assert "UNAVAILABLE" in entry["composite_risk_status"]

    # Dossier without explicit user assumptions -> PARTIALLY_ASSESSED
    dos_partial = client.post(
        "/api/evidence-intelligence/mission-dossier/generate",
        json={
            "mission_name": "Prompt 14 Partial Check",
            "dataset_id": "hirise_dteec_009149_1750",
            "start": payload["start"],
            "destination": payload["destination"],
        },
    )
    assert dos_partial.status_code == 200, dos_partial.text
    dp = dos_partial.json()
    assert dp["readiness_state"] in (
        ReadinessState.PARTIALLY_ASSESSED.value,
        ReadinessState.INSUFFICIENT_EVIDENCE.value,
    )
    assert "walking_speed_mps" in dp["missing_inputs"]
    assert dp["physical_energy_budget"]["available"] is False

    # Dossier with explicit user assumptions
    dos_full = client.post(
        "/api/evidence-intelligence/mission-dossier/generate",
        json={
            "mission_name": "Prompt 14 Explicit Check",
            "dataset_id": "hirise_dteec_009149_1750",
            "start": payload["start"],
            "destination": payload["destination"],
            "walking_speed_mps": 0.85,
            "mission_duration_limit_s": 14400.0,
            "return_reserve_fraction": 0.25,
            "astronaut_suit_mass_kg": 180.0,
            "payload_mass_kg": 25.0,
        },
    )
    assert dos_full.status_code == 200, dos_full.text
    df = dos_full.json()
    assert df["missing_inputs"] == []
    assert df["physical_energy_budget"]["available"] is True
    assert df["physical_energy_budget"]["input_total_mass_kg"] == 205.0

    get_dos = client.get(f"/api/evidence-intelligence/mission-dossier/{df['dossier_id']}")
    assert get_dos.status_code == 200
    assert get_dos.json()["dossier_id"] == df["dossier_id"]


def test_optical_crop_png_endpoint():
    resp = client.get(
        "/api/terrain/optical-crop",
        params={
            "dataset_id": "hirise_psp_009149_1750_ortho",
            "min_lat": -4.752,
            "max_lat": -4.749,
            "min_lon": 137.393,
            "max_lon": 137.396,
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert len(resp.content) > 100


def test_frontend_destination_marker_matches_start_silhouette():
    viewer_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "LocalTerrain3DViewer.tsx"
    )
    src = viewer_path.read_text(encoding="utf-8")
    assert 'export function getMarkerHeadGeometryKind(' in src
    assert 'if (shape === "waypoint") return "box";' in src
    assert 'return "sphere";' in src
    assert 'new THREE.ConeGeometry(0.65, 1.35, 12)' not in src
