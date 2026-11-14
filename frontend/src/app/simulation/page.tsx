"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { PlayCircle, Clock, BatteryCharging, Droplets, Wind } from "lucide-react";

export default function MissionSimulationPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Mission Simulation / EVA Timeline"
        badge="Awaiting Route Input"
        description="Temporal scrub simulation modeling astronaut traversal, dynamic consumable depletion (oxygen, battery, cooling water), and solar azimuth variations once a computed traverse exists."
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-[#121622] border border-[#1e2638] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#1e2638]">
            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Life-Support Consumables</h2>
            <Clock className="w-4 h-4 text-[#e25b38]" />
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-lg bg-[#161c2b] border border-[#212a3d] space-y-1">
              <div className="flex items-center justify-between text-slate-300">
                <span className="flex items-center gap-1.5"><Wind className="w-3.5 h-3.5 text-cyan-400" /> Primary O₂ Supply</span>
                <span className="font-mono text-slate-500 font-bold">--% (No Active Route)</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden" />
            </div>

            <div className="p-3 rounded-lg bg-[#161c2b] border border-[#212a3d] space-y-1">
              <div className="flex items-center justify-between text-slate-300">
                <span className="flex items-center gap-1.5"><BatteryCharging className="w-3.5 h-3.5 text-emerald-400" /> Suit Battery (Wh)</span>
                <span className="font-mono text-slate-500 font-bold">--% (No Active Route)</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden" />
            </div>

            <div className="p-3 rounded-lg bg-[#161c2b] border border-[#212a3d] space-y-1">
              <div className="flex items-center justify-between text-slate-300">
                <span className="flex items-center gap-1.5"><Droplets className="w-3.5 h-3.5 text-blue-400" /> Sublimator Water</span>
                <span className="font-mono text-slate-500 font-bold">--% (No Active Route)</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden" />
            </div>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Consumable margins are populated exclusively from computed route energy expenditure and user-configured suit capacities.
          </p>
        </div>

        <div className="lg:col-span-2 bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <h2 className="text-sm font-bold text-slate-200 mb-1">Traverse Timeline Scrubber</h2>
          <p className="text-xs text-slate-400 mb-4">
            Simulate crew progress from origin through waypoints and return-to-base completion.
          </p>
          <EmptyState
            title="No Computed Traverse Loaded"
            message="Timeline scrubbing and biophysical consumption telemetry activate only after a route is computed from a validated DEM and real waypoints."
            icon={PlayCircle}
          />
        </div>
      </div>
    </div>
  );
}
