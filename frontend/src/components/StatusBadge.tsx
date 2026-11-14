import React from "react";

interface StatusBadgeProps {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  let classes = "bg-slate-800/80 text-slate-300 border-slate-700/70";
  if (normalized === "verified") {
    classes = "bg-emerald-950/60 text-emerald-300 border-emerald-700/50";
  } else if (normalized === "pending") {
    classes = "bg-amber-950/60 text-amber-200 border-amber-700/50";
  } else if (normalized === "failed") {
    classes = "bg-red-950/60 text-red-200 border-red-700/50";
  } else if (normalized === "unverified" || normalized === "unknown") {
    classes = "bg-slate-900 text-slate-400 border-slate-700";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-mono uppercase tracking-wide ${classes}`}
    >
      {label ?? status}
    </span>
  );
}
