"use client";

import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileCheck2,
  Radio,
  RefreshCw,
  ShieldAlert,
  Sliders,
  Thermometer,
  XCircle,
} from "lucide-react";
import { useEvaOperationsStore, type EvaEvaluateParams } from "@/stores/useEvaOperationsStore";

interface Props {
  activeParams?: EvaEvaluateParams | null;
}

const EVENT_TYPES = [
  "HAZARD_MARKED_BY_OPERATOR",
  "CORRIDOR_BLOCKED",
  "SLOPE_LIMIT_CHANGED",
  "ROUGHNESS_LIMIT_CHANGED",
  "WALKING_SPEED_CHANGED",
  "SCIENCE_STOP_DURATION_CHANGED",
  "RESOURCE_RATE_OR_INVENTORY_CHANGED",
  "RESERVE_POLICY_CHANGED",
  "OBSTACLE_REVIEW_CHANGED",
  "MANUAL_REPLAN_REQUESTED",
];

function statusTone(status: string | undefined): string {
  const s = (status || "").toUpperCase();
  if (
    s.includes("FEASIBLE_UNDER") ||
    s.includes("WITHIN") ||
    s === "EVALUATED" ||
    s === "ROBUST_ACROSS_CONFIGURED_PERTURBATIONS" ||
    s === "ACTIVE" ||
    s === "LIVE"
  ) {
    return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
  }
  if (
    s.includes("INFEASIBLE") ||
    s.includes("EXCEEDS") ||
    s.includes("FAILED") ||
    s.includes("REPLANNING_REQUIRED")
  ) {
    return "border-red-500/40 bg-red-500/15 text-red-300";
  }
  if (
    s.includes("STALE") ||
    s.includes("REVIEW_REQUIRED") ||
    s.includes("SENSITIVE") ||
    s.includes("MODELLED") ||
    s.includes("USER_ASSUMED")
  ) {
    return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  }
  return "border-slate-700 bg-slate-800/80 text-slate-300";
}

export function Prompt20OperationalPanels({ activeParams }: Props) {
  const {
    evaEnvelope,
    lastEvalParams,
    missionSession,
    pendingComparison,
    sensitivityReport,
    operationsDossier,
    telemetryStatus,
    environmentalContext,
    loadingReplan,
    loadingSensitivity,
    loadingDossier,
    fetchSensitivity,
    fetchTelemetryStatus,
    exportOperationsDossier,
    recordMissionEvent,
    previewReplan,
    approveReplan,
    rejectReplan,
  } = useEvaOperationsStore();

  const [eventType, setEventType] = useState<string>("HAZARD_MARKED_BY_OPERATOR");
  const [eventDesc, setEventDesc] = useState<string>(
    "Operator flagged loose regolith talus pocket along outbound bench; review contingency corridor."
  );
  const [replanSpeedMps, setReplanSpeedMps] = useState<string>(
    activeParams?.walking_speed_mps ? String(activeParams.walking_speed_mps) : ""
  );

  if (!evaEnvelope) {
    return null;
  }

  const missionId = evaEnvelope.mission_id;
  const effTelemetry = telemetryStatus ?? evaEnvelope.telemetry_state ?? null;
  const effEnv = environmentalContext ?? evaEnvelope.environmental_context ?? null;
  const travAnalytics = evaEnvelope.traversability_analytics ?? {};
  const soilProps = (travAnalytics.unmeasured_soil_properties ?? {}) as Record<string, string>;
  const categoryCoverage = evaEnvelope.resource_budget.category_coverage ?? {};

  const handleExportDownload = async () => {
    const dossier = await exportOperationsDossier(missionId);
    if (!dossier) return;
    const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dossier.mission_id}_v${dossier.plan_version}_operations_dossier.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="space-y-4" data-testid="prompt20-operational-intelligence">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyan-400" />
          Prompt 20 · Human Marswalk Operational Intelligence, Dynamic Replanning & Epistemic Governance
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded border px-2 py-0.5 font-mono text-[10px] ${statusTone(
              evaEnvelope.model_feasibility_status
            )}`}
            data-testid="p20-model-feasibility-badge"
          >
            Model Status: {evaEnvelope.model_feasibility_status ?? evaEnvelope.envelope_status}
          </span>
          <span
            className={`rounded border px-2 py-0.5 font-mono text-[10px] ${statusTone(
              missionSession?.workflow_state ?? evaEnvelope.workflow_state
            )}`}
          >
            Workflow: {missionSession?.workflow_state ?? evaEnvelope.workflow_state ?? "CONFIGURED"} (v
            {missionSession?.active_plan_version ?? evaEnvelope.plan_version ?? 1})
          </span>
          <button
            type="button"
            onClick={handleExportDownload}
            disabled={loadingDossier}
            className="inline-flex items-center gap-1.5 rounded border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1 text-[11px] font-mono text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            {loadingDossier ? "Exporting Dossier..." : "Export Operations Dossier (SHA-256 JSON)"}
          </button>
        </div>
      </div>

      {operationsDossier && (
        <div className="rounded-lg border border-emerald-500/35 bg-emerald-950/20 p-3 text-[11px] font-mono text-emerald-200 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileCheck2 className="h-4 w-4 text-emerald-400" />
            <span>
              Dossier Ready: {operationsDossier.dossier_id} · Schema{" "}
              {operationsDossier.dossier_schema_version}
            </span>
          </div>
          <span className="text-emerald-300 break-all">
            SHA-256: {operationsDossier.sha256_integrity_digest}
          </span>
        </div>
      )}

      {/* Row 1: Locomotion Scenarios + Parameter Provenance + Traversability/Soil Disclosures */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-7 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3 overflow-x-auto">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
              <Sliders className="h-4 w-4 text-cyan-400" />
              3-Category Locomotion Comparison & Provenance
            </h3>
            {evaEnvelope.locomotion_model && (
              <span className="font-mono text-[10px] text-amber-300">
                Active: {evaEnvelope.locomotion_model.model_id} (
                {evaEnvelope.locomotion_model.category ?? evaEnvelope.time_budget.locomotion_category})
              </span>
            )}
          </div>
          {evaEnvelope.locomotion_scenarios && evaEnvelope.locomotion_scenarios.length > 0 ? (
            <table className="w-full text-left text-[11px] border-collapse font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-1.5 pr-2">Scenario</th>
                  <th className="py-1.5 pr-2">Status</th>
                  <th className="py-1.5 pr-2">Epistemic Class</th>
                  <th className="py-1.5 pr-2">Total Traverse</th>
                  <th className="py-1.5">Disclosure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {evaEnvelope.locomotion_scenarios.map((sc) => (
                  <tr key={sc.scenario_id} className="text-slate-300">
                    <td className="py-1.5 pr-2 font-sans text-white">{sc.scenario_label}</td>
                    <td className="py-1.5 pr-2">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${statusTone(sc.status)}`}>
                        {sc.status}
                      </span>
                    </td>
                    <td className="py-1.5 pr-2">{sc.classification}</td>
                    <td className="py-1.5 pr-2">
                      {sc.total_traverse_duration_s != null
                        ? `${(sc.total_traverse_duration_s / 60).toFixed(1)} min`
                        : "UNAVAILABLE"}
                    </td>
                    <td className="py-1.5 font-sans text-slate-400">{sc.disclosure}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="text-xs text-slate-400">No multi-scenario locomotion table returned.</div>
          )}

          {evaEnvelope.parameter_provenance && evaEnvelope.parameter_provenance.length > 0 && (
            <div className="pt-2 space-y-1.5">
              <div className="text-[11px] font-semibold text-slate-300">
                Parameter Provenance Registry (Zero Silent Physical Defaults)
              </div>
              <div className="max-h-40 overflow-y-auto rounded border border-slate-800 bg-slate-900/50 p-2 space-y-1 font-mono text-[10px]">
                {evaEnvelope.parameter_provenance.map((p) => (
                  <div key={p.parameter_name} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-cyan-300">{p.parameter_name}</span>
                    <span className="text-slate-200">
                      {p.value !== null && p.value !== undefined ? `${String(p.value)} ${p.units}` : "UNAVAILABLE"}
                    </span>
                    <span className={`rounded border px-1.5 py-0.5 ${statusTone(p.classification)}`}>
                      {p.classification}
                    </span>
                    <span className="text-slate-400">{p.source_type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 10-State Traversability & Unmeasured Material Properties */}
        <div className="xl:col-span-5 rounded-xl border border-amber-500/30 bg-slate-950/75 p-4 space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
              <ShieldAlert className="h-4 w-4 text-amber-400" />
              Unmeasured Regolith &amp; Sub-Pixel Disclosures
            </h3>
            <span className="font-mono text-[10px] text-amber-300">
              Policy: {String(travAnalytics.unknown_terrain_policy ?? "EXCLUDE_UNKNOWN")}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
              <div className="text-slate-400 text-[10px]">Native DEM Posting</div>
              <div className="text-white">
                {travAnalytics.native_dem_resolution_m != null
                  ? `${Number(travAnalytics.native_dem_resolution_m).toFixed(2)} m/px`
                  : "—"}
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-2">
              <div className="text-slate-400 text-[10px]">Min Resolvable Feature (~3 px)</div>
              <div className="text-amber-300">
                {travAnalytics.minimum_resolvable_feature_width_m != null
                  ? `${Number(travAnalytics.minimum_resolvable_feature_width_m).toFixed(2)} m`
                  : "—"}
              </div>
            </div>
          </div>
          {travAnalytics.sub_pixel_hazard_disclosure && (
            <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2 text-[11px] text-amber-200">
              {String(travAnalytics.sub_pixel_hazard_disclosure)}
            </div>
          )}
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-slate-300">
              Surface Material Properties Explicitly Flagged UNKNOWN_UNMEASURED:
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 font-mono text-[10px]">
              {Object.entries(soilProps).map(([k, v]) => (
                <div
                  key={k}
                  className="flex items-center justify-between rounded border border-slate-800 bg-slate-900/60 px-2 py-1"
                >
                  <span className="text-slate-300">{k}</span>
                  <span className="text-amber-300">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: 11-Category Extensible Resource Matrix + Dynamic Mission Replanning */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-5 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">11-Category Extensible Resource Coverage</h3>
            <span className="font-mono text-[10px] text-slate-400">
              {Object.keys(categoryCoverage).length} categories
            </span>
          </div>
          <div className="grid grid-cols-1 gap-1.5 font-mono text-[10px]">
            {Object.entries(categoryCoverage).map(([cat, st]) => (
              <div
                key={cat}
                className="flex items-center justify-between rounded border border-slate-800 bg-slate-900/60 px-2.5 py-1"
              >
                <span className="text-slate-200">{cat}</span>
                <span className={`rounded border px-1.5 py-0.5 ${statusTone(st)}`}>{st}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Dynamic Replanning, Event Invalidation & Operator Approval Gate */}
        <div className="xl:col-span-7 rounded-xl border border-cyan-500/35 bg-slate-950/75 p-4 space-y-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
                <RefreshCw className="h-4 w-4 text-cyan-400" />
                Dynamic Mission Replanning &amp; Operator Confirmation Gate
              </h3>
              <p className="text-[11px] text-slate-400">
                Operational events mark dependent subsystems STALE and preserve prior plan versions until approved.
              </p>
            </div>
            {(missionSession?.stale || evaEnvelope.stale) && (
              <span className="rounded border border-amber-500/50 bg-amber-500/15 px-2 py-0.5 font-mono text-[10px] text-amber-200">
                STALE ({missionSession?.stale_subsystems.length ?? 0} subsystems)
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 text-[11px]">
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="sm:col-span-5 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100 font-mono"
            >
              {EVENT_TYPES.map((et) => (
                <option key={et} value={et}>
                  {et}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={eventDesc}
              onChange={(e) => setEventDesc(e.target.value)}
              className="sm:col-span-5 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100"
              placeholder="Event reason..."
            />
            <button
              type="button"
              onClick={() =>
                void recordMissionEvent(missionId, {
                  event_type: eventType,
                  description: eventDesc,
                  operator_id: "eva_flight_lead",
                })
              }
              disabled={loadingReplan}
              className="sm:col-span-2 rounded border border-amber-500/40 bg-amber-500/15 px-2 py-1.5 font-mono text-amber-200 hover:bg-amber-500/25 disabled:opacity-50"
            >
              Trigger Event
            </button>
          </div>

          {missionSession?.stale && (
            <div className="rounded border border-amber-500/40 bg-amber-950/25 p-2.5 text-[11px] space-y-1">
              <div className="font-semibold text-amber-200 flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" />
                Invalidated Subsystems: {missionSession.stale_subsystems.join(", ")}
              </div>
              <ul className="list-disc pl-4 text-amber-100/90 space-y-0.5">
                {missionSession.stale_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <label className="flex items-center gap-1.5 text-slate-300">
              <span>Candidate Walking Speed (m/s):</span>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="3.0"
                value={replanSpeedMps}
                onChange={(e) => setReplanSpeedMps(e.target.value)}
                className="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
              />
            </label>
            <button
              type="button"
                onClick={() => {
                const baseParams = activeParams ?? lastEvalParams;
                if (!baseParams) return;
                const spd = Number(replanSpeedMps);
                void previewReplan(missionId, {
                  reason: `Preview contingency replan from event '${eventType}'`,
                  updated_config: {
                    ...baseParams,
                    mission_id: missionId,
                    walking_speed_mps: Number.isFinite(spd) && spd > 0 ? spd : baseParams.walking_speed_mps,
                  },
                });
              }}
              disabled={loadingReplan}
              className="rounded border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1 font-mono text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50"
            >
              Preview Replan Comparison
            </button>
          </div>

          {pendingComparison && (
            <div className="rounded-lg border border-cyan-500/40 bg-slate-900/80 p-3 space-y-2 text-[11px]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-cyan-200">
                  Candidate Plan v{pendingComparison.candidate_plan_version} vs Active v
                  {pendingComparison.previous_plan_version}
                </span>
                <span className="font-mono text-slate-300">
                  Return Overlap: {(pendingComparison.route_overlap_fraction * 100).toFixed(1)}%
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[10px]">
                <div>Out Δ: {pendingComparison.outbound_distance_delta_m.toFixed(1)} m</div>
                <div>Ret Δ: {pendingComparison.return_distance_delta_m.toFixed(1)} m</div>
                <div>
                  Duration Δ:{" "}
                  {pendingComparison.total_mission_time_delta_s != null
                    ? `${pendingComparison.total_mission_time_delta_s.toFixed(1)} s`
                    : "N/A"}
                </div>
                <div>
                  Margin Δ:{" "}
                  {pendingComparison.remaining_time_margin_delta_s != null
                    ? `${pendingComparison.remaining_time_margin_delta_s.toFixed(1)} s`
                    : "N/A"}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => void approveReplan(missionId)}
                  disabled={loadingReplan}
                  className="inline-flex items-center gap-1 rounded bg-emerald-500/20 border border-emerald-500/50 px-2.5 py-1 font-mono text-emerald-200 hover:bg-emerald-500/30"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Approve &amp; Activate v{pendingComparison.candidate_plan_version}
                </button>
                <button
                  type="button"
                  onClick={() => void rejectReplan(missionId)}
                  disabled={loadingReplan}
                  className="inline-flex items-center gap-1 rounded bg-red-500/20 border border-red-500/50 px-2.5 py-1 font-mono text-red-200 hover:bg-red-500/30"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Reject Candidate
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Row 3: Telemetry Adapter + Environmental/Radiation Context + Sensitivity Stability */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 text-xs">
        <div className="xl:col-span-4 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
              <Radio className="h-4 w-4 text-cyan-400" />
              Conditional Telemetry Adapter
            </h3>
            <button
              type="button"
              onClick={() => void fetchTelemetryStatus(missionId)}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-[10px] text-slate-300 hover:bg-slate-800"
            >
              Refresh
            </button>
          </div>
          <div className="rounded border border-slate-800 bg-slate-900/60 p-2.5 font-mono text-[11px] space-y-1">
            <div className="flex justify-between">
              <span className="text-slate-400">Connection</span>
              <span className="text-amber-300">
                {effTelemetry?.connection_status ?? "TELEMETRY NOT CONNECTED"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Crew State</span>
              <span className="text-amber-300">
                {effTelemetry?.crew_state_status ?? "LIVE CREW STATE UNAVAILABLE"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Freshness</span>
              <span className="text-slate-200">{effTelemetry?.freshness_state ?? "NOT_CONNECTED"}</span>
            </div>
          </div>
          {(effTelemetry?.disclosures ?? []).map((d, i) => (
            <div key={i} className="text-[10px] text-slate-400">
              • {d}
            </div>
          ))}
        </div>

        <div className="xl:col-span-4 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2">
          <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
            <Thermometer className="h-4 w-4 text-amber-400" />
            Environmental &amp; Radiation Context
          </h3>
          <div className="rounded border border-slate-800 bg-slate-900/60 p-2.5 font-mono text-[11px] space-y-1">
            <div className="flex justify-between">
              <span className="text-slate-400">Live Surface Weather</span>
              <span className="text-amber-300">
                {effEnv?.live_weather_status ?? "LIVE SURFACE WEATHER UNAVAILABLE"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Live Radiation Telemetry</span>
              <span className="text-amber-300">
                {effEnv?.live_radiation_status ?? "LIVE RADIATION TELEMETRY UNAVAILABLE"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Archive GCR Ref Dose</span>
              <span className="text-cyan-300">
                {effEnv?.archive_reference_gcr_dose_usv != null
                  ? `${effEnv.archive_reference_gcr_dose_usv.toFixed(2)} uSv`
                  : "Supply walking speed"}
              </span>
            </div>
          </div>
          {effEnv?.radiation_calculation_note && (
            <div className="text-[10px] text-slate-300">{effEnv.radiation_calculation_note}</div>
          )}
        </div>

        <div className="xl:col-span-4 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Operational Sensitivity Stability</h3>
            <button
              type="button"
              onClick={() => void fetchSensitivity(missionId)}
              disabled={loadingSensitivity}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 font-mono text-[10px] text-slate-300 hover:bg-slate-800"
            >
              {loadingSensitivity ? "Running..." : "Re-run"}
            </button>
          </div>
          {sensitivityReport ? (
            <div className="space-y-1.5 text-[11px]">
              <div className="flex items-center justify-between font-mono">
                <span className="text-slate-400">Stability</span>
                <span
                  className={`rounded border px-1.5 py-0.5 text-[10px] ${statusTone(
                    sensitivityReport.stability_classification
                  )}`}
                >
                  {sensitivityReport.stability_classification}
                </span>
              </div>
              <div className="font-mono text-[10px] text-slate-300">
                Feasible: {sensitivityReport.feasible_scenario_count} · Infeasible:{" "}
                {sensitivityReport.infeasible_scenario_count} · Unavailable:{" "}
                {sensitivityReport.unavailable_or_incomplete_count}
              </div>
              {sensitivityReport.critical_drivers.map((cd, i) => (
                <div key={i} className="rounded border border-red-500/30 bg-red-950/20 px-2 py-1 text-[10px] text-red-200">
                  {cd}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-slate-400">Click Re-run to compute perturbation envelope.</div>
          )}
        </div>
      </div>
    </section>
  );
}
