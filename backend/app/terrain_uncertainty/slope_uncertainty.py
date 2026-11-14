"""
MARSCOPE Horn 3x3 Slope Uncertainty Propagation
Implements exact analytical linearized Jacobian variance propagation matching
`app.terrain.slope.compute_horn_gradients` neighborhood geometry and sign convention.

Strictly distinguishes empirical per-pixel error maps from metadata sensitivity bounds
and reports NaN whenever any 3x3 neighbor lacks valid elevation or valid sigma.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from app.terrain.slope import compute_horn_gradients
from app.terrain_uncertainty.models import MeasurementQuantityKind, UncertaintyStatus
from app.terrain_uncertainty.schemas import SlopeUncertaintySummary


def propagate_horn_slope_uncertainty(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    *,
    sigma_z_m: Optional[Union[float, np.ndarray]] = None,
    nodata_mask: Optional[np.ndarray] = None,
    vertical_units: str = "meters",
    is_empirical_error_map: bool = False,
    basis_description: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray, SlopeUncertaintySummary]:
    """
    Propagate vertical elevation standard deviation `sigma_z_m` through Horn's (1981) 3x3
    finite-difference slope formula:
        gx = ((c + 2f + i) - (a + 2d + g)) / (8 * dx)
        gy = ((a + 2b + c) - (g + 2h + i)) / (8 * dy)
        slope = arctan(sqrt(gx^2 + gy^2))

    Args:
        elevation_grid: 2D array of elevations (m).
        dx_meters, dy_meters: Metric cell spacing.
        sigma_z_m: Scalar or 2D per-pixel vertical SD (m). If None, returns unquantified summary.
        nodata_mask: Optional boolean mask where True indicates no-data.
        is_empirical_error_map: True only when `sigma_z_m` comes from an actual raster error band.

    Returns:
        (slope_deg, slope_sigma_deg, summary)
    """
    gx, gy, valid_3x3 = compute_horn_gradients(
        elevation_grid,
        dx_meters,
        dy_meters,
        nodata_mask=nodata_mask,
        vertical_units=vertical_units,
    )
    grad_mag = np.full_like(gx, np.nan)
    slope_deg = np.full_like(gx, np.nan)
    grad_mag[valid_3x3] = np.hypot(gx[valid_3x3], gy[valid_3x3])
    slope_deg[valid_3x3] = np.degrees(np.arctan(grad_mag[valid_3x3]))

    slope_sigma_deg = np.full_like(gx, np.nan)
    total_cells = int(elevation_grid.size)
    invalid_frac = 1.0 - (float(np.count_nonzero(valid_3x3)) / float(max(1, total_cells)))

    if sigma_z_m is None:
        return (
            slope_deg,
            slope_sigma_deg,
            SlopeUncertaintySummary(
                status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                metric_kind=MeasurementQuantityKind.UNQUANTIFIED,
                basis_sigma_z_m=None,
                basis_description=basis_description
                or "No empirical elevation error raster or quantization/precision sigma provided.",
                is_empirical_error_map=False,
                is_metadata_sensitivity_probe=False,
                invalid_neighborhood_fraction=round(invalid_frac, 4),
                notes=[
                    "Horn 3x3 slope sigma is UNQUANTIFIED without empirical vertical RMSE or a declared precision probe.",
                    "Boundary cells and 3x3 neighborhoods touching no-data strictly return NaN.",
                ],
            ),
        )

    nrows, ncols = elevation_grid.shape
    if np.ndim(sigma_z_m) == 0:
        s_scalar = float(sigma_z_m)
        if not math.isfinite(s_scalar) or s_scalar < 0.0:
            raise ValueError("Scalar sigma_z_m must be finite and non-negative.")
        sigma_arr = np.full((nrows, ncols), s_scalar, dtype=np.float64)
        scalar_basis = s_scalar
    else:
        sigma_arr = np.asarray(sigma_z_m, dtype=np.float64)
        if sigma_arr.shape != elevation_grid.shape:
            raise ValueError("Per-pixel sigma_z_m array shape must match elevation_grid shape.")
        fin_sig = sigma_arr[np.isfinite(sigma_arr) & (sigma_arr >= 0.0)]
        scalar_basis = float(np.mean(fin_sig)) if fin_sig.size > 0 else 0.0

    # Variance of each pixel in the 3x3 window:
    # a b c  -> [0:-2, 0:-2] [0:-2, 1:-1] [0:-2, 2:]
    # d e f  -> [1:-1, 0:-2] [1:-1, 1:-1] [1:-1, 2:]
    # g h i  -> [2:,   0:-2] [2:,   1:-1] [2:,   2:]
    sig2 = np.where(np.isfinite(sigma_arr) & (sigma_arr >= 0.0), sigma_arr * sigma_arr, np.nan)
    va = sig2[0:-2, 0:-2]
    vb = sig2[0:-2, 1:-1]
    vc = sig2[0:-2, 2:]
    vd = sig2[1:-1, 0:-2]
    ve = sig2[1:-1, 1:-1]
    vf = sig2[1:-1, 2:]
    vg = sig2[2:, 0:-2]
    vh = sig2[2:, 1:-1]
    vi = sig2[2:, 2:]

    valid_inner = (
        valid_3x3[1:-1, 1:-1]
        & np.isfinite(va)
        & np.isfinite(vb)
        & np.isfinite(vc)
        & np.isfinite(vd)
        & np.isfinite(ve)
        & np.isfinite(vf)
        & np.isfinite(vg)
        & np.isfinite(vh)
        & np.isfinite(vi)
    )

    var_gx = (vc + 4.0 * vf + vi + va + 4.0 * vd + vg) / (64.0 * dx_meters * dx_meters)
    var_gy = (va + 4.0 * vb + vc + vg + 4.0 * vh + vi) / (64.0 * dy_meters * dy_meters)
    # Exact cross-covariance from matching Horn corner signs
    cov_gxy = (-va + vc + vg - vi) / (64.0 * dx_meters * dy_meters)

    gx_in = gx[1:-1, 1:-1]
    gy_in = gy[1:-1, 1:-1]
    g_in = grad_mag[1:-1, 1:-1]

    var_slope_rad = np.full_like(g_in, np.nan)
    near_flat_count = 0
    valid_count = int(np.count_nonzero(valid_inner))

    if valid_count > 0:
        g_safe = np.maximum(g_in, 1e-6)
        denom = (g_safe * g_safe) * ((1.0 + g_safe * g_safe) ** 2)
        lin_var = ((gx_in * gx_in) * var_gx + (gy_in * gy_in) * var_gy + 2.0 * gx_in * gy_in * cov_gxy) / denom

        # Near-flat regime (g <= grad_noise): arctan(sqrt(gx^2 + gy^2)) has directional gradient
        # noise envelope sqrt(var_gx + var_gy) / (1 + g^2)
        grad_noise = np.sqrt(np.maximum(0.0, var_gx + var_gy))
        flat_mask = valid_inner & (g_in <= np.maximum(1e-4, 1.5 * grad_noise))
        near_flat_count = int(np.count_nonzero(flat_mask))

        fallback_var = np.maximum(0.5 * (var_gx + var_gy), lin_var) / ((1.0 + g_in * g_in) ** 2)
        combined_var = np.where(flat_mask, np.maximum(lin_var, fallback_var), lin_var)
        var_slope_rad = np.where(valid_inner, np.maximum(0.0, combined_var), np.nan)

    sigma_deg_inner = np.degrees(np.sqrt(var_slope_rad))
    slope_sigma_deg[1:-1, 1:-1] = sigma_deg_inner

    fin_sig_deg = slope_sigma_deg[np.isfinite(slope_sigma_deg)]
    has_fin = fin_sig_deg.size > 0
    inv_frac_full = 1.0 - (float(fin_sig_deg.size) / float(max(1, total_cells)))

    notes: List[str] = [
        "Propagated assuming independent vertical elevation pixel errors across the Horn 3x3 kernel; spatially correlated DTM jitter reduces local slope error relative to uncorrelated bounds.",
    ]
    if near_flat_count > 0:
        notes.append(
            f"{near_flat_count}/{max(1, valid_count)} cells sit near flat terrain where nonlinear gradient magnitude sqrt(gx^2+gy^2) exhibits positive noise floor."
        )
    if not is_empirical_error_map:
        notes.append(
            "Derived as a scenario sensitivity bound from metadata precision/quantization input — NOT a verified per-pixel empirical stereo error map."
        )

    status = (
        UncertaintyStatus.QUANTIFIED_FROM_RASTER_ERROR_BAND
        if is_empirical_error_map
        else UncertaintyStatus.QUANTIFIED_FROM_METADATA
    )
    return (
        slope_deg,
        slope_sigma_deg,
        SlopeUncertaintySummary(
            status=status,
            metric_kind=MeasurementQuantityKind.STANDARD_DEVIATION,
            basis_sigma_z_m=round(scalar_basis, 4),
            basis_description=basis_description
            or (
                "Empirical per-pixel vertical sigma raster"
                if is_empirical_error_map
                else f"Scenario vertical precision probe sigma_z={scalar_basis:.3f} m (metadata/quantization sensitivity)"
            ),
            is_empirical_error_map=is_empirical_error_map,
            is_metadata_sensitivity_probe=not is_empirical_error_map,
            mean_slope_sigma_deg=round(float(np.mean(fin_sig_deg)), 3) if has_fin else None,
            max_slope_sigma_deg=round(float(np.max(fin_sig_deg)), 3) if has_fin else None,
            median_slope_sigma_deg=round(float(np.median(fin_sig_deg)), 3) if has_fin else None,
            near_flat_bias_affected_fraction=round(float(near_flat_count) / float(max(1, valid_count)), 4)
            if valid_count > 0
            else None,
            invalid_neighborhood_fraction=round(inv_frac_full, 4),
            notes=notes,
        ),
    )
