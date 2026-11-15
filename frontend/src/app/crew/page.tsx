"use client";

import React, { useState } from "react";
import { Crosshair, MapPin, Navigation, Shield, Trash2, Users } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { MissionRole } from "../../types";

export default function CrewRosterPage() {
  const {
    authenticated,
    astronaut,
    activeMissionId,
    activeMission,
    crew,
    ingestPosition,
    refreshMissionWorkspace,
  } = useAuthMissionStore();
  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const [latStr, setLatStr] = useState("");
  const [lonStr, setLonStr] = useState("");
  const [sourceId, setSourceId] = useState("suit_nav_imu_01");
  const [sourceClass, setSourceClass] = useState<"TELEMETRY_PROVIDER" | "LOCALIZATION_SOLVER" | "USER_PROVIDED">(
    "USER_PROVIDED"
  );
  const [uncertaintyM, setUncertaintyM] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!authenticated || !activeMissionId || !activeMission) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={Users}
          title="Active Mission Required"
          description="Sign in and select a mission to inspect crew members, position freshness, and sharing controls."
        />
      </div>
    );
  }

  const myMembership = crew.find((c) => c.astronaut_id === astronaut?.astronaut_id);
  const isLead = activeMission.my_role === "MISSION_LEAD";

  const handleSubmitPosition = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    const lat = Number(latStr);
    const lon = Number(lonStr);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setFeedback("Latitude and East Longitude must be valid numeric degrees.");
      return;
    }
    const res = await ingestPosition({
      latitude: lat,
      longitude: lon,
      crs: "IAU2000:49900",
      source_id: sourceId.trim() || "crew_manual_report",
      source_classification: sourceClass,
      uncertainty_m: uncertaintyM.trim() ? Number(uncertaintyM) : undefined,
      sequence_number: Date.now(),
    });
    if (!res.ok) {
      setFeedback(res.error || "Failed to ingest Mars coordinate.");
    } else if (res.queuedOffline) {
      setFeedback("Network offline: coordinate queued cleanly for automatic delivery.");
    } else {
      setFeedback("IAU2000:49900 crew position verified, DEM-sampled & broadcast.");
    }
  };

  const toggleMySharing = async () => {
    if (!myMembership) return;
    await apiFetch(`/missions/${activeMissionId}/positions/sharing`, {
      method: "PUT",
      body: JSON.stringify({ location_sharing_enabled: !myMembership.location_sharing_enabled }),
    });
    await refreshMissionWorkspace(activeMissionId);
  };

  const changeRole = async (targetId: string, role: MissionRole) => {
    await apiFetch(`/missions/${activeMissionId}/crew/${targetId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
    await refreshMissionWorkspace(activeMissionId);
  };

  const removeMember = async (targetId: string) => {
    await apiFetch(`/missions/${activeMissionId}/crew/${targetId}`, {
      method: "DELETE",
    });
    await refreshMissionWorkspace(activeMissionId);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title="Crew Roster & Mars Localization"
        badge={activeMission.name}
        description="Real-time crew connection status, IAU2000:49900 position freshness (CONNECTED vs POSITION_STALE vs POSITION_UNAVAILABLE), and opt-in location sharing."
        actions={
          myMembership && (
            <button
              type="button"
              onClick={() => void toggleMySharing()}
              className="px-3 py-1.5 rounded-[4px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-xs font-mono"
            >
              Location Sharing: {myMembership.location_sharing_enabled ? "ENABLED" : "DISABLED"}
            </button>
          )
        }
      />

      {/* Mars IAU2000:49900 Position Update Form */}
      <form onSubmit={handleSubmitPosition} className="ms-panel p-4 space-y-3 text-xs">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="font-semibold text-sm flex items-center gap-2 text-[var(--text-primary)]">
            <Navigation className="w-4 h-4 text-[var(--accent-telemetry)]" />
            <span>Report Validated Mars Coordinate (IAU2000:49900)</span>
          </div>
          <span className="font-mono text-[10px] text-[var(--text-muted)]">
            Browser GPS rejected · Elevation sampled from covering PDS DEM only
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
          <input
            type="text"
            required
            value={latStr}
            onChange={(e) => setLatStr(e.target.value)}
            placeholder="Latitude (-90..90)"
            className="ms-input font-mono text-xs"
          />
          <input
            type="text"
            required
            value={lonStr}
            onChange={(e) => setLonStr(e.target.value)}
            placeholder="East Lon (0..360)"
            className="ms-input font-mono text-xs"
          />
          <select
            value={sourceClass}
            onChange={(e) =>
              setSourceClass(e.target.value as "TELEMETRY_PROVIDER" | "LOCALIZATION_SOLVER" | "USER_PROVIDED")
            }
            className="ms-input text-xs"
          >
            <option value="USER_PROVIDED">USER_PROVIDED</option>
            <option value="LOCALIZATION_SOLVER">LOCALIZATION_SOLVER</option>
            <option value="TELEMETRY_PROVIDER">TELEMETRY_PROVIDER</option>
          </select>
          <input
            type="text"
            value={sourceId}
            onChange={(e) => setSourceId(e.target.value)}
            placeholder="Source adapter ID"
            className="ms-input font-mono text-xs"
          />
          <input
            type="text"
            value={uncertaintyM}
            onChange={(e) => setUncertaintyM(e.target.value)}
            placeholder="Uncertainty (m, opt)"
            className="ms-input font-mono text-xs"
          />
        </div>

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <button
            type="submit"
            className="px-4 py-1.5 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold"
          >
            Transmit Mars Coordinate
          </button>
          {feedback && <span className="font-mono text-[11px] text-[var(--accent-telemetry)]">{feedback}</span>}
        </div>
      </form>

      {/* Roster Table */}
      <div className="ms-panel divide-y divide-[var(--border-subtle)] text-xs">
        {crew.map((member) => (
          <div key={member.astronaut_id} className="p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-sm text-[var(--text-primary)]">{member.display_name}</span>
                <StatusIndicator label={member.role} tone="mars" />
                <StatusIndicator
                  label={member.connection_status}
                  tone={
                    member.connection_status === "CONNECTED"
                      ? "success"
                      : member.connection_status === "POSITION_STALE"
                      ? "warning"
                      : "unknown"
                  }
                />
              </div>
              <div className="flex items-center gap-2 font-mono text-[11px] text-[var(--text-secondary)]">
                <MapPin className="w-3.5 h-3.5 text-[var(--accent-telemetry)] shrink-0" />
                {member.latest_position ? (
                  <span>
                    {member.latest_position.latitude.toFixed(5)}, {member.latest_position.longitude_east.toFixed(5)} E ·
                    Elev:{" "}
                    {member.latest_position.elevation_m != null
                      ? `${member.latest_position.elevation_m.toFixed(1)} m`
                      : "Outside DEM"}
                    {" · "}Age: {Math.round(member.latest_position.age_seconds)}s ·{" "}
                    {member.latest_position.source_classification}
                  </span>
                ) : (
                  <span className="text-[var(--text-muted)]">
                    {member.location_sharing_enabled ? "No validated Mars position received" : "Sharing disabled"}
                  </span>
                )}
              </div>
              {member.total_mass_kg != null && (
                <div className="font-mono text-[10px] text-[var(--text-muted)]">
                  Mass Budget ({member.mass_classification}): {member.total_mass_kg} kg
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              {member.latest_position && (
                <button
                  type="button"
                  onClick={() =>
                    setFocusCoordinate({
                      lat: member.latest_position!.latitude,
                      lon: member.latest_position!.longitude_east,
                      label: member.display_name,
                    })
                  }
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-[4px] border border-[var(--border-strong)] hover:border-[var(--accent-telemetry)]"
                >
                  <Crosshair className="w-3.5 h-3.5 text-[var(--accent-telemetry)]" />
                  <span>Locate 3D</span>
                </button>
              )}

              {isLead && member.astronaut_id !== astronaut?.astronaut_id && (
                <>
                  <select
                    aria-label={`Change role for ${member.display_name}`}
                    value={member.role}
                    onChange={(e) => void changeRole(member.astronaut_id, e.target.value as MissionRole)}
                    className="ms-input text-xs py-1"
                  >
                    <option value="ASTRONAUT">ASTRONAUT</option>
                    <option value="MISSION_OPERATOR">MISSION_OPERATOR</option>
                    <option value="MISSION_LEAD">MISSION_LEAD</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => void removeMember(member.astronaut_id)}
                    aria-label={`Remove ${member.display_name}`}
                    className="p-1.5 rounded-[4px] border border-[var(--border-strong)] text-[#ff6b7a] hover:bg-[#DC3545]/15"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 text-[11px] font-mono text-[var(--text-muted)]">
        <Shield className="w-3.5 h-3.5" />
        <span>Role changes and removals apply immediately and are logged in mission_events.</span>
      </div>
    </div>
  );
}
