"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Compass,
  Crosshair,
  Database,
  Eye,
  EyeOff,
  FlaskConical,
  Info,
  Layers,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Trash2,
  Mountain,
  Globe2,
  Columns2,
  Route as RouteIcon,
} from "lucide-react";
import { MarsGlobeViewer } from "../../components/MarsGlobeViewer";
import { LocalTerrain3DViewer } from "../../components/LocalTerrain3DViewer";
import { API_BASE_URL } from "../../lib/constants";
import { useLayerStore } from "../../stores/useLayerStore";
import { useMissionStore } from "../../stores/useMissionStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import {
  type MultiScaleTerrainResponse,
  type OpticalAnalysisResponse,
  CandidateDiscoveryLocation,
  CompositionEvidence,
  CompositionIndexStatus,
  CompositionSearchMode,
  CompositionSearchResponse,
  MeasurementCategory,
  ScienceTarget,
  SourcesAuditResponse,
  SpeciesRecord,
} from "../../types";

type ExplorerTab = "layers" | "inspect" | "minerals";

export default function SurfaceExplorerPage() {
  const [activeTab, setActiveTab] = useState<ExplorerTab>("layers");
  const [searchLat, setSearchLat] = useState<string>("");
  const [searchLon, setSearchLon] = useState<string>("");
  const [searchLabel, setSearchLabel] = useState<string>("");
  const [manualLat, setManualLat] = useState<string>("");
  const [manualLon, setManualLon] = useState<string>("");
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verifyFeedback, setVerifyFeedback] = useState<string | null>(null);

  const [compositionQuery, setCompositionQuery] = useState<string>("Fe");
  const [compositionMode, setCompositionMode] = useState<CompositionSearchMode>("auto");
  const [measurementCategoryFilter, setMeasurementCategoryFilter] = useState<MeasurementCategory | "">("");
  const [includeBearingMinerals, setIncludeBearingMinerals] = useState<boolean>(false);
  const [excludeLowQuality, setExcludeLowQuality] = useState<boolean>(false);
  const [sortBy, setSortBy] = useState<string>("rank");
  const [selectedInstruments, setSelectedInstruments] = useState<string[]>([]);
  const [compositionLoading, setCompositionLoading] = useState<boolean>(false);
  const [compositionResult, setCompositionResult] = useState<CompositionSearchResponse | null>(null);
  const [compositionError, setCompositionError] = useState<string | null>(null);
  const [indexStatus, setIndexStatus] = useState<CompositionIndexStatus | null>(null);
  const [rebuildingIndex, setRebuildingIndex] = useState<boolean>(false);
  const [speciesVocab, setSpeciesVocab] = useState<SpeciesRecord[]>([]);
  const [inspectedEvidence, setInspectedEvidence] = useState<CompositionEvidence | null>(null);
  const [multiscaleData, setMultiscaleData] = useState<MultiScaleTerrainResponse | null>(null);
  const [opticalData, setOpticalData] = useState<OpticalAnalysisResponse | null>(null);
  const [derivedLoading, setDerivedLoading] = useState(false);

  const runDerivedAnalysis = async (lat: number, lonEast: number) => {
    setDerivedLoading(true);
    try {
      const dsId = useRoutingStore.getState().selectedDemDatasetId || "hirise_dteec_009149_1750";
      const d = 0.008;
      const [msRes, optRes] = await Promise.all([
        fetch(
          `${API_BASE_URL}/terrain/multiscale?lat=${lat}&lon=${lonEast}&dataset_id=${encodeURIComponent(dsId)}`,
          { cache: "no-store" }
        ),
        fetch(
          `${API_BASE_URL}/terrain/optical-features?dataset_id=${encodeURIComponent(dsId)}&min_lat=${lat - d}&max_lat=${lat + d}&min_lon=${lonEast - d}&max_lon=${lonEast + d}`,
          { cache: "no-store" }
        ),
      ]);
      if (msRes.ok) setMultiscaleData(await msRes.json());
      if (optRes.ok) setOpticalData(await optRes.json());
    } finally {
      setDerivedLoading(false);
    }
  };
  const [evidenceLoading, setEvidenceLoading] = useState<boolean>(false);
  const [savedTargetMessage, setSavedTargetMessage] = useState<string | null>(null);
  const [sourcesAudit, setSourcesAudit] = useState<SourcesAuditResponse | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/sources/audit`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.sources) setSourcesAudit(data);
      })
      .catch(() => {});
  }, []);

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
    selectedCandidateId,
    evaluateDestination,
    clearDestination,
    fetchLocalizationStatus,
    setManualPosition,
    clearManualPosition,
    setCompositionResults,
    selectCompositionCandidate,
    addTarget,
  } = useMissionStore();

  useEffect(() => {
    void fetchLayers();
    void fetchLocalizationStatus();
    fetch(`${API_BASE_URL}/composition/index/status`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setIndexStatus(data);
      })
      .catch(() => undefined);
    fetch(`${API_BASE_URL}/composition/species`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setSpeciesVocab(data);
      })
      .catch(() => undefined);
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

  async function runCompositionQuery(overrideQuery?: string) {
    const q = (overrideQuery ?? compositionQuery).trim();
    if (!q) return;
    setCompositionLoading(true);
    setCompositionError(null);
    setInspectedEvidence(null);
    setSavedTargetMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/destinations/search-composition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          search_mode: compositionMode,
          include_element_bearing_minerals: includeBearingMinerals,
          measurement_category_filter: measurementCategoryFilter || null,
          use_active_astronaut_position: true,
          instruments: selectedInstruments.length > 0 ? selectedInstruments : null,
          exclude_low_quality: excludeLowQuality,
          sort_by: sortBy,
          limit: 50,
        }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error(errBody?.detail || `HTTP ${res.status} searching composition index`);
      }
      const data: CompositionSearchResponse = await res.json();
      setCompositionResult(data);
      setCompositionResults(data);
      if (data.index_status) setIndexStatus(data.index_status);
    } catch (err) {
      setCompositionError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setCompositionLoading(false);
    }
  }

  async function handleCompositionSearch(e: React.FormEvent) {
    e.preventDefault();
    await runCompositionQuery();
  }

  const [viewportMode, setViewportMode] = useState<"local3d" | "split" | "globe">("split");
  const pickedSurfacePoint = useRoutingStore((s) => s.pickedSurfacePoint);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const routeLoading = useRoutingStore((s) => s.routeLoading);
  const computeRoute = useRoutingStore((s) => s.computeRoute);
  const setStartPoint = useRoutingStore((s) => s.setStartPoint);
  const setDestinationPoint = useRoutingStore((s) => s.setDestinationPoint);
  const storeTargets = useRoutingStore((s) => s.availableTargets);
  const targetsLoaded = useRoutingStore((s) => s.targetsLoaded);
  const fetchAvailableTargets = useRoutingStore((s) => s.fetchAvailableTargets);

  useEffect(() => {
    if (!targetsLoaded) {
      void fetchAvailableTargets();
    }
  }, [targetsLoaded, fetchAvailableTargets]);

  async function handleRebuildIndex() {
    setRebuildingIndex(true);
    setCompositionError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/composition/index/rebuild`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status} rebuilding index`);
      const st: CompositionIndexStatus = await res.json();
      setIndexStatus(st);
    } catch (err) {
      setCompositionError(err instanceof Error ? err.message : "Rebuild failed");
    } finally {
      setRebuildingIndex(false);
    }
  }

  async function handleInspectEvidence(evidenceId: string) {
    setEvidenceLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/composition/evidence/${encodeURIComponent(evidenceId)}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching evidence detail`);
      const detail: CompositionEvidence = await res.json();
      setInspectedEvidence(detail);
    } catch (err) {
      setCompositionError(err instanceof Error ? err.message : "Failed to inspect evidence");
    } finally {
      setEvidenceLoading(false);
    }
  }

  async function handleRegisterCandidateTarget(cand: CandidateDiscoveryLocation) {
    setSavedTargetMessage(null);
    try {
      const targetPayload: ScienceTarget = {
        id: `target-${cand.candidate_id}`,
        name: `${cand.cluster_label} (${cand.best_species_id})`,
        latitude: cand.latitude,
        longitude: cand.longitude_east,
        elevation_m: cand.elevation_m ?? null,
        crs: cand.crs,
        geology_type: cand.best_species_id,
        scientific_value: Number(Math.min(1, Math.max(0, cand.ranking.composite_rank_score ?? 0)).toFixed(4)),
        instrument_source: cand.distinct_instruments.join(", "),
        provenance_product_id: cand.evidence_ids[0] || cand.candidate_id,
        target_status: "evidence_backed",
        evidence_ids: cand.evidence_ids,
        matched_species: cand.best_species_id,
        distance_from_astronaut_m: cand.distance_from_astronaut_m ?? null,
        explanation: cand.ranking.rationale,
      };
      const res = await fetch(`${API_BASE_URL}/targets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(targetPayload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} saving target`);
      const saved: ScienceTarget = await res.json();
      addTarget(saved);
      setSavedTargetMessage(`Registered verified target "${saved.name}".`);
    } catch (err) {
      setCompositionError(err instanceof Error ? err.message : "Failed to register target");
    }
  }

  function toggleInstrumentFilter(inst: string) {
    setSelectedInstruments((prev) =>
      prev.includes(inst) ? prev.filter((i) => i !== inst) : [...prev, inst]
    );
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

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex bg-[#0d111a] border border-[#252f44] rounded-lg p-0.5 text-[11px] font-mono">
            <button
              type="button"
              onClick={() => setViewportMode("local3d")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
                viewportMode === "local3d" ? "bg-[#e25b38] text-white font-semibold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Mountain className="w-3 h-3" />
              <span>3D Terrain DEM</span>
            </button>
            <button
              type="button"
              onClick={() => setViewportMode("split")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
                viewportMode === "split" ? "bg-[#e25b38] text-white font-semibold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Columns2 className="w-3 h-3" />
              <span>Split View</span>
            </button>
            <button
              type="button"
              onClick={() => setViewportMode("globe")}
              className={`flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
                viewportMode === "globe" ? "bg-[#e25b38] text-white font-semibold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Globe2 className="w-3 h-3" />
              <span>Mars Globe</span>
            </button>
          </div>

          <button
            type="button"
            onClick={() => void computeRoute()}
            disabled={routeLoading || !startPoint || !destinationPoint}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 transition-colors disabled:opacity-50"
            title="Compute route between selected start and destination on real DEM"
          >
            <RouteIcon className="w-3.5 h-3.5" />
            <span>{routeLoading ? "Routing..." : activeRoute ? "Recompute Route" : "Compute Route"}</span>
          </button>

          <Link
            href="/planner"
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-lg bg-[#e25b38]/20 hover:bg-[#e25b38]/30 border border-[#e25b38]/40 text-[#f38d72] transition-colors"
          >
            <span>Open Full Route Planner →</span>
          </Link>

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

                {/* Challenge NASA/USGS Sources Audit & Exclusions */}
                {sourcesAudit && (
                  <div className="space-y-2 pt-2 border-t border-[#1e2638]">
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      <span>NASA / USGS Sources Audit</span>
                      <span>{sourcesAudit.sources.length}</span>
                    </div>
                    <div className="space-y-1.5">
                      {sourcesAudit.sources.map((src) => (
                        <div
                          key={src.id}
                          className="p-2 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-1 text-[10px]"
                        >
                          <div className="flex items-center justify-between gap-1.5">
                            <span className="font-semibold text-slate-200 truncate">{src.name}</span>
                            <span
                              className={`font-mono uppercase px-1.5 py-0.5 rounded shrink-0 ${
                                src.status === "excluded_no_mars_dataset"
                                  ? "bg-red-950/60 text-red-300 border border-red-700/40"
                                  : src.status === "integrated_isolated_jezero"
                                    ? "bg-amber-950/60 text-amber-300 border border-amber-700/40"
                                    : "bg-emerald-950/50 text-emerald-300 border border-emerald-700/40"
                              }`}
                            >
                              {src.status.replaceAll("_", " ")}
                            </span>
                          </div>
                          {src.scale && (
                            <div className="text-[9px] font-mono text-amber-300">Scale: {src.scale}</div>
                          )}
                          <p className="text-slate-400 leading-relaxed">
                            {src.reason || src.notes}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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
                        Verified Coverage ({selectedDestination.covering_datasets.length})
                      </div>
                      {selectedDestination.covering_datasets.length === 0 ? (
                        <div className="text-[10px] text-slate-500 p-1.5 rounded bg-[#0d111a] border border-[#1d2536]">
                          No verified local/remote product footprints match this point.
                        </div>
                      ) : (
                        selectedDestination.covering_datasets.map((ds) => (
                          <div
                            key={ds.dataset_id}
                            className="text-[10px] p-1.5 rounded bg-[#0d111a] border border-[#1d2536] flex items-center justify-between gap-2"
                          >
                            <span className="truncate text-slate-300" title={ds.footprint_provenance || ""}>
                              {ds.product_id}
                            </span>
                            <span className="font-mono text-emerald-400 shrink-0">{ds.verification_state}</span>
                          </div>
                        ))
                      )}
                      {selectedDestination.unverified_catalog_candidates &&
                        selectedDestination.unverified_catalog_candidates.length > 0 && (
                          <div className="pt-1 space-y-1">
                            <div className="text-[9px] font-bold uppercase tracking-wider text-amber-300/80">
                              Unverified Catalog Candidates ({selectedDestination.unverified_catalog_candidates.length})
                            </div>
                            {selectedDestination.unverified_catalog_candidates.map((ds) => (
                              <div
                                key={ds.dataset_id}
                                className="text-[10px] p-1.5 rounded bg-amber-950/20 border border-amber-900/40 flex items-center justify-between gap-2"
                              >
                                <span className="truncate text-amber-200/80">{ds.product_id}</span>
                                <span className="font-mono text-amber-400/90 shrink-0">
                                  {ds.verification_state}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        void runDerivedAnalysis(
                          selectedDestination.latitude,
                          selectedDestination.longitude
                        )
                      }
                      disabled={derivedLoading}
                      className="w-full py-1.5 rounded bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/40 text-[11px] font-medium text-cyan-200 transition-colors"
                    >
                      {derivedLoading
                        ? "Deriving Multi-Scale & Optical Metrics..."
                        : "Derive Multi-Scale Terrain & Optical Features"}
                    </button>

                    {multiscaleData && multiscaleData.available && (
                      <div className="p-2.5 rounded-lg bg-[#090d16] border border-cyan-500/30 space-y-1.5 text-[10px] font-mono">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-cyan-300">Multi-Scale Terrain</span>
                          <span className="px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-300 text-[9px]">
                            MARSCOPE_DERIVED
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-slate-300">
                          <span>TRI (r=5m):</span>
                          <span className="text-right">
                            {multiscaleData.tri_fine_m?.value != null
                              ? `${multiscaleData.tri_fine_m.value.toFixed(3)} m`
                              : multiscaleData.tri_fine_m?.status || "N/A"}
                          </span>
                          <span>TRI (r=15m):</span>
                          <span className="text-right">
                            {multiscaleData.tri_medium_m?.value != null
                              ? `${multiscaleData.tri_medium_m.value.toFixed(3)} m`
                              : multiscaleData.tri_medium_m?.status || "N/A"}
                          </span>
                          <span>Local Relief (10m):</span>
                          <span className="text-right">
                            {multiscaleData.local_relief_m?.value != null
                              ? `${multiscaleData.local_relief_m.value.toFixed(2)} m`
                              : "N/A"}
                          </span>
                          <span>TPI (10m):</span>
                          <span className="text-right">
                            {multiscaleData.tpi_m?.value != null
                              ? `${multiscaleData.tpi_m.value.toFixed(2)} m`
                              : "N/A"}
                          </span>
                          <span>Profile Curv:</span>
                          <span className="text-right">
                            {multiscaleData.profile_curvature_inv_m != null
                              ? `${multiscaleData.profile_curvature_inv_m.toExponential(2)} 1/m`
                              : "N/A"}
                          </span>
                        </div>
                      </div>
                    )}

                    {opticalData && opticalData.available && (
                      <div className="p-2.5 rounded-lg bg-[#090d16] border border-purple-500/30 space-y-1.5 text-[10px] font-mono">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-purple-300">HiRISE Optical Analysis</span>
                          <span className="px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 text-[9px]">
                            CANDIDATE_ONLY
                          </span>
                        </div>
                        <div className="text-slate-400">
                          Mean Sobel Edge: {opticalData.mean_sobel_edge_dn?.toFixed(2) ?? "N/A"} DN · Candidates: {opticalData.candidates.length}
                        </div>
                        {opticalData.candidates.slice(0, 3).map((c) => (
                          <div key={c.feature_id} className="text-[9px] text-slate-300 flex justify-between gap-2">
                            <span className="truncate">{c.candidate_type}</span>
                            <span className="text-purple-300 shrink-0">z={c.local_contrast_zscore.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    )}

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
                          placeholder="Latitude"
                          value={manualLat}
                          onChange={(e) => setManualLat(e.target.value)}
                          className="px-2 py-1 text-[10px] font-mono rounded bg-[#121622] border border-[#252f44] text-slate-200"
                        />
                        <input
                          type="number"
                          step="any"
                          placeholder="Longitude east"
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
                {/* Index Status Banner */}
                <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Composition Spatial Index</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleRebuildIndex}
                      disabled={rebuildingIndex}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[10px] text-slate-200 disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3 h-3 ${rebuildingIndex ? "animate-spin" : ""}`} />
                      <span>Rebuild</span>
                    </button>
                  </div>
                  {indexStatus ? (
                    <div className="text-[10px] font-mono text-slate-400 space-y-0.5">
                      <div className="flex items-center justify-between gap-2">
                        <span>
                          Validated: <span className="text-emerald-300">{indexStatus.located_evidence_count}</span> located ·{" "}
                          <span className="text-amber-300">{indexStatus.unlocated_evidence_count}</span> unlocated ·{" "}
                          <span className="text-red-300">{indexStatus.rejected_record_count}</span> rejected
                        </span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] border ${
                            indexStatus.integrity_status === "verified" &&
                            indexStatus.checksum_valid &&
                            indexStatus.source_dependencies_valid !== false &&
                            indexStatus.manifest_valid !== false &&
                            indexStatus.generation_build_status !== "partial" &&
                            indexStatus.generation_build_status !== "failed"
                              ? "bg-emerald-950/60 border-emerald-700/60 text-emerald-300"
                              : indexStatus.generation_build_status === "partial"
                              ? "bg-amber-950/60 border-amber-700/60 text-amber-300"
                              : "bg-red-950/60 border-red-700/60 text-red-300"
                          }`}
                        >
                          {(indexStatus.integrity_status || (indexStatus.checksum_valid ? "verified" : "checksum_mismatch")).toUpperCase()}
                          {indexStatus.generation_build_status ? ` · ${indexStatus.generation_build_status.toUpperCase()}` : ""}
                        </span>
                      </div>
                      <div>
                        Instruments: {indexStatus.instruments_indexed.join(", ") || "None"} · R*Tree:{" "}
                        {indexStatus.rtree_enabled ? "ON" : "OFF"} · Gen: {indexStatus.active_generation_id || "N/A"}
                      </div>
                      <div className="text-[9px] text-slate-400">
                        Src: {indexStatus.source_integrity_status || "?"} · Manifest:{" "}
                        {indexStatus.manifest_integrity_status || "?"} · Ptr: {indexStatus.pointer_integrity_status || "?"} · DB:{" "}
                        {indexStatus.database_integrity_status || "?"}
                      </div>
                      {(!indexStatus.checksum_valid ||
                        indexStatus.source_dependencies_valid === false ||
                        indexStatus.manifest_valid === false) && (
                        <div className="text-[9px] text-red-300">
                          Integrity drift detected ({indexStatus.missing_source_files?.length || 0} missing,{" "}
                          {indexStatus.checksum_mismatches?.length || 0} modified primary,{" "}
                          {(indexStatus.missing_dependency_files?.length || 0) +
                            (indexStatus.dependency_checksum_mismatches?.length || 0)}{" "}
                          companion drift). Rebuild required.
                        </div>
                      )}
                      <div className="text-[9px] text-amber-300/90">
                        CRISM orbital: {indexStatus.crism_status}
                      </div>
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-500">Checking spatial index...</div>
                  )}
                </div>

                {/* Discovery Query Form */}
                <form
                  onSubmit={handleCompositionSearch}
                  className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-2"
                >
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
                    <FlaskConical className="w-3.5 h-3.5 text-[#38bdf8]" />
                    <span>Element &amp; Mineral Discovery</span>
                  </div>

                  <input
                    type="text"
                    list="marscope-species-list"
                    value={compositionQuery}
                    onChange={(e) => setCompositionQuery(e.target.value)}
                    placeholder="Element (Fe, S), oxide (SO3, SiO2), or mineral (hematite, gypsum)"
                    className="w-full px-2.5 py-1.5 text-xs rounded bg-[#121622] border border-[#252f44] text-slate-100"
                  />
                  <datalist id="marscope-species-list">
                    {speciesVocab.map((sp) => (
                      <option key={sp.canonical_id} value={sp.canonical_id}>
                        {sp.canonical_name} ({sp.category})
                      </option>
                    ))}
                  </datalist>

                  {/* Quick-Pick Species Pills */}
                  <div className="flex flex-wrap gap-1">
                    {["Fe", "S", "SO3", "SiO2", "CaO", "hematite", "gypsum", "plagioclase", "olivine"].map((pill) => (
                      <button
                        key={pill}
                        type="button"
                        onClick={() => {
                          setCompositionQuery(pill);
                          void runCompositionQuery(pill);
                        }}
                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                          compositionQuery.toLowerCase() === pill.toLowerCase()
                            ? "bg-[#e25b38]/25 border-[#e25b38]/70 text-orange-200"
                            : "bg-[#121622] border-[#252f44] text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        {pill}
                      </button>
                    ))}
                  </div>

                  {/* Mode & Sort Controls */}
                  <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                    <select
                      value={compositionMode}
                      onChange={(e) => setCompositionMode(e.target.value as CompositionSearchMode)}
                      className="px-2 py-1 rounded bg-[#121622] border border-[#252f44] text-slate-200"
                    >
                      <option value="auto">Mode: Auto Resolve</option>
                      <option value="element">Mode: Element Only</option>
                      <option value="mineral">Mode: Mineral Only</option>
                      <option value="element_bearing_mineral">Mode: +Host Minerals</option>
                    </select>
                    <select
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                      className="px-2 py-1 rounded bg-[#121622] border border-[#252f44] text-slate-200"
                    >
                      <option value="rank">Sort: Composite Rank</option>
                      <option value="distance">Sort: Nearest to Explorer</option>
                      <option value="category_abundance">Sort: Within Category</option>
                      <option value="abundance">Sort: Same-Scale Abundance</option>
                      <option value="sol">Sort: Latest Sol</option>
                    </select>
                  </div>

                  <select
                    value={measurementCategoryFilter}
                    onChange={(e) => setMeasurementCategoryFilter(e.target.value as MeasurementCategory | "")}
                    className="w-full px-2 py-1 rounded bg-[#121622] border border-[#252f44] text-[10px] text-slate-200"
                  >
                    <option value="">Category: All Matching Categories</option>
                    <option value="direct_elemental_concentration">Direct Elemental Concentration</option>
                    <option value="oxide_derived_elemental_concentration">Oxide-Derived Elemental (Stoich.)</option>
                    <option value="direct_oxide_concentration">Direct Oxide Concentration</option>
                    <option value="mineral_weight_percent">Mineral Weight Percent (XRD)</option>
                    <option value="mineral_group_membership_evidence">Mineral Group Member</option>
                  </select>

                  {/* Instrument Filter Chips */}
                  <div className="flex flex-wrap items-center gap-1 text-[10px]">
                    <span className="text-slate-500 mr-0.5">Instr:</span>
                    {["APXS", "ChemCam_LIBS", "CheMin_XRD"].map((inst) => {
                      const active = selectedInstruments.includes(inst);
                      return (
                        <button
                          key={inst}
                          type="button"
                          onClick={() => toggleInstrumentFilter(inst)}
                          className={`px-1.5 py-0.5 rounded font-mono border ${
                            active
                              ? "bg-sky-950/60 border-sky-600/60 text-sky-200"
                              : "bg-[#121622] border-[#252f44] text-slate-400"
                          }`}
                        >
                          {inst}
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex flex-col gap-1 text-[10px] text-slate-300">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={includeBearingMinerals}
                        onChange={(e) => setIncludeBearingMinerals(e.target.checked)}
                      />
                      <span>Include element-bearing host minerals (lower evidence tier)</span>
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={excludeLowQuality}
                        onChange={(e) => setExcludeLowQuality(e.target.checked)}
                      />
                      <span>Exclude elevated-RMSEP / minor-abundance flagged records</span>
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={compositionLoading}
                    className="w-full py-1.5 rounded bg-[#e25b38] hover:bg-[#cf4f2e] text-[11px] font-semibold text-white disabled:opacity-50"
                  >
                    {compositionLoading ? "Querying Spatial Index..." : "Search Verified Detections"}
                  </button>
                </form>

                {compositionError && (
                  <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-800/50 text-[11px] text-red-200">
                    {compositionError}
                  </div>
                )}

                {savedTargetMessage && (
                  <div className="p-2 rounded-lg bg-emerald-950/40 border border-emerald-700/50 text-[11px] text-emerald-200">
                    {savedTargetMessage}
                  </div>
                )}

                {/* Results Summary & Warnings */}
                {compositionResult && (
                  <div className="space-y-2.5">
                    <div className="p-2.5 rounded-lg bg-[#161c2b] border border-[#252f44] space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-semibold text-slate-100">
                          {compositionResult.resolution?.species
                            ? `${compositionResult.resolution.species.canonical_name} (${compositionResult.resolution.species.canonical_id})`
                            : `Query: "${compositionResult.query}"`}
                        </span>
                        <span className="text-[10px] font-mono text-emerald-300">
                          {compositionResult.candidate_locations.length} sites · {compositionResult.total_matches} hits
                        </span>
                      </div>

                      {compositionResult.resolution?.explanation && (
                        <div className="text-[10px] text-slate-300">
                          {compositionResult.resolution.explanation}
                        </div>
                      )}

                      {compositionResult.grouped_counts_by_measurement_category &&
                        Object.keys(compositionResult.grouped_counts_by_measurement_category).length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-0.5">
                            {Object.entries(compositionResult.grouped_counts_by_measurement_category).map(([cat, cnt]) => (
                              <span
                                key={cat}
                                className="px-1.5 py-0.5 rounded bg-[#0d111a] border border-[#252f44] text-[9px] font-mono text-sky-200"
                              >
                                {cat}: {cnt}
                              </span>
                            ))}
                          </div>
                        )}

                      {compositionResult.applied_filter_scope_note && (
                        <div className="text-[10px] text-sky-200/90 bg-sky-950/30 border border-sky-800/40 rounded px-2 py-1">
                          {compositionResult.applied_filter_scope_note}
                        </div>
                      )}

                      {compositionResult.unlocated_matches_count > 0 && (
                        <div className="text-[10px] text-amber-200/90 bg-amber-950/30 border border-amber-800/40 rounded px-2 py-1">
                          {compositionResult.unlocated_matches_count} validated hits lack verified coordinates and are excluded from spatial candidates.
                        </div>
                      )}

                      {compositionResult.unavailable_reason && (
                        <p className="text-[10px] text-amber-200/90 leading-relaxed">
                          {compositionResult.unavailable_reason}
                        </p>
                      )}

                      {compositionResult.scientific_warnings.map((w, idx) => (
                        <div key={idx} className="text-[10px] text-slate-400 flex items-start gap-1">
                          <Info className="w-3 h-3 text-sky-400 shrink-0 mt-0.5" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>

                    {/* Evidence Provenance Inspector Card */}
                    {evidenceLoading && (
                      <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#252f44] text-[11px] text-slate-300">
                        Loading full evidence provenance &amp; 12-stage validation record...
                      </div>
                    )}

                    {inspectedEvidence && (
                      <div className="p-2.5 rounded-lg bg-[#0b101b] border border-sky-700/60 space-y-2 text-[10px]">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-sky-300">
                            Evidence Detail: {inspectedEvidence.target_name || inspectedEvidence.source_record_ref}
                          </span>
                          <button
                            type="button"
                            onClick={() => setInspectedEvidence(null)}
                            className="text-slate-400 hover:text-white shrink-0"
                          >
                            Close
                          </button>
                        </div>

                        <div className="flex flex-wrap gap-1 font-mono text-[9px]">
                          <span
                            className={`px-1.5 py-0.5 rounded border ${
                              inspectedEvidence.is_stoichiometric_conversion
                                ? "bg-amber-950/60 border-amber-700/60 text-amber-200"
                                : "bg-emerald-950/60 border-emerald-700/60 text-emerald-200"
                            }`}
                          >
                            {inspectedEvidence.is_stoichiometric_conversion
                              ? `Oxide-Derived (${inspectedEvidence.source_oxide_species} → ${inspectedEvidence.canonical_species_id})`
                              : "Direct Measurement"}
                          </span>
                          <span
                            className={`px-1.5 py-0.5 rounded border ${
                              inspectedEvidence.location_semantic_type === "rover_station_location"
                                ? "bg-purple-950/60 border-purple-700/60 text-purple-200"
                                : inspectedEvidence.location_semantic_type === "unlocated"
                                  ? "bg-red-950/60 border-red-700/60 text-red-200"
                                  : "bg-sky-950/60 border-sky-700/60 text-sky-200"
                            }`}
                          >
                            {inspectedEvidence.location_semantic_type || "unknown_spatial_semantics"}
                          </span>
                        </div>

                        <div className="font-mono text-slate-300 space-y-0.5">
                          <div>
                            {inspectedEvidence.instrument_id} · Sol {inspectedEvidence.sol ?? "N/A"} ·{" "}
                            {inspectedEvidence.canonical_species_id} ({inspectedEvidence.evidence_type})
                          </div>
                          <div>
                            Raw: {inspectedEvidence.raw_value ?? "N/A"} {inspectedEvidence.raw_unit || ""}{" "}
                            {inspectedEvidence.source_raw_token ? `[token: "${inspectedEvidence.source_raw_token}"] ` : ""}→ Norm:{" "}
                            {inspectedEvidence.normalized_value?.toFixed(3) ?? "N/A"} {inspectedEvidence.normalized_unit || ""}
                            {inspectedEvidence.uncertainty_value != null
                              ? ` (±${inspectedEvidence.uncertainty_value.toFixed(3)} ${inspectedEvidence.uncertainty_unit || ""} ${inspectedEvidence.uncertainty_type || ""})`
                              : " (primary uncert: Unreported in source)"}
                          </div>
                          {inspectedEvidence.value_semantics && (
                            <div className="text-sky-300/90">
                              Value Semantics: {inspectedEvidence.value_semantics}
                              {inspectedEvidence.source_interpretation_note
                                ? ` · ${inspectedEvidence.source_interpretation_note}`
                                : ""}
                            </div>
                          )}
                          {inspectedEvidence.secondary_uncertainty_value != null && (
                            <div className="text-slate-400">
                              Secondary Uncert: ±{inspectedEvidence.secondary_uncertainty_value.toFixed(3)}{" "}
                              {inspectedEvidence.secondary_uncertainty_unit || ""} ({inspectedEvidence.secondary_uncertainty_type})
                            </div>
                          )}
                          {inspectedEvidence.uncertainty_metadata && (
                            <div className="text-slate-400">
                              Uncert Semantics: {inspectedEvidence.uncertainty_metadata.statistical_interpretation} ·{" "}
                              Coverage: {inspectedEvidence.uncertainty_metadata.coverage_confidence_level}
                              {inspectedEvidence.uncertainty_metadata.source_definition
                                ? ` · Source def: ${inspectedEvidence.uncertainty_metadata.source_definition}`
                                : ""}
                              {inspectedEvidence.uncertainty_metadata.conversion_history &&
                              inspectedEvidence.uncertainty_metadata.conversion_history.length > 0
                                ? ` · Conversion: ${inspectedEvidence.uncertainty_metadata.conversion_history.join("; ")}`
                                : ""}
                            </div>
                          )}
                          {inspectedEvidence.normalization_formula && (
                            <div className="text-slate-400">
                              Formula: {inspectedEvidence.normalization_formula}
                              {inspectedEvidence.stoichiometric_weights_version
                                ? ` [${inspectedEvidence.stoichiometric_weights_version}]`
                                : ""}
                            </div>
                          )}
                          <div className="text-slate-400">
                            Coords: {inspectedEvidence.coordinate_source || "None"} · Pos. Uncert:{" "}
                            {inspectedEvidence.coordinate_uncertainty_m != null
                              ? `±${inspectedEvidence.coordinate_uncertainty_m} m`
                              : "Unreported in source"}
                            {inspectedEvidence.instrument_standoff_m != null
                              ? ` · Standoff: ${inspectedEvidence.instrument_standoff_m.toFixed(2)} m`
                              : ""}
                          </div>
                          {inspectedEvidence.coordinate_transform && (
                            <div className="text-slate-500">
                              Transform: {inspectedEvidence.coordinate_transform}
                              {inspectedEvidence.waypoint_id ? ` · Waypoint: ${inspectedEvidence.waypoint_id}` : ""}
                            </div>
                          )}
                          {inspectedEvidence.coordinate_limitations && inspectedEvidence.coordinate_limitations.length > 0 && (
                            <div className="text-amber-300/90">
                              Spatial note: {inspectedEvidence.coordinate_limitations.join(" ")}
                            </div>
                          )}
                          <div className="text-slate-500 break-all">
                            ID: {inspectedEvidence.evidence_id} ({inspectedEvidence.determinism_version || "v1"}) · Schema:{" "}
                            {inspectedEvidence.schema_version || "N/A"} · Parser: {inspectedEvidence.parser_id || "N/A"} v
                            {inspectedEvidence.parser_version || "?"}
                          </div>
                          {inspectedEvidence.source_file_checksum && (
                            <div className="text-slate-500 break-all">
                              SHA-256: {inspectedEvidence.source_file_checksum}
                            </div>
                          )}
                          <div className="text-slate-500 break-all">
                            Source: {inspectedEvidence.source_reference}
                          </div>
                        </div>
                        <div className="border-t border-[#1e2638] pt-1.5 space-y-0.5 max-h-36 overflow-y-auto">
                          <div className="font-semibold text-slate-400">12-Stage Validation Pipeline:</div>
                          {inspectedEvidence.validation_stages.map((st) => (
                            <div key={st.stage_number} className="flex items-center justify-between gap-2">
                              <span className={st.passed ? "text-emerald-300" : "text-red-300"}>
                                {st.stage_number}. {st.stage_name}
                              </span>
                              <span className="text-slate-500 truncate max-w-[160px]" title={st.detail}>
                                {st.detail}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Ranked Candidate Discovery Locations */}
                    <div className="space-y-2">
                      {compositionResult.candidate_locations.map((cand, idx) => {
                        const isSelected = cand.candidate_id === selectedCandidateId;
                        return (
                          <div
                            key={cand.candidate_id}
                            onClick={() => selectCompositionCandidate(cand.candidate_id)}
                            className={`p-2.5 rounded-lg border cursor-pointer transition-colors space-y-1.5 ${
                              isSelected
                                ? "bg-emerald-950/25 border-emerald-600/70"
                                : "bg-[#0d111a] border-[#1d2536] hover:border-[#324163]"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-100">
                                  <span className="px-1.5 py-0.5 rounded bg-[#161c2b] font-mono text-[10px] text-amber-300">
                                    #{idx + 1}
                                  </span>
                                  <span className="truncate">{cand.cluster_label}</span>
                                </div>
                                <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                                  {cand.latitude.toFixed(4)}°, {cand.longitude_east.toFixed(4)}°E · {cand.sol_range}
                                </div>
                              </div>
                              <div className="text-right shrink-0">
                                <div className="text-xs font-mono font-bold text-emerald-300">
                                  {cand.best_normalized_value != null
                                    ? `${cand.best_normalized_value.toFixed(2)} ${cand.best_normalized_unit || ""}`
                                    : cand.best_species_id}
                                </div>
                                <div className="text-[9px] font-mono text-slate-400" title={cand.ranking.score_formula}>
                                  Priority {cand.ranking.composite_rank_score != null ? cand.ranking.composite_rank_score.toFixed(3) : "N/A"} (Heuristic · Not Prob.)
                                </div>
                              </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-slate-300">
                              <span
                                className={`px-1.5 py-0.5 rounded border ${
                                  cand.location_semantic_type === "rover_station_location"
                                    ? "bg-purple-950/50 border-purple-700/60 text-purple-200"
                                    : "bg-amber-950/40 border-amber-700/50 text-amber-200"
                                }`}
                              >
                                {cand.location_semantic_type === "rover_station_location"
                                  ? "Rover Station Location"
                                  : "Instrument Target Location"}
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-[#121622] border border-[#1e2638]">
                                Uncert: {cand.coordinate_uncertainty_m != null ? `±${cand.coordinate_uncertainty_m} m` : "Unreported"}
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-[#121622] border border-[#1e2638]">
                                {cand.distinct_instruments.join(" + ")}
                              </span>
                              <span className="px-1.5 py-0.5 rounded bg-[#121622] border border-[#1e2638]">
                                {cand.matched_evidence_count} obs
                              </span>
                              {cand.distance_from_astronaut_m != null && (
                                <span className="px-1.5 py-0.5 rounded bg-sky-950/40 border border-sky-800/40 text-sky-200">
                                  {cand.distance_from_astronaut_m >= 1000
                                    ? `${(cand.distance_from_astronaut_m / 1000).toFixed(2)} km`
                                    : `${cand.distance_from_astronaut_m.toFixed(0)} m`}{" "}
                                  @ {cand.bearing_deg?.toFixed(0)}°
                                </span>
                              )}
                            </div>

                            <div className="text-[10px] text-slate-400 leading-snug">
                              {cand.ranking.rationale}
                            </div>
                            <div className="text-[9px] font-mono text-slate-300 leading-snug">
                              {cand.ranking.relative_uncertainty?.available &&
                              cand.ranking.relative_uncertainty.percent != null
                                ? `Relative Uncert: ${cand.ranking.relative_uncertainty.percent.toFixed(2)}% (reported separately; never quality score)`
                                : `Relative Uncert: Withheld (${cand.ranking.relative_uncertainty?.unavailable_reason || "unit/measurement incompatible"})`}
                            </div>
                            {cand.ranking.quality_exclusion_reason && (
                              <div className="text-[9px] text-amber-300/90 leading-snug">
                                Quality term omitted ({cand.ranking.uncertainty_compatibility_status || "withheld"}):{" "}
                                {cand.ranking.quality_exclusion_reason}
                              </div>
                            )}
                            {cand.coordinate_limitations && cand.coordinate_limitations.length > 0 && (
                              <div className="text-[9px] text-purple-300/90 leading-snug">
                                Note: {cand.coordinate_limitations[0]}
                              </div>
                            )}

                            <div className="flex items-center gap-1.5 pt-1">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  selectCompositionCandidate(cand.candidate_id);
                                  void evaluateDestination(cand.latitude, cand.longitude_east, cand.cluster_label);
                                }}
                                className="flex-1 py-1 px-2 rounded bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[10px] font-medium text-sky-200"
                              >
                                Terrain
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (cand.evidence_ids[0]) {
                                    void handleInspectEvidence(cand.evidence_ids[0]);
                                  }
                                }}
                                className="flex-1 py-1 px-2 rounded bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[10px] font-medium text-slate-200"
                              >
                                Evidence
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleRegisterCandidateTarget(cand);
                                }}
                                className="flex-1 inline-flex items-center justify-center gap-1 py-1 px-2 rounded bg-emerald-950/60 hover:bg-emerald-900/60 border border-emerald-700/60 text-[10px] font-medium text-emerald-200"
                              >
                                <Sparkles className="w-3 h-3" />
                                <span>Target</span>
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Interactive Mars 3D Terrain & Globe Viewports */}
        <div className="lg:col-span-8 xl:col-span-9 min-h-[480px] h-full flex flex-col gap-2">
          {pickedSurfacePoint && (
            <div className="flex flex-wrap items-center justify-between gap-2 bg-[#121622] border border-cyan-500/30 rounded-lg px-3 py-1.5 text-[11px] font-mono">
              <div className="text-slate-200">
                <span className="text-cyan-400 font-semibold">PICKED DEM SURFACE:</span>{" "}
                {pickedSurfacePoint.lat.toFixed(5)}°, {pickedSurfacePoint.lon_east.toFixed(5)}° E · Elev{" "}
                {pickedSurfacePoint.elevation_m.toFixed(1)} m
                {pickedSurfacePoint.slope_deg != null ? ` · Slope ${pickedSurfacePoint.slope_deg.toFixed(1)}°` : ""}
                {pickedSurfacePoint.roughness_tri_m != null ? ` · TRI ${pickedSurfacePoint.roughness_tri_m.toFixed(2)} m` : ""}
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() =>
                    setStartPoint({
                      lat: pickedSurfacePoint.lat,
                      lon_east: pickedSurfacePoint.lon_east,
                      label: `Picked Start (${pickedSurfacePoint.lat.toFixed(4)}°, ${pickedSurfacePoint.lon_east.toFixed(4)}°)`,
                    })
                  }
                  className="px-2 py-0.5 rounded bg-emerald-600/20 hover:bg-emerald-600/35 border border-emerald-500/40 text-emerald-300"
                >
                  Set as Start
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setDestinationPoint({
                      lat: pickedSurfacePoint.lat,
                      lon_east: pickedSurfacePoint.lon_east,
                      label: `Picked Dest (${pickedSurfacePoint.lat.toFixed(4)}°, ${pickedSurfacePoint.lon_east.toFixed(4)}°)`,
                    })
                  }
                  className="px-2 py-0.5 rounded bg-rose-600/20 hover:bg-rose-600/35 border border-rose-500/40 text-rose-300"
                >
                  Set as Destination
                </button>
              </div>
            </div>
          )}

          <div
            className={`flex-1 min-h-0 grid gap-3 ${
              viewportMode === "split" ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"
            }`}
          >
            {(viewportMode === "local3d" || viewportMode === "split") && (
              <div className="min-h-[380px] h-full">
                <LocalTerrain3DViewer targets={storeTargets} />
              </div>
            )}
            {(viewportMode === "globe" || viewportMode === "split") && (
              <div className="min-h-[380px] h-full">
                <MarsGlobeViewer />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
