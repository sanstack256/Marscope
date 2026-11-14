import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import {
  CandidateDiscoveryLocation,
  CompositionSearchResponse,
  DestinationEvaluationResponse,
  LocalizationStatusResponse,
  PlanningMode,
  PositionRecord,
  ScienceTarget,
} from "../types";

interface MissionStoreState {
  planningMode: PlanningMode;
  maxDurationHours: number;
  safetyReserveFactor: number;
  maxSlopeLimitDeg: number;
  selectedTargets: ScienceTarget[];

  // Destination & Localization states backed by API
  selectedDestination: DestinationEvaluationResponse | null;
  destinationLoading: boolean;
  destinationError: string | null;

  localizationStatus: LocalizationStatusResponse | null;
  localizationError: string | null;

  // Composition discovery markers synchronized with MarsGlobeViewer
  compositionSearchResponse: CompositionSearchResponse | null;
  compositionCandidates: CandidateDiscoveryLocation[];
  selectedCandidateId: string | null;

  setPlanningMode: (mode: PlanningMode) => void;
  setDuration: (hours: number) => void;
  setSafetyReserve: (factor: number) => void;
  addTarget: (target: ScienceTarget) => void;
  removeTarget: (targetId: string) => void;
  clearTargets: () => void;

  setCompositionResults: (response: CompositionSearchResponse | null) => void;
  selectCompositionCandidate: (candidateId: string | null) => void;

  evaluateDestination: (lat: number, lon: number, label?: string, signal?: AbortSignal) => Promise<void>;
  clearDestination: () => void;

  fetchLocalizationStatus: () => Promise<void>;
  setManualPosition: (lat: number, lon: number) => Promise<PositionRecord | null>;
  clearManualPosition: () => Promise<void>;
}

export const useMissionStore = create<MissionStoreState>((set) => ({
  planningMode: "balanced",
  maxDurationHours: 6.0,
  safetyReserveFactor: 1.5,
  maxSlopeLimitDeg: 25.0,
  selectedTargets: [],

  selectedDestination: null,
  destinationLoading: false,
  destinationError: null,

  localizationStatus: null,
  localizationError: null,

  compositionSearchResponse: null,
  compositionCandidates: [],
  selectedCandidateId: null,

  setPlanningMode: (mode) => set({ planningMode: mode }),
  setDuration: (hours) => set({ maxDurationHours: hours }),
  setSafetyReserve: (factor) => set({ safetyReserveFactor: factor }),
  addTarget: (target) =>
    set((state) => ({
      selectedTargets: state.selectedTargets.some((t) => t.id === target.id)
        ? state.selectedTargets
        : [...state.selectedTargets, target],
    })),
  removeTarget: (targetId) =>
    set((state) => ({
      selectedTargets: state.selectedTargets.filter((t) => t.id !== targetId),
    })),
  clearTargets: () => set({ selectedTargets: [] }),

  setCompositionResults: (response) =>
    set({
      compositionSearchResponse: response,
      compositionCandidates: response?.candidate_locations ?? [],
      selectedCandidateId: response?.candidate_locations?.[0]?.candidate_id ?? null,
    }),
  selectCompositionCandidate: (candidateId) => set({ selectedCandidateId: candidateId }),

  evaluateDestination: async (lat, lon, label, signal) => {
    set({ destinationLoading: true, destinationError: null });
    try {
      const res = await fetch(`${API_BASE_URL}/destinations/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: lat,
          longitude: lon,
          crs: "IAU2000:49900",
          latitude_convention: "Planetocentric",
          longitude_direction: "East",
          label: label || null,
        }),
        signal,
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${res.status} evaluating destination`);
      }
      const data: DestinationEvaluationResponse = await res.json();
      set({ selectedDestination: data, destinationLoading: false, destinationError: null });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      set({
        destinationLoading: false,
        destinationError: err instanceof Error ? err.message : "Destination evaluation failed",
      });
    }
  },

  clearDestination: () => set({ selectedDestination: null, destinationError: null }),

  fetchLocalizationStatus: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/localization/status`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data: LocalizationStatusResponse = await res.json();
      set({ localizationStatus: data, localizationError: null });
    } catch (err) {
      set({
        localizationError: err instanceof Error ? err.message : "Failed to query localization status",
      });
    }
  },

  setManualPosition: async (lat, lon) => {
    try {
      const res = await fetch(`${API_BASE_URL}/localization/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: lat,
          longitude: lon,
          crs: "IAU2000:49900",
          latitude_convention: "Planetocentric",
          longitude_direction: "East",
        }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `HTTP ${res.status}`);
      }
      const record: PositionRecord = await res.json();
      // Refresh status cleanly
      const statusRes = await fetch(`${API_BASE_URL}/localization/status`, { cache: "no-store" });
      if (statusRes.ok) {
        const statusData: LocalizationStatusResponse = await statusRes.json();
        set({ localizationStatus: statusData, localizationError: null });
      }
      return record;
    } catch (err) {
      set({
        localizationError: err instanceof Error ? err.message : "Failed to set manual position",
      });
      return null;
    }
  },

  clearManualPosition: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/localization`, { method: "DELETE" });
      if (res.ok) {
        const data: LocalizationStatusResponse = await res.json();
        set({ localizationStatus: data, localizationError: null });
      }
    } catch (err) {
      set({
        localizationError: err instanceof Error ? err.message : "Failed to clear manual position",
      });
    }
  },
}));
