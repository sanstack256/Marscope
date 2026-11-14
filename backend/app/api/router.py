"""
Central API Router Registry
Martian Surface Intelligence & Exploration System
"""

from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.datasets import router as datasets_router
from app.api.layers import router as layers_router
from app.api.terrain import router as terrain_router
from app.api.observations import router as observations_router
from app.api.targets import router as targets_router
from app.api.sources import router as sources_router
from app.api.physics import router as physics_router

api_router = APIRouter(prefix="/api")

# Register subsystem routers
api_router.include_router(health_router)
api_router.include_router(datasets_router)
api_router.include_router(layers_router)
api_router.include_router(terrain_router)
api_router.include_router(observations_router)
api_router.include_router(targets_router)
api_router.include_router(sources_router)
api_router.include_router(physics_router)
