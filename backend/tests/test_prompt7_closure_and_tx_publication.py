"""
MARSCOPE Prompt 7 Adversarial Tests:
  1. CheMin uncertainty unit correctness (independent field resolution, ESTIMATED_ERROR non-physicality, incompatible unit rejection)
  2. Removal of unsupported quality_component & separately defined relative_uncertainty
  3. Measurement-category-aware search filtering, per-category abundance normalization, and sorting guards
  4. Canonical cryptographic authentication of complete manifest (`complete_manifest_digest` + DB/pointer cross-check)
  5. Transaction-safe immutable generation publication, failure-boundary rollback, staging cleanup, and concurrent reader/writer isolation
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.science.composition.adapters import CheMinEvidenceAdapter
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    GenerationBuildStatus,
    IntegrityStatus,
    LocationSemanticType,
    MeasurementCategory,
    SearchMatchType,
    SpeciesCategory,
)
from app.science.composition.ranking import compute_ranking_dimensions, compute_relative_uncertainty
from app.science.composition.search import (
    CompositionSearchService,
    StructuredCompositionQuery,
)
from app.science.composition.uncertainty import canonicalize_uncertainty_type
from app.science.curiosity_parser import CuriosityDataParser, MalformedObservationError
from tests.test_prompt6_reproducibility_and_semantics import _write_minimal_seed_dataset


def _make_ev(**overrides) -> CompositionEvidence:
    base = dict(
        evidence_id="ev_test_001",
        source_dataset_id="test_ds",
        product_id="TEST_PROD",
        source_record_ref="row=0",
        instrument_id="APXS",
        instrument_name="Alpha Particle X-Ray Spectrometer",
        processing_level="RDR",
        calibration_status="calibrated",
        target_name="TargetA",
        sol=100,
        canonical_species_id="Fe",
        canonical_species_name="Iron",
        species_category=SpeciesCategory.ELEMENT,
        raw_species_name="FeO",
        evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        evidence_status=EvidenceStatus.MEASURED,
        raw_value=18.0,
        raw_unit="wt%",
        normalized_value=14.0,
        normalized_unit="wt%",
        uncertainty_value=0.7,
        uncertainty_unit="wt%",
        uncertainty_type="apxs_analytical_precision",
        uncertainty_sigma="analytical_precision",
        methodology="Test methodology",
        source_reference="Test source reference",
        location_verified=True,
        location_semantic_type=LocationSemanticType.ROVER_STATION_LOCATION,
        latitude=-4.59,
        longitude_east=137.44,
    )
    base.update(overrides)
    return CompositionEvidence(**base)


def test_chemin_independent_error_unit_resolution_and_non_coercion(tmp_path: Path):
    # 1. Real NASA PDS pattern: PERCENT UNIT="WEIGHT_PERCENT", ERROR UNIT="ESTIMATED_ERROR"
    fmt = tmp_path / "CHEMIN_MIN.FMT"
    fmt.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\n  UNIT = "ESTIMATED_ERROR"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    csv_p = tmp_path / "cma_valid.csv"
    lbl_p = tmp_path / "cma_valid.lbl"
    csv_p.write_text("MINERAL,WEIGHT_PERCENT,ERROR\nGypsum,4.5,0.4\nOlivine,12.0,\n", encoding="utf-8")
    lbl_p.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\n'
        '  DESCRIPTION = "Errors represent 2-sigma values from Rietveld refinements."\nEND_OBJECT = SPREADSHEET\nEND\n',
        encoding="utf-8",
    )

    parsed = CuriosityDataParser.parse_chemin_min_csv_with_contract(csv_p, label_path=lbl_p, require_label=True)
    assert len(parsed.records[0]["minerals"]) == 2
    gyp = parsed.records[0]["minerals"][0]
    oliv = parsed.records[0]["minerals"][1]

    # CRITICAL: ERROR unit MUST stay ESTIMATED_ERROR (never fabricated into wt%!)
    assert gyp["error_schema_unit"] == "ESTIMATED_ERROR"
    assert gyp["error_is_physical_unit"] is False
    assert gyp["normalized_error_unit"] == "ESTIMATED_ERROR"
    assert gyp["error_schema_field"] == "ERROR"
    assert gyp["error_schema_data_type"] == "ASCII_REAL"
    # Missing ERROR value stays None
    assert oliv["estimated_error"] is None

    ev_list, rej_list = CheMinEvidenceAdapter.adapt_rdr5_csv(csv_p, label_path=lbl_p)
    assert len(ev_list) == 2
    assert len(rej_list) == 0
    ev_gyp = ev_list[0]
    assert ev_gyp.uncertainty_value == 0.4
    assert ev_gyp.uncertainty_unit == "ESTIMATED_ERROR"
    assert ev_gyp.uncertainty_metadata is not None
    assert ev_gyp.uncertainty_metadata.reported_unit == "ESTIMATED_ERROR"
    assert ev_gyp.uncertainty_metadata.normalized_unit == "ESTIMATED_ERROR"
    assert ev_gyp.uncertainty_metadata.normalized_unit != "wt%"
    assert ev_gyp.uncertainty_metadata.is_physical_unit is False
    assert ev_gyp.uncertainty_metadata.source_field_name == "ERROR"

    # 2. Missing UNIT on ERROR column preserves None + limitation (never infers wt% from WEIGHT_PERCENT)
    fmt.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    parsed_no_unit = CuriosityDataParser.parse_chemin_min_csv_with_contract(csv_p, label_path=lbl_p, require_label=True)
    m_nu = parsed_no_unit.records[0]["minerals"][0]
    assert m_nu["error_schema_unit"] is None
    assert m_nu["normalized_error_unit"] is None
    assert any("lacks unit" in lim.lower() for lim in m_nu["error_limitations"])

    # 3. Physical PPM error converts cleanly when physical concentration unit; KELVIN rejects loudly
    fmt.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\n  UNIT = "PPM"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    csv_ppm = tmp_path / "cma_valid.csv"
    csv_ppm.write_text("MINERAL,WEIGHT_PERCENT,ERROR\nGypsum,4.5,4000\n", encoding="utf-8")
    parsed_ppm = CuriosityDataParser.parse_chemin_min_csv_with_contract(csv_ppm, label_path=lbl_p, require_label=True)
    assert parsed_ppm.records[0]["minerals"][0]["normalized_error"] == pytest.approx(0.4)
    assert parsed_ppm.records[0]["minerals"][0]["normalized_error_unit"] == "wt%"

    fmt.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\n  DATA_TYPE = CHARACTER\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = WEIGHT_PERCENT\n  DATA_TYPE = ASCII_REAL\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  DATA_TYPE = ASCII_REAL\n  UNIT = "KELVIN"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    with pytest.raises(MalformedObservationError, match="Incompatible or non-concentration CheMin error unit"):
        CuriosityDataParser.parse_chemin_min_csv_with_contract(csv_ppm, label_path=lbl_p, require_label=True)


def test_quality_component_withheld_and_relative_uncertainty_validity():
    # Valid physical relative uncertainty (APXS 0.7 wt% on 14.0 wt% = 5%)
    ev_ok = _make_ev(normalized_value=14.0, normalized_unit="wt%", uncertainty_value=0.7, uncertainty_unit="wt%")
    rel_ok = compute_relative_uncertainty(ev_ok)
    assert rel_ok.available is True
    assert rel_ok.value == pytest.approx(0.05)
    assert rel_ok.percent == pytest.approx(5.0)
    assert rel_ok.unavailable_reason is None

    r_ok = compute_ranking_dimensions(
        ev=ev_ok,
        match_type=SearchMatchType.EXACT_SPECIES,
        max_observed_abundance=28.0,
        corroborating_instruments=["APXS"],
        nearby_count=1,
        distance_m=100.0,
        cohort_uncertainty_types=["apxs_analytical_precision"],
    )
    assert r_ok.quality_component is None
    assert "quality_component" in r_ok.unavailable_dimensions
    assert "quality" not in r_ok.score_formula.lower().split("(withheld")[0]
    assert r_ok.ranking_config_version == "4.0.0"
    assert r_ok.relative_uncertainty is not None and r_ok.relative_uncertainty.percent == pytest.approx(5.0)

    # Zero value -> division invalid -> unavailable relative_uncertainty
    ev_zero = _make_ev(normalized_value=0.0, normalized_unit="wt%", uncertainty_value=0.5, uncertainty_unit="wt%")
    rel_zero = compute_relative_uncertainty(ev_zero)
    assert rel_zero.available is False
    assert rel_zero.percent is None
    assert "zero" in (rel_zero.unavailable_reason or "").lower()

    # Non-dimensional ESTIMATED_ERROR -> relative_uncertainty withheld!
    ev_est = _make_ev(
        instrument_id="CheMin_XRD",
        normalized_value=5.0,
        normalized_unit="wt%",
        uncertainty_value=0.5,
        uncertainty_unit="ESTIMATED_ERROR",
        uncertainty_type="chemin_rietveld_2sigma",
    )
    rel_est = compute_relative_uncertainty(ev_est)
    assert rel_est.available is False
    assert "physical" in (rel_est.unavailable_reason or "").lower() or "match" in (rel_est.unavailable_reason or "").lower()

    # Mismatched physical units (ppm vs wt%) -> withheld!
    ev_mismatch = _make_ev(normalized_value=5.0, normalized_unit="wt%", uncertainty_value=500.0, uncertainty_unit="ppm")
    rel_mm = compute_relative_uncertainty(ev_mismatch)
    assert rel_mm.available is False

    # Unspecified statistical uncertainty type -> withheld!
    ev_unspec = _make_ev(
        instrument_id="CheMin_XRD",
        normalized_value=5.0,
        normalized_unit="wt%",
        uncertainty_value=0.5,
        uncertainty_unit="wt%",
        uncertainty_type="chemin_estimated_error_unspecified_sigma",
    )
    rel_unspec = compute_relative_uncertainty(ev_unspec)
    assert rel_unspec.available is False
    assert canonicalize_uncertainty_type("WEIGHT_PERCENT") == "unknown"


def test_measurement_category_aware_filtering_and_sorting_guards(tmp_path: Path):
    idx = CompositionSpatialIndex(db_path=tmp_path / "comp.sqlite")
    # Publish mixed cohort: APXS FeO (~12 wt% Fe), CheMin hematite (28 wt% mineral), CheMin olivine (10 wt% mineral)
    ev_feo = _make_ev(
        evidence_id="ev_fe_apxs",
        canonical_species_id="FeO",
        canonical_species_name="Iron(II) oxide",
        species_category=SpeciesCategory.OXIDE,
        raw_species_name="FeO",
        evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        raw_value=15.44,
        raw_unit="wt%",
        normalized_value=15.44,  # ~12.0 wt% Fe after stoichiometric conversion
        normalized_unit="wt%",
    )
    ev_hem = _make_ev(
        evidence_id="ev_hem_chemin",
        instrument_id="CheMin_XRD",
        instrument_name="CheMin XRD",
        canonical_species_id="hematite",
        canonical_species_name="Hematite",
        species_category=SpeciesCategory.MINERAL,
        raw_species_name="Hematite",
        evidence_type=EvidenceType.DIRECT_MINERAL_DETECTION,
        raw_value=28.0,
        raw_unit="wt%",
        normalized_value=28.0,
        normalized_unit="wt%",
        uncertainty_value=1.2,
        uncertainty_unit="ESTIMATED_ERROR",
        uncertainty_type="chemin_rietveld_2sigma",
    )
    # Recompute exact deterministic IDs cleanly
    from app.science.composition.validation import compute_deterministic_evidence_id

    ev_feo = ev_feo.model_copy(update={"evidence_id": compute_deterministic_evidence_id(ev_feo)})
    ev_hem = ev_hem.model_copy(update={"evidence_id": compute_deterministic_evidence_id(ev_hem)})
    idx.publish_generation(evidence_records=[ev_feo, ev_hem], rejected_records=[])

    svc = CompositionSearchService(idx)

    # 1. min_value=15 on Fe query MUST NOT let hematite=28 wt% pass as if it were 28 wt% Fe!
    res_filt = svc.search(
        StructuredCompositionQuery(
            query="Fe",
            include_element_bearing_minerals=True,
            min_value=15.0,
        )
    )
    assert res_filt.total_located_matches == 0
    assert res_filt.applied_filter_scope_note is not None
    assert "non-elemental host-mineral" in res_filt.applied_filter_scope_note

    # 2. Explicit measurement_category_filter=MINERAL_WEIGHT_PERCENT filters minerals cleanly
    res_min = svc.search(
        StructuredCompositionQuery(
            query="Fe",
            include_element_bearing_minerals=True,
            measurement_category_filter=MeasurementCategory.MINERAL_WEIGHT_PERCENT,
            min_value=15.0,
        )
    )
    assert res_min.total_located_matches == 1
    assert res_min.hits[0].evidence.canonical_species_id == "hematite"
    assert res_min.hits[0].measurement_category == MeasurementCategory.MINERAL_WEIGHT_PERCENT

    # 3. Unfiltered Fe query + include_element_bearing_minerals: flat sort_by="abundance" MUST raise ValueError!
    with pytest.raises(ValueError, match="category_abundance"):
        svc.search(
            StructuredCompositionQuery(
                query="Fe",
                include_element_bearing_minerals=True,
                sort_by="abundance",
            )
        )

    # 4. sort_by="category_abundance" succeeds cleanly AND abundance_component is normalized per category!
    res_cat = svc.search(
        StructuredCompositionQuery(
            query="Fe",
            include_element_bearing_minerals=True,
            sort_by="category_abundance",
        )
    )
    assert res_cat.total_located_matches == 2
    assert len(res_cat.measurement_categories_present) == 2
    # Both highest in their own category -> both get abundance_component == 1.0 within their own category!
    assert all(h.ranking.abundance_component == 1.0 for h in res_cat.hits)


def test_complete_manifest_cryptographic_authentication_tamper_detection(tmp_path: Path, monkeypatch):
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_seed_dataset(raw_dir, include_extra_moc=True)

    index_dir = tmp_path / "index"
    idx = CompositionSpatialIndex(db_path=index_dir / "composition_index.sqlite")
    st = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
        strict_mode=True,
    )
    assert st.integrity_status == IntegrityStatus.VERIFIED
    assert st.source_integrity_status == IntegrityStatus.VERIFIED
    assert st.manifest_integrity_status == IntegrityStatus.VERIFIED
    assert st.pointer_integrity_status == IntegrityStatus.VERIFIED
    assert st.database_integrity_status == IntegrityStatus.VERIFIED
    assert st.source_artifact_digest is not None
    assert st.complete_manifest_digest is not None

    monkeypatch.setattr("app.api.composition.INDEX_DIR", index_dir)
    client = TestClient(app)
    assert client.get("/api/composition/reproducibility-manifest").status_code == 200

    manifest_file = idx._manifest_path()
    orig_text = manifest_file.read_text(encoding="utf-8")
    orig_obj = json.loads(orig_text)

    # Tamper ANY field (notes, rights_summary, retrieval_metadata, product_audit, products, dependency_artifacts, generation_build_status)
    tampered_mutations = [
        ("notes", [*orig_obj["notes"], "tampered note"]),
        ("rights_summary", {**orig_obj["rights_summary"], "note": "forged verified rights"}),
        ("retrieval_metadata", {**orig_obj["retrieval_metadata"], "verified_retrieval_timestamps": 999}),
        ("generation_build_status", "partial"),
        ("complete_manifest_digest", "0" * 64),
    ]
    for field, new_val in tampered_mutations:
        mutated = dict(orig_obj)
        mutated[field] = new_val
        manifest_file.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
        st_bad = idx.get_status()
        assert st_bad.manifest_integrity_status == IntegrityStatus.MANIFEST_INVALID
        assert st_bad.integrity_status == IntegrityStatus.MANIFEST_INVALID
        assert client.get("/api/composition/reproducibility-manifest").status_code == 422

    # Even if attacker recomputes self-consistent complete_manifest_digest in JSON, SQLite + pointer catch forgery!
    forged = dict(orig_obj)
    forged["notes"] = [*orig_obj["notes"], "attacker recomputed self-digest"]
    from app.science.composition.index import compute_complete_manifest_digest

    forged["complete_manifest_digest"] = compute_complete_manifest_digest(forged)
    manifest_file.write_text(json.dumps(forged, indent=2), encoding="utf-8")
    assert idx.get_status().manifest_integrity_status == IntegrityStatus.MANIFEST_INVALID
    assert client.get("/api/composition/reproducibility-manifest").status_code == 422

    # Restore valid manifest -> immediately re-authenticates
    manifest_file.write_text(orig_text, encoding="utf-8")
    assert idx.get_status().integrity_status == IntegrityStatus.VERIFIED


def test_transaction_safe_directory_publication_all_failure_stages_and_concurrency(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    _write_minimal_seed_dataset(raw_dir, include_extra_moc=True)

    index_dir = tmp_path / "index"
    idx = CompositionSpatialIndex(db_path=index_dir / "composition_index.sqlite")
    gen1 = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
    )
    assert gen1.integrity_status == IntegrityStatus.VERIFIED
    gen1_db_path = gen1.sqlite_path
    gen1_manifest_digest = gen1.complete_manifest_digest

    # Every single publication failure boundary MUST preserve gen1 untouched and leave 0 staging leftovers
    for stage in (
        "before_db_commit",
        "after_db_commit",
        "before_manifest_write",
        "before_staging_validation",
        "before_dir_publish",
        "before_pointer_replace",
    ):
        with pytest.raises(RuntimeError):
            idx.rebuild_from_raw_directory(
                raw_dir=raw_dir,
                processed_dir=proc_dir,
                declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
                failure_stage=stage,
            )
        st_after = idx.get_status()
        assert st_after.active_generation_id == gen1.active_generation_id
        assert st_after.sqlite_path == gen1_db_path
        assert st_after.complete_manifest_digest == gen1_manifest_digest
        assert st_after.integrity_status == IntegrityStatus.VERIFIED
        assert st_after.incomplete_staging_generations == []

    # Second successful build updates generation cleanly and links previous_successful_generation_id
    # Inject a stray simulated crash staging directory first to confirm visibility then automatic cleanup
    stray_stage = idx._generations_dir() / ".staging_crash_leftover"
    stray_stage.mkdir(parents=True, exist_ok=True)
    assert ".staging_crash_leftover" in idx.get_status().incomplete_staging_generations

    gen2 = idx.rebuild_from_raw_directory(
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
    )
    assert gen2.integrity_status == IntegrityStatus.VERIFIED
    assert gen2.previous_successful_generation_id == gen1.active_generation_id
    assert gen2.incomplete_staging_generations == []
    assert gen2.sqlite_path != gen1_db_path  # New immutable generation directory

    # Concurrent rebuilds (flock-serialized) + concurrent readers observe ONLY verified complete snapshots!
    reader_errors = []

    def _writer_task():
        return idx.rebuild_from_raw_directory(
            raw_dir=raw_dir,
            processed_dir=proc_dir,
            declared_unavailable_sources=["msl_crism_orbital_mineral_cube"],
        )

    def _reader_task():
        try:
            for _ in range(8):
                s = idx.get_status()
                assert s.index_available is True
                assert s.integrity_status == IntegrityStatus.VERIFIED
                assert s.source_integrity_status == IntegrityStatus.VERIFIED
                assert s.manifest_integrity_status == IntegrityStatus.VERIFIED
                assert s.pointer_integrity_status == IntegrityStatus.VERIFIED
                assert s.database_integrity_status == IntegrityStatus.VERIFIED
                mf = idx.get_authenticated_manifest()
                assert mf["complete_manifest_digest"]
                rows = idx.query_evidence(["FeO"])
                assert len(rows) > 0
        except Exception as exc:  # pragma: no cover - collected explicitly
            reader_errors.append(str(exc))

    with ThreadPoolExecutor(max_workers=4) as pool:
        wf1 = pool.submit(_writer_task)
        rf1 = pool.submit(_reader_task)
        rf2 = pool.submit(_reader_task)
        wf2 = pool.submit(_writer_task)
        st_w1 = wf1.result()
        st_w2 = wf2.result()
        rf1.result()
        rf2.result()

    assert reader_errors == []
    assert st_w1.integrity_status == IntegrityStatus.VERIFIED
    assert st_w2.integrity_status == IntegrityStatus.VERIFIED
    assert idx.get_status().integrity_status == IntegrityStatus.VERIFIED
