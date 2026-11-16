import test from "node:test";
import assert from "node:assert/strict";

import {
  deriveLandingSiteWorkflowState,
  isSiteEligibleForLocalDemView,
  validateMarsCoordinateInputs,
} from "../landingSiteWorkflow.ts";

test("Landing-Site Coordinate Validation & Workflow State Machine", async (t) => {
  await t.test("validates valid Mars planetocentric coordinates without modifying precision", () => {
    const res = validateMarsCoordinateInputs("-4.730125", "137.41093");
    assert.equal(res.valid, true);
    assert.equal(res.latitude, -4.730125);
    assert.equal(res.longitudeEast, 137.41093);
  });

  await t.test("rejects out-of-range, negative longitude, empty, and non-numeric coordinates", () => {
    assert.equal(validateMarsCoordinateInputs("-91", "137").valid, false);
    assert.equal(validateMarsCoordinateInputs("90.1", "137").valid, false);
    assert.equal(validateMarsCoordinateInputs("-4.7", "-10").valid, false);
    assert.equal(validateMarsCoordinateInputs("-4.7", "365").valid, false);
    assert.equal(validateMarsCoordinateInputs("", "137").valid, false);
    assert.equal(validateMarsCoordinateInputs("abc", "137").valid, false);
  });

  await t.test("prevents contradictory workflow states and blocks local DEM outside coverage", () => {
    const outsideDiscovery = {
      latitude: 20,
      longitude_east: 45,
      crs: "IAU2000:49900",
      covered: false,
      selected_dataset: null,
      covering_datasets: [],
      elevation_m: null,
      sample_is_nodata: false,
      unavailable_reason: "Outside DEM",
    };

    assert.equal(isSiteEligibleForLocalDemView(outsideDiscovery, null), false);

    const state = deriveLandingSiteWorkflowState({
      viewMode: "global",
      hasEnteredCoordinates: true,
      isValidating: false,
      isLoadingTerrain: false,
      terrainLoadError: null,
      terrainReady: false,
      isEvaluatingPerimeter: false,
      evaluationError: null,
      discovery: outsideDiscovery,
      bundle: null,
      constraintsComplete: false,
    });
    assert.equal(state, "OUTSIDE_DATA_COVERAGE");
  });

  await t.test("transitions cleanly through DATASET_SELECTED -> CONSTRAINTS_PENDING -> EVALUATION_COMPLETE", () => {
    const coveredDiscovery = {
      latitude: -4.73,
      longitude_east: 137.41,
      crs: "IAU2000:49900",
      covered: true,
      selected_dataset: {
        dataset_id: "hirise_dteec_009149_1750",
        product_id: "DTEEC_009149_1750_009294_1750_U01.IMG",
        product_title: "HiRISE DTM",
        native_resolution_m: 1.01,
        crs: "IAU2000:49900",
        source_type: "CATALOG_DEM",
        local_slope_suitable: true,
        selection_reason: "Selected HiRISE",
      },
      covering_datasets: [],
      elevation_m: -4090,
      sample_is_nodata: false,
    };

    assert.equal(isSiteEligibleForLocalDemView(coveredDiscovery, null), true);

    const pendingState = deriveLandingSiteWorkflowState({
      viewMode: "local",
      hasEnteredCoordinates: true,
      isValidating: false,
      isLoadingTerrain: false,
      terrainLoadError: null,
      terrainReady: true,
      isEvaluatingPerimeter: false,
      evaluationError: null,
      discovery: coveredDiscovery,
      bundle: null,
      constraintsComplete: false,
    });
    assert.equal(pendingState, "CONSTRAINTS_PENDING");

    const completeState = deriveLandingSiteWorkflowState({
      viewMode: "local",
      hasEnteredCoordinates: true,
      isValidating: false,
      isLoadingTerrain: false,
      terrainLoadError: null,
      terrainReady: true,
      isEvaluatingPerimeter: false,
      evaluationError: null,
      discovery: coveredDiscovery,
      bundle: {
        mission_id: "m1",
        landing_site_status: "REGISTERED",
        landing_site: {
          landing_site_id: "ls1",
          mission_id: "m1",
          name: "Alpha",
          latitude: -4.73,
          longitude_east: 137.41,
          crs: "IAU2000:49900",
          latitude_convention: "planetocentric",
          longitude_direction: "east",
          source: "USER_PROVIDED",
          elevation_m: -4090,
          terrain_dataset_id: "hirise_dteec_009149_1750",
          dem_coverage_state: "COVERED_DEM",
          registration_state: "REGISTERED",
          updated_by: "a1",
          history: [],
          created_at_utc: "2026-01-01T00:00:00Z",
          updated_at_utc: "2026-01-01T00:00:00Z",
        },
        perimeter: {
          perimeter_id: "p1",
          mission_id: "m1",
          landing_site_id: "ls1",
          status: "EVALUATED_WITH_VALIDATED_DEM",
          classification_label: "CURRENTLY EVALUATED PLANNING BOUNDARY — NOT A CERTIFIED SAFETY LIMIT",
          algorithm_id: "dem_bfs_slope_roughness_boundary",
          algorithm_version: "1.0.0",
          terrain_dataset_id: "hirise_dteec_009149_1750",
          constraints_used: { max_slope_deg: 15, max_roughness_m: 1.5, max_radius_m: 100 },
          constraints_missing: [],
          limitations: [],
          provenance: {},
          operator_approved: false,
          created_at_utc: "2026-01-01T00:00:00Z",
        },
      },
      constraintsComplete: true,
    });
    assert.equal(completeState, "EVALUATION_COMPLETE");
  });
});
