"""
Real NASA Dataset Integration Tests for Prompt 11 (Isolated from Synthetic Unit Tests).

Verifies:
- Real HiRISE Stereo DTM `hirise_dteec_009149_1750` (1.01 m/px Mount Sharp & 2025/2026 Boxwork)
- Real HiRISE Stereo DTM `hirise_dteec_040770_1755` (1.01 m/px Bradbury to Vera Rubin Ridge)
- Real MOLA 128ppd `mola_megt00n090hb` (463 m/px Gale Crater basin)
- Neighboring LOD mesh seam integrity on real NASA DEM pixels
- Real HiRISE Boxwork & Gediz Ridge route comparison (`conservative` <=16 deg steep scarp rejection vs
  `balanced` / `science_priority` completion, GeoJSON FeatureCollection export, deterministic signature)

Skips cleanly ONLY if the large raw NASA GeoTIFF/.IMG files are absent from disk.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.container import catalog_service


def _require_real_hirise():
    ds = catalog_service.get_dataset("hirise_dteec_009149_1750")
    if not ds or not ds.local_file_path:
        pytest.skip("Real NASA HiRISE DTEEC_009149_1750 not downloaded locally.")
    raw_dir = Path(catalog_service.raw_data_dir)
    cand = Path(ds.local_file_path)
    if cand.is_absolute():
        img_path = cand
    elif (raw_dir / cand).exists():
        img_path = raw_dir / cand
    else:
        img_path = raw_dir.parent / cand
    if not img_path.exists():
        pytest.skip(f"Missing real HiRISE DTM file at {img_path}.")


def test_real_nasa_hirise_mesh_manifest_seams_and_ortho_png():
    _require_real_hirise()
    client = TestClient(app)

    res_m = client.get(
        "/api/terrain/mesh/manifest?dataset_id=hirise_dteec_009149_1750&max_lod=2&tile_grid_size=33"
    )
    assert res_m.status_code == 200
    manifest = res_m.json()
    assert manifest["product_id"].startswith("DTEEC_009149_1750_009294_1750_U01")
    assert manifest["native_resolution_m"] == pytest.approx(1.01, abs=0.05)
    assert manifest["ortho_dataset_id"] == "hirise_psp_009149_1750_ortho"

    ox = manifest["origin"]["lon_east"]
    oy = manifest["origin"]["lat"]

    r_w = client.get(
        f"/api/terrain/mesh/tiles/L1_R0_C0?dataset_id=hirise_dteec_009149_1750&origin_lat={oy}&origin_lon_east={ox}&grid_size=33"
    )
    r_e = client.get(
        f"/api/terrain/mesh/tiles/L1_R0_C1?dataset_id=hirise_dteec_009149_1750&origin_lat={oy}&origin_lon_east={ox}&grid_size=33"
    )
    assert r_w.status_code == 200 and r_e.status_code == 200
    tw, te = r_w.json(), r_e.json()

    rows, cols = tw["grid_rows"], tw["grid_cols"]
    for r in range(rows):
        assert tw["valid_mask"][r * cols + (cols - 1)] == te["valid_mask"][r * cols]
        assert tw["elevations_m"][r * cols + (cols - 1)] == te["elevations_m"][r * cols]

    # Verify companion NASA HiRISE ortho PNG draping texture
    b = tw["bounds"]
    tex_res = client.get(
        "/api/terrain/ortho/hirise_psp_009149_1750_ortho/texture",
        params={
            "overlay": "ortho",
            "min_lat": b["min_lat"],
            "max_lat": b["max_lat"],
            "min_lon": b["min_lon"],
            "max_lon": b["max_lon"],
            "size": 256,
        },
    )
    assert tex_res.status_code == 200
    assert tex_res.headers["content-type"].startswith("image/png")
    assert tex_res.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_real_nasa_gale_boxwork_route_comparison_and_geojson():
    _require_real_hirise()
    client = TestClient(app)

    compare_payload = {
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.742, "lon_east": 137.392, "label": "Boxwork Station Alpha"},
        "destination": {"lat": -4.756, "lon_east": 137.402, "label": "Gediz Ridge Outcrop"},
        "constraints": {
            "max_slope_deg": 20.0,
            "walking_speed_m_per_s": 0.8,
            "return_to_start": True,
            "optimize_target_order": True,
            "max_grid_dim": 180,
        },
    }
    res_cmp = client.post("/api/routing/compare", json=compare_payload)
    assert res_cmp.status_code == 200
    cmp_body = res_cmp.json()
    assert cmp_body["source_product_id"].startswith("DTEEC_009149_1750_009294_1750_U01")

    entries = {e["mode"]: e for e in cmp_body["comparison"]}
    assert entries["conservative"]["feasible"] is False
    assert entries["balanced"]["feasible"] is True
    assert entries["science_priority"]["feasible"] is True

    bal_route = entries["balanced"]["route"]
    assert bal_route["total_surface_distance_m"] > 1500.0
    assert bal_route["max_slope_deg"] <= 20.01
    assert len(bal_route["instructions"]) >= 3
    assert bal_route["simplification_diagnostic"]["all_simplified_segments_verified_valid"] is True

    # Verify stored route & GeoJSON export
    rid = bal_route["route_id"]
    geo_res = client.get(f"/api/routing/{rid}/geojson")
    assert geo_res.status_code == 200
    geo = geo_res.json()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) >= 2
    assert geo["features"][0]["geometry"]["type"] == "LineString"

    # Verify deterministic repeatability of route_signature
    res_det = client.post(
        "/api/routing/compute",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": compare_payload["start"],
            "destination": compare_payload["destination"],
            "mode": "balanced",
            "algorithm": "astar",
            "constraints": compare_payload["constraints"],
        },
    )
    assert res_det.status_code == 200
    assert res_det.json()["route_signature"] == bal_route["route_signature"]


def test_real_nasa_second_hirise_and_mola_dem_manifests():
    client = TestClient(app)

    # Check second HiRISE Stereo DTM (Bradbury to Vera Rubin Ridge) if present
    ds2 = catalog_service.get_dataset("hirise_dteec_040770_1755")
    if ds2 and ds2.local_file_path:
        r2 = client.get(
            "/api/terrain/mesh/manifest?dataset_id=hirise_dteec_040770_1755&max_lod=1&tile_grid_size=33"
        )
        assert r2.status_code == 200
        m2 = r2.json()
        assert m2["product_id"].startswith("DTEEC_040770_1755")
        assert m2["native_resolution_m"] == pytest.approx(1.01, abs=0.05)

    # Check MOLA 128ppd Gale basin DEM + resolution suitability gate
    ds_mola = catalog_service.get_dataset("mola_megt00n090hb")
    if ds_mola and ds_mola.local_file_path:
        rm = client.get(
            "/api/terrain/mesh/manifest?dataset_id=mola_megt00n090hb&max_lod=1&tile_grid_size=33"
        )
        assert rm.status_code == 200
        mm = rm.json()
        assert mm["native_resolution_m"] > 400.0
        # MOLA ~463 m/px must be honestly flagged NOT suitable for local micro-obstacle detection
        assert mm["resolution_suitability"]["small_scale_obstacle_detection"]["supported"] is False


def test_real_nasa_multi_stop_tsp_order_and_return_loop():
    _require_real_hirise()
    client = TestClient(app)

    payload = {
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.742, "lon_east": 137.392, "label": "Start Station"},
        "destination": {"lat": -4.756, "lon_east": 137.402, "label": "South Objective"},
        "waypoints": [
            {"lat": -4.751, "lon_east": 137.398, "label": "Mid Ridge"},
            {"lat": -4.745, "lon_east": 137.395, "label": "Boxwork Sample B"},
        ],
        "mode": "science_priority",
        "algorithm": "astar",
        "constraints": {
            "max_slope_deg": 24.0,
            "walking_speed_m_per_s": None,
            "return_to_start": True,
            "optimize_target_order": True,
            "max_grid_dim": 160,
        },
    }
    res = client.post("/api/routing/compute", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["return_to_start"] is True
    assert body["estimated_duration_seconds"] is None
    assert "No walking speed or duration assumed" in body["assumption_classification"]
    # Must contain 4 legs: Start -> StopA -> StopB -> Dest -> Return to Start
    assert len(body["legs"]) == 4
    assert body["legs"][-1]["is_return_leg"] is True
    v0, vn = body["vertices"][0], body["vertices"][-1]
    assert v0["lat"] == pytest.approx(vn["lat"], abs=1e-4)
    assert v0["lon_east"] == pytest.approx(vn["lon_east"], abs=1e-4)
