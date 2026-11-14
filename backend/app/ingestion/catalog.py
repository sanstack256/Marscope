"""
MARSCOPE Reusable Dataset Catalog Service
Martian Surface Intelligence & Exploration System

Maintains registered planetary products, tracks multi-stage verification states
independently from discovery/license/download/processing, and persists metadata.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx
from app.geospatial.crs import validate_mars_crs
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.sources.hirise import HiriseSourceAdapter
from app.ingestion.sources.mars_trek import MarsTrekSourceAdapter
from app.ingestion.sources.msl_curiosity import MslCuriositySourceAdapter
from app.ingestion.sources.pds_mola import PdsMolaSourceAdapter
from app.ingestion.sources.usgs_pgm import UsgsPlanetaryGeologicMappingAdapter
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState


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
    ) -> Dataset:
        dataset = self._datasets.get(dataset_id)
        if not dataset:
            raise KeyError(f"Dataset '{dataset_id}' not found in catalog.")

        dataset.status = status
        if failure_reason:
            dataset.failure_reason = failure_reason
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
        Validate CRS, coverage, and local acquisition integrity honestly.
        Never marks an unacquired local binary product as PROCESSED/DOWNLOADED.
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

        is_wmts = "{" in dataset.original_product_url
        has_local_file = False
        if not is_wmts and dataset.local_file_path:
            if self._resolve_existing_path(dataset.local_file_path) is not None:
                has_local_file = True
                dataset.verification.download_verification = VerificationState.VERIFIED

        dataset.verification.last_checked_utc = datetime.now(timezone.utc)

        if not crs_valid or not coverage_result["is_covered"]:
            new_status = DatasetLifecycleStatus.FAILED_VALIDATION
            step = "Validation failed: invalid CRS or zero target overlap"
        elif is_wmts or has_local_file:
            new_status = DatasetLifecycleStatus.VALIDATED
            step = "Validated CRS, spatial overlap, and product integrity"
        else:
            # Catalog bounds/CRS checked, but binary product is not yet downloaded locally
            new_status = DatasetLifecycleStatus.METADATA_VERIFIED
            step = "Validated catalog CRS & coverage geometry; local product acquisition pending"

        self.update_dataset_status(dataset_id, new_status, processing_step=step)
        return {
            "dataset_id": dataset.id,
            "product_id": dataset.product_id,
            "crs_valid": crs_valid,
            "crs": dataset.coordinate_reference_system,
            "coverage_check": coverage_result,
            "license_status": dataset.license.value,
            "local_file_present": has_local_file,
            "verification": dataset.verification.model_dump(),
            "validation_passed": crs_valid and coverage_result["is_covered"],
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
            elif check_url.lower().endswith(".lbl"):
                lbl_path = self.raw_data_dir / f"{dataset.id}_remote.lbl"
                lbl_path.parent.mkdir(parents=True, exist_ok=True)
                lbl_path.write_bytes(resp.content)
                AcquisitionService._apply_pds3_label_verification(dataset, lbl_path)
                dataset.local_label_path = str(lbl_path.relative_to(self.catalog_storage_dir.parent.parent))
                if dataset.status == DatasetLifecycleStatus.DISCOVERED:
                    dataset.status = DatasetLifecycleStatus.METADATA_VERIFIED

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

    def _persist_dataset(self, dataset: Dataset) -> None:
        file_path = self.catalog_storage_dir / f"{dataset.id}.json"
        file_path.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")

    def _load_persisted_catalog(self) -> None:
        for json_file in self.catalog_storage_dir.glob("*.json"):
            try:
                ds = Dataset.model_validate_json(json_file.read_text(encoding="utf-8"))
                is_wmts = "{" in (ds.original_product_url or "")
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
                self._datasets[ds.id] = ds
            except Exception as exc:
                print(f"Failed to read catalog entry from {json_file}: {exc}")
