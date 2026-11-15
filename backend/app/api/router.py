"""
Central API Router Registry
Martian Surface Intelligence & Exploration System

Aggregates all domain sub-routers under the versioned /api namespace.
"""

from fastapi import APIRouter
from app.api import (
    auth,
    composition,
    datasets,
    demo,
    destinations,
    eva_operations,
    evidence_intelligence,
    field_observations,
    health,
    imagery,
    landing_site,
    layers,
    localization,
    missions,
    mobility,
    navigation,
    observations,
    physics,
    routing,
    sos,
    sources,
    spatial_intelligence,
    targets,
    terrain,
    terrain_mesh,
    terrain_uncertainty,
    science_investigation,
    tracking,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(demo.router)
api_router.include_router(field_observations.router)
api_router.include_router(landing_site.router)
api_router.include_router(missions.router)
api_router.include_router(navigation.router)
api_router.include_router(sos.router)
api_router.include_router(imagery.router)
api_router.include_router(datasets.router)
api_router.include_router(terrain.router)
api_router.include_router(terrain_mesh.router)
api_router.include_router(mobility.router)
api_router.include_router(routing.router)
api_router.include_router(layers.router)
api_router.include_router(observations.router)
api_router.include_router(composition.router)
api_router.include_router(targets.router)
api_router.include_router(sources.router)
api_router.include_router(physics.router)
api_router.include_router(localization.router)
api_router.include_router(tracking.router)
api_router.include_router(destinations.router)
api_router.include_router(evidence_intelligence.router)
api_router.include_router(eva_operations.router)
api_router.include_router(terrain_uncertainty.router)
api_router.include_router(science_investigation.router)
api_router.include_router(spatial_intelligence.router)
