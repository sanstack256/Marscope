"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { Telescope, Filter } from "lucide-react";

export default function ScientificDiscoveryPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Scientific Discovery / Target Explorer"
        badge="Ground-Truth Catalog"
        description="Filterable catalog of verified geological and mineralogical targets across Gale Crater, including boxwork fracture ridges, layered sulfates, and Curiosity rover drill sites."
        actions={
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-xs font-semibold text-slate-300 hover:bg-[#1f273b] transition-colors">
              <Filter className="w-3.5 h-3.5 text-[#e25b38]" />
              <span>Filter Geological Classes</span>
            </button>
          </div>
        }
      />

      {/* Target Discovery Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <div className="flex items-center justify-between pb-3 border-b border-[#1e2638] mb-4">
            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Candidate Targets</h2>
            <span className="text-[10px] font-mono text-slate-500">0 Active</span>
          </div>

          <div className="text-xs text-slate-400 space-y-2">
            <p>Target classifications will include:</p>
            <ul className="list-disc list-inside space-y-1 text-slate-300 font-mono text-[11px]">
              <li>Boxwork Ridge Crests (Fracture Fills)</li>
              <li>Inter-Ridge Aeolian Hollows</li>
              <li>Sulfate-Smectite Transition Strata</li>
              <li>MSL In-Situ ChemCam / CheMin Stops</li>
            </ul>
          </div>
        </div>

        <div className="lg:col-span-2 bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <h2 className="text-sm font-bold text-slate-200 mb-1">Target Dossier & Evidence Inspector</h2>
          <p className="text-xs text-slate-400 mb-4">
            Spectral absorptions (CRISM), elemental assays (ChemCam/APXS), and Mastcam ground-truth panoramas.
          </p>
          <EmptyState
            title="Scientific Target Ledger Awaiting Ingestion"
            message="No targets have been loaded yet. In accordance with MARSCOPE scientific integrity rules, targets will be populated exclusively from published Curiosity rover traverse records and verified HiRISE coordinates."
            icon={Telescope}
            actionLabel="View Data Sources"
          />
        </div>
      </div>
    </div>
  );
}
