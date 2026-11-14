"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { GitCompare, Download } from "lucide-react";

export default function RouteComparisonPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Route Comparison Matrix"
        badge="Multi-Scenario Trade-Off"
        description="Side-by-side evaluation of Conservative, Balanced, and Science-Priority Marswalk routes across physical cost, metabolic expenditure, and scientific return."
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => alert("GeoJSON export will be enabled when a route is computed.")}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-xs font-semibold text-slate-300 hover:bg-[#1f273b] transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              <span>Export GeoJSON</span>
            </button>
          </div>
        }
      />

      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6">
        <h2 className="text-sm font-bold text-slate-200 mb-1">Comparative Traversal Metrics</h2>
        <p className="text-xs text-slate-400 mb-6">
          Evaluation matrix benchmarking candidate traverse plans against mission constraints.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#1e2638] text-[10px] font-mono uppercase text-slate-500">
                <th className="pb-3 font-semibold">Evaluation Metric</th>
                <th className="pb-3 font-semibold text-emerald-400">Conservative Plan</th>
                <th className="pb-3 font-semibold text-cyan-400">Balanced Plan</th>
                <th className="pb-3 font-semibold text-[#f16f4d]">Science-Priority Plan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#182030] text-slate-300 font-mono text-[11px]">
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Total Traverse Distance</td>
                <td className="py-3">-- km</td>
                <td className="py-3">-- km</td>
                <td className="py-3">-- km</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Cumulative Elevation Gain</td>
                <td className="py-3">-- m</td>
                <td className="py-3">-- m</td>
                <td className="py-3">-- m</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Peak Segment Slope</td>
                <td className="py-3">-- °</td>
                <td className="py-3">-- °</td>
                <td className="py-3">-- °</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Estimated Metabolic Work</td>
                <td className="py-3">-- MJ</td>
                <td className="py-3">-- MJ</td>
                <td className="py-3">-- MJ</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Estimated Duration</td>
                <td className="py-3">-- hrs</td>
                <td className="py-3">-- hrs</td>
                <td className="py-3">-- hrs</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Return Consumable Margin</td>
                <td className="py-3">-- x</td>
                <td className="py-3">-- x</td>
                <td className="py-3">-- x</td>
              </tr>
              <tr>
                <td className="py-3 font-sans font-medium text-slate-400">Cumulative Science Value</td>
                <td className="py-3 text-emerald-400">-- pts</td>
                <td className="py-3 text-cyan-400">-- pts</td>
                <td className="py-3 text-[#f16f4d]">-- pts</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="mt-8">
          <EmptyState
            title="Comparison Matrix Awaiting Route Generation"
            message="Execute a route optimization run in the Route Planner to populate comparative metrics across all three operational planning profiles."
            icon={GitCompare}
          />
        </div>
      </div>
    </div>
  );
}
