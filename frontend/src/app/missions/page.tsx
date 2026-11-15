"use client";

import React, { useState } from "react";
import { KeyRound, Plus, ShieldCheck, Trash2, LogOut, Copy } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";

export default function MissionsPage() {
  const {
    authenticated,
    missions,
    activeMission,
    invitations,
    selectMission,
    createMission,
    joinMission,
    refreshMissionWorkspace,
    loadMissions,
  } = useAuthMissionStore();

  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [region, setRegion] = useState("");
  const [joinToken, setJoinToken] = useState("");
  const [inviteRole, setInviteRole] = useState<"ASTRONAUT" | "MISSION_OPERATOR" | "MISSION_LEAD">("ASTRONAUT");
  const [singleUse, setSingleUse] = useState(true);
  const [latestIssuedToken, setLatestIssuedToken] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  if (!authenticated) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={ShieldCheck}
          title="Authentication Required"
          description="Sign in from Mission Control to create, join, or administer isolated multi-astronaut missions."
        />
      </div>
    );
  }

  const canManageInvites =
    activeMission && ["MISSION_LEAD", "MISSION_OPERATOR"].includes(activeMission.my_role);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrMsg(null);
    setStatusMsg(null);
    const created = await createMission({
      name: name.trim(),
      objective: objective.trim(),
      operating_region: region.trim() || undefined,
    });
    if (created) {
      setName("");
      setObjective("");
      setRegion("");
      setStatusMsg(`Mission "${created.name}" created cleanly.`);
    } else {
      setErrMsg("Could not create mission.");
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrMsg(null);
    setStatusMsg(null);
    const joined = await joinMission(joinToken.trim());
    if (joined) {
      setJoinToken("");
      setStatusMsg(`Joined "${joined.name}" with role ${joined.my_role}.`);
    } else {
      setErrMsg("Invitation token is invalid, expired, revoked, or exhausted.");
    }
  };

  const handleIssueInvite = async () => {
    if (!activeMission) return;
    setErrMsg(null);
    setLatestIssuedToken(null);
    const res = await apiFetch(`/missions/${activeMission.mission_id}/invitations`, {
      method: "POST",
      body: JSON.stringify({ role_on_join: inviteRole, single_use: singleUse, expires_in_hours: 24 }),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      setErrMsg(b.detail || "Failed to generate invitation.");
      return;
    }
    const created = await res.json();
    setLatestIssuedToken(created.invite_token || null);
    await refreshMissionWorkspace(activeMission.mission_id);
  };

  const handleRevokeInvite = async (inviteId: string) => {
    if (!activeMission) return;
    await apiFetch(`/missions/${activeMission.mission_id}/invitations/${inviteId}/revoke`, {
      method: "POST",
    });
    await refreshMissionWorkspace(activeMission.mission_id);
  };

  const handleLeave = async (missionId: string) => {
    setErrMsg(null);
    const res = await apiFetch(`/missions/${missionId}/leave`, { method: "POST" });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      setErrMsg(b.detail || "Cannot leave mission.");
      return;
    }
    await loadMissions();
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title="Missions & Access Control"
        badge="RBAC"
        description="Manage isolated multi-astronaut missions, issue expiring CSPRNG invitations, and switch active expedition context."
      />

      {errMsg && (
        <div className="p-3 rounded-[6px] border border-[#DC3545]/45 bg-[#DC3545]/10 text-xs text-[#ff6b7a]">
          {errMsg}
        </div>
      )}
      {statusMsg && (
        <div className="p-3 rounded-[6px] border border-[#1F9D68]/45 bg-[#1F9D68]/10 text-xs text-[#4ade80]">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <form onSubmit={handleCreate} className="ms-panel p-4 space-y-3 text-xs">
          <h2 className="font-semibold text-sm flex items-center gap-2 text-[var(--text-primary)]">
            <Plus className="w-4 h-4 text-[var(--accent-mars)]" />
            <span>Create Mission</span>
          </h2>
          <input
            type="text"
            required
            minLength={3}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mission title"
            className="w-full ms-input"
          />
          <input
            type="text"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="Operating Mars region (optional, e.g. Gale Crater)"
            className="w-full ms-input"
          />
          <textarea
            rows={2}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Expedition objective"
            className="w-full ms-input"
          />
          <button type="submit" className="px-4 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold">
            Create & Activate
          </button>
        </form>

        <form onSubmit={handleJoin} className="ms-panel p-4 space-y-3 text-xs">
          <h2 className="font-semibold text-sm flex items-center gap-2 text-[var(--text-primary)]">
            <KeyRound className="w-4 h-4 text-[var(--accent-telemetry)]" />
            <span>Join Mission with Invitation Token</span>
          </h2>
          <input
            type="text"
            required
            value={joinToken}
            onChange={(e) => setJoinToken(e.target.value)}
            placeholder="Paste mission invite token"
            className="w-full ms-input font-mono"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold"
          >
            Redeem Invitation
          </button>
        </form>
      </div>

      {/* Mission Directory */}
      <div className="ms-panel overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)]/60 text-xs font-semibold uppercase tracking-wider">
          Your Active Missions ({missions.length})
        </div>
        <div className="divide-y divide-[var(--border-subtle)] text-xs">
          {missions.map((m) => (
            <div key={m.mission_id} className="p-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-[var(--text-primary)]">{m.name}</span>
                  <StatusIndicator label={m.my_role} tone="telemetry" />
                  <StatusIndicator
                    label={m.landing_site_status}
                    tone={m.landing_site_status === "REGISTERED" ? "success" : "unknown"}
                  />
                </div>
                <div className="text-[11px] font-mono text-[var(--text-muted)] mt-1">
                  Members: {m.active_member_count} · Active SOS: {m.active_sos_count}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void selectMission(m.mission_id)}
                  className={`px-3 py-1.5 rounded-[4px] font-medium ${
                    activeMission?.mission_id === m.mission_id
                      ? "bg-[var(--accent-mars)] text-white"
                      : "border border-[var(--border-strong)] text-[var(--text-primary)]"
                  }`}
                >
                  {activeMission?.mission_id === m.mission_id ? "Active" : "Switch To"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleLeave(m.mission_id)}
                  className="px-2.5 py-1.5 rounded-[4px] border border-[var(--border-strong)] text-[var(--text-secondary)] hover:text-[#ff6b7a]"
                  title="Leave mission"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Invitation Generator for Active Mission */}
      {canManageInvites && (
        <div className="ms-panel p-4 space-y-4 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold text-sm text-[var(--text-primary)]">
                Crew Invitations — {activeMission?.name}
              </h2>
              <p className="text-[11px] text-[var(--text-muted)]">
                Tokens are stored SHA-256 hashed on the server. Save or share the generated secret token immediately.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as "ASTRONAUT" | "MISSION_OPERATOR" | "MISSION_LEAD")}
                className="ms-input text-xs py-1"
              >
                <option value="ASTRONAUT">ASTRONAUT</option>
                <option value="MISSION_OPERATOR">MISSION_OPERATOR</option>
                <option value="MISSION_LEAD">MISSION_LEAD</option>
              </select>
              <label className="flex items-center gap-1.5 text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={singleUse}
                  onChange={(e) => setSingleUse(e.target.checked)}
                />
                <span>Single-use</span>
              </label>
              <button
                type="button"
                onClick={() => void handleIssueInvite()}
                className="px-3 py-1.5 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold"
              >
                Generate Invite
              </button>
            </div>
          </div>

          {latestIssuedToken && (
            <div className="p-3 rounded-[4px] bg-[var(--bg-void)] border border-[var(--accent-telemetry)]/50 flex items-center justify-between gap-2 font-mono">
              <span className="truncate text-[var(--accent-telemetry)]">{latestIssuedToken}</span>
              <button
                type="button"
                onClick={() => void navigator.clipboard?.writeText(latestIssuedToken)}
                className="px-2 py-1 rounded bg-[var(--bg-elevated)] text-xs inline-flex items-center gap-1 shrink-0"
              >
                <Copy className="w-3 h-3" />
                <span>Copy</span>
              </button>
            </div>
          )}

          <div className="divide-y divide-[var(--border-subtle)]">
            {invitations.map((inv) => (
              <div key={inv.invite_id} className="py-2 flex items-center justify-between gap-2 font-mono text-[11px]">
                <div>
                  Role: {inv.role_on_join} · Uses: {inv.uses_count}
                  {inv.max_uses ? `/${inv.max_uses}` : ""} · Expires:{" "}
                  {new Date(inv.expires_at_utc).toLocaleString()}
                </div>
                {inv.revoked_at_utc ? (
                  <StatusIndicator label="REVOKED" tone="danger" />
                ) : (
                  <button
                    type="button"
                    onClick={() => void handleRevokeInvite(inv.invite_id)}
                    className="text-[#ff6b7a] hover:underline inline-flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Revoke</span>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
