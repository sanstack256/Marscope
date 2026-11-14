"""
Offline unit & integration tests for PDS3/PDS4 schema-driven parsing and documented
MSL coordinate association (CoordinateAssociationService & CuriosityDataParser).
"""

import json
import math
from pathlib import Path
from app.ingestion.pds_label import (
    extract_pds3_metadata,
    load_pds3_columns_and_structure,
    parse_pds3_pointer,
)
from app.science.coordinate_association import (
    CoordinateAssociationService,
    extract_site_drive_from_product_name,
    gale_eqc_meters_to_lat_lon,
)
from app.science.curiosity_parser import CuriosityDataParser


def _write_waypoints_geojson(path: Path) -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "RMC": "3_4",
                    "site": 3,
                    "drive": 4,
                    "sol": 10,
                    "lon": 137.44172,
                    "lat": -4.5895,
                    "elev_geoid": -4520.1,
                    "easting": 8145966.2,
                    "northing": -272038.5,
                },
                "geometry": {"type": "Point", "coordinates": [137.44172, -4.5895]},
            },
            {
                "type": "Feature",
                "properties": {
                    "RMC": "5_104",
                    "site": 5,
                    "drive": 104,
                    "sol": 79,
                    "lon": 137.44831,
                    "lat": -4.5912,
                    "elev_geoid": -4516.8,
                },
                "geometry": {"type": "Point", "coordinates": [137.44831, -4.5912]},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pds3_pointer_and_structure_parsing(tmp_path: Path):
    ptr1 = parse_pds3_pointer('("MOC_0000_0089.CSV", 120 <BYTES>)')
    assert ptr1 == {"file": "MOC_0000_0089.CSV", "offset": 120, "unit": "BYTES"}
    ptr2 = parse_pds3_pointer('"REMS_MODRDR.TAB"')
    assert ptr2 == {"file": "REMS_MODRDR.TAB", "offset": 1, "unit": "RECORDS"}

    fmt = tmp_path / "TEST_FMT.FMT"
    fmt.write_text(
        """OBJECT = COLUMN
  NAME = SOL_TS
  DATA_TYPE = CHARACTER
  START_BYTE = 1
  BYTES = 10
END_OBJECT = COLUMN
OBJECT = COLUMN
  NAME = T_AIR
  DATA_TYPE = ASCII_REAL
  UNIT = "K"
  START_BYTE = 12
  BYTES = 8
END_OBJECT = COLUMN
""",
        encoding="utf-8",
    )
    lbl = tmp_path / "TEST.LBL"
    lbl.write_text(
        f"""PDS_VERSION_ID = PDS3
RECORD_TYPE = FIXED_LENGTH
DATA_SET_ID = "MSL-M-REMS-5-MODRDR-V1.0"
PRODUCT_ID = "RME_TEST_MODRDR"
ROVER_MOTION_COUNTER = (3, 4, 0, 0, 0)
OBJECT = TABLE
  INTERCHANGE_FORMAT = ASCII
  ROWS = 2
  COLUMNS = 2
  ^STRUCTURE = "{fmt.name}"
END_OBJECT = TABLE
END
""",
        encoding="utf-8",
    )
    meta = extract_pds3_metadata(lbl)
    assert meta["data_set_id"] == "MSL-M-REMS-5-MODRDR-V1.0"
    assert meta["rover_motion_counter"]["rmc_key"] == "3_4"
    parsed_meta, cols = load_pds3_columns_and_structure(lbl)
    assert "TABLE" in parsed_meta["_OBJECTS"]
    assert len(cols) >= 2
    col_names = [c["NAME"] for c in cols]
    assert "T_AIR" in col_names
    t_air_col = next(c for c in cols if c["NAME"] == "T_AIR")
    assert t_air_col["UNIT"] == "K"


def test_coordinate_association_never_invents_gale_fallback(tmp_path: Path):
    wp_path = tmp_path / "msl_waypoints.json"
    _write_waypoints_geojson(wp_path)
    svc = CoordinateAssociationService(wp_path)

    # Known RMC from filename -> resolves via waypoints
    extracted = extract_site_drive_from_product_name("CL5_398380611MOC_F0030004CHEM01010M1")
    assert extracted is not None
    assert extracted[0] == 3 and extracted[1] == 4

    assoc = svc.resolve_from_pds_metadata(None, product_id="CL5_398380611MOC_F0030004CHEM01010M1")
    assert assoc is not None
    assert math.isclose(assoc.latitude, -4.5895, abs_tol=1e-4)
    assert math.isclose(assoc.longitude, 137.44172, abs_tol=1e-4)

    # Unknown RMC & missing coordinates -> MUST return None (no Gale fallback!)
    unloc = svc.resolve_from_pds_metadata({"site": 999, "drive": 888}, product_id="UNKNOWN_999_888")
    assert unloc is None

    # Planar Gale Crater EQC conversion sanity check (near Bradbury Landing)
    lat_eqc, lon_eqc = gale_eqc_meters_to_lat_lon(8145966.2, -272038.5)
    assert -5.0 < lat_eqc < -4.2
    assert 137.0 < lon_eqc < 138.0


def test_chemcam_psv_distinguished_from_ccs_no_truncation(tmp_path: Path):
    wp_path = tmp_path / "msl_waypoints.json"
    _write_waypoints_geojson(wp_path)
    svc = CoordinateAssociationService(wp_path)

    # 1. Passive reflectance PSV with 250 channels in DIGITAL_NUMBER (no 100-row cap)
    tab = tmp_path / "cl1_398380611psv_f0030004.tab"
    tab.write_text("\n".join(str(1000.0 + i) for i in range(250)) + "\n", encoding="utf-8")
    lbl = tmp_path / "cl1_398380611psv_f0030004.lbl"
    lbl.write_text(
        """PDS_VERSION_ID = PDS3
PRODUCT_ID = "CL1_398380611PSV_F0030004CHEM00010"
PRODUCT_TYPE = "CHEMCAM-PSV"
DATA_SET_ID = "MSL-M-CHEMCAM-LIBS-2-EDR-V1.0"
SOL_NUMBER = 10
MSL:LASER_MODE = "NO"
ROVER_MOTION_COUNTER = (3, 4)
OBJECT = TABLE
  NAME = PSV_TABLE
  COLUMNS = 1
  OBJECT = COLUMN
    NAME = CHANNEL_DN
    UNIT = "DIGITAL_NUMBER"
    DESCRIPTION = "Spectrometer passive counts; see CCAM_DEFAULT_WAVE.TAB"
  END_OBJECT = COLUMN
END_OBJECT = TABLE
END
""",
        encoding="utf-8",
    )
    obs = CuriosityDataParser.parse_chemcam_psv_file(tab, label_path=lbl, coord_service=svc)
    assert obs.measurement_type == "passive_reflectance_spectrum_dn"
    assert obs.units == "DIGITAL_NUMBER"
    assert obs.measurement_value["total_channels_parsed"] == 250
    assert obs.measurement_value["composition_claim"] == "none_uncalibrated_passive_dn"
    assert obs.location is not None and math.isclose(obs.location.latitude, -4.5895, abs_tol=1e-4)

    # 2. Unlocated PSV without RMC -> location MUST remain None
    tab_unloc = tmp_path / "cl1_999999999psv.tab"
    tab_unloc.write_text("120.5\n121.5\n", encoding="utf-8")
    obs_unloc = CuriosityDataParser.parse_chemcam_psv_file(tab_unloc)
    assert obs_unloc.location is None

    # 3. LIBS CCS ^SPREADSHEET with 160 spectral rows -> all 160 parsed
    ccs_csv = tmp_path / "cl5_test_ccs.csv"
    header = "WAVE,MEAN\n"
    rows = "\n".join(f"{240.0 + i * 0.5},{1.25e10 + i}" for i in range(160)) + "\n"
    ccs_csv.write_text(
        f"""PDS_VERSION_ID = PDS3
PRODUCT_TYPE = "CHEMCAM-CCS"
DATA_SET_ID = "MSL-M-CHEMCAM-LIBS-4/5-RDR-V1.0"
^SPREADSHEET = ("{ccs_csv.name}", 1)
# Begin Processed Spectral Data
{header}{rows}""",
        encoding="utf-8",
    )
    obs_ccs = CuriosityDataParser.parse_chemcam_psv_file(ccs_csv, sol=10)
    assert obs_ccs.measurement_type == "libs_spectral_emission"
    assert obs_ccs.measurement_value["sampled_channel_count"] == 160


def test_rems_schema_driven_parsing_preserves_none_location(tmp_path: Path):
    fmt = tmp_path / "ADR_GEOM6.FMT"
    fmt.write_text(
        """OBJECT = COLUMN
  NAME = TIMESTAMP
  DATA_TYPE = CHARACTER
  START_BYTE = 1
  BYTES = 20
END_OBJECT = COLUMN
OBJECT = COLUMN
  NAME = LOCAL_MEAN_SOLAR_TIME
  DATA_TYPE = CHARACTER
  START_BYTE = 22
  BYTES = 16
END_OBJECT = COLUMN
OBJECT = COLUMN
  NAME = GROUND_TEMP
  DATA_TYPE = ASCII_REAL
  UNIT = "K"
  START_BYTE = 39
  BYTES = 8
END_OBJECT = COLUMN
""",
        encoding="utf-8",
    )
    tab = tmp_path / "RME_398334213ADR00100000000_______P9.TAB"
    tab.write_text(
        "2012-08-07T01:00:00Z ,Sol-00001M 00:00  , 245.50 \n"
        "2012-08-07T01:00:01Z ,Sol-00001M 00:01  , 246.10 \n",
        encoding="utf-8",
    )
    lbl = tmp_path / "RME_398334213ADR00100000000_______P9.LBL"
    lbl.write_text(
        f"""PDS_VERSION_ID = PDS3
DATA_SET_ID = "MSL-M-REMS-4-ENVADR-V1.0"
PRODUCT_ID = "RME_398334213ADR00100000000_______P9"
OBJECT = TABLE
  INTERCHANGE_FORMAT = ASCII
  ROWS = 2
  COLUMNS = 3
  ^STRUCTURE = "{fmt.name}"
END_OBJECT = TABLE
END
""",
        encoding="utf-8",
    )
    obs = CuriosityDataParser.parse_rems_adr_summary(tab, sol=1, label_path=lbl)
    assert obs.sol == 1
    assert obs.location is None
    assert obs.measurement_type in {"ancillary_geometry_and_calibration", "environmental_meteorology"}
    assert obs.measurement_value.get("composition_eligible") is False or obs.measurement_value.get("composition_claim") == "none_ancillary_geometry_only"
