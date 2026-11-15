"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertOctagon,
  Clock,
  Command,
  LogOut,
  RefreshCw,
  UserCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import { API_BASE_URL } from "../lib/constants";
import { SystemHealth } from "../types";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { useMissionStore } from "../stores/useMissionStore";
import { CommandPalette } from "./ui/CommandPalette";
import { ContextPopover } from "./ui/ContextPopover";

export function TopNav() {
  const [currentTimeUtc, setCurrentTimeUtc] = useState<string>("");
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const {
    authenticated,
    astronaut,
    missions,
    activeMissionId,
    activeMission,
    selectMission,
    logout,
    sosEvents,
    setSosDrawerOpen,
    streamState,
    browserOnline,
    offlineQueue,
    syncOfflineEventsNow,
  } = useAuthMissionStore();

  const { fetchLocalizationStatus } = useMissionStore();

  useEffect(() => {
    const updateTime = () => {
      setCurrentTimeUtc(new Date().toUTCString().slice(17, 25) + " UTC");
    };
    updateTime();
    const t = setInterval(updateTime, 1000);

    const checkApi = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
        if (res.ok) {
          setHealth(await res.json());
          setHealthError(false);
        } else {
          setHealthError(true);
        }
      } catch {
        setHealthError(true);
      }
      fetchLocalizationStatus();
    };
    void checkApi();

    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearInterval(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [fetchLocalizationStatus]);

  const activeSosList = sosEvents.filter((s) => s.status !== "RESOLVED" && s.status !== "CANCELLED");

  return (
    <>
      <header className="h-[56px] bg-[var(--bg-surface)]/95 backdrop-blur border-b border-[var(--border-subtle)] pl-14 pr-4 lg:px-5 flex items-center justify-between gap-3 shrink-0 z-30">
        {/* Left: System State + Active Mission Switcher */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            role="status"
            aria-live="polite"
            className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] text-[11px] font-mono"
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                healthError
                  ? "bg-[#DC3545]"
                  : health?.status === "healthy"
                  ? "bg-[#1F9D68]"
                  : "bg-[#D98A1F]"
              }`}
            />
            <span className="text-[var(--text-secondary)]">
              {healthError ? "API OFFLINE" : health ? `API ${health.status.toUpperCase()}` : "API CHECK"}
            </span>
          </div>

          {authenticated && (
            <div className="flex items-center gap-2 min-w-0">
              <label htmlFor="topnav-mission-select" className="sr-only">
                Active Mission
              </label>
              <select
                id="topnav-mission-select"
                value={activeMissionId || ""}
                onChange={(e) => void selectMission(e.target.value || null)}
                className="bg-[var(--bg-void)] border border-[var(--border-strong)] rounded-[4px] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] max-w-[200px] sm:max-w-[260px] truncate"
              >
                {missions.length === 0 ? (
                  <option value="">No missions joined</option>
                ) : (
                  missions.map((m) => (
                    <option key={m.mission_id} value={m.mission_id}>
                      {m.name} ({m.my_role})
                    </option>
                  ))
                )}
              </select>
            </div>
          )}

          {activeMission && (
            <span className="hidden xl:inline-flex items-center px-2 py-0.5 rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[10px] font-mono text-[var(--text-secondary)]">
              {activeMission.landing_site_status === "REGISTERED" ? "SITE REGISTERED" : "LANDING SITE UNCONFIGURED"}
            </span>
          )}
        </div>

        {/* Right: SOS Alert Pill, Offline Queue, SSE, Command Palette, UTC, Astronaut Chip */}
        <div className="flex items-center gap-2 text-xs">
          {activeSosList.length > 0 && (
            <button
              type="button"
              onClick={() => setSosDrawerOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-[#DC3545] text-white font-mono font-bold text-[11px] ms-sos-ring"
            >
              <AlertOctagon className="w-3.5 h-3.5" />
              <span>SOS ({activeSosList.length})</span>
            </button>
          )}

          {offlineQueue.length > 0 && (
            <button
              type="button"
              onClick={() => void syncOfflineEventsNow()}
              title="Queued offline events waiting for server delivery"
              className="flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[#D98A1F]/15 border border-[#D98A1F]/40 text-[#f5b041] font-mono text-[11px]"
            >
              <RefreshCw className="w-3 h-3" />
              <span>QUEUED: {offlineQueue.length}</span>
            </button>
          )}

          <div
            title={`Real-time mission stream: ${streamState}`}
            className="hidden md:flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] text-[11px] font-mono"
          >
            {browserOnline && streamState === "CONNECTED" ? (
              <Wifi className="w-3.5 h-3.5 text-[#1F9D68]" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-[#D98A1F]" />
            )}
            <span className="text-[var(--text-secondary)]">{browserOnline ? streamState : "OFFLINE"}</span>
          </div>

          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] text-[11px] font-mono text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <Command className="w-3 h-3" />
            <span>K</span>
          </button>

          <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] font-mono text-[11px] text-[var(--text-secondary)]">
            <Clock className="w-3.5 h-3.5 text-[var(--accent-mars)]" />
            <span>{currentTimeUtc || "--:--:-- UTC"}</span>
          </div>

          {authenticated && astronaut ? (
            <ContextPopover
              trigger={
                <button
                  type="button"
                  className="flex items-center gap-2 px-2.5 py-1 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-xs text-[var(--text-primary)] hover:border-[var(--accent-telemetry)]"
                >
                  <UserCheck className="w-3.5 h-3.5 text-[var(--accent-telemetry)]" />
                  <span className="max-w-[110px] truncate font-medium">{astronaut.display_name}</span>
                </button>
              }
            >
              <div className="space-y-2.5 text-xs">
                <div>
                  <div className="font-semibold text-[var(--text-primary)]">{astronaut.display_name}</div>
                  <div className="font-mono text-[11px] text-[var(--text-muted)] truncate">{astronaut.email}</div>
                </div>
                <div className="border-t border-[var(--border-subtle)] pt-2 flex flex-col gap-1">
                  <Link
                    href="/profile"
                    className="px-2 py-1.5 rounded-[4px] hover:bg-white/5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    Astronaut Profile & Mass
                  </Link>
                  <Link
                    href="/missions"
                    className="px-2 py-1.5 rounded-[4px] hover:bg-white/5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    Missions & Invitations
                  </Link>
                  <button
                    type="button"
                    onClick={() => void logout()}
                    className="flex items-center gap-1.5 px-2 py-1.5 rounded-[4px] hover:bg-[#DC3545]/15 text-[#ff6b7a] text-left"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            </ContextPopover>
          ) : (
            <Link
              href="/"
              className="px-2.5 py-1 rounded-[4px] bg-[var(--accent-mars)] text-white text-xs font-semibold hover:bg-[var(--accent-mars-hover)]"
            >
              Sign In
            </Link>
          )}
        </div>
      </header>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}
