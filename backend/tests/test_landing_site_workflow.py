"""
End-to-end backend tests for the rebuilt Landing-Site Intelligence & 3D Perimeter workflow:
- Dynamic catalog/GCS DEM discovery (without processed_dir)
- HiRISE vs MOLA-only vs Outside-all-DEMs differentiation
- No-data at landing-site coordinates
- Invalid coordinate rejection
- Missing constraints, slope exclusion, TRI exclusion, max-radius enforcement, and unknown/no-data terrain
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

from fastapi.testclient import TestClient
import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from app.db.database import MissionDatabase
from app.ingestion.catalog import DatasetCatalogService
from app.main import app
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
)
from app.services import container as svc_container
from app.services.landing_site_service import LandingSiteService


def _csrf_headers(client: TestClient) -> Dict[str, str]:
    token = client.cookies.get("marscope_csrf")
    return {"X-CSRF-Token": token} if token else {}


def _write_test_dem(
    path: Path,
    *,
    arr: np.ndarray,
    bounds: tuple[float, float, float, float],
    nodata: float = -32768.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    transform = from_bounds(*bounds, w, h)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs=CRS.from_proj4("+proj=longlat +R=3396190 +no_defs"),
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(arr.astype(np.float32), 1)


@pytest.fixture()
def isolated_landing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "missions.db"
    fresh_db = MissionDatabase(default_sqlite_path=db_path)

    datasets_dir = tmp_path / "datasets"
    cat_dir = datasets_dir / "catalog"
    raw_dir = datasets_dir / "raw"
    proc_dir = datasets_dir / "processed"
    cat_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    # Create a 64x64 synthetic HiRISE-scale DEM (~1.01 m/px) with a steep ridge on the east side and no-data corner at NW
    # 64 px * ~0.000017 deg/px ≈ 0.001088 deg (~64 m across)
    hirise_bounds = (137.400, -4.801088, 137.401088, -4.800)
    y_idx, x_idx = np.mgrid[0:64, 0:64]
    hirise_arr = -4000.0 + 0.05 * y_idx
    # Steep ridge on columns >= 46 -> high slope (> 25 deg) & high TRI
    hirise_arr[:, 46:] += (x_idx[:, 46:] - 45) * 1.5
    # No-data patch inside evaluation radius (rows 20..26, cols 20..26)
    hirise_arr[20:26, 20:26] = -32768.0
    hirise_file = raw_dir / "hirise_test.tif"
    _write_test_dem(hirise_file, arr=hirise_arr, bounds=hirise_bounds)

    # Create a coarse regional MOLA-scale DEM (~500 m/px) covering a wider region
    mola_bounds = (135.0, -6.0, 140.0, -3.0)
    mola_arr = np.full((32, 32), -3500.0, dtype=np.float32)
    mola_file = raw_dir / "mola_test.tif"
    _write_test_dem(mola_file, arr=mola_arr, bounds=mola_bounds)

    hirise_ds = Dataset(
        id="hirise_test_dtm",
        product_id="hirise_test.tif",
        product_title="Synthetic HiRISE Test DTM",
        product_type="DEM / Digital Terrain Model",
        mission="MRO",
        instrument="HiRISE",
        source_archive="Test PDS",
        original_product_url="https://example.invalid/hirise.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Test",
        coverage=GeographicCoverage(
            min_latitude=hirise_bounds[1],
            max_latitude=hirise_bounds[3],
            min_longitude=hirise_bounds[0],
            max_longitude=hirise_bounds[2],
            center_latitude=-4.800544,
            center_longitude=137.400544,
            longitude_range="[0, 360]",
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=1.01,
        sha256_checksum=hashlib.sha256(hirise_file.read_bytes()).hexdigest(),
        file_size_bytes=hirise_file.stat().st_size,
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path="raw/hirise_test.tif",
    )
    mola_ds = Dataset(
        id="mola_test_dtm",
        product_id="mola_test.tif",
        product_title="Synthetic MOLA Test DEM",
        product_type="DEM / Digital Terrain Model",
        mission="MGS",
        instrument="MOLA",
        source_archive="Test PDS",
        original_product_url="https://example.invalid/mola.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Test",
        coverage=GeographicCoverage(
            min_latitude=mola_bounds[1],
            max_latitude=mola_bounds[3],
            min_longitude=mola_bounds[0],
            max_longitude=mola_bounds[2],
            center_latitude=-4.5,
            center_longitude=137.5,
            longitude_range="[0, 360]",
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=463.0,
        sha256_checksum=hashlib.sha256(mola_file.read_bytes()).hexdigest(),
        file_size_bytes=mola_file.stat().st_size,
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path="raw/mola_test.tif",
    )
    (cat_dir / f"{hirise_ds.id}.json").write_text(hirise_ds.model_dump_json(), encoding="utf-8")
    (cat_dir / f"{mola_ds.id}.json").write_text(mola_ds.model_dump_json(), encoding="utf-8")
    catalog = DatasetCatalogService(cat_dir)

    ls_service = LandingSiteService(
        db=fresh_db,
        event_service=svc_container.mission_event_service,
        realtime_hub=svc_container.mission_realtime_hub,
        catalog_service=catalog,
        destination_service=svc_container.destination_service,
        processed_dir=proc_dir,
        raw_dir=raw_dir,
    )
    monkeypatch.setattr(svc_container, "mission_db", fresh_db)
    monkeypatch.setattr("app.api.deps.mission_db", fresh_db)
    monkeypatch.setattr(svc_container.mission_event_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.auth_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.mission_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container, "landing_site_service", ls_service)
    monkeypatch.setattr("app.api.landing_site.landing_site_service", ls_service)
    monkeypatch.setattr(svc_container.destination_service, "processed_dir", proc_dir)

    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "lead@mars.test", "password": "StrongPassword123!", "display_name": "Lead"},
    )
    m = client.post("/api/missions", headers=_csrf_headers(client), json={"name": "Landing Test"}).json()
    return client, m["mission_id"]


def test_dynamic_discovery_hirise_vs_mola_vs_outside_and_nodata(isolated_landing_env) -> None:
    client, mid = isolated_landing_env

    # F. Inside HiRISE DEM -> selects HiRISE (1.01 m/px) over MOLA (463 m/px)
    d_hi = client.get("/api/missions/landing-site/discover-coverage?lat=-4.8006&lon=137.4005").json()
    assert d_hi["covered"] is True
    assert d_hi["selected_dataset"]["dataset_id"] == "hirise_test_dtm"
    assert d_hi["selected_dataset"]["local_slope_suitable"] is True
    assert d_hi["elevation_m"] is not None
    assert d_hi["sample_is_nodata"] is False

    # G. Inside MOLA DEM but outside HiRISE -> selects MOLA with local_slope_suitable=False
    d_mo = client.get("/api/missions/landing-site/discover-coverage?lat=-4.5&lon=137.5").json()
    assert d_mo["covered"] is True
    assert d_mo["selected_dataset"]["dataset_id"] == "mola_test_dtm"
    assert d_mo["selected_dataset"]["local_slope_suitable"] is False

    # H. Outside every DEM
    d_out = client.get("/api/missions/landing-site/discover-coverage?lat=25.0&lon=45.0").json()
    assert d_out["covered"] is False
    assert d_out["selected_dataset"] is None
    assert d_out["elevation_m"] is None

    # L. No-data pixel inside HiRISE patch (rows 20..26, cols 20..26) -> sample_is_nodata=True and elevation_m is None
    d_nd = client.get("/api/missions/landing-site/discover-coverage?lat=-4.800391&lon=137.400391").json()
    assert d_nd["covered"] is True
    assert d_nd["sample_is_nodata"] is True
    assert d_nd["elevation_m"] is None

    # D. Invalid coordinates rejected 422 (no silent wrapping)
    bad_lon = client.put(
        f"/api/missions/{mid}/landing-site",
        headers=_csrf_headers(client),
        json={"name": "Bad Lon", "latitude": -4.8, "longitude": 370.0},
    )
    assert bad_lon.status_code == 422


def test_raw_dem_bfs_perimeter_constraints_and_unknown_terrain(isolated_landing_env) -> None:
    client, mid = isolated_landing_env

    # Register valid HiRISE site (no processed_dir files exist, uses raw catalog DEM!)
    reg = client.put(
        f"/api/missions/{mid}/landing-site",
        headers=_csrf_headers(client),
        json={"name": "HiRISE Alpha", "latitude": -4.80054, "longitude": 137.40050, "source": "USER_PROVIDED"},
    )
    assert reg.status_code == 200
    reg_body = reg.json()
    assert reg_body["landing_site"]["dem_coverage_state"] == "COVERED_DEM"
    assert reg_body["landing_site"]["terrain_dataset_id"] == "hirise_test_dtm"

    # M. Missing constraints -> INDETERMINATE_MISSING_CONSTRAINTS
    miss = client.post(
        f"/api/missions/{mid}/landing-site/perimeter",
        headers=_csrf_headers(client),
        json={"max_slope_deg": 10.0, "max_radius_m": 25.0},
    ).json()
    assert miss["perimeter"]["status"] == "INDETERMINATE_MISSING_CONSTRAINTS"
    assert miss["perimeter"]["geometry_geojson"] is None

    # N, P, Q, R, S: Valid evaluation with slope/TRI exclusion, max radius, and unknown no-data cells
    eval_res = client.post(
        f"/api/missions/{mid}/landing-site/perimeter",
        headers=_csrf_headers(client),
        json={"max_slope_deg": 10.0, "max_roughness_m": 0.5, "max_radius_m": 25.0},
    ).json()
    perim = eval_res["perimeter"]
    assert perim["status"] == "EVALUATED_WITH_VALIDATED_DEM"
    assert perim["terrain_dataset_id"] == "hirise_test_dtm"
    assert perim["geometry_geojson"] is not None
    assert perim["excluded_regions_geojson"] is not None
    assert perim["provenance"]["max_boundary_distance_m"] <= 25.0
    assert perim["provenance"]["excluded_cells"] > 0
    assert perim["provenance"]["unknown_cells"] > 0
    assert perim["unknown_regions_geojson"] is not None
