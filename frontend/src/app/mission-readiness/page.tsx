"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Eye,
  GitCompare,
  Layers,
  Loader2,
  Mountain,
  ShieldAlert,
} from "lucide-react";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import { PageHeader } from "@/components/PageHeader";
import { API_BASE_URL } from "@/lib/constants";
import { useEvidenceStore } from "@/stores/useEvidenceStore";
import { useRoutingStore } from "@/stores/useRoutingStore";

export default function MissionReadinessPage() {
  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const selectedMode = activeRoute?.mode ?? "balanced";

  const {
    corridorAssessment,
    routeComparison,
    missionDossier,
    selectedSegmentId,
    loadingCorridor,
    loadingComparison,
    loadingDossier,
    error,
    overlays,
    setSelectedSegmentId,
    toggleOverlay,
    assessCorridor,
    compareRoutesEvidence,
    generateMissionDossier,
  } = useEvidenceStore();

  const [corridorWidthM, setCorridorWidthM] = useState<number>(60);
  const [searchRadiusM, setSearchRadiusM] = useState<number>(250);
  const [walkingSpeedMps, setWalkingSpeedMps] = useState<string>("");
  const [durationLimitS, setDurationLimitS] = useState<string>("");
  const [reserveFrac, setReserveFrac] = useState<string>("");
  const [suitMassKg, setSuitMassKg] = useState<string>("");
  const [payloadMassKg, setPayloadMassKg] = useState<string>("");

  const effectiveStart = startPoint ?? { lat: -4.749, lon_east: 137.394, label: "Gale Boxwork Start" };
  const effectiveDest = destinationPoint ?? { lat: -4.756, lon_east: 137.399, label: "Mount Sharp Target" };

  const selectedSegment = useMemo(
    () =>
      corridorAssessment?.segments.find((s) => s.segment_id === selectedSegmentId) ??
      corridorAssessment?.segments[0] ??
      null,
    [corridorAssessment, selectedSegmentId]
  );

  const parseOptNum = (raw: string): number | null => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const val = Number(trimmed);
    return Number.isFinite(val) ? val : null;
  };

  const handleAssessCorridor = () => {
    assessCorridor({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
    });
  };

  const handleCompareRoutes = () => {
    compareRoutesEvidence({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
    });
  };

  const handleGenerateDossier = () => {
    generateMissionDossier({
      mission_name: "Gale Boxwork Traverse Assessment",
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
      walking_speed_mps: parseOptNum(walkingSpeedMps),
      mission_duration_limit_s: parseOptNum(durationLimitS),
      return_reserve_fraction: parseOptNum(reserveFrac),
      astronaut_suit_mass_kg: parseOptNum(suitMassKg),
      payload_mass_kg: parseOptNum(payloadMassKg),
    });
  };

  const opticalDataset = corridorAssessment?.dataset_inventory.find(
    (d) => d.acquired && (d.product_type === "HiRISE_ORTHO" || d.product_type === "ORTHO")
  );
  const opticalCropUrl =
    selectedSegment && opticalDataset
      ? `${API_BASE_URL}/terrain/optical-crop?dataset_id=${encodeURIComponent(
          opticalDataset.dataset_id
        )}&min_lat=${Math.min(selectedSegment.start_coord.lat, selectedSegment.end_coord.lat) - 0.001}&max_lat=${
          Math.max(selectedSegment.start_coord.lat, selectedSegment.end_coord.lat) + 0.001
        }&min_lon=${Math.min(selectedSegment.start_coord.lon_east, selectedSegment.end_coord.lon_east) - 0.001}&max_lon=${
          Math.max(selectedSegment.start_coord.lon_east, selectedSegment.end_coord.lon_east) + 0.001
        }`
      : null;

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title="Marswalk Evidence Intelligence & Mission Readiness"
        badge="EVD"
        description="Corridor hazard characterization, resolution adequacy, Curiosity observation association & reproducible Mission Dossier"
      />

      {/* Readiness & Controls */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <ClipboardCheck className="h-4 w-4 text-cyan-400" />
              <span>Corridor & Mission Assumptions (Explicitly Configured Only)</span>
            </div>
            <div className="text-xs font-mono text-slate-400">
              DEM: {selectedDemDatasetId} · Start ({effectiveStart.lat.toFixed(4)}, {effectiveStart.lon_east.toFixed(4)}°E) → Dest ({effectiveDest.lat.toFixed(4)}, {effectiveDest.lon_east.toFixed(4)}°E)
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <label className="space-y-1">
              <span className="text-slate-400">Corridor Width (m)</span>
              <input
                type="number"
                value={corridorWidthM}
                min={10}
                max={500}
                onChange={(e) => setCorridorWidthM(Number(e.target.value) || 60)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">Obs Search Radius (m)</span>
              <input
                type="number"
                value={searchRadiusM}
                min={10}
                max={5000}
                onChange={(e) => setSearchRadiusM(Number(e.target.value) || 250)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">Walking Speed (m/s, opt)</span>
              <input
                type="number"
                step="0.05"
                placeholder="Unset (no silent default)"
                value={walkingSpeedMps}
                onChange={(e) => setWalkingSpeedMps(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">EVA Duration Limit (s, opt)</span>
              <input
                type="number"
                placeholder="Unset"
                value={durationLimitS}
                onChange={(e) => setDurationLimitS(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">Return Reserve (0–1, opt)</span>
              <input
                type="number"
                step="0.05"
                placeholder="Unset"
                value={reserveFrac}
                onChange={(e) => setReserveFrac(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">Astronaut+Suit Mass (kg, opt)</span>
              <input
                type="number"
                placeholder="Unset"
                value={suitMassKg}
                onChange={(e) => setSuitMassKg(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-slate-400">Payload Mass (kg, opt)</span>
              <input
                type="number"
                placeholder="Unset"
                value={payloadMassKg}
                onChange={(e) => setPayloadMassKg(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleAssessCorridor}
              disabled={loadingCorridor}
              className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              {loadingCorridor ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Compass className="h-3.5 w-3.5" />}
              Assess Corridor Evidence
            </button>
            <button
              onClick={handleCompareRoutes}
              disabled={loadingComparison}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              {loadingComparison ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitCompare className="h-3.5 w-3.5" />}
              Compare Candidate Routes
            </button>
            <button
              onClick={handleGenerateDossier}
              disabled={loadingDossier}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3.5 py-2 text-xs font-semibold text-white disabled:opacity-50"
            >
              {loadingDossier ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Generate Mission Dossier
            </button>
            <Link
              href="/planner"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
            >
              Edit Start/Destination in Planner →
            </Link>
          </div>

          {error && (
            <div className="rounded-lg border border-rose-800 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">
              {error}
            </div>
          )}
        </div>

        {/* Readiness State Card */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Mission Readiness State
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                missionDossier?.readiness_state === "ASSESSED"
                  ? "bg-emerald-900/70 text-emerald-300 border border-emerald-700"
                  : missionDossier?.readiness_state === "INSUFFICIENT_EVIDENCE"
                  ? "bg-rose-900/70 text-rose-300 border border-rose-700"
                  : "bg-amber-900/70 text-amber-300 border border-amber-700"
              }`}
            >
              {missionDossier?.readiness_state ?? "NOT_ASSESSED"}
            </span>
          </div>

          <div className="rounded-lg border border-amber-800/60 bg-amber-950/30 p-2.5 text-[11px] text-amber-200 flex items-start gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" />
            <span>
              {missionDossier?.safety_certification_note ??
                "UNVERIFIED / NOT SAFETY CERTIFIED — analytical decision-support only."}
            </span>
          </div>

          {missionDossier ? (
            <div className="space-y-2 text-xs">
              <div className="text-slate-300 font-mono text-[11px]">
                Dossier ID: {missionDossier.dossier_id}
              </div>
              {missionDossier.missing_inputs.length > 0 && (
                <div className="text-amber-300">
                  Missing user inputs: {missionDossier.missing_inputs.join(", ")}
                </div>
              )}
              <ul className="list-disc pl-4 space-y-1 text-slate-400">
                {missionDossier.readiness_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              Click <strong>Generate Mission Dossier</strong> to evaluate physical energy budgets,
              corridor evidence coverage, and missing mission assumptions.
            </p>
          )}
        </div>
      </div>

      {/* 3D Terrain + Evidence Overlay Toggles */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Layers className="h-4 w-4 text-cyan-400" />
            <span>3D Terrain & Synchronized Evidence Overlays</span>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {(
              [
                ["showCorridor", "Corridor Bounds"],
                ["showSegments", "Segments"],
                ["showGaps", "Data Gaps"],
                ["showTerrainCandidates", "Terrain Candidates"],
                ["showOpticalCandidates", "Optical Candidates"],
                ["showObservations", "Curiosity Obs"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => toggleOverlay(key)}
                className={`rounded px-2.5 py-1 border ${
                  overlays[key]
                    ? "border-cyan-500 bg-cyan-950/60 text-cyan-200"
                    : "border-slate-700 bg-slate-950 text-slate-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="h-[420px] rounded-lg overflow-hidden border border-slate-800">
          <LocalTerrain3DViewer />
        </div>
        {!activeRoute && (
          <div className="text-[11px] text-slate-400">
            Tip: Run <strong>Assess Corridor Evidence</strong> to overlay the corridor polygon,
            segments, gaps, and Curiosity observations directly onto the 3D terrain.
          </div>
        )}
      </div>

      {/* Route Evidence Comparison Table */}
      {routeComparison && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <GitCompare className="h-4 w-4 text-indigo-400" />
              Evidence-Based Candidate Route Comparison ({routeComparison.source_product_id})
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              {routeComparison.compute_time_ms.toFixed(1)} ms
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 pr-3">Mode</th>
                  <th className="py-2 pr-3">Surface Dist</th>
                  <th className="py-2 pr-3">+Gain / -Loss</th>
                  <th className="py-2 pr-3">Max Slope</th>
                  <th className="py-2 pr-3">Max 5m-TRI</th>
                  <th className="py-2 pr-3">DEM Cov</th>
                  <th className="py-2 pr-3">Obs</th>
                  <th className="py-2 pr-3">Gaps</th>
                  <th className="py-2">Composite Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {routeComparison.entries.map((entry) => (
                  <tr key={entry.mode} className="text-slate-200">
                    <td className="py-2 pr-3 font-medium">{entry.mode_label}</td>
                    <td className="py-2 pr-3 font-mono">
                      {entry.feasible ? `${entry.surface_distance_m?.toFixed(1)} m` : "INFEASIBLE"}
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {entry.feasible
                        ? `+${entry.elevation_gain_m?.toFixed(1)} / -${entry.elevation_loss_m?.toFixed(1)} m`
                        : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {entry.max_slope_deg != null ? `${entry.max_slope_deg.toFixed(1)}°` : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {entry.max_tri_m != null ? `${entry.max_tri_m.toFixed(2)} m` : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {entry.terrain_coverage_fraction != null
                        ? `${(entry.terrain_coverage_fraction * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="py-2 pr-3 font-mono">{entry.associated_observation_count}</td>
                    <td className="py-2 pr-3 font-mono">{entry.data_gap_count}</td>
                    <td className="py-2 text-amber-300/90 text-[11px]">{entry.composite_risk_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="list-disc pl-4 text-xs text-slate-300 space-y-1">
            {routeComparison.tradeoff_explanations.map((t, idx) => (
              <li key={idx}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Corridor Segments + Selected Segment & Optical Crop Inspector */}
      {corridorAssessment && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <Mountain className="h-4 w-4 text-cyan-400" />
              Corridor Segments ({corridorAssessment.segments.length} · scale {corridorAssessment.segment_scale_m} m)
            </h2>
            <div className="max-h-80 overflow-y-auto space-y-1.5 pr-1">
              {corridorAssessment.segments.map((seg) => {
                const active = selectedSegment?.segment_id === seg.segment_id;
                return (
                  <button
                    key={seg.segment_id}
                    onClick={() => setSelectedSegmentId(seg.segment_id)}
                    className={`w-full text-left rounded-lg border px-3 py-2 text-xs transition ${
                      active
                        ? "border-cyan-500 bg-cyan-950/40"
                        : "border-slate-800 bg-slate-950/50 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-slate-100">{seg.segment_id}</span>
                      <span className="text-slate-400">
                        {seg.surface_distance_m.toFixed(1)} m · max slope{" "}
                        {seg.max_slope_deg != null ? `${seg.max_slope_deg.toFixed(1)}°` : "N/A"} · 5m-TRI{" "}
                        {seg.max_tri_m != null ? `${seg.max_tri_m.toFixed(2)} m` : "N/A"}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-slate-400">
                      <span>
                        DEM {(seg.valid_data_coverage_fraction * 100).toFixed(0)}% · Obs{" "}
                        {seg.associated_observation_ids.length} · Candidates{" "}
                        {seg.morphology_candidate_ids.length + seg.optical_candidate_ids.length}
                      </span>
                      {seg.unverified_area_present && (
                        <span className="text-amber-300 flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" /> Unverified gap
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <Eye className="h-4 w-4 text-fuchsia-400" />
              Segment Evidence & Optical Crop ({selectedSegment?.segment_id ?? "None"})
            </h2>
            {selectedSegment && (
              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-2 font-mono text-slate-300">
                  <div>Elev Δ: {selectedSegment.elevation_change_m ?? "N/A"} m</div>
                  <div>Local Relief: {selectedSegment.local_relief_m ?? "N/A"} m</div>
                  <div>Mean Slope: {selectedSegment.mean_slope_deg ?? "N/A"}°</div>
                  <div>Curvature: {selectedSegment.mean_profile_curvature_inv_m ?? "N/A"} 1/m</div>
                </div>
                <div className="text-[11px] text-slate-400">
                  {selectedSegment.uncertainty_summary} · {selectedSegment.coverage.geological_map_scale_note}
                </div>
                {opticalCropUrl && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-400">
                      Derived HiRISE Optical Candidate Overlay Crop (server PNG):
                    </div>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={opticalCropUrl}
                      alt={`Optical crop for ${selectedSegment.segment_id}`}
                      className="w-full max-h-52 object-contain rounded border border-slate-800 bg-black"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Physical Energy Budget & Dataset Validation Inventory */}
      {missionDossier && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-2 text-xs">
            <h2 className="text-sm font-semibold text-slate-100">
              Mechanical Gravitational Potential Energy Budget
            </h2>
            {missionDossier.physical_energy_budget.available ? (
              <div className="grid grid-cols-2 gap-2 font-mono text-slate-200">
                <div>Total Mass: {missionDossier.physical_energy_budget.input_total_mass_kg} kg</div>
                <div>Mars Weight: {missionDossier.physical_energy_budget.surface_weight_n} N</div>
                <div>+ΔPE (climb): +{missionDossier.physical_energy_budget.gravitational_pe_increase_j} J</div>
                <div>-ΔPE (descent): {missionDossier.physical_energy_budget.gravitational_pe_decrease_j} J</div>
                <div>Net ΔPE: {missionDossier.physical_energy_budget.net_gravitational_pe_change_j} J</div>
                <div>g: {missionDossier.physical_energy_budget.mars_gravity_m_s2} m/s²</div>
              </div>
            ) : (
              <div className="rounded border border-amber-800/60 bg-amber-950/30 p-2.5 text-amber-200">
                {missionDossier.physical_energy_budget.unavailable_reason}
              </div>
            )}
            <p className="text-[11px] text-slate-400">{missionDossier.physical_energy_budget.disclaimer}</p>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-2 text-xs">
            <h2 className="text-sm font-semibold text-slate-100">
              Dataset Validation Stage Audit ({missionDossier.corridor_assessment.dataset_inventory.length})
            </h2>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {missionDossier.corridor_assessment.dataset_inventory.map((ds) => (
                <div
                  key={ds.dataset_id}
                  className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/50 px-2.5 py-1.5 font-mono text-[11px]"
                >
                  <span className="text-slate-200 truncate max-w-[55%]">{ds.dataset_id}</span>
                  <span className={ds.renderable ? "text-emerald-400" : ds.acquired ? "text-amber-300" : "text-slate-500"}>
                    {ds.renderable ? "RENDERABLE" : ds.acquired ? "ACQUIRED" : "CATALOGUED_ONLY"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
