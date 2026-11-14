"""
MARSCOPE Reusable Dataset Catalog Service
Martian Surface Intelligence & Exploration System

Maintains registered planetary products, tracks lifecycle states, and persists metadata.
"""

from pathlib import Path
from typing import Dict, List, Optional
from app.schemas.dataset import Dataset, DatasetLifecycleStatus
from app.ingestion.sources.pds_mola import PdsMolaSourceAdapter
from app.ingestion.sources.msl_curiosity import MslCuriositySourceAdapter
from app.ingestion.sources.mars_trek import MarsTrekSourceAdapter


class DatasetCatalogService:
    def __init__(self, catalog_storage_dir: Path):
        self.catalog_storage_dir = catalog_storage_dir
        self.catalog_storage_dir.mkdir(parents=True, exist_ok=True)
        self._datasets: Dict[str, Dataset] = {}
        self._sources = [
            PdsMolaSourceAdapter(),
            MslCuriositySourceAdapter(),
            MarsTrekSourceAdapter(),
        ]
        self._load_persisted_catalog()

    def discover_all_sources(self) -> List[Dataset]:
        """
        Poll all registered source adapters to discover verified planetary products.
        """
        discovered: List[Dataset] = []
        for src in self._sources:
            try:
                products = src.discover_products()
                for p in products:
                    if p.id not in self._datasets:
                        self.register_dataset(p)
                    discovered.append(self._datasets[p.id])
            except Exception as e:
                # Log error and continue with remaining adapters
                print(f"Error querying adapter {src.source_name}: {e}")
        return discovered

    def register_dataset(self, dataset: Dataset) -> Dataset:
        """
        Register a new dataset into the catalog and persist its metadata.
        """
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
        if processing_step:
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

    def _persist_dataset(self, dataset: Dataset) -> None:
        file_path = self.catalog_storage_dir / f"{dataset.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(dataset.model_dump_json(indent=2))

    def _load_persisted_catalog(self) -> None:
        for json_file in self.catalog_storage_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    ds = Dataset.model_validate_json(f.read())
                    self._datasets[ds.id] = ds
            except Exception as e:
                print(f"Failed to read catalog entry from {json_file}: {e}")
