"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { useMissionStore } from "../../stores/useMissionStore";
import { Compass, ShieldAlert, Cpu, Play } from "lucide-react";
import { PlanningMode } from "../../types";

export default function RoutePlannerPage() {
  const {
    planningMode,
    maxDurationHours,
    safetyReserveFactor,
    maxSlopeLimitDeg,
    setPlanningMode,
    setDuration,
    setSafetyReserve,
  } = useMissionStore();

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Mission & Route Planner"
        badge="Constrained Graph Optimization"
        description="Generates science-aware, human-aware Marswalk traverses. Optimizes scientific return subject to non-negotiable slope safety limits and a 1.5x return-to-base consumable reserve."
        actions={
          <button
            onClick={() => alert("Route optimization engine will be wired in Prompt 3.")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#f16f4d] text-white text-xs font-semibold tracking-wide transition-all shadow-[0_0_15px_rgba(226,91,56,0.3)]"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Compute Marswalk Route</span>
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Traversal Constraint Controls */}
        <div className="lg:col-span-1 bg-[#121622] border border-[#1e2638] rounded-xl p-6 space-y-6">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#1e2638] mb-4">
              <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Mission Optimization Parameters</h2>
              <Cpu className="w-4 h-4 text-[#e25b38]" />
            </div>

            {/* Planning Mode Selector */}
            <div className="space-y-2 mb-5">
              <label className="text-xs font-medium text-slate-300">Optimization Mode</label>
              <div className="grid grid-cols-3 gap-2">
                {(["conservative", "balanced", "science_priority"] as PlanningMode[]).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setPlanningMode(mode)}
                    className={`py-2 px-2 text-[11px] font-medium rounded-lg capitalize border transition-all text-center ${
                      planningMode === mode
                        ? "bg-[#e25b38]/15 text-[#f16f4d] border-[#e25b38]/40"
                        : "bg-[#161c2b] text-slate-400 border-transparent hover:text-slate-200 hover:bg-[#1f273b]"
                    }`}
                  >
                    {mode.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Duration Slider */}
            <div className="space-y-2 mb-5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-300">Max EVA Duration</span>
                <span className="font-mono text-[#e25b38] font-bold">{maxDurationHours.toFixed(1)} hrs</span>
              </div>
              <input
                type="range"
                min="2.0"
                max="8.0"
                step="0.5"
                value={maxDurationHours}
                onChange={(e) => setDuration(parseFloat(e.target.value))}
                className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-[#e25b38]"
              />
              <div className="flex justify-between text-[10px] font-mono text-slate-500">
                <span>2.0 hrs</span>
                <span>Contingency Margin: 1.5 hrs</span>
                <span>8.0 hrs</span>
              </div>
            </div>

            {/* Safety Reserve Slider */}
            <div className="space-y-2 mb-5">
              <div className="flex justify-between text-xs">
                <span className="text-slate-300">Return Reserve Multiplier</span>
                <span className="font-mono text-cyan-400 font-bold">{safetyReserveFactor.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                min="1.2"
                max="2.0"
                step="0.1"
                value={safetyReserveFactor}
                onChange={(e) => setSafetyReserve(parseFloat(e.target.value))}
                className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
              <span className="text-[10px] text-slate-500 block">
                Guarantees {safetyReserveFactor}x consumable return capability at furthest point.
              </span>
            </div>

            {/* Hard Invariant Notice */}
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-300/90 flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <span>
                <strong>Hard Safety Constraint:</strong> Slopes exceeding {maxSlopeLimitDeg}° cannot be overridden by high scientific target scores.
              </span>
            </div>
          </div>
        </div>

        {/* Route Graph Display Area */}
        <div className="lg:col-span-2 bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <h2 className="text-sm font-bold text-slate-200 mb-1">Optimized Traverse Path & Profile</h2>
          <p className="text-xs text-slate-400 mb-4">
            A* / Dijkstra graph solver output incorporating slope penalties and return-to-base reserves.
          </p>
          <EmptyState
            title="Traverse Engine Ready for Target Selection"
            message="Select scientific investigation targets from the Target Explorer to trigger graph pathfinding. The engine will evaluate slope resistance, metabolic work, and point-of-no-return margins."
            icon={Compass}
            actionLabel="Browse Targets"
          />
        </div>
      </div>
    </div>
  );
}
