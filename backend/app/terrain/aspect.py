"""
MARSCOPE Terrain Aspect Calculator
Martian Surface Intelligence & Exploration System

Computes slope aspect (compass direction of steepest descent) in degrees clockwise from North [0, 360).
Flat surfaces are explicitly designated as -1.0.
"""

import math
from typing import Tuple
import numpy as np
from scipy.ndimage import convolve


def calculate_aspect(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: np.ndarray = None,
    flat_slope_threshold_deg: float = 0.01,
) -> np.ndarray:
    """
    Calculate terrain aspect angle in degrees clockwise from True North [0, 360).
    Flat regions are assigned -1.0. No-data regions are assigned NaN.
    """
    if dx_meters <= 0 or dy_meters <= 0:
        raise ValueError("Cell sizes dx and dy must be strictly positive in meters.")
    if elevation_grid.ndim != 2:
        raise ValueError("Elevation grid must be 2D.")

    nrows, ncols = elevation_grid.shape
    if nrows < 3 or ncols < 3:
        raise ValueError("Grid must be at least 3x3.")

    kernel_x = np.array([
        [-1.0, 0.0, 1.0],
        [-2.0, 0.0, 2.0],
        [-1.0, 0.0, 1.0],
    ], dtype=np.float64) / (8.0 * dx_meters)

    kernel_y = np.array([
        [1.0, 2.0, 1.0],
        [0.0, 0.0, 0.0],
        [-1.0, -2.0, -1.0],
    ], dtype=np.float64) / (8.0 * dy_meters)

    valid = ~np.isnan(elevation_grid)
    if nodata_mask is not None:
        valid = valid & (~nodata_mask)

    work_grid = elevation_grid.copy().astype(np.float64)
    if not np.all(valid):
        mean_val = float(np.nanmean(work_grid)) if np.any(valid) else 0.0
        work_grid[~valid] = mean_val

    dz_dx = convolve(work_grid, kernel_x, mode="nearest")
    dz_dy = convolve(work_grid, kernel_y, mode="nearest")

    # Gradient magnitude
    grad_mag = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_deg = np.degrees(np.arctan(grad_mag))

    # Standard cartographic aspect formula:
    # aspect_math = atan2(dz/dy, -dz/dx)
    # aspect_compass = 90 - degrees(aspect_math)
    aspect_rad = np.arctan2(dz_dy, -dz_dx)
    aspect_compass = (90.0 - np.degrees(aspect_rad)) % 360.0

    # Flat areas
    flat_mask = slope_deg < flat_slope_threshold_deg
    aspect_compass[flat_mask] = -1.0

    # Edges & invalid
    aspect_compass[0, :] = np.nan
    aspect_compass[-1, :] = np.nan
    aspect_compass[:, 0] = np.nan
    aspect_compass[:, -1] = np.nan

    if not np.all(valid):
        aspect_compass[~valid] = np.nan

    return aspect_compass
