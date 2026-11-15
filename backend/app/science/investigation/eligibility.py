"""
MARSCOPE 17-Dimension Evidence Eligibility, Duplication Detection,
Evidence Role Synthesis & Traceable Provenance Graph Engine (Prompt 18).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.geospatial.crs import evaluate_spatial_registration, validate_mars_crs
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.science.investigation.measurement_registry import get_instrument
from app.science.investigation.schemas import (
    EvidenceEligibilityDimensionResult,
    EvidenceEligibilityState,
    EvidenceMatchRecord,
    EvidenceMatchStrength,
    EvidenceRole,
    EvidenceSynthesisSummary,
    MeasurementClass,
    RegistryVerificationStatus,
    RequirementEvaluationRecord,
    ScienceQuestionDefinition,
    SpatialRegistrationState,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceEdge,
    ProvenanceNode,
    ProvenanceStep,
    ScientificDataClassification,
)


def _norm_reg_state(raw: str) -> SpatialRegistrationState:
    try:
        return SpatialRegistrationState(raw)
    except Exception:
        return SpatialRegistrationState.INSUFFICIENT_METADATA


def evaluate_dataset_eligibility(
    *,
    ds: Dataset,
    inst_cls: str,
    question: ScienceQuestionDefinition,
    is_gale: bool,
    seen_sha256: Set[str],
    seen_product_ids: Set[str],
    reference_dtm: Optional[Dataset] = None,
    has_contradicting_flag: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate all 17 independent Prompt 18 evidence-eligibility dimensions on a Dataset record.
    Product-level metadata takes precedence over generic instrument capability specs.
    """
    dims: List[EvidenceEligibilityDimensionResult] = []
    text = f"{ds.id} {ds.mission} {ds.product_title}".upper()
    is_wmts = "{" in (ds.original_product_url or "")
    inst_rec = get_instrument(inst_cls)

    # 1. Source authenticity
    src_ok = bool(ds.original_product_url and ds.source_archive)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="1_source_authenticity",
            status="PASS" if src_ok else "UNVERIFIED",
            detail=f"Source archive '{ds.source_archive}' ({ds.attribution})" if src_ok else "Missing authoritative source archive/URL.",
            source_reference=ds.original_product_url,
        )
    )

    # 2. Product identity
    pid_ok = bool(ds.product_id and not is_wmts)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="2_product_identity",
            status="PASS" if pid_ok else ("PASS_WITH_LIMITATION" if ds.product_id else "FAIL"),
            detail=(
                f"WMTS tile endpoint '{ds.product_id}' (streaming visual layer, not a scientific archival file)."
                if is_wmts
                else f"Product ID '{ds.product_id}' (PDS/DOI: {ds.doi_or_pds_id or 'unspecified'})."
            ),
            source_reference=ds.doi_or_pds_id,
        )
    )

    # 3. Product integrity
    has_local = bool(ds.local_file_path or ds.processed_file_path) and not is_wmts
    integrity_failed = bool(
        ds.status in {DatasetLifecycleStatus.FAILED_VALIDATION, DatasetLifecycleStatus.FAILED_DOWNLOAD, DatasetLifecycleStatus.FAILED_PROCESSING}
        or ds.failure_reason
    )
    if is_wmts:
        int_status = "UNVERIFIED"
        int_detail = "WMTS streaming mosaic has no local immutable binary file or SHA-256 verification."
    elif integrity_failed:
        int_status = "FAIL"
        int_detail = f"Failed lifecycle/validation state ({ds.status.value}): {ds.failure_reason or 'check verification ledger'}"
    elif has_local and ds.sha256_checksum and ds.verification.download_verification == VerificationState.VERIFIED:
        int_status = "PASS"
        int_detail = f"Local artifact SHA-256 verified ({ds.sha256_checksum[:16]}...)."
    elif has_local:
        int_status = "PASS_WITH_LIMITATION"
        int_detail = "Local artifact exists on disk but SHA-256 / archive checksum comparison is incomplete."
    else:
        int_status = "UNAVAILABLE"
        int_detail = "Product discovered in catalog only; binary artifact is not acquired locally."
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="3_product_integrity",
            status=int_status,
            detail=int_detail,
            source_reference=ds.local_file_path,
        )
    )

    # 4. Instrument identity & registry verification
    if inst_rec is None:
        inst_status = "UNVERIFIED"
        inst_detail = f"Instrument '{inst_cls}' lacks a verified entry in InstrumentCapabilityRegistry."
    elif inst_rec.verification_status == RegistryVerificationStatus.VERIFIED:
        inst_status = "PASS"
        inst_detail = f"Verified instrument capability '{inst_rec.instrument_id}' (v{inst_rec.registry_version})."
    else:
        # Unverified instrument capability requires verified product metadata to compensate, otherwise remains UNVERIFIED
        label_verified = ds.verification.metadata_verification == VerificationState.VERIFIED and has_local
        inst_status = "PASS_WITH_LIMITATION" if label_verified else "UNVERIFIED"
        inst_detail = (
            f"Instrument '{inst_rec.instrument_id}' registry specification is UNVERIFIED"
            + ("; product-level label verified on local artifact." if label_verified else "; requires verified product label.")
        )
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="4_instrument_identity",
            status=inst_status,
            detail=inst_detail,
            source_reference=inst_rec.registry_entry_id if inst_rec else None,
        )
    )

    # 5. Measurement semantics
    q_classes = {spec.measurement_class for spec in question.required_measurement_specs}
    inst_mc = inst_rec.measurement_class if inst_rec else None
    is_non_comp_telemetry = inst_cls == "REMS" or "psv" in ds.id.lower()
    if "psv" in ds.id.lower():
        sem_status = "FAIL"
        sem_detail = "Passive ChemCam PSV spectrum in DIGITAL_NUMBER (LASER_MODE=NO); excluded from composition evidence."
    elif is_wmts and inst_mc == MeasurementClass.MORPHOLOGY_HIGHRES:
        sem_status = "PASS_WITH_LIMITATION"
        sem_detail = "Visual optical basemap depicts albedo/morphology only; prohibited for mineral identification."
    elif inst_cls == "USGS_SIM3292_CONTEXT":
        sem_status = "PASS_WITH_LIMITATION"
        sem_detail = "1:20M planetary geologic map context unit only; not direct outcrop spectroscopy or chemistry."
    else:
        sem_status = "PASS"
        sem_detail = (
            f"Physical quantity verified by modality '{inst_rec.measurement_modality}'"
            if inst_rec
            else f"Product type '{ds.product_type}' semantics from {ds.instrument}."
        )
    dims.append(EvidenceEligibilityDimensionResult(dimension="5_measurement_semantics", status=sem_status, detail=sem_detail))

    # 6. Calibration status
    cal_l = (ds.calibration_status or "unknown").lower()
    cal_ok = cal_l not in {"unknown", "", "uncalibrated", "raw dn"}
    cal_status = "PASS" if (cal_ok and ds.verification.metadata_verification == VerificationState.VERIFIED) else ("UNVERIFIED" if cal_l in {"unknown", ""} else "FAIL")
    if is_wmts:
        cal_status = "UNVERIFIED"
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="6_calibration_status",
            status=cal_status,
            detail=f"Calibration state: '{ds.calibration_status}'",
        )
    )

    # 7. Processing level
    proc_ok = (ds.processing_level or "unknown").lower() not in {"unknown", ""}
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="7_processing_level",
            status="PASS" if proc_ok else "UNVERIFIED",
            detail=f"Processing level: '{ds.processing_level}'",
        )
    )

    # 8. Units (product metadata takes precedence)
    units_ok = (ds.units or "unknown").lower() not in {"unknown", ""}
    unit_stat = "PASS" if units_ok else ("PASS_WITH_LIMITATION" if "waypoint" in ds.id.lower() else "UNVERIFIED")
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="8_units",
            status=unit_stat,
            detail=f"Product physical units: '{ds.units}'",
        )
    )

    # 9. Coordinate validity (Prompt 19 detailed Mars CRS registry check)
    from app.geospatial.crs import validate_mars_crs_detailed
    from app.geospatial.models import SpatialRegistrationAssessmentState as _RegAssessState
    from app.geospatial.registration import evaluate_product_pair_registration

    crs_det = validate_mars_crs_detailed(
        ds.coordinate_reference_system,
        latitude_convention=ds.latitude_convention,
        longitude_direction=ds.longitude_direction,
        vertical_reference=ds.calibration_status,
    )
    crs_ok = crs_det.valid and validate_mars_crs(ds.coordinate_reference_system)
    coord_ok = (
        crs_ok
        and ds.coverage.min_latitude >= -90.0
        and ds.coverage.max_latitude <= 90.0
        and ds.coverage.min_latitude < ds.coverage.max_latitude
    )
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="9_coordinate_validity",
            status="PASS" if coord_ok else "FAIL",
            detail=(
                f"CRS={ds.coordinate_reference_system!r} ({crs_det.validation_state.value}), "
                f"lat=[{ds.coverage.min_latitude},{ds.coverage.max_latitude}], conv={ds.latitude_convention}/{ds.longitude_direction}."
            ),
        )
    )

    # 10. Spatial registration quality (pairwise footprint/datum check when local files exist)
    ref = reference_dtm
    if ref is not None and ref.id != ds.id:
        reg_report = evaluate_spatial_registration(
            product_a_id=ds.id,
            product_b_id=ref.id,
            crs_a=ds.coordinate_reference_system,
            crs_b=ref.coordinate_reference_system,
            bounds_a=ds.coverage.model_dump(),
            bounds_b=ref.coverage.model_dump(),
            resolution_a_m=ds.horizontal_resolution_meters,
            resolution_b_m=ref.horizontal_resolution_meters,
            lat_conv_a=ds.latitude_convention,
            lat_conv_b=ref.latitude_convention,
            lon_dir_a=ds.longitude_direction,
            lon_dir_b=ref.longitude_direction,
            projection_a=ds.map_projection,
            projection_b=ref.map_projection,
            radii_a_m=ds.planetary_radii_m,
            radii_b_m=ref.planetary_radii_m,
        )
    else:
        # Self-registration vs Gale IAU2000 reference datum
        gale_bounds = {"min_latitude": -5.5, "max_latitude": -4.3, "min_longitude": 137.2, "max_longitude": 138.0}
        reg_report = evaluate_spatial_registration(
            product_a_id=ds.id,
            product_b_id="gale_study_frame_iau2000",
            crs_a=ds.coordinate_reference_system,
            crs_b="IAU2000:49900",
            bounds_a=ds.coverage.model_dump(),
            bounds_b=gale_bounds,
            resolution_a_m=ds.horizontal_resolution_meters,
            resolution_b_m=ds.horizontal_resolution_meters,
            lat_conv_a=ds.latitude_convention,
            lat_conv_b="Planetocentric",
            lon_dir_a=ds.longitude_direction,
            lon_dir_b="East",
            projection_a=ds.map_projection,
            projection_b=ds.map_projection,
            radii_a_m=ds.planetary_radii_m,
            radii_b_m={"a": 3396190.0, "b": 3396190.0, "c": 3376200.0},
        )
    reg_state = _norm_reg_state(reg_report["registration_state"])
    if reg_state in {SpatialRegistrationState.INCOMPATIBLE_REFERENCE_SYSTEM, SpatialRegistrationState.NOT_REGISTERED}:
        reg_dim_stat = "FAIL"
    elif reg_state in {SpatialRegistrationState.INSUFFICIENT_METADATA, SpatialRegistrationState.REGISTRATION_UNVERIFIED}:
        reg_dim_stat = "PASS_WITH_LIMITATION" if crs_ok else "UNVERIFIED"
    elif reg_state in {SpatialRegistrationState.PARTIALLY_OVERLAPPING, SpatialRegistrationState.REGISTERED_WITH_LIMITATIONS}:
        reg_dim_stat = "PASS_WITH_LIMITATION"
    else:
        reg_dim_stat = "PASS"

    reg_detail = f"State={reg_state.value}; error_status={reg_report['registration_error_status']}."
    if ref is not None and ref.id != ds.id and (ds.local_file_path or ds.processed_file_path) and (ref.local_file_path or ref.processed_file_path):
        try:
            from pathlib import Path as _P

            ds_root = _P(__file__).resolve().parents[4] / "datasets"
            pair_reg = evaluate_product_pair_registration(
                ds,
                ref,
                dataset_root_dir=ds_root,
                intended_analysis=question.question_id,
            )
            if pair_reg.overall_state in {
                _RegAssessState.INCOMPATIBLE_CRS_OR_FRAME,
                _RegAssessState.NOT_REGISTERED,
            } or pair_reg.footprint_overlap_status == "bbox_only_no_valid_pixel_overlap":
                reg_dim_stat = "FAIL"
                reg_state = SpatialRegistrationState.NOT_REGISTERED
            elif pair_reg.overall_state == _RegAssessState.VALIDATED_WITH_LIMITATIONS and reg_dim_stat == "PASS":
                reg_dim_stat = "PASS_WITH_LIMITATION"
            reg_detail = f"State={pair_reg.overall_state.value}; overlap={pair_reg.footprint_overlap_status} ({pair_reg.overlap_area_m2 or 0.0} m2)."
        except Exception:
            pass

    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="10_spatial_registration_quality",
            status=reg_dim_stat,
            detail=reg_detail,
        )
    )

    # 11. Spatial scale compatibility (PRODUCT metadata takes precedence!)
    prod_res_m = ds.horizontal_resolution_meters
    matching_specs = [
        s for s in question.required_measurement_specs if inst_cls in {x.upper() for x in s.allowed_instrument_ids}
    ]
    scale_ok = True
    scale_detail = f"Product spatial resolution: {prod_res_m} m/px" if prod_res_m is not None else "Point / tabular or unquantified raster spacing"
    for sp in matching_specs:
        if sp.minimum_spatial_resolution_m is not None and prod_res_m is not None and prod_res_m > sp.minimum_spatial_resolution_m:
            scale_ok = False
            scale_detail = f"Product resolution {prod_res_m:.1f} m/px is coarser than spec limit {sp.minimum_spatial_resolution_m:.1f} m/px."
    if inst_cls in {"MOLA", "USGS_SIM3292_CONTEXT"} and MeasurementClass.TOPOGRAPHY_ELEVATION in q_classes:
        # MOLA (~463 m / 14.8 km) is scale-incompatible with local outcrop/boxwork requirements
        if any(s.minimum_spatial_resolution_m is not None and s.minimum_spatial_resolution_m < 100.0 for s in question.required_measurement_specs if s.measurement_class == MeasurementClass.TOPOGRAPHY_ELEVATION):
            scale_ok = False
            scale_detail = f"{inst_cls} resolution ({prod_res_m or 'regional'} m/px) is incompatible with meter-scale question requirements."
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="11_spatial_scale_compatibility",
            status="PASS" if scale_ok else "FAIL",
            detail=scale_detail,
        )
    )

    # 12. Mission compatibility (strict Jezero isolation)
    mission_isolated = bool(
        is_gale
        and (
            inst_cls == "PERSEVERANCE_JEZERO_ISOLATED"
            or "PERSEVERANCE" in text
            or "JEZERO" in text
            or "MARS 2020" in text
            or (inst_rec and inst_rec.mission_isolated_from_gale)
        )
    )
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="12_mission_compatibility",
            status="FAIL" if mission_isolated else "PASS",
            detail=(
                "STRICT MISSION ISOLATION: Jezero / Mars 2020 data quarantined from Gale Crater."
                if mission_isolated
                else f"Mission '{ds.mission}' compatible with '{question.study_region}'."
            ),
        )
    )

    # 13. Temporal compatibility
    has_time = bool(ds.acquisition_timestamp or ds.observation_sol is not None)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="13_temporal_compatibility",
            status="PASS" if has_time else "PASS_WITH_LIMITATION",
            detail=(
                f"Acquisition timestamp={ds.acquisition_timestamp.isoformat() if ds.acquisition_timestamp else 'N/A'}, sol={ds.observation_sol}."
                if has_time
                else "No acquisition timestamp or sol recorded; seasonal/temporal state unverified."
            ),
        )
    )

    # 14. Data quality
    qual_fail = bool(ds.failure_reason or ds.verification.processing_verification == VerificationState.FAILED)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="14_data_quality",
            status="FAIL" if qual_fail else ("PASS" if ds.quality_flags else "PASS_WITH_LIMITATION"),
            detail=f"Failures={ds.failure_reason}; flags={ds.quality_flags or ['none_recorded']}.",
        )
    )

    # 15. Scientific relevance (evaluated strictly against active question requirements/classes)
    if inst_cls == "WAYPOINTS":
        relevant = False
        rel_detail = "Rover traverse waypoint lookup supports coordinate joins only; not primary scientific mineral/topographic evidence."
    elif matching_specs or (inst_mc and inst_mc in q_classes):
        relevant = True
        rel_detail = f"Directly addresses question measurement class(es): {', '.join(s.label for s in matching_specs) or inst_mc.value}."
    elif inst_cls in {"MOLA", "CTX", "USGS_SIM3292_CONTEXT"}:
        relevant = True
        rel_detail = "Regional contextual framing only (not primary diagnostic evidence for this question)."
    elif is_non_comp_telemetry and MeasurementClass.METEOROLOGY_ENVIRONMENT not in q_classes:
        relevant = False
        rel_detail = f"Telemetry from {inst_cls} does not address any required measurement class of '{question.title}'."
    else:
        relevant = False
        rel_detail = f"Does not match required measurement classes/instruments of '{question.question_id}'."
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="15_scientific_relevance",
            status="PASS" if relevant else "FAIL",
            detail=rel_detail,
        )
    )

    # 16. Uncertainty availability
    has_unc = bool(ds.validation_report or ds.known_limitations or ds.processing_provenance)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="16_uncertainty_availability",
            status="PASS_WITH_LIMITATION",
            detail=(
                "Product-level limitations & metadata bounds documented; pixelwise statistical uncertainty unquantified unless paired uncertainty raster exists."
                if has_unc
                else "No per-record uncertainty metadata supplied (UNQUANTIFIED — never fabricated)."
            ),
        )
    )

    # 17. Duplication or correlation
    is_dup = False
    dup_reason: Optional[str] = None
    norm_pid = (ds.product_id or "").strip().upper()
    if ds.sha256_checksum and ds.sha256_checksum in seen_sha256:
        is_dup = True
        dup_reason = f"Exact SHA-256 checksum duplicate ({ds.sha256_checksum[:12]}...)."
    elif norm_pid and norm_pid in seen_product_ids:
        is_dup = True
        dup_reason = f"Duplicate or reprocessed record sharing product_id '{norm_pid}'."
    if not is_dup:
        if ds.sha256_checksum:
            seen_sha256.add(ds.sha256_checksum)
        if norm_pid and not is_wmts:
            seen_product_ids.add(norm_pid)
    dims.append(
        EvidenceEligibilityDimensionResult(
            dimension="17_duplication_or_correlation",
            status="FAIL" if is_dup else "PASS",
            detail=dup_reason or "Independent archive record (no duplicate checksum or product ID detected).",
        )
    )

    # Determine final Prompt 18 13-state EvidenceEligibilityState
    if mission_isolated:
        elig_state = EvidenceEligibilityState.MISSION_INCOMPATIBLE
    elif is_dup:
        elig_state = EvidenceEligibilityState.DUPLICATE_OR_CORRELATED
    elif integrity_failed or reg_state == SpatialRegistrationState.INCOMPATIBLE_REFERENCE_SYSTEM or not crs_ok:
        elig_state = (
            EvidenceEligibilityState.SPATIALLY_UNVERIFIED
            if not crs_ok or reg_state == SpatialRegistrationState.INCOMPATIBLE_REFERENCE_SYSTEM
            else EvidenceEligibilityState.REJECTED
        )
    elif not has_local and not is_wmts:
        elig_state = EvidenceEligibilityState.UNAVAILABLE
    elif not relevant:
        elig_state = EvidenceEligibilityState.SCIENTIFICALLY_IRRELEVANT
    elif sem_status == "FAIL":
        elig_state = EvidenceEligibilityState.MEASUREMENT_SEMANTICS_UNVERIFIED
    elif is_wmts or inst_status == "UNVERIFIED":
        elig_state = EvidenceEligibilityState.PRODUCT_UNVERIFIED
    elif cal_status != "PASS":
        elig_state = EvidenceEligibilityState.CALIBRATION_UNVERIFIED
    elif not scale_ok:
        elig_state = EvidenceEligibilityState.SCALE_INCOMPATIBLE
    elif reg_dim_stat in {"UNVERIFIED", "FAIL"}:
        elig_state = EvidenceEligibilityState.SPATIALLY_UNVERIFIED
    elif any(d.status == "PASS_WITH_LIMITATION" for d in dims):
        elig_state = EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS
    else:
        elig_state = EvidenceEligibilityState.ELIGIBLE

    # Evidence role classification (NEVER auto-supporting solely from keyword!)
    if elig_state == EvidenceEligibilityState.UNAVAILABLE:
        role = EvidenceRole.UNAVAILABLE
        role_reason = "Source product is not locally acquired/available."
    elif elig_state == EvidenceEligibilityState.SCIENTIFICALLY_IRRELEVANT or elig_state == EvidenceEligibilityState.MISSION_INCOMPATIBLE:
        role = EvidenceRole.NOT_RELEVANT
        role_reason = rel_detail if not mission_isolated else "Mission-isolated (Jezero Crater)."
    elif elig_state == EvidenceEligibilityState.REJECTED:
        role = EvidenceRole.INCONCLUSIVE
        role_reason = f"Product rejected at validation ({ds.failure_reason or 'integrity check failed'})."
    elif elig_state in {
        EvidenceEligibilityState.PRODUCT_UNVERIFIED,
        EvidenceEligibilityState.CALIBRATION_UNVERIFIED,
        EvidenceEligibilityState.SPATIALLY_UNVERIFIED,
        EvidenceEligibilityState.MEASUREMENT_SEMANTICS_UNVERIFIED,
    }:
        role = EvidenceRole.INCONCLUSIVE
        role_reason = f"Cannot serve as supporting diagnostic evidence because state is {elig_state.value}."
    elif elig_state == EvidenceEligibilityState.SCALE_INCOMPATIBLE or inst_cls in {"MOLA", "CTX", "USGS_SIM3292_CONTEXT"}:
        role = EvidenceRole.CONTEXTUAL
        role_reason = f"Provides regional/coarse framing only (~{prod_res_m or 'regional'} m scale)."
    elif elig_state == EvidenceEligibilityState.DUPLICATE_OR_CORRELATED:
        role = EvidenceRole.CONTEXTUAL
        role_reason = f"Duplicate/correlated observation ({dup_reason}); excluded from independent corroboration."
    elif has_contradicting_flag:
        role = EvidenceRole.CONTRADICTING
        role_reason = "Co-located measurements diverge from competing hypothesis criteria."
    elif inst_cls == "HIRISE":
        # Optical morphology provides geometric context, NEVER mineral confirmation
        role = EvidenceRole.CONTEXTUAL
        role_reason = "High-resolution optical morphology constrains geometry/hazard context only (not mineral chemistry)."
    else:
        role = EvidenceRole.SUPPORTING if matching_specs else EvidenceRole.CONTEXTUAL
        role_reason = (
            f"Directly addresses {', '.join(s.requirement_id for s in matching_specs)} with verified calibration and registration."
            if matching_specs
            else "Validated contextual observation within study region."
        )

    uncertainty_summary = {
        "quantified": False,
        "vertical_precision_m": None,
        "registration_error_m": reg_report.get("registration_error_m"),
        "status": "UNQUANTIFIED_BOUNDED_BY_LIMITATIONS_ONLY",
        "notes": list(ds.known_limitations or []) + [reg_report["registration_error_status"]],
    }
    chain = [
        f"mission:{ds.mission}",
        f"instrument:{inst_cls}",
        f"product:{ds.product_id}",
        f"label:{ds.local_label_path or 'none'}",
        f"raw:{ds.local_file_path or 'unavailable'}",
        f"processed:{ds.processed_file_path or 'none'}",
        f"registration:{reg_state.value}",
        f"eligibility:{elig_state.value}",
    ]

    return {
        "eligibility_state": elig_state,
        "dimensions": dims,
        "registration_state": reg_state,
        "registration_report": reg_report,
        "evidence_role": role,
        "role_reason": role_reason,
        "scientific_relevance": rel_detail,
        "uncertainty_summary": uncertainty_summary,
        "duplication_info": {"is_duplicate": is_dup, "reason": dup_reason},
        "resolved_scale_m": prod_res_m,
        "provenance_chain": chain,
    }


def synthesize_question_evidence(
    *,
    question: ScienceQuestionDefinition,
    matched: List[EvidenceMatchRecord],
    requirements: List[RequirementEvaluationRecord],
    conflicts: Optional[List[str]] = None,
) -> EvidenceSynthesisSummary:
    """
    Synthesize all evaluated EvidenceMatchRecords without hiding contradicting/inconclusive records,
    without counting duplicates as independent corroboration, and without inventing statistical confidence %.
    """
    sup = [m for m in matched if m.evidence_role == EvidenceRole.SUPPORTING]
    con = [m for m in matched if m.evidence_role == EvidenceRole.CONTRADICTING]
    ctx = [m for m in matched if m.evidence_role == EvidenceRole.CONTEXTUAL]
    inc = [m for m in matched if m.evidence_role == EvidenceRole.INCONCLUSIVE]
    irr = [m for m in matched if m.evidence_role == EvidenceRole.NOT_RELEVANT]
    una = [m for m in matched if m.evidence_role == EvidenceRole.UNAVAILABLE]
    dups = [m for m in matched if m.eligibility_state == EvidenceEligibilityState.DUPLICATE_OR_CORRELATED]

    dup_set = {m.match_id for m in dups}
    indep_sup = [m for m in sup if m.match_id not in dup_set]
    contradictions = list(conflicts or []) + [
        f"{m.source_id} ({m.instrument_id}): {m.evidence_role_rationale}" for m in con
    ]
    missing = []
    for req in requirements:
        if req.missing_information:
            missing.extend(req.missing_information)
        elif req.limitations_and_gaps:
            missing.extend(req.limitations_and_gaps)

    if contradictions:
        qual_state = "UNRESOLVED_CONTRADICTORY_OR_CONFLICTING_EVIDENCE"
    elif indep_sup and not missing:
        qual_state = "MULTI_INSTRUMENT_EVIDENCE_AVAILABLE_HYPOTHESIS_TESTABLE"
    elif indep_sup or ctx:
        qual_state = "PARTIAL_EVIDENCE_WITH_UNRESOLVED_MINERAL_OR_SPATIAL_GAPS"
    else:
        qual_state = "INSUFFICIENT_VERIFIED_EVIDENCE_UNRESOLVED"

    dup_notes = [
        f"{m.source_id}: {(m.duplication_or_correlation or {}).get('reason', 'duplicate/correlated record excluded from independent corroboration')}"
        for m in dups
    ]
    return EvidenceSynthesisSummary(
        qualitative_evidence_state=qual_state,
        statistical_confidence_state="UNAVAILABLE_NO_VALIDATED_STATISTICAL_MODEL",
        statistical_confidence_score=None,
        supporting_count=len(sup),
        contradicting_count=len(con),
        contextual_count=len(ctx),
        inconclusive_count=len(inc),
        not_relevant_count=len(irr),
        unavailable_count=len(una),
        duplicate_or_correlated_count=len(dups),
        independent_evidence_count=len(indep_sup),
        supporting_observations=[f"{m.source_id} [{m.instrument_id}]: {m.evidence_role_rationale}" for m in sup],
        contradicting_observations=[f"{m.source_id} [{m.instrument_id}]: {m.evidence_role_rationale}" for m in con],
        inconclusive_observations=[f"{m.source_id} [{m.instrument_id}]: {m.evidence_role_rationale}" for m in inc],
        missing_evidence=list(dict.fromkeys(missing)),
        competing_hypotheses=list(question.competing_hypotheses),
        alternative_explanations=list(question.alternative_explanations),
        unresolved_contradictions=list(dict.fromkeys(contradictions)),
        duplication_notes=dup_notes,
        synthesis_rationale=(
            f"Evaluated {len(matched)} candidate records against {len(requirements)} requirements: "
            f"{len(indep_sup)} independent supporting, {len(con)} contradicting, {len(ctx)} contextual, "
            f"{len(inc)} inconclusive, {len(dups)} duplicate/correlated excluded from corroboration. "
            "No numerical statistical confidence score is synthesized."
        ),
    )


def build_question_provenance_graph(
    *,
    question: ScienceQuestionDefinition,
    datasets: List[Dataset],
    matched: List[EvidenceMatchRecord],
    requirements: List[RequirementEvaluationRecord],
) -> ProvenanceDependencyGraph:
    """Build an inspectable end-to-end node/edge ProvenanceDependencyGraph across all pipeline stages."""
    nodes: Dict[str, ProvenanceNode] = {}
    edges: List[ProvenanceEdge] = []
    edge_keys: Set[Tuple[str, str, str]] = set()

    def _add_node(nid: str, ntype: str, label: str, cls: ScientificDataClassification, sha: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> None:
        if nid not in nodes:
            nodes[nid] = ProvenanceNode(
                node_id=nid, node_type=ntype, label=label, classification=cls, sha256_checksum=sha, metadata=meta or {}
            )

    def _add_edge(src: str, dst: str, rel: str) -> None:
        k = (src, dst, rel)
        if k not in edge_keys:
            edge_keys.add(k)
            edges.append(ProvenanceEdge(source_id=src, target_id=dst, relationship=rel))

    q_nid = f"question:{question.question_id}"
    _add_node(q_nid, "investigation_question", question.title, ScientificDataClassification.MARSCOPE_DERIVED)

    ds_map = {d.id: d for d in datasets}
    for m in matched:
        mission_nid = f"mission:{m.mission_host}"
        inst_nid = f"instrument:{m.instrument_id}"
        ev_nid = f"evidence:{m.match_id}"
        _add_node(mission_nid, "source_mission", m.mission_host, ScientificDataClassification.DIRECTLY_MEASURED)
        _add_node(inst_nid, "instrument", m.instrument_id, ScientificDataClassification.DIRECTLY_MEASURED)
        _add_edge(mission_nid, inst_nid, "hosts_instrument")

        ds = ds_map.get(m.source_id)
        if ds:
            prod_nid = f"source_product:{ds.product_id}"
            _add_node(prod_nid, "source_product", ds.product_id, ScientificDataClassification.ARCHIVE_DERIVED, ds.sha256_checksum)
            _add_edge(inst_nid, prod_nid, "acquired_product")
            parent_for_ev = prod_nid
            if ds.local_label_path:
                lbl_nid = f"product_label:{ds.id}"
                _add_node(lbl_nid, "product_label", Path(ds.local_label_path).name, ScientificDataClassification.DIRECTLY_MEASURED)
                _add_edge(prod_nid, lbl_nid, "documented_by_label")
            if ds.local_file_path:
                raw_nid = f"raw_file:{ds.id}"
                _add_node(raw_nid, "raw_file", Path(ds.local_file_path).name, ScientificDataClassification.DIRECTLY_MEASURED, ds.sha256_checksum)
                _add_edge(prod_nid, raw_nid, "stored_immutable_raw")
                parent_for_ev = raw_nid
            if ds.processed_file_path:
                proc_nid = f"processed_file:{ds.id}"
                _add_node(proc_nid, "processed_file", Path(ds.processed_file_path).name, ScientificDataClassification.MARSCOPE_DERIVED)
                _add_edge(parent_for_ev, proc_nid, "derived_processed_raster")
                parent_for_ev = proc_nid
            cal_nid = f"calibration:{ds.id}"
            _add_node(cal_nid, "calibration_operation", ds.calibration_status, ScientificDataClassification.ARCHIVE_DERIVED)
            _add_edge(parent_for_ev, cal_nid, "calibration_verified")
            crs_nid = f"crs_transform:{ds.id}"
            _add_node(crs_nid, "coordinate_transformation", ds.coordinate_reference_system or "unknown", ScientificDataClassification.MARSCOPE_DERIVED)
            _add_edge(cal_nid, crs_nid, "spatial_frame")
            reg_nid = f"spatial_reg:{m.match_id}"
            _add_node(reg_nid, "spatial_registration", m.spatial_registration_state.value, ScientificDataClassification.MARSCOPE_DERIVED)
            _add_edge(crs_nid, reg_nid, "registered_as")
            parent_for_ev = reg_nid
        else:
            parent_for_ev = inst_nid

        _add_node(
            ev_nid,
            "evidence_record",
            f"{m.source_id} [{m.eligibility_state.value} / {m.evidence_role.value}]",
            ScientificDataClassification.MARSCOPE_DERIVED
            if m.eligibility_state != EvidenceEligibilityState.UNAVAILABLE
            else ScientificDataClassification.UNAVAILABLE,
        )
        _add_edge(parent_for_ev, ev_nid, "evaluated_as_evidence")

    for req in requirements:
        req_nid = f"requirement:{req.requirement_id}"
        _add_node(
            req_nid,
            "scientific_requirement",
            f"{req.label} [{req.canonical_state.value}]",
            ScientificDataClassification.MARSCOPE_DERIVED,
        )
        _add_edge(req_nid, q_nid, "constrains_question")
        for sid in req.satisfying_source_ids:
            for m in matched:
                if m.source_id == sid or m.source_id.startswith(sid.split(" ")[0]):
                    _add_edge(f"evidence:{m.match_id}", req_nid, "evaluates_requirement")

    return ProvenanceDependencyGraph(
        output_id=f"discovery_{question.question_id}",
        classification=ScientificDataClassification.MARSCOPE_DERIVED,
        input_datasets=[d.id for d in datasets],
        input_product_ids=[d.product_id for d in datasets],
        method="17_dimension_eligibility_and_evidence_synthesis",
        algorithm_version="2.0.0-p18",
        nodes=list(nodes.values()),
        edges=edges,
        scientific_notes=[
            "Traces every evidence record through source mission, instrument, product, label, raw/processed artifacts, calibration, CRS/registration, requirement, and investigation question.",
        ],
    )
