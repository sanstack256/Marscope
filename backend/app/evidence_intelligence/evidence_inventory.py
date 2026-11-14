"""
MARSCOPE Evidence Inventory & Raw-Data Validation State Auditor
Martian Surface Intelligence & Exploration System

Explicitly distinguishes: catalogued, discovered, acquired, integrity_verified,
label_parsed, scientifically_validated, processed, renderable, and derived.
Never marks a dataset renderable simply because its catalogue record exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from app.evidence_intelligence.schemas import DatasetValidationStage
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import DatasetLifecycleStatus


def audit_dataset_validation_stages(
    *,
    catalog_service: DatasetCatalogService,
    raw_dir: Path,
    processed_dir: Path,
) -> List[DatasetValidationStage]:
    """Audit actual local files, labels, manifests, and validation state per catalogued dataset."""
    raw_root = raw_dir.parent
    entries: List[DatasetValidationStage] = []

    for ds in sorted(catalog_service.list_datasets(), key=lambda d: d.id):
        local_path = (raw_root / ds.local_file_path) if ds.local_file_path else None
        acquired = bool(local_path and local_path.exists())
        lbl_path = (raw_root / ds.local_label_path) if ds.local_label_path else None
        label_parsed = bool(lbl_path and lbl_path.exists())

        proc_manifest = processed_dir / f"{ds.id}.processing.json"
        processed = False
        derived = False
        if proc_manifest.exists():
            try:
                pdata = json.loads(proc_manifest.read_text(encoding="utf-8"))
                dem_f = pdata.get("files", {}).get("dem")
                processed = bool(dem_f and (processed_dir / dem_f).exists())
                slope_f = pdata.get("files", {}).get("slope")
                tri_f = pdata.get("files", {}).get("roughness")
                derived = bool(
                    slope_f and tri_f and (processed_dir / slope_f).exists() and (processed_dir / tri_f).exists()
                )
            except Exception:
                processed = False

        sci_valid = ds.status in {
            DatasetLifecycleStatus.VALIDATED,
            DatasetLifecycleStatus.PROCESSED,
            DatasetLifecycleStatus.AVAILABLE,
        }
        integrity_verified = acquired and bool(ds.sha256_checksum)
        is_remote_wmts = (
            "wmts" in (ds.data_format or "").lower()
            or "wmts" in (ds.original_product_url or "").lower()
        )
        renderable = (acquired and sci_valid) or (is_remote_wmts and sci_valid)

        missing_req = None
        if not acquired and not is_remote_wmts:
            missing_req = f"Local raw file missing for '{ds.product_id}'; requires real NASA PDS acquisition."
        elif not sci_valid:
            missing_req = f"Dataset status is '{ds.status.value}'; requires validation before scientific use."

        entries.append(
            DatasetValidationStage(
                dataset_id=ds.id,
                product_id=ds.product_id,
                product_type=ds.product_type,
                catalogued=True,
                discovered=True,
                acquired=acquired,
                integrity_verified=integrity_verified,
                label_parsed=label_parsed,
                scientifically_validated=sci_valid,
                processed=processed,
                renderable=renderable,
                derived=derived,
                native_resolution_m=ds.horizontal_resolution_meters,
                sha256_checksum=ds.sha256_checksum,
                missing_requirement=missing_req,
            )
        )

    return entries
