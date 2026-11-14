"""
MARSCOPE Resolution Adequacy Assessment
Martian Surface Intelligence & Exploration System

Evaluates whether available DEM, optical imagery, and geological mapping
resolutions support each Marswalk assessment domain using existing mobility
resolution policies. Never claims sub-pixel obstacle detection.
"""

from __future__ import annotations

from typing import List, Optional

from app.evidence_intelligence.schemas import ResolutionAdequacyRecord
from app.mobility.models import AnalysisScaleType, ResolutionSuitabilityLevel
from app.mobility.resolution import (
    RESOLUTION_POLICY_VERSION,
    evaluate_dem_resolution_suitability,
)


def _map_level(level: ResolutionSuitabilityLevel) -> str:
    if level == ResolutionSuitabilityLevel.SUITABLE:
        return "adequate"
    if level == ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY:
        return "resolution_limited"
    if level == ResolutionSuitabilityLevel.UNAVAILABLE:
        return "unavailable"
    return "insufficient"


def assess_resolution_adequacy(
    *,
    dem_dataset_id: str,
    dem_native_resolution_m: float,
    dem_effective_resolution_m: Optional[float] = None,
    optical_dataset_id: Optional[str] = None,
    optical_pixel_scale_m: Optional[float] = None,
    geological_map_available: bool = False,
) -> List[ResolutionAdequacyRecord]:
    """Produce resolution adequacy records across terrain, optical, and geology domains."""
    dem_eval = evaluate_dem_resolution_suitability(
        native_resolution_m=dem_native_resolution_m,
        effective_resolution_m=dem_effective_resolution_m or dem_native_resolution_m,
        dem_available=True,
    )
    slope_assess = dem_eval.get(AnalysisScaleType.LOCAL_SLOPE_ANALYSIS.value)
    obs_assess = dem_eval.get(AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION.value)

    dem_status = _map_level(slope_assess.suitability) if slope_assess else (
        "adequate" if dem_native_resolution_m <= 2.0 else "resolution_limited"
    )
    obs_status = _map_level(obs_assess.suitability) if obs_assess else "insufficient"

    records: List[ResolutionAdequacyRecord] = [
        ResolutionAdequacyRecord(
            analysis_domain="dem_slope_and_5m_tri",
            status=dem_status,
            source_dataset_id=dem_dataset_id,
            native_resolution_m=dem_native_resolution_m,
            policy_version=RESOLUTION_POLICY_VERSION,
            rationale=(
                slope_assess.explanation
                if slope_assess
                else f"DEM grid spacing is {dem_native_resolution_m:.2f} m/px."
            ),
        ),
        ResolutionAdequacyRecord(
            analysis_domain="sub_meter_micro_obstacles",
            status=obs_status,
            source_dataset_id=dem_dataset_id,
            native_resolution_m=dem_native_resolution_m,
            policy_version=RESOLUTION_POLICY_VERSION,
            rationale=(
                obs_assess.explanation
                if obs_assess
                else (
                    f"DEM grid spacing is {dem_native_resolution_m:.2f} m/px; cobbles, fractures, "
                    f"and micro-obstacles smaller than {dem_native_resolution_m * 2.0:.1f} m are unresolved."
                )
            ),
        ),
    ]

    if optical_dataset_id and optical_pixel_scale_m is not None:
        opt_status = "adequate" if optical_pixel_scale_m <= 0.5 else "resolution_limited"
        records.append(
            ResolutionAdequacyRecord(
                analysis_domain="optical_surface_candidates",
                status=opt_status,
                source_dataset_id=optical_dataset_id,
                native_resolution_m=optical_pixel_scale_m,
                policy_version=RESOLUTION_POLICY_VERSION,
                rationale=(
                    f"HiRISE orthophoto native scale is {optical_pixel_scale_m:.2f} m/px; "
                    "surface contrast anomalies are candidates requiring human/scientific review."
                ),
            )
        )
    else:
        records.append(
            ResolutionAdequacyRecord(
                analysis_domain="optical_surface_candidates",
                status="unavailable",
                source_dataset_id=optical_dataset_id,
                native_resolution_m=None,
                policy_version=RESOLUTION_POLICY_VERSION,
                rationale="No locally acquired orthophoto covering this corridor.",
            )
        )

    records.append(
        ResolutionAdequacyRecord(
            analysis_domain="geological_unit_mapping",
            status="insufficient" if geological_map_available else "unavailable",
            source_dataset_id="usgs_sim3292" if geological_map_available else None,
            native_resolution_m=None,
            policy_version=RESOLUTION_POLICY_VERSION,
            rationale=(
                "USGS SIM 3292 is 1:20,000,000 planetary scale — regional context only, "
                "insufficient for local Marswalk unit or bearing-strength determination."
                if geological_map_available
                else "No local geological map verified for this corridor."
            ),
        )
    )
    return records
