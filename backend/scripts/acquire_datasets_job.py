#!/usr/bin/env python3
"""
MARSCOPE Cloud Run Job — Sequential NASA Dataset Acquisition & GCS Persistence

Runs as a one-time Cloud Run Job (never inside web server startup) with bounded-memory
chunked streaming, incremental SHA-256 verification, atomic file replacement, and optional
Google Cloud Storage upload.
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

DEFAULT_JOB_DATASETS = [
    "mola_megt00n090hb",
    "mola_megt90n000cb",
    "hirise_dteec_009149_1750",
]


def run_acquisition_job(
    *,
    datasets_dir: Path,
    dataset_ids: List[str],
    upload_to_gcs: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    seed_catalog_metadata_if_empty(datasets_dir)
    catalog_service = DatasetCatalogService(datasets_dir / "catalog")
    acquisition_service = AcquisitionService(datasets_dir / "raw", datasets_dir / "manifests")

    acq_res = asyncio.run(
        acquire_bootstrap_datasets(
            catalog_service=catalog_service,
            acquisition_service=acquisition_service,
            dataset_ids=dataset_ids,
            overwrite=overwrite,
        )
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
            raw_path = next((p for p in raw_candidates if p.exists()), None)
            if raw_path is None:
                continue
            gcs_uploads.append(
                gcs_store.upload_file_streaming(
                    raw_path,
                    f"raw/{raw_path.name}",
                    expected_sha256=entry.get("expected_sha256"),
                )
            )
            lbl_rel = entry.get("expected_label_path")
            if lbl_rel and lbl_rel != entry.get("expected_raw_path"):
                lbl_path = datasets_dir / str(lbl_rel)
                if lbl_path.exists():
                    gcs_uploads.append(
                        gcs_store.upload_file_streaming(lbl_path, f"raw/{lbl_path.name}")
                    )
            cat_path = datasets_dir / "catalog" / f"{ds_id}.json"
            if cat_path.exists():
                gcs_uploads.append(
                    gcs_store.upload_file_streaming(cat_path, f"catalog/{cat_path.name}")
                )
            man_path = datasets_dir / "manifests" / f"{ds_id}.manifest.json"
            if man_path.exists():
                gcs_uploads.append(
                    gcs_store.upload_file_streaming(man_path, f"manifests/{man_path.name}")
                )

    report = verify_local_datasets(datasets_dir=datasets_dir, verify_checksums=True, strict=True)
    return {
        "acquisition": acq_res,
        "gcs_uploads": gcs_uploads,
        "verification": report.model_dump(),
        "preflight_passed": report.preflight_passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MARSCOPE Cloud Run Job for NASA dataset acquisition")
    parser.add_argument(
        "--dataset",
        action="append",
        default=None,
        help="Specific dataset_id(s) to acquire sequentially (defaults to mandatory MOLA + HiRISE DEMs)",
    )
    parser.add_argument("--include-ortho", action="store_true", help="Also acquire mandatory HiRISE ortho JP2")
    parser.add_argument("--no-gcs", action="store_true", help="Skip GCS upload even if MARSCOPE_GCS_BUCKET is set")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing local files")
    args = parser.parse_args()

    ds_dir = Path(os.environ.get("MARSCOPE_DATASETS_DIR", "/tmp/marscope_datasets")).resolve()
    target_ids = list(args.dataset or DEFAULT_JOB_DATASETS)
    if args.include_ortho and "hirise_psp_009149_1750_ortho" not in target_ids:
        target_ids.append("hirise_psp_009149_1750_ortho")

    result = run_acquisition_job(
        datasets_dir=ds_dir,
        dataset_ids=target_ids,
        upload_to_gcs=not args.no_gcs,
        overwrite=args.overwrite,
    )
    print(json.dumps(result, indent=2))

    if result["acquisition"]["failed"]:
        return 1
    if not result["preflight_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
