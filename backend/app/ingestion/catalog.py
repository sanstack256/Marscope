"""
MARSCOPE Reusable Dataset Catalog Service
Martian Surface Intelligence & Exploration System

Maintains registered planetary products, tracks multi-stage verification states
independently from discovery/license/download/processing, and persists metadata.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from app.core.persistence import atomic_write_text
from app.geospatial.crs import validate_mars_crs
from app.geospatial.raster import RasterInspectionService
from app.ingestion.acquisition import AcquisitionService, safe_write_downloaded_bytes, validate_artifact_signature
from app.ingestion.pds_label import extract_pds3_metadata, extract_pds4_metadata
from app.ingestion.sources.hirise import HiriseSourceAdapter
from app.ingestion.sources.mars_trek import MarsTrekSourceAdapter
from app.ingestion.sources.msl_curiosity import MslCuriositySourceAdapter
from app.ingestion.sources.pds_mola import PdsMolaSourceAdapter
from app.ingestion.sources.usgs_pgm import UsgsPlanetaryGeologicMappingAdapter
from app.schemas.dataset import (
    AcquisitionState,
    ChecksumSource,
    Dataset,
    DatasetLifecycleStatus,
    VerificationState,
    lifecycle_to_acquisition_state,
    map_dataset_lifecycle_state,
)


class DatasetCatalogService:
    def __init__(self, catalog_storage_dir: Path, raw_data_dir: Optional[Path] = None):
        self.catalog_storage_dir = catalog_storage_dir
        self.catalog_storage_dir.mkdir(parents=True, exist_ok=True)
        self.raw_data_dir = raw_data_dir or (catalog_storage_dir.parent / "raw")
        self._datasets: Dict[str, Dataset] = {}
        self._sources = [
            PdsMolaSourceAdapter(),
            HiriseSourceAdapter(),
            MslCuriositySourceAdapter(),
            MarsTrekSourceAdapter(),
            UsgsPlanetaryGeologicMappingAdapter(),
        ]
        self._load_persisted_catalog()

    def discover_all_sources(self) -> List[Dataset]:
        """
        Poll all registered source adapters to discover planetary products without
        falsely marking unverified metadata as validated.
        """
        discovered: List[Dataset] = []
        for src in self._sources:
            try:
                products = src.discover_products()
                for p in products:
                    if p.id not in self._datasets:
                        self.register_dataset(p)
                    discovered.append(self._datasets[p.id])
            except Exception as exc:
                print(f"Error querying adapter {src.source_name}: {exc}")
        return discovered

    def register_dataset(self, dataset: Dataset) -> Dataset:
        """Register or update a dataset in the catalog and persist its metadata."""
        self._datasets[dataset.id] = dataset
        self._persist_dataset(dataset)
        return dataset

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        return self._datasets.get(dataset_id)

    def list_datasets(
        self,
        mission: Optional[str] = None,
        instrument: Optional[str] = None,
        product_type: Optional[str] = None,
        status: Optional[DatasetLifecycleStatus] = None,
    ) -> List[Dataset]:
        results = list(self._datasets.values())
        if mission:
            results = [d for d in results if mission.lower() in d.mission.lower()]
        if instrument:
            results = [d for d in results if instrument.lower() in d.instrument.lower()]
        if product_type:
            results = [d for d in results if product_type.lower() in d.product_type.lower()]
        if status:
            results = [d for d in results if d.status == status]
        return results

    def update_dataset_status(
        self,
        dataset_id: str,
        status: DatasetLifecycleStatus,
        failure_reason: Optional[str] = None,
        processing_step: Optional[str] = None,
        acquisition_state: Optional[AcquisitionState] = None,
    ) -> Dataset:
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise KeyError(f"Dataset '{dataset_id}' not found in catalog.")

        dataset.status = status
        if acquisition_state is not None:
            dataset.acquisition_state = acquisition_state
        else:
            dataset.acquisition_state = lifecycle_to_acquisition_state(
                status,
                is_wmts=("{" in (dataset.original_product_url or "")),
                validation_passed=(status not in {DatasetLifecycleStatus.FAILED_VALIDATION}),
                has_local_file=bool(dataset.local_file_path),
            )
        if failure_reason is not None:
            dataset.failure_reason = failure_reason
        elif status not in {
            DatasetLifecycleStatus.FAILED_DOWNLOAD,
            DatasetLifecycleStatus.FAILED_VALIDATION,
            DatasetLifecycleStatus.FAILED_PROCESSING,
        }:
            dataset.failure_reason = None
        if processing_step and processing_step not in dataset.processing_history:
            dataset.processing_history.append(processing_step)

        self._persist_dataset(dataset)
        return dataset

    def check_study_area_coverage(
        self,
        dataset_id: str,
        target_bounds: Dict[str, float],
    ) -> Dict[str, Any]:
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise KeyError(f"Dataset '{dataset_id}' not found.")

        overlap_ratio = PdsMolaSourceAdapter.calculate_spatial_overlap(dataset.coverage, target_bounds)
        is_covered = overlap_ratio > 0.0
        is_full = overlap_ratio >= 0.999

        return {
            "dataset_id": dataset.id,
            "product_id": dataset.product_id,
            "target_bounds": target_bounds,
            "dataset_bounds": dataset.coverage.model_dump(),
            "overlap_ratio": round(overlap_ratio, 4),
            "overlap_percentage": round(overlap_ratio * 100.0, 2),
            "is_covered": is_covered,
            "is_fully_covered": is_full,
        }

    def validate_dataset_integrity(self, dataset_id: str, target_bounds: Dict[str, float]) -> Dict[str, Any]:
        """
        Validate CRS, coverage, label schema, physical units/scaling, checksum, and
        local binary/raster integrity honestly.
        Never marks unacquired products or streaming WMTS URL templates as locally validated rasters.
        """
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise KeyError(f"Dataset '{dataset_id}' not found.")

        coverage_result = self.check_study_area_coverage(dataset_id, target_bounds)
        crs_valid = validate_mars_crs(dataset.coordinate_reference_system)
        dataset.verification.field_verification["crs"] = (
            VerificationState.VERIFIED if crs_valid else VerificationState.FAILED
        )
        dataset.verification.coverage_verification = (
            VerificationState.VERIFIED if coverage_result["is_covered"] else VerificationState.FAILED
        )

        is_wmts = "{" in (dataset.original_product_url or "")
        local_raw = self._resolve_existing_path(dataset.local_file_path) if not is_wmts else None
        local_proc = self._resolve_existing_path(dataset.processed_file_path) if not is_wmts else None
        local_lbl = self._resolve_existing_path(dataset.local_label_path) if not is_wmts else None
        has_local_file = local_raw is not None or local_proc is not None

        failures: List[str] = []
        warnings: List[str] = []
        checksum_verified: Optional[bool] = None
        label_verified: Optional[bool] = None
        raster_report: Optional[Dict[str, Any]] = None

        if not crs_valid:
            failures.append(f"Invalid or Earth-bound CRS: {dataset.coordinate_reference_system!r}")
        if not coverage_result["is_covered"]:
            failures.append("Spatial coverage does not intersect requested study area bounds.")

        if local_raw is not None:
            actual_size = local_raw.stat().st_size
            if actual_size <= 0:
                failures.append(f"Local raw file '{local_raw.name}' is empty (0 bytes).")
            elif dataset.sha256_checksum:
                calc_sha = AcquisitionService._compute_file_sha256(local_raw)
                if calc_sha != dataset.sha256_checksum.strip().lower():
                    checksum_verified = False
                    failures.append(
                        f"SHA-256 checksum mismatch for '{local_raw.name}': expected {dataset.sha256_checksum}, got {calc_sha}."
                    )
                else:
                    checksum_verified = True
                    dataset.verification.download_verification = VerificationState.VERIFIED
            else:
                dataset.verification.download_verification = VerificationState.VERIFIED

            # Inspect companion label on disk if referenced or sibling exists
            if local_lbl is None and local_raw.suffix.lower() in {".img", ".jp2", ".csv", ".tab"}:
                for ext in (".lbl", ".LBL", ".xml"):
                    sib = local_raw.with_suffix(ext)
                    if sib.exists():
                        local_lbl = sib
                        break
            if local_lbl is not None:
                try:
                    AcquisitionService._apply_pds_label_verification(dataset, local_lbl)
                    label_verified = True
                    if local_lbl.suffix.lower() == ".lbl":
                        pds_meta = extract_pds3_metadata(local_lbl)
                        is_dem_or_img = local_raw.suffix.lower() in {".img", ".jp2"} and "dem" in dataset.product_type.lower()
                        if is_dem_or_img and pds_meta.get("scaling_factor") is None and "FLOAT" not in str(pds_meta.get("sample_type", "")).upper() and "REAL" not in str(pds_meta.get("sample_type", "")).upper():
                            failures.append(f"Integer PDS3 DEM label '{local_lbl.name}' lacks required SCALING_FACTOR.")
                        if pds_meta.get("units", "unknown") == "unknown" and "dem" in dataset.product_type.lower():
                            failures.append(f"PDS3 DEM label '{local_lbl.name}' lacks physical measurement UNIT.")
                except Exception as exc:
                    label_verified = False
                    failures.append(f"Companion label validation error ({local_lbl.name}): {exc}")

        # Inspect processed GeoTIFF if present (verify raster transform, CRS, units, scaling, dimensions)
        inspect_target = local_proc or (
            local_raw if (local_raw is not None and local_raw.suffix.lower() in {".tif", ".tiff", ".jp2"}) else None
        )
        if inspect_target is not None:
            try:
                raster_report = RasterInspectionService.inspect_raster_file(
                    inspect_target,
                    explicit_units=dataset.units if dataset.units != "unknown" else None,
                )
                if not raster_report.get("crs_verified"):
                    failures.append(f"Raster '{inspect_target.name}' failed Mars CRS verification ({raster_report.get('crs')!r}).")
                if not raster_report.get("units_verified"):
                    warnings.append(f"Raster '{inspect_target.name}' physical units remain unverified in GeoTIFF/label.")
                if raster_report.get("scaling_verified") is False:
                    warnings.append(f"Raster '{inspect_target.name}' lacks explicit scaling/offset metadata.")
                rb = raster_report.get("bounds") or []
                if len(rb) == 4 and (not all(abs(float(v)) <= 1e9 for v in rb) or rb[0] >= rb[2] or rb[1] >= rb[3]):
                    failures.append(f"Raster '{inspect_target.name}' has invalid spatial bounds {rb}.")
            except Exception as exc:
                failures.append(f"Raster structural validation error ({inspect_target.name}): {exc}")

        if not is_wmts and has_local_file and (dataset.processing_level.lower() in {"unknown", ""} or dataset.units.lower() in {"unknown", ""}):
            if "waypoint" not in dataset.id.lower() and "rems" not in dataset.id.lower():
                warnings.append("Product processing_level or measurement units remain incomplete.")

        dataset.verification.last_checked_utc = datetime.now(timezone.utc)
        validation_passed = len(failures) == 0

        report = {
            "validated_at_utc": dataset.verification.last_checked_utc.isoformat(),
            "is_wmts": is_wmts,
            "has_local_file": has_local_file,
            "checksum_verified": checksum_verified,
            "label_verified": label_verified,
            "crs_valid": crs_valid,
            "coverage_overlap_ratio": coverage_result["overlap_ratio"],
            "raster_validation": (
                {
                    "dimensions": raster_report.get("dimensions"),
                    "crs": raster_report.get("crs"),
                    "crs_verified": raster_report.get("crs_verified"),
                    "units": raster_report.get("units"),
                    "units_verified": raster_report.get("units_verified"),
                    "scaling_verified": raster_report.get("scaling_verified"),
                }
                if raster_report
                else None
            ),
            "failures": failures,
            "warnings": warnings,
            "validation_passed": validation_passed,
        }
        dataset.validation_report = report

        if not validation_passed:
            new_status = DatasetLifecycleStatus.FAILED_VALIDATION
            acq_state = AcquisitionState.REJECTED
            step = f"Validation failed: {'; '.join(failures)}"
            fail_reason_arg: Optional[str] = "; ".join(failures)
        elif is_wmts:
            # Visual streaming endpoints are NEVER upgraded to validated scientific local rasters
            wmts_verified = dataset.verification.metadata_verification == VerificationState.VERIFIED
            new_status = DatasetLifecycleStatus.AVAILABLE if wmts_verified else DatasetLifecycleStatus.METADATA_VERIFIED
            acq_state = AcquisitionState.AVAILABLE if wmts_verified else AcquisitionState.UNVERIFIED
            dataset.verification.download_verification = VerificationState.NOT_APPLICABLE
            dataset.verification.processing_verification = VerificationState.NOT_APPLICABLE
            step = "Validated WMTS visual layer CRS & overlap (not a downloadable scientific raster product)"
            fail_reason_arg = None
        elif local_proc is not None and dataset.status == DatasetLifecycleStatus.PROCESSED:
            new_status = DatasetLifecycleStatus.PROCESSED
            acq_state = AcquisitionState.PROCESSED
            dataset.verification.processing_verification = VerificationState.VERIFIED
            step = "Validated CRS, spatial overlap, checksum, label, and processed raster derivatives"
            fail_reason_arg = None
        elif has_local_file:
            new_status = DatasetLifecycleStatus.VALIDATED
            acq_state = AcquisitionState.PRODUCT_VALIDATED
            step = "Validated CRS, spatial overlap, checksum, and product format integrity"
            fail_reason_arg = None
        else:
            new_status = DatasetLifecycleStatus.METADATA_VERIFIED
            acq_state = AcquisitionState.UNVERIFIED
            step = "Validated catalog CRS & coverage geometry; local product acquisition pending"
            fail_reason_arg = None

        self.update_dataset_status(
            dataset_id,
            new_status,
            failure_reason=fail_reason_arg,
            processing_step=step,
            acquisition_state=acq_state,
        )
        return {
            "dataset_id": dataset.id,
            "product_id": dataset.product_id,
            "crs_valid": crs_valid,
            "crs": dataset.coordinate_reference_system,
            "coverage_check": coverage_result,
            "license_status": dataset.license.value,
            "local_file_present": has_local_file,
            "acquisition_state": dataset.acquisition_state.value if dataset.acquisition_state else None,
            "validation_report": report,
            "verification": dataset.verification.model_dump(),
            "validation_passed": validation_passed,
        }

    async def verify_remote_capabilities(self, dataset_id: str) -> Dataset:
        """
        Verify remote archive availability and label/WMTS metadata directly from the source URL.
        Updates archive_availability and metadata_verification fields based on observed response.
        """
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise KeyError(f"Dataset '{dataset_id}' not found.")

        check_url = dataset.original_label_url or dataset.original_product_url
        if "{" in check_url:
            raise ValueError("Cannot fetch template URL directly without capabilities endpoint.")

        from app.ingestion.http_client import create_async_http_client

        async with create_async_http_client(timeout_seconds=12.0) as client:
            resp = await client.get(check_url)
            now = datetime.now(timezone.utc)
            dataset.verification.last_checked_utc = now

            if resp.status_code != 200:
                dataset.verification.archive_availability = VerificationState.FAILED
                dataset.verification.evidence_notes.append(f"HTTP {resp.status_code} from {check_url} at {now.isoformat()}")
                self._persist_dataset(dataset)
                return dataset

            dataset.verification.archive_availability = VerificationState.VERIFIED
            if check_url.lower().endswith(".xml") and ("Capabilities" in resp.text or "WMTS" in resp.text):
                dataset.verification.metadata_verification = VerificationState.VERIFIED
                dataset.verification.coverage_verification = VerificationState.VERIFIED
                dataset.verification.field_verification["crs"] = VerificationState.VERIFIED
                dataset.verification.field_verification["coverage"] = VerificationState.VERIFIED
                dataset.status = DatasetLifecycleStatus.AVAILABLE
                dataset.verification.evidence_notes.append(
                    f"Verified WMTSCapabilities HTTP 200 ({len(resp.content)} bytes) at {now.isoformat()}"
                )
            elif check_url.lower().endswith((".lbl", ".xml")):
                suffix = ".lbl" if check_url.lower().endswith(".lbl") else ".xml"
                lbl_path = self.raw_data_dir / f"{dataset.id}_remote{suffix}"
                safe_write_downloaded_bytes(
                    lbl_path,
                    resp.content,
                    source_url=check_url,
                    content_type=resp.headers.get("content-type"),
                    http_status=resp.status_code,
                    max_bytes=20_000_000,
                    overwrite=True,
                )
                AcquisitionService._apply_pds_label_verification(dataset, lbl_path)
                dataset.local_label_path = str(lbl_path.relative_to(self.catalog_storage_dir.parent.parent))
                if dataset.status == DatasetLifecycleStatus.DISCOVERED:
                    dataset.status = DatasetLifecycleStatus.METADATA_VERIFIED
                    dataset.acquisition_state = AcquisitionState.UNVERIFIED

            self._persist_dataset(dataset)
            return dataset

    def get_source_registry_report(self) -> List[Dict[str, Any]]:
        """
        Generate source registry entries dynamically from active source adapters
        and observed catalog verification states (never hardcoded).
        """
        report: List[Dict[str, Any]] = []
        for adapter in self._sources:
            adapter_products = adapter.discover_products()
            matched_catalog: List[Dataset] = [
                self._datasets[p.id] if p.id in self._datasets else p for p in adapter_products
            ]

            def _agg(field: str) -> str:
                states = [getattr(d.verification, field).value for d in matched_catalog]
                if not states:
                    return VerificationState.UNKNOWN.value
                if all(s == VerificationState.VERIFIED.value for s in states):
                    return VerificationState.VERIFIED.value
                if any(s == VerificationState.VERIFIED.value for s in states):
                    return "partial"
                if any(s == VerificationState.FAILED.value for s in states):
                    return VerificationState.FAILED.value
                if all(s == VerificationState.NOT_APPLICABLE.value for s in states):
                    return VerificationState.NOT_APPLICABLE.value
                return VerificationState.UNVERIFIED.value

            evidence: List[str] = []
            for d in matched_catalog:
                evidence.extend(d.verification.evidence_notes)

            report.append({
                "source_name": adapter.source_name,
                "base_url": adapter.base_url,
                "product_count": len(matched_catalog),
                "product_ids": [d.id for d in matched_catalog],
                "verification_breakdown": {
                    "archive_availability": _agg("archive_availability"),
                    "product_discovery": _agg("product_discovery"),
                    "metadata_verification": _agg("metadata_verification"),
                    "license_verification": _agg("license_verification"),
                    "coverage_verification": _agg("coverage_verification"),
                    "download_verification": _agg("download_verification"),
                    "processing_verification": _agg("processing_verification"),
                },
                "licenses": sorted({d.license.value for d in matched_catalog}),
                "evidence_notes": evidence[:10],
            })
        return report

    def _resolve_existing_path(self, rel_or_abs: Optional[str]) -> Optional[Path]:
        if not rel_or_abs:
            return None
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p if p.exists() else None
        for root in (self.raw_data_dir.parent, self.catalog_storage_dir.parent):
            cand = root / p
            if cand.exists():
                return cand
        return None

    @staticmethod
    def _compute_file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _validate_processing_manifest(proc_json_path: Path, dataset: Dataset, processed_path: Path) -> tuple[bool, Optional[str]]:
        try:
            payload = json.loads(proc_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, f"Corrupt .processing.json at '{proc_json_path.name}': {exc}"
        if not isinstance(payload, dict):
            return False, f"Invalid .processing.json structure at '{proc_json_path.name}': expected JSON object."
        rec_ds = payload.get("dataset_id") or payload.get("source_dataset_id")
        if rec_ds and str(rec_ds) != dataset.id:
            return False, f"Processing manifest dataset_id '{rec_ds}' does not match '{dataset.id}'."
        if not processed_path.exists() or not processed_path.is_file() or processed_path.stat().st_size == 0:
            return False, f"Processed artifact '{processed_path.name}' missing or empty."
        rec_raw_sha = payload.get("raw_sha256") or payload.get("source_sha256")
        if rec_raw_sha and dataset.sha256_checksum and str(rec_raw_sha).lower() != dataset.sha256_checksum.lower():
            return False, "Processing manifest source SHA-256 differs from current verified raw SHA-256 (stale processed artifact)."
        rec_proc_sha = payload.get("processed_sha256") or payload.get("output_sha256")
        if rec_proc_sha:
            actual_proc_sha = DatasetCatalogService._compute_file_sha256(processed_path)
            if actual_proc_sha.lower() != str(rec_proc_sha).lower():
                return False, "Processed artifact SHA-256 mismatch vs .processing.json."
        return True, None

    def _persist_dataset(self, dataset: Dataset) -> None:
        file_path = self.catalog_storage_dir / f"{dataset.id}.json"
        atomic_write_text(file_path, dataset.model_dump_json(indent=2))

    def _load_persisted_catalog(self) -> None:
        bootstrap_map: Dict[str, Dict[str, Any]] = {}
        try:
            bpath = self.catalog_storage_dir.parent / "bootstrap_manifest.json"
            if bpath.exists():
                bdata = json.loads(bpath.read_text(encoding="utf-8"))
                for item in bdata.get("products") or []:
                    bootstrap_map[str(item["dataset_id"])] = item
        except Exception:
            bootstrap_map = {}

        manifests_dir = self.catalog_storage_dir.parent / "manifests"
        processed_dir = self.catalog_storage_dir.parent / "processed"

        for json_file in self.catalog_storage_dir.glob("*.json"):
            try:
                ds = Dataset.model_validate_json(json_file.read_text(encoding="utf-8"))
                is_wmts = "{" in (ds.original_product_url or "")

                # Reconcile tracked catalog record against actual .gitignore'd workspace files
                b_entry = bootstrap_map.get(ds.id)
                expected_sha = (
                    str(b_entry["expected_sha256"]).strip().lower()
                    if b_entry and b_entry.get("expected_sha256")
                    else (str(ds.sha256_checksum).strip().lower() if ds.sha256_checksum else None)
                )
                has_manifest_pin = bool(b_entry and b_entry.get("expected_sha256"))

                raw_cand: Optional[Path] = None
                if not is_wmts and b_entry:
                    raw_cand = self._resolve_existing_path(b_entry.get("expected_raw_path"))
                elif not is_wmts and ds.local_file_path:
                    raw_cand = self._resolve_existing_path(ds.local_file_path)

                if not is_wmts and raw_cand is not None:
                    actual_size = raw_cand.stat().st_size
                    exp_sz = b_entry.get("expected_size_bytes") if b_entry else ds.file_size_bytes
                    size_ok = (exp_sz is None) or (actual_size == int(exp_sz))
                    actual_sha = self._compute_file_sha256(raw_cand)

                    if not size_ok:
                        ds.status = DatasetLifecycleStatus.FAILED_VALIDATION
                        ds.failure_reason = f"Local raw size mismatch: expected {exp_sz} B, found {actual_size} B."
                        ds.verification.download_verification = VerificationState.FAILED
                    elif expected_sha and actual_sha.lower() != expected_sha.lower():
                        ds.status = DatasetLifecycleStatus.FAILED_VALIDATION
                        ds.failure_reason = (
                            f"SHA-256 integrity mismatch for '{raw_cand.name}': "
                            f"expected {expected_sha[:16]}..., got {actual_sha[:16]}..."
                        )
                        ds.verification.download_verification = VerificationState.FAILED
                    else:
                        if b_entry and b_entry.get("expected_raw_path"):
                            ds.local_file_path = str(b_entry["expected_raw_path"])
                            lbl_cand = self._resolve_existing_path(b_entry.get("expected_label_path"))
                            if lbl_cand is not None:
                                ds.local_label_path = str(b_entry["expected_label_path"])
                        ds.file_size_bytes = actual_size
                        if not ds.sha256_checksum:
                            ds.sha256_checksum = actual_sha
                        if ds.checksum_source is None:
                            ds.checksum_source = (
                                ChecksumSource.MANIFEST_PINNED
                                if has_manifest_pin
                                else ChecksumSource.LOCALLY_COMPUTED_ONLY
                            )
                        ds.verification.download_verification = VerificationState.VERIFIED
                        ds.verification.archive_availability = VerificationState.VERIFIED
                        if ds.status == DatasetLifecycleStatus.DISCOVERED:
                            ds.status = DatasetLifecycleStatus.DOWNLOADED
                        mpath = manifests_dir / f"{ds.id}.manifest.json"
                        if mpath.exists() and not ds.failure_reason:
                            ds.verification.metadata_verification = VerificationState.VERIFIED
                            ds.verification.coverage_verification = VerificationState.VERIFIED
                            ds.verification.field_verification.update(
                                {
                                    "crs": VerificationState.VERIFIED,
                                    "units": VerificationState.VERIFIED,
                                    "coverage": VerificationState.VERIFIED,
                                    "license": VerificationState.VERIFIED,
                                }
                            )

                if not is_wmts and ds.status != DatasetLifecycleStatus.FAILED_VALIDATION:
                    proc_rel = b_entry.get("expected_processed_path") if b_entry else ds.processed_file_path
                    proc_cand = self._resolve_existing_path(proc_rel) if proc_rel else None
                    proc_json = processed_dir / f"{ds.id}.processing.json"
                    if proc_cand is not None and proc_json.exists() and not ds.failure_reason:
                        proc_ok, proc_err = self._validate_processing_manifest(proc_json, ds, proc_cand)
                        if proc_ok:
                            ds.processed_file_path = str(proc_rel)
                            ds.verification.processing_verification = VerificationState.VERIFIED
                            ds.status = DatasetLifecycleStatus.PROCESSED
                        else:
                            ds.processed_file_path = None
                            ds.verification.processing_verification = VerificationState.FAILED
                            ds.status = DatasetLifecycleStatus.FAILED_PROCESSING
                            ds.failure_reason = proc_err

                if ds.local_file_path and self._resolve_existing_path(ds.local_file_path) is None:
                    ds.local_file_path = None
                    if not is_wmts:
                        ds.verification.download_verification = VerificationState.UNVERIFIED
                if ds.processed_file_path and self._resolve_existing_path(ds.processed_file_path) is None:
                    ds.processed_file_path = None
                    ds.verification.processing_verification = VerificationState.UNVERIFIED
                if (
                    not is_wmts
                    and ds.local_file_path is None
                    and ds.processed_file_path is None
                    and ds.status in {
                        DatasetLifecycleStatus.DOWNLOADED,
                        DatasetLifecycleStatus.VALIDATED,
                        DatasetLifecycleStatus.PROCESSED,
                        DatasetLifecycleStatus.AVAILABLE,
                    }
                ):
                    ds.status = (
                        DatasetLifecycleStatus.METADATA_VERIFIED
                        if ds.verification.metadata_verification == VerificationState.VERIFIED
                        else DatasetLifecycleStatus.DISCOVERED
                    )
                    ds.verification.coverage_verification = VerificationState.UNVERIFIED
                    note = "Local raw/processed asset absent on disk in this checkout; run scripts/bootstrap_datasets.py --verify/--acquire."
                    if note not in ds.verification.evidence_notes:
                        ds.verification.evidence_notes.append(note)

                ds.acquisition_state = lifecycle_to_acquisition_state(
                    ds.status,
                    is_wmts=is_wmts,
                    validation_passed=(not bool(ds.failure_reason)),
                    has_local_file=bool(ds.local_file_path),
                )
                if ds.failure_reason and ds.status == DatasetLifecycleStatus.PROCESSED:
                    ds.verification.processing_verification = VerificationState.FAILED
                    ds.acquisition_state = AcquisitionState.UNVERIFIED
                self._datasets[ds.id] = ds
            except Exception as exc:
                print(f"Failed to read catalog entry from {json_file}: {exc}")

    def audit_dataset_readiness(
        self,
        *,
        composition_index: Optional[Any] = None,
        verify_checksums: bool = True,
    ) -> Dict[str, Any]:
        """Return Prompt 22 Section 12 12-property Data Readiness Audit across all cataloged datasets."""
        bootstrap_map: Dict[str, Dict[str, Any]] = {}
        bpath = self.catalog_storage_dir.parent / "bootstrap_manifest.json"
        if bpath.exists():
            try:
                bdata = json.loads(bpath.read_text(encoding="utf-8"))
                for item in bdata.get("products") or []:
                    bootstrap_map[str(item["dataset_id"])] = item
            except Exception:
                bootstrap_map = {}

        idx_status = None
        indexed_ds_ids: set[str] = set()
        if composition_index is not None:
            try:
                idx_status = composition_index.get_status()
                for ds_name in (idx_status.dataset_counts or {}).keys():
                    indexed_ds_ids.add(str(ds_name))
            except Exception:
                idx_status = None

        processed_dir = self.catalog_storage_dir.parent / "processed"
        records: List[Dict[str, Any]] = []
        state_counts: Dict[str, int] = {}

        for ds in sorted(self._datasets.values(), key=lambda d: d.id):
            is_wmts = "{" in (ds.original_product_url or "")
            b_entry = bootstrap_map.get(ds.id) or {}
            mandatory = bool(b_entry.get("mandatory_for_gale_workflow", False))
            companions = [str(c) for c in (b_entry.get("companion_dependencies") or [])]
            ds_root = self.catalog_storage_dir.parent
            missing_comp = [c for c in companions if not (ds_root / c).exists()]

            raw_path = self._resolve_existing_path(ds.local_file_path or b_entry.get("expected_raw_path"))
            raw_exists = raw_path is not None and raw_path.is_file()
            actual_size = raw_path.stat().st_size if raw_exists else None

            expected_sha = (
                str(b_entry["expected_sha256"]).strip().lower()
                if b_entry.get("expected_sha256")
                else (str(ds.sha256_checksum).strip().lower() if ds.sha256_checksum else None)
            )
            actual_sha: Optional[str] = None
            checksum_matches: Optional[bool] = None
            checksum_source = ds.checksum_source.value if ds.checksum_source else (
                ChecksumSource.MANIFEST_PINNED.value if b_entry.get("expected_sha256") else ChecksumSource.UNAVAILABLE.value
            )
            if raw_exists and verify_checksums:
                actual_sha = self._compute_file_sha256(raw_path)
                if expected_sha:
                    checksum_matches = actual_sha.lower() == expected_sha.lower()
                else:
                    checksum_source = ChecksumSource.LOCALLY_COMPUTED_ONLY.value

            format_ok = False
            if raw_exists:
                try:
                    validate_artifact_signature(raw_path.read_bytes()[:4096], raw_path)
                    format_ok = True
                except Exception:
                    format_ok = False

            proc_rel = b_entry.get("expected_processed_path") or ds.processed_file_path
            proc_path = self._resolve_existing_path(proc_rel) if proc_rel else None
            proc_exists = proc_path is not None and proc_path.is_file()
            proc_json = processed_dir / f"{ds.id}.processing.json"
            proc_valid: Optional[bool] = None
            proc_err: Optional[str] = None
            if proc_exists and proc_json.exists():
                proc_valid, proc_err = self._validate_processing_manifest(proc_json, ds, proc_path)
            elif proc_exists and not proc_json.exists():
                proc_valid = False
                proc_err = f"Missing processing manifest '{proc_json.name}'."

            is_indexed = ds.id in indexed_ds_ids or any(ds.id.lower() in k.lower() for k in indexed_ds_ids)
            crs_ok = bool(ds.coordinate_reference_system)
            units_ok = bool(ds.units and ds.units.lower() != "unknown")

            lifecycle_13 = map_dataset_lifecycle_state(
                ds.status,
                is_wmts=is_wmts,
                has_raw_file=raw_exists,
                has_expected_sha256=bool(expected_sha),
                checksum_matches=checksum_matches,
                companion_missing=bool(missing_comp),
                format_validated=format_ok,
                has_processed_artifact=proc_exists,
                processing_manifest_valid=proc_valid,
                is_indexed=is_indexed,
            )
            state_counts[lifecycle_13] = state_counts.get(lifecycle_13, 0) + 1

            if is_wmts:
                repro_tier = "REMOTE_WMTS_SERVICE"
                remediation = "Remote NASA/USGS WMTS imagery service; usable only when network egress is permitted."
            elif lifecycle_13 in {"INDEXED", "PROCESSED", "VALIDATED_FORMAT", "HASH_VERIFIED"} and checksum_matches is not False:
                repro_tier = "OFFLINE_REPRODUCIBLE"
                remediation = "Ready for offline verification and processing."
            elif lifecycle_13 in {"CORRUPT", "MISSING_COMPANION_FILES"}:
                repro_tier = "CORRUPT_OR_INCOMPLETE"
                remediation = proc_err or ds.failure_reason or (
                    f"Re-acquire dataset '{ds.id}' via `python3 scripts/bootstrap_datasets.py --acquire --dataset-id {ds.id} --overwrite`."
                )
            else:
                repro_tier = "ONLINE_ACQUIRABLE"
                remediation = (
                    f"Absent locally; acquire via `python3 scripts/bootstrap_datasets.py --acquire --dataset-id {ds.id}`."
                )

            records.append(
                {
                    "dataset_id": ds.id,
                    "product_id": ds.product_id,
                    "mission_instrument": f"{ds.mission} / {ds.instrument}",
                    "catalog_status": ds.status.value,
                    "lifecycle_state": lifecycle_13,
                    "raw_file_exists": raw_exists,
                    "raw_path": str(ds.local_file_path or b_entry.get("expected_raw_path") or ""),
                    "raw_size_bytes": actual_size,
                    "companion_labels_present": len(missing_comp) == 0,
                    "missing_companions": missing_comp,
                    "checksum_status": {
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                        "checksum_verified": checksum_matches,
                        "checksum_source": checksum_source,
                    },
                    "format_validation_status": "verified" if format_ok else ("unavailable" if not raw_exists else "failed"),
                    "processed_artifact_exists": proc_exists,
                    "processed_path": str(proc_rel or ""),
                    "processing_manifest_valid": proc_valid,
                    "crs_and_units_verified": {"crs_ok": crs_ok, "crs": ds.coordinate_reference_system, "units_ok": units_ok, "units": ds.units},
                    "indexed_in_composition_store": is_indexed,
                    "index_generation_id": getattr(idx_status, "active_generation_id", None) if idx_status else None,
                    "mandatory_for_gale_workflow": mandatory,
                    "reproducibility_tier": repro_tier,
                    "remediation_hint": remediation,
                }
            )

        mandatory_items = [r for r in records if r["mandatory_for_gale_workflow"]]
        mandatory_ready = all(
            r["lifecycle_state"] in {"INDEXED", "PROCESSED", "VALIDATED_FORMAT", "HASH_VERIFIED"}
            for r in mandatory_items
        ) if mandatory_items else False

        return {
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_catalog_datasets": len(records),
            "mandatory_gale_count": len(mandatory_items),
            "mandatory_gale_ready": mandatory_ready,
            "lifecycle_state_counts": state_counts,
            "index_available": bool(getattr(idx_status, "index_available", False)) if idx_status else False,
            "active_index_generation": getattr(idx_status, "active_generation_id", None) if idx_status else None,
            "datasets": records,
        }
