"use client";

import { useEffect, useState } from "react";
import { Radio, ShieldCheck, Clock } from "lucide-react";
import { STUDY_AREA_NAME } from "../lib/constants";

export function TopNav() {
  const [currentTimeUtc, setCurrentTimeUtc] = useState<string>("");
  const [solNumber] = useState<number>(4362);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTimeUtc(now.toUTCString().slice(17, 25) + " UTC");
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-16 bg-[#0d111a]/90 backdrop-blur border-b border-[#1e2638] px-6 flex items-center justify-between shrink-0 z-10">
      {/* Active Mission Banner */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#161c2b] border border-[#252f44]">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span className="text-xs font-mono font-medium text-slate-300">SYSTEM: ACTIVE</span>
        </div>
        <div className="hidden md:flex items-center gap-2 text-xs text-slate-400">
          <span className="text-slate-600">|</span>
          <span className="font-mono text-slate-300 font-semibold">{STUDY_AREA_NAME}</span>
        </div>
      </div>

      {/* Telemetry Clock & Quick Indicators */}
      <div className="flex items-center gap-4 text-xs font-mono">
        <div className="hidden lg:flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-400">
          <Clock className="w-3.5 h-3.5 text-[#e25b38]" />
          <span>SOL {solNumber}</span>
          <span className="text-slate-600">/</span>
          <span className="text-slate-200">{currentTimeUtc || "--:--:-- UTC"}</span>
        </div>

        <div className="flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-slate-300">
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span>4.3m LATENCY</span>
        </div>

        <div className="flex items-center gap-2 px-3 py-1 rounded bg-[#131722] border border-[#1e2638] text-emerald-400">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span className="text-slate-300">OPEN DATA:</span>
          <span className="font-bold">VERIFIED</span>
        </div>
      </div>
    </header>
  );
}
