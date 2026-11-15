"""
MARSCOPE Human Mobility Intelligence API Endpoints
Martian Surface Intelligence & Exploration System

Exposes verified terrain characterization, 5-state coverage intelligence,
elevation gain/loss profiles, configurable mobility scenarios, and spatially
explicit traversal cost surfaces.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.core.security import validate_identifier

from app.mobility.schemas import (
    CostSurfaceSummary,
    CoverageIntelligenceResponse,
    ElevationProfileRequest,
    ElevationProfileResponse,
    MobilityEngineStatusResponse,
    MobilityEvaluationRequest,
    MobilityEvaluationResponse,
    MobilityScenario,
    MobilityScenarioCreateRequest,
    TerrainFeaturesWindowResponse,
)
from app.services.container import mobility_service
from app.terrain.processor import InsufficientDEMCoverageError

router = APIRouter(prefix="/mobility", tags=["Human Mobility Intelligence Engine"])


def _validate_bounds_query(
    min_lat: Optional[float],
    max_lat: Optional[float],
    min_lon: Optional[float],
    max_lon: Optional[float],
) -> dict:
    if any(v is None for v in (min_lat, max_lat, min_lon, max_lon)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Explicit min_lat, max_lat, min_lon, and max_lon parameters are required (hardcoded region defaults are prohibited).",
        )
    if float(min_lat) >= float(max_lat):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"min_lat ({min_lat}) must be strictly less than max_lat ({max_lat}).",
        )
    if float(min_lon) == float(max_lon):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"min_lon ({min_lon}) and max_lon ({max_lon}) must not be equal.",
        )
    return {
        "min_lat": float(min_lat),
        "max_lat": float(max_lat),
        "min_lon": float(min_lon),
        "max_lon": float(max_lon),
    }


@router.get("/status", response_model=MobilityEngineStatusResponse)
async def get_mobility_status() -> MobilityEngineStatusResponse:
    """
    Retrieve Human Mobility Intelligence Engine status, DEM inventory,
    resolution suitability assessments, and scientific constraints.
    """
    return mobility_service.get_status()


@router.get("/terrain/features", response_model=TerrainFeaturesWindowResponse)
async def get_windowed_terrain_features(
    dataset_id: str = Query(..., description="Source DEM dataset ID (explicitly required)"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit minimum latitude (deg)"),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit maximum latitude (deg)"),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit minimum longitude (deg)"),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit maximum longitude (deg)"),
    roughness_radius_meters: Optional[float] = Query(
        None,
        gt=0.0,
        description="Optional physical neighborhood radius (m) for TRI roughness calculation",
    ),
) -> TerrainFeaturesWindowResponse:
    """
    Extract windowed physical terrain features (elevation, Horn 3x3 slope,
    compass aspect, and metric TRI roughness) without silently expanding
    the requested bounding box or substituting default regions.
    """
    validate_identifier(dataset_id, field_name="dataset_id")
    bounds = _validate_bounds_query(min_lat, max_lat, min_lon, max_lon)
    try:
        return mobility_service.get_terrain_features(
            dataset_id=dataset_id,
            bounds=bounds,
            roughness_radius_meters=roughness_radius_meters,
        )
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except InsufficientDEMCoverageError as ice:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ice.report.model_dump(),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get("/coverage", response_model=CoverageIntelligenceResponse)
async def get_region_coverage_intelligence(
    dataset_id: str = Query(..., description="Source DEM dataset ID (explicitly required)"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit minimum latitude (deg)"),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit maximum latitude (deg)"),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit minimum longitude (deg)"),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit maximum longitude (deg)"),
    roughness_radius_meters: Optional[float] = Query(
        None,
        gt=0.0,
        description="Optional physical neighborhood radius (m) for TRI roughness",
    ),
) -> CoverageIntelligenceResponse:
    """
    Evaluate 5-state spatial coverage and unknown-data intelligence for a
    study region without expanding requested bounds or substituting defaults.
    """
    validate_identifier(dataset_id, field_name="dataset_id")
    bounds = _validate_bounds_query(min_lat, max_lat, min_lon, max_lon)
    try:
        return mobility_service.get_coverage_intelligence(
            dataset_id=dataset_id,
            bounds=bounds,
            roughness_radius_meters=roughness_radius_meters,
        )
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/scenarios", response_model=MobilityScenario, status_code=status.HTTP_201_CREATED)
async def create_mobility_scenario(req: MobilityScenarioCreateRequest) -> MobilityScenario:
    """
    Register an explicit, provenance-tagged MobilityScenario.
    Never injects arbitrary default walking speeds, slope limits, or physiology models.
    """
    return mobility_service.create_scenario(req)


@router.get("/scenarios", response_model=List[MobilityScenario])
async def list_mobility_scenarios() -> List[MobilityScenario]:
    """List all registered MobilityScenario configurations."""
    return mobility_service.list_scenarios()


@router.get("/scenarios/{scenario_id}", response_model=MobilityScenario)
async def get_mobility_scenario(scenario_id: str) -> MobilityScenario:
    """Retrieve a specific MobilityScenario by ID."""
    try:
        return mobility_service.get_scenario(scenario_id)
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))


@router.post("/elevation-profile", response_model=ElevationProfileResponse)
async def compute_elevation_profile_endpoint(req: ElevationProfileRequest) -> ElevationProfileResponse:
    """
    Compute a spatially explicit elevation profile and cumulative positive/negative
    elevation change along two positions or a user-supplied sequence of waypoints.
    Does NOT perform route optimization.
    """
    try:
        return mobility_service.compute_profile(req)
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))


@router.post("/evaluate", response_model=MobilityEvaluationResponse)
async def evaluate_mobility_endpoint(req: MobilityEvaluationRequest) -> MobilityEvaluationResponse:
    """
    Evaluate physical terrain measurements and scenario-dependent traversal estimates
    at a point, along a waypoint transect, or across a study bounding box.
    Strictly separates source-derived physical measurements from scenario estimates.
    """
    try:
        return mobility_service.evaluate_mobility(req)
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except InsufficientDEMCoverageError as ice:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ice.report.model_dump(),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))


@router.get("/cost-surface/metadata", response_model=CostSurfaceSummary)
async def get_cost_surface_metadata(
    dataset_id: str = Query(..., description="Source DEM dataset ID (explicitly required)"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit minimum latitude (deg)"),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Explicit maximum latitude (deg)"),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit minimum longitude (deg)"),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0, description="Explicit maximum longitude (deg)"),
    scenario_id: Optional[str] = Query(None, description="Optional registered MobilityScenario ID"),
    reference_walking_speed_m_per_s: Optional[float] = Query(
        None,
        gt=0.0,
        le=10.0,
        description="Optional explicit walking speed in m/s (if scenario_id is not supplied)",
    ),
    planning_max_slope_deg: Optional[float] = Query(
        None,
        gt=0.0,
        lt=90.0,
        description="Optional user-configured planning maximum slope threshold in degrees",
    ),
    planning_max_roughness_m: Optional[float] = Query(
        None,
        gt=0.0,
        description="Optional user-configured planning maximum TRI roughness threshold in meters",
    ),
) -> CostSurfaceSummary:
    """
    Generate and inspect a spatially explicit TraversalCostSurface over a study region.
    Preserves null traversal cost on unknown/no-data cells and never emits safe/unsafe labels.
    """
    validate_identifier(dataset_id, field_name="dataset_id")
    bounds = _validate_bounds_query(min_lat, max_lat, min_lon, max_lon)
    try:
        return mobility_service.get_cost_surface_metadata(
            dataset_id=dataset_id,
            bounds=bounds,
            scenario_id=scenario_id,
            reference_walking_speed_m_per_s=reference_walking_speed_m_per_s,
            planning_max_slope_deg=planning_max_slope_deg,
            planning_max_roughness_m=planning_max_roughness_m,
        )
    except LookupError as le:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(le))
    except FileNotFoundError as fe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(fe))
    except InsufficientDEMCoverageError as ice:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ice.report.model_dump(),
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
