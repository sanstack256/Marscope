"""
Curiosity (MSL) Verified Observation Parsers
Martian Surface Intelligence & Exploration System

Parses official NASA PDS3 & PDS4 MSL instrument products using their actual
documented labels (.LBL / .XML) and external format schemas (.FMT):
  - ChemCam Passive Reflectance (CHEMCAM-PSV)
  - ChemCam LIBS Calibrated Spectra (CHEMCAM-CCS / CHEMCAM-RDR)
  - ChemCam Multivariant Oxides Composition (CHEMCAM-MOC)
  - APXS Calibrated Oxide & Trace Element Tables
  - CheMin Quantitative Mineralogy (CHEMIN_MIN RDR5)
  - REMS Environmental & Ancillary Tables (MODRDR / ENVRDR / ADR)

Never fabricates coordinates or element/mineral identifications.
"""

import csv
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
from app.ingestion.pds_label import (
    extract_pds3_metadata,
    load_pds3_columns_and_structure,
    parse_pds3_pointer,
    parse_pds4_table_delimited,
)
from app.schemas.observation import Observation, ObservationCoordinates
from app.science.composition.models import (
    LocationSemanticType,
    ParserFieldMapping,
    ParserResult,
)
from app.science.coordinate_association import (
    CoordinateAssociationService,
    gale_eqc_meters_to_lat_lon,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class MalformedObservationError(ValueError):
    """Raised when an observation artifact is empty, malformed, or lacks schema validity."""


_NULL_TOKENS = {"", "NULL", "UNK", "UNKNOWN", "N/A", "NA", "NAN", "-9999", "-9999.0", "-999.0"}


def _safe_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().strip('"').strip("'")
    if s.upper() in _NULL_TOKENS:
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except ValueError:
        return None


def _slice_fixed_width(line: str, start_byte_1based: int, byte_len: int) -> str:
    start = max(0, start_byte_1based - 1)
    return line[start : start + byte_len].strip()


def _resolve_companion_label(file_path: Path, explicit_label: Optional[Path]) -> Optional[Path]:
    if explicit_label and explicit_label.exists():
        return explicit_label
    for ext in (".lbl", ".LBL"):
        cand = file_path.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def _coords_to_schema(assoc) -> Optional[ObservationCoordinates]:
    if assoc is None:
        return None
    return ObservationCoordinates(
        latitude=assoc.latitude,
        longitude=assoc.longitude,
        elevation_m=assoc.elevation_m,
    )


class CuriosityDataParser:
    @staticmethod
    def parse_chemcam_psv_file(
        file_path: Path,
        sol: Optional[int] = None,
        label_path: Optional[Path] = None,
        dataset_id: Optional[str] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
    ) -> Observation:
        """
        Parse a ChemCam product (.TAB or .CSV) using its companion PDS3 .LBL schema.
        Distinguishes CHEMCAM-PSV (passive reflectance digital numbers) from CHEMCAM-CCS/RDR (LIBS),
        preserves full channel coverage (no 100-row truncation), and resolves coordinates strictly
        via documented RMC lookup when available.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"ChemCam data file missing: {file_path}")

        lbl_file = _resolve_companion_label(file_path, label_path)
        pds_meta: Dict[str, Any] = {}
        columns: List[Dict[str, Any]] = []
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            _, columns = load_pds3_columns_and_structure(
                lbl_file, table_object_names=("TABLE", "SPREADSHEET")
            )

        product_type = str(pds_meta.get("product_type") or "").upper()
        laser_mode = str(pds_meta.get("laser_mode") or "").upper()
        resolved_sol = sol if sol is not None else pds_meta.get("planet_day_number")
        product_id = str(pds_meta.get("product_id") or file_path.stem.upper())

        is_psv = (
            product_type == "CHEMCAM-PSV"
            or laser_mode == "NO"
            or ("psv" in file_path.stem.lower() and "ccs" not in file_path.stem.lower())
        )

        # Resolve coordinates strictly from PDS metadata / RMC waypoints (never fabricate defaults or uncertainty)
        assoc_coords = (
            coord_service.resolve_from_pds_metadata(pds_meta, product_id=product_id, uncertainty_m=None)
            if coord_service is not None
            else None
        )
        obs_coords = _coords_to_schema(assoc_coords)

        raw_bytes = file_path.read_bytes()
        text = raw_bytes.decode("utf-8", errors="replace")
        pointers = pds_meta.get("pointers") or {}

        # Determine data start offset according to ^TABLE or ^SPREADSHEET
        lines: List[str]
        if is_psv:
            tbl_ptr = pointers.get("^TABLE")
            if tbl_ptr and tbl_ptr.get("unit") == "BYTES":
                lines = raw_bytes[max(0, tbl_ptr["offset"] - 1) :].decode("utf-8", errors="replace").splitlines()
            elif tbl_ptr and tbl_ptr.get("unit") == "RECORDS":
                all_lines = text.splitlines()
                start_idx = max(0, int(tbl_ptr["offset"]) - 1)
                lines = all_lines[start_idx:]
            else:
                lines = text.splitlines()

            # Read full column of intensities according to documented TABLE columns or single-column TAB
            intensities: List[float] = []
            col_name = columns[0].get("NAME", "CHANNEL_INTENSITY") if columns else "CHANNEL_INTENSITY"
            col_unit = columns[0].get("UNIT") if columns else None
            resolved_unit = str(col_unit or pds_meta.get("units") or "DIGITAL_NUMBER")

            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                val = _safe_float(stripped.split(",")[0].split()[0])
                if val is not None:
                    intensities.append(val)

            if not intensities:
                raise MalformedObservationError(
                    f"ChemCam PSV artifact '{file_path.name}' contains zero valid intensity channels."
                )

            companion_wave = None
            if columns:
                desc = str(columns[0].get("DESCRIPTION") or "")
                if "CCAM_DEFAULT_WAVE.TAB" in desc.upper():
                    companion_wave = "CCAM_DEFAULT_WAVE.TAB"

            return Observation(
                observation_id=f"CHEMCAM_PSV_{product_id}",
                dataset_id=dataset_id or f"msl_chemcam_{product_id.lower()}",
                mission="Mars Science Laboratory (MSL)",
                instrument="Chemistry Camera (ChemCam Passive Reflectance PSV)",
                observation_timestamp=None,
                sol=resolved_sol,
                location=obs_coords,
                crs=assoc_coords.crs if assoc_coords else None,
                measurement_type="passive_reflectance_spectrum_dn",
                measurement_value={
                    "product_type": product_type or "CHEMCAM-PSV",
                    "laser_mode": laser_mode or "NO",
                    "column_name": str(col_name),
                    "total_channels_parsed": len(intensities),
                    "min_digital_number": round(min(intensities), 6),
                    "max_digital_number": round(max(intensities), 6),
                    "mean_digital_number": round(sum(intensities) / len(intensities), 6),
                    "companion_wavelength_table": companion_wave,
                    "composition_claim": "none_uncalibrated_passive_dn",
                },
                units=resolved_unit,
                processing_level="Level 1 Passive Spectrum (MSL:LASER_MODE=NO)",
                calibration_status="Passive digital numbers (NOT calibrated LIBS elemental composition)",
                quality_flags=[
                    "verified_pds3_psv_dn_non_libs" if obs_coords is not None else "verified_pds3_psv_dn_unlocated"
                ],
                original_source_reference=product_id,
                known_limitations=[
                    f"Parsed {len(intensities)} channels from {file_path.name}; uncalibrated DIGITAL_NUMBER cannot establish element or mineral detections.",
                    *(
                        [f"Associated coordinates via {assoc_coords.coordinate_source}."]
                        if assoc_coords
                        else ["Coordinates absent in PDS3 label or RMC lookup; preserved as None."]
                    ),
                ],
            )

        # LIBS CCS / RDR spectral CSV path
        sp_ptr = pointers.get("^SPREADSHEET")
        if sp_ptr and sp_ptr.get("unit") == "BYTES":
            body = raw_bytes[max(0, int(sp_ptr["offset"]) - 1) :].decode("utf-8", errors="replace")
            candidate_lines = body.splitlines()
        elif sp_ptr and sp_ptr.get("unit") == "RECORDS":
            candidate_lines = text.splitlines()[max(0, int(sp_ptr["offset"]) - 1) :]
        else:
            all_lines = text.splitlines()
            start_idx = 0
            for idx, ln in enumerate(all_lines):
                if "begin processed spectral data" in ln.lower():
                    start_idx = idx + 1
                    break
            candidate_lines = all_lines[start_idx:]

        wavelengths: List[float] = []
        mean_intensities: List[float] = []
        header_cols: List[str] = []

        for ln in candidate_lines:
            stripped = ln.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = [p.strip() for p in stripped.split(",")]
            first_val = _safe_float(parts[0]) if parts else None
            if first_val is None:
                # Could be CSV header line
                if not header_cols and any(tok.isalpha() for tok in "".join(parts)):
                    header_cols = parts
                continue
            second_val = _safe_float(parts[1]) if len(parts) > 1 else None
            wavelengths.append(first_val)
            if second_val is not None:
                mean_intensities.append(second_val)

        if not wavelengths:
            raise MalformedObservationError(
                f"ChemCam LIBS artifact '{file_path.name}' yielded zero valid spectral channels."
            )

        libs_unit = str(pds_meta.get("units") or "photons / (s * cm^2 * sr * nm)")
        if libs_unit == "unknown":
            libs_unit = "photons / (s * cm^2 * sr * nm)"

        summary: Dict[str, Any] = {
            "product_type": product_type or "CHEMCAM-CCS",
            "sampled_channel_count": len(wavelengths),
            "min_wavelength_nm": min(wavelengths),
            "max_wavelength_nm": max(wavelengths),
            "min_intensity": min(mean_intensities) if mean_intensities else None,
            "max_intensity": max(mean_intensities) if mean_intensities else None,
            "has_header_columns": bool(header_cols),
        }

        return Observation(
            observation_id=f"CHEMCAM_LIBS_{product_id}",
            dataset_id=dataset_id or f"msl_chemcam_{product_id.lower()}",
            mission="Mars Science Laboratory (MSL)",
            instrument="Chemistry Camera (ChemCam LIBS)",
            observation_timestamp=None,
            sol=resolved_sol,
            location=obs_coords,
            crs=assoc_coords.crs if assoc_coords else None,
            measurement_type="libs_spectral_emission",
            measurement_value=summary,
            units=libs_unit,
            processing_level="Calibrated (CCS/RDR)",
            calibration_status="Dark-subtracted, continuum-removed LIBS spectral emission",
            quality_flags=[
                "verified_pds3_libs_spectra" if obs_coords else "verified_pds3_libs_unlocated"
            ],
            original_source_reference=product_id,
            known_limitations=[
                f"Parsed full {len(wavelengths)} spectral channels from {file_path.name}.",
                *(
                    [f"Associated coordinates via {assoc_coords.coordinate_source}."]
                    if assoc_coords
                    else ["Coordinates absent in source artifact; preserved as None."]
                ),
            ],
        )

    @staticmethod
    def parse_chemcam_moc_table_with_contract(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
    ) -> ParserResult:
        """
        Schema-driven parser for NASA PDS3 ChemCam Multivariant Oxides Composition (MOC) tables.
        Resolves every oxide, RMSEP, shots_stdev, sum_of_oxides, and distance_to_target column
        strictly from PDS3 OBJECT = FIELD schema + CSV header verification (never hardcoded column tuples).
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"ChemCam MOC table not found: {csv_path}")

        file_checksum = _sha256_file(csv_path)
        lbl_file = _resolve_companion_label(csv_path, label_path)
        lbl_checksum = _sha256_file(lbl_file) if lbl_file and lbl_file.exists() else None
        fields: List[Dict[str, Any]] = []
        pds_meta: Dict[str, Any] = {}
        data_offset_bytes = 0
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            _, fields = load_pds3_columns_and_structure(
                lbl_file, table_object_names=("SPREADSHEET",), strict_structure=True
            )
            sp_ptr = (pds_meta.get("pointers") or {}).get("^SPREADSHEET")
            if sp_ptr and sp_ptr.get("unit") == "BYTES":
                data_offset_bytes = max(0, int(sp_ptr["offset"]) - 1)
            elif sp_ptr and sp_ptr.get("unit") == "RECORDS":
                data_offset_bytes = 0
        dep_digest = hashlib.sha256(f"{file_checksum}|{lbl_checksum or ''}".encode("utf-8")).hexdigest()

        raw_bytes = csv_path.read_bytes()
        text = raw_bytes[data_offset_bytes:].decode("utf-8", errors="replace")
        all_csv_rows = list(csv.reader(text.splitlines()))
        if not all_csv_rows:
            raise MalformedObservationError(f"ChemCam MOC table '{csv_path.name}' contains zero rows.")

        ordered_fields: List[Dict[str, Any]] = []
        if fields:
            def _field_order_key(f: Dict[str, Any]) -> int:
                for k in ("FIELD_NUMBER", "COLUMN_NUMBER"):
                    if f.get(k) is not None and str(f.get(k)).isdigit():
                        return int(f[k])
                return 999999

            has_num = all(_field_order_key(f) < 999999 for f in fields)
            ordered_fields = sorted(fields, key=_field_order_key) if has_num else list(fields)

        header_row_idx: Optional[int] = None
        header_cells: List[str] = []
        for idx, r in enumerate(all_csv_rows[:15]):
            joined = ",".join(r).lower()
            if ("file" in joined or "product_name" in joined) and ("target" in joined or "sio2" in joined):
                header_row_idx = idx
                header_cells = [c.strip() for c in r]
                break

        if not ordered_fields and not header_cells:
            raise MalformedObservationError(
                f"ChemCam MOC table '{csv_path.name}' lacks both companion PDS3 .LBL FIELD schema and explicit CSV header."
            )

        known_oxides = ("SIO2", "TIO2", "AL2O3", "FEOT", "MGO", "CAO", "NA2O", "K2O", "MNO")
        oxide_canonical_case = {
            "SIO2": "SiO2",
            "TIO2": "TiO2",
            "AL2O3": "Al2O3",
            "FEOT": "FeOT",
            "MGO": "MgO",
            "CAO": "CaO",
            "NA2O": "Na2O",
            "K2O": "K2O",
            "MNO": "MnO",
        }
        field_mappings: List[ParserFieldMapping] = []
        col_lookup: Dict[str, int] = {}

        def _norm_col_key(s: str) -> str:
            return re.sub(r"[^A-Z0-9]+", "_", s.strip().upper()).strip("_")

        if ordered_fields:
            if header_cells and len(header_cells) < len(ordered_fields):
                raise MalformedObservationError(
                    f"ChemCam MOC header columns ({len(header_cells)}) do not match PDS3 .LBL FIELD count ({len(ordered_fields)})."
                )
            for idx, f in enumerate(ordered_fields):
                fnum = f.get("FIELD_NUMBER") or f.get("COLUMN_NUMBER")
                col_idx = (int(fnum) - 1) if (fnum is not None and str(fnum).isdigit()) else idx
                fname = str(f.get("NAME") or "").strip()
                nkey = _norm_col_key(fname)
                hdr_name = header_cells[col_idx] if header_cells and col_idx < len(header_cells) else None
                if hdr_name and nkey not in {"ERR_PLUS_MINUS", "PRODUCT_NAME", "TARGET_NAME", "DISTANCE_TO_TARGET", "SUM_OF_OXIDES"}:
                    hkey = _norm_col_key(hdr_name)
                    if nkey not in hkey and hkey not in nkey:
                        raise MalformedObservationError(
                            f"ChemCam MOC schema mismatch at col {col_idx + 1}: LBL defines '{fname}', CSV header has '{hdr_name}'."
                        )
                if nkey not in col_lookup and nkey != "ERR_PLUS_MINUS":
                    col_lookup[nkey] = col_idx
                field_mappings.append(
                    ParserFieldMapping(
                        schema_field_name=fname,
                        resolved_header_name=hdr_name,
                        column_index=col_idx,
                        data_type=str(f.get("DATA_TYPE") or "") or None,
                        unit="wt%" if nkey in known_oxides or any(nkey.endswith(s) for s in ("_RMSEP", "_SHOTS_STDEV")) or nkey == "SUM_OF_OXIDES" else ("m" if "DISTANCE" in nkey else None),
                        description=str(f.get("DESCRIPTION") or "") or None,
                    )
                )
        else:
            for col_idx, h in enumerate(header_cells):
                nkey = _norm_col_key(h)
                if nkey in {"", "ERR_PLUS_MINUS"} or h.strip() == "+/-":
                    continue
                if nkey == "FILE":
                    nkey = "PRODUCT_NAME"
                elif nkey == "TARGET":
                    nkey = "TARGET_NAME"
                elif nkey == "DISTANCE_M":
                    nkey = "DISTANCE_TO_TARGET"
                col_lookup[nkey] = col_idx
                field_mappings.append(
                    ParserFieldMapping(
                        schema_field_name=h,
                        resolved_header_name=h,
                        column_index=col_idx,
                    )
                )

        prod_idx = col_lookup.get("PRODUCT_NAME", col_lookup.get("FILE"))
        tgt_idx = col_lookup.get("TARGET_NAME", col_lookup.get("TARGET"))
        if prod_idx is None:
            raise MalformedObservationError("ChemCam MOC schema missing required PRODUCT_NAME / File column.")

        sum_idx = col_lookup.get("SUM_OF_OXIDES")
        dist_idx = col_lookup.get("DISTANCE_TO_TARGET", col_lookup.get("DISTANCE_M"))

        rmsep_definitions: Dict[str, str] = {}
        stdev_definitions: Dict[str, str] = {}
        if ordered_fields:
            for f in ordered_fields:
                fname_u = str(f.get("NAME") or "").strip().upper()
                fdesc = str(f.get("DESCRIPTION") or "").strip()
                if fname_u.endswith("_RMSEP") and fdesc:
                    rmsep_definitions[fname_u] = fdesc
                elif fname_u.endswith("_SHOTS_STDEV") and fdesc:
                    stdev_definitions[fname_u] = fdesc

        oxide_col_indices: Dict[str, Tuple[int, Optional[int], Optional[int]]] = {}
        for ox_u in known_oxides:
            if ox_u in col_lookup:
                oxide_col_indices[ox_u] = (
                    col_lookup[ox_u],
                    col_lookup.get(f"{ox_u}_RMSEP"),
                    col_lookup.get(f"{ox_u}_SHOTS_STDEV"),
                )
        if not oxide_col_indices:
            raise MalformedObservationError("ChemCam MOC schema yielded zero recognized oxide columns.")

        data_start = (header_row_idx + 1) if header_row_idx is not None else 0
        min_req_idx = max([prod_idx] + [v[0] for v in oxide_col_indices.values()])
        rows: List[Dict[str, Any]] = []
        row_rejections: List[Dict[str, Any]] = []
        total_data_rows = 0

        for row_idx, cols in enumerate(all_csv_rows[data_start:], start=data_start + 1):
            if not cols or not any(c.strip() for c in cols):
                continue
            total_data_rows += 1
            if len(cols) <= min_req_idx:
                row_rejections.append(
                    {"row_index": row_idx, "reason": f"Truncated row: {len(cols)} columns < required {min_req_idx + 1}"}
                )
                continue
            prod_name = cols[prod_idx].strip()
            if not prod_name.upper().startswith(("CL", "CR", "CC")):
                row_rejections.append(
                    {"row_index": row_idx, "reason": f"Non-ChemCam product token '{prod_name}' skipped."}
                )
                continue

            target_name = cols[tgt_idx].strip() if tgt_idx is not None and tgt_idx < len(cols) else ""
            total_pct = _safe_float(cols[sum_idx]) if sum_idx is not None and sum_idx < len(cols) else None
            dist_m = _safe_float(cols[dist_idx]) if dist_idx is not None and dist_idx < len(cols) else None

            coords = (
                coord_service.resolve_from_pds_metadata(
                    None,
                    product_id=prod_name,
                    uncertainty_m=None,
                    standoff_m=dist_m,
                )
                if coord_service is not None
                else None
            )

            oxides: Dict[str, Dict[str, Optional[float]]] = {}
            for ox_u, (val_i, rmsep_i, stdev_i) in oxide_col_indices.items():
                ox_canon = oxide_canonical_case[ox_u]
                val = _safe_float(cols[val_i]) if val_i < len(cols) else None
                rmsep = _safe_float(cols[rmsep_i]) if rmsep_i is not None and rmsep_i < len(cols) else None
                stdev = _safe_float(cols[stdev_i]) if stdev_i is not None and stdev_i < len(cols) else None
                oxides[ox_canon] = {
                    "value": val,
                    "rmsep": rmsep,
                    "shots_stdev": stdev,
                    "rmsep_definition": rmsep_definitions.get(f"{ox_u}_RMSEP"),
                    "shots_stdev_definition": stdev_definitions.get(f"{ox_u}_SHOTS_STDEV"),
                }

            rows.append(
                {
                    "row_index": row_idx,
                    "product_name": prod_name,
                    "target_name": target_name,
                    "data_set_id": pds_meta.get("data_set_id") or "MSL-M-CHEMCAM-LIBS-4/5-RDR-V1.0",
                    "release_id": (pds_meta.get("parsed_odl") or {}).get("RELEASE_ID"),
                    "total_wt_pct": total_pct,
                    "distance_m": dist_m,
                    "oxides": oxides,
                    "coordinates": coords,
                    "schema_fields_count": len(ordered_fields or field_mappings),
                    "source_file_checksum": file_checksum,
                    "label_file_path": str(lbl_file) if lbl_file else None,
                    "label_file_checksum": lbl_checksum,
                    "dependency_digest": dep_digest,
                    "schema_version": f"pds3_moc_release_{((pds_meta.get('parsed_odl') or {}).get('RELEASE_ID') or 'csv_header')}",
                }
            )

        return ParserResult(
            parser_id="chemcam_moc_schema_parser",
            parser_version="2.1.0",
            schema_source=lbl_file.name if lbl_file else f"{csv_path.name}:header",
            schema_version=f"pds3_moc_release_{((pds_meta.get('parsed_odl') or {}).get('RELEASE_ID') or 'header')}",
            source_file_path=str(csv_path),
            source_file_checksum=file_checksum,
            label_file_path=str(lbl_file) if lbl_file else None,
            label_file_checksum=lbl_checksum,
            dependency_digest=dep_digest,
            field_mappings=field_mappings,
            total_rows_read=total_data_rows,
            accepted_row_count=len(rows),
            rejected_row_count=len(row_rejections),
            row_rejections=row_rejections,
            records=rows,
        )

    @staticmethod
    def parse_chemcam_moc_table(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
    ) -> List[Dict[str, Any]]:
        """Backward-compatible wrapper returning parsed MOC record list."""
        return CuriosityDataParser.parse_chemcam_moc_table_with_contract(
            csv_path=csv_path,
            label_path=label_path,
            coord_service=coord_service,
        ).records

    @staticmethod
    def parse_apxs_csv_unverified_header_only(
        csv_path: Path,
        source_dataset_id: str = "msl_apxs_supplement_sols_0_3076",
        product_id: str = "DS01_2021JE007171R",
    ) -> ParserResult:
        """
        TEST-ONLY / DIAGNOSTIC helper parsing APXS CSV headers without a PDS4 XML schema.
        Explicitly emits parser_id='apxs_unverified_csv_header_only' and NEVER belongs in
        the verified production index.
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"APXS CSV not found: {csv_path}")
        file_checksum = _sha256_file(csv_path)
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = list(reader.fieldnames or [])
            if not headers:
                raise MalformedObservationError(f"APXS CSV '{csv_path.name}' is missing header row.")
            field_mappings = [
                ParserFieldMapping(
                    schema_field_name=hdr,
                    resolved_header_name=hdr,
                    column_index=idx,
                    unit="ppm" if hdr.lower().endswith("_ppm") else ("wt%" if hdr.lower().endswith("_pct") else None),
                    unit_source="unverified_csv_header_suffix",
                )
                for idx, hdr in enumerate(headers)
            ]
            rows = list(reader)
        return ParserResult(
            parser_id="apxs_unverified_csv_header_only",
            parser_version="unverified_header_only_1.0.0",
            schema_source=f"{csv_path.name}:unverified_header_only",
            schema_version="unverified_csv_header_only",
            source_file_path=str(csv_path),
            source_file_checksum=file_checksum,
            field_mappings=field_mappings,
            total_rows_read=len(rows),
            accepted_row_count=0,
            rejected_row_count=len(rows),
            row_rejections=[
                {"row_index": i + 1, "reason": "Excluded: APXS CSV lacked required companion PDS4 XML schema."}
                for i in range(len(rows))
            ],
            records=[],
        )

    @staticmethod
    def parse_apxs_csv_with_contract(
        csv_path: Path,
        source_dataset_id: str = "msl_apxs_supplement_sols_0_3076",
        product_id: str = "DS01_2021JE007171R",
        label_path: Optional[Path] = None,
        require_xml: bool = True,
    ) -> ParserResult:
        """
        Schema-driven parser for NASA PDS4 APXS calibrated oxide/trace CSV tables.

        Strictly requires a companion PDS4 XML label (<Table_Delimited>) in verified
        ingestion mode (no silent header-only fallback). Validates column count, column
        order, names, PDS4 data types, units, and <Special_Constants>, and binds the XML
        checksum into parser dependency provenance.
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"APXS CSV not found: {csv_path}")

        file_checksum = _sha256_file(csv_path)
        xml_file = label_path if (label_path and label_path.exists()) else None
        if xml_file is None:
            for ext in (".xml", ".XML"):
                cand = csv_path.with_suffix(ext)
                if cand.exists():
                    xml_file = cand
                    break

        if xml_file is None:
            if require_xml:
                raise MalformedObservationError(
                    f"APXS ingestion requires a companion PDS4 XML label for '{csv_path.name}'; "
                    "silent CSV-header fallback is prohibited."
                )
            return CuriosityDataParser.parse_apxs_csv_unverified_header_only(
                csv_path=csv_path,
                source_dataset_id=source_dataset_id,
                product_id=product_id,
            )

        try:
            pds4_schema = parse_pds4_table_delimited(xml_file)
        except Exception as exc:
            raise MalformedObservationError(
                f"APXS PDS4 XML schema '{xml_file.name}' is invalid or malformed: {exc}"
            ) from exc

        xml_checksum = pds4_schema.get("xml_sha256") or _sha256_file(xml_file)
        dep_digest = hashlib.sha256(f"{file_checksum}|{xml_checksum}".encode("utf-8")).hexdigest()

        known_apxs_oxides = ("Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O", "CaO", "TiO2", "Cr2O3", "MnO", "FeO")
        known_apxs_traces = ("Ni", "Zn", "Br")

        rows: List[Dict[str, Any]] = []
        row_rejections: List[Dict[str, Any]] = []
        field_mappings: List[ParserFieldMapping] = []
        total_rows_read = 0

        _supported_pds4_types = {
            "ASCII_Real",
            "ASCII_Integer",
            "ASCII_String",
            "UTF8_String",
            "ASCII_Date_Time_YMD",
            "ASCII_Date_Time_DOY",
            "ASCII_Date_Time_UTC",
            "ASCII_NonNegative_Integer",
        }

        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = list(reader.fieldnames or [])
            if not headers:
                raise MalformedObservationError(f"APXS CSV '{csv_path.name}' is missing header row.")

            def _apxs_base_key(name: str) -> str:
                return re.sub(r"[^a-z0-9]+", "", name.strip().lower())

            xml_fields = pds4_schema["fields"]
            if len(headers) != len(xml_fields):
                raise MalformedObservationError(
                    f"APXS column count ({len(headers)}) mismatches PDS4 XML schema count ({len(xml_fields)})."
                )

            field_meta_by_header: Dict[str, Dict[str, Any]] = {}
            for idx, (hdr, xf) in enumerate(zip(headers, xml_fields)):
                xname = str(xf.get("name") or "")
                h_base = _apxs_base_key(re.sub(r"_(pct|ppm)$", "", hdr, flags=re.IGNORECASE))
                x_base = _apxs_base_key(re.sub(r"_(pct|ppm)$", "", xname, flags=re.IGNORECASE))
                if not x_base or not h_base or (x_base != h_base and not (h_base.startswith("informal") and x_base.startswith("informal"))):
                    raise MalformedObservationError(
                        f"APXS schema mismatch at col {idx + 1}: XML declares '{xname}', CSV has '{hdr}'."
                    )

                dtype = str(xf.get("data_type") or "").strip()
                if dtype and dtype not in _supported_pds4_types:
                    raise MalformedObservationError(
                        f"Unsupported PDS4 data_type '{dtype}' for APXS column '{hdr}'."
                    )

                desc = str(xf.get("description") or "")
                xml_unit = xf.get("resolved_unit")
                unit_src = xf.get("unit_source")
                hdr_low = hdr.lower()
                if hdr_low.endswith("_pct") and xml_unit and xml_unit != "wt%":
                    raise MalformedObservationError(
                        f"APXS unit conflict at col '{hdr}': XML declares '{xml_unit}', CSV header suffix is '_pct'."
                    )
                if hdr_low.endswith("_ppm") and xml_unit and xml_unit != "ppm":
                    raise MalformedObservationError(
                        f"APXS unit conflict at col '{hdr}': XML declares '{xml_unit}', CSV header suffix is '_ppm'."
                    )
                if xml_unit and ("concentration" in desc.lower() or hdr_low.endswith("_pct") or hdr_low.endswith("_ppm")):
                    if xml_unit not in {"wt%", "ppm"}:
                        raise MalformedObservationError(
                            f"Unsupported APXS concentration unit '{xml_unit}' declared in XML for '{hdr}'."
                        )
                resolved_unit = xml_unit or ("ppm" if hdr_low.endswith("_ppm") else ("wt%" if hdr_low.endswith("_pct") else None))
                if not unit_src and resolved_unit:
                    unit_src = "csv_header_validated_against_xml_field"

                sc_map = xf.get("special_constants") or {}
                special_tokens = {str(v).strip() for v in sc_map.values() if str(v).strip()}
                field_meta_by_header[hdr] = {
                    "data_type": dtype,
                    "unit": resolved_unit,
                    "unit_source": unit_src,
                    "description": desc,
                    "special_constants": sc_map,
                    "special_tokens": special_tokens,
                }
                field_mappings.append(
                    ParserFieldMapping(
                        schema_field_name=xname,
                        resolved_header_name=hdr,
                        column_index=idx,
                        data_type=dtype or None,
                        unit=resolved_unit,
                        unit_source=unit_src,
                        description=desc or None,
                        special_constants=sc_map,
                    )
                )

            hdr_by_norm = {_apxs_base_key(h): h for h in headers}

            def _find_col(*candidates: str) -> Optional[str]:
                for c in candidates:
                    nk = _apxs_base_key(c)
                    if nk in hdr_by_norm:
                        return hdr_by_norm[nk]
                return None

            target_col = _find_col("Target")
            sol_col = _find_col("Sol")
            north_col = _find_col("Northing_m")
            east_col = _find_col("Easting_m")
            elev_col = _find_col("Elevation_m")
            if not target_col or not sol_col:
                raise MalformedObservationError("APXS CSV lacks required 'Target' or 'Sol' header columns.")

            qual_col = _find_col("Quality")
            fit_col = _find_col("Fit_Type")
            start_col = _find_col("Start_Time")
            offset_col = _find_col("Offset_cm")
            strat_g_col = _find_col("Strat_group_formal")
            strat_f_col = _find_col("Strat_fm")
            strat_m_col = _find_col("Strat_mbr")
            wp_col = _find_col("Informal waypoint/outcrop/region name")
            prep_col = _find_col("Preparation_method")

            oxide_cols: Dict[str, Tuple[str, Optional[str], str]] = {}
            for ox in known_apxs_oxides:
                vcol = _find_col(f"{ox}_pct", ox)
                ecol = _find_col(f"{ox}_err")
                if vcol:
                    unit_v = (field_meta_by_header.get(vcol) or {}).get("unit") or "wt%"
                    oxide_cols[ox] = (vcol, ecol, unit_v)
            trace_cols: Dict[str, Tuple[str, Optional[str], str]] = {}
            for el in known_apxs_traces:
                vcol = _find_col(f"{el}_ppm", el)
                ecol = _find_col(f"{el}_err")
                if vcol:
                    unit_v = (field_meta_by_header.get(vcol) or {}).get("unit") or "ppm"
                    trace_cols[el] = (vcol, ecol, unit_v)

            if not oxide_cols and not trace_cols:
                raise MalformedObservationError("APXS CSV resolved zero documented oxide or trace element columns.")

            def _parse_typed_number(raw_cell: Any, col_name: Optional[str]) -> Tuple[Optional[float], bool]:
                """Return (value, is_special_or_null_valid). False means corrupt non-numeric token."""
                s = str(raw_cell or "").strip()
                if not s or s.upper() in _NULL_TOKENS:
                    return None, True
                meta = field_meta_by_header.get(col_name or "") or {}
                if s in meta.get("special_tokens", set()):
                    return None, True
                dtype = str(meta.get("data_type") or "")
                try:
                    num = float(s)
                    if not math.isfinite(num):
                        return None, False
                    if dtype in {"ASCII_Integer", "ASCII_NonNegative_Integer"}:
                        if abs(num - round(num)) > 1e-6:
                            return None, False
                        if dtype == "ASCII_NonNegative_Integer" and num < 0:
                            return None, False
                    return num, True
                except ValueError:
                    return None, False

            for row_idx, r in enumerate(reader, start=1):
                total_rows_read += 1
                target = (r.get(target_col) or "").strip()
                if not target:
                    row_rejections.append({"row_index": row_idx, "reason": "Empty Target identifier."})
                    continue
                sol_val, sol_ok = _parse_typed_number(r.get(sol_col), sol_col)
                if not sol_ok:
                    row_rejections.append({"row_index": row_idx, "reason": f"Invalid non-integer Sol value '{r.get(sol_col)}'."})
                    continue
                northing, _ = _parse_typed_number(r.get(north_col), north_col) if north_col else (None, True)
                easting, _ = _parse_typed_number(r.get(east_col), east_col) if east_col else (None, True)
                elevation, _ = _parse_typed_number(r.get(elev_col), elev_col) if elev_col else (None, True)
                offset_cm, _ = _parse_typed_number(r.get(offset_col), offset_col) if offset_col else (None, True)

                coords = None
                if easting is not None and northing is not None:
                    try:
                        lat, lon = gale_eqc_meters_to_lat_lon(easting, northing)
                        coords = {
                            "latitude": lat,
                            "longitude": lon,
                            "elevation_m": elevation,
                            "easting_m": easting,
                            "northing_m": northing,
                            "crs": "IAU2000:49900",
                            "location_semantic_type": LocationSemanticType.INSTRUMENT_TARGET_LOCATION.value,
                            "original_coordinate_values": {
                                "easting_m": easting,
                                "northing_m": northing,
                                "elevation_m": elevation,
                            },
                            "original_coordinate_crs": "Gale_IAU2000_Equirectangular_R3396190m",
                            "coordinate_transform": "gale_eqc_meters_to_lat_lon_pyproj",
                            "coordinate_transform_params": {"R_m": 3396190.0},
                            "association_rule_version": "apxs_pds4_target_eqc_v2",
                            "coordinate_source": f"pds4_apxs_gale_eqc_projection:{csv_path.name}",
                            "coordinate_provenance": (
                                f"Converted APXS Gale Crater Equirectangular target coordinates "
                                f"(E={easting:.2f}m, N={northing:.2f}m) from {csv_path.name}."
                            ),
                            "coordinate_uncertainty_m": None,
                            "coordinate_limitations": [
                                "PDS4 XML defines Northing_m/Easting_m as approximate APXS target coordinates with no quantitative horizontal uncertainty reported (None)."
                            ],
                        }
                    except Exception:
                        coords = None

                oxides_wt_pct: Dict[str, Dict[str, Any]] = {}
                for ox, (vcol, ecol, unit) in oxide_cols.items():
                    raw_str = (r.get(vcol) or "").strip()
                    val, v_ok = _parse_typed_number(raw_str, vcol)
                    if not v_ok:
                        row_rejections.append({"row_index": row_idx, "reason": f"Non-numeric APXS {ox} value '{raw_str}' violates {field_meta_by_header.get(vcol, {}).get('data_type')}."})
                        continue
                    err, e_ok = _parse_typed_number(r.get(ecol), ecol) if ecol else (None, True)
                    if not e_ok:
                        row_rejections.append({"row_index": row_idx, "reason": f"Non-numeric APXS {ox} error '{r.get(ecol)}'."})
                        err = None
                    if val is not None or err is not None:
                        oxides_wt_pct[ox] = {
                            "value": val,
                            "error": err,
                            "unit": unit,
                            "source_column": vcol,
                            "error_definition": (field_meta_by_header.get(ecol or "") or {}).get("description") if ecol else None,
                            "is_exact_zero": (val == 0.0 and raw_str != ""),
                        }

                trace_ppm: Dict[str, Dict[str, Any]] = {}
                for el, (vcol, ecol, unit) in trace_cols.items():
                    raw_str = (r.get(vcol) or "").strip()
                    val, v_ok = _parse_typed_number(raw_str, vcol)
                    if not v_ok:
                        row_rejections.append({"row_index": row_idx, "reason": f"Non-numeric APXS {el} value '{raw_str}' violates {field_meta_by_header.get(vcol, {}).get('data_type')}."})
                        continue
                    err, e_ok = _parse_typed_number(r.get(ecol), ecol) if ecol else (None, True)
                    if not e_ok:
                        row_rejections.append({"row_index": row_idx, "reason": f"Non-numeric APXS {el} error '{r.get(ecol)}'."})
                        err = None
                    if val is not None or err is not None:
                        trace_ppm[el] = {
                            "value": val,
                            "error": err,
                            "unit": unit,
                            "source_column": vcol,
                            "error_definition": (field_meta_by_header.get(ecol or "") or {}).get("description") if ecol else None,
                            "is_exact_zero": (val == 0.0 and raw_str != ""),
                        }

                qual_raw = (r.get(qual_col) or "").strip() if qual_col else ""
                rows.append(
                    {
                        "row_index": row_idx,
                        "source_dataset_id": source_dataset_id,
                        "product_id": product_id,
                        "sol": int(sol_val) if sol_val is not None else None,
                        "target_name": target,
                        "strat_group": (r.get(strat_g_col) or "").strip() or None if strat_g_col else None,
                        "strat_formation": (r.get(strat_f_col) or "").strip() or None if strat_f_col else None,
                        "strat_member": (r.get(strat_m_col) or "").strip() or None if strat_m_col else None,
                        "waypoint_name": (r.get(wp_col) or "").strip() or None if wp_col else None,
                        "preparation_method": (r.get(prep_col) or "").strip() or None if prep_col else None,
                        "quality_flag": qual_raw or None,
                        "fit_type": (r.get(fit_col) or "").strip() or None if fit_col else None,
                        "start_time": (r.get(start_col) or "").strip() or None if start_col else None,
                        "offset_cm": offset_cm,
                        "coordinates": coords,
                        "oxides_wt_pct": oxides_wt_pct,
                        "trace_ppm": trace_ppm,
                        "source_file_checksum": file_checksum,
                        "label_file_path": str(xml_file),
                        "label_file_checksum": xml_checksum,
                        "dependency_digest": dep_digest,
                        "schema_version": pds4_schema["schema_version"],
                    }
                )

        return ParserResult(
            parser_id="apxs_pds4_schema_parser",
            parser_version="3.0.0",
            schema_source=xml_file.name,
            schema_version=pds4_schema["schema_version"],
            source_file_path=str(csv_path),
            source_file_checksum=file_checksum,
            label_file_path=str(xml_file),
            label_file_checksum=xml_checksum,
            dependency_digest=dep_digest,
            field_mappings=field_mappings,
            total_rows_read=total_rows_read,
            accepted_row_count=len(rows),
            rejected_row_count=len(row_rejections),
            row_rejections=row_rejections,
            records=rows,
        )

    @staticmethod
    def parse_apxs_csv(
        csv_path: Path,
        source_dataset_id: str = "msl_apxs_supplement_sols_0_3076",
        product_id: str = "DS01_2021JE007171R",
        label_path: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Backward-compatible wrapper returning parsed APXS record list."""
        return CuriosityDataParser.parse_apxs_csv_with_contract(
            csv_path=csv_path,
            source_dataset_id=source_dataset_id,
            product_id=product_id,
            label_path=label_path,
        ).records

    @staticmethod
    def parse_chemin_min_csv_with_contract(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
        extra_structure_dirs: Optional[List[Path]] = None,
        require_label: bool = True,
    ) -> ParserResult:
        """
        Schema-driven parser for NASA PDS3 CheMin RDR5 mineral abundance spreadsheets.
        Enforces companion .LBL + external ^STRUCTURE (CHEMIN_MIN.FMT) resolution,
        verifies quantitative WEIGHT_PERCENT unit metadata, rejects qualitative rows,
        and derives error sigma semantics strictly from .FMT + .LBL SPREADSHEET.DESCRIPTION.
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"CheMin mineral CSV missing: {csv_path}")

        file_checksum = _sha256_file(csv_path)
        lbl_file = _resolve_companion_label(csv_path, label_path)
        if lbl_file is None and require_label:
            raise MalformedObservationError(
                f"CheMin ingestion requires companion PDS3 .LBL + .FMT schema for '{csv_path.name}'."
            )
        lbl_checksum = _sha256_file(lbl_file) if lbl_file and lbl_file.exists() else None
        pds_meta: Dict[str, Any] = {}
        columns: List[Dict[str, Any]] = []
        fmt_checksums: Dict[str, str] = {}
        fmt_paths: List[str] = []
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            parsed_lbl, columns = load_pds3_columns_and_structure(
                lbl_file,
                table_object_names=("SPREADSHEET",),
                extra_structure_dirs=extra_structure_dirs,
                strict_structure=True,
            )
            pds_meta["parsed_odl"] = parsed_lbl
            for fp in parsed_lbl.get("_RESOLVED_STRUCTURES") or []:
                fpath = Path(fp)
                if fpath.exists():
                    fmt_paths.append(str(fpath))
                    fmt_checksums[fpath.name] = _sha256_file(fpath)

        dep_digest_parts = [file_checksum, lbl_checksum or ""] + [f"{k}:{v}" for k, v in sorted(fmt_checksums.items())]
        dep_digest = hashlib.sha256("|".join(dep_digest_parts).encode("utf-8")).hexdigest()

        product_id = str(pds_meta.get("product_id") or csv_path.stem.upper())
        tbl_obj = (pds_meta.get("parsed_odl") or {}).get("_OBJECTS", {}).get("SPREADSHEET", {})
        desc = str(tbl_obj.get("DESCRIPTION") or "")

        coords = (
            coord_service.resolve_from_pds_metadata(pds_meta, product_id=product_id, uncertainty_m=None)
            if coord_service is not None
            else None
        )

        sol_val = pds_meta.get("planet_day_number")
        if sol_val is None:
            m = re.search(r"MIN(\d{4})(\d{3})(\d{4})CH", product_id)
            if m:
                sol_val = int(m.group(1))

        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = list(reader.fieldnames or [])
            if not headers:
                raise MalformedObservationError(f"CheMin CSV '{csv_path.name}' lacks header row.")

            hdr_upper = {h.strip().upper(): h for h in headers}
            schema_names = [str(c.get("NAME") or "").strip().upper() for c in columns if c.get("NAME")]
            if schema_names:
                missing_cols = [sn for sn in schema_names if sn not in hdr_upper]
                if missing_cols:
                    raise MalformedObservationError(
                        f"CheMin CSV '{csv_path.name}' missing required ^STRUCTURE columns: {missing_cols}."
                    )

            def _resolve_col(schema_aliases: Tuple[str, ...]) -> Optional[str]:
                for c in columns:
                    cname = str(c.get("NAME") or "").strip().upper()
                    if cname in schema_aliases and cname in hdr_upper:
                        return hdr_upper[cname]
                for al in schema_aliases:
                    if al in hdr_upper:
                        return hdr_upper[al]
                return None

            min_col = _resolve_col(("MINERAL",))
            pct_col = _resolve_col(("PERCENT", "WEIGHT_PERCENT"))
            err_col = _resolve_col(("ERROR", "ESTIMATED_ERROR"))

            if not min_col or not pct_col:
                raise MalformedObservationError(
                    f"CheMin CSV '{csv_path.name}' lacks required mineral/abundance schema columns (got {headers})."
                )

            schema_id_str = (
                f"pds3:{pds_meta.get('structure_file') or (lbl_file.name if lbl_file else csv_path.name)}"
                if lbl_file
                else "chemin_csv_header"
            )
            pct_unit = "wt%"
            pct_schema_unit: Optional[str] = None
            pct_schema_dtype: Optional[str] = None
            err_schema_unit: Optional[str] = None
            err_schema_dtype: Optional[str] = None
            err_resolved_unit: Optional[str] = None
            err_is_physical: bool = False
            err_unit_source: Optional[str] = None
            err_conv_history: List[str] = []
            err_limitations: List[str] = []

            err_semantics = "chemin_estimated_error_unspecified_sigma"
            err_definition = "Estimated uncertainty without explicit sigma multiplier in PDS3 label."
            desc_low = desc.lower()
            if "2-sigma" in desc_low or "2 sigma" in desc_low:
                err_semantics = "chemin_rietveld_2sigma"
                err_definition = desc.strip()

            from app.science.composition.uncertainty import (
                SEMANTIC_NON_DIMENSIONAL_UNCERTAINTY_UNITS,
                convert_uncertainty_to_unit,
                normalize_uncertainty_unit,
            )

            field_mappings: List[ParserFieldMapping] = []
            for idx, h in enumerate(headers):
                cmeta = next((c for c in columns if str(c.get("NAME") or "").strip().upper() == h.strip().upper()), {})
                cdesc = str(cmeta.get("DESCRIPTION") or "")
                cunit = str(cmeta.get("UNIT") or "").strip()
                cdtype = str(cmeta.get("DATA_TYPE") or "").strip() or None
                mapped_unit: Optional[str] = None
                mapped_unit_src: Optional[str] = "pds3_fmt_unit" if cunit else None

                if h == pct_col:
                    if cunit and cunit.upper() not in {"WEIGHT_PERCENT", "WT%", "PERCENT", "WT_PCT"}:
                        raise MalformedObservationError(
                            f"Unsupported or non-quantitative CheMin abundance unit '{cunit}' in schema column '{h}'."
                        )
                    if require_label and columns and not cunit:
                        raise MalformedObservationError(
                            f"CheMin schema column '{h}' lacks required quantitative UNIT (expected WEIGHT_PERCENT)."
                        )
                    pct_schema_unit = cunit or "WEIGHT_PERCENT"
                    pct_schema_dtype = cdtype
                    mapped_unit = pct_unit
                elif h == err_col:
                    err_schema_unit = cunit or None
                    err_schema_dtype = cdtype
                    if cdesc and ("2-sigma" in cdesc.lower() or "2 sigma" in cdesc.lower()):
                        err_semantics = "chemin_rietveld_2sigma"
                        err_definition = cdesc.strip()
                    elif cunit and err_semantics != "chemin_rietveld_2sigma":
                        err_definition = f"CHEMIN_MIN.FMT UNIT={cunit}; sigma multiplier not specified in companion label."
                    elif not cunit:
                        err_unit_source = "missing_in_schema"
                        err_limitations.append(
                            f"Uncertainty column '{h}' lacks UNIT in companion schema; physical unit unknown and NOT coerced to wt%."
                        )
                        if not cdesc and err_semantics != "chemin_rietveld_2sigma":
                            err_definition = f"Uncertainty column '{h}' lacks both UNIT and DESCRIPTION in companion schema."

                    if cunit:
                        canon_u, is_phys = normalize_uncertainty_unit(cunit)
                        if is_phys and canon_u is not None:
                            err_resolved_unit = canon_u
                            err_is_physical = True
                            err_unit_source = "pds3_fmt_unit"
                        elif canon_u in SEMANTIC_NON_DIMENSIONAL_UNCERTAINTY_UNITS:
                            # Explicitly preserve semantic units like ESTIMATED_ERROR without casting to wt%
                            err_resolved_unit = canon_u
                            err_is_physical = False
                            err_unit_source = "pds3_fmt_semantic_unit"
                            err_limitations.append(
                                f"Schema declares semantic unit '{canon_u}' rather than physical mass % unit ('wt%'); original semantic unit preserved."
                            )
                        elif cunit.upper() in {"N/A", "NONE", "UNKNOWN"}:
                            err_resolved_unit = None
                            err_is_physical = False
                            err_unit_source = "unreported_in_schema"
                            err_limitations.append(
                                f"Schema declares non-dimensional/absent unit '{cunit}' for '{h}'; physical unit unknown."
                            )
                        else:
                            raise MalformedObservationError(
                                f"Incompatible or non-concentration CheMin error unit '{cunit}' declared in schema column '{h}'."
                            )
                        mapped_unit = err_resolved_unit
                        mapped_unit_src = err_unit_source
                    else:
                        mapped_unit = None
                        mapped_unit_src = "missing_in_schema"
                field_mappings.append(
                    ParserFieldMapping(
                        schema_field_name=str(cmeta.get("NAME") or h),
                        resolved_header_name=h,
                        column_index=idx,
                        data_type=cdtype,
                        unit=mapped_unit,
                        unit_source=mapped_unit_src,
                        description=cdesc or None,
                    )
                )

            minerals: List[Dict[str, Any]] = []
            row_rejections: List[Dict[str, Any]] = []
            total_rows = 0
            for idx, r in enumerate(reader, start=1):
                total_rows += 1
                mineral_name = (r.get(min_col) or "").strip()
                raw_pct = (r.get(pct_col) or "").strip()
                raw_err = (r.get(err_col) or "").strip() if err_col else ""
                if not mineral_name:
                    row_rejections.append({"row_index": idx, "reason": "Empty mineral name."})
                    continue
                pct = _safe_float(raw_pct)
                if pct is None:
                    row_rejections.append(
                        {
                            "row_index": idx,
                            "mineral": mineral_name,
                            "reason": f"Non-quantitative or missing mineral abundance token '{raw_pct}' rejected.",
                        }
                    )
                    continue
                raw_err_val = _safe_float(raw_err) if raw_err else None
                norm_err_val = raw_err_val
                norm_err_unit = err_resolved_unit
                row_err_history = list(err_conv_history)
                if raw_err_val is not None and err_is_physical and err_resolved_unit and err_resolved_unit != pct_unit:
                    norm_err_val, norm_err_unit, chist, conv_ok = convert_uncertainty_to_unit(
                        raw_err_val, err_resolved_unit, pct_unit
                    )
                    if not conv_ok:
                        raise MalformedObservationError(
                            f"Incompatible CheMin error conversion from '{err_resolved_unit}' to '{pct_unit}'."
                        )
                    row_err_history.extend(chist)
                minerals.append(
                    {
                        "row_index": idx,
                        "mineral": mineral_name,
                        "weight_percent": pct,
                        "estimated_error": raw_err_val,
                        "normalized_error": norm_err_val,
                        "unit": pct_unit,
                        "abundance_schema_field": pct_col,
                        "abundance_schema_unit": pct_schema_unit,
                        "abundance_schema_data_type": pct_schema_dtype,
                        "error_schema_field": err_col,
                        "error_schema_unit": err_schema_unit,
                        "error_schema_data_type": err_schema_dtype,
                        "error_unit": err_resolved_unit,
                        "normalized_error_unit": norm_err_unit,
                        "error_is_physical_unit": err_is_physical,
                        "error_conversion_history": row_err_history,
                        "error_limitations": list(err_limitations),
                        "error_semantics": err_semantics,
                        "error_definition": err_definition,
                        "schema_identity": schema_id_str,
                    }
                )

        if not minerals:
            raise MalformedObservationError(f"CheMin product '{csv_path.name}' yielded zero quantitative mineral rows.")

        schema_ver = (
            f"pds3:{pds_meta.get('structure_file') or lbl_file.name}"
            if lbl_file
            else "chemin_csv_header"
        )
        record = {
            "product_id": product_id,
            "data_set_id": pds_meta.get("data_set_id") or "MSL-M-CHEMIN-4-RDR-V1.0",
            "product_type": pds_meta.get("product_type") or "CHEMIN_MIN",
            "start_time": pds_meta.get("start_time"),
            "sol": sol_val,
            "description": desc,
            "coordinates": coords,
            "columns_schema": columns,
            "minerals": minerals,
            "source_file_checksum": file_checksum,
            "label_file_path": str(lbl_file) if lbl_file else None,
            "label_file_checksum": lbl_checksum,
            "format_file_paths": fmt_paths,
            "format_file_checksums": fmt_checksums,
            "dependency_digest": dep_digest,
            "schema_version": schema_ver,
        }
        return ParserResult(
            parser_id="chemin_rdr5_schema_parser",
            parser_version="3.0.0",
            schema_source=str(pds_meta.get("structure_file") or (lbl_file.name if lbl_file else csv_path.name)),
            schema_version=schema_ver,
            source_file_path=str(csv_path),
            source_file_checksum=file_checksum,
            label_file_path=str(lbl_file) if lbl_file else None,
            label_file_checksum=lbl_checksum,
            format_file_paths=fmt_paths,
            format_file_checksums=fmt_checksums,
            dependency_digest=dep_digest,
            field_mappings=field_mappings,
            total_rows_read=total_rows,
            accepted_row_count=len(minerals),
            rejected_row_count=len(row_rejections),
            row_rejections=row_rejections,
            records=[record],
        )

    @staticmethod
    def parse_chemin_min_csv(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
        extra_structure_dirs: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible wrapper returning CheMin product dict."""
        res = CuriosityDataParser.parse_chemin_min_csv_with_contract(
            csv_path=csv_path,
            label_path=label_path,
            coord_service=coord_service,
            extra_structure_dirs=extra_structure_dirs,
        )
        return res.records[0]

    @staticmethod
    def parse_rems_adr_summary(
        file_path: Path,
        sol: Optional[int] = None,
        label_path: Optional[Path] = None,
        dataset_id: Optional[str] = None,
        extra_structure_dirs: Optional[List[Path]] = None,
    ) -> Observation:
        """
        Schema-driven parser for MSL REMS PDS3 products (MODRDR / ENVRDR / ADR).
        Never guesses numeric columns by range thresholds. Strictly separates ancillary
        ADR geometry/correction tables from environmental MODRDR/ENVRDR weather tables.
        REMS products are never emitted as geochemical or mineralogical evidence.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"REMS table file missing: {file_path}")

        lbl_file = _resolve_companion_label(file_path, label_path)
        pds_meta: Dict[str, Any] = {}
        columns: List[Dict[str, Any]] = []
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            _, columns = load_pds3_columns_and_structure(
                lbl_file,
                table_object_names=(
                    "REMS_SCIENCE_TABLE",
                    "REMS_ADR_GEOMETRY_TABLE",
                    "REMS_ADR_CORRECTIONS_TABLE",
                    "TABLE",
                ),
                extra_structure_dirs=extra_structure_dirs,
            )

        product_id = str(pds_meta.get("product_id") or file_path.stem.upper())
        product_type = str(pds_meta.get("product_type") or "").upper()
        resolved_sol = sol if sol is not None else pds_meta.get("planet_day_number")
        is_adr_ancillary = "ADR" in product_type or "ADR" in product_id.upper()

        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            raise MalformedObservationError(f"REMS file '{file_path.name}' is empty.")

        col_names = [str(c.get("NAME") or "").upper() for c in columns]

        # Path 1: Fixed-width PDS3 .TAB governed by explicit .LBL/.FMT column BYTE offsets
        if columns and all(c.get("START_BYTE") and c.get("BYTES") for c in columns):
            pressures: List[float] = []
            temps: List[float] = []
            winds: List[float] = []
            uv_a: List[float] = []
            valid_rows = 0

            for ln in lines:
                if not ln.strip():
                    continue
                valid_rows += 1
                for col in columns:
                    cname = str(col.get("NAME") or "").upper()
                    start_b = int(col["START_BYTE"])
                    width_b = int(col["BYTES"])
                    raw_val = _slice_fixed_width(ln, start_b, width_b)
                    val = _safe_float(raw_val)
                    if val is None:
                        continue
                    if cname in {"PRESSURE", "AMBIENT_PRESSURE"}:
                        pressures.append(val)
                    elif cname in {"AMBIENT_TEMP", "AMBIENT_TEMPERATURE", "ATS_LOCAL_TEMP1"}:
                        temps.append(val)
                    elif cname in {"HORIZONTAL_WIND_SPEED", "WIND_SPEED"}:
                        winds.append(val)
                    elif cname in {"UV_A", "UV_A_IRRADIANCE"}:
                        uv_a.append(val)

            if is_adr_ancillary and not (pressures or temps or winds):
                return Observation(
                    observation_id=f"REMS_ADR_{product_id}",
                    dataset_id=dataset_id or f"msl_rems_{product_id.lower()}",
                    mission="Mars Science Laboratory (MSL)",
                    instrument="Rover Environmental Monitoring Station (REMS Ancillary ADR)",
                    sol=resolved_sol,
                    location=None,
                    measurement_type="ancillary_geometry_and_calibration",
                    measurement_value={
                        "product_type": product_type or "REMS_ADR",
                        "record_count": valid_rows,
                        "schema_columns": col_names[:16],
                        "composition_eligible": False,
                    },
                    units="ancillary_table",
                    processing_level="Level 5 Ancillary Geometry/Corrections",
                    calibration_status="Non-compositional ancillary table",
                    quality_flags=["verified_pds3_ancillary_adr", "non_compositional"],
                    original_source_reference=product_id,
                    known_limitations=[
                        f"Schema-parsed REMS ancillary ADR table {file_path.name} ({valid_rows} rows); excluded from weather & composition."
                    ],
                )

            if valid_rows == 0:
                raise MalformedObservationError(f"REMS table '{file_path.name}' has zero valid records.")

            return Observation(
                observation_id=f"REMS_ENV_{product_id}",
                dataset_id=dataset_id or f"msl_rems_{product_id.lower()}",
                mission="Mars Science Laboratory (MSL)",
                instrument="Rover Environmental Monitoring Station (REMS)",
                sol=resolved_sol,
                location=None,
                measurement_type="environmental_meteorology",
                measurement_value={
                    "product_type": product_type or "REMS_RDR",
                    "record_count": valid_rows,
                    "schema_columns_count": len(columns),
                    "pressure_pa_mean": round(sum(pressures) / len(pressures), 3) if pressures else None,
                    "ambient_temp_k_mean": round(sum(temps) / len(temps), 3) if temps else None,
                    "wind_speed_mps_max": round(max(winds), 3) if winds else None,
                    "uv_a_w_m2_max": round(max(uv_a), 3) if uv_a else None,
                    "composition_eligible": False,
                },
                units="Pa / K / m/s (per PDS3 FMT schema)",
                processing_level="Calibrated MODRDR/ENVRDR",
                calibration_status="REMS Environmental Telemetry",
                quality_flags=["verified_pds3_schema_parsed", "non_compositional"],
                original_source_reference=product_id,
                known_limitations=[
                    f"Schema-driven parse of REMS table {file_path.name} using {len(columns)} FMT columns; excluded from composition."
                ],
            )

        # Path 2: CSV/TAB without .LBL/.FMT ONLY allowed if explicit documented column header line exists
        header_row: Optional[List[str]] = None
        data_rows: List[List[str]] = []
        for ln in lines:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            parts = [p.strip() for p in s.split(",")]
            if header_row is None and any(tok.isalpha() for tok in "".join(parts)):
                header_row = [h.upper() for h in parts]
                continue
            if header_row is not None:
                data_rows.append(parts)

        if not header_row or not data_rows:
            raise MalformedObservationError(
                f"REMS file '{file_path.name}' lacks companion PDS3 .LBL/.FMT schema and documented column headers."
            )

        p_idx = next((i for i, h in enumerate(header_row) if "PRESSURE" in h), None)
        t_idx = next((i for i, h in enumerate(header_row) if "TEMP" in h), None)
        if p_idx is None and t_idx is None:
            raise MalformedObservationError(
                f"REMS file '{file_path.name}' headers {header_row} do not declare documented meteorological columns."
            )

        pressures = [v for r in data_rows if p_idx is not None and p_idx < len(r) and (v := _safe_float(r[p_idx])) is not None]
        temps = [v for r in data_rows if t_idx is not None and t_idx < len(r) and (v := _safe_float(r[t_idx])) is not None]

        return Observation(
            observation_id=f"REMS_CSV_{product_id}",
            dataset_id=dataset_id or f"msl_rems_{product_id.lower()}",
            mission="Mars Science Laboratory (MSL)",
            instrument="Rover Environmental Monitoring Station (REMS)",
            sol=resolved_sol,
            location=None,
            measurement_type="environmental_meteorology",
            measurement_value={
                "record_count": len(data_rows),
                "pressure_pa_mean": round(sum(pressures) / len(pressures), 3) if pressures else None,
                "ambient_temp_k_mean": round(sum(temps) / len(temps), 3) if temps else None,
                "composition_eligible": False,
            },
            units="Pa / K",
            processing_level="Header-validated CSV",
            calibration_status="Environmental Meteorology",
            quality_flags=["verified_named_header_csv", "non_compositional"],
            original_source_reference=product_id,
            known_limitations=[
                f"Header-validated REMS table {file_path.name} ({len(data_rows)} records); excluded from composition."
            ],
        )
