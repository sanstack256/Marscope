"""
MARSCOPE Instrument-Specific Composition Evidence Adapters
Martian Surface Intelligence & Exploration System

Converts parsed NASA PDS products (APXS, ChemCam MOC/PSV, CheMin RDR5, CRISM, REMS guard)
into candidate CompositionEvidence records and routes every record through the
12-stage validation pipeline before index admission.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.ingestion.pds_label import extract_pds3_metadata
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    GeometryType,
    RejectionRecord,
    SpeciesCategory,
)
from app.science.composition.normalization import canonicalize_unit, normalize_concentration_value
from app.science.composition.species import get_species_by_id, resolve_species_query
from app.science.composition.validation import validate_composition_evidence
from app.science.coordinate_association import CoordinateAssociationService
from app.science.curiosity_parser import CuriosityDataParser


def _deterministic_id(*parts: str) -> str:
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def _evaluate_batch(
    candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]],
) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
    accepted: List[CompositionEvidence] = []
    rejected: List[RejectionRecord] = []
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
    ) -> Tuple[List[CompositionEvidence], List[RejectionRecord]]:
        parsed_rows = CuriosityDataParser.parse_apxs_csv(
            csv_path,
            source_dataset_id=source_dataset_id,
            product_id=product_id,
        )
        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []

        for row in parsed_rows:
            coords = row.get("coordinates")
            loc_verified = coords is not None
            lat = coords["latitude"] if coords else None
            lon = coords["longitude"] if coords else None
            elev = coords.get("elevation_m") if coords else None

            # Oxides (Na2O .. FeO) and Cl (reported directly as elemental wt%)
            for raw_name, m in row.get("oxides_wt_pct", {}).items():
                val = m.get("value")
                err = m.get("error")
                raw_unit = m.get("unit", "wt%")
                res = resolve_species_query(raw_name)
                spec = res.species if res.resolved else get_species_by_id(raw_name)
                canon_id = spec.canonical_id if spec else raw_name
                canon_name = spec.canonical_name if spec else raw_name
                category = spec.category if spec else SpeciesCategory.OXIDE
                ev_type = (
                    EvidenceType.DIRECT_ELEMENT_MEASUREMENT
                    if category == SpeciesCategory.ELEMENT
                    else EvidenceType.OXIDE_COMPOSITION_MEASUREMENT
                )

                # In APXS table, val == 0 and (err is None or err == 0) denotes undetected / below LOD
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                elif val == 0.0 and (err is None or err == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "wt%", "bdl_zero_sentinel"
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
                ev = CompositionEvidence(
                    evidence_id=_deterministic_id(source_dataset_id, product_id, rec_ref, canon_id),
                    source_dataset_id=source_dataset_id,
                    product_id=product_id,
                    source_record_ref=rec_ref,
                    instrument_id="APXS",
                    instrument_name="Alpha Particle X-ray Spectrometer (APXS)",
                    processing_level=f"Calibrated Derived ({row.get('fit_type') or 'RGFit_v2'})",
                    calibration_status="Calibrated oxide & trace concentration with 1-sigma precision error",
                    target_name=row.get("target_name"),
                    sol=row.get("sol"),
                    observation_timestamp_utc=row.get("start_time"),
                    canonical_species_id=canon_id,
                    canonical_species_name=canon_name,
                    species_category=category,
                    raw_species_name=f"{raw_name}_pct",
                    evidence_type=ev_type,
                    evidence_status=status,
                    raw_value=val,
                    raw_unit=raw_unit,
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                    normalization_formula=norm_formula,
                    uncertainty_value=err,
                    uncertainty_unit=raw_unit if err is not None else None,
                    uncertainty_type="1_sigma_precision_error",
                    quality_flag=row.get("quality_flag"),
                    methodology="APXS X-ray spectroscopy calibrated RGFit_v2 elemental/oxide reduction",
                    provenance_url=provenance_url,
                    source_reference=f"PDS4:{product_id}:{rec_ref}",
                    citation="Berger et al. (2022), JGR Planets, DOI:10.1029/2021JE007171",
                    location_verified=loc_verified,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords["crs"] if coords else None,
                    latitude_convention="Planetocentric" if coords else None,
                    longitude_direction="East" if coords else None,
                    coordinate_source=coords["coordinate_source"] if coords else None,
                    coordinate_provenance=coords["coordinate_provenance"] if coords else None,
                    coordinate_uncertainty_m=coords.get("coordinate_uncertainty_m") if coords else None,
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                candidates.append((ev, {"sol": row.get("sol"), "target": row.get("target_name"), "val": val, "err": err}))

            # Trace elements (Ni, Zn, Br in ppm)
            for raw_el, m in row.get("trace_ppm", {}).items():
                val = m.get("value")
                err = m.get("error")
                spec = get_species_by_id(raw_el)
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                elif val == 0.0 and (err is None or err == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "ppm", "bdl_zero_sentinel"
                else:
                    status = EvidenceStatus.MEASURED if loc_verified else EvidenceStatus.UNLOCATED
                    norm_val, norm_unit, norm_formula = (
                        normalize_concentration_value(spec, val, "ppm", target_unit="ppm")
                        if spec
                        else (val, "ppm", "identity (ppm)")
                    )
                rec_ref = f"row:{row['row_index']}:{row['target_name']}:sol{row['sol']}"
                ev = CompositionEvidence(
                    evidence_id=_deterministic_id(source_dataset_id, product_id, rec_ref, raw_el),
                    source_dataset_id=source_dataset_id,
                    product_id=product_id,
                    source_record_ref=rec_ref,
                    instrument_id="APXS",
                    instrument_name="Alpha Particle X-ray Spectrometer (APXS)",
                    processing_level=f"Calibrated Derived ({row.get('fit_type') or 'RGFit_v2'})",
                    calibration_status="Calibrated trace element (ppm) with 1-sigma precision error",
                    target_name=row.get("target_name"),
                    sol=row.get("sol"),
                    observation_timestamp_utc=row.get("start_time"),
                    canonical_species_id=spec.canonical_id if spec else raw_el,
                    canonical_species_name=spec.canonical_name if spec else raw_el,
                    species_category=SpeciesCategory.ELEMENT,
                    raw_species_name=f"{raw_el}_ppm",
                    evidence_type=EvidenceType.DIRECT_ELEMENT_MEASUREMENT,
                    evidence_status=status,
                    raw_value=val,
                    raw_unit="ppm",
                    normalized_value=norm_val,
                    normalized_unit=norm_unit,
                    normalization_formula=norm_formula,
                    uncertainty_value=err,
                    uncertainty_unit="ppm" if err is not None else None,
                    uncertainty_type="1_sigma_precision_error",
                    quality_flag=row.get("quality_flag"),
                    methodology="APXS X-ray spectroscopy calibrated RGFit_v2 trace element quantification",
                    provenance_url=provenance_url,
                    source_reference=f"PDS4:{product_id}:{rec_ref}",
                    citation="Berger et al. (2022), JGR Planets, DOI:10.1029/2021JE007171",
                    location_verified=loc_verified,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords["crs"] if coords else None,
                    latitude_convention="Planetocentric" if coords else None,
                    longitude_direction="East" if coords else None,
                    coordinate_source=coords["coordinate_source"] if coords else None,
                    coordinate_provenance=coords["coordinate_provenance"] if coords else None,
                    coordinate_uncertainty_m=coords.get("coordinate_uncertainty_m") if coords else None,
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                candidates.append((ev, {"sol": row.get("sol"), "target": row.get("target_name"), "val": val, "err": err}))

        return _evaluate_batch(candidates)


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
        rows = CuriosityDataParser.parse_chemcam_moc_table(
            csv_path,
            label_path=label_path,
            coord_service=coord_service,
        )
        moc_pid = csv_path.stem.upper()
        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []

        for r in rows:
            coords = r.get("coordinates")
            loc_verified = coords is not None
            lat = coords.latitude if coords else None
            lon = coords.longitude if coords else None
            elev = coords.elevation_m if coords else None
            rmc_key = coords.rmc_key if coords else None

            # Extract Sol cleanly from filename CCAM02014P3 -> 14 if numeric suffix matches
            sol_num = None
            import re

            m_sol = re.search(r"CCAM\d{2}(\d{3})P", r["product_name"], re.I)
            if m_sol:
                sol_num = int(m_sol.group(1))

            for ox_name, ox_m in r.get("oxides", {}).items():
                val = ox_m.get("value")
                rmsep = ox_m.get("rmsep")
                spec = get_species_by_id(ox_name)
                if val is None:
                    status = EvidenceStatus.MISSING_NULL
                    norm_val, norm_unit, norm_formula = None, None, None
                elif val == 0.0 and (rmsep is None or rmsep == 0.0):
                    status = EvidenceStatus.BELOW_DETECTION_LIMIT
                    norm_val, norm_unit, norm_formula = 0.0, "wt%", "bdl_zero_sentinel"
                else:
                    status = EvidenceStatus.MEASURED if loc_verified else EvidenceStatus.UNLOCATED
                    norm_val, norm_unit, norm_formula = (
                        normalize_concentration_value(spec, val, "wt%")
                        if spec
                        else (val, "wt%", "identity (wt%)")
                    )

                rec_ref = f"moc_row:{r['row_index']}:{r['product_name']}"
                ev = CompositionEvidence(
                    evidence_id=_deterministic_id(source_dataset_id, moc_pid, rec_ref, ox_name),
                    source_dataset_id=source_dataset_id,
                    product_id=r["product_name"].replace(".CSV", ""),
                    source_record_ref=rec_ref,
                    instrument_id="ChemCam_LIBS",
                    instrument_name="Chemistry Camera (ChemCam LIBS)",
                    processing_level="Derived Level 5 (PLS+ICA Combined Oxide Prediction)",
                    calibration_status="Calibrated major oxide wt% with RMSEP uncertainty",
                    target_name=r.get("target_name"),
                    sol=sol_num,
                    rmc=rmc_key,
                    canonical_species_id=spec.canonical_id if spec else ox_name,
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
                    uncertainty_type="RMSEP",
                    quality_flag=f"total_oxide_wt={r.get('total_wt_pct')}",
                    methodology="ChemCam LIBS Multivariate PLS+ICA Oxide Regression (LANL MOC table)",
                    provenance_url=provenance_url,
                    source_reference=f"PDS3:{r['data_set_id']}:{r['product_name']}",
                    location_verified=loc_verified,
                    latitude=lat,
                    longitude_east=lon,
                    elevation_m=elev,
                    crs=coords.crs if coords else None,
                    latitude_convention=coords.latitude_convention if coords else None,
                    longitude_direction=coords.longitude_direction if coords else None,
                    coordinate_source=coords.coordinate_source if coords else None,
                    coordinate_provenance=coords.coordinate_provenance if coords else None,
                    coordinate_uncertainty_m=coords.coordinate_uncertainty_m if coords else None,
                    geometry_type=GeometryType.POINT,
                    min_lat=lat,
                    max_lat=lat,
                    min_lon_east=lon,
                    max_lon_east=lon,
                    geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
                )
                candidates.append((ev, {"product": r["product_name"], "oxide": ox_name, "val": val, "rmsep": rmsep}))

        return _evaluate_batch(candidates)

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
            evidence_id=_deterministic_id(source_dataset_id, pid, "raw_psv_audit"),
            source_dataset_id=source_dataset_id,
            product_id=pid,
            source_record_ref=file_path.name,
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
        parsed = CuriosityDataParser.parse_chemin_min_csv(
            csv_path,
            label_path=label_path,
            coord_service=coord_service,
            extra_structure_dirs=extra_structure_dirs,
        )
        coords = parsed.get("coordinates")
        loc_verified = coords is not None
        lat = coords.latitude if coords else None
        lon = coords.longitude if coords else None
        elev = coords.elevation_m if coords else None
        rmc_key = coords.rmc_key if coords else None
        pid = parsed["product_id"]

        # Extract sample target phrase cleanly from CheMin PDS3 description if present
        target_label = pid
        desc = parsed.get("description") or ""
        if "rocknest" in desc.lower():
            target_label = "Rocknest_Scoop"

        candidates: List[Tuple[CompositionEvidence, Dict[str, Any]]] = []
        for m in parsed.get("minerals", []):
            raw_min = m["mineral"]
            wt_pct = m.get("weight_percent")
            err = m.get("estimated_error")
            res = resolve_species_query(raw_min)
            spec = res.species if res.resolved else None
            canon_id = spec.canonical_id if spec else raw_min.lower()
            canon_name = spec.canonical_name if spec else raw_min
            category = spec.category if spec else SpeciesCategory.MINERAL

            if wt_pct is None:
                status = EvidenceStatus.MISSING_NULL
                norm_val, norm_unit, norm_formula = None, None, None
            elif wt_pct == 0.0 and (err is None or err == 0.0):
                status = EvidenceStatus.BELOW_DETECTION_LIMIT
                norm_val, norm_unit, norm_formula = 0.0, "wt%", "bdl_zero_sentinel"
            else:
                status = EvidenceStatus.DETECTED if loc_verified else EvidenceStatus.UNLOCATED
                norm_val, norm_unit, norm_formula = (
                    normalize_concentration_value(spec, wt_pct, "wt%")
                    if spec
                    else (wt_pct, "wt%", "identity (wt%)")
                )

            rec_ref = f"chemin_row:{m['row_index']}:{raw_min}"
            ev = CompositionEvidence(
                evidence_id=_deterministic_id(source_dataset_id, pid, rec_ref, canon_id),
                source_dataset_id=source_dataset_id,
                product_id=pid,
                source_record_ref=rec_ref,
                instrument_id="CheMin_XRD",
                instrument_name="Chemistry & Mineralogy X-Ray Diffractometer (CheMin)",
                processing_level="Derived Mineral Abundance RDR5 (TOPAS Rietveld)",
                calibration_status="Quantitative crystalline mineral weight% with 1-sigma error",
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
                uncertainty_value=err,
                uncertainty_unit="wt%" if err is not None else None,
                uncertainty_type="TOPAS_Rietveld_1_sigma_error",
                quality_flag="crystalline_phase_wt_pct",
                methodology="CheMin Co K-alpha X-Ray Diffraction TOPAS Rietveld refinement",
                provenance_url=provenance_url,
                source_reference=f"PDS3:{parsed.get('data_set_id')}:{pid}",
                location_verified=loc_verified,
                latitude=lat,
                longitude_east=lon,
                elevation_m=elev,
                crs=coords.crs if coords else None,
                latitude_convention=coords.latitude_convention if coords else None,
                longitude_direction=coords.longitude_direction if coords else None,
                coordinate_source=coords.coordinate_source if coords else None,
                coordinate_provenance=coords.coordinate_provenance if coords else None,
                coordinate_uncertainty_m=coords.coordinate_uncertainty_m if coords else None,
                geometry_type=GeometryType.POINT,
                min_lat=lat,
                max_lat=lat,
                min_lon_east=lon,
                max_lon_east=lon,
                geometry_wkt=f"POINT ({lon} {lat})" if loc_verified else None,
            )
            candidates.append((ev, {"mineral": raw_min, "wt_pct": wt_pct, "err": err}))

        return _evaluate_batch(candidates)


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
            evidence_id=_deterministic_id(source_dataset_id, file_path.stem.upper(), "env_exclusion"),
            source_dataset_id=source_dataset_id,
            product_id=file_path.stem.upper(),
            source_record_ref=file_path.name,
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
        _, _, rej = validate_composition_evidence(ev, raw_payload={"file": file_path.name})
        return [rej] if rej else []
