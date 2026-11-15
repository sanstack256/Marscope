"""
MARSCOPE Terrain Uncertainty Domain Models & Enumerations
"""

from __future__ import annotations

from enum import Enum

UNCERTAINTY_MODEL_VERSION = "terrain_uncertainty_v1.0"
RESOLUTION_OBSERVABILITY_VERSION = "observability_policy_v1.0"


class UncertaintyStatus(str, Enum):
    """Explicit epistemic status of an uncertainty estimate."""

    QUANTIFIED_FROM_RASTER_ERROR_BAND = "QUANTIFIED_FROM_RASTER_ERROR_BAND"
    QUANTIFIED_FROM_METADATA = "QUANTIFIED_FROM_METADATA"
    QUANTIZATION_LOWER_BOUND_ONLY = "QUANTIZATION_LOWER_BOUND_ONLY"
    UNCERTAINTY_UNQUANTIFIED = "UNCERTAINTY_UNQUANTIFIED"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNAVAILABLE = "UNAVAILABLE"


class MeasurementQuantityKind(str, Enum):
    """Distinguishes statistical measures, quantization limits, and spatial resolution."""

    STANDARD_DEVIATION = "STANDARD_DEVIATION"
    RMSE = "RMSE"
    CONFIDENCE_INTERVAL_95 = "CONFIDENCE_INTERVAL_95"
    MAXIMUM_ERROR_BOUND = "MAXIMUM_ERROR_BOUND"
    APPROXIMATE_UNCERTAINTY_BOUND = "APPROXIMATE_UNCERTAINTY_BOUND"
    SENSITIVITY_BOUND = "SENSITIVITY_BOUND"
    QUANTIZATION_STEP = "QUANTIZATION_STEP"
    GRID_SPACING_RESOLUTION = "GRID_SPACING_RESOLUTION"
    NOMINAL_PRECISION_METADATA = "NOMINAL_PRECISION_METADATA"
    UNQUANTIFIED = "UNQUANTIFIED"


class FeatureObservabilityState(str, Enum):
    """Resolution-aware observability state for a physical feature or analysis scale."""

    RESOLVED_FOR_ANALYSIS = "RESOLVED_FOR_ANALYSIS"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLUTION_LIMITED = "RESOLUTION_LIMITED"
    BELOW_SOURCE_RESOLUTION = "BELOW_SOURCE_RESOLUTION"
    NOT_VALIDATED = "NOT_VALIDATED"
    UNKNOWN = "UNKNOWN"


class AnalysisScaleCategory(str, Enum):
    """Distinct geomorphological & operational analysis categories."""

    REGIONAL_ELEVATION = "regional_elevation"
    LOCAL_SLOPE = "local_slope"
    TERRAIN_RUGGEDNESS_TRI = "terrain_ruggedness_tri"
    RIDGE_LIKE_LANDFORM = "ridge_like_landform"
    CANDIDATE_BOULDER_FEATURE = "candidate_boulder_feature"
    SMALL_OBSTACLE_HAZARD = "small_obstacle_hazard"
    LOCAL_OUTCROP_GEOLOGY = "local_outcrop_geology"


class TerrainTraversabilityState(str, Enum):
    """Strict three-state terrain classification preserving unknown terrain vs constraints."""

    EVALUATED = "EVALUATED"
    KNOWN_CONSTRAINT_EXCLUSION = "KNOWN_CONSTRAINT_EXCLUSION"
    UNKNOWN_INSUFFICIENTLY_OBSERVED = "UNKNOWN_INSUFFICIENTLY_OBSERVED"
