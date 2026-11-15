"use client";

import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import type {
  EvaEnvironmentalContextReport,
  EvaExplicitResourceSpec,
  EvaMissionEnvelopeResponse,
  MissionOperationalSession,
  MissionOperationsDossier,
  MissionSensitivityAnalysisReport,
  PlanComparisonReport,
  TelemetryAdapterStatusResponse,
} from "../types";
import { useEvidenceStore } from "./useEvidenceStore";

export interface EvaEvaluateParams {
  mission_id?: string;
  mission_name?: string;
  dataset_id: string;
  start: { lat: number; lon_east: number; label?: string | null };
  destination: { lat: number; lon_east: number; label?: string | null };
  mode?: string;
  corridor_width_m?: number;
  observation_search_radius_m?: number;
  walking_speed_mps?: number | null;
  use_tobler_grade_approximation?: boolean;
  locomotion_category?:
    | "USER_CONFIGURED_CONSTANT_SPEED"
    | "TERRESTRIAL_HIKING_APPROXIMATION"
    | "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL";
  unknown_terrain_policy?:
    | "EXCLUDE_UNKNOWN"
    | "ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE"
    | "REQUIRE_ADDITIONAL_OBSERVATION"
    | "ROUTE_THROUGH_WITH_LIMITATION";
  operator_unknown_override_reason?: string | null;
  confirm_default_policies?: boolean;
  mission_duration_limit_s?: number | null;
  return_reserve_fraction?: number | null;
  operational_overhead_s?: number;
  astronaut_suit_mass_kg?: number | null;
  payload_mass_kg?: number | null;
  resources?: EvaExplicitResourceSpec[];
  compute_reverse_return_route?: boolean;
}

interface EvaOperationsState {
  evaEnvelope: EvaMissionEnvelopeResponse | null;
  lastEvalParams: EvaEvaluateParams | null;
  missionSession: MissionOperationalSession | null;
  pendingComparison: PlanComparisonReport | null;
  sensitivityReport: MissionSensitivityAnalysisReport | null;
  operationsDossier: MissionOperationsDossier | null;
  telemetryStatus: TelemetryAdapterStatusResponse | null;
  environmentalContext: EvaEnvironmentalContextReport | null;
  selectedTimelineIndex: number | null;
  selectedReturnAlternativeId: string | null;
  loadingEva: boolean;
  loadingReplan: boolean;
  loadingSensitivity: boolean;
  loadingDossier: boolean;
  error: string | null;

  setSelectedTimelineStep: (index: number | null, segmentId?: string | null) => void;
  setSelectedReturnAlternativeId: (alternativeId: string | null) => void;
  syncFromCampaignEnvelope: (envelope: EvaMissionEnvelopeResponse | null | undefined) => void;
  loadLinkedMission: (missionId: string) => Promise<MissionOperationalSession | null>;
  fetchReturnAnalysis: (missionId: string) => Promise<void>;
  fetchSession: (missionId: string) => Promise<void>;
  fetchSensitivity: (missionId: string) => Promise<void>;
  fetchTelemetryStatus: (missionId?: string) => Promise<void>;
  fetchEnvironmentalContext: (missionId: string) => Promise<void>;
  exportOperationsDossier: (missionId: string) => Promise<MissionOperationsDossier | null>;
  recordMissionEvent: (
    missionId: string,
    payload: { event_type: string; description: string; operator_id?: string; payload?: Record<string, unknown> }
  ) => Promise<void>;
  previewReplan: (
    missionId: string,
    payload: { reason: string; updated_config: EvaEvaluateParams; operator_id?: string }
  ) => Promise<PlanComparisonReport | null>;
  approveReplan: (missionId: string, note?: string) => Promise<void>;
  rejectReplan: (missionId: string, note?: string) => Promise<void>;
  evaluateMission: (params: EvaEvaluateParams) => Promise<EvaMissionEnvelopeResponse | null>;
}

export const useEvaOperationsStore = create<EvaOperationsState>((set, get) => ({
  evaEnvelope: null,
  lastEvalParams: null,
  missionSession: null,
  pendingComparison: null,
  sensitivityReport: null,
  operationsDossier: null,
  telemetryStatus: null,
  environmentalContext: null,
  selectedTimelineIndex: null,
  selectedReturnAlternativeId: null,
  loadingEva: false,
  loadingReplan: false,
  loadingSensitivity: false,
  loadingDossier: false,
  error: null,

  setSelectedTimelineStep: (index, segmentId) => {
    set({ selectedTimelineIndex: index });
    if (segmentId !== undefined) {
      useEvidenceStore.getState().setSelectedSegmentId(segmentId);
    }
  },

  setSelectedReturnAlternativeId: (alternativeId) => set({ selectedReturnAlternativeId: alternativeId }),

  syncFromCampaignEnvelope: (envelope) => {
    if (!envelope) return;
    set({
      evaEnvelope: envelope,
      environmentalContext: envelope.environmental_context ?? null,
      telemetryStatus: envelope.telemetry_state ?? null,
      selectedTimelineIndex: 0,
      selectedReturnAlternativeId: null,
      error: null,
    });
    if (envelope.mission_id) {
      void get().fetchSession(envelope.mission_id);
      void get().fetchSensitivity(envelope.mission_id);
    }
  },

  loadLinkedMission: async (missionId) => {
    set({ loadingEva: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/session`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const session: MissionOperationalSession = await res.json();
      set({
        missionSession: session,
        evaEnvelope: session.active_envelope,
        pendingComparison: session.pending_comparison ?? null,
        environmentalContext: session.active_envelope?.environmental_context ?? null,
        telemetryStatus: session.active_envelope?.telemetry_state ?? null,
        loadingEva: false,
      });
      void get().fetchSensitivity(missionId);
      void get().fetchReturnAnalysis(missionId);
      return session;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to load linked mission session";
      set({ error: msg, loadingEva: false });
      return null;
    }
  },

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

  fetchSession: async (missionId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/session`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const session: MissionOperationalSession = await res.json();
      set({
        missionSession: session,
        evaEnvelope: session.active_envelope,
        pendingComparison: session.pending_comparison ?? null,
      });
    } catch {
      // Keep existing session state
    }
  },

  fetchSensitivity: async (missionId) => {
    set({ loadingSensitivity: true });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/sensitivity`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        set({ loadingSensitivity: false });
        return;
      }
      const rep: MissionSensitivityAnalysisReport = await res.json();
      set({ sensitivityReport: rep, loadingSensitivity: false });
    } catch {
      set({ loadingSensitivity: false });
    }
  },

  fetchTelemetryStatus: async (missionId) => {
    try {
      const qs = missionId ? `?mission_id=${encodeURIComponent(missionId)}` : "";
      const res = await fetch(`${API_BASE_URL}/eva-operations/telemetry/status${qs}`, {
        cache: "no-store",
      });
      if (!res.ok) return;
      const data: TelemetryAdapterStatusResponse = await res.json();
      set({ telemetryStatus: data });
    } catch {
      // Ignore network errors
    }
  },

  fetchEnvironmentalContext: async (missionId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/environmental-context`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const data: EvaEnvironmentalContextReport = await res.json();
      set({ environmentalContext: data });
    } catch {
      // Ignore network errors
    }
  },

  exportOperationsDossier: async (missionId) => {
    set({ loadingDossier: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/dossier`,
        { cache: "no-store" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const dossier: MissionOperationsDossier = await res.json();
      set({ operationsDossier: dossier, loadingDossier: false });
      return dossier;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to export mission operations dossier";
      set({ error: msg, loadingDossier: false });
      return null;
    }
  },

  recordMissionEvent: async (missionId, payload) => {
    set({ loadingReplan: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/events`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const session: MissionOperationalSession = await res.json();
      set({
        missionSession: session,
        evaEnvelope: session.active_envelope,
        loadingReplan: false,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to record mission event";
      set({ error: msg, loadingReplan: false });
    }
  },

  previewReplan: async (missionId, payload) => {
    set({ loadingReplan: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/replan/preview`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const cmp: PlanComparisonReport = await res.json();
      set({ pendingComparison: cmp, loadingReplan: false });
      await get().fetchSession(missionId);
      return cmp;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to preview mission replan";
      set({ error: msg, loadingReplan: false });
      return null;
    }
  },

  approveReplan: async (missionId, note = "Operator verified and approved revised plan") => {
    set({ loadingReplan: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/replan/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operator_id: "operator", note }),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const session: MissionOperationalSession = await res.json();
      set({
        missionSession: session,
        evaEnvelope: session.active_envelope,
        pendingComparison: null,
        loadingReplan: false,
      });
      void get().fetchSensitivity(missionId);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to approve revised plan";
      set({ error: msg, loadingReplan: false });
    }
  },

  rejectReplan: async (missionId, note = "Operator retained previous plan") => {
    set({ loadingReplan: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/eva-operations/mission/${encodeURIComponent(missionId)}/replan/reject`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operator_id: "operator", note }),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const session: MissionOperationalSession = await res.json();
      set({
        missionSession: session,
        evaEnvelope: session.active_envelope,
        pendingComparison: null,
        loadingReplan: false,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to reject revised plan";
      set({ error: msg, loadingReplan: false });
    }
  },

  evaluateMission: async (params) => {
    set({ loadingEva: true, error: null, lastEvalParams: params });
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
        environmentalContext: data.environmental_context ?? null,
        telemetryStatus: data.telemetry_state ?? null,
        selectedTimelineIndex: 0,
        selectedReturnAlternativeId: null,
        loadingEva: false,
      });
      void get().fetchSession(data.mission_id);
      void get().fetchSensitivity(data.mission_id);
      return data;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to evaluate EVA operational envelope";
      set({ error: msg, loadingEva: false });
      return null;
    }
  },
}));
