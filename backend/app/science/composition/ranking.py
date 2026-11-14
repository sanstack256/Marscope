"""
MARSCOPE Mars Geodesic Distance & Explainable Composition Evidence Ranking
Martian Surface Intelligence & Exploration System

Computes true ellipsoidal surface distances on the IAU2000 Mars spheroid and
ranks verified composition evidence using transparent, non-probabilistic dimensions.
"""

import math
from typing import Dict, List, Optional, Tuple
from pyproj import Geod
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, MARS_POLAR_RADIUS_M, normalize_longitude_180
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceType,
    RankingConfiguration,
    RankingDimensions,
    SearchMatchType,
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


def compute_ranking_dimensions(
    ev: CompositionEvidence,
    match_type: SearchMatchType,
    max_observed_abundance: float,
    corroborating_instruments: List[str],
    nearby_count: int,
    distance_m: Optional[float] = None,
    config: Optional[RankingConfiguration] = None,
) -> RankingDimensions:
    """
    Compute deterministic, explicitly heuristic exploration-priority ranking components.
    Never fabricates default quality (None when unreported) or default corroboration (None when single observation).
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

    # 2. Abundance normalized cleanly within observed result set
    abundance_comp: Optional[float] = None
    if ev.normalized_value is not None and math.isfinite(ev.normalized_value):
        val = float(ev.normalized_value)
        if ev.normalized_unit == "ppm":
            val_wt = val / 10000.0
            max_wt = max(max_observed_abundance / 10000.0, 1e-6)
        else:
            val_wt = val
            max_wt = max(max_observed_abundance, 1e-6)
        abundance_comp = round(min(1.0, max(0.0, val_wt / max_wt)), 4) if max_wt > 0 else 0.0
    else:
        val = 0.0
        unavailable.append("abundance_component")

    # 3. Uncertainty & calibration quality score (None when source reports no uncertainty or quality flag)
    quality_comp: Optional[float] = None
    if ev.uncertainty_value is not None and ev.normalized_value is not None and ev.normalized_value > 0:
        rel_err = float(ev.uncertainty_value) / float(ev.normalized_value)
        q_base = max(0.05, 1.0 - min(0.95, rel_err))
        if ev.quality_flag and "low" in ev.quality_flag.lower():
            q_base *= 0.65
        quality_comp = round(max(0.0, min(1.0, q_base)), 4)
    elif ev.quality_flag and any(tok in ev.quality_flag.lower() for tok in ("low", "poor", "fair", "high")):
        q_low = ev.quality_flag.lower()
        if "low" in q_low or "poor" in q_low:
            quality_comp = 0.45
        elif "fair" in q_low:
            quality_comp = 0.70
        else:
            quality_comp = 0.90
    else:
        unavailable.append("quality_component")

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

    # Weighted linear sum re-normalized across available components only
    w = cfg.weights
    active_terms: List[Tuple[str, float, float]] = [
        ("evidence_tier", float(w.get("evidence_tier", 0.35)), round(tier, 4))
    ]
    if abundance_comp is not None:
        active_terms.append(("abundance", float(w.get("abundance", 0.25)), abundance_comp))
    if quality_comp is not None:
        active_terms.append(("quality", float(w.get("quality", 0.15)), quality_comp))
    if corrob_comp is not None:
        active_terms.append(("corroboration", float(w.get("corroboration", 0.15)), corrob_comp))
    if prox_comp is not None:
        active_terms.append(("spatial_proximity", float(w.get("spatial_proximity", 0.10)), prox_comp))

    weight_sum = sum(weight for _, weight, _ in active_terms)
    composite_score: Optional[float] = None
    if weight_sum > 0:
        composite_score = round(sum(weight * val_c for _, weight, val_c in active_terms) / weight_sum, 4)

    formula_parts = [f"{round(weight / weight_sum, 3)}*{name}" for name, weight, _ in active_terms] if weight_sum > 0 else []
    formula = f"[{cfg.ranking_config_id} v{cfg.ranking_config_version} HEURISTIC] " + " + ".join(formula_parts)
    if unavailable:
        formula += f" (unreported/excluded: {', '.join(unavailable)})"

    val_str = f"{ev.normalized_value:.3g} {ev.normalized_unit}" if ev.normalized_value is not None else "N/A"
    err_str = f" +/- {ev.uncertainty_value:.3g}" if ev.uncertainty_value is not None else " (uncertainty unreported)"
    dist_str = f"; {distance_m:.0f} m geodesic from astronaut" if distance_m is not None else ""
    rationale = (
        f"[Heuristic priority only] {ev.instrument_id} {ev.canonical_species_id}={val_str}{err_str} "
        f"({match_type.value}); {n_inst} instrument(s), {nearby_count} obs at cluster{dist_str}."
    )

    return RankingDimensions(
        ranking_config_id=cfg.ranking_config_id,
        ranking_config_version=cfg.ranking_config_version,
        is_heuristic_only=cfg.is_heuristic_only,
        evidence_tier_score=round(tier, 4),
        abundance_component=abundance_comp,
        quality_component=quality_comp,
        corroboration_component=corrob_comp,
        spatial_proximity_component=prox_comp,
        composite_rank_score=composite_score,
        unavailable_dimensions=unavailable,
        score_formula=formula,
        rationale=rationale,
    )
