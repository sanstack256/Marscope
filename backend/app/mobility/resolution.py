"""
MARSCOPE DEM Resolution Suitability Engine
Martian Surface Intelligence & Exploration System

Evaluates whether a DEM's native and effective pixel resolution supports:
  1. Regional elevation analysis
  2. Local human-scale slope analysis
  3. Regional roughness analysis
  4. Small-scale obstacle / rock hazard detection

A 4 pixel/degree global MOLA product (~6.6–14.8 km/pixel) is never treated as
suitable for local human-scale slope or foot-level obstacle detection.
"""

import json
from pathlib import Path
from typing import Dict, Optional

from app.mobility.models import AnalysisScaleType, ResolutionSuitabilityLevel
from app.mobility.schemas import ResolutionSuitabilityAssessment


RESOLUTION_POLICY = json.loads(
    (Path(__file__).parent / "policies" / "resolution_v1.json").read_text(encoding="utf-8")
)
RESOLUTION_POLICY_VERSION = RESOLUTION_POLICY["version"]
_PARAMETERS = RESOLUTION_POLICY["parameters"]

# These are versioned planning screens, not scientific detection limits.
RECOMMENDED_MAX_RESOLUTION_METERS: Dict[AnalysisScaleType, float] = {
    AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS: _PARAMETERS["regional_elevation_analysis"]["maximum_effective_spacing_m"],
    AnalysisScaleType.REGIONAL_ROUGHNESS_ANALYSIS: _PARAMETERS["regional_roughness_analysis"]["maximum_effective_spacing_m"],
    AnalysisScaleType.LOCAL_SLOPE_ANALYSIS: _PARAMETERS["local_slope_analysis"]["maximum_effective_spacing_m"],
    AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION: _PARAMETERS["small_scale_obstacle_detection"]["maximum_effective_spacing_m"],
}


def evaluate_dem_resolution_suitability(
    *,
    native_resolution_m: Optional[float],
    effective_resolution_m: Optional[float] = None,
    dem_available: bool = True,
) -> Dict[str, ResolutionSuitabilityAssessment]:
    """
    Evaluate resolution suitability across all four mandatory spatial analysis scales.
    """
    eff_m = effective_resolution_m if effective_resolution_m is not None else native_resolution_m
    nat_m = native_resolution_m if native_resolution_m is not None else eff_m

    results: Dict[str, ResolutionSuitabilityAssessment] = {}

    for analysis_type, min_rec_m in RECOMMENDED_MAX_RESOLUTION_METERS.items():
        policy_key = {
            AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS: "regional_elevation_analysis",
            AnalysisScaleType.REGIONAL_ROUGHNESS_ANALYSIS: "regional_roughness_analysis",
            AnalysisScaleType.LOCAL_SLOPE_ANALYSIS: "local_slope_analysis",
            AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION: "small_scale_obstacle_detection",
        }[analysis_type]
        policy_parameter = _PARAMETERS[policy_key]
        if not dem_available or eff_m is None or eff_m <= 0.0:
            results[analysis_type.value] = ResolutionSuitabilityAssessment(
                analysis_type=analysis_type,
                suitability=ResolutionSuitabilityLevel.UNAVAILABLE,
                supported=False,
                native_resolution_m=nat_m,
                effective_resolution_m=eff_m,
                minimum_recommended_resolution_m=min_rec_m,
                policy_id=RESOLUTION_POLICY["policy_id"],
                policy_version=RESOLUTION_POLICY_VERSION,
                threshold_classification=policy_parameter["classification"],
                threshold_rationale=policy_parameter["rationale"],
                explanation="DEM raster is not locally available or resolution metadata is unknown.",
                scientific_caveat="Cannot evaluate terrain at this scale without a verified local DEM.",
            )
            continue

        if analysis_type == AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS:
            if eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) resolves regional elevation trends "
                    f"and basin/mound hypsometry (recommended <= {min_rec_m:.0f} m/pixel)."
                )
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) is coarser than {min_rec_m:.0f} m/pixel."
                )
            caveat = (
                f"Each pixel averages elevation over a ~{eff_m:.0f} m footprint; sub-pixel ridges, "
                "troughs, and scarps are smoothed out."
            )

        elif analysis_type == AnalysisScaleType.REGIONAL_ROUGHNESS_ANALYSIS:
            mesoscale_spacing_m = _PARAMETERS["regional_roughness_analysis"]["mesoscale_spacing_m"]
            if eff_m <= mesoscale_spacing_m:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = f"Effective grid spacing ({eff_m:.1f} m/pixel) passes the MARSCOPE mesoscale TRI screen (<= {mesoscale_spacing_m:.0f} m/pixel); this is an unvalidated engineering heuristic."
            elif eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) passes the MARSCOPE macro-scale TRI screen "
                    f"over a 3x3 (~{eff_m * 3.0:.0f} m) window only; this is an unvalidated engineering heuristic."
                )
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) is too coarse even for regional TRI "
                    f"(recommended <= {min_rec_m:.0f} m/pixel)."
                )
            caveat = (
                f"TRI at {eff_m:.1f} m/pixel summarizes relief over its processing window. It does not establish "
                "meter-scale surface rockiness or foot-level roughness; policy screens are unvalidated heuristics."
            )

        elif analysis_type == AnalysisScaleType.LOCAL_SLOPE_ANALYSIS:
            if eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) passes the MARSCOPE local-slope scale screen "
                    f"(<= {min_rec_m:.0f} m/pixel); this does not certify the accuracy of a slope measurement."
                )
                caveat = "Horn 3x3 finite-difference slope averages gradient over a 3x3 pixel kernel. Resolution suitability is engineering guidance only and does not establish feature detectability or source accuracy."
            elif eff_m <= _PARAMETERS["local_slope_analysis"]["regional_approximation_spacing_m"]:
                suitability = ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY
                supported = False
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) is within the regional-approximation screen "
                    f"but cannot resolve local EVA slopes (<={min_rec_m:.0f} m/pixel required)."
                )
                caveat = "Sub-grid scarps and steep local slopes are strongly attenuated at this resolution."
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Coarse DEM ({eff_m:.1f} m/pixel; 3x3 Horn kernel spans ~{eff_m * 3.0:.0f} m) "
                    f"is outside the local-slope screen (<= {min_rec_m:.0f} m/pixel)."
                )
                caveat = (
                    "Reported slope values represent regional multi-kilometer gradients only and must "
                    "never be interpreted as local foot-level or rover-scale slope angles."
                )

        else:  # AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION
            if eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.2f} m/pixel) passes the MARSCOPE resolution-only obstacle screen "
                    f"(<= {min_rec_m:.1f} m/pixel). This does not establish obstacle detection capability."
                )
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Grid spacing ({eff_m:.1f} m/pixel) is {eff_m / min_rec_m:.0f}x coarser than the "
                    f"<= {min_rec_m:.1f} m/pixel resolution required for small-scale obstacle/boulder detection."
                )
            caveat = (
                "Resolution-only heuristic. Feature scale and contrast, source accuracy, observation geometry, and processing affect detectability and are unavailable here; a passing value is not a detection guarantee."
            )

        results[analysis_type.value] = ResolutionSuitabilityAssessment(
            analysis_type=analysis_type,
            suitability=suitability,
            supported=supported,
            native_resolution_m=round(nat_m, 3) if nat_m is not None else None,
            effective_resolution_m=round(eff_m, 3) if eff_m is not None else None,
            minimum_recommended_resolution_m=min_rec_m,
            policy_id=RESOLUTION_POLICY["policy_id"],
            policy_version=RESOLUTION_POLICY_VERSION,
            threshold_classification=policy_parameter["classification"],
            threshold_rationale=policy_parameter["rationale"],
            explanation=explanation,
            scientific_caveat=caveat,
        )

    return results
