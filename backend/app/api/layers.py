"""
MARSCOPE Geospatial Map Layers API
Martian Surface Intelligence & Exploration System
"""

from typing import List, Dict, Any
from fastapi import APIRouter
from app.services.container import catalog_service

router = APIRouter(prefix="/layers", tags=["Geospatial Layers"])


@router.get("")
async def list_map_layers() -> List[Dict[str, Any]]:
    """
    List available raster, vector, and WMTS map layers for 2D/3D surface viewers.
    """
    return [
        {
            "id": "viking_color_mosaic",
            "name": "Viking MDIM 2.1 Color Basemap",
            "category": "optical",
            "type": "wmts",
            "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
            "attribution": "NASA/JPL/USGS",
            "license": "NASA Public Domain",
            "visible": True,
            "opacity": 1.0,
            "crs": "IAU2000:MARS_SPHERE",
            "resolution_m": 232.0,
        },
        {
            "id": "mola_shaded_relief",
            "name": "MOLA Shaded Relief & Topography (128 ppd)",
            "category": "topography",
            "type": "raster",
            "source_dataset_id": "mola_megt00n090hb",
            "attribution": "NASA/JPL/GSFC/PDS Geosciences",
            "license": "NASA Public Domain",
            "visible": True,
            "opacity": 0.7,
            "crs": "IAU2000:MARS_SPHERE",
            "resolution_m": 463.0,
        },
        {
            "id": "slope_gradient_layer",
            "name": "Calculated Slope Gradient Map",
            "category": "topography",
            "type": "derived",
            "source_dataset_id": "mola_megt00n090hb",
            "attribution": "Derived by MARSCOPE (Horn 3x3 algorithm)",
            "license": "Open Science / MARSCOPE Derivative",
            "visible": False,
            "opacity": 0.8,
            "crs": "IAU2000:MARS_SPHERE",
            "units": "degrees",
        },
        {
            "id": "msl_curiosity_traverse",
            "name": "Curiosity Rover Gale Crater Traverse",
            "category": "rover",
            "type": "vector",
            "source_dataset_id": "msl_chemcam_sol00010_psv",
            "attribution": "NASA/JPL-Caltech/PDS",
            "license": "NASA Public Domain",
            "visible": True,
            "opacity": 1.0,
            "crs": "IAU2000:49900",
        },
    ]
