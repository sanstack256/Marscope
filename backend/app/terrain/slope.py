"""
MARSCOPE Slope Gradient Calculator
Martian Surface Intelligence & Exploration System

Implements Horn's 8-neighbor finite difference gradient algorithm on a metric scale.
Strictly enforces 3x3 neighborhood validity: any border cell or cell adjacent to no-data
returns NaN (no-data). Never fills or interpolates missing elevations.
"""

import math
from typing import Optional, Tuple
import numpy as np

SUPPORTED_METRIC_VERTICAL_UNITS = {
    "m",
    "meter",
    "meters",
    "meters relative to mola areoid",
}


def validate_terrain_inputs(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    vertical_units: str = "meters",
) -> None:
    """Validate grid geometry, finite positive metric spacing, and metric elevation units."""
    if not (math.isfinite(dx_meters) and math.isfinite(dy_meters)) or dx_meters <= 0 or dy_meters <= 0:
        raise ValueError("Grid cell spacing (dx_meters, dy_meters) must be finite positive numbers in meters.")
    if not vertical_units or vertical_units.strip().lower() not in SUPPORTED_METRIC_VERTICAL_UNITS:
        raise ValueError(
            f"Unsupported or unknown vertical elevation units: '{vertical_units}'. "
            "Terrain derivatives require verified metric elevation units."
        )
    if elevation_grid.ndim != 2:
        raise ValueError(f"Elevation grid must be 2-dimensional (got shape {elevation_grid.shape}).")

    nrows, ncols = elevation_grid.shape
    if nrows < 3 or ncols < 3:
        raise ValueError(f"Grid dimensions ({nrows}x{ncols}) must be at least 3x3.")


def compute_horn_gradients(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: Optional[np.ndarray] = None,
    vertical_units: str = "meters",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute Horn's 3x3 partial derivatives (dz/dx, dz/dy) in East/North Cartesian frame.
    Row index 0 is North (increasing row index moves South); col index 0 is West (increasing col moves East).

    Returns:
        (dz_dx, dz_dy, valid_3x3_mask) where invalid neighborhoods and 1-px edges have NaN gradients.
    """
    validate_terrain_inputs(elevation_grid, dx_meters, dy_meters, vertical_units)
    nrows, ncols = elevation_grid.shape

    z = elevation_grid.astype(np.float64)
    valid = np.isfinite(z)
    if nodata_mask is not None:
        if nodata_mask.shape != elevation_grid.shape:
            raise ValueError("nodata_mask shape must match elevation_grid shape.")
        valid = valid & (~nodata_mask)

    # Interior neighborhood slices:
    # a b c
    # d e f
    # g h i
    a = z[0:-2, 0:-2]
    b = z[0:-2, 1:-1]
    c = z[0:-2, 2:]
    d = z[1:-1, 0:-2]
    e_valid = valid[1:-1, 1:-1]
    f = z[1:-1, 2:]
    g = z[2:, 0:-2]
    h = z[2:, 1:-1]
    i = z[2:, 2:]

    full_window_valid = (
        valid[0:-2, 0:-2] & valid[0:-2, 1:-1] & valid[0:-2, 2:]
        & valid[1:-1, 0:-2] & e_valid & valid[1:-1, 2:]
        & valid[2:, 0:-2] & valid[2:, 1:-1] & valid[2:, 2:]
    )

    dz_dx = np.full((nrows, ncols), np.nan, dtype=np.float64)
    dz_dy = np.full((nrows, ncols), np.nan, dtype=np.float64)
    valid_out = np.zeros((nrows, ncols), dtype=bool)
    valid_out[1:-1, 1:-1] = full_window_valid

    with np.errstate(invalid="ignore"):
        gx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / (8.0 * dx_meters)
        gy = ((a + 2.0 * b + c) - (g + 2.0 * h + i)) / (8.0 * dy_meters)

    dz_dx[1:-1, 1:-1] = np.where(full_window_valid, gx, np.nan)
    dz_dy[1:-1, 1:-1] = np.where(full_window_valid, gy, np.nan)

    return dz_dx, dz_dy, valid_out


def calculate_slope(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: Optional[np.ndarray] = None,
    vertical_units: str = "meters",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute slope angle from a 2D elevation grid using Horn's 3x3 finite-difference method.

    Neighborhood Validity Requirement:
        All 9 pixels in the centered 3x3 window must be valid (finite & not masked).
        Borders and cells with any invalid neighbor strictly yield NaN.
    """
    dz_dx, dz_dy, valid_out = compute_horn_gradients(
        elevation_grid,
        dx_meters,
        dy_meters,
        nodata_mask=nodata_mask,
        vertical_units=vertical_units,
    )

    slope_rad = np.full_like(dz_dx, np.nan)
    slope_deg = np.full_like(dz_dx, np.nan)

    grad_mag = np.sqrt(dz_dx[valid_out] ** 2 + dz_dy[valid_out] ** 2)
    rad_vals = np.arctan(grad_mag)
    slope_rad[valid_out] = rad_vals
    slope_deg[valid_out] = np.degrees(rad_vals)

    return slope_deg, slope_rad
