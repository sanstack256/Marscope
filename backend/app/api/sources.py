"""
MARSCOPE Data Sources & Provenance Register API
Martian Surface Intelligence & Exploration System

Generates source registry status dynamically from registered adapters and recorded verification evidence,
plus live paginated NASA PDS / ODE archive discovery endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.ingestion.sources.msl_curiosity import MslCuriositySourceAdapter
from app.services.container import catalog_service

router = APIRouter(prefix="/sources", tags=["Data Sources & Provenance"])


@router.get("")
async def list_data_sources() -> List[Dict[str, Any]]:
    """
    Returns source archive adapters with separated verification status:
    archive_availability, product_discovery, metadata_verification, license_verification,
    coverage_verification, download_verification, and processing_verification.
    """
    return catalog_service.get_source_registry_report()


@router.get("/msl/archive-query")
async def query_msl_pds_archive(
    collection: str = Query("chemcam_moc", description="chemcam_moc | chemin_rdr5 | crism_ode"),
    sol_min: Optional[int] = Query(None, ge=0),
    sol_max: Optional[int] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Query live official NASA PDS Geosciences / ODE REST archive directories with filtering,
    pagination, and explicit query-provenance recording.
    """
    adapter = MslCuriositySourceAdapter()
    try:
        return await adapter.discover_archive_products(
            collection=collection,
            sol_min=sol_min,
            sol_max=sol_max,
            page=page,
            limit=limit,
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream NASA PDS archive query failed: {exc}")


@router.get("/audit")
async def get_challenge_sources_audit() -> Dict[str, Any]:
    """
    Return the authoritative NASA/USGS data-source audit across all five challenge sources,
    preserving strict exclusion and spatial/mission isolation boundaries.
    """
    from app.ingestion.sources.usgs_pgm import UsgsPlanetaryGeologicMappingAdapter

    return {
        "primary_study_region": {
            "name": "Gale Crater / Mount Sharp (Curiosity 2025/2026 Boxwork Focus)",
            "crs": "IAU2000:49900",
            "bounding_box": {"min_lat": -6.0, "max_lat": -4.0, "min_lon": 136.5, "max_lon": 139.0},
        },
        "sources": [
            {
                "id": "jpl_mars_trek",
                "name": "JPL Mars Trek",
                "status": "integrated",
                "layers": [
                    "Mars_Viking_MDIM21_ClrMosaic_global_232m",
                    "Mars_MGS_MOLA_ClrShade_merge_global_463m",
                    "Mars_MGS_TES_Albedo_mosaic_global_7410m",
                    "curiosity_hirise_mosaic",
                    "Gale_CTX_BlockAdj_dd",
                ],
                "notes": "Verified WMTS basemaps and orbital overlays; visual mosaics never replace local DEM elevation.",
            },
            {
                "id": "usgs_planetary_geologic_mapping",
                "name": "USGS-NASA Planetary Geologic Mapping Program",
                "status": "integrated_context_only",
                **UsgsPlanetaryGeologicMappingAdapter.get_scale_constraint_metadata(),
            },
            {
                "id": "curiosity_route_and_observations",
                "name": "Curiosity Route-Map and Rover Observations",
                "status": "integrated",
                "endpoints": [
                    "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json",
                    "PDS Geosciences MSL APXS, ChemCam LIBS, CheMin XRD, REMS",
                ],
                "notes": "Official JPL MSL traverse (Sols 0-5073+) and calibrated geochemical/mineralogical observations in Gale Crater.",
            },
            {
                "id": "nasa_worldview",
                "name": "NASA Worldview (EOSDIS GIBS)",
                "status": "excluded_no_mars_dataset",
                "included_in_mars_pipeline": False,
                "reason": (
                    "Audited and excluded: NASA Worldview / EOSDIS GIBS serves Earth satellite observation layers only "
                    "and provides no authoritative IAU2000 Mars surface datasets."
                ),
            },
            {
                "id": "perseverance_raw_images_gallery",
                "name": "Mars Perseverance Raw Images Gallery",
                "status": "integrated_isolated_jezero",
                "mission": "Mars 2020 Perseverance",
                "site": "Jezero Crater",
                "endpoint": "/api/imagery/perseverance",
                "isolated_from_gale_planning": True,
                "notes": "Maintained exclusively as a Jezero Crater imagery feed; never mixed into Gale Crater routes or science targets.",
            },
        ],
    }
