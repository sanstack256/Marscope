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
from typing import Any, Dict, List, Optional
from app.schemas.target import (
    InvestigationTargetEvidenceState,
    ScienceTarget,
    TargetGenerationRequest,
    TargetProvenanceStatus,
)
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.search import (
    CompositionSearchService,
    StructuredCompositionQuery,
)


_IN_SITU_INSTRUMENTS = {"CHEMCAM", "APXS", "CHEMIN", "SAM", "DAN", "MASTCAM", "MAHLI", "MARDI"}
_ORBITAL_SPECTRAL_INSTRUMENTS = {"CRISM", "THEMIS", "OMEGA"}


def _classify_evidence_state_from_records(records: List[Any], fallback_source: str = "") -> InvestigationTargetEvidenceState:
    """Derive 7-state InvestigationTargetEvidenceState honestly without upgrading proxies or orbital detections."""
    if not records:
        low = fallback_source.lower()
        if "optical" in low or "hirise" in low or "ctx" in low or "morpholog" in low:
            return InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED
        if "manual" in low:
            return InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED
        return InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED

    ev_types = {
        getattr(getattr(r, "evidence_type", None), "value", str(getattr(r, "evidence_type", ""))).lower()
        for r in records
    }
    instruments = {
        str(getattr(r, "instrument_id", None) or getattr(r, "instrument", "")).upper()
        for r in records
    }
    if any(
        t in {
            "direct_mineral_detection",
            "direct_element_measurement",
            "oxide_composition_measurement",
            "elemental_proxy_detection",
            "confirmed_local_observation",
        }
        for t in ev_types
    ):
        if instruments & _IN_SITU_INSTRUMENTS:
            return InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION
        if instruments & _ORBITAL_SPECTRAL_INSTRUMENTS:
            return InvestigationTargetEvidenceState.ORBITAL_DETECTION_ONLY
        return InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION
    if "co_located_context_only" in ev_types or "regional" in fallback_source.lower():
        return InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY
    return InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED


class TargetRegistryService:
    def __init__(self, composition_index: Optional[CompositionSpatialIndex] = None):
        self._targets: Dict[str, ScienceTarget] = {}
        self.composition_index = composition_index

    def register_target(self, target: ScienceTarget) -> ScienceTarget:
        """
        Register a scientific target. If backed by verified CompositionEvidence IDs present
        in the active spatial index, marks it EVIDENCE_BACKED with exact InvestigationTargetEvidenceState;
        otherwise explicitly marks it MANUAL_UNVERIFIED_ADMINISTRATIVE / MANUAL_WAYPOINT_UNVERIFIED.
        """
        verified_records: List[Any] = []
        if target.evidence_ids and self.composition_index is not None:
            for eid in target.evidence_ids:
                ev = self.composition_index.get_evidence_by_id(eid)
                if ev is not None and ev.location_verified:
                    verified_records.append(ev)

        if verified_records and len(verified_records) == len(target.evidence_ids):
            resolved_status = TargetProvenanceStatus.EVIDENCE_BACKED
            evidence_state = _classify_evidence_state_from_records(
                verified_records, fallback_source=target.instrument_source
            )
            explanation = target.explanation or (
                f"Backed by {len(verified_records)} verified composition evidence record(s) in active SQLite index ({evidence_state.value})."
            )
        else:
            resolved_status = TargetProvenanceStatus.MANUAL_UNVERIFIED_ADMINISTRATIVE
            evidence_state = (
                target.evidence_state
                if target.evidence_state in {
                    InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED,
                    InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED,
                    InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED,
                }
                else InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED
            )
            explanation = (
                target.explanation
                or "Manually registered administrative coordinate; not verified by indexed NASA PDS composition evidence."
            )

        priority_val: Optional[float] = (
            float(target.exploration_priority_score)
            if target.exploration_priority_score is not None
            else None
        )
        breakdown = dict(target.prioritization_breakdown or {})
        if not breakdown:
            breakdown = {
                "is_heuristic": True,
                "classification": "engineering_exploration_priority_heuristic",
                "evidence_state": evidence_state.value,
                "verified_evidence_count": len(verified_records),
                "configured_or_derived_priority": round(priority_val, 4) if priority_val is not None else None,
                "status": "COMPUTED" if priority_val is not None else "UNAVAILABLE",
            }

        evidence_summary = dict(target.scientific_evidence_summary or {})
        if not evidence_summary:
            evidence_summary = {
                "instrument_source": target.instrument_source,
                "geology_type": target.geology_type,
                "matched_species": target.matched_species,
                "evidence_ids": list(verified_ids if resolved_status == TargetProvenanceStatus.EVIDENCE_BACKED else target.evidence_ids),
                "verified_evidence_count": len(verified_records),
                "preserves_original_measurement_semantics": True,
            }

        clean_target = target.model_copy(
            update={
                "target_status": resolved_status,
                "evidence_state": evidence_state,
                "exploration_priority_score": priority_val,
                "scientific_evidence_summary": evidence_summary,
                "scientific_confidence_state": "QUALITATIVE_ONLY_NOT_STATISTICALLY_QUANTIFIED",
                "scientific_confidence_score": None,
                "prioritization_is_heuristic": True,
                "prioritization_breakdown": breakdown,
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

            inst_upper = {i.upper() for i in cand.distinct_instruments}
            ev_val = cand.best_evidence_type.value.lower()
            if "co_located_context" in ev_val:
                ev_state = InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY
            elif inst_upper & _IN_SITU_INSTRUMENTS:
                ev_state = InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION
            elif inst_upper & _ORBITAL_SPECTRAL_INSTRUMENTS:
                ev_state = InvestigationTargetEvidenceState.ORBITAL_DETECTION_ONLY
            else:
                ev_state = InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY

            raw_rank = getattr(cand.ranking, "composite_rank_score", None)
            priority_score: Optional[float] = (
                min(1.0, max(0.0, float(raw_rank))) if raw_rank is not None else None
            )
            breakdown = {
                "is_heuristic": True,
                "classification": "engineering_exploration_priority_heuristic",
                "evidence_state": ev_state.value,
                "measurement_directness_score": round(float(cand.ranking.directness_score), 4)
                if hasattr(cand.ranking, "directness_score") and cand.ranking.directness_score is not None
                else (round(priority_score, 4) if priority_score is not None else None),
                "evidence_support_count": len(cand.evidence_ids),
                "distinct_instruments": list(cand.distinct_instruments),
                "distance_from_astronaut_m": cand.distance_from_astronaut_m,
                "composite_priority_score": round(priority_score, 4) if priority_score is not None else None,
            }

            tgt = ScienceTarget(
                id=tid,
                name=f"{cand.cluster_label} [{spec_label}]",
                latitude=cand.latitude,
                longitude=cand.longitude_east,
                elevation_m=cand.elevation_m,
                crs=cand.crs,
                geology_type=geol,
                scientific_value=None,
                exploration_priority_score=priority_score,
                scientific_evidence_summary={
                    "matched_species": spec_label,
                    "best_evidence_type": cand.best_evidence_type.value,
                    "distinct_instruments": list(cand.distinct_instruments),
                    "evidence_ids": list(cand.evidence_ids),
                    "preserves_original_measurement_semantics": True,
                },
                scientific_confidence_state="QUALITATIVE_ONLY_NOT_STATISTICALLY_QUANTIFIED",
                scientific_confidence_score=None,
                prioritization_is_heuristic=True,
                prioritization_breakdown=breakdown,
                instrument_source=inst_str,
                provenance_product_id=f"CAND:{cand.candidate_id}",
                target_status=TargetProvenanceStatus.EVIDENCE_BACKED,
                evidence_state=ev_state,
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
        evidence_state_filter: Optional[InvestigationTargetEvidenceState] = None,
    ) -> List[ScienceTarget]:
        items = list(self._targets.values())
        if classification:
            items = [t for t in items if classification.lower() in t.geology_type.lower()]
        if status_filter is not None:
            items = [t for t in items if t.target_status == status_filter]
        if evidence_state_filter is not None:
            items = [t for t in items if t.evidence_state == evidence_state_filter]
        return items

    def get_target(self, target_id: str) -> Optional[ScienceTarget]:
        return self._targets.get(target_id)

    def clear_targets(self) -> None:
        self._targets.clear()
