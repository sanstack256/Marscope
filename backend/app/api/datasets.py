"""
MARSCOPE Dataset Ingestion & Discovery Endpoints
Martian Surface Intelligence & Exploration System
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, DatasetManifest
from app.services.container import PROCESSED_DIR, RAW_DIR, acquisition_service, catalog_service
from app.terrain.processor import DEMProcessingService

router = APIRouter(prefix="/datasets", tags=["Dataset Catalog & Acquisition"])


@router.get("", response_model=List[Dataset])
async def list_datasets(
    mission: Optional[str] = Query(None, description="Filter by mission name"),
    instrument: Optional[str] = Query(None, description="Filter by instrument name"),
    product_type: Optional[str] = Query(None, description="Filter by product type"),
    status: Optional[DatasetLifecycleStatus] = Query(None, description="Filter by lifecycle status"),
) -> List[Dataset]:
    """List registered planetary datasets with optional faceted filtering."""
    return catalog_service.list_datasets(
        mission=mission,
        instrument=instrument,
        product_type=product_type,
        status=status,
    )


@router.post("/discover", response_model=List[Dataset])
async def discover_datasets() -> List[Dataset]:
    """Poll official NASA/ESA source adapters to discover planetary products."""
    return catalog_service.discover_all_sources()


@router.get("/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: str) -> Dataset:
    """Retrieve full metadata, verification evidence, and processing history for a dataset."""
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in MARSCOPE catalog.",
        )
    return dataset


@router.post("/{dataset_id}/verify-remote", response_model=Dataset)
async def verify_dataset_remote(dataset_id: str) -> Dataset:
    """Verify remote archive availability and label/WMTS capabilities live."""
    try:
        return await catalog_service.verify_remote_capabilities(dataset_id)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/{dataset_id}/download", response_model=DatasetManifest)
async def download_dataset(dataset_id: str) -> DatasetManifest:
    """
    Download a verified scientific product from its official archive URL, verifying SHA-256 hash
    and fetching companion PDS3 label when present.
    """
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")

    try:
        manifest = await acquisition_service.download_product(dataset)
        catalog_service.register_dataset(dataset)
        return manifest
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        catalog_service.update_dataset_status(
            dataset_id,
            DatasetLifecycleStatus.FAILED_DOWNLOAD,
            failure_reason=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to acquire product from archive: {e}",
        )


@router.post("/{dataset_id}/validate")
async def validate_dataset(dataset_id: str) -> Dict[str, Any]:
    """Validate dataset CRS, study-area overlap, and local integrity honestly."""
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")

    gale_bounds = {
        "min_lat": -5.5,
        "max_lat": -4.3,
        "min_lon": 137.2,
        "max_lon": 138.0,
    }
    return catalog_service.validate_dataset_integrity(dataset_id, gale_bounds)


@router.post("/{dataset_id}/process")
async def process_dataset(
    dataset_id: str,
    roughness_radius_meters: Optional[float] = Query(None, gt=0.0, description="Physical TRI neighborhood radius in meters"),
) -> Dict[str, Any]:
    """
    Process a locally downloaded DEM dataset into clipped GeoTIFF and terrain derivatives
    (slope, aspect, metric TRI) with a verifiable processing manifest.
    """
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")
    if "DEM" not in dataset.product_type.upper() and "ELEVATION" not in dataset.product_type.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset '{dataset_id}' (type '{dataset.product_type}') is not a DEM raster product.",
        )

    gale_bounds = {
        "min_lat": -5.5,
        "max_lat": -4.3,
        "min_lon": 137.2,
        "max_lon": 138.0,
    }
    try:
        manifest = DEMProcessingService.process_dem_dataset(
            dataset=dataset,
            raw_dir=RAW_DIR,
            processed_dir=PROCESSED_DIR,
            study_bounds=gale_bounds,
            roughness_radius_meters=roughness_radius_meters,
        )
        catalog_service.register_dataset(dataset)
        return manifest
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except Exception as exc:
        catalog_service.update_dataset_status(
            dataset_id,
            DatasetLifecycleStatus.FAILED_PROCESSING,
            failure_reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
