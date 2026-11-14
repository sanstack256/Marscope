"""
MARSCOPE Terrain Intelligence Endpoints
Martian Surface Intelligence & Exploration System

Strictly operates on verified, processed elevation rasters backed by manifests.
Never generates synthetic fallback terrain surfaces.
"""

import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from app.schemas.terrain import (
    TerrainLayerMetadata,
    TerrainPointResponse,
    TerrainSummary,
    TerrainSummaryResponse,
)
from app.services.container import PROCESSED_DIR, RAW_DIR, catalog_service, destination_service, layer_service
from app.terrain.derivatives import MultiScaleTerrainResponse, analyze_multiscale_terrain_point
from app.terrain.optical_analysis import (
    OpticalAnalysisResponse,
    analyze_optical_region,
    render_optical_derived_crop_png,
)

router = APIRouter(prefix="/terrain", tags=["Terrain Intelligence"])


@router.get("/summary", response_model=TerrainSummaryResponse)
async def get_terrain_summary() -> TerrainSummaryResponse:
    """
    Retrieve terrain summary strictly from a validated processed DEM and manifest.
    Returns available=False and summary=None when no validated DEM raster is present.
    """
    manifests = sorted(PROCESSED_DIR.glob("*.processing.json"))
    for mpath in manifests:
        try:
            pdata = json.loads(mpath.read_text(encoding="utf-8"))
            dem_fname = pdata.get("files", {}).get("dem")
            if not dem_fname or not (PROCESSED_DIR / dem_fname).exists():
                continue
            summary = TerrainSummary.model_validate(pdata["summary"])
            return TerrainSummaryResponse(
                available=True,
                unavailable_reason=None,
                summary=summary,
            )
        except Exception:
            continue

    return TerrainSummaryResponse(
        available=False,
        unavailable_reason=(
            "No validated DEM raster has been downloaded and processed into terrain derivatives. "
            "Acquire and process a DEM dataset (e.g., via /api/datasets/{id}/download and /process) "
            "before inspecting elevation, slope, aspect, or roughness statistics."
        ),
        summary=None,
    )


@router.get("/point", response_model=TerrainPointResponse)
async def inspect_terrain_point(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Planetocentric latitude in [-90, 90]"),
    lon: float = Query(..., ge=-180.0, le=360.0, description="East-positive longitude in [-180, 360]"),
    crs: str = Query("IAU2000:49900", description="Active Mars CRS identifier"),
) -> TerrainPointResponse:
    """
    Sample real elevation and local derivatives at a planetary coordinate from validated local DEMs.
    Returns available=False and elevation_m=None when no validated DEM covers the point or pixel is no-data.
    """
    try:
        return destination_service.sample_processed_terrain_point(lat, lon, crs=crs)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.get("/layers", response_model=List[TerrainLayerMetadata])
async def list_terrain_layers() -> List[TerrainLayerMetadata]:
    """
    List only validated, renderable terrain derivative layers currently processed on disk.
    """
    catalog = layer_service.build_layer_catalog()
    results: List[TerrainLayerMetadata] = []
    for layer in catalog.available_layers:
        if layer.layer_type not in {"elevation_raster", "slope_raster", "aspect_raster", "roughness_raster"}:
            continue
        mpath = PROCESSED_DIR / f"{layer.source_dataset_id}.processing.json"
        if not mpath.exists():
            continue
        try:
            pdata = json.loads(mpath.read_text(encoding="utf-8"))
            short_type = layer.layer_type.replace("_raster", "")
            file_key = "dem" if short_type == "elevation" else short_type
            fname = pdata.get("files", {}).get(file_key)
            if not fname:
                continue
            import rasterio
            with rasterio.open(PROCESSED_DIR / fname) as src:
                w, h = src.width, src.height
            results.append(
                TerrainLayerMetadata(
                    layer_id=layer.layer_id,
                    name=layer.display_name,
                    layer_type=short_type,
                    source_dataset_id=layer.source_dataset_id,
                    source_product_id=layer.source_product_id,
                    units=layer.units,
                    min_val=layer.legend.min_value if layer.legend else None,
                    max_val=layer.legend.max_value if layer.legend else None,
                    width=w,
                    height=h,
                    bounds=layer.spatial_bounds,
                    resolution_m=layer.spatial_resolution_m or 0.0,
                    crs=layer.crs,
                    processing_version=layer.processing_version,
                    preview_url=layer.rendering_endpoint,
                )
            )
        except Exception:
            continue
    return results


@router.get("/multiscale", response_model=MultiScaleTerrainResponse)
async def get_multiscale_terrain_derivatives(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Target latitude (deg)"),
    lon: float = Query(..., ge=-180.0, le=360.0, description="Target longitude East (deg)"),
    dataset_id: Optional[str] = Query(None, description="Optional DEM dataset_id"),
    fine_radius_m: float = Query(5.0, gt=0.0, le=500.0),
    medium_radius_m: float = Query(15.0, gt=0.0, le=1000.0),
    relief_radius_m: float = Query(10.0, gt=0.0, le=1000.0),
) -> MultiScaleTerrainResponse:
    """
    Compute traceable multi-scale terrain derivatives (slope, curvature, fine/medium TRI,
    TPI, local relief) at a coordinate with full provenance dependency graph.
    """
    return analyze_multiscale_terrain_point(
        catalog_service=catalog_service,
        raw_dir=RAW_DIR,
        lat=lat,
        lon_east=lon,
        dataset_id=dataset_id,
        fine_radius_m=fine_radius_m,
        medium_radius_m=medium_radius_m,
        relief_radius_m=relief_radius_m,
    )


@router.get("/optical-features", response_model=OpticalAnalysisResponse)
async def get_optical_feature_analysis(
    dataset_id: str = Query("hirise_dteec_009149_1750", description="DEM or paired ortho dataset_id"),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    max_candidates: int = Query(12, ge=1, le=50),
) -> OpticalAnalysisResponse:
    """
    Extract Sobel edge texture and candidate optical ridges / dark hollows from
    real HiRISE orthorectified imagery. All detections are labelled candidate-only.
    """
    return analyze_optical_region(
        catalog_service=catalog_service,
        raw_dir=RAW_DIR,
        dataset_id=dataset_id,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        max_candidates=max_candidates,
    )


@router.get("/optical-crop")
async def get_optical_derived_crop(
    dataset_id: str = Query("hirise_dteec_009149_1750"),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    size: int = Query(192, ge=64, le=512),
) -> Response:
    """Return a derived Sobel-edge visualization crop PNG (never modifies source imagery)."""
    try:
        png_bytes = render_optical_derived_crop_png(
            catalog_service=catalog_service,
            raw_dir=RAW_DIR,
            dataset_id=dataset_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            size=size,
        )
        return Response(content=png_bytes, media_type="image/png")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
