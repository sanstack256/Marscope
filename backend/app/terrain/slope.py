"""
MARSCOPE Slope Gradient Calculator
Martian Surface Intelligence & Exploration System

Implements Horn's 8-neighbor finite difference gradient algorithm on a metric scale.
Angular grid cell sizes are rigorously converted to meters on Mars before slope calculation.
"""

import math
from typing import Dict, Any, Tuple
import numpy as np
from scipy.ndimage import convolve
from app.geospatial.crs import angular_displacement_to_metric


def calculate_slope(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: np.ndarray = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute slope angle from a 2D elevation grid using Horn's 3x3 finite-difference kernel.
    
    Args:
        elevation_grid: 2D array of elevation values in meters.
        dx_meters: Cell horizontal width in meters.
        dy_meters: Cell vertical height in meters.
        nodata_mask: Optional boolean mask where True = no-data / invalid.
        
    Returns:
        Tuple of (slope_degrees, slope_radians) with no-data pixels set to NaN.
    """
    if dx_meters <= 0 or dy_meters <= 0:
        raise ValueError("Grid cell spacing (dx, dy) must be strictly positive in meters.")
    if elevation_grid.ndim != 2:
        raise ValueError(f"Elevation grid must be 2-dimensional (got shape {elevation_grid.shape}).")
    
    nrows, ncols = elevation_grid.shape
    if nrows < 3 or ncols < 3:
        raise ValueError(f"Grid dimensions ({nrows}x{ncols}) must be at least 3x3.")

    # Horn's weighting kernels
    # dz/dx kernel:
    # [-1  0  1]
    # [-2  0  2]
    # [-1  0  1] / (8 * dx)
    kernel_x = np.array([
        [-1.0, 0.0, 1.0],
        [-2.0, 0.0, 2.0],
        [-1.0, 0.0, 1.0],
    ], dtype=np.float64) / (8.0 * dx_meters)

    # dz/dy kernel (row increases downwards, so north is upwards: row i-1 is north):
    # [ 1  2  1]
    # [ 0  0  0]
    # [-1 -2 -1] / (8 * dy)
    kernel_y = np.array([
        [1.0, 2.0, 1.0],
        [0.0, 0.0, 0.0],
        [-1.0, -2.0, -1.0],
    ], dtype=np.float64) / (8.0 * dy_meters)

    # Handle NaNs in elevation by filling with edge/nearest for convolution
    valid = ~np.isnan(elevation_grid)
    if nodata_mask is not None:
        valid = valid & (~nodata_mask)

    work_grid = elevation_grid.copy().astype(np.float64)
    if not np.all(valid):
        mean_val = float(np.nanmean(work_grid)) if np.any(valid) else 0.0
        work_grid[~valid] = mean_val

    dz_dx = convolve(work_grid, kernel_x, mode="nearest")
    dz_dy = convolve(work_grid, kernel_y, mode="nearest")

    # Slope gradient = sqrt((dz/dx)^2 + (dz/dy)^2)
    gradient_magnitude = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_rad = np.arctan(gradient_magnitude)
    slope_deg = np.degrees(slope_rad)

    # Invalidate boundary pixels and original no-data pixels
    slope_deg[0, :] = np.nan
    slope_deg[-1, :] = np.nan
    slope_deg[:, 0] = np.nan
    slope_deg[:, -1] = np.nan

    slope_rad[0, :] = np.nan
    slope_rad[-1, :] = np.nan
    slope_rad[:, 0] = np.nan
    slope_rad[:, -1] = np.nan

    if not np.all(valid):
        slope_deg[~valid] = np.nan
        slope_rad[~valid] = np.nan

    return slope_deg, slope_rad
