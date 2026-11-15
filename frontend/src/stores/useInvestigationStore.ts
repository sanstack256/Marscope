import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import { createChannelGuard, isAbortError, parseApiError } from "../lib/requestGuard";
import { useEvaOperationsStore } from "./useEvaOperationsStore";
import type {
  CampaignBuildRequest,
  CampaignDossierExport,
  CampaignFreshnessReport,
  CampaignSummary,
  CustomScienceQuestionCreateRequest,
  InferenceValidationRequest,
  InferenceValidationResponse,
  IngestionLedgerResponse,
  InstrumentCapabilityRecord,
  MissionLifecycleSummaryResponse,
  ObservationArchiveComparison,
  ProductDetailInspectionResponse,
  QuestionEvidenceDiscoveryResponse,
  RecordedFieldObservation,
  RecordObservationRequest,
  ScienceCampaignPlan,
  ScienceQuestionDefinition,
  TargetEvaluationBatchResponse,
  TargetEvaluationRequest,
} from "../types";

interface InvestigationState {
  instruments: InstrumentCapabilityRecord[];
  inferenceValidation: InferenceValidationResponse | null;
  questions: ScienceQuestionDefinition[];
  activeQuestionId: string;
  discovery: QuestionEvidenceDiscoveryResponse | null;
  evaluatedBatch: TargetEvaluationBatchResponse | null;
  selectedStopTargetIds: string[];
  campaigns: CampaignSummary[];
  activeCampaign: ScienceCampaignPlan | null;
  activeLifecycle: MissionLifecycleSummaryResponse | null;
  freshnessReport: CampaignFreshnessReport | null;
  observations: RecordedFieldObservation[];
  comparisons: ObservationArchiveComparison[];
  activeComparison: ObservationArchiveComparison | null;
  ledger: IngestionLedgerResponse | null;

  loadingQuestions: boolean;
  loadingDiscovery: boolean;
  loadingTargets: boolean;
  loadingCampaign: boolean;
  loadingApprove: boolean;
  loadingFreshness: boolean;
  loadingObservations: boolean;
  loadingComparison: boolean;
  loadingProductInspect: boolean;
  inspectedProduct: ProductDetailInspectionResponse | null;
  error: string | null;

  clearError: () => void;
  setActiveQuestionId: (questionId: string) => void;
  toggleStopTargetId: (targetId: string) => void;
  setSelectedStopTargetIds: (targetIds: string[]) => void;

  fetchInstruments: (includeIsolated?: boolean) => Promise<void>;
  validateInference: (req: InferenceValidationRequest) => Promise<InferenceValidationResponse | null>;
  fetchQuestions: () => Promise<void>;
  createCustomQuestion: (req: CustomScienceQuestionCreateRequest) => Promise<ScienceQuestionDefinition | null>;
  deleteCustomQuestion: (questionId: string) => Promise<boolean>;
  discoverEvidence: (questionId: string) => Promise<QuestionEvidenceDiscoveryResponse | null>;
  inspectProductDetail: (
    datasetId: string,
    questionId?: string
  ) => Promise<ProductDetailInspectionResponse | null>;
  exportCampaignDossier: (campaignId: string) => Promise<CampaignDossierExport | null>;
  exportUnifiedDossier: (campaignId: string) => Promise<Record<string, unknown> | null>;
  evaluateTargets: (req?: Partial<TargetEvaluationRequest>) => Promise<TargetEvaluationBatchResponse | null>;
  buildCampaign: (req: CampaignBuildRequest) => Promise<ScienceCampaignPlan | null>;
  fetchCampaigns: () => Promise<void>;
  loadCampaign: (campaignId: string) => Promise<ScienceCampaignPlan | null>;
  approveCampaign: (
    campaignId: string,
    note?: string,
    operatorId?: string
  ) => Promise<ScienceCampaignPlan | null>;
  fetchLifecycle: (campaignId: string) => Promise<MissionLifecycleSummaryResponse | null>;
  checkFreshness: (campaignId: string) => Promise<CampaignFreshnessReport | null>;
  recomputeCampaign: (campaignId: string) => Promise<ScienceCampaignPlan | null>;
  recordObservation: (req: RecordObservationRequest) => Promise<RecordedFieldObservation | null>;
  fetchObservations: (campaignId?: string, targetId?: string) => Promise<void>;
  compareObservation: (observationId: string, searchRadiusM?: number) => Promise<ObservationArchiveComparison | null>;
  fetchComparisons: (observationId?: string) => Promise<void>;
  fetchIngestionLedger: (limit?: number) => Promise<void>;
}

const _parseError = parseApiError;

const _discoveryGuard = createChannelGuard();
const _targetsGuard = createChannelGuard();
const _campaignGuard = createChannelGuard();
const _freshnessGuard = createChannelGuard();
const _lifecycleGuard = createChannelGuard();
const _inspectGuard = createChannelGuard();

export const useInvestigationStore = create<InvestigationState>((set, get) => ({
  instruments: [],
  inferenceValidation: null,
  questions: [],
  activeQuestionId: "gale_boxwork_origin",
  discovery: null,
  evaluatedBatch: null,
  selectedStopTargetIds: [],
  campaigns: [],
  activeCampaign: null,
  activeLifecycle: null,
  freshnessReport: null,
  observations: [],
  comparisons: [],
  activeComparison: null,
  ledger: null,

  loadingQuestions: false,
  loadingDiscovery: false,
  loadingTargets: false,
  loadingCampaign: false,
  loadingApprove: false,
  loadingFreshness: false,
  loadingObservations: false,
  loadingComparison: false,
  loadingProductInspect: false,
  inspectedProduct: null,
  error: null,

  clearError: () => set({ error: null }),

  setActiveQuestionId: (questionId) =>
    set({
      activeQuestionId: questionId,
      discovery: null,
      evaluatedBatch: null,
      selectedStopTargetIds: [],
    }),

  toggleStopTargetId: (targetId) =>
    set((state) => {
      const exists = state.selectedStopTargetIds.includes(targetId);
      return {
        selectedStopTargetIds: exists
          ? state.selectedStopTargetIds.filter((id) => id !== targetId)
          : [...state.selectedStopTargetIds, targetId],
      };
    }),

  setSelectedStopTargetIds: (targetIds) => set({ selectedStopTargetIds: targetIds }),

  fetchInstruments: async (includeIsolated = true) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/instruments?include_mission_isolated=${includeIsolated}`
      );
      if (!res.ok) throw new Error(await _parseError(res, "Failed to load instruments"));
      const data: InstrumentCapabilityRecord[] = await res.json();
      set({ instruments: data });
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "Failed to load instruments" });
    }
  },

  validateInference: async (req) => {
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/instruments/validate-inference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Inference validation error"));
      const data: InferenceValidationResponse = await res.json();
      set({ inferenceValidation: data });
      return data;
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "Inference validation failed" });
      return null;
    }
  },

  fetchQuestions: async () => {
    set({ loadingQuestions: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/questions`);
      if (!res.ok) throw new Error(await _parseError(res, "Failed to load scientific questions"));
      const data: ScienceQuestionDefinition[] = await res.json();
      set({ questions: data, loadingQuestions: false });
    } catch (e: unknown) {
      set({
        loadingQuestions: false,
        error: e instanceof Error ? e.message : "Failed to load scientific questions",
      });
    }
  },

  createCustomQuestion: async (req) => {
    set({ loadingQuestions: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to create custom question"));
      const created: ScienceQuestionDefinition = await res.json();
      set((s) => ({
        questions: [...s.questions, created],
        activeQuestionId: created.question_id,
        loadingQuestions: false,
      }));
      return created;
    } catch (e: unknown) {
      set({
        loadingQuestions: false,
        error: e instanceof Error ? e.message : "Failed to create custom question",
      });
      return null;
    }
  },

  deleteCustomQuestion: async (questionId) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/questions/${encodeURIComponent(questionId)}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Failed to delete question"));
      set((s) => ({
        questions: s.questions.filter((q) => q.question_id !== questionId),
        activeQuestionId:
          s.activeQuestionId === questionId ? "gale_boxwork_origin" : s.activeQuestionId,
      }));
      return true;
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : "Failed to delete question" });
      return false;
    }
  },

  discoverEvidence: async (questionId) => {
    const { seq, signal } = _discoveryGuard.next();
    set({ loadingDiscovery: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/questions/${encodeURIComponent(questionId)}/discover-evidence`,
        { signal, cache: "no-store" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Failed to discover question evidence"));
      const data: QuestionEvidenceDiscoveryResponse = await res.json();
      if (!_discoveryGuard.isCurrent(seq)) return null;
      set({ discovery: data, loadingDiscovery: false });
      return data;
    } catch (e: unknown) {
      if (isAbortError(e) || !_discoveryGuard.isCurrent(seq)) return null;
      set({
        loadingDiscovery: false,
        error: e instanceof Error ? e.message : "Failed to discover question evidence",
      });
      return null;
    }
  },

  evaluateTargets: async (partialReq = {}) => {
    const { seq, signal } = _targetsGuard.next();
    set({ loadingTargets: true, error: null });
    try {
      const qId = partialReq.question_id ?? get().activeQuestionId;
      const body: TargetEvaluationRequest = {
        question_id: qId,
        include_discovered_candidates: true,
        search_radius_m: 250,
        max_candidates: 12,
        ...partialReq,
      };
      const res = await fetch(`${API_BASE_URL}/science-investigation/targets/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to evaluate targets"));
      const data: TargetEvaluationBatchResponse = await res.json();
      if (!_targetsGuard.isCurrent(seq)) return null;
      set({ evaluatedBatch: data, loadingTargets: false });
      return data;
    } catch (e: unknown) {
      if (isAbortError(e) || !_targetsGuard.isCurrent(seq)) return null;
      set({
        loadingTargets: false,
        error: e instanceof Error ? e.message : "Failed to evaluate targets",
      });
      return null;
    }
  },

  buildCampaign: async (req) => {
    set({ loadingCampaign: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/campaigns/build`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to build science campaign"));
      const plan: ScienceCampaignPlan = await res.json();
      set({ activeCampaign: plan, loadingCampaign: false });
      useEvaOperationsStore.getState().syncFromCampaignEnvelope(plan.eva_envelope);
      await get().fetchCampaigns();
      void get().fetchLifecycle(plan.campaign_id);
      return plan;
    } catch (e: unknown) {
      set({
        loadingCampaign: false,
        error: e instanceof Error ? e.message : "Failed to build science campaign",
      });
      return null;
    }
  },

  fetchCampaigns: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/campaigns`);
      if (!res.ok) return;
      const data: CampaignSummary[] = await res.json();
      set({ campaigns: data });
    } catch {
      // silent list failure handled elsewhere
    }
  },

  loadCampaign: async (campaignId) => {
    const { seq, signal } = _campaignGuard.next();
    set({ loadingCampaign: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}`,
        { signal, cache: "no-store" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Failed to load campaign"));
      const plan: ScienceCampaignPlan = await res.json();
      if (!_campaignGuard.isCurrent(seq)) return null;
      set({ activeCampaign: plan, loadingCampaign: false });
      useEvaOperationsStore.getState().syncFromCampaignEnvelope(plan.eva_envelope);
      void get().fetchLifecycle(campaignId);
      return plan;
    } catch (e: unknown) {
      if (isAbortError(e) || !_campaignGuard.isCurrent(seq)) return null;
      set({
        loadingCampaign: false,
        error: e instanceof Error ? e.message : "Failed to load campaign",
      });
      return null;
    }
  },

  checkFreshness: async (campaignId) => {
    const { seq, signal } = _freshnessGuard.next();
    set({ loadingFreshness: true });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/freshness`,
        { signal, cache: "no-store" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Freshness check failed"));
      const rep: CampaignFreshnessReport = await res.json();
      if (!_freshnessGuard.isCurrent(seq)) return null;
      set((s) => ({
        freshnessReport: rep,
        loadingFreshness: false,
        activeCampaign:
          s.activeCampaign?.campaign_id === campaignId
            ? {
                ...s.activeCampaign,
                freshness_state: rep.freshness_state,
                staleness_reasons: rep.staleness_reasons,
              }
            : s.activeCampaign,
      }));
      return rep;
    } catch (e: unknown) {
      if (isAbortError(e) || !_freshnessGuard.isCurrent(seq)) return null;
      set({
        loadingFreshness: false,
        error: e instanceof Error ? e.message : "Freshness check failed",
      });
      return null;
    }
  },

  recomputeCampaign: async (campaignId) => {
    const { seq } = _campaignGuard.next();
    set({ loadingCampaign: true, error: null });
    try {
      const cur = get().activeCampaign;
      const expectedVer = cur?.campaign_id === campaignId ? cur.plan_version : undefined;
      const qs = expectedVer ? `?expected_plan_version=${expectedVer}` : "";
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/recompute${qs}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Campaign recompute failed"));
      const plan: ScienceCampaignPlan = await res.json();
      if (!_campaignGuard.isCurrent(seq)) return null;
      set({ activeCampaign: plan, freshnessReport: null, loadingCampaign: false });
      useEvaOperationsStore.getState().syncFromCampaignEnvelope(plan.eva_envelope);
      await get().fetchCampaigns();
      void get().fetchLifecycle(campaignId);
      return plan;
    } catch (e: unknown) {
      if (!_campaignGuard.isCurrent(seq)) return null;
      set({
        loadingCampaign: false,
        error: e instanceof Error ? e.message : "Campaign recompute failed",
      });
      return null;
    }
  },

  recordObservation: async (req) => {
    set({ loadingObservations: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/science-investigation/observations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error(await _parseError(res, "Failed to record field observation"));
      const obs: RecordedFieldObservation = await res.json();
      set((s) => ({
        observations: [obs, ...s.observations],
        loadingObservations: false,
      }));
      if (req.campaign_id) {
        void get().checkFreshness(req.campaign_id);
        void get().fetchLifecycle(req.campaign_id);
      }
      return obs;
    } catch (e: unknown) {
      set({
        loadingObservations: false,
        error: e instanceof Error ? e.message : "Failed to record field observation",
      });
      return null;
    }
  },

  fetchObservations: async (campaignId, targetId) => {
    try {
      const qs = new URLSearchParams();
      if (campaignId) qs.set("campaign_id", campaignId);
      if (targetId) qs.set("target_id", targetId);
      const q = qs.toString();
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/observations${q ? `?${q}` : ""}`
      );
      if (!res.ok) return;
      const data: RecordedFieldObservation[] = await res.json();
      set({ observations: data });
    } catch {
      // handled upstream
    }
  },

  compareObservation: async (observationId, searchRadiusM = 150) => {
    set({ loadingComparison: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/observations/${encodeURIComponent(
          observationId
        )}/compare?search_radius_m=${searchRadiusM}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Archive comparison failed"));
      const cmp: ObservationArchiveComparison = await res.json();
      set((s) => ({
        activeComparison: cmp,
        comparisons: [cmp, ...s.comparisons.filter((c) => c.comparison_id !== cmp.comparison_id)],
        loadingComparison: false,
      }));
      const activeCid = get().activeCampaign?.campaign_id;
      if (activeCid) {
        void get().loadCampaign(activeCid);
      }
      return cmp;
    } catch (e: unknown) {
      set({
        loadingComparison: false,
        error: e instanceof Error ? e.message : "Archive comparison failed",
      });
      return null;
    }
  },

  fetchComparisons: async (observationId) => {
    try {
      const qs = observationId ? `?observation_id=${encodeURIComponent(observationId)}` : "";
      const res = await fetch(`${API_BASE_URL}/science-investigation/comparisons${qs}`);
      if (!res.ok) return;
      const data: ObservationArchiveComparison[] = await res.json();
      set({ comparisons: data });
    } catch {
      // handled upstream
    }
  },

  fetchIngestionLedger: async (limit = 50) => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/ingestion-ledger?limit=${limit}`
      );
      if (!res.ok) return;
      const data: IngestionLedgerResponse = await res.json();
      set({ ledger: data });
    } catch {
      // handled upstream
    }
  },

  inspectProductDetail: async (datasetId, questionId = "gale_boxwork_origin") => {
    const { seq, signal } = _inspectGuard.next();
    set({ loadingProductInspect: true, error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/products/${encodeURIComponent(
          datasetId
        )}/inspect?question_id=${encodeURIComponent(questionId)}`,
        { cache: "no-store", signal }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Product inspection failed"));
      const data: ProductDetailInspectionResponse = await res.json();
      if (!_inspectGuard.isCurrent(seq)) return null;
      set({ inspectedProduct: data, loadingProductInspect: false });
      return data;
    } catch (e: unknown) {
      if (isAbortError(e) || !_inspectGuard.isCurrent(seq)) return null;
      set({
        loadingProductInspect: false,
        error: e instanceof Error ? e.message : "Product inspection failed",
      });
      return null;
    }
  },

  exportCampaignDossier: async (campaignId) => {
    set({ error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/export`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Campaign dossier export failed"));
      const data: CampaignDossierExport = await res.json();
      return data;
    } catch (e: unknown) {
      set({
        error: e instanceof Error ? e.message : "Campaign dossier export failed",
      });
      return null;
    }
  },

  exportUnifiedDossier: async (campaignId) => {
    set({ error: null });
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/unified-dossier`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Unified dossier export failed"));
      return (await res.json()) as Record<string, unknown>;
    } catch (e: unknown) {
      set({
        error: e instanceof Error ? e.message : "Unified dossier export failed",
      });
      return null;
    }
  },

  approveCampaign: async (
    campaignId,
    note = "Operator reviewed science evidence, spatial registration, and EVA engineering envelope.",
    operatorId = "operator"
  ) => {
    set({ loadingApprove: true, error: null });
    try {
      const cur = get().activeCampaign;
      const expectedPlanVersion = cur?.campaign_id === campaignId ? cur.plan_version : undefined;
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            operator_id: operatorId,
            note,
            ...(expectedPlanVersion !== undefined ? { expected_plan_version: expectedPlanVersion } : {}),
          }),
        }
      );
      if (!res.ok) throw new Error(await _parseError(res, "Campaign approval failed"));
      const plan: ScienceCampaignPlan = await res.json();
      set({ activeCampaign: plan, loadingApprove: false });
      useEvaOperationsStore.getState().syncFromCampaignEnvelope(plan.eva_envelope);
      await get().fetchCampaigns();
      void get().fetchLifecycle(campaignId);
      return plan;
    } catch (e: unknown) {
      set({
        loadingApprove: false,
        error: e instanceof Error ? e.message : "Campaign approval failed",
      });
      return null;
    }
  },

  fetchLifecycle: async (campaignId) => {
    const { seq, signal } = _lifecycleGuard.next();
    try {
      const res = await fetch(
        `${API_BASE_URL}/science-investigation/campaigns/${encodeURIComponent(campaignId)}/lifecycle`,
        { cache: "no-store", signal }
      );
      if (!res.ok) return null;
      const summary: MissionLifecycleSummaryResponse = await res.json();
      if (!_lifecycleGuard.isCurrent(seq)) return null;
      set({ activeLifecycle: summary });
      return summary;
    } catch {
      return null;
    }
  },
}));
