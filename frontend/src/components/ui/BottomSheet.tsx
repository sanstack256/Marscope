"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

interface BottomSheetProps {
  title: string;
  subtitle?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

export function BottomSheet({ title, subtitle, defaultExpanded = false, children }: BottomSheetProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="ms-panel overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full px-4 py-2.5 flex items-center justify-between bg-[var(--bg-elevated)]/80 border-b border-[var(--border-subtle)] text-left"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-primary)] truncate">
            {title}
          </span>
          {subtitle && (
            <span className="text-[11px] font-mono text-[var(--text-muted)] truncate hidden sm:inline">
              — {subtitle}
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
        ) : (
          <ChevronUp className="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
        )}
      </button>
      {expanded && <div className="p-4 max-h-[340px] overflow-y-auto">{children}</div>}
    </div>
  );
}
