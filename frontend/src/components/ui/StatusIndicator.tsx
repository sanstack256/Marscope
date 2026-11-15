"use client";

import React from "react";

export type StatusTone = "success" | "telemetry" | "warning" | "danger" | "unknown" | "mars";

const TONE_CLASSES: Record<StatusTone, string> = {
  success: "bg-[#1F9D68]/15 text-[#4ade80] border-[#1F9D68]/40",
  telemetry: "bg-[#22B8CF]/15 text-[#22B8CF] border-[#22B8CF]/40",
  warning: "bg-[#D98A1F]/15 text-[#f5b041] border-[#D98A1F]/40",
  danger: "bg-[#DC3545]/15 text-[#ff6b7a] border-[#DC3545]/45",
  unknown: "bg-[#7A8699]/15 text-[#A6B3C4] border-[#7A8699]/35",
  mars: "bg-[#E25B38]/15 text-[#F16F4D] border-[#E25B38]/40",
};

const DOT_CLASSES: Record<StatusTone, string> = {
  success: "bg-[#1F9D68]",
  telemetry: "bg-[#22B8CF]",
  warning: "bg-[#D98A1F]",
  danger: "bg-[#DC3545]",
  unknown: "bg-[#7A8699]",
  mars: "bg-[#E25B38]",
};

interface StatusIndicatorProps {
  label: string;
  tone?: StatusTone;
  pulse?: boolean;
  className?: string;
}

export function StatusIndicator({
  label,
  tone = "unknown",
  pulse = false,
  className = "",
}: StatusIndicatorProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] border text-[11px] font-mono font-medium uppercase tracking-wide ${TONE_CLASSES[tone]} ${className}`}
    >
      <span
        aria-hidden="true"
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT_CLASSES[tone]} ${pulse ? "animate-pulse" : ""}`}
      />
      <span>{label}</span>
    </span>
  );
}
