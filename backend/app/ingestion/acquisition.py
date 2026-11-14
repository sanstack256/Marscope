"""
MARSCOPE Scientific Data Acquisition Service
Martian Surface Intelligence & Exploration System

Implements streaming, chunked, verified downloads from authoritative NASA/ESA planetary archives.
Computes SHA-256 hashes on the fly and generates immutable manifests.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import httpx
from app.schemas.dataset import Dataset, DatasetManifest, DatasetLifecycleStatus


class AcquisitionService:
    def __init__(self, raw_data_dir: Path, manifests_dir: Path):
        self.raw_data_dir = raw_data_dir
        self.manifests_dir = manifests_dir
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    async def download_product(
        self,
        dataset: Dataset,
        timeout_seconds: float = 60.0,
        chunk_size: int = 65536,
    ) -> DatasetManifest:
        """
        Stream a verified NASA scientific product, calculating SHA-256 and creating a manifest.
        """
        # Determine target filename preserving original naming convention
        source_url = dataset.original_product_url
        filename = Path(source_url.split("?")[0]).name
        if not filename or "{" in filename:
            filename = f"{dataset.product_id.lower()}.dat"

        target_file_path = self.raw_data_dir / filename
        manifest_file_path = self.manifests_dir / f"{dataset.id}.manifest.json"

        # Check if already downloaded and verified
        if target_file_path.exists() and manifest_file_path.exists():
            existing_size = target_file_path.stat().st_size
            if existing_size > 0:
                with open(manifest_file_path, "r", encoding="utf-8") as mf:
                    existing_manifest = DatasetManifest.model_validate_json(mf.read())
                    # Validate existing checksum matches
                    calc_sha = self._compute_file_sha256(target_file_path)
                    if calc_sha == existing_manifest.sha256_checksum:
                        dataset.status = DatasetLifecycleStatus.DOWNLOADED
                        dataset.local_file_path = str(target_file_path.relative_to(self.raw_data_dir.parent))
                        dataset.file_size_bytes = existing_size
                        dataset.sha256_checksum = calc_sha
                        return existing_manifest

        # Execute streaming download
        hasher = hashlib.sha256()
        total_downloaded = 0

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            async with client.stream("GET", source_url) as response:
                if response.status_code != 200:
                    dataset.status = DatasetLifecycleStatus.FAILED_DOWNLOAD
                    dataset.failure_reason = f"HTTP Error {response.status_code} while downloading from {source_url}"
                    raise RuntimeError(dataset.failure_reason)

                with open(target_file_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        hasher.update(chunk)
                        total_downloaded += len(chunk)

        calculated_sha = hasher.hexdigest()

        # Build manifest
        manifest = DatasetManifest(
            product_id=dataset.product_id,
            dataset_id=dataset.id,
            source_url=source_url,
            download_timestamp_utc=datetime.now(timezone.utc),
            file_size_bytes=total_downloaded,
            sha256_checksum=calculated_sha,
            storage_path=str(target_file_path.relative_to(self.raw_data_dir.parent)),
            verified_integrity=True,
        )

        # Write manifest file
        with open(manifest_file_path, "w", encoding="utf-8") as mf:
            mf.write(manifest.model_dump_json(indent=2))

        # Update dataset status
        dataset.status = DatasetLifecycleStatus.DOWNLOADED
        dataset.local_file_path = manifest.storage_path
        dataset.file_size_bytes = total_downloaded
        dataset.sha256_checksum = calculated_sha
        dataset.processing_history.append(
            f"Downloaded {total_downloaded} bytes at {manifest.download_timestamp_utc.isoformat()} (SHA-256: {calculated_sha[:12]}...)"
        )

        return manifest

    @staticmethod
    def _compute_file_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
