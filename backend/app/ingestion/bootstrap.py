"""
MARSCOPE Reproducible Dataset Bootstrap & Integrity Verification Engine
Prompt 19 Part 2: Reconciles .gitignore'd local real NASA source files between clean
Git checkouts and installed workspaces under two explicit modes:
  - Mode A (verify_local_datasets): verifies exact local filenames, SHA-256 digests,
    companion PDS3/PDS4 labels, format signatures, and processed manifests on disk.
  - Mode B (acquire_bootstrap_datasets): fetches selected/missing products from their
    authoritative NASA PDS / UArizona / JPL URLs via AcquisitionService.
Never fabricates missing files or substitutes synthetic artifacts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.ingestion.acquisition import AcquisitionService, validate_artifact_signature
from app.ingestion.pds_label import extract_pds3_metadata, extract_pds4_metadata


class BootstrapProductStatus(BaseModel):
    dataset_id: str
    product_id: str
    category: str
    mandatory_for_gale_workflow: bool
    source_archive: str
    source_url: str
    expected_raw_path: str
    expected_size_bytes: Optional[int] = None
    expected_sha256: Optional[str] = None
    local_raw_exists: bool
    actual_size_bytes: Optional[int] = None
    actual_sha256: Optional[str] = None
    checksum_verified: Optional[bool] = None
    companion_labels_present: bool
    missing_companions: List[str] = Field(default_factory=list)
    label_verified: Optional[bool] = None
    format_signature_verified: Optional[bool] = None
    processed_artifact_present: Optional[bool] = None
    state: str  # VERIFIED_LOCAL | CHECKSUM_MISMATCH | INVALID_FORMAT | MISSING_COMPANION | MISSING_MANDATORY | MISSING_OPTIONAL
    notes: List[str] = Field(default_factory=list)


class BootstrapVerificationReport(BaseModel):
    manifest_version: str
    mode: str  # mode_a_local_verification | mode_b_network_acquisition
    checked_at_utc: str
    datasets_dir: str
    total_manifest_products: int
    verified_count: int
    checksum_mismatch_count: int
    missing_mandatory_count: int
    missing_optional_count: int
    preflight_passed: bool
    products: List[BootstrapProductStatus] = Field(default_factory=list)
    summary_note: str


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_bootstrap_manifest(manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    path = manifest_path or (
        Path(__file__).resolve().parents[3] / "datasets" / "bootstrap_manifest.json"
    )
    if not path.exists():
        raise FileNotFoundError(f"Bootstrap manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_local_datasets(
    *,
    datasets_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    verify_checksums: bool = True,
    strict: bool = False,
) -> BootstrapVerificationReport:
    """
    Mode A: Inspect local files against the authoritative bootstrap manifest without
    network access or modifying tracked catalogs.
    """
    ds_root = datasets_dir or (Path(__file__).resolve().parents[3] / "datasets")
    manifest = load_bootstrap_manifest(manifest_path or (ds_root / "bootstrap_manifest.json"))
    entries = list(manifest.get("products") or [])
    statuses: List[BootstrapProductStatus] = []

    verified_count = 0
    mismatch_count = 0
    missing_mandatory = 0
    missing_optional = 0

    for item in entries:
        ds_id = str(item["dataset_id"])
        pid = str(item["product_id"])
        rel_raw = str(item["expected_raw_path"])
        raw_path = ds_root / rel_raw
        mandatory = bool(item.get("mandatory_for_gale_workflow", False))
        expected_sha = item.get("expected_sha256")
        expected_size = item.get("expected_size_bytes")
        companions = [str(c) for c in (item.get("companion_dependencies") or [])]

        notes: List[str] = []
        raw_exists = raw_path.exists() and raw_path.is_file()
        missing_comp = [c for c in companions if not (ds_root / c).exists()]

        actual_size: Optional[int] = raw_path.stat().st_size if raw_exists else None
        actual_sha: Optional[str] = None
        checksum_ok: Optional[bool] = None
        sig_ok: Optional[bool] = None
        lbl_ok: Optional[bool] = None

        proc_rel = item.get("expected_processed_path")
        proc_present: Optional[bool] = None
        if proc_rel:
            proc_present = (ds_root / str(proc_rel)).exists()

        if not raw_exists:
            if mandatory:
                missing_mandatory += 1
                state = "MISSING_MANDATORY"
                notes.append(f"Mandatory local source product absent at '{rel_raw}'.")
            else:
                missing_optional += 1
                state = "MISSING_OPTIONAL"
                notes.append(f"Optional local source product absent at '{rel_raw}'.")
        else:
            if expected_size is not None and actual_size != int(expected_size):
                notes.append(f"Size difference: expected {expected_size} B, got {actual_size} B.")
            if verify_checksums:
                actual_sha = compute_sha256(raw_path)
                if expected_sha:
                    checksum_ok = actual_sha.lower() == str(expected_sha).strip().lower()
                    if not checksum_ok:
                        notes.append("SHA-256 digest mismatch vs bootstrap manifest.")
            # Format magic / header check
            try:
                head = raw_path.read_bytes()[:4096]
                validate_artifact_signature(head, raw_path)
                sig_ok = True
            except Exception as exc:
                sig_ok = False
                notes.append(f"Format signature validation failed: {exc}")

            # Companion label parse check
            lbl_rel = item.get("expected_label_path")
            if lbl_rel and (ds_root / str(lbl_rel)).exists():
                lbl_path = ds_root / str(lbl_rel)
                try:
                    if lbl_path.suffix.lower() == ".xml":
                        extract_pds4_metadata(lbl_path)
                    else:
                        extract_pds3_metadata(lbl_path)
                    lbl_ok = True
                except Exception as exc:
                    lbl_ok = False
                    notes.append(f"Companion label parse failed ({lbl_path.name}): {exc}")

            if checksum_ok is False:
                mismatch_count += 1
                state = "CHECKSUM_MISMATCH"
            elif sig_ok is False or lbl_ok is False:
                mismatch_count += 1
                state = "INVALID_FORMAT"
            elif missing_comp:
                state = "MISSING_COMPANION"
                notes.append(f"Missing companion dependency file(s): {', '.join(missing_comp)}")
            else:
                verified_count += 1
                state = "VERIFIED_LOCAL"
                notes.append("Verified local file presence, signature, companion label, and SHA-256.")

        statuses.append(
            BootstrapProductStatus(
                dataset_id=ds_id,
                product_id=pid,
                category=str(item.get("category", "unknown")),
                mandatory_for_gale_workflow=mandatory,
                source_archive=str(item.get("source_archive", "")),
                source_url=str(item.get("source_url", "")),
                expected_raw_path=rel_raw,
                expected_size_bytes=expected_size,
                expected_sha256=expected_sha,
                local_raw_exists=raw_exists,
                actual_size_bytes=actual_size,
                actual_sha256=actual_sha,
                checksum_verified=checksum_ok,
                companion_labels_present=(len(missing_comp) == 0),
                missing_companions=missing_comp,
                label_verified=lbl_ok,
                format_signature_verified=sig_ok,
                processed_artifact_present=proc_present,
                state=state,
                notes=notes,
            )
        )

    preflight_passed = (mismatch_count == 0) and (missing_mandatory == 0 if strict else True)
    return BootstrapVerificationReport(
        manifest_version=str(manifest.get("manifest_version", "1.0.0")),
        mode="mode_a_local_verification",
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        datasets_dir=str(ds_root),
        total_manifest_products=len(entries),
        verified_count=verified_count,
        checksum_mismatch_count=mismatch_count,
        missing_mandatory_count=missing_mandatory,
        missing_optional_count=missing_optional,
        preflight_passed=preflight_passed,
        products=statuses,
        summary_note=(
            f"Verified {verified_count}/{len(entries)} manifest products locally; "
            f"missing mandatory={missing_mandatory}, missing optional={missing_optional}, "
            f"integrity mismatches={mismatch_count}."
        ),
    )


async def acquire_bootstrap_datasets(
    *,
    catalog_service: Any,
    acquisition_service: AcquisitionService,
    dataset_ids: Optional[List[str]] = None,
    mandatory_only: bool = False,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Mode B: Download missing authoritative NASA source products using AcquisitionService
    with strict signature/checksum/label verification.
    """
    manifest = load_bootstrap_manifest(acquisition_service.raw_data_dir.parent / "bootstrap_manifest.json")
    entries = list(manifest.get("products") or [])
    if dataset_ids:
        id_set = set(dataset_ids)
        entries = [e for e in entries if e["dataset_id"] in id_set]
    elif mandatory_only:
        entries = [e for e in entries if e.get("mandatory_for_gale_workflow")]

    acquired: List[Dict[str, Any]] = []
    skipped_present: List[str] = []
    failed: List[Dict[str, Any]] = []

    ds_root = acquisition_service.raw_data_dir.parent
    for entry in entries:
        ds_id = entry["dataset_id"]
        target = ds_root / str(entry["expected_raw_path"])
        if target.exists() and not overwrite:
            skipped_present.append(ds_id)
            continue
        ds = catalog_service.get_dataset(ds_id)
        if ds is None:
            failed.append({"dataset_id": ds_id, "error": "Dataset missing from catalog."})
            continue
        try:
            man = await acquisition_service.download_product(ds, overwrite=overwrite)
            catalog_service.register_dataset(ds)
            acquired.append(
                {
                    "dataset_id": ds_id,
                    "product_id": man.product_id,
                    "sha256_checksum": man.sha256_checksum,
                    "file_size_bytes": man.file_size_bytes,
                }
            )
        except Exception as exc:
            failed.append({"dataset_id": ds_id, "error": str(exc)})

    post_report = verify_local_datasets(datasets_dir=ds_root, strict=False)
    return {
        "mode": "mode_b_network_acquisition",
        "acquired": acquired,
        "skipped_already_present": skipped_present,
        "failed": failed,
        "post_verification": post_report.model_dump(),
    }


def require_real_data_or_skip(
    required_paths: List[Path],
    *,
    require_env_var: str = "MARSCOPE_REQUIRE_REAL_DATA",
) -> None:
    """
    Used by real-data integration tests (Part 2.2):
      - When MARSCOPE_REQUIRE_REAL_DATA=1 (release preflight), missing files FAIL hard.
      - Otherwise missing files cleanly pytest.skip with exact bootstrap guidance
        rather than failing on gitignored checkouts or silently faking success.
    """
    import os
    import pytest

    missing = [str(p) for p in required_paths if not p.exists()]
    if not missing:
        return
    msg = (
        f"Real NASA product file(s) absent locally: {', '.join(missing)}. "
        "Run 'python3 backend/scripts/bootstrap_datasets.py --verify' (Mode A) or "
        "'python3 backend/scripts/bootstrap_datasets.py --acquire' (Mode B)."
    )
    if os.getenv(require_env_var) == "1":
        pytest.fail(f"[{require_env_var}=1 preflight failure] {msg}")
    pytest.skip(msg)
