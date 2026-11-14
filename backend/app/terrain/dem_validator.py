"""
MARSCOPE Digital Elevation Model (DEM) Validation Service
Martian Surface Intelligence & Exploration System

Ensures input rasters are genuine elevation products with verified CRS, horizontal scale, and metric units.
"""

from typing import Any, Dict, Optional, Tuple
import numpy as np
from app.terrain.slope import SUPPORTED_METRIC_VERTICAL_UNITS


class DEMValidationError(ValueError):
    pass


class DEMValidator:
    @staticmethod
    def validate_dem_metadata(metadata: Dict[str, Any]) -> None:
        """
        Validate that raster metadata represents a valid, georeferenced metric elevation surface
        suitable for slope, aspect, and roughness analysis.
        """
        dims = metadata.get("dimensions", {})
        width = dims.get("width", 0)
        height = dims.get("height", 0)

        if width < 3 or height < 3:
            raise DEMValidationError(
                f"DEM raster dimensions ({width}x{height}) are too small for 3x3 kernel analysis."
            )

        if not metadata.get("crs_verified", False) or not metadata.get("crs"):
            raise DEMValidationError(
                f"DEM raster lacks a verified Martian CRS (got '{metadata.get('crs')}')."
            )

        units = str(metadata.get("units") or "unknown").strip().lower()
        if not metadata.get("units_verified", False) or units not in SUPPORTED_METRIC_VERTICAL_UNITS:
            raise DEMValidationError(
                f"DEM measurement units '{metadata.get('units')}' are unknown or non-metric; "
                "cannot compute physically valid terrain derivatives."
            )

        stats = metadata.get("stats", {})
        valid_pct = stats.get("valid_data_percentage", 0.0)
        if not stats.get("available", False) or valid_pct <= 0.0:
            raise DEMValidationError("DEM raster contains zero valid pixels (100% no-data).")

        min_val = stats.get("min_value")
        max_val = stats.get("max_value")
        if min_val is None or max_val is None:
            raise DEMValidationError("DEM min/max elevation statistics are unavailable.")

        # Mars areoid elevation extreme bounds: [-9000 m (Hellas) to +22000 m (Olympus Mons)]
        if min_val < -15000.0 or max_val > 30000.0:
            raise DEMValidationError(
                f"Elevation values [{min_val}, {max_val}] exceed physical planetary bounds on Mars."
            )

    @staticmethod
    def extract_valid_elevation_mask(
        elevation_data: np.ndarray,
        nodata_val: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns (masked_elevation_data, boolean_valid_mask).
        """
        valid_mask = np.isfinite(elevation_data)
        if nodata_val is not None and np.isfinite(nodata_val):
            valid_mask = valid_mask & (elevation_data != nodata_val)

        clean_data = elevation_data.copy().astype(np.float64)
        clean_data[~valid_mask] = np.nan
        return clean_data, valid_mask
