"""
MARSCOPE Corridor Uncertainty Assessment
Martian Surface Intelligence & Exploration System

Drives DEM vertical uncertainty notes directly from inspected PDS3/catalog metadata
and propagated derivative uncertainty summaries rather than hardcoded guesses.
"""

from __future__ import annotations

from typing import List, Optional

from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    CorridorUncertaintySummary,
)
from app.terrain_uncertainty.models import UncertaintyStatus
from app.terrain_uncertainty.schemas import (
    DatasetUncertaintyProfile,
    SlopeUncertaintySummary,
)


def assess_corridor_uncertainty(
    *,
    segments: List[CorridorSegmentAssessment],
    native_resolution_m: float,
    corridor_valid_fraction: float,
    optical_available: bool,
    dataset_uncertainty_profile: Optional[DatasetUncertaintyProfile] = None,
    slope_uncertainty_summary: Optional[SlopeUncertaintySummary] = None,
) -> CorridorUncertaintySummary:
    """Summarize geometric precision, empirical uncertainty gaps, and unquantified physical unknowns."""
    res_limited = sum(1 for s in segments if s.native_resolution_m > 2.0)
    nodata_segs = sum(1 for s in segments if s.valid_data_coverage_fraction < 0.95)

    if dataset_uncertainty_profile is not None:
        status = dataset_uncertainty_profile.overall_elevation_uncertainty_status
        nom_metric = next(
            (m for m in dataset_uncertainty_profile.elevation_uncertainty_metrics if m.metric_name == "nominal_vertical_precision_metadata"),
            None,
        )
        quant_metric = next(
            (m for m in dataset_uncertainty_profile.elevation_uncertainty_metrics if m.metric_name == "elevation_quantization_step"),
            None,
        )
        if status == UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY and quant_metric is not None:
            dem_note = (
                f"{dataset_uncertainty_profile.product_id} ({native_resolution_m:.1f} m/px): integer-quantized DEM "
                f"with {quant_metric.value} m quantization step (lower bound ONLY; inter-track interpolation errors up to ~12 km unquantified)."
            )
        elif status == UncertaintyStatus.QUANTIFIED_FROM_METADATA and nom_metric is not None:
            dem_note = (
                f"{dataset_uncertainty_profile.product_id} ({native_resolution_m:.2f} m/px): catalog reports nominal "
                f"vertical precision ~{nom_metric.value:.2f} m metadata; attached PDS3 header & raster contain NO per-pixel "
                "vertical sigma band (empirical local RMSE unquantified)."
            )
        elif dataset_uncertainty_profile.has_per_pixel_error_raster:
            dem_note = (
                f"{dataset_uncertainty_profile.product_id} ({native_resolution_m:.2f} m/px): per-pixel empirical vertical error raster verified."
            )
        else:
            dem_note = (
                f"{dataset_uncertainty_profile.product_id} ({native_resolution_m:.2f} m/px): vertical accuracy UNQUANTIFIED in PDS3 label and catalog."
            )
        if slope_uncertainty_summary is not None and slope_uncertainty_summary.mean_slope_sigma_deg is not None:
            dem_note += (
                f" Horn 3x3 sensitivity probe mean slope sigma = {slope_uncertainty_summary.mean_slope_sigma_deg:.2f} deg "
                "(scenario bound, not empirical error map)."
            )
    else:
        dem_note = (
            f"DEM posting is {native_resolution_m:.2f} m/px. Horizontal posting NEVER establishes vertical RMSE; "
            "per-pixel empirical height error is unquantified unless explicit error raster or PDS3 vertical sigma is supplied."
        )

    unquantified: List[str] = [
        "Regolith bearing strength, cohesion, and sinkage (unmeasured from orbital DEM/ortho)",
        "Surface dust thickness and slip/friction coefficient",
        "Subsurface voids or weakly cemented crust",
        "Per-pixel empirical stereo correlation / height RMSE band (absent in PDS3 attached header)",
        "Co-registration lateral tiepoint RMS across DEM/ortho/rover coordinates",
    ]
    if not optical_available:
        unquantified.append("Local high-resolution optical albedo/shadow verification unavailable")

    if dataset_uncertainty_profile is not None:
        for lim in dataset_uncertainty_profile.limitations:
            if lim not in unquantified:
                unquantified.append(lim)

    return CorridorUncertaintySummary(
        dem_vertical_precision_note=dem_note,
        horizontal_resolution_m=native_resolution_m,
        corridor_valid_fraction=round(corridor_valid_fraction, 4),
        resolution_limited_segments=res_limited,
        nodata_segments=nodata_segs,
        coordinate_uncertainty_note=(
            "IAU2000:49900 planetocentric; rover observation offsets reflect PDS/JPL traverse "
            "localization uncertainty and cross-layer misalignment may affect boundary slopes."
        ),
        unquantified_limitations=unquantified,
    )
