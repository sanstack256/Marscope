"use client";

import React from "react";
import { LucideIcon } from "lucide-react";

export interface IconToolbarAction {
  id: string;
  label: string;
  icon: LucideIcon;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

interface IconToolbarProps {
  actions: IconToolbarAction[];
  className?: string;
}

export function IconToolbar({ actions, className = "" }: IconToolbarProps) {
  return (
    <div
      role="toolbar"
      aria-label="Viewport tools"
      className={`inline-flex items-center gap-1 p-1 rounded-[6px] bg-[var(--bg-glass)] border border-[var(--border-strong)] backdrop-blur ${className}`}
    >
      {actions.map((act) => {
        const Icon = act.icon;
        return (
          <button
            key={act.id}
            type="button"
            disabled={act.disabled}
            onClick={act.onClick}
            title={act.label}
            aria-label={act.label}
            aria-pressed={act.active}
            className={`px-2 py-1.5 rounded-[4px] flex items-center gap-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
              act.active
                ? "bg-[var(--accent-telemetry)]/20 text-[var(--accent-telemetry)] border border-[var(--accent-telemetry)]/40"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/5 border border-transparent"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span className="hidden xl:inline">{act.label}</span>
          </button>
        );
      })}
    </div>
  );
}
