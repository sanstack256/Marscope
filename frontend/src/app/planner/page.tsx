"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Compass,
  Download,
  Flag,
  Layers,
  Loader2,
  MapPin,
  Navigation,
  RefreshCw,
  Route as RouteIcon,
  Scale,
  ShieldAlert,
  Sparkles,
  Target,
  Trash2,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import { useRoutingStore } from "@/stores/useRoutingStore";
import type { PathAlgorithm, PlanningMode, RouteVertex } from "@/types";

function formatDurationSeconds(sec?: number | null): string {
  if (sec == null || !Number.isFinite(sec)) return "Not Modeled (Speed Omitted)";
  const totalMin = Math.round(sec / 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m (${Math.round(sec)}s)`;
}

function ElevationChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: RouteVertex }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0].payload;
  return (
    <div className="bg-[#0b101b]/95 border border-[#2a3854] rounded-lg px-3 py-2 text-[11px] font-mono text-slate-200 shadow-xl space-y-0.5">
      <div className="text-cyan-300 font-semibold">
        {pt.stop_label ? `Stop: ${pt.stop_label}` : `Vertex #${pt.seq}`}
      </div>
      <div>Distance: {pt.cumulative_distance_m.toFixed(1)} m</div>
      <div>Elevation: {pt.elevation_m.toFixed(2)} m</div>
      <div>Slope: {pt.slope_deg != null ? `${pt.slope_deg.toFixed(1)}°` : "N/A"}</div>
      <div>TRI: {pt.roughness_tri_m != null ? `${pt.roughness_tri_m.toFixed(2)} m` : "N/A"}</div>
      <div className="text-slate-400">
        {pt.lat.toFixed(5)}°, {pt.lon_east.toFixed(5)}° E
      </div>
    </div>
  );
}

export default function PlannerPage() {
  const targets = useRoutingStore((s) => s.availableTargets);
  const fetchTargets = useRoutingStore((s) => s.fetchAvailableTargets);

  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const meshManifest = useRoutingStore((s) => s.meshManifest);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const selectedTargetIds = useRoutingStore((s) => s.selectedTargetIds);
  const customWaypoints = useRoutingStore((s) => s.customWaypoints);
  const activeMode = useRoutingStore((s) => s.activeMode);
  const algorithm = useRoutingStore((s) => s.algorithm);
  const constraints = useRoutingStore((s) => s.constraints);
  const surfacePickMode = useRoutingStore((s) => s.surfacePickMode);

  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const routeLoading = useRoutingStore((s) => s.routeLoading);
  const compareLoading = useRoutingStore((s) => s.compareLoading);
  const routeError = useRoutingStore((s) => s.routeError);
  const staleRoute = useRoutingStore((s) => s.staleRoute);
  const staleReason = useRoutingStore((s) => s.staleReason);
  const selectedInstructionStep = useRoutingStore((s) => s.selectedInstructionStep);
  const selectedWaypointSeq = useRoutingStore((s) => s.selectedWaypointSeq);

  const setStartPoint = useRoutingStore((s) => s.setStartPoint);
  const setDestinationPoint = useRoutingStore((s) => s.setDestinationPoint);
  const toggleTargetId = useRoutingStore((s) => s.toggleTargetId);
  const removeCustomWaypoint = useRoutingStore((s) => s.removeCustomWaypoint);
  const clearCustomWaypoints = useRoutingStore((s) => s.clearCustomWaypoints);
  const setActiveMode = useRoutingStore((s) => s.setActiveMode);
  const setAlgorithm = useRoutingStore((s) => s.setAlgorithm);
  const updateConstraints = useRoutingStore((s) => s.updateConstraints);
  const setSurfacePickMode = useRoutingStore((s) => s.setSurfacePickMode);
  const loadRealGaleBoxworkPreset = useRoutingStore((s) => s.loadRealGaleBoxworkPreset);
  const computeRoute = useRoutingStore((s) => s.computeRoute);
  const compareRoutes = useRoutingStore((s) => s.compareRoutes);
  const exportActiveGeoJSON = useRoutingStore((s) => s.exportActiveGeoJSON);
  const selectInstructionStep = useRoutingStore((s) => s.selectInstructionStep);

  const [showDiagnostics, setShowDiagnostics] = useState(false);

  useEffect(() => {
    void fetchTargets();
  }, [fetchTargets]);

  const stopVertices = activeRoute?.vertices.filter((v) => v.is_stop) ?? [];
  const modeOptions: Array<{ id: PlanningMode; label: string; desc: string }> = [
    { id: "conservative", label: "Conservative", desc: "Cap <= 16°, heavy slope/TRI penalty" },
    { id: "balanced", label: "Balanced", desc: "Moderate grade + terrain impedance" },
    { id: "science_priority", label: "Science Priority", desc: "Attracted to composition evidence" },
  ];

  const handleCoordEdit = (
    role: "start" | "destination",
    field: "lat" | "lon_east",
    raw: string
  ) => {
    const val = Number.parseFloat(raw);
    if (!Number.isFinite(val)) return;
    if (role === "start" && startPoint) {
      setStartPoint({ ...startPoint, [field]: val });
    } else if (role === "destination" && destinationPoint) {
      setDestinationPoint({ ...destinationPoint, [field]: val });
    }
  };

  return (
    <div className="space-y-4">
      {/* Header Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-3">
        <div>
          <div className="flex items-center gap-2.5">
            <RouteIcon className="w-5 h-5 text-[#e25b38]" />
            <h1 className="text-base font-bold text-slate-100">
              Science-Aware Marswalk Route Planner
            </h1>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/30 text-cyan-300">
              {meshManifest?.product_id || selectedDemDatasetId}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Graph-verified 8-connected A* / Dijkstra planning on real NASA DEM terrain · True North (deg) &amp; Grid North headings
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => loadRealGaleBoxworkPreset()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e273d] border border-[#2a3652] text-xs font-medium text-slate-200 transition-colors"
            title="Load real Curiosity Sol 4500+ Boxwork Crater & Gediz Ridge coordinates"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Boxwork Preset</span>
          </button>

          <button
            type="button"
            onClick={() => void computeRoute()}
            disabled={routeLoading || !startPoint || !destinationPoint}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#c84d2d] text-xs font-semibold text-white transition-colors disabled:opacity-50"
          >
            {routeLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Navigation className="w-3.5 h-3.5" />
            )}
            <span>{routeLoading ? "Computing..." : "Compute Route"}</span>
          </button>

          <button
            type="button"
            onClick={() => void compareRoutes()}
            disabled={compareLoading || !startPoint || !destinationPoint}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/35 border border-cyan-500/40 text-xs font-medium text-cyan-200 transition-colors disabled:opacity-50"
          >
            <Scale className="w-3.5 h-3.5" />
            <span>{compareLoading ? "Comparing..." : "Compare 3 Modes"}</span>
          </button>

          <button
            type="button"
            onClick={() => void exportActiveGeoJSON()}
            disabled={!activeRoute}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e273d] border border-[#2a3652] text-xs font-medium text-slate-200 transition-colors disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            <span>GeoJSON</span>
          </button>

          <Link
            href="/routes"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e273d] border border-[#2a3652] text-xs text-slate-300"
          >
            <span>Comparison</span>
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      </div>

      {/* Stale Route Warning Banner */}
      {staleRoute && activeRoute && (
        <div className="flex flex-wrap items-center justify-between gap-2 bg-amber-950/50 border border-amber-500/50 rounded-xl px-4 py-2.5 text-xs text-amber-200">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Route Outdated:</strong> {staleReason || "Planning inputs changed."} Recalculate to update path, metrics, and navigation directions.
            </span>
          </div>
          <button
            type="button"
            onClick={() => void computeRoute()}
            disabled={routeLoading}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-[#0b0e17] font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${routeLoading ? "animate-spin" : ""}`} />
            <span>Recalculate Route</span>
          </button>
        </div>
      )}

      {/* Honest Route Infeasibility / API Error Diagnostics */}
      {routeError && (
        <div className="bg-red-950/50 border border-red-500/50 rounded-xl px-4 py-3 text-xs text-red-200 flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-red-100">Route Constraint / Terrain Feasibility Rejection</div>
            <p className="text-red-200/90 leading-relaxed">{routeError}</p>
          </div>
        </div>
      )}

      {/* Main Split Workspace */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
        {/* LEFT COLUMN: Mission & Planning Controls (4 cols) */}
        <div className="xl:col-span-4 space-y-4">
          {/* 1. Start, Destination & Intermediate Waypoints */}
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-emerald-400" />
                Positions &amp; Waypoints
              </h2>
              <span className="text-[10px] font-mono text-slate-400">
                Click 3D terrain after picking tool
              </span>
            </div>

            {/* Start Point */}
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-emerald-500/25 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-emerald-300">Start Station</span>
                <button
                  type="button"
                  onClick={() =>
                    setSurfacePickMode(surfacePickMode === "set_start" ? "inspect" : "set_start")
                  }
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                    surfacePickMode === "set_start"
                      ? "bg-emerald-500 text-[#070a10] font-bold"
                      : "bg-[#172033] text-emerald-300 hover:bg-[#1e2940]"
                  }`}
                >
                  {surfacePickMode === "set_start" ? "Click 3D Terrain..." : "Pick on 3D"}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[10px] font-mono text-slate-400">
                  Lat (°)
                  <input
                    type="number"
                    step="0.0001"
                    value={startPoint?.lat ?? ""}
                    onChange={(e) => handleCoordEdit("start", "lat", e.target.value)}
                    className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                  />
                </label>
                <label className="text-[10px] font-mono text-slate-400">
                  Lon East (°)
                  <input
                    type="number"
                    step="0.0001"
                    value={startPoint?.lon_east ?? ""}
                    onChange={(e) => handleCoordEdit("start", "lon_east", e.target.value)}
                    className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                  />
                </label>
              </div>
            </div>

            {/* Destination Point */}
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-rose-500/25 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-rose-300">Final Objective</span>
                <button
                  type="button"
                  onClick={() =>
                    setSurfacePickMode(
                      surfacePickMode === "set_destination" ? "inspect" : "set_destination"
                    )
                  }
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                    surfacePickMode === "set_destination"
                      ? "bg-rose-500 text-white font-bold"
                      : "bg-[#172033] text-rose-300 hover:bg-[#1e2940]"
                  }`}
                >
                  {surfacePickMode === "set_destination" ? "Click 3D Terrain..." : "Pick on 3D"}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="text-[10px] font-mono text-slate-400">
                  Lat (°)
                  <input
                    type="number"
                    step="0.0001"
                    value={destinationPoint?.lat ?? ""}
                    onChange={(e) => handleCoordEdit("destination", "lat", e.target.value)}
                    className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                  />
                </label>
                <label className="text-[10px] font-mono text-slate-400">
                  Lon East (°)
                  <input
                    type="number"
                    step="0.0001"
                    value={destinationPoint?.lon_east ?? ""}
                    onChange={(e) => handleCoordEdit("destination", "lon_east", e.target.value)}
                    className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                  />
                </label>
              </div>
            </div>

            {/* Custom 3D Waypoints */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-300 font-medium flex items-center gap-1">
                  <Flag className="w-3 h-3 text-amber-400" />
                  Custom Waypoints ({customWaypoints.length})
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      setSurfacePickMode(
                        surfacePickMode === "add_waypoint" ? "inspect" : "add_waypoint"
                      )
                    }
                    className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                      surfacePickMode === "add_waypoint"
                        ? "bg-amber-500 text-[#070a10] font-bold"
                        : "bg-[#172033] text-amber-300 hover:bg-[#1e2940]"
                    }`}
                  >
                    {surfacePickMode === "add_waypoint" ? "Clicking..." : "+ Pick Waypt"}
                  </button>
                  {customWaypoints.length > 0 && (
                    <button
                      type="button"
                      onClick={() => clearCustomWaypoints()}
                      className="text-[10px] text-slate-400 hover:text-red-300"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
              {customWaypoints.map((wp, idx) => (
                <div
                  key={`${wp.lat}-${wp.lon_east}-${idx}`}
                  className="flex items-center justify-between bg-[#0d111a] border border-[#1e2638] rounded px-2 py-1 text-[10px] font-mono text-slate-300"
                >
                  <span>
                    {wp.label || `Waypt ${idx + 1}`}: {wp.lat.toFixed(4)}°, {wp.lon_east.toFixed(4)}° E
                  </span>
                  <button
                    type="button"
                    onClick={() => removeCustomWaypoint(idx)}
                    className="text-slate-500 hover:text-red-400"
                    title="Remove waypoint"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* 2. Verified Science Targets Multi-Select */}
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-purple-400" />
                Verified Science Targets ({selectedTargetIds.length}/{targets.length})
              </h2>
              <Link href="/targets" className="text-[10px] text-cyan-400 hover:underline">
                Manage Targets →
              </Link>
            </div>
            {targets.length === 0 ? (
              <div className="text-xs text-slate-400 bg-[#0d111a] border border-[#1e2638] rounded-lg p-3">
                No saved science targets yet. Register evidence-backed discoveries from{" "}
                <Link href="/explorer" className="text-cyan-400 underline">
                  Explorer
                </Link>{" "}
                or inspect direct coordinates above.
              </div>
            ) : (
              <div className="max-h-44 overflow-y-auto space-y-1.5 pr-1">
                {targets.map((t) => {
                  const checked = selectedTargetIds.includes(t.id);
                  return (
                    <label
                      key={t.id}
                      className={`flex items-start gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${
                        checked
                          ? "bg-purple-950/35 border-purple-500/45"
                          : "bg-[#0d111a] border-[#1e2638] hover:border-[#2a3652]"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTargetId(t.id)}
                        className="mt-0.5 accent-purple-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-semibold text-slate-100 truncate">
                          {t.name}
                        </div>
                        <div className="text-[10px] font-mono text-slate-400">
                          {t.matched_species || t.geology_type} · {t.latitude.toFixed(4)}°,{" "}
                          {t.longitude.toFixed(4)}° E
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* 3. Planning Mode & Algorithm */}
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
              <Compass className="w-3.5 h-3.5 text-cyan-400" />
              Optimization Strategy &amp; Constraints
            </h2>

            <div className="grid grid-cols-1 gap-1.5">
              {modeOptions.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setActiveMode(m.id)}
                  className={`text-left px-3 py-2 rounded-lg border transition-colors ${
                    activeMode === m.id
                      ? "bg-[#e25b38]/20 border-[#e25b38]/60 text-white"
                      : "bg-[#0d111a] border-[#1e2638] text-slate-300 hover:border-[#2a3652]"
                  }`}
                >
                  <div className="text-xs font-semibold">{m.label}</div>
                  <div className="text-[10px] text-slate-400">{m.desc}</div>
                </button>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <label className="text-[10px] font-mono text-slate-400">
                Max Slope Limit (°)
                <input
                  type="number"
                  min={2}
                  max={45}
                  step={1}
                  value={constraints.max_slope_deg}
                  onChange={(e) =>
                    updateConstraints({
                      max_slope_deg: Math.max(2, Math.min(45, Number(e.target.value) || 20)),
                    })
                  }
                  className="mt-0.5 w-full bg-[#0d111a] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                />
              </label>

              <label className="text-[10px] font-mono text-slate-400">
                Max Roughness TRI (m)
                <input
                  type="number"
                  min={0.1}
                  step={0.1}
                  placeholder="Optional"
                  value={constraints.max_roughness_tri_m ?? ""}
                  onChange={(e) => {
                    const v = e.target.value.trim();
                    updateConstraints({
                      max_roughness_tri_m: v === "" ? null : Math.max(0.1, Number(v)),
                    });
                  }}
                  className="mt-0.5 w-full bg-[#0d111a] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                />
              </label>

              <label className="text-[10px] font-mono text-slate-400">
                Snap Radius (m)
                <input
                  type="number"
                  min={5}
                  max={500}
                  step={5}
                  value={constraints.snap_radius_m}
                  onChange={(e) =>
                    updateConstraints({
                      snap_radius_m: Math.max(5, Math.min(500, Number(e.target.value) || 60)),
                    })
                  }
                  className="mt-0.5 w-full bg-[#0d111a] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                />
              </label>

              <label className="text-[10px] font-mono text-slate-400">
                Solver Algorithm
                <select
                  value={algorithm}
                  onChange={(e) => setAlgorithm(e.target.value as PathAlgorithm)}
                  className="mt-0.5 w-full bg-[#0d111a] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                >
                  <option value="astar">A* (Admissible)</option>
                  <option value="dijkstra">Dijkstra (Exact)</option>
                </select>
              </label>
            </div>

            {/* Transparent Walking Speed Assumption Control */}
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-amber-500/25 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <label className="flex items-center gap-1.5 text-[11px] font-medium text-slate-200 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={constraints.walking_speed_m_per_s != null}
                    onChange={(e) =>
                      updateConstraints({
                        walking_speed_m_per_s: e.target.checked ? 0.8 : null,
                        walking_speed_provenance: e.target.checked
                          ? "User-Configured Planning Assumption (Unvalidated)"
                          : null,
                      })
                    }
                    className="accent-amber-500"
                  />
                  <span>Model Duration w/ Speed Assumption</span>
                </label>
                <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">
                  Unvalidated Input
                </span>
              </div>

              {constraints.walking_speed_m_per_s != null && (
                <div className="grid grid-cols-2 gap-2">
                  <label className="text-[10px] font-mono text-slate-400">
                    Flat Speed (m/s)
                    <input
                      type="number"
                      min={0.1}
                      max={3.0}
                      step={0.1}
                      value={constraints.walking_speed_m_per_s}
                      onChange={(e) =>
                        updateConstraints({
                          walking_speed_m_per_s: Math.max(0.1, Number(e.target.value) || 0.8),
                        })
                      }
                      className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                    />
                  </label>
                  <label className="text-[10px] font-mono text-slate-400">
                    EVA Budget (hrs)
                    <input
                      type="number"
                      min={0.2}
                      max={24}
                      step={0.5}
                      value={constraints.max_eva_duration_hours ?? 4}
                      onChange={(e) =>
                        updateConstraints({
                          max_eva_duration_hours: Math.max(0.2, Number(e.target.value) || 4),
                        })
                      }
                      className="mt-0.5 w-full bg-[#131926] border border-[#243047] rounded px-2 py-1 text-xs text-slate-100"
                    />
                  </label>
                </div>
              )}

              <div className="flex flex-wrap gap-3 text-[11px] text-slate-300 pt-1">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={constraints.return_to_start}
                    onChange={(e) => updateConstraints({ return_to_start: e.target.checked })}
                    className="accent-cyan-500"
                  />
                  <span>Return to Start</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={constraints.optimize_target_order}
                    onChange={(e) => updateConstraints({ optimize_target_order: e.target.checked })}
                    className="accent-cyan-500"
                  />
                  <span>Optimize Visit Order</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={constraints.enforce_budget}
                    onChange={(e) => updateConstraints({ enforce_budget: e.target.checked })}
                    className="accent-amber-500"
                  />
                  <span>Enforce Budget Reserve ({Math.round(constraints.safety_reserve_fraction * 100)}%)</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: 3D Terrain Viewport + Elevation Profile + Turn-by-Turn Instructions (8 cols) */}
        <div className="xl:col-span-8 space-y-4">
          {/* Interactive 3D Martian DEM Viewport */}
          <div className="h-[460px] lg:h-[510px]">
            <LocalTerrain3DViewer targets={targets} />
          </div>

          {!activeRoute ? (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6 text-center space-y-2">
              <Layers className="w-7 h-7 text-cyan-400 mx-auto" />
              <div className="text-sm font-semibold text-slate-200">
                No Route Computed for Current Configuration
              </div>
              <p className="text-xs text-slate-400 max-w-xl mx-auto">
                Verify Start/Destination positions on the 3D terrain mesh above (default pre-loaded to real Curiosity Boxwork Crater DEM coordinates) and click{" "}
                <strong className="text-slate-200">Compute Route</strong> or{" "}
                <strong className="text-cyan-300">Compare 3 Modes</strong>.
              </p>
            </div>
          ) : (
            <>
              {/* Route Telemetry KPI Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2.5">
                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">3D Surface Dist</div>
                  <div className="text-base font-bold font-mono text-cyan-300 mt-0.5">
                    {activeRoute.total_surface_distance_m.toFixed(1)} m
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    Planar: {activeRoute.total_horizontal_distance_m.toFixed(1)} m
                  </div>
                </div>

                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Elev Gain / Loss</div>
                  <div className="text-base font-bold font-mono text-slate-100 mt-0.5">
                    +{activeRoute.total_elevation_gain_m.toFixed(1)} / -{activeRoute.total_elevation_loss_m.toFixed(1)} m
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    Net: {activeRoute.net_elevation_change_m >= 0 ? "+" : ""}
                    {activeRoute.net_elevation_change_m.toFixed(1)} m
                  </div>
                </div>

                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Slope Max / Mean</div>
                  <div className="text-base font-bold font-mono text-amber-300 mt-0.5">
                    {activeRoute.max_slope_deg.toFixed(1)}° / {activeRoute.mean_slope_deg.toFixed(1)}°
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    Cap: {activeRoute.effective_slope_limit_deg.toFixed(1)}°
                  </div>
                </div>

                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Est. Duration</div>
                  <div className="text-sm font-bold font-mono text-slate-100 mt-0.5">
                    {formatDurationSeconds(activeRoute.estimated_duration_seconds)}
                  </div>
                  <div className="text-[10px] text-amber-300/80 truncate" title={activeRoute.assumption_classification}>
                    {activeRoute.assumption_classification}
                  </div>
                </div>

                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Science Corridor</div>
                  <div className="text-base font-bold font-mono text-purple-300 mt-0.5">
                    {activeRoute.corridor_evidence_hits_within_150m} hits
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    {activeRoute.science_targets_reached.length} targets visited
                  </div>
                </div>

                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3">
                  <div className="text-[10px] font-mono uppercase text-slate-400">Solver &amp; DEM</div>
                  <div className="text-sm font-bold font-mono text-emerald-300 mt-0.5">
                    {activeRoute.compute_time_ms.toFixed(1)} ms
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    {activeRoute.solver_grid_spacing_m.toFixed(1)} m grid · {activeRoute.nodes_expanded} exp
                  </div>
                </div>
              </div>

              {/* Elevation Profile Chart */}
              <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Elevation Profile Along Computed Route ({activeRoute.source_product_id})
                  </h3>
                  <span className="text-[10px] font-mono text-slate-400">
                    Min {activeRoute.min_elevation_m.toFixed(1)} m · Max {activeRoute.max_elevation_m.toFixed(1)} m · Mean TRI{" "}
                    {activeRoute.mean_roughness_tri_m != null
                      ? `${activeRoute.mean_roughness_tri_m.toFixed(2)} m`
                      : "N/A"}
                  </span>
                </div>
                <div className="h-44 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={activeRoute.vertices}
                      margin={{ top: 8, right: 16, left: 4, bottom: 4 }}
                    >
                      <defs>
                        <linearGradient id="elevFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.38} />
                          <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.03} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        dataKey="cumulative_distance_m"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        tickFormatter={(v: number) => `${Math.round(v)}m`}
                        tick={{ fill: "#94a3b8", fontSize: 10 }}
                        stroke="#334155"
                      />
                      <YAxis
                        domain={["auto", "auto"]}
                        tickFormatter={(v: number) => `${Math.round(v)}m`}
                        tick={{ fill: "#94a3b8", fontSize: 10 }}
                        stroke="#334155"
                        width={56}
                      />
                      <Tooltip content={<ElevationChartTooltip />} />
                      <Area
                        type="monotone"
                        dataKey="elevation_m"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        fill="url(#elevFill)"
                        isAnimationActive={false}
                      />
                      {stopVertices.map((sv) => (
                        <ReferenceDot
                          key={sv.seq}
                          x={sv.cumulative_distance_m}
                          y={sv.elevation_m}
                          r={selectedWaypointSeq === sv.seq ? 6 : 4}
                          fill={selectedWaypointSeq === sv.seq ? "#fde047" : "#f43f5e"}
                          stroke="#0b101b"
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Turn-by-Turn Astronaut Navigation Directions Table */}
              <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                      <Navigation className="w-3.5 h-3.5 text-cyan-400" />
                      Turn-by-Turn Astronaut Navigation ({activeRoute.instructions.length} steps)
                    </h3>
                    <p className="text-[10px] font-mono text-slate-400 mt-0.5">
                      {activeRoute.bearing_convention} · Click any row to focus 3D camera on waypoint
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowDiagnostics((v) => !v)}
                    className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#161c2b] border border-[#252f44] text-slate-300 hover:text-white"
                  >
                    {showDiagnostics ? "Hide Diagnostics" : "Show Provenance & Diagnostics"}
                  </button>
                </div>

                <div className="overflow-x-auto max-h-72 overflow-y-auto border border-[#1e2638] rounded-lg">
                  <table className="w-full text-left text-[11px]">
                    <thead className="bg-[#0d111a] text-[10px] font-mono uppercase text-slate-400 sticky top-0">
                      <tr>
                        <th className="px-2.5 py-2">#</th>
                        <th className="px-2.5 py-2">Heading</th>
                        <th className="px-2.5 py-2">Dist / Cum</th>
                        <th className="px-2.5 py-2">Elev &amp; Grade</th>
                        <th className="px-2.5 py-2">Instruction &amp; Terrain</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1a2233]">
                      {activeRoute.instructions.map((inst) => {
                        const isSelected = selectedInstructionStep === inst.step_index;
                        return (
                          <tr
                            key={inst.step_index}
                            onClick={() => selectInstructionStep(inst.step_index, true)}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? "bg-cyan-950/50 text-white"
                                : "hover:bg-[#171e2f] text-slate-200"
                            }`}
                          >
                            <td className="px-2.5 py-2 font-mono text-slate-400">
                              {inst.step_index}
                            </td>
                            <td className="px-2.5 py-2 font-mono whitespace-nowrap">
                              {inst.bearing_true_north_deg != null ? (
                                <div>
                                  <span className="text-cyan-300 font-semibold">
                                    {inst.bearing_true_north_deg.toFixed(0)}°T
                                  </span>{" "}
                                  <span className="text-slate-400">({inst.cardinal_direction})</span>
                                  {inst.bearing_grid_north_deg != null && (
                                    <div className="text-[10px] text-slate-500">
                                      {inst.bearing_grid_north_deg.toFixed(0)}°G
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <span className="text-emerald-300 uppercase">{inst.action}</span>
                              )}
                            </td>
                            <td className="px-2.5 py-2 font-mono whitespace-nowrap">
                              <div>{inst.segment_distance_m.toFixed(1)} m</div>
                              <div className="text-[10px] text-slate-500">
                                Σ {inst.cumulative_distance_m.toFixed(0)} m
                              </div>
                            </td>
                            <td className="px-2.5 py-2 font-mono whitespace-nowrap">
                              <div
                                className={
                                  inst.elevation_delta_m >= 0 ? "text-amber-300" : "text-sky-300"
                                }
                              >
                                {inst.elevation_delta_m >= 0 ? "+" : ""}
                                {inst.elevation_delta_m.toFixed(1)} m ({inst.grade_percent >= 0 ? "+" : ""}
                                {inst.grade_percent.toFixed(1)}%)
                              </div>
                              <div className="text-[10px] text-slate-500">
                                Slope {inst.segment_slope_deg.toFixed(1)}°
                              </div>
                            </td>
                            <td className="px-2.5 py-2 space-y-0.5">
                              <div>{inst.instruction_text}</div>
                              {inst.caution_notes.length > 0 && (
                                <div className="text-[10px] text-amber-300">
                                  Caution: {inst.caution_notes.join(" · ")}
                                </div>
                              )}
                              {inst.nearby_science_targets.length > 0 && (
                                <div className="text-[10px] text-purple-300">
                                  Targets: {inst.nearby_science_targets.join(", ")}
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Provenance, Simplification & Limitations Drawer */}
                {showDiagnostics && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-[#1e2638] text-[11px]">
                    <div className="bg-[#0d111a] border border-[#1e2638] rounded-lg p-3 space-y-1.5 font-mono">
                      <div className="text-slate-300 font-bold">Simplification &amp; Graph Integrity</div>
                      <div className="text-slate-400">
                        Raw grid nodes: {activeRoute.simplification_diagnostic.raw_grid_nodes} →{" "}
                        Simplified vertices: {activeRoute.simplification_diagnostic.simplified_vertices}
                      </div>
                      <div className="text-slate-400">
                        Shortcuts checked: {activeRoute.simplification_diagnostic.segments_checked} (Rejected obstacle/nodata:{" "}
                        {activeRoute.simplification_diagnostic.shortcuts_rejected_obstacle_or_nodata})
                      </div>
                      <div className="text-emerald-300">
                        Obstacle-checked segments:{" "}
                        {String(activeRoute.simplification_diagnostic.all_simplified_segments_verified_valid)}
                      </div>
                      <div className="text-slate-400 pt-1">
                        Signature: {activeRoute.route_signature}
                      </div>
                    </div>

                    <div className="bg-[#0d111a] border border-[#1e2638] rounded-lg p-3 space-y-1">
                      <div className="text-slate-300 font-bold font-mono">Scientific Limitations</div>
                      <ul className="list-disc pl-4 space-y-1 text-slate-400">
                        {activeRoute.limitations.map((lim, i) => (
                          <li key={i}>{lim}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
