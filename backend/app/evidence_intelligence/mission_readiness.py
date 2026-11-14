"""
MARSCOPE Mission Readiness, Physical Energy Budget & Trade-off Synthesis
Martian Surface Intelligence & Exploration System

Computes mechanical gravitational potential energy budgets strictly gated on
explicit user-supplied mass inputs (never silent defaults), evaluates transparent
readiness states (ASSESSED / PARTIALLY_ASSESSED / INSUFFICIENT_EVIDENCE), and
summarizes objective route trade-offs without composite risk percentages or
safety certifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.evidence_intelligence.schemas import (
    CorridorAssessment,
    MissionDossierRequest,
    PhysicalEnergyBudget,
    ReadinessState,
    RouteEvidenceComparisonEntry,
)
from app.physics.registry.parameters import get_parameter
from app.science.provenance_graph import ScientificDataClassification


def compute_physical_energy_budget(
    *,
    positive_elevation_gain_m: float,
    negative_elevation_loss_m: float,
    astronaut_suit_mass_kg: Optional[float],
    payload_mass_kg: Optional[float],
) -> PhysicalEnergyBudget:
    """
    Compute W = m * g and separate +dPE / -dPE / net dPE strictly when explicit
    astronaut_suit_mass_kg and payload_mass_kg are provided. Never substitutes
    silent default masses or fabricates metabolic/oxygen estimates.
    """
    g_param = get_parameter("mars_standard_gravity")
    g_val = float(g_param.value) if g_param is not None else 3.72076
    g_src = str(g_param.source) if g_param is not None else "NASA GSFC Mars Fact Sheet"
    g_ver = str(g_param.version) if g_param is not None else "1.0.0"

    if astronaut_suit_mass_kg is None or payload_mass_kg is None:
        missing = []
        if astronaut_suit_mass_kg is None:
            missing.append("astronaut_suit_mass_kg")
        if payload_mass_kg is None:
            missing.append("payload_mass_kg")
        return PhysicalEnergyBudget(
            available=False,
            classification=ScientificDataClassification.USER_ASSUMED,
            input_total_mass_kg=None,
            astronaut_suit_mass_kg=astronaut_suit_mass_kg,
            payload_mass_kg=payload_mass_kg,
            surface_weight_n=None,
            mars_gravity_m_s2=g_val,
            gravity_parameter_source=g_src,
            gravity_parameter_version=g_ver,
            positive_elevation_gain_m=round(positive_elevation_gain_m, 2),
            negative_elevation_loss_m=round(negative_elevation_loss_m, 2),
            unavailable_reason=(
                f"Explicit user-configured {', '.join(missing)} required; "
                "no silent default astronaut or suit mass is assumed."
            ),
        )

    total_mass = float(astronaut_suit_mass_kg) + float(payload_mass_kg)
    weight_n = total_mass * g_val
    pe_gain_j = weight_n * float(positive_elevation_gain_m)
    pe_loss_j = -weight_n * float(negative_elevation_loss_m)
    net_pe_j = pe_gain_j + pe_loss_j

    return PhysicalEnergyBudget(
        available=True,
        classification=ScientificDataClassification.USER_ASSUMED,
        input_total_mass_kg=round(total_mass, 2),
        astronaut_suit_mass_kg=round(float(astronaut_suit_mass_kg), 2),
        payload_mass_kg=round(float(payload_mass_kg), 2),
        surface_weight_n=round(weight_n, 2),
        mars_gravity_m_s2=g_val,
        gravity_parameter_source=g_src,
        gravity_parameter_version=g_ver,
        positive_elevation_gain_m=round(positive_elevation_gain_m, 2),
        negative_elevation_loss_m=round(negative_elevation_loss_m, 2),
        gravitational_pe_increase_j=round(pe_gain_j, 1),
        gravitational_pe_decrease_j=round(pe_loss_j, 1),
        net_gravitational_pe_change_j=round(net_pe_j, 1),
    )


def evaluate_readiness_state(
    *,
    request: MissionDossierRequest,
    corridor: CorridorAssessment,
    native_resolution_m: float,
) -> Tuple[ReadinessState, List[str], List[str], Dict[str, Any], List[str]]:
    """
    Determine transparent ReadinessState from DEM resolution, coverage, optical
    availability, and explicit user mission assumptions.
    """
    missing_inputs: List[str] = []
    if request.walking_speed_mps is None:
        missing_inputs.append("walking_speed_mps")
    if request.mission_duration_limit_s is None:
        missing_inputs.append("mission_duration_limit_s")
    if request.return_reserve_fraction is None:
        missing_inputs.append("return_reserve_fraction")
    if request.astronaut_suit_mass_kg is None:
        missing_inputs.append("astronaut_suit_mass_kg")
    if request.payload_mass_kg is None:
        missing_inputs.append("payload_mass_kg")

    reasons: List[str] = []
    valid_frac = corridor.uncertainty.corridor_valid_fraction
    opt_cov = float(corridor.coverage_summary.get("mean_optical_coverage_fraction", 0.0))

    if valid_frac < 0.5 or native_resolution_m > 10.0:
        state = ReadinessState.INSUFFICIENT_EVIDENCE
        if valid_frac < 0.5:
            reasons.append(
                f"Corridor valid DEM coverage ({valid_frac * 100:.1f}%) is below 50% minimum threshold."
            )
        if native_resolution_m > 10.0:
            reasons.append(
                f"DEM native resolution ({native_resolution_m:.1f} m/px) is regional scale only and insufficient for Marswalk assessment."
            )
    elif missing_inputs or valid_frac < 0.95 or opt_cov <= 0.0 or native_resolution_m > 2.0:
        state = ReadinessState.PARTIALLY_ASSESSED
        if missing_inputs:
            reasons.append(
                f"User mission assumptions not configured: {', '.join(missing_inputs)}."
            )
        if valid_frac < 0.95:
            reasons.append(
                f"Corridor DEM contains {(1.0 - valid_frac) * 100:.1f}% nodata/unmapped cells."
            )
        if opt_cov <= 0.0:
            reasons.append("No locally acquired HiRISE orthophoto verified across this corridor.")
        if native_resolution_m > 2.0:
            reasons.append(
                f"DEM spacing ({native_resolution_m:.1f} m/px) is resolution-limited for local terrain morphology."
            )
    else:
        state = ReadinessState.ASSESSED
        reasons.append(
            "High-resolution DEM, optical context, and explicit mission assumptions are all present and assessed."
        )

    # Kinematics only computed if explicit walking_speed_mps is provided
    travel_time_s: Optional[float] = None
    within_duration_limit: Optional[bool] = None
    if request.walking_speed_mps is not None and request.walking_speed_mps > 0:
        travel_time_s = round(corridor.route_surface_distance_m / request.walking_speed_mps, 1)
        if (
            request.mission_duration_limit_s is not None
            and request.return_reserve_fraction is not None
        ):
            usable_s = request.mission_duration_limit_s * (1.0 - request.return_reserve_fraction)
            within_duration_limit = travel_time_s <= usable_s

    mobility_assessment = {
        "classification": ScientificDataClassification.USER_ASSUMED.value
        if request.walking_speed_mps is not None
        else ScientificDataClassification.UNAVAILABLE.value,
        "walking_speed_mps": request.walking_speed_mps,
        "estimated_one_way_travel_time_s": travel_time_s,
        "mission_duration_limit_s": request.mission_duration_limit_s,
        "return_reserve_fraction": request.return_reserve_fraction,
        "within_usable_duration_limit": within_duration_limit,
        "note": (
            "Constant-speed kinematic duration only (surface_distance / walking_speed_mps); "
            "does not model slope-dependent metabolic rate or suit mobility penalty."
            if travel_time_s is not None
            else "Travel duration unavailable until explicit walking_speed_mps is configured."
        ),
    }

    unmodeled = [
        "Metabolic expenditure, O2/CO2 scrubbing, and suit thermal load",
        "Regolith bearing strength, wheel/boot sinkage, and loose-sand slip",
        "Sub-meter cobbles, fractures, and dust depth below DEM grid resolution",
        "Local dust storm or solar illumination angle at planned EVA epoch",
    ]
    return state, reasons, missing_inputs, mobility_assessment, unmodeled


def build_tradeoff_explanations(entries: List[RouteEvidenceComparisonEntry]) -> List[str]:
    """Generate objective, metric-driven route comparison explanations."""
    feasible = [e for e in entries if e.feasible]
    if not feasible:
        return ["No feasible routes could be computed under the active terrain and constraint policy."]
    if len(feasible) == 1:
        only = feasible[0]
        return [
            f"Only {only.mode_label} produced a feasible route ({only.surface_distance_m} m surface, "
            f"max slope {only.max_slope_deg}°)."
        ]

    explanations: List[str] = []
    shortest = min(feasible, key=lambda e: e.surface_distance_m or float("inf"))
    gentlest = min(feasible, key=lambda e: e.max_slope_deg if e.max_slope_deg is not None else float("inf"))
    most_obs = max(feasible, key=lambda e: e.associated_observation_count)

    explanations.append(
        f"Shortest surface path: {shortest.mode_label} ({shortest.surface_distance_m:.1f} m, "
        f"+{shortest.elevation_gain_m or 0.0:.1f} m climb)."
    )
    if gentlest.max_slope_deg is not None:
        explanations.append(
            f"Lowest peak slope: {gentlest.mode_label} (max slope {gentlest.max_slope_deg:.1f}°, "
            f"max 5m-TRI {gentlest.max_tri_m or 0.0:.2f} m)."
        )
    if most_obs.associated_observation_count > 0:
        explanations.append(
            f"Highest rover observation density: {most_obs.mode_label} "
            f"({most_obs.associated_observation_count} nearby verified Curiosity records)."
        )
    return explanations
