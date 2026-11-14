"""
MARSCOPE Data Sources & Provenance Register API
Martian Surface Intelligence & Exploration System

Generates source registry status dynamically from registered adapters and recorded verification evidence,
plus live paginated NASA PDS / ODE archive discovery endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.ingestion.sources.msl_curiosity import MslCuriositySourceAdapter
from app.services.container import catalog_service

router = APIRouter(prefix="/sources", tags=["Data Sources & Provenance"])


@router.get("")
async def list_data_sources() -> List[Dict[str, Any]]:
    """
    Returns source archive adapters with separated verification status:
    archive_availability, product_discovery, metadata_verification, license_verification,
    coverage_verification, download_verification, and processing_verification.
    """
    return catalog_service.get_source_registry_report()


@router.get("/msl/archive-query")
async def query_msl_pds_archive(
    collection: str = Query("chemcam_moc", description="chemcam_moc | chemin_rdr5 | crism_ode"),
    sol_min: Optional[int] = Query(None, ge=0),
    sol_max: Optional[int] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Query live official NASA PDS Geosciences / ODE REST archive directories with filtering,
    pagination, and explicit query-provenance recording.
    """
    adapter = MslCuriositySourceAdapter()
    try:
        return await adapter.discover_archive_products(
            collection=collection,
            sol_min=sol_min,
            sol_max=sol_max,
            page=page,
            limit=limit,
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream NASA PDS archive query failed: {exc}")
