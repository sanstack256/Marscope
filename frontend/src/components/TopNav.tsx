"use client";

import { useEffect, useState } from "react";
import { Clock, Database, MapPinOff, Radio } from "lucide-react";
import { API_BASE_URL } from "../lib/constants";
import { SystemHealth } from "../types";
import { useMissionStore } from "../stores/useMissionStore";
import { useTrackingStore } from "../stores/useTrackingStore";

export function TopNav() {
  const [currentTimeUtc, setCurrentTimeUtc] = useState<string>("");
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthError, setHealthError] = useState<boolean>(false);
  const { localizationStatus, fetchLocalizationStatus } = useMissionStore();
  const trackingStatus = useTrackingStore((s) => s.trackingStatus);
  const connectTrackingStream = useTrackingStore((s) => s.connectTrackingStream);

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
    const disconnectStream = connectTrackingStream();
    return () => {
      clearInterval(interval);
      disconnectStream();
    };
  }, [fetchLocalizationStatus, connectTrackingStream]);

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

  const livePosAvailable = Boolean(trackingStatus?.live_available);
  const manualPos = localizationStatus?.current_position;

  return (
    <header className="h-16 bg-[#0d111a]/90 backdrop-blur border-b border-[#1e2638] px-6 flex items-center justify-between shrink-0 z-10">
      {/* System Status Banner */}
      <div className="flex items-center gap-3">
        <div role="status" aria-live="polite" className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#161c2b] border border-[#252f44]">
          <span aria-hidden="true" className={`w-2 h-2 rounded-full ${dotClass}`}></span>
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
          title={
            trackingStatus?.message ||
            "Live Mars position unavailable — no mission positioning provider connected."
          }
        >
          {livePosAvailable ? (
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
          ) : (
            <MapPinOff className="w-3.5 h-3.5 text-amber-400" />
          )}
          <span className="text-slate-400">POS:</span>
          <span
            className={
              livePosAvailable
                ? "text-emerald-300"
                : manualPos?.latitude != null
                  ? "text-cyan-300"
                  : "text-amber-400"
            }
          >
            {livePosAvailable && trackingStatus?.lat != null && trackingStatus?.lon_east != null
              ? `LIVE (${trackingStatus.lat.toFixed(3)}°, ${trackingStatus.lon_east.toFixed(3)}°E)`
              : trackingStatus?.status === "stale"
                ? "LIVE STALE"
                : manualPos?.latitude != null
                  ? `MANUAL (${manualPos.latitude.toFixed(2)}°, ${manualPos.longitude?.toFixed(2)}°)`
                  : "LIVE UNAVAILABLE"}
          </span>
        </div>

        <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-300">
          <Database className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-slate-400">API:</span>
          <span className="font-bold text-slate-200">{health ? `v${health.version}` : "--"}</span>
        </div>
      </div>
    </header>
  );
}
