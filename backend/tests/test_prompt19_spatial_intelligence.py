"""
Prompt 19 Adversarial & Real-Data Validation Test Suite.

Validates:
- Part 3 / 13.1: Planetary CRS registry, 8-state validation, Planetocentric/Planetographic conversion,
  vertical datum compatibility, and auditable coordinate transformations.
- Part 4 / 13.2: 12-step multi-mission spatial registration, modality guard against raw DEM-vs-optical
  pixel correlation, control-point residual/outlier handling, and correlated uncertainty guard.
- Part 5 / 13.3: True rotated valid-pixel swath footprints vs rectangular bounding boxes, oblique swath
  corner rejection, Mars LAEA equal-area calculation, and 6-category × 5-stage spatial coverage & gaps.
- Part 6 / 13.4: Native-resolution 13-field terrain derivatives, NoData border propagation, multi-scale
  smoothing attenuation, and 6-gate temporal terrain change evaluation (CHANGE_NOT_EVALUABLE).
- Part 7 / 13.5: Resolution-gated geological morphology detection, 2-px NoData border artifact rejection,
  epistemic separation, and atomic USER_PROVIDED human review persistence with fail-closed auth.
- Part 8 / 11: 9-input deterministic cache key invalidation, multi-resolution pyramid planning, and
  FastAPI /api/spatial/* contract & security guards.
- Part 10 / 12: Scale-aware rover-to-orbital association (confirms_entire_orbital_pixel=False) and
  cross-engine integration across target evaluation, routing DEM selection, and evidence reports.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape
from shapely.validation import make_valid

from app.geospatial.coverage import compute_multi_category_spatial_coverage
from app.geospatial.crs import (
    MARS_CRS_REGISTRY,
    check_vertical_datum_compatibility,
    convert_latitude_convention,
    transform_mars_coordinates,
    validate_mars_crs_detailed,
)
from app.geospatial.footprints import (
    FootprintExtractionMethod,
    compute_mars_geometry_area_m2,
    extract_dataset_footprint,
    point_intersects_footprint,
)
from app.geospatial.models import (
    CoordinateValidationState,
    MorphologyEpistemicState,
    MorphologyFeatureClass,
    SpatialRegistrationAssessmentState,
    VerticalDatumKind,
)
from app.geospatial.registration import evaluate_product_pair_registration
from app.geospatial.spatial_delivery import compute_spatial_cache_digest
from app.main import app
from app.science.investigation.eligibility import evaluate_dataset_eligibility
from app.science.investigation.target_evaluation import _evaluate_single_location
from app.science.rover_association import (
    RoverAssociationState,
    evaluate_rover_orbital_association,
)
from app.services.container import (
    DATASETS_DIR,
    RAW_DIR,
    catalog_service,
    composition_index,
    footprint_index_service,
    routing_service,
    science_investigation_service,
)
from app.terrain.morphology import GeologicalMorphologyService
from app.terrain.spatial_terrain import (
    compare_terrain_scales,
    compute_terrain_derivatives_window,
    evaluate_terrain_change,
    inspect_dem_native_metadata,
)


@pytest.mark.unit
class TestPlanetaryCrsIntelligence:
    def test_known_mars_crs_and_earth_or_non_mars_rejection(self) -> None:
        assert "IAU2000:49900" in MARS_CRS_REGISTRY
        assert "MARS:IAU2015_49900" in MARS_CRS_REGISTRY
        valid_res = validate_mars_crs_detailed(
            "IAU2000:49900",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            vertical_reference=VerticalDatumKind.AREOID_RELATIVE_ELEVATION.value,
            require_conventions=True,
            require_vertical_datum=True,
        )
        assert valid_res.valid is True
        assert valid_res.validation_state in {
            CoordinateValidationState.CRS_VALIDATED,
            CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS,
        }

        earth_res = validate_mars_crs_detailed("EPSG:4326")
        assert earth_res.valid is False
        assert earth_res.validation_state == CoordinateValidationState.CRS_INCOMPATIBLE
        assert any("non-Martian" in b or "EPSG:4326" in b for b in earth_res.blockers)

        moon_res = validate_mars_crs_detailed("IAU_2015:30100")
        assert moon_res.valid is False
        assert moon_res.validation_state in {
            CoordinateValidationState.CRS_INCOMPATIBLE,
            CoordinateValidationState.CRS_UNSUPPORTED,
        }

        missing_res = validate_mars_crs_detailed(None)
        assert missing_res.valid is False
        assert missing_res.validation_state == CoordinateValidationState.CRS_UNVERIFIED

    def test_planetocentric_planetographic_conversion_and_mismatch(self) -> None:
        lat_c = -45.0
        lat_g = convert_latitude_convention(
            lat_c,
            from_convention="Planetocentric",
            to_convention="Planetographic",
            semi_major_m=3396190.0,
            semi_minor_m=3376200.0,
        )
        # On oblate Mars (b < a), |planetographic| > |planetocentric| at mid-latitudes
        assert abs(lat_g) > abs(lat_c)
        roundtrip = convert_latitude_convention(
            lat_g,
            from_convention="Planetographic",
            to_convention="Planetocentric",
            semi_major_m=3396190.0,
            semi_minor_m=3376200.0,
        )
        assert math.isclose(lat_c, roundtrip, abs_tol=1e-7)

        # Requesting Planetographic on IAU2000:49900 records explicit limitations
        mismatch = validate_mars_crs_detailed(
            "IAU2000:49900",
            latitude_convention="Planetographic",
            longitude_direction="East",
        )
        assert mismatch.validation_state == CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS
        assert any("Planetographic" in l for l in mismatch.limitations)

        unverified_conv = validate_mars_crs_detailed(
            "+proj=eqc +R=3396190 +no_defs",
            latitude_convention=None,
            longitude_direction=None,
            require_conventions=True,
        )
        assert unverified_conv.validation_state == CoordinateValidationState.COORDINATE_CONVENTION_UNVERIFIED

    def test_vertical_datum_compatibility_and_optical_reflectance_guard(self) -> None:
        same = check_vertical_datum_compatibility(
            VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
            VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
        )
        assert same.compatible is True
        assert same.is_absolute_elevation_a is True

        areoid_vs_ellip = check_vertical_datum_compatibility(
            VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
            VerticalDatumKind.ELLIPSOID_RELATIVE_ELEVATION,
        )
        assert areoid_vs_ellip.compatible is False
        assert areoid_vs_ellip.validation_state == CoordinateValidationState.CRS_INCOMPATIBLE
        assert areoid_vs_ellip.requires_validated_transformation is True

        with_offset = check_vertical_datum_compatibility(
            VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
            VerticalDatumKind.ELLIPSOID_RELATIVE_ELEVATION,
            validated_vertical_offset_m=-2950.0,
        )
        assert with_offset.compatible is True

        unknown_vert = check_vertical_datum_compatibility(
            VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
            VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE,
        )
        assert unknown_vert.compatible is False
        assert unknown_vert.is_absolute_elevation_b is False

    def test_coordinate_transformation_provenance_and_invalid_bounds(self) -> None:
        tx = transform_mars_coordinates(
            x_or_lon=222.58,
            y_or_lat=-4.66,
            source_crs="IAU2000:49900",
            target_crs="MARS:IAU2015_49900",
            source_lat_convention="Planetocentric",
            target_lat_convention="Planetographic",
            source_lon_direction="West",
            target_lon_domain="[-180, 180]",
        )
        assert tx.success is True
        assert tx.output_coordinates is not None
        # 222.58W -> 137.42E -> +137.42 in [-180, 180]
        assert math.isclose(tx.output_coordinates["lon_deg"], 137.42, abs_tol=1e-4)
        assert len(tx.provenance_steps) >= 3

        bad_lat = transform_mars_coordinates(
            x_or_lon=137.4,
            y_or_lat=-95.0,
            source_crs="IAU2000:49900",
            target_crs="IAU2000:49900",
        )
        assert bad_lat.success is False
        assert bad_lat.validation_state == CoordinateValidationState.TRANSFORMATION_FAILED

        earth_tx = transform_mars_coordinates(
            x_or_lon=137.4,
            y_or_lat=-4.66,
            source_crs="EPSG:4326",
            target_crs="IAU2000:49900",
        )
        assert earth_tx.success is False
        assert earth_tx.validation_state == CoordinateValidationState.CRS_INCOMPATIBLE


@pytest.mark.local_real_data
class TestSpatialFootprintsAndCoverage:
    def test_real_hirise_valid_pixel_swath_vs_oblique_bbox_corner(self) -> None:
        fp = footprint_index_service.get_footprint("hirise_dteec_009149_1750")
        assert fp is not None
        assert fp.extraction_method == FootprintExtractionMethod.AUTHORITATIVE_RASTER_VALID_MASK_HULL
        assert fp.is_approximate is False
        assert fp.valid_data_fraction is not None
        assert 0.55 < fp.valid_data_fraction < 0.85
        assert fp.swath_to_bbox_ratio is not None
        assert fp.swath_to_bbox_ratio < 0.85

        # Center of valid HiRISE 009149 swath (-4.800, 137.410) is inside both bbox and valid swath
        in_val, reason_val = point_intersects_footprint(
            fp, -4.800, 137.410, require_valid_pixels_if_known=True
        )
        assert in_val is True
        assert reason_val == "inside_valid_data_polygon"

        # Bottom-right corner of bounding box (-4.915, 137.460) is inside outer bbox but in oblique NoData triangle
        in_bbox, _ = point_intersects_footprint(
            fp, -4.915, 137.460, require_valid_pixels_if_known=False
        )
        in_swath, reason_corner = point_intersects_footprint(
            fp, -4.915, 137.460, require_valid_pixels_if_known=True
        )
        assert in_bbox is True
        assert in_swath is False
        assert reason_corner == "bbox_only_outside_valid_swath_pixels"

    def test_self_intersecting_geometry_repair_and_approximate_bbox_suppression(self) -> None:
        bowtie = shape(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [137.40, -4.68],
                        [137.44, -4.64],
                        [137.44, -4.68],
                        [137.40, -4.64],
                        [137.40, -4.68],
                    ]
                ],
            }
        )
        assert bowtie.is_valid is False
        repaired = make_valid(bowtie)
        assert repaired.is_valid is True
        area_m2 = compute_mars_geometry_area_m2(repaired)
        assert area_m2 > 0.0

        # Catalog-only product without local raster must report approximate bbox and withhold valid_data_fraction
        ctx_ds = catalog_service.get_dataset("mars_trek_gale_ctx")
        assert ctx_ds is not None
        ctx_fp = extract_dataset_footprint(ctx_ds, dataset_root_dir=DATASETS_DIR)
        assert ctx_fp.is_approximate is True
        assert ctx_fp.valid_data_fraction is None

    def test_six_category_spatial_coverage_and_explicit_evidence_gaps(self) -> None:
        report = compute_multi_category_spatial_coverage(
            catalog_service=catalog_service,
            footprint_index=footprint_index_service,
            dataset_root_dir=DATASETS_DIR,
            min_lat=-4.80,
            max_lat=-4.70,
            min_lon=137.38,
            max_lon=137.44,
            composition_index=composition_index,
            reference_dataset_id="hirise_dteec_009149_1750",
            intended_resolution_threshold_m=5.0,
        )
        assert set(report.categories.keys()) == {
            "elevation",
            "optical",
            "spectral",
            "thermal",
            "rover",
            "environmental",
        }
        dem_cat = report.categories["elevation"]
        assert dem_cat.valid_pixel_fraction is not None
        assert 0.50 < dem_cat.valid_pixel_fraction <= 1.0

        # Rover category has only approximate catalog bbox + point records -> exact footprint % withheld
        rover_cat = report.categories["rover"]
        assert rover_cat.only_approximate_footprints is True
        assert rover_cat.product_footprint_fraction is None
        assert rover_cat.rover_point_observation_count > 0

        assert len(report.evidence_gaps) >= 2
        for gap in report.evidence_gaps:
            assert gap.never_implies_feature_absence is True


@pytest.mark.local_real_data
class TestMultiMissionSpatialRegistration:
    def test_real_hirise_dem_ortho_pair_registration_and_modality_guard(self) -> None:
        ds_a = catalog_service.get_dataset("hirise_dteec_009149_1750")
        ds_b = catalog_service.get_dataset("hirise_psp_009149_1750_ortho")
        assert ds_a is not None and ds_b is not None

        reg = evaluate_product_pair_registration(
            ds_a,
            ds_b,
            dataset_root_dir=DATASETS_DIR,
            intended_analysis="spatial_overlay",
            attempt_image_matching=True,
        )
        assert reg.overall_state == SpatialRegistrationAssessmentState.VALIDATED_WITH_LIMITATIONS
        assert reg.suitable_for_intended_analysis is True
        assert reg.crs_compatible is True
        assert len(reg.workflow_steps) == 12
        # Same stereo bundle shares tie points -> independence assumption is False
        assert reg.uncertainty_breakdown.independence_assumption_valid is False
        assert reg.uncertainty_breakdown.total_uncertainty_computable is False
        assert reg.uncertainty_breakdown.pixel_quantization_half_px_a_m is not None
        # Attempting raw NCC between elevation (m) and reflectance (DN) must be rejected
        ncc_methods = [m for m in reg.registration_methods_attempted if m.method_name == "feature_based_image_registration"]
        assert len(ncc_methods) == 1
        assert ncc_methods[0].validation_result == "skipped_incompatible_physics"

    def test_partial_overlap_and_control_point_outliers(self) -> None:
        ds_a = catalog_service.get_dataset("hirise_dteec_009149_1750")
        ds_b = catalog_service.get_dataset("hirise_dteec_040770_1755")
        assert ds_a is not None and ds_b is not None

        partial = evaluate_product_pair_registration(
            ds_a,
            ds_b,
            dataset_root_dir=DATASETS_DIR,
            intended_analysis="spatial_overlay",
        )
        assert partial.overall_state in {
            SpatialRegistrationAssessmentState.PARTIAL_OVERLAP,
            SpatialRegistrationAssessmentState.VALIDATED_WITH_LIMITATIONS,
        }
        assert partial.overlap_area_m2 is not None and partial.overlap_area_m2 > 0

        # Control points with gross outlier on overlapping pair
        ds_ortho = catalog_service.get_dataset("hirise_psp_009149_1750_ortho")
        assert ds_ortho is not None
        cps = [
            {"x_a": 137.410, "y_a": -4.770, "x_b": 137.410, "y_b": -4.770},
            {"x_a": 137.430, "y_a": -4.770, "x_b": 137.430, "y_b": -4.770},
            {"x_a": 137.420, "y_a": -4.750, "x_b": 137.420, "y_b": -4.750},
            {"x_a": 137.415, "y_a": -4.760, "x_b": 137.415, "y_b": -4.760},
            {"x_a": 137.425, "y_a": -4.760, "x_b": 138.900, "y_b": -2.100},  # Outlier
        ]
        cp_reg = evaluate_product_pair_registration(
            ds_a,
            ds_ortho,
            dataset_root_dir=DATASETS_DIR,
            control_points=cps,
        )
        cp_methods = [m for m in cp_reg.registration_methods_attempted if m.method_name == "control_point_registration"]
        assert len(cp_methods) == 1
        assert cp_methods[0].rejected_correspondences >= 1


@pytest.mark.local_real_data
class TestMultiResolutionTerrainAndChangeGating:
    def test_real_hirise_derivatives_provenance_and_scale_comparison(self) -> None:
        hirise = catalog_service.get_dataset("hirise_dteec_009149_1750")
        mola = catalog_service.get_dataset("mola_megt00n090hb")
        assert hirise is not None and mola is not None

        meta = inspect_dem_native_metadata(hirise, raw_dir=RAW_DIR)
        assert meta.native_pixel_spacing_m is not None
        assert 0.9 < meta.native_pixel_spacing_m < 1.2
        assert meta.vertical_datum == VerticalDatumKind.AREOID_RELATIVE_ELEVATION

        derivs = compute_terrain_derivatives_window(
            hirise,
            raw_dir=RAW_DIR,
            min_lat=-4.80,
            max_lat=-4.76,
            min_lon=137.39,
            max_lon=137.43,
            max_grid_dim=96,
        )
        assert len(derivs.derivatives) == 13
        assert derivs.valid_pixel_count > 1000
        assert derivs.derivatives["slope"].stats["mean"] is not None
        assert derivs.derivatives["slope"].stats["mean"] > 2.0

        # Compare HiRISE (1m) vs MOLA (463m) over the same Gale Crater boxwork window
        comp = compare_terrain_scales(
            datasets=[hirise, mola],
            raw_dir=RAW_DIR,
            min_lat=-4.80,
            max_lat=-4.76,
            min_lon=137.39,
            max_lon=137.43,
        )
        assert comp.never_interprets_scale_diff_as_temporal_change is True
        assert len(comp.compared_datasets) == 2

        # Temporal change evaluation across 463x resolution jump must be blocked
        change_cross_res = evaluate_terrain_change(
            hirise,
            mola,
            dataset_root_dir=DATASETS_DIR,
            raw_dir=RAW_DIR,
            min_lat=-4.80,
            max_lat=-4.76,
            min_lon=137.39,
            max_lon=137.43,
        )
        assert change_cross_res.status == "CHANGE_NOT_EVALUABLE"
        assert change_cross_res.evaluable is False

        # Same-dataset / same-epoch temporal change must also be blocked
        change_same_epoch = evaluate_terrain_change(
            hirise,
            hirise,
            dataset_root_dir=DATASETS_DIR,
            raw_dir=RAW_DIR,
            min_lat=-4.80,
            max_lat=-4.76,
            min_lon=137.39,
            max_lon=137.43,
        )
        assert change_same_epoch.status == "CHANGE_NOT_EVALUABLE"
        assert change_same_epoch.evaluable is False


@pytest.mark.local_real_data
class TestGeologicalMorphologyAndHumanReview:
    def test_nodata_border_guard_and_resolution_gating_and_user_provided_review(
        self, tmp_path: Path
    ) -> None:
        # 1. Synthetic DEM array with sharp NoData cliff at column 15 + genuine interior ridge at column 36
        arr = np.full((64, 64), -1000.0, dtype=np.float32)
        arr[:, :15] = np.nan  # NoData region
        arr[:, 15] = -850.0  # Artificial 150m cliff directly bordering NoData
        for r in range(16, 48):
            arr[r, 35:38] = -982.0  # Genuine interior ridge far from NoData border

        svc = GeologicalMorphologyService(
            catalog_service=catalog_service,
            raw_dir=RAW_DIR,
            processed_dir=tmp_path,
        )
        resp = svc.detect_candidates_from_arrays(
            dataset_id="test_border_dem",
            product_id="TEST_BORDER_DEM",
            dem_array=arr,
            dem_resolution_m=1.0,
            bounds={"min_lat": -4.80, "max_lat": -4.76, "min_lon": 137.39, "max_lon": 137.43},
        )
        assert len(resp.rejected_nodata_border_candidates) >= 1
        assert all(c.nodata_border_rejected is True for c in resp.rejected_nodata_border_candidates)
        assert len(resp.candidates) >= 1
        assert all(
            c.epistemic_state
            in {
                MorphologyEpistemicState.ALGORITHMIC_CANDIDATE,
                MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
            }
            for c in resp.candidates
        )

        # Boulder detection must be blocked at 1.0 m/px (requires <= 0.35 m/px)
        boulder_gate = next(
            g for g in resp.resolution_gating if g.feature_class == MorphologyFeatureClass.BOULDER
        )
        assert boulder_gate.detectable is False

        # 2. Atomic USER_PROVIDED human review persistence
        cand_id = resp.candidates[0].candidate_id
        rec = svc.submit_human_review(
            candidate_id=cand_id,
            dataset_id="hirise_dteec_009149_1750",
            action="accept",
            reviewer_id="planetary_geologist_1",
            annotation_note="Validated linear ridge candidate; not a mineral confirmation.",
            assigned_feature_class=MorphologyFeatureClass.LINEAR_RIDGE,
        )
        assert rec.classification == "USER_PROVIDED"
        assert rec.updated_epistemic_state == MorphologyEpistemicState.EXPERT_INTERPRETATION


@pytest.mark.local_real_data
class TestScaleAwareRoverAssociationAndCrossEngineIntegration:
    def test_rover_scale_disparity_and_location_semantics(self) -> None:
        obs = {
            "evidence_id": "apxs_test_spot_01",
            "mission": "MSL",
            "instrument": "APXS",
            "product_id": "APXS_GALE_01",
            "latitude": -4.750,
            "longitude_east": 137.410,
            "location_semantic_type": "instrument_target_location",
            "coordinate_source": "PDS_TARGET_TABLE",
            "coordinate_uncertainty_m": 2.5,
            "sol": 1200,
            "measurement_category": "element_oxide_wt_pct",
        }
        assoc = evaluate_rover_orbital_association(
            observation=obs,
            feature_lat=-4.750,
            feature_lon_east=137.410,
            orbital_dataset_id="hirise_dteec_009149_1750",
            orbital_product_id="DTEEC_009149_1750_009294_1750_A01",
            orbital_pixel_footprint_m=1.01,
        )
        assert assoc.association_state in {
            RoverAssociationState.DIRECT_SPATIAL_ASSOCIATION,
            RoverAssociationState.ASSOCIATED_WITH_UNCERTAINTY,
        }
        # Sub-2cm APXS spot (~0.017m) vs 1.01m HiRISE pixel (~59.4x disparity) -> NEVER confirms entire orbital pixel
        assert assoc.confirms_entire_orbital_pixel is False
        assert assoc.scale_disparity_ratio is not None
        assert assoc.scale_disparity_ratio > 20.0

    def test_oblique_swath_corner_excluded_in_eligibility_target_eval_and_routing(self) -> None:
        hirise = catalog_service.get_dataset("hirise_dteec_009149_1750")
        assert hirise is not None
        question = science_investigation_service.get_question("gale_boxwork_origin")
        assert question is not None

        elig_res = evaluate_dataset_eligibility(
            ds=hirise,
            inst_cls="HiRISE",
            question=question,
            is_gale=True,
            seen_sha256=set(),
            seen_product_ids=set(),
        )
        assert elig_res["eligibility_state"].value in {
            "ELIGIBLE_WITH_LIMITATIONS",
            "ELIGIBLE_FOR_SCIENTIFIC_TARGET_EVALUATION",
        }
        assert any("Oblique stereo swath" in note for note in elig_res["uncertainty_summary"]["notes"])

        # Target evaluation at oblique corner (-4.680, 137.390) must NOT claim HiRISE 009149 DEM/Ortho support
        eval_res = _evaluate_single_location(
            target_id="oblique_corner_target",
            name="Oblique Swath Corner Test Target",
            latitude=-4.680,
            longitude_east=137.390,
            elevation_m=None,
            crs="IAU2000:49900",
            matched_species=None,
            initial_evidence_state=None,
            initial_instruments=[],
            initial_evidence_ids=[],
            geology_type="ridge",
            question=question,
            catalog_service=catalog_service,
            composition_index=composition_index,
            recorded_observations=[],
            astronaut_lat=None,
            astronaut_lon=None,
            search_radius_m=30.0,
        )
        assert "hirise_dteec_009149_1750" not in eval_res.covering_datasets
        assert "hirise_psp_009149_1750_ortho" not in eval_res.covering_datasets
        assert any("outside valid swath pixels" in g for g in eval_res.unknowns_and_gaps)

        # Routing DEM selector must NOT select hirise_dteec_009149_1750 for oblique NoData corner points
        selected_dem = routing_service._select_dem_for_points(
            None,
            [(-4.915, 137.460), (-4.914, 137.461)],
        )
        assert selected_dem.id == "mola_megt00n090hb"


@pytest.mark.local_real_data
class TestScalableDeliveryCacheAndSpatialApi:
    def test_nine_input_cache_digest_and_api_contracts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        d1 = compute_spatial_cache_digest(
            dataset_id="hirise_dteec_009149_1750",
            source_sha256="abc123",
            algorithm="mesh_tile_dem",
            algorithm_version="2.0.0-p19",
            parameters={"lod": 1},
            crs="IAU2000:49900",
            resolution_m=1.01,
            bounds={"min_lat": -4.80, "max_lat": -4.76, "min_lon": 137.39, "max_lon": 137.43},
            metadata_hash="meta1",
        )
        d2 = compute_spatial_cache_digest(
            dataset_id="hirise_dteec_009149_1750",
            source_sha256="changed_sha256",
            algorithm="mesh_tile_dem",
            algorithm_version="2.0.0-p19",
            parameters={"lod": 1},
            crs="IAU2000:49900",
            resolution_m=1.01,
            bounds={"min_lat": -4.80, "max_lat": -4.76, "min_lon": 137.39, "max_lon": 137.43},
            metadata_hash="meta1",
        )
        assert d1 != d2

        client = TestClient(app)
        # CRS Registry & Footprints
        assert client.get("/api/spatial/crs/registry").status_code == 200
        assert client.get("/api/spatial/footprints").status_code == 200
        assert client.get("/api/spatial/footprints/bad..id").status_code == 422

        # Pyramid plan prevents coarse DEM upsampling into pseudo-1m
        plan_res = client.get(
            "/api/spatial/delivery/pyramid-plan?min_lat=-4.80&max_lat=-4.76&min_lon=137.39&max_lon=137.43&viewport_px=512&preferred_dataset_id=mola_megt00n090hb"
        )
        assert plan_res.status_code == 200
        plan = plan_res.json()
        assert plan["upsampling_prevented"] is True
        assert any("upsampling" in c.lower() for c in plan["delivery_constraints"])

        # Fail-closed auth guard on cache invalidation & morphology review
        monkeypatch.delenv("MARSCOPE_OPERATOR_TOKEN", raising=False)
        unauth = client.post("/api/spatial/cache/invalidate", json={"reason": "test"})
        assert unauth.status_code == 403

        monkeypatch.setenv("MARSCOPE_OPERATOR_TOKEN", "p19_secret_token")
        auth_ok = client.post(
            "/api/spatial/cache/invalidate",
            json={"dataset_id": "hirise_dteec_009149_1750", "reason": "test_invalidation"},
            headers={"X-Mars-Operator-Token": "p19_secret_token"},
        )
        assert auth_ok.status_code == 200
        assert auth_ok.json()["scope"] == "dataset"
