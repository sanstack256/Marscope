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
    RankingDimensions,
    SearchMatchType,
)

# Authoritative Mars IAU2000 ellipsoidal geodesic calculator
MARS_GEOD = Geod(a=MARS_EQUATORIAL_RADIUS_M, b=MARS_POLAR_RADIUS_M)


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
    distance_scale_m: float = 2000.0,
) -> RankingDimensions:
    """
    Compute deterministic, explainable ranking components (NOT probability percentages).
    """
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

    # 2. Abundance normalized cleanly within the observed result set for this unit/query
    val = float(ev.normalized_value or 0.0)
    if ev.normalized_unit == "ppm":
        val_wt = val / 10000.0
        max_wt = max(max_observed_abundance / 10000.0, 1e-6)
    else:
        val_wt = val
        max_wt = max(max_observed_abundance, 1e-6)
    abundance_comp = round(min(1.0, max(0.0, val_wt / max_wt)), 4) if max_wt > 0 else 0.0

    # 3. Uncertainty & quality score
    quality_comp = 0.85
    if ev.quality_flag and "low" in ev.quality_flag.lower():
        quality_comp -= 0.25
    if ev.uncertainty_value is not None and val > 0:
        rel_err = ev.uncertainty_value / val
        if rel_err <= 0.05:
            quality_comp = min(1.0, quality_comp + 0.10)
        elif rel_err > 0.35:
            quality_comp = max(0.25, quality_comp - 0.25)
    quality_comp = round(max(0.0, min(1.0, quality_comp)), 4)

    # 4. Multi-instrument / repeated observation corroboration
    n_inst = len(set(corroborating_instruments))
    corrob_comp = round(min(1.0, 0.35 * max(0, n_inst - 1) + 0.12 * min(4, max(0, nearby_count - 1)) + 0.20), 4)

    # 5. Geodesic spatial proximity if astronaut position is available
    prox_comp: Optional[float] = None
    if distance_m is not None and math.isfinite(distance_m):
        prox_comp = round(math.exp(-max(0.0, distance_m) / max(1.0, distance_scale_m)), 4)
        score = (
            0.35 * tier
            + 0.25 * abundance_comp
            + 0.15 * quality_comp
            + 0.10 * corrob_comp
            + 0.15 * prox_comp
        )
        formula = "0.35*tier + 0.25*abundance + 0.15*quality + 0.10*corroboration + 0.15*exp(-dist_m/2000)"
    else:
        score = (
            0.40 * tier
            + 0.30 * abundance_comp
            + 0.15 * quality_comp
            + 0.15 * corrob_comp
        )
        formula = "0.40*tier + 0.30*abundance + 0.15*quality + 0.15*corroboration (no astronaut position)"

    val_str = f"{ev.normalized_value:.3g} {ev.normalized_unit}" if ev.normalized_value is not None else "N/A"
    err_str = f" +/- {ev.uncertainty_value:.3g}" if ev.uncertainty_value is not None else ""
    dist_str = f"; {distance_m:.0f} m geodesic from astronaut" if distance_m is not None else ""
    rationale = (
        f"{ev.instrument_id} {ev.canonical_species_id}={val_str}{err_str} ({match_type.value})"
        f"; {len(set(corroborating_instruments))} instrument(s) within cluster{dist_str}."
    )

    return RankingDimensions(
        evidence_tier_score=round(tier, 4),
        abundance_component=abundance_comp,
        quality_component=quality_comp,
        corroboration_component=corrob_comp,
        spatial_proximity_component=prox_comp,
        composite_rank_score=round(score, 4),
        score_formula=formula,
        rationale=rationale,
    )
