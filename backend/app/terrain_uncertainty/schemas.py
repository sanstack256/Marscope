"""
MARSCOPE Terrain Uncertainty, Observability, Registration & Overlay Schemas
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.terrain_uncertainty.models import (
    AnalysisScaleCategory,
    FeatureObservabilityState,
    MeasurementQuantityKind,
    TerrainTraversabilityState,
    UNCERTAINTY_MODEL_VERSION,
    UncertaintyStatus,
)


class UncertaintyMetricRecord(BaseModel):
    """Explicit self-describing uncertainty record never conflating units or types."""

    metric_name: str
    metric_kind: MeasurementQuantityKind
    status: UncertaintyStatus
    value: Optional[float] = None
    units: str = "unquantified"
    confidence_level: Optional[float] = None
    is_spatial_map: bool = False
    is_quantified_empirical_error: bool = False
    source_basis: str
    notes: List[str] = Field(default_factory=list)


class DatasetUncertaintyProfile(BaseModel):
    """Real NASA PDS3 / catalog / raster uncertainty inventory for a single dataset."""

    model_version: str = UNCERTAINTY_MODEL_VERSION
    dataset_id: str
    product_id: str
    product_type: str
    crs: str
    vertical_datum: str
    horizontal_resolution_m: Optional[float] = None
    sample_bits: Optional[int] = None
    sample_type: Optional[str] = None
    is_integer_quantized: bool = False
    has_per_pixel_error_raster: bool = False
    pds_keywords_present: Dict[str, Any] = Field(default_factory=dict)
    elevation_uncertainty_metrics: List[UncertaintyMetricRecord] = Field(default_factory=list)
    overall_elevation_uncertainty_status: UncertaintyStatus
    georegistration_uncertainty: UncertaintyMetricRecord
    missing_uncertainty_fields: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class RegistrationPairAssessment(BaseModel):
    """Alignment and co-registration assessment between two planetary products."""

    primary_dataset_id: str
    secondary_dataset_id: str
    shared_crs: bool
    primary_crs: str
    secondary_crs: str
    shared_stereo_bundle: bool = False
    datum_tie_note: str
    lateral_misregistration_status: UncertaintyStatus
    nominal_co_registration_note: str
    quantified_rms_offset_m: Optional[float] = None
    cross_layer_boundary_caution: str


class RegistrationUncertaintyResult(BaseModel):
    """Corridor/region multi-dataset co-registration uncertainty report."""

    dem_dataset_id: str
    optical_dataset_id: Optional[str] = None
    overall_status: UncertaintyStatus
    pair_assessments: List[RegistrationPairAssessment] = Field(default_factory=list)
    slope_and_point_sensitivity_note: str
    limitations: List[str] = Field(default_factory=list)


class FeatureObservabilityRecord(BaseModel):
    """Observability status for one analysis scale or physical landform class."""

    category: AnalysisScaleCategory
    observability_state: FeatureObservabilityState
    source_dataset_id: str
    native_pixel_scale_m: Optional[float] = None
    minimum_resolvable_feature_size_m: Optional[float] = None
    minimum_recommended_spacing_m: float
    nyquist_factor_pixels: float = 2.0
    policy_id: str
    policy_version: str
    classification: str  # engineering_screen | resolution_limit | unvalidated_heuristic
    negative_evidence_permitted: bool = False
    negative_evidence_statement: str
    rationale: str


class NegativeEvidenceStatement(BaseModel):
    """Explicit anti-hallucination guarantee prohibiting zero-detection = safe terrain inference."""

    zero_detections_implies_obstacle_free: bool = False
    unresolved_hazard_classes: List[str] = Field(default_factory=list)
    minimum_resolvable_feature_m: Optional[float] = None
    statement: str


class SlopeUncertaintySummary(BaseModel):
    """Horn 3x3 propagated slope uncertainty summary across an evaluated window or corridor."""

    status: UncertaintyStatus
    metric_kind: MeasurementQuantityKind
    basis_sigma_z_m: Optional[float] = None
    basis_description: str
    is_empirical_error_map: bool = False
    is_metadata_sensitivity_probe: bool = False
    mean_slope_sigma_deg: Optional[float] = None
    max_slope_sigma_deg: Optional[float] = None
    median_slope_sigma_deg: Optional[float] = None
    near_flat_bias_affected_fraction: Optional[float] = None
    invalid_neighborhood_fraction: float
    analytical_formula: str = (
        "Horn (1981) 3x3 Jacobian variance propagation: Var(slope_rad) = J * Sigma_grad * J^T; "
        "uniform sigma_z gives sigma(dz/dx) = sqrt(3)*sigma_z/(4*dx)."
    )
    notes: List[str] = Field(default_factory=list)


class RoughnessUncertaintySummary(BaseModel):
    """Riley RMS TRI uncertainty and resolution completeness summary."""

    status: UncertaintyStatus
    metric_kind: MeasurementQuantityKind
    window_shape_pixels: Optional[List[int]] = None
    window_dimensions_m: Optional[Dict[str, float]] = None
    mean_tri_sigma_m: Optional[float] = None
    max_tri_sigma_m: Optional[float] = None
    invalid_neighborhood_fraction: float
    notes: List[str] = Field(default_factory=list)


class TraversabilityCellBreakdown(BaseModel):
    """Cell-level separation of terrain values, constraints, and uncertainty."""

    evaluated_cell_count: int
    known_exclusion_cell_count: int
    unknown_insufficient_cell_count: int
    evaluated_fraction: float
    known_exclusion_fraction: float
    unknown_insufficient_fraction: float
    quantified_uncertainty_cell_fraction: float
    unquantified_uncertainty_cell_fraction: float
    traversability_states_present: List[TerrainTraversabilityState] = Field(default_factory=list)


class OverlayLegendDescriptor(BaseModel):
    """Exact backend-verified legend metadata paired with rendered PNG overlay textures."""

    overlay_id: str
    label: str
    available: bool = True
    unavailable_reason: Optional[str] = None
    units: str
    normalization: str  # linear | categorical | source_reflectance
    method: str
    uncertainty_classification: str  # quantified | metadata_sensitivity | categorical | unquantified | reflectance
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    no_data_meaning: str = "Transparent alpha=0 indicates outside footprint, missing DEM pixels, or incomplete 3x3 derivative neighborhood."
    palette_stops: List[Dict[str, Any]] = Field(default_factory=list)
    categories: List[Dict[str, str]] = Field(default_factory=list)


class CorridorUncertaintyProfile(BaseModel):
    """Complete Prompt 16 uncertainty & observability profile for a corridor or study bbox."""

    model_version: str = UNCERTAINTY_MODEL_VERSION
    dataset_profile: DatasetUncertaintyProfile
    slope_uncertainty: SlopeUncertaintySummary
    roughness_uncertainty: RoughnessUncertaintySummary
    registration_uncertainty: RegistrationUncertaintyResult
    observability: List[FeatureObservabilityRecord] = Field(default_factory=list)
    negative_evidence: NegativeEvidenceStatement
    traversability_breakdown: Optional[TraversabilityCellBreakdown] = None
    overlay_legends: Dict[str, OverlayLegendDescriptor] = Field(default_factory=dict)
    compute_time_ms: float = 0.0
