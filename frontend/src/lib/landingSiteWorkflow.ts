import type {
  LandingSiteBundle,
  LandingSiteCoverageDiscovery,
  LandingSitePerimeter,
  LandingSiteRecord,
} from "../types";

export type LandingSiteWorkflowState =
  | "GLOBAL_VIEW"
  | "COORDINATES_ENTERED"
  | "VALIDATING_COORDINATES"
  | "OUTSIDE_DATA_COVERAGE"
  | "DATASET_SELECTED"
  | "LOADING_LOCAL_TERRAIN"
  | "LOCAL_TERRAIN_READY"
  | "CONSTRAINTS_PENDING"
  | "EVALUATING_PERIMETER"
  | "EVALUATION_COMPLETE"
  | "EVALUATION_FAILED";

export interface CoordinateValidationResult {
  valid: boolean;
  latitude?: number;
  longitudeEast?: number;
  error?: string;
}

/**
 * Strictly validate Mars planetocentric latitude [-90..90] and east longitude [0..360].
 * Never silently modifies or wraps out-of-range coordinates.
 */
export function validateMarsCoordinateInputs(
  latStr: string,
  lonStr: string
): CoordinateValidationResult {
  const cleanLat = latStr.trim();
  const cleanLon = lonStr.trim();
  if (!cleanLat || !cleanLon) {
    return { valid: false, error: "Both latitude and east longitude are required." };
  }
  const lat = Number(cleanLat);
  const lon = Number(cleanLon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return { valid: false, error: "Latitude and east longitude must be finite numbers." };
  }
  if (lat < -90 || lat > 90) {
    return { valid: false, error: `Latitude ${lat} is outside valid Mars range [-90, +90].` };
  }
  if (lon < 0 || lon > 360) {
    return {
      valid: false,
      error: `East longitude ${lon} is outside valid IAU2000:49900 range [0, 360].`,
    };
  }
  return { valid: true, latitude: lat, longitudeEast: lon };
}

export interface WorkflowStateInputs {
  viewMode: "global" | "local";
  hasEnteredCoordinates: boolean;
  isValidating: boolean;
  isLoadingTerrain: boolean;
  terrainLoadError: string | null;
  terrainReady: boolean;
  isEvaluatingPerimeter: boolean;
  evaluationError: string | null;
  discovery: LandingSiteCoverageDiscovery | null;
  bundle: LandingSiteBundle | null;
  constraintsComplete: boolean;
}

export function deriveLandingSiteWorkflowState(input: WorkflowStateInputs): LandingSiteWorkflowState {
  if (input.isValidating) return "VALIDATING_COORDINATES";
  if (input.isEvaluatingPerimeter) return "EVALUATING_PERIMETER";
  if (input.evaluationError) return "EVALUATION_FAILED";

  const site: LandingSiteRecord | null | undefined = input.bundle?.landing_site;
  const perimeter: LandingSitePerimeter | null | undefined = input.bundle?.perimeter;

  const outsideCoverage =
    (input.discovery && !input.discovery.covered) ||
    (input.discovery &&
      input.discovery.covered &&
      input.discovery.selected_dataset &&
      !input.discovery.selected_dataset.local_slope_suitable &&
      input.viewMode === "global") ||
    (site?.dem_coverage_state === "OUTSIDE_EVALUATED_DEM_COVERAGE" && !input.discovery?.covered);

  if (outsideCoverage && !site?.terrain_dataset_id) {
    return "OUTSIDE_DATA_COVERAGE";
  }

  if (
    perimeter?.status === "EVALUATED_WITH_VALIDATED_DEM" &&
    site?.dem_coverage_state === "COVERED_DEM" &&
    Boolean(site.terrain_dataset_id) &&
    input.viewMode === "local"
  ) {
    return "EVALUATION_COMPLETE";
  }

  if (
    perimeter &&
    perimeter.status !== "EVALUATED_WITH_VALIDATED_DEM" &&
    input.viewMode === "local"
  ) {
    return "EVALUATION_FAILED";
  }

  if (input.viewMode === "local") {
    if (input.isLoadingTerrain) return "LOADING_LOCAL_TERRAIN";
    if (input.terrainLoadError) return "EVALUATION_FAILED";
    if (input.terrainReady) {
      return input.constraintsComplete ? "LOCAL_TERRAIN_READY" : "CONSTRAINTS_PENDING";
    }
    return "DATASET_SELECTED";
  }

  if (input.discovery?.covered && input.discovery.selected_dataset) {
    return "DATASET_SELECTED";
  }
  if (input.hasEnteredCoordinates) {
    return "COORDINATES_ENTERED";
  }
  return "GLOBAL_VIEW";
}

export function isSiteEligibleForLocalDemView(
  discovery: LandingSiteCoverageDiscovery | null,
  site: LandingSiteRecord | null | undefined
): boolean {
  if (discovery?.covered && discovery.selected_dataset) {
    return true;
  }
  if (site && site.dem_coverage_state === "COVERED_DEM" && Boolean(site.terrain_dataset_id)) {
    return true;
  }
  return false;
}
