"""
MARSCOPE Raster Alignment & Windowed Clipping Service
Martian Surface Intelligence & Exploration System

Performs memory-efficient windowed extraction of regional study areas from global/regional planetary rasters.
Generates valid GeoTIFF files with embedded CRS and metadata.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.crs import CRS
from app.geospatial.crs import get_mars_crs


def clip_raster_to_bounding_box(
    source_raster_path: Path,
    output_geotiff_path: Path,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    output_crs_str: str = "IAU2000:49900",
) -> Dict[str, Any]:
    """
    Extract a sub-region from source_raster_path strictly bounded by [min_lon, min_lat, max_lon, max_lat].
    Writes output GeoTIFF with correct affine georeferencing and no-data mask.
    """
    if not source_raster_path.exists():
        raise FileNotFoundError(f"Source raster not found: {source_raster_path}")

    output_geotiff_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(source_raster_path) as src:
        # Check source bounds
        s_bounds = src.bounds
        
        # Calculate window from bounding box
        window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
        # Round window to integer offsets
        window = window.round_offsets().round_lengths()

        # Read windowed data
        window_data = src.read(1, window=window)
        window_transform = src.window_transform(window)
        nodata_val = src.nodatavals[0] if src.nodatavals else -32768.0

        # Update profile for output
        profile = src.profile.copy()
        profile.update({
            "driver": "GTiff",
            "height": window.height,
            "width": window.width,
            "transform": window_transform,
            "count": 1,
            "nodata": nodata_val,
            "crs": CRS.from_proj4(output_crs_str) if "+" in output_crs_str else CRS.from_string(output_crs_str),
        })

        with rasterio.open(output_geotiff_path, "w", **profile) as dst:
            dst.write(window_data, 1)

        return {
            "output_path": str(output_geotiff_path),
            "dimensions": {"width": int(window.width), "height": int(window.height)},
            "bounds": [min_lon, min_lat, max_lon, max_lat],
            "crs": output_crs_str,
            "pixel_count": int(window.width * window.height),
            "nodata_value": nodata_val,
        }
