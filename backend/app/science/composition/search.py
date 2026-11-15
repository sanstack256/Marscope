"""
MARSCOPE Composition Discovery & Candidate Location Search Engine
Martian Surface Intelligence & Exploration System

Orchestrates query resolution against the controlled species vocabulary, queries the
persistent SQLite spatial index, computes Mars ellipsoidal distances from astronaut
coordinates, clusters hits into candidate geological sites, and returns full provenance.
"""

from collections import defaultdict
import hashlib
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.geospatial.crs import normalize_longitude_360, validate_mars_coordinates
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CandidateDiscoveryLocation,
    CompositionEvidence,
    CompositionIndexStatus,
    CompositionSearchMode,
    EvidenceType,
    LocationSemanticType,
    MeasurementCategory,
    RankedCompositionHit,
    RankingConfiguration,
    SearchMatchType,
    SpeciesCategory,
    SpeciesResolutionResult,
)
from app.science.composition.normalization import oxide_wt_pct_to_element_with_metadata
from app.science.composition.ranking import (
    DEFAULT_HEURISTIC_RANKING_CONFIG,
    compute_ranking_dimensions,
    mars_geodesic_distance_and_bearing,
)
from app.science.composition.species import (
    get_child_minerals_for_group,
    get_element_bearing_minerals,
    resolve_species_query,
)


class StructuredCompositionQuery(BaseModel):
    query: str = Field(..., min_length=1)
    search_mode: CompositionSearchMode = CompositionSearchMode.AUTO
    include_element_bearing_minerals: bool = False
    astronaut_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    astronaut_longitude: Optional[float] = Field(None, ge=-180.0, le=360.0)
    max_distance_m: Optional[float] = Field(None, gt=0.0)
    instruments: Optional[List[str]] = None
    sol_min: Optional[int] = Field(None, ge=0)
    sol_max: Optional[int] = Field(None, ge=0)
    min_value: Optional[float] = Field(None, ge=0.0)
    max_value: Optional[float] = Field(None, ge=0.0)
    measurement_category_filter: Optional[MeasurementCategory] = None
    exclude_low_quality: bool = False
    bbox: Optional[Tuple[float, float, float, float]] = None
    sort_by: str = Field("rank", description="rank | distance | abundance | category_abundance | sol")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)
    ranking_config: Optional[RankingConfiguration] = None


class StructuredCompositionSearchResult(BaseModel):
    query: str
    resolution: SpeciesResolutionResult
    index_status: CompositionIndexStatus
    index_available: bool
    astronaut_position_used: Optional[Dict[str, float]] = None
    ranking_configuration_used: RankingConfiguration = Field(default_factory=lambda: DEFAULT_HEURISTIC_RANKING_CONFIG)
    total_located_matches: int = 0
    unlocated_matches_count: int = 0
    returned_count: int = 0
    limit: int = 50
    offset: int = 0
    measurement_categories_present: List[MeasurementCategory] = Field(default_factory=list)
    grouped_counts_by_measurement_category: Dict[str, int] = Field(default_factory=dict)
    applied_filter_scope_note: Optional[str] = None
    hits: List[RankedCompositionHit] = Field(default_factory=list)
    candidate_locations: List[CandidateDiscoveryLocation] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
    scientific_warnings: List[str] = Field(default_factory=list)


def classify_measurement_category(ev: CompositionEvidence, match_type: SearchMatchType) -> MeasurementCategory:
    """Assign explicit MeasurementCategory distinguishing elemental, oxide, and mineral measurements."""
    if match_type == SearchMatchType.OXIDE_TO_ELEMENT_CONVERSION or ev.is_stoichiometric_conversion:
        return MeasurementCategory.OXIDE_DERIVED_ELEMENTAL_CONCENTRATION
    if ev.species_category == SpeciesCategory.ELEMENT or ev.evidence_type == EvidenceType.DIRECT_ELEMENT_MEASUREMENT:
        return MeasurementCategory.DIRECT_ELEMENTAL_CONCENTRATION
    if ev.species_category == SpeciesCategory.OXIDE or ev.evidence_type == EvidenceType.OXIDE_COMPOSITION_MEASUREMENT:
        return MeasurementCategory.DIRECT_OXIDE_CONCENTRATION
    if match_type == SearchMatchType.MINERAL_GROUP_MEMBER or ev.species_category == SpeciesCategory.MINERAL_GROUP:
        return MeasurementCategory.MINERAL_GROUP_MEMBERSHIP_EVIDENCE
    return MeasurementCategory.MINERAL_WEIGHT_PERCENT


class CompositionSearchService:
    """Service executing scientifically governed element & mineral discovery queries."""

    def __init__(self, index: CompositionSpatialIndex):
        self.index = index

    def search(self, req: StructuredCompositionQuery) -> StructuredCompositionSearchResult:
        valid_sorts = {"rank", "distance", "abundance", "category_abundance", "sol"}
        if req.sort_by not in valid_sorts:
            raise ValueError(f"Unsupported sort_by='{req.sort_by}'. Allowed: {sorted(valid_sorts)}.")
        if req.min_value is not None and req.max_value is not None and req.min_value > req.max_value:
            raise ValueError(f"min_value ({req.min_value}) cannot exceed max_value ({req.max_value}).")

        status = self.index.get_status()
        res = resolve_species_query(req.query)

        astro_pos: Optional[Dict[str, float]] = None
        if req.astronaut_latitude is not None and req.astronaut_longitude is not None:
            a_lat, a_lon = validate_mars_coordinates(req.astronaut_latitude, req.astronaut_longitude)
            astro_pos = {"latitude": a_lat, "longitude_east": normalize_longitude_360(a_lon)}

        rank_cfg = req.ranking_config or DEFAULT_HEURISTIC_RANKING_CONFIG

        if not status.index_available:
            return StructuredCompositionSearchResult(
                query=req.query,
                resolution=res,
                index_status=status,
                index_available=False,
                astronaut_position_used=astro_pos,
                ranking_configuration_used=rank_cfg,
                unavailable_reason=(
                    "Composition spatial index is currently empty or unbuilt. "
                    "Acquire NASA PDS composition products (APXS / ChemCam MOC / CheMin RDR5) "
                    "and run index rebuild."
                ),
            )

        if not res.resolved or res.species is None:
            return StructuredCompositionSearchResult(
                query=req.query,
                resolution=res,
                index_status=status,
                index_available=True,
                astronaut_position_used=astro_pos,
                ranking_configuration_used=rank_cfg,
                unavailable_reason=res.explanation,
            )

        spec = res.species
        warnings: List[str] = []

        # Collect matching canonical species IDs + match classifications without conflating types
        target_species_meta: Dict[str, Tuple[SearchMatchType, str]] = {}

        if req.search_mode == CompositionSearchMode.MINERAL and spec.category == SpeciesCategory.ELEMENT:
            return StructuredCompositionSearchResult(
                query=req.query,
                resolution=res,
                index_status=status,
                index_available=True,
                astronaut_position_used=astro_pos,
                unavailable_reason=(
                    f"Query '{spec.canonical_id}' is a chemical element, not a crystalline mineral. "
                    "Use search_mode='element' or 'element_bearing_mineral' instead."
                ),
            )

        if spec.category == SpeciesCategory.ELEMENT:
            target_species_meta[spec.canonical_id] = (
                SearchMatchType.EXACT_SPECIES,
                f"Direct elemental measurement of {spec.canonical_id}.",
            )
            for ox_id in spec.child_species:
                target_species_meta[ox_id] = (
                    SearchMatchType.OXIDE_TO_ELEMENT_CONVERSION,
                    f"Calibrated {ox_id} oxide concentration converted via exact IUPAC stoichiometry to elemental {spec.canonical_id} wt%.",
                )
            if req.include_element_bearing_minerals or req.search_mode == CompositionSearchMode.ELEMENT_BEARING_MINERAL:
                for min_id in get_element_bearing_minerals(spec.canonical_id):
                    target_species_meta[min_id] = (
                        SearchMatchType.ELEMENT_BEARING_MINERAL,
                        f"Crystalline mineral '{min_id}' structurally bears {spec.canonical_id}; CheMin mineral wt% is NOT elemental {spec.canonical_id} wt%.",
                    )
        elif spec.category == SpeciesCategory.OXIDE:
            target_species_meta[spec.canonical_id] = (
                SearchMatchType.EXACT_SPECIES,
                f"Direct calibrated {spec.canonical_id} oxide concentration.",
            )
            if spec.canonical_id == "FeO":
                target_species_meta["FeOT"] = (
                    SearchMatchType.EXACT_SPECIES,
                    "ChemCam total iron oxide reported as FeOT (equivalent total FeO basis).",
                )
            elif spec.canonical_id == "FeOT":
                target_species_meta["FeO"] = (
                    SearchMatchType.EXACT_SPECIES,
                    "APXS total iron oxide reported as FeO.",
                )
        elif spec.category == SpeciesCategory.MINERAL_GROUP:
            target_species_meta[spec.canonical_id] = (
                SearchMatchType.EXACT_SPECIES,
                f"Direct detection of mineral group '{spec.canonical_id}'.",
            )
            for child in get_child_minerals_for_group(spec.canonical_id):
                target_species_meta[child] = (
                    SearchMatchType.MINERAL_GROUP_MEMBER,
                    f"Member phase '{child}' belonging to mineral group '{spec.canonical_id}'.",
                )
        else:
            target_species_meta[spec.canonical_id] = (
                SearchMatchType.EXACT_SPECIES,
                f"Direct crystalline mineral detection of '{spec.canonical_id}'.",
            )

        species_ids = list(target_species_meta.keys())

        # Query ALL matching (located + count unlocated separately so unlocated NEVER leaks to map/distance ranking)
        all_rows = self.index.query_evidence(
            species_ids=species_ids,
            located_only=False,
            instruments=req.instruments,
            sol_min=req.sol_min,
            sol_max=req.sol_max,
            bbox=req.bbox,
        )

        located_raw: List[CompositionEvidence] = []
        unlocated_count = 0
        for ev in all_rows:
            if not ev.location_verified or ev.latitude is None or ev.longitude_east is None:
                unlocated_count += 1
                continue
            located_raw.append(ev)

        if unlocated_count > 0:
            warnings.append(
                f"{unlocated_count} additional matching observation(s) lack verified planetary coordinates and were excluded from map markers and distance ranking."
            )

        # Convert oxide measurements to elemental wt% view when user queried an element
        pre_filter: List[Tuple[CompositionEvidence, SearchMatchType, MeasurementCategory, str, Optional[float], Optional[float]]] = []
        for ev in located_raw:
            if req.exclude_low_quality and ev.quality_flag and "low" in ev.quality_flag.lower():
                continue

            mtype, mexpl = target_species_meta[ev.canonical_species_id]
            ev_out = ev
            if mtype == SearchMatchType.OXIDE_TO_ELEMENT_CONVERSION and spec.category == SpeciesCategory.ELEMENT and ev.normalized_value is not None:
                stoich = oxide_wt_pct_to_element_with_metadata(
                    ev.canonical_species_id, ev.normalized_value, ev.uncertainty_value
                )
                # Preserve exact uncertainty matching only if units align cleanly
                el_err = stoich["element_uncertainty_wt_pct"]
                updated_unc_meta = None
                if ev.uncertainty_metadata is not None and el_err is not None:
                    updated_unc_meta = ev.uncertainty_metadata.model_copy(
                        update={
                            "conversion_history": list(ev.uncertainty_metadata.conversion_history)
                            + [f"stoichiometric_oxide_to_element:{ev.canonical_species_id}->{spec.canonical_id} (factor={stoich['stoichiometric_factor']})"]
                        }
                    )
                ev_out = ev.model_copy(
                    update={
                        "normalized_value": stoich["element_wt_pct"],
                        "normalized_unit": "wt%",
                        "uncertainty_value": el_err,
                        "uncertainty_unit": "wt%" if el_err is not None else None,
                        "uncertainty_metadata": updated_unc_meta,
                        "normalization_formula": stoich["formula"],
                        "is_stoichiometric_conversion": True,
                        "source_oxide_species": stoich["source_oxide_species"],
                        "stoichiometric_factor": stoich["stoichiometric_factor"],
                        "stoichiometric_weights_version": stoich["weights_version"],
                    }
                )
                mexpl = (
                    f"Stoichiometric oxide conversion ({stoich['weights_version']}): "
                    f"{ev.canonical_species_id} ({ev.raw_value} {ev.raw_unit}) -> {spec.canonical_id} ({stoich['element_wt_pct']} wt%) via factor {stoich['stoichiometric_factor']}."
                )

            mcat = classify_measurement_category(ev_out, mtype)
            if req.measurement_category_filter is not None and mcat != req.measurement_category_filter:
                continue

            dist_m: Optional[float] = None
            bearing: Optional[float] = None
            if astro_pos is not None:
                dist_m, bearing = mars_geodesic_distance_and_bearing(
                    astro_pos["latitude"],
                    astro_pos["longitude_east"],
                    ev_out.latitude,  # type: ignore[arg-type]
                    ev_out.longitude_east,  # type: ignore[arg-type]
                )
                if req.max_distance_m is not None and dist_m > req.max_distance_m:
                    continue

            pre_filter.append((ev_out, mtype, mcat, mexpl, dist_m, bearing))

        applied_filter_scope_note: Optional[str] = None
        if req.measurement_category_filter is not None:
            applied_filter_scope_note = (
                f"Filtered explicitly to measurement_category='{req.measurement_category_filter.value}'."
            )

        # Measurement-category & unit-safe numeric filtering (min_value / max_value)
        processed: List[Tuple[CompositionEvidence, SearchMatchType, MeasurementCategory, str, Optional[float], Optional[float]]] = []
        if req.min_value is not None or req.max_value is not None:
            elemental_cats = {
                MeasurementCategory.DIRECT_ELEMENTAL_CONCENTRATION,
                MeasurementCategory.OXIDE_DERIVED_ELEMENTAL_CONCENTRATION,
            }
            if req.measurement_category_filter is not None:
                threshold_cats = {req.measurement_category_filter}
                excluded_non_target_count = 0
                scope_label = req.measurement_category_filter.value
            elif spec.category == SpeciesCategory.ELEMENT:
                threshold_cats = elemental_cats
                excluded_non_target_count = sum(1 for item in pre_filter if item[2] not in threshold_cats)
                scope_label = "elemental concentrations (direct + oxide-derived)"
            else:
                distinct_cats = {item[2] for item in pre_filter}
                if len(distinct_cats) > 1:
                    raise ValueError(
                        "Cannot apply unqualified min_value/max_value across multiple measurement categories "
                        f"({sorted(c.value for c in distinct_cats)}). Specify measurement_category_filter."
                    )
                threshold_cats = distinct_cats
                excluded_non_target_count = 0
                scope_label = next((c.value for c in distinct_cats), "none")

            scoped_candidates = [item for item in pre_filter if item[2] in threshold_cats]
            scoped_units = {
                item[0].normalized_unit
                for item in scoped_candidates
                if item[0].normalized_value is not None
            }
            if len(scoped_units) > 1:
                raise ValueError(
                    "Cannot apply single numeric threshold (min_value/max_value) across mixed units "
                    f"({sorted(str(u) for u in scoped_units)}) within {scope_label}. Filter to a single unit-compatible category or subset."
                )

            bounds_desc: List[str] = []
            if req.min_value is not None:
                bounds_desc.append(f"min_value={req.min_value}")
            if req.max_value is not None:
                bounds_desc.append(f"max_value={req.max_value}")
            unit_str = next((u for u in scoped_units if u), "unit")
            applied_filter_scope_note = (
                f"Numeric threshold ({', '.join(bounds_desc)} {unit_str}) applied exclusively to {scope_label}."
            )
            if excluded_non_target_count > 0:
                applied_filter_scope_note += (
                    f" Excluded {excluded_non_target_count} non-elemental host-mineral record(s) "
                    "because mineral wt% cannot be evaluated against an elemental concentration threshold."
                )
                warnings.append(applied_filter_scope_note)

            for item in scoped_candidates:
                val = item[0].normalized_value
                if val is None:
                    continue
                if req.min_value is not None and val < req.min_value:
                    continue
                if req.max_value is not None and val > req.max_value:
                    continue
                processed.append(item)
        else:
            processed = pre_filter

        if not processed:
            reason = (
                f"No located verified detections matched '{spec.canonical_id}' under current filters."
                + (f" ({status.crism_status})" if spec.category in {SpeciesCategory.MINERAL, SpeciesCategory.MINERAL_GROUP} else "")
            )
            return StructuredCompositionSearchResult(
                query=req.query,
                resolution=res,
                index_status=status,
                index_available=True,
                astronaut_position_used=astro_pos,
                ranking_configuration_used=rank_cfg,
                total_located_matches=0,
                unlocated_matches_count=unlocated_count,
                limit=req.limit,
                offset=req.offset,
                applied_filter_scope_note=applied_filter_scope_note,
                unavailable_reason=reason,
                scientific_warnings=warnings,
            )

        zero_unresolved = sum(
            1 for item in processed if item[0].value_semantics == "reported_numerical_zero_unresolved_semantics"
        )
        if zero_unresolved:
            warnings.append(
                f"{zero_unresolved} matching record(s) report a numerical zero whose meaning (absent, below detection, "
                "or true zero) is not defined by the source product; they are preserved as reported zeros and are not "
                "evidence of presence."
            )

        seen_oxide_sources = {item[0].canonical_species_id for item in processed if item[0].is_stoichiometric_conversion}
        if "FeO" in seen_oxide_sources and "FeOT" in seen_oxide_sources:
            warnings.append(
                "Total iron oxide stoichiometry combines APXS total iron reported as FeO with ChemCam LIBS total iron reported as FeOT (both on divalent FeO basis; oxidation state Fe2+/Fe3+ is not independently resolved)."
            )
        if spec.canonical_id in {"FeO", "FeOT"}:
            warnings.append(
                "APXS reports total iron as FeO and ChemCam LIBS MOC reports total iron as FeOT; both express total iron on an equivalent FeO basis rather than separated ferric/ferrous speciation."
            )

        # Compute max abundance strictly per (MeasurementCategory, normalized_unit) scale
        max_abund_by_group: Dict[Tuple[MeasurementCategory, str], float] = {}
        for item in processed:
            ev_out, _, mcat, _, _, _ = item
            if ev_out.normalized_value is not None:
                gkey = (mcat, ev_out.normalized_unit or "")
                max_abund_by_group[gkey] = max(max_abund_by_group.get(gkey, 0.0), float(ev_out.normalized_value))

        cohort_unc_types = [x[0].uncertainty_type for x in processed if x[0].uncertainty_value is not None]
        distinct_unc_types = sorted({t for t in cohort_unc_types if t})
        if len(distinct_unc_types) > 1:
            warnings.append(
                f"Query cohort mixes heterogeneous statistical uncertainty types ({', '.join(distinct_unc_types)}); "
                "cross-instrument numeric quality scoring remains withheld rather than equating incompatible error definitions."
            )

        # Cluster nearby located hits (~0.001 deg ~ 60 m grid key or target) for corroboration & candidate sites
        clusters: Dict[str, List[Tuple[CompositionEvidence, SearchMatchType, MeasurementCategory, str, Optional[float], Optional[float]]]] = {}
        for item in processed:
            ev_out = item[0]
            ckey = f"{round(float(ev_out.latitude), 3):.3f}_{round(float(ev_out.longitude_east), 3):.3f}"
            clusters.setdefault(ckey, []).append(item)

        hits: List[RankedCompositionHit] = []
        for item in processed:
            ev_out, mtype, mcat, mexpl, dist_m, bearing = item
            ckey = f"{round(float(ev_out.latitude), 3):.3f}_{round(float(ev_out.longitude_east), 3):.3f}"
            peer_items = clusters[ckey]
            insts = sorted({p[0].instrument_id for p in peer_items})
            gkey = (mcat, ev_out.normalized_unit or "")
            group_max = max_abund_by_group.get(gkey, 1.0)
            rdims = compute_ranking_dimensions(
                ev_out,
                match_type=mtype,
                max_observed_abundance=group_max,
                corroborating_instruments=insts,
                nearby_count=len(peer_items),
                distance_m=dist_m,
                config=rank_cfg,
                cohort_uncertainty_types=distinct_unc_types,
            )
            hits.append(
                RankedCompositionHit(
                    evidence=ev_out,
                    match_type=mtype,
                    measurement_category=mcat,
                    match_explanation=mexpl,
                    distance_from_astronaut_m=round(dist_m, 2) if dist_m is not None else None,
                    bearing_deg=round(bearing, 1) if bearing is not None else None,
                    supporting_instruments_nearby=insts,
                    nearby_observation_count=len(peer_items),
                    ranking=rdims,
                )
            )

        # Sort hits deterministically (never allow flat abundance across mixed categories or units)
        if req.sort_by == "distance" and astro_pos is not None:
            hits.sort(
                key=lambda h: (
                    h.distance_from_astronaut_m if h.distance_from_astronaut_m is not None else 1e12,
                    -(h.ranking.composite_rank_score if h.ranking.composite_rank_score is not None else -1.0),
                )
            )
        elif req.sort_by == "abundance":
            distinct_scales = {
                (h.measurement_category, h.evidence.normalized_unit or "")
                for h in hits
            }
            if len(distinct_scales) > 1:
                raise ValueError(
                    "Flat sort_by='abundance' is invalid when hits span multiple measurement categories or units "
                    f"({sorted((c.value if c else 'none', u) for c, u in distinct_scales)}). "
                    "Use sort_by='category_abundance' or set measurement_category_filter."
                )
            hits.sort(key=lambda h: -(h.evidence.normalized_value if h.evidence.normalized_value is not None else -1e18))
        elif req.sort_by == "category_abundance":
            hits.sort(
                key=lambda h: (
                    h.measurement_category.value if h.measurement_category else "",
                    h.evidence.normalized_unit or "",
                    -(h.evidence.normalized_value if h.evidence.normalized_value is not None else -1e18),
                    h.evidence.evidence_id,
                )
            )
        elif req.sort_by == "sol":
            hits.sort(key=lambda h: -(h.evidence.sol or -1))
        else:
            hits.sort(
                key=lambda h: (
                    -(h.ranking.composite_rank_score if h.ranking.composite_rank_score is not None else -1.0),
                    -(h.ranking.abundance_component if h.ranking.abundance_component is not None else -1.0),
                    h.distance_from_astronaut_m if h.distance_from_astronaut_m is not None else 1e12,
                )
            )

        # Build clustered Candidate Discovery Locations (for map markers & destination evaluation)
        hits_by_cluster: Dict[str, List[RankedCompositionHit]] = defaultdict(list)
        for h in hits:
            hkey = f"{round(float(h.evidence.latitude), 3):.3f}_{round(float(h.evidence.longitude_east), 3):.3f}"
            hits_by_cluster[hkey].append(h)

        cand_locs: List[CandidateDiscoveryLocation] = []
        for ckey, items in clusters.items():
            # Pick best ranked hit in cluster as cluster representative
            cluster_hits = hits_by_cluster.get(ckey, [])
            cluster_hits.sort(key=lambda h: -(h.ranking.composite_rank_score if h.ranking.composite_rank_score is not None else -1.0))
            best = cluster_hits[0]
            rep = best.evidence
            sols = [h.evidence.sol for h in cluster_hits if h.evidence.sol is not None]
            sol_rng = f"Sol {min(sols)}-{max(sols)}" if sols and min(sols) != max(sols) else (f"Sol {sols[0]}" if sols else None)
            t_names = sorted({h.evidence.target_name for h in cluster_hits if h.evidence.target_name})
            cand_locs.append(
                CandidateDiscoveryLocation(
                    candidate_id="cand_" + hashlib.sha256(f"{spec.canonical_id}|{ckey}".encode()).hexdigest()[:12],
                    cluster_label=t_names[0] if t_names else f"Site ({rep.latitude:.4f}, {rep.longitude_east:.4f})",
                    latitude=float(rep.latitude),  # type: ignore[arg-type]
                    longitude_east=float(rep.longitude_east),  # type: ignore[arg-type]
                    elevation_m=rep.elevation_m,
                    crs=rep.crs or "IAU2000:49900",
                    location_semantic_type=rep.location_semantic_type,
                    coordinate_source=rep.coordinate_source or "verified",
                    coordinate_uncertainty_m=rep.coordinate_uncertainty_m,
                    coordinate_limitations=rep.coordinate_limitations,
                    distance_from_astronaut_m=best.distance_from_astronaut_m,
                    bearing_deg=best.bearing_deg,
                    matched_evidence_count=len(cluster_hits),
                    distinct_instruments=sorted({h.evidence.instrument_id for h in cluster_hits}),
                    best_evidence_type=rep.evidence_type,
                    best_species_id=rep.canonical_species_id,
                    best_normalized_value=rep.normalized_value,
                    best_normalized_unit=rep.normalized_unit,
                    ranking=best.ranking,
                    evidence_ids=[h.evidence.evidence_id for h in cluster_hits[:20]],
                    target_names=t_names[:10],
                    sol_range=sol_rng,
                )
            )
        cand_locs.sort(key=lambda c: -(c.ranking.composite_rank_score if c.ranking.composite_rank_score is not None else -1.0))

        cat_counts: Dict[str, int] = {}
        for h in hits:
            if h.measurement_category is not None:
                k = h.measurement_category.value
                cat_counts[k] = cat_counts.get(k, 0) + 1
        cats_present = sorted({h.measurement_category for h in hits if h.measurement_category is not None}, key=lambda c: c.value)

        paged_hits = hits[req.offset : req.offset + req.limit]
        return StructuredCompositionSearchResult(
            query=req.query,
            resolution=res,
            index_status=status,
            index_available=True,
            astronaut_position_used=astro_pos,
            ranking_configuration_used=rank_cfg,
            total_located_matches=len(hits),
            unlocated_matches_count=unlocated_count,
            returned_count=len(paged_hits),
            limit=req.limit,
            offset=req.offset,
            measurement_categories_present=cats_present,
            grouped_counts_by_measurement_category=cat_counts,
            applied_filter_scope_note=applied_filter_scope_note,
            hits=paged_hits,
            candidate_locations=cand_locs,
            scientific_warnings=warnings,
        )
