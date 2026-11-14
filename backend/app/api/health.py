"""
Health Endpoint Route
"""

from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.schemas.health import HealthResponse, EngineStatus

router = APIRouter(tags=["Health & Status"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """
    Get system health status, active environment, and subsystem engine readiness.
    """
    return HealthResponse(
        status="healthy",
        system="MARSCOPE Martian Surface Intelligence Engine",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp_utc=datetime.now(timezone.utc),
        engines=EngineStatus(
            physics="ready",
            geospatial="ready",
            terrain="ready",
            routing="ready",
        ),
    )
