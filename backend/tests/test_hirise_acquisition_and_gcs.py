"""
Tests for memory-bounded HiRISE/MOLA DEM acquisition, incremental SHA-256,
error reporting, concurrent serialization, GCS persistence/retrieval, and
the Cloud Run acquisition job.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pytest

from app.ingestion.acquisition import AcquisitionService
from app.ingestion.gcs_storage import GCSDatasetStore
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
)
from scripts import acquire_datasets_job


def _make_pds3_dataset(
    *,
    dataset_id: str = "hirise_dteec_009149_1750",
    product_id: str = "DTEEC_009149_1750_009294_1750_U01.IMG",
    url: str = "https://example.org/pds/DTEEC_009149_1750_009294_1750_U01.IMG",
) -> Dataset:
    return Dataset(
        id=dataset_id,
        product_id=product_id,
        product_title="HiRISE Gale Crater DTM",
        product_type="DEM",
        mission="Mars Reconnaissance Orbiter",
        instrument="HiRISE",
        source_archive="NASA PDS HiRISE",
        original_product_url=url,
        attribution="NASA/JPL-Caltech/UArizona",
        coverage=GeographicCoverage(
            min_latitude=-5.6,
            max_latitude=-4.5,
            min_longitude=137.0,
            max_longitude=137.8,
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=1.0,
        status=DatasetLifecycleStatus.DISCOVERED,
    )


def _sample_pds3_img_bytes(payload_size: int = 16384) -> bytes:
    header = (
        b"PDS_VERSION_ID = PDS3\r\n"
        b"RECORD_TYPE = FIXED_LENGTH\r\n"
        b"RECORD_BYTES = 512\r\n"
        b"OBJECT = IMAGE\r\n"
        b"  LINES = 32\r\n"
        b"  LINE_SAMPLES = 32\r\n"
        b"  SAMPLE_BITS = 32\r\n"
        b"END_OBJECT = IMAGE\r\n"
        b"END\r\n"
    )
    pad_len = max(0, payload_size - len(header))
    return header + (b"\x01\x02\x03\x04" * (pad_len // 4 + 1))[:pad_len]


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        chunks: List[bytes],
        headers: Optional[Dict[str, str]] = None,
        fail_after_chunk: Optional[int] = None,
        exc_factory: Optional[Any] = None,
        observed_chunk_sizes: Optional[List[int]] = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.headers = headers or {}
        self._fail_after_chunk = fail_after_chunk
        self._exc_factory = exc_factory
        self._observed_chunk_sizes = observed_chunk_sizes
        self.request = httpx.Request("GET", "https://example.org/pds/test.img")

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def aiter_bytes(self, chunk_size: Optional[int] = None):
        if self._observed_chunk_sizes is not None:
            self._observed_chunk_sizes.append(chunk_size)
        for idx, chunk in enumerate(self._chunks):
            yield chunk
            if self._fail_after_chunk is not None and idx == self._fail_after_chunk:
                raise self._exc_factory()


class _FakeAsyncClient:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def stream(self, method: str, url: str, headers: Optional[Dict[str, str]] = None) -> _FakeResponse:
        return self._handler(method, url, headers or {})

    async def get(self, url: str) -> httpx.Response:
        return httpx.Response(404, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_interrupted_download_and_range_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _sample_pds3_img_bytes(20480)
    expected_sha = hashlib.sha256(payload).hexdigest()
    split = 8192
    calls: List[Dict[str, str]] = []

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        calls.append(dict(headers))
        if "Range" not in headers:
            return _FakeResponse(
                status_code=200,
                chunks=[payload[:4096], payload[4096:split]],
                headers={"Content-Length": str(len(payload)), "Content-Type": "application/octet-stream"},
                fail_after_chunk=1,
                exc_factory=lambda: httpx.ReadTimeout(""),
            )
        assert headers["Range"] == f"bytes={split}-"
        return _FakeResponse(
            status_code=206,
            chunks=[payload[split:split + 4096], payload[split + 4096:]],
            headers={"Content-Length": str(len(payload) - split), "Content-Type": "application/octet-stream"},
        )

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )

    svc = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    ds = _make_pds3_dataset()
    manifest = await svc.download_product(
        ds,
        expected_sha256=expected_sha,
        max_retries=2,
    )

    assert len(calls) == 2
    assert manifest.verified_integrity is True
    assert manifest.sha256_checksum == expected_sha
    assert manifest.file_size_bytes == len(payload)
    target = tmp_path / "raw" / ds.product_id
    assert target.exists()
    assert target.read_bytes() == payload
    assert not (tmp_path / "raw" / f".{ds.product_id}.download_tmp").exists()


@pytest.mark.asyncio
async def test_memory_bounded_streaming_and_non_empty_timeout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_chunk_sizes: List[int] = []
    payload = _sample_pds3_img_bytes(4096)

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        return _FakeResponse(
            status_code=200,
            chunks=[payload[:1024]],
            headers={"Content-Length": str(len(payload))},
            fail_after_chunk=0,
            exc_factory=lambda: httpx.TimeoutException(""),
            observed_chunk_sizes=observed_chunk_sizes,
        )

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )

    svc = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    ds = _make_pds3_dataset()
    with pytest.raises(httpx.TimeoutException):
        await svc.download_product(
            ds,
            chunk_size=10_000_000,  # Must be clamped to <= 262144
            max_retries=1,
            timeout_seconds=120.0,
        )

    assert observed_chunk_sizes == [None]
    assert ds.failure_reason
    assert "TimeoutException" in ds.failure_reason
    assert "bytes_downloaded=" in ds.failure_reason
    assert "timeout_seconds=120.0" in ds.failure_reason

    ledger_lines = (tmp_path / "manifests" / "acquisition_ledger.jsonl").read_text().strip().splitlines()
    last_entry = json.loads(ledger_lines[-1])
    assert last_entry["error"]
    assert "TimeoutException" in last_entry["error"]


@pytest.mark.asyncio
async def test_checksum_mismatch_rejects_and_cleans_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _sample_pds3_img_bytes(8192)
    wrong_sha = "0" * 64

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        return _FakeResponse(
            status_code=200,
            chunks=[payload],
            headers={"Content-Length": str(len(payload))},
        )

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )

    svc = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    ds = _make_pds3_dataset()
    with pytest.raises(ValueError, match="SHA-256 checksum mismatch"):
        await svc.download_product(
            ds,
            expected_sha256=wrong_sha,
            max_retries=1,
        )

    assert not (tmp_path / "raw" / ds.product_id).exists()
    assert not (tmp_path / "raw" / f".{ds.product_id}.download_tmp").exists()


@pytest.mark.asyncio
async def test_transient_http_503_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _sample_pds3_img_bytes(8192)
    expected_sha = hashlib.sha256(payload).hexdigest()
    attempt = {"count": 0}

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        attempt["count"] += 1
        if attempt["count"] == 1:
            return _FakeResponse(status_code=503, chunks=[])
        return _FakeResponse(
            status_code=200,
            chunks=[payload[:4096], payload[4096:]],
            headers={"Content-Length": str(len(payload))},
        )

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )

    svc = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    ds = _make_pds3_dataset()
    manifest = await svc.download_product(
        ds,
        expected_sha256=expected_sha,
        max_retries=2,
    )

    assert attempt["count"] == 2
    assert manifest.verified_integrity is True
    assert manifest.sha256_checksum == expected_sha


@pytest.mark.asyncio
async def test_concurrent_acquisition_is_serialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload1 = _sample_pds3_img_bytes(8192)
    payload2 = _sample_pds3_img_bytes(8192)
    concurrency = {"active": 0, "max": 0}

    class _CountingResponse(_FakeResponse):
        async def aiter_bytes(self, chunk_size: Optional[int] = None):
            concurrency["active"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["active"])
            try:
                for chunk in self._chunks:
                    await asyncio.sleep(0.01)
                    yield chunk
            finally:
                concurrency["active"] -= 1

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        data = payload1 if "ONE" in url else payload2
        return _CountingResponse(
            status_code=200,
            chunks=[data[:4096], data[4096:]],
            headers={"Content-Length": str(len(data))},
        )

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )

    svc = AcquisitionService(tmp_path / "raw", tmp_path / "manifests")
    ds1 = _make_pds3_dataset(
        dataset_id="ds_one",
        product_id="ONE.IMG",
        url="https://example.org/pds/ONE.IMG",
    )
    ds2 = _make_pds3_dataset(
        dataset_id="ds_two",
        product_id="TWO.IMG",
        url="https://example.org/pds/TWO.IMG",
    )

    m1, m2 = await asyncio.gather(
        svc.download_product(ds1),
        svc.download_product(ds2),
    )

    assert concurrency["max"] == 1
    assert m1.verified_integrity is True
    assert m2.verified_integrity is True


class _FakeBlob:
    def __init__(self, store: Dict[str, bytes], name: str, metadata_store: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        self._store = store
        self._metadata_store = metadata_store if metadata_store is not None else {}
        self.name = name
        self.chunk_size: Optional[int] = None
        self.metadata: Dict[str, str] = dict(self._metadata_store.get(name, {}))
        self.size: Optional[int] = len(store[name]) if name in store else None

    def exists(self) -> bool:
        return self.name in self._store

    def reload(self) -> None:
        if self.name in self._store:
            self.size = len(self._store[self.name])
            self.metadata = dict(self._metadata_store.get(self.name, {}))

    def upload_from_filename(self, filename: str) -> None:
        data = Path(filename).read_bytes()
        self._store[self.name] = data
        self.size = len(data)
        self._metadata_store[self.name] = dict(self.metadata)

    def download_to_file(self, fh: io.BufferedWriter) -> None:
        fh.write(self._store[self.name])


class _FakeBucket:
    def __init__(self, store: Dict[str, bytes], metadata_store: Dict[str, Dict[str, str]]) -> None:
        self._store = store
        self._metadata_store = metadata_store

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._store, name, self._metadata_store)


class _FakeGCSClient:
    def __init__(self) -> None:
        self.objects: Dict[str, bytes] = {}
        self.metadata_store: Dict[str, Dict[str, str]] = {}

    def bucket(self, bucket_name: str) -> _FakeBucket:
        return _FakeBucket(self.objects, self.metadata_store)

    def list_blobs(self, bucket_name: str, prefix: str = "") -> List[_FakeBlob]:
        return [
            _FakeBlob(self.objects, k, self.metadata_store)
            for k in sorted(self.objects.keys())
            if k.startswith(prefix)
        ]


def test_gcs_store_streaming_upload_download_and_case_insensitive_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _sample_pds3_img_bytes(12288)
    expected_sha = hashlib.sha256(payload).hexdigest()

    src_file = tmp_path / "src" / "DTEEC_009149_1750_009294_1750_U01.IMG"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_bytes(payload)

    fake_client = _FakeGCSClient()
    store = GCSDatasetStore(bucket_name="marscope-test-bucket", prefix="datasets", client=fake_client)

    upload_meta = store.upload_file_streaming(
        src_file,
        f"raw/{src_file.name}",
        expected_sha256=expected_sha,
    )
    assert upload_meta["object_name"] == "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG"
    assert upload_meta["sha256"] == expected_sha

    resolved = store.find_raw_object_name("dteec_009149_1750_009294_1750_u01.img")
    assert resolved == "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG"

    # Reject checksum mismatch on download without creating destination file
    bad_dest = tmp_path / "bad" / src_file.name
    with pytest.raises(ValueError, match="SHA-256 checksum mismatch"):
        store.download_file_streaming(
            resolved,
            bad_dest,
            expected_sha256="f" * 64,
            expected_size_bytes=len(payload),
        )
    assert not bad_dest.exists()

    # On-demand retrieval from coverage._resolve_raw_dem_open_path
    local_raw_dir = tmp_path / "datasets" / "raw"
    local_raw_dir.mkdir(parents=True, exist_ok=True)
    ds = _make_pds3_dataset()
    ds.local_file_path = f"raw/{ds.product_id}"
    ds.sha256_checksum = expected_sha
    ds.file_size_bytes = len(payload)

    monkeypatch.setattr("app.ingestion.gcs_storage.GCSDatasetStore.from_env", classmethod(lambda cls: store))
    retrieved_path, _ = _resolve_raw_dem_open_path(ds, local_raw_dir)
    assert retrieved_path.exists()
    assert retrieved_path.read_bytes() == payload


def test_acquisition_job_fails_nonzero_when_mandatory_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = datasets_dir / "bootstrap_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "products": [
                    {
                        "id": "hirise_dteec_009149_1750",
                        "dataset_id": "hirise_dteec_009149_1750",
                        "product_id": "DTEEC_009149_1750_009294_1750_U01.IMG",
                        "product_title": "HiRISE Gale Crater DTM",
                        "product_type": "DEM",
                        "mission": "Mars Reconnaissance Orbiter",
                        "instrument": "HiRISE",
                        "source_archive": "NASA PDS HiRISE",
                        "original_product_url": "https://example.org/pds/DTEEC_009149_1750_009294_1750_U01.IMG",
                        "attribution": "NASA/JPL-Caltech/UArizona",
                        "coverage": {
                            "min_latitude": -5.6,
                            "max_latitude": -4.5,
                            "min_longitude": 137.0,
                            "max_longitude": 137.8,
                        },
                        "role": "core_mandatory",
                        "expected_raw_path": "raw/DTEEC_009149_1750_009294_1750_U01.IMG",
                        "expected_size_bytes": 390551132,
                        "expected_sha256": "74881a6f7af9f3dcacbee72cf148020467bba5fac5dec4b5349a614397455e32",
                    }
                ],
            }
        )
    )

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        return _FakeResponse(status_code=503, chunks=[])

    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )
    monkeypatch.setenv("MARSCOPE_DATASETS_DIR", str(datasets_dir))
    monkeypatch.setattr("sys.argv", ["acquire_datasets_job.py", "--no-gcs"])

    exit_code = acquire_datasets_job.main()
    assert exit_code == 1


def test_production_manifest_route_reads_gcs_persisted_dem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from app.api import terrain_mesh as terrain_mesh_api
    from app.ingestion.catalog import DatasetCatalogService
    from app.main import app
    from app.terrain.mesh import TerrainMeshService

    ds_dir = tmp_path / "datasets"
    (ds_dir / "catalog").mkdir(parents=True, exist_ok=True)
    (ds_dir / "raw").mkdir(parents=True, exist_ok=True)

    import numpy as np
    import rasterio
    from rasterio.transform import from_bounds

    ds = _make_pds3_dataset(product_id="DTEEC_009149_1750_009294_1750_U01.tif")
    ds.local_file_path = f"raw/{ds.product_id}"
    catalog = DatasetCatalogService(ds_dir / "catalog")
    catalog.register_dataset(ds)

    src_file = tmp_path / "src" / ds.product_id
    src_file.parent.mkdir(parents=True, exist_ok=True)
    elev = np.linspace(-4500.0, -4400.0, 16 * 16, dtype=np.float32).reshape((16, 16))
    with rasterio.open(
        src_file,
        "w",
        driver="GTiff",
        height=16,
        width=16,
        count=1,
        dtype="float32",
        crs="+proj=longlat +a=3396190 +b=3396190 +no_defs",
        transform=from_bounds(137.0, -5.6, 137.8, -4.5, 16, 16),
    ) as dst:
        dst.write(elev, 1)
    expected_sha = hashlib.sha256(src_file.read_bytes()).hexdigest()
    ds.sha256_checksum = expected_sha
    ds.file_size_bytes = src_file.stat().st_size
    catalog.register_dataset(ds)

    fake_client = _FakeGCSClient()
    store = GCSDatasetStore(bucket_name="marscope-test-bucket", prefix="datasets", client=fake_client)
    store.upload_file_streaming(src_file, f"raw/{ds.product_id}", expected_sha256=expected_sha)

    monkeypatch.setattr(
        terrain_mesh_api,
        "terrain_mesh_service",
        TerrainMeshService(catalog_service=catalog, raw_dir=ds_dir / "raw"),
    )
    monkeypatch.setattr("app.ingestion.gcs_storage.GCSDatasetStore.from_env", classmethod(lambda cls: store))

    client = TestClient(app)
    resp = client.get("/api/terrain/mesh/manifest", params={"dataset_id": "hirise_dteec_009149_1750"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_id"] == "hirise_dteec_009149_1750"
    assert body["product_id"] == ds.product_id
    assert len(body["lod_levels"]) > 0
    assert len(body["tiles"]) > 0
    assert (ds_dir / "raw" / ds.product_id).exists()


def test_targeted_hirise_acquisition_and_full_manifest_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ingestion.bootstrap import verify_local_datasets

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    payload = _sample_pds3_img_bytes(16384)
    expected_sha = hashlib.sha256(payload).hexdigest()

    manifest_path = datasets_dir / "bootstrap_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "products": [
                    {
                        "id": "hirise_dteec_009149_1750",
                        "dataset_id": "hirise_dteec_009149_1750",
                        "product_id": "DTEEC_009149_1750_009294_1750_U01.IMG",
                        "product_title": "HiRISE Gale Crater DTM",
                        "product_type": "DEM",
                        "mission": "Mars Reconnaissance Orbiter",
                        "instrument": "HiRISE",
                        "source_archive": "NASA PDS HiRISE",
                        "original_product_url": "https://example.org/pds/DTEEC_009149_1750_009294_1750_U01.IMG",
                        "source_url": "https://example.org/pds/DTEEC_009149_1750_009294_1750_U01.IMG",
                        "attribution": "NASA/JPL-Caltech/UArizona",
                        "coverage": {
                            "min_latitude": -5.6,
                            "max_latitude": -4.5,
                            "min_longitude": 137.0,
                            "max_longitude": 137.8,
                        },
                        "mandatory_for_gale_workflow": True,
                        "expected_raw_path": "raw/dteec_009149_1750_009294_1750_u01.img",
                        "expected_label_path": "raw/dteec_009149_1750_009294_1750_u01.img",
                        "expected_size_bytes": len(payload),
                        "expected_sha256": expected_sha,
                    },
                    {
                        "id": "rems_env_surface",
                        "dataset_id": "rems_env_surface",
                        "product_id": "REMS_ENV.TAB",
                        "product_title": "REMS Environmental",
                        "product_type": "ATMOSPHERIC",
                        "mission": "MSL",
                        "instrument": "REMS",
                        "source_archive": "NASA PDS",
                        "original_product_url": "https://example.org/pds/REMS_ENV.TAB",
                        "source_url": "https://example.org/pds/REMS_ENV.TAB",
                        "attribution": "NASA/JPL",
                        "coverage": {
                            "min_latitude": -5.6,
                            "max_latitude": -4.5,
                            "min_longitude": 137.0,
                            "max_longitude": 137.8,
                        },
                        "mandatory_for_gale_workflow": True,
                        "expected_raw_path": "raw/rems_env.tab",
                        "expected_size_bytes": 1024,
                        "expected_sha256": "a" * 64,
                    },
                    {
                        "id": "chemcam_libs_spectra",
                        "dataset_id": "chemcam_libs_spectra",
                        "product_id": "CHEMCAM.CSV",
                        "product_title": "ChemCam LIBS",
                        "product_type": "SPECTRUM",
                        "mission": "MSL",
                        "instrument": "ChemCam",
                        "source_archive": "NASA PDS",
                        "original_product_url": "https://example.org/pds/CHEMCAM.CSV",
                        "source_url": "https://example.org/pds/CHEMCAM.CSV",
                        "attribution": "NASA/LANL",
                        "coverage": {
                            "min_latitude": -5.6,
                            "max_latitude": -4.5,
                            "min_longitude": 137.0,
                            "max_longitude": 137.8,
                        },
                        "mandatory_for_gale_workflow": False,
                        "expected_raw_path": "raw/chemcam.csv",
                        "expected_size_bytes": 512,
                        "expected_sha256": "b" * 64,
                    },
                ],
            }
        )
    )

    def handler(method: str, url: str, headers: Dict[str, str]) -> _FakeResponse:
        return _FakeResponse(
            status_code=200,
            chunks=[payload[:8192], payload[8192:]],
            headers={"Content-Length": str(len(payload)), "Content-Type": "application/octet-stream"},
        )

    fake_client = _FakeGCSClient()
    store = GCSDatasetStore(
        bucket_name="marscope-datasets-marscope-514815",
        prefix="datasets",
        client=fake_client,
    )
    monkeypatch.setattr(
        "app.ingestion.acquisition.create_async_http_client",
        lambda **kwargs: _FakeAsyncClient(handler),
    )
    monkeypatch.setattr("app.ingestion.gcs_storage.GCSDatasetStore.from_env", classmethod(lambda cls: store))

    # 1. Targeted HiRISE acquisition mode succeeds without unrelated REMS/ChemCam files
    result = acquire_datasets_job.run_acquisition_job(
        datasets_dir=datasets_dir,
        dataset_ids=["hirise_dteec_009149_1750"],
        upload_to_gcs=True,
        mode="targeted",
    )
    assert result["preflight_passed"] is True
    assert result["verification"]["verified_count"] == 1
    assert result["verification"]["total_manifest_products"] == 1
    assert result["verification"]["missing_mandatory_count"] == 0
    raw_uploads = [u for u in result["gcs_uploads"] if u["object_name"].endswith(".IMG")]
    assert len(raw_uploads) == 1
    assert raw_uploads[0]["bucket"] == "marscope-datasets-marscope-514815"
    assert raw_uploads[0]["object_name"] == "datasets/raw/DTEEC_009149_1750_009294_1750_U01.IMG"
    assert raw_uploads[0]["sha256"] == expected_sha
    assert raw_uploads[0]["verified"] is True

    # 2. Full-manifest preflight still requires all mandatory products and does not falsely pass
    full_report = verify_local_datasets(datasets_dir=datasets_dir, verify_checksums=True, strict=True)
    assert full_report.preflight_passed is False
    assert full_report.total_manifest_products == 3
    assert full_report.verified_count == 1
    assert full_report.missing_mandatory_count == 1
    assert full_report.missing_optional_count == 1
