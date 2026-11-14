"""
MARSCOPE Coupled Terrain Uncertainty & 3-State Traversability Propagation
Combines elevation uncertainty inventory, Horn 3x3 slope sigma, Riley TRI sigma,
cross-dataset registration, feature observability, and backend-exact overlay legends.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.schemas.dataset import Dataset
from app.terrain.mesh import PALETTE_STOPS
from app.terrain_uncertainty.models import (
    TerrainTraversabilityState,
    UncertaintyStatus,
)
from app.terrain_uncertainty.registration_uncertainty import assess_cross_dataset_registration
from app.terrain_uncertainty.resolution_analysis import evaluate_feature_observability
from app.terrain_uncertainty.roughness_uncertainty import propagate_tri_roughness_uncertainty
from app.terrain_uncertainty.schemas import (
    CorridorUncertaintyProfile,
    DatasetUncertaintyProfile,
    OverlayLegendDescriptor,
    TraversabilityCellBreakdown,
)
from app.terrain_uncertainty.slope_uncertainty import propagate_horn_slope_uncertainty


def classify_three_state_traversability_grid(
    elevation_grid: np.ndarray,
    slope_deg: np.ndarray,
    *,
    max_slope_deg: float = 20.0,
    dem_resolution_m: Optional[float] = None,
    nodata_mask: Optional[np.ndarray] = None,
    local_slope_suitable_threshold_m: float = 5.0,
) -> Tuple[np.ndarray, TraversabilityCellBreakdown]:
    """
    Classify every cell into strict 3-state semantics:
      - 0: UNKNOWN_INSUFFICIENTLY_OBSERVED (no-data, border NaN gradient, or coarse DEM unsuitable for local slope)
      - 1: EVALUATED (valid elevation + valid 3x3 gradient + local slope <= max_slope_deg + adequate resolution)
      - 2: KNOWN_CONSTRAINT_EXCLUSION (valid 3x3 slope > max_slope_deg)
    Never merges unmapped/coarse terrain into flat "safe" terrain.
    """
    nodata = np.zeros_like(elevation_grid, dtype=bool) if nodata_mask is None else np.asarray(nodata_mask, dtype=bool)
    valid_elev = np.isfinite(elevation_grid) & (~nodata)
    valid_slope = np.isfinite(slope_deg)
    coarse_insufficient = (dem_resolution_m is not None) and (dem_resolution_m > local_slope_suitable_threshold_m)

    state_grid = np.zeros(elevation_grid.shape, dtype=np.uint8)  # 0 = UNKNOWN_INSUFFICIENTLY_OBSERVED
    if not coarse_insufficient:
        observed = valid_elev & valid_slope
        excluded = observed & (slope_deg > float(max_slope_deg))
        evaluated = observed & (~excluded)
        state_grid[evaluated] = 1
        state_grid[excluded] = 2

    total = max(1, int(state_grid.size))
    n_eval = int(np.count_nonzero(state_grid == 1))
    n_excl = int(np.count_nonzero(state_grid == 2))
    n_unk = int(np.count_nonzero(state_grid == 0))

    present: List[TerrainTraversabilityState] = []
    if n_eval > 0:
        present.append(TerrainTraversabilityState.EVALUATED)
    if n_excl > 0:
        present.append(TerrainTraversabilityState.KNOWN_CONSTRAINT_EXCLUSION)
    if n_unk > 0:
        present.append(TerrainTraversabilityState.UNKNOWN_INSUFFICIENTLY_OBSERVED)

    return (
        state_grid,
        TraversabilityCellBreakdown(
            evaluated_cell_count=n_eval,
            known_exclusion_cell_count=n_excl,
            unknown_insufficient_cell_count=n_unk,
            evaluated_fraction=round(n_eval / total, 4),
            known_exclusion_fraction=round(n_excl / total, 4),
            unknown_insufficient_fraction=round(n_unk / total, 4),
            quantified_uncertainty_cell_fraction=0.0,
            unquantified_uncertainty_cell_fraction=round((n_eval + n_excl) / total, 4),
            traversability_states_present=present,
        ),
    )


def build_prompt16_overlay_legends(
    *,
    dataset: Dataset,
    optical_available: bool,
    dem_profile: DatasetUncertaintyProfile,
    elev_range: Optional[Tuple[float, float]] = None,
    tri_range: Optional[Tuple[float, float]] = None,
    slope_sigma_range: Optional[Tuple[float, float]] = None,
    max_slope_deg: float = 20.0,
) -> Dict[str, OverlayLegendDescriptor]:
    """
    Produce self-describing legend & availability metadata matched pixel-for-pixel to
    rendered overlay PNG textures.
    """
    def _stops(key: str) -> List[Dict[str, Any]]:
        return [{"t": t, "rgb": list(rgb), "hex": hx} for (t, rgb, hx) in PALETTE_STOPS[key]["stops"]]

    elev_min, elev_max = elev_range if elev_range else (-4500.0, -3500.0)
    tri_min, tri_max = tri_range if tri_range else (0.0, 5.0)
    sig_min, sig_max = slope_sigma_range if slope_sigma_range else (0.0, 15.0)

    is_quant_empirical = dem_profile.has_per_pixel_error_raster
    has_probe = dem_profile.overall_elevation_uncertainty_status in {
        UncertaintyStatus.QUANTIFIED_FROM_METADATA,
        UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY,
    }
    probe_status_class = "quantified" if is_quant_empirical else ("metadata_sensitivity" if has_probe else "unquantified")

    return {
        "ortho": OverlayLegendDescriptor(
            overlay_id="ortho",
            label="HiRISE Grayscale / Warm Orthophoto",
            available=optical_available,
            unavailable_reason=None if optical_available else f"No paired co-registered orthophoto available locally for '{dataset.id}'.",
            units="DN (0-255 radiometric brightness)",
            normalization="source_reflectance",
            method="Bilinear resampling of paired HiRISE RDR orthophoto",
            uncertainty_classification="reflectance",
            no_data_meaning="Transparent alpha=0 indicates outside optical swath footprint or null pixels.",
        ),
        "elevation": OverlayLegendDescriptor(
            overlay_id="elevation",
            label="Surface Elevation (DTM Height)",
            available=True,
            units="m (MOLA Areoid datum)",
            normalization="linear",
            method="Normalized elevation field over valid clipped study window",
            uncertainty_classification=probe_status_class,
            vmin=round(elev_min, 2),
            vmax=round(elev_max, 2),
            palette_stops=_stops("elevation"),
        ),
        "slope": OverlayLegendDescriptor(
            overlay_id="slope",
            label="Local Slope Angle (Horn 3x3)",
            available=True,
            units="deg",
            normalization="linear",
            method="Horn (1981) 3x3 finite-difference surface gradient arctan(|grad z|)",
            uncertainty_classification=probe_status_class,
            vmin=0.0,
            vmax=35.0,
            palette_stops=_stops("slope"),
        ),
        "roughness": OverlayLegendDescriptor(
            overlay_id="roughness",
            label="Terrain Ruggedness Index (Riley RMS TRI)",
            available=True,
            units="m",
            normalization="linear",
            method="Riley et al. RMS elevation difference over ~5 m radius neighborhood",
            uncertainty_classification=probe_status_class,
            vmin=round(tri_min, 3),
            vmax=round(max(tri_max, 0.5), 3),
            palette_stops=_stops("roughness"),
        ),
        "uncertainty_status": OverlayLegendDescriptor(
            overlay_id="uncertainty_status",
            label="Measurement Uncertainty Status",
            available=True,
            units="categorical epistemic status",
            normalization="categorical",
            method="Classifies empirical raster sigma vs nominal catalog/quantization bound vs missing/edge no-data",
            uncertainty_classification="categorical",
            categories=[
                {"label": "Quantified Empirical Raster Error", "hex": "#16a34a"},
                {"label": "Nominal Catalog Precision / Quantization Bound Only", "hex": "#eab308"},
                {"label": "Unquantified Slope/Height Derivative (Edge or Missing)", "hex": "#dc2626"},
                {"label": "No-Data / Outside Coverage", "hex": "#475569"},
            ],
        ),
        "traversability_state": OverlayLegendDescriptor(
            overlay_id="traversability_state",
            label=f"3-State Traversability (Cap <= {max_slope_deg:.0f} deg)",
            available=True,
            units="categorical traversability class",
            normalization="categorical",
            method=f"Separates evaluated slope <= {max_slope_deg:.0f} deg, slope > cap exclusion, and unknown/coarse cells",
            uncertainty_classification="categorical",
            categories=[
                {"label": f"Evaluated Traversable (slope <= {max_slope_deg:.0f} deg)", "hex": "#10b981"},
                {"label": f"Known Constraint Exclusion (slope > {max_slope_deg:.0f} deg)", "hex": "#ef4444"},
                {"label": "Unknown / Insufficiently Observed", "hex": "#f59e0b"},
            ],
        ),
        "observability": OverlayLegendDescriptor(
            overlay_id="observability",
            label="Sensor Feature Observability Scale",
            available=True,
            units="m/pixel resolution adequacy",
            normalization="categorical",
            method="Separates m-scale DEM slope coverage from sub-meter optical boulder/hazard resolution limits",
            uncertainty_classification="categorical",
            categories=[
                {"label": "m-Scale Slope Resolved + Orthophoto Coverage (sub-0.5m Hazards Still Unresolved)", "hex": "#06b6d4"},
                {"label": "m-Scale Slope Resolved Only (No Sub-Meter Ortho Footprint)", "hex": "#3b82f6"},
                {"label": "Coarse Regional DEM Only (Local Slope BELOW_SOURCE_RESOLUTION)", "hex": "#a855f7"},
            ],
        ),
        "slope_uncertainty_probe": OverlayLegendDescriptor(
            overlay_id="slope_uncertainty_probe",
            label="Horn 3x3 Slope Sensitivity Probe (sigma_slope)",
            available=has_probe or is_quant_empirical,
            unavailable_reason=None
            if (has_probe or is_quant_empirical)
            else "Dataset supplies neither per-pixel error band nor nominal vertical precision metadata for sensitivity propagation.",
            units="deg (propagated 1-sigma scenario probe)",
            normalization="linear",
            method="Analytical Horn (1981) 3x3 Jacobian propagation of dataset nominal/quantization sigma_z",
            uncertainty_classification=probe_status_class,
            vmin=round(sig_min, 2),
            vmax=round(max(sig_max, 5.0), 2),
            palette_stops=[
                {"t": 0.0, "rgb": [30, 64, 175], "hex": "#1e40af"},
                {"t": 0.4, "rgb": [6, 182, 212], "hex": "#06b6d4"},
                {"t": 0.75, "rgb": [245, 158, 11], "hex": "#f59e0b"},
                {"t": 1.0, "rgb": [220, 38, 38], "hex": "#dc2626"},
            ],
        ),
    }


def evaluate_coupled_corridor_uncertainty(
    *,
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    dem_dataset: Dataset,
    dem_profile: DatasetUncertaintyProfile,
    optical_dataset: Optional[Dataset] = None,
    additional_datasets: Optional[List[Dataset]] = None,
    nodata_mask: Optional[np.ndarray] = None,
    max_slope_deg: float = 20.0,
    neighborhood_radius_meters: float = 5.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, CorridorUncertaintyProfile]:
    """
    Propagate DEM uncertainty profile through slope, TRI, 3-state traversability, registration,
    and resolution observability for a clipped terrain array.
    """
    probe_sigma_z: Optional[float] = None
    basis_desc = "No empirical sigma raster or metadata precision available."
    for m in dem_profile.elevation_uncertainty_metrics:
        if m.metric_name == "nominal_vertical_precision_metadata" and m.value is not None:
            probe_sigma_z = float(m.value)
            basis_desc = (
                f"Scenario probe using catalog nominal vertical precision sigma_z={probe_sigma_z:.3f} m "
                f"({dem_dataset.product_id}); NOT an empirical pixel error raster."
            )
            break
        if m.metric_name == "quantization_uniform_standard_deviation" and m.value is not None:
            probe_sigma_z = float(m.value)
            basis_desc = (
                f"Lower-bound probe using integer quantization SD sigma_z={probe_sigma_z:.3f} m "
                f"({dem_dataset.product_id}); excludes inter-track interpolation errors."
            )
            break

    slope_deg, slope_sigma_deg, slope_summary = propagate_horn_slope_uncertainty(
        elevation_grid=elevation_grid,
        dx_meters=dx_meters,
        dy_meters=dy_meters,
        sigma_z_m=probe_sigma_z,
        nodata_mask=nodata_mask,
        is_empirical_error_map=dem_profile.has_per_pixel_error_raster,
        basis_description=basis_desc,
    )

    tri_m, tri_sigma_m, _tri_meta, tri_summary = propagate_tri_roughness_uncertainty(
        elevation_grid=elevation_grid,
        dx_meters=dx_meters,
        dy_meters=dy_meters,
        sigma_z_m=probe_sigma_z,
        nodata_mask=nodata_mask,
        neighborhood_radius_meters=neighborhood_radius_meters,
        is_empirical_error_map=dem_profile.has_per_pixel_error_raster,
    )

    state_grid, trav_breakdown = classify_three_state_traversability_grid(
        elevation_grid=elevation_grid,
        slope_deg=slope_deg,
        max_slope_deg=max_slope_deg,
        dem_resolution_m=dem_dataset.horizontal_resolution_meters,
        nodata_mask=nodata_mask,
    )
    if dem_profile.has_per_pixel_error_raster:
        known_frac = round(trav_breakdown.evaluated_fraction + trav_breakdown.known_exclusion_fraction, 4)
        trav_breakdown.quantified_uncertainty_cell_fraction = known_frac
        trav_breakdown.unquantified_uncertainty_cell_fraction = 0.0

    reg_result = assess_cross_dataset_registration(
        dem_dataset=dem_dataset,
        optical_dataset=optical_dataset,
        additional_datasets=additional_datasets,
    )
    obs_records, neg_ev = evaluate_feature_observability(
        dem_dataset_id=dem_dataset.id,
        dem_resolution_m=dem_dataset.horizontal_resolution_meters,
        optical_dataset_id=optical_dataset.id if optical_dataset else None,
        optical_resolution_m=optical_dataset.horizontal_resolution_meters if optical_dataset else None,
    )

    fin_z = elevation_grid[np.isfinite(elevation_grid)]
    fin_tri = tri_m[np.isfinite(tri_m)]
    fin_sig = slope_sigma_deg[np.isfinite(slope_sigma_deg)]
    legends = build_prompt16_overlay_legends(
        dataset=dem_dataset,
        optical_available=optical_dataset is not None,
        dem_profile=dem_profile,
        elev_range=(float(np.min(fin_z)), float(np.max(fin_z))) if fin_z.size > 0 else None,
        tri_range=(float(np.min(fin_tri)), float(np.max(fin_tri))) if fin_tri.size > 0 else None,
        slope_sigma_range=(0.0, float(np.percentile(fin_sig, 98))) if fin_sig.size > 0 else None,
        max_slope_deg=max_slope_deg,
    )

    return (
        slope_deg,
        slope_sigma_deg,
        tri_m,
        state_grid,
        tri_sigma_m,
        CorridorUncertaintyProfile(
            dataset_profile=dem_profile,
            slope_uncertainty=slope_summary,
            roughness_uncertainty=tri_summary,
            registration_uncertainty=reg_result,
            observability=obs_records,
            negative_evidence=neg_ev,
            traversability_breakdown=trav_breakdown,
            overlay_legends=legends,
        ),
    )
