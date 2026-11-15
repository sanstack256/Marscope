"""
Isolated synthetic fixture tests for the backend terrain no-data contract
(/api/terrain/mesh/tiles/{tile_id} and /api/terrain/mesh/heightgrid).
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from fastapi.testclient import TestClient

from app.api import terrain_mesh as terrain_mesh_api
from app.ingestion.catalog import DatasetCatalogService
from app.main import app
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, GeographicCoverage
from app.terrain.mesh import TerrainMeshService


def _create_synthetic_nodata_dem_fixture(
    tmp_path: Path,
    *,
    elev_grid: np.ndarray,
    nodata_val: float = -32768.0,
) -> tuple[TerrainMeshService, Dataset]:
    ds_dir = tmp_path / "datasets"
    (ds_dir / "catalog").mkdir(parents=True, exist_ok=True)
    (ds_dir / "raw").mkdir(parents=True, exist_ok=True)

    product_id = "SYNTH_NODATA_FIXTURE.tif"
    raw_path = ds_dir / "raw" / product_id
    rows, cols = elev_grid.shape
    with rasterio.open(
        raw_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        nodata=nodata_val,
        crs="+proj=longlat +a=3396190 +b=3396190 +no_defs",
        transform=from_bounds(137.0, -5.0, 137.2, -4.8, cols, rows),
    ) as dst:
        dst.write(elev_grid.astype(np.float32), 1)

    ds = Dataset(
        id="synth_nodata_dem",
        product_id=product_id,
        product_title="Synthetic No-Data Test Fixture DEM",
        product_type="DEM",
        mission="TestFixture",
        instrument="TestFixture",
        source_archive="Synthetic Test Fixture",
        original_product_url="https://example.invalid/synth_nodata.tif",
        attribution="Test Fixture",
        coverage=GeographicCoverage(
            min_latitude=-5.0,
            max_latitude=-4.8,
            min_longitude=137.0,
            max_longitude=137.2,
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=1.0117,
        local_file_path=f"raw/{product_id}",
        status=DatasetLifecycleStatus.VALIDATED,
    )
    catalog = DatasetCatalogService(ds_dir / "catalog")
    catalog.register_dataset(ds)
    return TerrainMeshService(catalog_service=catalog, raw_dir=ds_dir / "raw"), ds


def test_mesh_tile_and_heightgrid_preserve_zero_and_nodata_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Synthetic fixture: left half valid (including exact 0.0), right half nodata (-32768.0)
    grid = np.full((16, 16), -32768.0, dtype=np.float32)
    grid[:, :8] = 0.0
    grid[0:4, 0:4] = 12.5

    svc, ds = _create_synthetic_nodata_dem_fixture(tmp_path, elev_grid=grid)
    monkeypatch.setattr(terrain_mesh_api, "terrain_mesh_service", svc)
    client = TestClient(app)

    tile_resp = client.get(
        "/api/terrain/mesh/tiles/custom",
        params={
            "dataset_id": ds.id,
            "min_lat": -4.98,
            "max_lat": -4.82,
            "min_lon": 137.02,
            "max_lon": 137.18,
            "grid_size": 9,
        },
    )
    assert tile_resp.status_code == 200
    t_body = tile_resp.json()
    assert len(t_body["elevations_m"]) == 81
    assert len(t_body["valid_mask"]) == 81
    assert t_body["native_resolution_m"] == pytest.approx(1.0117, rel=1e-4)
    assert t_body["sample_spacing_m"]["dx_m"] > 10.0
    assert t_body["sample_spacing_m"]["dy_m"] > 10.0

    # Valid 0.0 elevations must have valid_mask == 1 and value == 0.0; invalid must have None and 0
    zero_indices = [i for i, v in enumerate(t_body["elevations_m"]) if v == 0.0]
    assert len(zero_indices) > 0
    assert all(t_body["valid_mask"][i] == 1 for i in zero_indices)

    invalid_indices = [i for i, m in enumerate(t_body["valid_mask"]) if m == 0]
    assert len(invalid_indices) > 0
    assert all(t_body["elevations_m"][i] is None for i in invalid_indices)

    hg_resp = client.get(
        "/api/terrain/mesh/heightgrid",
        params={
            "dataset_id": ds.id,
            "min_lat": -4.98,
            "max_lat": -4.82,
            "min_lon": 137.02,
            "max_lon": 137.18,
            "grid_size": 9,
        },
    )
    assert hg_resp.status_code == 200
    hg = hg_resp.json()
    assert hg["available"] is True
    assert hg["nodata_fill_value"] is None
    assert len(hg["valid_mask"]) == 81
    assert hg["native_resolution_m"] == pytest.approx(1.0117, rel=1e-4)
    assert hg["sample_spacing_m"]["dx_m"] > 10.0
    assert all(hg["elevations_m"][i] is None for i, m in enumerate(hg["valid_mask"]) if m == 0)
    assert any(hg["elevations_m"][i] == 0.0 and hg["valid_mask"][i] == 1 for i in range(81))


def test_all_invalid_region_returns_unavailable_heightgrid_and_zero_valid_tile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grid = np.full((16, 16), -32768.0, dtype=np.float32)
    svc, ds = _create_synthetic_nodata_dem_fixture(tmp_path, elev_grid=grid)
    monkeypatch.setattr(terrain_mesh_api, "terrain_mesh_service", svc)
    client = TestClient(app)

    hg_resp = client.get(
        "/api/terrain/mesh/heightgrid",
        params={
            "dataset_id": ds.id,
            "min_lat": -4.98,
            "max_lat": -4.82,
            "min_lon": 137.02,
            "max_lon": 137.18,
            "grid_size": 9,
        },
    )
    assert hg_resp.status_code == 200
    hg = hg_resp.json()
    assert hg["available"] is False
    assert hg["nodata_fill_value"] is None
    assert hg["valid_fraction"] == 0.0
    assert all(v is None for v in hg["elevations_m"])
    assert all(m == 0 for m in hg["valid_mask"])
