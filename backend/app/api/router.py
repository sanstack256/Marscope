"""
Central API Router Registry
Martian Surface Intelligence & Exploration System

Aggregates all domain sub-routers under the versioned /api namespace.
"""

from fastapi import APIRouter
from app.api import (
    datasets,
    destinations,
    health,
    layers,
    localization,
    observations,
    physics,
    sources,
    targets,
    terrain,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(terrain.router)
api_router.include_router(layers.router)
api_router.include_router(observations.router)
api_router.include_router(targets.router)
api_router.include_router(sources.router)
api_router.include_router(physics.router)
api_router.include_router(localization.router)
api_router.include_router(destinations.router)
