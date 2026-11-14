"use client";

import { useState } from "react";
import { PageHeader } from "../../components/PageHeader";
import { Server, Scale, RefreshCw } from "lucide-react";
import { API_BASE_URL } from "../../lib/constants";

export default function SettingsPage() {
  const [backendStatus, setBackendStatus] = useState<string>("Standby (Click to test)");
  const [backendVersion, setBackendVersion] = useState<string>("--");

  const checkBackend = async () => {
    try {
      setBackendStatus("Connecting...");
      const res = await fetch(`${API_BASE_URL}/health`);
      if (res.ok) {
        const data = await res.json();
        setBackendStatus("Connected & Healthy");
        setBackendVersion(data.version || "1.0.0");
      } else {
        setBackendStatus("HTTP Error " + res.status);
      }
    } catch {
      setBackendStatus("Backend Not Running (Start FastAPI on port 8000)");
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Settings & Mission Assumptions"
        badge="Physical Parameter Registry"
        description="Inspect and calibrate mission engineering assumptions, biophysical explorer limits, and backend microservice connection parameters."
        actions={
          <button
            onClick={checkBackend}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-xs font-semibold text-slate-300 hover:bg-[#1f273b] transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
            <span>Test API Connection</span>
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Backend Connectivity Status */}
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#1e2638]">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-[#e25b38]" />
              <h2 className="text-sm font-bold text-slate-200">Backend API Connectivity</h2>
            </div>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                backendStatus.includes("Healthy")
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
              }`}
            >
              {backendStatus.includes("Healthy") ? "ONLINE" : "STANDBY"}
            </span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1.5 border-b border-[#1a2130]">
              <span className="text-slate-400">Endpoint Base:</span>
              <span className="font-mono text-slate-200">{API_BASE_URL}</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-[#1a2130]">
              <span className="text-slate-400">Status:</span>
              <span className="font-mono text-slate-200">{backendStatus}</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400">API Version:</span>
              <span className="font-mono text-slate-200">{backendVersion}</span>
            </div>
          </div>
        </div>

        {/* Biophysical & EVA Engineering Assumptions */}
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#1e2638]">
            <div className="flex items-center gap-2">
              <Scale className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-bold text-slate-200">Biophysical Explorer Baseline</h2>
            </div>
            <span className="text-[10px] font-mono text-slate-500">SI Units</span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-1.5 border-b border-[#1a2130]">
              <span className="text-slate-400">Astronaut Body Mass:</span>
              <span className="font-mono text-slate-200">80.0 kg</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-[#1a2130]">
              <span className="text-slate-400">Advanced Planetary Suit Mass:</span>
              <span className="font-mono text-slate-200">120.0 kg</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-[#1a2130]">
              <span className="text-slate-400">Total System Mass ($m$):</span>
              <span className="font-mono text-emerald-400 font-bold">200.0 kg (Weight: 744.15 N)</span>
            </div>
            <div className="flex justify-between py-1.5">
              <span className="text-slate-400">Nominal Walking Pace:</span>
              <span className="font-mono text-slate-200">1.0 m/s (3.6 km/h)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
