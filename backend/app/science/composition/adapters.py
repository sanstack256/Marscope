"""
MARSCOPE Instrument-Specific Composition Evidence Adapters
Martian Surface Intelligence & Exploration System

Converts parsed NASA PDS products (APXS, ChemCam MOC/PSV, CheMin RDR5, CRISM, REMS guard)
into candidate CompositionEvidence records and routes every record through the
12-stage validation pipeline before index admission.
"""

import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from app.ingestion.pds_label import extract_pds3_metadata
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    GeometryType,
    LocationSemanticType,
    ParserResult,
    RejectionRecord,
    SpeciesCategory,
    UncertaintyMetadata,
)
from app.science.composition.normalization import canonicalize_unit, normalize_concentration_value
from app.science.composition.species import get_species_by_id, resolve_species_query
from app.science.composition.uncertainty import get_uncertainty_spec
from app.science.composition.validation import (
    EVIDENCE_ID_DETERMINISM_VERSION,
    compute_deterministic_evidence_id,
    validate_composition_evidence,
)
from app.science.coordinate_association import CoordinateAssociationService
from app.science.curiosity_parser import CuriosityDataParser, _sha256_file


def _build_uncertainty_metadata(
    uncertainty_type: Optional[str],
    reported_value: Optional[float],
    reported_unit: Optional[str],
    source_product: str,
    source_definition: Optional[str] = None,
    conversion_history: Optional[List[str]] = None,
    source_field_name: Optional[str] = None,
    source_data_type: Optional[str] = None,
    schema_identity: Optional[str] = None,
    normalized_value: Optional[float] = None,
    normalized_unit: Optional[str] = None,
    is_physical_unit: Optional[bool] = None,
    limitations: Optional[List[str]] = None,
) -> Optional[UncertaintyMetadata]:
    """Construct complete traceable uncertainty semantics without fabricating units or coverage levels."""
    if reported_value is None or not uncertainty_type:
        return None
    spec = get_uncertainty_spec(uncertainty_type)
    inferred_phys = (
        is_physical_unit
        if is_physical_unit is not None
        else bool(reported_unit and reported_unit.strip().lower() in {"wt%", "ppm"})
    )
    return UncertaintyMetadata(
        reported_value=reported_value,
        reported_unit=reported_unit,
        normalized_value=normalized_value if normalized_value is not None else reported_value,
        normalized_unit=normalized_unit if normalized_unit is not None else reported_unit,
        is_physical_unit=inferred_phys,
        source_field_name=source_field_name,
        source_data_type=source_data_type,
        schema_identity=schema_identity,
        uncertainty_type=spec.uncertainty_type,
        statistical_interpretation=spec.statistical_interpretation,
        coverage_confidence_level=spec.coverage_confidence_level,
        source_definition=source_definition or spec.default_source_definition,
        source_product=source_product,
        conversion_history=conversion_history or [],
        limitations=limitations or [],
    )


def _collect_dependency_provenance(
    parsed_res: ParserResult,
    extra_paths: Optional[List[Path]] = None,
) -> Tuple[Dict[str, str], str]:
    """Collect companion schema/reference SHA-256 checksums and unified dependency digest."""
    checksums: Dict[str, str] = {}
    if parsed_res.label_file_path and parsed_res.label_file_checksum:
        checksums[Path(parsed_res.label_file_path).name] = parsed_res.label_file_checksum
    for k, v in (parsed_res.format_file_checksums or {}).items():
        checksums[k] = v
    for p in extra_paths or []:
        if p and p.exists():
            checksums[p.name] = _sha256_file(p)
    digest_src = "|".join(
        [parsed_res.source_file_checksum] + [f"{k}:{v}" for k, v in sorted(checksums.items())]
    )
    return checksums, hashlib.sha256(digest_src.encode("utf-8")).hexdigest()


def _evaluate_batch(
    candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]],
    parser_result: Optional[ParserResult] = None,
    source_dataset_id: str = "",
    product_id: str = "",
    instrument_id: str = "",
) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
    accepted: List[CompositionEvidence] = []
    rejected: List[RejectionRecord] = []

    if parser_result is not None:
        for rr in parser_result.row_rejections:
            ridx = rr.get("row_index", "?")
            reason = str(rr.get("reason") or "Schema row rejection")
            rkey = f"{source_dataset_id}|{product_id}|parser_row:{ridx}|{reason}"
            rejected.append(
                RejectionRecord(
                    rejection_id=hashlib.sha256(rkey.encode("utf-8")).hexdigest()[:20],
                    source_dataset_id=source_dataset_id,
                    product_id=product_id,
                    source_record_ref=f"parser_row:{ridx}",
                    instrument_id=instrument_id,
                    rejection_stage=0,
                    rejection_code="PARSER_ROW_REJECTED",
                    reason=reason,
                    raw_payload=rr,
                )
            )

    for cand, raw_payload in candidates:
        ok, stages, rej = validate_composition_evidence(cand, raw_payload=raw_payload)
        cand.validation_stages = stages
        if ok:
            accepted.append(cand)
        elif rej is not None:
            rejected.append(rej)
    return accepted, rejected


class ApxsEvidenceAdapter:
    """Adapter for NASA PDS4 APXS calibrated oxide (wt%) & trace element (ppm) CSV tables."""

    @staticmethod
    def adapt_csv(
        csv_path: Path,
        source_dataset_id: str = "msl_apxs_supplement_sols_0_3076",
        product_id: str = "DS01_2021JE007171R",
        provenance_url: Optional[str] = None,
        label_path: Optional[Path] = None,
    ) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
        parsed_res = CuriosityDataParser.parse_apxs_csv_with_contract(
            csv_path,
            source_dataset_id=source_dataset_id,
            product_id=product_id,
            label_path=label_path,
            require_xml=True,
        )
        dep_checksums, dep_digest = _collect_dependency_provenance(parsed_res)
        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []

        for row in parsed_res.records:
            coords = row.get("coordinates")
            loc_verified = coords is not None
            lat = coords["latitude"] if coords else None
            lon = coords["longitude"] if coords else None
            elev = coords.get("elevation_m") if coords else None
            loc_semantic = (
                LocationSemanticType(coords["location_semantic_type"])
                if coords and coords.get("location_semantic_type")
                else LocationSemanticType.UNLOCATED
            )

            # Oxides (Na2O .. FeO) and Cl (reported directly as elemental wt%)
            for raw_name, m in row.get("oxides_wt_pct", {}).items():
                val = m.get("value")
                err = m.get("error")
                raw_unit = m.get("unit", "wt%")
                res = resolve_species_query(raw_name)
                spec = res.species if res.resolved else get_species_by_id(raw_name)
                canon_id = spec.canonical_id if spec else f"UNKNOWN:{raw_name}"
                canon_name = spec.canonical_name if spec else raw_name
                category = spec.category if spec else SpeciesCategory.OXIDE
                ev_type = (
                    EvidenceType.DIRECT_ELEMENT_MEASUREMENT
                    if category == SpeciesCategory.ELEMENT
                    else EvidenceType.OXIDE_COMPOSITION_MEASUREMENT
                )

                dl_status: Optional[str] = None
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                    dl_status = "missing_null_in_source"
                elif val == 0.0 and (err is None or err == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "wt%", "zero_with_zero_error_bdl_excluded"
                    dl_status = "reported_zero_with_zero_error_bdl_excluded_no_quantitative_lod_in_source"
                else:
                    status = EvidenceStatus.MEASURED if loc_verified else EvidenceStatus.UNLOCATED
                    try:
                        norm_val, norm_unit, norm_formula = (
                            normalize_concentration_value(spec, val, raw_unit)
                            if spec
                            else (val, canonicalize_unit(raw_unit), "identity")
                        )
                    except Exception:
                        norm_val, norm_unit, norm_formula = None, None, None

                rec_ref = f"row:{row['row_index']}:{row['target_name']}:sol{row['sol']}"
                raw_sp = m.get("source_column") or f"{raw_name}_pct"
                apxs_unc_meta = _build_uncertainty_metadata(
                    "apxs_analytical_precision",
                    err,
                    norm_unit,
                    source_product=product_id,
                    source_definition=m.get("error_definition"),
                )
                ev = CompositionEvidence(
                    evidence_id="pending",
                    determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
                    source_dataset_id=source_dataset_id,
                    product_id=product_id,
                    source_record_ref=rec_ref,
                    source_file_path=parsed_res.source_file_path,
                    source_file_checksum=parsed_res.source_file_checksum,
                    source_artifact_dependency_digest=dep_digest,
                    companion_schema_checksums=dep_checksums,
                    schema_version=parsed_res.schema_version,
                    parser_id=parsed_res.parser_id,
                    parser_version=parsed_res.parser_version,
                    instrument_id="APXS",
                    instrument_name="Alpha Particle X-ray Spectrometer (APXS)",
                    processing_level=f"Calibrated Derived ({row.get('fit_type') or 'RGFit'})",
                    calibration_status="Calibrated oxide concentration with reported analytical precision error",
                    target_name=row.get("target_name"),
                    sol=row.get("sol"),
                    observation_timestamp_utc=row.get("start_time"),
                    canonical_species_id=canon_id,
                    canonical_species_name=canon_name,
                    species_category=category,
                    raw_species_name=raw_sp,
                    evidence_type=ev_type,
                    evidence_status=status,
                    raw_value=val,
                    raw_unit=raw_unit,
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                    normalization_formula=norm_formula,
                    uncertainty_value=err,
                    uncertainty_unit=norm_unit if err is not None else None,
                    uncertainty_type="apxs_analytical_precision" if err is not None else None,
                    uncertainty_semantics=(apxs_unc_meta.statistical_interpretation if apxs_unc_meta else None),
                    uncertainty_metadata=apxs_unc_meta,
                    detection_limit_status=dl_status,
                    quality_flag=row.get("quality_flag"),
                    methodology="APXS X-ray spectroscopy calibrated RGFit elemental/oxide reduction",
                    provenance_url=provenance_url,
                    source_reference=f"PDS4:{product_id}:{rec_ref}",
                    citation="Berger et al. (2022), JGR Planets, DOI:10.1029/2021JE007171",
                    location_verified=loc_verified,
                    location_semantic_type=loc_semantic,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords["crs"] if coords else None,
                    latitude_convention="Planetocentric" if coords else None,
                    longitude_direction="East" if coords else None,
                    coordinate_source=coords["coordinate_source"] if coords else None,
                    coordinate_provenance=coords["coordinate_provenance"] if coords else None,
                    original_coordinate_values=coords.get("original_coordinate_values") if coords else None,
                    original_coordinate_crs=coords.get("original_coordinate_crs") if coords else None,
                    coordinate_transform=coords.get("coordinate_transform") if coords else None,
                    coordinate_transform_params=coords.get("coordinate_transform_params") if coords else None,
                    association_rule_version=coords.get("association_rule_version") if coords else None,
                    coordinate_limitations=coords.get("coordinate_limitations", []) if coords else [],
                    coordinate_uncertainty_m=None,
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                ev.evidence_id = compute_deterministic_evidence_id(ev)
                candidates.append((ev, {"sol": row.get("sol"), "target": row.get("target_name"), "val": val, "err": err}))

            # Trace elements (Ni, Zn, Br in ppm)
            for raw_el, m in row.get("trace_ppm", {}).items():
                val = m.get("value")
                err = m.get("error")
                spec = get_species_by_id(raw_el)
                canon_id = spec.canonical_id if spec else f"UNKNOWN:{raw_el}"
                dl_status = None
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                    dl_status = "missing_null_in_source"
                elif val == 0.0 and (err is None or err == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "ppm", "zero_with_zero_error_bdl_excluded"
                    dl_status = "reported_zero_with_zero_error_bdl_excluded_no_quantitative_lod_in_source"
                else:
                    status = EvidenceStatus.MEASURED if loc_verified else EvidenceStatus.UNLOCATED
                    norm_val, norm_unit, norm_formula = (
                        normalize_concentration_value(spec, val, "ppm", target_unit="ppm")
                        if spec
                        else (val, "ppm", "identity (ppm)")
                    )
                rec_ref = f"row:{row['row_index']}:{row['target_name']}:sol{row['sol']}"
                raw_sp = m.get("source_column") or f"{raw_el}_ppm"
                apxs_trace_unc = _build_uncertainty_metadata(
                    "apxs_analytical_precision",
                    err,
                    norm_unit,
                    source_product=product_id,
                    source_definition=m.get("error_definition"),
                )
                ev = CompositionEvidence(
                    evidence_id="pending",
                    determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
                    source_dataset_id=source_dataset_id,
                    product_id=product_id,
                    source_record_ref=rec_ref,
                    source_file_path=parsed_res.source_file_path,
                    source_file_checksum=parsed_res.source_file_checksum,
                    source_artifact_dependency_digest=dep_digest,
                    companion_schema_checksums=dep_checksums,
                    schema_version=parsed_res.schema_version,
                    parser_id=parsed_res.parser_id,
                    parser_version=parsed_res.parser_version,
                    instrument_id="APXS",
                    instrument_name="Alpha Particle X-ray Spectrometer (APXS)",
                    processing_level=f"Calibrated Derived ({row.get('fit_type') or 'RGFit'})",
                    calibration_status="Calibrated trace element (ppm) with reported analytical precision error",
                    target_name=row.get("target_name"),
                    sol=row.get("sol"),
                    observation_timestamp_utc=row.get("start_time"),
                    canonical_species_id=canon_id,
                    canonical_species_name=spec.canonical_name if spec else raw_el,
                    species_category=SpeciesCategory.ELEMENT,
                    raw_species_name=raw_sp,
                    evidence_type=EvidenceType.DIRECT_ELEMENT_MEASUREMENT,
                    evidence_status=status,
                    raw_value=val,
                    raw_unit="ppm",
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                    normalization_formula=norm_formula,
                    uncertainty_value=err,
                    uncertainty_unit=norm_unit if err is not None else None,
                    uncertainty_type="apxs_analytical_precision" if err is not None else None,
                    uncertainty_semantics=(apxs_trace_unc.statistical_interpretation if apxs_trace_unc else None),
                    uncertainty_metadata=apxs_trace_unc,
                    detection_limit_status=dl_status,
                    quality_flag=row.get("quality_flag"),
                    methodology="APXS X-ray spectroscopy calibrated RGFit trace element quantification",
                    provenance_url=provenance_url,
                    source_reference=f"PDS4:{product_id}:{rec_ref}",
                    citation="Berger et al. (2022), JGR Planets, DOI:10.1029/2021JE007171",
                    location_verified=loc_verified,
                    location_semantic_type=loc_semantic,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords["crs"] if coords else None,
                    latitude_convention="Planetocentric" if coords else None,
                    longitude_direction="East" if coords else None,
                    coordinate_source=coords["coordinate_source"] if coords else None,
                    coordinate_provenance=coords["coordinate_provenance"] if coords else None,
                    original_coordinate_values=coords.get("original_coordinate_values") if coords else None,
                    original_coordinate_crs=coords.get("original_coordinate_crs") if coords else None,
                    coordinate_transform=coords.get("coordinate_transform") if coords else None,
                    coordinate_transform_params=coords.get("coordinate_transform_params") if coords else None,
                    association_rule_version=coords.get("association_rule_version") if coords else None,
                    coordinate_limitations=coords.get("coordinate_limitations", []) if coords else [],
                    coordinate_uncertainty_m=None,
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                ev.evidence_id = compute_deterministic_evidence_id(ev)
                candidates.append((ev, {"sol": row.get("sol"), "target": row.get("target_name"), "val": val, "err": err}))

        return _evaluate_batch(
            candidates,
            parser_result=parsed_res,
            source_dataset_id=source_dataset_id,
            product_id=product_id,
            instrument_id="APXS",
        )


class ChemCamEvidenceAdapter:
    """
    Adapter for MSL ChemCam products:
      - Validated MOC (Multivariant Oxides Composition) tables -> calibrated oxide wt% evidence.
      - Raw CHEMCAM-PSV passive spectra -> explicitly rejected into RejectionRecords (never element claims).
    """

    @staticmethod
    def adapt_moc_csv(
        csv_path: Path,
        label_path: Optional[Path] = None,
        source_dataset_id: str = "msl_chemcam_moc",
        coord_service: Optional[CoordinateAssociationService] = None,
        provenance_url: Optional[str] = None,
    ) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
        parsed_res = CuriosityDataParser.parse_chemcam_moc_table_with_contract(
            csv_path,
            label_path=label_path,
            coord_service=coord_service,
        )
        dep_checksums, dep_digest = _collect_dependency_provenance(
            parsed_res,
            [coord_service.waypoints_path] if coord_service and coord_service.waypoints_path else None,
        )
        moc_pid = csv_path.stem.upper()
        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []

        for r in parsed_res.records:
            coords = r.get("coordinates")
            loc_verified = coords is not None
            lat = coords.latitude if coords else None
            lon = coords.longitude if coords else None
            elev = coords.elevation_m if coords else None
            rmc_key = coords.rmc_key if coords else None
            loc_semantic = coords.location_semantic_type if coords else LocationSemanticType.UNLOCATED

            sol_num = None
            m_sol = re.search(r"CCAM\d{2}(\d{3})P", r["product_name"], re.I)
            if m_sol:
                sol_num = int(m_sol.group(1))

            for ox_name, ox_m in r.get("oxides", {}).items():
                val = ox_m.get("value")
                rmsep = ox_m.get("rmsep")
                shots_stdev = ox_m.get("shots_stdev")
                spec = get_species_by_id(ox_name)
                canon_id = spec.canonical_id if spec else f"UNKNOWN:{ox_name}"
                dl_status: Optional[str] = None
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                    dl_status = "missing_null_in_source"
                elif val == 0.0 and (rmsep is None or rmsep == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "wt%", "zero_with_zero_rmsep_excluded"
                    dl_status = "reported_zero_with_zero_rmsep_excluded_no_quantitative_lod_in_source"
                else:
                    status = EvidenceStatus.MEASURED if loc_verified else EvidenceStatus.UNLOCATED
                    norm_val, norm_unit, norm_formula = (
                        normalize_concentration_value(spec, val, "wt%")
                        if spec
                        else (val, "wt%", "identity (wt%)")
                    )

                rec_ref = f"moc_row:{r['row_index']}:{r['product_name']}"
                cc_unc = _build_uncertainty_metadata(
                    "chemcam_pls_rmsep",
                    rmsep,
                    "wt%",
                    source_product=moc_pid,
                    source_definition=ox_m.get("rmsep_definition"),
                )
                cc_sec_unc = _build_uncertainty_metadata(
                    "chemcam_shots_stdev",
                    shots_stdev,
                    "wt%",
                    source_product=moc_pid,
                    source_definition=ox_m.get("shots_stdev_definition"),
                )
                ev = CompositionEvidence(
                    evidence_id="pending",
                    determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
                    source_dataset_id=source_dataset_id,
                    product_id=r["product_name"].replace(".CSV", ""),
                    source_record_ref=rec_ref,
                    source_file_path=parsed_res.source_file_path,
                    source_file_checksum=parsed_res.source_file_checksum,
                    source_artifact_dependency_digest=dep_digest,
                    companion_schema_checksums=dep_checksums,
                    schema_version=parsed_res.schema_version,
                    parser_id=parsed_res.parser_id,
                    parser_version=parsed_res.parser_version,
                    instrument_id="ChemCam_LIBS",
                    instrument_name="Chemistry Camera (ChemCam LIBS)",
                    processing_level="Derived Level 5 (PLS+ICA Combined Oxide Prediction)",
                    calibration_status="Calibrated major oxide wt% with RMSEP & shot-to-shot stdev",
                    target_name=r.get("target_name"),
                    sol=sol_num,
                    rmc=rmc_key,
                    canonical_species_id=canon_id,
                    canonical_species_name=spec.canonical_name if spec else ox_name,
                    species_category=SpeciesCategory.OXIDE,
                    raw_species_name=ox_name,
                    evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
                    evidence_status=status,
                    raw_value=val,
                    raw_unit="wt%",
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                    normalization_formula=norm_formula,
                    uncertainty_value=rmsep,
                    uncertainty_unit="wt%" if rmsep is not None else None,
                    uncertainty_type="chemcam_pls_rmsep" if rmsep is not None else None,
                    uncertainty_semantics=(cc_unc.statistical_interpretation if cc_unc else None),
                    uncertainty_metadata=cc_unc,
                    secondary_uncertainty_value=shots_stdev,
                    secondary_uncertainty_unit="wt%" if shots_stdev is not None else None,
                    secondary_uncertainty_type="chemcam_shots_stdev" if shots_stdev is not None else None,
                    secondary_uncertainty_metadata=cc_sec_unc,
                    detection_limit_status=dl_status,
                    quality_flag=f"total_oxide_wt={r.get('total_wt_pct')}" if r.get("total_wt_pct") is not None else None,
                    methodology="ChemCam LIBS Multivariate PLS+ICA Oxide Regression (LANL MOC table)",
                    provenance_url=provenance_url,
                    source_reference=f"PDS3:{r['data_set_id']}:{r['product_name']}",
                    citation="Clegg et al. (2017), Spectrochimica Acta B; LANL ChemCam PDS3 MOC RDR",
                    location_verified=loc_verified,
                    location_semantic_type=loc_semantic,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords.crs if coords else None,
                    latitude_convention=coords.latitude_convention if coords else None,
                    longitude_direction=coords.longitude_direction if coords else None,
                    coordinate_source=coords.coordinate_source if coords else None,
                    coordinate_provenance=coords.coordinate_provenance if coords else None,
                    original_coordinate_values=coords.original_coordinate_values if coords else None,
                    original_coordinate_crs=coords.original_coordinate_crs if coords else None,
                    coordinate_transform=coords.coordinate_transform if coords else None,
                    coordinate_transform_params=coords.coordinate_transform_params if coords else None,
                    waypoint_id=coords.waypoint_id if coords else None,
                    association_rule_version=coords.association_rule_version if coords else None,
                    coordinate_limitations=coords.coordinate_limitations if coords else [],
                    coordinate_uncertainty_m=coords.coordinate_uncertainty_m if coords else None,
                    instrument_standoff_m=coords.instrument_standoff_m if coords else r.get("distance_m"),
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                ev.evidence_id = compute_deterministic_evidence_id(ev)
                candidates.append((ev, {"product": r["product_name"], "oxide": ox_name, "val": val, "rmsep": rmsep, "shots_stdev": shots_stdev}))

        return _evaluate_batch(
            candidates,
            parser_result=parsed_res,
            source_dataset_id=source_dataset_id,
            product_id=moc_pid,
            instrument_id="ChemCam_LIBS",
        )

    @staticmethod
    def audit_raw_psv_as_non_compositional(
        file_path: Path,
        label_path: Optional[Path] = None,
        source_dataset_id: str = "msl_chemcam_sol00010_psv",
    ) -> List[RejectionRecord]:
        """
        Explicitly audit raw CHEMCAM-PSV passive spectrum files through validation stage 3
        so audit logs record why raw DN passive spectra do not generate mineral/element claims.
        """
        meta = extract_pds3_metadata(label_path) if label_path and label_path.exists() else {}
        pid = str(meta.get("product_id") or file_path.stem.upper())
        ev = CompositionEvidence(
            evidence_id="pending",
            determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
            source_dataset_id=source_dataset_id,
            product_id=pid,
            source_record_ref=file_path.name,
            source_file_path=str(file_path),
            source_file_checksum=_sha256_file(file_path) if file_path.exists() else "missing",
            schema_version="pds3_psv",
            parser_id="chemcam_psv_audit",
            parser_version="2.0.0",
            instrument_id="ChemCam_PSV",
            instrument_name="ChemCam Passive Spectrometer",
            processing_level="Level 1 Passive Spectrum (MSL:LASER_MODE=NO)",
            calibration_status=str(meta.get("product_type") or "CHEMCAM-PSV DIGITAL_NUMBER"),
            sol=meta.get("planet_day_number"),
            canonical_species_id="SiO2",
            canonical_species_name="Uncalibrated Spectrum Placeholder",
            species_category=SpeciesCategory.OXIDE,
            raw_species_name="CHANNEL_INTENSITY",
            evidence_type=EvidenceType.UNINTERPRETED_SPECTRAL_RECORD,
            evidence_status=EvidenceStatus.REJECTED,
            raw_value=None,
            raw_unit=str(meta.get("units") or "DIGITAL_NUMBER"),
            methodology="Passive reflectance intensity without calibrated mineral/element inversion",
            source_reference=f"PDS3:{pid}",
        )
        ev.evidence_id = compute_deterministic_evidence_id(ev)
        _, _, rej = validate_composition_evidence(ev, raw_payload={"file": file_path.name})
        return [rej] if rej else []


class CheMinEvidenceAdapter:
    """Adapter for NASA PDS3 CheMin quantitative Rietveld XRD mineral abundance tables (RDR5)."""

    @staticmethod
    def adapt_rdr5_csv(
        csv_path: Path,
        label_path: Optional[Path] = None,
        source_dataset_id: str = "msl_chemin_rdr5",
        coord_service: Optional[CoordinateAssociationService] = None,
        provenance_url: Optional[str] = None,
        extra_structure_dirs: Optional[List[Path]] = None,
    ) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
        parsed_res = CuriosityDataParser.parse_chemin_min_csv_with_contract(
            csv_path,
            label_path=label_path,
            coord_service=coord_service,
            extra_structure_dirs=extra_structure_dirs,
            require_label=True,
        )
        dep_checksums, dep_digest = _collect_dependency_provenance(
            parsed_res,
            [coord_service.waypoints_path] if coord_service and coord_service.waypoints_path else None,
        )
        parsed = parsed_res.records[0]
        coords = parsed.get("coordinates")
        loc_verified = coords is not None
        lat = coords.latitude if coords else None
        lon = coords.longitude if coords else None
        elev = coords.elevation_m if coords else None
        rmc_key = coords.rmc_key if coords else None
        loc_semantic = coords.location_semantic_type if coords else LocationSemanticType.UNLOCATED
        pid = parsed["product_id"]

        target_label = pid
        desc = parsed.get("description") or ""
        if "rocknest" in desc.lower():
            target_label = "Rocknest_Scoop"

        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []
        for m in parsed.get("minerals", []):
            raw_min = m["mineral"]
            wt_pct = m.get("weight_percent")
            err = m.get("estimated_error")
            norm_err = m.get("normalized_error", err)
            raw_err_unit = m.get("error_schema_unit") or m.get("error_unit")
            norm_err_unit = m.get("normalized_error_unit")
            err_is_phys = bool(m.get("error_is_physical_unit", False))
            err_sem = m.get("error_semantics") or "chemin_estimated_error_unspecified_sigma"
            err_def = m.get("error_definition")
            chemin_unc_type = (
                "chemin_rietveld_2sigma"
                if err_sem == "chemin_rietveld_2sigma"
                else "chemin_estimated_error_unspecified_sigma"
            )
            chemin_unc = _build_uncertainty_metadata(
                chemin_unc_type,
                err,
                raw_err_unit,
                source_product=pid,
                source_definition=err_def,
                conversion_history=list(m.get("error_conversion_history") or []),
                source_field_name=m.get("error_schema_field"),
                source_data_type=m.get("error_schema_data_type"),
                schema_identity=m.get("schema_identity") or parsed_res.schema_version,
                normalized_value=norm_err,
                normalized_unit=norm_err_unit,
                is_physical_unit=err_is_phys,
                limitations=list(m.get("error_limitations") or []),
            )
            res = resolve_species_query(raw_min)
            spec = res.species if res.resolved else None
            # Never invent/guess canonical species IDs for unknown mineral rows
            canon_id = spec.canonical_id if spec else f"UNKNOWN:{raw_min}"
            canon_name = spec.canonical_name if spec else raw_min
            category = spec.category if spec else SpeciesCategory.MINERAL

            dl_status: Optional[str] = None
            if wt_pct is None:
                status = EvidenceStatus.MISSING_NULL
                norm_val, norm_unit, norm_formula = None, None, None
                dl_status = "missing_null_in_source"
            elif wt_pct == 0.0 and (err is None or err == 0.0):
                status = EvidenceStatus.BELOW_DETECTION_LIMIT
                norm_val, norm_unit, norm_formula = 0.0, "wt%", "zero_with_zero_error_bdl_excluded"
                dl_status = "reported_zero_with_zero_error_bdl_excluded_no_quantitative_lod_in_source"
            else:
                status = EvidenceStatus.DETECTED if loc_verified else EvidenceStatus.UNLOCATED
                norm_val, norm_unit, norm_formula = (
                    normalize_concentration_value(spec, wt_pct, "wt%")
                    if spec
                    else (wt_pct, "wt%", "identity (wt%)")
                )

            rec_ref = f"chemin_row:{m['row_index']}:{raw_min}"
            ev = CompositionEvidence(
                evidence_id="pending",
                determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
                source_dataset_id=source_dataset_id,
                product_id=pid,
                source_record_ref=rec_ref,
                source_file_path=parsed_res.source_file_path,
                source_file_checksum=parsed_res.source_file_checksum,
                source_artifact_dependency_digest=dep_digest,
                companion_schema_checksums=dep_checksums,
                schema_version=parsed_res.schema_version,
                parser_id=parsed_res.parser_id,
                parser_version=parsed_res.parser_version,
                instrument_id="CheMin_XRD",
                instrument_name="Chemistry & Mineralogy X-Ray Diffractometer (CheMin)",
                processing_level="Derived Mineral Abundance RDR5 (TOPAS Rietveld)",
                calibration_status=(
                    "Quantitative crystalline mineral weight% with 2-sigma TOPAS Rietveld error"
                    if chemin_unc_type == "chemin_rietveld_2sigma"
                    else "Quantitative crystalline mineral weight% with ESTIMATED_ERROR (sigma unspecified in label)"
                ),
                target_name=target_label,
                sol=parsed.get("sol"),
                observation_timestamp_utc=parsed.get("start_time"),
                rmc=rmc_key,
                canonical_species_id=canon_id,
                canonical_species_name=canon_name,
                species_category=category,
                raw_species_name=raw_min,
                evidence_type=EvidenceType.DIRECT_MINERAL_DETECTION,
                evidence_status=status,
                raw_value=wt_pct,
                raw_unit="wt%",
                normalized_value=norm_val,
                normalized_unit=norm_unit,
                normalization_formula=norm_formula,
                uncertainty_value=norm_err if err is not None else None,
                uncertainty_unit=norm_err_unit if err is not None else None,
                uncertainty_type=chemin_unc_type if err is not None else None,
                uncertainty_semantics=(chemin_unc.statistical_interpretation if chemin_unc else None),
                uncertainty_metadata=chemin_unc,
                detection_limit_status=dl_status,
                quality_flag="crystalline_phase_wt_pct",
                methodology="CheMin Co K-alpha X-Ray Diffraction TOPAS Rietveld refinement",
                provenance_url=provenance_url,
                source_reference=f"PDS3:{parsed.get('data_set_id')}:{pid}",
                citation="Blake et al., MSL CheMin PDS3 RDR5 Mineral Abundance Table",
                location_verified=loc_verified,
                location_semantic_type=loc_semantic,
                latitude=lat,
                longitude_east=lon,
                elevation_m=elev,
                crs=coords.crs if coords else None,
                latitude_convention=coords.latitude_convention if coords else None,
                longitude_direction=coords.longitude_direction if coords else None,
                coordinate_source=coords.coordinate_source if coords else None,
                coordinate_provenance=coords.coordinate_provenance if coords else None,
                original_coordinate_values=coords.original_coordinate_values if coords else None,
                original_coordinate_crs=coords.original_coordinate_crs if coords else None,
                coordinate_transform=coords.coordinate_transform if coords else None,
                coordinate_transform_params=coords.coordinate_transform_params if coords else None,
                waypoint_id=coords.waypoint_id if coords else None,
                association_rule_version=coords.association_rule_version if coords else None,
                coordinate_limitations=coords.coordinate_limitations if coords else [],
                coordinate_uncertainty_m=coords.coordinate_uncertainty_m if coords else None,
                geometry_type=GeometryType.POINT,
                min_lat=lat,
                max_lat=lat,
                min_lon_east=lon,
                max_lon_east=lon,
                geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
            )
            ev.evidence_id = compute_deterministic_evidence_id(ev)
            candidates.append((ev, {"mineral": raw_min, "wt_pct": wt_pct, "err": err}))

        return _evaluate_batch(
            candidates,
            parser_result=parsed_res,
            source_dataset_id=source_dataset_id,
            product_id=pid,
            instrument_id="CheMin_XRD",
        )


class CrismEvidenceAdapter:
    """
    Strict CRISM orbital mineral indicator adapter.
    Reports explicit unavailable state unless verified, localized CRISM mineral products exist locally.
    Never infers or fabricates CRISM detections from ODE product discovery alone.
    """

    @staticmethod
    def check_availability(raw_dir: Path, processed_dir: Path) -> Tuple[str, Optional[Path]]:
        for base in (processed_dir, raw_dir):
            if base.exists():
                matches = list(base.glob("*crism*mineral*.csv")) + list(base.glob("*crism*mineral*.json"))
                if matches:
                    return "available_verified_mineral_table", matches[0]
        return "unavailable_no_validated_mineral_cube", None


class EnvironmentalExclusionAdapter:
    """Audits non-compositional REMS/RAD files so audit logs prove explicit exclusion."""

    @staticmethod
    def audit_non_composition_file(
        file_path: Path,
        instrument_id: str = "REMS",
        source_dataset_id: str = "msl_rems_sol00010_adr",
    ) -> List[RejectionRecord]:
        ev = CompositionEvidence(
            evidence_id="pending",
            determinism_version=EVIDENCE_ID_DETERMINISM_VERSION,
            source_dataset_id=source_dataset_id,
            product_id=file_path.stem.upper(),
            source_record_ref=file_path.name,
            source_file_path=str(file_path),
            source_file_checksum=_sha256_file(file_path) if file_path.exists() else "missing",
            schema_version="pds3_rems",
            parser_id="rems_exclusion_audit",
            parser_version="2.0.0",
            instrument_id=instrument_id,
            instrument_name="Rover Environmental Monitoring Station (REMS)",
            processing_level="Environmental Telemetry",
            calibration_status="Non-compositional meteorological/ancillary record",
            canonical_species_id="SiO2",
            canonical_species_name="Non-Compositional Record",
            species_category=SpeciesCategory.OXIDE,
            raw_species_name="METEOROLOGY_TELEMETRY",
            evidence_type=EvidenceType.UNINTERPRETED_SPECTRAL_RECORD,
            evidence_status=EvidenceStatus.REJECTED,
            raw_value=None,
            raw_unit="Pa",
            methodology="Meteorological/Ancillary observation (excluded from geochemical index)",
            source_reference=f"PDS3:{file_path.stem.upper()}",
        )
        ev.evidence_id = compute_deterministic_evidence_id(ev)
        _, _, rej = validate_composition_evidence(ev, raw_payload={"file": file_path.name})
        return [rej] if rej else []
