#!/usr/bin/env python3
"""
MARSCOPE Dataset Bootstrap & Preflight Verification CLI (Prompt 19 Part 2)

Usage:
  Mode A — Verify installed local NASA products:
    python3 backend/scripts/bootstrap_datasets.py --verify [--strict] [--no-checksum]
  Mode B — Acquire missing NASA products from authoritative PDS / JPL endpoints:
    python3 backend/scripts/bootstrap_datasets.py --acquire [--mandatory-only] [--dataset hirise_dteec_009149_1750]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.bootstrap import acquire_bootstrap_datasets, verify_local_datasets
from app.services.container import acquisition_service, catalog_service, DATASETS_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description="MARSCOPE NASA dataset bootstrap and integrity verifier")
    parser.add_argument("--verify", action="store_true", help="Mode A: verify locally installed NASA files against manifest")
    parser.add_argument("--strict", action="store_true", help="Fail with exit code 1 if any mandatory dataset is missing/invalid")
    parser.add_argument("--no-checksum", action="store_true", help="Skip SHA-256 hashing during fast file presence checks")
    parser.add_argument("--acquire", action="store_true", help="Mode B: download missing NASA datasets from authoritative URLs")
    parser.add_argument("--mandatory-only", action="store_true", help="Restrict Mode B acquisition to mandatory Gale products")
    parser.add_argument("--dataset", action="append", default=None, help="Specific dataset_id(s) to acquire")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    args = parser.parse_args()

    if args.acquire:
        res = asyncio.run(
            acquire_bootstrap_datasets(
                catalog_service=catalog_service,
                acquisition_service=acquisition_service,
                dataset_ids=args.dataset,
                mandatory_only=args.mandatory_only,
            )
        )
        print(json.dumps(res, indent=2))
        if res["failed"]:
            return 1
        if args.strict and not res["post_verification"]["preflight_passed"]:
            return 1
        return 0

    report = verify_local_datasets(
        datasets_dir=DATASETS_DIR,
        verify_checksums=not args.no_checksum,
        strict=args.strict,
    )
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"=== MARSCOPE Dataset Bootstrap Verification ({report.mode}) ===")
        print(report.summary_note)
        for p in report.products:
            flag = "OK" if p.state == "VERIFIED_LOCAL" else p.state
            print(f"  - [{flag}] {p.dataset_id} ({p.product_id}) -> {p.expected_raw_path}")
        print(f"Preflight passed: {report.preflight_passed}")

    return 0 if report.preflight_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
