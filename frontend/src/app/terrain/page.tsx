"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Database, Layers, Mountain, RefreshCw } from "lucide-react";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import { PhysicsParameter, TerrainSummaryResponse } from "../../types";

interface TerrainLayerRow {
  layer_id: string;
  name: string;
  layer_type: string;
  source_dataset_id: string;
  source_product_id: string;
  units: string;
  min_val?: number | null;
  max_val?: number | null;
  width: number;
  height: number;
  bounds: number[];
  resolution_m: number;
  crs: string;
  processing_version: string;
}

export default function TerrainIntelligencePage() {
  const [summaryResp, setSummaryResp] = useState<TerrainSummaryResponse | null>(null);
  const [layers, setLayers] = useState<TerrainLayerRow[]>([]);
  const [parameters, setParameters] = useState<PhysicsParameter[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  async function loadTerrain(showSpinner = true) {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const [sRes, lRes, pRes] = await Promise.all([
        fetch(`${API_BASE_URL}/terrain/summary`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/terrain/layers`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/parameters`, { cache: "no-store" }),
      ]);
      if (!sRes.ok) throw new Error(`HTTP ${sRes.status} loading terrain summary`);
      setSummaryResp(await sRes.json());
      if (lRes.ok) setLayers(await lRes.json());
      if (pRes.ok) setParameters(await pRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch terrain intelligence");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [sRes, lRes, pRes] = await Promise.all([
          fetch(`${API_BASE_URL}/terrain/summary`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/terrain/layers`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/parameters`, { cache: "no-store" }),
        ]);
        if (!active) return;
        if (!sRes.ok) throw new Error(`HTTP ${sRes.status} loading terrain summary`);
        setSummaryResp(await sRes.json());
        if (lRes.ok) setLayers(await lRes.json());
        if (pRes.ok) setParameters(await pRes.json());
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to fetch terrain intelligence");
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  const slopeThresholdParam = parameters.find(
    (p) => p.id === "nasa_eva_nominal_slope_limit" || p.id.includes("slope")
  );
  const summary = summaryResp?.available ? summaryResp.summary : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Terrain Intelligence"
        badge={summary ? `${summary.resolution_meters_per_pixel.toFixed(0)} m/px Validated DEM` : "Awaiting DEM"}
        description="Resolution-aware planetary DEM statistics, Horn slope gradients, compass-aligned downhill aspect, and metric Terrain Ruggedness Index (TRI)."
        actions={
          <button
            type="button"
            onClick={() => void loadTerrain()}
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

      {!loading && summaryResp && !summaryResp.available && (
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-700/40 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1 text-xs">
              <div className="font-semibold text-amber-200">No Processed DEM Available</div>
              <p className="text-amber-100/80 leading-relaxed">
                {summaryResp.unavailable_reason}
              </p>
              <Link
                href="/evidence"
                className="inline-flex items-center gap-1.5 mt-2 px-3 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-white font-semibold"
              >
                <Database className="w-3.5 h-3.5" />
                <span>Go to Evidence &amp; Acquisition</span>
              </Link>
            </div>
          </div>
          <EmptyState
            title="Terrain Analytics Require a Validated DEM"
            message="MARSCOPE never synthesizes fallback elevation grids. Download a verified PDS DEM product (such as MOLA MEGDR) and run terrain processing to populate elevation, slope, aspect, and TRI metrics."
            icon={Mountain}
          />
        </div>
      )}

      {summary && (
        <>
          {/* Source & Provenance Header */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">Source DEM Product</div>
              <div className="text-sm font-bold font-mono text-slate-100 mt-1 truncate">
                {summary.source_product_id || summary.source_dem_id}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">{summary.study_area_name}</div>
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">Coordinate System</div>
              <div className="text-sm font-bold font-mono text-[#38bdf8] mt-1">{summary.crs}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                {summary.resolution_meters_per_pixel.toFixed(2)} m/px · TRI window {summary.roughness_window_radius_meters?.toFixed(0) ?? "--"} m
              </div>
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">Critical Slope Coverage</div>
              <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                {summary.critical_slope_coverage_pct !== null && summary.critical_slope_coverage_pct !== undefined
                  ? `${summary.critical_slope_coverage_pct.toFixed(2)}% > ${summary.critical_slope_threshold_deg}°`
                  : "--"}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                {slopeThresholdParam ? `Ref param: ${slopeThresholdParam.value} ${slopeThresholdParam.units}` : "Derived over valid cells"}
              </div>
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">Processing Version</div>
              <div className="text-sm font-bold font-mono text-emerald-300 mt-1">{summary.processing_version}</div>
              <div className="text-[11px] text-slate-400 mt-1">Valid pixels: {summary.elevation_stats.valid_pixel_count.toLocaleString()}</div>
            </div>
          </div>

          {/* Derivative Stats Table */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: "Elevation", stats: summary.elevation_stats },
              { title: "Horn Slope", stats: summary.slope_stats },
              { title: "Compass Aspect (CW N)", stats: summary.aspect_stats },
              { title: "Roughness (Metric TRI)", stats: summary.roughness_stats },
            ].map(({ title, stats }) => (
              <div key={title} className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-100">{title}</span>
                  <span className="text-[10px] font-mono text-slate-400">{stats?.units ?? "--"}</span>
                </div>
                {stats && stats.available ? (
                  <div className="space-y-1 text-xs font-mono">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Min</span>
                      <span className="text-slate-100">{stats.min_value?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Mean</span>
                      <span className="text-slate-100">{stats.mean_value?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Max</span>
                      <span className="text-slate-100">{stats.max_value?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Std Dev</span>
                      <span className="text-slate-100">{stats.std_dev?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between pt-1 border-t border-[#1e2638] text-[10px]">
                      <span className="text-slate-500">Valid Coverage</span>
                      <span className="text-emerald-300">{stats.valid_data_percentage.toFixed(1)}%</span>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Unavailable (0 valid cells)</p>
                )}
              </div>
            ))}
          </div>

          {summary.quality_warnings.length > 0 && (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-bold text-slate-200">Quality &amp; Uncertainty Notes</div>
              {summary.quality_warnings.map((w, i) => (
                <p key={i} className="text-xs text-slate-400 font-mono">
                  • {w}
                </p>
              ))}
            </div>
          )}

          {/* Processed Terrain Layers */}
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
                <Layers className="w-4 h-4 text-[#e25b38]" />
                <span>Renderable Processed Raster Layers ({layers.length})</span>
              </div>
              <Link href="/explorer" className="text-xs text-[#38bdf8] hover:underline">
                View on 3D Globe →
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {layers.map((layer) => (
                <div key={layer.layer_id} className="p-3 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-100">{layer.name}</span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {layer.width}×{layer.height} px · {layer.units}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-slate-500">
                    Bounds: [{layer.bounds.map((b) => b.toFixed(2)).join(", ")}] · {layer.crs}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
