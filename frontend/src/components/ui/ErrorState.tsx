"use client";

import React from "react";
import { AlertTriangle } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message: string;
  action?: React.ReactNode;
}

export function ErrorState({ title = "Operational Error", message, action }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-[8px] border border-[#DC3545]/45 bg-[#DC3545]/10 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="w-4 h-4 text-[#ff6b7a] shrink-0 mt-0.5" />
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#ff6b7a]">{title}</p>
          <p className="text-xs text-[var(--text-primary)] mt-0.5">{message}</p>
        </div>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
