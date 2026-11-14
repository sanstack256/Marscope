"use client";

import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import type { EvaExplicitResourceSpec, EvaMissionEnvelopeResponse } from "../types";
import { useEvidenceStore } from "./useEvidenceStore";

interface EvaOperationsState {
  evaEnvelope: EvaMissionEnvelopeResponse | null;
  selectedTimelineIndex: number | null;
  selectedReturnAlternativeId: string | null;
  loadingEva: boolean;
  error: string | null;

  setSelectedTimelineStep: (index: number | null, segmentId?: string | null) => void;
  setSelectedReturnAlternativeId: (alternativeId: string | null) => void;
  fetchReturnAnalysis: (missionId: string) => Promise<void>;
  evaluateMission: (params: {
    mission_name?: string;
    dataset_id: string;
    start: { lat: number; lon_east: number; label?: string | null };
    destination: { lat: number; lon_east: number; label?: string | null };
    mode?: string;
    corridor_width_m?: number;
    observation_search_radius_m?: number;
    walking_speed_mps?: number | null;
    use_tobler_grade_approximation?: boolean;
    mission_duration_limit_s?: number | null;
    return_reserve_fraction?: number | null;
    operational_overhead_s?: number;
    astronaut_suit_mass_kg?: number | null;
    payload_mass_kg?: number | null;
    resources?: EvaExplicitResourceSpec[];
    compute_reverse_return_route?: boolean;
  }) => Promise<EvaMissionEnvelopeResponse | null>;
}

export const useEvaOperationsStore = create<EvaOperationsState>((set, get) => ({
  evaEnvelope: null,
  selectedTimelineIndex: null,
  selectedReturnAlternativeId: null,
  loadingEva: false,
  error: null,

  setSelectedTimelineStep: (index, segmentId) => {
    set({ selectedTimelineIndex: index });
    if (segmentId !== undefined) {
      useEvidenceStore.getState().setSelectedSegmentId(segmentId);
    }
  },

  setSelectedReturnAlternativeId: (alternativeId) => set({ selectedReturnAlternativeId: alternativeId }),

  fetchReturnAnalysis: async (missionId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/return-analysis`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const body = await res.json();
      const cur = get().evaEnvelope;
      if (cur && cur.mission_id === missionId && body.return_plan) {
        set({ evaEnvelope: { ...cur, return_plan: body.return_plan } });
      }
    } catch {
      // Keep existing envelope if fetch fails
    }
  },

  evaluateMission: async (params) => {
    set({ loadingEva: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/eva-operations/mission/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: EvaMissionEnvelopeResponse = await res.json();
      set({
        evaEnvelope: data,
        selectedTimelineIndex: 0,
        selectedReturnAlternativeId: null,
        loadingEva: false,
      });
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to evaluate EVA operational envelope";
      set({ error: msg, loadingEva: false });
      return null;
    }
  },
}));
