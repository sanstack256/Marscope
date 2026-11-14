"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Navigation,
  Pause,
  Play,
  RotateCcw,
  Route as RouteIcon,
} from "lucide-react";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import { useRoutingStore } from "@/stores/useRoutingStore";

const MARS_SURFACE_GRAVITY_M_S2 = 3.72076; // NASA Mars Fact Sheet / IAU reference gravity for mechanical climb work only

export default function EvaSimulationPage() {
  const targets = useRoutingStore((s) => s.availableTargets);
  const targetsLoaded = useRoutingStore((s) => s.targetsLoaded);
  const fetchTargets = useRoutingStore((s) => s.fetchAvailableTargets);

  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const constraints = useRoutingStore((s) => s.constraints);
  const routeLoading = useRoutingStore((s) => s.routeLoading);
  const computeRoute = useRoutingStore((s) => s.computeRoute);

  const [progressState, setProgressState] = useState<{ routeId: string | null; m: number }>({
    routeId: activeRoute?.route_id ?? null,
    m: 0,
  });
  const [playingRouteId, setPlayingRouteId] = useState<string | null>(null);
  const [speedMult, setSpeedMult] = useState(2);

  useEffect(() => {
    if (!targetsLoaded) void fetchTargets();
  }, [targetsLoaded, fetchTargets]);

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

    const activeInst =
      activeRoute.instructions.find(
        (inst) => progressM <= inst.cumulative_distance_m + 1e-6
      ) ?? activeRoute.instructions[activeRoute.instructions.length - 1];

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
    };
  }, [activeRoute, progressM, constraints.astronaut_total_mass_kg]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-3">
        <div>
          <div className="flex items-center gap-2.5">
            <Activity className="w-5 h-5 text-cyan-400" />
            <h1 className="text-base font-bold text-slate-100">
              Synchronized EVA Trajectory Playback
            </h1>
            {activeRoute && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/35 text-cyan-300">
                {activeRoute.mode_label} · {activeRoute.source_product_id}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Scrub real DEM elevation, slope, heading, and gravitational climb work along the active route without fabricated metabolic or O2 curves.
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
            Compute the default Curiosity Boxwork Crater EVA route directly or configure custom targets and constraints in the Route Planner first.
          </p>
          <div className="flex items-center justify-center gap-3 pt-1">
            <button
              type="button"
              onClick={() => void computeRoute()}
              disabled={routeLoading}
              className="px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#c84d2d] text-xs font-semibold text-white disabled:opacity-50"
            >
              {routeLoading ? "Computing Route..." : "Compute Default Boxwork Route"}
            </button>
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
                    <span>{playing ? "Pause" : "Play Traversal"}</span>
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
                  </div>
                )}
              </>
            )}

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
