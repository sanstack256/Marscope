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
    raw_opt_cov = corridor.coverage_summary.get("mean_optical_coverage_fraction")
    opt_cov: Optional[float] = float(raw_opt_cov) if raw_opt_cov is not None else None
    opt_status = str(corridor.coverage_summary.get("optical_coverage_status") or "COVERAGE_UNAVAILABLE")

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
    elif missing_inputs or valid_frac < min_assessed_dem or opt_cov is None or opt_cov < min_opt or native_resolution_m > max_local_res:
        state = ReadinessState.PARTIALLY_ASSESSED
        if missing_inputs:
            reasons.append(
                f"User mission assumptions not configured: {', '.join(missing_inputs)}."
            )
        if valid_frac < min_assessed_dem:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] Corridor DEM valid fraction ({valid_frac * 100:.1f}%) is below {min_assessed_dem * 100:.0f}% completeness policy."
            )
        if opt_cov is None:
            reasons.append(
                f"[{READINESS_POLICY['policy_version']}] Optical imagery coverage is unverified ({opt_status}; never coerced to 0%)."
            )
        elif opt_cov < min_opt:
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
    raw_opt_cov = corridor.coverage_summary.get("mean_optical_coverage_fraction")
    opt_cov: Optional[float] = float(raw_opt_cov) if raw_opt_cov is not None else None
    raw_opt_foot = corridor.coverage_summary.get("mean_optical_footprint_coverage_fraction")
    opt_foot_cov: Optional[float] = float(raw_opt_foot) if raw_opt_foot is not None else None
    opt_status = str(corridor.coverage_summary.get("optical_coverage_status") or "COVERAGE_UNAVAILABLE")

    segs = corridor.segments
    seg_count = len(segs)
    if segs:
        seg_weights = [
            float(s.coverage.segment_corridor_area_m2 or s.corridor_area_m2 or max(1.0, s.geodesic_distance_m))
            for s in segs
        ]
        tot_seg_w = max(1e-6, sum(seg_weights))
        slope_cov_frac = round(sum((1.0 if s.coverage.slope_available else 0.0) * w for s, w in zip(segs, seg_weights)) / tot_seg_w, 4)
        tri_cov_frac = round(sum((1.0 if s.coverage.tri_available else 0.0) * w for s, w in zip(segs, seg_weights)) / tot_seg_w, 4)
        geo_cov_frac = round(sum(float(s.coverage.geological_coverage_fraction or (1.0 if s.coverage.geological_map_coverage else 0.0)) * w for s, w in zip(segs, seg_weights)) / tot_seg_w, 4)
        spec_cov_frac = round(sum(float(s.coverage.spectral_coverage_fraction or 0.0) * w for s, w in zip(segs, seg_weights)) / tot_seg_w, 4)
        therm_cov_frac = round(sum(float(s.coverage.thermal_coverage_fraction or 0.0) * w for s, w in zip(segs, seg_weights)) / tot_seg_w, 4)
        geo_segs = sum(1 for s in segs if s.coverage.geological_map_coverage)
        spec_segs = sum(1 for s in segs if s.coverage.spectral_data_available)
        therm_segs = sum(1 for s in segs if s.coverage.thermal_data_available)
    else:
        slope_cov_frac = 0.0
        tri_cov_frac = 0.0
        geo_cov_frac = 0.0
        spec_cov_frac = 0.0
        therm_cov_frac = 0.0
        geo_segs = 0
        spec_segs = 0
        therm_segs = 0

    has_slope = all(s.coverage.slope_available for s in segs) if segs else False
    has_tri = all(s.coverage.tri_available for s in segs) if segs else False
    obs_count = len(corridor.observations)
    obs_segs = sum(1 for s in segs if s.coverage.rover_observation_count > 0)

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
    dem_res_adequacy = (
        "adequate_for_engineering_slope"
        if native_resolution_m <= READINESS_POLICY["max_local_dem_resolution_m"]
        else ("regional_only" if native_resolution_m <= READINESS_POLICY["max_assessable_dem_resolution_m"] else "insufficient")
    )

    domains: List[DomainAssessmentRecord] = [
        DomainAssessmentRecord(
            domain="topographic_dem",
            status=dem_status,
            evidence_basis=f"{corridor.source_product_id} ({native_resolution_m:.2f} m/px, {valid_dem * 100:.1f}% corridor valid)",
            policy_version=pv,
            threshold_or_rule=f"valid >= {READINESS_POLICY['min_dem_valid_fraction_assessed'] * 100:.0f}% & res <= {READINESS_POLICY['max_local_dem_resolution_m']:.1f} m/px (local slope screening ONLY; sub-meter obstacles < 0.5 m unresolved)",
            spatial_footprint_coverage_fraction=round(valid_dem, 4),
            valid_measurement_coverage_fraction=round(valid_dem, 4),
            product_availability="verified_local" if valid_dem > 0 else "unavailable",
            scientific_validation_state="calibrated_pds_dtm_unquantified_per_pixel_sigma",
            spatial_association_quality="full_corridor_polygon_mask",
            resolution_adequacy=dem_res_adequacy,
            temporal_relevance="static_orbital_dtm",
            missing_inputs=["per_pixel_vertical_rmse_raster", "sub_meter_obstacle_height_map"],
            notes=["Corridor polygon masked via rasterio.geometry_mask; empirical per-pixel DEM height sigma raster absent in PDS3."],
        ),
        DomainAssessmentRecord(
            domain="slope_and_relief",
            status="ASSESSED" if (has_slope and dem_status == "ASSESSED") else ("PARTIALLY_ASSESSED" if slope_cov_frac > 0.0 else "UNAVAILABLE"),
            evidence_basis=f"Horn 3x3 windowed DEM slope across {slope_cov_frac * 100:.1f}% weighted corridor coverage",
            policy_version=pv,
            threshold_or_rule="All corridor segments require finite slope & local relief",
            spatial_footprint_coverage_fraction=slope_cov_frac,
            valid_measurement_coverage_fraction=slope_cov_frac,
            product_availability="verified_local" if slope_cov_frac > 0 else "unavailable",
            scientific_validation_state="derived_from_dem_finite_differences",
            spatial_association_quality="full_corridor_raster",
            resolution_adequacy=dem_res_adequacy,
            temporal_relevance="static_orbital_dtm",
            missing_inputs=[] if has_slope else ["nodata_corridor_segments"],
        ),
        DomainAssessmentRecord(
            domain="surface_roughness",
            status="ASSESSED" if (has_tri and dem_status == "ASSESSED") else ("PARTIALLY_ASSESSED" if tri_cov_frac > 0.0 else "UNAVAILABLE"),
            evidence_basis=f"5.0 m physical-radius RMS TRI across {tri_cov_frac * 100:.1f}% weighted corridor coverage",
            policy_version=pv,
            threshold_or_rule="Features below 2x DEM pixel scale remain unresolved",
            spatial_footprint_coverage_fraction=tri_cov_frac,
            valid_measurement_coverage_fraction=tri_cov_frac,
            product_availability="verified_local" if tri_cov_frac > 0 else "unavailable",
            scientific_validation_state="derived_riley_tri_5m_kernel",
            spatial_association_quality="full_corridor_raster",
            resolution_adequacy="resolution_limited" if native_resolution_m > 0.5 else "adequate",
            temporal_relevance="static_orbital_dtm",
            missing_inputs=["sub_dem_scale_boulder_size_frequency_distribution"],
        ),
        DomainAssessmentRecord(
            domain="optical_imagery",
            status=(
                "ASSESSED"
                if (opt_cov is not None and opt_cov >= READINESS_POLICY["min_optical_valid_fraction_assessed"])
                else ("PARTIALLY_ASSESSED" if (opt_cov is not None and opt_cov > 0.0) else ("INSUFFICIENT_EVIDENCE" if opt_cov == 0.0 else "UNAVAILABLE"))
            ),
            evidence_basis=(
                f"Area-weighted valid HiRISE optical coverage {opt_cov * 100:.1f}% (footprint {(opt_foot_cov or 0.0) * 100:.1f}%, status {opt_status})"
                if opt_cov is not None
                else f"Optical imagery coverage unverified ({opt_status}; never coerced to 0%)"
            ),
            policy_version=pv,
            threshold_or_rule=f"valid_optical >= {READINESS_POLICY['min_optical_valid_fraction_assessed'] * 100:.0f}%",
            spatial_footprint_coverage_fraction=opt_foot_cov,
            valid_measurement_coverage_fraction=opt_cov,
            product_availability="verified_local" if (opt_cov is not None and opt_cov > 0.0) else opt_status.lower(),
            scientific_validation_state="calibrated_pds_orthophoto" if (opt_cov is not None and opt_cov > 0.0) else "unverified",
            spatial_association_quality="shapely_union_footprint_and_valid_pixel_mask" if opt_cov is not None else "unverified_footprint",
            resolution_adequacy="adequate_0.25m_visual" if (opt_cov is not None and opt_cov > 0.0) else "unverified",
            temporal_relevance="static_orbital_orthophoto",
            missing_inputs=[] if (opt_cov is not None and opt_cov >= READINESS_POLICY["min_optical_valid_fraction_assessed"]) else ["complete_corridor_hirise_orthophoto_mosaic"],
        ),
        DomainAssessmentRecord(
            domain="optical_candidate_features",
            status="PARTIALLY_ASSESSED" if corridor.optical_candidates else ("UNAVAILABLE" if opt_cov is None else "INSUFFICIENT_EVIDENCE"),
            evidence_basis=f"{len(corridor.optical_candidates)} in-corridor contrast/edge candidates (interpretation required)",
            policy_version=pv,
            threshold_or_rule="2D optical candidates are never promoted to confirmed boulder counts or 3D heights",
            spatial_footprint_coverage_fraction=opt_foot_cov,
            valid_measurement_coverage_fraction=opt_cov,
            product_availability="verified_local" if corridor.optical_candidates else "none_detected_or_unavailable",
            scientific_validation_state="candidate_requiring_interpretation",
            spatial_association_quality="in_corridor_polygon_filtered",
            resolution_adequacy="visual_proxy_only",
            temporal_relevance="static_orbital_orthophoto",
            missing_inputs=["stereo_height_verification_for_2d_candidates"],
        ),
        DomainAssessmentRecord(
            domain="geological_context",
            status="PARTIALLY_ASSESSED" if geo_cov_frac > 0.0 else "UNAVAILABLE",
            evidence_basis=(
                f"USGS SIM 3292 global geological map ({geo_cov_frac * 100:.1f}% weighted, {geo_segs}/{seg_count} segments; 1:20,000,000 scale)"
                if geo_cov_frac > 0.0
                else "No geological raster/map verified for corridor"
            ),
            policy_version=pv,
            threshold_or_rule="Regional 1:20M geology is insufficient for outcrop-scale trafficability",
            spatial_footprint_coverage_fraction=geo_cov_frac,
            valid_measurement_coverage_fraction=geo_cov_frac,
            product_availability="verified_local" if geo_cov_frac > 0.0 else "unavailable",
            scientific_validation_state="published_usgs_map_regional_only",
            spatial_association_quality="coarse_1_20M_regional_polygon" if geo_cov_frac > 0.0 else "none",
            resolution_adequacy="insufficient_for_outcrop_scale",
            temporal_relevance="static_geologic_map",
            missing_inputs=["outcrop_scale_geological_map"],
        ),
        DomainAssessmentRecord(
            domain="mineralogical_spectral_context",
            status="PARTIALLY_ASSESSED" if spec_cov_frac > 0.0 else "UNAVAILABLE",
            evidence_basis=(
                f"Localized Curiosity ChemCam/APXS PDS records near {spec_segs}/{seg_count} corridor segments "
                f"(point-sample proxy fraction {spec_cov_frac * 100:.1f}%; not continuous orbital spectroscopy)"
                if spec_cov_frac > 0.0
                else "No verified corridor spectral or geochemical coverage"
            ),
            policy_version=pv,
            threshold_or_rule="Point measurements do not establish whole-corridor mineral continuity",
            spatial_footprint_coverage_fraction=spec_cov_frac,
            valid_measurement_coverage_fraction=spec_cov_frac,
            product_availability="verified_local" if spec_cov_frac > 0.0 else "unavailable",
            scientific_validation_state="localized_rover_elemental_proxy_not_continuous_crism",
            spatial_association_quality="point_records_within_search_radius" if spec_cov_frac > 0.0 else "none",
            resolution_adequacy="point_samples_only_insufficient_for_continuous_corridor",
            temporal_relevance="historical_msl_archive",
            missing_inputs=["continuous_crism_orbital_hyperspectral_cube", "in_situ_chemin_xrd_at_destination"],
        ),
        DomainAssessmentRecord(
            domain="thermal_inertia_and_temperature",
            status="PARTIALLY_ASSESSED" if therm_cov_frac > 0.0 else "UNAVAILABLE",
            evidence_basis=(
                f"Historical REMS thermal archive near {therm_segs}/{seg_count} corridor segments "
                f"(point proxy {therm_cov_frac * 100:.1f}%; no THEMIS/orbital thermal inertia raster)"
                if therm_cov_frac > 0.0
                else "No verified thermal inertia raster or live temperature"
            ),
            policy_version=pv,
            threshold_or_rule="Historical PDS records only; live thermal environment unavailable",
            spatial_footprint_coverage_fraction=therm_cov_frac,
            valid_measurement_coverage_fraction=therm_cov_frac,
            product_availability="verified_local" if therm_cov_frac > 0.0 else "unavailable",
            scientific_validation_state="historical_point_archive_unsuitable_for_live_forecast",
            spatial_association_quality="historical_localized_rems_only" if therm_cov_frac > 0.0 else "none",
            resolution_adequacy="no_spatial_thermal_inertia_map",
            temporal_relevance="historical_archive_stale_for_live_weather",
            missing_inputs=["orbital_themis_thermal_inertia_raster", "live_surface_air_and_ground_temperature"],
        ),
        DomainAssessmentRecord(
            domain="rover_and_surface_observations",
            status="PARTIALLY_ASSESSED" if obs_count > 0 else "UNAVAILABLE",
            evidence_basis=(
                f"{obs_count} localized Gale / Curiosity point observation records indexed near {obs_segs}/{seg_count} segments (non-continuous coverage)"
                if obs_count > 0
                else "No spatially associated Curiosity point records within corridor search radius"
            ),
            policy_version=pv,
            threshold_or_rule="Localized Curiosity records anchor point sites ONLY and never certify whole-corridor ground truth; Perseverance/Jezero records isolated",
            spatial_footprint_coverage_fraction=round(obs_segs / max(1, seg_count), 4) if seg_count else 0.0,
            valid_measurement_coverage_fraction=round(obs_segs / max(1, seg_count), 4) if seg_count else 0.0,
            product_availability="verified_local" if obs_count > 0 else "unavailable",
            scientific_validation_state="published_msl_pds_observations",
            spatial_association_quality="strtree_point_and_footprint_association" if obs_count > 0 else "none",
            resolution_adequacy="point_observations_only",
            temporal_relevance="historical_msl_traverse_archive",
            missing_inputs=[] if obs_count > 0 else ["in_corridor_curiosity_observations"],
        ),
        DomainAssessmentRecord(
            domain="navigation_and_return_feasibility",
            status=(
                "ASSESSED"
                if (
                    corridor.route_surface_distance_m > 0
                    and native_resolution_m <= READINESS_POLICY["max_local_dem_resolution_m"]
                    and getattr(request, "independent_return_computed", False) is True
                )
                else ("PARTIALLY_ASSESSED" if corridor.route_surface_distance_m > 0 else "UNAVAILABLE")
            ),
            evidence_basis=(
                f"Outbound {corridor.route_surface_distance_m:.1f} m with {len(corridor.segments)} segments; "
                + (
                    "independent destination->start return trajectory verified."
                    if getattr(request, "independent_return_computed", False)
                    else "independent return trajectory not yet verified inside corridor dossier (run EVA Return Analysis)."
                )
            ),
            policy_version=pv,
            threshold_or_rule="Requires independent destination->origin path computation, checkpoint turnback verification, and <= 2.0 m/px DEM slope coverage",
            spatial_footprint_coverage_fraction=round(valid_dem, 4),
            valid_measurement_coverage_fraction=round(valid_dem, 4),
            product_availability="computed" if corridor.route_surface_distance_m > 0 else "unavailable",
            scientific_validation_state="validated_8_neighbor_dijkstra_on_dem",
            spatial_association_quality="exact_route_geometry",
            resolution_adequacy=dem_res_adequacy,
            temporal_relevance="computed_for_current_dem",
            missing_inputs=[] if getattr(request, "independent_return_computed", False) else ["independent_destination_to_start_return_route"],
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
            product_availability="user_configured" if request.walking_speed_mps is not None else "unavailable",
            scientific_validation_state="explicit_user_assumption_unvalidated_biomechanics",
            spatial_association_quality="corridor_segment_integration",
            resolution_adequacy=dem_res_adequacy,
            temporal_relevance="mission_assumption",
            missing_inputs=[k for k in ("walking_speed_mps", "mission_duration_limit_s", "return_reserve_fraction") if getattr(request, k) is None],
        ),
        DomainAssessmentRecord(
            domain="gravitational_energy_work",
            status="ASSESSED" if energy_budget.available else "UNAVAILABLE",
            evidence_basis="W = m * g_mars; dPE = m * g * dh (Mars Standard Gravity 3.72076 m/s^2)",
            policy_version=pv,
            threshold_or_rule="Requires explicit suit + payload mass; downhill does NOT recover metabolic energy",
            spatial_footprint_coverage_fraction=round(valid_dem, 4) if energy_budget.available else None,
            valid_measurement_coverage_fraction=round(valid_dem, 4) if energy_budget.available else None,
            product_availability="computed_from_user_mass" if energy_budget.available else "unavailable",
            scientific_validation_state="classical_mechanics_lower_bound_only",
            spatial_association_quality="corridor_elevation_profile",
            resolution_adequacy=dem_res_adequacy,
            temporal_relevance="physics_constant",
            missing_inputs=[] if energy_budget.available else ["astronaut_suit_mass_kg", "payload_mass_kg"],
        ),
        DomainAssessmentRecord(
            domain="consumables_and_eva_endurance",
            status="ASSESSED" if consumables_configured else "UNAVAILABLE",
            evidence_basis="Unit-aware explicit user EVA supply limits" if consumables_configured else "No user O2/battery/cooling supply limits supplied",
            policy_version=pv,
            threshold_or_rule="Never infers suit consumables from route length without explicit consumption rate",
            product_availability="user_configured" if consumables_configured else "unavailable",
            scientific_validation_state="unvalidated_hardware_model" if not consumables_configured else "explicit_user_linear_budget",
            spatial_association_quality="not_spatially_varying",
            resolution_adequacy="not_applicable",
            temporal_relevance="mission_assumption",
            missing_inputs=[] if consumables_configured else ["explicit_o2_battery_water_cooling_limits"],
        ),
        DomainAssessmentRecord(
            domain="live_localization_and_telemetry",
            status="PARTIALLY_ASSESSED" if live_telemetry_connected else "UNAVAILABLE",
            evidence_basis="Live authenticated SSE telemetry only when external feed active" if live_telemetry_connected else "No verified live astronaut position feed connected",
            policy_version=pv,
            threshold_or_rule="Zero fabricated live astronaut coordinates",
            product_availability="connected" if live_telemetry_connected else "unavailable",
            scientific_validation_state="external_telemetry_dependent",
            spatial_association_quality="live_stream" if live_telemetry_connected else "none",
            resolution_adequacy="sensor_dependent" if live_telemetry_connected else "unavailable",
            temporal_relevance="real_time_required",
            missing_inputs=[] if live_telemetry_connected else ["authenticated_eva_telemetry_feed"],
        ),
        DomainAssessmentRecord(
            domain="astronaut_survivability_safety_certification",
            status="UNVALIDATED",
            evidence_basis="Regolith bearing strength, dust depth, subsurface voids, and suit thermal endurance are unmodeled",
            policy_version=pv,
            threshold_or_rule="MARSCOPE is an analytical planning support engine, NEVER an EVA life-safety certification",
            product_availability="unavailable",
            scientific_validation_state="unvalidated",
            spatial_association_quality="none",
            resolution_adequacy="unmodeled_geotechnical_and_physiological",
            temporal_relevance="not_applicable",
            missing_inputs=["regolith_geotechnical_strength", "radiation_weather_live_clearance", "eva_flight_certification"],
        ),
    ]

    math_complete = (
        dem_status in ("ASSESSED", "PARTIALLY_ASSESSED")
        and has_slope
        and request.walking_speed_mps is not None
        and energy_budget.available
    )
    return domains, bool(math_complete)

