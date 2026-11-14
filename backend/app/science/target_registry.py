"""
MARSCOPE Evidence-Backed Scientific Target Registry
Martian Surface Intelligence & Exploration System

Supports:
  1. Reproducible generation of investigation targets directly from verified composition
     discovery search results and candidate locations.
  2. Explicit labeling of manually entered targets without backing CompositionEvidence
     as `manual_unverified_administrative`.
"""

import hashlib
from typing import Dict, List, Optional
from app.schemas.target import (
    ScienceTarget,
    TargetGenerationRequest,
    TargetProvenanceStatus,
)
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.search import (
    CompositionSearchService,
    StructuredCompositionQuery,
)


class TargetRegistryService:
    def __init__(self, composition_index: Optional[CompositionSpatialIndex] = None):
        self._targets: Dict[str, ScienceTarget] = {}
        self.composition_index = composition_index

    def register_target(self, target: ScienceTarget) -> ScienceTarget:
        """
        Register a scientific target. If backed by verified CompositionEvidence IDs present
        in the active spatial index, marks it EVIDENCE_BACKED; otherwise explicitly marks it
        MANUAL_UNVERIFIED_ADMINISTRATIVE so manual pins never masquerade as verified evidence.
        """
        verified_ids: List[str] = []
        if target.evidence_ids and self.composition_index is not None:
            for eid in target.evidence_ids:
                ev = self.composition_index.get_evidence_by_id(eid)
                if ev is not None and ev.location_verified:
                    verified_ids.append(eid)

        if verified_ids and len(verified_ids) == len(target.evidence_ids):
            resolved_status = TargetProvenanceStatus.EVIDENCE_BACKED
            explanation = target.explanation or (
                f"Backed by {len(verified_ids)} verified composition evidence record(s) in active SQLite index."
            )
        else:
            resolved_status = TargetProvenanceStatus.MANUAL_UNVERIFIED_ADMINISTRATIVE
            explanation = (
                target.explanation
                or "Manually registered administrative coordinate; not verified by indexed NASA PDS composition evidence."
            )

        clean_target = target.model_copy(
            update={
                "target_status": resolved_status,
                "explanation": explanation,
            }
        )
        self._targets[clean_target.id] = clean_target
        return clean_target

    def generate_targets_from_discovery(
        self,
        req: TargetGenerationRequest,
        search_service: CompositionSearchService,
    ) -> List[ScienceTarget]:
        """
        Generate reproducible, evidence-backed ScienceTargets directly from ranked
        composition candidate locations. Never fabricates targets when evidence is absent.
        """
        search_res = search_service.search(
            StructuredCompositionQuery(
                query=req.query,
                include_element_bearing_minerals=req.include_element_bearing_minerals,
                astronaut_latitude=req.astronaut_latitude,
                astronaut_longitude=req.astronaut_longitude,
                max_distance_m=req.max_distance_m,
                limit=max(50, req.max_targets * 5),
            )
        )
        if not search_res.index_available or not search_res.candidate_locations:
            return []

        created: List[ScienceTarget] = []
        spec_label = (
            search_res.resolution.species.canonical_id
            if search_res.resolution.species
            else req.query.strip()
        )
        for cand in search_res.candidate_locations[: req.max_targets]:
            tid_seed = f"{spec_label}|{cand.candidate_id}"
            tid = "tgt_" + hashlib.sha256(tid_seed.encode("utf-8")).hexdigest()[:12]
            inst_str = ", ".join(cand.distinct_instruments)
            geol = f"{spec_label} ({cand.best_evidence_type.value})"
            tgt = ScienceTarget(
                id=tid,
                name=f"{cand.cluster_label} [{spec_label}]",
                latitude=cand.latitude,
                longitude=cand.longitude_east,
                elevation_m=cand.elevation_m,
                crs=cand.crs,
                geology_type=geol,
                scientific_value=min(1.0, max(0.0, cand.ranking.composite_rank_score or 0.0)),
                instrument_source=inst_str,
                provenance_product_id=f"CAND:{cand.candidate_id}",
                target_status=TargetProvenanceStatus.EVIDENCE_BACKED,
                evidence_ids=cand.evidence_ids,
                matched_species=spec_label,
                distance_from_astronaut_m=cand.distance_from_astronaut_m,
                explanation=cand.ranking.rationale,
            )
            self._targets[tid] = tgt
            created.append(tgt)

        return created

    def list_targets(
        self,
        classification: Optional[str] = None,
        status_filter: Optional[TargetProvenanceStatus] = None,
    ) -> List[ScienceTarget]:
        items = list(self._targets.values())
        if classification:
            items = [t for t in items if classification.lower() in t.geology_type.lower()]
        if status_filter is not None:
            items = [t for t in items if t.target_status == status_filter]
        return items

    def get_target(self, target_id: str) -> Optional[ScienceTarget]:
        return self._targets.get(target_id)

    def clear_targets(self) -> None:
        self._targets.clear()
