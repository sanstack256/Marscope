"""
MARSCOPE Composition Discovery & Candidate Location Search Engine
Martian Surface Intelligence & Exploration System

Orchestrates query resolution against the controlled species vocabulary, queries the
persistent SQLite spatial index, computes Mars ellipsoidal distances from astronaut
coordinates, clusters hits into candidate geological sites, and returns full provenance.
"""

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
    RankedCompositionHit,
    SearchMatchType,
    SpeciesCategory,
    SpeciesResolutionResult,
)
from app.science.composition.normalization import oxide_wt_pct_to_element_wt_pct
from app.science.composition.ranking import (
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
    exclude_low_quality: bool = False
    bbox: Optional[Tuple[float, float, float, float]] = None
    sort_by: str = Field("rank", description="rank | distance | abundance | sol")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class StructuredCompositionSearchResult(BaseModel):
    query: str
    resolution: SpeciesResolutionResult
    index_status: CompositionIndexStatus
    index_available: bool
    astronaut_position_used: Optional[Dict[str, float]] = None
    total_located_matches: int = 0
    unlocated_matches_count: int = 0
    returned_count: int = 0
    limit: int = 50
    offset: int = 0
    hits: List[RankedCompositionHit] = Field(default_factory=list)
    candidate_locations: List[CandidateDiscoveryLocation] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
    scientific_warnings: List[str] = Field(default_factory=list)


class CompositionSearchService:
    """Service executing scientifically governed element & mineral discovery queries."""

    def __init__(self, index: CompositionSpatialIndex):
        self.index = index

    def search(self, req: StructuredCompositionQuery) -> StructuredCompositionSearchResult:
        status = self.index.get_status()
        res = resolve_species_query(req.query)

        astro_pos: Optional[Dict[str, float]] = None
        if req.astronaut_latitude is not None and req.astronaut_longitude is not None:
            a_lat, a_lon = validate_mars_coordinates(req.astronaut_latitude, req.astronaut_longitude)
            astro_pos = {"latitude": a_lat, "longitude_east": normalize_longitude_360(a_lon)}

        if not status.index_available:
            return StructuredCompositionSearchResult(
                query=req.query,
                resolution=res,
                index_status=status,
                index_available=False,
                astronaut_position_used=astro_pos,
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
        processed: List[Tuple[CompositionEvidence, SearchMatchType, str, Optional[float], Optional[float]]] = []
        for ev in located_raw:
            if req.exclude_low_quality and ev.quality_flag and "low" in ev.quality_flag.lower():
                continue

            mtype, mexpl = target_species_meta[ev.canonical_species_id]
            ev_out = ev
            if mtype == SearchMatchType.OXIDE_TO_ELEMENT_CONVERSION and spec.category == SpeciesCategory.ELEMENT and ev.normalized_value is not None:
                el_id, el_val, el_err, stoich_formula = oxide_wt_pct_to_element_wt_pct(
                    ev.canonical_species_id, ev.normalized_value, ev.uncertainty_value
                )
                ev_out = ev.model_copy(
                    update={
                        "normalized_value": el_val,
                        "normalized_unit": "wt%",
                        "uncertainty_value": el_err,
                        "normalization_formula": stoich_formula,
                    }
                )
                mexpl = f"{ev.canonical_species_id} ({ev.raw_value} {ev.raw_unit}) converted via {stoich_formula}."

            if req.min_value is not None and (ev_out.normalized_value is None or ev_out.normalized_value < req.min_value):
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

            processed.append((ev_out, mtype, mexpl, dist_m, bearing))

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
                total_located_matches=0,
                unlocated_matches_count=unlocated_count,
                limit=req.limit,
                offset=req.offset,
                unavailable_reason=reason,
                scientific_warnings=warnings,
            )

        # Compute max abundance per query unit scale for ranking normalization
        max_abund = max((float(x[0].normalized_value or 0.0) for x in processed), default=1.0)

        # Cluster nearby located hits (~0.001 deg ~ 60 m grid key or target) for corroboration & candidate sites
        clusters: Dict[str, List[Tuple[CompositionEvidence, SearchMatchType, str, Optional[float], Optional[float]]]] = {}
        for item in processed:
            ev_out = item[0]
            ckey = f"{round(float(ev_out.latitude), 3):.3f}_{round(float(ev_out.longitude_east), 3):.3f}"
            clusters.setdefault(ckey, []).append(item)

        hits: List[RankedCompositionHit] = []
        for item in processed:
            ev_out, mtype, mexpl, dist_m, bearing = item
            ckey = f"{round(float(ev_out.latitude), 3):.3f}_{round(float(ev_out.longitude_east), 3):.3f}"
            peer_items = clusters[ckey]
            insts = sorted({p[0].instrument_id for p in peer_items})
            rdims = compute_ranking_dimensions(
                ev_out,
                match_type=mtype,
                max_observed_abundance=max_abund,
                corroborating_instruments=insts,
                nearby_count=len(peer_items),
                distance_m=dist_m,
            )
            hits.append(
                RankedCompositionHit(
                    evidence=ev_out,
                    match_type=mtype,
                    match_explanation=mexpl,
                    distance_from_astronaut_m=round(dist_m, 2) if dist_m is not None else None,
                    bearing_deg=round(bearing, 1) if bearing is not None else None,
                    supporting_instruments_nearby=insts,
                    nearby_observation_count=len(peer_items),
                    ranking=rdims,
                )
            )

        # Sort hits deterministically
        if req.sort_by == "distance" and astro_pos is not None:
            hits.sort(key=lambda h: (h.distance_from_astronaut_m if h.distance_from_astronaut_m is not None else 1e12, -h.ranking.composite_rank_score))
        elif req.sort_by == "abundance":
            hits.sort(key=lambda h: -(h.evidence.normalized_value or 0.0))
        elif req.sort_by == "sol":
            hits.sort(key=lambda h: -(h.evidence.sol or -1))
        else:
            hits.sort(
                key=lambda h: (
                    -h.ranking.composite_rank_score,
                    -(h.evidence.normalized_value or 0.0),
                    h.distance_from_astronaut_m if h.distance_from_astronaut_m is not None else 1e12,
                )
            )

        # Build clustered Candidate Discovery Locations (for map markers & destination evaluation)
        cand_locs: List[CandidateDiscoveryLocation] = []
        for ckey, items in clusters.items():
            # Pick best ranked hit in cluster as cluster representative
            cluster_hits = [h for h in hits if f"{round(float(h.evidence.latitude), 3):.3f}_{round(float(h.evidence.longitude_east), 3):.3f}" == ckey]
            cluster_hits.sort(key=lambda h: -h.ranking.composite_rank_score)
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
                    coordinate_source=rep.coordinate_source or "verified",
                    coordinate_uncertainty_m=rep.coordinate_uncertainty_m,
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
        cand_locs.sort(key=lambda c: -c.ranking.composite_rank_score)

        paged_hits = hits[req.offset : req.offset + req.limit]
        return StructuredCompositionSearchResult(
            query=req.query,
            resolution=res,
            index_status=status,
            index_available=True,
            astronaut_position_used=astro_pos,
            total_located_matches=len(hits),
            unlocated_matches_count=unlocated_count,
            returned_count=len(paged_hits),
            limit=req.limit,
            offset=req.offset,
            hits=paged_hits,
            candidate_locations=cand_locs,
            scientific_warnings=warnings,
        )
