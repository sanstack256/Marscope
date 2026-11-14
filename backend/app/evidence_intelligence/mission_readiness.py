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
    DomainAssessmentRecord,
    MissionDossierRequest,
    PhysicalEnergyBudget,
    ReadinessState,
    RouteEvidenceComparisonEntry,
)
from app.physics.registry.parameters import get_parameter
from app.science.provenance_graph import ScientificDataClassification


READINESS_POLICY: Dict[str, Any] = {
    "policy_version": "readiness-v2.0",
    "min_dem_valid_fraction_usable": 0.50,
    "min_dem_valid_fraction_assessed": 0.95,
    "max_assessable_dem_resolution_m": 10.0,
    "max_local_dem_resolution_m": 2.0,
    "min_optical_valid_fraction_assessed": 0.50,
    "rationale": (
        "Versioned policy gating corridor elevation completeness, local obstacle scale "
        "(HiRISE <= 2.0 m/px vs regional > 10 m/px), and explicit user planning parameters."
    ),
}


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

    min_usable_dem = READINESS_POLICY["min_dem_valid_fraction_usable"]
    min_assessed_dem = READINESS_POLICY["min_dem_valid_fraction_assessed"]
    max_assess_res = READINESS_POLICY["max_assessable_dem_resolution_m"]
    max_local_res = READINESS_POLICY["max_local_dem_resolution_m"]
    min_opt = READINESS_POLICY["min_optical_valid_fraction_assessed"]

    if valid_frac < min_usable_dem or native_resolution_m > max_assess_res:
        state = ReadinessState.INSUFFICIENT_EVIDENCE
        if valid_frac < min_usable_dem:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] Corridor valid DEM coverage ({valid_frac * 100:.1f}%) is below {min_usable_dem * 100:.0f}% minimum threshold."
            )
        if native_resolution_m > max_assess_res:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] DEM native resolution ({native_resolution_m:.1f} m/px) exceeds {max_assess_res:.1f} m/px limit and is regional scale only."
            )
    elif missing_inputs or valid_frac < min_assessed_dem or opt_cov < min_opt or native_resolution_m > max_local_res:
        state = ReadinessState.PARTIALLY_ASSESSED
        if missing_inputs:
            reasons.append(
                f"User mission assumptions not configured: {', '.join(missing_inputs)}."
            )
        if valid_frac < min_assessed_dem:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] Corridor DEM valid fraction ({valid_frac * 100:.1f}%) is below {min_assessed_dem * 100:.0f}% completeness policy."
            )
        if opt_cov < min_opt:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] Area-weighted valid optical coverage ({opt_cov * 100:.1f}%) is below {min_opt * 100:.0f}% policy threshold."
            )
        if native_resolution_m > max_local_res:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] DEM spacing ({native_resolution_m:.1f} m/px) exceeds {max_local_res:.1f} m/px local resolution threshold."
            )
    else:
        state = ReadinessState.ASSESSED
        reasons.append(
            f"[{READINESS_POLICY['policy_version']}] Mathematical corridor terrain, optical context, and user planning inputs meet assessment policy; NOT operational safety certification."
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


def evaluate_multidomain_readiness(
    *,
    request: MissionDossierRequest,
    corridor: CorridorAssessment,
    native_resolution_m: float,
    energy_budget: PhysicalEnergyBudget,
    consumables_configured: bool = False,
    live_telemetry_connected: bool = False,
) -> Tuple[List[DomainAssessmentRecord], bool]:
    """
    Evaluate all 15 explicit operational and scientific readiness domains using
    READINESS_POLICY (`readiness-v2.0`), clearly separating mathematical assessment
    completeness from operational human survival safety certification.
    """
    pv = READINESS_POLICY["policy_version"]
    valid_dem = float(corridor.uncertainty.corridor_valid_fraction)
    opt_cov = float(corridor.coverage_summary.get("mean_optical_coverage_fraction", 0.0))
    segs = corridor.segments
    has_slope = all(s.coverage.slope_available for s in segs) if segs else False
    has_tri = all(s.coverage.tri_available for s in segs) if segs else False
    has_geo = any(s.coverage.geological_map_coverage for s in segs)
    has_spec = any(s.coverage.spectral_data_available for s in segs)
    has_therm = any(s.coverage.thermal_data_available for s in segs)
    obs_count = len(corridor.observations)

    dem_status = (
        "ASSESSED"
        if valid_dem >= READINESS_POLICY["min_dem_valid_fraction_assessed"]
        and native_resolution_m <= READINESS_POLICY["max_local_dem_resolution_m"]
        else (
            "INSUFFICIENT_EVIDENCE"
            if valid_dem < READINESS_POLICY["min_dem_valid_fraction_usable"]
            or native_resolution_m > READINESS_POLICY["max_assessable_dem_resolution_m"]
            else "PARTIALLY_ASSESSED"
        )
    )

    domains: List[DomainAssessmentRecord] = [
        DomainAssessmentRecord(
            domain="topographic_dem",
            status=dem_status,
            evidence_basis=f"{corridor.source_product_id} ({native_resolution_m:.2f} m/px, {valid_dem * 100:.1f}% corridor valid)",
            policy_version=pv,
            threshold_or_rule=f"valid >= {READINESS_POLICY['min_dem_valid_fraction_assessed'] * 100:.0f}% & res <= {READINESS_POLICY['max_local_dem_resolution_m']:.1f} m/px",
            notes=["Corridor polygon masked via rasterio.geometry_mask."],
        ),
        DomainAssessmentRecord(
            domain="slope_and_relief",
            status="ASSESSED" if (has_slope and dem_status == "ASSESSED") else ("PARTIALLY_ASSESSED" if has_slope else "UNAVAILABLE"),
            evidence_basis="Horn 3x3 windowed DEM slope across convolution-buffered corridor",
            policy_version=pv,
            threshold_or_rule="All corridor segments have finite slope & local relief",
        ),
        DomainAssessmentRecord(
            domain="surface_roughness",
            status="ASSESSED" if (has_tri and dem_status == "ASSESSED") else ("PARTIALLY_ASSESSED" if has_tri else "UNAVAILABLE"),
            evidence_basis="5.0 m physical-radius RMS TRI",
            policy_version=pv,
            threshold_or_rule="Features below 2x DEM pixel scale remain unresolved",
        ),
        DomainAssessmentRecord(
            domain="optical_imagery",
            status="ASSESSED" if opt_cov >= READINESS_POLICY["min_optical_valid_fraction_assessed"] else ("PARTIALLY_ASSESSED" if opt_cov > 0 else "UNAVAILABLE"),
            evidence_basis=f"Area-weighted valid HiRISE optical coverage {opt_cov * 100:.1f}%",
            policy_version=pv,
            threshold_or_rule=f"valid_optical >= {READINESS_POLICY['min_optical_valid_fraction_assessed'] * 100:.0f}%",
        ),
        DomainAssessmentRecord(
            domain="optical_candidate_features",
            status="PARTIALLY_ASSESSED" if corridor.optical_candidates else "UNAVAILABLE",
            evidence_basis=f"{len(corridor.optical_candidates)} in-corridor contrast/edge candidates (interpretation required)",
            policy_version=pv,
            threshold_or_rule="2D optical candidates are never promoted to confirmed boulder counts or 3D heights",
        ),
        DomainAssessmentRecord(
            domain="geological_context",
            status="PARTIALLY_ASSESSED" if has_geo else "UNAVAILABLE",
            evidence_basis="USGS SIM 3292 global geological context (1:20,000,000 scale)" if has_geo else "No geological raster/map verified",
            policy_version=pv,
            threshold_or_rule="Regional 1:20M geology is insufficient for outcrop-scale trafficability",
        ),
        DomainAssessmentRecord(
            domain="mineralogical_spectral_context",
            status="PARTIALLY_ASSESSED" if has_spec else "UNAVAILABLE",
            evidence_basis="Nearby Curiosity ChemCam/APXS PDS records" if has_spec else "No verified corridor spectral coverage",
            policy_version=pv,
            threshold_or_rule="Point measurements do not establish whole-corridor mineral continuity",
        ),
        DomainAssessmentRecord(
            domain="thermal_inertia_and_temperature",
            status="PARTIALLY_ASSESSED" if has_therm else "UNAVAILABLE",
            evidence_basis="Historical REMS thermal archive near Gale" if has_therm else "No verified thermal inertia raster or live temperature",
            policy_version=pv,
            threshold_or_rule="Historical PDS records only; live thermal environment unavailable",
        ),
        DomainAssessmentRecord(
            domain="rover_and_surface_observations",
            status="ASSESSED" if obs_count > 0 else "UNAVAILABLE",
            evidence_basis=f"{obs_count} Gale / Curiosity observations spatially indexed by Shapely STRtree",
            policy_version=pv,
            threshold_or_rule="Perseverance/Jezero records isolated; local product existence checked explicitly",
        ),
        DomainAssessmentRecord(
            domain="navigation_and_return_feasibility",
            status="ASSESSED" if corridor.route_surface_distance_m > 0 else "UNAVAILABLE",
            evidence_basis=f"Route {corridor.route_surface_distance_m:.1f} m with {len(corridor.segments)} segments",
            policy_version=pv,
            threshold_or_rule="Strict return-path verification via EVA Operational Envelope when duration limits provided",
        ),
        DomainAssessmentRecord(
            domain="kinematic_duration_budget",
            status=(
                "ASSESSED"
                if (
                    request.walking_speed_mps is not None
                    and request.mission_duration_limit_s is not None
                    and request.return_reserve_fraction is not None
                )
                else ("PARTIALLY_ASSESSED" if request.walking_speed_mps is not None else "UNAVAILABLE")
            ),
            evidence_basis="Constant user speed vs unvalidated Tobler grade scaling",
            policy_version=pv,
            threshold_or_rule="Explicit user walking_speed_mps, duration limit, and reserve required",
        ),
        DomainAssessmentRecord(
            domain="gravitational_energy_work",
            status="ASSESSED" if energy_budget.available else "UNAVAILABLE",
            evidence_basis="W = m * g_mars; dPE = m * g * dh (Mars Standard Gravity 3.72076 m/s^2)",
            policy_version=pv,
            threshold_or_rule="Requires explicit suit + payload mass; downhill does NOT recover metabolic energy",
        ),
        DomainAssessmentRecord(
            domain="consumables_and_eva_endurance",
            status="ASSESSED" if consumables_configured else "UNAVAILABLE",
            evidence_basis="Unit-aware explicit user EVA supply limits" if consumables_configured else "No user O2/battery/cooling supply limits supplied",
            policy_version=pv,
            threshold_or_rule="Never infers suit consumables from route length without explicit consumption rate",
        ),
        DomainAssessmentRecord(
            domain="live_localization_and_telemetry",
            status="PARTIALLY_ASSESSED" if live_telemetry_connected else "UNAVAILABLE",
            evidence_basis="Live authenticated SSE telemetry only when external feed active" if live_telemetry_connected else "No verified live astronaut position feed connected",
            policy_version=pv,
            threshold_or_rule="Zero fabricated live astronaut coordinates",
        ),
        DomainAssessmentRecord(
            domain="astronaut_survivability_safety_certification",
            status="UNVALIDATED",
            evidence_basis="Regolith bearing strength, dust depth, subsurface voids, and suit thermal endurance are unmodeled",
            policy_version=pv,
            threshold_or_rule="MARSCOPE is an analytical planning support engine, NEVER an EVA life-safety certification",
        ),
    ]

    math_complete = (
        dem_status in ("ASSESSED", "PARTIALLY_ASSESSED")
        and has_slope
        and request.walking_speed_mps is not None
        and energy_budget.available
    )
    return domains, bool(math_complete)

