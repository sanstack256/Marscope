"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Database, RefreshCw, Telescope } from "lucide-react";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import { Observation, ScienceTarget } from "../../types";

export default function TargetExplorerPage() {
  const [targets, setTargets] = useState<ScienceTarget[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scientific Targets & Observations"
        badge={`${targets.length} Targets · ${observations.length} Observations`}
        description="Parsed NASA in-situ rover measurements and verified science targets. Displays zero synthetic records when no observation product is acquired locally."
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

      {error && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/50 text-xs text-red-200">
          {error}
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
