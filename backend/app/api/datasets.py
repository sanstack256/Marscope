"""
MARSCOPE Dataset Ingestion & Discovery Endpoints
Martian Surface Intelligence & Exploration System
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, status
from app.core.security import validate_identifier, verify_operator_auth
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, DatasetManifest
from app.schemas.terrain import PlanningSlopeThreshold
from app.services.container import (
    PROCESSED_DIR,
    RAW_DIR,
    acquisition_service,
    catalog_service,
    science_investigation_service,
)
from app.terrain.processor import DEMProcessingService, InsufficientDEMCoverageError

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
async def discover_datasets(request: Request) -> List[Dataset]:
    """Poll official NASA/ESA source adapters to discover planetary products."""
    verify_operator_auth(request, fail_closed_when_unconfigured=False, operation_name="dataset_discover")
    return catalog_service.discover_all_sources()


@router.get("/{dataset_id}", response_model=Dataset)
async def get_dataset(dataset_id: str) -> Dataset:
    """Retrieve full metadata, verification evidence, and processing history for a dataset."""
    validate_identifier(dataset_id, field_name="dataset_id")
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' not found in MARSCOPE catalog.",
        )
    return dataset


@router.post("/{dataset_id}/verify-remote", response_model=Dataset)
async def verify_dataset_remote(dataset_id: str, request: Request) -> Dataset:
    """Verify remote archive availability and label/WMTS capabilities live."""
    validate_identifier(dataset_id, field_name="dataset_id")
    verify_operator_auth(request, fail_closed_when_unconfigured=False, operation_name="dataset_verify_remote")
    try:
        return await catalog_service.verify_remote_capabilities(dataset_id)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/{dataset_id}/download", response_model=DatasetManifest)
async def download_dataset(dataset_id: str, request: Request) -> DatasetManifest:
    """
    Download a verified scientific product from its official archive URL, verifying SHA-256 hash
    and fetching companion PDS3/PDS4 label when present.
    """
    validate_identifier(dataset_id, field_name="dataset_id")
    verify_operator_auth(request, fail_closed_when_unconfigured=False, operation_name="dataset_download")
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")

    url_l = (dataset.original_product_url or "").strip().lower()
    if not (url_l.startswith("https://") or url_l.startswith("http://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Dataset '{dataset_id}' lacks a valid HTTP/HTTPS archive download URL.",
        )

    try:
        manifest = await acquisition_service.download_product(dataset)
        catalog_service.register_dataset(dataset)
        science_investigation_service.propagate_external_invalidation(
            source_type="dataset_downloaded",
            description=f"Dataset '{dataset_id}' downloaded and integrity-validated; dependent campaigns marked stale for recomputation.",
            dataset_id=dataset_id,
        )
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


def _resolve_explicit_or_dataset_bounds(
    dataset: Dataset,
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
) -> Dict[str, float]:
    explicit = [min_lat, max_lat, min_lon, max_lon]
    if any(v is not None for v in explicit):
        if not all(v is not None for v in explicit):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="When specifying study bounds, all four of min_lat, max_lat, min_lon, and max_lon are required.",
            )
        bounds = {
            "min_lat": float(min_lat),
            "max_lat": float(max_lat),
            "min_lon": float(min_lon),
            "max_lon": float(max_lon),
        }
    elif dataset.coverage is not None and dataset.coverage.min_latitude < dataset.coverage.max_latitude:
        bounds = {
            "min_lat": float(dataset.coverage.min_latitude),
            "max_lat": float(dataset.coverage.max_latitude),
            "min_lon": float(dataset.coverage.min_longitude),
            "max_lon": float(dataset.coverage.max_longitude),
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Explicit study bounds are required for '{dataset.id}' because no valid coverage extent exists.",
        )
    if bounds["min_lat"] >= bounds["max_lat"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid latitude bounds: min_lat ({bounds['min_lat']}) must be < max_lat ({bounds['max_lat']}).",
        )
    return bounds


@router.post("/{dataset_id}/validate")
async def validate_dataset(
    dataset_id: str,
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
) -> Dict[str, Any]:
    """Validate dataset CRS, study-area overlap, and local integrity honestly without hardcoded fallbacks."""
    validate_identifier(dataset_id, field_name="dataset_id")
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")
    study_bounds = _resolve_explicit_or_dataset_bounds(dataset, min_lat, max_lat, min_lon, max_lon)
    return catalog_service.validate_dataset_integrity(dataset_id, study_bounds)


@router.post("/{dataset_id}/process")
async def process_dataset(
    dataset_id: str,
    request: Request,
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit minimum latitude (deg)"),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit maximum latitude (deg)"),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit minimum longitude (deg)"),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit maximum longitude (deg)"),
    roughness_radius_meters: Optional[float] = Query(None, gt=0.0, description="Physical TRI neighborhood radius in meters"),
    planning_slope_threshold_deg: Optional[float] = Query(
        None,
        gt=0.0,
        lt=90.0,
        description="Optional user-configured planning slope threshold in degrees (not a safety limit)",
    ),
    planning_threshold_label: str = Query(
        "user_configured_planning_slope_threshold",
        description="Label for optional user-configured planning slope threshold",
    ),
    planning_threshold_provenance: str = Query(
        "Explicitly configured by user for exploratory terrain summarization; not a validated suit or physiology limit.",
        description="Provenance statement for optional planning slope threshold",
    ),
    planning_threshold_version: str = Query("1.0.0", description="Version tag for optional planning slope threshold"),
) -> Dict[str, Any]:
    """
    Process a locally downloaded DEM dataset into clipped GeoTIFF and terrain derivatives
    (slope, aspect, metric TRI) with a verifiable processing manifest.
    Never silently expands requested study bounds or injects hardcoded defaults.
    """
    validate_identifier(dataset_id, field_name="dataset_id")
    verify_operator_auth(request, fail_closed_when_unconfigured=False, operation_name="dataset_process")
    dataset = catalog_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{dataset_id}' not found.")
    if "DEM" not in dataset.product_type.upper() and "ELEVATION" not in dataset.product_type.upper():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset '{dataset_id}' (type '{dataset.product_type}') is not a DEM raster product.",
        )

    study_bounds = _resolve_explicit_or_dataset_bounds(dataset, min_lat, max_lat, min_lon, max_lon)

    planning_threshold = (
        PlanningSlopeThreshold(
            threshold_deg=planning_slope_threshold_deg,
            label=planning_threshold_label,
            provenance=planning_threshold_provenance,
            version=planning_threshold_version,
            is_validated_safety_limit=False,
        )
        if planning_slope_threshold_deg is not None
        else None
    )

    try:
        manifest = DEMProcessingService.process_dem_dataset(
            dataset=dataset,
            raw_dir=RAW_DIR,
            processed_dir=PROCESSED_DIR,
            study_bounds=study_bounds,
            roughness_radius_meters=roughness_radius_meters,
            planning_threshold=planning_threshold,
        )
        catalog_service.register_dataset(dataset)
        science_investigation_service.propagate_external_invalidation(
            source_type="dataset_processed",
            description=f"Dataset '{dataset_id}' processed/reprocessed into calibrated terrain derivatives; dependent campaigns marked stale.",
            dataset_id=dataset_id,
        )
        return manifest
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except InsufficientDEMCoverageError as ice:
        catalog_service.update_dataset_status(
            dataset_id,
            DatasetLifecycleStatus.FAILED_PROCESSING,
            failure_reason=ice.report.insufficient_coverage_reason,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ice.report.model_dump(),
        )
    except Exception as exc:
        catalog_service.update_dataset_status(
            dataset_id,
            DatasetLifecycleStatus.FAILED_PROCESSING,
            failure_reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
