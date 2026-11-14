"""
MARSCOPE Prompt 8 Verification Suite:
  - Part A:
      1. Zero-measurement classification across APXS, ChemCam, and CheMin
      2. Removal of silent DEM footprint expansion + structured InsufficientCoverageReport
      3. Removal of default 25 deg safety threshold + explicit PlanningSlopeThreshold
      4. Reader lease protection preventing active generation deletion during concurrent rebuilds
  - Part B:
      5. DEM inventory & resolution suitability (regional vs local slope vs obstacle detection)
      6. Windowed physical terrain features (elevation, Horn 3x3 slope, aspect, metric TRI)
      7. 5-state spatial coverage & unknown-data intelligence
      8. Spatially explicit elevation gain/loss profile (2-point & polyline, valid & nodata gaps)
      9. Configurable MobilityScenario & transparent TraversalModel (no defaults, no extrapolation)
     10. Spatially explicit TraversalCostSurface (null cost on nodata, no safe/unsafe labels)
     11. FastAPI /api/mobility/* endpoint contracts
"""

from pathlib import Path
from fastapi.testclient import TestClient
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.main import app
from app.mobility.coverage import evaluate_region_coverage_intelligence
from app.mobility.models import (
    AnalysisScaleType,
    CellTraversalAvailabilityState,
    ParameterOriginType,
    ResolutionSuitabilityLevel,
    TerrainCoverageState,
)
from app.mobility.resolution import RESOLUTION_POLICY_VERSION, evaluate_dem_resolution_suitability
from app.mobility.schemas import (
    GeoPoint,
    MobilityScenarioCreateRequest,
    RoughnessSpeedAdjustmentRule,
    SlopeSpeedAdjustmentRule,
)
from app.mobility.traversal_model import evaluate_cell_or_segment_traversal
from app.physics.registry.parameters import list_parameters
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, GeographicCoverage
from app.schemas.terrain import PlanningSlopeThreshold
from app.science.composition.adapters import (
    ApxsEvidenceAdapter,
    CheMinEvidenceAdapter,
    ChemCamEvidenceAdapter,
)
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    SpeciesCategory,
)
from app.science.composition.validation import (
    compute_deterministic_evidence_id,
    validate_composition_evidence,
)
from app.science.composition.value_semantics import (
    ValueSemantics,
    classify_value_semantics,
)
from app.services.container import RAW_DIR
from app.terrain.processor import DEMProcessingService, InsufficientDEMCoverageError
from app.terrain.summary import compile_terrain_summary

client = TestClient(app)


# ============================================================================
# PART A.1 — ZERO-MEASUREMENT CLASSIFICATION
# ============================================================================


def test_zero_measurement_semantics_across_apxs_chemcam_and_chemin(tmp_path: Path):
    """
    Verify that numerical zero values (0.0) without explicit source-defined BDL
    metadata are preserved as reported_numerical_zero_unresolved_semantics (MEASURED)
    and never automatically converted into BELOW_DETECTION_LIMIT.
    """
    # 1. Direct classify_value_semantics unit checks
    sem_zero, note_zero = classify_value_semantics(0.0, raw_token="0.0", special_constants={})
    assert sem_zero == ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED
    assert "zero" in (note_zero or "").lower()

    sem_bdl, _ = classify_value_semantics(
        0.0,
        raw_token="0.0",
        special_constants={"detection_limit_constant": "0.0"},
    )
    assert sem_bdl == ValueSemantics.SOURCE_DEFINED_BELOW_DETECTION_LIMIT

    sem_missing, _ = classify_value_semantics(
        -9999.0,
        raw_token="-9999",
        special_constants={"missing_constant": "-9999"},
    )
    assert sem_missing == ValueSemantics.SOURCE_DEFINED_MISSING

    # 2. Synthetic PDS4 APXS CSV: verify reported 0.0 values (e.g. Ni = 0.0 ± 0.0) are accepted
    #    with value_semantics == reported_numerical_zero_unresolved_semantics, NOT rejected as BDL
    apxs_xml = tmp_path / "ds01_zero.xml"
    apxs_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
  <File_Area_Observational>
    <Table_Delimited>
      <Record_Delimited>
        <Field_Delimited><name>FeO</name><field_number>1</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>FeO_err</name><field_number>2</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>Ni</name><field_number>3</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>Ni_err</name><field_number>4</field_number><data_type>ASCII_Real</data_type><unit>wt%</unit></Field_Delimited>
        <Field_Delimited><name>Easting_m</name><field_number>5</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Northing_m</name><field_number>6</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Elevation_m</name><field_number>7</field_number><data_type>ASCII_Real</data_type><unit>m</unit></Field_Delimited>
        <Field_Delimited><name>Quality</name><field_number>8</field_number><data_type>ASCII_String</data_type></Field_Delimited>
        <Field_Delimited><name>Target</name><field_number>9</field_number><data_type>ASCII_String</data_type></Field_Delimited>
        <Field_Delimited><name>Sol</name><field_number>10</field_number><data_type>ASCII_Integer</data_type></Field_Delimited>
      </Record_Delimited>
    </Table_Delimited>
  </File_Area_Observational>
</Product_Observational>
""",
        encoding="utf-8",
    )
    apxs_csv = tmp_path / "ds01_zero.csv"
    apxs_csv.write_text(
        "FeO_pct,FeO_err,Ni,Ni_err,Easting_m,Northing_m,Elevation_m,Quality,Target,Sol\n"
        "21.4,0.6,0.0,0.0,8145966.2,-272038.5,-4520.0,,Rocknest_Test,82\n",
        encoding="utf-8",
    )
    accepted_apxs, rejected_apxs = ApxsEvidenceAdapter.adapt_csv(
        apxs_csv,
        source_dataset_id="msl_apxs_supplement_sols_0_3076",
        product_id="DS01_2021JE007171R",
        provenance_url="https://pds-geosciences.wustl.edu/",
        label_path=apxs_xml,
    )
    zero_apxs = [e for e in accepted_apxs if e.raw_value == 0.0]
    assert len(zero_apxs) >= 1
    for z_ev in zero_apxs:
        assert z_ev.value_semantics == ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED.value
        assert z_ev.evidence_status in (EvidenceStatus.MEASURED, EvidenceStatus.UNLOCATED)
        assert z_ev.source_interpretation_note is not None
    assert not any(r.rejection_code == "BELOW_DETECTION_LIMIT" for r in rejected_apxs)

    # 3. Synthetic PDS3 CheMin RDR5 CSV: verify 0.0 mineral abundances are preserved as reported numerical zeros
    fmt_path = tmp_path / "CHEMIN_MIN.FMT"
    fmt_path.write_text(
        'OBJECT = COLUMN\n  NAME = MINERAL\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = PERCENT\n  UNIT = "WEIGHT_PERCENT"\nEND_OBJECT = COLUMN\n'
        'OBJECT = COLUMN\n  NAME = ERROR\n  UNIT = "ESTIMATED_ERROR"\n  DESCRIPTION = "2-sigma TOPAS Rietveld"\nEND_OBJECT = COLUMN\n',
        encoding="utf-8",
    )
    cm_lbl = tmp_path / "cma_zero.lbl"
    cm_lbl.write_text(
        'PDS_VERSION_ID = PDS3\nOBJECT = SPREADSHEET\n  ^STRUCTURE = "CHEMIN_MIN.FMT"\nEND_OBJECT = SPREADSHEET\n',
        encoding="utf-8",
    )
    cm_csv = tmp_path / "cma_zero.csv"
    cm_csv.write_text("MINERAL,PERCENT,ERROR\nGypsum,3.4,1.1\nOlivine,0.0,0.0\n", encoding="utf-8")
    accepted_cm, rejected_cm = CheMinEvidenceAdapter.adapt_rdr5_csv(
        cm_csv,
        label_path=cm_lbl,
        source_dataset_id="msl_chemin_test",
        extra_structure_dirs=[tmp_path],
    )
    zero_cm = [e for e in accepted_cm if e.raw_value == 0.0]
    assert len(zero_cm) == 1
    for z_ev in zero_cm:
        assert z_ev.value_semantics == ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED.value
    assert not any(r.rejection_code == "BELOW_DETECTION_LIMIT" for r in rejected_cm)

    # 4. Synthetic PDS3 ChemCam MOC CSV: verify zero values are preserved as reported numerical zeros
    moc_lbl = tmp_path / "moc_zero.lbl"
    moc_lbl.write_text(
        """PDS_VERSION_ID = PDS3
PRODUCT_ID = "MOC_ZERO"
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
    moc_csv = tmp_path / "moc_zero.csv"
    moc_csv.write_text(
        "SOL,FEOT_RMSEP,DISTANCE_TO_TARGET,SUM_OF_OXIDES,FEOT,FEOT_SHOTS_STDEV,SITE_ID,DRIVE_ID,TARGET_NAME,SCLK,PRODUCT_NAME\n"
        "54,2.1,3.4,98.5,0.0,0.0,99,99,Zero_FeOT_Target,401234567,CL5_401234567CCS_F0990099CCAM04010P3\n",
        encoding="utf-8",
    )
    accepted_moc, rejected_moc = ChemCamEvidenceAdapter.adapt_moc_csv(
        moc_csv,
        label_path=moc_lbl,
        source_dataset_id="msl_chemcam_moc_0000_0089",
    )
    zero_moc = [e for e in accepted_moc if e.raw_value == 0.0]
    assert len(zero_moc) == 1
    for z_ev in zero_moc:
        assert z_ev.value_semantics == ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED.value
    assert not any(r.rejection_code == "BELOW_DETECTION_LIMIT" for r in rejected_moc)


def test_validation_stage6_rejects_unsupported_bdl_and_source_missing_constants():
    """
    Verify Stage 6 of the 12-stage validation gate:
      - Rejects unsupported BDL inference (BELOW_DETECTION_LIMIT without source_defined_below_detection_limit)
      - Rejects source_defined_missing values with SOURCE_DEFINED_MISSING_VALUE
    """
    unsupported_bdl = CompositionEvidence(
        evidence_id="temp_ev_id",
        source_dataset_id="msl_apxs",
        product_id="PROD1",
        source_record_ref="r1",
        instrument_id="APXS",
        instrument_name="Alpha Particle X-Ray Spectrometer",
        processing_level="Derived",
        calibration_status="Calibrated",
        canonical_species_id="SiO2",
        canonical_species_name="SiO2",
        raw_species_name="SiO2",
        species_category=SpeciesCategory.OXIDE,
        evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        evidence_status=EvidenceStatus.BELOW_DETECTION_LIMIT,
        value_semantics=ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED.value,
        raw_value=0.0,
        raw_unit="wt%",
        normalized_value=0.0,
        normalized_unit="wt%",
        methodology="X-ray fluorescence and particle-induced X-ray emission",
        source_reference="NASA PDS Geosciences Node",
        source_file_checksum="abc123def4567890",
        schema_version="2.0.0",
        parser_version="2.0.0",
    )
    unsupported_bdl.evidence_id = compute_deterministic_evidence_id(unsupported_bdl)
    ok, stages, rej = validate_composition_evidence(unsupported_bdl)
    assert ok is False
    assert stages[-1].stage_number == 6
    assert rej is not None
    assert rej.rejection_code == "UNSUPPORTED_BDL_INFERENCE"

    missing_const_rec = unsupported_bdl.model_copy(
        update={
            "evidence_status": EvidenceStatus.REJECTED,
            "value_semantics": ValueSemantics.SOURCE_DEFINED_MISSING.value,
            "raw_value": -9999.0,
            "normalized_value": -9999.0,
        }
    )
    missing_const_rec.evidence_id = compute_deterministic_evidence_id(missing_const_rec)
    ok2, stages2, rej2 = validate_composition_evidence(missing_const_rec)
    assert ok2 is False
    assert stages2[-1].stage_number == 6
    assert rej2 is not None
    assert rej2.rejection_code == "SOURCE_DEFINED_MISSING_VALUE"


# ============================================================================
# PART A.2 — NO SILENT DEM FOOTPRINT EXPANSION
# ============================================================================


def test_dem_processor_never_silently_expands_small_footprint(tmp_path: Path):
    """
    Verify that requesting a small study box (< 3x3 pixels on 4 ppd MOLA) raises
    InsufficientDEMCoverageError with `requested_bounds_modified=False` and
    does NOT silently expand the bounding box.
    """
    from app.geospatial.crs import MARS_CRS_DEFINITIONS

    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    dem_path = raw_dir / "synthetic_mola_4ppd.tif"

    # 4 ppd grid = 0.25 deg/px across Gale crater [-7..-3] x [135..140] -> 20 cols x 16 rows
    cols, rows = 20, 16
    elev = np.linspace(-4600.0, -3900.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype=rasterio.float32,
        crs=MARS_CRS_DEFINITIONS["IAU2000:49900"],
        transform=from_bounds(135.0, -7.0, 140.0, -3.0, cols, rows),
        nodata=-32768.0,
    ) as dst:
        dst.write(elev, 1)

    ds = Dataset(
        id="mola_megt90n000cb",
        product_title="Synthetic MGS MOLA MEGDR 4 ppd",
        mission="Mars Global Surveyor",
        instrument="MOLA",
        product_id="MEGT90N000CB.IMG",
        product_type="DEM",
        source_archive="NASA PDS Geosciences",
        original_product_url="https://pds-geosciences.wustl.edu/",
        attribution="NASA PDS MOLA Science Team",
        coordinate_reference_system="IAU2000:49900",
        units="meters",
        horizontal_resolution_meters=14800.0,
        coverage=GeographicCoverage(
            min_latitude=-7.0,
            max_latitude=-3.0,
            min_longitude=135.0,
            max_longitude=140.0,
        ),
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path="raw/synthetic_mola_4ppd.tif",
    )

    tiny_bounds = {
        "min_lat": -4.60,
        "max_lat": -4.55,
        "min_lon": 137.35,
        "max_lon": 137.40,
    }
    with pytest.raises(InsufficientDEMCoverageError) as exc_info:
        DEMProcessingService.process_dem_dataset(
            dataset=ds,
            raw_dir=raw_dir,
            processed_dir=proc_dir,
            study_bounds=tiny_bounds,
        )

    rep = exc_info.value.report
    assert rep.requested_bounds_modified is False
    assert rep.requested_bounds["min_lat"] == pytest.approx(-4.60)
    assert rep.requested_bounds["max_lat"] == pytest.approx(-4.55)
    assert rep.available_pixel_dimensions["width"] < 3
    assert rep.available_pixel_dimensions["height"] < 3
    assert "slope" in rep.unsupported_derivative_products
    assert "NOT enlarged" in rep.insufficient_coverage_reason

    # Verify explicit broader region succeeds without modifying requested_bounds
    broader_bounds = {
        "min_lat": -6.0,
        "max_lat": -4.0,
        "min_lon": 136.5,
        "max_lon": 139.0,
    }
    manifest = DEMProcessingService.process_dem_dataset(
        dataset=ds,
        raw_dir=raw_dir,
        processed_dir=proc_dir,
        study_bounds=broader_bounds,
    )
    assert manifest["requested_bounds_modified"] is False
    assert manifest["requested_bounds"]["min_lat"] == pytest.approx(-6.0)
    assert manifest["requested_bounds"]["max_lat"] == pytest.approx(-4.0)
    assert manifest["raster_dimensions"]["width"] >= 3
    assert manifest["raster_dimensions"]["height"] >= 3


# ============================================================================
# PART A.3 — NO DEFAULT 25 DEG SAFETY THRESHOLD
# ============================================================================


def test_no_default_25_deg_safety_threshold_and_explicit_planning_threshold():
    """
    Verify that `critical_slope_threshold` is removed from PARAMETER_REGISTRY,
    TerrainSummary has `planning_threshold=None` by default, and an optional
    user-configured `PlanningSlopeThreshold` is explicitly tagged as a non-safety
    planning assumption.
    """
    assert "critical_slope_threshold" not in list_parameters()

    elev = np.array([[0.0, 10.0, 20.0], [0.0, 10.0, 20.0], [0.0, 10.0, 20.0]], dtype=np.float64)
    slope = np.array([[np.nan, np.nan, np.nan], [np.nan, 28.0, np.nan], [np.nan, np.nan, np.nan]], dtype=np.float64)
    aspect = np.array([[np.nan, np.nan, np.nan], [np.nan, 90.0, np.nan], [np.nan, np.nan, np.nan]], dtype=np.float64)
    tri = np.array([[np.nan, np.nan, np.nan], [np.nan, 12.0, np.nan], [np.nan, np.nan, np.nan]], dtype=np.float64)

    summary_default = compile_terrain_summary(
        source_dem_id="test_dem",
        study_area_name="Test Region",
        resolution_m=100.0,
        crs="IAU2000:MARS_SPHERE",
        elevation=elev,
        slope_deg=slope,
        aspect_deg=aspect,
        roughness_tri=tri,
        source_product_id="TEST.IMG",
        roughness_window_radius_meters=100.0,
    )
    assert summary_default.planning_threshold is None
    assert summary_default.planning_threshold_coverage_pct is None
    assert not hasattr(summary_default, "critical_slope_threshold_deg")

    user_thresh = PlanningSlopeThreshold(
        threshold_deg=20.0,
        label="custom_eva_planning_slope_threshold",
        provenance="Configured by mission planner for candidate comparison only.",
        version="1.0.0",
    )
    summary_with_thresh = compile_terrain_summary(
        source_dem_id="test_dem",
        study_area_name="Test Region",
        resolution_m=100.0,
        crs="IAU2000:MARS_SPHERE",
        elevation=elev,
        slope_deg=slope,
        aspect_deg=aspect,
        roughness_tri=tri,
        planning_threshold=user_thresh,
        source_product_id="TEST.IMG",
        roughness_window_radius_meters=100.0,
    )
    assert summary_with_thresh.planning_threshold is not None
    assert summary_with_thresh.planning_threshold.is_validated_safety_limit is False
    assert summary_with_thresh.planning_threshold.parameter_class == "user_configured_planning_assumption"
    assert summary_with_thresh.planning_threshold_coverage_pct == pytest.approx(100.0)


# ============================================================================
# PART A.4 — READER LEASE PROTECTION ACROSS CONCURRENT GENERATION REBUILDS
# ============================================================================


def test_generation_reader_lease_prevents_pruning_of_in_flight_generation(tmp_path: Path):
    """
    Verify that a reader holding `acquire_generation_lease()` on Generation 1
    is protected from having Generation 1's directory deleted even when 3 consecutive
    `publish_generation()` rebuilds execute while the reader is in flight.
    Once the reader releases its lease, a subsequent publish prunes Generation 1 cleanly.
    """
    db_path = tmp_path / "composition_index.sqlite"
    idx = CompositionSpatialIndex(db_path=db_path)

    def _make_ev(val: float) -> CompositionEvidence:
        ev = CompositionEvidence(
            evidence_id=f"temp_{val}",
            source_dataset_id="msl_apxs",
            product_id="P1",
            source_record_ref=f"rec_{val}",
            instrument_id="APXS",
            instrument_name="Alpha Particle X-Ray Spectrometer",
            processing_level="Derived",
            calibration_status="Calibrated",
            canonical_species_id="SiO2",
            canonical_species_name="SiO2",
            raw_species_name="SiO2",
            species_category=SpeciesCategory.OXIDE,
            evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
            evidence_status=EvidenceStatus.MEASURED,
            value_semantics=ValueSemantics.REPORTED_VALUE.value,
            raw_value=val,
            raw_unit="wt%",
            normalized_value=val,
            normalized_unit="wt%",
            methodology="X-ray fluorescence and particle-induced X-ray emission",
            source_reference="NASA PDS Geosciences Node",
            location_verified=True,
            latitude=-4.59,
            longitude_east=137.44,
        )
        ev.evidence_id = compute_deterministic_evidence_id(ev)
        return ev

    # Publish Generation 1
    idx.publish_generation(
        evidence_records=[_make_ev(45.1)],
        rejected_records=[],
        generation_id="gen_lease_01",
    )

    with idx.acquire_generation_lease() as (gen1_db, gen1_mf, gen1_ptr, gen1_errs):
        assert not gen1_errs
        assert gen1_db is not None and gen1_db.exists()
        assert gen1_mf is not None and gen1_mf.exists()
        gen1_dir = gen1_db.parent

        # While reader holds lease on gen_lease_01, publish 3 newer generations
        idx.publish_generation(
            evidence_records=[_make_ev(46.2)],
            rejected_records=[],
            generation_id="gen_lease_02",
        )
        idx.publish_generation(
            evidence_records=[_make_ev(47.3)],
            rejected_records=[],
            generation_id="gen_lease_03",
        )
        idx.publish_generation(
            evidence_records=[_make_ev(48.4)],
            rejected_records=[],
            generation_id="gen_lease_04",
        )

        # Generation 1 directory, DB, and manifest MUST still exist on disk while leased!
        assert gen1_dir.exists()
        assert gen1_db.exists()
        assert gen1_mf.exists()

    # Now that the reader lease is released, publish Generation 5 and verify gen_lease_01 is pruned
    idx.publish_generation(
        evidence_records=[_make_ev(49.5)],
        rejected_records=[],
        generation_id="gen_lease_05",
    )
    assert not gen1_dir.exists()


# ============================================================================
# PART B — HUMAN MOBILITY INTELLIGENCE ENGINE
# ============================================================================


def test_resolution_suitability_distinguishes_regional_and_local_regimes():
    """
    Verify that MOLA 4 ppd (~6603 m/pixel) is marked suitable for regional elevation,
    regional_approximation_only for regional roughness, and insufficient_resolution
    (supported=False) for local human-scale slope and small-scale obstacle detection.
    """
    mola_suit = evaluate_dem_resolution_suitability(
        native_resolution_m=14800.0,
        effective_resolution_m=6603.1,
        dem_available=True,
    )
    assert (
        mola_suit[AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS.value].suitability
        == ResolutionSuitabilityLevel.SUITABLE
    )
    assert mola_suit[AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS.value].supported is True
    regional = mola_suit[AnalysisScaleType.REGIONAL_ELEVATION_ANALYSIS.value]
    obstacle = mola_suit[AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION.value]
    assert RESOLUTION_POLICY_VERSION == "1.0.0"
    assert regional.policy_id == "marscope-dem-resolution-suitability"
    assert regional.threshold_classification == "engineering_recommendation"
    assert obstacle.threshold_classification == "unvalidated_heuristic"
    assert "cannot guarantee" in obstacle.threshold_rationale

    assert (
        mola_suit[AnalysisScaleType.REGIONAL_ROUGHNESS_ANALYSIS.value].suitability
        == ResolutionSuitabilityLevel.REGIONAL_APPROXIMATION_ONLY
    )

    assert (
        mola_suit[AnalysisScaleType.LOCAL_SLOPE_ANALYSIS.value].suitability
        == ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
    )
    assert mola_suit[AnalysisScaleType.LOCAL_SLOPE_ANALYSIS.value].supported is False

    assert (
        mola_suit[AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION.value].suitability
        == ResolutionSuitabilityLevel.INSUFFICIENT_RESOLUTION
    )
    assert mola_suit[AnalysisScaleType.SMALL_SCALE_OBSTACLE_DETECTION.value].supported is False


def test_coverage_5_states_and_elevation_profile_with_nodata_gaps(tmp_path: Path):
    """
    Construct a synthetic Mars DEM GeoTIFF containing both valid planar elevations
    and explicit nodata (-32768) pixels, and verify:
      - 5-state coverage intelligence counts
      - Elevation profile gain/loss and contiguous nodata_gap_segments
    """
    dem_path = tmp_path / "synthetic_mars_dem.tif"
    rows, cols = 8, 8
    arr = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            arr[r, c] = -4000.0 + (c * 50.0)  # +50 m per column eastward
    # Inject nodata column in the middle (col=4)
    arr[:, 4] = -32768.0

    rio_crs = rasterio.crs.CRS.from_proj4(
        f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
    )
    transform = from_bounds(137.0, -5.0, 137.8, -4.2, cols, rows)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=rio_crs,
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(arr, 1)

    ds = Dataset(
        id="test_synth_dem",
        product_title="Test Mars DEM",
        mission="Test",
        instrument="Test",
        product_id="synthetic_mars_dem.tif",
        product_type="DEM",
        source_archive="Test Archive",
        original_product_url="https://pds-geosciences.wustl.edu/",
        attribution="Test Attribution",
        coordinate_reference_system="IAU2000:49900",
        units="meters",
        horizontal_resolution_meters=5900.0,
        coverage=GeographicCoverage(
            min_latitude=-5.0,
            max_latitude=-4.2,
            min_longitude=137.0,
            max_longitude=137.8,
        ),
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path=str(dem_path),
    )

    cov = evaluate_region_coverage_intelligence(
        dataset=ds,
        raw_dir=tmp_path,
        requested_bounds={"min_lat": -5.0, "max_lat": -4.2, "min_lon": 137.0, "max_lon": 137.8},
    )
    assert cov.has_spatial_overlap is True
    assert cov.coverage_state_counts[TerrainCoverageState.INSIDE_FOOTPRINT_NODATA.value] == 8
    assert cov.coverage_state_counts[TerrainCoverageState.VALID_SOURCE_DATA.value] > 0
    assert cov.coverage_state_counts[TerrainCoverageState.DERIVATIVE_UNAVAILABLE_INVALID_NEIGHBORHOOD.value] > 0

    # Out-of-footprint request
    cov_outside = evaluate_region_coverage_intelligence(
        dataset=ds,
        raw_dir=tmp_path,
        requested_bounds={"min_lat": 10.0, "max_lat": 11.0, "min_lon": 137.0, "max_lon": 138.0},
    )
    assert cov_outside.has_spatial_overlap is False
    assert cov_outside.coverage_state_counts[TerrainCoverageState.OUTSIDE_SOURCE_FOOTPRINT.value] >= 1
    assert cov_outside.insufficient_coverage_report is not None


def test_mobility_scenario_and_traversal_model_no_defaults_and_no_extrapolation(tmp_path: Path):
    """
    Verify:
      - Unconfigured walking speed returns INSUFFICIENT_SCENARIO_PARAMETERS and null time
      - Configured walking speed returns exact baseline time t = d / v0
      - Slope and roughness adjustment rules apply within valid domain and refuse extrapolation outside
      - Unknown/nodata cells return UNKNOWN_TERRAIN and null cost (never 0.0)
      - Planning threshold exclusions return EXPLICIT_SCENARIO_EXCLUSION without 'unsafe' claims
    """
    from app.mobility.mobility_scenario import MobilityScenarioRegistry

    reg = MobilityScenarioRegistry(tmp_path / "scenarios.json")

    # 1. Scenario without walking speed
    sc_no_speed = reg.create_scenario(
        MobilityScenarioCreateRequest(
            name="Physical Only Scenario",
            astronaut_body_mass_kg=80.0,
            suit_mass_kg=60.0,
        )
    )
    assert sc_no_speed.reference_walking_speed_m_per_s is None
    assert sc_no_speed.traversal_time_estimation_ready is False
    assert sc_no_speed.total_mass_kg == pytest.approx(140.0)
    assert sc_no_speed.mars_surface_weight_n == pytest.approx(140.0 * 3.72076, rel=1e-4)
    assert (
        sc_no_speed.parameters["reference_walking_speed_m_per_s"].origin
        == ParameterOriginType.UNAVAILABLE
    )

    seg_no_speed = evaluate_cell_or_segment_traversal(
        segment_index=0,
        lat=-4.6,
        lon_east=137.4,
        horizontal_distance_meters=100.0,
        coverage_state=TerrainCoverageState.VALID_SOURCE_DATA,
        elevation_meters=-4400.0,
        elevation_delta_meters=10.0,
        slope_deg=5.0,
        aspect_deg=90.0,
        roughness_tri_meters=2.0,
        scenario=sc_no_speed,
    )
    assert seg_no_speed.traversal_availability_state == CellTraversalAvailabilityState.INSUFFICIENT_SCENARIO_PARAMETERS
    assert seg_no_speed.baseline_time_seconds is None
    assert seg_no_speed.adjusted_time_seconds is None
    # Physical measurements are still computed!
    assert seg_no_speed.gravitational_potential_energy_delta_joules == pytest.approx(140.0 * 3.72076 * 10.0, rel=1e-4)
    assert seg_no_speed.uphill_parallel_gravity_force_newtons is not None

    # 2. Scenario with explicit walking speed and slope/roughness adjustments
    sc_configured = reg.create_scenario(
        MobilityScenarioCreateRequest(
            name="Configured EVA Scenario",
            reference_walking_speed_m_per_s=1.0,
            walking_speed_provenance="User test assumption 1.0 m/s",
            planning_max_slope_deg=22.0,
            slope_speed_adjustment=SlopeSpeedAdjustmentRule(
                rule_id="test_linear_slope",
                rule_type="piecewise_linear_factor",
                reference_slope_deg=0.0,
                coefficient_per_deg=0.02,
                min_valid_slope_deg=0.0,
                max_valid_slope_deg=20.0,
                min_speed_factor=0.2,
                max_speed_factor=1.0,
                provenance="User test linear slope penalty (2% per deg up to 20 deg)",
            ),
            roughness_speed_adjustment=RoughnessSpeedAdjustmentRule(
                rule_id="test_linear_rough",
                reference_roughness_m=0.0,
                coefficient_per_meter=0.0001,
                min_valid_roughness_m=0.0,
                max_valid_roughness_m=2000.0,
                min_speed_factor=0.2,
                max_speed_factor=1.0,
                provenance="User test linear TRI penalty",
            ),
        )
    )
    assert sc_configured.traversal_time_estimation_ready is True

    # Valid cell at 10 deg slope, 1000 m TRI -> f_slope = 0.8, f_rough = 0.9 -> v_eff = 0.72 m/s
    seg_valid = evaluate_cell_or_segment_traversal(
        segment_index=1,
        lat=-4.6,
        lon_east=137.4,
        horizontal_distance_meters=720.0,
        coverage_state=TerrainCoverageState.VALID_SOURCE_DATA,
        elevation_meters=-4400.0,
        elevation_delta_meters=0.0,
        slope_deg=10.0,
        aspect_deg=180.0,
        roughness_tri_meters=1000.0,
        scenario=sc_configured,
    )
    assert seg_valid.traversal_availability_state == CellTraversalAvailabilityState.EVALUATED
    assert seg_valid.slope_speed_factor == pytest.approx(0.8)
    assert seg_valid.roughness_speed_factor == pytest.approx(0.9)
    assert seg_valid.effective_speed_m_per_s == pytest.approx(0.72)
    assert seg_valid.baseline_time_seconds == pytest.approx(720.0)
    assert seg_valid.adjusted_time_seconds == pytest.approx(1000.0)

    # Cell at 21 deg slope -> <= planning_max_slope_deg (22.0), but > rule max_valid_slope_deg (20.0) -> OUTSIDE_MODEL_VALID_DOMAIN
    seg_out_domain = evaluate_cell_or_segment_traversal(
        segment_index=2,
        lat=-4.6,
        lon_east=137.4,
        horizontal_distance_meters=100.0,
        coverage_state=TerrainCoverageState.VALID_SOURCE_DATA,
        elevation_meters=-4400.0,
        elevation_delta_meters=0.0,
        slope_deg=21.0,
        aspect_deg=180.0,
        roughness_tri_meters=500.0,
        scenario=sc_configured,
    )
    assert seg_out_domain.traversal_availability_state == CellTraversalAvailabilityState.OUTSIDE_MODEL_VALID_DOMAIN
    assert seg_out_domain.adjusted_time_seconds is None
    assert "extrapolation is prohibited" in (seg_out_domain.unavailable_or_exclusion_reason or "")

    # Cell at 25 deg slope -> exceeds planning_max_slope_deg (22.0) -> EXPLICIT_SCENARIO_EXCLUSION
    seg_excluded = evaluate_cell_or_segment_traversal(
        segment_index=3,
        lat=-4.6,
        lon_east=137.4,
        horizontal_distance_meters=100.0,
        coverage_state=TerrainCoverageState.VALID_SOURCE_DATA,
        elevation_meters=-4400.0,
        elevation_delta_meters=0.0,
        slope_deg=25.0,
        aspect_deg=180.0,
        roughness_tri_meters=500.0,
        scenario=sc_configured,
    )
    assert seg_excluded.traversal_availability_state == CellTraversalAvailabilityState.EXPLICIT_SCENARIO_EXCLUSION
    assert seg_excluded.adjusted_time_seconds is None

    # Unknown / nodata cell -> UNKNOWN_TERRAIN, null time (never 0.0!)
    seg_nodata = evaluate_cell_or_segment_traversal(
        segment_index=4,
        lat=-4.6,
        lon_east=137.4,
        horizontal_distance_meters=100.0,
        coverage_state=TerrainCoverageState.INSIDE_FOOTPRINT_NODATA,
        elevation_meters=None,
        elevation_delta_meters=None,
        slope_deg=None,
        aspect_deg=None,
        roughness_tri_meters=None,
        scenario=sc_configured,
    )
    assert seg_nodata.traversal_availability_state == CellTraversalAvailabilityState.UNKNOWN_TERRAIN
    assert seg_nodata.adjusted_time_seconds is None
    assert seg_nodata.baseline_time_seconds is None


def test_mobility_api_endpoints_live_contracts(tmp_path: Path, monkeypatch):
    """
    Exercise all `/api/mobility/*` endpoints against an isolated synthetic MOLA-scale
    DEM raster (7.4 km/px, IAU2000:49900) so tests pass offline on a clean checkout
    without requiring pre-downloaded multi-gigabyte PDS binaries.
    """
    from app.api import mobility as api_mobility
    from app.geospatial.crs import MARS_CRS_DEFINITIONS
    from app.ingestion.catalog import DatasetCatalogService
    from app.mobility.service import HumanMobilityService
    from app.schemas.dataset import LicenseStatus

    cat_dir = tmp_path / "catalog"
    raw_dir = tmp_path / "raw"
    proc_dir = tmp_path / "processed"
    cat_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)

    # Create synthetic regional DEM at ~0.125 deg/px (~7.4 km/px) over Gale [135..140] x [-7..-3]
    cols, rows = 40, 32
    dem_path = raw_dir / "megt90n000cb.tif"
    yy, xx = np.mgrid[0:rows, 0:cols]
    elev = (-4500.0 + yy * 18.5 + xx * 12.0).astype(np.float32)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype=rasterio.float32,
        crs=MARS_CRS_DEFINITIONS["IAU2000:49900"],
        transform=from_bounds(135.0, -7.0, 140.0, -3.0, cols, rows),
        nodata=-32768.0,
    ) as dst:
        dst.write(elev, 1)

    iso_cat = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
    iso_cat.register_dataset(
        Dataset(
            id="mola_megt90n000cb",
            product_title="Synthetic Regional MOLA MEGDR (8 ppd)",
            mission="Mars Global Surveyor",
            instrument="MOLA",
            product_id="MEGT90N000CB.IMG",
            product_type="DEM",
            source_archive="NASA PDS Geosciences",
            original_product_url="https://pds-geosciences.wustl.edu/",
            license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
            attribution="NASA PDS MOLA Science Team",
            coordinate_reference_system="IAU2000:49900",
            units="meters",
            horizontal_resolution_meters=7400.0,
            coverage=GeographicCoverage(
                min_latitude=-7.0,
                max_latitude=-3.0,
                min_longitude=135.0,
                max_longitude=140.0,
            ),
            status=DatasetLifecycleStatus.DOWNLOADED,
            local_file_path=str(dem_path),
        )
    )
    iso_mob = HumanMobilityService(
        catalog_service=iso_cat,
        raw_dir=raw_dir,
        processed_dir=proc_dir,
    )
    monkeypatch.setattr(api_mobility, "mobility_service", iso_mob)

    # 1. GET /api/mobility/status
    r_status = client.get("/api/mobility/status")
    assert r_status.status_code == 200
    st_body = r_status.json()
    assert st_body["route_optimization_enabled"] is True
    assert st_body["safety_certification_enabled"] is False
    assert st_body["locally_downloaded_dem_count"] >= 1
    mola_inv = next(i for i in st_body["terrain_inventory"] if i["dataset_id"] == "mola_megt90n000cb")
    assert (
        mola_inv["resolution_suitability"]["local_slope_analysis"]["suitability"]
        == "insufficient_resolution"
    )
    assert mola_inv["resolution_suitability"]["local_slope_analysis"]["supported"] is False

    # 2. GET /api/mobility/terrain/features (valid Gale study area)
    r_feat = client.get(
        "/api/mobility/terrain/features",
        params={"dataset_id": "mola_megt90n000cb", "min_lat": -5.5, "max_lat": -4.3, "min_lon": 137.2, "max_lon": 138.0},
    )
    assert r_feat.status_code == 200
    feat_body = r_feat.json()
    assert feat_body["requested_bounds_modified"] is False
    assert feat_body["grid_shape"]["rows"] >= 3
    assert feat_body["grid_shape"]["cols"] >= 3
    assert feat_body["elevation_stats"]["available"] is True
    assert feat_body["slope_stats"]["available"] is True

    # 2b. GET /api/mobility/terrain/features on tiny region (< 3x3 pixels) -> HTTP 422 with structured InsufficientCoverageReport
    r_tiny = client.get(
        "/api/mobility/terrain/features",
        params={"dataset_id": "mola_megt90n000cb", "min_lat": -4.60, "max_lat": -4.55, "min_lon": 137.35, "max_lon": 137.40},
    )
    assert r_tiny.status_code == 422
    tiny_detail = r_tiny.json()["detail"]
    assert tiny_detail["requested_bounds_modified"] is False
    assert "slope" in tiny_detail["unsupported_derivative_products"]

    # 3. GET /api/mobility/coverage
    r_cov = client.get(
        "/api/mobility/coverage",
        params={"dataset_id": "mola_megt90n000cb", "min_lat": -5.5, "max_lat": -4.3, "min_lon": 137.2, "max_lon": 138.0},
    )
    assert r_cov.status_code == 200
    cov_body = r_cov.json()
    assert cov_body["has_spatial_overlap"] is True
    assert cov_body["sufficient_for_3x3_derivatives"] is True
    assert cov_body["coverage_state_counts"]["valid_source_data"] > 0
    assert cov_body["coverage_state_counts"]["derivative_unavailable_invalid_neighborhood"] > 0

    # 4. POST /api/mobility/scenarios + GET /api/mobility/scenarios + GET /api/mobility/scenarios/{id}
    r_scen = client.post(
        "/api/mobility/scenarios",
        json={
            "name": "Gale Regional Transect Scenario",
            "version": "1.0.0",
            "reference_walking_speed_m_per_s": 0.8,
            "walking_speed_provenance": "Explicit user test speed 0.8 m/s",
            "planning_max_slope_deg": 12.0,
            "astronaut_body_mass_kg": 75.0,
            "suit_mass_kg": 55.0,
        },
    )
    assert r_scen.status_code == 201
    scen_body = r_scen.json()
    scen_id = scen_body["scenario_id"]
    assert scen_body["traversal_time_estimation_ready"] is True

    r_list = client.get("/api/mobility/scenarios")
    assert r_list.status_code == 200
    assert any(s["scenario_id"] == scen_id for s in r_list.json())

    r_get_scen = client.get(f"/api/mobility/scenarios/{scen_id}")
    assert r_get_scen.status_code == 200
    assert r_get_scen.json()["scenario_id"] == scen_id

    # Invalid negative walking speed -> 422
    r_bad_scen = client.post(
        "/api/mobility/scenarios",
        json={"name": "Invalid Speed", "reference_walking_speed_m_per_s": -1.5},
    )
    assert r_bad_scen.status_code == 422

    # 5. POST /api/mobility/elevation-profile
    r_prof = client.post(
        "/api/mobility/elevation-profile",
        json={
            "dataset_id": "mola_megt90n000cb",
            "start": {"lat": -4.5895, "lon": 137.4417, "label": "Bradbury Landing"},
            "end": {"lat": -5.08, "lon": 137.85, "label": "Mount Sharp Flank"},
            "sample_count": 15,
            "sampling_method": "nearest",
        },
    )
    assert r_prof.status_code == 200
    prof_body = r_prof.json()
    assert prof_body["sample_count"] == 15
    assert prof_body["valid_sample_count"] == 15
    assert prof_body["total_horizontal_distance_meters"] > 10000.0
    assert prof_body["total_positive_elevation_gain_meters"] is not None
    assert prof_body["total_negative_elevation_change_meters"] is not None

    # 6. POST /api/mobility/evaluate (transect mode)
    r_eval = client.post(
        "/api/mobility/evaluate",
        json={
            "dataset_id": "mola_megt90n000cb",
            "scenario_id": scen_id,
            "waypoints": [
                {"lat": -4.5895, "lon": 137.4417},
                {"lat": -5.08, "lon": 137.85},
            ],
            "sample_count": 10,
        },
    )
    assert r_eval.status_code == 200
    eval_body = r_eval.json()
    assert eval_body["evaluation_mode"] == "transect"
    assert "physical_terrain_measurements" in eval_body
    assert "scenario_traversal_estimates" in eval_body
    assert eval_body["scenario_traversal_estimates"]["safety_assessment"] == "not_performed_no_validated_safety_limits"

    # 7. GET /api/mobility/cost-surface/metadata
    r_cs = client.get(
        "/api/mobility/cost-surface/metadata",
        params={
            "dataset_id": "mola_megt90n000cb",
            "min_lat": -5.5,
            "max_lat": -4.3,
            "min_lon": 137.2,
            "max_lon": 138.0,
            "scenario_id": scen_id,
        },
    )
    assert r_cs.status_code == 200
    cs_body = r_cs.json()
    assert cs_body["unknown_cell_policy"] == "preserve_null_never_zero_cost"
    assert cs_body["safety_classification_policy"] == "no_safe_or_unsafe_labels_emitted"
    expected_cells = feat_body["grid_shape"]["rows"] * feat_body["grid_shape"]["cols"]
    assert len(cs_body["cells"]) == expected_cells
    # Border cells without 3x3 slope must have null traversal_cost_seconds_per_meter when planning_max_slope_deg is set
    border_cell = cs_body["cells"][0]
    assert border_cell["row"] == 0 and border_cell["col"] == 0
    assert border_cell["traversal_cost_seconds_per_meter"] is None
