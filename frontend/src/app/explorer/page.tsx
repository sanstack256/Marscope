"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Compass,
  Crosshair,
  Database,
  Eye,
  EyeOff,
  FlaskConical,
  Layers,
  MapPin,
  RefreshCw,
  Search,
  Sliders,
  Trash2,
} from "lucide-react";
import { MarsGlobeViewer } from "../../components/MarsGlobeViewer";
import { API_BASE_URL } from "../../lib/constants";
import { useLayerStore } from "../../stores/useLayerStore";
import { useMissionStore } from "../../stores/useMissionStore";
import { CompositionSearchResponse } from "../../types";

type ExplorerTab = "layers" | "inspect" | "minerals";

export default function SurfaceExplorerPage() {
  const [activeTab, setActiveTab] = useState<ExplorerTab>("layers");
  const [searchLat, setSearchLat] = useState<string>("-4.65");
  const [searchLon, setSearchLon] = useState<string>("137.42");
  const [searchLabel, setSearchLabel] = useState<string>("");
  const [manualLat, setManualLat] = useState<string>("");
  const [manualLon, setManualLon] = useState<string>("");
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyFeedback, setVerifyFeedback] = useState<string | null>(null);

  const [compositionQuery, setCompositionQuery] = useState<string>("smectite");
  const [compositionLoading, setCompositionLoading] = useState<boolean>(false);
  const [compositionResult, setCompositionResult] = useState<CompositionSearchResponse | null>(null);
  const [compositionError, setCompositionError] = useState<string | null>(null);

  const {
    availableLayers,
    unavailableLayers,
    layerStates,
    layerOrder,
    loading: layersLoading,
    error: layersError,
    fetchLayers,
    toggleLayer,
    setLayerOpacity,
    moveLayerOrder,
    clearTileErrors,
  } = useLayerStore();

  const {
    selectedDestination,
    destinationLoading,
    destinationError,
    localizationStatus,
    localizationError,
    evaluateDestination,
    clearDestination,
    fetchLocalizationStatus,
    setManualPosition,
    clearManualPosition,
  } = useMissionStore();

  useEffect(() => {
    void fetchLayers();
    void fetchLocalizationStatus();
  }, [fetchLayers, fetchLocalizationStatus]);

  const orderedAvailableLayers = layerOrder
    .map((id) => availableLayers.find((l) => l.layer_id === id))
    .filter((l): l is NonNullable<typeof l> => Boolean(l));

  async function handleSearchDestination(e: React.FormEvent) {
    e.preventDefault();
    const lat = Number.parseFloat(searchLat);
    const lon = Number.parseFloat(searchLon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    await evaluateDestination(lat, lon, searchLabel.trim() || undefined);
    setActiveTab("inspect");
  }

  async function handleVerifyRemote(datasetId: string) {
    setVerifyingId(datasetId);
    setVerifyFeedback(null);
    try {
      const res = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}/verify-remote`, {
        method: "POST",
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        setVerifyFeedback(payload.detail || `Remote verification returned HTTP ${res.status}`);
      } else {
        setVerifyFeedback(`Verified ${datasetId}: ${payload.status}`);
        await fetchLayers();
      }
    } catch (err) {
      setVerifyFeedback(err instanceof Error ? err.message : "Network error verifying remote capability");
    } finally {
      setVerifyingId(null);
    }
  }

  async function handleSetManualPosition(e: React.FormEvent) {
    e.preventDefault();
    const lat = Number.parseFloat(manualLat || searchLat);
    const lon = Number.parseFloat(manualLon || searchLon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return;
    await setManualPosition(lat, lon);
  }

  async function handleCompositionSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!compositionQuery.trim()) return;
    setCompositionLoading(true);
    setCompositionError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/destinations/search-composition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: compositionQuery.trim() }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} searching composition index`);
      }
      const data: CompositionSearchResponse = await res.json();
      setCompositionResult(data);
    } catch (err) {
      setCompositionError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setCompositionLoading(false);
    }
  }

  return (
    <div className="h-[calc(100vh-88px)] min-h-[620px] flex flex-col gap-3">
      {/* Compact Explorer Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-2.5">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-slate-100 tracking-tight">Mars Surface Explorer</h1>
          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#e25b38]/15 border border-[#e25b38]/30 text-[#f1886c]">
            IAU2000:49900 · GeographicTilingScheme
          </span>
          <span className="text-[11px] font-mono text-slate-400">
            {availableLayers.length} renderable · {unavailableLayers.length} unverified/unprocessed
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fetchLayers()}
            disabled={layersLoading}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263a] border border-[#252f44] text-slate-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${layersLoading ? "animate-spin" : ""}`} />
            <span>Sync Layers</span>
          </button>
          <Link
            href="/evidence"
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263a] border border-[#252f44] text-slate-300 transition-colors"
          >
            <Database className="w-3.5 h-3.5 text-[#38bdf8]" />
            <span>Evidence & Ingestion</span>
          </Link>
        </div>
      </div>

      {/* Main Split Workspace: Interactive Mars Globe + Side Workbench */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Side Workbench Drawer */}
        <div className="lg:col-span-4 xl:col-span-3 bg-[#121622] border border-[#1e2638] rounded-xl flex flex-col min-h-0 overflow-hidden">
          {/* Workbench Tabs */}
          <div className="grid grid-cols-3 border-b border-[#1e2638] bg-[#0e121b]">
            <button
              type="button"
              onClick={() => setActiveTab("layers")}
              className={`py-2.5 px-2 text-[11px] font-semibold flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
                activeTab === "layers"
                  ? "border-[#e25b38] text-slate-100 bg-[#141927]"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Layers ({availableLayers.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("inspect")}
              className={`py-2.5 px-2 text-[11px] font-semibold flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
                activeTab === "inspect"
                  ? "border-[#e25b38] text-slate-100 bg-[#141927]"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Crosshair className="w-3.5 h-3.5" />
              <span>Inspect</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("minerals")}
              className={`py-2.5 px-2 text-[11px] font-semibold flex items-center justify-center gap-1.5 border-b-2 transition-colors ${
                activeTab === "minerals"
                  ? "border-[#e25b38] text-slate-100 bg-[#141927]"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <FlaskConical className="w-3.5 h-3.5" />
              <span>Minerals</span>
            </button>
          </div>

          {/* Scrollable Tab Body */}
          <div className="flex-1 overflow-y-auto p-3 space-y-4">
            {activeTab === "layers" && (
              <>
                {layersError && (
                  <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/50 text-[11px] text-red-200">
                    {layersError}
                  </div>
                )}

                {verifyFeedback && (
                  <div className="p-2.5 rounded-lg bg-[#161c2b] border border-[#2a3650] text-[11px] text-slate-200">
                    {verifyFeedback}
                  </div>
                )}

                {/* Renderable Layers */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <span>Available Map Layers</span>
                    <span>{orderedAvailableLayers.length} active-ready</span>
                  </div>

                  {orderedAvailableLayers.length === 0 ? (
                    <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1d2536] text-[11px] text-slate-400 space-y-2">
                      <p>No verified remote WMTS or processed local raster layers are currently available.</p>
                      <p className="text-slate-500">
                        Verify a NASA Mars Trek WMTS capability below or acquire &amp; process a DEM in Evidence &amp; Provenance.
                      </p>
                    </div>
                  ) : (
                    orderedAvailableLayers.map((layer, idx) => {
                      const state = layerStates[layer.layer_id];
                      const visible = state?.visible ?? false;
                      const opacity = state?.opacity ?? layer.default_opacity;
                      const errCount = state?.tileErrorCount ?? 0;

                      return (
                        <div
                          key={layer.layer_id}
                          className={`p-2.5 rounded-lg border space-y-2 transition-colors ${
                            visible
                              ? "bg-[#161c2b] border-[#2e3b56]"
                              : "bg-[#10141f] border-[#1d2536]"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-xs font-semibold text-slate-100 truncate">
                                {layer.display_name}
                              </div>
                              <div className="text-[10px] font-mono text-slate-400">
                                {layer.source_product_id} · {layer.spatial_resolution_m ? `${layer.spatial_resolution_m} m/px` : layer.crs}
                              </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                type="button"
                                title="Move Up"
                                disabled={idx === 0}
                                onClick={() => moveLayerOrder(layer.layer_id, "up")}
                                className="p-1 rounded bg-[#0d111a] text-slate-400 hover:text-slate-100 disabled:opacity-30"
                              >
                                <ArrowUp className="w-3 h-3" />
                              </button>
                              <button
                                type="button"
                                title="Move Down"
                                disabled={idx === orderedAvailableLayers.length - 1}
                                onClick={() => moveLayerOrder(layer.layer_id, "down")}
                                className="p-1 rounded bg-[#0d111a] text-slate-400 hover:text-slate-100 disabled:opacity-30"
                              >
                                <ArrowDown className="w-3 h-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => toggleLayer(layer.layer_id)}
                                className={`p-1 rounded border transition-colors ${
                                  visible
                                    ? "bg-[#e25b38]/20 border-[#e25b38]/50 text-[#f38d72]"
                                    : "bg-[#0d111a] border-[#242e42] text-slate-500 hover:text-slate-300"
                                }`}
                                title={visible ? "Hide layer" : "Show layer"}
                              >
                                {visible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                              </button>
                            </div>
                          </div>

                          {visible && (
                            <div className="space-y-1.5 pt-1">
                              <div className="flex items-center gap-2">
                                <Sliders className="w-3 h-3 text-slate-400" />
                                <input
                                  type="range"
                                  min={0}
                                  max={1}
                                  step={0.05}
                                  value={opacity}
                                  onChange={(e) => setLayerOpacity(layer.layer_id, Number.parseFloat(e.target.value))}
                                  className="flex-1 accent-[#e25b38] h-1.5"
                                />
                                <span className="text-[10px] font-mono text-slate-300 w-8 text-right">
                                  {Math.round(opacity * 100)}%
                                </span>
                              </div>

                              {layer.legend && layer.legend.stops.length > 0 && (
                                <div className="pt-1 border-t border-[#20293d]">
                                  <div className="text-[10px] text-slate-400 mb-1">
                                    {layer.legend.title} ({layer.legend.units})
                                  </div>
                                  <div className="flex flex-wrap gap-1.5">
                                    {layer.legend.stops.map((stop, sIdx) => (
                                      <div key={sIdx} className="flex items-center gap-1 text-[9px] font-mono text-slate-300">
                                        <span
                                          className="w-2.5 h-2.5 rounded-sm border border-white/10 inline-block"
                                          style={{ backgroundColor: stop.color }}
                                        />
                                        <span>{stop.label}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {errCount > 0 && (
                            <div className="flex items-center justify-between text-[10px] bg-amber-950/40 border border-amber-800/50 text-amber-200 px-2 py-1 rounded">
                              <span>{errCount} tile request error(s)</span>
                              <button
                                type="button"
                                onClick={() => clearTileErrors(layer.layer_id)}
                                className="underline hover:text-white"
                              >
                                Clear
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Unavailable Layers */}
                <div className="space-y-2 pt-2 border-t border-[#1e2638]">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    <span>Unavailable / Pending Products</span>
                    <span>{unavailableLayers.length}</span>
                  </div>

                  {unavailableLayers.map((layer) => {
                    const isWmts = layer.layer_type === "remote_wmts";
                    return (
                      <div
                        key={layer.layer_id}
                        className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] font-medium text-slate-300 truncate">
                            {layer.display_name}
                          </span>
                          <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                            {layer.verification_state}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-500 leading-relaxed">
                          {layer.unavailable_reason || "Product not yet verified or processed for rendering."}
                        </p>
                        {isWmts && (
                          <button
                            type="button"
                            disabled={verifyingId === layer.source_dataset_id}
                            onClick={() => handleVerifyRemote(layer.source_dataset_id)}
                            className="w-full py-1 px-2 rounded bg-[#161c2b] hover:bg-[#1e273c] border border-[#2a3650] text-[10px] font-medium text-slate-200 transition-colors disabled:opacity-50"
                          >
                            {verifyingId === layer.source_dataset_id
                              ? "Probing NASA Capabilities..."
                              : "Verify NASA Remote Capabilities"}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {activeTab === "inspect" && (
              <>
                {/* Geographic Coordinate Search */}
                <form
                  onSubmit={handleSearchDestination}
                  className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2"
                >
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                    <Search className="w-3.5 h-3.5 text-[#e25b38]" />
                    <span>Coordinate Lookup (IAU2000:49900)</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] text-slate-400 block mb-0.5">Latitude [-90, 90]</label>
                      <input
                        type="number"
                        step="any"
                        min={-90}
                        max={90}
                        value={searchLat}
                        onChange={(e) => setSearchLat(e.target.value)}
                        className="w-full px-2 py-1 text-xs font-mono rounded bg-[#121622] border border-[#252f44] text-slate-100"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 block mb-0.5">Longitude (East)</label>
                      <input
                        type="number"
                        step="any"
                        min={-180}
                        max={360}
                        value={searchLon}
                        onChange={(e) => setSearchLon(e.target.value)}
                        className="w-full px-2 py-1 text-xs font-mono rounded bg-[#121622] border border-[#252f44] text-slate-100"
                      />
                    </div>
                  </div>
                  <input
                    type="text"
                    placeholder="Optional label (e.g., Target site)"
                    value={searchLabel}
                    onChange={(e) => setSearchLabel(e.target.value)}
                    className="w-full px-2 py-1 text-[11px] rounded bg-[#121622] border border-[#252f44] text-slate-200"
                  />
                  <button
                    type="submit"
                    disabled={destinationLoading}
                    className="w-full py-1.5 rounded bg-[#e25b38] hover:bg-[#cf4f2e] text-white text-[11px] font-semibold transition-colors disabled:opacity-50"
                  >
                    {destinationLoading ? "Evaluating Coordinate..." : "Inspect Coordinates"}
                  </button>
                </form>

                {destinationError && (
                  <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/50 text-[11px] text-red-200">
                    {destinationError}
                  </div>
                )}

                {/* Selected Destination Evaluation Card */}
                {selectedDestination ? (
                  <div className="p-3 rounded-lg bg-[#161c2b] border border-[#2a3650] space-y-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-100">
                          <MapPin className="w-3.5 h-3.5 text-[#38bdf8]" />
                          <span>{selectedDestination.label || "Inspected Coordinate"}</span>
                        </div>
                        <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                          {selectedDestination.crs} · {selectedDestination.latitude_convention}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={clearDestination}
                        title="Clear selection"
                        className="p-1 rounded hover:bg-[#1e2638] text-slate-400 hover:text-slate-200"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[11px] font-mono bg-[#0d111a] p-2 rounded border border-[#1d2536]">
                      <div>
                        <div className="text-[9px] text-slate-500">LATITUDE</div>
                        <div className="text-slate-100">{selectedDestination.latitude.toFixed(5)}°</div>
                      </div>
                      <div>
                        <div className="text-[9px] text-slate-500">LON [-180,180] / [0,360]</div>
                        <div className="text-slate-100">
                          {selectedDestination.normalized_longitude_180.toFixed(4)}° / {selectedDestination.normalized_longitude_360.toFixed(4)}°
                        </div>
                      </div>
                    </div>

                    {/* Terrain Sampling Results */}
                    <div className="space-y-1.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        DEM & Terrain Derivatives
                      </div>
                      {selectedDestination.terrain.available ? (
                        <div className="grid grid-cols-2 gap-1.5 text-[11px] font-mono">
                          <div className="p-1.5 rounded bg-[#0d111a] border border-[#1d2536]">
                            <div className="text-[9px] text-slate-500">ELEVATION</div>
                            <div className="text-emerald-300">
                              {selectedDestination.terrain.elevation_m !== null &&
                              selectedDestination.terrain.elevation_m !== undefined
                                ? `${selectedDestination.terrain.elevation_m.toFixed(2)} m`
                                : "NoData"}
                            </div>
                          </div>
                          <div className="p-1.5 rounded bg-[#0d111a] border border-[#1d2536]">
                            <div className="text-[9px] text-slate-500">SLOPE</div>
                            <div className="text-slate-100">
                              {selectedDestination.terrain.slope_deg !== null &&
                              selectedDestination.terrain.slope_deg !== undefined
                                ? `${selectedDestination.terrain.slope_deg.toFixed(2)}°`
                                : "Unavailable"}
                            </div>
                          </div>
                          <div className="p-1.5 rounded bg-[#0d111a] border border-[#1d2536]">
                            <div className="text-[9px] text-slate-500">ASPECT (CW from N)</div>
                            <div className="text-slate-100">
                              {selectedDestination.terrain.aspect_deg !== null &&
                              selectedDestination.terrain.aspect_deg !== undefined
                                ? `${selectedDestination.terrain.aspect_deg.toFixed(1)}°`
                                : "Unavailable"}
                            </div>
                          </div>
                          <div className="p-1.5 rounded bg-[#0d111a] border border-[#1d2536]">
                            <div className="text-[9px] text-slate-500">ROUGHNESS (TRI)</div>
                            <div className="text-slate-100">
                              {selectedDestination.terrain.roughness_tri_m !== null &&
                              selectedDestination.terrain.roughness_tri_m !== undefined
                                ? `${selectedDestination.terrain.roughness_tri_m.toFixed(2)} m`
                                : "Unavailable"}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="p-2 rounded bg-amber-950/30 border border-amber-800/40 text-[10px] text-amber-200 flex items-start gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                          <span>
                            {selectedDestination.terrain.unavailable_reason ||
                              "No validated local DEM raster covers this coordinate."}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Covering Datasets */}
                    <div className="space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Catalog Overlap ({selectedDestination.covering_datasets.length})
                      </div>
                      {selectedDestination.covering_datasets.map((ds) => (
                        <div
                          key={ds.dataset_id}
                          className="text-[10px] p-1.5 rounded bg-[#0d111a] border border-[#1d2536] flex items-center justify-between gap-2"
                        >
                          <span className="truncate text-slate-300">{ds.product_id}</span>
                          <span className="font-mono text-slate-500 shrink-0">{ds.verification_state}</span>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        setManualPosition(selectedDestination.latitude, selectedDestination.longitude)
                      }
                      className="w-full py-1.5 rounded bg-[#1d263b] hover:bg-[#26324d] border border-[#324163] text-[11px] font-medium text-sky-200 transition-colors"
                    >
                      Set as Active Manual Position
                    </button>
                  </div>
                ) : (
                  <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1d2536] text-[11px] text-slate-400">
                    Click any point on the 3D Mars globe or enter coordinates above to inspect datum metadata and real DEM values.
                  </div>
                )}

                {/* Localization Acquisition Architecture Panel */}
                <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                      <Compass className="w-3.5 h-3.5 text-[#38bdf8]" />
                      <span>Localization Status</span>
                    </div>
                    <span
                      className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase ${
                        localizationStatus?.live_localization_available
                          ? "bg-emerald-950/60 text-emerald-300 border border-emerald-700/50"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {localizationStatus?.live_localization_available ? "Live" : "Live Unavailable"}
                    </span>
                  </div>

                  {localizationStatus?.unavailable_reason && (
                    <p className="text-[10px] text-slate-400 leading-relaxed">
                      {localizationStatus.unavailable_reason}
                    </p>
                  )}

                  {localizationError && (
                    <p className="text-[10px] text-red-300">{localizationError}</p>
                  )}

                  {localizationStatus?.current_position ? (
                    <div className="p-2 rounded bg-[#121622] border border-[#242e44] space-y-1 text-[10px] font-mono">
                      <div className="flex items-center justify-between text-emerald-300">
                        <span>SOURCE: {localizationStatus.current_position.position_source}</span>
                        <button
                          type="button"
                          onClick={() => clearManualPosition()}
                          className="text-slate-400 hover:text-red-300 underline"
                        >
                          Clear
                        </button>
                      </div>
                      <div className="text-slate-200">
                        {localizationStatus.current_position.latitude?.toFixed(5)}°,{" "}
                        {localizationStatus.current_position.longitude?.toFixed(5)}° (
                        {localizationStatus.current_position.crs})
                      </div>
                    </div>
                  ) : (
                    <form onSubmit={handleSetManualPosition} className="space-y-1.5 pt-1">
                      <div className="grid grid-cols-2 gap-1.5">
                        <input
                          type="number"
                          step="any"
                          placeholder="Lat (-4.65)"
                          value={manualLat}
                          onChange={(e) => setManualLat(e.target.value)}
                          className="px-2 py-1 text-[10px] font-mono rounded bg-[#121622] border border-[#252f44] text-slate-200"
                        />
                        <input
                          type="number"
                          step="any"
                          placeholder="Lon (137.42)"
                          value={manualLon}
                          onChange={(e) => setManualLon(e.target.value)}
                          className="px-2 py-1 text-[10px] font-mono rounded bg-[#121622] border border-[#252f44] text-slate-200"
                        />
                      </div>
                      <button
                        type="submit"
                        className="w-full py-1 rounded bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[10px] font-medium text-slate-200"
                      >
                        Set Manual Surface Position
                      </button>
                    </form>
                  )}
                </div>
              </>
            )}

            {activeTab === "minerals" && (
              <div className="space-y-3">
                <form
                  onSubmit={handleCompositionSearch}
                  className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2"
                >
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                    <FlaskConical className="w-3.5 h-3.5 text-[#38bdf8]" />
                    <span>Mineral / Element Occurrence Search</span>
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Queries indexed spectral/chemical observation products (CRISM, ChemCam LIBS, APXS). Returns results only from verified loaded datasets.
                  </p>
                  <input
                    type="text"
                    value={compositionQuery}
                    onChange={(e) => setCompositionQuery(e.target.value)}
                    placeholder="e.g., smectite, hematite, sulfate, SiO2"
                    className="w-full px-2.5 py-1.5 text-xs rounded bg-[#121622] border border-[#252f44] text-slate-100"
                  />
                  <button
                    type="submit"
                    disabled={compositionLoading}
                    className="w-full py-1.5 rounded bg-[#1e2638] hover:bg-[#28334a] border border-[#344260] text-[11px] font-semibold text-slate-100 disabled:opacity-50"
                  >
                    {compositionLoading ? "Querying Composition Index..." : "Search Verified Detections"}
                  </button>
                </form>

                {compositionError && (
                  <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/50 text-[11px] text-red-200">
                    {compositionError}
                  </div>
                )}

                {compositionResult && (
                  <div className="p-3 rounded-lg bg-[#161c2b] border border-[#252f44] space-y-2">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold text-slate-200">Query: &ldquo;{compositionResult.query}&rdquo;</span>
                      <span
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded uppercase ${
                          compositionResult.index_available
                            ? "bg-emerald-950 text-emerald-300"
                            : "bg-amber-950 text-amber-200"
                        }`}
                      >
                        {compositionResult.index_available ? "Indexed" : "Index Unavailable"}
                      </span>
                    </div>
                    {compositionResult.unavailable_reason && (
                      <p className="text-[11px] text-amber-200/90 leading-relaxed">
                        {compositionResult.unavailable_reason}
                      </p>
                    )}
                    <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                      <span>Verified matches returned: {compositionResult.total_matches}</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Interactive Mars Globe Viewport */}
        <div className="lg:col-span-8 xl:col-span-9 min-h-[480px] h-full">
          <MarsGlobeViewer />
        </div>
      </div>
    </div>
  );
}
