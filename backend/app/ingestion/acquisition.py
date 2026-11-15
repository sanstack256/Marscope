"""
MARSCOPE Scientific Data Acquisition Service
Martian Surface Intelligence & Exploration System

Implements streaming, chunked, verified downloads from authoritative NASA/ESA planetary archives.
Computes SHA-256 hashes on the fly, fetches paired PDS labels when provided, and writes immutable manifests.
"""

import hashlib
import json
import os
import tempfile
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from app.ingestion.http_client import create_async_http_client
from app.ingestion.pds_label import extract_pds3_metadata, extract_pds4_metadata
from app.schemas.dataset import (
    AcquisitionState,
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


def validate_artifact_signature(
    prefix: bytes,
    target_path: Path,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate magic bytes / content signatures matching the target extension and reject
    disguised HTML or archive error responses.
    """
    if not prefix:
        raise ValueError(f"Empty download payload for '{target_path.name}'.")
    if _looks_like_html_error(prefix, target_path, content_type):
        raise ValueError(
            f"Refusing HTML response (content_type={content_type!r}) for non-HTML artifact '{target_path.name}'."
        )
    sfx = target_path.suffix.lower()
    head_l = prefix[:512].lstrip().lower()
    if sfx not in {".xml", ".html", ".htm"} and (
        b"<exceptionreport" in head_l or b"<serviceexceptionreport" in head_l or head_l.startswith(b"<?xml")
        and sfx in {".tif", ".tiff", ".jp2", ".j2k", ".png", ".jpg", ".jpeg", ".csv", ".tab", ".json"}
    ):
        raise ValueError(
            f"Refusing XML error/service response (content_type={content_type!r}) for artifact '{target_path.name}'."
        )

    sig_kind = "generic_binary_or_text"
    if sfx in {".tif", ".tiff"}:
        if not prefix.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")):
            raise ValueError(f"Artifact '{target_path.name}' lacks a valid TIFF/GeoTIFF magic header.")
        sig_kind = "geotiff_or_tiff"
    elif sfx in {".jp2", ".j2k"}:
        if not (prefix.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n") or prefix.startswith(b"\xff\x4f\xff\x51")):
            raise ValueError(f"Artifact '{target_path.name}' lacks a valid JP2 or JPEG2000 codestream signature.")
        sig_kind = "jpeg2000"
    elif sfx == ".png":
        if not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"Artifact '{target_path.name}' lacks a valid PNG signature.")
        sig_kind = "png"
    elif sfx in {".jpg", ".jpeg"}:
        if not prefix.startswith(b"\xff\xd8\xff"):
            raise ValueError(f"Artifact '{target_path.name}' lacks a valid JPEG signature.")
        sig_kind = "jpeg"
    elif sfx == ".lbl":
        head_u = prefix[:256].lstrip()
        if not (head_u.startswith(b"PDS_VERSION_ID") or head_l.startswith(b"<?xml") or b"<product" in head_l):
            raise ValueError(f"Artifact '{target_path.name}' lacks a recognized PDS3/PDS4 label header.")
        sig_kind = "pds_label"
    elif sfx == ".xml":
        if not prefix.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
            raise ValueError(f"Artifact '{target_path.name}' does not begin with XML markup.")
        sig_kind = "xml"
    elif sfx == ".json":
        stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
        if not stripped.startswith((b"{", b"[")):
            raise ValueError(f"Downloaded JSON '{target_path.name}' failed JSON validation: missing JSON root token.")
        sig_kind = "json"
    elif sfx in {".csv", ".tab", ".fmt", ".txt", ".sts"}:
        if b"\x00" in prefix:
            raise ValueError(f"Text/tabular artifact '{target_path.name}' contains unexpected binary NUL bytes.")
        try:
            prefix.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            prefix.decode("latin-1", errors="strict")
        sig_kind = "delimited_or_text"
    elif sfx == ".img":
        sig_kind = "pds3_attached_img" if b"PDS_VERSION_ID" in prefix[:1024] else "binary_pds_img"

    return {"signature_kind": sig_kind, "signature_verified": True}


def safe_write_downloaded_bytes(
    target_path: Path,
    payload: bytes,
    source_url: str,
    content_type: Optional[str] = None,
    expected_sha256: Optional[str] = None,
    http_status: int = 200,
    write_retrieval_sidecar: bool = True,
    max_bytes: Optional[int] = None,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Validate and atomically write downloaded bytes to `target_path` via a sibling temporary file.
    Preserves any pre-existing valid `target_path` untouched if validation fails or overwrite=False.
    """
    if not payload:
        raise ValueError(f"Empty download payload from '{source_url}' for '{target_path.name}'.")
    if max_bytes is not None and len(payload) > max_bytes:
        raise ValueError(f"Download payload exceeds max_bytes limit ({max_bytes} bytes) for '{target_path.name}'.")
    if _looks_like_html_error(payload, target_path, content_type):
        raise ValueError(
            f"Refusing HTML response (content_type={content_type!r}) for non-HTML artifact '{target_path.name}' from '{source_url}'."
        )
    if target_path.suffix.lower() == ".json":
        try:
            json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Downloaded JSON '{target_path.name}' failed JSON validation: {exc}") from exc
    sig_meta = validate_artifact_signature(payload[:4096], target_path, content_type)

    calc_sha = hashlib.sha256(payload).hexdigest()
    if expected_sha256 and calc_sha != expected_sha256.strip().lower():
        raise ValueError(
            f"SHA-256 checksum mismatch for '{target_path.name}': got {calc_sha}, expected {expected_sha256}."
        )
    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing local file '{target_path.name}' when overwrite=False."
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
        "signature_kind": sig_meta["signature_kind"],
        "signature_verified": True,
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
        self.ledger_path = self.manifests_dir / "acquisition_ledger.jsonl"
        self.query_provenance_path = self.manifests_dir / "query_provenance.jsonl"
        self._download_lock = asyncio.Lock()

    @staticmethod
    def _format_exc_detail(
        exc: Exception,
        *,
        http_status: Optional[int] = None,
        bytes_downloaded: int = 0,
        declared_size: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> str:
        msg = str(exc).strip() or repr(exc)
        parts = [f"{type(exc).__name__}: {msg}"]
        if http_status:
            parts.append(f"http_status={http_status}")
        parts.append(f"bytes_downloaded={bytes_downloaded}")
        if declared_size is not None:
            parts.append(f"declared_size={declared_size}")
        if timeout_seconds is not None:
            parts.append(f"timeout_seconds={timeout_seconds}")
        return " | ".join(parts)

    def _append_jsonl(self, path: Path, record: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")

    def record_query_provenance(
        self,
        *,
        archive_name: str,
        endpoint: str,
        params: Dict[str, Any],
        http_status: Optional[int],
        result_count: Optional[int],
        success: bool,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        rec = {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "archive_name": archive_name,
            "endpoint": endpoint,
            "params": params,
            "http_status": http_status,
            "result_count": result_count,
            "success": success,
            "error": error,
            "lifecycle_stage": "discovered_only_not_acquired",
        }
        self._append_jsonl(self.query_provenance_path, rec)
        return rec

    def _record_acquisition_ledger(self, entry: Dict[str, Any]) -> None:
        self._append_jsonl(self.ledger_path, entry)

    def get_acquisition_ledger(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        lines = [ln for ln in self.ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines[-limit:]]

    def get_query_provenance(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.query_provenance_path.exists():
            return []
        lines = [ln for ln in self.query_provenance_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines[-limit:]]

    async def download_product(
        self,
        dataset: Dataset,
        timeout_seconds: float = 600.0,
        chunk_size: int = 65536,
        max_bytes: Optional[int] = 1_500_000_000,
        overwrite: bool = False,
        expected_sha256: Optional[str] = None,
        max_retries: int = 3,
        allow_resume: bool = True,
    ) -> DatasetManifest:
        """
        Stream a verified NASA scientific product and its companion PDS label (if present),
        computing SHA-256 incrementally while streaming to a sibling temporary file with strict
        max_bytes, bounded chunk memory, magic-byte validation, non-overwrite guarantees, bounded
        transient retries, and strictly verified HTTP Range resumption. Serializes large downloads
        so multiple products are never streamed concurrently.
        """
        async with self._download_lock:
            return await self._download_product_locked(
                dataset=dataset,
                timeout_seconds=timeout_seconds,
                chunk_size=chunk_size,
                max_bytes=max_bytes,
                overwrite=overwrite,
                expected_sha256=expected_sha256,
                max_retries=max_retries,
                allow_resume=allow_resume,
            )

    async def _download_product_locked(
        self,
        dataset: Dataset,
        timeout_seconds: float = 600.0,
        chunk_size: int = 65536,
        max_bytes: Optional[int] = 1_500_000_000,
        overwrite: bool = False,
        expected_sha256: Optional[str] = None,
        max_retries: int = 3,
        allow_resume: bool = True,
    ) -> DatasetManifest:
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
        dataset.acquisition_state = AcquisitionState.DOWNLOAD_PENDING

        # Download companion PDS3/PDS4 label atomically first when available as a separate label file
        if (
            dataset.original_label_url
            and dataset.original_label_url != source_url
            and not dataset.original_label_url.lower().split("?")[0].endswith(".img")
        ):
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
                                max_bytes=20_000_000,
                                overwrite=overwrite or not target_lbl_path.exists(),
                            )
                            label_rel_path = str(target_lbl_path.relative_to(self.raw_data_dir.parent))
                            dataset.local_label_path = label_rel_path
                            self._apply_pds_label_verification(dataset, target_lbl_path)
                        else:
                            dataset.verification.evidence_notes.append(
                                f"Companion label HTTP {lbl_resp.status_code} from {dataset.original_label_url}; preserved local file if any."
                            )
                except Exception as exc:
                    dataset.verification.evidence_notes.append(f"Companion label fetch warning: {exc}")

        # Reuse verified file if intact manifest matches SHA-256 (prevent duplicate downloads)
        if target_file_path.exists() and manifest_file_path.exists() and not overwrite:
            existing_size = target_file_path.stat().st_size
            if existing_size > 0:
                existing_manifest = DatasetManifest.model_validate_json(manifest_file_path.read_text(encoding="utf-8"))
                calc_sha = self._compute_file_sha256(target_file_path)
                if calc_sha == existing_manifest.sha256_checksum:
                    dataset.status = DatasetLifecycleStatus.DOWNLOADED
                    dataset.acquisition_state = AcquisitionState.INTEGRITY_VALIDATED
                    dataset.failure_reason = None
                    dataset.local_file_path = str(target_file_path.relative_to(self.raw_data_dir.parent))
                    dataset.file_size_bytes = existing_size
                    dataset.sha256_checksum = calc_sha
                    dataset.verification.archive_availability = VerificationState.VERIFIED
                    dataset.verification.download_verification = VerificationState.VERIFIED
                    self._record_acquisition_ledger(
                        {
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "dataset_id": dataset.id,
                            "product_id": dataset.product_id,
                            "source_url": source_url,
                            "outcome": "REUSED_VERIFIED_ARTIFACT",
                            "sha256_checksum": calc_sha,
                            "byte_size": existing_size,
                            "stage_after": AcquisitionState.INTEGRITY_VALIDATED.value,
                        }
                    )
                    return existing_manifest

        # Non-overwrite protection for unmanifested or pre-existing files
        if target_file_path.exists() and not overwrite:
            msg = f"Refusing to overwrite existing local file '{target_file_path.name}' when overwrite=False."
            dataset.acquisition_state = AcquisitionState.REJECTED
            self._record_acquisition_ledger(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "dataset_id": dataset.id,
                    "product_id": dataset.product_id,
                    "source_url": source_url,
                    "outcome": "FAILED_OVERWRITE_PROTECTED",
                    "error": msg,
                    "stage_after": AcquisitionState.REJECTED.value,
                }
            )
            raise FileExistsError(msg)

        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_file_path.parent / f".{target_file_path.name}.download_tmp"
        resume_meta_path = target_file_path.parent / f".{target_file_path.name}.resume.json"
        if not allow_resume and temp_path.exists():
            temp_path.unlink(missing_ok=True)
            resume_meta_path.unlink(missing_ok=True)

        total_downloaded = 0
        progress_bytes = 0
        declared_size: Optional[int] = None
        content_type: Optional[str] = None
        http_status = 0
        resumed_from_bytes = 0
        calculated_sha = ""
        sig_meta: Dict[str, Any] = {}
        effective_chunk_size = max(4096, min(int(chunk_size), 262144))
        stream_hasher = hashlib.sha256()

        try:
            dataset.acquisition_state = AcquisitionState.DOWNLOADING
            last_exc: Optional[Exception] = None
            attempts = max(1, int(max_retries))
            for attempt in range(attempts):
                try:
                    headers: Dict[str, str] = {}
                    existing_partial = temp_path.stat().st_size if (allow_resume and temp_path.exists()) else 0
                    saved_meta: Dict[str, Any] = {}
                    if existing_partial > 0 and resume_meta_path.exists():
                        try:
                            saved_meta = json.loads(resume_meta_path.read_text(encoding="utf-8"))
                        except Exception:
                            saved_meta = {}
                    if existing_partial > 0 and saved_meta.get("source_url") == source_url:
                        headers["Range"] = f"bytes={existing_partial}-"
                        if saved_meta.get("etag"):
                            headers["If-Range"] = str(saved_meta["etag"])
                    else:
                        existing_partial = 0
                        temp_path.unlink(missing_ok=True)

                    async with create_async_http_client(timeout_seconds=timeout_seconds) as client:
                        async with client.stream("GET", source_url, headers=headers) as response:
                            http_status = response.status_code
                            content_type = response.headers.get("content-type")
                            if response.status_code not in {200, 206}:
                                raise RuntimeError(
                                    f"HTTP Error {response.status_code} while downloading from {source_url}"
                                )

                            is_partial = response.status_code == 206 and existing_partial > 0
                            if existing_partial > 0 and not is_partial:
                                # Server ignored Range and restarted from byte 0: do not append duplicate bytes!
                                existing_partial = 0
                                temp_path.unlink(missing_ok=True)

                            resumed_from_bytes = existing_partial if is_partial else 0
                            progress_bytes = resumed_from_bytes
                            stream_hasher = hashlib.sha256()
                            if is_partial and temp_path.exists():
                                with temp_path.open("rb") as pf:
                                    while True:
                                        blk = pf.read(65536)
                                        if not blk:
                                            break
                                        stream_hasher.update(blk)

                            etag_hdr = response.headers.get("etag")
                            if is_partial:
                                cr = response.headers.get("content-range", "")
                                if "/" in cr and cr.split("/")[-1].isdigit():
                                    declared_size = int(cr.split("/")[-1])
                            else:
                                declared = response.headers.get("content-length")
                                declared_size = int(declared) if (declared and declared.isdigit()) else None

                            if declared_size is not None and max_bytes is not None and declared_size > max_bytes:
                                raise ValueError(
                                    f"Declared payload size ({declared_size} bytes) exceeds max_bytes limit ({max_bytes} bytes)."
                                )

                            from app.core.persistence import atomic_write_text

                            atomic_write_text(
                                resume_meta_path,
                                json.dumps({"source_url": source_url, "etag": etag_hdr}),
                            )
                            mode = "ab" if is_partial else "wb"
                            with temp_path.open(mode) as stream:
                                # Stream raw transport chunks as they arrive (chunk_size=None avoids
                                # httpx ByteChunker buffering/dropping partial bytes on mid-stream errors)
                                # and slice writes/hashing to <= effective_chunk_size for bounded memory.
                                async for raw_chunk in response.aiter_bytes(chunk_size=None):
                                    if not raw_chunk:
                                        continue
                                    for offset in range(0, len(raw_chunk), effective_chunk_size):
                                        chunk = raw_chunk[offset : offset + effective_chunk_size]
                                        if max_bytes is not None and (progress_bytes + len(chunk)) > max_bytes:
                                            raise ValueError(
                                                f"Streamed download exceeded max_bytes limit ({max_bytes} bytes) for '{target_file_path.name}'."
                                            )
                                        stream.write(chunk)
                                        stream_hasher.update(chunk)
                                        progress_bytes += len(chunk)
                                stream.flush()
                    last_exc = None
                    break
                except (httpx.TimeoutException, httpx.TransportError, RuntimeError) as exc:
                    last_exc = exc
                    if temp_path.exists():
                        progress_bytes = temp_path.stat().st_size
                    transient_http = isinstance(exc, RuntimeError) and any(
                        tok in str(exc) for tok in ("HTTP Error 429", "HTTP Error 500", "HTTP Error 502", "HTTP Error 503", "HTTP Error 504")
                    )
                    retryable = isinstance(exc, (httpx.TimeoutException, httpx.TransportError)) or transient_http
                    if attempt + 1 >= attempts or not retryable:
                        raise
                    await asyncio.sleep(0.1 * (2 ** attempt))

            if last_exc is not None:
                raise last_exc

            total_downloaded = temp_path.stat().st_size if temp_path.exists() else 0
            if total_downloaded == 0:
                raise ValueError(f"Empty download payload from '{source_url}' for '{target_file_path.name}'.")
            if declared_size is not None and declared_size != total_downloaded:
                raise ValueError(
                    f"Truncated or inconsistent download for '{target_file_path.name}': received {total_downloaded} bytes, archive declared {declared_size}."
                )

            with temp_path.open("rb") as pf:
                prefix_bytes = pf.read(4096)
            sig_meta = validate_artifact_signature(prefix_bytes, target_file_path, content_type)
            if target_file_path.suffix.lower() == ".json" and total_downloaded <= 50_000_000:
                try:
                    json.loads(temp_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise ValueError(
                        f"Downloaded JSON '{target_file_path.name}' failed JSON validation: {exc}"
                    ) from exc

            calculated_sha = stream_hasher.hexdigest()
            if expected_sha256 and calculated_sha != expected_sha256.strip().lower():
                raise ValueError(
                    f"SHA-256 checksum mismatch for '{target_file_path.name}': got {calculated_sha}, expected {expected_sha256}."
                )

            os.replace(temp_path, target_file_path)
            resume_meta_path.unlink(missing_ok=True)
            now_utc = datetime.now(timezone.utc)
            dl_meta = {
                "file_name": target_file_path.name,
                "source_url": source_url,
                "http_status": http_status,
                "content_type": content_type,
                "retrieval_timestamp_utc": now_utc.isoformat(),
                "sha256_checksum": calculated_sha,
                "byte_size": total_downloaded,
                "resumed_from_bytes": resumed_from_bytes,
                "signature_kind": sig_meta["signature_kind"],
                "signature_verified": True,
            }
            sidecar = target_file_path.parent / f".{target_file_path.name}.retrieval.json"
            tmp_sc = target_file_path.parent / f".{target_file_path.name}.retrieval.tmp"
            tmp_sc.write_text(json.dumps(dl_meta, indent=2), encoding="utf-8")
            os.replace(tmp_sc, sidecar)
        except Exception as exc:
            err_detail = self._format_exc_detail(
                exc,
                http_status=http_status or None,
                bytes_downloaded=progress_bytes,
                declared_size=declared_size,
                timeout_seconds=timeout_seconds,
            )
            dataset.status = DatasetLifecycleStatus.FAILED_DOWNLOAD
            dataset.acquisition_state = AcquisitionState.FAILED
            dataset.failure_reason = err_detail
            dataset.verification.download_verification = VerificationState.FAILED
            if http_status and http_status not in {200, 206}:
                dataset.verification.archive_availability = VerificationState.FAILED
            self._record_acquisition_ledger(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "dataset_id": dataset.id,
                    "product_id": dataset.product_id,
                    "source_url": source_url,
                    "http_status": http_status,
                    "bytes_downloaded": progress_bytes,
                    "declared_size": declared_size,
                    "timeout_seconds": timeout_seconds,
                    "outcome": "FAILED",
                    "error": err_detail,
                    "stage_after": AcquisitionState.FAILED.value,
                }
            )
            raise
        finally:
            # Retain temp_path ONLY when interrupted mid-stream on network timeout/transport error and allow_resume=True;
            # remove temp_path if final state succeeded or corruption/validation error occurred.
            if temp_path.exists() and (dataset.acquisition_state == AcquisitionState.FAILED):
                err_l = (dataset.failure_reason or "").lower()
                if any(tok in err_l for tok in ("checksum mismatch", "signature", "html", "exceeds max_bytes", "malformed")):
                    temp_path.unlink(missing_ok=True)
                    resume_meta_path.unlink(missing_ok=True)

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
        dataset.acquisition_state = AcquisitionState.INTEGRITY_VALIDATED
        dataset.failure_reason = None
        dataset.local_file_path = manifest.storage_path
        dataset.file_size_bytes = total_downloaded
        dataset.sha256_checksum = calculated_sha
        dataset.verification.archive_availability = VerificationState.VERIFIED
        dataset.verification.download_verification = VerificationState.VERIFIED
        dataset.verification.last_checked_utc = datetime.now(timezone.utc)
        dataset.verification.evidence_notes.append(
            f"Downloaded {total_downloaded} bytes; SHA-256={calculated_sha[:16]}... ({sig_meta['signature_kind']})"
        )
        dataset.processing_history.append(
            f"Downloaded {total_downloaded} bytes at {manifest.download_timestamp_utc.isoformat()} (SHA-256: {calculated_sha[:12]}...)"
        )
        self._record_acquisition_ledger(
            {
                "timestamp_utc": manifest.download_timestamp_utc.isoformat(),
                "dataset_id": dataset.id,
                "product_id": dataset.product_id,
                "source_url": source_url,
                "http_status": http_status,
                "outcome": "ACQUIRED",
                "byte_size": total_downloaded,
                "sha256_checksum": calculated_sha,
                "signature_kind": sig_meta["signature_kind"],
                "stage_after": AcquisitionState.INTEGRITY_VALIDATED.value,
            }
        )
        return manifest

    async def download_imagery_file(
        self, *, product_id: str, source_url: str, filename: str,
        expected_md5: Optional[str] = None, max_bytes: int = 2_000_000_000,
        timeout_seconds: float = 180.0,
    ) -> Dict[str, Any]:
        """Serialize same-path acquisition across workers and delegate the stream."""
        target = self.raw_data_dir / "imagery" / Path(filename).name
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = target.with_suffix(target.suffix + ".acquiring")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError(f"An acquisition is already in progress for {target.name}") from exc
        os.close(fd)
        try:
            for attempt in range(3):
                try:
                    return await self._download_imagery_file_locked(
                        product_id=product_id, source_url=source_url, filename=filename,
                        expected_md5=expected_md5, max_bytes=max_bytes, timeout_seconds=timeout_seconds,
                    )
                except Exception as exc:
                    transient_status = isinstance(exc, RuntimeError) and any(
                        token in str(exc) for token in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")
                    )
                    if attempt == 2 or not (transient_status or isinstance(exc, (httpx.TimeoutException, httpx.TransportError))):
                        raise
                    await asyncio.sleep(0.25 * (2 ** attempt))
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    async def _download_imagery_file_locked(
        self, *, product_id: str, source_url: str, filename: str,
        expected_md5: Optional[str], max_bytes: int, timeout_seconds: float,
    ) -> Dict[str, Any]:
        """Stream an explicitly requested immutable image product and verify it."""
        from urllib.parse import urlparse
        allowed_hosts = {"pds-imaging.jpl.nasa.gov", "planetarydata.jpl.nasa.gov", "hirise.lpl.arizona.edu"}
        if urlparse(source_url).hostname not in allowed_hosts or urlparse(source_url).scheme != "https":
            raise ValueError("Imagery downloads are restricted to the verified PDS Imaging HTTPS host")
        clean_name = Path(filename).name
        if clean_name in {"", ".", ".."}:
            raise ValueError("Archive did not provide a safe original filename")
        target = self.raw_data_dir / "imagery" / clean_name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing_hash = self._compute_file_sha256(target)
            sidecar = target.parent / f".{target.name}.retrieval.json"
            if sidecar.exists():
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                if meta.get("source_url") == source_url and meta.get("sha256_checksum") == existing_hash:
                    return {**meta, "local_file_path": str(target), "reused_verified_file": True}
            raise FileExistsError(f"Refusing to overwrite an existing imagery product: {target}")
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{clean_name}.", suffix=".partial", dir=target.parent)
        os.close(tmp_fd)
        temp_path = Path(tmp_name)
        sha = hashlib.sha256(); md5 = hashlib.md5(); total = 0; response_code = 0; content_type = None
        declared_size = None
        try:
            async with create_async_http_client(timeout_seconds=timeout_seconds) as client:
                async with client.stream("GET", source_url) as response:
                    if urlparse(str(response.url)).hostname not in allowed_hosts:
                        raise ValueError("PDS IMG redirected outside the verified NASA data hosts")
                    response_code = response.status_code; content_type = response.headers.get("content-type")
                    if response.status_code != 200:
                        raise RuntimeError(f"PDS imagery download returned HTTP {response.status_code}")
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > max_bytes:
                        raise ValueError(f"Image product exceeds the {max_bytes} byte acquisition limit")
                    declared_size = int(declared) if declared else None
                    with temp_path.open("wb") as stream:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            total += len(chunk)
                            if total > max_bytes:
                                raise ValueError(f"Image product exceeds the {max_bytes} byte acquisition limit")
                            sha.update(chunk); md5.update(chunk); stream.write(chunk)
            if total == 0:
                raise ValueError("Archive returned an empty image product")
            if declared_size is not None and declared_size != total:
                raise ValueError(f"Truncated or inconsistent product: received {total} bytes, archive declared {declared_size}")
            with temp_path.open("rb") as stream:
                raw_prefix = stream.read(4096)
            prefix = raw_prefix[:512].lstrip().lower()
            if (content_type or "").lower().startswith("text/html") or prefix.startswith((b"<html", b"<!doctype html")):
                raise ValueError("Archive returned an HTML error page instead of an image")
            if Path(clean_name).suffix.lower() in {".jp2", ".j2k"}:
                if not (raw_prefix.startswith(b"\x00\x00\x00\x0cjP  \r\n\x87\n") or raw_prefix.startswith(b"\xff\x4f\xff\x51")):
                    raise ValueError("Downloaded JPEG 2000 product lacks a valid JP2 or codestream signature")
            sig_meta = validate_artifact_signature(raw_prefix, target, content_type)
            actual_md5 = md5.hexdigest()
            if expected_md5 and actual_md5.lower() != expected_md5.lower():
                raise ValueError(f"Archive MD5 mismatch: calculated {actual_md5}, expected {expected_md5}")
            os.replace(temp_path, target)
            metadata = {"file_name": clean_name, "source_url": source_url, "http_status": response_code,
                        "content_type": content_type, "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "sha256_checksum": sha.hexdigest(), "md5_checksum": actual_md5, "byte_size": total,
                        "archive_md5_verified": bool(expected_md5), "product_id": product_id,
                        "local_file_path": str(target), "reused_verified_file": False,
                        "signature_kind": sig_meta["signature_kind"], "signature_verified": True}
            sidecar = target.parent / f".{target.name}.retrieval.json"
            tmp_sidecar = sidecar.with_suffix(".tmp"); tmp_sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8"); os.replace(tmp_sidecar, sidecar)
            self._record_acquisition_ledger({
                "timestamp_utc": metadata["retrieval_timestamp_utc"],
                "dataset_id": None,
                "product_id": product_id,
                "source_url": source_url,
                "http_status": response_code,
                "outcome": "ACQUIRED",
                "byte_size": total,
                "sha256_checksum": metadata["sha256_checksum"],
                "signature_kind": sig_meta["signature_kind"],
                "stage_after": "downloaded_not_yet_validated",
            })
            return metadata
        except Exception as exc:
            self._record_acquisition_ledger({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "dataset_id": None,
                "product_id": product_id,
                "source_url": source_url,
                "http_status": response_code,
                "outcome": "FAILED",
                "error": str(exc),
                "stage_after": "failed_download",
            })
            raise
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _apply_pds_label_verification(dataset: Dataset, label_path: Path) -> None:
        sfx = label_path.suffix.lower()
        if sfx == ".lbl":
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
        elif sfx == ".xml":
            meta = extract_pds4_metadata(label_path)
            if meta.get("units"):
                dataset.units = str(meta["units"])
                dataset.verification.field_verification["units"] = VerificationState.VERIFIED
            if meta.get("processing_level"):
                dataset.processing_level = str(meta["processing_level"])
            if meta.get("logical_identifier") and not dataset.doi_or_pds_id:
                dataset.doi_or_pds_id = str(meta["logical_identifier"])
            dataset.verification.metadata_verification = VerificationState.VERIFIED
            dataset.verification.evidence_notes.append(f"Verified metadata from PDS4 XML label {label_path.name}")

    @staticmethod
    def _apply_pds3_label_verification(dataset: Dataset, label_path: Path) -> None:
        AcquisitionService._apply_pds_label_verification(dataset, label_path)

    @staticmethod
    def _compute_file_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
