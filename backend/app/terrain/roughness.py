"""
MARSCOPE Terrain Ruggedness Index (TRI) Calculator
Martian Surface Intelligence & Exploration System

Implements physical-scale Terrain Ruggedness Index (Riley et al., 1999 generalized to metric windows):
    TRI = sqrt( (1 / N) * sum_{k in neighborhood} (z_center - z_k)^2 )
in physical vertical units (meters).

Resolution Awareness:
    A physical neighborhood radius (in meters) is converted into grid offsets (rx, ry) using
    dx_meters and dy_meters so physical roughness represents a consistent spatial footprint
    across rasters of differing resolution.
No-Data Policy:
    Requires ALL cells in the configured neighborhood window to be valid. Border cells and
    any neighborhood touching a no-data pixel strictly yield NaN.
"""

import math
from typing import Any, Dict, Optional, Tuple
import numpy as np
from app.terrain.slope import validate_terrain_inputs


def calculate_roughness_tri_with_metadata(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: Optional[np.ndarray] = None,
    neighborhood_radius_meters: Optional[float] = None,
    vertical_units: str = "meters",
    source_product_id: Optional[str] = None,
    native_resolution_m: Optional[float] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Calculate physical Terrain Ruggedness Index (TRI) over a resolution-aware metric window.

    Args:
        elevation_grid: 2D array of metric elevation values.
        dx_meters: Pixel horizontal spacing in meters.
        dy_meters: Pixel vertical spacing in meters.
        nodata_mask: Optional boolean array (True = no-data).
        neighborhood_radius_meters: Physical search radius in meters. If None, uses 1-pixel half-window
            corresponding to physical radius max(dx_meters, dy_meters).
        vertical_units: Must be verified metric units ('meters').
        source_product_id: Optional authoritative source DEM product identifier.
        native_resolution_m: Optional native DEM pixel spacing in meters.
    """
    validate_terrain_inputs(elevation_grid, dx_meters, dy_meters, vertical_units)
    if neighborhood_radius_meters is not None and (
        not math.isfinite(neighborhood_radius_meters) or neighborhood_radius_meters <= 0
    ):
        raise ValueError("neighborhood_radius_meters must be strictly positive when provided.")

    nrows, ncols = elevation_grid.shape
    if neighborhood_radius_meters is not None:
        max_spacing = max(dx_meters, dy_meters)
        if neighborhood_radius_meters < 0.5 * max_spacing:
            raise ValueError(
                f"Requested TRI physical neighborhood radius ({neighborhood_radius_meters} m) "
                f"is resolution-limited by DEM spacing ({dx_meters:.3f} m x {dy_meters:.3f} m); "
                f"minimum resolvable radius is {0.5 * max_spacing:.3f} m."
            )
        rx = max(1, int(round(neighborhood_radius_meters / dx_meters)))
        ry = max(1, int(round(neighborhood_radius_meters / dy_meters)))
    else:
        rx = 1
        ry = 1

    if nrows < (2 * ry + 1) or ncols < (2 * rx + 1):
        raise ValueError(
            f"Grid dimensions ({nrows}x{ncols}) too small for physical TRI window "
            f"{2*ry+1}x{2*rx+1} pixels (radius={neighborhood_radius_meters} m)."
        )

    z = elevation_grid.astype(np.float64)
    valid = np.isfinite(z)
    if nodata_mask is not None:
        if nodata_mask.shape != elevation_grid.shape:
            raise ValueError("nodata_mask shape must match elevation_grid shape.")
        valid = valid & (~nodata_mask)

    tri = np.full((nrows, ncols), np.nan, dtype=np.float64)
    r_slice = slice(ry, nrows - ry)
    c_slice = slice(rx, ncols - rx)

    center_vals = z[r_slice, c_slice]
    all_neighbors_valid = valid[r_slice, c_slice].copy()
    diff_sum_sq = np.zeros_like(center_vals, dtype=np.float64)
    neighbor_total = 0

    for dr in range(-ry, ry + 1):
        for dc in range(-rx, rx + 1):
            if dr == 0 and dc == 0:
                continue
            nr_slice = slice(ry + dr, nrows - ry + dr)
            nc_slice = slice(rx + dc, ncols - rx + dc)
            n_vals = z[nr_slice, nc_slice]
            n_valid = valid[nr_slice, nc_slice]
            all_neighbors_valid &= n_valid
            with np.errstate(invalid="ignore"):
                diff = np.where(all_neighbors_valid, center_vals - n_vals, 0.0)
                diff_sum_sq += diff * diff
            neighbor_total += 1

    interior_tri = np.where(all_neighbors_valid, np.sqrt(diff_sum_sq / float(neighbor_total)), np.nan)
    tri[r_slice, c_slice] = interior_tri

    metadata = {
        "metric": "Terrain Ruggedness Index (RMS elevation difference)",
        "formula_id": "riley_1999_rms_elevation_difference_v1",
        "neighborhood_shape": "rectangular_metric_window",
        "units": "meters",
        "window_half_pixels_x": rx,
        "window_half_pixels_y": ry,
        "window_shape_pixels": [2 * ry + 1, 2 * rx + 1],
        "neighbor_count_required": neighbor_total,
        "physical_radius_m": round(float(neighborhood_radius_meters), 3)
        if neighborhood_radius_meters is not None
        else round(max(rx * dx_meters, ry * dy_meters), 3),
        "physical_half_width_m": round(rx * dx_meters, 3),
        "physical_half_height_m": round(ry * dy_meters, 3),
        "actual_window_width_m": round((2 * rx + 1) * dx_meters, 3),
        "actual_window_height_m": round((2 * ry + 1) * dy_meters, 3),
        "requested_radius_meters": neighborhood_radius_meters,
        "source_product_id": source_product_id,
        "native_resolution_m": native_resolution_m,
        "processing_resolution_m": round(0.5 * (dx_meters + dy_meters), 3),
        "nodata_policy": "strict_all_neighbors_valid",
        "processing_version": "tri_v2_fixed_physical_window",
    }
    return tri, metadata


def calculate_roughness_tri(
    elevation_grid: np.ndarray,
    dx_meters: float = 1.0,
    dy_meters: float = 1.0,
    nodata_mask: Optional[np.ndarray] = None,
    neighborhood_radius_meters: Optional[float] = None,
    vertical_units: str = "meters",
) -> np.ndarray:
    """
    Calculate physical Terrain Ruggedness Index (TRI) in meters.
    See calculate_roughness_tri_with_metadata for full window specification.
    """
    tri, _ = calculate_roughness_tri_with_metadata(
        elevation_grid=elevation_grid,
        dx_meters=dx_meters,
        dy_meters=dy_meters,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=neighborhood_radius_meters,
        vertical_units=vertical_units,
    )
    return tri
