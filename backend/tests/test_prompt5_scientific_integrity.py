"""
Prompt 5 Section 9: Adversarial & Scientific Integrity Regression Tests.
Verifies PDS schema-driven column resolution, zero invented defaults/uncertainties,
spatial semantic separation, validation Stages 1/9/10/12, heuristic ranking honesty,
deterministic index reproducibility, and integrity drift detection.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.science.composition.adapters import (
    CheMinEvidenceAdapter,
    ChemCamEvidenceAdapter,
)
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    IntegrityStatus,
    LocationSemanticType,
    RankingConfiguration,
    SearchMatchType,
    SpeciesCategory,
)
from app.science.composition.ranking import compute_ranking_dimensions
from app.science.composition.validation import (
    compute_deterministic_evidence_id,
    validate_composition_evidence,
)
from app.science.coordinate_association import CoordinateAssociationService
from app.science.curiosity_parser import CuriosityDataParser, MalformedObservationError


def _make_valid_evidence(**overrides) -> CompositionEvidence:
    base = {
        "evidence_id": "placeholder",
        "source_dataset_id": "msl_apxs_test",
        "product_id": "DS01_TEST",
        "source_record_ref": "row:1:FeO",
        "source_file_checksum": "b" * 64,
        "schema_version": "PDS4_APXS_TEST",
        "parser_id": "apxs_pds4_schema_parser",
        "parser_version": "2.0.0",
        "instrument_id": "APXS",
        "instrument_name": "Alpha Particle X-Ray Spectrometer (APXS)",
        "methodology": "X-ray fluorescence and alpha-particle induced X-ray emission spectroscopy",
        "mission": "MSL",
        "raw_species_name": "FeO",
        "canonical_species_id": "FeO",
        "canonical_species_name": "Iron(II) Oxide (FeO)",
        "species_category": SpeciesCategory.OXIDE,
        "evidence_type": EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        "evidence_status": EvidenceStatus.MEASURED,
        "raw_value": 19.8,
        "raw_unit": "wt%",
        "normalized_value": 19.8,
        "normalized_unit": "wt%",
        "uncertainty_value": 0.4,
        "uncertainty_unit": "wt%",
        "uncertainty_type": "1-sigma",
        "calibration_status": "PDS4 Peer-Reviewed Calibrated",
        "processing_level": "Derived Calibrated Oxide",
        "source_reference": "PDS4_APXS_TEST",
        "location_verified": True,
        "location_semantic_type": LocationSemanticType.INSTRUMENT_TARGET_LOCATION,
        "latitude": -4.5895,
        "longitude_east": 137.44172,
        "elevation_m": -4520.0,
        "crs": "IAU2000:49900",
        "latitude_convention": "Planetocentric",
        "longitude_direction": "East",
        "coordinate_source": "pds4_apxs_gale_eqc_projection",
        "coordinate_provenance": "Converted APXS Gale Crater Equirectangular planar coordinates",
        "coordinate_uncertainty_m": None,
    }
    base.update(overrides)
    explicit_id = "evidence_id" in overrides
    ev = CompositionEvidence(**base)
    if not explicit_id:
        ev.evidence_id = compute_deterministic_evidence_id(ev)
    return ev


def test_pds3_chemcam_moc_reordered_columns_and_header_mismatch(tmp_path: Path):
    wp_path = tmp_path / "msl_waypoints.json"
    wp_path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"RMC":"3_4","lon":137.44172,"lat":-4.5895,"elev_geoid":-4520.0}}]}',
        encoding="utf-8",
    )
    coord_svc = CoordinateAssociationService()
    coord_svc.load_waypoints_geojson(wp_path)

    # Put DISTANCE_TO_TARGET, FeOT, SHOTS_STDEV, RMSEP in non-standard column order
    lbl_path = tmp_path / "moc_reordered.lbl"
    lbl_path.write_text(
        """PDS_VERSION_ID = PDS3
PRODUCT_ID = "MOC_REORDERED"
OBJECT = SPREADSHEET
  ROWS = 2
  FIELD_DELIMITER = "COMMA"
  FIELDS = 11
  OBJECT = FIELD
    NAME = "SOL"
    FIELD_NUMBER = 1
    DATA_TYPE = INTEGER
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "FEOT_RMSEP"
    FIELD_NUMBER = 2
    DATA_TYPE = ASCII_REAL
    UNIT = "WT%"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "DISTANCE_TO_TARGET"
    FIELD_NUMBER = 3
    DATA_TYPE = ASCII_REAL
    UNIT = "M"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SUM_OF_OXIDES"
    FIELD_NUMBER = 4
    DATA_TYPE = ASCII_REAL
    UNIT = "WT%"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "FEOT"
    FIELD_NUMBER = 5
    DATA_TYPE = ASCII_REAL
    UNIT = "WT%"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "FEOT_SHOTS_STDEV"
    FIELD_NUMBER = 6
    DATA_TYPE = ASCII_REAL
    UNIT = "WT%"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SITE_ID"
    FIELD_NUMBER = 7
    DATA_TYPE = INTEGER
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "DRIVE_ID"
    FIELD_NUMBER = 8
    DATA_TYPE = INTEGER
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "TARGET_NAME"
    FIELD_NUMBER = 9
    DATA_TYPE = CHARACTER
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SCLK"
    FIELD_NUMBER = 10
    DATA_TYPE = INTEGER
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "PRODUCT_NAME"
    FIELD_NUMBER = 11
    DATA_TYPE = CHARACTER
  END_OBJECT = FIELD
END_OBJECT = SPREADSHEET
END
""",
        encoding="utf-8",
    )
    csv_path = tmp_path / "moc_reordered.csv"
    csv_path.write_text(
        "SOL,FEOT_RMSEP,DISTANCE_TO_TARGET,SUM_OF_OXIDES,FEOT,FEOT_SHOTS_STDEV,SITE_ID,DRIVE_ID,TARGET_NAME,SCLK,PRODUCT_NAME\n"
        "54,2.1,3.4,98.5,18.75,0.65,3,4,Bathurst_Test,401234567,CL5_401234567CCS_F0030004CCAM04010P3\n"
        "55,1.9,2.8,97.2,15.20,0.55,99,99,Unmatched_Test,401234999,CL5_401234999CCS_F0990099CCAM04010P3\n",
        encoding="utf-8",
    )

    res = CuriosityDataParser.parse_chemcam_moc_table_with_contract(
        csv_path, label_path=lbl_path, coord_service=coord_svc
    )
    assert len(res.records) == 2
    rec0 = res.records[0]
    assert rec0["oxides"]["FeOT"]["value"] == pytest.approx(18.75)
    assert rec0["oxides"]["FeOT"]["rmsep"] == pytest.approx(2.1)
    assert rec0["oxides"]["FeOT"]["shots_stdev"] == pytest.approx(0.65)
    assert rec0["total_wt_pct"] == pytest.approx(98.5)
    # Distance to target is standoff ONLY, NEVER invented as positional uncertainty
    assert rec0["distance_m"] == pytest.approx(3.4)
    assert rec0["coordinates"].coordinate_uncertainty_m is None
    assert rec0["coordinates"].instrument_standoff_m == pytest.approx(3.4)
    assert rec0["coordinates"].location_semantic_type == LocationSemanticType.ROVER_STATION_LOCATION

    # Second row has unmatched RMC 99_99 -> coordinates None / UNLOCATED
    assert res.records[1]["coordinates"] is None

    # Adapter preserves primary uncertainty=RMSEP and secondary=shots_stdev, plus semantic separation
    acc, _ = ChemCamEvidenceAdapter.adapt_moc_csv(
        csv_path,
        label_path=lbl_path,
        source_dataset_id="msl_chemcam_reordered",
        coord_service=coord_svc,
    )
    loc_evs = [e for e in acc if e.location_verified]
    unloc_evs = [e for e in acc if not e.location_verified]
    assert len(loc_evs) == 1
    assert len(unloc_evs) == 1
    assert loc_evs[0].uncertainty_value == pytest.approx(2.1)
    assert loc_evs[0].secondary_uncertainty_value == pytest.approx(0.65)
    assert loc_evs[0].instrument_standoff_m == pytest.approx(3.4)
    assert loc_evs[0].coordinate_uncertainty_m is None
    assert loc_evs[0].location_semantic_type == LocationSemanticType.ROVER_STATION_LOCATION
    assert unloc_evs[0].location_semantic_type == LocationSemanticType.UNLOCATED

    # Header mismatch against PDS3 OBJECT = FIELD schema must fail loudly
    bad_csv = tmp_path / "moc_bad_header.csv"
    bad_csv.write_text(
        "SOL,FEOT_RMSEP,DISTANCE_TO_TARGET,SUM_OF_OXIDES,WRONG_OXIDE,FEOT_SHOTS_STDEV,SITE_ID,DRIVE_ID,TARGET_NAME,SCLK,PRODUCT_NAME\n"
        "54,2.1,3.4,98.5,18.75,0.65,3,4,Bathurst_Test,401234567,CL5_401234567CCS_F0030004\n",
        encoding="utf-8",
    )
    with pytest.raises(MalformedObservationError, match="schema mismatch"):
        CuriosityDataParser.parse_chemcam_moc_table_with_contract(bad_csv, label_path=lbl_path)


def test_pds4_apxs_reordered_columns_and_preserves_none_quality(tmp_path: Path):
    xml_path = tmp_path / "ds01_test.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <File_Area_Observational>
    <Table_Delimited>
      <Record_Delimited>
        <Field_Delimited><name>FeO</name><field_number>1</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>FeO_err</name><field_number>2</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>Easting_m</name><field_number>3</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Northing_m</name><field_number>4</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Elevation_m</name><field_number>5</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Quality</name><field_number>6</field_number><data_type>ASCII_String</data_type></Field_Delimited>
        <Field_Delimited><name>Target</name><field_number>7</field_number><data_type>ASCII_String</data_type></Field_Delimited>
        <Field_Delimited><name>Sol</name><field_number>8</field_number><data_type>ASCII_Integer</data_type></Field_Delimited>
      </Record_Delimited>
    </Table_Delimited>
  </File_Area_Observational>
</Product_Observational>
""",
        encoding="utf-8",
    )
    csv_path = tmp_path / "ds01_test.csv"
    csv_path.write_text(
        "FeO_pct,FeO_err,Easting_m,Northing_m,Elevation_m,Quality,Target,Sol\n"
        "21.4,0.6,8145966.2,-272038.5,-4520.0,,Rocknest_Test,82\n",
        encoding="utf-8",
    )

    res = CuriosityDataParser.parse_apxs_csv_with_contract(csv_path, label_path=xml_path)
    assert len(res.records) == 1
    rec = res.records[0]
    assert rec["oxides_wt_pct"]["FeO"]["value"] == pytest.approx(21.4)
    assert rec["oxides_wt_pct"]["FeO"]["error"] == pytest.approx(0.6)
    # Missing Quality stays None (never fabricated "Nominal")
    assert rec["quality_flag"] is None
    assert rec["coordinates"] is not None
    assert rec["coordinates"]["location_semantic_type"] == LocationSemanticType.INSTRUMENT_TARGET_LOCATION.value
    assert rec["coordinates"].get("uncertainty_m") is None


def test_chemin_missing_fmt_raises_and_unknown_mineral_never_guessed(tmp_path: Path):
    lbl_missing_fmt = tmp_path / "cma_001min00790030004ch11503p1.lbl"
    lbl_missing_fmt.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "NONEXISTENT_CHEMIN.FMT"\nEND_OBJECT = SPREADSHEET\n',
        encoding="utf-8",
    )
    csv_path = tmp_path / "cma_001min00790030004ch11503p1.csv"
    csv_path.write_text("MINERAL,PERCENT,ERROR\nGypsum,3.4,1.1\n", encoding="utf-8")

    # strict_structure=True must fail cleanly instead of falling back silently
    with pytest.raises(FileNotFoundError, match="NONEXISTENT_CHEMIN.FMT"):
        CuriosityDataParser.parse_chemin_min_csv_with_contract(csv_path, label_path=lbl_missing_fmt)

    # With valid CHEMIN_MIN.FMT, unknown mineral species must be rejected as UNKNOWN_SPECIES (never guessed)
    fmt_path = tmp_path / "CHEMIN_MIN.FMT"
    fmt_path.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = PERCENT\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  UNIT = "ESTIMATED_ERROR"\n  DESCRIPTION = "2-sigma TOPAS Rietveld"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    lbl_ok = tmp_path / "cma_001min00790030004ch11503p2.lbl"
    lbl_ok.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\nEND_OBJECT = SPREADSHEET\n',
        encoding="utf-8",
    )
    csv_unknown = tmp_path / "cma_001min00790030004ch11503p2.csv"
    csv_unknown.write_text(
        "MINERAL,PERCENT,ERROR\nUnobtainium_Phase,12.5,1.2\nGypsum,3.4,1.1\n",
        encoding="utf-8",
    )

    acc, rej = CheMinEvidenceAdapter.adapt_rdr5_csv(
        csv_unknown,
        label_path=lbl_ok,
        source_dataset_id="msl_chemin_test",
        coord_service=CoordinateAssociationService(),
    )
    assert len(acc) == 1
    assert acc[0].canonical_species_id == "gypsum"
    assert acc[0].uncertainty_type == "chemin_rietveld_2sigma"
    assert any(r.rejection_code == "UNKNOWN_SPECIES" and r.raw_species == "Unobtainium_Phase" for r in rej)


def test_validation_stages_1_9_10_12_adversarial():
    # Stage 1: missing source_file_checksum / schema_version / parser_version rejected
    for field_name in ("source_file_checksum", "schema_version", "parser_version"):
        ok, _, rej = validate_composition_evidence(_make_valid_evidence(**{field_name: None}))
        assert not ok and rej is not None and rej.rejection_stage == 1

    # Stage 9: uncertainty unit mismatch or missing uncertainty_type rejected
    ok_u, _, rej_u = validate_composition_evidence(_make_valid_evidence(uncertainty_unit="ppm"))
    assert not ok_u and rej_u is not None and rej_u.rejection_stage == 9

    ok_t, _, rej_t = validate_composition_evidence(_make_valid_evidence(uncertainty_type=None))
    assert not ok_t and rej_t is not None and rej_t.rejection_stage == 9

    # Stage 10: semantic type conflict (verified location claiming UNLOCATED) rejected
    ok_sem, _, rej_sem = validate_composition_evidence(
        _make_valid_evidence(location_semantic_type=LocationSemanticType.UNLOCATED)
    )
    assert not ok_sem and rej_sem is not None and rej_sem.rejection_stage == 10

    # Stage 12: tampered non-deterministic evidence_id rejected
    ok_id, _, rej_id = validate_composition_evidence(
        _make_valid_evidence(evidence_id="tampered_arbitrary_id_123")
    )
    assert not ok_id and rej_id is not None and rej_id.rejection_stage == 12


def test_ranking_missing_uncertainty_and_single_obs_no_defaults():
    # Evidence without uncertainty/quality & 1 obs -> quality_component & corroboration_component MUST be None
    ev = _make_valid_evidence(uncertainty_value=None, uncertainty_unit=None, uncertainty_type=None)
    dims = compute_ranking_dimensions(
        ev=ev,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["APXS"],
        nearby_count=1,
        distance_m=None,
    )
    assert dims.is_heuristic_only is True
    assert dims.quality_component is None
    assert dims.corroboration_component is None
    assert "quality_component" in dims.unavailable_dimensions
    assert "corroboration_component" in dims.unavailable_dimensions

    # Custom RankingConfiguration changes score cleanly and records config ID/version
    custom_cfg = RankingConfiguration(
        ranking_config_id="custom_abundance_heavy",
        ranking_config_version="9.9.0",
        weights={
            "evidence_tier": 0.10,
            "abundance": 0.90,
            "quality": 0.0,
            "corroboration": 0.0,
            "spatial_proximity": 0.0,
        },
    )
    dims_custom = compute_ranking_dimensions(
        ev=ev,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["APXS"],
        nearby_count=1,
        distance_m=None,
        config=custom_cfg,
    )
    assert dims_custom.ranking_config_id == "custom_abundance_heavy"
    assert dims_custom.ranking_config_version == "9.9.0"
    assert dims_custom.composite_rank_score != dims.composite_rank_score


def test_deterministic_rebuild_and_integrity_drift(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()

    (raw_dir / "msl_waypoints.json").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"RMC":"3_4","lon":137.44172,"lat":-4.5895,"elev_geoid":-4520.0}}]}',
        encoding="utf-8",
    )
    apxs_csv = raw_dir / "ds01_2021je007171r.csv"
    apxs_csv.write_text(
        "Sol,Target,Northing_m,Easting_m,Elevation_m,FeO_pct,FeO_err\n54,Bathurst,-272038.5,8145966.2,-4520.0,19.8,0.4\n",
        encoding="utf-8",
    )
    apxs_xml = raw_dir / "ds01_2021je007171r.xml"
    apxs_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <File_Area_Observational><Table_Delimited><Record_Delimited><fields>7</fields>
    <Field_Delimited><name>Sol</name><field_number>1</field_number><data_type>ASCII_Integer</data_type></Field_Delimited>
    <Field_Delimited><name>Target</name><field_number>2</field_number><data_type>ASCII_String</data_type></Field_Delimited>
    <Field_Delimited><name>Northing_m</name><field_number>3</field_number><data_type>ASCII_Real</data_type></Field_Delimited>
    <Field_Delimited><name>Easting_m</name><field_number>4</field_number><data_type>ASCII_Real</data_type></Field_Delimited>
    <Field_Delimited><name>Elevation_m</name><field_number>5</field_number><data_type>ASCII_Real</data_type></Field_Delimited>
    <Field_Delimited><name>FeO</name><field_number>6</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
    <Field_Delimited><name>FeO_err</name><field_number>7</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
  </Record_Delimited></Table_Delimited></File_Area_Observational>
</Product_Observational>
""",
        encoding="utf-8",
    )

    idx1 = CompositionSpatialIndex(tmp_path / "idx1.sqlite")
    idx2 = CompositionSpatialIndex(tmp_path / "idx2.sqlite")
    st1 = idx1.rebuild_from_raw_directory(raw_dir, processed_dir)
    st2 = idx2.rebuild_from_raw_directory(raw_dir, processed_dir)

    assert st1.integrity_status == IntegrityStatus.VERIFIED
    assert st1.active_generation_id == st2.active_generation_id
    assert st1.total_validated_evidence == st2.total_validated_evidence
    ids1 = sorted(h.evidence_id for h in idx1.query_evidence(["FeO"], located_only=False))
    ids2 = sorted(h.evidence_id for h in idx2.query_evidence(["FeO"], located_only=False))
    assert ids1 == ids2 and len(ids1) == 1
    assert st1.reproducibility_manifest_path is not None
    assert Path(st1.reproducibility_manifest_path).exists()

    # Checksum mismatch detection
    apxs_csv.write_text(
        "Sol,Target,Northing_m,Easting_m,Elevation_m,FeO_pct,FeO_err\n54,Bathurst,-272038.5,8145966.2,-4520.0,20.1,0.4\n",
        encoding="utf-8",
    )
    drift_st = idx1.get_status()
    assert drift_st.integrity_status == IntegrityStatus.CHECKSUM_MISMATCH
    assert drift_st.checksum_valid is False

    # Missing source file detection
    apxs_csv.unlink()
    missing_st = idx1.get_status()
    assert missing_st.integrity_status == IntegrityStatus.SOURCE_FILES_MISSING
    assert len(missing_st.missing_source_files) >= 1

    # API endpoint reproducibility-manifest returns authenticated manifest (200), unbuilt (404), or unauthenticated legacy (422)
    client = TestClient(app)
    res_man = client.get("/api/composition/reproducibility-manifest")
    assert res_man.status_code in (200, 404, 422)
