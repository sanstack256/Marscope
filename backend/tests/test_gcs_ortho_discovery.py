"""
Tests for production GCS orthophoto discovery, checksum verification,
bounded caching, JP2 decoding, manifest reporting, and strict no-fallback behavior.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from app.main import app  # noqa: F401 (initialize package import order)
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.gcs_storage import GCSDatasetStore
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
)
from app.terrain.mesh import TerrainMeshService


class _FakeBlob:
    def __init__(self, bucket: "_FakeBucket", name: str) -> None:
        self._bucket = bucket
        self.name = name
        self.metadata: Dict[str, str] = {}
        self.size: Optional[int] = None
        self.chunk_size: Optional[int] = None

    def exists(self) -> bool:
        return self.name in self._bucket.objects

    def reload(self) -> None:
        data = self._bucket.objects.get(self.name)
        if data is not None:
            self.size = len(data)

    def download_to_file(self, fh: Any) -> None:
        data = self._bucket.objects[self.name]
        self._bucket.download_calls[self.name] = self._bucket.download_calls.get(self.name, 0) + 1
        fh.write(data)

    def download_as_text(self, encoding: str = "utf-8") -> str:
        return self._bucket.objects[self.name].decode(encoding)

    def upload_from_filename(self, filename: str) -> None:
        self._bucket.objects[self.name] = Path(filename).read_bytes()
        self.size = len(self._bucket.objects[self.name])


class _FakeBucket:
    def __init__(self, objects: Optional[Dict[str, bytes]] = None) -> None:
        self.objects: Dict[str, bytes] = dict(objects or {})
        self.download_calls: Dict[str, int] = {}

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self, name)


class _FakeStorageClient:
    def __init__(self, bucket: _FakeBucket) -> None:
        self._bucket = bucket

    def bucket(self, _name: str) -> _FakeBucket:
        return self._bucket

    def list_blobs(self, _bucket_name: str, prefix: str = "") -> list[_FakeBlob]:
        return [
            _FakeBlob(self._bucket, name)
            for name in sorted(self._bucket.objects.keys())
            if name.startswith(prefix)
        ]


def _make_projected_dem_and_ortho(tmp_path: Path) -> tuple[bytes, bytes]:
    """Create a real GeoTIFF DEM and a real JP2OpenJPEG orthophoto in projected Mars Equirectangular CRS."""
    crs = CRS.from_proj4("+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=137.41 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs")
    # Small projected box near (-4.8, 137.41)
    transform = from_bounds(-500.0, -285000.0, 500.0, -284000.0, 64, 64)

    dem_path = tmp_path / "seed_dem.tif"
    dem_arr = np.linspace(-4200.0, -3800.0, 64 * 64, dtype=np.float32).reshape((64, 64))
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(dem_arr, 1)

    ortho_path = tmp_path / "seed_ortho.jp2"
    ortho_arr = np.full((64, 64), 180, dtype=np.uint8)
    ortho_arr[:32, :32] = 220
    with rasterio.open(
        ortho_path,
        "w",
        driver="JP2OpenJPEG",
        height=64,
        width=64,
        count=1,
        dtype="uint8",
        crs=crs,
        transform=transform,
        QUALITY="100",
        REVERSIBLE="YES",
    ) as dst:
        dst.write(ortho_arr, 1)

    return dem_path.read_bytes(), ortho_path.read_bytes()


def _make_datasets(ortho_sha: Optional[str], ortho_size: Optional[int]) -> tuple[Dataset, Dataset]:
    cov = GeographicCoverage(
        min_latitude=-4.812,
        max_latitude=-4.790,
        min_longitude=137.400,
        max_longitude=137.420,
        center_latitude=-4.801,
        center_longitude=137.410,
        longitude_range="[0, 360]",
    )
    dem_ds = Dataset(
        id="hirise_dteec_009149_1750",
        product_id="DTEEC_009149_1750_009294_1750_U01.IMG",
        product_title="HiRISE DTM Test",
        product_type="DEM / Digital Terrain Model",
        mission="MRO",
        instrument="HiRISE",
        source_archive="NASA PDS",
        original_product_url="https://example.invalid/dem.img",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="NASA/JPL/UArizona",
        coverage=cov,
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=1.0117,
        status=DatasetLifecycleStatus.DISCOVERED,
        local_file_path=None,
    )
    ortho_ds = Dataset(
        id="hirise_psp_009149_1750_ortho",
        product_id="PSP_009149_1750_RED_C_01_ORTHO.JP2",
        product_title="HiRISE Ortho Test",
        product_type="IMAGE / Orthorectified Orbital Imagery",
        mission="MRO",
        instrument="HiRISE",
        source_archive="NASA PDS",
        original_product_url="https://example.invalid/ortho.jp2",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="NASA/JPL/UArizona",
        coverage=cov,
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=1.0117,
        sha256_checksum=ortho_sha,
        file_size_bytes=ortho_size,
        status=DatasetLifecycleStatus.DISCOVERED,
        local_file_path=None,
    )
    return dem_ds, ortho_ds


def _setup_ephemeral_catalog(tmp_path: Path, dem_ds: Dataset, ortho_ds: Optional[Dataset]) -> tuple[Path, DatasetCatalogService]:
    datasets_dir = tmp_path / "ephemeral_datasets"
    cat_dir = datasets_dir / "catalog"
    raw_dir = datasets_dir / "raw"
    cat_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / f"{dem_ds.id}.json").write_text(dem_ds.model_dump_json(indent=2), encoding="utf-8")
    if ortho_ds is not None:
        (cat_dir / f"{ortho_ds.id}.json").write_text(ortho_ds.model_dump_json(indent=2), encoding="utf-8")
    catalog = DatasetCatalogService(cat_dir)
    # Simulate fresh Cloud Run container where local_file_path is None
    for ds in catalog.list_datasets():
        ds.local_file_path = None
    return raw_dir, catalog


def test_gcs_orthophoto_discovery_manifest_decode_and_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests 1, 5, 6, 7, 8: GCS-only ortho is discovered, verified, decoded from JP2, cached, and served."""
    dem_bytes, ortho_bytes = _make_projected_dem_and_ortho(tmp_path)
    ortho_sha = hashlib.sha256(ortho_bytes).hexdigest()
    dem_sha = hashlib.sha256(dem_bytes).hexdigest()
    dem_ds, ortho_ds = _make_datasets(ortho_sha, len(ortho_bytes))
    dem_ds.sha256_checksum = dem_sha
    dem_ds.file_size_bytes = len(dem_bytes)

    raw_dir, catalog = _setup_ephemeral_catalog(tmp_path, dem_ds, ortho_ds)
    bucket = _FakeBucket(
        {
            "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG": dem_bytes,
            "datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2": ortho_bytes,
            "datasets/catalog/hirise_psp_009149_1750_ortho.json": ortho_ds.model_dump_json().encode("utf-8"),
            "datasets/manifests/hirise_psp_009149_1750_ortho.manifest.json": json.dumps(
                {"sha256_checksum": ortho_sha, "file_size_bytes": len(ortho_bytes)}
            ).encode("utf-8"),
        }
    )
    fake_store = GCSDatasetStore("marscope-datasets-marscope-514815", "datasets", client=_FakeStorageClient(bucket))
    monkeypatch.setattr(GCSDatasetStore, "from_env", classmethod(lambda cls: fake_store))

    svc = TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)

    # 6 & 7: Paired discovery & manifest reporting without local ortho file
    summaries = svc.list_available_dem_summaries()
    assert len(summaries) == 1
    assert summaries[0].ortho_dataset_id == "hirise_psp_009149_1750_ortho"

    manifest = svc.get_mesh_manifest(
        dataset_id="hirise_dteec_009149_1750",
        min_lat=-4.808,
        max_lat=-4.794,
        min_lon=137.402,
        max_lon=137.418,
    )
    assert manifest.ortho_dataset_id == "hirise_psp_009149_1750_ortho"
    assert manifest.overlay_legends["ortho"]["available"] is True
    # Manifest check must NOT have downloaded the ortho JP2 yet
    assert bucket.download_calls.get("datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2", 0) == 0

    # 5 & 8: Texture endpoint decodes JP2 and serves actual orthophoto pixels, downloading only once
    png_bytes = svc.render_region_texture_png(
        dataset_id="hirise_dteec_009149_1750",
        overlay="ortho",
        min_lat=-4.808,
        max_lat=-4.794,
        min_lon=137.402,
        max_lon=137.418,
        size=64,
    )
    img = Image.open(io.BytesIO(png_bytes))
    arr = np.asarray(img)
    assert arr.shape == (64, 64, 4)
    assert np.any(arr[..., 3] == 255)
    assert bucket.download_calls["datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2"] == 1

    # Second call with different bounds hits disk cache (no second GCS download)
    _ = svc.render_region_texture_png(
        dataset_id="hirise_dteec_009149_1750",
        overlay="ortho",
        min_lat=-4.807,
        max_lat=-4.795,
        min_lon=137.403,
        max_lon=137.417,
        size=64,
    )
    assert bucket.download_calls["datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2"] == 1


def test_gcs_orthophoto_absent_and_no_silent_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests 2, 3, 9: Catalog present but ortho image absent from GCS -> unavailable & no silent elevation fallback."""
    dem_bytes, _ = _make_projected_dem_and_ortho(tmp_path)
    dem_ds, ortho_ds = _make_datasets(None, None)
    dem_ds.sha256_checksum = hashlib.sha256(dem_bytes).hexdigest()
    dem_ds.file_size_bytes = len(dem_bytes)

    raw_dir, catalog = _setup_ephemeral_catalog(tmp_path, dem_ds, ortho_ds)
    bucket = _FakeBucket(
        {
            "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG": dem_bytes,
            "datasets/catalog/hirise_psp_009149_1750_ortho.json": ortho_ds.model_dump_json().encode("utf-8"),
        }
    )
    fake_store = GCSDatasetStore("marscope-datasets-marscope-514815", "datasets", client=_FakeStorageClient(bucket))
    monkeypatch.setattr(GCSDatasetStore, "from_env", classmethod(lambda cls: fake_store))

    svc = TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)
    manifest = svc.get_mesh_manifest(
        dataset_id="hirise_dteec_009149_1750",
        min_lat=-4.808,
        max_lat=-4.794,
        min_lon=137.402,
        max_lon=137.418,
    )
    assert manifest.ortho_dataset_id is None
    assert manifest.overlay_legends["ortho"]["available"] is False

    # Requesting overlay="ortho" must raise FileNotFoundError, never silently return elevation coloring
    with pytest.raises(FileNotFoundError):
        svc.render_region_texture_png(
            dataset_id="hirise_dteec_009149_1750",
            overlay="ortho",
            min_lat=-4.808,
            max_lat=-4.794,
            min_lon=137.402,
            max_lon=137.418,
            size=64,
        )


def test_gcs_orthophoto_checksum_mismatch_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests 4 & 9: SHA-256 mismatch from GCS is rejected explicitly and never cached on disk."""
    dem_bytes, ortho_bytes = _make_projected_dem_and_ortho(tmp_path)
    wrong_sha = "b6a530e185957b7633f0a9b20f3a66e373921dda98b81a7af797f19b34461bef"
    dem_ds, ortho_ds = _make_datasets(wrong_sha, len(ortho_bytes))
    dem_ds.sha256_checksum = hashlib.sha256(dem_bytes).hexdigest()
    dem_ds.file_size_bytes = len(dem_bytes)

    raw_dir, catalog = _setup_ephemeral_catalog(tmp_path, dem_ds, ortho_ds)
    bucket = _FakeBucket(
        {
            "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG": dem_bytes,
            "datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2": ortho_bytes,
        }
    )
    fake_store = GCSDatasetStore("marscope-datasets-marscope-514815", "datasets", client=_FakeStorageClient(bucket))
    monkeypatch.setattr(GCSDatasetStore, "from_env", classmethod(lambda cls: fake_store))

    svc = TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)
    with pytest.raises(ValueError, match="SHA-256 checksum mismatch"):
        svc.render_region_texture_png(
            dataset_id="hirise_dteec_009149_1750",
            overlay="ortho",
            min_lat=-4.808,
            max_lat=-4.794,
            min_lon=137.402,
            max_lon=137.418,
            size=64,
        )
    assert not (raw_dir / "PSP_009149_1750_RED_C_01_ORTHO.JP2").exists()


def test_gcs_orthophoto_api_endpoints_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests 7, 8, 9 via FastAPI TestClient: /api/terrain/mesh/manifest and /api/terrain/ortho/{id}/texture."""
    from fastapi.testclient import TestClient
    from app.main import app
    import app.api.terrain_mesh as terrain_mesh_api

    dem_bytes, ortho_bytes = _make_projected_dem_and_ortho(tmp_path)
    ortho_sha = hashlib.sha256(ortho_bytes).hexdigest()
    dem_ds, ortho_ds = _make_datasets(ortho_sha, len(ortho_bytes))
    dem_ds.sha256_checksum = hashlib.sha256(dem_bytes).hexdigest()
    dem_ds.file_size_bytes = len(dem_bytes)

    raw_dir, catalog = _setup_ephemeral_catalog(tmp_path, dem_ds, ortho_ds)
    bucket = _FakeBucket(
        {
            "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG": dem_bytes,
            "datasets/raw/PSP_009149_1750_RED_C_01_ORTHO.JP2": ortho_bytes,
        }
    )
    fake_store = GCSDatasetStore("marscope-datasets-marscope-514815", "datasets", client=_FakeStorageClient(bucket))
    monkeypatch.setattr(GCSDatasetStore, "from_env", classmethod(lambda cls: fake_store))

    svc = TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)
    monkeypatch.setattr(terrain_mesh_api, "terrain_mesh_service", svc)

    client = TestClient(app)
    m_resp = client.get(
        "/api/terrain/mesh/manifest",
        params={
            "dataset_id": "hirise_dteec_009149_1750",
            "min_lat": -4.808,
            "max_lat": -4.794,
            "min_lon": 137.402,
            "max_lon": 137.418,
        },
    )
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert m_data["ortho_dataset_id"] == "hirise_psp_009149_1750_ortho"
    assert m_data["overlay_legends"]["ortho"]["available"] is True

    t_resp = client.get(
        "/api/terrain/ortho/hirise_dteec_009149_1750/texture",
        params={
            "overlay": "ortho",
            "min_lat": -4.808,
            "max_lat": -4.794,
            "min_lon": 137.402,
            "max_lon": 137.418,
            "size": 64,
        },
    )
    assert t_resp.status_code == 200
    assert t_resp.headers["content-type"] == "image/png"
    assert len(t_resp.content) > 0
