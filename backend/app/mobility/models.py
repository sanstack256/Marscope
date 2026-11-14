"""
MARSCOPE Human Mobility Intelligence Domain Models & Enumerations
Martian Surface Intelligence & Exploration System
"""

from enum import Enum


class TerrainCoverageState(str, Enum):
    """
    Five mandatory coverage and unknown-data states for every evaluated cell or sample.
    Never conflates outside-footprint with inside-footprint nodata or boundary derivative loss.
    """

    OUTSIDE_SOURCE_FOOTPRINT = "outside_source_footprint"
    INSIDE_FOOTPRINT_NODATA = "inside_footprint_nodata"
    VALID_SOURCE_DATA = "valid_source_data"
    INSUFFICIENT_RESOLUTION_FOR_ANALYSIS = "insufficient_resolution_for_analysis"
    DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD = "derivative_unavailable_invalid_neighborhood"


class CellTraversalAvailabilityState(str, Enum):
    """
    Explicit traversal cost evaluation state for a terrain cell or segment.
    Unknown terrain is never assigned zero cost, and user-configured scenario
    exclusions are never labeled as universal physical 'unsafe' hazards.
    """

    EVALUATED = "evaluated"
    UNKNOWN_TERRAIN = "unknown_terrain"
    EXPLICIT_SCENARIO_EXCLUSION = "explicit_scenario_exclusion"
    INSUFFICIENT_SCENARIO_PARAMETERS = "insufficient_scenario_parameters"
    OUTSIDE_MODEL_VALID_DOMAIN = "outside_model_valid_domain"


class AnalysisScaleType(str, Enum):
    """
    Distinct spatial analysis regimes with different minimum DEM resolution requirements.
    """

    REGIONAL_ELEVATION_ANALYSIS = "regional_elevation_analysis"
    LOCAL_SLOPE_ANALYSIS = "local_slope_analysis"
    REGIONAL_ROUGHNESS_ANALYSIS = "regional_roughness_analysis"
    SMALL_SCALE_OBSTACLE_DETECTION = "small_scale_obstacle_detection"


class ResolutionSuitabilityLevel(str, Enum):
    """
    Honest classification of whether a DEM's native/effective pixel size supports a given analysis.
    """

    SUITABLE = "suitable"
    REGIONAL_APPROXIMATION_ONLY = "regional_approximation_only"
    INSUFFICIENT_RESOLUTION = "insufficient_resolution"
    UNAVAILABLE = "unavailable"


class ParameterOriginType(str, Enum):
    """
    Provenance classification for every parameter in a MobilityScenario or TraversalModel.
    """

    SOURCE_SUPPORTED_PHYSICAL_PARAMETER = "source_supported_physical_parameter"
    USER_CONFIGURED_ASSUMPTION = "user_configured_assumption"
    MODEL_DERIVED_PARAMETER = "model_derived_parameter"
    UNAVAILABLE = "unavailable"
