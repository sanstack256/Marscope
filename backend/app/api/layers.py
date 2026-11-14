"""
MARSCOPE Geospatial Map Layers API
Martian Surface Intelligence & Exploration System

Exposes dynamically discovered renderable layers, unavailable layers with explicit causes,
and cached GeoTIFF RGBA tile rendering.
"""

from fastapi import APIRouter, HTTPException, Response, status
from app.schemas.layer import LayerCatalogResponse, MapLayer
from app.services.container import layer_service

router = APIRouter(prefix="/layers", tags=["Geospatial Layers"])


@router.get("", response_model=LayerCatalogResponse)
async def list_map_layers() -> LayerCatalogResponse:
    """
    List available (renderable) map layers separately from discovered-but-unavailable layers.
    Never exposes hardcoded mock layers.
    """
    return layer_service.build_layer_catalog()


@router.get("/{layer_id}", response_model=MapLayer)
async def get_map_layer(layer_id: str) -> MapLayer:
    """Retrieve full provenance and availability metadata for a single layer."""
    layer = layer_service.get_layer_metadata(layer_id)
    if not layer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layer_id}' not found.",
        )
    return layer


@router.get("/{layer_id}/tiles/{z}/{x}/{y}.png")
async def get_raster_tile(layer_id: str, z: int, x: int, y: int) -> Response:
    """
    Deliver a 256x256 GeographicTilingScheme RGBA PNG tile for a verified local raster layer.
    Immutable scientific tiles include long-lived HTTP cache headers.
    """
    layer = layer_service.get_layer_metadata(layer_id)
    if not layer or not layer.renderable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Renderable raster layer '{layer_id}' not available.",
        )
    if layer.tile_scheme != "geographic_wmts" or not layer.rendering_endpoint or not layer.rendering_endpoint.startswith("/api/layers/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Layer '{layer_id}' is served via external tile source '{layer.rendering_endpoint}'.",
        )

    png_bytes = layer_service.render_tile_png(layer_id, z, x, y)
    if png_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tile z={z}, x={x}, y={y} out of range or unavailable.",
        )
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
