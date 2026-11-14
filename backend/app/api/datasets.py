"""
MARSCOPE Dataset Ingestion & Discovery Endpoints
Martian Surface Intelligence & Exploration System
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status
from app.schemas.dataset import Dataset, DatasetManifest, DatasetLifecycleStatus
from app.services.container import catalog_service, acquisition_service

router = APIRouter(prefix="/datasets", tags=["Dataset Catalog & Acquisition"])


@router.get("", response_model=List[Dataset])
async def list_datasets(
    mission: Optional[str] = Query(None, description="Filter by mission name"),
    instrument: Optional[str] = Query(None, description="Filter by instrument name"),
    product_type: Optional[str] = Query(None, description="Filter by product type (DEM, SPECTRUM, etc.)"),
    status: Optional[DatasetLifecycleStatus] = Query(None, description="Filter by lifecycle status"),
) -> List[Dataset]:
    """
    List registered planetary datasets with optional faceted filtering.
    """
    return catalog_service.list_datasets(
        mission=mission,
        instrument=instrument,
        product_type=product_type,
        status=status,
    )


@router.post("/discover", response_model=List[Dataset])
async def discover_datasets() -> List[Dataset]:
    """
    Poll official NASA/ESA archives (PDS MOLA, MSL Curiosity, Mars Trek) to discover verified planetary products.
    """
    return catalog_service.discover_all_sources()


@router.get("/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: str) -> Dataset:
    """
    Retrieve full metadata, provenance, and processing history for a specific registered dataset.
    """
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found in MARSCOPE catalog.",
        )
    return dataset


@router.post("/{dataset_id}/download", response_model=DatasetManifest)
async def download_dataset(dataset_id: str) -> DatasetManifest:
    """
    Download a verified scientific product from its official archive URL, verifying integrity and SHA-256 hash.
    """
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")

    try:
        manifest = await acquisition_service.download_product(dataset)
        catalog_service.register_dataset(dataset)
        return manifest
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
    """
    Validate product coordinate reference system, integrity, and spatial coverage against the Gale Crater study area.
    """
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")

    gale_bounds = {
        "min_lat": -5.5,
        "max_lat": -4.3,
        "min_lon": 137.2,
        "max_lon": 138.0,
    }

    coverage_result = catalog_service.check_study_area_coverage(dataset_id, gale_bounds)

    # Check CRS
    from app.geospatial.crs import validate_mars_crs
    crs_valid = validate_mars_crs(dataset.coordinate_reference_system)

    catalog_service.update_dataset_status(
        dataset_id,
        DatasetLifecycleStatus.VALIDATED if crs_valid and coverage_result["is_covered"] else DatasetLifecycleStatus.FAILED_VALIDATION,
        processing_step="Validated spatial coverage and IAU Mars CRS definition",
    )

    return {
        "dataset_id": dataset.id,
        "product_id": dataset.product_id,
        "crs_valid": crs_valid,
        "crs": dataset.coordinate_reference_system,
        "coverage_check": coverage_result,
        "license_status": dataset.license,
        "validation_passed": crs_valid and coverage_result["is_covered"],
    }
