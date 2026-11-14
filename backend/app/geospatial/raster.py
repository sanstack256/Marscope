"""
MARSCOPE Raster Inspection Service
Martian Surface Intelligence & Exploration System

Uses Rasterio and NumPy to inspect planetary rasters.
Statistics are calculated strictly on valid pixels; no-data values are never treated as zero.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import rasterio
from rasterio.crs import CRS
from app.schemas.terrain import RasterBandStats


class RasterInspectionService:
    @staticmethod
    def inspect_raster_file(file_path: Path, band_index: int = 1) -> Dict[str, Any]:
        """
        Inspect a GeoTIFF or supported planetary raster, computing valid-pixel statistics.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Raster file not found: {file_path}")

        with rasterio.open(file_path) as src:
            width = src.width
            height = src.height
            count = src.count
            dtypes = [src.dtypes[i] for i in range(count)]
            bounds = src.bounds
            crs = str(src.crs) if src.crs else "Unprojected"
            transform = list(src.transform)
            nodata = src.nodatavals[band_index - 1]

            # Read band data
            data = src.read(band_index)
            
            # Mask no-data values
            if nodata is not None:
                mask = (data == nodata) | np.isnan(data)
            else:
                mask = np.isnan(data)
            
            valid_pixels = data[~mask]
            total_pixels = width * height
            valid_count = int(valid_pixels.size)
            nodata_count = int(total_pixels - valid_count)
            valid_pct = (valid_count / total_pixels * 100.0) if total_pixels > 0 else 0.0

            if valid_count > 0:
                stats = RasterBandStats(
                    min_value=float(np.min(valid_pixels)),
                    max_value=float(np.max(valid_pixels)),
                    mean_value=float(np.mean(valid_pixels)),
                    std_dev=float(np.std(valid_pixels)),
                    valid_pixel_count=valid_count,
                    nodata_pixel_count=nodata_count,
                    valid_data_percentage=round(valid_pct, 2),
                    units="meters" if "dem" in file_path.name.lower() or "topography" in file_path.name.lower() else "uncalibrated_DN",
                )
            else:
                stats = RasterBandStats(
                    min_value=0.0,
                    max_value=0.0,
                    mean_value=0.0,
                    std_dev=0.0,
                    valid_pixel_count=0,
                    nodata_pixel_count=nodata_count,
                    valid_data_percentage=0.0,
                    units="nodata",
                )

            return {
                "file_name": file_path.name,
                "file_size_bytes": file_path.stat().st_size,
                "dimensions": {"width": width, "height": height},
                "band_count": count,
                "data_types": dtypes,
                "bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
                "crs": crs,
                "transform": transform,
                "nodata_value": nodata,
                "stats": stats.model_dump(),
            }
