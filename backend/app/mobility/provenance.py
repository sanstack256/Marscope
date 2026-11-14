"""
MARSCOPE Terrain Data Inventory & Provenance Builder
Martian Surface Intelligence & Exploration System

Audits registered DEM datasets, local PDS3/GeoTIFF artifacts, and processing
manifests to provide verifiable provenance and resolution suitability metadata.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.schemas import TerrainDataInventoryEntry


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_terrain_data_inventory(
    *,
    catalog_service: DatasetCatalogService,
    raw_dir: Path,
    processed_dir: Path,
) -> List[TerrainDataInventoryEntry]:
    """
    Build the complete inventory of DEM datasets in the MARSCOPE catalog,
    inspecting local raw files, companion PDS3 labels, and processed manifests.
    """
    all_datasets = catalog_service.list_datasets()
    dem_datasets = [
        ds
        for ds in all_datasets
        if "DEM" in ds.product_type.upper() or "ELEVATION" in ds.product_type.upper()
    ]

    entries: List[TerrainDataInventoryEntry] = []
    for ds in sorted(dem_datasets, key=lambda d: d.id):
        raw_path: Optional[Path] = None
        if ds.local_file_path:
            cand = Path(ds.local_file_path)
            if cand.exists():
                raw_path = cand
            else:
                cand_rel = raw_dir.parent / ds.local_file_path
                if cand_rel.exists():
                    raw_path = cand_rel
        if raw_path is None:
            cand_raw = raw_dir / ds.product_id.lower()
            if cand_raw.exists():
                raw_path = cand_raw

        lbl_path: Optional[Path] = None
        if raw_path is not None:
            for sfx in (".lbl", ".LBL"):
                cand_l = raw_path.with_suffix(sfx)
                if cand_l.exists():
                    lbl_path = cand_l
                    break

        proc_manifest_path = processed_dir / f"{ds.id}.processing.json"
        proc_obj: Optional[Dict[str, Any]] = None
        if proc_manifest_path.exists():
            try:
                proc_obj = json.loads(proc_manifest_path.read_text(encoding="utf-8"))
            except Exception:
                proc_obj = None

        lbl_meta: Dict[str, Any] = {}
        if lbl_path is not None and lbl_path.exists():
            try:
                lbl_meta = extract_pds3_metadata(lbl_path)
            except Exception:
                lbl_meta = {}

        sha256_hex: Optional[str] = None
        if proc_obj and proc_obj.get("source_sha256"):
            sha256_hex = str(proc_obj["source_sha256"])
        elif ds.sha256_checksum:
            sha256_hex = ds.sha256_checksum
        elif raw_path is not None and raw_path.exists():
            sha256_hex = _sha256_file(raw_path)

        # Native resolution (pixels/deg and meters/pixel)
        native_ppd: Optional[float] = None
        if lbl_meta.get("map_resolution_ppd") is not None:
            try:
                native_ppd = float(lbl_meta["map_resolution_ppd"])
            except (TypeError, ValueError):
                native_ppd = None
        elif "000cb" in ds.product_id.lower():
            native_ppd = 4.0
        elif "090hb" in ds.product_id.lower():
            native_ppd = 16.0

        native_m: Optional[float] = ds.horizontal_resolution_meters
        if lbl_meta.get("map_scale_km_per_pixel") is not None:
            try:
                native_m = float(lbl_meta["map_scale_km_per_pixel"]) * 1000.0
            except (TypeError, ValueError):
                pass

        effective_m: Optional[float] = None
        if proc_obj and proc_obj.get("dx_meters") is not None:
            try:
                effective_m = float(proc_obj["dx_meters"])
            except (TypeError, ValueError):
                effective_m = native_m
        else:
            effective_m = native_m

        vertical_units = str(
            (proc_obj.get("units") if proc_obj else None)
            or lbl_meta.get("unit")
            or ds.units
            or "meters"
        ).lower()
        if vertical_units in {"m", "meter", "meters"}:
            vertical_units = "meters"

        nodata_val: Optional[float] = None
        if proc_obj and proc_obj.get("nodata_value") is not None:
            nodata_val = float(proc_obj["nodata_value"])
        elif lbl_meta.get("missing_constant") is not None:
            try:
                nodata_val = float(lbl_meta["missing_constant"])
            except (TypeError, ValueError):
                nodata_val = None
        elif ds.nodata_value is not None:
            nodata_val = float(ds.nodata_value)
        else:
            nodata_val = -32768.0 if "mola" in ds.id.lower() else None

        cov_bounds = {
            "min_lat": float(ds.coverage.min_latitude) if ds.coverage else -90.0,
            "max_lat": float(ds.coverage.max_latitude) if ds.coverage else 90.0,
            "min_lon": float(ds.coverage.min_longitude) if ds.coverage else 0.0,
            "max_lon": float(ds.coverage.max_longitude) if ds.coverage else 360.0,
        }

        limitations: List[str] = list(ds.known_limitations or [])
        if effective_m is not None and effective_m >= 1000.0:
            limitations.append(
                f"Coarse orbital grid spacing (~{effective_m:.0f} m/pixel effective, ~{native_m or effective_m:.0f} m/pixel nominal) "
                "resolves regional basin and mound hypsometry only."
            )
            limitations.append(
                "Unsuitable for local human-scale EVA slope assessment (<= 20 m/pixel required) or small-scale "
                "obstacle/boulder detection (<= 1 m/pixel required)."
            )
            limitations.append(
                "Horn 3x3 slope and TRI roughness kernels span ~3x3 pixels (~20 km x 20 km on 4 ppd MOLA), "
                "representing regional gradients rather than local foot-level terrain."
            )
        if raw_path is None:
            limitations.append(
                "Dataset is registered in catalog metadata only and has not been downloaded to local storage."
            )

        suitability = evaluate_dem_resolution_suitability(
            native_resolution_m=native_m,
            effective_resolution_m=effective_m,
            dem_available=(raw_path is not None and raw_path.exists()),
        )

        entries.append(
            TerrainDataInventoryEntry(
                dataset_id=ds.id,
                product_id=ds.product_id,
                title=ds.product_title,
                mission=ds.mission,
                instrument=ds.instrument,
                source_url=ds.original_product_url,
                local_raw_path=str(raw_path) if raw_path else None,
                local_label_path=str(lbl_path) if lbl_path else None,
                processed_manifest_path=str(proc_manifest_path) if proc_manifest_path.exists() else None,
                present_locally=(raw_path is not None and raw_path.exists()),
                processed_locally=(proc_obj is not None),
                sha256_checksum=sha256_hex,
                native_resolution_ppd=native_ppd,
                native_resolution_meters_per_pixel=round(native_m, 3) if native_m is not None else None,
                effective_resolution_meters_per_pixel=round(effective_m, 3) if effective_m is not None else None,
                crs=str((proc_obj.get("crs") if proc_obj else None) or ds.coordinate_reference_system or "IAU2000:49900"),
                vertical_datum="Mars MOLA Areoid (IAU 2000 reference sphere R=3396.0 km)",
                vertical_units=vertical_units,
                nodata_value=nodata_val,
                coverage_bounds=cov_bounds,
                license_status="not_verified",
                rights_statement=(
                    "NASA PDS planetary science archive artifact; explicit machine-readable license tag "
                    "not embedded in PDS3 detached label (reported as not_verified per data policy)."
                ),
                known_limitations=limitations,
                resolution_suitability=suitability,
            )
        )

    return entries
