"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertOctagon,
  CheckCircle2,
  Compass,
  FileSearch,
  Flag,
  FlaskConical,
  Gauge,
  Globe2,
  Menu,
  Microscope,
  Mountain,
  Navigation,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  Route,
  Satellite,
  Settings,
  ShieldCheck,
  Target,
  UserCog,
  Users,
  Waypoints,
  X,
} from "lucide-react";
import { NAVIGATION_GROUPS } from "../lib/constants";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Activity,
  AlertOctagon,
  CheckCircle2,
  Compass,
  FileSearch,
  Flag,
  FlaskConical,
  Gauge,
  Globe2,
  Microscope,
  Mountain,
  Navigation,
  Radar,
  Route,
  Satellite,
  Settings,
  ShieldCheck,
  Target,
  UserCog,
  Users,
  Waypoints,
};

const SIDEBAR_STORAGE_KEY = "marscope.sidebar_collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const sosEvents = useAuthMissionStore((s) => s.sosEvents);
  const activeMission = useAuthMissionStore((s) => s.activeMission);
  const astronaut = useAuthMissionStore((s) => s.astronaut);
  const activeSosCount = sosEvents.filter(
    (s) => s.status !== "RESOLVED" && s.status !== "CANCELLED"
  ).length;

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => {
      try {
        const saved = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
        if (saved === "true") setCollapsed(true);
      } catch {
        // ignore storage errors
      }
    });
    return () => window.cancelAnimationFrame(raf);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const renderNavBody = (isMobile: boolean) => (
    <div className="flex flex-col h-full bg-[var(--bg-void)] border-r border-[var(--border-subtle)] select-none">
      {/* Brand + Collapse Toggle */}
      <div className="h-[56px] px-3.5 flex items-center justify-between border-b border-[var(--border-subtle)] shrink-0">
        <Link href="/mission-control" onClick={() => setMobileOpen(false)} className="flex items-center gap-2.5 min-w-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand-icon.png"
            alt="MARSCOPE"
            className="w-9 h-9 rounded-[6px] object-contain bg-black border border-[var(--border-strong)] shrink-0"
          />
          {(!collapsed || isMobile) && (
            <div className="min-w-0">
              <div className="text-sm font-bold tracking-wider text-[var(--text-primary)] leading-none">
                MARSCOPE
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)] tracking-wider mt-1 truncate">
                SURFACE OPS PLATFORM
              </div>
            </div>
          )}
        </Link>
        {isMobile ? (
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation menu"
            className="p-1.5 rounded-[4px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <X className="w-4 h-4" />
          </button>
        ) : (
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="p-1.5 rounded-[4px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/5 shrink-0"
          >
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* Navigation Groups */}
      <nav aria-label="Primary operational navigation" className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
        {NAVIGATION_GROUPS.map((group) => (
          <div key={group.id}>
            {(!collapsed || isMobile) && (
              <div className="px-2.5 mb-1.5 text-[10px] font-mono font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                {group.label}
              </div>
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = ICON_MAP[item.icon] || Compass;
                const isActive =
                  item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`);
                const isSos = item.href === "/emergency";

                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      title={collapsed && !isMobile ? item.label : undefined}
                      className={`flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-xs font-medium transition-colors ${
                        isActive
                          ? "bg-[var(--accent-mars)]/15 text-[var(--text-primary)] border border-[var(--accent-mars)]/40"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/[0.04] border border-transparent"
                      }`}
                    >
                      <Icon
                        className={`w-[18px] h-[18px] shrink-0 ${
                          isSos && activeSosCount > 0
                            ? "text-[#ff6b7a]"
                            : isActive
                            ? "text-[var(--accent-mars)]"
                            : "text-[var(--text-secondary)]"
                        }`}
                      />
                      {(!collapsed || isMobile) && (
                        <>
                          <span className="flex-1 truncate">{item.label}</span>
                          {isSos && activeSosCount > 0 && (
                            <span className="px-1.5 py-0.5 rounded-[4px] bg-[#DC3545] text-white text-[10px] font-mono font-bold">
                              {activeSosCount}
                            </span>
                          )}
                          {!isSos && item.badge && (
                            <span className="px-1.5 py-0.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[9px] font-mono text-[var(--text-muted)]">
                              {item.badge}
                            </span>
                          )}
                        </>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer Context Summary + Astronaut User Icon */}
      {(!collapsed || isMobile) && (
        <div className="p-3 border-t border-[var(--border-subtle)] text-[11px] font-mono text-[var(--text-muted)] space-y-2.5">
          <div>
            <div className="truncate text-[var(--text-secondary)] font-semibold">
              {activeMission ? activeMission.name : "No Active Mission"}
            </div>
            <div className="mt-0.5 truncate">CRS: IAU2000:49900</div>
          </div>
          <Link
            href="/profile"
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-2.5 pt-2 border-t border-[var(--border-subtle)]/70 hover:text-[var(--text-primary)] transition-colors"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/astronaut-icon.png"
              alt="Astronaut"
              className="w-7 h-7 rounded-full border border-[#FF6A1A]/75 object-cover shrink-0 bg-[#050505]"
            />
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-sans font-semibold text-[var(--text-primary)] leading-tight flex items-center gap-1.5">
                <span>Astronaut</span>
                {astronaut?.is_demo && (
                  <span className="px-1 py-0.5 rounded-[3px] bg-[#FF6A1A]/20 border border-[#FF6A1A]/50 text-[#FF6A1A] text-[9px] font-mono">
                    DEMO
                  </span>
                )}
              </div>
              {astronaut && (
                <div className="text-[10px] font-mono text-[var(--text-muted)] truncate">
                  {astronaut.display_name}
                </div>
              )}
            </div>
          </Link>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Mobile Hamburger Trigger rendered inside header area on small screens */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation menu"
        className="lg:hidden fixed top-3 left-3 z-40 p-2 rounded-[6px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-[var(--text-primary)]"
      >
        <Menu className="w-4 h-4" />
      </button>

      {/* Desktop Collapsible Rail */}
      <aside
        className={`hidden lg:block shrink-0 transition-[width] duration-150 ${
          collapsed ? "w-[72px]" : "w-[248px]"
        }`}
      >
        {renderNavBody(false)}
      </aside>

      {/* Mobile Overlay Drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex bg-black/70 backdrop-blur-[2px]">
          <div className="w-[260px] h-full">{renderNavBody(true)}</div>
          <div className="flex-1" onClick={() => setMobileOpen(false)} />
        </div>
      )}
    </>
  );
}
