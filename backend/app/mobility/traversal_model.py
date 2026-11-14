"""
MARSCOPE Transparent, Versioned Human Traversal Model
Martian Surface Intelligence & Exploration System

Model ID: mars_transparent_kinematic_traversal_model (v1.0.0)

Strictly separates:
  1. Source-derived physical terrain & gravitational measurements:
     - Horizontal distance (m), elevation (m), elevation delta (m),
       Horn 3x3 slope (deg), compass aspect (deg), metric TRI roughness (m),
       and (when mass is configured) Mars gravitational potential energy delta (J)
       and uphill slope-parallel gravity force (N).
  2. Scenario-dependent traversal estimates:
     - Baseline traversal time t_base = d / v_0 under an explicitly configured
       positive reference walking speed v_0 (m/s).
     - Optional user-configured slope and roughness speed adjustment factors
       evaluated strictly within their declared valid input domains (never extrapolated).
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.mobility.models import CellTraversalAvailabilityState, TerrainCoverageState
from app.mobility.schemas import (
    ElevationProfileSample,
    MobilityScenario,
    RoughnessSpeedAdjustmentRule,
    SlopeSpeedAdjustmentRule,
    TraversalSegmentEvaluation,
)
from app.physics.models.surface import (
    calculate_gravitational_potential_energy,
    calculate_uphill_parallel_force,
)

TRAVERSAL_MODEL_ID = "mars_transparent_kinematic_traversal_model"
TRAVERSAL_MODEL_VERSION = "1.0.0"


def evaluate_slope_speed_factor(
    slope_deg: Optional[float],
    rule: Optional[SlopeSpeedAdjustmentRule],
) -> Tuple[Optional[float], Optional[str]]:
    """
    Evaluate optional user-configured slope speed factor.
    Returns (factor, error_reason). Never extrapolates outside [min_valid_slope_deg, max_valid_slope_deg].
    """
    if rule is None:
        return 1.0, None
    if slope_deg is None or not math.isfinite(slope_deg):
        return None, "Slope derivative is unavailable at this location; slope_speed_adjustment cannot be evaluated."
    if slope_deg < rule.min_valid_slope_deg or slope_deg > rule.max_valid_slope_deg:
        return (
            None,
            f"Slope ({slope_deg:.3f} deg) is outside the valid domain [{rule.min_valid_slope_deg}, "
            f"{rule.max_valid_slope_deg}] deg of slope adjustment rule '{rule.rule_id}'; extrapolation is prohibited.",
        )

    excess_deg = max(0.0, slope_deg - rule.reference_slope_deg)
    if rule.rule_type == "exponential_decay_factor":
        raw_factor = math.exp(-rule.coefficient_per_deg * excess_deg)
    else:
        raw_factor = 1.0 - (rule.coefficient_per_deg * excess_deg)

    clamped = max(rule.min_speed_factor, min(rule.max_speed_factor, raw_factor))
    return float(clamped), None


def evaluate_roughness_speed_factor(
    roughness_m: Optional[float],
    rule: Optional[RoughnessSpeedAdjustmentRule],
) -> Tuple[Optional[float], Optional[str]]:
    """
    Evaluate optional user-configured TRI roughness speed factor.
    Returns (factor, error_reason). Never extrapolates outside [min_valid_roughness_m, max_valid_roughness_m].
    """
    if rule is None:
        return 1.0, None
    if roughness_m is None or not math.isfinite(roughness_m):
        return None, "TRI roughness derivative is unavailable at this location; roughness_speed_adjustment cannot be evaluated."
    if roughness_m < rule.min_valid_roughness_m or roughness_m > rule.max_valid_roughness_m:
        return (
            None,
            f"Roughness TRI ({roughness_m:.3f} m) is outside the valid domain [{rule.min_valid_roughness_m}, "
            f"{rule.max_valid_roughness_m}] m of roughness adjustment rule '{rule.rule_id}'; extrapolation is prohibited.",
        )

    excess_m = max(0.0, roughness_m - rule.reference_roughness_m)
    raw_factor = 1.0 - (rule.coefficient_per_meter * excess_m)
    clamped = max(rule.min_speed_factor, min(rule.max_speed_factor, raw_factor))
    return float(clamped), None


def evaluate_cell_or_segment_traversal(
    *,
    segment_index: int,
    lat: float,
    lon_east: float,
    horizontal_distance_meters: float,
    coverage_state: TerrainCoverageState,
    elevation_meters: Optional[float],
    elevation_delta_meters: Optional[float],
    slope_deg: Optional[float],
    aspect_deg: Optional[float],
    roughness_tri_meters: Optional[float],
    scenario: MobilityScenario,
) -> TraversalSegmentEvaluation:
    """
    Evaluate both physical measurements and scenario-dependent traversal estimates
    for a single terrain cell or profile segment.
    """
    # Physical gravitational metrics when total_mass_kg is explicitly configured
    pe_delta_j: Optional[float] = None
    uphill_force_n: Optional[float] = None
    if scenario.total_mass_kg is not None and scenario.total_mass_kg > 0.0:
        if elevation_delta_meters is not None and math.isfinite(elevation_delta_meters):
            pe_delta_j = round(
                float(
                    calculate_gravitational_potential_energy(
                        scenario.total_mass_kg,
                        elevation_delta_meters,
                    ).calculated_value
                ),
                4,
            )
        if slope_deg is not None and math.isfinite(slope_deg) and 0.0 <= slope_deg <= 90.0:
            uphill_force_n = round(
                float(
                    calculate_uphill_parallel_force(
                        scenario.total_mass_kg,
                        slope_deg,
                    ).calculated_value
                ),
                4,
            )

    # 1. Check unknown terrain first (never assign zero cost to unknown/no-data terrain!)
    if coverage_state in (
        TerrainCoverageState.OUTSIDE_SOURCE_FOOTPRINT,
        TerrainCoverageState.INSIDE_FOOTPRINT_NODATA,
        TerrainCoverageState.INSUFFICIENT_RESOLUTION_FOR_ANALYSIS,
    ) or elevation_meters is None:
        return TraversalSegmentEvaluation(
            segment_index=segment_index,
            lat=lat,
            lon_east=lon_east,
            horizontal_distance_meters=round(horizontal_distance_meters, 3),
            coverage_state=coverage_state,
            elevation_meters=elevation_meters,
            elevation_delta_meters=elevation_delta_meters,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri_meters=roughness_tri_meters,
            gravitational_potential_energy_delta_joules=pe_delta_j,
            uphill_parallel_gravity_force_newtons=uphill_force_n,
            traversal_availability_state=CellTraversalAvailabilityState.UNKNOWN_TERRAIN,
            unavailable_or_exclusion_reason=(
                f"Terrain data is unavailable ({coverage_state.value}); unknown terrain is never assigned a traversal cost."
            ),
        )

    # 2. Check explicit user-configured scenario planning exclusions (slope / roughness thresholds)
    if scenario.planning_max_slope_deg is not None:
        if slope_deg is None:
            return TraversalSegmentEvaluation(
                segment_index=segment_index,
                lat=lat,
                lon_east=lon_east,
                horizontal_distance_meters=round(horizontal_distance_meters, 3),
                coverage_state=coverage_state,
                elevation_meters=elevation_meters,
                elevation_delta_meters=elevation_delta_meters,
                slope_deg=slope_deg,
                aspect_deg=aspect_deg,
                roughness_tri_meters=roughness_tri_meters,
                gravitational_potential_energy_delta_joules=pe_delta_j,
                uphill_parallel_gravity_force_newtons=uphill_force_n,
                traversal_availability_state=CellTraversalAvailabilityState.UNKNOWN_TERRAIN,
                unavailable_or_exclusion_reason=(
                    "Scenario defines planning_max_slope_deg, but local 3x3 slope derivative is unavailable at this cell."
                ),
            )
        if slope_deg > scenario.planning_max_slope_deg:
            return TraversalSegmentEvaluation(
                segment_index=segment_index,
                lat=lat,
                lon_east=lon_east,
                horizontal_distance_meters=round(horizontal_distance_meters, 3),
                coverage_state=coverage_state,
                elevation_meters=elevation_meters,
                elevation_delta_meters=elevation_delta_meters,
                slope_deg=slope_deg,
                aspect_deg=aspect_deg,
                roughness_tri_meters=roughness_tri_meters,
                gravitational_potential_energy_delta_joules=pe_delta_j,
                uphill_parallel_gravity_force_newtons=uphill_force_n,
                traversal_availability_state=CellTraversalAvailabilityState.EXPLICIT_SCENARIO_EXCLUSION,
                unavailable_or_exclusion_reason=(
                    f"Cell slope ({slope_deg:.2f} deg) exceeds user-configured scenario planning_max_slope_deg "
                    f"({scenario.planning_max_slope_deg:.2f} deg)."
                ),
            )

    if scenario.planning_max_roughness_m is not None:
        if roughness_tri_meters is None:
            return TraversalSegmentEvaluation(
                segment_index=segment_index,
                lat=lat,
                lon_east=lon_east,
                horizontal_distance_meters=round(horizontal_distance_meters, 3),
                coverage_state=coverage_state,
                elevation_meters=elevation_meters,
                elevation_delta_meters=elevation_delta_meters,
                slope_deg=slope_deg,
                aspect_deg=aspect_deg,
                roughness_tri_meters=roughness_tri_meters,
                gravitational_potential_energy_delta_joules=pe_delta_j,
                uphill_parallel_gravity_force_newtons=uphill_force_n,
                traversal_availability_state=CellTraversalAvailabilityState.UNKNOWN_TERRAIN,
                unavailable_or_exclusion_reason=(
                    "Scenario defines planning_max_roughness_m, but local 3x3 TRI roughness is unavailable at this cell."
                ),
            )
        if roughness_tri_meters > scenario.planning_max_roughness_m:
            return TraversalSegmentEvaluation(
                segment_index=segment_index,
                lat=lat,
                lon_east=lon_east,
                horizontal_distance_meters=round(horizontal_distance_meters, 3),
                coverage_state=coverage_state,
                elevation_meters=elevation_meters,
                elevation_delta_meters=elevation_delta_meters,
                slope_deg=slope_deg,
                aspect_deg=aspect_deg,
                roughness_tri_meters=roughness_tri_meters,
                gravitational_potential_energy_delta_joules=pe_delta_j,
                uphill_parallel_gravity_force_newtons=uphill_force_n,
                traversal_availability_state=CellTraversalAvailabilityState.EXPLICIT_SCENARIO_EXCLUSION,
                unavailable_or_exclusion_reason=(
                    f"Cell TRI roughness ({roughness_tri_meters:.2f} m) exceeds user-configured scenario "
                    f"planning_max_roughness_m ({scenario.planning_max_roughness_m:.2f} m)."
                ),
            )

    # 3. Check whether an explicit reference walking speed is configured
    v0 = scenario.reference_walking_speed_m_per_s
    if v0 is None or v0 <= 0.0:
        return TraversalSegmentEvaluation(
            segment_index=segment_index,
            lat=lat,
            lon_east=lon_east,
            horizontal_distance_meters=round(horizontal_distance_meters, 3),
            coverage_state=coverage_state,
            elevation_meters=elevation_meters,
            elevation_delta_meters=elevation_delta_meters,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri_meters=roughness_tri_meters,
            gravitational_potential_energy_delta_joules=pe_delta_j,
            uphill_parallel_gravity_force_newtons=uphill_force_n,
            traversal_availability_state=CellTraversalAvailabilityState.INSUFFICIENT_SCENARIO_PARAMETERS,
            unavailable_or_exclusion_reason=(
                "No reference_walking_speed_m_per_s configured in MobilityScenario; traversal time cannot be "
                "estimated without an explicit walking speed assumption."
            ),
        )

    # 4. Evaluate optional slope and roughness adjustment rules within their valid domains
    f_slope, slope_err = evaluate_slope_speed_factor(slope_deg, scenario.slope_speed_adjustment)
    if slope_err is not None or f_slope is None:
        state = (
            CellTraversalAvailabilityState.UNKNOWN_TERRAIN
            if slope_deg is None
            else CellTraversalAvailabilityState.OUTSIDE_MODEL_VALID_DOMAIN
        )
        return TraversalSegmentEvaluation(
            segment_index=segment_index,
            lat=lat,
            lon_east=lon_east,
            horizontal_distance_meters=round(horizontal_distance_meters, 3),
            coverage_state=coverage_state,
            elevation_meters=elevation_meters,
            elevation_delta_meters=elevation_delta_meters,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri_meters=roughness_tri_meters,
            gravitational_potential_energy_delta_joules=pe_delta_j,
            uphill_parallel_gravity_force_newtons=uphill_force_n,
            traversal_availability_state=state,
            reference_speed_m_per_s=round(v0, 4),
            unavailable_or_exclusion_reason=slope_err,
        )

    f_rough, rough_err = evaluate_roughness_speed_factor(roughness_tri_meters, scenario.roughness_speed_adjustment)
    if rough_err is not None or f_rough is None:
        state = (
            CellTraversalAvailabilityState.UNKNOWN_TERRAIN
            if roughness_tri_meters is None
            else CellTraversalAvailabilityState.OUTSIDE_MODEL_VALID_DOMAIN
        )
        return TraversalSegmentEvaluation(
            segment_index=segment_index,
            lat=lat,
            lon_east=lon_east,
            horizontal_distance_meters=round(horizontal_distance_meters, 3),
            coverage_state=coverage_state,
            elevation_meters=elevation_meters,
            elevation_delta_meters=elevation_delta_meters,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri_meters=roughness_tri_meters,
            gravitational_potential_energy_delta_joules=pe_delta_j,
            uphill_parallel_gravity_force_newtons=uphill_force_n,
            traversal_availability_state=state,
            reference_speed_m_per_s=round(v0, 4),
            slope_speed_factor=round(f_slope, 4),
            unavailable_or_exclusion_reason=rough_err,
        )

    v_eff = v0 * f_slope * f_rough
    if v_eff <= 0.0:
        return TraversalSegmentEvaluation(
            segment_index=segment_index,
            lat=lat,
            lon_east=lon_east,
            horizontal_distance_meters=round(horizontal_distance_meters, 3),
            coverage_state=coverage_state,
            elevation_meters=elevation_meters,
            elevation_delta_meters=elevation_delta_meters,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri_meters=roughness_tri_meters,
            gravitational_potential_energy_delta_joules=pe_delta_j,
            uphill_parallel_gravity_force_newtons=uphill_force_n,
            traversal_availability_state=CellTraversalAvailabilityState.OUTSIDE_MODEL_VALID_DOMAIN,
            reference_speed_m_per_s=round(v0, 4),
            unavailable_or_exclusion_reason="Effective walking speed evaluated to <= 0 m/s.",
        )

    t_base = horizontal_distance_meters / v0 if horizontal_distance_meters >= 0.0 else None
    t_adj = horizontal_distance_meters / v_eff if horizontal_distance_meters >= 0.0 else None

    return TraversalSegmentEvaluation(
        segment_index=segment_index,
        lat=lat,
        lon_east=lon_east,
        horizontal_distance_meters=round(horizontal_distance_meters, 3),
        coverage_state=coverage_state,
        elevation_meters=elevation_meters,
        elevation_delta_meters=elevation_delta_meters,
        slope_deg=slope_deg,
        aspect_deg=aspect_deg,
        roughness_tri_meters=roughness_tri_meters,
        gravitational_potential_energy_delta_joules=pe_delta_j,
        uphill_parallel_gravity_force_newtons=uphill_force_n,
        traversal_availability_state=CellTraversalAvailabilityState.EVALUATED,
        reference_speed_m_per_s=round(v0, 4),
        slope_speed_factor=round(f_slope, 4),
        roughness_speed_factor=round(f_rough, 4),
        effective_speed_m_per_s=round(v_eff, 4),
        baseline_time_seconds=round(t_base, 3) if t_base is not None else None,
        adjusted_time_seconds=round(t_adj, 3) if t_adj is not None else None,
        unavailable_or_exclusion_reason=None,
    )


def evaluate_transect_traversal(
    *,
    profile_samples: Sequence[ElevationProfileSample],
    scenario: MobilityScenario,
) -> Tuple[List[TraversalSegmentEvaluation], Dict[str, Any]]:
    """
    Evaluate traversal along a sequence of profile samples and aggregate
    scenario-dependent traversal estimates honestly.
    """
    segments: List[TraversalSegmentEvaluation] = []
    total_base_time_s = 0.0
    total_adj_time_s = 0.0
    evaluated_dist_m = 0.0
    Unevaluated_dist_m = 0.0
    eff_speeds: List[float] = []
    state_counts: Dict[str, int] = {s.value: 0 for s in CellTraversalAvailabilityState}

    for idx, samp in enumerate(profile_samples):
        eff_slope = samp.slope_deg if samp.slope_deg is not None else samp.segment_slope_deg
        seg_eval = evaluate_cell_or_segment_traversal(
            segment_index=idx,
            lat=samp.lat,
            lon_east=samp.lon_east,
            horizontal_distance_meters=samp.segment_distance_meters,
            coverage_state=samp.coverage_state,
            elevation_meters=samp.elevation_meters,
            elevation_delta_meters=samp.segment_elevation_delta_meters,
            slope_deg=eff_slope,
            aspect_deg=samp.aspect_deg,
            roughness_tri_meters=samp.roughness_tri_meters,
            scenario=scenario,
        )
        segments.append(seg_eval)
        state_counts[seg_eval.traversal_availability_state.value] += 1

        if (
            seg_eval.traversal_availability_state == CellTraversalAvailabilityState.EVALUATED
            and seg_eval.baseline_time_seconds is not None
            and seg_eval.adjusted_time_seconds is not None
        ):
            total_base_time_s += seg_eval.baseline_time_seconds
            total_adj_time_s += seg_eval.adjusted_time_seconds
            evaluated_dist_m += samp.segment_distance_meters
            if seg_eval.effective_speed_m_per_s is not None:
                eff_speeds.append(seg_eval.effective_speed_m_per_s)
        else:
            Unevaluated_dist_m += samp.segment_distance_meters

    all_evaluated = all(
        s.traversal_availability_state == CellTraversalAvailabilityState.EVALUATED
        for s in segments
    )
    any_evaluated = len(eff_speeds) > 0

    summary: Dict[str, Any] = {
        "traversal_model_id": TRAVERSAL_MODEL_ID,
        "traversal_model_version": TRAVERSAL_MODEL_VERSION,
        "scenario_id": scenario.scenario_id,
        "scenario_version": scenario.version,
        "traversal_time_available": any_evaluated,
        "complete_transect_evaluated": all_evaluated,
        "evaluated_horizontal_distance_meters": round(evaluated_dist_m, 3),
        "unevaluated_horizontal_distance_meters": round(Unevaluated_dist_m, 3),
        "baseline_traversal_time_seconds": round(total_base_time_s, 3) if any_evaluated else None,
        "baseline_traversal_time_minutes": round(total_base_time_s / 60.0, 3) if any_evaluated else None,
        "adjusted_traversal_time_seconds": round(total_adj_time_s, 3) if any_evaluated else None,
        "adjusted_traversal_time_minutes": round(total_adj_time_s / 60.0, 3) if any_evaluated else None,
        "mean_effective_speed_m_per_s": round(sum(eff_speeds) / len(eff_speeds), 4) if eff_speeds else None,
        "min_effective_speed_m_per_s": round(min(eff_speeds), 4) if eff_speeds else None,
        "max_effective_speed_m_per_s": round(max(eff_speeds), 4) if eff_speeds else None,
        "segment_availability_counts": state_counts,
        "unconfigured_capabilities": scenario.unconfigured_capabilities,
        "safety_assessment": "not_performed_no_validated_safety_limits",
    }
    if not all_evaluated and any_evaluated:
        summary["partial_evaluation_warning"] = (
            "One or more transect segments could not be evaluated (unknown terrain, missing derivative, "
            "or scenario exclusion); reported traversal time covers only evaluated_horizontal_distance_meters."
        )
    elif not any_evaluated:
        reasons = sorted({s.unavailable_or_exclusion_reason for s in segments if s.unavailable_or_exclusion_reason})
        summary["unavailable_reason"] = "; ".join(reasons) if reasons else "Traversal time unavailable."

    return segments, summary
