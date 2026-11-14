"""
MARSCOPE Science-Aware Route Computation & Turn-by-Turn Navigation Endpoints
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.routing.graph import RoutePlanningError
from app.routing.schemas import (
    NavigationInstruction,
    RouteCompareRequest,
    RouteCompareResponse,
    RouteComputeRequest,
    RouteComputeResponse,
    RouteStatusResponse,
    RouteValidationResponse,
    RouteVertex,
)
from app.services.container import routing_service

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/status", response_model=RouteStatusResponse)
async def get_routing_status() -> RouteStatusResponse:
    return routing_service.get_status()


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
