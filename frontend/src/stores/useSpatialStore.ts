import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import type {
  CacheInvalidationEvent,
  CoordinateTransformationResult,
  CrsValidationResult,
  MorphologicalFeatureCandidate,
  MorphologyDetectionResponse,
  MorphologyReviewRecord,
  MultiCategorySpatialCoverageReport,
  MultiResolutionPyramidPlan,
  MultiScaleTerrainComparisonResponse,
  NativeDemMetadataRecord,
  RoverOrbitalAssociationRecord,
  SpatialCacheStatus,
  SpatialFootprintRecord,
  SpatialGapRegion,
  SpatialRegistrationAssessment,
  TerrainChangeEvaluationResult,
  VerticalDatumComparisonResult,
  WindowedTerrainDerivativesReport,
} from "../types";

export interface StudyWindowBounds {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}

export type SpatialComparisonMode = "single" | "swipe" | "side_by_side" | "blend";

export type SelectedSpatialEntity =
  | { kind: "footprint"; data: SpatialFootprintRecord }
  | { kind: "gap"; data: SpatialGapRegion }
  | { kind: "morphology"; data: MorphologicalFeatureCandidate }
  | { kind: "rover_assoc"; data: RoverOrbitalAssociationRecord }
  | null;

export interface MeasurePoint {
  lat: number;
  lon_east: number;
  elevation_m: number | null;
  slope_deg: number | null;
  label?: string;
}

export interface SpatialCrsRegistryResponse {
  registry_version: string;
  supported_crs: Record<string, Record<string, unknown>>;
  vertical_datum_kinds: string[];
}

export interface ReviewSubmitInput {
  candidate_id: string;
  dataset_id: string;
  action: "accept" | "reject" | "annotate";
  reviewer_id: string;
  annotation_note?: string;
  assigned_feature_class?: string | null;
  operator_token?: string;
}

interface SpatialState {
  // Default Gale Crater boxwork study window inside valid HiRISE 009149 swath
  studyBounds: StudyWindowBounds;
  primaryDatasetId: string;
  secondaryDatasetId: string;

  // Map/3D overlay & comparison controls
  comparisonMode: SpatialComparisonMode;
  swipeFraction: number;
  blendOpacity: number;
  showFootprintsOverlay: boolean;
  showGapsOverlay: boolean;
  showMorphologyOverlay: boolean;
  showRoverAssocOverlay: boolean;
  measurePoints: MeasurePoint[];
  selectedEntity: SelectedSpatialEntity;

  // Data payloads
  crsRegistry: SpatialCrsRegistryResponse | null;
  crsValidation: CrsValidationResult | null;
  verticalDatumComparison: VerticalDatumComparisonResult | null;
  coordinateTransform: CoordinateTransformationResult | null;

  footprints: SpatialFootprintRecord[];
  intersectingFootprints: SpatialFootprintRecord[];
  registrationAssessments: SpatialRegistrationAssessment[];
  activeRegistration: SpatialRegistrationAssessment | null;
  coverageReport: MultiCategorySpatialCoverageReport | null;

  demMetadata: NativeDemMetadataRecord | null;
  terrainDerivatives: WindowedTerrainDerivativesReport | null;
  scaleComparison: MultiScaleTerrainComparisonResponse | null;
  changeEvaluation: TerrainChangeEvaluationResult | null;

  morphologyReport: MorphologyDetectionResponse | null;
  morphologyReviews: Record<string, MorphologyReviewRecord>;
  roverAssociations: RoverOrbitalAssociationRecord[];
  pyramidPlan: MultiResolutionPyramidPlan | null;
  cacheStatus: SpatialCacheStatus | null;

  // Loading & error tracking
  loadingFootprints: boolean;
  loadingRegistration: boolean;
  loadingCoverage: boolean;
  loadingTerrain: boolean;
  loadingMorphology: boolean;
  loadingRoverAssoc: boolean;
  loadingPyramid: boolean;
  submittingReview: boolean;
  error: string | null;
  statusBanner: string | null;

  // Mutations & UI actions
  setStudyBounds: (bounds: StudyWindowBounds) => void;
  setPrimaryDatasetId: (datasetId: string) => void;
  setSecondaryDatasetId: (datasetId: string) => void;
  setComparisonMode: (mode: SpatialComparisonMode) => void;
  setSwipeFraction: (val: number) => void;
  setBlendOpacity: (val: number) => void;
  setOverlayFlag: (
    key:
      | "showFootprintsOverlay"
      | "showGapsOverlay"
      | "showMorphologyOverlay"
      | "showRoverAssocOverlay"
      | "showLandingSiteOverlay"
      | "showCrewOverlay"
      | "showFieldObservationsOverlay",
    value: boolean
  ) => void;
  focusCoordinate: { lat: number; lon: number; heightM?: number; label?: string } | null;
  setFocusCoordinate: (coord: { lat: number; lon: number; heightM?: number; label?: string } | null) => void;
  showLandingSiteOverlay: boolean;
  showCrewOverlay: boolean;
  showFieldObservationsOverlay: boolean;
  addMeasurePoint: (pt: MeasurePoint) => void;
  clearMeasurePoints: () => void;
  setSelectedEntity: (entity: SelectedSpatialEntity) => void;
  clearMessages: () => void;

  // Async API actions (abort-guarded where appropriate)
  fetchCrsRegistry: () => Promise<void>;
  validateCrs: (req: {
    crs_string?: string | null;
    latitude_convention?: string | null;
    longitude_direction?: string | null;
    vertical_reference?: string | null;
    require_conventions?: boolean;
    require_vertical_datum?: boolean;
  }) => Promise<CrsValidationResult | null>;
  compareVerticalDatums: (
    datumA: string,
    datumB: string,
    validatedOffsetM?: number | null
  ) => Promise<VerticalDatumComparisonResult | null>;
  transformCoordinates: (req: {
    x_or_lon: number;
    y_or_lat: number;
    source_crs: string;
    target_crs: string;
    source_lat_convention?: string;
    target_lat_convention?: string;
    source_lon_direction?: string;
    target_lon_domain?: string;
    source_vertical_datum?: string | null;
    target_vertical_datum?: string | null;
  }) => Promise<CoordinateTransformationResult | null>;

  fetchFootprints: (category?: string) => Promise<void>;
  fetchIntersectingFootprints: (bounds?: StudyWindowBounds) => Promise<void>;

  evaluateRegistration: (req: {
    dataset_a_id: string;
    dataset_b_id: string;
    intended_analysis?: string;
    attempt_image_matching?: boolean;
  }) => Promise<SpatialRegistrationAssessment | null>;
  fetchRegistrationAssessments: () => Promise<void>;

  evaluateCoverage: (
    bounds?: StudyWindowBounds,
    referenceDatasetId?: string | null,
    intendedResolutionThresholdM?: number,
    questionFocus?: string | null
  ) => Promise<MultiCategorySpatialCoverageReport | null>;

  fetchDemMetadata: (datasetId?: string) => Promise<NativeDemMetadataRecord | null>;
  fetchTerrainDerivatives: (
    datasetId?: string,
    bounds?: StudyWindowBounds,
    maxGridDim?: number
  ) => Promise<WindowedTerrainDerivativesReport | null>;
  compareTerrainScales: (
    datasetIds: string[],
    bounds?: StudyWindowBounds
  ) => Promise<MultiScaleTerrainComparisonResponse | null>;
  evaluateTerrainChange: (
    datasetAId: string,
    datasetBId: string,
    bounds?: StudyWindowBounds,
    validatedOffsetM?: number | null
  ) => Promise<TerrainChangeEvaluationResult | null>;

  detectMorphology: (
    datasetId?: string,
    bounds?: StudyWindowBounds,
    gridSize?: number
  ) => Promise<MorphologyDetectionResponse | null>;
  fetchMorphologyReviews: () => Promise<void>;
  submitMorphologyReview: (input: ReviewSubmitInput) => Promise<MorphologyReviewRecord | null>;

  fetchRoverAssociations: (
    orbitalDatasetId?: string,
    bounds?: StudyWindowBounds
  ) => Promise<RoverOrbitalAssociationRecord[]>;

  fetchPyramidPlan: (
    bounds?: StudyWindowBounds,
    viewportPx?: number,
    preferredDatasetId?: string | null
  ) => Promise<MultiResolutionPyramidPlan | null>;
  fetchCacheStatus: () => Promise<void>;
  invalidateCache: (
    datasetId?: string | null,
    reason?: string,
    operatorToken?: string
  ) => Promise<CacheInvalidationEvent | null>;
}

const controllers: Record<string, AbortController | undefined> = {};

function _nextSignal(key: string): AbortSignal {
  controllers[key]?.abort();
  const c = new AbortController();
  controllers[key] = c;
  return c.signal;
}

async function _parseError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body?.detail ?? body);
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
}

function _getOperatorToken(explicitToken?: string): string {
  if (explicitToken && explicitToken.trim()) return explicitToken.trim();
  if (typeof window !== "undefined") {
    return window.sessionStorage.getItem("marscope_operator_token") || "";
  }
  return "";
}

export const DEFAULT_GALE_STUDY_BOUNDS: StudyWindowBounds = {
  min_lat: -4.775,
  max_lat: -4.725,
  min_lon: 137.395,
  max_lon: 137.430,
};

export const useSpatialStore = create<SpatialState>((set, get) => ({
  studyBounds: DEFAULT_GALE_STUDY_BOUNDS,
  primaryDatasetId: "hirise_dteec_009149_1750",
  secondaryDatasetId: "hirise_psp_009149_1750_ortho",

  comparisonMode: "single",
  swipeFraction: 0.5,
  blendOpacity: 0.65,
  showFootprintsOverlay: true,
  showGapsOverlay: true,
  showMorphologyOverlay: false,
  showRoverAssocOverlay: false,
  showLandingSiteOverlay: true,
  showCrewOverlay: true,
  showFieldObservationsOverlay: true,
  focusCoordinate: null,
  setFocusCoordinate: (focusCoordinate) => set({ focusCoordinate }),
  measurePoints: [],
  selectedEntity: null,

  crsRegistry: null,
  crsValidation: null,
  verticalDatumComparison: null,
  coordinateTransform: null,

  footprints: [],
  intersectingFootprints: [],
  registrationAssessments: [],
  activeRegistration: null,
  coverageReport: null,

  demMetadata: null,
  terrainDerivatives: null,
  scaleComparison: null,
  changeEvaluation: null,

  morphologyReport: null,
  morphologyReviews: {},
  roverAssociations: [],
  pyramidPlan: null,
  cacheStatus: null,

  loadingFootprints: false,
  loadingRegistration: false,
  loadingCoverage: false,
  loadingTerrain: false,
  loadingMorphology: false,
  loadingRoverAssoc: false,
  loadingPyramid: false,
  submittingReview: false,
  error: null,
  statusBanner: null,

  setStudyBounds: (bounds) => set({ studyBounds: bounds }),
  setPrimaryDatasetId: (datasetId) => set({ primaryDatasetId: datasetId }),
  setSecondaryDatasetId: (datasetId) => set({ secondaryDatasetId: datasetId }),
  setComparisonMode: (mode) => set({ comparisonMode: mode }),
  setSwipeFraction: (val) => set({ swipeFraction: Math.max(0.05, Math.min(0.95, val)) }),
  setBlendOpacity: (val) => set({ blendOpacity: Math.max(0.0, Math.min(1.0, val)) }),
  setOverlayFlag: (key, value) => set({ [key]: value } as Partial<SpatialState>),
  addMeasurePoint: (pt) =>
    set((state) => {
      const next = state.measurePoints.length >= 2 ? [pt] : [...state.measurePoints, pt];
      return { measurePoints: next };
    }),
  clearMeasurePoints: () => set({ measurePoints: [] }),
  setSelectedEntity: (entity) => set({ selectedEntity: entity }),
  clearMessages: () => set({ error: null, statusBanner: null }),

  fetchCrsRegistry: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/crs/registry`, { cache: "no-store" });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to load CRS registry"));
      const data: SpatialCrsRegistryResponse = await res.json();
      set({ crsRegistry: data });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "CRS registry request failed" });
    }
  },

  validateCrs: async (req) => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/crs/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "CRS validation failed"));
      const data: CrsValidationResult = await res.json();
      set({ crsValidation: data });
      return data;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "CRS validation failed" });
      return null;
    }
  },

  compareVerticalDatums: async (datumA, datumB, validatedOffsetM) => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/crs/vertical-datum/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          datum_a: datumA,
          datum_b: datumB,
          validated_vertical_offset_m: validatedOffsetM ?? null,
        }),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Vertical datum comparison failed"));
      const data: VerticalDatumComparisonResult = await res.json();
      set({ verticalDatumComparison: data });
      return data;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Vertical datum comparison failed" });
      return null;
    }
  },

  transformCoordinates: async (req) => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/crs/transform`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Coordinate transformation failed"));
      const data: CoordinateTransformationResult = await res.json();
      set({ coordinateTransform: data });
      return data;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Coordinate transformation failed" });
      return null;
    }
  },

  fetchFootprints: async (category) => {
    const signal = _nextSignal("footprints_list");
    set({ loadingFootprints: true, error: null });
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (category) params.set("category", category);
      const res = await fetch(`${API_BASE_URL}/spatial/footprints?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to fetch spatial footprints"));
      const data = await res.json();
      set({ footprints: data.footprints ?? [], loadingFootprints: false });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      set({
        loadingFootprints: false,
        error: err instanceof Error ? err.message : "Failed to fetch footprints",
      });
    }
  },

  fetchIntersectingFootprints: async (bounds) => {
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("footprints_intersect");
    set({ loadingFootprints: true });
    try {
      const params = new URLSearchParams({
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
      });
      const res = await fetch(`${API_BASE_URL}/spatial/footprints/query/intersect?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to query intersecting footprints"));
      const data = await res.json();
      set({ intersectingFootprints: data.footprints ?? [], loadingFootprints: false });
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      set({
        loadingFootprints: false,
        error: err instanceof Error ? err.message : "Footprint query failed",
      });
    }
  },

  evaluateRegistration: async (req) => {
    const signal = _nextSignal("registration_eval");
    set({ loadingRegistration: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/registration/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Registration evaluation failed"));
      const data: SpatialRegistrationAssessment = await res.json();
      set((state) => ({
        activeRegistration: data,
        registrationAssessments: [
          data,
          ...state.registrationAssessments.filter(
            (r) => !(r.dataset_a_id === data.dataset_a_id && r.dataset_b_id === data.dataset_b_id && r.intended_analysis === data.intended_analysis)
          ),
        ].slice(0, 20),
        loadingRegistration: false,
      }));
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingRegistration: false,
        error: err instanceof Error ? err.message : "Registration evaluation failed",
      });
      return null;
    }
  },

  fetchRegistrationAssessments: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/registration/assessments`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const data: SpatialRegistrationAssessment[] = await res.json();
      set((state) => ({
        registrationAssessments: data,
        activeRegistration: state.activeRegistration ?? (data[0] ?? null),
      }));
    } catch {
      // Non-blocking background sync
    }
  },

  evaluateCoverage: async (bounds, referenceDatasetId, intendedResolutionThresholdM = 5.0, questionFocus) => {
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("coverage_eval");
    set({ loadingCoverage: true, error: null });
    try {
      const params = new URLSearchParams({
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
        intended_resolution_threshold_m: String(intendedResolutionThresholdM),
      });
      if (referenceDatasetId) params.set("reference_dataset_id", referenceDatasetId);
      if (questionFocus) params.set("question_focus", questionFocus);
      const res = await fetch(`${API_BASE_URL}/spatial/coverage/evaluate?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Coverage evaluation failed"));
      const data: MultiCategorySpatialCoverageReport = await res.json();
      set({ coverageReport: data, loadingCoverage: false });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingCoverage: false,
        error: err instanceof Error ? err.message : "Coverage evaluation failed",
      });
      return null;
    }
  },

  fetchDemMetadata: async (datasetId) => {
    const did = datasetId ?? get().primaryDatasetId;
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/terrain/${encodeURIComponent(did)}/metadata`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to load native DEM metadata"));
      const data: NativeDemMetadataRecord = await res.json();
      set({ demMetadata: data });
      return data;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "DEM metadata failed" });
      return null;
    }
  },

  fetchTerrainDerivatives: async (datasetId, bounds, maxGridDim = 128) => {
    const did = datasetId ?? get().primaryDatasetId;
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("terrain_derivatives");
    set({ loadingTerrain: true, error: null });
    try {
      const params = new URLSearchParams({
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
        max_grid_dim: String(maxGridDim),
      });
      const res = await fetch(
        `${API_BASE_URL}/spatial/terrain/${encodeURIComponent(did)}/derivatives?${params.toString()}`,
        { cache: "no-store", signal }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Terrain derivatives computation failed"));
      const data: WindowedTerrainDerivativesReport = await res.json();
      set({
        terrainDerivatives: data,
        demMetadata: data.dataset_metadata,
        loadingTerrain: false,
      });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingTerrain: false,
        error: err instanceof Error ? err.message : "Terrain derivatives failed",
      });
      return null;
    }
  },

  compareTerrainScales: async (datasetIds, bounds) => {
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("terrain_scales");
    set({ loadingTerrain: true, error: null });
    try {
      const params = new URLSearchParams({
        dataset_ids: datasetIds.join(","),
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
      });
      const res = await fetch(`${API_BASE_URL}/spatial/terrain/compare-scales?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Cross-scale comparison failed"));
      const data: MultiScaleTerrainComparisonResponse = await res.json();
      set({ scaleComparison: data, loadingTerrain: false });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingTerrain: false,
        error: err instanceof Error ? err.message : "Cross-scale comparison failed",
      });
      return null;
    }
  },

  evaluateTerrainChange: async (datasetAId, datasetBId, bounds, validatedOffsetM) => {
    const b = bounds ?? get().studyBounds;
    set({ loadingTerrain: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/terrain/compare-change`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_a_id: datasetAId,
          dataset_b_id: datasetBId,
          min_lat: b.min_lat,
          max_lat: b.max_lat,
          min_lon: b.min_lon,
          max_lon: b.max_lon,
          validated_vertical_offset_m: validatedOffsetM ?? null,
        }),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Terrain change evaluation failed"));
      const data: TerrainChangeEvaluationResult = await res.json();
      set({ changeEvaluation: data, loadingTerrain: false });
      return data;
    } catch (err) {
      set({
        loadingTerrain: false,
        error: err instanceof Error ? err.message : "Terrain change evaluation failed",
      });
      return null;
    }
  },

  detectMorphology: async (datasetId, bounds, gridSize = 96) => {
    const did = datasetId ?? get().primaryDatasetId;
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("morphology_detect");
    set({ loadingMorphology: true, error: null });
    try {
      const params = new URLSearchParams({
        dataset_id: did,
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
        grid_size: String(gridSize),
      });
      const res = await fetch(`${API_BASE_URL}/spatial/morphology/detect?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Morphology detection failed"));
      const data: MorphologyDetectionResponse = await res.json();
      set({ morphologyReport: data, loadingMorphology: false });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingMorphology: false,
        error: err instanceof Error ? err.message : "Morphology detection failed",
      });
      return null;
    }
  },

  fetchMorphologyReviews: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/morphology/reviews`, { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      set({ morphologyReviews: data.reviews ?? {} });
    } catch {
      // Ignore transient review read failure
    }
  },

  submitMorphologyReview: async (input) => {
    set({ submittingReview: true, error: null, statusBanner: null });
    try {
      const token = _getOperatorToken(input.operator_token);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["X-Mars-Operator-Token"] = token;
      const res = await fetch(`${API_BASE_URL}/spatial/morphology/review`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          candidate_id: input.candidate_id,
          dataset_id: input.dataset_id,
          action: input.action,
          reviewer_id: input.reviewer_id,
          annotation_note: input.annotation_note ?? null,
          assigned_feature_class: input.assigned_feature_class ?? null,
        }),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to submit human review"));
      const record: MorphologyReviewRecord = await res.json();
      set((state) => {
        const nextReviews = { ...state.morphologyReviews, [record.candidate_id]: record };
        const nextReport = state.morphologyReport
          ? {
              ...state.morphologyReport,
              persisted_review_count: Object.keys(nextReviews).length,
              candidates: state.morphologyReport.candidates.map((c) =>
                c.candidate_id === record.candidate_id
                  ? {
                      ...c,
                      epistemic_state: record.updated_epistemic_state,
                      review_status: record.action,
                      human_review: record,
                      feature_class: record.assigned_feature_class || c.feature_class,
                    }
                  : c
              ),
            }
          : null;
        return {
          submittingReview: false,
          morphologyReviews: nextReviews,
          morphologyReport: nextReport,
          statusBanner: `Saved USER_PROVIDED ${record.action} review for ${record.candidate_id}.`,
        };
      });
      return record;
    } catch (err) {
      set({
        submittingReview: false,
        error: err instanceof Error ? err.message : "Human review failed",
      });
      return null;
    }
  },

  fetchRoverAssociations: async (orbitalDatasetId, bounds) => {
    const oid = orbitalDatasetId ?? get().primaryDatasetId;
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("rover_assoc");
    set({ loadingRoverAssoc: true, error: null });
    try {
      const params = new URLSearchParams({
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
        orbital_dataset_id: oid,
        limit: "30",
      });
      const res = await fetch(`${API_BASE_URL}/spatial/rover/region-associations?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Rover association query failed"));
      const data: RoverOrbitalAssociationRecord[] = await res.json();
      set({ roverAssociations: data, loadingRoverAssoc: false });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return [];
      set({
        loadingRoverAssoc: false,
        error: err instanceof Error ? err.message : "Rover association query failed",
      });
      return [];
    }
  },

  fetchPyramidPlan: async (bounds, viewportPx = 512, preferredDatasetId) => {
    const b = bounds ?? get().studyBounds;
    const signal = _nextSignal("pyramid_plan");
    set({ loadingPyramid: true, error: null });
    try {
      const params = new URLSearchParams({
        min_lat: String(b.min_lat),
        max_lat: String(b.max_lat),
        min_lon: String(b.min_lon),
        max_lon: String(b.max_lon),
        viewport_px: String(viewportPx),
      });
      if (preferredDatasetId) params.set("preferred_dataset_id", preferredDatasetId);
      const res = await fetch(`${API_BASE_URL}/spatial/delivery/pyramid-plan?${params.toString()}`, {
        cache: "no-store",
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Delivery pyramid plan failed"));
      const data: MultiResolutionPyramidPlan = await res.json();
      set({ pyramidPlan: data, loadingPyramid: false });
      return data;
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return null;
      set({
        loadingPyramid: false,
        error: err instanceof Error ? err.message : "Pyramid plan failed",
      });
      return null;
    }
  },

  fetchCacheStatus: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/spatial/cache/status`, { cache: "no-store" });
      if (!res.ok) return;
      const data: SpatialCacheStatus = await res.json();
      set({ cacheStatus: data });
    } catch {
      // Non-blocking status check
    }
  },

  invalidateCache: async (datasetId, reason = "operator_requested_invalidation", operatorToken) => {
    set({ error: null, statusBanner: null });
    try {
      const token = _getOperatorToken(operatorToken);
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["X-Mars-Operator-Token"] = token;
      const res = await fetch(`${API_BASE_URL}/spatial/cache/invalidate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ dataset_id: datasetId ?? null, reason }),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Cache invalidation failed"));
      const ev: CacheInvalidationEvent = await res.json();
      await get().fetchCacheStatus();
      set({
        statusBanner: `Cache invalidated (${ev.scope}): cleared ${ev.cleared_entries} entries.`,
      });
      return ev;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Cache invalidation failed" });
      return null;
    }
  },
}));
