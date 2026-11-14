"""
MARSCOPE Terrain Uncertainty, Resolution Observability & Sensitivity Engine
Martian Surface Intelligence & Exploration System

Quantifies terrain elevation, slope, roughness, and registration uncertainty strictly
from verified NASA PDS3 labels, dataset catalog metadata, quantization limits, and
supplied error rasters without ever fabricating error bounds or conflating resolution
with vertical accuracy.
"""

from app.terrain_uncertainty.models import (
    AnalysisScaleCategory,
    FeatureObservabilityState,
    MeasurementQuantityKind,
    RESOLUTION_OBSERVABILITY_VERSION,
    TerrainTraversabilityState,
    UNCERTAINTY_MODEL_VERSION,
    UncertaintyStatus,
)
from app.terrain_uncertainty.sensitivity import (
    DEFAULT_SENSITIVITY_SCENARIOS,
    RouteSensitivityReport,
    RouteStabilityStatus,
    SENSITIVITY_POLICY_ID,
    SENSITIVITY_POLICY_VERSION,
    ScenarioSensitivityOutcome,
    SensitivityScenarioConfig,
    summarize_sensitivity_outcomes,
)
from app.terrain_uncertainty.service import TerrainUncertaintyService

__all__ = [
    "AnalysisScaleCategory",
    "DEFAULT_SENSITIVITY_SCENARIOS",
    "FeatureObservabilityState",
    "MeasurementQuantityKind",
    "RESOLUTION_OBSERVABILITY_VERSION",
    "RouteSensitivityReport",
    "RouteStabilityStatus",
    "SENSITIVITY_POLICY_ID",
    "SENSITIVITY_POLICY_VERSION",
    "ScenarioSensitivityOutcome",
    "SensitivityScenarioConfig",
    "TerrainTraversabilityState",
    "TerrainUncertaintyService",
    "UNCERTAINTY_MODEL_VERSION",
    "UncertaintyStatus",
    "summarize_sensitivity_outcomes",
]
