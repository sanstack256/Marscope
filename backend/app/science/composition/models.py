"""
MARSCOPE Verified Composition Discovery Domain Models
Martian Surface Intelligence & Exploration System

Strictly distinguishes chemical elements, oxide measurements, crystalline minerals,
mineral groups, evidence strength tiers, below-detection-limit states, unlocated records,
validation stage results, and rejection audit trails.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SpeciesCategory(str, Enum):
    ELEMENT = "element"
    OXIDE = "oxide"
    MINERAL = "mineral"
    MINERAL_GROUP = "mineral_group"


class EvidenceType(str, Enum):
    DIRECT_MINERAL_DETECTION = "direct_mineral_detection"
    DIRECT_ELEMENT_MEASUREMENT = "direct_element_measurement"
    OXIDE_COMPOSITION_MEASUREMENT = "oxide_composition_measurement"
    SPECTRAL_CLASSIFICATION_INDICATOR = "spectral_classification_indicator"
    UNINTERPRETED_SPECTRAL_RECORD = "uninterpreted_spectral_record"


class EvidenceStatus(str, Enum):
    MEASURED = "measured"
    DETECTED = "detected"
    TENTATIVE = "tentative"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    MISSING_NULL = "missing_null"
    UNLOCATED = "unlocated"
    REJECTED = "rejected"


class GeometryType(str, Enum):
    POINT = "point"
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"


class SearchMatchType(str, Enum):
    EXACT_SPECIES = "exact_species"
    OXIDE_TO_ELEMENT_CONVERSION = "oxide_to_element_conversion"
    ELEMENT_BEARING_MINERAL = "element_bearing_mineral"
    MINERAL_GROUP_MEMBER = "mineral_group_member"


class CompositionSearchMode(str, Enum):
    AUTO = "auto"
    ELEMENT = "element"
    MINERAL = "mineral"
    ELEMENT_BEARING_MINERAL = "element_bearing_mineral"


class LocationSemanticType(str, Enum):
    INSTRUMENT_TARGET_LOCATION = "instrument_target_location"
    ROVER_STATION_LOCATION = "rover_station_location"
    PRODUCT_FOOTPRINT = "product_footprint"
    OBSERVATION_REGION = "observation_region"
    UNLOCATED = "unlocated"


class IntegrityStatus(str, Enum):
    VERIFIED = "verified"
    SOURCE_FILES_MISSING = "source_files_missing"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    MANIFEST_INVALID = "manifest_invalid"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class RightsStatus(str, Enum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    NOT_FOUND = "not_found"
    RESTRICTED_CONDITIONS_APPLY = "restricted_conditions_apply"


class GenerationBuildStatus(str, Enum):
    COMPLETE = "complete"
    COMPLETE_WITH_DECLARED_UNAVAILABLE_SOURCES = "complete_with_declared_unavailable_sources"
    PARTIAL = "partial"
    FAILED = "failed"


class UncertaintyMetadata(BaseModel):
    reported_value: Optional[float] = None
    reported_unit: Optional[str] = None
    uncertainty_type: str = "unknown"
    statistical_interpretation: str
    coverage_confidence_level: str = "unspecified"
    source_definition: str
    source_product: str
    conversion_history: List[str] = Field(default_factory=list)


class SourceArtifactRecord(BaseModel):
    artifact_id: str
    artifact_role: str
    dataset_id: Optional[str] = None
    product_id: Optional[str] = None
    file_path: str
    required: bool = True
    present: bool = True
    verified: bool = False
    sha256_checksum: Optional[str] = None
    byte_size: Optional[int] = None
    retrieval_timestamp_utc: str = "unknown"
    source_mtime_utc: Optional[str] = None
    source_url: Optional[str] = None
    license_status: RightsStatus = RightsStatus.NOT_VERIFIED
    rights_statement: str = "Rights/license metadata not verified in source product artifacts."
    failure_reason: Optional[str] = None


class ProductAuditEntry(BaseModel):
    dataset_id: str
    product_id: str
    expected_artifact_name: str
    discovery_scope: str = "static_seed_manifest"
    present_locally: bool = False
    build_status: str = "pending"
    accepted_record_count: int = 0
    rejected_record_count: int = 0
    companion_dependencies: List[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class RankingConfiguration(BaseModel):
    ranking_config_id: str = "heuristic_exploration_priority_v3"
    ranking_config_version: str = "3.0.0"
    is_heuristic_only: bool = True
    methodology_note: str = (
        "Heuristic exploration priority weighting ONLY — NOT a validated scientific probability, "
        "detection confidence, statistical certainty, or physical hazard rating."
    )
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "evidence_tier": 0.35,
            "abundance": 0.25,
            "quality": 0.15,
            "corroboration": 0.15,
            "spatial_proximity": 0.10,
        }
    )
    distance_reference_scale_m: float = 2000.0
    quality_scaling_rule: str = (
        "When cohort uncertainties share one compatible statistical family with documented scale "
        "and matching units (and positive abundance > 0), quality_component = max(0.05, 1 - min(0.95, uncertainty / abundance)). "
        "Across incompatible uncertainty types (e.g. ChemCam RMSEP vs APXS precision vs CheMin 2-sigma), "
        "unspecified sigma scales, or text-only quality flags, quality_component is None (withheld, never fabricated)."
    )
    corroboration_rule: str = (
        "Explicit peer corroboration: None when only 1 matching observation exists at the site; "
        "scaled across independent instruments and nearby cluster count when count >= 2."
    )


class ParserFieldMapping(BaseModel):
    schema_field_name: str
    resolved_header_name: Optional[str] = None
    column_index: Optional[int] = None
    data_type: Optional[str] = None
    unit: Optional[str] = None
    unit_source: Optional[str] = None
    description: Optional[str] = None
    special_constants: Dict[str, Any] = Field(default_factory=dict)


class ParserResult(BaseModel):
    parser_id: str
    parser_version: str
    schema_source: str
    schema_version: str
    source_file_path: str
    source_file_checksum: str
    label_file_path: Optional[str] = None
    label_file_checksum: Optional[str] = None
    format_file_paths: List[str] = Field(default_factory=list)
    format_file_checksums: Dict[str, str] = Field(default_factory=dict)
    dependency_digest: Optional[str] = None
    field_mappings: List[ParserFieldMapping] = Field(default_factory=list)
    total_rows_read: int = 0
    accepted_row_count: int = 0
    rejected_row_count: int = 0
    unsupported_row_count: int = 0
    row_rejections: List[Dict[str, Any]] = Field(default_factory=list)
    records: List[Dict[str, Any]] = Field(default_factory=list)


class SpeciesRecord(BaseModel):
    canonical_id: str = Field(..., description="Canonical identifier e.g. 'Fe', 'SiO2', 'hematite'")
    symbol_or_formula: str = Field(..., description="Chemical symbol, oxide formula, or mineral formula")
    canonical_name: str = Field(..., description="Human-readable scientific species name")
    category: SpeciesCategory
    aliases: List[str] = Field(default_factory=list)
    associated_elements: List[str] = Field(
        default_factory=list,
        description="Element symbols stoichiometrically or structurally borne by this oxide/mineral",
    )
    parent_group: Optional[str] = Field(None, description="Parent mineral group ID when applicable")
    child_species: List[str] = Field(default_factory=list, description="Member species for groups or element oxides")
    atomic_or_molar_mass: Optional[float] = None
    stoichiometric_element: Optional[str] = None
    stoichiometric_mass_fraction: Optional[float] = Field(
        None, description="Exact IUPAC mass fraction of elemental constituent in oxide"
    )
    supported_instruments: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SpeciesResolutionResult(BaseModel):
    raw_query: str
    normalized_query: str
    resolved: bool
    ambiguous: bool = False
    species: Optional[SpeciesRecord] = None
    candidates: List[SpeciesRecord] = Field(default_factory=list)
    explanation: str


class ValidationStageResult(BaseModel):
    stage_number: int = Field(..., ge=1, le=12)
    stage_name: str
    passed: bool
    detail: str


class RejectionRecord(BaseModel):
    rejection_id: str
    source_dataset_id: str
    product_id: str
    source_record_ref: str
    instrument_id: str
    raw_species: Optional[str] = None
    rejection_stage: int
    rejection_code: str
    reason: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    rejected_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompositionEvidence(BaseModel):
    evidence_id: str
    determinism_version: str = "evidence_id_v2"
    source_dataset_id: str
    product_id: str
    source_record_ref: str
    source_file_path: Optional[str] = None
    source_file_checksum: Optional[str] = None
    source_artifact_dependency_digest: Optional[str] = None
    companion_schema_checksums: Dict[str, str] = Field(default_factory=dict)
    schema_version: Optional[str] = None
    parser_id: Optional[str] = None
    parser_version: Optional[str] = None
    instrument_id: str
    instrument_name: str
    mission: str = "Mars Science Laboratory (MSL)"
    processing_level: str
    calibration_status: str
    target_name: Optional[str] = None
    sol: Optional[int] = None
    observation_timestamp_utc: Optional[str] = None
    rmc: Optional[str] = None

    canonical_species_id: str
    canonical_species_name: str
    species_category: SpeciesCategory
    raw_species_name: str
    evidence_type: EvidenceType
    evidence_status: EvidenceStatus

    raw_value: Optional[float] = None
    raw_unit: Optional[str] = None
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    normalization_formula: Optional[str] = None
    is_stoichiometric_conversion: bool = False
    source_oxide_species: Optional[str] = None
    stoichiometric_factor: Optional[float] = None
    stoichiometric_weights_version: Optional[str] = None
    uncertainty_value: Optional[float] = None
    uncertainty_unit: Optional[str] = None
    uncertainty_type: Optional[str] = None
    uncertainty_semantics: Optional[str] = None
    uncertainty_metadata: Optional[UncertaintyMetadata] = None
    secondary_uncertainty_value: Optional[float] = None
    secondary_uncertainty_unit: Optional[str] = None
    secondary_uncertainty_type: Optional[str] = None
    secondary_uncertainty_metadata: Optional[UncertaintyMetadata] = None
    detection_limit_value: Optional[float] = None
    detection_limit_unit: Optional[str] = None
    detection_limit_status: Optional[str] = None
    quality_flag: Optional[str] = None

    methodology: str
    provenance_url: Optional[str] = None
    source_reference: str
    citation: Optional[str] = None

    # Spatial coordinates & footprint (explicitly separated unlocated vs verified & station vs target)
    location_verified: bool = False
    location_semantic_type: LocationSemanticType = LocationSemanticType.UNLOCATED
    latitude: Optional[float] = None
    longitude_east: Optional[float] = None
    elevation_m: Optional[float] = None
    crs: Optional[str] = None
    latitude_convention: Optional[str] = None
    longitude_direction: Optional[str] = None
    coordinate_source: Optional[str] = None
    coordinate_provenance: Optional[str] = None
    original_coordinate_values: Optional[Dict[str, Any]] = None
    original_coordinate_crs: Optional[str] = None
    coordinate_transform: Optional[str] = None
    coordinate_transform_params: Optional[Dict[str, Any]] = None
    waypoint_id: Optional[str] = None
    association_rule_version: Optional[str] = None
    coordinate_limitations: List[str] = Field(default_factory=list)
    coordinate_uncertainty_m: Optional[float] = None
    instrument_standoff_m: Optional[float] = None
    geometry_type: GeometryType = GeometryType.POINT
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lon_east: Optional[float] = None
    max_lon_east: Optional[float] = None
    geometry_wkt: Optional[str] = None

    validation_stages: List[ValidationStageResult] = Field(default_factory=list)
    validated_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generation_id: Optional[str] = None


class RankingDimensions(BaseModel):
    ranking_config_id: str = "heuristic_exploration_priority_v3"
    ranking_config_version: str = "3.0.0"
    is_heuristic_only: bool = True
    ranking_methodology_label: str = "HEURISTIC_EXPLORATION_PRIORITY_ONLY"
    evidence_tier_score: float = Field(..., description="Instrument/methodology tier (1.0=direct mineral/oxide, 0.55=element-bearing host)")
    abundance_component: Optional[float] = Field(None, description="Normalized abundance contribution [0, 1] within query scale")
    quality_component: Optional[float] = Field(
        None,
        description=(
            "Within-family precision ranking contribution [0, 1]; strictly None when uncertainty is "
            "unreported, statistically unspecified, or incompatible across cohort uncertainty types."
        ),
    )
    uncertainty_compatibility_status: str = "unreported"
    quality_exclusion_reason: Optional[str] = None
    corroboration_component: Optional[float] = Field(
        None, description="Independent instrument/observation corroboration [0, 1]; None for single uncorroborated observation"
    )
    spatial_proximity_component: Optional[float] = Field(
        None, description="Inverse Mars geodesic distance factor [0, 1] when astronaut position provided"
    )
    composite_rank_score: Optional[float] = Field(
        None, description="Transparent heuristic weighted priority score (NOT probability or statistical confidence)"
    )
    unavailable_dimensions: List[str] = Field(default_factory=list)
    score_formula: str = Field(..., description="Exact formula documenting weights & active terms used")
    rationale: str = Field(..., description="Human-readable scientific explanation for ranking position")


class RankedCompositionHit(BaseModel):
    evidence: CompositionEvidence
    match_type: SearchMatchType
    match_explanation: str
    distance_from_astronaut_m: Optional[float] = None
    bearing_deg: Optional[float] = None
    supporting_instruments_nearby: List[str] = Field(default_factory=list)
    nearby_observation_count: int = 1
    ranking: RankingDimensions


class CandidateDiscoveryLocation(BaseModel):
    candidate_id: str
    cluster_label: str
    latitude: float
    longitude_east: float
    elevation_m: Optional[float] = None
    crs: str = "IAU2000:49900"
    location_semantic_type: LocationSemanticType = LocationSemanticType.ROVER_STATION_LOCATION
    coordinate_source: str
    coordinate_uncertainty_m: Optional[float] = None
    coordinate_limitations: List[str] = Field(default_factory=list)
    distance_from_astronaut_m: Optional[float] = None
    bearing_deg: Optional[float] = None
    matched_evidence_count: int
    distinct_instruments: List[str] = Field(default_factory=list)
    best_evidence_type: EvidenceType
    best_species_id: str
    best_normalized_value: Optional[float] = None
    best_normalized_unit: Optional[str] = None
    ranking: RankingDimensions
    evidence_ids: List[str] = Field(default_factory=list)
    target_names: List[str] = Field(default_factory=list)
    sol_range: Optional[str] = None


class CompositionIndexStatus(BaseModel):
    index_available: bool
    integrity_status: IntegrityStatus = IntegrityStatus.UNAVAILABLE
    generation_build_status: GenerationBuildStatus = GenerationBuildStatus.FAILED
    active_generation_id: Optional[str] = None
    built_at_utc: Optional[str] = None
    total_validated_evidence: int = 0
    located_evidence_count: int = 0
    unlocated_evidence_count: int = 0
    rejected_record_count: int = 0
    species_count: int = 0
    ingested_products_count: int = 0
    expected_products_count: int = 0
    discovery_scope: str = "static_seed_manifest"
    instruments_indexed: List[str] = Field(default_factory=list)
    checksum_valid: bool = True
    source_dependencies_valid: bool = True
    manifest_valid: bool = True
    missing_source_files: List[str] = Field(default_factory=list)
    checksum_mismatches: List[str] = Field(default_factory=list)
    missing_dependency_files: List[str] = Field(default_factory=list)
    dependency_checksum_mismatches: List[str] = Field(default_factory=list)
    missing_expected_products: List[str] = Field(default_factory=list)
    manifest_validation_errors: List[str] = Field(default_factory=list)
    rtree_enabled: bool = False
    crism_status: str = "unavailable_no_validated_mineral_cube"
    sqlite_path: Optional[str] = None
    reproducibility_manifest_path: Optional[str] = None
    product_manifests: List[Dict[str, Any]] = Field(default_factory=list)
    dependency_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    product_audit: List[Dict[str, Any]] = Field(default_factory=list)
    rights_summary: Dict[str, Any] = Field(default_factory=dict)
    retrieval_metadata: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
