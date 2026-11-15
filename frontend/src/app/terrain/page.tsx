"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  Compass,
  Database,
  Layers,
  Mountain,
  RefreshCw,
  Sliders,
} from "lucide-react";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import {
  CoverageIntelligenceResponse,
  ElevationProfileResponse,
  MobilityEvaluationResponse,
  MobilityScenario,
  MobilityStatusResponse,
  TerrainSummaryResponse,
} from "../../types";

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
  const [mobilityStatus, setMobilityStatus] = useState<MobilityStatusResponse | null>(null);
  const [scenarios, setScenarios] = useState<MobilityScenario[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Coverage Intelligence state
  const [selectedCoverageDatasetId, setSelectedCoverageDatasetId] = useState<string>("");
  const [covBounds, setCovBounds] = useState({
    min_lat: "-5.5",
    max_lat: "-4.3",
    min_lon: "137.2",
    max_lon: "138.0",
  });
  const [coverageResp, setCoverageResp] = useState<CoverageIntelligenceResponse | null>(null);
  const [covLoading, setCovLoading] = useState<boolean>(false);

  // Elevation Profile state
  const [profStartLat, setProfStartLat] = useState("-4.5895");
  const [profStartLon, setProfStartLon] = useState("137.4417");
  const [profEndLat, setProfEndLat] = useState("-5.0800");
  const [profEndLon, setProfEndLon] = useState("137.8500");
  const [profSamples, setProfSamples] = useState("20");
  const [profileResp, setProfileResp] = useState<ElevationProfileResponse | null>(null);
  const [profLoading, setProfLoading] = useState<boolean>(false);

  // Mobility Scenario & Evaluation state (no silent defaults for walking speed!)
  const [scenName, setScenName] = useState("Gale Regional Transect Assumption");
  const [scenSpeed, setScenSpeed] = useState("");
  const [scenMaxSlope, setScenMaxSlope] = useState("");
  const [scenMaxRough, setScenMaxRough] = useState("");
  const [scenBodyMass, setScenBodyMass] = useState("75");
  const [scenSuitMass, setScenSuitMass] = useState("55");
  const [scenLoadMass, setScenLoadMass] = useState("10");
  const [evalResp, setEvalResp] = useState<MobilityEvaluationResponse | null>(null);
  const [evalLoading, setEvalLoading] = useState<boolean>(false);

  async function loadTerrain(showSpinner = true) {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const [sRes, lRes, mRes, scRes] = await Promise.all([
        fetch(`${API_BASE_URL}/terrain/summary`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/terrain/layers`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/mobility/status`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/mobility/scenarios`, { cache: "no-store" }),
      ]);
      if (!sRes.ok) throw new Error(`HTTP ${sRes.status} loading terrain summary`);
      setSummaryResp(await sRes.json());
      if (lRes.ok) setLayers(await lRes.json());
      let resolvedId = selectedCoverageDatasetId;
      if (mRes.ok) {
        const mobData: MobilityStatusResponse = await mRes.json();
        setMobilityStatus(mobData);
        if (!resolvedId) {
          resolvedId =
            mobData.active_dem_dataset_id ||
            mobData.terrain_inventory.find((d) => d.locally_processed)?.dataset_id ||
            "";
          if (resolvedId) setSelectedCoverageDatasetId(resolvedId);
        }
      }
      if (scRes.ok) setScenarios(await scRes.json());
      if (resolvedId) {
        const cRes = await fetch(
          `${API_BASE_URL}/mobility/coverage?dataset_id=${encodeURIComponent(
            resolvedId
          )}&min_lat=${encodeURIComponent(covBounds.min_lat)}&max_lat=${encodeURIComponent(
            covBounds.max_lat
          )}&min_lon=${encodeURIComponent(covBounds.min_lon)}&max_lon=${encodeURIComponent(covBounds.max_lon)}`,
          { cache: "no-store" }
        );
        if (cRes.ok) setCoverageResp(await cRes.json());
      } else {
        setCoverageResp(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch terrain & mobility intelligence");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [sRes, lRes, mRes, scRes] = await Promise.all([
          fetch(`${API_BASE_URL}/terrain/summary`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/terrain/layers`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/mobility/status`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/mobility/scenarios`, { cache: "no-store" }),
        ]);
        if (!active) return;
        if (!sRes.ok) throw new Error(`HTTP ${sRes.status} loading terrain summary`);
        setSummaryResp(await sRes.json());
        if (lRes.ok) setLayers(await lRes.json());
        let resolvedId = "";
        if (mRes.ok) {
          const mobData: MobilityStatusResponse = await mRes.json();
          setMobilityStatus(mobData);
          resolvedId =
            mobData.active_dem_dataset_id ||
            mobData.terrain_inventory.find((d) => d.locally_processed)?.dataset_id ||
            "";
          if (resolvedId) setSelectedCoverageDatasetId(resolvedId);
        }
        if (scRes.ok) setScenarios(await scRes.json());
        if (resolvedId) {
          const cRes = await fetch(
            `${API_BASE_URL}/mobility/coverage?dataset_id=${encodeURIComponent(
              resolvedId
            )}&min_lat=-5.5&max_lat=-4.3&min_lon=137.2&max_lon=138.0`,
            { cache: "no-store" }
          );
          if (active && cRes.ok) setCoverageResp(await cRes.json());
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to fetch terrain & mobility intelligence");
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  async function runCoverageQuery(customBounds?: {
    min_lat: string;
    max_lat: string;
    min_lon: string;
    max_lon: string;
  }) {
    const b = customBounds || covBounds;
    if (customBounds) setCovBounds(customBounds);
    const targetId =
      selectedCoverageDatasetId ||
      mobilityStatus?.active_dem_dataset_id ||
      mobilityStatus?.terrain_inventory.find((d) => d.locally_processed)?.dataset_id ||
      "";
    if (!targetId) {
      setError("Select a locally processed DEM dataset before querying spatial coverage.");
      return;
    }
    setCovLoading(true);
    try {
      const q = new URLSearchParams({
        dataset_id: targetId,
        min_lat: b.min_lat,
        max_lat: b.max_lat,
        min_lon: b.min_lon,
        max_lon: b.max_lon,
      });
      const res = await fetch(`${API_BASE_URL}/mobility/coverage?${q.toString()}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} evaluating coverage`);
      setCoverageResp(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Coverage evaluation failed");
    } finally {
      setCovLoading(false);
    }
  }

  async function runElevationProfile() {
    setProfLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/mobility/elevation-profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: {
            lat: parseFloat(profStartLat),
            lon: parseFloat(profStartLon),
            label: "Transect Start",
          },
          end: {
            lat: parseFloat(profEndLat),
            lon: parseFloat(profEndLon),
            label: "Transect End",
          },
          sample_count: Math.max(2, parseInt(profSamples, 10) || 20),
          sampling_method: "nearest",
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setProfileResp(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Elevation profile computation failed");
    } finally {
      setProfLoading(false);
    }
  }

  async function runScenarioEvaluation() {
    setEvalLoading(true);
    setError(null);
    try {
      const speedVal = scenSpeed.trim() !== "" ? parseFloat(scenSpeed) : null;
      const maxSlopeVal = scenMaxSlope.trim() !== "" ? parseFloat(scenMaxSlope) : null;
      const maxRoughVal = scenMaxRough.trim() !== "" ? parseFloat(scenMaxRough) : null;
      const bodyMassVal = scenBodyMass.trim() !== "" ? parseFloat(scenBodyMass) : null;
      const suitMassVal = scenSuitMass.trim() !== "" ? parseFloat(scenSuitMass) : null;
      const loadMassVal = scenLoadMass.trim() !== "" ? parseFloat(scenLoadMass) : null;

      const inlineScenario: Record<string, unknown> = {
        name: scenName || "User Configured Scenario",
        version: "1.0.0",
        reference_walking_speed_m_per_s: speedVal,
        walking_speed_provenance:
          speedVal !== null
            ? `Explicitly configured by user in Terrain & Mobility Intelligence UI (${speedVal} m/s)`
            : "Not configured (user left walking speed blank)",
        planning_max_slope_deg: maxSlopeVal,
        planning_max_roughness_m: maxRoughVal,
        astronaut_body_mass_kg: bodyMassVal,
        suit_mass_kg: suitMassVal,
        carried_load_mass_kg: loadMassVal,
      };

      const res = await fetch(`${API_BASE_URL}/mobility/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          inline_scenario: inlineScenario,
          waypoints: [
            { lat: parseFloat(profStartLat), lon: parseFloat(profStartLon), label: "Start" },
            { lat: parseFloat(profEndLat), lon: parseFloat(profEndLon), label: "End" },
          ],
          sample_count: Math.max(2, parseInt(profSamples, 10) || 20),
          sampling_method: "nearest",
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || `HTTP ${res.status}`)
        );
      }
      const data: MobilityEvaluationResponse = await res.json();
      setEvalResp(data);
      if (data.elevation_profile) {
        setProfileResp(data.elevation_profile);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mobility scenario evaluation failed");
    } finally {
      setEvalLoading(false);
    }
  }

  const summary = summaryResp?.available ? summaryResp.summary : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Terrain & Human Mobility Intelligence"
        badge={
          summary
            ? `${summary.resolution_meters_per_pixel.toFixed(0)} m/px Validated DEM · Mobility v${
                mobilityStatus?.engine_version || "1.0.0"
              }`
            : "Awaiting DEM"
        }
        description="Spatially explicit planetary DEM characterization, resolution suitability analysis, 5-state coverage intelligence, elevation gain/loss transects, and assumption-transparent human traversal modelling (no route optimization or safety certification)."
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/spatial-intelligence"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-xs font-medium text-cyan-200"
            >
              <span>Spatial Intelligence →</span>
            </Link>
            <button
              type="button"
              onClick={() => void loadTerrain()}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-xs font-medium text-slate-200 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
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
              <p className="text-amber-100/80 leading-relaxed">{summaryResp.unavailable_reason}</p>
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
                {summary.resolution_meters_per_pixel.toFixed(2)} m/px · TRI window{" "}
                {summary.roughness_window_radius_meters?.toFixed(0) ?? "--"} m
              </div>
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">
                Optional Planning Slope Threshold
              </div>
              <div className="text-sm font-bold font-mono text-slate-100 mt-1">
                {summary.planning_threshold && summary.planning_threshold_coverage_pct != null
                  ? `${summary.planning_threshold_coverage_pct.toFixed(2)}% > ${summary.planning_threshold.threshold_deg}°`
                  : "Not Configured"}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                No default safety slope limit assumed (user-configured planning assumption only)
              </div>
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4">
              <div className="text-[10px] font-mono uppercase text-slate-400">Processing & Policy</div>
              <div className="text-sm font-bold font-mono text-emerald-300 mt-1">
                v{summary.processing_version} · no_expansion_v1
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Valid pixels: {summary.elevation_stats.valid_pixel_count.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Derivative Stats Table */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { title: "Elevation", stats: summary.elevation_stats },
              { title: "Horn 3x3 Slope", stats: summary.slope_stats },
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

          {/* DEM Inventory & Resolution Suitability Matrix */}
          {mobilityStatus && mobilityStatus.terrain_inventory.length > 0 && (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-slate-100">
                    DEM Resolution Suitability & Scale Honesty Matrix
                  </h2>
                  <p className="text-xs text-slate-400">
                    Coarse orbital DEMs (~14.8 km native / ~6.6 km gridded pixel spacing) are never presented as local human-scale hazard maps.
                  </p>
                </div>
                <span className="text-[10px] font-mono px-2 py-1 rounded bg-[#161c2b] border border-[#252f44] text-slate-300">
                  Route Optimization: Disabled · Safety Certification: Disabled
                </span>
              </div>

              {mobilityStatus.terrain_inventory.map((item) => (
                <div key={item.dataset_id} className="p-4 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="text-xs font-bold text-slate-100">{item.product_title}</span>
                      <span className="ml-2 text-[11px] font-mono text-slate-400">
                        ({item.product_id} · {item.mission} / {item.instrument})
                      </span>
                    </div>
                    <span className="text-[11px] font-mono text-sky-300">
                      Native: {item.native_horizontal_resolution_m?.toFixed(0) ?? "--"} m · Gridded:{" "}
                      {item.effective_equatorial_pixel_m?.toFixed(1) ?? "--"} m/px
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                    {Object.entries(item.resolution_suitability).map(([scaleKey, rec]) => (
                      <div
                        key={scaleKey}
                        className={`p-3 rounded-lg border text-xs space-y-1 ${
                          rec.supported
                            ? "bg-emerald-950/20 border-emerald-700/40"
                            : "bg-amber-950/20 border-amber-700/40"
                        }`}
                      >
                        <div className="font-mono font-semibold text-slate-100">{scaleKey}</div>
                        <div
                          className={`text-[10px] font-mono uppercase ${
                            rec.supported ? "text-emerald-300" : "text-amber-300"
                          }`}
                        >
                          {rec.suitability} (min rec: ≤{rec.minimum_recommended_resolution_m} m)
                        </div>
                        <p className="text-[11px] text-slate-300 leading-snug">{rec.explanation}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 5-State Spatial Coverage & Footprint Honesty Inspector */}
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-bold text-slate-100">
                  5-State Spatial Coverage &amp; Unknown-Data Intelligence
                </h2>
                <p className="text-xs text-slate-400">
                  Evaluates exact requested bounds without silent footprint expansion. Regions smaller than 3×3 source pixels return a structured InsufficientCoverageReport.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    void runCoverageQuery({
                      min_lat: "-4.60",
                      max_lat: "-4.55",
                      min_lon: "137.35",
                      max_lon: "137.40",
                    })
                  }
                  className="px-2.5 py-1 rounded bg-amber-950/50 hover:bg-amber-900/50 border border-amber-700/50 text-[11px] text-amber-200"
                >
                  Test Small Box (&lt;3×3 px)
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void runCoverageQuery({
                      min_lat: "-5.5",
                      max_lat: "-4.3",
                      min_lon: "137.2",
                      max_lon: "138.0",
                    })
                  }
                  className="px-2.5 py-1 rounded bg-sky-950/50 hover:bg-sky-900/50 border border-sky-700/50 text-[11px] text-sky-200"
                >
                  Query Regional Gale Box (≥3×3 px)
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
              <select
                value={selectedCoverageDatasetId}
                onChange={(e) => setSelectedCoverageDatasetId(e.target.value)}
                aria-label="DEM Dataset for Coverage Query"
                className="px-2.5 py-1.5 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
              >
                <option value="">Select Processed DEM...</option>
                {(mobilityStatus?.terrain_inventory || []).map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.dataset_id} ({d.locally_processed ? "processed" : d.status})
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={covBounds.min_lat}
                onChange={(e) => setCovBounds({ ...covBounds, min_lat: e.target.value })}
                placeholder="Min Lat"
                className="px-2.5 py-1.5 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
              />
              <input
                type="text"
                value={covBounds.max_lat}
                onChange={(e) => setCovBounds({ ...covBounds, max_lat: e.target.value })}
                placeholder="Max Lat"
                className="px-2.5 py-1.5 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
              />
              <input
                type="text"
                value={covBounds.min_lon}
                onChange={(e) => setCovBounds({ ...covBounds, min_lon: e.target.value })}
                placeholder="Min Lon (°E)"
                className="px-2.5 py-1.5 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
              />
              <input
                type="text"
                value={covBounds.max_lon}
                onChange={(e) => setCovBounds({ ...covBounds, max_lon: e.target.value })}
                placeholder="Max Lon (°E)"
                className="px-2.5 py-1.5 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
              />
              <button
                type="button"
                onClick={() => void runCoverageQuery()}
                disabled={covLoading}
                className="px-3 py-1.5 rounded bg-[#e25b38] hover:bg-[#cf4f2e] text-white font-semibold disabled:opacity-50"
              >
                {covLoading ? "Checking..." : "Evaluate Coverage"}
              </button>
            </div>

            {coverageResp && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 text-xs font-mono">
                  {Object.entries(coverageResp.coverage_state_counts).map(([stateKey, cnt]) => (
                    <div key={stateKey} className="p-2.5 rounded bg-[#0d111a] border border-[#1d2536]">
                      <div className="text-[10px] text-slate-400 break-all">{stateKey}</div>
                      <div className="text-sm font-bold text-slate-100 mt-1">{cnt} px</div>
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap gap-4 text-xs font-mono text-slate-300">
                  <span>Requested Area: {coverageResp.requested_area_km2.toFixed(1)} km²</span>
                  <span>Covered Area: {coverageResp.covered_area_km2.toFixed(1)} km²</span>
                  <span>
                    Valid Derivatives: {coverageResp.valid_derivative_area_km2.toFixed(1)} km² (
                    {coverageResp.valid_derivative_percentage_of_requested.toFixed(1)}%)
                  </span>
                  <span>Bounds Modified: {String(coverageResp.requested_bounds_modified)}</span>
                </div>

                {coverageResp.insufficient_coverage_report && (
                  <div className="p-3.5 rounded-lg bg-amber-950/30 border border-amber-700/50 space-y-1.5 text-xs">
                    <div className="font-bold text-amber-200">
                      Structured InsufficientCoverageReport (Requested Footprint Never Enlarged)
                    </div>
                    <p className="text-amber-100/90 font-mono">
                      {coverageResp.insufficient_coverage_report.insufficient_coverage_reason}
                    </p>
                    <p className="text-slate-300">
                      Unsupported Derivatives:{" "}
                      {coverageResp.insufficient_coverage_report.unsupported_derivative_products.join(", ")} · Next
                      Action: {coverageResp.insufficient_coverage_report.next_action}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Elevation Profile &Configurable Mobility Scenario Evaluation */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Spatially Explicit Elevation Profile & Gain/Loss */}
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                <h2 className="text-sm font-bold text-slate-100">
                  Spatially Explicit Elevation Profile &amp; Gain/Loss Transect
                </h2>
              </div>
              <p className="text-xs text-slate-400">
                Computes geodesic horizontal distance, cumulative positive elevation gain, cumulative negative elevation loss, and net elevation change between two coordinates without route optimization.
              </p>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                <div>
                  <label className="text-[10px] text-slate-400">Start Lat (°)</label>
                  <input
                    type="text"
                    value={profStartLat}
                    onChange={(e) => setProfStartLat(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Start Lon (°E)</label>
                  <input
                    type="text"
                    value={profStartLon}
                    onChange={(e) => setProfStartLon(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">End Lat (°)</label>
                  <input
                    type="text"
                    value={profEndLat}
                    onChange={(e) => setProfEndLat(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">End Lon (°E)</label>
                  <input
                    type="text"
                    value={profEndLon}
                    onChange={(e) => setProfEndLon(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Samples</label>
                  <input
                    type="text"
                    value={profSamples}
                    onChange={(e) => setProfSamples(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
              </div>

              <button
                type="button"
                onClick={() => void runElevationProfile()}
                disabled={profLoading}
                className="px-3.5 py-1.5 rounded bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-xs font-semibold text-sky-200 disabled:opacity-50"
              >
                {profLoading ? "Sampling DEM Transect..." : "Compute Elevation Gain/Loss Profile"}
              </button>

              {profileResp && (
                <div className="p-3.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2.5 text-xs font-mono">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <div>
                      <span className="text-[10px] text-slate-400 block">Horizontal Dist</span>
                      <span className="text-slate-100 font-bold">
                        {(profileResp.total_horizontal_distance_meters / 1000).toFixed(2)} km
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Positive Gain (+Δz)</span>
                      <span className="text-emerald-300 font-bold">
                        +{profileResp.total_positive_elevation_gain_meters?.toFixed(1) ?? "N/A"} m
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Elevation Loss (-Δz)</span>
                      <span className="text-amber-300 font-bold">
                        -{profileResp.total_negative_elevation_change_meters?.toFixed(1) ?? "N/A"} m
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Net Δz</span>
                      <span className="text-sky-300 font-bold">
                        {profileResp.net_elevation_change_meters?.toFixed(1) ?? "N/A"} m
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Min / Max Elev</span>
                      <span className="text-slate-200">
                        {profileResp.min_elevation_meters?.toFixed(0) ?? "--"} /{" "}
                        {profileResp.max_elevation_meters?.toFixed(0) ?? "--"} m
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 block">Valid Samples</span>
                      <span className="text-slate-200">
                        {profileResp.valid_sample_count} / {profileResp.sample_count}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Configurable Mobility Scenario & Traversal Model Evaluator */}
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-[#e25b38]" />
                  <h2 className="text-sm font-bold text-slate-100">
                    Configurable MobilityScenario &amp; Traversal Estimator
                  </h2>
                </div>
                <span className="text-[10px] font-mono text-slate-400">
                  Saved Scenarios: {scenarios.length}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Walking speed has no silent default: leave blank to verify that physical work (ΔPE = m·g·Δh) is computed while traversal time is withheld as insufficient_scenario_parameters.
              </p>

              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div className="col-span-2 md:col-span-3">
                  <label className="text-[10px] text-slate-400">Scenario Name</label>
                  <input
                    type="text"
                    value={scenName}
                    onChange={(e) => setScenName(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Walking Speed (m/s, optional)</label>
                  <input
                    type="text"
                    value={scenSpeed}
                    onChange={(e) => setScenSpeed(e.target.value)}
                    placeholder="e.g. 0.8 (or blank)"
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Planning Max Slope (°)</label>
                  <input
                    type="text"
                    value={scenMaxSlope}
                    onChange={(e) => setScenMaxSlope(e.target.value)}
                    placeholder="Optional (no default)"
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Planning Max TRI (m)</label>
                  <input
                    type="text"
                    value={scenMaxRough}
                    onChange={(e) => setScenMaxRough(e.target.value)}
                    placeholder="Optional (no default)"
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Body Mass (kg)</label>
                  <input
                    type="text"
                    value={scenBodyMass}
                    onChange={(e) => setScenBodyMass(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Suit Mass (kg)</label>
                  <input
                    type="text"
                    value={scenSuitMass}
                    onChange={(e) => setScenSuitMass(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400">Carried Load (kg)</label>
                  <input
                    type="text"
                    value={scenLoadMass}
                    onChange={(e) => setScenLoadMass(e.target.value)}
                    className="w-full px-2 py-1 rounded bg-[#0d111a] border border-[#252f44] font-mono text-slate-100"
                  />
                </div>
              </div>

              <button
                type="button"
                onClick={() => void runScenarioEvaluation()}
                disabled={evalLoading}
                className="px-3.5 py-1.5 rounded bg-[#e25b38] hover:bg-[#cf4f2e] text-xs font-semibold text-white disabled:opacity-50"
              >
                {evalLoading ? "Evaluating Scenario..." : "Evaluate Transect Under Scenario"}
              </button>

              {evalResp && (
                <div className="p-3.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2.5 text-xs font-mono">
                  <div className="text-[11px] font-bold text-sky-300">
                    1. Physical Measurements (Scenario-Independent, g ={" "}
                    {evalResp.scenario.mars_surface_gravity_m_s2} m/s²)
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      Total Mass / Weight:{" "}
                      {evalResp.scenario.total_mass_kg != null
                        ? `${evalResp.scenario.total_mass_kg.toFixed(1)} kg (${evalResp.scenario.mars_surface_weight_n?.toFixed(1)} N)`
                        : "Mass not configured"}
                    </div>
                    <div>
                      Positive Gravitational Work:{" "}
                      {evalResp.physical_measurements.cumulative_positive_potential_energy_joules != null
                        ? `${(
                            Number(evalResp.physical_measurements.cumulative_positive_potential_energy_joules) / 1000
                          ).toFixed(2)} kJ`
                        : "N/A"}
                    </div>
                  </div>

                  <div className="text-[11px] font-bold text-amber-300 pt-1 border-t border-[#1e2638]">
                    2. Scenario Traversal Estimates (Model: {evalResp.traversal_model_id} v
                    {evalResp.traversal_model_version})
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      Ref Walking Speed:{" "}
                      {evalResp.scenario.reference_walking_speed_m_per_s != null
                        ? `${evalResp.scenario.reference_walking_speed_m_per_s} m/s`
                        : "Withheld (Not Configured)"}
                    </div>
                    <div>
                      Estimated Time:{" "}
                      {evalResp.scenario_traversal_estimates.total_adjusted_time_seconds != null
                        ? `${(
                            Number(evalResp.scenario_traversal_estimates.total_adjusted_time_seconds) / 3600
                          ).toFixed(2)} h (${Number(
                            evalResp.scenario_traversal_estimates.total_adjusted_time_seconds
                          ).toFixed(0)} s)`
                        : "Withheld (Insufficient Scenario Parameters)"}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {summary.quality_warnings.length > 0 && (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-1.5">
              <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                <Compass className="w-3.5 h-3.5 text-amber-400" />
                <span>Quality, Resolution &amp; Uncertainty Notes</span>
              </div>
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
