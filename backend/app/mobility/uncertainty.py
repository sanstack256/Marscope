"""
MARSCOPE Terrain & Mobility Uncertainty and Numerical Precision Module
Martian Surface Intelligence & Exploration System

Explicitly separates:
  - Source measurement / altimetry uncertainty
  - DEM vertical quantization and radial accuracy
  - Horizontal positional / pixel footprint uncertainty
  - Processing / resampling uncertainty
  - Finite-difference derivative sensitivity (slope, aspect, TRI)
  - User-configured traversal model parameter uncertainty

Never sums or combines incompatible physical uncertainty categories into a single scalar.
"""

import math
from typing import Optional

from app.mobility.schemas import (
    MobilityScenario,
    MobilityUncertaintySummary,
    UncertaintyComponentRecord,
)


def build_mobility_uncertainty_summary(
    *,
    dataset_id: str,
    product_id: str,
    dx_meters: Optional[float],
    dy_meters: Optional[float],
    vertical_units: str = "meters",
    is_integer_dem: bool = True,
    sampling_method: str = "nearest_whole_pixel",
    scenario: Optional[MobilityScenario] = None,
) -> MobilityUncertaintySummary:
    """
    Construct an honest, multi-component uncertainty summary for terrain and mobility outputs.
    """
    is_mola_megdr = "megt" in product_id.lower() or "mola" in dataset_id.lower()

    # 1. Source measurement uncertainty (MOLA laser altimeter radial accuracy)
    if is_mola_megdr:
        src_comp = UncertaintyComponentRecord(
            component_id="mola_pedr_radial_orbit_altimetry_accuracy",
            category="source_measurement_uncertainty",
            available=True,
            value=1.0,
            units="meters",
            representation="approximate_1sigma_radial_topology_accuracy",
            provenance="NASA PDS MGS-M-MOLA-5-MEGDR-L3-V1.0 documentation (Smith et al., 2001, JGR 106(E10), 23689-23722)",
            notes=(
                "Individual MOLA shots have ~37.5 cm vertical range precision and ~1 m radial orbit accuracy, "
                "but gridded MEGDR cells average multiple orbits and interpolate across inter-track gaps."
            ),
        )
    else:
        src_comp = UncertaintyComponentRecord(
            component_id="source_altimetry_measurement_uncertainty",
            category="source_measurement_uncertainty",
            available=False,
            value=None,
            units=None,
            representation="unreported_in_local_label",
            provenance="Local PDS label metadata",
            notes="Per-pixel source measurement uncertainty is not embedded in the local raster label.",
        )

    # 2. DEM vertical quantization & gridding accuracy
    if is_integer_dem:
        vert_comp = UncertaintyComponentRecord(
            component_id="dem_int16_vertical_quantization",
            category="dem_vertical_accuracy",
            available=True,
            value=0.5,
            units=vertical_units,
            representation="half_lsb_integer_quantization_step",
            provenance="16-bit signed integer elevation storage in source PDS3 IMG (1 m integer step -> +/- 0.5 m quantization)",
            notes=(
                "Does not include sub-pixel topographic relief variance within the multi-kilometer cell footprint, "
                "which can exceed tens to hundreds of meters in rugged cratered terrain."
            ),
        )
    else:
        vert_comp = UncertaintyComponentRecord(
            component_id="dem_vertical_gridding_accuracy",
            category="dem_vertical_accuracy",
            available=False,
            value=None,
            units=vertical_units,
            representation="unreported_per_pixel_vertical_sigma",
            provenance="Source DEM raster",
            notes="Floating-point DEM without per-cell vertical error band.",
        )

    # 3. Horizontal positional / footprint uncertainty
    if dx_meters is not None and dy_meters is not None and dx_meters > 0 and dy_meters > 0:
        half_diag = 0.5 * math.hypot(dx_meters, dy_meters)
        horiz_comp = UncertaintyComponentRecord(
            component_id="dem_cell_horizontal_footprint_half_diagonal",
            category="horizontal_positional_accuracy",
            available=True,
            value=round(half_diag, 3),
            units="meters",
            representation="cell_half_diagonal_footprint_radius",
            provenance=f"Computed from metric grid spacing dx={dx_meters:.2f} m, dy={dy_meters:.2f} m on IAU2000 Mars sphere",
            notes=(
                f"A point coordinate mapped to a {dx_meters:.1f} m x {dy_meters:.1f} m DEM cell represents "
                f"topography aggregated over a half-diagonal radius of {half_diag:.1f} m."
            ),
        )
    else:
        horiz_comp = UncertaintyComponentRecord(
            component_id="dem_cell_horizontal_footprint_half_diagonal",
            category="horizontal_positional_accuracy",
            available=False,
            value=None,
            units="meters",
            representation="unavailable",
            provenance="Grid spacing unavailable",
            notes="Horizontal cell footprint radius cannot be computed without valid metric pixel spacing.",
        )

    # 4. Processing / resampling uncertainty
    proc_comp = UncertaintyComponentRecord(
        component_id="raster_window_and_sampling_method",
        category="processing_resampling_uncertainty",
        available=True,
        value=0.0 if "nearest" in sampling_method else None,
        units="meters" if "nearest" in sampling_method else None,
        representation=f"sampling_mode:{sampling_method}",
        provenance="MARSCOPE DEMProcessingService v2.0.0 whole-pixel window clipping (no_expansion_v1)",
        notes=(
            "Whole-pixel window clipping preserves native pixel values without resampling smoothing. "
            "Pixel boundary snapping is documented explicitly in analysis_footprint_bounds."
        ),
    )

    # 5. Derivative sensitivity (Horn 3x3 slope sensitivity to +/- 0.5 m quantization)
    if dx_meters is not None and dy_meters is not None and dx_meters > 0 and dy_meters > 0:
        # Minimum detectable gradient step from 1 m quantization across 2*dx baseline
        min_step_deg = math.degrees(math.atan(1.0 / (2.0 * min(dx_meters, dy_meters))))
        deriv_comp = UncertaintyComponentRecord(
            component_id="horn_3x3_quantization_sensitivity",
            category="derivative_sensitivity",
            available=True,
            value=round(min_step_deg, 5),
            units="degrees",
            representation="single_lsb_elevation_step_slope_sensitivity",
            provenance="Analytical sensitivity of Horn 3x3 central difference to a 1 m vertical quantization step over 2*dx",
            notes=(
                "Slope, aspect, and TRI require a complete valid 3x3 neighborhood (8 neighbors + center). "
                "Cells adjacent to the window edge or any no-data pixel are explicitly marked unavailable."
            ),
        )
    else:
        deriv_comp = UncertaintyComponentRecord(
            component_id="horn_3x3_quantization_sensitivity",
            category="derivative_sensitivity",
            available=False,
            value=None,
            units="degrees",
            representation="unavailable",
            provenance="Horn 3x3 finite difference",
            notes="Grid spacing unavailable for derivative sensitivity calculation.",
        )

    # 6. Model parameter uncertainty
    if scenario is not None and scenario.reference_walking_speed_m_per_s is not None:
        model_comp = UncertaintyComponentRecord(
            component_id="scenario_assumption_parameter_uncertainty",
            category="model_parameter_uncertainty",
            available=False,
            value=None,
            units="seconds",
            representation="user_configured_deterministic_scenario_parameters",
            provenance=f"MobilityScenario '{scenario.scenario_id}' (v{scenario.version})",
            notes=(
                "Traversal speeds and optional slope/roughness adjustments are deterministic evaluations "
                "of user-configured planning assumptions, not calibrated human-factors probability distributions."
            ),
        )
    else:
        model_comp = UncertaintyComponentRecord(
            component_id="scenario_assumption_parameter_uncertainty",
            category="model_parameter_uncertainty",
            available=False,
            value=None,
            units=None,
            representation="no_walking_speed_configured",
            provenance="MobilityScenario",
            notes="No reference walking speed is configured; traversal time is not estimated.",
        )

    return MobilityUncertaintySummary(
        source_dataset_id=dataset_id,
        source_product_id=product_id,
        combined_scalar_uncertainty_withheld=True,
        components=[src_comp, vert_comp, horiz_comp, proc_comp, deriv_comp, model_comp],
        numerical_precision_policy={
            "internal_computation_dtype": "float64",
            "api_rounding": {
                "elevation_meters": "4 decimal places (or exact integer for int16 source)",
                "slope_deg": "4 decimal places",
                "aspect_deg": "4 decimal places",
                "roughness_tri_meters": "4 decimal places",
                "distance_meters": "3 decimal places",
                "time_seconds": "3 decimal places",
            },
            "rounding_stage": "output_serialization_only",
        },
    )
