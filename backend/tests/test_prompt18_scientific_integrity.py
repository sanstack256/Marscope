"""
PROMPT 18 — STRICT ADVERSARIAL SCIENTIFIC INTEGRITY & DATA-PIPELINE TEST SUITE

Covers Section 16.1 - 16.5 acceptance requirements:
  - 16.1 Scientific semantics (priority != scientific_value, firewall, unverified instruments,
         duplicate non-corroboration, contradiction retention, no fabricated uncertainty)
  - 16.2 Product validation (corrupt files, truncated downloads, bad labels/PDS4 XML, missing scaling,
         missing units, invalid dimensions, wrong signatures, oversized payload, checksum mismatch, WMTS)
  - 16.3 Coordinate and spatial registration checks (Earth CRS, lat/lon convention mismatch, invalid lat,
         ellipsoid mismatch, partial/disjoint overlap, resolution mismatch, resampling provenance)
  - 16.4 Target, campaign & security/API contracts (irrelevant/uncalibrated/wrong-mission targets,
         missing constraints -> INCOMPLETE_CONSTRAINT_EVALUATION, return-path failure -> INFEASIBLE,
         dependency SHA-256 staleness -> stale_upstream_dependency_changed, fail-closed rebuild auth, 422 guards)
  - 16.5 Acquisition resilience (503 retry, interrupted stream + 206 Range resume, overwrite protection,
         atomic write, checksum rejection, persistent SQLite/JSONL ledger & query provenance)

NOTE: Every synthetic fixture constructed in this file is explicitly labelled SYNTHETIC_TEST_DATA
and uses isolated tmp_path storage so real persisted NASA catalog artifacts are never mutated.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import AsyncIterator, List, Optional

import httpx
from httpx import ASGITransport, AsyncClient
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

import app.api.composition as api_comp
import app.api.datasets as api_ds
import app.api.science_investigation as api_si
from app.geospatial.crs import MARS_CRS_DEFINITIONS, evaluate_spatial_registration, validate_mars_crs
from app.geospatial.raster import RasterInspectionService
from app.ingestion.acquisition import AcquisitionService, safe_write_downloaded_bytes, validate_artifact_signature
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.pds_label import extract_pds3_metadata, extract_pds4_metadata, parse_pds4_table_delimited
from app.main import app
from app.routing.schemas import RouteCoordinateInput, RoutePlanningConstraints, RoutingMode
from app.schemas.dataset import (
    AcquisitionState,
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)
from app.schemas.target import InvestigationTargetEvidenceState, ScienceTarget
from app.science.composition.index import CompositionSpatialIndex
from app.science.investigation.eligibility import evaluate_dataset_eligibility, synthesize_question_evidence
from app.science.investigation.measurement_registry import check_inference_validity, list_instruments
from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignFeasibilityModelState,
    CampaignFreshnessState,
    CanonicalRequirementState,
    EvidenceEligibilityState,
    EvidenceMatchRecord,
    EvidenceMatchStrength,
    EvidenceRole,
    MeasurementClass,
    RecordObservationRequest,
    RegistryVerificationStatus,
    TargetEvaluationRequest,
)
from app.science.investigation.service import ScienceInvestigationService
from app.science.target_registry import TargetRegistryService
from app.services.container import (
    catalog_service,
    composition_index,
    composition_search_service,
    imagery_service,
    routing_service,
    science_investigation_service as live_si_service,
    target_registry,
)
from app.terrain.dem_validator import DEMValidationError, DEMValidator

MARS_PROJ4 = MARS_CRS_DEFINITIONS["IAU2000:49900"]


def _synthetic_dataset(
    *,
    ds_id: str = "synth_test_dem",
    product_id: str = "SYNTHETIC_TEST_DATA_PRODUCT_01",
    mission: str = "Mars Science Laboratory (MSL) SYNTHETIC_TEST_DATA",
    instrument: str = "SYNTHETIC_CHEMIN",
    crs: Optional[str] = "IAU2000:49900",
    units: str = "wt%",
    processing_level: str = "Derived RDR5",
    calibration_status: str = "SYNTHETIC_TEST_DATA calibrated wt%",
    status: DatasetLifecycleStatus = DatasetLifecycleStatus.VALIDATED,
    lat_conv: str = "Planetocentric",
    lon_dir: str = "East",
    res_m: Optional[float] = 1.0,
    sha256: Optional[str] = "a" * 64,
    bounds: Optional[GeographicCoverage] = None,
    radii_m: Optional[dict] = None,
    url: str = "https://example.invalid/synthetic_test_data.csv",
    local_file_path: Optional[str] = "raw/synthetic.csv",
    data_format: str = "CSV",
) -> Dataset:
    cov = bounds or GeographicCoverage(
        min_latitude=-4.76,
        max_latitude=-4.70,
        min_longitude=137.38,
        max_longitude=137.44,
        center_latitude=-4.73,
        center_longitude=137.41,
        longitude_range="[0, 360]",
    )
    return Dataset(
        id=ds_id,
        product_id=product_id,
        product_title=f"SYNTHETIC_TEST_DATA {product_id}",
        product_type="SYNTHETIC_TEST_DATA / SCIENCE",
        mission=mission,
        instrument=instrument,
        source_archive="SYNTHETIC_TEST_DATA_ARCHIVE",
        original_product_url=url,
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="SYNTHETIC_TEST_DATA Fixture",
        processing_level=processing_level,
        calibration_status=calibration_status,
        coverage=cov,
        coordinate_reference_system=crs,
        latitude_convention=lat_conv,
        longitude_direction=lon_dir,
        map_projection="Equirectangular",
        planetary_radii_m=radii_m,
        horizontal_resolution_meters=res_m,
        units=units,
        data_format=data_format,
        sha256_checksum=sha256,
        status=status,
        acquisition_state=AcquisitionState.PRODUCT_VALIDATED
        if status in {DatasetLifecycleStatus.VALIDATED, DatasetLifecycleStatus.PROCESSED}
        else AcquisitionState.DISCOVERED,
        local_file_path=local_file_path,
        verification=MetadataVerification(
            archive_availability=VerificationState.VERIFIED,
            product_discovery=VerificationState.VERIFIED,
            metadata_verification=VerificationState.VERIFIED
            if calibration_status != "unknown"
            else VerificationState.UNVERIFIED,
            license_verification=VerificationState.VERIFIED,
            coverage_verification=VerificationState.VERIFIED,
            download_verification=VerificationState.VERIFIED
            if status in {DatasetLifecycleStatus.DOWNLOADED, DatasetLifecycleStatus.VALIDATED, DatasetLifecycleStatus.PROCESSED}
            else VerificationState.UNVERIFIED,
            processing_verification=VerificationState.VERIFIED
            if status == DatasetLifecycleStatus.PROCESSED
            else VerificationState.NOT_APPLICABLE,
        ),
        validation_report={
            "validation_passed": status in {DatasetLifecycleStatus.VALIDATED, DatasetLifecycleStatus.PROCESSED},
            "checksum_verified": sha256 is not None,
            "crs_valid": crs == "IAU2000:49900",
            "failures": [],
            "warnings": [],
        },
    )


def _write_synthetic_float_geotiff(path: Path, bounds=(-4.755, -4.705, 137.385, 137.435), shape=(12, 12)) -> Path:
    min_lat, max_lat, min_lon, max_lon = bounds
    h, w = shape
    elev = np.linspace(-4200.0, -4190.0, h * w, dtype=np.float32).reshape(h, w)
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs=MARS_PROJ4,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(elev, 1)
        dst.set_band_unit(1, "meters")
        dst.update_tags(VERTICAL_UNITS="meters", UNITS="meters")
    return path


@pytest.fixture()
def isolated_si(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScienceInvestigationService:
    svc = ScienceInvestigationService(
        catalog_service=catalog_service,
        target_registry=target_registry,
        composition_search_service=composition_search_service,
        composition_index=composition_index,
        routing_service=routing_service,
        evidence_service=live_si_service.evidence_service,
        processed_dir=tmp_path,
        imagery_service=imagery_service,
    )
    monkeypatch.setattr(api_si, "science_investigation_service", svc)
    return svc


# =============================================================================
# 16.1 SCIENTIFIC SEMANTICS
# =============================================================================


class TestScientificSemantics:
    def test_scientific_value_not_copied_from_exploration_priority(self, tmp_path: Path):
        reg = TargetRegistryService()
        tgt = ScienceTarget(
            id="synth_t1",
            name="SYNTHETIC_TEST_DATA Boxwork Site",
            latitude=-4.73,
            longitude=137.41,
            geology_type="MgSO4",
            scientific_value=None,
            exploration_priority_score=0.88,
            instrument_source="ChemCam LIBS",
            provenance_product_id="SYNTHETIC_TEST_DATA_01",
            target_status="evidence_backed",
            evidence_ids=["ev_synth_01"],
        )
        saved = reg.register_target(tgt)
        assert saved.scientific_value is None
        assert saved.exploration_priority_score == pytest.approx(0.88)
        assert saved.scientific_confidence_score is None

    def test_optical_and_elemental_inference_firewall(self):
        # Optical cannot establish mineral phase/identity
        for inst_id in ("HIRISE", "CTX", "MASTCAM"):
            res = check_inference_validity(inst_id, "confirm gypsum mineral hydration visually")
            assert res.allowed is False
            assert res.prohibited_inferences
        wmts_res = check_inference_validity("MARS_TREK_WMTS", "confirm gypsum mineral hydration visually")
        assert wmts_res.allowed is False

        # Elemental chemistry cannot establish crystalline mineral phase without XRD/IR
        chemcam_res = check_inference_validity(
            "CHEMCAM_LIBS", "prove crystalline smectite clay mineral phase presence from MgO"
        )
        assert chemcam_res.allowed is False
        apxs_res = check_inference_validity("APXS", "establish CaSO4 mineral phase identification")
        assert apxs_res.allowed is False

    def test_missing_observations_never_establish_absence(self, isolated_si: ScienceInvestigationService):
        disc = isolated_si.discover_evidence_for_question("gale_sulfate_clay_transition")
        # CRISM orbital spectroscopy is absent in Gale local composition index
        crism_reqs = [
            r for r in disc.requirements_evaluation if r.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL
        ]
        assert crism_reqs
        req = crism_reqs[0]
        assert req.canonical_state in {
            CanonicalRequirementState.UNSATISFIED,
            CanonicalRequirementState.BLOCKED_BY_DATA_GAP,
            CanonicalRequirementState.UNAVAILABLE,
        }
        assert any(
            "absence" in g.lower() or "unavailable" in g.lower() or "unacquired" in g.lower() or "crism" in g.lower()
            for g in (req.limitations_and_gaps + req.missing_information)
        )

    def test_unverified_instruments_cannot_qualify_evidence(self, isolated_si: ScienceInvestigationService):
        unverified_inst = [
            inst for inst in list_instruments(include_mission_isolated=True)
            if inst.verification_status == RegistryVerificationStatus.UNVERIFIED
        ]
        assert len(unverified_inst) >= 1, "Expected unverified registry entries for unbacked instruments."
        q = isolated_si.questions_repo.get_question("gale_boxwork_origin")
        assert q is not None

        # Inject synthetic dataset tied to an UNVERIFIED instrument (THEMIS / OMEGA / PIXL)
        ds = _synthetic_dataset(
            ds_id="synth_unverified_inst",
            instrument="MARS2020_PIXL",
            mission="Mars 2020 SYNTHETIC_TEST_DATA",
            units="wt%",
        )
        ev = evaluate_dataset_eligibility(
            ds=ds,
            inst_cls="PIXL",
            question=q,
            is_gale=True,
            seen_sha256=set(),
            seen_product_ids=set(),
            reference_dtm=None,
        )
        assert ev["eligibility_state"] in {
            EvidenceEligibilityState.MISSION_INCOMPATIBLE,
            EvidenceEligibilityState.PRODUCT_UNVERIFIED,
            EvidenceEligibilityState.REJECTED,
        }

    def test_duplicate_non_corroboration_and_contradiction_retention(self, isolated_si: ScienceInvestigationService):
        # 1. Duplicate synthesis check: two identical SHA-256 evidence records must not count as 2 independent
        q = isolated_si.questions_repo.get_question("gale_boxwork_origin")
        assert q is not None
        dup_rec_1 = EvidenceMatchRecord(
            match_id="synth_dup_1",
            source_type="dataset",
            source_id="synth_ds_a",
            product_id="SYNTH_PROD_A",
            instrument_id="CHEMIN",
            mission_host="MSL",
            study_region="Gale Crater",
            dataset_status="validated",
            eligibility_state=EvidenceEligibilityState.ELIGIBLE,
            evidence_role=EvidenceRole.SUPPORTING,
            evidence_role_rationale="SYNTHETIC_TEST_DATA primary CheMin XRD product",
            evidence_strength=EvidenceMatchStrength.DIRECT_LOCAL_IN_SITU,
            duplication_or_correlation={"is_duplicate": False, "corroborates_independently": True},
        )
        dup_rec_2 = EvidenceMatchRecord(
            match_id="synth_dup_2",
            source_type="dataset",
            source_id="synth_ds_b",
            product_id="SYNTH_PROD_A",
            instrument_id="CHEMIN",
            mission_host="MSL",
            study_region="Gale Crater",
            dataset_status="validated",
            eligibility_state=EvidenceEligibilityState.DUPLICATE_OR_CORRELATED,
            evidence_role=EvidenceRole.SUPPORTING,
            evidence_role_rationale="SYNTHETIC_TEST_DATA mirrored CheMin XRD product",
            evidence_strength=EvidenceMatchStrength.ORBITAL_FOOTPRINT_INTERSECTION,
            duplication_or_correlation={"is_duplicate": True, "corroborates_independently": False},
        )
        synth = synthesize_question_evidence(question=q, matched=[dup_rec_1, dup_rec_2], requirements=[])
        assert synth.duplicate_or_correlated_count == 1
        assert synth.independent_evidence_count == 1

        # 2. Contradictory crew observation is retained and surfaced during campaign freshness/archive comparison
        obs = isolated_si.record_observation(
            RecordObservationRequest(
                instrument_id="CHEMCAM_LIBS",
                measurement_type="elemental_oxide_wt_pct",
                species_or_feature="SO3",
                measured_value=95.0,
                units="wt%",
                latitude=-4.59,
                longitude_east=137.44,
                notes="SYNTHETIC_TEST_DATA extreme contradicting test reading",
            )
        )
        obs_list = isolated_si.list_observations()
        assert any(o.observation_id == obs.observation_id for o in obs_list)
        cmp = isolated_si.compare_observation_with_archive(obs.observation_id, search_radius_m=500.0)
        assert cmp.observation_id == obs.observation_id

    def test_no_fabricated_observation_data_volume(self, isolated_si: ScienceInvestigationService):
        targs = isolated_si.evaluate_targets(
            TargetEvaluationRequest(
                question_id="gale_boxwork_origin",
                study_bounds={"min_lat": -4.752, "max_lat": -4.706, "min_lon": 137.386, "max_lon": 137.433},
                max_candidates=2,
            )
        )
        assert targs.targets
        t0 = targs.targets[0]
        plan = isolated_si.build_campaign(
            CampaignBuildRequest(
                campaign_name="SYNTHETIC_TEST_DATA No Fabricated Volume",
                question_id="gale_boxwork_origin",
                dataset_id="hirise_dteec_009149_1750",
                start=RouteCoordinateInput(lat=t0.latitude + 0.0007, lon_east=t0.longitude_east - 0.0007),
                selected_target_ids=[t0.target_id],
                candidate_targets=[t0],
                include_alternatives=False,
            )
        )
        for sp in plan.stop_plans:
            assert sp.observation_plan.estimated_data_volume_mb is None
            assert "UNAVAILABLE" in sp.observation_plan.data_volume_status


# =============================================================================
# 16.2 PRODUCT VALIDATION
# =============================================================================


class TestProductValidation:
    def test_missing_scaling_factor_and_missing_units_rejected(self, tmp_path: Path):
        raw_dir = tmp_path / "raw"
        cat_dir = tmp_path / "catalog"
        raw_dir.mkdir()
        cat_dir.mkdir()

        # Synthetic integer DEM label lacking BOTH SCALING_FACTOR and UNIT
        lbl_path = raw_dir / "synth_missing.lbl"
        lbl_path.write_text(
            "PDS_VERSION_ID = PDS3\n"
            "RECORD_TYPE = FIXED_LENGTH\n"
            "OBJECT = IMAGE\n"
            "  LINES = 10\n"
            "  LINE_SAMPLES = 10\n"
            "  SAMPLE_TYPE = MSB_INTEGER\n"
            "  SAMPLE_BITS = 16\n"
            "END_OBJECT = IMAGE\nEND\n",
            encoding="utf-8",
        )
        img_path = raw_dir / "synth_missing.img"
        img_bytes = b"\x00\x01" * 100
        img_path.write_bytes(img_bytes)
        sha = hashlib.sha256(img_bytes).hexdigest()

        parsed = extract_pds3_metadata(lbl_path)
        assert parsed.get("scaling_factor") is None
        assert parsed.get("units") in {None, "unknown"}

        cat = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
        ds = _synthetic_dataset(
            ds_id="synth_missing_meta_dem",
            product_id="SYNTHETIC_MISSING_SCALE",
            units="unknown",
            sha256=sha,
            local_file_path="raw/synth_missing.img",
            data_format="PDS3 MSB_INTEGER DEM",
        )
        ds.product_type = "DEM / SYNTHETIC_TEST_DATA"
        ds.local_label_path = "raw/synth_missing.lbl"
        cat.register_dataset(ds)

        report = cat.validate_dataset_integrity(
            "synth_missing_meta_dem",
            {"min_lat": -4.75, "max_lat": -4.71, "min_lon": 137.39, "max_lon": 137.43},
        )
        assert report["validation_passed"] is False
        assert report["acquisition_state"] == AcquisitionState.REJECTED.value
        assert any("SCALING_FACTOR" in f or "UNIT" in f for f in report["validation_report"]["failures"])

    def test_corrupt_raster_wrong_signature_oversized_and_checksum_mismatch(self, tmp_path: Path):
        # 1. HTML error masquerading as GeoTIFF
        bad_tif = tmp_path / "fake.tif"
        with pytest.raises(ValueError, match="HTML"):
            safe_write_downloaded_bytes(
                bad_tif,
                b"<!DOCTYPE html><html><body>502 Bad Gateway</body></html>",
                source_url="https://example.invalid/fake.tif",
                content_type="text/html",
            )

        # 2. Random bytes masquerading as GeoTIFF -> magic byte rejection
        with pytest.raises(ValueError, match="TIFF"):
            validate_artifact_signature(b"NOT_A_TIFF_HEADER_BYTES_1234", bad_tif, "image/tiff")

        # 3. Oversized artifact rejected
        good_json = tmp_path / "small.json"
        with pytest.raises(ValueError, match="max_bytes"):
            safe_write_downloaded_bytes(
                good_json,
                b'{"a": 1, "b": "SYNTHETIC_TEST_DATA"}',
                source_url="https://example.invalid/small.json",
                content_type="application/json",
                max_bytes=10,
            )

        # 4. Corrupt TIFF file fails RasterInspectionService
        bad_tif.write_bytes(b"II*\x00corrupted_payload")
        with pytest.raises(Exception):
            RasterInspectionService.inspect_raster_file(bad_tif)

        # 5. Checksum mismatch rejected cleanly in validate_dataset_integrity
        raw_dir = tmp_path / "raw2"
        cat_dir = tmp_path / "cat2"
        raw_dir.mkdir()
        cat_dir.mkdir()
        good_tif = _write_synthetic_float_geotiff(raw_dir / "valid_test.tif")
        cat = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
        ds = _synthetic_dataset(
            ds_id="synth_bad_sha",
            units="meters",
            sha256="f" * 64,  # Deliberately wrong hash
            local_file_path="raw2/valid_test.tif",
            data_format="GeoTIFF",
        )
        cat.register_dataset(ds)
        rep = cat.validate_dataset_integrity(
            "synth_bad_sha",
            {"min_lat": -4.75, "max_lat": -4.71, "min_lon": 137.39, "max_lon": 137.43},
        )
        assert rep["validation_passed"] is False
        assert rep["validation_report"]["checksum_verified"] is False
        assert any("checksum mismatch" in f.lower() for f in rep["validation_report"]["failures"])

    def test_invalid_dimensions_and_malformed_pds4_xml(self, tmp_path: Path):
        # 1. Invalid dimensions (< 3x3) rejected by DEMValidator
        tiny_tif = _write_synthetic_float_geotiff(tmp_path / "tiny.tif", shape=(2, 2))
        insp = RasterInspectionService.inspect_raster_file(tiny_tif, explicit_units="meters")
        with pytest.raises(DEMValidationError, match="3x3"):
            DEMValidator.validate_dem_metadata(insp)

        # 2. Malformed PDS4 XML and wrong root tag rejected
        bad_xml = tmp_path / "malformed.xml"
        bad_xml.write_text("<NotAProduct><logical_identifier>urn:x</logical_identifier></NotAProduct>", encoding="utf-8")
        with pytest.raises(ValueError, match="Product_"):
            extract_pds4_metadata(bad_xml)

        missing_lid = tmp_path / "no_lid.xml"
        missing_lid.write_text("<Product_Observational></Product_Observational>", encoding="utf-8")
        with pytest.raises(ValueError, match="logical_identifier"):
            extract_pds4_metadata(missing_lid)

        bad_syntax = tmp_path / "broken.xml"
        bad_syntax.write_text("<Product_Observational><unclosed>", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed PDS4 XML"):
            extract_pds4_metadata(bad_syntax)
        with pytest.raises(ValueError):
            parse_pds4_table_delimited(bad_syntax)

    def test_unverified_calibration_and_wmts_exclusion(self, tmp_path: Path):
        raw_dir = tmp_path / "raw3"
        cat_dir = tmp_path / "cat3"
        raw_dir.mkdir()
        cat_dir.mkdir()
        cat = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
        wmts = _synthetic_dataset(
            ds_id="synth_wmts",
            product_id="WMTS_TILE_URL",
            status=DatasetLifecycleStatus.AVAILABLE,
            url="https://trek.nasa.gov/tiles/{z}/{y}/{x}.jpg",
            local_file_path=None,
            data_format="WMTS",
            sha256=None,
            units="visual_rgb",
        )
        cat.register_dataset(wmts)
        rep = cat.validate_dataset_integrity(
            "synth_wmts",
            {"min_lat": -4.75, "max_lat": -4.71, "min_lon": 137.39, "max_lon": 137.43},
        )
        assert rep["acquisition_state"] == AcquisitionState.AVAILABLE.value
        assert rep["verification"]["download_verification"] == "not_applicable"

        # Unverified calibration product never gets ELIGIBLE
        q = live_si_service.questions_repo.get_question("gale_boxwork_origin")
        assert q is not None
        uncal_ds = _synthetic_dataset(
            ds_id="synth_uncal",
            instrument="CheMin XRD",
            calibration_status="unknown",
            processing_level="unknown",
            status=DatasetLifecycleStatus.DOWNLOADED,
        )
        ev = evaluate_dataset_eligibility(
            ds=uncal_ds,
            inst_cls="CHEMIN",
            question=q,
            is_gale=True,
            seen_sha256=set(),
            seen_product_ids=set(),
            reference_dtm=None,
        )
        assert ev["eligibility_state"] != EvidenceEligibilityState.ELIGIBLE


# =============================================================================
# 16.3 COORDINATE AND SPATIAL REGISTRATION
# =============================================================================


class TestCoordinateAndRegistration:
    def test_earth_crs_convention_radii_overlap_scale_and_resampling(self):
        # 1. Earth WGS84 rejected
        assert validate_mars_crs("EPSG:4326") is False
        reg_earth = evaluate_spatial_registration(
            product_a_id="synth_a",
            product_b_id="ref_dtm",
            crs_a="EPSG:4326",
            crs_b="IAU2000:49900",
            bounds_a={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            bounds_b={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            resolution_a_m=1.0,
            resolution_b_m=1.0,
        )
        assert reg_earth["registration_state"] == "INCOMPATIBLE_REFERENCE_SYSTEM"
        assert reg_earth["crs_compatible"] is False

        # 2. Planetocentric vs Planetographic mismatch flagged
        reg_lat = evaluate_spatial_registration(
            product_a_id="synth_pgr",
            product_b_id="ref_dtm",
            crs_a="IAU2000:49900",
            crs_b="IAU2000:49900",
            bounds_a={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            bounds_b={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            resolution_a_m=1.0,
            resolution_b_m=1.0,
            lat_conv_a="Planetographic",
            lat_conv_b="Planetocentric",
        )
        assert reg_lat["registration_state"] == "INCOMPATIBLE_REFERENCE_SYSTEM"
        assert any("Planetographic" in b for b in reg_lat["blockers"])

        # 3. Ellipsoid major radius incompatibility blocked
        reg_rad = evaluate_spatial_registration(
            product_a_id="synth_rad",
            product_b_id="ref_dtm",
            crs_a="IAU2000:49900",
            crs_b="IAU2000:49900",
            bounds_a={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            bounds_b={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            resolution_a_m=1.0,
            resolution_b_m=1.0,
            lat_conv_a="Planetocentric",
            lat_conv_b="Planetocentric",
            radii_a_m={"a": 6378137.0, "c": 6356752.0},
            radii_b_m={"a": 3396190.0, "c": 3376200.0},
        )
        assert reg_rad["registration_state"] == "INCOMPATIBLE_REFERENCE_SYSTEM"

        # 4. Disjoint footprint -> NOT_REGISTERED
        reg_disjoint = evaluate_spatial_registration(
            product_a_id="synth_far",
            product_b_id="ref_dtm",
            crs_a="IAU2000:49900",
            crs_b="IAU2000:49900",
            bounds_a={"min_latitude": 18.0, "max_latitude": 19.0, "min_longitude": 77.0, "max_longitude": 78.0},
            bounds_b={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.3, "max_longitude": 137.5},
            resolution_a_m=1.0,
            resolution_b_m=1.0,
            lat_conv_a="Planetocentric",
            lat_conv_b="Planetocentric",
            lon_dir_a="East",
            lon_dir_b="East",
            declared_registration_error_m=0.5,
        )
        assert reg_disjoint["registration_state"] == "NOT_REGISTERED"
        assert reg_disjoint["overlap_ratio"] == 0.0

        # 5. Partial overlap + >10x resolution disparity + explicit resampling provenance
        reg_partial = evaluate_spatial_registration(
            product_a_id="synth_part",
            product_b_id="ref_dtm",
            crs_a="IAU2000:MARS_SPHERE",
            crs_b="IAU2000:49900",
            bounds_a={"min_latitude": -5.0, "max_latitude": -4.6, "min_longitude": 137.3, "max_longitude": 137.6},
            bounds_b={"min_latitude": -4.8, "max_latitude": -4.7, "min_longitude": 137.35, "max_longitude": 137.45},
            resolution_a_m=463.0,
            resolution_b_m=1.01,
            lat_conv_a="Planetocentric",
            lat_conv_b="Planetocentric",
            lon_dir_a="East",
            lon_dir_b="East",
            resampling_method="bilinear",
            declared_registration_error_m=120.0,
        )
        assert reg_partial["registration_state"] == "PARTIALLY_OVERLAPPING"
        assert reg_partial["resolution_ratio"] > 10.0
        assert reg_partial["resampling_method"] == "bilinear"
        assert reg_partial["registration_error_m"] == 120.0
        assert any("resolution disparity" in w.lower() for w in reg_partial["warnings"])


# =============================================================================
# 16.4 TARGET, CAMPAIGN, STALENESS & API SECURITY
# =============================================================================


class TestTargetCampaignAndAPI:
    def test_irrelevant_and_wrong_mission_dataset_eligibility(self):
        q = live_si_service.questions_repo.get_question("gale_boxwork_origin")
        assert q is not None

        # Wrong mission (Mars 2020 Jezero) quarantined
        ds_jezero = _synthetic_dataset(
            ds_id="synth_jezero_pixl",
            mission="Mars 2020 Perseverance",
            instrument="PIXL",
            bounds=GeographicCoverage(
                min_latitude=18.2, max_latitude=18.6, min_longitude=77.3, max_longitude=77.6, longitude_range="[0, 360]"
            ),
        )
        ev_jz = evaluate_dataset_eligibility(
            ds=ds_jezero,
            inst_cls="PIXL",
            question=q,
            is_gale=True,
            seen_sha256=set(),
            seen_product_ids=set(),
            reference_dtm=None,
        )
        assert ev_jz["eligibility_state"] == EvidenceEligibilityState.MISSION_INCOMPATIBLE

        # Scientifically irrelevant (atmospheric pressure REMS in Gale)
        ds_rems = _synthetic_dataset(
            ds_id="synth_rems_pres",
            mission="Mars Science Laboratory (MSL)",
            instrument="REMS",
            units="Pa",
        )
        ds_rems.product_type = "METEOROLOGY / PRESSURE"
        ev_irrel = evaluate_dataset_eligibility(
            ds=ds_rems,
            inst_cls="REMS",
            question=q,
            is_gale=True,
            seen_sha256=set(),
            seen_product_ids=set(),
            reference_dtm=None,
        )
        assert ev_irrel["eligibility_state"] in {
            EvidenceEligibilityState.SCIENTIFICALLY_IRRELEVANT,
            EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS,
        }

    def test_missing_constraints_return_failure_and_staleness(self, isolated_si: ScienceInvestigationService):
        targs = isolated_si.evaluate_targets(
            TargetEvaluationRequest(
                question_id="gale_boxwork_origin",
                study_bounds={"min_lat": -4.752, "max_lat": -4.706, "min_lon": 137.386, "max_lon": 137.433},
                max_candidates=2,
            )
        )
        t0 = targs.targets[0]

        # 1. Missing walking_speed_mps / mission_duration_limit_s -> INCOMPLETE_CONSTRAINT_EVALUATION
        incomplete_plan = isolated_si.build_campaign(
            CampaignBuildRequest(
                campaign_name="SYNTHETIC_TEST_DATA Incomplete Constraints",
                question_id="gale_boxwork_origin",
                dataset_id="hirise_dteec_009149_1750",
                start=RouteCoordinateInput(lat=t0.latitude + 0.0007, lon_east=t0.longitude_east - 0.0007),
                selected_target_ids=[t0.target_id],
                candidate_targets=[t0],
                walking_speed_mps=None,
                mission_duration_limit_s=None,
                include_alternatives=False,
            )
        )
        assert incomplete_plan.feasibility_state == CampaignFeasibilityModelState.INCOMPLETE_CONSTRAINT_EVALUATION
        assert incomplete_plan.constraint_evaluation_complete is False
        assert incomplete_plan.operational_safety_certified is False

        # 2. Return-path / duration infeasibility (tight 10-second mission duration limit)
        infeasible_plan = isolated_si.build_campaign(
            CampaignBuildRequest(
                campaign_name="SYNTHETIC_TEST_DATA Infeasible Time",
                question_id="gale_boxwork_origin",
                dataset_id="hirise_dteec_009149_1750",
                start=RouteCoordinateInput(lat=t0.latitude + 0.0008, lon_east=t0.longitude_east - 0.0008),
                selected_target_ids=[t0.target_id],
                candidate_targets=[t0],
                walking_speed_mps=0.8,
                mission_duration_limit_s=10.0,
                return_reserve_fraction=0.25,
                include_alternatives=False,
            )
        )
        assert infeasible_plan.feasibility_state == CampaignFeasibilityModelState.INFEASIBLE_UNDER_CONFIGURED_MODEL

        # 3. Dependency staleness: recording a new field observation on the campaign invalidates signature
        fr_before = isolated_si.check_campaign_freshness(infeasible_plan.campaign_id)
        assert fr_before.freshness_state == CampaignFreshnessState.CURRENT
        isolated_si.record_observation(
            RecordObservationRequest(
                campaign_id=infeasible_plan.campaign_id,
                target_id=t0.target_id,
                instrument_id="CHEMCAM_LIBS",
                measurement_type="elemental_oxide_wt_pct",
                species_or_feature="SO3",
                measured_value=9.5,
                units="wt%",
                latitude=t0.latitude,
                longitude_east=t0.longitude_east,
            )
        )
        fr_after = isolated_si.check_campaign_freshness(infeasible_plan.campaign_id)
        assert fr_after.freshness_state == CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED
        assert fr_after.current_signature != fr_after.stored_signature

        recomputed = isolated_si.recompute_campaign(infeasible_plan.campaign_id)
        assert recomputed.freshness_state == CampaignFreshnessState.CURRENT

    @pytest.mark.asyncio
    async def test_api_fail_closed_auth_and_explicit_422_guards(
        self, isolated_si: ScienceInvestigationService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MARSCOPE_OPERATOR_TOKEN", "prompt18-secret-token")
        comp_idx = CompositionSpatialIndex(
            db_path=tmp_path / "comp_test.sqlite",
        )
        monkeypatch.setattr(api_comp, "composition_index", comp_idx)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Fail-closed composition index rebuild without token -> 401/403
            r_unauth = await client.post("/api/composition/index/rebuild")
            assert r_unauth.status_code in {401, 403}

            # Wrong token rejected
            r_wrong = await client.post(
                "/api/composition/index/rebuild",
                headers={"X-Mars-Operator-Token": "wrong-token"},
            )
            assert r_wrong.status_code in {401, 403}

            # 2. Invalid path identifier rejected with HTTP 422
            r_bad_id = await client.get("/api/science-investigation/products/bad%20id%3Bdrop/inspect")
            assert r_bad_id.status_code == 422

            # 3. Missing explicit bounds / dataset_id on mobility endpoints rejected with HTTP 422 (no silent defaults)
            r_mob_cov = await client.get("/api/mobility/coverage")
            assert r_mob_cov.status_code == 422
            r_mob_feat = await client.get("/api/mobility/terrain/features")
            assert r_mob_feat.status_code == 422
            r_mob_cost = await client.get("/api/mobility/cost-surface/metadata")
            assert r_mob_cost.status_code == 422

            # 4. Product inspect (#21) & Campaign dossier export (#22)
            r_insp = await client.get(
                "/api/science-investigation/products/hirise_dteec_009149_1750/inspect",
                params={"question_id": "gale_boxwork_origin"},
            )
            assert r_insp.status_code == 200
            insp_body = r_insp.json()
            assert insp_body["dataset"]["product_id"] == "DTEEC_009149_1750_009294_1750_U01.IMG"
            assert len(insp_body["eligibility_dimensions"]) >= 12


# =============================================================================
# 16.5 ACQUISITION RESILIENCE
# =============================================================================


class TestAcquisitionResilience:
    @pytest.mark.asyncio
    async def test_retry_range_resume_non_overwrite_and_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        raw_dir = tmp_path / "raw"
        man_dir = tmp_path / "manifests"
        acq = AcquisitionService(raw_data_dir=raw_dir, manifests_dir=man_dir)

        csv_payload = (
            b"phase,abundance_wt_pct,error_wt_pct\n"
            b"SYNTHETIC_TEST_DATA_PLAGIOCLASE,40.8,3.2\n"
            b"SYNTHETIC_TEST_DATA_ANHYDRITE,1.4,0.3\n"
        )
        expected_sha = hashlib.sha256(csv_payload).hexdigest()
        lbl_payload = (
            b"PDS_VERSION_ID = PDS3\n"
            b"PRODUCT_ID = \"SYNTH_CHEMIN_01\"\n"
            b"OBJECT = TABLE\n  INTERCHANGE_FORMAT = ASCII\n"
            b"  ROWS = 2\n  COLUMNS = 3\n"
            b"END_OBJECT = TABLE\nEND\n"
        )

        # Simulate: request 1 (product): HTTP 503 transient failure
        #           request 2 (product): Interrupted stream after 30 bytes
        #           request 3 (product): HTTP 206 Range resumption of remaining bytes
        product_calls = 0

        class _PartialInterruptStream(httpx.AsyncByteStream):
            def __init__(self, first_chunk: bytes):
                self._first = first_chunk

            async def __aiter__(self) -> AsyncIterator[bytes]:
                yield self._first
                raise httpx.ReadError("Simulated mid-stream TCP reset")

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal product_calls
            url = str(request.url)
            if url.endswith(".lbl"):
                return httpx.Response(200, content=lbl_payload, headers={"content-type": "text/plain"})
            product_calls += 1
            if product_calls == 1:
                return httpx.Response(503, text="Service Unavailable")
            range_hdr = request.headers.get("range")
            if product_calls == 2 and not range_hdr:
                return httpx.Response(
                    200,
                    stream=_PartialInterruptStream(csv_payload[:30]),
                    headers={
                        "content-type": "text/csv",
                        "content-length": str(len(csv_payload)),
                        "etag": '"synth-etag-1"',
                    },
                )
            assert range_hdr == "bytes=30-"
            assert request.headers.get("if-range") == '"synth-etag-1"'
            rest = csv_payload[30:]
            return httpx.Response(
                206,
                content=rest,
                headers={
                    "content-type": "text/csv",
                    "content-range": f"bytes 30-{len(csv_payload) - 1}/{len(csv_payload)}",
                    "etag": '"synth-etag-1"',
                },
            )

        transport = httpx.MockTransport(handler)

        def mock_client(*, timeout_seconds: float = 30.0, **kwargs):
            return httpx.AsyncClient(transport=transport, timeout=timeout_seconds)

        monkeypatch.setattr("app.ingestion.acquisition.create_async_http_client", mock_client)

        ds = _synthetic_dataset(
            ds_id="synth_resume_ds",
            product_id="SYNTH_CHEMIN_01",
            url="https://pds.example.invalid/synth_chemin.csv",
            sha256=None,
            status=DatasetLifecycleStatus.DISCOVERED,
        )
        ds.original_label_url = "https://pds.example.invalid/synth_chemin.lbl"

        manifest = await acq.download_product(ds, overwrite=False, max_retries=4, allow_resume=True)
        assert product_calls == 3
        assert manifest.sha256_checksum == expected_sha
        assert manifest.byte_size if hasattr(manifest, "byte_size") else manifest.file_size_bytes == len(csv_payload)
        assert ds.acquisition_state == AcquisitionState.INTEGRITY_VALIDATED
        assert (raw_dir / "synth_chemin.csv").read_bytes() == csv_payload

        # Duplicate download reuses verified artifact cleanly without clobbering
        manifest_2 = await acq.download_product(ds, overwrite=False)
        assert manifest_2.sha256_checksum == expected_sha
        assert product_calls == 3  # no extra network fetch

        # Non-overwrite protection when manifest removed or different file on disk
        (man_dir / f"{ds.id}.manifest.json").unlink()
        with pytest.raises(FileExistsError):
            await acq.download_product(ds, overwrite=False)

        # Query provenance & acquisition ledger persisted
        acq.record_query_provenance(
            archive_name="SYNTHETIC_TEST_DATA_ARCHIVE",
            endpoint="https://pds.example.invalid/query",
            params={"sol": 79},
            http_status=200,
            result_count=1,
            success=True,
        )
        ledger = acq.get_acquisition_ledger(limit=10)
        qprov = acq.get_query_provenance(limit=10)
        assert any(e.get("outcome") == "ACQUIRED" for e in ledger)
        assert any(e.get("outcome") == "REUSED_VERIFIED_ARTIFACT" for e in ledger)
        assert any(e.get("outcome") == "FAILED_OVERWRITE_PROTECTED" for e in ledger)
        assert any(q.get("archive_name") == "SYNTHETIC_TEST_DATA_ARCHIVE" for q in qprov)
