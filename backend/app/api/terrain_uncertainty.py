"""
MARSCOPE Terrain Uncertainty, Observability, 3-State Traversability & Complementarity API
Exposes dataset uncertainty profiles, bounded corridor uncertainty/slope propagation,
georeferenced PNG uncertainty overlays, and the Data Complementarity Registry.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response

from app.science.complementarity import (
    ComplementarityAssessmentReport,
    evaluate_data_complementarity,
)
from app.services.container import catalog_service, terrain_uncertainty_service
from app.terrain.mesh import DEFAULT_GALE_STUDY_BOUNDS, HIRISE_DEFAULT_FOCUS_BOUNDS
from app.terrain_uncertainty.schemas import (
    CorridorUncertaintyProfile,
    DatasetUncertaintyProfile,
)

router = APIRouter(prefix="/terrain-uncertainty", tags=["terrain-uncertainty"])


@router.get("/dataset/{dataset_id}", response_model=DatasetUncertaintyProfile)
async def get_dataset_uncertainty(dataset_id: str) -> DatasetUncertaintyProfile:
    """Inspect real PDS3 label/header elevation uncertainty metadata and dtype limits for a dataset."""
    try:
        return terrain_uncertainty_service.inspect_dataset_uncertainty(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/corridor", response_model=CorridorUncertaintyProfile)
async def analyze_corridor_uncertainty(
    dataset_id: Optional[str] = Query(None, description="DEM dataset_id (defaults to highest-res local HiRISE DEM)"),
    optical_dataset_id: Optional[str] = Query(None, description="Optional paired orthophoto dataset_id"),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_slope_deg: float = Query(20.0, ge=1.0, le=60.0),
    grid_size: int = Query(97, ge=17, le=193),
) -> CorridorUncertaintyProfile:
    """Compute coupled Horn 3x3 slope sigma, TRI sigma, 3-state traversability, and 7-scale observability."""
    if min_lat is not None and max_lat is not None and min_lat >= max_lat:
        raise HTTPException(status_code=422, detail="min_lat must be < max_lat.")
    if min_lon is not None and max_lon is not None and min_lon >= max_lon:
        raise HTTPException(status_code=422, detail="min_lon must be < max_lon.")
    try:
        return terrain_uncertainty_service.analyze_corridor_uncertainty(
            dataset_id=dataset_id,
            optical_dataset_id=optical_dataset_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            max_slope_deg=max_slope_deg,
            grid_size=grid_size,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/overlay.png")
async def get_uncertainty_overlay_png(
    dataset_id: Optional[str] = Query(None, description="DEM dataset_id"),
    overlay: str = Query(
        "traversability_state",
        description="uncertainty_status | traversability_state | observability | slope_uncertainty_probe",
    ),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=360.0),
    size: int = Query(256, ge=64, le=512),
    max_slope_deg: float = Query(20.0, ge=1.0, le=60.0),
    vmin: Optional[float] = Query(None),
    vmax: Optional[float] = Query(None),
) -> Response:
    """Render strictly registered RGBA PNG overlay for 3D terrain mesh draping."""
    try:
        ds = terrain_uncertainty_service._resolve_dem_dataset(dataset_id)
        focus = HIRISE_DEFAULT_FOCUS_BOUNDS.get(ds.id) or {
            "min_lat": max(ds.coverage.min_latitude, DEFAULT_GALE_STUDY_BOUNDS["min_lat"]),
            "max_lat": min(ds.coverage.max_latitude, DEFAULT_GALE_STUDY_BOUNDS["max_lat"]),
            "min_lon": max(ds.coverage.min_longitude, DEFAULT_GALE_STUDY_BOUNDS["min_lon"]),
            "max_lon": min(ds.coverage.max_longitude, DEFAULT_GALE_STUDY_BOUNDS["max_lon"]),
        }
        q_min_lat = min_lat if min_lat is not None else focus["min_lat"]
        q_max_lat = max_lat if max_lat is not None else focus["max_lat"]
        q_min_lon = min_lon if min_lon is not None else focus["min_lon"]
        q_max_lon = max_lon if max_lon is not None else focus["max_lon"]
        if q_min_lat >= q_max_lat or q_min_lon >= q_max_lon:
            q_min_lat = ds.coverage.min_latitude
            q_max_lat = ds.coverage.max_latitude
            q_min_lon = ds.coverage.min_longitude
            q_max_lon = ds.coverage.max_longitude
        if q_min_lat >= q_max_lat or q_min_lon >= q_max_lon:
            raise HTTPException(status_code=422, detail="Invalid bounding box for overlay texture.")

        png_bytes = terrain_uncertainty_service.render_uncertainty_overlay_png(
            dataset_id=ds.id,
            overlay=overlay,
            min_lat=q_min_lat,
            max_lat=q_max_lat,
            min_lon=q_min_lon,
            max_lon=q_max_lon,
            size=size,
            max_slope_deg=max_slope_deg,
            vmin=vmin,
            vmax=vmax,
        )
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=1800"},
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/complementarity", response_model=ComplementarityAssessmentReport)
async def get_data_complementarity(
    dataset_ids: Optional[str] = Query(
        None,
        description="Optional comma-separated active dataset IDs (defaults to all locally available catalog datasets + MSL/Jezero records)",
    ),
    route_distance_m: Optional[float] = Query(None, gt=0.0),
) -> ComplementarityAssessmentReport:
    """Return MARSCOPE Data Complementarity Registry supports vs does-not-support contract."""
    if dataset_ids:
        active = [item.strip() for item in dataset_ids.split(",") if item.strip()]
    else:
        active = [ds.id for ds in catalog_service.list_datasets() if ds.local_file_path]
        active.extend(["curiosity_msl_waypoints_and_observations", "perseverance_jezero_gallery"])
    return evaluate_data_complementarity(
        active_dataset_ids=active,
        route_distance_m=route_distance_m,
    )
