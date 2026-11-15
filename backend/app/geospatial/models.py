"""
MARSCOPE Planetary Spatial Intelligence Domain Models & Enumerations
Prompt 19 Parts 3, 4, 5, 7 & 10: Authoritative CRS registry models, validation states,
multi-mission spatial registration assessment states, footprint/coverage models, morphology
epistemic ladder states, and rover observation spatial association states.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


CRS_REGISTRY_VERSION = "mars_crs_registry_v2.0"


class CoordinateValidationState(str, Enum):
    CRS_VALIDATED = "CRS_VALIDATED"
    CRS_VALID_WITH_LIMITATIONS = "CRS_VALID_WITH_LIMITATIONS"
    CRS_UNVERIFIED = "CRS_UNVERIFIED"
    CRS_INCOMPATIBLE = "CRS_INCOMPATIBLE"
    CRS_UNSUPPORTED = "CRS_UNSUPPORTED"
    COORDINATE_CONVENTION_UNVERIFIED = "COORDINATE_CONVENTION_UNVERIFIED"
    VERTICAL_DATUM_UNVERIFIED = "VERTICAL_DATUM_UNVERIFIED"
    TRANSFORMATION_FAILED = "TRANSFORMATION_FAILED"


class CrsCategory(str, Enum):
    IAU_ELLIPSOID = "IAU_ELLIPSOID"
    IAU_SPHERE = "IAU_SPHERE"
    PRODUCT_SPECIFIC_DATUM = "PRODUCT_SPECIFIC_DATUM"
    PROJECTED_PLANETARY_CRS = "PROJECTED_PLANETARY_CRS"
    LOCAL_STUDY_AREA_PROJECTION = "LOCAL_STUDY_AREA_PROJECTION"
    UNKNOWN_PLANETARY_REFERENCE = "UNKNOWN_PLANETARY_REFERENCE"


class VerticalDatumKind(str, Enum):
    REFERENCE_SPHERE_ELEVATION = "REFERENCE_SPHERE_ELEVATION"
    ELLIPSOID_RELATIVE_ELEVATION = "ELLIPSOID_RELATIVE_ELEVATION"
    AREOID_RELATIVE_ELEVATION = "AREOID_RELATIVE_ELEVATION"
    PRODUCT_SPECIFIC_VERTICAL_DATUM = "PRODUCT_SPECIFIC_VERTICAL_DATUM"
    UNKNOWN_VERTICAL_REFERENCE = "UNKNOWN_VERTICAL_REFERENCE"


class MarsCrsDefinition(BaseModel):
    identifier: str
    aliases: List[str] = Field(default_factory=list)
    registry_version: str = CRS_REGISTRY_VERSION
    crs_category: CrsCategory
    planetary_body: str = "Mars"
    authority: str
    authority_document: str
    specification_version: str
    shape_type: str  # "ellipsoid" | "sphere"
    semi_major_axis_m: float
    semi_minor_axis_m: float
    reference_radii_m: Dict[str, float]
    coordinate_frame: str
    latitude_convention: str
    longitude_convention: str
    longitude_domain: str
    projection: str
    proj4_string: str
    vertical_reference: VerticalDatumKind
    vertical_datum_name: str
    validity_conditions: List[str] = Field(default_factory=list)
    supported_transformations: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    verification_timestamp_utc: Optional[str] = None
    verification_source: Optional[str] = None
    verification_method: Optional[str] = None


class CrsValidationResult(BaseModel):
    input_crs: Optional[str] = None
    canonical_identifier: Optional[str] = None
    valid: bool
    validation_state: CoordinateValidationState
    crs_category: CrsCategory
    planetary_body: str = "unknown"
    shape_type: Optional[str] = None
    semi_major_axis_m: Optional[float] = None
    semi_minor_axis_m: Optional[float] = None
    latitude_convention: str = "unknown"
    longitude_convention: str = "unknown"
    vertical_reference: VerticalDatumKind = VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
    is_projected: bool = False
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    verified_event_method: Optional[str] = None
    verified_at_utc: Optional[str] = None


class CoordinateTransformationResult(BaseModel):
    success: bool
    validation_state: CoordinateValidationState
    source_crs: str
    target_crs: str
    algorithm: str
    library: str = "pyproj"
    library_version: str
    input_coordinates: Dict[str, float]
    output_coordinates: Optional[Dict[str, float]] = None
    axis_order: str = "longitude_east_deg, latitude_deg"
    longitude_normalization: str
    latitude_convention_in: str
    latitude_convention_out: str
    ellipsoid_assumptions: str
    vertical_reference_in: VerticalDatumKind
    vertical_reference_out: VerticalDatumKind
    vertical_compatible: bool
    known_error_or_limitation: Optional[str] = None
    failure_reason: Optional[str] = None
    provenance_steps: List[str] = Field(default_factory=list)


class VerticalDatumComparisonResult(BaseModel):
    compatible: bool
    validation_state: CoordinateValidationState
    datum_a: VerticalDatumKind
    datum_b: VerticalDatumKind
    is_absolute_elevation_a: bool
    is_absolute_elevation_b: bool
    requires_validated_transformation: bool
    explanation: str
    warnings: List[str] = Field(default_factory=list)


class SpatialRegistrationAssessmentState(str, Enum):
    VALIDATED_REGISTRATION = "VALIDATED_REGISTRATION"
    VALIDATED_WITH_LIMITATIONS = "VALIDATED_WITH_LIMITATIONS"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
    RELATIVE_ALIGNMENT_ONLY = "RELATIVE_ALIGNMENT_ONLY"
    NOT_REGISTERED = "NOT_REGISTERED"
    REGISTRATION_UNVERIFIED = "REGISTRATION_UNVERIFIED"
    INCOMPATIBLE_COORDINATES = "INCOMPATIBLE_COORDINATES"
    INSUFFICIENT_CONTROL = "INSUFFICIENT_CONTROL"
    REGISTRATION_FAILED = "REGISTRATION_FAILED"


class SpatialGapCause(str, Enum):
    NO_OBSERVATION = "NO_OBSERVATION"
    INVALID_DATA_ONLY = "INVALID_DATA_ONLY"
    INSUFFICIENT_RESOLUTION = "INSUFFICIENT_RESOLUTION"
    SCIENTIFICALLY_IRRELEVANT = "SCIENTIFICALLY_IRRELEVANT"
    NOT_SPATIALLY_REGISTERED = "NOT_SPATIALLY_REGISTERED"


class ObservationCategory(str, Enum):
    OPTICAL = "optical"
    ELEVATION = "elevation"
    SPECTRAL = "spectral"
    THERMAL = "thermal"
    ROVER = "rover"
    ENVIRONMENTAL = "environmental"


class RoverAssociationState(str, Enum):
    DIRECT_SPATIAL_ASSOCIATION = "DIRECT_SPATIAL_ASSOCIATION"
    ASSOCIATED_WITH_UNCERTAINTY = "ASSOCIATED_WITH_UNCERTAINTY"
    REGIONAL_CONTEXT_ONLY = "REGIONAL_CONTEXT_ONLY"
    SCALE_INCOMPATIBLE = "SCALE_INCOMPATIBLE"
    LOCATION_UNVERIFIED = "LOCATION_UNVERIFIED"
    NOT_ASSOCIATED = "NOT_ASSOCIATED"
    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"


class MorphologyEpistemicState(str, Enum):
    OBSERVED_IMAGE_PATTERN = "OBSERVED_IMAGE_PATTERN"
    OBSERVED_TOPOGRAPHIC_PATTERN = "OBSERVED_TOPOGRAPHIC_PATTERN"
    ALGORITHMIC_CANDIDATE = "ALGORITHMIC_CANDIDATE"
    EXPERT_INTERPRETATION = "EXPERT_INTERPRETATION"
    SCIENTIFIC_HYPOTHESIS = "SCIENTIFIC_HYPOTHESIS"
    CONFIRMED_BY_INDEPENDENT_EVIDENCE = "CONFIRMED_BY_INDEPENDENT_EVIDENCE"
    UNRESOLVED = "UNRESOLVED"


class MorphologyFeatureClass(str, Enum):
    LINEAR_RIDGE = "linear_ridge"
    POLYGONAL_RIDGE_NETWORK = "polygonal_ridge_network"
    FRACTURE_LIKE_LINEAMENT = "fracture_like_lineament"
    CHANNEL = "channel"
    FAN = "fan"
    LAYER_BOUNDARY = "layer_boundary"
    SCARP = "scarp"
    CRATER_RIM = "crater_rim"
    DEPRESSION = "depression"
    KNOB = "knob"
    BOULDER = "boulder"
    TALUS_LIKE_DEPOSIT = "talus_like_deposit"
    OUTCROP_BOUNDARY = "outcrop_boundary"
    BEDDING_LIKE_STRUCTURE = "bedding_like_structure"
    AEOLIAN_BEDFORM = "aeolian_bedform"
