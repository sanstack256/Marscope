"""
MARSCOPE Localization Acquisition Endpoints
Martian Surface Intelligence & Exploration System

Exposes astronaut/mission positioning status without browser GPS spoofing
or fabricated default coordinates. Never caches live position indefinitely.
"""

from fastapi import APIRouter, HTTPException, Response
from app.schemas.localization import (
    LocalizationStatusResponse,
    ManualPositionRequest,
    PositionRecord,
)
from app.services.container import destination_service, localization_service

router = APIRouter(prefix="/localization", tags=["Mission Localization"])


@router.get("/status", response_model=LocalizationStatusResponse)
async def get_localization_status(response: Response) -> LocalizationStatusResponse:
    """
    Return current localization provider readiness and active position (if manually selected
    or fed by an authorized mission adapter). Live position is never stale-cached.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return localization_service.get_status()


@router.post("/manual", response_model=PositionRecord)
async def set_manual_position(request: ManualPositionRequest, response: Response) -> PositionRecord:
    """
    Record an explicit operator-selected position in Mars IAU2000 coordinates.
    Elevation is sampled ONLY if a validated local DEM covers the coordinate.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    try:
        terrain_pt = destination_service.sample_processed_terrain_point(
            request.latitude,
            request.longitude,
            crs=request.crs,
            latitude_convention=request.latitude_convention,
            longitude_direction=request.longitude_direction,
        )
        sampled_elev = terrain_pt.elevation_m if terrain_pt.available else None
        return localization_service.set_manual_position(request, sampled_elevation_m=sampled_elev)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.delete("", response_model=LocalizationStatusResponse)
async def clear_position(response: Response) -> LocalizationStatusResponse:
    """Clear any active manual coordinate selection."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return localization_service.clear_position()
