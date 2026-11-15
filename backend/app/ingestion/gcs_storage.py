"""
MARSCOPE Google Cloud Storage (GCS) Verified Dataset Store
Streams verified NASA DEMs/products to and from GCS with bounded memory,
incremental SHA-256 verification, and atomic local replacement.
Uses Application Default Credentials (Cloud Run / Cloud Run Job service account).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import threading
from typing import Any, Dict, Optional

from app.core.config import settings
from app.schemas.dataset import Dataset

_GCS_DOWNLOAD_LOCK = threading.Lock()
_CHUNK_BYTES = 262_144  # 256 KiB bounded streaming chunk size


def _compute_sha256_streaming(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class GCSDatasetStore:
    def __init__(
        self,
        bucket_name: str,
        prefix: str = "datasets",
        client: Optional[Any] = None,
    ) -> None:
        clean_bucket = (bucket_name or "").strip()
        if not clean_bucket:
            raise ValueError("MARSCOPE_GCS_BUCKET must be non-empty.")
        self.bucket_name = clean_bucket
        self.prefix = (prefix or "datasets").strip().strip("/")
        if client is None:
            from google.cloud import storage  # type: ignore[import-untyped]

            client = storage.Client()
        self.client = client
        self.bucket = self.client.bucket(self.bucket_name)

    @classmethod
    def from_env(cls) -> Optional["GCSDatasetStore"]:
        bucket_name = (os.getenv("MARSCOPE_GCS_BUCKET") or settings.MARSCOPE_GCS_BUCKET or "").strip()
        if not bucket_name:
            return None
        prefix = (os.getenv("MARSCOPE_GCS_PREFIX") or settings.MARSCOPE_GCS_PREFIX or "datasets").strip()
        return cls(bucket_name=bucket_name, prefix=prefix)

    def _object_name(self, relative_key: str) -> str:
        rel = relative_key.lstrip("/")
        return f"{self.prefix}/{rel}" if self.prefix else rel

    def find_raw_object_name(self, product_id: str) -> Optional[str]:
        """Resolve raw/<product_id> in GCS supporting case-insensitive filenames."""
        candidates = []
        for name in (product_id.lower(), product_id, product_id.upper()):
            obj = self._object_name(f"raw/{name}")
            if obj not in candidates:
                candidates.append(obj)
        for obj_name in candidates:
            blob = self.bucket.blob(obj_name)
            if blob.exists():
                return obj_name

        target_lower = product_id.lower()
        raw_prefix = self._object_name("raw/")
        for blob in self.client.list_blobs(self.bucket_name, prefix=raw_prefix):
            if Path(blob.name).name.lower() == target_lower:
                return str(blob.name)
        return None

    def upload_file_streaming(
        self,
        local_path: Path,
        relative_key: str,
        *,
        expected_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"Cannot upload missing file: {local_path}")
        actual_sha = _compute_sha256_streaming(local_path)
        if expected_sha256 and actual_sha != expected_sha256.strip().lower():
            raise ValueError(
                f"Refusing to upload '{local_path.name}' to GCS: SHA-256 mismatch "
                f"(got {actual_sha}, expected {expected_sha256})."
            )
        obj_name = self._object_name(relative_key)
        blob = self.bucket.blob(obj_name)
        actual_size = local_path.stat().st_size
        blob.chunk_size = 8 * 1024 * 1024  # 8 MiB resumable upload chunks
        blob.metadata = {"sha256": actual_sha}
        blob.upload_from_filename(str(local_path))
        verified = self.verify_uploaded_object(
            obj_name,
            expected_size_bytes=actual_size,
            expected_sha256=actual_sha,
        )
        return {
            "bucket": self.bucket_name,
            "object_name": obj_name,
            "size_bytes": actual_size,
            "sha256": actual_sha,
            "verified": verified,
        }

    def verify_uploaded_object(
        self,
        object_name: str,
        *,
        expected_size_bytes: Optional[int] = None,
        expected_sha256: Optional[str] = None,
    ) -> bool:
        """Verify an uploaded GCS object exists and matches expected size and SHA-256 metadata."""
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"Uploaded GCS object 'gs://{self.bucket_name}/{object_name}' could not be verified (not found)."
            )
        if hasattr(blob, "reload"):
            blob.reload()
        remote_size = getattr(blob, "size", None)
        if expected_size_bytes is not None and remote_size is not None and int(remote_size) != int(expected_size_bytes):
            raise ValueError(
                f"GCS object '{object_name}' size mismatch after upload: got {remote_size}, expected {expected_size_bytes}."
            )
        remote_meta = getattr(blob, "metadata", None) or {}
        remote_sha = str(remote_meta.get("sha256") or "").strip().lower()
        if expected_sha256 and remote_sha and remote_sha != expected_sha256.strip().lower():
            raise ValueError(
                f"GCS object '{object_name}' SHA-256 metadata mismatch after upload: got {remote_sha}, expected {expected_sha256}."
            )
        return True

    def download_file_streaming(
        self,
        object_name: str,
        local_path: Path,
        *,
        expected_sha256: Optional[str] = None,
        expected_size_bytes: Optional[int] = None,
    ) -> Path:
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"GCS object 'gs://{self.bucket_name}/{object_name}' does not exist."
            )

        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = local_path.parent / f".{local_path.name}.gcs_tmp"
        tmp_path.unlink(missing_ok=True)
        try:
            with tmp_path.open("wb") as fh:
                blob.download_to_file(fh)
                fh.flush()

            actual_size = tmp_path.stat().st_size
            if actual_size <= 0:
                raise ValueError(f"GCS object '{object_name}' downloaded 0 bytes.")
            if expected_size_bytes is not None and actual_size != expected_size_bytes:
                raise ValueError(
                    f"GCS size mismatch for '{object_name}': got {actual_size} bytes, expected {expected_size_bytes}."
                )

            actual_sha = _compute_sha256_streaming(tmp_path)
            if expected_sha256 and actual_sha != expected_sha256.strip().lower():
                raise ValueError(
                    f"GCS SHA-256 checksum mismatch for '{object_name}': got {actual_sha}, expected {expected_sha256}."
                )

            os.replace(tmp_path, local_path)
            return local_path
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def ensure_raw_dataset_on_disk(
        self,
        dataset: Dataset,
        raw_dir: Path,
        *,
        expected_sha256: Optional[str] = None,
        expected_size_bytes: Optional[int] = None,
    ) -> Optional[Path]:
        """Thread-safe on-demand retrieval of a verified raw NASA product from GCS."""
        with _GCS_DOWNLOAD_LOCK:
            target_lower = dataset.product_id.lower()
            if raw_dir.exists():
                for entry in raw_dir.iterdir():
                    if entry.is_file() and entry.name.lower() == target_lower:
                        return entry

            obj_name = self.find_raw_object_name(dataset.product_id)
            if not obj_name:
                return None
            dest_path = raw_dir / Path(obj_name).name
            return self.download_file_streaming(
                obj_name,
                dest_path,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size_bytes,
            )
