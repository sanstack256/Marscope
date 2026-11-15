"""
MARSCOPE Evidence Matching Engine for Science Questions
Prompt 17: Matches verified catalog datasets, composition spatial index hits,
and planetary imagery products to scientific questions while strictly isolating
Jezero Crater / Perseverance from Gale Crater and labeling absent orbital archives.
"""

from __future__ import annotations

import hashlib
from typing import Any, List, Optional

from app.schemas.dataset import Dataset, DatasetLifecycleStatus
from app.science.composition.search import StructuredCompositionQuery
from app.science.investigation.requirements import (
    _classify_dataset_instrument,
    evaluate_question_requirements,
)
from app.science.investigation.schemas import (
    EvidenceMatchRecord,
    EvidenceMatchStrength,
    QuestionEvidenceDiscoveryResponse,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
)


def _match_id(prefix: str, key: str) -> str:
    return f"{prefix}_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def discover_evidence_for_question(
    *,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    composition_search_service: Any,
    composition_index: Any,
    imagery_service: Optional[Any] = None,
) -> QuestionEvidenceDiscoveryResponse:
    """
    Gather all relevant NASA evidence for a scientific question and separate
    verified direct data, orbital/regional context, absent archives, and
    mission-isolated (Jezero/Perseverance) exclusions.
    """
    is_gale = "gale" in question.study_region.lower() or "sharp" in question.study_region.lower()
    matched: List[EvidenceMatchRecord] = []
    rejected: List[EvidenceMatchRecord] = []

    datasets: List[Dataset] = list(catalog_service.list_datasets()) if catalog_service else []
    for ds in datasets:
        inst_cls = _classify_dataset_instrument(ds)
        text = f"{ds.id} {ds.mission} {ds.product_title}".upper()
        if is_gale and (
            inst_cls == "PERSEVERANCE_JEZERO_ISOLATED"
            or "PERSEVERANCE" in text
            or "JEZERO" in text
            or "MARS 2020" in text
        ):
            rejected.append(
                EvidenceMatchRecord(
                    match_id=_match_id("rej", ds.id),
                    source_type="dataset_catalog",
                    source_id=ds.id,
                    instrument_id="PIXL_SHERLOC / SUPERCAM_MASTCAMZ",
                    mission_host=ds.mission,
                    study_region="Jezero Crater (~18.4 N, 77.5 E)",
                    dataset_status=ds.status.value,
                    evidence_strength=EvidenceMatchStrength.MISSION_ISOLATED_REJECTED,
                    spatial_scale_m=ds.horizontal_resolution_meters,
                    rejected_for_gale_reason=(
                        "STRICT MISSION ISOLATION: Jezero Crater / Mars 2020 Perseverance data "
                        "(~3,700 km northeast) is quarantined from Gale Crater science campaigns."
                    ),
                    citation=ds.attribution,
                )
            )
            continue

        if inst_cls in {"USGS_SIM3292_CONTEXT", "MOLA", "CTX", "THEMIS"}:
            matched.append(
                EvidenceMatchRecord(
                    match_id=_match_id("ctx", ds.id),
                    source_type="dataset_catalog",
                    source_id=ds.id,
                    instrument_id=inst_cls,
                    mission_host=ds.mission,
                    study_region=question.study_region,
                    dataset_status=ds.status.value,
                    evidence_strength=EvidenceMatchStrength.CONTEXT_ONLY_SCALE_MISMATCH,
                    spatial_scale_m=ds.horizontal_resolution_meters,
                    scale_mismatch_warning=(
                        f"{ds.product_title} operates at ~{ds.horizontal_resolution_meters or 'regional'} scale; "
                        "usable for regional stratigraphic framing only, NOT meter-scale slope or mineral confirmation."
                    ),
                    citation=ds.attribution,
                )
            )
            continue

        if ds.status == DatasetLifecycleStatus.DISCOVERED or not (
            ds.local_file_path or ds.processed_file_path
        ):
            # Track non-local orbital imagery/catalog discoveries as UNVERIFIED / ABSENT locally
            if "{" in ds.original_product_url:
                matched.append(
                    EvidenceMatchRecord(
                        match_id=_match_id("orb", ds.id),
                        source_type="dataset_catalog",
                        source_id=ds.id,
                        instrument_id=inst_cls,
                        mission_host=ds.mission,
                        study_region=question.study_region,
                        dataset_status=ds.status.value,
                        evidence_strength=EvidenceMatchStrength.UNVERIFIED_OPTICAL_ONLY
                        if inst_cls in {"HIRISE", "CTX"}
                        else EvidenceMatchStrength.ORBITAL_FOOTPRINT_INTERSECTION,
                        spatial_scale_m=ds.horizontal_resolution_meters,
                        prohibited_inference_guard="Optical mosaic layers depict morphology only; never infer mineral identity from visual tone.",
                        citation=ds.attribution,
                    )
                )
            else:
                matched.append(
                    EvidenceMatchRecord(
                        match_id=_match_id("gap", ds.id),
                        source_type="dataset_catalog",
                        source_id=ds.id,
                        instrument_id=inst_cls,
                        mission_host=ds.mission,
                        study_region=question.study_region,
                        dataset_status=ds.status.value,
                        evidence_strength=EvidenceMatchStrength.ABSENT_DATA_GAP,
                        spatial_scale_m=ds.horizontal_resolution_meters,
                        prohibited_inference_guard="Catalog discovery only (DISCOVERED != ACQUIRED/VALIDATED).",
                        citation=ds.attribution,
                    )
                )
            continue

        strength = (
            EvidenceMatchStrength.ORBITAL_FOOTPRINT_INTERSECTION
            if inst_cls in {"HIRISE_DTM", "HIRISE", "CRISM"}
            else EvidenceMatchStrength.DIRECT_LOCAL_IN_SITU
        )
        matched.append(
            EvidenceMatchRecord(
                match_id=_match_id("ds", ds.id),
                source_type="dataset_catalog",
                source_id=ds.id,
                instrument_id=inst_cls,
                mission_host=ds.mission,
                study_region=question.study_region,
                dataset_status=ds.status.value,
                evidence_strength=strength,
                spatial_scale_m=ds.horizontal_resolution_meters,
                prohibited_inference_guard=(
                    "1 m DTM quantifies terrain geometry only; does not establish mineralogy."
                    if inst_cls == "HIRISE_DTM"
                    else None
                ),
                citation=ds.attribution,
            )
        )

    # Query composition spatial index for question phenomena (top phenomena terms)
    comp_status = composition_index.get_status() if composition_index else None
    if composition_search_service and comp_status and getattr(comp_status, "index_available", False):
        queried_terms: List[str] = []
        for term in question.target_phenomena[:6]:
            t_clean = term.strip()
            if not t_clean or t_clean.lower() in queried_terms or t_clean.lower() in {"boxwork", "bedrock", "vein"}:
                continue
            queried_terms.append(t_clean.lower())
            try:
                res = composition_search_service.search(
                    StructuredCompositionQuery(
                        query=t_clean,
                        include_element_bearing_minerals=True,
                        limit=20,
                    )
                )
                if res.total_located_matches > 0:
                    matched.append(
                        EvidenceMatchRecord(
                            match_id=_match_id("comp", f"{question.question_id}|{t_clean}"),
                            source_type="composition_index",
                            source_id=f"comp_query:{t_clean} (gen={comp_status.active_generation_id})",
                            instrument_id=", ".join(
                                sorted({h.evidence.instrument_id for h in res.hits[:10]})
                            )
                            or "APXS / CHEMCAM_LIBS",
                            mission_host="MSL Curiosity",
                            study_region="Gale Crater / Mount Sharp",
                            dataset_status="validated_spatial_index",
                            evidence_strength=EvidenceMatchStrength.DIRECT_LOCAL_IN_SITU,
                            spatial_scale_m=0.02,
                            matched_observables=[
                                f"{t_clean} ({res.total_located_matches} located hits, {res.unlocated_matches_count} unlocated archived)"
                            ],
                            prohibited_inference_guard=(
                                "Elemental/oxide proxies indicate local spot chemistry only; "
                                "absence elsewhere reflects rover traverse limits, and unlocated hits lack verified coordinates."
                            ),
                        )
                    )
                elif res.unlocated_matches_count > 0:
                    matched.append(
                        EvidenceMatchRecord(
                            match_id=_match_id("unloc", f"{question.question_id}|{t_clean}"),
                            source_type="composition_index",
                            source_id=f"comp_unlocated:{t_clean}",
                            instrument_id="MSL Curiosity (CheMin/SAM/unlinked)",
                            mission_host="MSL Curiosity",
                            study_region="Gale Crater / Mount Sharp",
                            dataset_status="unlocated_archive_record_excluded_from_map",
                            evidence_strength=EvidenceMatchStrength.CONTEXT_ONLY_SCALE_MISMATCH,
                            spatial_scale_m=None,
                            matched_observables=[
                                f"{t_clean} ({res.unlocated_matches_count} records lack verified RMC lat/lon coordinates)"
                            ],
                            scale_mismatch_warning="Unlocated mineral/volatile records are NEVER plotted at synthetic map pins.",
                        )
                    )
            except Exception:
                continue

        if getattr(comp_status, "crism_status", "") != "available":
            matched.append(
                EvidenceMatchRecord(
                    match_id=_match_id("gap_crism", question.question_id),
                    source_type="absent_archive_slot",
                    source_id="msl_crism_orbital_mineral_cube",
                    instrument_id="CRISM",
                    mission_host="MRO",
                    study_region=question.study_region,
                    dataset_status=str(getattr(comp_status, "crism_status", "unavailable_no_validated_mineral_cube")),
                    evidence_strength=EvidenceMatchStrength.ABSENT_DATA_GAP,
                    spatial_scale_m=18.0,
                    prohibited_inference_guard=(
                        "NO validated CRISM mineral cube is acquired/indexed locally; "
                        "regional orbital phyllosilicate/sulfate distribution remains an explicit DATA GAP."
                    ),
                )
            )

    if imagery_service is not None:
        for prod in imagery_service.all_products():
            m_u = (prod.mission or "").upper()
            ds_u = (prod.dataset_id or "").upper()
            if is_gale and ("M2020" in m_u or "PERSEVERANCE" in m_u or "JEZERO" in ds_u):
                rejected.append(
                    EvidenceMatchRecord(
                        match_id=_match_id("rej_img", prod.product_id),
                        source_type="imagery_catalog",
                        source_id=prod.product_id,
                        instrument_id=prod.instrument or "Perseverance",
                        mission_host=prod.mission or "Mars 2020",
                        study_region="Jezero Crater",
                        dataset_status="discovered" if not prod.local_file_path else "downloaded",
                        evidence_strength=EvidenceMatchStrength.MISSION_ISOLATED_REJECTED,
                        rejected_for_gale_reason="STRICT MISSION ISOLATION: Jezero imagery excluded from Gale campaigns.",
                    )
                )

    if is_gale:
        from app.science.investigation.measurement_registry import list_instruments

        existing_iso_ids = {r.instrument_id for r in rejected}
        for inst in list_instruments(include_mission_isolated=True):
            if inst.mission_isolated_from_gale and inst.instrument_id not in existing_iso_ids:
                rejected.append(
                    EvidenceMatchRecord(
                        match_id=_match_id("rej_inst", f"{question.question_id}|{inst.instrument_id}"),
                        source_type="instrument_registry_quarantine",
                        source_id=inst.instrument_id,
                        instrument_id=inst.instrument_id,
                        mission_host=inst.mission_host,
                        study_region=inst.study_region_scope,
                        dataset_status="quarantined_wrong_landing_site",
                        evidence_strength=EvidenceMatchStrength.MISSION_ISOLATED_REJECTED,
                        spatial_scale_m=inst.typical_spatial_scale_m,
                        rejected_for_gale_reason=inst.mission_isolation_note
                        or "STRICT MISSION ISOLATION: Mars 2020 Jezero Crater instrument excluded from Gale campaigns.",
                    )
                )

    req_evals = evaluate_question_requirements(
        question=question,
        catalog_service=catalog_service,
        composition_index=composition_index,
        imagery_service=imagery_service,
    )

    critical_gaps: List[str] = []
    for reval in req_evals:
        if reval.fulfillment_state in {
            RequirementFulfillmentState.MISSING_REQUIRED_DATA,
            RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE,
            RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED,
        }:
            critical_gaps.extend(reval.limitations_and_gaps or [f"{reval.label}: {reval.fulfillment_state.value}"])

    essential_reqs = [r for r in req_evals if r.essential]
    if all(r.fulfillment_state == RequirementFulfillmentState.SATISFIED_DIRECT for r in essential_reqs) and essential_reqs:
        readiness = "ALL_ESSENTIAL_MEASUREMENTS_AVAILABLE"
    elif any(r.fulfillment_state == RequirementFulfillmentState.SATISFIED_DIRECT for r in essential_reqs):
        readiness = "PARTIAL_ARCHIVE_WITH_EXPLICIT_MINERAL_OR_ORBITAL_GAPS"
    else:
        readiness = "INSUFFICIENT_LOCAL_ARCHIVE_NEEDS_ACQUISITION"

    return QuestionEvidenceDiscoveryResponse(
        question=question,
        matched_records=matched,
        isolated_or_rejected_records=rejected,
        requirements_evaluation=req_evals,
        overall_evidence_readiness=readiness,
        critical_data_gaps=list(dict.fromkeys(critical_gaps)),
    )
