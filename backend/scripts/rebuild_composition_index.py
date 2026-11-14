#!/usr/bin/env python3
"""
MARSCOPE Reproducible NASA PDS Composition Index Acquisition & Rebuild Script
Martian Surface Intelligence & Exploration System

Downloads (when `--acquire` is specified) or verifies official NASA PDS MSL composition
products and JPL traverse waypoints, validates companion labels/schemas, atomically
rebuilds datasets/index/composition_index.sqlite, writes datasets/index/reproducibility_manifest.json,
and runs independent post-build integrity verification checks.

Usage:
  PYTHONPATH=backend python3 backend/scripts/rebuild_composition_index.py
  PYTHONPATH=backend python3 backend/scripts/rebuild_composition_index.py --acquire
  PYTHONPATH=backend python3 backend/scripts/rebuild_composition_index.py --raw-dir /path/to/raw --db-path /path/to/index.sqlite
"""

import argparse
import json
from pathlib import Path
import sys
import urllib.request

# Ensure backend/ is on sys.path when run directly
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import IntegrityStatus
from app.science.composition.search import CompositionSearchService, StructuredCompositionQuery


OFFICIAL_ARTIFACTS = [
    (
        "msl_waypoints.json",
        "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
    ),
    (
        "ds01_2021je007171r.csv",
        "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.csv",
    ),
    (
        "ds01_2021je007171r.xml",
        "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/ds01_2021je007171r.xml",
    ),
    (
        "moc_0000_0089.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0000_0089.csv",
    ),
    (
        "moc_0000_0089.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0000_0089.lbl",
    ),
    (
        "moc_0090_0179.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0090_0179.csv",
    ),
    (
        "moc_0090_0179.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_0090_0179.lbl",
    ),
    (
        "moc_1294_1417.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_1294_1417.csv",
    ),
    (
        "moc_1294_1417.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/moc_1294_1417.lbl",
    ),
    (
        "chemin_min.fmt",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/label/chemin_min.fmt",
    ),
    (
        "cma_404470826min00790050104ch11503p1.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_404470826min00790050104ch11503p1.csv",
    ),
    (
        "cma_404470826min00790050104ch11503p1.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_404470826min00790050104ch11503p1.lbl",
    ),
    (
        "cma_414856883min01960060000ch12240p1.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_414856883min01960060000ch12240p1.csv",
    ),
    (
        "cma_414856883min01960060000ch12240p1.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_414856883min01960060000ch12240p1.lbl",
    ),
    (
        "cma_595174954min22270730550ch00111p1.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_595174954min22270730550ch00111p1.csv",
    ),
    (
        "cma_595174954min22270730550ch00111p1.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cma_595174954min22270730550ch00111p1.lbl",
    ),
    (
        "cmb_476051894min08850450000ch00113p1.csv",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cmb_476051894min08850450000ch00113p1.csv",
    ),
    (
        "cmb_476051894min08850450000ch00113p1.lbl",
        "https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/cmb_476051894min08850450000ch00113p1.lbl",
    ),
]


def acquire_missing_artifacts(raw_dir: Path, force: bool = False) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for fname, url in OFFICIAL_ARTIFACTS:
        dest = raw_dir / fname
        if dest.exists() and not force:
            continue
        print(f"[ACQUIRE] Downloading {url} -> {dest}")
        req = urllib.request.Request(url, headers={"User-Agent": "MARSCOPE-Reproducible-Builder/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="MARSCOPE Reproducible Composition Index Builder")
    parser.add_argument("--raw-dir", type=Path, default=_REPO_ROOT / "datasets" / "raw")
    parser.add_argument("--processed-dir", type=Path, default=_REPO_ROOT / "datasets" / "processed")
    parser.add_argument("--db-path", type=Path, default=_REPO_ROOT / "datasets" / "index" / "composition_index.sqlite")
    parser.add_argument("--acquire", action="store_true", help="Download missing official NASA PDS files before rebuilding")
    parser.add_argument("--force-download", action="store_true", help="Re-download all official artifacts even if present")
    args = parser.parse_args()

    if args.acquire or args.force_download:
        acquire_missing_artifacts(args.raw_dir, force=args.force_download)

    if not args.raw_dir.exists():
        print(f"[ERROR] Raw dataset directory does not exist: {args.raw_dir}", file=sys.stderr)
        return 1

    index = CompositionSpatialIndex(args.db_path)
    status = index.rebuild_from_raw_directory(args.raw_dir, args.processed_dir)
    if not status.index_available or status.integrity_status != IntegrityStatus.VERIFIED:
        print(f"[ERROR] Index verification failed: {status.model_dump()}", file=sys.stderr)
        return 2

    # Smoke verification queries via CompositionSearchService
    search = CompositionSearchService(index)
    fe_res = search.search(StructuredCompositionQuery(query="Fe", astronaut_latitude=-4.59, astronaut_longitude=137.44, limit=5))
    gyp_res = search.search(StructuredCompositionQuery(query="gypsum", limit=5))

    summary = {
        "generation_id": status.active_generation_id,
        "integrity_status": status.integrity_status.value,
        "checksum_valid": status.checksum_valid,
        "ingested_products_count": status.ingested_products_count,
        "total_validated_evidence": status.total_validated_evidence,
        "located_evidence_count": status.located_evidence_count,
        "unlocated_evidence_count": status.unlocated_evidence_count,
        "rejected_record_count": status.rejected_record_count,
        "instruments_indexed": status.instruments_indexed,
        "reproducibility_manifest_path": status.reproducibility_manifest_path,
        "smoke_fe_located_matches": fe_res.total_located_matches,
        "smoke_gypsum_located_matches": gyp_res.total_located_matches,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
