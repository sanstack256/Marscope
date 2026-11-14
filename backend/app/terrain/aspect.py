"""
MARSCOPE Terrain Aspect Calculator
Martian Surface Intelligence & Exploration System

Computes slope aspect (compass direction of steepest descent) in degrees clockwise from True North [0, 360).
Flat surfaces are designated -1.0; raster borders and invalid 3x3 neighborhoods return NaN.
"""

from typing import Optional
import numpy as np
from app.terrain.slope import compute_horn_gradients


def calculate_aspect(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: Optional[np.ndarray] = None,
    flat_slope_threshold_deg: float = 0.01,
    vertical_units: str = "meters",
) -> np.ndarray:
    """
    Calculate compass aspect in degrees clockwise from True North [0, 360).
    - North = 0 deg, East = 90 deg, South = 180 deg, West = 270 deg.
    - Flat regions (slope < flat_slope_threshold_deg) return -1.0.
    - Borders and incomplete 3x3 neighborhoods (any no-data neighbor) strictly return NaN.
    """
    dz_dx, dz_dy, valid_out = compute_horn_gradients(
        elevation_grid,
        dx_meters,
        dy_meters,
        nodata_mask=nodata_mask,
        vertical_units=vertical_units,
    )

    aspect_compass = np.full_like(dz_dx, np.nan)
    if not np.any(valid_out):
        return aspect_compass

    gx = dz_dx[valid_out]
    gy = dz_dy[valid_out]
    slope_deg = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    # Steepest descent vector points opposite the uphill gradient (+East = -dz/dx, +North = -dz/dy)
    # Compass clockwise from North: atan2(east_component, north_component)
    aspect_vals = np.degrees(np.arctan2(-gx, -gy)) % 360.0
    aspect_vals = np.where(slope_deg < flat_slope_threshold_deg, -1.0, aspect_vals)

    aspect_compass[valid_out] = aspect_vals
    return aspect_compass
