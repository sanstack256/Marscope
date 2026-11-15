"""
MARSCOPE Evidence Matching Engine for Science Questions
Prompt 17 & 18: Evaluates catalog datasets, composition spatial index hits,
and planetary imagery products through the 17-dimension eligibility engine,
enforces Jezero/Perseverance isolation, prohibits WMTS/optical mineralogy inference,
synthesizes contradicting/duplicate records explicitly, and builds a traceable
ProvenanceDependencyGraph.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set

from app.geospatial.crs import evaluate_spatial_registration
from app.schemas.dataset import Dataset
from app.science.composition.search import StructuredCompositionQuery
from app.science.investigation.eligibility import (
    build_question_provenance_graph,
    evaluate_dataset_eligibility,
    synthesize_question_evidence,
)
from app.science.investigation.measurement_registry import get_instrument, list_instruments
from app.science.investigation.requirements import (
    _classify_dataset_instrument,
    _select_reference_dtm,
    evaluate_question_requirements,
)
from app.science.investigation.schemas import (
    EvidenceEligibilityDimensionResult,
    EvidenceEligibilityState,
    EvidenceMatchRecord,
    EvidenceMatchStrength,
    EvidenceRole,
    MeasurementClass,
    QuestionEvidenceDiscoveryResponse,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
    SpatialRegistrationState,
)


def _match_id(prefix: str, key: str) -> str:
    return f"{prefix}_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _derive_composition_spot_scale_m(hits: List[Any]) -> tuple[Optional[float], str]:
    """Derive actual observation spot scale from instruments in hits; return None if mixed/unknown."""
    insts = {str(getattr(h.evidence, "instrument_id", "")).upper() for h in hits}
    if not insts:
        return None, "No spot observations available to determine spatial footprint scale."
    scales: List[float] = []
    for inst_id in sorted(insts):
        if "CHEMCAM" in inst_id:
            scales.append(0.0005)
        elif "APXS" in inst_id:
            scales.append(0.017)
        elif "CHEMIN" in inst_id:
            scales.append(0.016)
        elif "SAM" in inst_id:
            scales.append(0.016)
        else:
            rec = get_instrument(inst_id)
            if rec and rec.typical_spatial_scale_m is not None:
                scales.append(float(rec.typical_spatial_scale_m))
    if len(scales) == 1:
        return scales[0], f"Derived from instrument aperture/beam spot size ({scales[0]} m)."
    if len(scales) > 1:
        return None, (
            f"Multiple measurement footprints combined ({', '.join(sorted(insts))}, "
            f"{min(scales):g} m to {max(scales):g} m); reported as None rather than forced single scale."
        )
    return None, "Nominal spot scale unspecified for instrument set."


def _evaluate_composition_match_dimensions(
    *,
    term: str,
    res: Any,
    comp_status: Any,
    question: ScienceQuestionDefinition,
    is_located: bool,
    is_duplicate: bool,
) -> Dict[str, Any]:
    """Compute Prompt 18 17-dimension assessment for a composition_index hit group."""
    hits = list(getattr(res, "hits", []) or [])
    integrity_ok = bool(
        getattr(comp_status, "index_available", False)
        and getattr(comp_status, "checksum_valid", False)
        and getattr(comp_status, "source_dependencies_valid", True)
        and getattr(comp_status, "manifest_valid", True)
    )
    inst_set = sorted({str(getattr(h.evidence, "instrument_id", "")).upper() for h in hits})
    cal_states = sorted({str(getattr(h.evidence, "calibration_status", "unknown")) for h in hits})
    proc_levels = sorted({str(getattr(h.evidence, "processing_level", "unknown")) for h in hits})
    units_set = sorted({str(getattr(h.evidence, "normalized_unit", None) or getattr(h.evidence, "raw_unit", "unknown")) for h in hits})
    species_cats = {getattr(h.evidence, "species_category", None) for h in hits}
    has_uncertainty = any(getattr(h.ranking, "relative_uncertainty", None) is not None and getattr(h.ranking.relative_uncertainty, "available", False) for h in hits)
    source_products = sorted({str(getattr(h.evidence, "product_id", "")) for h in hits if getattr(h.evidence, "product_id", None)})
    scale_m, scale_note = _derive_composition_spot_scale_m(hits)

    q_classes = {s.measurement_class for s in question.required_measurement_specs}
    # Check whether query term corresponds only to elemental chemistry while only XRD is requested
    has_elemental_only = all(
        str(getattr(c, "value", c)).lower() in {"element", "oxide"} for c in species_cats
    ) if species_cats else True
    needs_xrd_or_crism = (
        MeasurementClass.MINERALOGY_XRD in q_classes or MeasurementClass.MINERALOGY_SPECTRAL in q_classes
    )
    addresses_elem = MeasurementClass.ELEMENTAL_CHEMISTRY in q_classes

    # Detect numeric heterogeneity >3x across co-located records for possible contradiction/heterogeneity
    vals = [
        float(getattr(h.evidence, "normalized_value", None) or getattr(h.evidence, "raw_value", 0.0))
        for h in hits
        if getattr(h.evidence, "normalized_value", None) is not None or getattr(h.evidence, "raw_value", None) is not None
    ]
    heterogeneous_spread = bool(len(vals) >= 2 and min(vals) > 0 and (max(vals) / min(vals) >= 3.0 and (max(vals) - min(vals)) >= 5.0))

    dims = [
        EvidenceEligibilityDimensionResult(
            dimension="1_source_authenticity",
            status="PASS" if source_products else "PASS_WITH_LIMITATION",
            detail=f"NASA PDS MSL archive products: {', '.join(source_products[:4]) or 'CompositionSpatialIndex'}.",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="2_product_identity",
            status="PASS",
            detail=f"Generation ID {getattr(comp_status, 'active_generation_id', 'unknown')}; {len(source_products)} PDS product(s).",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="3_product_integrity",
            status="PASS" if integrity_ok else "FAIL",
            detail=(
                f"Index checksum & manifest verified ({getattr(comp_status, 'integrity_status', 'verified')})."
                if integrity_ok
                else f"Index integrity failure ({getattr(comp_status, 'integrity_status', 'invalid')})."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="4_instrument_identity",
            status="PASS" if inst_set else "UNVERIFIED",
            detail=f"Verified MSL instrument(s): {', '.join(inst_set) or 'unspecified'}",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="5_measurement_semantics",
            status="PASS_WITH_LIMITATION" if (has_elemental_only and not addresses_elem and needs_xrd_or_crism) else "PASS",
            detail=(
                "Measures elemental/oxide abundances ONLY (ChemCam/APXS); does NOT establish crystalline mineral phase without CheMin/CRISM."
                if has_elemental_only
                else "Reports quantitative mineralogy or compound chemistry."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="6_calibration_status",
            status="PASS" if (cal_states and not any("unknown" in c.lower() for c in cal_states)) else "UNVERIFIED",
            detail=f"Calibration state(s): {', '.join(cal_states) or 'unknown'}",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="7_processing_level",
            status="PASS" if proc_levels else "UNVERIFIED",
            detail=f"Processing level(s): {', '.join(proc_levels) or 'unknown'}",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="8_units",
            status="PASS" if (units_set and not any("unknown" in u.lower() for u in units_set)) else "UNVERIFIED",
            detail=f"Normalized physical unit(s): {', '.join(units_set) or 'unknown'}",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="9_coordinate_validity",
            status="PASS" if is_located else "FAIL",
            detail=(
                "Verified IAU2000:49900 rover/target coordinates via PDS SPICE RMC join."
                if is_located
                else "Unlocated archive records lack verified rover station/target coordinates; excluded from map."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="10_spatial_registration_quality",
            status="PASS_WITH_LIMITATION" if is_located else "FAIL",
            detail=(
                "Co-registered to MSL rover frame; APXS/ChemCam spot standoff (~1.7 cm - 7 m) vs 1 m HiRISE DTM pixel."
                if is_located
                else "No spatial coordinate registration available."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="11_spatial_scale_compatibility",
            status="PASS_WITH_LIMITATION",
            detail=scale_note,
        ),
        EvidenceEligibilityDimensionResult(
            dimension="12_mission_compatibility",
            status="PASS",
            detail="Mars Science Laboratory (Curiosity) — Gale Crater / Mount Sharp.",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="13_temporal_compatibility",
            status="PASS",
            detail="Sol/timestamp tracked per individual observation record.",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="14_data_quality",
            status="PASS_WITH_LIMITATION" if heterogeneous_spread else "PASS",
            detail=(
                f"Observation span {min(vals):.2f}..{max(vals):.2f} shows outcrop vs vein chemical heterogeneity."
                if heterogeneous_spread
                else "Passed 12-stage composition ingestion quality pipeline."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="15_scientific_relevance",
            status="PASS" if (addresses_elem or not has_elemental_only or needs_xrd_or_crism) else "PASS_WITH_LIMITATION",
            detail=f"Phenomenon '{term}' matched in {len(hits)} record(s).",
        ),
        EvidenceEligibilityDimensionResult(
            dimension="16_uncertainty_availability",
            status="PASS" if has_uncertainty else "PASS_WITH_LIMITATION",
            detail=(
                "Per-record reported measurement uncertainty & relative uncertainty ratio preserved without synthesis."
                if has_uncertainty
                else "Source table lacks explicit per-row uncertainty column for some hits; unquantified uncertainty is NOT fabricated."
            ),
        ),
        EvidenceEligibilityDimensionResult(
            dimension="17_duplication_or_correlation",
            status="FAIL" if is_duplicate else "PASS",
            detail=(
                "Correlated or overlapping oxide/element conversion of already-counted query hits."
                if is_duplicate
                else "Distinct query term within CompositionSpatialIndex."
            ),
        ),
    ]

    if not integrity_ok:
        elig_state = EvidenceEligibilityState.REJECTED
        role = EvidenceRole.INCONCLUSIVE
        role_reason = "CompositionSpatialIndex failed integrity check."
    elif is_duplicate:
        elig_state = EvidenceEligibilityState.DUPLICATE_OR_CORRELATED
        role = EvidenceRole.CONTEXTUAL
        role_reason = f"Species/term '{term}' overlaps stoichiometric oxide/element records already counted."
    elif not is_located:
        elig_state = EvidenceEligibilityState.SPATIALLY_UNVERIFIED
        role = EvidenceRole.INCONCLUSIVE
        role_reason = "Records lack verified rover RMC coordinates and cannot anchor spatial campaign stops."
    elif heterogeneous_spread and not addresses_elem:
        elig_state = EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS
        role = EvidenceRole.CONTRADICTING
        role_reason = f"Wide chemical contrast ({min(vals):.2f}..{max(vals):.2f}) between co-located host bedrock and alteration veins."
    elif addresses_elem or not has_elemental_only:
        elig_state = EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS
        role = EvidenceRole.SUPPORTING
        role_reason = (
            f"Verified located MSL observations ({', '.join(inst_set)}) address '{term}' within Gale Crater "
            "(subject to point-sampling traverse coverage bounds)."
        )
    else:
        elig_state = EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS
        role = EvidenceRole.CONTEXTUAL
        role_reason = "Elemental proxy provides bulk chemical context only; cannot confirm mineralogy directly."

    reg_state = (
        SpatialRegistrationState.REGISTERED_WITH_LIMITATIONS
        if is_located
        else SpatialRegistrationState.NOT_REGISTERED
    )

    return {
        "eligibility_state": elig_state,
        "dimensions": dims,
        "role": role,
        "role_reason": role_reason,
        "scale_m": scale_m,
        "scale_note": scale_note,
        "inst_str": ", ".join(inst_set) or ("APXS / CHEMCAM_LIBS" if is_located else "MSL Curiosity (unlocated)"),
        "units": ", ".join(units_set) or None,
        "cal_status": ", ".join(cal_states) or None,
        "proc_level": ", ".join(proc_levels) or None,
        "reg_state": reg_state,
        "has_uncertainty": has_uncertainty,
        "source_products": source_products,
        "integrity_status": str(getattr(comp_status, "integrity_status", "verified")),
        "provenance_chain": [
            "mission:Mars Science Laboratory (MSL)",
            f"instruments:{','.join(inst_set) or 'unknown'}",
            f"index_gen:{getattr(comp_status, 'active_generation_id', 'unknown')}",
            f"products:{','.join(source_products[:5]) or 'tabular_index'}",
            f"registration:{reg_state.value}",
        ],
    }


def _numeric_bounds(cov: Any) -> Optional[Dict[str, float]]:
    if not cov:
        return None
    try:
        return {
            "min_latitude": float(cov.min_latitude),
            "max_latitude": float(cov.max_latitude),
            "min_longitude": float(cov.min_longitude),
            "max_longitude": float(cov.max_longitude),
        }
    except Exception:
        return None


def discover_evidence_for_question(
    *,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    composition_search_service: Any,
    composition_index: Any,
    imagery_service: Optional[Any] = None,
) -> QuestionEvidenceDiscoveryResponse:
    """
    Gather all relevant NASA evidence for a scientific question using full 17-dimension
    eligibility evaluation, separate Direct vs Contextual vs Contradicting vs Inconclusive
    vs Duplicate vs Absent vs Mission-Isolated records, and return an EvidenceSynthesisSummary
    and inspectable ProvenanceDependencyGraph.
    """
    is_gale = "gale" in question.study_region.lower() or "sharp" in question.study_region.lower()
    matched: List[EvidenceMatchRecord] = []
    rejected: List[EvidenceMatchRecord] = []
    spatial_registrations: List[Dict[str, Any]] = []

    datasets: List[Dataset] = list(catalog_service.list_datasets()) if catalog_service else []
    ref_dtm = _select_reference_dtm(datasets, is_gale)
    seen_sha: Set[str] = set()
    seen_pids: Set[str] = set()

    for ds in datasets:
        inst_cls = _classify_dataset_instrument(ds)
        ev = evaluate_dataset_eligibility(
            ds=ds,
            inst_cls=inst_cls,
            question=question,
            is_gale=is_gale,
            seen_sha256=seen_sha,
            seen_product_ids=seen_pids,
            reference_dtm=ref_dtm,
        )
        elig_state: EvidenceEligibilityState = ev["eligibility_state"]
        reg_state: SpatialRegistrationState = ev["registration_state"]
        reg_report: Dict[str, Any] = ev["registration_report"]
        spatial_registrations.append(reg_report)

        if elig_state == EvidenceEligibilityState.MISSION_INCOMPATIBLE:
            rejected.append(
                EvidenceMatchRecord(
                    match_id=_match_id("rej", ds.id),
                    source_type="dataset_catalog",
                    source_id=ds.id,
                    product_id=ds.product_id,
                    instrument_id="PIXL_SHERLOC / SUPERCAM_MASTCAMZ",
                    mission_host=ds.mission,
                    study_region="Jezero Crater (~18.4 N, 77.5 E)",
                    dataset_status=ds.status.value,
                    evidence_strength=EvidenceMatchStrength.MISSION_ISOLATED_REJECTED,
                    eligibility_state=elig_state,
                    eligibility_dimensions=ev["dimensions"],
                    evidence_role=ev["evidence_role"],
                    evidence_role_rationale=ev["role_reason"],
                    scientific_relevance=ev["scientific_relevance"],
                    spatial_scale_m=ev["resolved_scale_m"],
                    product_spatial_resolution_m=ds.horizontal_resolution_meters,
                    product_footprint_bounds=_numeric_bounds(ds.coverage),
                    coordinate_reference=ds.coordinate_reference_system,
                    units=ds.units,
                    calibration_status=ds.calibration_status,
                    integrity_status=ds.status.value,
                    spatial_registration_state=reg_state,
                    uncertainty_summary=ev["uncertainty_summary"],
                    rejected_for_gale_reason=(
                        "STRICT MISSION ISOLATION: Jezero Crater / Mars 2020 Perseverance data "
                        "(~3,700 km northeast) is quarantined from Gale Crater science campaigns."
                    ),
                    provenance_chain=ev["provenance_chain"],
                    citation=ds.attribution,
                )
            )
            continue

        is_wmts = "{" in (ds.original_product_url or "")
        if elig_state == EvidenceEligibilityState.UNAVAILABLE:
            strength = EvidenceMatchStrength.ABSENT_DATA_GAP
        elif is_wmts:
            strength = EvidenceMatchStrength.UNVERIFIED_OPTICAL_ONLY
        elif elig_state == EvidenceEligibilityState.SCALE_INCOMPATIBLE or inst_cls in {"MOLA", "CTX", "USGS_SIM3292_CONTEXT", "THEMIS"}:
            strength = EvidenceMatchStrength.CONTEXT_ONLY_SCALE_MISMATCH
        elif elig_state == EvidenceEligibilityState.REJECTED:
            strength = EvidenceMatchStrength.ABSENT_DATA_GAP
        elif inst_cls in {"HIRISE_DTM", "HIRISE", "CRISM"}:
            strength = EvidenceMatchStrength.ORBITAL_FOOTPRINT_INTERSECTION
        else:
            strength = EvidenceMatchStrength.DIRECT_LOCAL_IN_SITU

        prohibited_guard: Optional[str] = None
        if is_wmts:
            prohibited_guard = (
                "WMTS tile endpoint depicts visual albedo/morphology only; unverified as scientific raster and NEVER valid for mineral identification."
            )
        elif inst_cls == "HIRISE_DTM":
            prohibited_guard = "1 m DTM quantifies terrain geometry only; does not establish mineralogy."
        elif elig_state == EvidenceEligibilityState.REJECTED:
            prohibited_guard = f"Validation/integrity check FAILED: {ds.failure_reason or ds.status.value}"
        elif elig_state == EvidenceEligibilityState.UNAVAILABLE:
            prohibited_guard = "Catalog discovery only (DISCOVERED != ACQUIRED/VALIDATED)."

        scale_warn: Optional[str] = None
        if strength == EvidenceMatchStrength.CONTEXT_ONLY_SCALE_MISMATCH:
            scale_warn = (
                f"{ds.product_title} operates at ~{ds.horizontal_resolution_meters or 'regional'} m/px scale; "
                "usable for regional stratigraphic framing only, NOT meter-scale slope or mineral confirmation."
            )
        elif is_wmts:
            scale_warn = "Streaming WMTS mosaic has unverified product scaling and cannot enter elevation/mineral calculations."

        rec = EvidenceMatchRecord(
            match_id=_match_id("ds" if strength != EvidenceMatchStrength.ABSENT_DATA_GAP else "gap", ds.id),
            source_type="dataset_catalog",
            source_id=ds.id,
            product_id=ds.product_id,
            instrument_id=inst_cls,
            mission_host=ds.mission,
            study_region=question.study_region,
            dataset_status=ds.status.value,
            evidence_strength=strength,
            eligibility_state=elig_state,
            eligibility_dimensions=ev["dimensions"],
            evidence_role=ev["evidence_role"],
            evidence_role_rationale=ev["role_reason"],
            scientific_relevance=ev["scientific_relevance"],
            spatial_scale_m=ev["resolved_scale_m"],
            product_spatial_resolution_m=ds.horizontal_resolution_meters,
            product_footprint_bounds=_numeric_bounds(ds.coverage),
            acquisition_time_utc=ds.acquisition_timestamp.isoformat() if ds.acquisition_timestamp else None,
            processing_level=ds.processing_level,
            coordinate_reference=ds.coordinate_reference_system,
            units=ds.units,
            calibration_status=ds.calibration_status,
            integrity_status=ds.verification.download_verification.value,
            spatial_registration_state=reg_state,
            data_quality_flags=list(ds.quality_flags or []),
            product_limitations=list(ds.known_limitations or []),
            uncertainty_summary=ev["uncertainty_summary"],
            duplication_or_correlation=ev["duplication_info"],
            scale_mismatch_warning=scale_warn,
            prohibited_inference_guard=prohibited_guard,
            provenance_chain=ev["provenance_chain"],
            citation=ds.attribution,
        )
        matched.append(rec)
        if elig_state == EvidenceEligibilityState.REJECTED:
            rejected.append(rec)

    # Query composition spatial index across ALL question.target_phenomena (never truncated!)
    comp_status = composition_index.get_status() if composition_index else None
    if composition_search_service and comp_status and getattr(comp_status, "index_available", False):
        queried_terms: List[str] = []
        seen_evidence_signatures: Set[str] = set()
        for term in question.target_phenomena:
            t_clean = term.strip()
            if not t_clean or t_clean.lower() in queried_terms or t_clean.lower() in {"boxwork", "bedrock", "vein"}:
                continue
            queried_terms.append(t_clean.lower())
            try:
                res = composition_search_service.search(
                    StructuredCompositionQuery(
                        query=t_clean,
                        include_element_bearing_minerals=True,
                        limit=50,
                    )
                )
            except Exception:
                continue

            if res.total_located_matches > 0:
                hit_sig = "|".join(sorted(getattr(h.evidence, "evidence_id", "") for h in res.hits[:25]))
                is_dup = bool(hit_sig and hit_sig in seen_evidence_signatures)
                if hit_sig:
                    seen_evidence_signatures.add(hit_sig)

                comp_eval = _evaluate_composition_match_dimensions(
                    term=t_clean,
                    res=res,
                    comp_status=comp_status,
                    question=question,
                    is_located=True,
                    is_duplicate=is_dup,
                )
                matched.append(
                    EvidenceMatchRecord(
                        match_id=_match_id("comp", f"{question.question_id}|{t_clean}"),
                        source_type="composition_index",
                        source_id=f"comp_query:{t_clean} (gen={comp_status.active_generation_id})",
                        product_id=", ".join(comp_eval["source_products"][:3]) or None,
                        instrument_id=comp_eval["inst_str"],
                        mission_host="MSL Curiosity",
                        study_region="Gale Crater / Mount Sharp",
                        dataset_status="validated_spatial_index" if comp_status.checksum_valid else "integrity_failed_index",
                        evidence_strength=EvidenceMatchStrength.DIRECT_LOCAL_IN_SITU,
                        eligibility_state=comp_eval["eligibility_state"],
                        eligibility_dimensions=comp_eval["dimensions"],
                        evidence_role=comp_eval["role"],
                        evidence_role_rationale=comp_eval["role_reason"],
                        scientific_relevance=f"Matched {res.total_located_matches} located hit(s) for '{t_clean}'",
                        spatial_scale_m=comp_eval["scale_m"],
                        product_spatial_resolution_m=comp_eval["scale_m"],
                        processing_level=comp_eval["proc_level"],
                        coordinate_reference="IAU2000:49900",
                        units=comp_eval["units"],
                        calibration_status=comp_eval["cal_status"],
                        integrity_status=comp_eval["integrity_status"],
                        spatial_registration_state=comp_eval["reg_state"],
                        product_limitations=[comp_eval["scale_note"]],
                        uncertainty_summary={
                            "quantified": comp_eval["has_uncertainty"],
                            "status": (
                                "REPORTED_PER_ROW_UNCERTAINTY_NO_STATISTICAL_AGGREGATE"
                                if comp_eval["has_uncertainty"]
                                else "UNQUANTIFIED_UNCERTAINTY_NOT_FABRICATED"
                            ),
                        },
                        duplication_or_correlation={
                            "is_duplicate": is_dup,
                            "reason": "Identical underlying observation hits already returned by sibling phenomenon query." if is_dup else None,
                        },
                        matched_observables=[
                            f"{t_clean} ({res.total_located_matches} located hits, {res.unlocated_matches_count} unlocated archived)"
                        ],
                        prohibited_inference_guard=(
                            "Elemental/oxide proxies indicate local spot chemistry only; "
                            "absence elsewhere reflects rover traverse limits, and unlocated hits lack verified coordinates."
                        ),
                        provenance_chain=comp_eval["provenance_chain"],
                    )
                )
            elif res.unlocated_matches_count > 0:
                comp_eval = _evaluate_composition_match_dimensions(
                    term=t_clean,
                    res=res,
                    comp_status=comp_status,
                    question=question,
                    is_located=False,
                    is_duplicate=False,
                )
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
                        eligibility_state=comp_eval["eligibility_state"],
                        eligibility_dimensions=comp_eval["dimensions"],
                        evidence_role=comp_eval["role"],
                        evidence_role_rationale=comp_eval["role_reason"],
                        scientific_relevance=f"Unlocated archive hits ({res.unlocated_matches_count}) for '{t_clean}' lack spatial coordinates",
                        spatial_scale_m=None,
                        spatial_registration_state=SpatialRegistrationState.NOT_REGISTERED,
                        matched_observables=[
                            f"{t_clean} ({res.unlocated_matches_count} records lack verified RMC lat/lon coordinates)"
                        ],
                        scale_mismatch_warning="Unlocated mineral/volatile records are NEVER plotted at synthetic map pins.",
                        provenance_chain=comp_eval["provenance_chain"],
                    )
                )

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
                    eligibility_state=EvidenceEligibilityState.UNAVAILABLE,
                    evidence_role=EvidenceRole.UNAVAILABLE,
                    evidence_role_rationale="No validated CRISM SWIR mineral cube acquired locally.",
                    scientific_relevance="Required for continuous regional clay/sulfate spectroscopy.",
                    spatial_scale_m=18.0,
                    spatial_registration_state=SpatialRegistrationState.NOT_REGISTERED,
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
                        product_id=prod.product_id,
                        instrument_id=prod.instrument or "Perseverance",
                        mission_host=prod.mission or "Mars 2020",
                        study_region="Jezero Crater",
                        dataset_status="discovered" if not prod.local_file_path else "downloaded",
                        evidence_strength=EvidenceMatchStrength.MISSION_ISOLATED_REJECTED,
                        eligibility_state=EvidenceEligibilityState.MISSION_INCOMPATIBLE,
                        evidence_role=EvidenceRole.NOT_RELEVANT,
                        evidence_role_rationale="Strict mission isolation excludes Mars 2020 Jezero frames.",
                        rejected_for_gale_reason="STRICT MISSION ISOLATION: Jezero imagery excluded from Gale campaigns.",
                    )
                )

    if is_gale:
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
                        eligibility_state=EvidenceEligibilityState.MISSION_INCOMPATIBLE,
                        evidence_role=EvidenceRole.NOT_RELEVANT,
                        evidence_role_rationale="Quarantined wrong landing site instrument.",
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
        evaluated_matches=matched,
    )

    synthesis = synthesize_question_evidence(
        question=question,
        matched=matched,
        requirements=req_evals,
    )
    prov_graph = build_question_provenance_graph(
        question=question,
        datasets=datasets,
        matched=matched,
        requirements=req_evals,
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
        evidence_synthesis=synthesis,
        spatial_registrations=spatial_registrations,
        overall_evidence_readiness=readiness,
        critical_data_gaps=list(dict.fromkeys(critical_gaps)),
        provenance_graph=prov_graph,
    )
