"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, X } from "lucide-react";
import { NAVIGATION_PAGES } from "../../lib/constants";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) onClose();
      } else if (e.key === "Escape" && open) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return NAVIGATION_PAGES;
    return NAVIGATION_PAGES.filter(
      (p) => p.label.toLowerCase().includes(q) || p.href.toLowerCase().includes(q)
    );
  }, [query]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-[2px] flex items-start justify-center pt-20 px-4"
    >
      <div className="w-full max-w-lg ms-panel-elevated overflow-hidden shadow-2xl">
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[var(--border-subtle)]">
          <Search className="w-4 h-4 text-[var(--accent-telemetry)]" />
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to workspace view (Ctrl/Cmd+K)..."
            className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close command palette"
            className="p-1 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="max-h-72 overflow-y-auto p-2 space-y-1">
          {filtered.length === 0 ? (
            <div className="p-4 text-xs text-[var(--text-muted)] text-center">No matching operational view.</div>
          ) : (
            filtered.map((item) => (
              <button
                key={item.href}
                type="button"
                onClick={() => {
                  router.push(item.href);
                  onClose();
                  setQuery("");
                }}
                className="w-full px-3 py-2 rounded-[4px] flex items-center justify-between text-xs text-[var(--text-primary)] hover:bg-white/10 transition-colors"
              >
                <span className="font-medium">{item.label}</span>
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--text-muted)]">
                  {item.href}
                  <ArrowRight className="w-3 h-3" />
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
