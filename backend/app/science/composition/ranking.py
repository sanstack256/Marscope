"""
MARSCOPE Mars Geodesic Distance & Explainable Composition Evidence Ranking
Martian Surface Intelligence & Exploration System

Computes true ellipsoidal surface distances on the IAU2000 Mars spheroid and
ranks verified composition evidence using transparent, non-probabilistic dimensions.
"""

import math
from typing import List, Optional, Sequence, Tuple
from pyproj import Geod
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, MARS_POLAR_RADIUS_M, normalize_longitude_180
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceType,
    RankingConfiguration,
    RankingDimensions,
    RelativeUncertaintySummary,
    SearchMatchType,
)
from app.science.composition.uncertainty import (
    evaluate_uncertainty_compatibility,
    get_uncertainty_spec,
    normalize_uncertainty_unit,
)

# Authoritative Mars IAU2000 ellipsoidal geodesic calculator
MARS_GEOD = Geod(a=MARS_EQUATORIAL_RADIUS_M, b=MARS_POLAR_RADIUS_M)

DEFAULT_HEURISTIC_RANKING_CONFIG = RankingConfiguration()


def mars_geodesic_distance_and_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> Tuple[float, float]:
    """
    Compute shortest ellipsoidal geodesic distance (meters) and forward azimuth
    (degrees clockwise from North, [0, 360)) on IAU2000 Mars.
    """
    l1 = normalize_longitude_180(lon1)
    l2 = normalize_longitude_180(lon2)
    az12, _, dist_m = MARS_GEOD.inv(l1, lat1, l2, lat2)
    bearing = az12 % 360.0
    return float(dist_m), float(bearing)


def compute_relative_uncertainty(ev: CompositionEvidence) -> RelativeUncertaintySummary:
    """
    Compute derived relative_uncertainty = uncertainty_value / normalized_value cleanly
    ONLY when uncertainty & measurement are finite, positive measurement (> 0),
    physically commensurable (identical physical concentration unit), and statistically
    defined. Never converts relative uncertainty into a numerical quality score.
    """
    if ev.uncertainty_value is None or not math.isfinite(ev.uncertainty_value):
        return RelativeUncertaintySummary(
            available=False,
            numerator_uncertainty=ev.uncertainty_value,
            numerator_unit=ev.uncertainty_unit,
            denominator_measurement=ev.normalized_value,
            denominator_unit=ev.normalized_unit,
            uncertainty_type=ev.uncertainty_type,
            unavailable_reason="Source record reports no quantitative uncertainty value.",
        )
    if ev.normalized_value is None or not math.isfinite(ev.normalized_value) or ev.normalized_value <= 0.0:
        return RelativeUncertaintySummary(
            available=False,
            numerator_uncertainty=ev.uncertainty_value,
            numerator_unit=ev.uncertainty_unit,
            denominator_measurement=ev.normalized_value,
            denominator_unit=ev.normalized_unit,
            uncertainty_type=ev.uncertainty_type,
            unavailable_reason=(
                "Measurement value is zero, negative, or missing; relative uncertainty "
                "(uncertainty / measurement) is mathematically undefined."
            ),
        )
    unc_unit_canon, unc_is_phys = normalize_uncertainty_unit(ev.uncertainty_unit)
    norm_unit_canon, norm_is_phys = normalize_uncertainty_unit(ev.normalized_unit)
    if not unc_is_phys or not norm_is_phys or unc_unit_canon != norm_unit_canon:
        return RelativeUncertaintySummary(
            available=False,
            numerator_uncertainty=ev.uncertainty_value,
            numerator_unit=ev.uncertainty_unit,
            denominator_measurement=ev.normalized_value,
            denominator_unit=ev.normalized_unit,
            uncertainty_type=ev.uncertainty_type,
            unavailable_reason=(
                f"Uncertainty unit '{ev.uncertainty_unit or 'missing'}' is not physically commensurable "
                f"with measurement unit '{ev.normalized_unit or 'missing'}'; ratio withheld."
            ),
        )
    spec = get_uncertainty_spec(ev.uncertainty_type)
    if not spec.allows_relative_uncertainty:
        return RelativeUncertaintySummary(
            available=False,
            numerator_uncertainty=ev.uncertainty_value,
            numerator_unit=unc_unit_canon,
            denominator_measurement=ev.normalized_value,
            denominator_unit=norm_unit_canon,
            uncertainty_type=spec.uncertainty_type,
            statistical_interpretation=spec.statistical_interpretation,
            unavailable_reason=(
                f"Uncertainty type '{spec.uncertainty_type}' lacks a validated statistical scale "
                f"({spec.coverage_confidence_level}); relative uncertainty withheld."
            ),
        )

    ratio = round(float(ev.uncertainty_value) / float(ev.normalized_value), 6)
    hist = list(ev.uncertainty_metadata.conversion_history) if ev.uncertainty_metadata else []
    return RelativeUncertaintySummary(
        available=True,
        value=ratio,
        percent=round(ratio * 100.0, 4),
        numerator_uncertainty=float(ev.uncertainty_value),
        numerator_unit=unc_unit_canon,
        denominator_measurement=float(ev.normalized_value),
        denominator_unit=norm_unit_canon,
        uncertainty_type=spec.uncertainty_type,
        statistical_interpretation=spec.statistical_interpretation,
        conversion_history=hist,
    )


def compute_ranking_dimensions(
    ev: CompositionEvidence,
    match_type: SearchMatchType,
    max_observed_abundance: float,
    corroborating_instruments: List[str],
    nearby_count: int,
    distance_m: Optional[float] = None,
    config: Optional[RankingConfiguration] = None,
    cohort_uncertainty_types: Optional[Sequence[Optional[str]]] = None,
) -> RankingDimensions:
    """
    Compute deterministic, explicitly heuristic exploration-priority ranking components.

    Never converts relative uncertainty into a numerical quality score, never treats unvalidated
    uncertainty types as comparable, and never invents default corroboration.
    """
    cfg = config or DEFAULT_HEURISTIC_RANKING_CONFIG
    unavailable: List[str] = []

    # 1. Evidence tier weight by analytical directness
    if match_type == SearchMatchType.EXACT_SPECIES and ev.evidence_type == EvidenceType.DIRECT_MINERAL_DETECTION:
        tier = 1.0
    elif match_type in {SearchMatchType.EXACT_SPECIES, SearchMatchType.MINERAL_GROUP_MEMBER}:
        tier = 0.95
    elif match_type == SearchMatchType.OXIDE_TO_ELEMENT_CONVERSION:
        tier = 0.85
    elif match_type == SearchMatchType.ELEMENT_BEARING_MINERAL:
        tier = 0.60
    else:
        tier = 0.50

    # 2. Abundance normalized cleanly within the compatible measurement category & unit scale
    abundance_comp: Optional[float] = None
    if ev.normalized_value is not None and math.isfinite(ev.normalized_value):
        val_num = float(ev.normalized_value)
        max_num = max(float(max_observed_abundance), 1e-6)
        abundance_comp = round(min(1.0, max(0.0, val_num / max_num)), 4) if max_num > 0 else 0.0
    else:
        unavailable.append("abundance_component")

    # 3. Quality scoring strictly withheld (no calibrated quality model exists); evaluate compatibility + relative uncertainty separately
    quality_comp: Optional[float] = None
    _, compat_status, compat_reason = evaluate_uncertainty_compatibility(
        ev.uncertainty_type,
        ev.uncertainty_value,
        cohort_uncertainty_types=cohort_uncertainty_types,
    )
    rel_unc = compute_relative_uncertainty(ev)
    unavailable.append("quality_component")
    quality_reason = (
        "Numerical quality scoring withheld: no independently validated measurement-quality model exists "
        "(relative_uncertainty is reported separately when valid and is never mapped to quality)."
    )
    if compat_reason:
        quality_reason += f" {compat_reason}"

    # 4. Multi-instrument / repeated observation corroboration (None when only 1 observation exists)
    n_inst = len(set(corroborating_instruments))
    corrob_comp: Optional[float] = None
    if nearby_count >= 2 or n_inst >= 2:
        corrob_comp = round(
            min(1.0, 0.40 * max(0, n_inst - 1) + 0.15 * min(4, max(0, nearby_count - 1))),
            4,
        )
    else:
        unavailable.append("corroboration_component")

    # 5. Geodesic spatial proximity if astronaut position is available
    prox_comp: Optional[float] = None
    if distance_m is not None and math.isfinite(distance_m):
        prox_comp = round(
            math.exp(-max(0.0, distance_m) / max(1.0, cfg.distance_reference_scale_m)),
            4,
        )
    else:
        unavailable.append("spatial_proximity_component")

    # Weighted linear sum re-normalized solely across justified heuristic dimensions (never includes quality)
    w = cfg.weights
    active_terms: List[Tuple[str, float, float]] = [
        ("evidence_tier", float(w.get("evidence_tier", 0.40)), round(tier, 4))
    ]
    if abundance_comp is not None:
        active_terms.append(("abundance", float(w.get("abundance", 0.30)), abundance_comp))
    if corrob_comp is not None:
        active_terms.append(("corroboration", float(w.get("corroboration", 0.20)), corrob_comp))
    if prox_comp is not None:
        active_terms.append(("spatial_proximity", float(w.get("spatial_proximity", 0.10)), prox_comp))

    weight_sum = sum(weight for _, weight, _ in active_terms)
    composite_score: Optional[float] = None
    if weight_sum > 0:
        composite_score = round(sum(weight * val_c for _, weight, val_c in active_terms) / weight_sum, 4)

    formula_parts = [f"{round(weight / weight_sum, 3)}*{name}" for name, weight, _ in active_terms] if weight_sum > 0 else []
    formula = f"[{cfg.ranking_config_id} v{cfg.ranking_config_version} HEURISTIC] " + " + ".join(formula_parts)
    if unavailable:
        formula += f" (withheld/unavailable: {', '.join(unavailable)})"

    val_str = f"{ev.normalized_value:.3g} {ev.normalized_unit}" if ev.normalized_value is not None else "N/A"
    err_str = (
        f" +/- {ev.uncertainty_value:.3g} {ev.uncertainty_unit or 'unitless'} ({ev.uncertainty_type or 'unknown'})"
        if ev.uncertainty_value is not None
        else " (uncertainty unreported)"
    )
    rel_str = (
        f" [rel_unc={rel_unc.percent:.2f}%]"
        if rel_unc.available and rel_unc.percent is not None
        else ""
    )
    dist_str = f"; {distance_m:.0f} m geodesic from astronaut" if distance_m is not None else ""
    rationale = (
        f"[Heuristic priority only — NOT scientific confidence or calibrated quality] "
        f"{ev.instrument_id} {ev.canonical_species_id}={val_str}{err_str}{rel_str} "
        f"({match_type.value}); {n_inst} instrument(s), {nearby_count} obs at cluster{dist_str}."
    )

    return RankingDimensions(
        ranking_config_id=cfg.ranking_config_id,
        ranking_config_version=cfg.ranking_config_version,
        is_heuristic_only=cfg.is_heuristic_only,
        ranking_methodology_label="HEURISTIC_EXPLORATION_PRIORITY_ONLY",
        evidence_tier_score=round(tier, 4),
        abundance_component=abundance_comp,
        quality_component=quality_comp,
        uncertainty_compatibility_status=compat_status,
        quality_exclusion_reason=quality_reason,
        relative_uncertainty=rel_unc,
        corroboration_component=corrob_comp,
        spatial_proximity_component=prox_comp,
        composite_rank_score=composite_score,
        unavailable_dimensions=unavailable,
        score_formula=formula,
        rationale=rationale,
    )
