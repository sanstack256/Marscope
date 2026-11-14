"""
Prompt 13 Scientific Consistency, TRI Cross-LOD Invariance, Color Normalization,
Multi-Scale Terrain Derivatives, Optical Candidates & Provenance Graph Tests.
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services.container import RAW_DIR, catalog_service, terrain_mesh_service
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


def test_tri_scientific_fixtures_and_nodata_strictness() -> None:
    # 1. Flat terrain -> TRI == 0.0
    flat = np.full((7, 7), -4000.0, dtype=np.float64)
    tri_flat, meta = calculate_roughness_tri_with_metadata(
        flat, dx_meters=1.0, dy_meters=1.0, neighborhood_radius_meters=1.0
    )
    assert math.isclose(float(tri_flat[3, 3]), 0.0, abs_tol=1e-12)
    assert meta["formula_id"] == "riley_1999_rms_elevation_difference_v1"
    assert meta["nodata_policy"] == "strict_all_neighbors_valid"
    assert meta["processing_version"] == "tri_v2_fixed_physical_window"

    # 2. DEM edge strictly NaN (never shrunk neighborhood)
    assert np.isnan(tri_flat[0, 3])
    assert np.isnan(tri_flat[3, 0])

    # 3. Known elevation step (left=-10, right=+10; center at col 3 is 0)
    step = np.zeros((7, 7), dtype=np.float64)
    step[:, :3] = -10.0
    step[:, 4:] = 10.0
    tri_step, _ = calculate_roughness_tri_with_metadata(
        step, dx_meters=1.0, dy_meters=1.0, neighborhood_radius_meters=1.0
    )
    # 3 neighbors at -10, 3 at +10, 2 at 0 -> sum_sq = 6 * 100 = 600, N = 8 -> sqrt(75)
    assert math.isclose(float(tri_step[3, 3]), math.sqrt(600.0 / 8.0), rel_tol=1e-9)

    # 4. Known isolated peak (+8m at center) -> all 8 neighbors differ by 8m -> TRI == 8.0
    peak = np.zeros((7, 7), dtype=np.float64)
    peak[3, 3] = 8.0
    tri_peak, _ = calculate_roughness_tri_with_metadata(
        peak, dx_meters=1.0, dy_meters=1.0, neighborhood_radius_meters=1.0
    )
    assert math.isclose(float(tri_peak[3, 3]), 8.0, rel_tol=1e-9)

    # 5. Known depression (-6m at center) -> TRI == 6.0
    dep = np.zeros((7, 7), dtype=np.float64)
    dep[3, 3] = -6.0
    tri_dep, _ = calculate_roughness_tri_with_metadata(
        dep, dx_meters=1.0, dy_meters=1.0, neighborhood_radius_meters=1.0
    )
    assert math.isclose(float(tri_dep[3, 3]), 6.0, rel_tol=1e-9)

    # 6. Constant plane with known slope (dz/dx = 0.5 -> atan(0.5) deg)
    rows, cols = np.mgrid[0:7, 0:7]
    plane = cols.astype(np.float64) * 0.5
    slope_plane, _ = calculate_slope(plane, dx_meters=1.0, dy_meters=1.0)
    expected_deg = math.degrees(math.atan(0.5))
    assert math.isclose(float(slope_plane[3, 3]), expected_deg, rel_tol=1e-6)

    # 7. No-data hole strictly yields NaN for any touching neighborhood
    hole = flat.copy()
    hole[3, 4] = np.nan
    tri_hole, _ = calculate_roughness_tri_with_metadata(
        hole, dx_meters=1.0, dy_meters=1.0, neighborhood_radius_meters=1.0
    )
    assert np.isnan(tri_hole[3, 3])
    assert np.isnan(tri_hole[3, 4])

    # 8. Resolution-limited physical radius raises ValueError instead of silent substitution
    with pytest.raises(ValueError, match="resolution-limited"):
        calculate_roughness_tri_with_metadata(
            flat, dx_meters=10.0, dy_meters=10.0, neighborhood_radius_meters=2.0
        )


def test_tri_cross_lod_invariance_real_hirise() -> None:
    ds = catalog_service.get_dataset("hirise_dteec_009149_1750")
    if not ds or not (RAW_DIR / "dteec_009149_1750_009294_1750_u01.img").exists():
        pytest.skip("Local HiRISE DTM binary not present")

    manifest = terrain_mesh_service.get_mesh_manifest(
        dataset_id="hirise_dteec_009149_1750", max_lod=2, tile_grid_size=65
    )
    req = manifest.requested_bounds
    t0 = terrain_mesh_service.get_mesh_tile(
        tile_id="L0_R0_C0",
        dataset_id=ds.id,
        min_lat=req["min_lat"],
        max_lat=req["max_lat"],
        min_lon=req["min_lon"],
        max_lon=req["max_lon"],
        grid_size=65,
        include_derivatives=True,
    )
    t1 = terrain_mesh_service.get_mesh_tile(
        tile_id="L1_R0_C0",
        dataset_id=ds.id,
        min_lat=req["min_lat"],
        max_lat=req["max_lat"],
        min_lon=req["min_lon"],
        max_lon=req["max_lon"],
        grid_size=65,
        include_derivatives=True,
    )
    t2 = terrain_mesh_service.get_mesh_tile(
        tile_id="L2_R0_C0",
        dataset_id=ds.id,
        min_lat=req["min_lat"],
        max_lat=req["max_lat"],
        min_lon=req["min_lon"],
        max_lon=req["max_lon"],
        grid_size=65,
        include_derivatives=True,
    )

    assert t0.tri_status == "valid"
    assert t1.tri_status == "valid"
    assert t2.tri_status == "valid"
    assert t0.tri_metadata is not None
    assert t0.tri_metadata["physical_radius_m"] == 5.0
    assert t0.tri_metadata["formula_id"] == "riley_1999_rms_elevation_difference_v1"
    assert t0.roughness_tri_m is not None and t1.roughness_tri_m is not None and t2.roughness_tri_m is not None

    # Shared Northwest corner (0,0) and shared interior grid vertices:
    # In a 65x65 grid: L2 (r,c) step is 1/4 of L0, so (r=16, c=16) in L0 == (r=32, c=32) in L1 == (r=64, c=64) in L2.
    def _at(tile, r: int, c: int):
        return tile.roughness_tri_m[r * 65 + c]

    # Compare several shared valid coordinates across LOD 0, LOD 1, and LOD 2
    shared_samples = []
    for r0 in range(0, 17, 4):
        for c0 in range(0, 17, 4):
            v0 = _at(t0, r0, c0)
            v1 = _at(t1, r0 * 2, c0 * 2)
            v2 = _at(t2, r0 * 4, c0 * 4)
            if v0 is not None and v1 is not None and v2 is not None:
                shared_samples.append((v0, v1, v2))
                assert math.isclose(v0, v1, abs_tol=1e-6)
                assert math.isclose(v0, v2, abs_tol=1e-6)

    assert len(shared_samples) >= 5, "Expected valid shared TRI samples across LOD 0, 1, 2"


def test_color_normalization_spec_and_shared_palette_rendering() -> None:
    ds = catalog_service.get_dataset("hirise_dteec_009149_1750")
    if not ds or not (RAW_DIR / "dteec_009149_1750_009294_1750_u01.img").exists():
        pytest.skip("Local HiRISE DTM binary not present")

    manifest = terrain_mesh_service.get_mesh_manifest(
        dataset_id="hirise_dteec_009149_1750", max_lod=2, tile_grid_size=65
    )
    norms = manifest.color_normalizations
    assert "elevation" in norms
    assert "slope" in norms
    assert "roughness" in norms
    assert "ortho" in norms

    assert norms["elevation"].units == "meters"
    assert norms["slope"].units == "degrees"
    assert norms["slope"].vmin == 0.0 and norms["slope"].vmax == 35.0
    assert norms["roughness"].units == "meters"
    assert norms["roughness"].physical_radius_m == 5.0
    assert norms["ortho"].scale_type == "source_imagery"
    assert len(norms["elevation"].palette_stops) >= 3

    # Render adjacent tiles at identical manifest bounds & confirm seam RGB match
    req = manifest.requested_bounds
    mid_lon = 0.5 * (req["min_lon"] + req["max_lon"])
    el_norm = norms["elevation"]
    png_left = terrain_mesh_service.render_region_texture_png(
        dataset_id=ds.id,
        overlay="elevation",
        min_lat=req["min_lat"],
        max_lat=req["max_lat"],
        min_lon=req["min_lon"],
        max_lon=mid_lon,
        size=128,
        vmin=el_norm.vmin,
        vmax=el_norm.vmax,
    )
    png_right = terrain_mesh_service.render_region_texture_png(
        dataset_id=ds.id,
        overlay="elevation",
        min_lat=req["min_lat"],
        max_lat=req["max_lat"],
        min_lon=mid_lon,
        max_lon=req["max_lon"],
        size=128,
        vmin=el_norm.vmin,
        vmax=el_norm.vmax,
    )
    arr_l = np.array(Image.open(io.BytesIO(png_left)))
    arr_r = np.array(Image.open(io.BytesIO(png_right)))
    # Shared seam column where both are opaque should match closely
    opaque = (arr_l[:, -1, 3] == 255) & (arr_r[:, 0, 3] == 255)
    assert np.any(opaque)
    diff = np.abs(arr_l[opaque, -1, :3].astype(np.int32) - arr_r[opaque, 0, :3].astype(np.int32))
    assert float(np.mean(diff)) < 3.0


def test_multiscale_optical_and_route_provenance_endpoints() -> None:
    client = TestClient(app)

    # 1. Multi-scale terrain endpoint
    r_ms = client.get(
        "/api/terrain/multiscale",
        params={"lat": -4.74, "lon": 137.405, "dataset_id": "hirise_dteec_009149_1750"},
    )
    assert r_ms.status_code == 200
    ms = r_ms.json()
    assert ms["available"] is True
    assert ms["tri_fine_m"]["classification"] == "MARSCOPE_DERIVED"
    assert ms["tri_fine_m"]["physical_radius_m"] == 5.0
    assert ms["tri_medium_m"]["physical_radius_m"] == 15.0
    assert ms["local_relief_m"]["status"] == "valid"
    assert ms["provenance_graph"]["classification"] == "MARSCOPE_DERIVED"
    assert "DTEEC_009149_1750_009294_1750_U01.IMG" in ms["provenance_graph"]["input_product_ids"]

    # 2. Optical feature candidate endpoint
    r_opt = client.get(
        "/api/terrain/optical-features",
        params={
            "dataset_id": "hirise_dteec_009149_1750",
            "min_lat": -4.75,
            "max_lat": -4.73,
            "min_lon": 137.395,
            "max_lon": 137.415,
        },
    )
    assert r_opt.status_code == 200
    opt = r_opt.json()
    if opt["available"]:
        assert opt["provenance_graph"]["validation_state"] == "candidate_requiring_interpretation"
        for c in opt["candidates"]:
            assert c["classification"] == "MARSCOPE_DERIVED"
            assert c["validation_state"] == "candidate_requiring_interpretation"

    # 3. Route compute includes full provenance_graph
    r_rt = client.post(
        "/api/routing/compute",
        json={
            "dataset_id": "hirise_dteec_009149_1750",
            "start": {"lat": -4.749, "lon_east": 137.397},
            "destination": {"lat": -4.740, "lon_east": 137.406},
            "mode": "balanced",
        },
    )
    assert r_rt.status_code == 200
    rt = r_rt.json()
    assert rt["provenance_graph"] is not None
    assert rt["provenance_graph"]["classification"] == "MARSCOPE_DERIVED"
    assert len(rt["provenance_graph"]["intermediate_steps"]) == 3
