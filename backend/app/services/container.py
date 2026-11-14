"""
MARSCOPE System Service Container
Martian Surface Intelligence & Exploration System

Initializes and provides singleton access to catalog, acquisition, target,
layer, localization, and destination services.
"""

from pathlib import Path
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.catalog import DatasetCatalogService
from app.science.target_registry import TargetRegistryService
from app.services.destination_service import DestinationEvaluationService
from app.services.layer_service import LayerCatalogService
from app.services.localization_service import LocalizationService

# Project root path resolution
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
DATASETS_DIR = REPO_ROOT / "datasets"

CATALOG_DIR = DATASETS_DIR / "catalog"
MANIFESTS_DIR = DATASETS_DIR / "manifests"
RAW_DIR = DATASETS_DIR / "raw"
PROCESSED_DIR = DATASETS_DIR / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Initialize singletons
catalog_service = DatasetCatalogService(catalog_storage_dir=CATALOG_DIR, raw_data_dir=RAW_DIR)
acquisition_service = AcquisitionService(raw_data_dir=RAW_DIR, manifests_dir=MANIFESTS_DIR)
target_registry = TargetRegistryService()
layer_service = LayerCatalogService(
    catalog_service=catalog_service,
    processed_dir=PROCESSED_DIR,
    raw_dir=RAW_DIR,
)
localization_service = LocalizationService()
destination_service = DestinationEvaluationService(
    catalog_service=catalog_service,
    processed_dir=PROCESSED_DIR,
)
