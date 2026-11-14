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
    source_dataset_id: str
    product_id: str
    source_record_ref: str
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
    uncertainty_value: Optional[float] = None
    uncertainty_unit: Optional[str] = None
    uncertainty_type: Optional[str] = None
    detection_limit_value: Optional[float] = None
    detection_limit_unit: Optional[str] = None
    quality_flag: Optional[str] = None

    methodology: str
    provenance_url: Optional[str] = None
    source_reference: str
    citation: Optional[str] = None

    # Spatial coordinates & footprint (explicitly separated unlocated vs verified)
    location_verified: bool = False
    latitude: Optional[float] = None
    longitude_east: Optional[float] = None
    elevation_m: Optional[float] = None
    crs: Optional[str] = None
    latitude_convention: Optional[str] = None
    longitude_direction: Optional[str] = None
    coordinate_source: Optional[str] = None
    coordinate_provenance: Optional[str] = None
    coordinate_uncertainty_m: Optional[float] = None
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
    evidence_tier_score: float = Field(..., description="Instrument/methodology tier (1.0=direct mineral/oxide, 0.55=element-bearing host)")
    abundance_component: float = Field(..., description="Normalized abundance contribution [0, 1] within query scale")
    quality_component: float = Field(..., description="Uncertainty & calibration quality score [0, 1]")
    corroboration_component: float = Field(..., description="Independent instrument/observation corroboration [0, 1]")
    spatial_proximity_component: Optional[float] = Field(
        None, description="Inverse Mars geodesic distance factor [0, 1] when astronaut position provided"
    )
    composite_rank_score: float = Field(..., description="Transparent weighted ranking score for candidate sorting only (NOT probability %)")
    score_formula: str = Field(..., description="Exact formula documenting weights used")
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
    coordinate_source: str
    coordinate_uncertainty_m: Optional[float] = None
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
    active_generation_id: Optional[str] = None
    built_at_utc: Optional[str] = None
    total_validated_evidence: int = 0
    located_evidence_count: int = 0
    unlocated_evidence_count: int = 0
    rejected_record_count: int = 0
    species_count: int = 0
    ingested_products_count: int = 0
    instruments_indexed: List[str] = Field(default_factory=list)
    checksum_valid: bool = True
    rtree_enabled: bool = False
    crism_status: str = "unavailable_no_validated_mineral_cube"
    sqlite_path: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
