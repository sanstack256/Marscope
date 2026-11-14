"""
Offline scientific validation, normalization, spatial R*Tree indexing, geodesic search,
target provenance separation, and API integration tests for MARSCOPE Prompt 4.
"""

from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.dataset import (
    Dataset,
    GeographicCoverage,
    MetadataVerification,
    VerificationState,
)
from app.schemas.target import TargetGenerationRequest, TargetProvenanceStatus
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    CompositionSearchMode,
    EvidenceStatus,
    EvidenceType,
    LocationSemanticType,
    SpeciesCategory,
)
from app.science.composition.normalization import (
    canonicalize_unit,
    normalize_concentration_value,
    oxide_wt_pct_to_element_wt_pct,
)
from app.science.composition.search import CompositionSearchService, StructuredCompositionQuery
from app.science.composition.species import get_species_by_id, resolve_species_query
from app.science.composition.validation import (
    compute_deterministic_evidence_id,
    validate_composition_evidence,
)
from app.science.target_registry import TargetRegistryService
from app.services.destination_service import DestinationEvaluationService


def _make_sample_evidence(**overrides) -> CompositionEvidence:
    base = {
        "evidence_id": "ev_sample_01",
        "source_dataset_id": "msl_apxs_test",
        "product_id": "DS01_TEST",
        "source_record_ref": "row:1:FeO",
        "instrument_id": "APXS",
        "instrument_name": "Alpha Particle X-Ray Spectrometer",
        "processing_level": "Level 4 Derived Oxide",
        "calibration_status": "Calibrated",
        "target_name": "Bathurst_Inlet",
        "sol": 54,
        "canonical_species_id": "FeO",
        "canonical_species_name": "Iron(II) Oxide",
        "species_category": SpeciesCategory.OXIDE,
        "raw_species_name": "FeO_pct",
        "evidence_type": EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        "evidence_status": EvidenceStatus.MEASURED,
        "raw_value": 19.5,
        "raw_unit": "wt%",
        "normalized_value": 19.5,
        "normalized_unit": "wt%",
        "uncertainty_value": 0.4,
        "uncertainty_unit": "wt%",
        "uncertainty_type": "analytical_error",
        "methodology": "APXS alpha-XRF quantitative oxide determination",
        "source_reference": "PDS4_APXS_TEST",
        "source_file_checksum": "a" * 64,
        "schema_version": "PDS4_TEST_1",
        "parser_version": "test_parser_v1",
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


def test_species_vocabulary_normalization_and_ambiguity():
    # Element resolution
    res_fe = resolve_species_query("iron")
    assert res_fe.resolved and not res_fe.ambiguous
    assert res_fe.species is not None and res_fe.species.canonical_id == "Fe"

    # Mineral vs element separation
    res_s = resolve_species_query("sulfur")
    assert res_s.resolved and res_s.species is not None and res_s.species.canonical_id == "S"
    res_gyp = resolve_species_query("gypsum")
    assert res_gyp.resolved and res_gyp.species is not None and res_gyp.species.category == SpeciesCategory.MINERAL

    # Ambiguous terms explicitly flagged
    res_silica = resolve_species_query("silica")
    assert res_silica.ambiguous and len(res_silica.candidates) >= 2
    res_iron_ox = resolve_species_query("iron oxide")
    assert res_iron_ox.ambiguous and len(res_iron_ox.candidates) >= 2

    # Unit canonicalization & IUPAC stoichiometry
    assert canonicalize_unit("pct") == "wt%"
    assert canonicalize_unit("ug/g") == "ppm"
    spec_na = get_species_by_id("Na2O")
    assert spec_na is not None
    v_ppm, u_ppm, _ = normalize_concentration_value(spec_na, 1.5, "wt%", target_unit="ppm")
    assert u_ppm == "ppm" and v_ppm == 15000.0

    el_id, el_val, el_err, formula = oxide_wt_pct_to_element_wt_pct("FeO", 10.0, 0.5)
    assert el_id == "Fe"
    assert 7.75 < el_val < 7.80
    assert 0.38 < (el_err or 0) < 0.40
    assert "IUPAC" in formula


def test_validation_pipeline_rejects_invalid_and_non_composition_records():
    # Stage 2: REMS telemetry rejected
    ok_rems, _, rej_rems = validate_composition_evidence(
        _make_sample_evidence(instrument_id="REMS", raw_species_name="T_AIR")
    )
    assert not ok_rems and rej_rems is not None and rej_rems.rejection_code == "NON_COMPOSITION_INSTRUMENT"

    # Stage 3: ChemCam PSV DIGITAL_NUMBER rejected
    ok_psv, _, rej_psv = validate_composition_evidence(
        _make_sample_evidence(
            instrument_id="ChemCam_PSV",
            calibration_status="CHEMCAM-PSV",
            processing_level="Level 1 Passive Spectrum",
            evidence_type=EvidenceType.UNINTERPRETED_SPECTRAL_RECORD,
            raw_unit="DIGITAL_NUMBER",
        )
    )
    assert not ok_psv and rej_psv is not None and rej_psv.rejection_code == "UNCALIBRATED_OR_PASSIVE_RECORD"

    # Stage 4: ChemCam claiming XRD crystalline mineral directly rejected
    ok_cc_min, _, rej_cc_min = validate_composition_evidence(
        _make_sample_evidence(
            instrument_id="ChemCam_LIBS",
            canonical_species_id="hematite",
            canonical_species_name="Hematite",
            species_category=SpeciesCategory.MINERAL,
            evidence_type=EvidenceType.DIRECT_MINERAL_DETECTION,
        )
    )
    assert not ok_cc_min and rej_cc_min is not None and rej_cc_min.rejection_code == "INVALID_MINERAL_CLAIM_FROM_LIBS"

    # Stage 6: Negative & <LOD rejected
    ok_neg, _, rej_neg = validate_composition_evidence(_make_sample_evidence(raw_value=-0.5, normalized_value=-0.5))
    assert not ok_neg and rej_neg is not None and rej_neg.rejection_code == "NEGATIVE_PHYSICAL_VALUE"

    ok_lod, _, rej_lod = validate_composition_evidence(
        _make_sample_evidence(evidence_status=EvidenceStatus.BELOW_DETECTION_LIMIT, raw_value=0.0, normalized_value=0.0)
    )
    assert not ok_lod and rej_lod is not None and rej_lod.rejection_code == "BELOW_DETECTION_LIMIT"

    # Stage 7: >100 wt% rejected
    ok_big, _, rej_big = validate_composition_evidence(_make_sample_evidence(raw_value=105.0, normalized_value=105.0))
    assert not ok_big and rej_big is not None and rej_big.rejection_code == "OUT_OF_PHYSICAL_BOUNDS_WT_PCT"

    # Stage 10: Earth WGS84 CRS rejected
    ok_crs, _, rej_crs = validate_composition_evidence(_make_sample_evidence(crs="EPSG:4326"))
    assert not ok_crs and rej_crs is not None and rej_crs.rejection_stage == 10

    # Valid unlocated record passes ONLY when status == UNLOCATED & semantic type == UNLOCATED
    ok_unloc, stages_unloc, rej_unloc = validate_composition_evidence(
        _make_sample_evidence(
            evidence_status=EvidenceStatus.UNLOCATED,
            location_verified=False,
            location_semantic_type=LocationSemanticType.UNLOCATED,
            latitude=None,
            longitude_east=None,
            crs=None,
            coordinate_source=None,
        )
    )
    assert ok_unloc and rej_unloc is None and len(stages_unloc) == 12


def _write_test_apxs_xml(path: Path, columns: list[str]) -> None:
    fields_xml = []
    for i, col in enumerate(columns, start=1):
        dtype = "ASCII_Integer" if (col == "Sol" or col.endswith("_ppm") or (col.endswith("_err") and any(c.startswith(col[:-4] + "_ppm") for c in columns))) else ("ASCII_String" if col == "Target" else "ASCII_Real")
        unit_el = "<unit>ppm</unit>" if col.endswith("_ppm") else ("<unit>wt%</unit>" if col.endswith("_pct") else "")
        desc = f"Precision Error in Concentration ({'ppm' if col.endswith('_ppm') else 'wt%'})" if col.endswith("_err") else col
        fields_xml.append(
            f"<Field_Delimited><name>{col}</name><field_number>{i}</field_number><data_type>{dtype}</data_type>{unit_el}<description>{desc}</description></Field_Delimited>"
        )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">'
        "<File_Area_Observational><Table_Delimited><Record_Delimited>"
        f"<fields>{len(columns)}</fields>"
        + "".join(fields_xml)
        + "</Record_Delimited></Table_Delimited></File_Area_Observational></Product_Observational>",
        encoding="utf-8",
    )


def test_spatial_index_rebuild_search_antimeridian_and_targets(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True)

    # Waypoints
    (raw_dir / "msl_waypoints.json").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"RMC":"3_4","lon":137.44172,"lat":-4.5895,"elev_geoid":-4520.0}}]}',
        encoding="utf-8",
    )
    # APXS with 1 valid target + 1 <LOD (0/0) AND required companion PDS4 XML
    apxs_headers = "Sol,Target,Northing_m,Easting_m,Elevation_m,Na2O_pct,Na2O_err,MgO_pct,MgO_err,Al2O3_pct,Al2O3_err,SiO2_pct,SiO2_err,P2O5_pct,P2O5_err,SO3_pct,SO3_err,Cl_pct,Cl_err,K2O_pct,K2O_err,CaO_pct,CaO_err,TiO2_pct,TiO2_err,Cr2O3_pct,Cr2O3_err,MnO_pct,MnO_err,FeO_pct,FeO_err,Ni_ppm,Ni_err,Zn_ppm,Zn_err,Br_ppm,Br_err"
    (raw_dir / "ds01_2021je007171r.csv").write_text(
        apxs_headers + "\n"
        "54,Bathurst_Inlet,-272038.5,8145966.2,-4520.0,2.5,0.2,8.1,0.3,7.2,0.2,45.0,0.5,0.9,0.1,5.2,0.2,0.8,0.1,0.5,0.1,6.4,0.2,1.1,0.1,0.4,0.1,0.4,0.1,19.8,0.4,0,0,150,20,80,10\n",
        encoding="utf-8",
    )
    _write_test_apxs_xml(raw_dir / "ds01_2021je007171r.xml", apxs_headers.split(","))
    # CheMin with gypsum detection & unlocated RMC (99_99) + required .lbl & WEIGHT_PERCENT .fmt
    (raw_dir / "chemin_min.fmt").write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\nEND_OBJECT = COLUMN\nOBJECT = COLUMN\n  NAME = PERCENT\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\nOBJECT = COLUMN\n  NAME = ERROR\n  UNIT = "ESTIMATED_ERROR"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    (raw_dir / "cma_001min00790990099ch11503p1.lbl").write_text(
        'PDS_VERSION_ID = PDS3\nPRODUCT_ID = "CMA_001MIN00790990099CH11503P1"\nROVER_MOTION_COUNTER = (99, 99)\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\n  DESCRIPTION = "Column 3 indicates the estimated 2-sigma analytical errors."\nEND_OBJECT = SPREADSHEET\nEND\n',
        encoding="utf-8",
    )
    (raw_dir / "cma_001min00790990099ch11503p1.csv").write_text(
        "MINERAL,PERCENT,ERROR\nGypsum,3.4,1.1\nAndesine,38.0,2.5\n",
        encoding="utf-8",
    )
    # ChemCam PSV (must be audited as rejected) & REMS (must be audited as rejected)
    (raw_dir / "cl1_398380611psv_f0030004.tab").write_text("100\n200\n", encoding="utf-8")
    (raw_dir / "cl1_398380611psv_f0030004.lbl").write_text(
        'PDS_VERSION_ID = PDS3\nPRODUCT_TYPE = "CHEMCAM-PSV"\nPRODUCT_ID = "PSV_TEST"\n',
        encoding="utf-8",
    )
    (raw_dir / "rme_test.lbl").write_text('PRODUCT_ID = "RME_TEST"\n', encoding="utf-8")
    (raw_dir / "rme_test.tab").write_text("2012-08-07T00:00:00Z,245.0\n", encoding="utf-8")

    db_path = tmp_path / "comp.sqlite"
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True)
    index = CompositionSpatialIndex(db_path)
    status = index.rebuild_from_raw_directory(raw_dir, processed_dir)
    assert status.index_available
    assert status.located_evidence_count > 0
    assert status.unlocated_evidence_count >= 2  # Gypsum + Andesine at missing RMC 99_99
    assert status.rejected_record_count >= 3  # APXS Ni <LOD + PSV + REMS
    assert status.checksum_valid is True
    assert status.crism_status == "unavailable_no_validated_mineral_cube"

    # Search Fe with astronaut location nearby
    svc = CompositionSearchService(index)
    fe_res = svc.search(
        StructuredCompositionQuery(
            query="Fe",
            astronaut_latitude=-4.59,
            astronaut_longitude=137.44,
        )
    )
    assert fe_res.total_located_matches >= 1
    assert len(fe_res.candidate_locations) >= 1
    assert fe_res.hits[0].distance_from_astronaut_m is not None
    assert fe_res.hits[0].ranking.composite_rank_score > 0.0

    # Search gypsum -> located=0, unlocated_matches_count>=1!
    gyp_res = svc.search(StructuredCompositionQuery(query="gypsum"))
    assert gyp_res.total_located_matches == 0
    assert gyp_res.unlocated_matches_count >= 1
    assert len(gyp_res.candidate_locations) == 0

    # Antimeridian wrap query on synthetic wrapped point
    wrapped_ev = _make_sample_evidence(
        source_record_ref="wrap:358",
        latitude=-2.0,
        longitude_east=358.5,
    )
    ok_w, stages_w, rej_w = validate_composition_evidence(wrapped_ev)
    assert ok_w, f"Validation failed: {rej_w}"
    wrapped_ev.validation_stages = stages_w
    index.publish_generation([wrapped_ev], [], generation_id="gen_wrap")
    wrap_hits = index.query_evidence(["FeO"], located_only=True, bbox=(-5.0, 5.0, 355.0, 5.0))
    assert len(wrap_hits) == 1

    # Checksum drift detection
    index2 = CompositionSpatialIndex(tmp_path / "comp2.sqlite")
    (raw_dir / "ds01_2021je007171r.csv").write_text(
        "Sol,Target,Northing_m,Easting_m,Elevation_m,FeO_pct,FeO_err\n54,Bathurst,-272038.5,8145966.2,-4520.0,19.8,0.4\n",
        encoding="utf-8",
    )
    _write_test_apxs_xml(
        raw_dir / "ds01_2021je007171r.xml",
        ["Sol", "Target", "Northing_m", "Easting_m", "Elevation_m", "FeO_pct", "FeO_err"],
    )
    index2.rebuild_from_raw_directory(raw_dir, processed_dir)
    assert index2.get_status().checksum_valid is True
    (raw_dir / "ds01_2021je007171r.csv").write_text("modified\n", encoding="utf-8")
    assert index2.get_status().checksum_valid is False

    # Target provenance separation
    treg = TargetRegistryService(composition_index=index2)
    manual = treg.register_target(_make_manual_target())
    assert manual.target_status == TargetProvenanceStatus.MANUAL_UNVERIFIED_ADMINISTRATIVE

    ev_loc = _make_sample_evidence(source_record_ref="tgt:1")
    ok_t, st_t, _ = validate_composition_evidence(ev_loc)
    assert ok_t
    ev_loc.validation_stages = st_t
    index2.publish_generation([ev_loc], [], generation_id="gen_tgt")
    generated = treg.generate_targets_from_discovery(
        TargetGenerationRequest(query="Fe", max_targets=3),
        CompositionSearchService(index2),
    )
    assert len(generated) >= 1
    assert all(t.target_status == TargetProvenanceStatus.EVIDENCE_BACKED for t in generated)
    assert len(generated[0].evidence_ids) >= 1


def _make_manual_target():
    from app.schemas.target import ScienceTarget

    return ScienceTarget(
        id="manual_admin_01",
        name="Admin Waypoint Alpha",
        latitude=-4.6,
        longitude=137.4,
        geology_type="unverified_poi",
        scientific_value=0.1,
        instrument_source="manual",
        provenance_product_id="manual_entry",
    )


def test_destination_strict_coverage_verification_enforced():
    # Create an unverified catalog dataset covering Gale Crater -> must NOT enter covering_datasets!
    class _FakeCatalog:
        def list_datasets(self):
            return [
                Dataset(
                    id="unverified_psv",
                    source_archive="NASA PDS",
                    mission="MSL",
                    instrument="ChemCam",
                    product_id="PSV_UNVER",
                    product_title="Unverified PSV",
                    product_type="SPECTRUM",
                    original_product_url="https://example.invalid/psv",
                    attribution="NASA/JPL",
                    coverage=GeographicCoverage(
                        min_latitude=-6.0,
                        max_latitude=-4.0,
                        min_longitude=137.0,
                        max_longitude=138.0,
                        longitude_range="[0, 360)",
                    ),
                    data_format="TAB",
                    units="DIGITAL_NUMBER",
                    verification=MetadataVerification(
                        coverage_verification=VerificationState.UNVERIFIED,
                    ),
                )
            ]

    from app.schemas.destination import DestinationSelectionRequest

    svc = DestinationEvaluationService(catalog_service=_FakeCatalog(), processed_dir=Path("/tmp/nonexistent_processed_dir_test"))
    resp = svc.evaluate_destination(DestinationSelectionRequest(latitude=-4.6, longitude=137.4))
    assert len(resp.covering_datasets) == 0
    assert len(resp.unverified_catalog_candidates) == 1
    assert resp.unverified_catalog_candidates[0].coverage_verified is False


def test_composition_api_endpoints_live_router_contract():
    client = TestClient(app)
    res_sp = client.get("/api/composition/species?q=fe")
    assert res_sp.status_code == 200
    assert any(s["canonical_id"] == "Fe" for s in res_sp.json())

    res_st = client.get("/api/composition/index/status")
    assert res_st.status_code == 200
    assert "rtree_enabled" in res_st.json()
    assert res_st.json()["crism_status"] == "unavailable_no_validated_mineral_cube"

    res_rej = client.get("/api/composition/rejected?limit=5")
    assert res_rej.status_code == 200
    assert "records" in res_rej.json()

    res_search = client.post(
        "/api/composition/search",
        json={"query": "Fe", "search_mode": CompositionSearchMode.AUTO.value, "limit": 5},
    )
    assert res_search.status_code == 200
    payload = res_search.json()
    assert payload["query"] == "Fe"
    assert payload["crism_status" if "crism_status" in payload else "index_available"] is not None
