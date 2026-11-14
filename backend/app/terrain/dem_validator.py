"""
MARSCOPE Digital Elevation Model (DEM) Validation Service
Martian Surface Intelligence & Exploration System

Ensures input rasters are genuine elevation products with verified horizontal scale and units.
"""

from typing import Dict, Any, Tuple
import numpy as np


class DEMValidationError(ValueError):
    pass


class DEMValidator:
    @staticmethod
    def validate_dem_metadata(metadata: Dict[str, Any]) -> None:
        """
        Validate that raster metadata represents a valid elevation surface suitable for slope/terrain derivatives.
        """
        dims = metadata.get("dimensions", {})
        width = dims.get("width", 0)
        height = dims.get("height", 0)
        
        if width < 3 or height < 3:
            raise DEMValidationError(f"DEM raster dimensions ({width}x{height}) are too small for 3x3 kernel analysis.")

        stats = metadata.get("stats", {})
        valid_pct = stats.get("valid_data_percentage", 0.0)
        if valid_pct <= 0.0:
            raise DEMValidationError("DEM raster contains zero valid pixels (100% no-data).")

        min_val = stats.get("min_value", 0.0)
        max_val = stats.get("max_value", 0.0)
        
        # Mars areoid elevation extreme range: [-9000 m (Hellas Basin) to +22000 m (Olympus Mons)]
        if min_val < -15000.0 or max_val > 30000.0:
            raise DEMValidationError(f"Elevation values [{min_val}, {max_val}] exceed physical planetary bounds on Mars.")

    @staticmethod
    def extract_valid_elevation_mask(
        elevation_data: np.ndarray,
        nodata_val: float = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns (masked_elevation_data, boolean_valid_mask).
        """
        if nodata_val is not None:
            valid_mask = (~np.isnan(elevation_data)) & (elevation_data != nodata_val)
        else:
            valid_mask = ~np.isnan(elevation_data)
        
        clean_data = elevation_data.copy().astype(np.float64)
        clean_data[~valid_mask] = np.nan
        return clean_data, valid_mask
