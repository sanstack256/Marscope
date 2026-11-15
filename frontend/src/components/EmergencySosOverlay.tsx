"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertOctagon, CheckCircle2, MapPin, ShieldAlert, XCircle } from "lucide-react";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { DetailDrawer } from "./ui/DetailDrawer";
import { StatusIndicator } from "./ui/StatusIndicator";
import { VoiceRecorderWidget } from "./ui/VoiceRecorderWidget";
import { VoiceNoteRecord } from "../types";

const HOLD_DURATION_MS = 1200;

export function EmergencySosOverlay() {
  const {
    authenticated,
    activeMissionId,
    activeMission,
    sosEvents,
    sosDrawerOpen,
    setSosDrawerOpen,
    triggerSos,
    acknowledgeSos,
    resolveSos,
    cancelSos,
  } = useAuthMissionStore();

  const [holdProgress, setHoldProgress] = useState(0);
  const [composeOpen, setComposeOpen] = useState(false);
  const [sosMessage, setSosMessage] = useState("");
  const [voiceNote, setVoiceNote] = useState<VoiceNoteRecord | null>(null);
  const [explicitLat, setExplicitLat] = useState("");
  const [explicitLon, setExplicitLon] = useState("");
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [dispatchBusy, setDispatchBusy] = useState(false);

  const rafRef = useRef<number | null>(null);
  const holdStartRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  if (!authenticated || !activeMissionId) return null;

  const activeAlerts = sosEvents.filter((s) => s.status !== "RESOLVED" && s.status !== "CANCELLED");

  const startHold = () => {
    setDispatchError(null);
    holdStartRef.current = performance.now();
    const tick = (now: number) => {
      if (!holdStartRef.current) return;
      const pct = Math.min(1, (now - holdStartRef.current) / HOLD_DURATION_MS);
      setHoldProgress(pct);
      if (pct >= 1) {
        holdStartRef.current = null;
        setHoldProgress(0);
        setComposeOpen(true);
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  const cancelHold = () => {
    holdStartRef.current = null;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    setHoldProgress(0);
  };

  const handleDispatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setDispatchBusy(true);
    setDispatchError(null);
    try {
      const latNum = explicitLat.trim() ? Number(explicitLat) : null;
      const lonNum = explicitLon.trim() ? Number(explicitLon) : null;
      if ((latNum !== null && Number.isNaN(latNum)) || (lonNum !== null && Number.isNaN(lonNum))) {
        setDispatchError("Explicit coordinates must be numeric Mars lat/lon degrees.");
        return;
      }
      const res = await triggerSos({
        message: sosMessage.trim() || undefined,
        voice_note_id: voiceNote?.voice_note_id || null,
        explicit_latitude: latNum,
        explicit_longitude: lonNum,
      });
      if (!res.ok) {
        setDispatchError(res.error || "SOS dispatch failed.");
        return;
      }
      setComposeOpen(false);
      setSosMessage("");
      setVoiceNote(null);
      setExplicitLat("");
      setExplicitLon("");
      setSosDrawerOpen(true);
    } finally {
      setDispatchBusy(false);
    }
  };

  const canResolve =
    activeMission?.my_role === "MISSION_LEAD" || activeMission?.my_role === "MISSION_OPERATOR";

  return (
    <>
      {/* Persistent 56x56px Press-and-Hold SOS Button */}
      <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2">
        {activeAlerts.length > 0 && (
          <button
            type="button"
            onClick={() => setSosDrawerOpen(true)}
            className="px-3 py-1.5 rounded-[6px] bg-[#DC3545] text-white text-xs font-mono font-bold shadow-xl flex items-center gap-1.5"
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>{activeAlerts.length} ACTIVE SOS ALERT</span>
          </button>
        )}

        <button
          type="button"
          onPointerDown={startHold}
          onPointerUp={cancelHold}
          onPointerLeave={cancelHold}
          onPointerCancel={cancelHold}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setComposeOpen(true);
            }
          }}
          aria-label="Hold 1.2 seconds to dispatch Emergency SOS"
          title="Press and hold 1.2s for Emergency SOS (Enter/Space to open SOS console)"
          className="relative w-[56px] h-[56px] rounded-[8px] bg-[#DC3545] hover:bg-[#c82333] text-white shadow-2xl border border-white/25 flex flex-col items-center justify-center select-none touch-none ms-sos-ring"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 56 56"
            className="absolute inset-0 w-full h-full pointer-events-none"
          >
            <rect
              x="2"
              y="2"
              width="52"
              height="52"
              rx="6"
              fill="none"
              stroke="rgba(255,255,255,0.9)"
              strokeWidth="3"
              strokeDasharray={208}
              strokeDashoffset={208 * (1 - holdProgress)}
            />
          </svg>
          <AlertOctagon className="w-5 h-5" />
          <span className="text-[10px] font-mono font-bold tracking-wider leading-none mt-0.5">SOS</span>
        </button>
      </div>

      {/* Emergency SOS Activation Modal */}
      <DetailDrawer
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        title="Dispatch Mission Emergency SOS"
        subtitle={`Mission: ${activeMission?.name || activeMissionId}`}
      >
        <form onSubmit={handleDispatch} className="space-y-4 text-xs">
          <div className="rounded-[6px] border border-[#DC3545]/45 bg-[#DC3545]/10 p-3 text-[var(--text-primary)] leading-relaxed space-y-1.5">
            <div>
              This broadcasts an urgent alert to all active crew members in{" "}
              <span className="font-semibold">{activeMission?.name}</span>. Your latest validated{" "}
              <span className="font-mono">IAU2000:49900</span> position (or{" "}
              <span className="font-mono">POSITION_UNAVAILABLE</span> if none) is attached automatically without
              fabricating coordinates.
            </div>
            <div className="font-mono text-[10px] text-[#f5b041]">
              Channel Notice: Available only through the authenticated MARSCOPE application channel. No SMS, email, push, or satellite provider is configured.
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="block font-medium text-[var(--text-secondary)]">
              Emergency Message (Optional)
            </label>
            <textarea
              rows={3}
              value={sosMessage}
              onChange={(e) => setSosMessage(e.target.value)}
              placeholder="Suit pressure anomaly, mobility hazard, medical injury..."
              className="w-full ms-input"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block font-medium text-[var(--text-secondary)]">
              Voice Note Attachment (Optional, stored privately per mission)
            </label>
            <VoiceRecorderWidget
              missionId={activeMissionId}
              linkedEventType="SOS"
              onUploaded={(rec) => setVoiceNote(rec)}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] font-mono text-[var(--text-muted)] mb-1">
                Explicit Lat (deg, optional)
              </label>
              <input
                type="text"
                value={explicitLat}
                onChange={(e) => setExplicitLat(e.target.value)}
                placeholder="Blank = latest server pos"
                className="w-full ms-input font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-[var(--text-muted)] mb-1">
                Explicit Lon East (deg, optional)
              </label>
              <input
                type="text"
                value={explicitLon}
                onChange={(e) => setExplicitLon(e.target.value)}
                placeholder="0..360"
                className="w-full ms-input font-mono text-xs"
              />
            </div>
          </div>

          {dispatchError && (
            <div className="text-xs text-[#ff6b7a] font-mono">{dispatchError}</div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setComposeOpen(false)}
              className="px-3 py-2 rounded-[4px] border border-[var(--border-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              Abort
            </button>
            <button
              type="submit"
              disabled={dispatchBusy}
              className="px-4 py-2 rounded-[4px] bg-[#DC3545] hover:bg-[#c82333] text-white font-semibold disabled:opacity-50"
            >
              {dispatchBusy ? "Dispatching SOS..." : "Confirm & Broadcast SOS"}
            </button>
          </div>
        </form>
      </DetailDrawer>

      {/* Crew Emergency Alert Monitor Drawer */}
      <DetailDrawer
        open={sosDrawerOpen}
        onClose={() => setSosDrawerOpen(false)}
        title="Mission SOS Alert Console"
        subtitle={`Mission: ${activeMission?.name || activeMissionId}`}
      >
        <div className="space-y-3 text-xs">
          {sosEvents.length === 0 ? (
            <div className="ms-panel p-4 text-[var(--text-secondary)]">
              No SOS alerts recorded for this mission.
            </div>
          ) : (
            sosEvents.map((ev) => (
              <div
                key={ev.sos_id}
                className={`rounded-[8px] border p-4 space-y-2.5 ${
                  ev.status === "RESOLVED" || ev.status === "CANCELLED"
                    ? "bg-[var(--bg-void)] border-[var(--border-subtle)] opacity-80"
                    : "bg-[#DC3545]/10 border-[#DC3545]/50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-sm text-[var(--text-primary)]">
                      {ev.astronaut_display_name}
                    </div>
                    <div className="font-mono text-[11px] text-[var(--text-muted)]">
                      Server UTC: {new Date(ev.server_received_at_utc).toLocaleString()}
                    </div>
                  </div>
                  <StatusIndicator
                    label={ev.status}
                    tone={
                      ev.status === "RESOLVED"
                        ? "success"
                        : ev.status === "CANCELLED"
                        ? "unknown"
                        : ev.status === "ACKNOWLEDGED_BY_CREW"
                        ? "warning"
                        : "danger"
                    }
                    pulse={ev.status === "ACTIVE"}
                  />
                </div>

                {ev.message && (
                  <p className="text-[var(--text-primary)] bg-[var(--bg-void)]/70 p-2.5 rounded-[4px] border border-[var(--border-subtle)]">
                    {ev.message}
                  </p>
                )}

                <div className="flex items-center gap-1.5 font-mono text-[11px] text-[var(--text-secondary)]">
                  <MapPin className="w-3.5 h-3.5 text-[var(--accent-mars)] shrink-0" />
                  {ev.latitude !== null && ev.latitude !== undefined && ev.longitude_east !== null && ev.longitude_east !== undefined ? (
                    <span>
                      {ev.latitude.toFixed(5)}, {ev.longitude_east.toFixed(5)} E ({ev.crs || "IAU2000:49900"}) —{" "}
                      {ev.position_status}
                    </span>
                  ) : (
                    <span className="text-[#f5b041]">{ev.position_status}</span>
                  )}
                </div>

                {ev.voice_note && (
                  <div className="pt-1 space-y-1">
                    <div className="text-[10px] font-mono text-[var(--text-muted)]">
                      ENCRYPTED VOICE NOTE ({Math.round(ev.voice_note.file_size_bytes / 1024)} KB)
                    </div>
                    <audio controls src={ev.voice_note.playback_url} className="w-full h-8" />
                  </div>
                )}

                {ev.acknowledgements.length > 0 && (
                  <div className="space-y-1 pt-1 border-t border-[var(--border-subtle)]">
                    {ev.acknowledgements.map((ack) => (
                      <div key={ack.ack_id} className="font-mono text-[10px] text-[var(--text-secondary)]">
                        • {ack.display_name}: {ack.ack_type} ({new Date(ack.created_at_utc).toLocaleTimeString()})
                      </div>
                    ))}
                  </div>
                )}

                {ev.status !== "RESOLVED" && ev.status !== "CANCELLED" && (
                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => void acknowledgeSos(ev.sos_id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-[4px] bg-[#D98A1F] text-[#07090C] font-semibold text-xs"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Acknowledge</span>
                    </button>
                    {canResolve && (
                      <button
                        type="button"
                        onClick={() => void resolveSos(ev.sos_id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-[4px] bg-[#1F9D68] text-white font-semibold text-xs"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Resolve</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void cancelSos(ev.sos_id)}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-[4px] border border-[var(--border-strong)] text-[var(--text-secondary)] hover:text-white text-xs"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Cancel (Retain Audit)</span>
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </DetailDrawer>
    </>
  );
}
