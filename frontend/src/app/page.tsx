"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Compass,
  Database,
  Globe2,
  Layers,
  Mountain,
  Telescope,
} from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { API_BASE_URL } from "../lib/constants";
import {
  Dataset,
  LayerCatalogResponse,
  LocalizationStatusResponse,
  Observation,
  SystemHealth,
  TerrainSummaryResponse,
} from "../types";

export default function MissionOverviewPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [layers, setLayers] = useState<LayerCatalogResponse | null>(null);
  const [terrain, setTerrain] = useState<TerrainSummaryResponse | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [localization, setLocalization] = useState<LocalizationStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadOverview() {
      setLoading(true);
      setError(null);
      try {
        const [hRes, dRes, lRes, tRes, oRes, locRes] = await Promise.all([
          fetch(`${API_BASE_URL}/health`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/layers`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/terrain/summary`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/localization/status`, { cache: "no-store" }),
        ]);

        if (!active) return;

        if (hRes.ok) setHealth(await hRes.json());
        if (dRes.ok) setDatasets(await dRes.json());
        if (lRes.ok) setLayers(await lRes.json());
        if (tRes.ok) setTerrain(await tRes.json());
        if (oRes.ok) setObservations(await oRes.json());
        if (locRes.ok) setLocalization(await locRes.json());
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to connect to MARSCOPE backend");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    loadOverview();
    return () => {
      active = false;
    };
  }, []);

  const downloadedCount = datasets.filter(
    (d) => d.verification?.download_verification === "verified"
  ).length;
  const processedCount = datasets.filter(
    (d) => d.verification?.processing_verification === "verified"
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Mission Overview"
        badge={health ? `Backend ${health.version}` : "Connecting..."}
        description="Martian Surface Intelligence & Exploration System. Operational indicators below reflect only verified catalog state, local raster products, and live service telemetry."
        actions={
          <Link
            href="/explorer"
            className="flex items-center gap-2 text-xs font-semibold px-3.5 py-2 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-white transition-colors"
          >
            <Globe2 className="w-4 h-4" />
            <span>Open Mars Surface Explorer</span>
          </Link>
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/50 text-xs text-red-200">
          Backend API Error: {error}
        </div>
      )}

      {/* Live Telemetry / Readiness Cards (Zero hardcoded facts) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold uppercase tracking-wider">API Status</span>
            <Activity className="w-4 h-4 text-[#38bdf8]" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100">
            {loading ? "..." : health ? health.status.toUpperCase() : "UNREACHABLE"}
          </div>
          <div className="text-[11px] text-slate-400">
            {health
              ? `Physics: ${health.engines.physics} · Geo: ${health.engines.geospatial}`
              : "Awaiting backend health check"}
          </div>
        </div>

        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold uppercase tracking-wider">Map Layers</span>
            <Layers className="w-4 h-4 text-[#e25b38]" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100">
            {layers ? `${layers.total_available} / ${layers.total_available + layers.total_unavailable}` : "--"}
          </div>
          <div className="text-[11px] text-slate-400">
            {layers
              ? `${layers.total_available} renderable · ${layers.total_unavailable} pending`
              : "Querying /api/layers"}
          </div>
        </div>

        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold uppercase tracking-wider">Validated DEM</span>
            <Mountain className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100">
            {terrain === null ? "--" : terrain.available && terrain.summary ? `${terrain.summary.resolution_meters_per_pixel.toFixed(0)} m/px` : "UNAVAILABLE"}
          </div>
          <div className="text-[11px] text-slate-400 truncate">
            {terrain?.available && terrain.summary
              ? `${terrain.summary.source_product_id || terrain.summary.source_dem_id}`
              : "No processed local DEM yet"}
          </div>
        </div>

        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="font-semibold uppercase tracking-wider">Observations & Pos</span>
            <Telescope className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-xl font-bold font-mono text-slate-100">
            {observations.length} parsed
          </div>
          <div className="text-[11px] text-slate-400 truncate">
            {localization?.current_position
              ? `Manual Pos: ${localization.current_position.latitude?.toFixed(2)}°, ${localization.current_position.longitude?.toFixed(2)}°`
              : "Live Localization: Unavailable"}
          </div>
        </div>
      </div>

      {/* Dataset Pipeline Readiness */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-[#1e2638] pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-100">Dataset Verification & Processing Readiness</h2>
              <p className="text-xs text-slate-400">
                {datasets.length} discovered · {downloadedCount} downloaded locally · {processedCount} processed into terrain products
              </p>
            </div>
            <Link
              href="/evidence"
              className="text-xs font-medium text-[#38bdf8] hover:underline flex items-center gap-1"
            >
              <span>Manage Pipeline</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          <div className="space-y-2.5">
            {datasets.map((ds) => (
              <div
                key={ds.id}
                className="p-3 rounded-lg bg-[#0e121b] border border-[#1c2436] flex flex-wrap items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slate-100 truncate">{ds.product_title}</div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {ds.product_id} · {ds.source_archive} · {ds.license}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <StatusBadge
                    status={ds.verification?.download_verification === "verified" ? "verified" : "unverified"}
                    label={`DL: ${ds.verification?.download_verification || "unverified"}`}
                  />
                  <StatusBadge
                    status={ds.verification?.processing_verification === "verified" ? "verified" : "unverified"}
                    label={`Proc: ${ds.verification?.processing_verification || "unverified"}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Honest Subsystems Navigation */}
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <h2 className="text-sm font-bold text-slate-100 border-b border-[#1e2638] pb-3">
            Exploration Workflows
          </h2>
          <Link
            href="/explorer"
            className="block p-3 rounded-lg bg-[#161c2b] hover:bg-[#1c2438] border border-[#242e44] transition-colors"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
              <Globe2 className="w-4 h-4 text-[#e25b38]" />
              <span>Interactive 3D Mars Explorer</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Inspect global orbital imagery, DEM overlays, coordinates, and localization providers.
            </p>
          </Link>
          <Link
            href="/evidence"
            className="block p-3 rounded-lg bg-[#161c2b] hover:bg-[#1c2438] border border-[#242e44] transition-colors"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
              <Database className="w-4 h-4 text-[#38bdf8]" />
              <span>Evidence & NASA Acquisition</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Verify remote capabilities, download PDS3/WMTS products, and compute DEM derivatives.
            </p>
          </Link>
          <Link
            href="/terrain"
            className="block p-3 rounded-lg bg-[#161c2b] hover:bg-[#1c2438] border border-[#242e44] transition-colors"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
              <Mountain className="w-4 h-4 text-emerald-400" />
              <span>Terrain & Slope Intelligence</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Review real DEM statistics, aspect distributions, and resolution-aware TRI roughness.
            </p>
          </Link>
          <Link
            href="/settings"
            className="block p-3 rounded-lg bg-[#161c2b] hover:bg-[#1c2438] border border-[#242e44] transition-colors"
          >
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
              <Compass className="w-4 h-4 text-amber-400" />
              <span>Traceable Physics Constants</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">
              Inspect NASA GSFC / MSL parameter registry entries and run surface physics models.
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
