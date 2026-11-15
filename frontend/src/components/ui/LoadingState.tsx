"use client";

import React from "react";
import { Loader2 } from "lucide-react";

interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Loading verified operational telemetry..." }: LoadingStateProps) {
  return (
    <div className="ms-panel p-6 flex items-center justify-center gap-3 text-xs font-mono text-[var(--text-secondary)]">
      <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-telemetry)]" />
      <span>{label}</span>
    </div>
  );
}
