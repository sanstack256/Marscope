"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  MapPinOff,
  Navigation,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Route as RouteIcon,
} from "lucide-react";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import { useRoutingStore } from "@/stores/useRoutingStore";
import { useTrackingStore } from "@/stores/useTrackingStore";

const MARS_SURFACE_GRAVITY_M_S2 = 3.72076; // NASA Mars Fact Sheet / IAU reference gravity for mechanical climb work only

export default function EvaSimulationPage() {
  const targets = useRoutingStore((s) => s.availableTargets);
  const targetsLoaded = useRoutingStore((s) => s.targetsLoaded);
  const fetchTargets = useRoutingStore((s) => s.fetchAvailableTargets);

  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const constraints = useRoutingStore((s) => s.constraints);
  const routeLoading = useRoutingStore((s) => s.routeLoading);
  const loadBoxworkStudyExample = useRoutingStore((s) => s.loadBoxworkStudyExample);
  const computeRoute = useRoutingStore((s) => s.computeRoute);

  const trackingStatus = useTrackingStore((s) => s.trackingStatus);
  const replanPreview = useTrackingStore((s) => s.replanPreview);
  const replanLoading = useTrackingStore((s) => s.replanLoading);
  const replanError = useTrackingStore((s) => s.replanError);
  const connectTrackingStream = useTrackingStore((s) => s.connectTrackingStream);
  const requestReplanPreview = useTrackingStore((s) => s.requestReplanPreview);
  const adoptReplanPreview = useTrackingStore((s) => s.adoptReplanPreview);
  const dismissReplanPreview = useTrackingStore((s) => s.dismissReplanPreview);

  const [progressState, setProgressState] = useState<{ routeId: string | null; m: number }>({
    routeId: activeRoute?.route_id ?? null,
    m: 0,
  });
  const [playingRouteId, setPlayingRouteId] = useState<string | null>(null);
  const [speedMult, setSpeedMult] = useState(2);

  useEffect(() => {
    if (!targetsLoaded) void fetchTargets();
  }, [targetsLoaded, fetchTargets]);

  useEffect(() => {
    return connectTrackingStream(activeRoute?.route_id ?? null);
  }, [activeRoute?.route_id, connectTrackingStream]);

  const currentRouteId = activeRoute?.route_id ?? null;
  const maxDistM = activeRoute?.total_surface_distance_m ?? 0;
  const progressM =
    progressState.routeId === currentRouteId
      ? Math.min(maxDistM, Math.max(0, progressState.m))
      : 0;
  const playing = playingRouteId !== null && playingRouteId === currentRouteId;

  useEffect(() => {
    if (!playing || !activeRoute || maxDistM <= 0 || !currentRouteId) return;
    let lastTs = performance.now();
    let rafId = 0;
    const step = (now: number) => {
      const dt = (now - lastTs) / 1000;
      lastTs = now;
      const baseSpeed = constraints.walking_speed_m_per_s ?? 0.8;
      setProgressState((prev) => {
        const curM = prev.routeId === currentRouteId ? prev.m : 0;
        const next = curM + dt * baseSpeed * 25 * speedMult;
        if (next >= maxDistM) {
          setPlayingRouteId(null);
          return { routeId: currentRouteId, m: maxDistM };
        }
        return { routeId: currentRouteId, m: next };
      });
      rafId = window.requestAnimationFrame(step);
    };
    rafId = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(rafId);
  }, [playing, activeRoute, currentRouteId, maxDistM, constraints.walking_speed_m_per_s, speedMult]);

  const sample = useMemo(() => {
    if (!activeRoute || activeRoute.vertices.length === 0) return null;
    const verts = activeRoute.vertices;
    let cur = verts[0];
    let gainM = 0;
    for (let i = 0; i < verts.length - 1; i += 1) {
      const a = verts[i];
      const b = verts[i + 1];
      const dz = b.elevation_m - a.elevation_m;
      if (progressM >= b.cumulative_distance_m) {
        if (dz > 0) gainM += dz;
        cur = b;
      } else if (progressM >= a.cumulative_distance_m) {
        const frac =
          (progressM - a.cumulative_distance_m) /
          Math.max(1e-6, b.cumulative_distance_m - a.cumulative_distance_m);
        if (dz > 0) gainM += dz * frac;
        cur = {
          ...a,
          lat: a.lat + (b.lat - a.lat) * frac,
          lon_east: a.lon_east + (b.lon_east - a.lon_east) * frac,
          elevation_m: a.elevation_m + dz * frac,
          slope_deg: b.slope_deg ?? a.slope_deg,
          roughness_tri_m: b.roughness_tri_m ?? a.roughness_tri_m,
          cumulative_distance_m: progressM,
        };
        break;
      }
    }

    const activeIdx = activeRoute.instructions.findIndex(
      (inst) => progressM <= inst.cumulative_distance_m + 1e-6
    );
    const resolvedIdx = activeIdx >= 0 ? activeIdx : activeRoute.instructions.length - 1;
    const activeInst = activeRoute.instructions[resolvedIdx];
    const nextInst =
      resolvedIdx + 1 < activeRoute.instructions.length
        ? activeRoute.instructions[resolvedIdx + 1]
        : null;

    const massKg = constraints.astronaut_total_mass_kg;
    const climbWorkKJ =
      massKg != null && Number.isFinite(massKg)
        ? (massKg * MARS_SURFACE_GRAVITY_M_S2 * gainM) / 1000.0
        : null;

    return {
      vertex: cur,
      cumulativeGainM: gainM,
      climbWorkKJ,
      instruction: activeInst,
      nextInstruction: nextInst,
      instructionIndex: resolvedIdx,
    };
  }, [activeRoute, progressM, constraints.astronaut_total_mass_kg]);

  const stepInstructionBy = (delta: number) => {
    if (!activeRoute || activeRoute.instructions.length === 0) return;
    setPlayingRouteId(null);
    const curIdx = sample?.instructionIndex ?? 0;
    const targetIdx = Math.max(
      0,
      Math.min(activeRoute.instructions.length - 1, curIdx + delta)
    );
    const targetDist = activeRoute.instructions[targetIdx].cumulative_distance_m;
    setProgressState({ routeId: currentRouteId, m: targetDist });
  };

  return (
    <div className="space-y-4">
      {/* Header + Explicit Simulation Isolation Disclosure */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-3">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <Activity className="w-5 h-5 text-cyan-400" />
            <h1 className="text-base font-bold text-slate-100">
              Synchronized EVA Trajectory Playback
            </h1>
            <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/50 text-amber-300">
              SIMULATION — NOT LIVE MISSION TELEMETRY
            </span>
            {activeRoute && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/35 text-cyan-300">
                {activeRoute.mode_label} · {activeRoute.source_product_id}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Deterministic playback along exact computed polyline vertices (`activeRoute.vertices`). Separate from authenticated live positioning telemetry.
          </p>
        </div>

        <Link
          href="/planner"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e273d] border border-[#2a3652] text-xs font-medium text-slate-200"
        >
          <span>Edit Route in Planner</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {!activeRoute ? (
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-8 text-center space-y-3">
          <RouteIcon className="w-8 h-8 text-[#e25b38] mx-auto" />
          <div className="text-sm font-semibold text-slate-100">
            No Active Route Selected for Simulation
          </div>
          <p className="text-xs text-slate-400 max-w-lg mx-auto">
            Configure custom endpoints in the Route Planner or load and simulate the Boxwork Study Example coordinates over the real HiRISE DEM.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
            {startPoint && destinationPoint ? (
              <button
                type="button"
                onClick={() => void computeRoute()}
                disabled={routeLoading}
                className="px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#c84d2d] text-xs font-semibold text-white disabled:opacity-50"
              >
                {routeLoading ? "Computing Route..." : "Compute Active Route"}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  loadBoxworkStudyExample();
                  setTimeout(() => void computeRoute(), 60);
                }}
                disabled={routeLoading}
                className="px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#c84d2d] text-xs font-semibold text-white disabled:opacity-50"
              >
                {routeLoading ? "Computing Study Example..." : "Load & Simulate Boxwork Study Example"}
              </button>
            )}
            <Link
              href="/planner"
              className="px-4 py-2 rounded-lg bg-[#161c2b] border border-[#2a3652] text-xs font-medium text-slate-200"
            >
              Go to Planner
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          {/* 3D Terrain Playback Viewport (8 cols) */}
          <div className="xl:col-span-8 space-y-3">
            <div className="h-[460px] lg:h-[520px]">
              <LocalTerrain3DViewer
                compact
                targets={targets}
                simulationProgressM={progressM}
                livePositionMarker={
                  trackingStatus?.live_available &&
                  trackingStatus.lat != null &&
                  trackingStatus.lon_east != null
                    ? {
                        lat: trackingStatus.lat,
                        lon_east: trackingStatus.lon_east,
                        elevation_m: trackingStatus.elevation_m,
                        off_route: trackingStatus.route_relative?.off_route,
                        heading_deg: trackingStatus.heading_deg,
                      }
                    : null
                }
              />
            </div>

            {/* Playback Controls */}
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (!currentRouteId) return;
                      if (progressM >= maxDistM) {
                        setProgressState({ routeId: currentRouteId, m: 0 });
                      }
                      setPlayingRouteId((prev) =>
                        prev === currentRouteId ? null : currentRouteId
                      );
                    }}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs font-semibold text-white"
                  >
                    {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                    <span>{playing ? "Pause" : "Play Simulation"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => stepInstructionBy(-1)}
                    className="p-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-slate-300 hover:text-white"
                    title="Step Back One Instruction"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => stepInstructionBy(1)}
                    className="p-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-slate-300 hover:text-white"
                    title="Step Forward One Instruction"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setPlayingRouteId(null);
                      setProgressState({ routeId: currentRouteId, m: 0 });
                    }}
                    className="p-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-slate-300 hover:text-white"
                    title="Reset to Start"
                  >
                    <RotateCcw className="w-4 h-4" />
                  </button>
                  <div className="flex bg-[#0d111a] border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono">
                    {[1, 2, 5].map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setSpeedMult(s)}
                        className={`px-2 py-0.5 rounded ${
                          speedMult === s ? "bg-[#e25b38] text-white font-semibold" : "text-slate-400"
                        }`}
                      >
                        {s}x
                      </button>
                    ))}
                  </div>
                </div>

                <div className="text-xs font-mono text-cyan-300">
                  {progressM.toFixed(1)} m / {maxDistM.toFixed(1)} m (
                  {maxDistM > 0 ? Math.round((progressM / maxDistM) * 100) : 0}%)
                </div>
              </div>

              <input
                type="range"
                min={0}
                max={Math.max(1, maxDistM)}
                step={0.5}
                value={progressM}
                onChange={(e) => {
                  setPlayingRouteId(null);
                  setProgressState({ routeId: currentRouteId, m: Number(e.target.value) });
                }}
                className="w-full accent-cyan-400"
              />
            </div>
          </div>

          {/* Live Synchronized Telemetry & Scientific Honesty Disclosures (4 cols) */}
          <div className="xl:col-span-4 space-y-3">
            {sample && (
              <>
                <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-3">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Navigation className="w-3.5 h-3.5 text-cyan-400" />
                    Current Waypoint State
                  </h2>
                  <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">Latitude</div>
                      <div className="text-slate-100">{sample.vertex.lat.toFixed(5)}°</div>
                    </div>
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">Longitude E</div>
                      <div className="text-slate-100">{sample.vertex.lon_east.toFixed(5)}°</div>
                    </div>
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">DEM Elevation</div>
                      <div className="text-cyan-300 font-bold">
                        {sample.vertex.elevation_m.toFixed(2)} m
                      </div>
                    </div>
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">Local Slope / TRI</div>
                      <div className="text-amber-300 font-semibold">
                        {sample.vertex.slope_deg != null ? `${sample.vertex.slope_deg.toFixed(1)}°` : "N/A"} ·{" "}
                        {sample.vertex.roughness_tri_m != null
                          ? `${sample.vertex.roughness_tri_m.toFixed(2)}m`
                          : "N/A"}
                      </div>
                    </div>
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">Cum. Ascent</div>
                      <div className="text-slate-100">+{sample.cumulativeGainM.toFixed(1)} m</div>
                    </div>
                    <div className="bg-[#0d111a] p-2.5 rounded-lg border border-[#1e2638]">
                      <div className="text-[10px] text-slate-400">Mech. Climb Work</div>
                      <div className="text-emerald-300">
                        {sample.climbWorkKJ != null ? `${sample.climbWorkKJ.toFixed(1)} kJ` : "Mass Unset"}
                      </div>
                    </div>
                  </div>
                </div>

                {sample.instruction && (
                  <div className="bg-[#121622] border border-cyan-500/30 rounded-xl p-4 space-y-2">
                    <div className="text-[10px] font-mono uppercase text-cyan-400">
                      Active Navigation Cue (Step #{sample.instruction.step_index})
                    </div>
                    <div className="text-xs font-medium text-slate-100 leading-relaxed">
                      {sample.instruction.instruction_text}
                    </div>
                    {sample.instruction.bearing_true_north_deg != null && (
                      <div className="text-[11px] font-mono text-slate-400">
                        Bearing: {sample.instruction.bearing_true_north_deg.toFixed(0)}° True ({sample.instruction.cardinal_direction}) · Grade {sample.instruction.grade_percent.toFixed(1)}%
                      </div>
                    )}
                    {sample.nextInstruction && (
                      <div className="pt-1.5 border-t border-[#1e2638] text-[10px] font-mono text-slate-400">
                        NEXT CUE (#{sample.nextInstruction.step_index}): {sample.nextInstruction.instruction_text}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {/* Authenticated Live Mission Positioning Panel (Strictly Separated from Simulation) */}
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-200 flex items-center gap-1.5">
                  {trackingStatus?.live_available ? (
                    <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                  ) : (
                    <MapPinOff className="w-3.5 h-3.5 text-amber-400" />
                  )}
                  Live Mission Positioning
                </span>
                <span
                  className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                    trackingStatus?.live_available
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-slate-800 text-amber-300"
                  }`}
                >
                  {trackingStatus?.status ?? "disconnected"}
                </span>
              </div>

              {!trackingStatus?.live_available ? (
                <p className="text-amber-200/90 leading-relaxed">
                  {trackingStatus?.message ||
                    "Live Mars position unavailable — no mission positioning provider connected."}
                </p>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px]">
                    <div className="bg-[#0d111a] p-2 rounded border border-[#1e2638]">
                      <div className="text-[9px] text-slate-400">PROVIDER / SEQ</div>
                      <div className="text-emerald-300 truncate">
                        {trackingStatus.provider_id} #{trackingStatus.sequence_number}
                      </div>
                    </div>
                    <div className="bg-[#0d111a] p-2 rounded border border-[#1e2638]">
                      <div className="text-[9px] text-slate-400">FIX (IAU2000:49900)</div>
                      <div className="text-slate-100">
                        {trackingStatus.lat?.toFixed(5)}°, {trackingStatus.lon_east?.toFixed(5)}°E
                      </div>
                    </div>
                    {trackingStatus.route_relative && (
                      <>
                        <div className="bg-[#0d111a] p-2 rounded border border-[#1e2638]">
                          <div className="text-[9px] text-slate-400">CROSS-TRACK ERR</div>
                          <div
                            className={
                              trackingStatus.route_relative.off_route
                                ? "text-red-300 font-bold"
                                : "text-cyan-300"
                            }
                          >
                            {trackingStatus.route_relative.cross_track_error_m.toFixed(1)} m (
                            {trackingStatus.route_relative.off_route ? "OFF-ROUTE" : "IN CORRIDOR"})
                          </div>
                        </div>
                        <div className="bg-[#0d111a] p-2 rounded border border-[#1e2638]">
                          <div className="text-[9px] text-slate-400">REMAINING DIST</div>
                          <div className="text-slate-100">
                            {trackingStatus.route_relative.remaining_distance_m.toFixed(1)} m
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  {activeRoute && (
                    <button
                      type="button"
                      disabled={replanLoading}
                      onClick={() => void requestReplanPreview(activeRoute.route_id)}
                      className="w-full py-1.5 px-3 rounded-lg bg-amber-600/25 hover:bg-amber-600/40 border border-amber-500/40 text-amber-200 font-semibold flex items-center justify-center gap-1.5"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${replanLoading ? "animate-spin" : ""}`} />
                      <span>Preview DEM Replan Diff from Live Fix</span>
                    </button>
                  )}
                  {replanError && (
                    <div className="text-[10px] text-red-300 font-mono">{replanError}</div>
                  )}
                  {replanPreview && (
                    <div className="p-2.5 rounded-lg bg-[#161c2b] border border-cyan-500/40 space-y-2 text-[11px]">
                      <div className="font-bold text-cyan-300">
                        Confirmation Required: Live Replan Diff
                      </div>
                      <div className="font-mono text-slate-300 space-y-0.5">
                        <div>
                          Dist delta: {replanPreview.distance_delta_m >= 0 ? "+" : ""}
                          {replanPreview.distance_delta_m.toFixed(1)} m
                        </div>
                        <div>
                          Gain delta: {replanPreview.elevation_gain_delta_m >= 0 ? "+" : ""}
                          {replanPreview.elevation_gain_delta_m.toFixed(1)} m
                        </div>
                        <div>
                          Max slope delta: {replanPreview.max_slope_delta_deg >= 0 ? "+" : ""}
                          {replanPreview.max_slope_delta_deg.toFixed(1)}°
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => adoptReplanPreview()}
                          className="flex-1 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                        >
                          Confirm Adopt
                        </button>
                        <button
                          type="button"
                          onClick={() => dismissReplanPreview()}
                          className="px-2.5 py-1 rounded bg-slate-800 text-slate-300"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Honest Telemetry Disclosure Card */}
            <div className="bg-amber-950/35 border border-amber-500/40 rounded-xl p-4 space-y-2 text-xs">
              <div className="flex items-center gap-2 text-amber-300 font-semibold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>Unmodeled Physiological &amp; Consumables Disclosure</span>
              </div>
              <p className="text-amber-200/85 leading-relaxed">
                <strong>Oxygen (O₂) reserve, CO₂ scrubbing, suit battery SoC, and metabolic calorie curves: Not Modeled (Unvalidated).</strong>
              </p>
              <p className="text-amber-200/75 leading-relaxed">
                This timeline animates geometric position, NASA DEM elevation, slope, bearing, and potential-energy climb work (m·g_Mars·Δh) from declared mass ({constraints.astronaut_total_mass_kg ?? "unset"} kg) and speed ({constraints.walking_speed_m_per_s != null ? `${constraints.walking_speed_m_per_s} m/s` : "omitted"}). No suit-telemetry fabrication is performed.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
