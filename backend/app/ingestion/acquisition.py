"""
MARSCOPE Scientific Data Acquisition Service
Martian Surface Intelligence & Exploration System

Implements streaming, chunked, verified downloads from authoritative NASA/ESA planetary archives.
Computes SHA-256 hashes on the fly, fetches paired PDS labels when provided, and writes immutable manifests.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from app.ingestion.http_client import create_async_http_client
from app.ingestion.pds_label import extract_pds3_metadata
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    DatasetManifest,
    VerificationState,
)


class AcquisitionService:
    def __init__(self, raw_data_dir: Path, manifests_dir: Path):
        self.raw_data_dir = raw_data_dir
        self.manifests_dir = manifests_dir
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    async def download_product(
        self,
        dataset: Dataset,
        timeout_seconds: float = 120.0,
        chunk_size: int = 65536,
    ) -> DatasetManifest:
        """
        Stream a verified NASA scientific product and its companion PDS3 label (if present),
        computing SHA-256 and writing an immutable download manifest.
        """
        source_url = dataset.original_product_url
        if "{" in source_url:
            raise ValueError(
                f"Dataset '{dataset.id}' is a tiled WMTS endpoint, not a single downloadable binary product."
            )

        filename = Path(source_url.split("?")[0]).name
        if not filename:
            filename = f"{dataset.product_id.lower()}.dat"

        target_file_path = self.raw_data_dir / filename
        manifest_file_path = self.manifests_dir / f"{dataset.id}.manifest.json"
        label_rel_path: Optional[str] = None

        # Download companion PDS3 label first when available
        if dataset.original_label_url:
            lbl_name = Path(dataset.original_label_url.split("?")[0]).name
            if lbl_name:
                # Preserve exact stem matching target_file_path for GDAL PDS driver when .lbl
                if lbl_name.lower().endswith(".lbl"):
                    target_lbl_path = target_file_path.with_suffix(".lbl")
                else:
                    target_lbl_path = self.raw_data_dir / f"{dataset.id}_{lbl_name}"
                try:
                    async with create_async_http_client(timeout_seconds=30.0) as client:
                        lbl_resp = await client.get(dataset.original_label_url)
                        if lbl_resp.status_code == 200:
                            target_lbl_path.write_bytes(lbl_resp.content)
                            label_rel_path = str(target_lbl_path.relative_to(self.raw_data_dir.parent))
                            dataset.local_label_path = label_rel_path
                            self._apply_pds3_label_verification(dataset, target_lbl_path)
                except Exception as exc:
                    dataset.verification.evidence_notes.append(f"Companion label fetch warning: {exc}")

        # Reuse verified file if intact manifest matches SHA-256
        if target_file_path.exists() and manifest_file_path.exists():
            existing_size = target_file_path.stat().st_size
            if existing_size > 0:
                existing_manifest = DatasetManifest.model_validate_json(manifest_file_path.read_text(encoding="utf-8"))
                calc_sha = self._compute_file_sha256(target_file_path)
                if calc_sha == existing_manifest.sha256_checksum:
                    dataset.status = DatasetLifecycleStatus.DOWNLOADED
                    dataset.local_file_path = str(target_file_path.relative_to(self.raw_data_dir.parent))
                    dataset.file_size_bytes = existing_size
                    dataset.sha256_checksum = calc_sha
                    dataset.verification.archive_availability = VerificationState.VERIFIED
                    dataset.verification.download_verification = VerificationState.VERIFIED
                    return existing_manifest

        # Execute streaming download
        hasher = hashlib.sha256()
        total_downloaded = 0

        async with create_async_http_client(timeout_seconds=timeout_seconds) as client:
            async with client.stream("GET", source_url) as response:
                if response.status_code != 200:
                    dataset.status = DatasetLifecycleStatus.FAILED_DOWNLOAD
                    dataset.failure_reason = f"HTTP Error {response.status_code} while downloading from {source_url}"
                    dataset.verification.archive_availability = VerificationState.FAILED
                    dataset.verification.download_verification = VerificationState.FAILED
                    raise RuntimeError(dataset.failure_reason)

                with open(target_file_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        hasher.update(chunk)
                        total_downloaded += len(chunk)

        calculated_sha = hasher.hexdigest()

        manifest = DatasetManifest(
            product_id=dataset.product_id,
            dataset_id=dataset.id,
            source_url=source_url,
            download_timestamp_utc=datetime.now(timezone.utc),
            file_size_bytes=total_downloaded,
            sha256_checksum=calculated_sha,
            storage_path=str(target_file_path.relative_to(self.raw_data_dir.parent)),
            label_storage_path=label_rel_path,
            verified_integrity=True,
        )
        manifest_file_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        dataset.status = DatasetLifecycleStatus.DOWNLOADED
        dataset.local_file_path = manifest.storage_path
        dataset.file_size_bytes = total_downloaded
        dataset.sha256_checksum = calculated_sha
        dataset.verification.archive_availability = VerificationState.VERIFIED
        dataset.verification.download_verification = VerificationState.VERIFIED
        dataset.verification.last_checked_utc = datetime.now(timezone.utc)
        dataset.verification.evidence_notes.append(
            f"Downloaded {total_downloaded} bytes; SHA-256={calculated_sha[:16]}..."
        )
        dataset.processing_history.append(
            f"Downloaded {total_downloaded} bytes at {manifest.download_timestamp_utc.isoformat()} (SHA-256: {calculated_sha[:12]}...)"
        )
        return manifest

    @staticmethod
    def _apply_pds3_label_verification(dataset: Dataset, label_path: Path) -> None:
        if label_path.suffix.lower() != ".lbl":
            return
        meta = extract_pds3_metadata(label_path)
        if meta.get("units") and meta["units"] != "unknown":
            dataset.units = str(meta["units"])
            dataset.verification.field_verification["units"] = VerificationState.VERIFIED
        if meta.get("planetary_radii_m"):
            dataset.planetary_radii_m = meta["planetary_radii_m"]
            dataset.verification.field_verification["crs"] = VerificationState.VERIFIED
        if meta.get("map_scale_m_per_px"):
            dataset.horizontal_resolution_meters = float(meta["map_scale_m_per_px"])
            dataset.verification.field_verification["resolution"] = VerificationState.VERIFIED
        if meta.get("latitude_convention") != "unknown":
            dataset.latitude_convention = str(meta["latitude_convention"])
        if meta.get("longitude_direction") != "unknown":
            dataset.longitude_direction = str(meta["longitude_direction"])
        if meta.get("longitude_range") != "unknown":
            dataset.coverage.longitude_range = str(meta["longitude_range"])
            dataset.verification.field_verification["coverage"] = VerificationState.VERIFIED
        dataset.verification.metadata_verification = VerificationState.VERIFIED
        dataset.verification.coverage_verification = VerificationState.VERIFIED
        dataset.verification.evidence_notes.append(f"Verified metadata from PDS3 label {label_path.name}")

    @staticmethod
    def _compute_file_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
