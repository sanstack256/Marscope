"""
MARSCOPE Measurement Requirement Mapping & Gap Assessment
Prompt 17 & 18: Evaluates a ScienceQuestionDefinition against live catalog datasets,
verified composition spatial index status, and imagery archive holdings using the
17-dimension eligibility framework without fabricating mineral cubes, accepting WMTS
tile endpoints as local scientific data, or accepting unverified/failed products.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.science.investigation.eligibility import evaluate_dataset_eligibility
from app.science.investigation.measurement_registry import get_instrument
from app.science.investigation.schemas import (
    CanonicalRequirementState,
    EvidenceEligibilityState,
    EvidenceMatchRecord,
    MeasurementClass,
    RegistryVerificationStatus,
    RequirementEvaluationRecord,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
)


def _classify_dataset_instrument(ds: Dataset) -> str:
    text = f"{ds.id} {ds.instrument} {ds.product_title}".upper()
    if "PERSEVERANCE" in ds.mission.upper() or "JEZERO" in text or "MARS 2020" in ds.mission.upper():
        return "PERSEVERANCE_JEZERO_ISOLATED"
    if "HIRISE" in text and ("DTEEC" in text or ds.product_type == "DTM" or "ELEVATION" in text or "DEM" in ds.product_type.upper()):
        return "HIRISE_DTM"
    if "HIRISE" in text:
        return "HIRISE"
    if "MOLA" in text:
        return "MOLA"
    if "CRISM" in text:
        return "CRISM"
    if "THEMIS" in text:
        return "THEMIS"
    if "CTX" in text:
        return "CTX"
    if "CHEMCAM" in text:
        return "CHEMCAM_LIBS"
    if "APXS" in text:
        return "APXS"
    if "CHEMIN" in text:
        return "CHEMIN_XRD"
    if "SAM" in text:
        return "SAM_EGA_GCMS"
    if "REMS" in text:
        return "REMS"
    if "MASTCAM" in text:
        return "MASTCAM"
    if "MAHLI" in text:
        return "MAHLI"
    if "SIM3292" in text or "USGS" in text:
        return "USGS_SIM3292_CONTEXT"
    if "WAYPOINT" in text:
        return "WAYPOINTS"
    return ds.instrument.upper()


def _select_reference_dtm(datasets: List[Dataset], is_gale: bool) -> Optional[Dataset]:
    for ds in datasets:
        inst = _classify_dataset_instrument(ds)
        if inst == "HIRISE_DTM" and (ds.local_file_path or ds.processed_file_path) and not ds.failure_reason:
            if is_gale and "jezero" in ds.id.lower():
                continue
            return ds
    return None


def _map_canonical_state(
    *,
    fulfillment: RequirementFulfillmentState,
    has_unverified_candidates: bool,
    has_unavailable_candidates: bool,
    has_failed_candidates: bool,
    missing_info: List[str],
) -> CanonicalRequirementState:
    if fulfillment == RequirementFulfillmentState.SATISFIED_DIRECT:
        return (
            CanonicalRequirementState.PARTIALLY_SATISFIED
            if missing_info
            else CanonicalRequirementState.SATISFIED
        )
    if fulfillment == RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED:
        return CanonicalRequirementState.PARTIALLY_SATISFIED
    if fulfillment == RequirementFulfillmentState.SATISFIED_PROXY_ONLY:
        return CanonicalRequirementState.PARTIALLY_SATISFIED
    if fulfillment == RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE:
        return CanonicalRequirementState.BLOCKED_BY_DATA_GAP
    if fulfillment == RequirementFulfillmentState.CONFLICT_REQUIRES_RESOLUTION:
        return CanonicalRequirementState.UNVERIFIED
    # Missing / unsatisfied branch
    if has_failed_candidates:
        return CanonicalRequirementState.UNSATISFIED
    if has_unverified_candidates:
        return CanonicalRequirementState.UNVERIFIED
    if has_unavailable_candidates:
        return CanonicalRequirementState.UNAVAILABLE
    return CanonicalRequirementState.BLOCKED_BY_DATA_GAP


def evaluate_question_requirements(
    *,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    composition_index: Any,
    imagery_service: Optional[Any] = None,
    evaluated_matches: Optional[List[EvidenceMatchRecord]] = None,
) -> List[RequirementEvaluationRecord]:
    """
    Evaluate every measurement requirement for a scientific question honestly against
    17-dimension eligibility results, composition index integrity, and imagery holdings.
    """
    datasets: List[Dataset] = list(catalog_service.list_datasets()) if catalog_service else []
    comp_status = composition_index.get_status() if composition_index else None
    imagery_products = list(imagery_service.all_products()) if imagery_service else []

    is_gale_question = "gale" in question.study_region.lower() or "sharp" in question.study_region.lower()
    crism_status_raw = str(getattr(comp_status, "crism_status", "unavailable") or "unavailable")
    crism_available = bool(
        comp_status
        and getattr(comp_status, "index_available", False)
        and getattr(comp_status, "checksum_valid", False)
        and crism_status_raw in {"available", "partially_available", "verified"}
    )

    # Pre-evaluate dataset eligibilities once if caller did not supply them
    ds_eval_cache: Dict[str, Dict[str, Any]] = {}
    if evaluated_matches is not None:
        match_by_id = {m.source_id: m for m in evaluated_matches if m.source_type == "dataset_catalog"}
    else:
        match_by_id = {}

    ref_dtm = _select_reference_dtm(datasets, is_gale_question)
    seen_sha: Set[str] = set()
    seen_pids: Set[str] = set()
    for ds in datasets:
        inst_cls = _classify_dataset_instrument(ds)
        if ds.id in match_by_id:
            m = match_by_id[ds.id]
            ds_eval_cache[ds.id] = {
                "eligibility_state": m.eligibility_state,
                "inst_cls": inst_cls,
                "is_wmts": "{" in (ds.original_product_url or ""),
            }
        else:
            ev = evaluate_dataset_eligibility(
                ds=ds,
                inst_cls=inst_cls,
                question=question,
                is_gale=is_gale_question,
                seen_sha256=seen_sha,
                seen_product_ids=seen_pids,
                reference_dtm=ref_dtm,
            )
            ds_eval_cache[ds.id] = {
                "eligibility_state": ev["eligibility_state"],
                "inst_cls": inst_cls,
                "is_wmts": "{" in (ds.original_product_url or ""),
            }

    records: List[RequirementEvaluationRecord] = []

    for spec in question.required_measurement_specs:
        satisfying_ids: List[str] = []
        satisfying_insts: List[str] = []
        gaps: List[str] = []
        missing_info: List[str] = []
        resolution_steps: List[str] = []
        elig_summary: Dict[str, int] = {}
        matched_count = 0

        has_unverified = False
        has_unavailable = False
        has_failed = False
        has_wmts_only = False
        has_verified_calibration = False
        has_swath_or_coverage_limitation = False
        has_proxy_only = False
        has_conflict = False

        allowed_set = {i.upper() for i in spec.allowed_instrument_ids}

        # 1. Evaluate DatasetCatalogService holdings under strict 17-dimension eligibility
        for ds in datasets:
            ds_inst = _classify_dataset_instrument(ds)
            if ds_inst == "PERSEVERANCE_JEZERO_ISOLATED" and is_gale_question:
                continue
            if ds_inst == "USGS_SIM3292_CONTEXT":
                continue
            if ds_inst not in allowed_set:
                continue

            cached = ds_eval_cache[ds.id]
            elig: EvidenceEligibilityState = cached["eligibility_state"]
            is_wmts: bool = cached["is_wmts"]
            elig_summary[elig.value] = elig_summary.get(elig.value, 0) + 1

            if is_wmts:
                has_wmts_only = True
                has_unverified = True
                gaps.append(
                    f"Dataset '{ds.id}' ({ds_inst}) is a WMTS tile streaming endpoint ('{ds.original_product_url[:48]}...') — excluded from local verified scientific raster requirements."
                )
                missing_info.append(f"Validated local calibrated raster for {ds_inst} (non-WMTS archival PDS product)")
                resolution_steps.append(f"Acquire a radiometrically/geometrically calibrated local PDS GeoTIFF/IMG product for {ds_inst} covering the study corridor.")
                continue

            if elig in {
                EvidenceEligibilityState.ELIGIBLE,
                EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS,
            }:
                if (
                    spec.minimum_spatial_resolution_m is not None
                    and ds.horizontal_resolution_meters is not None
                    and ds.horizontal_resolution_meters > spec.minimum_spatial_resolution_m
                ):
                    gaps.append(
                        f"Dataset '{ds.id}' resolution (~{ds.horizontal_resolution_meters:.1f} m) is coarser than threshold {spec.minimum_spatial_resolution_m:.1f} m."
                    )
                    continue
                satisfying_ids.append(ds.id)
                if ds_inst not in satisfying_insts:
                    satisfying_insts.append(ds_inst)
                matched_count += 1
                if ds.verification.metadata_verification == VerificationState.VERIFIED:
                    has_verified_calibration = True
                if ds.known_limitations:
                    has_swath_or_coverage_limitation = True
                    gaps.extend(ds.known_limitations[:2])
                if elig == EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS:
                    if not ds.validation_report or not any("vertical" in k.lower() for k in (ds.known_limitations or [])):
                        gaps.append(
                            f"Dataset '{ds.id}' passes product & calibration verification; pixelwise statistical error raster is unquantified."
                        )
            elif elig == EvidenceEligibilityState.SCALE_INCOMPATIBLE:
                gaps.append(
                    f"Dataset '{ds.id}' ({ds_inst}) is scale-incompatible ({ds.horizontal_resolution_meters or 'coarse'} m vs {spec.minimum_spatial_resolution_m} m limit)."
                )
            elif elig == EvidenceEligibilityState.UNAVAILABLE:
                has_unavailable = True
                gaps.append(
                    f"Dataset '{ds.id}' ({ds_inst}) is catalog-discovered only (not locally acquired or checksum-verified)."
                )
                missing_info.append(f"Local archival download for '{ds.product_id}'")
                resolution_steps.append(f"Download and checksum-verify '{ds.product_id}' from {ds.source_archive}.")
            elif elig == EvidenceEligibilityState.REJECTED:
                has_failed = True
                gaps.append(
                    f"Dataset '{ds.id}' failed integrity/validation ({ds.failure_reason or ds.status.value}) and was excluded."
                )
                missing_info.append(f"Clean integrity-validated replacement for rejected '{ds.id}'")
                resolution_steps.append(f"Re-acquire or repair corrupted product '{ds.id}' and verify checksum/bounds/transform.")
            elif elig in {
                EvidenceEligibilityState.CALIBRATION_UNVERIFIED,
                EvidenceEligibilityState.PRODUCT_UNVERIFIED,
                EvidenceEligibilityState.SPATIALLY_UNVERIFIED,
                EvidenceEligibilityState.MEASUREMENT_SEMANTICS_UNVERIFIED,
            }:
                has_unverified = True
                gaps.append(
                    f"Dataset '{ds.id}' ({ds_inst}) cannot verify requirement because eligibility state is {elig.value}."
                )
                missing_info.append(f"Verified label, calibration, and spatial registration metadata for '{ds.id}'")
                resolution_steps.append(f"Obtain detached PDS3/PDS4 label & verify calibration/CRS metadata for '{ds.id}'.")
            elif elig == EvidenceEligibilityState.DUPLICATE_OR_CORRELATED:
                gaps.append(f"Dataset '{ds.id}' excluded as duplicate/correlated record.")

        # 2. Inspect CompositionSpatialIndex with strict integrity & calibration gating
        comp_integrity_ok = bool(
            comp_status
            and getattr(comp_status, "index_available", False)
            and getattr(comp_status, "checksum_valid", False)
            and getattr(comp_status, "source_dependencies_valid", True)
            and getattr(comp_status, "manifest_valid", True)
        )
        if comp_status and getattr(comp_status, "index_available", False) and not comp_integrity_ok:
            has_failed = True
            gaps.append(
                f"Composition spatial index failed integrity checks (status={getattr(comp_status, 'integrity_status', 'unknown')}) and is excluded."
            )
            missing_info.append("Integrity-verified CompositionSpatialIndex rebuild")
            resolution_steps.append("Run /api/composition/index/rebuild after verifying PDS tabular source checksums.")
        elif comp_integrity_ok:
            inst_indexed = {str(x).upper() for x in (getattr(comp_status, "instruments_indexed", []) or [])}
            located_n = int(getattr(comp_status, "located_evidence_count", 0) or 0)
            unlocated_n = int(getattr(comp_status, "unlocated_evidence_count", 0) or 0)

            if spec.measurement_class == MeasurementClass.ELEMENTAL_CHEMISTRY and located_n > 0:
                if {"APXS", "CHEMCAM_LIBS"} & inst_indexed:
                    satisfying_ids.append(f"composition_index:{comp_status.active_generation_id}")
                    for candidate_i in ("APXS", "CHEMCAM_LIBS"):
                        if candidate_i in allowed_set and candidate_i in inst_indexed:
                            if candidate_i not in satisfying_insts:
                                satisfying_insts.append(candidate_i)
                    matched_count += located_n
                    has_verified_calibration = True
                    elig_summary[EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS.value] = (
                        elig_summary.get(EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS.value, 0) + 1
                    )
                    if unlocated_n > 0:
                        gaps.append(
                            f"{unlocated_n} composition archive records lack verified rover coordinates and are excluded from spatial plots."
                        )
            elif spec.measurement_class == MeasurementClass.MINERALOGY_XRD:
                if "CHEMIN_XRD" in inst_indexed and located_n > 0:
                    satisfying_ids.append(f"composition_index_chemin:{comp_status.active_generation_id}")
                    if "CHEMIN_XRD" in allowed_set and "CHEMIN_XRD" not in satisfying_insts:
                        satisfying_insts.append("CHEMIN_XRD")
                    matched_count += 1
                    has_verified_calibration = True
                    has_swath_or_coverage_limitation = True
                    gaps.append(
                        "CheMin XRD verifies crystalline phases ONLY at sparse Curiosity drill holes; intervening terrain remains unmeasured."
                    )
                    if not crism_available:
                        gaps.append(
                            f"Regional orbital CRISM cubes unavailable ({crism_status_raw}); interpolation between drill holes is unsupported."
                        )
                        missing_info.append("Co-registered MRO CRISM SWIR mineral cube covering intermediate terrain")
                        resolution_steps.append("Acquire & calibrate MRO CRISM TRR3/MTRDR cube for continuous regional mineral mapping.")
                else:
                    has_unavailable = True
                    gaps.append("No local CheMin XRD crystalline phase file is indexed alongside verified coordinates.")
                    missing_info.append("Curiosity CheMin XRD quantitative mineral table + drill coordinates")
                    resolution_steps.append("Ingest PDS CheMin RDR mineral abundances with verified RMC coordinates.")
                    if located_n > 0:
                        has_proxy_only = True
                        gaps.append(
                            "Elemental oxides (ChemCam/APXS) are indexed locally ONLY as elemental proxies — they CANNOT confirm crystalline mineral phase."
                        )
            elif spec.measurement_class == MeasurementClass.VOLATILE_ORGANIC_ISOTOPE:
                if "SAM_EGA_GCMS" in inst_indexed and located_n > 0:
                    satisfying_ids.append(f"composition_index_sam:{comp_status.active_generation_id}")
                    if "SAM_EGA_GCMS" not in satisfying_insts:
                        satisfying_insts.append("SAM_EGA_GCMS")
                    matched_count += 1
                    has_verified_calibration = True
                else:
                    has_unavailable = True
                    gaps.append("SAM EGA/GCMS evolved-gas records are not indexed with verified spatial coordinates.")
                    missing_info.append("MSL SAM EGA/GCMS PDS product + verified drill coordinates")
                    resolution_steps.append("Ingest PDS MSL-M-SAM-2/4-RDR calibrated EGA/GCMS files into local archive.")
            elif spec.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL:
                if crism_available:
                    satisfying_ids.append("crism_validated_cube")
                    satisfying_insts.append("CRISM")
                    matched_count += 1
                    has_verified_calibration = True
                else:
                    has_unavailable = True
                    gaps.append(
                        f"CRISM spectral cubes unavailable ({crism_status_raw}); orbital mineral confirmation remains unestablished."
                    )
                    missing_info.append("MRO CRISM TRR3/MTRDR atmospherically corrected SWIR spectral cube")
                    resolution_steps.append("Acquire PDS MRO-M-CRISM-3/5-RDR spectral cube covering Gale boxwork ROI.")
        elif comp_status is None or not getattr(comp_status, "index_available", False):
            if spec.measurement_class in {
                MeasurementClass.ELEMENTAL_CHEMISTRY,
                MeasurementClass.MINERALOGY_XRD,
                MeasurementClass.VOLATILE_ORGANIC_ISOTOPE,
                MeasurementClass.MINERALOGY_SPECTRAL,
            }:
                has_unavailable = True
                missing_info.append("Local validated CompositionSpatialIndex")
                resolution_steps.append("Acquire verified MSL PDS tabular data and build the composition spatial index.")

        # 3. Inspect ImageryArchiveService ONLY for locally acquired + metadata-verified products
        for prod in imagery_products:
            inst_u = (prod.instrument or "").upper()
            mission_u = (prod.mission or "").upper()
            if is_gale_question and ("M2020" in mission_u or "PERSEVERANCE" in mission_u or "JEZERO" in (prod.dataset_id or "").upper()):
                continue
            inst_match = any(k in inst_u or inst_u in k for k in allowed_set)
            if not inst_match:
                continue
            if prod.local_file_path:
                inst_rec = get_instrument(inst_u)
                # Ensure optical imagery alone does not falsely satisfy spectral mineralogy
                if spec.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL:
                    continue
                if inst_rec and inst_rec.verification_status == RegistryVerificationStatus.UNVERIFIED and not getattr(prod, "pds_label_metadata", None):
                    has_unverified = True
                    gaps.append(
                        f"Imagery '{prod.product_id}' ({inst_u}) lacks verified detached PDS label / calibration metadata."
                    )
                    continue
                satisfying_ids.append(prod.product_id)
                if inst_u not in satisfying_insts:
                    satisfying_insts.append(inst_u)
                matched_count += 1
                has_swath_or_coverage_limitation = True
                elig_summary[EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS.value] = (
                    elig_summary.get(EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS.value, 0) + 1
                )
            else:
                has_unavailable = True
                gaps.append(
                    f"Imagery product '{prod.product_id}' ({inst_u}) is remotely discovered only (not downloaded locally)."
                )
                missing_info.append(f"Local download & verification of imagery '{prod.product_id}'")

        # 4. Determine strict RequirementFulfillmentState AND CanonicalRequirementState
        if spec.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL and not crism_available and not satisfying_ids:
            state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
        elif spec.measurement_class == MeasurementClass.MINERALOGY_XRD and "CHEMIN_XRD" not in satisfying_insts and not crism_available:
            if has_proxy_only:
                state = RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE
                gaps.append(
                    "Only elemental oxide measurements (ChemCam/APXS) are indexed locally; elemental abundance is a proxy and CANNOT establish crystalline mineral phase without CheMin XRD or CRISM SWIR spectra."
                )
            else:
                state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
        elif has_conflict:
            state = RequirementFulfillmentState.CONFLICT_REQUIRES_RESOLUTION
        elif satisfying_ids:
            if spec.measurement_class == MeasurementClass.THERMAL_INERTIA_COMPOSITION:
                state = RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
                gaps.append("Orbital thermal inertia (~100 m scale) provides broad induration framing only, not meter-scale hazard verification.")
            elif spec.measurement_class == MeasurementClass.MORPHOLOGY_HIGHRES and (has_unverified or has_wmts_only or has_swath_or_coverage_limitation):
                # Do NOT mark partial only if local verified ortho covers core cleanly, UNLESS only WMTS or incomplete!
                has_local_geotiff_ortho = any(
                    d.id in satisfying_ids and (d.local_file_path or d.processed_file_path) and "{" not in d.original_product_url
                    for d in datasets
                )
                state = (
                    RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
                    if (not has_local_geotiff_ortho and (has_unverified or has_wmts_only))
                    else (RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED if has_wmts_only else RequirementFulfillmentState.SATISFIED_DIRECT)
                )
            elif spec.measurement_class == MeasurementClass.ELEMENTAL_CHEMISTRY:
                state = RequirementFulfillmentState.SATISFIED_DIRECT
            elif spec.measurement_class == MeasurementClass.TOPOGRAPHY_ELEVATION:
                has_verified_dtm = any(
                    d.id in satisfying_ids and (d.local_file_path or d.processed_file_path) and "{" not in d.original_product_url
                    for d in datasets
                )
                state = (
                    RequirementFulfillmentState.SATISFIED_DIRECT
                    if has_verified_dtm
                    else RequirementFulfillmentState.MISSING_REQUIRED_DATA
                )
            else:
                state = (
                    RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
                    if (has_unavailable or has_unverified)
                    else RequirementFulfillmentState.SATISFIED_DIRECT
                )
        else:
            if has_unverified and not has_unavailable and not has_failed:
                state = RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE
            else:
                state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
            if not gaps:
                gaps.append(f"No validated local datasets or index records satisfy {spec.label}.")

        if not satisfying_ids and not missing_info:
            missing_info.append(f"Validated local product from allowed instruments: {', '.join(spec.allowed_instrument_ids)}")
        if not satisfying_ids and not resolution_steps:
            resolution_steps.append(f"Acquire and validate local NASA PDS archival product(s) from {', '.join(spec.allowed_instrument_ids)}.")

        canonical = _map_canonical_state(
            fulfillment=state,
            has_unverified_candidates=has_unverified,
            has_unavailable_candidates=has_unavailable,
            has_failed_candidates=has_failed,
            missing_info=missing_info,
        )

        # Coverage status
        if not satisfying_ids:
            cov_status = "UNAVAILABLE_NOT_ACQUIRED" if has_unavailable else ("UNVERIFIED_NON_LOCAL_OR_FAILED" if (has_unverified or has_failed) else "MISSING")
        elif spec.measurement_class in {MeasurementClass.ELEMENTAL_CHEMISTRY, MeasurementClass.MINERALOGY_XRD, MeasurementClass.VOLATILE_ORGANIC_ISOTOPE}:
            cov_status = "SPARSE_ROVER_TRAVERSE_POINTS_ONLY"
        elif has_swath_or_coverage_limitation or has_wmts_only:
            cov_status = "COVERED_WITH_SWATH_OR_BOUNDARY_LIMITATIONS"
        else:
            cov_status = "COVERED_LOCAL_CORE"

        # Quality status
        if has_failed and not satisfying_ids:
            qual_status = "FAILED_INTEGRITY_VALIDATION_REJECTED"
        elif has_unverified and not satisfying_ids:
            qual_status = "UNVERIFIED_CALIBRATION_OR_ENDPOINT"
        elif satisfying_ids and has_verified_calibration:
            qual_status = "CALIBRATED_PRODUCT_VERIFIED_UNCERTAINTY_UNQUANTIFIED"
        elif satisfying_ids:
            qual_status = "LOCAL_PRODUCT_PARTIALLY_VERIFIED"
        else:
            qual_status = "UNAVAILABLE"

        fail_reason: Optional[str] = None
        if not satisfying_ids:
            fail_reason = "; ".join(list(dict.fromkeys(gaps))[:2]) or f"No eligible evidence for {spec.label}"

        records.append(
            RequirementEvaluationRecord(
                requirement_id=spec.requirement_id,
                label=spec.label,
                measurement_class=spec.measurement_class,
                essential=spec.essential,
                fulfillment_state=state,
                canonical_state=canonical,
                required_measurement=list(spec.required_observables),
                required_spatial_scale_m=spec.minimum_spatial_resolution_m,
                threshold_rule_classification=spec.threshold_rule_classification,
                threshold_rationale=spec.threshold_rationale,
                required_calibration_state=spec.required_calibration_state,
                required_product_characteristics=list(spec.required_product_characteristics),
                satisfying_source_ids=list(dict.fromkeys(satisfying_ids)),
                satisfying_instruments=list(dict.fromkeys(satisfying_insts)),
                evidence_eligibility_summary=elig_summary,
                coverage_status=cov_status,
                quality_status=qual_status,
                matched_evidence_count=matched_count,
                limitations_and_gaps=list(dict.fromkeys(gaps)),
                missing_information=list(dict.fromkeys(missing_info)),
                failure_reason=fail_reason,
                resolution_path=list(dict.fromkeys(resolution_steps)),
                prohibited_substitutions=list(spec.prohibited_substitutions),
            )
        )

    return records
