"use client";

import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import type {
  ComplementarityAssessmentReport,
  CorridorAssessment,
  CorridorUncertaintyProfile,
  MissionDossierResponse,
  RouteEvidenceComparisonResponse,
} from "../types";

export interface EvidenceOverlayToggles {
  showCorridor: boolean;
  showSegments: boolean;
  showGaps: boolean;
  showTerrainCandidates: boolean;
  showOpticalCandidates: boolean;
  showObservations: boolean;
  showReturnRoute: boolean;
  showAlternativeRoutes: boolean;
  showTurnbackPonr: boolean;
}

interface EvidenceState {
  corridorAssessment: CorridorAssessment | null;
  routeComparison: RouteEvidenceComparisonResponse | null;
  missionDossier: MissionDossierResponse | null;
  decisionTrace: Record<string, unknown> | null;
  dependencyTrace: Record<string, unknown> | null;
  corridorUncertainty: CorridorUncertaintyProfile | null;
  complementarityReport: ComplementarityAssessmentReport | null;
  selectedSegmentId: string | null;
  loadingCorridor: boolean;
  loadingComparison: boolean;
  loadingDossier: boolean;
  loadingUncertainty: boolean;
  loadingComplementarity: boolean;
  error: string | null;
  overlays: EvidenceOverlayToggles;

  setSelectedSegmentId: (segmentId: string | null) => void;
  toggleOverlay: (key: keyof EvidenceOverlayToggles) => void;
  assessCorridor: (params: {
    dataset_id: string;
    start: { lat: number; lon_east: number; label?: string | null };
    destination: { lat: number; lon_east: number; label?: string | null };
    mode?: string;
    corridor_width_m?: number;
    observation_search_radius_m?: number;
    force_recompute?: boolean;
  }) => Promise<CorridorAssessment | null>;
  fetchDecisionTrace: (assessmentId: string) => Promise<Record<string, unknown> | null>;
  compareRoutesEvidence: (params: {
    dataset_id: string;
    start: { lat: number; lon_east: number; label?: string | null };
    destination: { lat: number; lon_east: number; label?: string | null };
    corridor_width_m?: number;
    observation_search_radius_m?: number;
  }) => Promise<RouteEvidenceComparisonResponse | null>;
  fetchDependencyTrace: (assessmentId: string) => Promise<Record<string, unknown> | null>;
  fetchCorridorUncertainty: (params?: { dataset_id?: string; max_slope_deg?: number }) => Promise<CorridorUncertaintyProfile | null>;
  fetchComplementarity: (datasetIds?: string[]) => Promise<ComplementarityAssessmentReport | null>;
  generateMissionDossier: (params: {
    mission_name?: string;
    dataset_id: string;
    start: { lat: number; lon_east: number; label?: string | null };
    destination: { lat: number; lon_east: number; label?: string | null };
    mode?: string;
    corridor_width_m?: number;
    observation_search_radius_m?: number;
    walking_speed_mps?: number | null;
    mission_duration_limit_s?: number | null;
    return_reserve_fraction?: number | null;
    astronaut_suit_mass_kg?: number | null;
    payload_mass_kg?: number | null;
    independent_return_computed?: boolean;
    force_recompute?: boolean;
  }) => Promise<MissionDossierResponse | null>;
}

export const useEvidenceStore = create<EvidenceState>((set, get) => ({
  corridorAssessment: null,
  routeComparison: null,
  missionDossier: null,
  decisionTrace: null,
  dependencyTrace: null,
  corridorUncertainty: null,
  complementarityReport: null,
  selectedSegmentId: null,
  loadingCorridor: false,
  loadingComparison: false,
  loadingDossier: false,
  loadingUncertainty: false,
  loadingComplementarity: false,
  error: null,
  overlays: {
    showCorridor: true,
    showSegments: true,
    showGaps: true,
    showTerrainCandidates: true,
    showOpticalCandidates: true,
    showObservations: true,
    showReturnRoute: true,
    showAlternativeRoutes: true,
    showTurnbackPonr: true,
  },

  setSelectedSegmentId: (segmentId) => set({ selectedSegmentId: segmentId }),

  toggleOverlay: (key) =>
    set((s) => ({
      overlays: { ...s.overlays, [key]: !s.overlays[key] },
    })),

  assessCorridor: async (params) => {
    set({ loadingCorridor: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/evidence-intelligence/corridor/assess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: CorridorAssessment = await res.json();
      set({
        corridorAssessment: data,
        selectedSegmentId: data.segments[0]?.segment_id ?? null,
        loadingCorridor: false,
      });
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to assess corridor";
      set({ error: msg, loadingCorridor: false });
      return null;
    }
  },

  fetchDecisionTrace: async (assessmentId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/evidence-intelligence/corridor/${encodeURIComponent(assessmentId)}/decision-trace`
      );
      if (!res.ok) return null;
      const data = await res.json();
      set({ decisionTrace: data });
      return data;
    } catch {
      return null;
    }
  },

  compareRoutesEvidence: async (params) => {
    set({ loadingComparison: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/evidence-intelligence/routes/compare-evidence`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: RouteEvidenceComparisonResponse = await res.json();
      set({ routeComparison: data, loadingComparison: false });
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to compare route evidence";
      set({ error: msg, loadingComparison: false });
      return null;
    }
  },

  generateMissionDossier: async (params) => {
    set({ loadingDossier: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/evidence-intelligence/mission-dossier/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(params),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: MissionDossierResponse = await res.json();
      set({
        missionDossier: data,
        corridorAssessment: data.corridor_assessment,
        routeComparison: data.route_comparison ?? null,
        corridorUncertainty: data.corridor_uncertainty_profile ?? get().corridorUncertainty,
        complementarityReport: data.complementarity_report ?? get().complementarityReport,
        selectedSegmentId: data.corridor_assessment.segments[0]?.segment_id ?? null,
        loadingDossier: false,
      });
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to generate mission dossier";
      set({ error: msg, loadingDossier: false });
      return null;
    }
  },

  fetchDependencyTrace: async (assessmentId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/evidence-intelligence/corridor/${encodeURIComponent(assessmentId)}/dependency-trace`,
        { cache: "no-store" }
      );
      if (!res.ok) return null;
      const data = await res.json();
      set({ dependencyTrace: data });
      return data;
    } catch {
      return null;
    }
  },

  fetchCorridorUncertainty: async (params) => {
    set({ loadingUncertainty: true });
    try {
      const qs = new URLSearchParams();
      if (params?.dataset_id) qs.set("dataset_id", params.dataset_id);
      if (params?.max_slope_deg != null) qs.set("max_slope_deg", String(params.max_slope_deg));
      const res = await fetch(`${API_BASE_URL}/terrain-uncertainty/corridor?${qs.toString()}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        set({ loadingUncertainty: false });
        return null;
      }
      const data: CorridorUncertaintyProfile = await res.json();
      set({ corridorUncertainty: data, loadingUncertainty: false });
      return data;
    } catch {
      set({ loadingUncertainty: false });
      return null;
    }
  },

  fetchComplementarity: async (datasetIds) => {
    set({ loadingComplementarity: true });
    try {
      const qs = new URLSearchParams();
      if (datasetIds && datasetIds.length > 0) {
        qs.set("dataset_ids", datasetIds.join(","));
      }
      const res = await fetch(`${API_BASE_URL}/terrain-uncertainty/complementarity?${qs.toString()}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        set({ loadingComplementarity: false });
        return null;
      }
      const data: ComplementarityAssessmentReport = await res.json();
      set({ complementarityReport: data, loadingComplementarity: false });
      return data;
    } catch {
      set({ loadingComplementarity: false });
      return null;
    }
  },
}));
