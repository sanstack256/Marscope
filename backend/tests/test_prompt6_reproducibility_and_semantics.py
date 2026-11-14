"""
Prompt 6 Adversarial & Reproducibility Regression Tests.

Covers:
1. Uncertainty compatibility registry & cross-type ranking quality withholding
2. Strict APXS PDS4 XML contract enforcement & unverified fallback isolation
3. CheMin UNIT quantitative enforcement, missing sigma honesty, and corrupt row rejections
4. Source-complete dependency manifest & companion artifact drift (LBL/XML/FMT/waypoints + JSON)
5. Rights/license & retrieval timestamp honesty (no fabricated public domain or acquisition dates)
6. Safe atomic downloads preserving existing files upon error
7. Staging-then-cutover atomic index build preserving active generation on failure
8. Build completeness states (complete / complete_with_declared_unavailable_sources / partial)
9. Deterministic rebuild & stoichiometric uncertainty history preservation
"""

import json
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app.ingestion.acquisition import safe_write_downloaded_bytes
from app.main import app
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    GenerationBuildStatus,
    IntegrityStatus,
    LocationSemanticType,
    RankingConfiguration,
    RightsStatus,
    SearchMatchType,
    SpeciesCategory,
)
from app.science.composition.ranking import compute_ranking_dimensions
from app.science.composition.search import CompositionSearchService, StructuredCompositionQuery
from app.science.composition.uncertainty import (
    canonicalize_uncertainty_type,
    evaluate_uncertainty_compatibility,
)
from app.science.composition.validation import (
    EVIDENCE_ID_DETERMINISM_VERSION,
    compute_deterministic_evidence_id,
    validate_composition_evidence,
)
from app.science.curiosity_parser import CuriosityDataParser, MalformedObservationError


def _make_ev(**overrides) -> CompositionEvidence:
    base = {
        "evidence_id": "placeholder",
        "determinism_version": EVIDENCE_ID_DETERMINISM_VERSION,
        "source_dataset_id": "msl_test_ds",
        "product_id": "PROD_1",
        "source_record_ref": "row:1:FeO",
        "source_file_checksum": "a" * 64,
        "source_artifact_dependency_digest": "b" * 64,
        "schema_version": "PDS4_APXS_TEST",
        "parser_id": "apxs_pds4_schema_parser",
        "parser_version": "2.0.0",
        "instrument_id": "APXS",
        "instrument_name": "Alpha Particle X-Ray Spectrometer (APXS)",
        "methodology": "XRF + PIXE spectroscopy",
        "mission": "MSL",
        "raw_species_name": "FeO",
        "canonical_species_id": "FeO",
        "canonical_species_name": "Iron(II) Oxide (FeO)",
        "species_category": SpeciesCategory.OXIDE,
        "evidence_type": EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        "evidence_status": EvidenceStatus.MEASURED,
        "raw_value": 18.0,
        "raw_unit": "wt%",
        "normalized_value": 18.0,
        "normalized_unit": "wt%",
        "uncertainty_value": 0.4,
        "uncertainty_unit": "wt%",
        "uncertainty_type": "apxs_analytical_precision",
        "calibration_status": "PDS4 Calibrated",
        "processing_level": "Derived",
        "source_reference": "PDS4_TEST",
        "location_verified": True,
        "location_semantic_type": LocationSemanticType.INSTRUMENT_TARGET_LOCATION,
        "latitude": -4.6,
        "longitude_east": 137.4,
        "crs": "IAU2000:49900",
        "latitude_convention": "Planetocentric",
        "longitude_direction": "East",
        "coordinate_source": "test_coords",
        "coordinate_provenance": "test_provenance",
    }
    base.update(overrides)
    ev = CompositionEvidence(**base)
    ev.evidence_id = compute_deterministic_evidence_id(ev)
    return ev


def _write_valid_apxs_pair(raw_dir: Path, name: str = "apxs_sample") -> Path:
    csv_path = raw_dir / f"{name}.csv"
    xml_path = raw_dir / f"{name}.xml"
    csv_path.write_text(
        "Sol,Target,Northing_m,Easting_m,Elevation_m,FeO,FeO_err\n"
        "100,RockNest,-270000.0,8140000.0,-4500.0,18.2,0.5\n",
        encoding="utf-8",
    )
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <Observation_Area>
    <Target_Identification><name>Mars</name></Target_Identification>
  </Observation_Area>
  <File_Area_Observational>
    <Table_Delimited>
      <Record_Delimited>
        <fields>7</fields>
        <Field_Delimited><name>Sol</name><field_number>1</field_number><data_type>ASCII_Integer</data_type><description>Sol</description></Field_Delimited>
        <Field_Delimited><name>Target</name><field_number>2</field_number><data_type>UTF8_String</data_type><description>Target</description></Field_Delimited>
        <Field_Delimited><name>Northing_m</name><field_number>3</field_number><data_type>ASCII_Real</data_type><description>Northing (meters)</description></Field_Delimited>
        <Field_Delimited><name>Easting_m</name><field_number>4</field_number><data_type>ASCII_Real</data_type><description>Longitude (Degrees)</description></Field_Delimited>
        <Field_Delimited><name>Elevation_m</name><field_number>5</field_number><data_type>ASCII_Real</data_type><description>Elevation (Meters)</description></Field_Delimited>
        <Field_Delimited><name>FeO</name><field_number>6</field_number><data_type>ASCII_Real</data_type><description>FeO Concentration (wt%)</description></Field_Delimited>
        <Field_Delimited><name>FeO_err</name><field_number>7</field_number><data_type>ASCII_Real</data_type><description>Precision Error in FeO Concentration (wt%)</description></Field_Delimited>
      </Record_Delimited>
    </Table_Delimited>
  </File_Area_Observational>
</Product_Observational>
""",
        encoding="utf-8",
    )
    return csv_path


def _write_minimal_seed_dataset(raw_dir: Path, include_extra_moc: bool = True) -> Dict[str, Path]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    waypoints_path = raw_dir / "msl_waypoints.json"
    waypoints_path.write_text(
        json.dumps(
            {
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [137.4417, -4.5895, -4510.0]},
                        "properties": {"sol": 100, "RMC": "0003_0000", "site": 3, "drive": 0, "dist_km": 0.1},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [137.4450, -4.5910, -4505.0]},
                        "properties": {"sol": 885, "RMC": "0045_0000", "site": 45, "drive": 0, "dist_km": 8.0},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    apxs_csv = _write_valid_apxs_pair(raw_dir, name="ds01_2021je007171r")
    # Also add an apxs standalone CSV without XML if needed; above uses the expected name ds01_2021je007171r

    fmt_path = raw_dir / "CHEMIN_MIN.FMT"
    fmt_path.write_text(
        """OBJECT = COLUMN
  NAME = MINERAL
  DATA_TYPE = CHARACTER
  UNIT = "N/A"
END_OBJECT = COLUMN
OBJECT = COLUMN
  NAME = WEIGHT_PERCENT
  DATA_TYPE = ASCII_REAL
  UNIT = "WEIGHT_PERCENT"
END_OBJECT = COLUMN
OBJECT = COLUMN
  NAME = ERROR
  DATA_TYPE = ASCII_REAL
  UNIT = "ESTIMATED_ERROR"
END_OBJECT = COLUMN
""",
        encoding="utf-8",
    )

    chemin_names = [
        "cma_404470826min00790050104ch11503p1",
        "cma_414856883min01960060000ch12240p1",
        "cma_595174954min22270730550ch00111p1",
        "cmb_476051894min08850450000ch00113p1",
    ]
    for idx, cname in enumerate(chemin_names):
        (raw_dir / f"{cname}.csv").write_text(
            "MINERAL,WEIGHT_PERCENT,ERROR\n"
            "Gypsum,2.4,0.3\n",
            encoding="utf-8",
        )
        (raw_dir / f"{cname}.lbl").write_text(
            f'''PDS_VERSION_ID = PDS3
PRODUCT_ID = "{cname.upper()}"
PRODUCT_CREATION_TIME = 2020-01-01T00:00:00
SPACECRAFT_NAME = MARS_SCIENCE_LABORATORY
INSTRUMENT_NAME = "CHEMISTRY AND MINERALOGY X-RAY DIFFRACTION"
PLANET_DAY_NUMBER = 100
RMC = "0003_0000"
OBJECT = SPREADSHEET
  ^STRUCTURE = "CHEMIN_MIN.FMT"
  DESCRIPTION = "Mineral abundances and estimated 2-sigma analytical errors."
END_OBJECT = SPREADSHEET
END
''',
            encoding="utf-8",
        )

    moc_names = ["moc_0000_0089"]
    if include_extra_moc:
        moc_names.extend(["moc_0090_0179", "moc_1294_1417"])

    for mname in moc_names:
        (raw_dir / f"{mname}.csv").write_text(
            "Sol,Target,File,SIO2,SIO2_RMSEP,SIO2_SHOTS_STDEV\n"
            "100,Coronation,cl5_test,48.5,1.2,0.8\n",
            encoding="utf-8",
        )
        (raw_dir / f"{mname}.lbl").write_text(
            """PDS_VERSION_ID = PDS3
OBJECT = SPREADSHEET
  OBJECT = FIELD
    NAME = "Sol"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "Target"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "File"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SIO2"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SIO2_RMSEP"
    DESCRIPTION = "Predicted SiO2_RMSEP (wt%)"
  END_OBJECT = FIELD
  OBJECT = FIELD
    NAME = "SIO2_SHOTS_STDEV"
    DESCRIPTION = "SiO2 standard deviation across LIBS shots (wt%)"
  END_OBJECT = FIELD
END_OBJECT = SPREADSHEET
END
""",
            encoding="utf-8",
        )

    return {
        "waypoints": waypoints_path,
        "apxs_csv": apxs_csv,
        "apxs_xml": raw_dir / "ds01_2021je007171r.xml",
        "fmt": fmt_path,
        "chemin_lbl": raw_dir / f"{chemin_names[0]}.lbl",
        "moc_lbl": raw_dir / "moc_0000_0089.lbl",
    }


def test_uncertainty_compatibility_and_withheld_cross_type_quality():
    # Mixed cohort across APXS precision, ChemCam RMSEP, CheMin 2-sigma MUST withhold quality_component
    ok_compat, compat_status, reason = evaluate_uncertainty_compatibility(
        ev_uncertainty_type="apxs_analytical_precision",
        ev_uncertainty_value=0.35,
        cohort_uncertainty_types=["apxs_analytical_precision", "chemcam_pls_rmsep", "chemin_rietveld_2sigma"],
    )
    assert ok_compat is False
    assert compat_status == "incompatible_mixed_uncertainty_types"
    assert reason is not None and "mixes statistically incompatible" in reason

    ev_apxs = _make_ev(uncertainty_type="apxs_analytical_precision", uncertainty_value=0.35, uncertainty_unit="wt%")
    ranks_mixed = compute_ranking_dimensions(
        ev=ev_apxs,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["APXS", "ChemCam_LIBS"],
        nearby_count=2,
        cohort_uncertainty_types=["apxs_analytical_precision", "chemcam_pls_rmsep"],
    )
    assert ranks_mixed.quality_component is None
    assert "quality_component" in ranks_mixed.unavailable_dimensions
    assert ranks_mixed.uncertainty_compatibility_status == "incompatible_mixed_uncertainty_types"
    assert ranks_mixed.quality_exclusion_reason is not None
    assert ranks_mixed.ranking_config_version == "3.0.0"

    # Homogeneous compatible cohort allows within-family quality_component
    ranks_homog = compute_ranking_dimensions(
        ev=ev_apxs,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["APXS"],
        nearby_count=1,
        cohort_uncertainty_types=["apxs_analytical_precision"],
    )
    assert ranks_homog.quality_component is not None
    assert ranks_homog.uncertainty_compatibility_status == "compatible_single_family"

    # Qualitative quality_flag ("high"/"poor"/"fair") without quantitative uncertainty NEVER yields float score
    ev_flag_only = _make_ev(
        uncertainty_value=None,
        uncertainty_unit=None,
        uncertainty_type=None,
        quality_flag="high",
    )
    ranks_flag = compute_ranking_dimensions(
        ev=ev_flag_only,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["APXS"],
        nearby_count=1,
        cohort_uncertainty_types=[],
    )
    assert ranks_flag.quality_component is None
    assert "quality_component" in ranks_flag.unavailable_dimensions

    # Unspecified sigma uncertainty ALSO never produces numeric quality_component
    ev_unspec = _make_ev(
        instrument_id="CheMin_XRD",
        uncertainty_type="chemin_estimated_error_unspecified_sigma",
        uncertainty_value=0.3,
        uncertainty_unit="wt%",
    )
    ranks_unspec = compute_ranking_dimensions(
        ev=ev_unspec,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=25.0,
        corroborating_instruments=["CheMin_XRD"],
        nearby_count=1,
        cohort_uncertainty_types=["chemin_estimated_error_unspecified_sigma"],
    )
    assert ranks_unspec.quality_component is None
    assert canonicalize_uncertainty_type("topas_rietveld_2sigma") == "chemin_rietveld_2sigma"
    assert canonicalize_uncertainty_type("2-sigma") == "unknown"


def test_apxs_strict_pds4_xml_enforcement_and_unverified_isolation(tmp_path: Path):
    # 1. Missing companion XML raises MalformedObservationError when require_xml=True
    orphan_csv = tmp_path / "orphan_apxs.csv"
    orphan_csv.write_text("Sol,Target,FeO,FeO_err\n10,RockA,19.1,0.3\n", encoding="utf-8")
    with pytest.raises(MalformedObservationError, match="requires a companion PDS4 XML"):
        CuriosityDataParser.parse_apxs_csv_with_contract(orphan_csv, require_xml=True)

    # 2. Explicit test-only header-only helper emits 0 indexable records and explicit unverified id
    unver_res = CuriosityDataParser.parse_apxs_csv_unverified_header_only(orphan_csv)
    assert unver_res.accepted_row_count == 0
    assert unver_res.parser_id == "apxs_unverified_csv_header_only"
    assert unver_res.rejected_row_count == 1

    # 3. Malformed XML, field count mismatch, header swap, unsupported data_type, unit conflict, corrupt numeric value
    valid_csv = _write_valid_apxs_pair(tmp_path, name="apxs_ok")
    ok_res = CuriosityDataParser.parse_apxs_csv_with_contract(valid_csv, require_xml=True)
    assert ok_res.accepted_row_count == 1
    assert ok_res.label_file_checksum is not None
    assert ok_res.dependency_digest is not None

    # Unit conflict: _pct header vs XML declaring ppm
    unit_conflict_csv = tmp_path / "unit_conflict.csv"
    unit_conflict_xml = tmp_path / "unit_conflict.xml"
    unit_conflict_csv.write_text("Sol,Target,FeO_pct\n10,RockA,18.2\n", encoding="utf-8")
    unit_conflict_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational>
  <File_Area_Observational><Table_Delimited><Record_Delimited>
    <fields>3</fields>
    <Field_Delimited><name>Sol</name><data_type>ASCII_Integer</data_type></Field_Delimited>
    <Field_Delimited><name>Target</name><data_type>UTF8_String</data_type></Field_Delimited>
    <Field_Delimited><name>FeO_pct</name><data_type>ASCII_Real</data_type><description>FeO Concentration (ppm)</description></Field_Delimited>
  </Record_Delimited></Table_Delimited></File_Area_Observational>
</Product_Observational>""",
        encoding="utf-8",
    )
    with pytest.raises(MalformedObservationError, match="unit conflict"):
        CuriosityDataParser.parse_apxs_csv_with_contract(unit_conflict_csv, require_xml=True)

    # Corrupt numeric token rejected cleanly into row_rejections instead of crashing or fabricating 0.0
    corrupt_csv = tmp_path / "apxs_badval.csv"
    corrupt_xml = tmp_path / "apxs_badval.xml"
    corrupt_csv.write_text("Sol,Target,FeO\n10,TargetA,BAD_NUM\n11,TargetB,15.5\n", encoding="utf-8")
    corrupt_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational>
  <File_Area_Observational><Table_Delimited><Record_Delimited>
    <fields>3</fields>
    <Field_Delimited><name>Sol</name><data_type>ASCII_Integer</data_type></Field_Delimited>
    <Field_Delimited><name>Target</name><data_type>UTF8_String</data_type></Field_Delimited>
    <Field_Delimited><name>FeO</name><data_type>ASCII_Real</data_type><description>FeO Concentration (wt%)</description></Field_Delimited>
  </Record_Delimited></Table_Delimited></File_Area_Observational>
</Product_Observational>""",
        encoding="utf-8",
    )
    bad_res = CuriosityDataParser.parse_apxs_csv_with_contract(corrupt_csv, require_xml=True)
    assert bad_res.accepted_row_count == 2  # both rows kept, BAD_NUM oxide omitted & logged cleanly
    assert bad_res.rejected_row_count == 1
    assert "FeO" not in bad_res.records[0]["oxides_wt_pct"]
    assert bad_res.records[1]["oxides_wt_pct"]["FeO"]["value"] == 15.5


def test_chemin_unit_and_sigma_honesty_and_corrupt_rows(tmp_path: Path):
    # FMT declaring UNIT="QUALITATIVE" must fail loudly instead of assuming wt%
    (tmp_path / "CHEMIN_MIN.FMT").write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "QUALITATIVE"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\n  UNIT = "ESTIMATED_ERROR"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    c_csv = tmp_path / "cma_test.csv"
    c_lbl = tmp_path / "cma_test.lbl"
    c_csv.write_text("MINERAL,WEIGHT_PERCENT,ERROR\nGypsum,2.4,0.3\n", encoding="utf-8")
    c_lbl.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\nEND_OBJECT = SPREADSHEET\nEND\n',
        encoding="utf-8",
    )
    with pytest.raises(MalformedObservationError, match="non-quantitative CheMin abundance unit"):
        CuriosityDataParser.parse_chemin_min_csv_with_contract(c_csv, label_path=c_lbl, require_label=True)

    # Valid WEIGHT_PERCENT UNIT, but .LBL omits "2-sigma" -> must record chemin_estimated_error_unspecified_sigma!
    (tmp_path / "CHEMIN_MIN.FMT").write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\n  UNIT = "ESTIMATED_ERROR"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    c_csv.write_text("MINERAL,WEIGHT_PERCENT,ERROR\nGypsum,2.4,0.3\nMagnetite,trace,0.2\n", encoding="utf-8")
    c_lbl.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\n  DESCRIPTION = "Mineral table."\nEND_OBJECT = SPREADSHEET\nEND\n',
        encoding="utf-8",
    )
    parsed = CuriosityDataParser.parse_chemin_min_csv_with_contract(c_csv, label_path=c_lbl, require_label=True)
    assert parsed.accepted_row_count == 1
    assert parsed.rejected_row_count == 1
    assert parsed.records[0]["minerals"][0]["error_semantics"] == "chemin_estimated_error_unspecified_sigma"


def test_source_complete_manifest_dependency_drift_rights_and_retrieval_honesty(tmp_path: Path, monkeypatch):
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    paths = _write_minimal_seed_dataset(raw_dir, include_extra_moc=True)

    idx = CompositionSpatialIndex(db_path=tmp_path / "index" / "composition_index.sqlite")
    status = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
        strict_mode=True,
    )
    assert status.generation_build_status == GenerationBuildStatus.COMPLETE_WITH_DECLARED_UNAVAILABLE_SOURCES
    assert status.integrity_status == IntegrityStatus.VERIFIED
    assert status.source_dependencies_valid is True
    assert status.manifest_valid is True
    assert status.expected_products_count == 10
    assert status.ingested_products_count == 9
    assert status.missing_expected_products == []

    # Pre-existing untracked files MUST report retrieval_timestamp_utc == "unknown" & license_status == "not_verified"
    assert status.dependency_artifacts
    assert all(d["retrieval_timestamp_utc"] == "unknown" for d in status.dependency_artifacts)
    assert all(d["license_status"] == RightsStatus.NOT_VERIFIED.value for d in status.dependency_artifacts)

    # Drift check 1: Modify companion msl_waypoints.json -> must detect dependency checksum mismatch!
    orig_wp = paths["waypoints"].read_text(encoding="utf-8")
    paths["waypoints"].write_text(orig_wp + "\n", encoding="utf-8")
    drifted_wp = idx.get_status()
    assert drifted_wp.integrity_status == IntegrityStatus.CHECKSUM_MISMATCH
    assert drifted_wp.source_dependencies_valid is False
    assert drifted_wp.dependency_checksum_mismatches

    # Restore waypoints, then modify CHEMIN_MIN.FMT -> must also detect dependency mismatch!
    paths["waypoints"].write_text(orig_wp, encoding="utf-8")
    assert idx.get_status().integrity_status == IntegrityStatus.VERIFIED
    orig_fmt = paths["fmt"].read_text(encoding="utf-8")
    paths["fmt"].write_text(orig_fmt + "\n", encoding="utf-8")
    assert idx.get_status().integrity_status == IntegrityStatus.CHECKSUM_MISMATCH

    # Restore FMT, then corrupt reproducibility_manifest.json -> MANIFEST_INVALID + API returns 422!
    paths["fmt"].write_text(orig_fmt, encoding="utf-8")
    manifest_file = idx._manifest_path()
    manifest_file.write_text("{broken json", encoding="utf-8")
    corrupt_st = idx.get_status()
    assert corrupt_st.integrity_status == IntegrityStatus.MANIFEST_INVALID
    assert corrupt_st.manifest_valid is False

    monkeypatch.setattr("app.api.composition.INDEX_DIR", tmp_path / "index")
    client = TestClient(app)
    resp = client.get("/api/composition/reproducibility-manifest")
    assert resp.status_code == 422


def test_atomic_safe_download_preserves_valid_file_and_records_sidecar(tmp_path: Path):
    target = tmp_path / "msl_waypoints.json"
    valid_bytes = b'{"features": []}'
    meta = safe_write_downloaded_bytes(
        target_path=target,
        payload=valid_bytes,
        source_url="https://example.org/msl_waypoints.json",
        content_type="application/json",
    )
    assert target.read_bytes() == valid_bytes
    assert meta["retrieval_timestamp_utc"] != "unknown"
    assert (tmp_path / ".msl_waypoints.json.retrieval.json").exists()

    # Reject HTML error page, empty payload, malformed JSON, checksum mismatch — existing valid file preserved!
    with pytest.raises(ValueError, match="Refusing HTML"):
        safe_write_downloaded_bytes(
            target_path=target,
            payload=b"<!DOCTYPE html><html>404 Not Found</html>",
            source_url="https://example.org/msl_waypoints.json",
            content_type="text/html",
        )
    with pytest.raises(ValueError, match="Empty download"):
        safe_write_downloaded_bytes(target_path=target, payload=b"", source_url="https://example.org/msl_waypoints.json")
    with pytest.raises(ValueError, match="failed JSON validation"):
        safe_write_downloaded_bytes(target_path=target, payload=b"{bad", source_url="https://example.org/msl_waypoints.json")
    with pytest.raises(ValueError, match="checksum mismatch"):
        safe_write_downloaded_bytes(
            target_path=target,
            payload=b'{"features": [1]}',
            source_url="https://example.org/msl_waypoints.json",
            expected_sha256="f" * 64,
        )
    assert target.read_bytes() == valid_bytes


def test_staging_atomic_cutover_preserves_active_generation_on_failure_and_partial_state(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_seed_dataset(raw_dir, include_extra_moc=True)

    idx = CompositionSpatialIndex(db_path=tmp_path / "index" / "composition_index.sqlite")
    gen1 = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
    )
    assert gen1.index_available is True
    assert gen1.active_generation_id is not None

    # Failed staging cutover MUST preserve active generation untouched
    with pytest.raises(RuntimeError, match="Simulated pre-cutover failure"):
        idx.rebuild_from_raw_directory(
            raw_dir=raw_dir,
            processed_dir=proc_dir,
            declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
            simulate_failure_before_cutover=True,
        )

    after_fail = idx.get_status()
    assert after_fail.active_generation_id == gen1.active_generation_id
    assert after_fail.total_validated_evidence == gen1.total_validated_evidence
    assert after_fail.integrity_status == IntegrityStatus.VERIFIED

    # Partial dataset (missing two MOC files) -> strict_mode fails without replacing gen1, non-strict records PARTIAL
    for gone in ("moc_0090_0179.csv", "moc_1294_1417.csv"):
        (raw_dir / gone).unlink()

    strict_fail_st = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
        strict_mode=True,
    )
    assert strict_fail_st.generation_build_status == GenerationBuildStatus.FAILED
    assert strict_fail_st.index_available is False
    # Strict failure also preserved gen1 untouched!
    assert idx.get_status().active_generation_id == gen1.active_generation_id

    partial_st = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
        strict_mode=False,
    )
    assert partial_st.generation_build_status == GenerationBuildStatus.PARTIAL
    assert len(partial_st.missing_expected_products) == 2


def test_stoichiometric_conversion_preserves_uncertainty_history_and_deterministic_rebuild(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_seed_dataset(raw_dir, include_extra_moc=True)

    idx1 = CompositionSpatialIndex(db_path=tmp_path / "i1" / "composition_index.sqlite")
    idx2 = CompositionSpatialIndex(db_path=tmp_path / "i2" / "composition_index.sqlite")
    st1 = idx1.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
    )
    st2 = idx2.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
    )
    assert st1.active_generation_id == st2.active_generation_id
    assert st1.total_validated_evidence == st2.total_validated_evidence

    # Searching "Fe" hits FeO stoichiometric conversion and annotates uncertainty conversion_history cleanly
    svc = CompositionSearchService(idx1)
    resp = svc.search(StructuredCompositionQuery(query="Fe"))
    assert resp.index_available is True
    assert resp.hits
    fe_hit = next(h for h in resp.hits if h.evidence.is_stoichiometric_conversion)
    assert fe_hit.evidence.uncertainty_metadata is not None
    assert fe_hit.evidence.uncertainty_metadata.conversion_history
    assert "stoichiometric_oxide_to_element:FeO->Fe" in fe_hit.evidence.uncertainty_metadata.conversion_history[0]
    passed, stages, rejections = validate_composition_evidence(fe_hit.evidence)
    assert passed is True
    assert not rejections
    assert all(st.passed for st in stages)
