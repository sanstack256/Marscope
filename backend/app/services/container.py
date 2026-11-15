"""
MARSCOPE System Service Container
Martian Surface Intelligence & Exploration System

Initializes and provides singleton access to catalog, acquisition, target,
layer, localization, composition spatial index, coordinate association, and destination services.
"""

from pathlib import Path
import os
from app.core.config import settings
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.bootstrap import seed_catalog_metadata_if_empty
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
from app.ingestion.imagery import ImageryArchiveService
from app.science.investigation.service import ScienceInvestigationService
from app.geospatial.footprints import SpatialFootprintIndex
from app.geospatial.services import (
    RoverSpatialAssociationService,
    SpatialCoverageService,
    SpatialRegistrationService,
)
from app.geospatial.spatial_delivery import SpatialDeliveryService
from app.terrain.morphology import GeologicalMorphologyService
from app.services.demo_service import DemoService

# Project root path resolution
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent
_configured_datasets_dir = (
    settings.MARSCOPE_DATASETS_DIR or os.getenv("MARSCOPE_DATASETS_DIR") or ""
).strip()
DATASETS_DIR = Path(_configured_datasets_dir).resolve() if _configured_datasets_dir else (REPO_ROOT / "datasets")
seed_catalog_metadata_if_empty(DATASETS_DIR)

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
imagery_service = ImageryArchiveService(
    CATALOG_DIR / "imagery_products" / "catalog.json",
    raw_dir=RAW_DIR,
)
science_investigation_service = ScienceInvestigationService(
    catalog_service=catalog_service,
    target_registry=target_registry,
    composition_search_service=composition_search_service,
    composition_index=composition_index,
    routing_service=routing_service,
    evidence_service=evidence_intelligence_service,
    processed_dir=PROCESSED_DIR,
    imagery_service=imagery_service,
)

# Prompt 19 Multi-Mission Spatial Intelligence singletons
footprint_index_service = SpatialFootprintIndex(
    catalog_service=catalog_service,
    dataset_root_dir=DATASETS_DIR,
)
spatial_registration_service = SpatialRegistrationService(
    catalog_service=catalog_service,
    footprint_index=footprint_index_service,
    dataset_root_dir=DATASETS_DIR,
)
spatial_coverage_service = SpatialCoverageService(
    catalog_service=catalog_service,
    footprint_index=footprint_index_service,
    dataset_root_dir=DATASETS_DIR,
    composition_index=composition_index,
)
morphology_service = GeologicalMorphologyService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
)
spatial_delivery_service = SpatialDeliveryService(
    catalog_service=catalog_service,
    raw_dir=RAW_DIR,
)
spatial_delivery_service.attach_mesh_service(terrain_mesh_service)
rover_association_service = RoverSpatialAssociationService(
    catalog_service=catalog_service,
    composition_index=composition_index,
)

# Prompt 21 End-to-End Bidirectional Service Integration
science_investigation_service.attach_integration_services(
    eva_operations_service=eva_operations_service,
    morphology_service=morphology_service,
    spatial_coverage_service=spatial_coverage_service,
    spatial_registration_service=spatial_registration_service,
)
eva_operations_service.attach_science_service(science_investigation_service)

# Prompt 1 Multi-Astronaut Mission Foundation Singletons
from app.db.database import MissionDatabase
from app.services.realtime_hub import MissionRealtimeHub
from app.services.mission_event_service import MissionEventService
from app.services.auth_service import AuthService
from app.services.position_service import CrewPositionService
from app.services.mission_service import MissionService
from app.services.sos_service import SosService
from app.services.field_observation_service import FieldObservationService
from app.services.landing_site_service import LandingSiteService
from app.services.navigation_service import NavigationService

PRIVATE_ATTACHMENTS_DIR = DATASETS_DIR / "private_attachments"
PRIVATE_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

mission_db = MissionDatabase(default_sqlite_path=DATASETS_DIR / "index" / "marscope_mission.sqlite")
mission_realtime_hub = MissionRealtimeHub()
mission_event_service = MissionEventService(mission_db)
auth_service = AuthService(mission_db)
position_service = CrewPositionService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    destination_service=destination_service,
)
mission_service = MissionService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    position_service=position_service,
)
sos_service = SosService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    position_service=position_service,
    private_attachments_dir=PRIVATE_ATTACHMENTS_DIR,
)
field_observation_service = FieldObservationService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    destination_service=destination_service,
)
landing_site_service = LandingSiteService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    catalog_service=catalog_service,
    destination_service=destination_service,
    processed_dir=PROCESSED_DIR,
)
navigation_service = NavigationService(
    db=mission_db,
    event_service=mission_event_service,
    realtime_hub=mission_realtime_hub,
    position_service=position_service,
    routing_service=routing_service,
)
demo_service = DemoService(
    db=mission_db,
    event_service=mission_event_service,
    credentials_file=INDEX_DIR / ".demo_credentials.json",
    processed_dir=PROCESSED_DIR,
)
