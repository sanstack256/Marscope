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
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.ingestion.pds_label import (
    extract_pds3_metadata,
    load_pds3_columns_and_structure,
    parse_pds3_pointer,
)
from app.schemas.observation import Observation, ObservationCoordinates
from app.science.coordinate_association import (
    CoordinateAssociationService,
    gale_eqc_meters_to_lat_lon,
)


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

        # Resolve coordinates strictly from PDS metadata / RMC waypoints (never fabricate Gale defaults)
        assoc_coords = (
            coord_service.resolve_from_pds_metadata(pds_meta, product_id=product_id, uncertainty_m=10.0)
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
    def parse_chemcam_moc_table(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
    ) -> List[Dict[str, Any]]:
        """
        Parse NASA PDS MSL ChemCam Multivariant Oxides Composition (MOC) CSV table
        (e.g., moc_0000_0089.csv + .lbl).
        Returns structured row dicts preserving exact oxide values, RMSEP, shot stdev, and RMC.
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"ChemCam MOC table not found: {csv_path}")

        lbl_file = _resolve_companion_label(csv_path, label_path)
        fields: List[Dict[str, Any]] = []
        pds_meta: Dict[str, Any] = {}
        data_offset_bytes = 0
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            _, fields = load_pds3_columns_and_structure(lbl_file, table_object_names=("SPREADSHEET",))
            sp_ptr = (pds_meta.get("pointers") or {}).get("^SPREADSHEET")
            if sp_ptr and sp_ptr.get("unit") == "BYTES":
                data_offset_bytes = max(0, int(sp_ptr["offset"]) - 1)

        raw_bytes = csv_path.read_bytes()
        text = raw_bytes[data_offset_bytes:].decode("utf-8", errors="replace")

        oxide_specs = [
            ("SiO2", 2, 4, 5),
            ("TiO2", 6, 8, 9),
            ("Al2O3", 10, 12, 13),
            ("FeOT", 14, 16, 17),
            ("MgO", 18, 20, 21),
            ("CaO", 22, 24, 25),
            ("Na2O", 26, 28, 29),
            ("K2O", 30, 32, 33),
            ("MnO", 34, 36, 37),
        ]

        rows: List[Dict[str, Any]] = []
        reader = csv.reader(text.splitlines())
        for row_idx, cols in enumerate(reader, start=1):
            if not cols or len(cols) < 38:
                continue
            prod_name = cols[0].strip()
            # Skip unskipped quartile header rows when parsed without companion .LBL byte offset
            if not prod_name.upper().startswith(("CL", "CR", "CC")):
                continue
            target_name = cols[1].strip()
            total_pct = _safe_float(cols[38]) if len(cols) > 38 else None
            dist_mm = _safe_float(cols[39]) if len(cols) > 39 else None
            if dist_mm is None and len(cols) > 39:
                # Some MOC releases have TOTAL at idx 38 and DISTANCE_M or DISTANCE_MM at idx 39
                dist_mm = _safe_float(cols[39])

            coords = (
                coord_service.resolve_from_pds_metadata(None, product_id=prod_name, uncertainty_m=8.0)
                if coord_service is not None
                else None
            )

            oxides: Dict[str, Dict[str, Optional[float]]] = {}
            for ox_name, val_idx, rmsep_idx, stdev_idx in oxide_specs:
                val = _safe_float(cols[val_idx])
                rmsep = _safe_float(cols[rmsep_idx])
                stdev = _safe_float(cols[stdev_idx])
                oxides[ox_name] = {
                    "value": val,
                    "rmsep": rmsep,
                    "shots_stdev": stdev,
                }

            rows.append(
                {
                    "row_index": row_idx,
                    "product_name": prod_name,
                    "target_name": target_name,
                    "data_set_id": pds_meta.get("data_set_id") or "MSL-M-CHEMCAM-LIBS-4/5-RDR-V1.0",
                    "release_id": pds_meta.get("parsed_odl", {}).get("RELEASE_ID"),
                    "total_wt_pct": total_pct,
                    "distance_m": dist_mm,
                    "oxides": oxides,
                    "coordinates": coords,
                    "schema_fields_count": len(fields),
                }
            )
        return rows

    @staticmethod
    def parse_apxs_csv(
        csv_path: Path,
        source_dataset_id: str = "msl_apxs_supplement_sols_0_3076",
        product_id: str = "DS01_2021JE007171R",
    ) -> List[Dict[str, Any]]:
        """
        Parse calibrated NASA PDS4 APXS elemental/oxide CSV table (e.g., ds01_2021je007171r.csv),
        converting Gale Crater Equirectangular (Northing_m, Easting_m) into verified IAU2000 coords.
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"APXS CSV not found: {csv_path}")

        rows: List[Dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_idx, r in enumerate(reader, start=1):
                target = (r.get("Target") or "").strip()
                if not target:
                    continue
                sol_val = _safe_float(r.get("Sol"))
                northing = _safe_float(r.get("Northing_m"))
                easting = _safe_float(r.get("Easting_m"))
                elevation = _safe_float(r.get("Elevation_m"))
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
                            "coordinate_source": f"pds4_apxs_gale_eqc_projection:{csv_path.name}",
                            "coordinate_provenance": (
                                f"Converted APXS Gale Crater Equirectangular coordinates "
                                f"(E={easting:.2f}m, N={northing:.2f}m) from {csv_path.name}."
                            ),
                            "coordinate_uncertainty_m": 5.0,
                        }
                    except Exception:
                        coords = None

                oxides_wt_pct: Dict[str, Dict[str, Optional[float]]] = {}
                for ox in ("Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O", "CaO", "TiO2", "Cr2O3", "MnO", "FeO"):
                    val = _safe_float(r.get(f"{ox}_pct"))
                    err = _safe_float(r.get(f"{ox}_err"))
                    if val is not None or err is not None:
                        oxides_wt_pct[ox] = {"value": val, "error": err, "unit": "wt%"}

                trace_ppm: Dict[str, Dict[str, Optional[float]]] = {}
                for el in ("Ni", "Zn", "Br"):
                    val = _safe_float(r.get(f"{el}_ppm"))
                    err = _safe_float(r.get(f"{el}_err"))
                    if val is not None or err is not None:
                        trace_ppm[el] = {"value": val, "error": err, "unit": "ppm"}

                rows.append(
                    {
                        "row_index": row_idx,
                        "source_dataset_id": source_dataset_id,
                        "product_id": product_id,
                        "sol": int(sol_val) if sol_val is not None else None,
                        "target_name": target,
                        "strat_group": (r.get("Strat_group_formal") or "").strip() or None,
                        "strat_formation": (r.get("Strat_fm") or "").strip() or None,
                        "strat_member": (r.get("Strat_mbr") or "").strip() or None,
                        "waypoint_name": (r.get("Informal waypoint/outcrop/region name") or "").strip() or None,
                        "preparation_method": (r.get("Preparation_method") or "").strip() or None,
                        "quality_flag": (r.get("Quality") or "").strip() or "Nominal",
                        "fit_type": (r.get("Fit_Type") or "").strip() or None,
                        "start_time": (r.get("Start_Time") or "").strip() or None,
                        "coordinates": coords,
                        "oxides_wt_pct": oxides_wt_pct,
                        "trace_ppm": trace_ppm,
                    }
                )
        return rows

    @staticmethod
    def parse_chemin_min_csv(
        csv_path: Path,
        label_path: Optional[Path] = None,
        coord_service: Optional[CoordinateAssociationService] = None,
        extra_structure_dirs: Optional[List[Path]] = None,
    ) -> Dict[str, Any]:
        """
        Parse NASA PDS3 CheMin RDR5 mineral abundance spreadsheet (e.g., cma_..._min...csv + .lbl).
        Uses PDS3 schema / CHEMIN_MIN.FMT definitions (`MINERAL`, `PERCENT`, `ERROR`).
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"CheMin mineral CSV missing: {csv_path}")

        lbl_file = _resolve_companion_label(csv_path, label_path)
        pds_meta: Dict[str, Any] = {}
        columns: List[Dict[str, Any]] = []
        if lbl_file:
            pds_meta = extract_pds3_metadata(lbl_file)
            _, columns = load_pds3_columns_and_structure(
                lbl_file,
                table_object_names=("SPREADSHEET",),
                extra_structure_dirs=extra_structure_dirs,
            )

        product_id = str(pds_meta.get("product_id") or csv_path.stem.upper())
        # Extract sample target name from PDS3 SPREADSHEET DESCRIPTION when available
        tbl_obj = (pds_meta.get("parsed_odl") or {}).get("_OBJECTS", {}).get("SPREADSHEET", {})
        desc = str(tbl_obj.get("DESCRIPTION") or "")

        coords = (
            coord_service.resolve_from_pds_metadata(pds_meta, product_id=product_id, uncertainty_m=15.0)
            if coord_service is not None
            else None
        )

        # Extract Sol cleanly from filename MIN<SOL4><SITE3><DRIVE4> when PLANET_DAY_NUMBER absent
        sol_val = pds_meta.get("planet_day_number")
        if sol_val is None:
            import re

            m = re.search(r"MIN(\d{4})(\d{3})(\d{4})CH", product_id)
            if m:
                sol_val = int(m.group(1))

        minerals: List[Dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for idx, r in enumerate(reader, start=1):
                mineral_name = (r.get("MINERAL") or r.get("Mineral") or "").strip()
                pct = _safe_float(r.get("PERCENT") if "PERCENT" in r else r.get("WEIGHT_PERCENT"))
                err = _safe_float(r.get("ERROR") if "ERROR" in r else r.get("ESTIMATED_ERROR"))
                if not mineral_name:
                    continue
                minerals.append(
                    {
                        "row_index": idx,
                        "mineral": mineral_name,
                        "weight_percent": pct,
                        "estimated_error": err,
                    }
                )

        if not minerals:
            raise MalformedObservationError(f"CheMin product '{csv_path.name}' yielded zero mineral rows.")

        return {
            "product_id": product_id,
            "data_set_id": pds_meta.get("data_set_id") or "MSL-M-CHEMIN-4-RDR-V1.0",
            "product_type": pds_meta.get("product_type") or "CHEMIN_MIN",
            "start_time": pds_meta.get("start_time"),
            "sol": sol_val,
            "description": desc,
            "coordinates": coords,
            "columns_schema": columns,
            "minerals": minerals,
        }

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
