"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Database, RefreshCw, Route as RouteIcon, ShieldAlert, ShieldCheck, Sparkles, Telescope } from "lucide-react";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { Observation, ScienceTarget } from "../../types";

export default function TargetExplorerPage() {
  const selectedTargetIds = useRoutingStore((s) => s.selectedTargetIds);
  const toggleTargetId = useRoutingStore((s) => s.toggleTargetId);
  const setDestinationPoint = useRoutingStore((s) => s.setDestinationPoint);
  const [targets, setTargets] = useState<ScienceTarget[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);
  const [genQuery, setGenQuery] = useState<string>("Fe");
  const [includeHostMinerals, setIncludeHostMinerals] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [tRes, oRes] = await Promise.all([
        fetch(`${API_BASE_URL}/targets`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
      ]);
      if (tRes.ok) setTargets(await tRes.json());
      if (oRes.ok) setObservations(await oRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load targets/observations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [tRes, oRes] = await Promise.all([
          fetch(`${API_BASE_URL}/targets`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
        ]);
        if (!active) return;
        if (tRes.ok) setTargets(await tRes.json());
        if (oRes.ok) setObservations(await oRes.json());
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load targets/observations");
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  async function handleGenerateTargets(e: React.FormEvent) {
    e.preventDefault();
    if (!genQuery.trim()) return;
    setGenerating(true);
    setError(null);
    setStatusMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/targets/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: genQuery.trim(),
          max_targets: 8,
          include_element_bearing_minerals: includeHostMinerals,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status} generating targets`);
      }
      const created: ScienceTarget[] = await res.json();
      setStatusMessage(
        `Generated ${created.length} evidence-backed target(s) for "${genQuery.trim()}".`
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate evidence-backed targets");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scientific Targets & Observations"
        badge={`${targets.length} Targets · ${observations.length} Observations`}
        description="Evidence-backed targets generated from the verified Composition Spatial Index alongside parsed NASA in-situ rover measurements. Manual unverified registrations are strictly separated."
        actions={
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-xs font-medium text-slate-200 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        }
      />

      {/* Generate Targets from Composition Index */}
      <form
        onSubmit={handleGenerateTargets}
        className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 flex flex-wrap items-center gap-3"
      >
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
          <Sparkles className="w-4 h-4 text-[#e25b38]" />
          <span>Generate Evidence-Backed Targets:</span>
        </div>
        <input
          type="text"
          value={genQuery}
          onChange={(e) => setGenQuery(e.target.value)}
          placeholder="e.g., Fe, SO3, gypsum, hematite"
          className="px-2.5 py-1.5 text-xs rounded bg-[#0d111a] border border-[#252f44] text-slate-100 w-48"
        />
        <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={includeHostMinerals}
            onChange={(e) => setIncludeHostMinerals(e.target.checked)}
          />
          <span>+Host minerals</span>
        </label>
        <button
          type="submit"
          disabled={generating}
          className="px-3 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-xs font-semibold text-white disabled:opacity-50"
        >
          {generating ? "Generating..." : "Generate from Index"}
        </button>
      </form>

      {statusMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-700/50 text-xs text-emerald-200">
          {statusMessage}
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/50 text-xs text-red-200">
          {error}
        </div>
      )}

      {targets.length > 0 && (
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <div className="text-sm font-bold text-slate-100">
            Registered Scientific Targets ({targets.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {targets.map((tgt) => {
              const isEvidenceBacked = tgt.target_status === "evidence_backed";
              return (
                <div
                  key={tgt.id}
                  className="p-3.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-xs font-bold text-slate-100">{tgt.name}</div>
                      <div className="text-[10px] font-mono text-slate-400">
                        {tgt.latitude.toFixed(4)}°, {tgt.longitude.toFixed(4)}°E · {tgt.crs || "IAU2000:49900"}
                      </div>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border shrink-0 ${
                        isEvidenceBacked
                          ? "bg-emerald-950/50 border-emerald-700/60 text-emerald-300"
                          : "bg-amber-950/50 border-amber-700/60 text-amber-300"
                      }`}
                    >
                      {isEvidenceBacked ? (
                        <ShieldCheck className="w-3 h-3" />
                      ) : (
                        <ShieldAlert className="w-3 h-3" />
                      )}
                      <span>
                        {isEvidenceBacked ? "evidence_backed" : "manual_unverified_administrative"}
                      </span>
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-300 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span>
                      Species: {tgt.matched_species || tgt.geology_type} · Exploration Heuristic Priority:{" "}
                      {(tgt.exploration_priority_score ?? tgt.scientific_value) != null
                        ? (tgt.exploration_priority_score ?? tgt.scientific_value)!.toFixed(3)
                        : "N/A"}{" "}
                      · Instr: {tgt.instrument_source}
                      {tgt.distance_from_astronaut_m != null &&
                        ` · Dist: ${(tgt.distance_from_astronaut_m / 1000).toFixed(2)} km`}
                    </span>
                    {tgt.evidence_state && (
                      <span className="px-1.5 py-0.5 rounded border border-cyan-500/35 bg-cyan-500/10 text-cyan-300 text-[9px] uppercase">
                        {tgt.evidence_state}
                      </span>
                    )}
                    {tgt.prioritization_is_heuristic !== false && (
                      <span className="px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/10 text-amber-200 text-[9px] uppercase">
                        {tgt.prioritization_label || "engineering_heuristic"}
                      </span>
                    )}
                  </div>
                  {tgt.explanation && (
                    <div className="text-[10px] text-slate-400 leading-relaxed">{tgt.explanation}</div>
                  )}
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <span className="text-[10px] font-mono text-slate-500 truncate">
                      Evidence IDs: {tgt.evidence_ids?.length ? tgt.evidence_ids.slice(0, 4).join(", ") : "None (administrative)"}
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => toggleTargetId(tgt.id)}
                        className={`px-2 py-1 rounded text-[10px] font-mono border transition-colors ${
                          selectedTargetIds.includes(tgt.id)
                            ? "bg-purple-600/30 border-purple-400 text-purple-200"
                            : "bg-[#161c2b] border-[#252f44] text-slate-300 hover:border-purple-400/50"
                        }`}
                      >
                        {selectedTargetIds.includes(tgt.id) ? "In Route ✓" : "+ Add to Route"}
                      </button>
                      <Link
                        href="/planner"
                        onClick={() =>
                          setDestinationPoint({
                            lat: tgt.latitude,
                            lon_east: tgt.longitude,
                            label: tgt.name,
                            target_id: tgt.id,
                          })
                        }
                        className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono bg-[#e25b38]/20 border border-[#e25b38]/40 text-[#f38d72] hover:bg-[#e25b38]/35"
                      >
                        <RouteIcon className="w-3 h-3" />
                        <span>Route Here</span>
                      </Link>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!loading && observations.length === 0 && targets.length === 0 && (
        <div className="space-y-4">
          <EmptyState
            title="No Verified In-Situ Observations Loaded"
            message="No Curiosity ChemCam/REMS or MRO CRISM observation files have been downloaded into datasets/raw/. Acquire a supported NASA PDS observation product in Evidence & Provenance to parse genuine measurements."
            icon={Telescope}
          />
          <div className="flex justify-center">
            <Link
              href="/evidence"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-xs font-semibold text-white"
            >
              <Database className="w-4 h-4" />
              <span>Acquire Observation Datasets</span>
            </Link>
          </div>
        </div>
      )}

      {observations.length > 0 && (
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <div className="text-sm font-bold text-slate-100">
            Parsed Scientific Observations ({observations.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {observations.map((obs) => (
              <div
                key={obs.observation_id}
                className="p-3.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold font-mono text-slate-100">{obs.observation_id}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950/60 text-sky-300 border border-sky-800/50">
                    {obs.mission} / {obs.instrument}
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {obs.sol !== null && obs.sol !== undefined ? `Sol ${obs.sol}` : "Sol N/A"} ·{" "}
                  {obs.observation_timestamp || "Timestamp N/A"} · {obs.measurement_type} ({obs.units})
                </div>
                <div className="text-[10px] font-mono text-slate-300 bg-[#121622] p-2 rounded border border-[#1e2638] overflow-x-auto">
                  {JSON.stringify(obs.measurement_value)}
                </div>
                <div className="text-[10px] text-slate-500">
                  {obs.location
                    ? `Location: ${obs.location.latitude.toFixed(4)}°, ${obs.location.longitude.toFixed(4)}° (${obs.crs || "CRS unspecified"})`
                    : "Geolocation: Not included in parsed observation record"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
