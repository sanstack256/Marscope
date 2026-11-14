"""
MARSCOPE Data Sources & Provenance Register API
Martian Surface Intelligence & Exploration System

Generates source registry status dynamically from registered adapters and recorded verification evidence.
"""

from typing import Any, Dict, List
from fastapi import APIRouter
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
