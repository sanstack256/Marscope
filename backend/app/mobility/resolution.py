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

from typing import Dict, Optional

from app.mobility.models import AnalysisScaleType, ResolutionSuitabilityLevel
from app.mobility.schemas import ResolutionSuitabilityAssessment


# Documented engineering resolution thresholds for planetary surface analysis (meters/pixel)
RECOMMENDED_MAX_RESOLUTION_METERS: Dict[AnalysisScaleType, float] = {
    AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS: 20000.0,   # <= 20 km/px supports regional topography
    AnalysisScaleType.REGIONAL_ROUGHNESS_ANALYSIS: 10000.0,   # <= 10 km/px supports macro-scale TRI
    AnalysisScaleType.LOCAL_SLOPE_ANALYSIS: 20.0,             # <= 20 m/px (e.g., CTX/HiRISE DEM) needed for local EVA slope
    AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION: 1.0,    # <= 1 m/px (e.g., HiRISE/Navcam stereo) needed for boulders/ledges
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
        if not dem_available or eff_m is None or eff_m <= 0.0:
            results[analysis_type.value] = ResolutionSuitabilityAssessment(
                analysis_type=analysis_type,
                suitability=ResolutionSuitabilityLevel.UNAVAILABLE,
                supported=False,
                native_resolution_m=nat_m,
                effective_resolution_m=eff_m,
                minimum_recommended_resolution_m=min_rec_m,
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
            if eff_m <= 100.0:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) resolves mesoscale terrain ruggedness."
                )
            elif eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) supports macro-scale regional TRI "
                    f"over a 3x3 (~{eff_m * 3.0:.0f} m) window only."
                )
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) is too coarse even for regional TRI "
                    f"(recommended <= {min_rec_m:.0f} m/pixel)."
                )
            caveat = (
                f"TRI at {eff_m:.1f} m/pixel measures multi-kilometer elevation relief, NOT meter-scale "
                "surface rockiness or foot-level roughness."
            )

        elif analysis_type == AnalysisScaleType.LOCAL_SLOPE_ANALYSIS:
            if eff_m <= min_rec_m:
                suitability = ResolutionSuitabilityLevel.SUITABLE
                supported = True
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) resolves local human-scale slopes "
                    f"(recommended <= {min_rec_m:.0f} m/pixel)."
                )
                caveat = "Horn 3x3 finite-difference slope averages gradient over a 3x3 pixel kernel."
            elif eff_m <= 500.0:
                suitability = ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY
                supported = False
                explanation = (
                    f"Effective grid spacing ({eff_m:.1f} m/pixel) resolves landform-scale gradients "
                    f"but cannot resolve local EVA slopes (<={min_rec_m:.0f} m/pixel required)."
                )
                caveat = "Sub-grid scarps and steep local slopes are strongly attenuated at this resolution."
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Coarse DEM ({eff_m:.1f} m/pixel; 3x3 Horn kernel spans ~{eff_m * 3.0:.0f} m) "
                    f"cannot resolve local human-scale slopes (requires <= {min_rec_m:.0f} m/pixel, e.g., HiRISE/CTX DEM)."
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
                    f"Effective grid spacing ({eff_m:.2f} m/pixel) can resolve meter-scale obstacles "
                    f"(recommended <= {min_rec_m:.1f} m/pixel)."
                )
            else:
                suitability = ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
                supported = False
                explanation = (
                    f"Grid spacing ({eff_m:.1f} m/pixel) is {eff_m / min_rec_m:.0f}x coarser than the "
                    f"<= {min_rec_m:.1f} m/pixel resolution required for small-scale obstacle/boulder detection."
                )
            caveat = (
                "Boulders, meter-scale craters, boxwork fractures, and regolith hazards are completely "
                "unresolved unless sub-meter stereo DEM products are ingested."
            )

        results[analysis_type.value] = ResolutionSuitabilityAssessment(
            analysis_type=analysis_type,
            suitability=suitability,
            supported=supported,
            native_resolution_m=round(nat_m, 3) if nat_m is not None else None,
            effective_resolution_m=round(eff_m, 3) if eff_m is not None else None,
            minimum_recommended_resolution_m=min_rec_m,
            explanation=explanation,
            scientific_caveat=caveat,
        )

    return results
