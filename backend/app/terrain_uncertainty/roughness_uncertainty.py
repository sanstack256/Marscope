"""
MARSCOPE Riley RMS TRI Roughness Uncertainty Propagation
Propagates elevation uncertainty sigma_z through the physical-window Terrain Ruggedness
Index `TRI = sqrt(mean((z_c - z_k)^2))` using first-order delta-method variance propagation,
while enforcing strict neighborhood completeness and pixel-scale honesty.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain_uncertainty.models import MeasurementQuantityKind, UncertaintyStatus
from app.terrain_uncertainty.schemas import RoughnessUncertaintySummary


def propagate_tri_roughness_uncertainty(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    *,
    sigma_z_m: Optional[Union[float, np.ndarray]] = None,
    nodata_mask: Optional[np.ndarray] = None,
    neighborhood_radius_meters: Optional[float] = 5.0,
    is_empirical_error_map: bool = False,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, object], RoughnessUncertaintySummary]:
    """
    Propagate vertical elevation SD `sigma_z_m` through Riley RMS TRI:
        T = sqrt((1 / N) * sum_k d_k^2),  d_k = z_c - z_k
    When T > 0, first-order partial derivatives give:
        dT/dz_k = -d_k / (N * T)
        dT/dz_c = (sum_k d_k) / (N * T)
        Var(T)  = (dT/dz_c)^2 * sigma_c^2 + sum_k (dT/dz_k)^2 * sigma_k^2
    Note: TRI is non-negative and inherits a positive noise floor near zero relief (~sigma_z * sqrt(1 + 1/N)).
    """
    tri_arr, tri_meta = calculate_roughness_tri_with_metadata(
        elevation_grid=elevation_grid,
        dx_meters=dx_meters,
        dy_meters=dy_meters,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=neighborhood_radius_meters,
    )
    total_cells = int(elevation_grid.size)
    valid_tri_mask = np.isfinite(tri_arr)
    inv_frac = 1.0 - (float(np.count_nonzero(valid_tri_mask)) / float(max(1, total_cells)))
    tri_sigma = np.full_like(tri_arr, np.nan, dtype=np.float64)

    win_shape = tri_meta.get("window_shape_pixels")
    win_dims = {
        "width_m": float(tri_meta.get("actual_window_width_m", 0.0)),
        "height_m": float(tri_meta.get("actual_window_height_m", 0.0)),
    }

    if sigma_z_m is None:
        return (
            tri_arr,
            tri_sigma,
            tri_meta,
            RoughnessUncertaintySummary(
                status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                window_shape_pixels=win_shape,
                window_dimensions_m=win_dims,
                invalid_neighborhood_fraction=round(inv_frac, 4),
                notes=[
                    "TRI roughness uncertainty is UNQUANTIFIED without verified elevation sigma_z.",
                    f"TRI summarizes relief over {win_dims['width_m']:.1f} x {win_dims['height_m']:.1f} m window; sub-pixel cobbles are unresolved.",
                ],
            ),
        )

    nrows, ncols = elevation_grid.shape
    rx = int(tri_meta["window_half_pixels_x"])
    ry = int(tri_meta["window_half_pixels_y"])
    n_neigh = int(tri_meta["neighbor_count_required"])

    if np.ndim(sigma_z_m) == 0:
        s_scalar = float(sigma_z_m)
        if not math.isfinite(s_scalar) or s_scalar < 0.0:
            raise ValueError("Scalar sigma_z_m must be finite and non-negative.")
        sigma_arr = np.full((nrows, ncols), s_scalar, dtype=np.float64)
    else:
        sigma_arr = np.asarray(sigma_z_m, dtype=np.float64)
        if sigma_arr.shape != elevation_grid.shape:
            raise ValueError("sigma_z_m array shape must match elevation_grid shape.")

    z = elevation_grid.astype(np.float64)
    sig2 = np.where(np.isfinite(sigma_arr) & (sigma_arr >= 0.0), sigma_arr * sigma_arr, np.nan)
    r_slice = slice(ry, nrows - ry)
    c_slice = slice(rx, ncols - rx)

    z_c = z[r_slice, c_slice]
    s2_c = sig2[r_slice, c_slice]
    t_in = tri_arr[r_slice, c_slice]
    valid_in = np.isfinite(t_in) & np.isfinite(s2_c)

    sum_diff = np.zeros_like(z_c, dtype=np.float64)
    sum_d2_s2 = np.zeros_like(z_c, dtype=np.float64)

    for dr in range(-ry, ry + 1):
        for dc in range(-rx, rx + 1):
            if dr == 0 and dc == 0:
                continue
            nr = slice(ry + dr, nrows - ry + dr)
            nc = slice(rx + dc, ncols - rx + dc)
            valid_in &= np.isfinite(sig2[nr, nc])
            d_k = np.where(valid_in, z_c - z[nr, nc], 0.0)
            sum_diff += d_k
            sum_d2_s2 += (d_k * d_k) * np.where(valid_in, sig2[nr, nc], 0.0)

    # First-order variance where T > eps, and RMS noise floor sqrt((1 + 1/N)*sigma^2) near T ~ 0
    eps = 1e-4
    t_safe = np.maximum(t_in, eps)
    denom = float(n_neigh * n_neigh) * (t_safe * t_safe)
    lin_var_t = (((sum_diff * sum_diff) * np.where(valid_in, s2_c, 0.0)) + sum_d2_s2) / np.maximum(1e-12, denom)
    noise_floor_var = np.where(valid_in, s2_c * (1.0 + 1.0 / max(1, n_neigh)), np.nan)
    var_t = np.where(t_in > eps, lin_var_t, noise_floor_var)

    tri_sigma[r_slice, c_slice] = np.where(valid_in, np.sqrt(np.maximum(0.0, var_t)), np.nan)
    fin = tri_sigma[np.isfinite(tri_sigma)]
    inv_full = 1.0 - (float(fin.size) / float(max(1, total_cells)))

    notes: List[str] = [
        f"TRI window {win_shape} spans ~{win_dims['width_m']:.1f} x {win_dims['height_m']:.1f} m.",
        "Zero-relief planes exhibit positive TRI noise floor proportional to vertical elevation jitter.",
    ]
    if not is_empirical_error_map:
        notes.append("Propagated as scenario sensitivity bound from metadata/quantization precision — NOT an empirical roughness error band.")

    return (
        tri_arr,
        tri_sigma,
        tri_meta,
        RoughnessUncertaintySummary(
            status=(
                UncertaintyStatus.QUANTIFIED_FROM_RASTER_ERROR_BAND
                if is_empirical_error_map
                else UncertaintyStatus.QUANTIFIED_FROM_METADATA
            ),
            metric_kind=MeasurementQuantityKind.STANDARD_DEVIATION,
            window_shape_pixels=win_shape,
            window_dimensions_m=win_dims,
            mean_tri_sigma_m=round(float(np.mean(fin)), 4) if fin.size else None,
            max_tri_sigma_m=round(float(np.max(fin)), 4) if fin.size else None,
            invalid_neighborhood_fraction=round(inv_full, 4),
            notes=notes,
        ),
    )
