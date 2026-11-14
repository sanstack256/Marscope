"""
MARSCOPE System Service Container
Martian Surface Intelligence & Exploration System

Initializes and provides singleton access to the catalog, acquisition, and target services.
"""

from pathlib import Path
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.acquisition import AcquisitionService
from app.science.target_registry import TargetRegistryService

# Project root path resolution
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
DATASETS_DIR = REPO_ROOT / "datasets"

CATALOG_DIR = DATASETS_DIR / "catalog"
MANIFESTS_DIR = DATASETS_DIR / "manifests"
RAW_DIR = DATASETS_DIR / "raw"
PROCESSED_DIR = DATASETS_DIR / "processed"

# Initialize singletons
catalog_service = DatasetCatalogService(catalog_storage_dir=CATALOG_DIR)
acquisition_service = AcquisitionService(raw_data_dir=RAW_DIR, manifests_dir=MANIFESTS_DIR)
target_registry = TargetRegistryService()
