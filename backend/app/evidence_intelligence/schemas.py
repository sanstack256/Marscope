"""
MARSCOPE Evidence Intelligence Schemas
Martian Surface Intelligence & Exploration System

Defines typed, provenance-backed schemas for Marswalk corridor assessment,
route segmentation, terrain/optical morphology candidates, multi-mission
observation association, spatial coverage/gaps, physical energy budgets,
alternative route evidence comparison, and Marswalk Mission Dossiers.
Uses the authoritative 7-tier ScientificDataClassification enum.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.routing.schemas import (
    RoutingMode,
    RouteComputeResponse,
    RouteCoordinateInput,
    RoutePlanningConstraints,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ScientificDataClassification,
)
from app.terrain.optical_analysis import (
    OpticalCandidateFeature,
    RejectedOpticalCandidate,
)


class ReadinessState(str, Enum):
    ASSESSED = "ASSESSED"
    PARTIALLY_ASSESSED = "PARTIALLY_ASSESSED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_ASSESSED = "NOT_ASSESSED"


class ObservationAssociationType(str, Enum):
    INTERSECTS_ROUTE = "INTERSECTS_ROUTE"
    INTERSECTS_CORRIDOR = "INTERSECTS_CORRIDOR"
    NEAR_CORRIDOR = "NEAR_CORRIDOR"
    OUTSIDE_SEARCH_RADIUS = "OUTSIDE_SEARCH_RADIUS"
    UNLOCATED = "UNLOCATED"
    SPATIAL_REFERENCE_UNVERIFIED = "SPATIAL_REFERENCE_UNVERIFIED"


class ProductAvailabilityStatus(str, Enum):
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    VERIFIED_REMOTE = "VERIFIED_REMOTE"
    URL_UNVERIFIED = "URL_UNVERIFIED"
    MISSING = "MISSING"
    ACCESS_DENIED = "ACCESS_DENIED"
    ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"


class CacheValidityState(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    RECOMPUTING = "RECOMPUTING"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class DomainAssessmentRecord(BaseModel):
    domain: str
    status: str  # ASSESSED | PARTIALLY_ASSESSED | INSUFFICIENT_EVIDENCE | UNAVAILABLE | UNVALIDATED
    evidence_basis: str
    policy_version: str = "readiness-v2.0"
    threshold_or_rule: str
    notes: List[str] = Field(default_factory=list)


class AssessmentDependencySignature(BaseModel):
    dem_dataset_id: str
    dem_product_id: str
    dem_file_checksum: Optional[str] = None
    optical_dataset_id: Optional[str] = None
    optical_product_id: Optional[str] = None
    optical_file_checksum: Optional[str] = None
    geology_dataset_ids: List[str] = Field(default_factory=list)
    geology_checksums: Dict[str, Optional[str]] = Field(default_factory=dict)
    observation_catalog_checksum: Optional[str] = None
    route_signature: Optional[str] = None
    route_geometry_hash: str
    corridor_width_m: float
    segment_scale_m: float
    observation_search_radius_m: float
    routing_algorithm_version: str = "routing_v2_science_aware"
    terrain_assessment_version: str = "terrain_corridor_v3"
    optical_detector_version: str = "optical_candidate_v3"
    observation_matcher_version: str = "obs_strtree_v2"
    eva_model_version: str = "eva_envelope_v2"
    readiness_policy_version: str = "readiness-v2.0"
    uncertainty_model_version: str = "terrain_uncertainty_v1.0"
    resolution_policy_version: str = "observability_policy_v1.0"
    traversability_model_version: str = "traversability_v2.0"
    locomotion_model_id: str = "MARSCOPE-LOCO"
    locomotion_model_version: str = "locomotion_v1.0"
    routing_objectives_version: str = "routing_objectives_v1.0"
    return_planning_version: str = "return_planning_v2.0"
    sensitivity_policy_version: str = "sensitivity_v1.0"
    complementarity_registry_version: str = "complementarity_v1.0"
    mission_config_hash: Optional[str] = None
    signature_digest: str


class DatasetValidationStage(BaseModel):
    dataset_id: str
    product_id: str
    product_type: str
    catalogued: bool = True
    discovered: bool = True
    acquired: bool = False
    integrity_verified: bool = False
    label_parsed: bool = False
    scientifically_validated: bool = False
    processed: bool = False
    renderable: bool = False
    derived: bool = False
    native_resolution_m: Optional[float] = None
    sha256_checksum: Optional[str] = None
    missing_requirement: Optional[str] = None


class CorridorPolygon(BaseModel):
    centerline: List[List[float]] = Field(default_factory=list)  # [[lon_east, lat], ...]
    left_boundary: List[List[float]] = Field(default_factory=list)
    right_boundary: List[List[float]] = Field(default_factory=list)
    polygon_ring: List[List[float]] = Field(default_factory=list)
    clipped_to_dem_footprint: bool = False
    clipped_to_dem_bounds: bool = True
    corridor_area_m2: Optional[float] = None
    projection: str
    projection_epsg_or_wkt: Optional[str] = None
    corridor_width_m: float
    polygon_wkt: Optional[str] = None


class TerrainMorphologyCandidate(BaseModel):
    candidate_id: str
    morphology_type: str  # ridge_like_landform | depression | local_peak | steep_transition | channel_like_form | scarp | relief_anomaly
    segment_id: Optional[str] = None
    latitude: float
    longitude_east: float
    footprint_bounds: Dict[str, float]
    detection_method: str
    input_dataset_id: str
    input_product_id: str
    input_resolution_m: float
    detection_parameters: Dict[str, Any] = Field(default_factory=dict)
    geometric_measurements: Dict[str, float] = Field(default_factory=dict)
    resolution_status: str = "adequate"  # adequate | resolution_limited | unresolved
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED
    validation_state: str = "candidate_requiring_interpretation"
    limitations: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class AssociatedObservation(BaseModel):
    observation_id: str
    mission: str
    instrument: str
    sol: Optional[int] = None
    observation_time: Optional[str] = None
    latitude: Optional[float] = None
    longitude_east: Optional[float] = None
    coordinate_uncertainty_m: Optional[float] = None
    product_id: str
    distance_from_route_m: Optional[float] = None
    distance_from_corridor_m: Optional[float] = None
    association_type: ObservationAssociationType = ObservationAssociationType.NEAR_CORRIDOR
    nearest_segment_id: Optional[str] = None
    spatial_footprint: Optional[Dict[str, float]] = None
    footprint_geometry: Optional[Dict[str, Any]] = None
    processing_level: Optional[str] = None
    measurement_type: str
    availability_status: ProductAvailabilityStatus = ProductAvailabilityStatus.URL_UNVERIFIED
    product_available: bool = False
    availability_check_note: Optional[str] = None
    spatial_reference_verified: bool = True
    is_panorama: bool = False
    panorama_metadata: Optional[Dict[str, Any]] = None
    classification: ScientificDataClassification = ScientificDataClassification.DIRECTLY_MEASURED
    spatial_association_note: str = (
        "Nearby observation only; not a direct measurement of the exact route surface."
    )


class ResolutionAdequacyRecord(BaseModel):
    analysis_domain: str
    status: str  # adequate | resolution_limited | insufficient | unavailable | unverified
    source_dataset_id: Optional[str] = None
    native_resolution_m: Optional[float] = None
    policy_version: str
    rationale: str


class SegmentCoverageReport(BaseModel):
    segment_id: str
    dem_coverage_fraction: float
    valid_elevation_fraction: float
    slope_available: bool
    tri_available: bool
    optical_coverage_fraction: float
    optical_quality_note: str
    geological_map_coverage: bool
    geological_map_scale_note: str = "USGS SIM 3292 (1:20,000,000 regional context only; unverified locally)"
    spectral_data_available: bool
    thermal_data_available: bool
    rover_observation_count: int
    panorama_available: bool
    source_resolution_m: Optional[float] = None
    unverified_regions_present: bool
    # Prompt 15 exact per-segment metric denominators & non-double-counted multi-product coverage
    segment_corridor_area_m2: Optional[float] = None
    dem_valid_area_m2: Optional[float] = None
    optical_footprint_coverage_fraction: float = 0.0
    valid_optical_pixel_coverage_fraction: float = 0.0
    optical_covered_area_m2: Optional[float] = None
    optical_contributing_product_ids: List[str] = Field(default_factory=list)
    geological_coverage_fraction: float = 0.0
    thermal_coverage_fraction: float = 0.0
    spectral_coverage_fraction: float = 0.0
    spatial_resolution_adequate_for_eva: Optional[bool] = None
    validation_status: str = "unvalidated_planning_evidence"
    temporal_applicability_note: str = (
        "Static orbital/rover archive; not live environmental state"
    )


class EvidenceGapCell(BaseModel):
    gap_id: str
    gap_type: str  # no_dem_coverage | nodata_region | no_optical_coverage | insufficient_resolution | unverified_imagery | missing_mission_input
    segment_id: Optional[str] = None
    bounds: Dict[str, float]
    reason: str


class CorridorSegmentAssessment(BaseModel):
    segment_id: str
    segment_index: int
    start_coord: RouteCoordinateInput
    end_coord: RouteCoordinateInput
    vertices: List[RouteCoordinateInput] = Field(default_factory=list)
    geometry_geojson: Optional[Dict[str, Any]] = None
    corridor_polygon: List[List[float]] = Field(default_factory=list)  # [[lon_east, lat], ...]
    corridor_area_m2: Optional[float] = None
    cumulative_start_m: Optional[float] = None
    cumulative_end_m: Optional[float] = None
    geodesic_distance_m: float
    horizontal_distance_m: Optional[float] = None
    surface_distance_m: float
    three_d_distance_m: Optional[float] = None
    straight_line_distance_m: Optional[float] = None
    terrain_pixel_count: int = 0
    valid_terrain_pixel_count: int = 0
    resolution_supportable: bool = True
    resolution_support_note: Optional[str] = None
    start_elevation_m: Optional[float] = None
    end_elevation_m: Optional[float] = None
    elevation_change_m: Optional[float] = None
    max_slope_deg: Optional[float] = None
    mean_slope_deg: Optional[float] = None
    max_tri_m: Optional[float] = None
    mean_tri_m: Optional[float] = None
    tri_physical_radius_m: float = 5.0
    local_relief_m: Optional[float] = None
    mean_profile_curvature_inv_m: Optional[float] = None
    source_dem_id: str
    source_product_id: str
    native_resolution_m: float
    valid_data_coverage_fraction: float
    uncertainty_summary: str
    associated_observation_ids: List[str] = Field(default_factory=list)
    optical_candidate_ids: List[str] = Field(default_factory=list)
    morphology_candidate_ids: List[str] = Field(default_factory=list)
    unverified_area_present: bool = False
    coverage: SegmentCoverageReport
    provenance: Dict[str, Any] = Field(default_factory=dict)


class CorridorUncertaintySummary(BaseModel):
    dem_vertical_precision_note: str
    horizontal_resolution_m: float
    corridor_valid_fraction: float
    resolution_limited_segments: int
    nodata_segments: int
    coordinate_uncertainty_note: str
    unquantified_limitations: List[str] = Field(default_factory=list)


class CorridorAssessRequest(BaseModel):
    dataset_id: str = "hirise_dteec_009149_1750"
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    route: Optional[RouteComputeResponse] = None
    mode: RoutingMode = RoutingMode.BALANCED
    corridor_width_m: float = Field(default=60.0, ge=10.0, le=500.0)
    target_segment_length_m: Optional[float] = Field(default=None, ge=15.0, le=500.0)
    observation_search_radius_m: float = Field(default=250.0, ge=10.0, le=5000.0)
    selected_target_ids: List[str] = Field(default_factory=list)
    selected_imagery_ids: List[str] = Field(default_factory=list)
    constraints: Optional[RoutePlanningConstraints] = None
    force_recompute: bool = False


class CorridorAssessment(BaseModel):
    assessment_id: str
    dataset_id: str
    source_product_id: str
    crs: str = "IAU2000:49900"
    local_projection: str
    corridor_width_m: float
    segment_scale_m: float
    observation_search_radius_m: float
    corridor_geometry: CorridorPolygon
    route_horizontal_distance_m: float
    route_surface_distance_m: float
    segments: List[CorridorSegmentAssessment] = Field(default_factory=list)
    terrain_candidates: List[TerrainMorphologyCandidate] = Field(default_factory=list)
    optical_candidates: List[OpticalCandidateFeature] = Field(default_factory=list)
    rejected_optical_candidates: List[RejectedOpticalCandidate] = Field(default_factory=list)
    observations: List[AssociatedObservation] = Field(default_factory=list)
    coverage_summary: Dict[str, Any] = Field(default_factory=dict)
    resolution_adequacy: List[ResolutionAdequacyRecord] = Field(default_factory=list)
    evidence_gaps: List[EvidenceGapCell] = Field(default_factory=list)
    uncertainty: CorridorUncertaintySummary
    dataset_inventory: List[DatasetValidationStage] = Field(default_factory=list)
    compute_time_ms: float
    provenance_graph: ProvenanceDependencyGraph
    cache_validity: CacheValidityState = CacheValidityState.CURRENT
    stale_reasons: List[str] = Field(default_factory=list)
    dependency_signature: Optional[AssessmentDependencySignature] = None
    readiness_policy_version: str = "readiness-v2.0"
    convolution_buffer_m: Optional[float] = None
    convolution_buffer_px: Optional[int] = None
    route_decision_explainer: Optional[Dict[str, Any]] = None


class RouteEvidenceComparisonEntry(BaseModel):
    mode: RoutingMode
    mode_label: str
    feasible: bool
    error_reason: Optional[str] = None
    assessment_id: Optional[str] = None
    horizontal_distance_m: Optional[float] = None
    surface_distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    max_slope_deg: Optional[float] = None
    mean_slope_deg: Optional[float] = None
    max_tri_m: Optional[float] = None
    mean_tri_m: Optional[float] = None
    local_relief_max_m: Optional[float] = None
    terrain_coverage_fraction: Optional[float] = None
    optical_coverage_fraction: Optional[float] = None
    unknown_data_fraction: Optional[float] = None
    resolution_adequacy_status: Optional[str] = None
    associated_observation_count: int = 0
    science_targets_reached_count: int = 0
    unresolved_candidate_count: int = 0
    data_gap_count: int = 0
    composite_risk_score: Optional[float] = None  # Strictly None unless validated composite model exists
    composite_risk_status: str = "UNAVAILABLE (no validated composite risk model)"


class RouteEvidenceComparisonRequest(BaseModel):
    dataset_id: str = "hirise_dteec_009149_1750"
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    modes: List[RoutingMode] = Field(
        default_factory=lambda: [
            RoutingMode.CONSERVATIVE,
            RoutingMode.BALANCED,
            RoutingMode.SCIENCE_PRIORITY,
        ]
    )
    corridor_width_m: float = Field(default=60.0, ge=10.0, le=500.0)
    observation_search_radius_m: float = Field(default=250.0, ge=10.0, le=5000.0)
    selected_target_ids: List[str] = Field(default_factory=list)
    constraints: Optional[RoutePlanningConstraints] = None


class RouteEvidenceComparisonResponse(BaseModel):
    dataset_id: str
    source_product_id: str
    corridor_width_m: float
    entries: List[RouteEvidenceComparisonEntry] = Field(default_factory=list)
    tradeoff_explanations: List[str] = Field(default_factory=list)
    compute_time_ms: float


class PhysicalEnergyBudget(BaseModel):
    available: bool
    classification: ScientificDataClassification
    input_total_mass_kg: Optional[float] = None
    astronaut_suit_mass_kg: Optional[float] = None
    payload_mass_kg: Optional[float] = None
    surface_weight_n: Optional[float] = None
    mars_gravity_m_s2: float
    gravity_parameter_source: str
    gravity_parameter_version: str
    positive_elevation_gain_m: float
    negative_elevation_loss_m: float
    gravitational_pe_increase_j: Optional[float] = None
    gravitational_pe_decrease_j: Optional[float] = None
    net_gravitational_pe_change_j: Optional[float] = None
    disclaimer: str = (
        "Mechanical gravitational potential-energy work only (W=mg, dPE=mg*dh). "
        "Not astronaut metabolic energy or oxygen consumption; downhill steps do not recover metabolic energy."
    )
    unavailable_reason: Optional[str] = None


class MissionDossierRequest(BaseModel):
    mission_name: str = "Gale Boxwork Traverse Assessment"
    study_region: str = "Gale Crater / Mount Sharp"
    dataset_id: str = "hirise_dteec_009149_1750"
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    mode: RoutingMode = RoutingMode.BALANCED
    corridor_width_m: float = Field(default=60.0, ge=10.0, le=500.0)
    observation_search_radius_m: float = Field(default=250.0, ge=10.0, le=5000.0)
    selected_target_ids: List[str] = Field(default_factory=list)
    selected_imagery_ids: List[str] = Field(default_factory=list)
    constraints: Optional[RoutePlanningConstraints] = None
    # Strictly optional explicit user assumptions — never silently defaulted
    walking_speed_mps: Optional[float] = Field(default=None, gt=0.0, le=5.0)
    mission_duration_limit_s: Optional[float] = Field(default=None, gt=0.0)
    return_reserve_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    astronaut_suit_mass_kg: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    payload_mass_kg: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    independent_return_computed: bool = False
    force_recompute: bool = False


class MissionDossierResponse(BaseModel):
    dossier_id: str
    mission_name: str
    study_region: str
    readiness_state: ReadinessState
    readiness_reasons: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    corridor_assessment: CorridorAssessment
    route_comparison: Optional[RouteEvidenceComparisonResponse] = None
    physical_energy_budget: PhysicalEnergyBudget
    mobility_assessment: Dict[str, Any] = Field(default_factory=dict)
    scientific_opportunities: List[Dict[str, Any]] = Field(default_factory=list)
    unmodeled_parameters: List[str] = Field(default_factory=list)
    corridor_uncertainty_profile: Optional[Dict[str, Any]] = None
    complementarity_report: Optional[Dict[str, Any]] = None
    safety_certification_note: str = (
        "UNVERIFIED / NOT SAFETY CERTIFIED — analytical mission dossier only."
    )
    provenance_graph: ProvenanceDependencyGraph
    mathematical_assessment_complete: bool = False
    operational_safety_certified: bool = False
    domain_assessments: List[DomainAssessmentRecord] = Field(default_factory=list)
    readiness_policy_version: str = "readiness-v2.0"
    cache_validity: CacheValidityState = CacheValidityState.CURRENT
    stale_reasons: List[str] = Field(default_factory=list)
    dependency_signature: Optional[AssessmentDependencySignature] = None
