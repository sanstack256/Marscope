"use client";

import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import type {
  CorridorAssessment,
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
}

interface EvidenceState {
  corridorAssessment: CorridorAssessment | null;
  routeComparison: RouteEvidenceComparisonResponse | null;
  missionDossier: MissionDossierResponse | null;
  selectedSegmentId: string | null;
  loadingCorridor: boolean;
  loadingComparison: boolean;
  loadingDossier: boolean;
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
  }) => Promise<CorridorAssessment | null>;
  compareRoutesEvidence: (params: {
    dataset_id: string;
    start: { lat: number; lon_east: number; label?: string | null };
    destination: { lat: number; lon_east: number; label?: string | null };
    corridor_width_m?: number;
    observation_search_radius_m?: number;
  }) => Promise<RouteEvidenceComparisonResponse | null>;
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
  }) => Promise<MissionDossierResponse | null>;
}

export const useEvidenceStore = create<EvidenceState>((set) => ({
  corridorAssessment: null,
  routeComparison: null,
  missionDossier: null,
  selectedSegmentId: null,
  loadingCorridor: false,
  loadingComparison: false,
  loadingDossier: false,
  error: null,
  overlays: {
    showCorridor: true,
    showSegments: true,
    showGaps: true,
    showTerrainCandidates: true,
    showOpticalCandidates: true,
    showObservations: true,
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
}));
