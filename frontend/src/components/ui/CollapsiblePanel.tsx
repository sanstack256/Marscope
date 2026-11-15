"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface CollapsiblePanelProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function CollapsiblePanel({
  title,
  subtitle,
  badge,
  defaultOpen = true,
  actions,
  children,
  className = "",
}: CollapsiblePanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`ms-panel overflow-hidden ${className}`}>
      <div className="flex items-center justify-between px-4 py-3 bg-[var(--bg-elevated)]/70 border-b border-[var(--border-subtle)] gap-2">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
          className="flex items-center gap-2 text-left min-w-0 flex-1 focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent-telemetry)] rounded-[4px]"
        >
          {open ? (
            <ChevronDown className="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
          ) : (
            <ChevronRight className="w-4 h-4 text-[var(--text-secondary)] shrink-0" />
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-primary)] truncate">
                {title}
              </h2>
              {badge}
            </div>
            {subtitle && (
              <p className="text-[11px] text-[var(--text-muted)] truncate mt-0.5">{subtitle}</p>
            )}
          </div>
        </button>
        {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
      </div>
      {open && <div className="p-4">{children}</div>}
    </section>
  );
}
