"use client";

import React, { useState } from "react";
import { AlertOctagon, CheckCircle2, MapPin, ShieldAlert, XCircle } from "lucide-react";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { VoiceRecorderWidget } from "../../components/ui/VoiceRecorderWidget";
import { VoiceNoteRecord } from "../../types";

export default function EmergencyConsolePage() {
  const {
    authenticated,
    activeMissionId,
    activeMission,
    sosEvents,
    offlineQueue,
    triggerSos,
    acknowledgeSos,
    resolveSos,
    cancelSos,
  } = useAuthMissionStore();
  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const [filterMode, setFilterMode] = useState<"ALL" | "ACTIVE" | "CLOSED">("ALL");

  const [message, setMessage] = useState("");
  const [voiceNote, setVoiceNote] = useState<VoiceNoteRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!authenticated || !activeMissionId || !activeMission) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={AlertOctagon}
          title="Mission Workspace Required"
          description="Sign in and join an active mission to dispatch or monitor crew SOS alerts."
        />
      </div>
    );
  }

  const canResolve = ["MISSION_LEAD", "MISSION_OPERATOR"].includes(activeMission.my_role);
  const queuedSos = offlineQueue.filter((q) => q.event_kind === "SOS_TRIGGER");
  const filteredSos = sosEvents.filter((ev) => {
    const isClosed = ev.status === "RESOLVED" || ev.status === "CANCELLED";
    if (filterMode === "ACTIVE") return !isClosed;
    if (filterMode === "CLOSED") return isClosed;
    return true;
  });

  const handleTrigger = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await triggerSos({
        message: message.trim() || undefined,
        voice_note_id: voiceNote?.voice_note_id || null,
      });
      if (!res.ok) {
        setError(res.error || "SOS dispatch failed.");
      } else {
        setMessage("");
        setVoiceNote(null);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title="Emergency SOS & Voice Dispatch Console"
        badge={activeMission.name}
        description="Real-time crew SOS alerts with server acknowledgement, private voice-note audio playback, and permanent audit retention on resolution or cancellation."
      />

      <form onSubmit={handleTrigger} className="ms-panel p-4 space-y-3 text-xs border-[#DC3545]/45">
        <div className="flex items-center gap-2 font-semibold text-sm text-[#ff6b7a]">
          <ShieldAlert className="w-4 h-4" />
          <span>Manual Emergency SOS Dispatch</span>
        </div>
        <textarea
          rows={2}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Describe emergency situation (optional)..."
          className="w-full ms-input"
        />
        <VoiceRecorderWidget
          missionId={activeMissionId}
          linkedEventType="SOS"
          onUploaded={(rec) => setVoiceNote(rec)}
        />
        {error && <div className="text-[#ff6b7a] font-mono">{error}</div>}
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2 rounded-[4px] bg-[#DC3545] hover:bg-[#c82333] text-white font-semibold"
        >
          {busy ? "Dispatching..." : "Dispatch Mission SOS"}
        </button>
      </form>

      <div className="ms-panel p-3 border-[#D98A1F]/40 text-[11px] font-mono text-[#f5b041]">
        Delivery Channel Notice: Alerts are distributed only through the authenticated MARSCOPE application SSE/REST channel. No external SMS, email, push, or satellite alert provider is configured.
      </div>

      {queuedSos.length > 0 && (
        <div className="ms-panel p-3 border-[#DC3545]/60 bg-[#DC3545]/10 text-xs space-y-1">
          <div className="font-mono font-bold text-[#ff6b7a]">
            QUEUED_OFFLINE — NOT DELIVERED ({queuedSos.length} pending offline SOS)
          </div>
          <div className="text-[var(--text-secondary)]">
            An offline browser cannot contact remote crew members. Queued SOS events will dispatch when connectivity restores.
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 text-xs">
        <div className="flex gap-2">
          {(["ALL", "ACTIVE", "CLOSED"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setFilterMode(mode)}
              className={`px-2.5 py-1 rounded-[4px] font-mono border ${
                filterMode === mode
                  ? "border-[var(--accent-mars)] bg-[var(--accent-mars)]/15 text-[var(--text-primary)]"
                  : "border-[var(--border-subtle)] text-[var(--text-secondary)]"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <span className="font-mono text-[var(--text-secondary)]">Showing {filteredSos.length} of {sosEvents.length} events</span>
      </div>

      <div className="space-y-3">
        {filteredSos.length === 0 ? (
          <EmptyState
            icon={AlertOctagon}
            title="No SOS Events Recorded"
            description="All emergency activations, device delivery confirmations, crew acknowledgements, and cancellations appear here."
          />
        ) : (
          filteredSos.map((ev) => (
            <div
              key={ev.sos_id}
              className={`ms-panel p-4 space-y-2.5 text-xs ${
                ev.status !== "RESOLVED" && ev.status !== "CANCELLED" ? "border-[#DC3545]/60 bg-[#DC3545]/5" : ""
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-semibold text-sm text-[var(--text-primary)]">{ev.astronaut_display_name}</span>
                  <span className="ml-2 font-mono text-[11px] text-[var(--text-muted)]">
                    {new Date(ev.server_received_at_utc).toLocaleString()}
                  </span>
                </div>
                <StatusIndicator
                  label={ev.status}
                  tone={ev.status === "RESOLVED" ? "success" : ev.status === "CANCELLED" ? "unknown" : "danger"}
                  pulse={ev.status === "ACTIVE"}
                />
              </div>

              {ev.message && <p className="text-[var(--text-primary)]">{ev.message}</p>}

              <div className="flex items-center justify-between flex-wrap gap-2 font-mono text-[11px] text-[var(--text-secondary)]">
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-[var(--accent-mars)]" />
                  {ev.latitude != null && ev.longitude_east != null
                    ? `${ev.latitude.toFixed(5)}, ${ev.longitude_east.toFixed(5)} E — ${ev.position_status}`
                    : ev.position_status}
                </span>
                {ev.latitude != null && ev.longitude_east != null && (
                  <button
                    type="button"
                    onClick={() =>
                      setFocusCoordinate({
                        lat: ev.latitude!,
                        lon: ev.longitude_east!,
                        label: `SOS ${ev.astronaut_display_name}`,
                      })
                    }
                    className="px-2 py-1 rounded-[4px] border border-[var(--border-strong)] hover:border-[var(--accent-telemetry)]"
                  >
                    Focus on 3D Globe
                  </button>
                )}
              </div>

              {ev.voice_note && (
                <audio controls src={ev.voice_note.playback_url} className="w-full h-8" />
              )}

              {ev.acknowledgements.length > 0 && (
                <div className="pt-1 border-t border-[var(--border-subtle)] space-y-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                  {ev.acknowledgements.map((a) => (
                    <div key={a.ack_id}>
                      • {a.display_name}: {a.ack_type} ({new Date(a.created_at_utc).toLocaleTimeString()})
                    </div>
                  ))}
                </div>
              )}

              {ev.status !== "RESOLVED" && ev.status !== "CANCELLED" && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => void acknowledgeSos(ev.sos_id)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[4px] bg-[#D98A1F] text-[#07090C] font-semibold"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Acknowledge</span>
                  </button>
                  {canResolve && (
                    <button
                      type="button"
                      onClick={() => void resolveSos(ev.sos_id)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[4px] bg-[#1F9D68] text-white font-semibold"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Resolve</span>
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void cancelSos(ev.sos_id)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[4px] border border-[var(--border-strong)] text-[var(--text-secondary)]"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    <span>Cancel</span>
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
