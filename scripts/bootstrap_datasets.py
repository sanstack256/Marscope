#!/usr/bin/env python3
"""
MARSCOPE Reproducible Dataset Bootstrap & Verification CLI (Prompt 22).

Supports clean-environment preflight verification (Mode A, no network required),
authoritative NASA archive acquisition (Mode B, explicit operator command),
DEM derivative processing (--process), composition index rebuild (--rebuild-index),
and 12-property readiness auditing.

Usage:
  python3 scripts/bootstrap_datasets.py --verify [--strict] [--json]
  python3 scripts/bootstrap_datasets.py --acquire [--mandatory-only] [--dataset-id ID] [--overwrite]
  python3 scripts/bootstrap_datasets.py --process [--dataset-id ID]
  python3 scripts/bootstrap_datasets.py --rebuild-index
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.acquisition import AcquisitionService  # noqa: E402
from app.ingestion.bootstrap import (  # noqa: E402
    acquire_bootstrap_datasets,
    default_datasets_dir,
    seed_catalog_metadata_if_empty,
    verify_local_datasets,
)
from app.ingestion.catalog import DatasetCatalogService  # noqa: E402
from app.science.composition.index import CompositionSpatialIndex  # noqa: E402
from app.terrain.processor import DEMProcessingService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MARSCOPE reproducible dataset verification, acquisition, processing, and index bootstrapper."
    )
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=default_datasets_dir(),
        help="Path to MARSCOPE datasets directory (default: MARSCOPE_DATASETS_DIR or <repo>/datasets).",
    )
    parser.add_argument("--verify", action="store_true", help="Mode A: verify local raw/processed artifacts against bootstrap_manifest.json without network.")
    parser.add_argument("--acquire", action="store_true", help="Mode B: acquire missing authoritative products from NASA/PDS/UArizona URLs.")
    parser.add_argument("--process", action="store_true", help="Process downloaded local DEM products into calibrated GeoTIFF derivatives.")
    parser.add_argument("--rebuild-index", action="store_true", help="Rebuild versioned spatial composition index from verified local raw/processed files.")
    parser.add_argument("--dataset-id", action="append", default=None, help="Filter specific dataset_id(s) (repeatable).")
    parser.add_argument("--mandatory-only", action="store_true", help="Restrict --acquire/--process to mandatory Gale Crater workflow products.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing local files during --acquire.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any mandatory dataset is missing or any checksum/signature fails.")
    parser.add_argument("--no-checksum", action="store_true", help="Skip SHA-256 recomputation during --verify (faster inspection only).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    ds_dir: Path = args.datasets_dir.resolve()
    seed_catalog_metadata_if_empty(ds_dir)
    raw_dir = ds_dir / "raw"
    processed_dir = ds_dir / "processed"
    catalog_dir = ds_dir / "catalog"
    manifests_dir = ds_dir / "manifests"
    index_dir = ds_dir / "index"

    for d in (raw_dir, processed_dir, catalog_dir, manifests_dir, index_dir):
        d.mkdir(parents=True, exist_ok=True)

    run_verify = args.verify or (not args.acquire and not args.process and not args.rebuild_index)
    catalog_svc = DatasetCatalogService(catalog_dir, raw_data_dir=raw_dir)
    acq_svc = AcquisitionService(raw_dir, manifests_dir)
    comp_idx = CompositionSpatialIndex(index_dir / "composition_index.sqlite")

    output_summary: dict = {"datasets_dir": str(ds_dir)}
    exit_code = 0

    if args.acquire:
        acq_res = asyncio.run(
            acquire_bootstrap_datasets(
                catalog_service=catalog_svc,
                acquisition_service=acq_svc,
                dataset_ids=args.dataset_id,
                mandatory_only=args.mandatory_only,
                overwrite=args.overwrite,
            )
        )
        output_summary["acquire"] = acq_res
        if acq_res.get("failed"):
            exit_code = 2

    if args.process:
        proc_results = []
        target_ids = set(args.dataset_id or [])
        manifest_path = ds_dir / "bootstrap_manifest.json"
        mandatory_ids = set()
        if manifest_path.exists():
            mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in mdata.get("products") or []:
                if item.get("mandatory_for_gale_workflow"):
                    mandatory_ids.add(str(item["dataset_id"]))

        for ds in catalog_svc.list_datasets():
            if target_ids and ds.id not in target_ids:
                continue
            if args.mandatory_only and ds.id not in mandatory_ids:
                continue
            if "DEM" not in ds.product_type.upper() and "ELEVATION" not in ds.product_type.upper():
                continue
            if not ds.local_file_path:
                proc_results.append({"dataset_id": ds.id, "status": "skipped_missing_raw"})
                continue
            try:
                man = DEMProcessingService.process_dem_dataset(
                    dataset=ds,
                    raw_dir=raw_dir,
                    processed_dir=processed_dir,
                    study_bounds=ds.coverage,
                )
                catalog_svc.register_dataset(ds)
                proc_results.append({"dataset_id": ds.id, "status": "processed", "output": man.get("processed_file")})
            except Exception as exc:
                proc_results.append({"dataset_id": ds.id, "status": "failed", "error": str(exc)})
                exit_code = 2
        output_summary["process"] = proc_results

    if args.rebuild_index:
        idx_res = comp_idx.rebuild_from_raw_directory(raw_dir=raw_dir, processed_dir=processed_dir)
        output_summary["rebuild_index"] = (
            idx_res.model_dump(mode="json") if hasattr(idx_res, "model_dump") else idx_res
        )

    if run_verify:
        rep = verify_local_datasets(
            datasets_dir=ds_dir,
            verify_checksums=not args.no_checksum,
            strict=args.strict,
        )
        audit = catalog_svc.audit_dataset_readiness(
            composition_index=comp_idx,
            verify_checksums=not args.no_checksum,
        )
        output_summary["verification"] = rep.model_dump(mode="json")
        output_summary["readiness_audit"] = {
            "total_catalog_datasets": audit["total_catalog_datasets"],
            "mandatory_gale_ready": audit["mandatory_gale_ready"],
            "lifecycle_state_counts": audit["lifecycle_state_counts"],
            "index_available": audit["index_available"],
            "active_index_generation": audit["active_index_generation"],
        }
        if args.strict and not rep.preflight_passed:
            exit_code = 2
        elif rep.checksum_mismatch_count > 0:
            exit_code = 2

    if args.json:
        print(json.dumps(output_summary, indent=2))
    else:
        if "acquire" in output_summary:
            acq = output_summary["acquire"]
            print(
                f"[ACQUIRE] downloaded={len(acq['acquired'])} skipped={len(acq['skipped_already_present'])} failed={len(acq['failed'])}"
            )
        if "process" in output_summary:
            print(f"[PROCESS] evaluated={len(output_summary['process'])} DEM datasets")
        if "rebuild_index" in output_summary:
            print(f"[INDEX] rebuilt composition index: {output_summary['rebuild_index'].get('active_generation_id', 'ok')}")
        if "verification" in output_summary:
            ver = output_summary["verification"]
            print(
                f"[VERIFY] {ver['summary_note']} preflight_passed={ver['preflight_passed']}"
            )
            for p in ver["products"]:
                tag = "MANDATORY" if p["mandatory_for_gale_workflow"] else "OPTIONAL"
                print(f"  - {p['dataset_id']} [{tag}] -> {p['state']}")
                if p["state"] != "VERIFIED_LOCAL":
                    print(f"      remediation: run scripts/bootstrap_datasets.py --acquire --dataset-id {p['dataset_id']}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
