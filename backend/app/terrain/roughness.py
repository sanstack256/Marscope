"""
MARSCOPE Terrain Ruggedness Calculator
Martian Surface Intelligence & Exploration System

Implements the Terrain Ruggedness Index (TRI, Riley et al. 1999 / Wilson et al. 2007).
Calculates the root-mean-square elevation difference between each cell and its 8 neighbors in physical meters.
"""

from typing import Tuple
import numpy as np


def calculate_roughness_tri(
    elevation_grid: np.ndarray,
    nodata_mask: np.ndarray = None,
) -> np.ndarray:
    """
    Calculate the Terrain Ruggedness Index (TRI) in physical units of meters.
    
    TRI = sqrt( 1/8 * sum_{k=1}^8 (z_center - z_k)^2 )
    """
    if elevation_grid.ndim != 2:
        raise ValueError("Elevation grid must be 2D.")

    nrows, ncols = elevation_grid.shape
    if nrows < 3 or ncols < 3:
        raise ValueError("Grid must be at least 3x3 for TRI calculation.")

    valid = ~np.isnan(elevation_grid)
    if nodata_mask is not None:
        valid = valid & (~nodata_mask)

    tri = np.full((nrows, ncols), np.nan, dtype=np.float64)

    # Compute differences for each of the 8 neighbors
    diff_sum_sq = np.zeros((nrows, ncols), dtype=np.float64)
    neighbor_count = np.zeros((nrows, ncols), dtype=np.int32)

    shifts = [
        (-1, -1), (-1, 0), (-1, 1),
        ( 0, -1),          ( 0, 1),
        ( 1, -1), ( 1, 0), ( 1, 1),
    ]

    center_slice_r = slice(1, nrows - 1)
    center_slice_c = slice(1, ncols - 1)
    center_vals = elevation_grid[center_slice_r, center_slice_c]
    center_valid = valid[center_slice_r, center_slice_c]

    for dr, dc in shifts:
        neighbor_slice_r = slice(1 + dr, nrows - 1 + dr)
        neighbor_slice_c = slice(1 + dc, ncols - 1 + dc)
        neighbor_vals = elevation_grid[neighbor_slice_r, neighbor_slice_c]
        neighbor_valid = valid[neighbor_slice_r, neighbor_slice_c]

        pair_valid = center_valid & neighbor_valid
        diff_sq = np.where(pair_valid, (center_vals - neighbor_vals) ** 2, 0.0)

        diff_sum_sq[center_slice_r, center_slice_c] += diff_sq
        neighbor_count[center_slice_r, center_slice_c] += pair_valid.astype(np.int32)

    # Only cells with at least 4 valid neighbors are computed
    valid_cells = neighbor_count >= 4
    tri[valid_cells] = np.sqrt(diff_sum_sq[valid_cells] / neighbor_count[valid_cells])

    return tri
