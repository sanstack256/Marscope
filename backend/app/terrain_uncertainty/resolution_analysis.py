"""
MARSCOPE Resolution-Aware Feature Observability & Negative-Evidence Logic
Enforces strict Nyquist observability floors and prohibits equating zero detected
hazards with obstacle-free terrain when resolution cannot observe small obstacles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.terrain_uncertainty.models import (
    AnalysisScaleCategory,
    FeatureObservabilityState,
    RESOLUTION_OBSERVABILITY_VERSION,
)
from app.terrain_uncertainty.schemas import (
    FeatureObservabilityRecord,
    NegativeEvidenceStatement,
)


@dataclass(frozen=True)
class _ScaleRule:
    category: AnalysisScaleCategory
    label: str
    feature_target_m: float
    nyquist_factor: float
    prefer_optical: bool
    classification: str  # engineering_screen | resolution_limit | unvalidated_heuristic
    rationale_prefix: str


_SCALE_RULES: Tuple[_ScaleRule, ...] = (
    _ScaleRule(
        category=AnalysisScaleCategory.REGIONAL_ELEVATION,
        label="Regional Elevation & Macro Basin Relief (>500 m)",
        feature_target_m=500.0,
        nyquist_factor=2.0,
        prefer_optical=False,
        classification="resolution_limit",
        rationale_prefix="Regional relief profiles only require multi-hundred-meter DEM spacing.",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.LOCAL_SLOPE,
        label="Local Slope Gradient (Horn 3x3 m-scale screening)",
        feature_target_m=2.0,
        nyquist_factor=1.0,
        prefer_optical=False,
        classification="engineering_screen",
        rationale_prefix="Engineering traversability slope screening requires <= 2.0 m/px DEM (resolves >= 4-6 m ramps; sub-meter breaks smooth out).",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.TERRAIN_RUGGEDNESS_TRI,
        label="Terrain Ruggedness Index (Multi-meter Relief Window)",
        feature_target_m=5.0,
        nyquist_factor=2.0,
        prefer_optical=False,
        classification="engineering_screen",
        rationale_prefix="TRI summarizes multi-meter relief across a ~5 m physical window; never equates to cm-scale rock distribution.",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.RIDGE_LIKE_LANDFORM,
        label="Ridge-like Landforms & Boxwork Polygons (~3-20 m crests)",
        feature_target_m=3.0,
        nyquist_factor=3.0,
        prefer_optical=False,
        classification="resolution_limit",
        rationale_prefix="Boxwork fracture ridges span ~1-15 m width; multi-pixel crests appear in <= 1 m DTMs while narrower fins drop below stereo correlation scale.",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.CANDIDATE_BOULDER_FEATURE,
        label="Candidate Boulder Features (~0.5-1.5 m optical scale)",
        feature_target_m=0.75,
        nyquist_factor=3.0,
        prefer_optical=True,
        classification="resolution_limit",
        rationale_prefix="Minimum ~3x0.25 m = 0.75 m needed to distinguish >= 0.75-1.0 m boulders morphologically in orthoimagery; smaller blocks cannot be verified.",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.SMALL_OBSTACLE_HAZARD,
        label="Small Human/Rover Obstacle Hazards (0.15-0.45 m blocks, wheel traps)",
        feature_target_m=0.30,
        nyquist_factor=3.0,
        prefer_optical=True,
        classification="resolution_limit",
        rationale_prefix="0.15-0.45 m obstacles require <= 0.10 m/px imagery/LiDAR; HiRISE 0.25 m/px & 1.0 m DTMs fundamentally cannot certify absence.",
    ),
    _ScaleRule(
        category=AnalysisScaleCategory.LOCAL_OUTCROP_GEOLOGY,
        label="Local Outcrop Bedding & Fracture Geometry",
        feature_target_m=1.0,
        nyquist_factor=4.0,
        prefer_optical=True,
        classification="resolution_limit",
        rationale_prefix="Meter-scale outcrop morphology benefits from 0.25 m/px optical tone + stereo context, yet cm-scale textures require landed camera verification.",
    ),
)


def evaluate_feature_observability(
    *,
    dem_dataset_id: str,
    dem_resolution_m: Optional[float],
    optical_dataset_id: Optional[str] = None,
    optical_resolution_m: Optional[float] = None,
) -> Tuple[List[FeatureObservabilityRecord], NegativeEvidenceStatement]:
    """
    Classify all seven analysis scales strictly by native sensor resolution and physical
    Nyquist resolvability, paired with an explicit negative-evidence guarantee.
    """
    records: List[FeatureObservabilityRecord] = []
    unresolved_classes: List[str] = []

    for rule in _SCALE_RULES:
        if rule.prefer_optical and optical_resolution_m is not None:
            px_scale = float(optical_resolution_m)
            src_id = optical_dataset_id or dem_dataset_id
        else:
            px_scale = float(dem_resolution_m) if dem_resolution_m is not None else None
            src_id = dem_dataset_id

        if px_scale is None or px_scale <= 0:
            records.append(
                FeatureObservabilityRecord(
                    category=rule.category,
                    observability_state=FeatureObservabilityState.UNKNOWN,
                    source_dataset_id=src_id,
                    native_pixel_scale_m=None,
                    minimum_resolvable_feature_size_m=None,
                    minimum_recommended_spacing_m=round(rule.feature_target_m / rule.nyquist_factor, 3),
                    nyquist_factor_pixels=rule.nyquist_factor,
                    policy_id="MARSCOPE-OBS",
                    policy_version=RESOLUTION_OBSERVABILITY_VERSION,
                    classification=rule.classification,
                    negative_evidence_permitted=False,
                    negative_evidence_statement="Pixel resolution unknown; zero detections cannot support hazard absence.",
                    rationale=f"{rule.rationale_prefix} Pixel spacing is unavailable.",
                )
            )
            unresolved_classes.append(rule.label)
            continue

        min_resolvable_m = px_scale * rule.nyquist_factor
        max_rec_spacing = rule.feature_target_m / rule.nyquist_factor if rule.nyquist_factor > 1.0 else rule.feature_target_m

        if rule.category == AnalysisScaleCategory.SMALL_OBSTACLE_HAZARD:
            # Strict rule: orbital 0.25-1.0 m sensors NEVER resolve 0.15-0.45 m boots/wheel-trap hazards cleanly
            if px_scale <= 0.10:
                state = FeatureObservabilityState.RESOLVED_FOR_ANALYSIS
                neg_ok = True
            elif px_scale <= 0.35:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False
            else:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False
        elif rule.category == AnalysisScaleCategory.CANDIDATE_BOULDER_FEATURE:
            if px_scale <= 0.30 and rule.prefer_optical and optical_resolution_m is not None:
                # 0.25 m ortho resolves >= ~0.75 m boulders PARTIALLY/UNVALIDATED, sub-0.5m remains unresolved
                state = FeatureObservabilityState.NOT_VALIDATED
                neg_ok = False
            elif px_scale <= max_rec_spacing:
                state = FeatureObservabilityState.PARTIALLY_RESOLVED
                neg_ok = False
            else:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False
        elif rule.category == AnalysisScaleCategory.RIDGE_LIKE_LANDFORM:
            if px_scale <= 1.2:
                state = FeatureObservabilityState.PARTIALLY_RESOLVED
                neg_ok = False
            elif px_scale <= 5.0:
                state = FeatureObservabilityState.RESOLUTION_LIMITED
                neg_ok = False
            else:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False
        elif rule.category == AnalysisScaleCategory.LOCAL_OUTCROP_GEOLOGY:
            if px_scale <= 0.35 and optical_resolution_m is not None:
                state = FeatureObservabilityState.PARTIALLY_RESOLVED
                neg_ok = False
            elif px_scale <= 2.0:
                state = FeatureObservabilityState.RESOLUTION_LIMITED
                neg_ok = False
            else:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False
        else:
            # regional_elevation, local_slope, terrain_ruggedness_tri
            if px_scale <= max_rec_spacing:
                state = FeatureObservabilityState.RESOLVED_FOR_ANALYSIS
                neg_ok = False  # Even 1m DTM only resolves >=2-3m slopes, never sub-pixel hazards
            elif px_scale <= max_rec_spacing * 2.5:
                state = FeatureObservabilityState.RESOLUTION_LIMITED
                neg_ok = False
            else:
                state = FeatureObservabilityState.BELOW_SOURCE_RESOLUTION
                neg_ok = False

        if state in {
            FeatureObservabilityState.BELOW_SOURCE_RESOLUTION,
            FeatureObservabilityState.RESOLUTION_LIMITED,
            FeatureObservabilityState.NOT_VALIDATED,
            FeatureObservabilityState.PARTIALLY_RESOLVED,
            FeatureObservabilityState.UNKNOWN,
        }:
            unresolved_classes.append(f"{rule.category.value} ({state.value})")

        neg_stmt = (
            "Resolved for aggregate macro-scale terrain metrics, yet sub-pixel hazard absence cannot be certified."
            if state == FeatureObservabilityState.RESOLVED_FOR_ANALYSIS
            else (
                f"Zero orbital detections in '{src_id}' ({px_scale:.2f} m/px) DO NOT imply obstacle-free ground; "
                f"minimum ~{min_resolvable_m:.2f} m morphological scale required."
            )
        )

        records.append(
            FeatureObservabilityRecord(
                category=rule.category,
                observability_state=state,
                source_dataset_id=src_id,
                native_pixel_scale_m=round(px_scale, 4),
                minimum_resolvable_feature_size_m=round(min_resolvable_m, 3),
                minimum_recommended_spacing_m=round(max_rec_spacing, 3),
                nyquist_factor_pixels=rule.nyquist_factor,
                policy_id="MARSCOPE-OBS",
                policy_version=RESOLUTION_OBSERVABILITY_VERSION,
                classification=rule.classification,
                negative_evidence_permitted=neg_ok,
                negative_evidence_statement=neg_stmt,
                rationale=f"{rule.rationale_prefix} Active source '{src_id}' has {px_scale:.2f} m/px spacing (Nyquist >= {min_resolvable_m:.2f} m).",
            )
        )

    eff_floor = float(optical_resolution_m or dem_resolution_m or 1.0) * 3.0
    neg_summary = NegativeEvidenceStatement(
        zero_detections_implies_obstacle_free=False,
        unresolved_hazard_classes=unresolved_classes,
        minimum_resolvable_feature_m=round(eff_floor, 3),
        statement=(
            f"Negative Evidence Prohibition: Zero detected boulders, scarps, or anomalies at "
            f"source spacing ({(optical_resolution_m or dem_resolution_m or 0.0):.2f} m/px; Nyquist threshold ~{eff_floor:.2f} m) "
            "NEVER indicates obstacle-free surface. Sub-meter rocks (0.15-0.5 m), unconsolidated dust pockets, "
            "and sharp undercut fractures require local rover/astronaut visual verification."
        ),
    )
    return records, neg_summary
