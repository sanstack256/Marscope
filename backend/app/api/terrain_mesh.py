"""
MARSCOPE 3D Terrain Mesh & Ortho/Overlay Texture Endpoints
Serves LOD heightfield mesh tiles, Cesium heightgrids, and georeferenced ortho/derivative PNGs.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.core.security import validate_identifier, verify_operator_auth
from app.services.container import spatial_delivery_service, terrain_mesh_service
from app.terrain.mesh import (
    HeightGridResponse,
    TerrainMeshManifestResponse,
    TerrainMeshTileResponse,
)

router = APIRouter(prefix="/terrain", tags=["terrain-mesh"])


@router.get("/mesh/manifest", response_model=TerrainMeshManifestResponse)
async def get_terrain_mesh_manifest(
    dataset_id: Optional[str] = Query(None, description="DEM dataset_id (defaults to highest-res local DEM)"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lod: int = Query(2, ge=0, le=3),
    tile_grid_size: int = Query(65, ge=17, le=129),
) -> TerrainMeshManifestResponse:
    try:
        return terrain_mesh_service.get_mesh_manifest(
            dataset_id=dataset_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            max_lod=max_lod,
            tile_grid_size=tile_grid_size,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mesh/tiles/{tile_id}", response_model=TerrainMeshTileResponse)
async def get_terrain_mesh_tile(
    tile_id: str,
    dataset_id: Optional[str] = Query(None),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    origin_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    origin_lon_east: Optional[float] = Query(None, ge=-180.0, le=360.0),
    grid_size: int = Query(65, ge=9, le=129),
    include_derivatives: bool = Query(True),
) -> TerrainMeshTileResponse:
    try:
        return terrain_mesh_service.get_mesh_tile(
            tile_id=tile_id,
            dataset_id=dataset_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            origin_lat=origin_lat,
            origin_lon_east=origin_lon_east,
            grid_size=grid_size,
            include_derivatives=include_derivatives,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mesh/heightgrid", response_model=HeightGridResponse)
async def get_terrain_heightgrid(
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    dataset_id: Optional[str] = Query(None),
    grid_size: int = Query(33, ge=9, le=65),
) -> HeightGridResponse:
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(status_code=422, detail="min_lat < max_lat and min_lon < max_lon required.")
    try:
        return terrain_mesh_service.get_heightgrid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            dataset_id=dataset_id,
            grid_size=grid_size,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ortho/{dataset_id}/texture")
async def get_terrain_texture(
    dataset_id: str,
    overlay: str = Query(
        "ortho",
        description="ortho | elevation | slope | roughness | uncertainty_status | traversability_state | observability | slope_uncertainty_probe",
    ),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    size: int = Query(512, ge=64, le=1024),
    vmin: Optional[float] = Query(None, description="Optional global color scale minimum for cross-tile consistency"),
    vmax: Optional[float] = Query(None, description="Optional global color scale maximum for cross-tile consistency"),
    max_slope_deg: float = Query(20.0, ge=1.0, le=60.0, description="Slope cap used by 3-state traversability overlay"),
) -> Response:
    if min_lat >= max_lat or min_lon >= max_lon:
        raise HTTPException(status_code=422, detail="Invalid bounding box.")
    try:
        png_bytes = terrain_mesh_service.render_region_texture_png(
            dataset_id=dataset_id,
            overlay=overlay,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            size=size,
            vmin=vmin,
            vmax=vmax,
            max_slope_deg=max_slope_deg,
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mesh/cache/status")
async def get_mesh_cache_status() -> Dict[str, Any]:
    return spatial_delivery_service.get_cache_status()


@router.post("/mesh/cache/invalidate")
async def invalidate_mesh_cache(
    request: Request,
    dataset_id: Optional[str] = Query(None),
    reason: str = Query("mesh_operator_invalidation", max_length=200),
) -> Dict[str, Any]:
    verify_operator_auth(
        request,
        fail_closed_when_unconfigured=True,
        operation_name="mesh cache invalidation",
    )
    did = validate_identifier(dataset_id, field_name="dataset_id") if dataset_id else None
    return spatial_delivery_service.invalidate_cache(
        dataset_id=did,
        reason=reason,
        operator="operator",
    ).model_dump()
