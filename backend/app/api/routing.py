"""
MARSCOPE Science-Aware Route Computation & Turn-by-Turn Navigation Endpoints
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.routing.graph import RoutePlanningError
from app.routing.models import OBJECTIVE_POLICIES, ROUTE_OBJECTIVES_VERSION
from app.routing.schemas import (
    NavigationInstruction,
    RobustRouteCompareRequest,
    RobustRouteCompareResponse,
    RouteCompareRequest,
    RouteCompareResponse,
    RouteComputeRequest,
    RouteComputeResponse,
    RouteStatusResponse,
    RouteValidationResponse,
    RouteVertex,
)
from app.services.container import routing_service
from app.terrain_uncertainty.sensitivity import RouteSensitivityReport

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/status", response_model=RouteStatusResponse)
async def get_routing_status() -> RouteStatusResponse:
    return routing_service.get_status()


@router.get("/objectives")
async def list_routing_objectives() -> Dict[str, Any]:
    """Return all seven explicit Prompt 16 RouteObjective policies and cost weights."""
    return {
        "policy_version": ROUTE_OBJECTIVES_VERSION,
        "objectives": [
            {
                "objective": obj.value,
                "legacy_mode": pol.mode.value,
                "label": pol.label,
                "description": pol.description,
                "effective_slope_limit_factor": pol.effective_slope_limit_factor,
                "slope_weight": pol.slope_weight,
                "uphill_weight": pol.uphill_weight,
                "downhill_weight": pol.downhill_weight,
                "roughness_weight": pol.roughness_weight,
                "uncertainty_weight": pol.uncertainty_weight,
                "nodata_proximity_weight": pol.nodata_proximity_weight,
                "science_corridor_bonus": pol.science_corridor_bonus,
                "min_cost_multiplier": pol.min_cost_multiplier,
            }
            for obj, pol in OBJECTIVE_POLICIES.items()
        ],
    }


@router.post("/validate", response_model=RouteValidationResponse)
async def validate_routing_inputs(req: RouteComputeRequest) -> RouteValidationResponse:
    try:
        return routing_service.validate_inputs(req)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.post("/compute", response_model=RouteComputeResponse)
async def compute_route(req: RouteComputeRequest) -> RouteComputeResponse:
    try:
        return routing_service.compute_route(req)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.post("/compare", response_model=RouteCompareResponse)
async def compare_routes(req: RouteCompareRequest) -> RouteCompareResponse:
    try:
        return routing_service.compare_routes(req)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.post("/robust-compare", response_model=RobustRouteCompareResponse)
async def compare_robust_routes(req: RobustRouteCompareRequest) -> RobustRouteCompareResponse:
    """Generate genuinely distinct alternative routes with return check, cost decomposition, and sensitivity."""
    try:
        return routing_service.compute_robust_comparison(req)
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.get("/{route_id}/sensitivity", response_model=RouteSensitivityReport)
async def get_route_sensitivity(route_id: str) -> RouteSensitivityReport:
    """Evaluate deterministic scenario perturbation stability for a previously computed route."""
    try:
        return routing_service.evaluate_route_sensitivity(route_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoutePlanningError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


@router.get("/{route_id}", response_model=RouteComputeResponse)
async def get_computed_route(route_id: str) -> RouteComputeResponse:
    try:
        return routing_service.get_route(route_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{route_id}/instructions", response_model=List[NavigationInstruction])
async def get_route_instructions(route_id: str) -> List[NavigationInstruction]:
    try:
        return routing_service.get_route(route_id).instructions
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{route_id}/profile", response_model=List[RouteVertex])
async def get_route_profile(route_id: str) -> List[RouteVertex]:
    try:
        return routing_service.get_route(route_id).vertices
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{route_id}/geojson")
async def export_route_geojson(route_id: str) -> Dict[str, Any]:
    try:
        return routing_service.export_geojson(route_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
