import Link from "next/link";
import Image from "next/image";
import { PageHeader } from "../components/PageHeader";
import { StatusCard } from "../components/StatusCard";
import { EmptyState } from "../components/EmptyState";
import {
  Globe2,
  Compass,
  Mountain,
  Telescope,
  Thermometer,
  Gauge,
  Radiation,
  Layers,
  ArrowRight,
} from "lucide-react";
import { STUDY_AREA_NAME, MARS_FACTS } from "../lib/constants";

export default function MissionOverviewPage() {
  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <PageHeader
        title="Mission Command Overview"
        badge="Gale Crater Basin"
        description="Martian Surface Intelligence & Exploration System — Surface operations context, atmospheric conditions & quick-start traversal controls."
        actions={
          <div className="flex items-center gap-3">
            <Link
              href="/explorer"
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-[#161c2b] hover:bg-[#1f273b] border border-[#252f44] text-xs font-semibold text-slate-200 transition-colors"
            >
              <Globe2 className="w-3.5 h-3.5 text-cyan-400" />
              <span>3D Surface Globe</span>
            </Link>
            <Link
              href="/planner"
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-[#e25b38] hover:bg-[#f16f4d] text-white text-xs font-semibold tracking-wide transition-all shadow-[0_0_15px_rgba(226,91,56,0.3)]"
            >
              <Compass className="w-3.5 h-3.5" />
              <span>Plan Marswalk Route</span>
            </Link>
          </div>
        }
      />

      {/* Atmospheric & Environmental Indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatusCard
          label="Atmospheric Pressure"
          value={MARS_FACTS.ATM_PRESSURE_PA}
          unit="Pa"
          subValue="REMS In-Situ Sensor Baseline"
          icon={Gauge}
          badge="Nominal"
        />
        <StatusCard
          label="Surface Temperature"
          value={MARS_FACTS.SURFACE_TEMP_K}
          unit="K (-58°C)"
          subValue="Diurnal Mean at Gale Crater"
          icon={Thermometer}
        />
        <StatusCard
          label="Surface Gravity"
          value={MARS_FACTS.GRAVITY_M_S2}
          unit="m/s²"
          subValue="0.379g Earth Equivalent"
          icon={Mountain}
        />
        <StatusCard
          label="Cosmic Radiation Dose"
          value="0.21"
          unit="mSv/day"
          subValue="MSL RAD In-Situ Baseline"
          icon={Radiation}
        />
      </div>

      {/* Exploration Region Dossier */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#121622] border border-[#1e2638] rounded-xl p-6 relative overflow-hidden">
          <div className="relative z-10 flex items-center justify-between pb-4 border-b border-[#1e2638]">
            <div>
              <div className="text-[11px] font-mono text-[#e25b38] uppercase tracking-wider">Target Exploration Zone</div>
              <h2 className="text-lg font-bold text-slate-100 mt-0.5">{STUDY_AREA_NAME}</h2>
            </div>
            <span className="px-2.5 py-1 rounded text-xs font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              {MARS_FACTS.CRS}
            </span>
          </div>

          <p className="relative z-10 text-xs text-slate-300 mt-4 leading-relaxed">
            The boxwork structures on Mount Sharp (Aeolis Mons) represent mineralized fracture networks formed by ancient subsurface groundwater circulation. As wind erosion removed the surrounding softer bedrock over billions of years, these cemented veins were left standing in positive relief. MARSCOPE calculates traversability across these ridges while maximizing scientific target acquisition.
          </p>

          <div className="relative z-10 grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-4 border-t border-[#1a2130]">
            <div>
              <div className="text-[10px] font-mono uppercase text-slate-500">Min Latitude</div>
              <div className="text-sm font-mono font-bold text-slate-200 mt-0.5">-5.5° S</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase text-slate-500">Max Latitude</div>
              <div className="text-sm font-mono font-bold text-slate-200 mt-0.5">-4.3° S</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase text-slate-500">Min Longitude</div>
              <div className="text-sm font-mono font-bold text-slate-200 mt-0.5">137.2° E</div>
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase text-slate-500">Max Longitude</div>
              <div className="text-sm font-mono font-bold text-slate-200 mt-0.5">138.0° E</div>
            </div>
          </div>

          <Image
            src="/marscope-logo.png"
            alt=""
            aria-hidden="true"
            width={887}
            height={329}
            className="absolute bottom-0 right-4 w-64 h-auto opacity-15 pointer-events-none select-none"
          />
        </div>

        {/* Quick System Navigation */}
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-200 mb-1">Core Workspaces</h3>
            <p className="text-xs text-slate-400 mb-4">Direct shortcuts to active planetary intelligence systems:</p>
            <div className="space-y-2">
              <Link
                href="/explorer"
                className="flex items-center justify-between p-2.5 rounded-lg bg-[#161c2b] hover:bg-[#1c2437] text-xs text-slate-300 transition-colors border border-transparent hover:border-[#252f44]"
              >
                <div className="flex items-center gap-2.5">
                  <Globe2 className="w-4 h-4 text-cyan-400" />
                  <span>3D Mars Surface Explorer</span>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
              </Link>
              <Link
                href="/terrain"
                className="flex items-center justify-between p-2.5 rounded-lg bg-[#161c2b] hover:bg-[#1c2437] text-xs text-slate-300 transition-colors border border-transparent hover:border-[#252f44]"
              >
                <div className="flex items-center gap-2.5">
                  <Mountain className="w-4 h-4 text-amber-400" />
                  <span>Terrain & Slope Intelligence</span>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
              </Link>
              <Link
                href="/targets"
                className="flex items-center justify-between p-2.5 rounded-lg bg-[#161c2b] hover:bg-[#1c2437] text-xs text-slate-300 transition-colors border border-transparent hover:border-[#252f44]"
              >
                <div className="flex items-center gap-2.5">
                  <Telescope className="w-4 h-4 text-emerald-400" />
                  <span>Scientific Target Catalog</span>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
              </Link>
              <Link
                href="/planner"
                className="flex items-center justify-between p-2.5 rounded-lg bg-[#161c2b] hover:bg-[#1c2437] text-xs text-slate-300 transition-colors border border-transparent hover:border-[#252f44]"
              >
                <div className="flex items-center gap-2.5">
                  <Compass className="w-4 h-4 text-[#e25b38]" />
                  <span>Route Optimization Engine</span>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
              </Link>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-[#1a2130] flex items-center justify-between text-[11px] text-slate-500">
            <span>NASA Space Apps Challenge</span>
            <span className="text-emerald-400 font-mono">100% OPEN DATA</span>
          </div>
        </div>
      </div>

      {/* Surface Map Preview Skeleton */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#e25b38]" />
            <h3 className="text-sm font-bold text-slate-200">Active Planetary Data Feeds</h3>
          </div>
          <span className="text-[11px] font-mono text-slate-500">Pipeline Level: Initialized</span>
        </div>

        <EmptyState
          title="Surface Map Viewport Initialized"
          message="The 3D CesiumJS globe and MapLibre geospatial canvas are configured with the IAU2000 Mars datum. Connect to the backend ingestion service in Prompt 2 to stream high-resolution HiRISE, CTX, and MOLA tiles."
          actionLabel="Launch Surface Explorer"
        />
      </div>
    </div>
  );
}
