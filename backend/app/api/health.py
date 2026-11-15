"""
Enhanced System Health Check Endpoint
Martian Surface Intelligence & Exploration System

Verifies actual subsystem initialization and dependency health.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query
from app.core.config import settings
from app.core.readiness import evaluate_system_readiness
from app.schemas.health import HealthResponse, EngineStatus
from app.physics.registry.parameters import list_parameters
from app.services.container import (
    catalog_service,
    composition_index,
    eva_operations_service,
    morphology_service,
    science_investigation_service,
    target_registry,
)

router = APIRouter(tags=["Health & Status"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """
    Get system health status, runtime environment, and verified subsystem readiness.
    """
    # 1. Physics Engine Check: Check parameter registry
    params = list_parameters()
    physics_status = "ready" if len(params) >= 8 else "degraded"

    # 2. Geospatial Engine Check: Verify rasterio and pyproj imports
    try:
        import rasterio
        import pyproj
        import shapely
        geospatial_status = "ready"
    except Exception as e:
        geospatial_status = f"unavailable ({e})"

    # 3. Terrain Engine Check: Verify scipy convolution
    try:
        from scipy.ndimage import convolve
        terrain_status = "ready"
    except Exception as e:
        terrain_status = f"unavailable ({e})"

    # 4. Catalog / Routing Check (verify whether at least one processed DEM is genuinely ready)
    try:
        from app.terrain.processor import DEMProcessingService

        has_ready_dem = any(
            getattr(ds, "processed_file_path", None)
            and catalog_service._resolve_existing_path(ds.processed_file_path) is not None
            and not getattr(ds, "failure_reason", None)
            for ds in catalog_service.list_datasets()
        )
        routing_status = "ready" if has_ready_dem else "ready_no_local_dem"
    except Exception as e:
        routing_status = f"degraded ({e})"

    return HealthResponse(
        status="healthy" if geospatial_status == "ready" and physics_status == "ready" else "degraded",
        system="MARSCOPE Martian Surface Intelligence Engine",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp_utc=datetime.now(timezone.utc),
        engines=EngineStatus(
            physics=physics_status,
            geospatial=geospatial_status,
            terrain=terrain_status,
            routing=routing_status,
        ),
    )


@router.get("/health/readiness")
async def get_system_readiness(
    verify_checksums: bool = Query(
        False,
        description="Recompute SHA-256 checksums for all local raw/processed assets during inspection.",
    ),
    dataset_id: Optional[str] = Query(
        None,
        description="Optional dataset_id to check contextual readiness for terrain/routing execution.",
    ),
    question_id: Optional[str] = Query(
        None,
        description="Optional science question_id to check contextual investigation readiness.",
    ),
) -> Dict[str, Any]:
    """Return Prompt 22 Section 12 4-pillar operational & data readiness audit."""
    return evaluate_system_readiness(
        catalog_service=catalog_service,
        composition_index=composition_index,
        science_investigation_service=science_investigation_service,
        eva_operations_service=eva_operations_service,
        morphology_service=morphology_service,
        target_registry=target_registry,
        settings=settings,
        verify_checksums=verify_checksums,
        dataset_id=dataset_id,
        question_id=question_id,
    )
