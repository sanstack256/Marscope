"""
MARSCOPE Scientific Data Acquisition Service
Martian Surface Intelligence & Exploration System

Implements streaming, chunked, verified downloads from authoritative NASA/ESA planetary archives.
Computes SHA-256 hashes on the fly, fetches paired PDS labels when provided, and writes immutable manifests.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from app.ingestion.http_client import create_async_http_client
from app.ingestion.pds_label import extract_pds3_metadata
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    DatasetManifest,
    VerificationState,
)


def _looks_like_html_error(payload: bytes, target_path: Path, content_type: Optional[str]) -> bool:
    """Detect HTML error pages masquerading as CSV/JSON/XML/LBL/TAB/FMT data artifacts."""
    sfx = target_path.suffix.lower()
    if sfx in {".html", ".htm"}:
        return False
    ct = (content_type or "").lower()
    if "text/html" in ct or "application/xhtml" in ct:
        return True
    head = payload[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def safe_write_downloaded_bytes(
    target_path: Path,
    payload: bytes,
    source_url: str,
    content_type: Optional[str] = None,
    expected_sha256: Optional[str] = None,
    http_status: int = 200,
    write_retrieval_sidecar: bool = True,
) -> Dict[str, Any]:
    """
    Validate and atomically write downloaded bytes to `target_path` via a sibling temporary file.
    Preserves any pre-existing valid `target_path` untouched if validation fails.
    """
    if not payload:
        raise ValueError(f"Empty download payload from '{source_url}' for '{target_path.name}'.")
    if _looks_like_html_error(payload, target_path, content_type):
        raise ValueError(
            f"Refusing HTML response (content_type={content_type!r}) for non-HTML artifact '{target_path.name}' from '{source_url}'."
        )
    if target_path.suffix.lower() == ".json":
        try:
            json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Downloaded JSON '{target_path.name}' failed JSON validation: {exc}") from exc

    calc_sha = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and calc_sha != expected_sha256.strip().lower():
        raise ValueError(
            f"SHA-256 checksum mismatch for '{target_path.name}': got {calc_sha}, expected {expected_sha256}."
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.parent / f".{target_path.name}.download_tmp"
    try:
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, target_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    now_utc = datetime.now(timezone.utc).isoformat()
    meta = {
        "file_name": target_path.name,
        "source_url": source_url,
        "http_status": http_status,
        "content_type": content_type,
        "retrieval_timestamp_utc": now_utc,
        "sha256_checksum": calc_sha,
        "byte_size": len(payload),
    }
    if write_retrieval_sidecar:
        sidecar = target_path.parent / f".{target_path.name}.retrieval.json"
        tmp_sc = target_path.parent / f".{target_path.name}.retrieval.tmp"
        tmp_sc.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(tmp_sc, sidecar)
    return meta


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

        # Download companion PDS3/PDS4 label atomically first when available
        if dataset.original_label_url:
            lbl_name = Path(dataset.original_label_url.split("?")[0]).name
            if lbl_name:
                if lbl_name.lower().endswith(".lbl"):
                    target_lbl_path = target_file_path.with_suffix(".lbl")
                elif lbl_name.lower().endswith(".xml"):
                    target_lbl_path = target_file_path.with_suffix(".xml")
                else:
                    target_lbl_path = self.raw_data_dir / f"{dataset.id}_{lbl_name}"
                try:
                    async with create_async_http_client(timeout_seconds=30.0) as client:
                        lbl_resp = await client.get(dataset.original_label_url)
                        if lbl_resp.status_code == 200:
                            safe_write_downloaded_bytes(
                                target_lbl_path,
                                lbl_resp.content,
                                source_url=dataset.original_label_url,
                                content_type=lbl_resp.headers.get("content-type"),
                                http_status=lbl_resp.status_code,
                            )
                            label_rel_path = str(target_lbl_path.relative_to(self.raw_data_dir.parent))
                            dataset.local_label_path = label_rel_path
                            self._apply_pds3_label_verification(dataset, target_lbl_path)
                        else:
                            dataset.verification.evidence_notes.append(
                                f"Companion label HTTP {lbl_resp.status_code} from {dataset.original_label_url}; preserved local file if any."
                            )
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

        # Execute streaming download into validated buffer/temp file before atomic replace
        chunks = bytearray()
        content_type: Optional[str] = None
        http_status = 0

        async with create_async_http_client(timeout_seconds=timeout_seconds) as client:
            async with client.stream("GET", source_url) as response:
                http_status = response.status_code
                content_type = response.headers.get("content-type")
                if response.status_code != 200:
                    dataset.status = DatasetLifecycleStatus.FAILED_DOWNLOAD
                    dataset.failure_reason = f"HTTP Error {response.status_code} while downloading from {source_url}"
                    dataset.verification.archive_availability = VerificationState.FAILED
                    dataset.verification.download_verification = VerificationState.FAILED
                    raise RuntimeError(dataset.failure_reason)

                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    chunks.extend(chunk)

        try:
            dl_meta = safe_write_downloaded_bytes(
                target_file_path,
                bytes(chunks),
                source_url=source_url,
                content_type=content_type,
                http_status=http_status,
            )
        except Exception as exc:
            dataset.status = DatasetLifecycleStatus.FAILED_DOWNLOAD
            dataset.failure_reason = str(exc)
            dataset.verification.download_verification = VerificationState.FAILED
            raise

        total_downloaded = int(dl_meta["byte_size"])
        calculated_sha = str(dl_meta["sha256_checksum"])

        manifest = DatasetManifest(
            product_id=dataset.product_id,
            dataset_id=dataset.id,
            source_url=source_url,
            download_timestamp_utc=datetime.fromisoformat(dl_meta["retrieval_timestamp_utc"]),
            file_size_bytes=total_downloaded,
            sha256_checksum=calculated_sha,
            storage_path=str(target_file_path.relative_to(self.raw_data_dir.parent)),
            label_storage_path=label_rel_path,
            verified_integrity=True,
        )
        tmp_manifest = manifest_file_path.with_suffix(".tmp")
        tmp_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp_manifest, manifest_file_path)

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
