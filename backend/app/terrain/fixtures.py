"""
MARSCOPE Analytical Terrain Test Fixtures
Martian Surface Intelligence & Exploration System

NOTE: These surfaces are strictly mathematical test fixtures for unit testing and algorithm validation.
They must NEVER be placed in the operational dataset catalog or presented as real planetary measurements.
"""

import math
from typing import Tuple
import numpy as np


def generate_flat_surface(elevation_m: float = 0.0, shape: Tuple[int, int] = (20, 20)) -> np.ndarray:
    """
    Generate an analytically flat elevation surface.
    Expected slope: exactly 0.0 degrees.
    Expected aspect: -1.0 (flat).
    Expected TRI roughness: 0.0 meters.
    """
    return np.full(shape, elevation_m, dtype=np.float64)


def generate_planar_slope(
    slope_deg: float,
    dx_m: float = 10.0,
    dy_m: float = 10.0,
    shape: Tuple[int, int] = (25, 25),
    azimuth_deg: float = 180.0,  # Sloping downwards towards South by default
) -> np.ndarray:
    """
    Generate an analytically defined planar tilted surface with exact mathematical slope angle.
    
    dz/dx = -sin(azimuth) * tan(slope)
    dz/dy = -cos(azimuth) * tan(slope)
    """
    nrows, ncols = shape
    rad_slope = math.radians(slope_deg)
    rad_az = math.radians(azimuth_deg)

    grad_mag = math.tan(rad_slope)
    grad_x = math.sin(rad_az) * grad_mag
    grad_y = -math.cos(rad_az) * grad_mag

    y_indices, x_indices = np.indices((nrows, ncols))
    x_coords = x_indices * dx_m
    y_coords = (nrows - 1 - y_indices) * dy_m  # North is top (row 0)

    z = grad_x * x_coords + grad_y * y_coords
    return z.astype(np.float64)


def generate_stepped_ridge(
    h_base_m: float = 100.0,
    h_ridge_m: float = 150.0,
    shape: Tuple[int, int] = (30, 30),
) -> np.ndarray:
    """
    Generate a stepped ridge mimicking an idealized boxwork fin standing in relief.
    """
    z = np.full(shape, h_base_m, dtype=np.float64)
    # Ridge runs along middle 4 columns
    mid_col = shape[1] // 2
    z[:, mid_col - 1 : mid_col + 2] = h_ridge_m
    return z
