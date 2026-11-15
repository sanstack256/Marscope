"use client";

import { useEffect, useState } from "react";
import { Activity, Calculator, Compass, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import {
  LocalizationStatusResponse,
  PhysicsCalculationResult,
  PhysicsModelDescriptor,
  PhysicsParameter,
  SystemHealth,
} from "../../types";

type ModelKey = "weight" | "potential_energy" | "atmospheric_density" | "drag" | "uphill_force";

interface ReadinessAuditPayload {
  system_readiness_state: string;
  operational_safety_certified: boolean;
  application_health?: {
    healthy: boolean;
    status: string;
  };
  execution_readiness?: {
    ready: boolean;
    status: string;
    telemetry_connected: boolean;
    reason?: string;
  };
  data_gaps?: string[];
  degraded_reasons?: string[];
  pillars?: Record<
    string,
    {
      ready: boolean;
      [key: string]: unknown;
    }
  >;
}

export default function SettingsAssumptionsPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [readiness, setReadiness] = useState<ReadinessAuditPayload | null>(null);
  const [parameters, setParameters] = useState<PhysicsParameter[]>([]);
  const [models, setModels] = useState<PhysicsModelDescriptor[]>([]);
  const [localization, setLocalization] = useState<LocalizationStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Interactive Physics Workbench state (explicit user inputs — blank by default until user enters values or loads example)
  const [selectedModel, setSelectedModel] = useState<ModelKey>("weight");
  const [massKg, setMassKg] = useState<string>("");
  const [deltaHm, setDeltaHm] = useState<string>("");
  const [pressurePa, setPressurePa] = useState<string>("");
  const [tempK, setTempK] = useState<string>("");
  const [velocityMs, setVelocityMs] = useState<string>("");
  const [slopeDeg, setSlopeDeg] = useState<string>("");
  const [exampleLoaded, setExampleLoaded] = useState<boolean>(false);
  const [calcResult, setCalcResult] = useState<PhysicsCalculationResult | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calcLoading, setCalcLoading] = useState<boolean>(false);

  async function loadSystemData() {
    setLoading(true);
    setError(null);
    try {
      const [hRes, rRes, pRes, mRes, lRes] = await Promise.all([
        fetch(`${API_BASE_URL}/health`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/health/readiness?verify_checksums=false`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/parameters`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/physics/models`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/localization/status`, { cache: "no-store" }),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
      if (rRes.ok) setReadiness(await rRes.json());
      if (pRes.ok) setParameters(await pRes.json());
      if (mRes.ok) setModels(await mRes.json());
      if (lRes.ok) setLocalization(await lRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system diagnostics");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [hRes, rRes, pRes, mRes, lRes] = await Promise.all([
          fetch(`${API_BASE_URL}/health`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/health/readiness?verify_checksums=false`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/parameters`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/physics/models`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/localization/status`, { cache: "no-store" }),
        ]);
        if (!active) return;
        if (hRes.ok) setHealth(await hRes.json());
        if (rRes.ok) setReadiness(await rRes.json());
        if (pRes.ok) setParameters(await pRes.json());
        if (mRes.ok) setModels(await mRes.json());
        if (lRes.ok) setLocalization(await lRes.json());
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load system diagnostics");
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  async function runPhysicsCalculation(e: React.FormEvent) {
    e.preventDefault();
    setCalcError(null);
    const body: Record<string, unknown> = { model_name: selectedModel };
    const requireNum = (raw: string, label: string): number | null => {
      const val = Number.parseFloat(raw);
      if (!Number.isFinite(val)) {
        setCalcError(`Enter a numeric value for "${label}" or load Example Test Inputs first.`);
        return null;
      }
      return val;
    };
    if (["weight", "potential_energy", "uphill_force"].includes(selectedModel)) {
      const v = requireNum(massKg, "Mass Assumption (kg)");
      if (v === null) return;
      body.mass_kg = v;
    }
    if (selectedModel === "potential_energy") {
      const v = requireNum(deltaHm, "Elevation Delta (m)");
      if (v === null) return;
      body.delta_h_m = v;
    }
    if (["atmospheric_density", "drag"].includes(selectedModel)) {
      const p = requireNum(pressurePa, "Pressure Input (Pa)");
      const t = requireNum(tempK, "Temperature Input (K)");
      if (p === null || t === null) return;
      body.pressure_pa = p;
      body.temperature_k = t;
    }
    if (selectedModel === "drag") {
      const v = requireNum(velocityMs, "Relative Wind/Speed (m/s)");
      if (v === null) return;
      body.velocity_m_s = v;
    }
    if (selectedModel === "uphill_force") {
      const s = requireNum(slopeDeg, "Slope Input (deg)");
      if (s === null) return;
      body.slope_degrees = s;
    }

    setCalcLoading(true);
    try {

      const res = await fetch(`${API_BASE_URL}/physics/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) {
        throw new Error(payload.detail || `HTTP ${res.status}`);
      }
      setCalcResult(payload);
    } catch (err) {
      setCalcError(err instanceof Error ? err.message : "Calculation failed");
    } finally {
      setCalcLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Mission Assumptions & Physics Registry"
        badge={health ? `Backend ${health.status.toUpperCase()}` : "Diagnostics"}
        description="Traceable scientific reference constants loaded from the backend parameter registry, live localization provider status, and interactive physics workbench with explicit assumption labeling."
        actions={
          <button
            type="button"
            onClick={loadSystemData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-xs font-medium text-slate-200 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Diagnostics</span>
          </button>
        }
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800/50 text-xs text-red-200">
          {error}
        </div>
      )}

      {/* Backend Engine & Localization Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100 border-b border-[#1e2638] pb-3">
            <Activity className="w-4 h-4 text-[#38bdf8]" />
            <span>Backend Engine Telemetry</span>
          </div>
          {health ? (
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 rounded bg-[#0d111a] border border-[#1d2536]">
                <div className="text-[10px] text-slate-500">SYSTEM / VERSION</div>
                <div className="text-slate-100">{health.system} v{health.version}</div>
              </div>
              <div className="p-2.5 rounded bg-[#0d111a] border border-[#1d2536]">
                <div className="text-[10px] text-slate-500">STATUS</div>
                <div className="text-emerald-300">{health.status}</div>
              </div>
              {Object.entries(health.engines).map(([eng, st]) => (
                <div key={eng} className="p-2.5 rounded bg-[#0d111a] border border-[#1d2536]">
                  <div className="text-[10px] text-slate-500 uppercase">{eng}</div>
                  <div className="text-slate-200">{st}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400">Querying backend health...</p>
          )}
        </div>

        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100 border-b border-[#1e2638] pb-3">
            <Compass className="w-4 h-4 text-[#e25b38]" />
            <span>Localization Acquisition Providers</span>
          </div>
          {localization ? (
            <div className="space-y-2">
              <div className="text-xs text-slate-300">
                Live Localization: <span className="font-mono text-amber-300">{localization.live_localization_available ? "Available" : "Unavailable"}</span>
              </div>
              <div className="space-y-1.5">
                {localization.supported_providers.map((prov) => (
                  <div key={prov.provider_id} className="p-2.5 rounded bg-[#0d111a] border border-[#1d2536] flex items-center justify-between gap-2 text-xs">
                    <div>
                      <div className="font-semibold text-slate-200">{prov.name}</div>
                      <div className="text-[10px] text-slate-400">{prov.status_detail}</div>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {prov.connected ? "connected" : "disconnected"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">Loading provider capabilities...</p>
          )}
        </div>
      </div>

      {/* 4-Pillar System Readiness vs Execution Readiness Audit */}
      {readiness && (
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1e2638] pb-3">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
              <ShieldCheck className="w-4 h-4 text-amber-400" />
              <span>System Readiness &amp; Operational Boundaries</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono">
              <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-700/50 text-emerald-300">
                APP: {readiness.application_health?.status ?? "UNKNOWN"}
              </span>
              <span className="px-2 py-0.5 rounded bg-amber-950/60 border border-amber-700/50 text-amber-300">
                READINESS: {readiness.system_readiness_state}
              </span>
              <span className="px-2 py-0.5 rounded bg-red-950/60 border border-red-800/50 text-red-300">
                EXECUTION: {readiness.execution_readiness?.status ?? "UNAVAILABLE"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
            {["data", "science", "spatial", "mission"].map((key) => {
              const p = readiness.pillars?.[key];
              const ok = Boolean(p?.ready);
              return (
                <div key={key} className="p-3 rounded bg-[#0d111a] border border-[#1d2536] space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="uppercase text-slate-400">{key} pillar</span>
                    <span className={ok ? "text-emerald-300" : "text-amber-300"}>
                      {ok ? "READY" : "GAPS / NOT READY"}
                    </span>
                  </div>
                  {key === "data" && p && (
                    <div className="text-[10px] text-slate-400">
                      DEMs ready: {String(p.processed_dem_ready_count ?? 0)} | Comp Index:{" "}
                      {p.composition_index_available ? "verified" : "unavailable"}
                    </div>
                  )}
                  {key === "science" && p && (
                    <div className="text-[10px] text-slate-400">
                      Questions: {String(p.questions_registered ?? 0)} | Instruments: {String(p.instruments_registered ?? 0)}
                    </div>
                  )}
                  {key === "spatial" && p && (
                    <div className="text-[10px] text-slate-400">
                      Libs: {p.geospatial_libraries_available ? "ok" : "missing"} | DEMs:{" "}
                      {String(p.processed_dem_ready_count ?? 0)}
                    </div>
                  )}
                  {key === "mission" && p && (
                    <div className="text-[10px] text-slate-400">
                      Routing DEM: {p.routing_executable_with_local_dem ? "yes" : "no"} | Telemetry: offline
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {readiness.execution_readiness?.reason && (
            <div className="text-[11px] text-amber-200/90 bg-amber-950/30 border border-amber-800/40 rounded px-3 py-2">
              {readiness.execution_readiness.reason}
            </div>
          )}

          {readiness.data_gaps && readiness.data_gaps.length > 0 && (
            <ul className="text-[11px] text-slate-300 list-disc list-inside space-y-0.5">
              {readiness.data_gaps.map((gap, i) => (
                <li key={i}>{gap}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Interactive Physics Calculation Workbench */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-[#1e2638] pb-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <Calculator className="w-4 h-4 text-[#e25b38]" />
            <span>Validated Physics Workbench (User-Supplied Inputs)</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {exampleLoaded && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950/60 border border-sky-700/50 text-sky-300">
                USER EXAMPLE VALUES — NOT MISSION TELEMETRY
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                setMassKg("180");
                setDeltaHm("25");
                setPressurePa("700");
                setTempK("215");
                setVelocityMs("1.5");
                setSlopeDeg("12");
                setExampleLoaded(true);
                setCalcError(null);
              }}
              className="px-2.5 py-1 rounded bg-[#182032] hover:bg-[#1e273d] border border-[#2a344c] text-[11px] font-mono text-sky-300"
            >
              Load Example Test Inputs (User Example)
            </button>
          </div>
        </div>

        <form onSubmit={runPhysicsCalculation} className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <div>
            <label className="text-[11px] text-slate-400 block mb-1">Physical Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value as ModelKey)}
              className="w-full px-2.5 py-1.5 text-xs rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
            >
              <option value="weight">Surface Weight (W = m * g_mars)</option>
              <option value="potential_energy">Potential Energy Delta</option>
              <option value="atmospheric_density">CO2 Atmospheric Density</option>
              <option value="drag">Aerodynamic Drag Force</option>
              <option value="uphill_force">Uphill Parallel Force</option>
            </select>
          </div>

          {["weight", "potential_energy", "uphill_force"].includes(selectedModel) && (
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Mass Assumption (kg)</label>
              <input
                type="number"
                step="any"
                value={massKg}
                onChange={(e) => setMassKg(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
              />
            </div>
          )}

          {selectedModel === "potential_energy" && (
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Elevation Delta (m)</label>
              <input
                type="number"
                step="any"
                value={deltaHm}
                onChange={(e) => setDeltaHm(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
              />
            </div>
          )}

          {["atmospheric_density", "drag"].includes(selectedModel) && (
            <>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Pressure Input (Pa)</label>
                <input
                  type="number"
                  step="any"
                  value={pressurePa}
                  onChange={(e) => setPressurePa(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Temperature Input (K)</label>
                <input
                  type="number"
                  step="any"
                  value={tempK}
                  onChange={(e) => setTempK(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
                />
              </div>
            </>
          )}

          {selectedModel === "drag" && (
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Relative Wind/Speed (m/s)</label>
              <input
                type="number"
                step="any"
                value={velocityMs}
                onChange={(e) => setVelocityMs(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
              />
            </div>
          )}

          {selectedModel === "uphill_force" && (
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Slope Input (deg)</label>
              <input
                type="number"
                step="any"
                value={slopeDeg}
                onChange={(e) => setSlopeDeg(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs font-mono rounded bg-[#0d111a] border border-[#252f44] text-slate-100"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={calcLoading}
            className="px-4 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-white text-xs font-semibold"
          >
            {calcLoading ? "Computing..." : "Run Calculation"}
          </button>
        </form>

        {calcError && (
          <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/50 text-xs text-red-200">
            {calcError}
          </div>
        )}

        {calcResult && (
          <div className="p-3.5 rounded-lg bg-[#0d111a] border border-[#252f44] space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-100">{calcResult.model_name}</span>
              <span className="font-mono text-lg font-bold text-emerald-300">
                {calcResult.calculated_value.toFixed(4)} {calcResult.units}
              </span>
            </div>
            <div className="text-[11px] text-slate-400">
              References: {calcResult.scientific_references.join(" | ")}
            </div>
            {calcResult.engineering_assumptions.length > 0 && (
              <div className="text-[11px] text-amber-200/90">
                Assumptions: {calcResult.engineering_assumptions.join(" | ")}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Scientific Reference Parameter Registry Table */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-3">
        <div className="flex items-center justify-between border-b border-[#1e2638] pb-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Traceable Reference Parameter Registry ({parameters.length} Constants)</span>
          </div>
          <span className="text-[10px] font-mono text-slate-400">{models.length} Physics Models Loaded</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {parameters.map((param) => (
            <div key={param.id} className="p-3 rounded-lg bg-[#0d111a] border border-[#1d2536] space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-slate-100">{param.name}</span>
                <span className="text-xs font-mono text-[#38bdf8]">
                  {param.value} {param.units}
                </span>
              </div>
              <div className="text-[10px] text-slate-400">{param.applicable_conditions}</div>
              <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1">
                <span>Source: {param.source}</span>
                <a
                  href={param.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-sky-400 hover:underline"
                >
                  <span>Ref</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
