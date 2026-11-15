"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Compass,
  GitBranch,
  Layers,
  Microscope,
  Route,
  ShieldAlert,
} from "lucide-react";
import { useEvaOperationsStore } from "../stores/useEvaOperationsStore";
import { useInvestigationStore } from "../stores/useInvestigationStore";
import { useRoutingStore } from "../stores/useRoutingStore";

function lifecycleTone(state?: string | null): string {
  switch (state) {
    case "OPERATOR_APPROVAL":
    case "EXECUTION_NOT_STARTED":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "REPLAN_IF_REQUIRED":
    case "HYPOTHESIS_REASSESSMENT":
    case "CAMPAIGN_FRESHNESS_CHECK":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    default:
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-200";
  }
}

export function IntegratedMissionContextBar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const activeQuestionId = useInvestigationStore((s) => s.activeQuestionId);
  const activeCampaign = useInvestigationStore((s) => s.activeCampaign);
  const activeLifecycle = useInvestigationStore((s) => s.activeLifecycle);
  const loadingApprove = useInvestigationStore((s) => s.loadingApprove);
  const loadCampaign = useInvestigationStore((s) => s.loadCampaign);
  const fetchLifecycle = useInvestigationStore((s) => s.fetchLifecycle);
  const approveCampaign = useInvestigationStore((s) => s.approveCampaign);
  const setActiveQuestionId = useInvestigationStore((s) => s.setActiveQuestionId);

  const evaEnvelope = useEvaOperationsStore((s) => s.evaEnvelope);
  const missionSession = useEvaOperationsStore((s) => s.missionSession);
  const loadLinkedMission = useEvaOperationsStore((s) => s.loadLinkedMission);

  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);

  const qCampaignId = searchParams.get("campaignId");
  const qMissionId = searchParams.get("missionId");
  const qQuestionId = searchParams.get("questionId");

  useEffect(() => {
    if (qQuestionId && qQuestionId !== activeQuestionId) {
      setActiveQuestionId(qQuestionId);
    }
  }, [qQuestionId, activeQuestionId, setActiveQuestionId]);

  useEffect(() => {
    if (qCampaignId && activeCampaign?.campaign_id !== qCampaignId) {
      void loadCampaign(qCampaignId);
    }
  }, [qCampaignId, activeCampaign?.campaign_id, loadCampaign]);

  useEffect(() => {
    if (qMissionId && evaEnvelope?.mission_id !== qMissionId) {
      void loadLinkedMission(qMissionId);
    }
  }, [qMissionId, evaEnvelope?.mission_id, loadLinkedMission]);

  // If EVA session points to a linked campaign that isn't loaded yet, hydrate it silently
  useEffect(() => {
    const linkedCid = missionSession?.linked_campaign_id ?? evaEnvelope?.linked_campaign_id;
    if (linkedCid && activeCampaign?.campaign_id !== linkedCid) {
      void loadCampaign(linkedCid);
    }
  }, [
    missionSession?.linked_campaign_id,
    evaEnvelope?.linked_campaign_id,
    activeCampaign?.campaign_id,
    loadCampaign,
  ]);

  useEffect(() => {
    if (activeCampaign?.campaign_id && activeLifecycle?.campaign_id !== activeCampaign.campaign_id) {
      void fetchLifecycle(activeCampaign.campaign_id);
    }
  }, [activeCampaign?.campaign_id, activeLifecycle?.campaign_id, fetchLifecycle]);

  const effectiveCampaignId = activeCampaign?.campaign_id ?? missionSession?.linked_campaign_id ?? null;
  const effectiveMissionId =
    activeCampaign?.linked_mission_id ?? evaEnvelope?.mission_id ?? missionSession?.mission_id ?? null;
  const effectiveDatasetId = activeCampaign?.dataset_id ?? evaEnvelope?.dataset_id ?? selectedDemDatasetId;
  const effectiveLifecycleState =
    activeLifecycle?.integrated_lifecycle_state ??
    activeCampaign?.integrated_lifecycle_state ??
    evaEnvelope?.integrated_lifecycle_state ??
    missionSession?.integrated_lifecycle_state ??
    null;

  const isStale =
    activeLifecycle?.freshness?.freshness_state === "stale_upstream_dependency_changed" ||
    activeCampaign?.freshness_state === "stale_upstream_dependency_changed" ||
    Boolean(missionSession?.stale) ||
    Boolean(evaEnvelope?.stale);

  const hasContextMismatch = Boolean(
    (activeCampaign?.linked_mission_id &&
      missionSession?.mission_id &&
      activeCampaign.linked_mission_id !== missionSession.mission_id) ||
      (activeCampaign?.dataset_id &&
        evaEnvelope?.dataset_id &&
        activeCampaign.dataset_id !== evaEnvelope.dataset_id)
  );

  const linkQuery = useMemo(() => {
    const p = new URLSearchParams();
    if (effectiveCampaignId) p.set("campaignId", effectiveCampaignId);
    if (effectiveMissionId) p.set("missionId", effectiveMissionId);
    if (activeQuestionId) p.set("questionId", activeQuestionId);
    if (effectiveDatasetId) p.set("datasetId", effectiveDatasetId);
    const qs = p.toString();
    return qs ? `?${qs}` : "";
  }, [effectiveCampaignId, effectiveMissionId, activeQuestionId, effectiveDatasetId]);

  const stages = [
    { href: "/science-campaign", label: "Science Campaign", icon: Microscope },
    { href: "/spatial-intelligence", label: "Spatial Fusion", icon: Layers },
    { href: "/targets", label: "Targets", icon: Compass },
    { href: "/planner", label: "Route Planner", icon: Route },
    { href: "/mission-readiness", label: "EVA & Replan", icon: ShieldAlert },
    { href: "/evidence", label: "Evidence", icon: GitBranch },
  ];

  return (
    <div className="border-b border-[#1e2638] bg-[#0e121c]/95 px-6 md:px-8 py-2 flex flex-wrap items-center justify-between gap-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
          Mission Context
        </span>
        <span className="px-2 py-0.5 rounded bg-[#141a29] border border-[#232d45] font-mono text-slate-200 truncate max-w-[14rem]">
          Q: {activeQuestionId}
        </span>
        <span className="px-2 py-0.5 rounded bg-[#141a29] border border-[#232d45] font-mono text-slate-300 truncate max-w-[13rem]">
          DEM: {effectiveDatasetId}
        </span>
        {effectiveCampaignId && (
          <span className="px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-500/30 font-mono text-cyan-200">
            Camp: {effectiveCampaignId} · v{activeLifecycle?.plan_version ?? activeCampaign?.plan_version ?? 1}
          </span>
        )}
        {effectiveMissionId && (
          <span className="px-2 py-0.5 rounded bg-indigo-950/40 border border-indigo-500/30 font-mono text-indigo-200">
            EVA: {effectiveMissionId}
          </span>
        )}
        {effectiveLifecycleState && (
          <span
            className={`px-2 py-0.5 rounded border font-mono text-[10px] uppercase ${lifecycleTone(
              effectiveLifecycleState
            )}`}
          >
            {effectiveLifecycleState}
          </span>
        )}
        {isStale && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-amber-500/50 bg-amber-500/20 text-amber-200 font-mono text-[10px]">
            <AlertTriangle className="w-3 h-3" />
            STALE — RECOMPUTE REQUIRED
          </span>
        )}
        {hasContextMismatch && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-rose-500/50 bg-rose-500/20 text-rose-200 font-mono text-[10px]">
            <AlertTriangle className="w-3 h-3" />
            CAMPAIGN / EVA CONTEXT MISMATCH
          </span>
        )}
        {activeCampaign && !activeCampaign.operator_approved && (
          <button
            type="button"
            disabled={loadingApprove}
            onClick={() => void approveCampaign(activeCampaign.campaign_id)}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-200 font-mono text-[10px] disabled:opacity-50"
          >
            <CheckCircle2 className="w-3 h-3" />
            {loadingApprove ? "Approving..." : "Approve Plan"}
          </button>
        )}
      </div>

      <nav className="flex flex-wrap items-center gap-1">
        {stages.map((st) => {
          const Icon = st.icon;
          const active = pathname === st.href;
          return (
            <Link
              key={st.href}
              href={`${st.href}${linkQuery}`}
              className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-mono transition ${
                active
                  ? "border-[#e25b38]/60 bg-[#e25b38]/20 text-white"
                  : "border-[#1e2638] bg-[#121622] text-slate-300 hover:border-slate-600 hover:text-white"
              }`}
            >
              <Icon className="w-3 h-3" />
              {st.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
