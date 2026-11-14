"""
MARSCOPE System Service Container
Martian Surface Intelligence & Exploration System

Initializes and provides singleton access to catalog, acquisition, target,
layer, localization, composition spatial index, coordinate association, and destination services.
"""

from pathlib import Path
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.catalog import DatasetCatalogService
from app.mobility.service import HumanMobilityService
from app.routing.service import ScienceAwareRoutingService
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.search import CompositionSearchService
from app.science.coordinate_association import CoordinateAssociationService
from app.science.target_registry import TargetRegistryService
from app.services.destination_service import DestinationEvaluationService
from app.services.layer_service import LayerCatalogService
from app.services.localization_service import LocalizationService
from app.services.tracking_service import TrackingService
from app.evidence_intelligence.report import EvidenceIntelligenceService
from app.eva_operations.mission import EvaOperationsService
from app.terrain.mesh import TerrainMeshService
from app.terrain_uncertainty.service import TerrainUncertaintyService

# Project root path resolution
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
DATASETS_DIR = REPO_ROOT / "datasets"

CATALOG_DIR = DATASETS_DIR / "catalog"
MANIFESTS_DIR = DATASETS_DIR / "manifests"
RAW_DIR = DATASETS_DIR / "raw"
PROCESSED_DIR = DATASETS_DIR / "processed"
INDEX_DIR = DATASETS_DIR / "index"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
INDEX_DIR.mkdir(parents=True, exist_ok=True)

COMPOSITION_INDEX_DB = INDEX_DIR / "composition_index.sqlite"

# Initialize coordinate association from JPL MSL waypoints if locally acquired
_wp_file = next(iter(sorted(RAW_DIR.glob("*waypoints*.json"))), None)
coordinate_association_service = CoordinateAssociationService(waypoints_path=_wp_file)

# Initialize singletons
catalog_service = DatasetCatalogService(catalog_storage_dir=CATALOG_DIR, raw_data_dir=RAW_DIR)
acquisition_service = AcquisitionService(raw_data_dir=RAW_DIR, manifests_dir=MANIFESTS_DIR)
composition_index = CompositionSpatialIndex(db_path=COMPOSITION_INDEX_DB)
composition_search_service = CompositionSearchService(index=composition_index)
target_registry = TargetRegistryService(composition_index=composition_index)
layer_service = LayerCatalogService(
    catalog_service=catalog_service,
    processed_dir=PROCESSED_DIR,
    raw_dir=RAW_DIR,
)
localization_service = LocalizationService()
destination_service = DestinationEvaluationService(
    catalog_service=catalog_service,
    processed_dir=PROCESSED_DIR,
    composition_search_service=composition_search_service,
    localization_service=localization_service,
)
mobility_service = HumanMobilityService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
)
terrain_uncertainty_service = TerrainUncertaintyService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
)
terrain_mesh_service = TerrainMeshService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
    uncertainty_service=terrain_uncertainty_service,
)
routing_service = ScienceAwareRoutingService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
    target_registry=target_registry,
    composition_search=composition_search_service,
)
tracking_service = TrackingService(routing_service=routing_service)
evidence_intelligence_service = EvidenceIntelligenceService(
    catalog_service=catalog_service,
    routing_service=routing_service,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
)
eva_operations_service = EvaOperationsService(
    routing_service=routing_service,
    evidence_service=evidence_intelligence_service,
    processed_dir=PROCESSED_DIR,
)
