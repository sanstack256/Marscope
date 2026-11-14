import { PageHeader } from "../../components/PageHeader";
import { Database, ExternalLink, ShieldCheck, Clock } from "lucide-react";

interface DatasetRow {
  name: string;
  mission: string;
  instrument: string;
  purpose: string;
  license: string;
  coverage: string;
  priority: string;
  sourceUrl: string;
}

const DATASETS: DatasetRow[] = [
  {
    name: "HiRISE RDR Orthorectified Imagery",
    mission: "MRO",
    instrument: "HiRISE",
    purpose: "Sub-meter optical terrain & visible boulder hazards",
    license: "Verified Open (CC0)",
    coverage: "Pending Verification",
    priority: "P0",
    sourceUrl: "https://www.uahirise.org/",
  },
  {
    name: "HiRISE Digital Terrain Model (DTM)",
    mission: "MRO",
    instrument: "HiRISE Stereo",
    purpose: "1-meter micro-topography for local slope & roughness",
    license: "Verified Open (CC0)",
    coverage: "Pending Verification",
    priority: "P0",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/mro/hirise.htm",
  },
  {
    name: "CTX Controlled Mosaics",
    mission: "MRO",
    instrument: "CTX",
    purpose: "6-meter regional optical context linking HiRISE swaths",
    license: "Verified Open (CC0)",
    coverage: "Verified Gale Basin",
    priority: "P0",
    sourceUrl: "https://ode.rsl.wustl.edu/mars/",
  },
  {
    name: "MOLA MEGDR Topography (128 ppd)",
    mission: "MGS",
    instrument: "MOLA",
    purpose: "Regional elevation datum & MOLA Areoid 0-datum",
    license: "Verified Open (CC0)",
    coverage: "Verified Global Gale",
    priority: "P0",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
  },
  {
    name: "CRISM Targeted Observations",
    mission: "MRO",
    instrument: "CRISM",
    purpose: "Hyperspectral mineralogy: sulfates & phyllosilicates",
    license: "Verified Open (CC0)",
    coverage: "Pending Verification",
    priority: "P1",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
  },
  {
    name: "MSL ChemCam LIBS / RMI",
    mission: "MSL",
    instrument: "ChemCam",
    purpose: "In-situ elemental rock & vein chemistry assays",
    license: "Verified Open (CC0)",
    coverage: "Verified MSL Traverse",
    priority: "P1",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/msl/",
  },
  {
    name: "MSL CheMin XRD Mineralogy",
    mission: "MSL",
    instrument: "CheMin",
    purpose: "Quantitative mineral phase determinations",
    license: "Verified Open (CC0)",
    coverage: "Verified MSL Drill Holes",
    priority: "P1",
    sourceUrl: "https://pds-geosciences.wustl.edu/missions/msl/",
  },
  {
    name: "MSL RAD Radiation Dosimetry",
    mission: "MSL",
    instrument: "RAD",
    purpose: "Surface ionizing radiation dose rate logs",
    license: "Verified Open (CC0)",
    coverage: "Verified Mission Log",
    priority: "P1",
    sourceUrl: "https://pds-ppi.igpp.ucla.edu/",
  },
  {
    name: "MSL REMS Environmental Sensor",
    mission: "MSL",
    instrument: "REMS",
    purpose: "Diurnal atmospheric pressure, temperature & wind",
    license: "Verified Open (CC0)",
    coverage: "Verified Mission Log",
    priority: "P1",
    sourceUrl: "https://pds-atmospheres.nmsu.edu/",
  },
  {
    name: "NASA Mars Trek WMTS Reference Tiles",
    mission: "NASA Solar System Treks",
    instrument: "Cartographic Pipeline",
    purpose: "OGC WMTS rapid discovery and map visualization",
    license: "Verified Open (US Govt Open)",
    coverage: "Verified Global Mars",
    priority: "P1",
    sourceUrl: "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars",
  },
];

export default function EvidencePage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Data Sources, Evidence & Provenance Ledger"
        badge="Open Science Compliance"
        description="Authoritative planetary dataset register. Every layer, observation, and calculation in MARSCOPE is tracked back to its original NASA/ESA archive, processing level, and open license."
      />

      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6">
        <div className="flex items-center justify-between pb-4 border-b border-[#1e2638] mb-4">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-[#e25b38]" />
            <h2 className="text-sm font-bold text-slate-200">NASA & International Planetary Product Register</h2>
          </div>
          <span className="text-[11px] font-mono text-emerald-400">100% Free & Open Access</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#1e2638] text-[10px] font-mono uppercase text-slate-500">
                <th className="pb-3 font-semibold">Dataset / Instrument</th>
                <th className="pb-3 font-semibold">Mission</th>
                <th className="pb-3 font-semibold">Primary Purpose</th>
                <th className="pb-3 font-semibold">License Status</th>
                <th className="pb-3 font-semibold">Gale Coverage</th>
                <th className="pb-3 font-semibold">Priority</th>
                <th className="pb-3 font-semibold text-right">Archive Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#182030] text-slate-300">
              {DATASETS.map((d, i) => (
                <tr key={i} className="hover:bg-[#161c2b]/50 transition-colors">
                  <td className="py-3 font-medium text-slate-200">
                    <div>{d.name}</div>
                    <div className="text-[10px] font-mono text-slate-500">{d.instrument}</div>
                  </td>
                  <td className="py-3 font-mono text-slate-400">{d.mission}</td>
                  <td className="py-3 text-slate-400 max-w-xs">{d.purpose}</td>
                  <td className="py-3">
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      <ShieldCheck className="w-3 h-3" />
                      {d.license}
                    </span>
                  </td>
                  <td className="py-3 font-mono text-[11px]">
                    <span
                      className={
                        d.coverage.includes("Verified")
                          ? "text-emerald-400"
                          : "text-amber-400/90 flex items-center gap-1"
                      }
                    >
                      {d.coverage.includes("Pending") && <Clock className="w-3 h-3 inline" />}
                      {d.coverage}
                    </span>
                  </td>
                  <td className="py-3 font-mono text-xs">{d.priority}</td>
                  <td className="py-3 text-right">
                    <a
                      href={d.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-mono text-cyan-400 hover:text-cyan-300"
                    >
                      <span>PDS Archive</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
