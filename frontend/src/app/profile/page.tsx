"use client";

import React, { useEffect, useState } from "react";
import { Shield, Trash2, UserCog } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import type { AstronautProfile } from "../../types";

interface SessionItem {
  session_id: string;
  user_agent?: string | null;
  created_at_utc: string;
  last_seen_at_utc: string;
  revoked_at_utc?: string | null;
  is_current: boolean;
}

export default function AstronautProfilePage() {
  const { authenticated, astronaut, updateProfile, checkSession, logout } = useAuthMissionStore();

  if (!authenticated || !astronaut) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={UserCog}
          title="Sign In Required"
          description="Sign in from Mission Control to manage your astronaut account, operational mass assumptions, and active sessions."
        />
      </div>
    );
  }

  return (
    <AstronautProfileContent
      key={astronaut.astronaut_id}
      astronaut={astronaut}
      updateProfile={updateProfile}
      checkSession={checkSession}
      logout={logout}
    />
  );
}

function AstronautProfileContent({
  astronaut,
  updateProfile,
  checkSession,
  logout,
}: {
  astronaut: AstronautProfile;
  updateProfile: (patch: Record<string, unknown>) => Promise<AstronautProfile | null>;
  checkSession: () => Promise<void>;
  logout: () => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(astronaut.display_name);
  const [bodyMass, setBodyMass] = useState(
    astronaut.body_mass_kg != null ? String(astronaut.body_mass_kg) : ""
  );
  const [suitMass, setSuitMass] = useState(
    astronaut.suit_mass_kg != null ? String(astronaut.suit_mass_kg) : ""
  );
  const [equipMass, setEquipMass] = useState(
    astronaut.equipment_mass_kg != null ? String(astronaut.equipment_mass_kg) : ""
  );
  const [mobilityNotes, setMobilityNotes] = useState(astronaut.mobility_constraints || "");
  const [emergencyContact, setEmergencyContact] = useState(astronaut.emergency_contact || "");
  const [visibility, setVisibility] = useState<"mission_members" | "private">(
    astronaut.profile_visibility
  );
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const res = await apiFetch("/auth/sessions");
      if (active && res.ok) setSessions(await res.json());
    })();
    return () => {
      active = false;
    };
  }, [astronaut.astronaut_id]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavedNotice(null);
    const patch: Record<string, unknown> = {
      display_name: displayName.trim(),
      mobility_constraints: mobilityNotes.trim(),
      emergency_contact: emergencyContact.trim(),
      profile_visibility: visibility,
    };
    if (bodyMass.trim() === "") patch.clear_body_mass = true;
    else patch.body_mass_kg = Number(bodyMass);

    if (suitMass.trim() === "") patch.clear_suit_mass = true;
    else patch.suit_mass_kg = Number(suitMass);

    if (equipMass.trim() === "") patch.clear_equipment_mass = true;
    else patch.equipment_mass_kg = Number(equipMass);

    const updated = await updateProfile(patch);
    if (updated) {
      setSavedNotice("Astronaut profile saved. Entered mass parameters are tagged USER_ASSUMED.");
      await checkSession();
    } else {
      setSavedNotice("Failed to save profile changes.");
    }
  };

  const revokeSession = async (id: string) => {
    await apiFetch(`/auth/sessions/${id}`, { method: "DELETE" });
    const res = await apiFetch("/auth/sessions");
    if (res.ok) setSessions(await res.json());
  };

  const deactivateAccount = async () => {
    const res = await apiFetch("/auth/account/deactivate", { method: "POST" });
    if (res.ok) await logout();
  };

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader
        title="Astronaut Profile & Operational Assumptions"
        badge={astronaut.email}
        description="Operational body, EVA suit, and payload mass fields stay explicitly unprovided (NULL) until you enter them. Entered values are labeled USER_ASSUMED and audited."
      />

      {savedNotice && (
        <div className="p-3 rounded-[6px] border border-[#1F9D68]/45 bg-[#1F9D68]/10 text-xs text-[#4ade80]">
          {savedNotice}
        </div>
      )}

      <form onSubmit={handleSave} className="ms-panel p-5 space-y-4 text-xs">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Display Name</label>
            <input
              type="text"
              required
              minLength={2}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Profile Visibility</label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as "mission_members" | "private")}
              className="w-full ms-input"
            >
              <option value="mission_members">Visible to active mission crew</option>
              <option value="private">Private (visible only to you)</option>
            </select>
          </div>
        </div>

        <div className="p-3.5 rounded-[6px] bg-[var(--bg-void)] border border-[var(--border-subtle)] space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <span className="font-semibold text-[var(--text-primary)]">EVA Operational Mass Inputs (kg)</span>
            <StatusIndicator
              label={astronaut.body_mass_meta.classification}
              tone={astronaut.body_mass_meta.classification === "USER_ASSUMED" ? "warning" : "unknown"}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-mono text-[var(--text-muted)] mb-1">
                Body Mass (kg) [{astronaut.body_mass_meta.classification}]
              </label>
              <input
                type="number"
                step="0.1"
                value={bodyMass}
                onChange={(e) => setBodyMass(e.target.value)}
                placeholder="Not provided"
                className="w-full ms-input font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-[var(--text-muted)] mb-1">
                Suit Mass (kg) [{astronaut.suit_mass_meta.classification}]
              </label>
              <input
                type="number"
                step="0.1"
                value={suitMass}
                onChange={(e) => setSuitMass(e.target.value)}
                placeholder="Not provided"
                className="w-full ms-input font-mono"
              />
            </div>
            <div>
              <label className="block text-[11px] font-mono text-[var(--text-muted)] mb-1">
                Equipment Mass (kg) [{astronaut.equipment_mass_meta.classification}]
              </label>
              <input
                type="number"
                step="0.1"
                value={equipMass}
                onChange={(e) => setEquipMass(e.target.value)}
                placeholder="Not provided"
                className="w-full ms-input font-mono"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Mobility Constraints (Optional)</label>
            <input
              type="text"
              value={mobilityNotes}
              onChange={(e) => setMobilityNotes(e.target.value)}
              placeholder="e.g. Max sustained slope 18 deg"
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Emergency Contact Reference (Optional)</label>
            <input
              type="text"
              value={emergencyContact}
              onChange={(e) => setEmergencyContact(e.target.value)}
              placeholder="Flight Surgeon / MCC Desk"
              className="w-full ms-input"
            />
          </div>
        </div>

        <button type="submit" className="px-4 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold">
          Save Astronaut Profile
        </button>
      </form>

      {/* Active Sessions */}
      <div className="ms-panel p-4 space-y-3 text-xs">
        <div className="font-semibold text-sm flex items-center gap-2 text-[var(--text-primary)]">
          <Shield className="w-4 h-4 text-[var(--accent-telemetry)]" />
          <span>Active & Recent Authentication Sessions</span>
        </div>
        <div className="divide-y divide-[var(--border-subtle)] font-mono text-[11px]">
          {sessions.map((s) => (
            <div key={s.session_id} className="py-2 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[var(--text-primary)]">
                  {s.is_current ? "[CURRENT SESSION] " : ""}
                  {s.user_agent || "Browser / API Client"}
                </div>
                <div className="text-[var(--text-muted)]">
                  Created: {new Date(s.created_at_utc).toLocaleString()}
                  {s.revoked_at_utc ? ` · Revoked` : ""}
                </div>
              </div>
              {!s.revoked_at_utc && (
                <button
                  type="button"
                  onClick={() => void revokeSession(s.session_id)}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--border-strong)] text-[#ff6b7a]"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>Revoke</span>
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="pt-3 border-t border-[var(--border-subtle)] flex items-center justify-between">
          <span className="text-[var(--text-muted)]">Revoke account credentials and terminate all sessions:</span>
          <button
            type="button"
            onClick={() => void deactivateAccount()}
            className="px-3 py-1.5 rounded-[4px] border border-[#DC3545]/50 text-[#ff6b7a] hover:bg-[#DC3545]/10"
          >
            Deactivate Account
          </button>
        </div>
      </div>
    </div>
  );
}
