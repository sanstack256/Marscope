"""
MARSCOPE Human Mobility Intelligence Pydantic Schemas
Martian Surface Intelligence & Exploration System
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from app.mobility.models import (
    AnalysisScaleType,
    CellTraversalAvailabilityState,
    ParameterOriginType,
    ResolutionSuitabilityLevel,
    TerrainCoverageState,
)
from app.schemas.terrain import InsufficientCoverageReport, RasterBandStats


class GeoPoint(BaseModel):
    """Mars planetocentric coordinate in IAU2000 CRS."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees [-90, 90]")
    lon: float = Field(..., ge=-180.0, le=360.0, description="Longitude in degrees [-180, 360]")
    label: Optional[str] = Field(None, description="Optional human-readable waypoint label")


class StudyBoundsInput(BaseModel):
    """Explicit Mars bounding box in degrees."""

    min_lat: float = Field(..., ge=-90.0, le=90.0)
    max_lat: float = Field(..., ge=-90.0, le=90.0)
    min_lon: float = Field(..., ge=-180.0, le=360.0)
    max_lon: float = Field(..., ge=-180.0, le=360.0)

    @model_validator(mode="after")
    def _validate_lat_order(self) -> "StudyBoundsInput":
        if self.min_lat >= self.max_lat:
            raise ValueError(f"min_lat ({self.min_lat}) must be strictly less than max_lat ({self.max_lat}).")
        if self.min_lon == self.max_lon:
            raise ValueError(f"min_lon ({self.min_lon}) and max_lon ({self.max_lon}) must not be identical.")
        return self


class ResolutionSuitabilityAssessment(BaseModel):
    """Explicit resolution suitability assessment for a specific analysis regime."""

    analysis_type: AnalysisScaleType
    suitability: ResolutionSuitabilityLevel
    supported: bool
    native_resolution_m: Optional[float] = None
    effective_resolution_m: Optional[float] = None
    minimum_recommended_resolution_m: float
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    threshold_classification: Optional[str] = None
    threshold_rationale: Optional[str] = None
    explanation: str
    scientific_caveat: str


class TerrainDataInventoryEntry(BaseModel):
    """Complete provenance and suitability record for a registered DEM dataset."""

    dataset_id: str
    product_id: str
    title: str
    mission: str
    instrument: str
    source_url: str
    local_raw_path: Optional[str] = None
    local_label_path: Optional[str] = None
    processed_manifest_path: Optional[str] = None
    present_locally: bool
    processed_locally: bool
    sha256_checksum: Optional[str] = None
    native_resolution_ppd: Optional[float] = None
    native_resolution_meters_per_pixel: Optional[float] = None
    effective_resolution_meters_per_pixel: Optional[float] = None
    crs: str
    vertical_datum: str
    vertical_units: str
    nodata_value: Optional[float] = None
    coverage_bounds: Dict[str, float]
    license_status: str
    rights_statement: str
    known_limitations: List[str] = Field(default_factory=list)
    resolution_suitability: Dict[str, ResolutionSuitabilityAssessment] = Field(default_factory=dict)


class UncertaintyComponentRecord(BaseModel):
    """Explicitly separated uncertainty or numerical precision component."""

    component_id: str
    category: Literal[
        "source_measurement_uncertainty",
        "dem_vertical_accuracy",
        "horizontal_positional_accuracy",
        "processing_resampling_uncertainty",
        "derivative_sensitivity",
        "model_parameter_uncertainty",
    ]
    available: bool
    value: Optional[float] = None
    units: Optional[str] = None
    representation: str
    provenance: str
    notes: str


class MobilityUncertaintySummary(BaseModel):
    """
    Honest uncertainty and numerical precision report.
    Never combines incompatible vertical, horizontal, and model-parameter uncertainties into a single number.
    """

    source_dataset_id: str
    source_product_id: str
    combined_scalar_uncertainty_withheld: bool = True
    withholding_reason: str = (
        "Vertical DEM quantization/accuracy (meters), horizontal grid spacing (meters), finite-difference "
        "slope sensitivity (degrees), and user-configured scenario assumptions have incompatible physical "
        "dimensions and error distributions; they are reported separately rather than summed."
    )
    components: List[UncertaintyComponentRecord] = Field(default_factory=list)
    numerical_precision_policy: Dict[str, Any] = Field(default_factory=dict)


class ScenarioParameterRecord(BaseModel):
    """Traceable parameter record inside a MobilityScenario."""

    name: str
    value: Optional[float] = None
    units: str
    origin: ParameterOriginType
    valid_range: Optional[List[Optional[float]]] = None
    provenance: str
    version: str = "1.0.0"
    is_validated_physiological_or_suit_standard: bool = False


class SlopeSpeedAdjustmentRule(BaseModel):
    """
    Explicitly configured slope speed adjustment rule.
    Only evaluated when supplied by the user; never extrapolated outside [min_valid_slope_deg, max_valid_slope_deg].
    """

    rule_id: str = Field("user_linear_slope_penalty_v1", min_length=1)
    rule_type: Literal["piecewise_linear_factor", "exponential_decay_factor"] = "piecewise_linear_factor"
    reference_slope_deg: float = Field(0.0, ge=0.0, lt=90.0, description="Slope (deg) at which speed factor is 1.0")
    coefficient_per_deg: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fractional speed reduction per degree (linear) or decay constant per degree (exponential) above reference_slope_deg",
    )
    min_valid_slope_deg: float = Field(0.0, ge=0.0, lt=90.0)
    max_valid_slope_deg: float = Field(45.0, gt=0.0, lt=90.0)
    min_speed_factor: float = Field(0.05, gt=0.0, le=1.0)
    max_speed_factor: float = Field(1.0, gt=0.0, le=2.0)
    formula_description: str = Field(
        "f_slope(theta) = clamp(1.0 - coefficient_per_deg * max(0, theta - reference_slope_deg), min_speed_factor, max_speed_factor) for theta in [min_valid_slope_deg, max_valid_slope_deg]",
        description="Mathematical formula for slope speed factor",
    )
    provenance: str = Field(
        ...,
        min_length=3,
        description="Explicit user or literature provenance for this slope adjustment rule",
    )
    version: str = Field("1.0.0", min_length=1)

    @model_validator(mode="after")
    def _validate_ranges(self) -> "SlopeSpeedAdjustmentRule":
        if self.min_valid_slope_deg >= self.max_valid_slope_deg:
            raise ValueError("min_valid_slope_deg must be strictly less than max_valid_slope_deg.")
        if self.min_speed_factor > self.max_speed_factor:
            raise ValueError("min_speed_factor must not exceed max_speed_factor.")
        return self


class RoughnessSpeedAdjustmentRule(BaseModel):
    """
    Explicitly configured TRI roughness speed adjustment rule.
    Only evaluated when supplied by the user; never extrapolated outside [min_valid_roughness_m, max_valid_roughness_m].
    """

    rule_id: str = Field("user_linear_roughness_penalty_v1", min_length=1)
    reference_roughness_m: float = Field(0.0, ge=0.0, description="TRI roughness (m) at which speed factor is 1.0")
    coefficient_per_meter: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fractional speed reduction per meter of TRI above reference_roughness_m",
    )
    min_valid_roughness_m: float = Field(0.0, ge=0.0)
    max_valid_roughness_m: float = Field(5000.0, gt=0.0)
    min_speed_factor: float = Field(0.05, gt=0.0, le=1.0)
    max_speed_factor: float = Field(1.0, gt=0.0, le=2.0)
    formula_description: str = Field(
        "f_rough(tri) = clamp(1.0 - coefficient_per_meter * max(0, tri - reference_roughness_m), min_speed_factor, max_speed_factor) for tri in [min_valid_roughness_m, max_valid_roughness_m]",
        description="Mathematical formula for TRI roughness speed factor",
    )
    provenance: str = Field(
        ...,
        min_length=3,
        description="Explicit user or literature provenance for this roughness adjustment rule",
    )
    version: str = Field("1.0.0", min_length=1)

    @model_validator(mode="after")
    def _validate_ranges(self) -> "RoughnessSpeedAdjustmentRule":
        if self.min_valid_roughness_m >= self.max_valid_roughness_m:
            raise ValueError("min_valid_roughness_m must be strictly less than max_valid_roughness_m.")
        if self.min_speed_factor > self.max_speed_factor:
            raise ValueError("min_speed_factor must not exceed max_speed_factor.")
        return self


class MobilityScenarioCreateRequest(BaseModel):
    """
    Request payload to create/register an explicit MobilityScenario.
    Contains NO hardcoded default walking speed, slope limit, suit mass, or physiology model.
    """

    name: str = Field(..., min_length=1, max_length=160, description="Scenario name")
    description: Optional[str] = Field(None, description="Scenario description and operational context")
    version: str = Field("1.0.0", min_length=1, description="Scenario version")
    astronaut_position: Optional[GeoPoint] = Field(None, description="Optional starting astronaut position")
    destination_position: Optional[GeoPoint] = Field(None, description="Optional candidate destination position")
    study_bounds: Optional[StudyBoundsInput] = Field(None, description="Optional study region bounding box")
    reference_walking_speed_m_per_s: Optional[float] = Field(
        None,
        gt=0.0,
        le=10.0,
        description="Explicit user-configured flat-terrain reference walking speed in m/s (required for traversal time estimation)",
    )
    reference_walking_speed_units: Literal["m/s"] = Field(
        "m/s",
        description="Physical unit for reference_walking_speed_m_per_s (must be 'm/s')",
    )
    walking_speed_provenance: Optional[str] = Field(
        None,
        description="Provenance or justification for configured walking speed",
    )
    planning_max_slope_deg: Optional[float] = Field(
        None,
        gt=0.0,
        lt=90.0,
        description="Optional user-configured planning maximum slope threshold in degrees (not a safety limit)",
    )
    planning_max_roughness_m: Optional[float] = Field(
        None,
        gt=0.0,
        description="Optional user-configured planning maximum TRI roughness threshold in meters (not a safety limit)",
    )
    roughness_window_radius_m: Optional[float] = Field(
        None,
        gt=0.0,
        description="Optional physical neighborhood radius (m) for TRI roughness computation",
    )
    slope_speed_adjustment: Optional[SlopeSpeedAdjustmentRule] = None
    roughness_speed_adjustment: Optional[RoughnessSpeedAdjustmentRule] = None
    astronaut_body_mass_kg: Optional[float] = Field(None, gt=0.0, le=500.0)
    suit_mass_kg: Optional[float] = Field(None, ge=0.0, le=500.0)
    carried_load_mass_kg: Optional[float] = Field(None, ge=0.0, le=500.0)
    notes: List[str] = Field(default_factory=list)


class MobilityScenario(BaseModel):
    """Persisted, provenance-tagged Human Mobility Scenario."""

    scenario_id: str
    name: str
    description: Optional[str] = None
    version: str
    created_at_utc: str
    astronaut_position: Optional[GeoPoint] = None
    destination_position: Optional[GeoPoint] = None
    study_bounds: Optional[StudyBoundsInput] = None
    reference_walking_speed_m_per_s: Optional[float] = None
    walking_speed_provenance: Optional[str] = None
    planning_max_slope_deg: Optional[float] = None
    planning_max_roughness_m: Optional[float] = None
    roughness_window_radius_m: Optional[float] = None
    slope_speed_adjustment: Optional[SlopeSpeedAdjustmentRule] = None
    roughness_speed_adjustment: Optional[RoughnessSpeedAdjustmentRule] = None
    astronaut_body_mass_kg: Optional[float] = None
    suit_mass_kg: Optional[float] = None
    carried_load_mass_kg: Optional[float] = None
    total_mass_kg: Optional[float] = None
    mars_surface_weight_n: Optional[float] = None
    parameters: Dict[str, ScenarioParameterRecord] = Field(default_factory=dict)
    traversal_time_estimation_ready: bool = False
    unconfigured_capabilities: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ElevationProfileRequest(BaseModel):
    """
    Request for a spatially explicit elevation profile and cumulative gain/loss calculation
    between two positions or along a user-supplied sequence of waypoints.
    Does NOT perform route optimization or pathfinding.
    """

    dataset_id: str = Field("mola_megt90n000cb", description="Source DEM dataset ID")
    start: Optional[GeoPoint] = Field(None, description="Start position (if waypoints not supplied)")
    end: Optional[GeoPoint] = Field(None, description="End position (if waypoints not supplied)")
    waypoints: Optional[List[GeoPoint]] = Field(
        None,
        min_length=2,
        description="Explicit ordered waypoint sequence (>= 2 points). If provided, overrides start/end.",
    )
    sample_count: int = Field(
        25,
        ge=2,
        le=500,
        description="Total number of profile samples along the geometry",
    )
    sampling_method: Literal["nearest", "bilinear"] = Field(
        "nearest",
        description="Raster sampling method ('nearest' preserves exact source pixel values; 'bilinear' interpolates only when all 4 surrounding pixels are valid)",
    )

    @model_validator(mode="after")
    def _validate_geometry(self) -> "ElevationProfileRequest":
        if self.waypoints and len(self.waypoints) >= 2:
            return self
        if self.start is not None and self.end is not None:
            return self
        raise ValueError("Provide either `waypoints` (>= 2 points) or both `start` and `end` GeoPoints.")


class ElevationProfileSample(BaseModel):
    """Single sample along an elevation profile transect."""

    sample_index: int
    lat: float
    lon_east: float
    cumulative_distance_meters: float
    segment_distance_meters: float
    coverage_state: TerrainCoverageState
    elevation_meters: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    roughness_tri_meters: Optional[float] = None
    segment_elevation_delta_meters: Optional[float] = None
    segment_slope_deg: Optional[float] = None
    source_pixel_row: Optional[int] = None
    source_pixel_col: Optional[int] = None


class ElevationProfileGapSegment(BaseModel):
    """Contiguous no-data or out-of-footprint gap along an elevation profile."""

    start_sample_index: int
    end_sample_index: int
    start_distance_meters: float
    end_distance_meters: float
    gap_length_meters: float
    reason: TerrainCoverageState


class ElevationProfileResponse(BaseModel):
    """Spatially explicit elevation profile and cumulative gain/loss report."""

    dataset_id: str
    source_product_id: str
    crs: str
    elevation_units: str = "meters"
    distance_units: str = "meters"
    sampling_method: str
    geometry_type: Literal["two_point_transect", "user_supplied_polyline"]
    waypoint_count: int
    sample_count: int
    valid_sample_count: int
    nodata_sample_count: int
    complete_coverage: bool
    sample_spacing_meters: float
    total_horizontal_distance_meters: float
    evaluated_horizontal_distance_meters: float
    total_positive_elevation_gain_meters: Optional[float] = None
    total_negative_elevation_change_meters: Optional[float] = None
    net_elevation_change_meters: Optional[float] = None
    min_elevation_meters: Optional[float] = None
    max_elevation_meters: Optional[float] = None
    mean_slope_along_profile_deg: Optional[float] = None
    max_slope_along_profile_deg: Optional[float] = None
    nodata_gap_segments: List[ElevationProfileGapSegment] = Field(default_factory=list)
    samples: List[ElevationProfileSample] = Field(default_factory=list)
    resolution_suitability: Dict[str, ResolutionSuitabilityAssessment] = Field(default_factory=dict)
    uncertainty: MobilityUncertaintySummary
    limitations: List[str] = Field(default_factory=list)


class TerrainFeatureCell(BaseModel):
    """Per-cell physical terrain features and coverage state inside an inspection window."""

    row: int
    col: int
    center_lat: float
    center_lon_east: float
    coverage_state: TerrainCoverageState
    elevation_meters: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    aspect_undefined_flat: bool = False
    roughness_tri_meters: Optional[float] = None


class TerrainFeaturesWindowResponse(BaseModel):
    """Windowed physical terrain feature extraction response."""

    dataset_id: str
    source_product_id: str
    processing_version: str
    crs: str
    requested_bounds: Dict[str, float]
    requested_bounds_modified: bool = False
    source_coverage_bounds: Dict[str, float]
    analysis_footprint_bounds: Dict[str, float]
    dx_meters: float
    dy_meters: float
    grid_shape: Dict[str, int]
    roughness_window_metadata: Dict[str, Any]
    elevation_stats: RasterBandStats
    slope_stats: RasterBandStats
    aspect_stats: RasterBandStats
    roughness_stats: RasterBandStats
    coverage_state_counts: Dict[str, int]
    cells: List[TerrainFeatureCell] = Field(default_factory=list)
    resolution_suitability: Dict[str, ResolutionSuitabilityAssessment] = Field(default_factory=dict)
    uncertainty: MobilityUncertaintySummary
    provenance: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class CoverageIntelligenceResponse(BaseModel):
    """
    Dedicated spatial coverage & unknown-data intelligence report for a study region.
    Explicitly distinguishes all 5 coverage states and quantifies covered/uncovered/nodata areas.
    """

    dataset_id: str
    source_product_id: str
    crs: str
    requested_bounds: Dict[str, float]
    requested_bounds_modified: bool = False
    source_footprint_bounds: Dict[str, float]
    overlap_bounds: Optional[Dict[str, float]] = None
    has_spatial_overlap: bool
    sufficient_for_3x3_derivatives: bool
    requested_area_km2: float
    covered_area_km2: float
    uncovered_area_km2: float
    valid_elevation_area_km2: float
    nodata_elevation_area_km2: float
    valid_derivative_area_km2: float
    valid_elevation_percentage_of_requested: float
    valid_derivative_percentage_of_requested: float
    pixel_counts: Dict[str, int]
    coverage_state_counts: Dict[str, int]
    derivative_availability: Dict[str, bool]
    resolution_suitability: Dict[str, ResolutionSuitabilityAssessment] = Field(default_factory=dict)
    insufficient_coverage_report: Optional[InsufficientCoverageReport] = None
    notes: List[str] = Field(default_factory=list)


class TraversalSegmentEvaluation(BaseModel):
    """
    Separated physical measurements vs scenario-derived traversal estimates for a single cell or transect segment.
    """

    segment_index: int
    lat: float
    lon_east: float
    horizontal_distance_meters: float
    # Physical measurements (from DEM + Mars gravity only)
    coverage_state: TerrainCoverageState
    elevation_meters: Optional[float] = None
    elevation_delta_meters: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    roughness_tri_meters: Optional[float] = None
    gravitational_potential_energy_delta_joules: Optional[float] = None
    uphill_parallel_gravity_force_newtons: Optional[float] = None
    # Scenario-derived traversal estimates (explicitly separated)
    traversal_availability_state: CellTraversalAvailabilityState
    reference_speed_m_per_s: Optional[float] = None
    slope_speed_factor: Optional[float] = None
    roughness_speed_factor: Optional[float] = None
    effective_speed_m_per_s: Optional[float] = None
    baseline_time_seconds: Optional[float] = None
    adjusted_time_seconds: Optional[float] = None
    unavailable_or_exclusion_reason: Optional[str] = None


class MobilityEvaluationRequest(BaseModel):
    """
    Evaluate physical terrain measurements and scenario-dependent traversal estimates
    at a point, along a 2-point/polyline transect, or across a bounded study window.
    """

    dataset_id: str = Field("mola_megt90n000cb", description="Source DEM dataset ID")
    scenario_id: Optional[str] = Field(None, description="Registered MobilityScenario ID to apply")
    inline_scenario: Optional[MobilityScenarioCreateRequest] = Field(
        None,
        description="Optional inline MobilityScenario definition (used if scenario_id is omitted)",
    )
    point: Optional[GeoPoint] = Field(None, description="Evaluate at a single point")
    waypoints: Optional[List[GeoPoint]] = Field(
        None,
        min_length=2,
        description="Evaluate along an explicit ordered waypoint transect (>= 2 points)",
    )
    study_bounds: Optional[StudyBoundsInput] = Field(
        None,
        description="Evaluate a spatially explicit cost surface over a study bounding box",
    )
    sample_count: int = Field(25, ge=2, le=500, description="Profile sample count when `waypoints` is provided")


class CostSurfaceCellRecord(BaseModel):
    """Single cell in a spatially explicit TraversalCostSurface."""

    row: int
    col: int
    center_lat: float
    center_lon_east: float
    cell_width_meters: float
    cell_height_meters: float
    cell_diagonal_meters: float
    # Physical measurements
    coverage_state: TerrainCoverageState
    elevation_meters: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    roughness_tri_meters: Optional[float] = None
    # Scenario-derived traversal cost (null whenever unknown/excluded/unconfigured)
    traversal_availability_state: CellTraversalAvailabilityState
    effective_speed_m_per_s: Optional[float] = None
    traversal_cost_seconds_per_meter: Optional[float] = None
    cell_crossing_time_seconds: Optional[float] = None
    slope_speed_factor: Optional[float] = None
    roughness_speed_factor: Optional[float] = None
    reason: Optional[str] = None


class CostSurfaceSummary(BaseModel):
    """Spatially explicit TraversalCostSurface metadata and cell records."""

    cost_surface_id: str
    dataset_id: str
    source_product_id: str
    processing_version: str
    traversal_model_id: str
    traversal_model_version: str
    scenario_id: str
    scenario_version: str
    crs: str
    requested_bounds: Dict[str, float]
    analysis_footprint_bounds: Dict[str, float]
    grid_shape: Dict[str, int]
    dx_meters: float
    dy_meters: float
    cost_units: str = "seconds_per_meter"
    cell_crossing_time_units: str = "seconds"
    unknown_cell_policy: str = "preserve_null_never_zero_cost"
    safety_classification_policy: str = "no_safe_or_unsafe_labels_emitted"
    coverage_state_counts: Dict[str, int]
    traversal_availability_counts: Dict[str, int]
    evaluated_cell_count: int
    unknown_terrain_cell_count: int
    excluded_by_scenario_cell_count: int
    min_effective_speed_m_per_s: Optional[float] = None
    max_effective_speed_m_per_s: Optional[float] = None
    mean_effective_speed_m_per_s: Optional[float] = None
    min_cell_crossing_time_seconds: Optional[float] = None
    max_cell_crossing_time_seconds: Optional[float] = None
    mean_cell_crossing_time_seconds: Optional[float] = None
    cells: List[CostSurfaceCellRecord] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class MobilityEvaluationResponse(BaseModel):
    """
    Complete evaluation response strictly separating physical terrain measurements
    from scenario-dependent traversal estimates.
    """

    evaluation_id: str
    evaluated_at_utc: str
    evaluation_mode: Literal["point", "transect", "study_window"]
    dataset_id: str
    source_product_id: str
    crs: str
    traversal_model_id: str
    traversal_model_version: str
    scenario: MobilityScenario
    physical_terrain_measurements: Dict[str, Any]
    scenario_traversal_estimates: Dict[str, Any]
    segments: List[TraversalSegmentEvaluation] = Field(default_factory=list)
    cost_surface: Optional[CostSurfaceSummary] = None
    resolution_suitability: Dict[str, ResolutionSuitabilityAssessment] = Field(default_factory=dict)
    uncertainty: MobilityUncertaintySummary
    provenance: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class MobilityEngineStatusResponse(BaseModel):
    """Status and inventory overview for GET /api/mobility/status."""

    engine_name: str = "MARSCOPE Human Mobility Intelligence Engine"
    engine_version: str = "1.0.0"
    processing_version: str
    traversal_model_id: str
    traversal_model_version: str
    route_optimization_enabled: bool = False
    safety_certification_enabled: bool = False
    active_dem_dataset_id: Optional[str] = None
    available_dem_count: int
    locally_downloaded_dem_count: int
    processed_dem_count: int
    registered_scenarios_count: int
    terrain_inventory: List[TerrainDataInventoryEntry] = Field(default_factory=list)
    capabilities: Dict[str, bool] = Field(default_factory=dict)
    scientific_constraints: List[str] = Field(default_factory=list)
