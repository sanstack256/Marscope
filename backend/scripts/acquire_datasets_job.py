#!/usr/bin/env python3
"""
MARSCOPE Cloud Run Job — Sequential NASA Dataset Acquisition & GCS Persistence

Runs as a one-time Cloud Run Job (never inside web server startup) with bounded-memory
chunked streaming, incremental SHA-256 verification, atomic file replacement, and
Google Cloud Storage upload + verification.

Supports two preflight modes:
- targeted (default): validates only the requested dataset(s) and their companions
  (e.g. hirise_dteec_009149_1750) without requiring unrelated REMS/ChemCam/CheMin data.
- full: runs the comprehensive 12-product scientific manifest preflight.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.acquisition import AcquisitionService
from app.ingestion.bootstrap import (
    acquire_bootstrap_datasets,
    load_bootstrap_manifest,
    seed_catalog_metadata_if_empty,
    verify_local_datasets,
)
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.gcs_storage import GCSDatasetStore

TARGETED_HIRISE_DATASETS = ["hirise_dteec_009149_1750"]
DEFAULT_JOB_DATASETS = [
    "mola_megt00n090hb",
    "mola_megt90n000cb",
    "hirise_dteec_009149_1750",
]


def _log_stage(stage: str, message: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    print(f"[MARSCOPE][{stage}] {message}", file=stream, flush=True)


def run_acquisition_job(
    *,
    datasets_dir: Path,
    dataset_ids: List[str],
    upload_to_gcs: bool = True,
    overwrite: bool = False,
    mode: str = "targeted",
) -> Dict[str, Any]:
    if mode not in {"targeted", "full"}:
        raise ValueError(f"Unsupported acquisition mode '{mode}'; expected 'targeted' or 'full'.")

    _log_stage(
        "PREFLIGHT",
        f"Seeding metadata and preparing mode={mode} datasets={','.join(dataset_ids)} datasets_dir={datasets_dir}",
    )
    seed_catalog_metadata_if_empty(datasets_dir)
    catalog_service = DatasetCatalogService(datasets_dir / "catalog")
    acquisition_service = AcquisitionService(datasets_dir / "raw", datasets_dir / "manifests")

    _log_stage("DOWNLOAD", f"Starting sequential bounded-memory acquisition for {','.join(dataset_ids)}")
    acq_res = asyncio.run(
        acquire_bootstrap_datasets(
            catalog_service=catalog_service,
            acquisition_service=acquisition_service,
            dataset_ids=dataset_ids,
            overwrite=overwrite,
        )
    )
    _log_stage(
        "DOWNLOAD",
        f"acquired={len(acq_res.get('acquired', []))} "
        f"skipped={len(acq_res.get('skipped_already_present', []))} "
        f"failed={len(acq_res.get('failed', []))}",
        err=bool(acq_res.get("failed")),
    )

    verify_ids = dataset_ids if mode == "targeted" else None
    report = verify_local_datasets(
        datasets_dir=datasets_dir,
        verify_checksums=True,
        strict=True,
        dataset_ids=verify_ids,
    )
    for prod in report.products:
        _log_stage(
            "CHECKSUM",
            f"dataset_id={prod.dataset_id} state={prod.state} "
            f"size_bytes={prod.actual_size_bytes}/{prod.expected_size_bytes} "
            f"checksum_verified={prod.checksum_verified} sha256={prod.actual_sha256}",
            err=prod.state not in {"VERIFIED_LOCAL"},
        )
    _log_stage(
        "PREFLIGHT",
        f"mode={mode} verified={report.verified_count}/{report.total_manifest_products} "
        f"missing_mandatory={report.missing_mandatory_count} "
        f"mismatches={report.checksum_mismatch_count} preflight_passed={report.preflight_passed}",
        err=not report.preflight_passed,
    )

    gcs_uploads: List[Dict[str, Any]] = []
    gcs_store = GCSDatasetStore.from_env() if upload_to_gcs else None
    if gcs_store is not None:
        manifest = load_bootstrap_manifest(datasets_dir / "bootstrap_manifest.json")
        by_id = {p["dataset_id"]: p for p in manifest.get("products", [])}
        for ds_id in dataset_ids:
            entry = by_id.get(ds_id)
            if not entry:
                continue
            ds = catalog_service.get_dataset(ds_id)
            raw_candidates = []
            if ds and ds.local_file_path:
                raw_candidates.append(datasets_dir / ds.local_file_path)
            raw_candidates.append(datasets_dir / str(entry["expected_raw_path"]))
            # Case-insensitive fallback inside raw/
            raw_dir = datasets_dir / "raw"
            target_name_lower = Path(str(entry["expected_raw_path"])).name.lower()
            if raw_dir.exists():
                for candidate in raw_dir.iterdir():
                    if candidate.is_file() and candidate.name.lower() == target_name_lower:
                        raw_candidates.append(candidate)
            raw_path = next((p for p in raw_candidates if p.exists()), None)
            if raw_path is None:
                _log_stage("UPLOAD", f"Skipping GCS upload for missing raw file dataset_id={ds_id}", err=True)
                continue

            _log_stage(
                "UPLOAD",
                f"Uploading {raw_path.name} to gs://{gcs_store.bucket_name}/{gcs_store.prefix}/raw/{raw_path.name}",
            )
            up_meta = gcs_store.upload_file_streaming(
                raw_path,
                f"raw/{raw_path.name}",
                expected_sha256=entry.get("expected_sha256"),
            )
            gcs_uploads.append(up_meta)
            _log_stage(
                "GCS_VERIFY",
                f"Verified gs://{up_meta['bucket']}/{up_meta['object_name']} "
                f"size_bytes={up_meta['size_bytes']} sha256={up_meta['sha256']} verified={up_meta.get('verified')}",
            )

            lbl_rel = entry.get("expected_label_path")
            if lbl_rel and lbl_rel != entry.get("expected_raw_path"):
                lbl_path = datasets_dir / str(lbl_rel)
                if lbl_path.exists():
                    lbl_meta = gcs_store.upload_file_streaming(lbl_path, f"raw/{lbl_path.name}")
                    gcs_uploads.append(lbl_meta)
                    _log_stage(
                        "GCS_VERIFY",
                        f"Verified companion gs://{lbl_meta['bucket']}/{lbl_meta['object_name']} sha256={lbl_meta['sha256']}",
                    )

            cat_path = datasets_dir / "catalog" / f"{ds_id}.json"
            if cat_path.exists():
                cat_meta = gcs_store.upload_file_streaming(cat_path, f"catalog/{cat_path.name}")
                gcs_uploads.append(cat_meta)
            man_path = datasets_dir / "manifests" / f"{ds_id}.manifest.json"
            if man_path.exists():
                man_meta = gcs_store.upload_file_streaming(man_path, f"manifests/{man_path.name}")
                gcs_uploads.append(man_meta)

    return {
        "mode": mode,
        "target_datasets": dataset_ids,
        "acquisition": acq_res,
        "gcs_uploads": gcs_uploads,
        "verification": report.model_dump(),
        "preflight_passed": report.preflight_passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MARSCOPE Cloud Run Job for NASA dataset acquisition")
    parser.add_argument(
        "--mode",
        choices=["targeted", "full"],
        default="targeted",
        help="Preflight mode: 'targeted' validates only requested datasets; 'full' validates all 12 manifest products",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        default=None,
        help="Specific dataset_id(s) to acquire sequentially (defaults to hirise_dteec_009149_1750 in targeted mode)",
    )
    parser.add_argument("--include-mola", action="store_true", help="Also include MOLA DEMs in targeted mode")
    parser.add_argument("--include-ortho", action="store_true", help="Also acquire HiRISE ortho JP2")
    parser.add_argument("--no-gcs", action="store_true", help="Skip GCS upload even if MARSCOPE_GCS_BUCKET is set")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing local files")
    args = parser.parse_args()

    ds_dir = Path(os.environ.get("MARSCOPE_DATASETS_DIR", "/tmp/marscope_datasets")).resolve()
    if args.dataset:
        target_ids = list(args.dataset)
    elif args.mode == "full":
        target_ids = list(DEFAULT_JOB_DATASETS)
    else:
        target_ids = list(DEFAULT_JOB_DATASETS if args.include_mola else TARGETED_HIRISE_DATASETS)

    if args.include_ortho and "hirise_psp_009149_1750_ortho" not in target_ids:
        target_ids.append("hirise_psp_009149_1750_ortho")

    _log_stage(
        "COMPLETE",
        f"Job starting mode={args.mode} gcs_enabled={not args.no_gcs} datasets={','.join(target_ids)}",
    )
    try:
        result = run_acquisition_job(
            datasets_dir=ds_dir,
            dataset_ids=target_ids,
            upload_to_gcs=not args.no_gcs,
            overwrite=args.overwrite,
            mode=args.mode,
        )
    except Exception as exc:
        exc_msg = str(exc).strip() or repr(exc)
        _log_stage(
            "COMPLETE",
            f"Acquisition job failed: exception_type={type(exc).__name__} "
            f"exception_message={exc_msg} exit_status=1",
            err=True,
        )
        return 1

    print(json.dumps(result, indent=2), flush=True)

    failed_items = result["acquisition"]["failed"]
    if failed_items:
        _log_stage(
            "COMPLETE",
            f"Acquisition job completed with failures: count={len(failed_items)} "
            f"details={json.dumps(failed_items)} exit_status=1",
            err=True,
        )
        return 1
    if not result["preflight_passed"]:
        _log_stage(
            "COMPLETE",
            f"Preflight verification failed (mode={args.mode}): exit_status=1",
            err=True,
        )
        return 1
    _log_stage(
        "COMPLETE",
        f"Acquisition job succeeded: mode={args.mode} datasets={','.join(target_ids)} exit_status=0",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
