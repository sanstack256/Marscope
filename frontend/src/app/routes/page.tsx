"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  Loader2,
  RefreshCw,
  Scale,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useRoutingStore } from "@/stores/useRoutingStore";
import type { RouteCompareEntry } from "@/types";

export default function RoutesComparisonPage() {
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const constraints = useRoutingStore((s) => s.constraints);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const comparisonResult = useRoutingStore((s) => s.comparisonResult);
  const compareLoading = useRoutingStore((s) => s.compareLoading);
  const routeError = useRoutingStore((s) => s.routeError);
  const staleRoute = useRoutingStore((s) => s.staleRoute);
  const compareRoutes = useRoutingStore((s) => s.compareRoutes);
  const selectComparedRoute = useRoutingStore((s) => s.selectComparedRoute);
  const exportActiveGeoJSON = useRoutingStore((s) => s.exportActiveGeoJSON);

  const autoTriggeredRef = useRef(false);

  useEffect(() => {
    if (!comparisonResult && !compareLoading && !autoTriggeredRef.current && startPoint && destinationPoint) {
      autoTriggeredRef.current = true;
      void compareRoutes();
    }
  }, [comparisonResult, compareLoading, startPoint, destinationPoint, compareRoutes]);

  const chartData =
    comparisonResult?.comparison
      .filter((c) => c.feasible && c.route)
      .map((c) => ({
        mode: c.mode_label,
        "Surface Dist (m)": Number(c.route!.total_surface_distance_m.toFixed(1)),
        "Elev Gain (m)": Number(c.route!.total_elevation_gain_m.toFixed(1)),
        "Evidence Hits": c.route!.corridor_evidence_hits_within_150m,
      })) ?? [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-3">
        <div>
          <div className="flex items-center gap-2.5">
            <Scale className="w-5 h-5 text-cyan-400" />
            <h1 className="text-base font-bold text-slate-100">
              Route Trade-Off Comparison Matrix
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#161c2b] border border-[#2a3652] text-cyan-300">
              {comparisonResult?.source_product_id || selectedDemDatasetId}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Evaluate Conservative (&le;16°), Balanced, and Science Priority trajectories across the identical real DEM graph and constraints.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void compareRoutes()}
            disabled={compareLoading || !startPoint || !destinationPoint}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#c84d2d] text-xs font-semibold text-white transition-colors disabled:opacity-50"
          >
            {compareLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span>{compareLoading ? "Comparing 3 Modes..." : "Run 3-Mode Comparison"}</span>
          </button>

          <Link
            href="/planner"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e273d] border border-[#2a3652] text-xs font-medium text-slate-200"
          >
            <span>Open 3D Planner</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Stale Banner */}
      {staleRoute && (
        <div className="flex items-center justify-between gap-2 bg-amber-950/50 border border-amber-500/40 rounded-xl px-4 py-2.5 text-xs text-amber-200">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              Constraints or waypoints changed in Planner. Re-run 3-mode comparison to keep metrics synchronized.
            </span>
          </div>
          <button
            type="button"
            onClick={() => void compareRoutes()}
            className="px-3 py-1 rounded bg-amber-500 hover:bg-amber-400 text-[#0b101b] font-semibold"
          >
            Refresh Comparison
          </button>
        </div>
      )}

      {routeError && (
        <div className="bg-red-950/50 border border-red-500/40 rounded-xl px-4 py-3 text-xs text-red-200">
          {routeError}
        </div>
      )}

      {/* Active Endpoints & Constraints Bar */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-2.5 flex flex-wrap items-center gap-x-6 gap-y-1 text-[11px] font-mono text-slate-300">
        <span>
          <strong className="text-emerald-300">START:</strong>{" "}
          {startPoint ? `${startPoint.lat.toFixed(5)}°, ${startPoint.lon_east.toFixed(5)}° E` : "Unset"}
        </span>
        <span>
          <strong className="text-rose-300">DEST:</strong>{" "}
          {destinationPoint
            ? `${destinationPoint.lat.toFixed(5)}°, ${destinationPoint.lon_east.toFixed(5)}° E`
            : "Unset"}
        </span>
        <span>
          <strong>USER SLOPE CAP:</strong> {constraints.max_slope_deg}°
        </span>
        <span>
          <strong>RETURN LEG:</strong> {constraints.return_to_start ? "Included" : "One-Way"}
        </span>
        <span>
          <strong>SPEED ASSUMPTION:</strong>{" "}
          {constraints.walking_speed_m_per_s != null
            ? `${constraints.walking_speed_m_per_s} m/s (Unvalidated User Assumption)`
            : "Omitted (Geometry Only)"}
        </span>
      </div>

      {/* 3-Mode Comparison Cards */}
      {comparisonResult && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {comparisonResult.comparison.map((entry: RouteCompareEntry) => {
              const r = entry.route;
              const isActive = Boolean(r && activeRoute?.route_id === r.route_id);
              return (
                <div
                  key={entry.mode}
                  className={`rounded-xl border p-4 flex flex-col justify-between space-y-4 ${
                    !entry.feasible
                      ? "bg-[#141118] border-red-500/35"
                      : isActive
                        ? "bg-[#121a2a] border-cyan-400/60"
                        : "bg-[#121622] border-[#1e2638]"
                  }`}
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-bold text-slate-100 flex items-center gap-1.5">
                          {entry.mode === "science_priority" && (
                            <Sparkles className="w-4 h-4 text-purple-400" />
                          )}
                          <span>{entry.mode_label}</span>
                        </div>
                        <div className="text-[10px] font-mono text-slate-400 uppercase mt-0.5">
                          mode: {entry.mode}
                        </div>
                      </div>
                      {entry.feasible ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/35 text-emerald-300">
                          <CheckCircle2 className="w-3 h-3" />
                          Feasible
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/15 border border-red-500/40 text-red-300">
                          <ShieldAlert className="w-3 h-3" />
                          Rejected
                        </span>
                      )}
                    </div>

                    {!entry.feasible || !r ? (
                      <div className="p-3 rounded-lg bg-red-950/35 border border-red-500/30 text-xs text-red-200 leading-relaxed">
                        {entry.error_reason ||
                          "No traversable path satisfies this mode's terrain / slope / budget limits."}
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">3D Surface Dist</div>
                          <div className="text-cyan-300 font-bold">
                            {r.total_surface_distance_m.toFixed(1)} m
                          </div>
                        </div>
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">Planar Dist</div>
                          <div className="text-slate-200 font-semibold">
                            {r.total_horizontal_distance_m.toFixed(1)} m
                          </div>
                        </div>
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">Gain / Loss</div>
                          <div className="text-slate-100">
                            +{r.total_elevation_gain_m.toFixed(1)} / -{r.total_elevation_loss_m.toFixed(1)} m
                          </div>
                        </div>
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">Max / Cap Slope</div>
                          <div className="text-amber-300 font-semibold">
                            {r.max_slope_deg.toFixed(1)}° / {r.effective_slope_limit_deg.toFixed(1)}°
                          </div>
                        </div>
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">Evidence Hits (&le;150m)</div>
                          <div className="text-purple-300 font-bold">
                            {r.corridor_evidence_hits_within_150m} hits
                          </div>
                        </div>
                        <div className="bg-[#0d111a] rounded-lg p-2 border border-[#1e2638]">
                          <div className="text-[10px] text-slate-400">Mean TRI / Compute</div>
                          <div className="text-slate-200">
                            {r.mean_roughness_tri_m != null ? `${r.mean_roughness_tri_m.toFixed(2)}m` : "N/A"} ·{" "}
                            {r.compute_time_ms.toFixed(0)}ms
                          </div>
                        </div>
                        <div className="col-span-2 bg-[#0d111a] rounded-lg p-2 border border-[#1e2638] flex items-center justify-between">
                          <span className="text-[10px] text-slate-400">Est. EVA Duration</span>
                          <span className="text-slate-100 font-semibold">
                            {r.estimated_duration_seconds != null
                              ? `${Math.round(r.estimated_duration_seconds / 60)} min (${r.assumption_classification})`
                              : "Not Modeled (Speed Omitted)"}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {entry.feasible && r && (
                    <div className="flex items-center gap-2 pt-2 border-t border-[#1e2638]">
                      <button
                        type="button"
                        onClick={() => selectComparedRoute(entry.mode)}
                        className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-colors ${
                          isActive
                            ? "bg-cyan-600 text-white"
                            : "bg-[#1a2438] hover:bg-cyan-600/30 text-cyan-200 border border-cyan-500/30"
                        }`}
                      >
                        {isActive ? "Active in 3D & Instructions" : "Activate Route"}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          selectComparedRoute(entry.mode);
                          await exportActiveGeoJSON();
                        }}
                        className="p-1.5 rounded-lg bg-[#0d111a] border border-[#252f44] text-emerald-300 hover:bg-[#172033]"
                        title="Export GeoJSON"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Quantitative Trade-Off Bar Chart */}
          {chartData.length > 0 && (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Feasible Modes Metric Trade-Off
              </h2>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 20, left: 4, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="mode" tick={{ fill: "#cbd5e1", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0b101b",
                        borderColor: "#2a3854",
                        borderRadius: "8px",
                        fontSize: "11px",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: "11px" }} />
                    <Bar dataKey="Surface Dist (m)" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Elev Gain (m)" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Evidence Hits" fill="#a855f7" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Methodology Notes */}
          {comparisonResult.comparison_notes.length > 0 && (
            <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-4 space-y-1.5 text-xs">
              <div className="font-mono font-bold uppercase text-[10px] text-slate-400">
                Comparison Methodology &amp; Constraints Notes
              </div>
              <ul className="list-disc pl-4 space-y-1 text-slate-300">
                {comparisonResult.comparison_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
