"use client";

import { useEffect, useState } from "react";
import { Clock, Database, MapPinOff, Radio } from "lucide-react";
import { API_BASE_URL } from "../lib/constants";
import { SystemHealth } from "../types";
import { useMissionStore } from "../stores/useMissionStore";

export function TopNav() {
  const [currentTimeUtc, setCurrentTimeUtc] = useState<string>("");
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthError, setHealthError] = useState<boolean>(false);
  const { localizationStatus, fetchLocalizationStatus } = useMissionStore();

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTimeUtc(now.toUTCString().slice(17, 25) + " UTC");
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);

    const loadStatus = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
        if (res.ok) {
          setHealth(await res.json());
          setHealthError(false);
        } else {
          setHealthError(true);
        }
      } catch {
        setHealthError(true);
      }
      fetchLocalizationStatus();
    };

    loadStatus();
    return () => clearInterval(interval);
  }, [fetchLocalizationStatus]);

  const backendLabel = healthError
    ? "API: OFFLINE"
    : health
    ? `API: ${health.status.toUpperCase()}`
    : "API: CHECKING";

  const dotClass = healthError
    ? "bg-red-500"
    : health?.status === "healthy"
    ? "bg-emerald-400 animate-pulse"
    : "bg-amber-400";

  const livePosAvailable = localizationStatus?.live_localization_available ?? false;
  const manualPos = localizationStatus?.current_position;

  return (
    <header className="h-16 bg-[#0d111a]/90 backdrop-blur border-b border-[#1e2638] px-6 flex items-center justify-between shrink-0 z-10">
      {/* System Status Banner */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#161c2b] border border-[#252f44]">
          <span className={`w-2 h-2 rounded-full ${dotClass}`}></span>
          <span className="text-xs font-mono font-medium text-slate-300">{backendLabel}</span>
        </div>
        <div className="hidden md:flex items-center gap-2 text-xs text-slate-400">
          <span className="text-slate-600">|</span>
          <span className="font-mono text-slate-300 font-semibold">IAU2000:49900 MARS</span>
        </div>
      </div>

      {/* Real-Time Clock & Live Adapter Indicators */}
      <div className="flex items-center gap-3 text-xs font-mono">
        <div className="hidden lg:flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-400">
          <Clock className="w-3.5 h-3.5 text-[#e25b38]" />
          <span className="text-slate-200">{currentTimeUtc || "--:--:-- UTC"}</span>
        </div>

        <div
          className="flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-300"
          title={localizationStatus?.unavailable_reason || "Localization provider state"}
        >
          {livePosAvailable ? (
            <Radio className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <MapPinOff className="w-3.5 h-3.5 text-amber-400" />
          )}
          <span className="text-slate-400">POS:</span>
          <span className={manualPos?.latitude != null ? "text-cyan-300" : "text-amber-400"}>
            {manualPos?.latitude != null
              ? `MANUAL (${manualPos.latitude.toFixed(2)}°, ${manualPos.longitude?.toFixed(2)}°)`
              : "LIVE UNAVAILABLE"}
          </span>
        </div>

        <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-300">
          <Database className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-slate-400">CATALOG:</span>
          <span className="font-bold text-slate-200">{health ? `v${health.version}` : "--"}</span>
        </div>
      </div>
    </header>
  );
}
