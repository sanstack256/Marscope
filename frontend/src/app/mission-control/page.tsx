"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  AlertOctagon,
  Compass,
  Flag,
  Globe2,
  KeyRound,
  LogIn,
  Microscope,
  Play,
  Plus,
  RotateCcw,
  Route,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { startDemoTour } from "../../components/DemoTourOverlay";

export default function MissionControlHomePage() {
  const {
    authChecked,
    authenticated,
    astronaut,
    authError,
    register,
    login,
    missions,
    activeMission,
    crew,
    observations,
    sosEvents,
    landingSiteBundle,
    missionEvents,
    createMission,
    joinMission,
    resetDemoMission,
  } = useAuthMissionStore();
  const [demoResetBusy, setDemoResetBusy] = useState(false);

  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const [authTab, setAuthTab] = useState<"login" | "register" | "reset">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [resetNotice, setResetNotice] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const [overviewTab, setOverviewTab] = useState<"overview" | "crew" | "observations" | "landing" | "activity">("overview");
  const [newMissionName, setNewMissionName] = useState("");
  const [newMissionObjective, setNewMissionObjective] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [missionMsg, setMissionMsg] = useState<string | null>(null);

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthBusy(true);
    setResetNotice(null);
    try {
      if (authTab === "login") {
        await login(email, password);
      } else if (authTab === "register") {
        await register(email, password, displayName);
      }
    } finally {
      setAuthBusy(false);
    }
  };

  const handleResetRequest = async () => {
    setResetNotice(null);
    const res = await apiFetch("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    const body = await res.json().catch(() => ({}));
    setResetNotice(body.reset_token_preview ? `Reset token (dev/test): ${body.reset_token_preview}` : body.message || "Reset requested.");
  };

  const handleResetConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await apiFetch("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token: resetToken, new_password: newPassword }),
    });
    if (res.ok) {
      setResetNotice("Password updated. Sign in with your new credentials.");
      setAuthTab("login");
    } else {
      const b = await res.json().catch(() => ({}));
      setResetNotice(b.detail || "Failed to confirm reset token.");
    }
  };

  const handleCreateMission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMissionName.trim()) return;
    setMissionMsg(null);
    const created = await createMission({
      name: newMissionName.trim(),
      objective: newMissionObjective.trim(),
    });
    if (created) {
      setNewMissionName("");
      setNewMissionObjective("");
      setMissionMsg(`Created mission "${created.name}".`);
    } else {
      setMissionMsg("Failed to create mission.");
    }
  };

  const handleJoinMission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteCode.trim()) return;
    setMissionMsg(null);
    const joined = await joinMission(inviteCode.trim());
    if (joined) {
      setInviteCode("");
      setMissionMsg(`Joined mission "${joined.name}" as ${joined.my_role}.`);
    } else {
      setMissionMsg("Invalid, expired, or revoked mission invitation.");
    }
  };

  if (!authChecked) {
    return (
      <div className="max-w-5xl mx-auto p-6 ms-panel text-xs font-mono text-[var(--text-secondary)]">
        Verifying astronaut session...
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <PageHeader
          title="MARSCOPE Mission Control"
          badge="IAU2000:49900"
          description="Sign in or register an astronaut account to establish isolated multi-astronaut mission workspaces, live coordinates, SOS emergency coordination, and DEM-backed landing-site planning."
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Auth Portal */}
          <div className="lg:col-span-6 ms-panel p-5 space-y-4">
            <div className="flex items-center gap-1 p-1 rounded-[6px] bg-[var(--bg-void)] border border-[var(--border-subtle)] text-xs">
              <button
                type="button"
                onClick={() => setAuthTab("login")}
                className={`flex-1 py-1.5 rounded-[4px] font-medium ${
                  authTab === "login" ? "bg-[var(--accent-mars)] text-white" : "text-[var(--text-secondary)]"
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => setAuthTab("register")}
                className={`flex-1 py-1.5 rounded-[4px] font-medium ${
                  authTab === "register" ? "bg-[var(--accent-mars)] text-white" : "text-[var(--text-secondary)]"
                }`}
              >
                Register Astronaut
              </button>
              <button
                type="button"
                onClick={() => setAuthTab("reset")}
                className={`flex-1 py-1.5 rounded-[4px] font-medium ${
                  authTab === "reset" ? "bg-[var(--bg-elevated)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                }`}
              >
                Reset Password
              </button>
            </div>

            {authTab === "reset" ? (
              <form onSubmit={handleResetConfirm} className="space-y-3 text-xs">
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Astronaut Email</label>
                  <div className="flex gap-2">
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="astronaut@agency.org"
                      className="flex-1 ms-input"
                    />
                    <button
                      type="button"
                      onClick={() => void handleResetRequest()}
                      className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-[var(--text-primary)]"
                    >
                      Request Token
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Reset Token</label>
                  <input
                    type="text"
                    required
                    value={resetToken}
                    onChange={(e) => setResetToken(e.target.value)}
                    className="w-full ms-input font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">New Password (10+ chars, upper+lower+digit)</label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full ms-input"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-2 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold"
                >
                  Confirm Password Reset
                </button>
              </form>
            ) : (
              <form onSubmit={handleAuthSubmit} className="space-y-3.5 text-xs">
                {authTab === "register" && (
                  <div>
                    <label className="block text-[var(--text-secondary)] mb-1">Crew Display Name</label>
                    <input
                      type="text"
                      required
                      minLength={2}
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder="Cmdr. Elena Rostova"
                      className="w-full ms-input"
                    />
                  </div>
                )}
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="astronaut@marscope.org"
                    className="w-full ms-input"
                  />
                </div>
                <div>
                  <label className="block text-[var(--text-secondary)] mb-1">
                    Password {authTab === "register" && "(min 10 chars, upper, lower, digit)"}
                  </label>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full ms-input"
                  />
                </div>

                {authError && (
                  <div className="p-2.5 rounded-[4px] bg-[#DC3545]/15 border border-[#DC3545]/45 text-[#ff6b7a]">
                    {authError}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={authBusy}
                  className="w-full py-2.5 rounded-[4px] bg-[var(--accent-mars)] hover:bg-[var(--accent-mars-hover)] text-white font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {authTab === "login" ? <LogIn className="w-4 h-4" /> : <UserPlus className="w-4 h-4" />}
                  <span>
                    {authBusy
                      ? "Authenticating..."
                      : authTab === "login"
                      ? "Establish Authenticated Session"
                      : "Create Astronaut Account"}
                  </span>
                </button>
              </form>
            )}

            {resetNotice && (
              <div className="p-2.5 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-strong)] font-mono text-[11px] text-[var(--accent-telemetry)]">
                {resetNotice}
              </div>
            )}
          </div>

          {/* Honest Platform Readiness Summary */}
          <div className="lg:col-span-6 space-y-4">
            <div className="ms-panel p-5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--accent-telemetry)]">
                <ShieldCheck className="w-4 h-4" />
                <span>Authenticated Multi-Astronaut Architecture</span>
              </div>
              <ul className="space-y-2 text-xs text-[var(--text-secondary)] leading-relaxed">
                <li>• <strong className="text-[var(--text-primary)]">Zero Fabricated Defaults:</strong> Operational mass parameters and landing sites remain explicitly unconfigured until entered or registered.</li>
                <li>• <strong className="text-[var(--text-primary)]">Cookie + CSRF Isolation:</strong> HttpOnly SameSite cookies paired with per-session CSRF headers and strict mission membership authorization.</li>
                <li>• <strong className="text-[var(--text-primary)]">Mars Planetary Integrity:</strong> All coordinates validate against IAU2000:49900; terrain elevation and landing-site perimeters sample local NASA PDS DEM GeoTIFFs only.</li>
              </ul>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Link href="/explorer" className="ms-panel p-4 hover:border-[var(--accent-telemetry)] transition-colors">
                <Globe2 className="w-5 h-5 text-[var(--accent-telemetry)] mb-2" />
                <div className="text-xs font-semibold text-[var(--text-primary)]">Surface Explorer 3D</div>
                <div className="text-[11px] text-[var(--text-muted)] mt-0.5">Mars Globe + HiRISE DEM mesh</div>
              </Link>
              <Link href="/planner" className="ms-panel p-4 hover:border-[var(--accent-mars)] transition-colors">
                <Route className="w-5 h-5 text-[var(--accent-mars)] mb-2" />
                <div className="text-xs font-semibold text-[var(--text-primary)]">Uncertainty Route Planner</div>
                <div className="text-[11px] text-[var(--text-muted)] mt-0.5">A*/Dijkstra + return corridor</div>
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const activeAlerts = sosEvents.filter((s) => s.status !== "RESOLVED" && s.status !== "CANCELLED");

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title={activeMission ? activeMission.name : "Mission Control Workspace"}
        badge={activeMission ? activeMission.my_role : "AUTHENTICATED"}
        description={
          activeMission
            ? activeMission.objective || "Active multi-astronaut Mars surface expedition workspace."
            : `Signed in as ${astronaut?.display_name}. Create a new mission or join with an invitation token.`
        }
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/landing-site"
              className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-xs font-medium text-[var(--text-primary)] hover:border-[var(--accent-telemetry)]"
            >
              Landing Site & 3D Bounds
            </Link>
            <Link
              href="/explorer"
              className="px-3 py-1.5 rounded-[4px] bg-[var(--accent-mars)] text-white text-xs font-semibold hover:bg-[var(--accent-mars-hover)]"
            >
              Open 3D Explorer
            </Link>
          </div>
        }
      />

      {missions.length === 0 || !activeMission ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <form onSubmit={handleCreateMission} className="ms-panel p-5 space-y-3 text-xs">
            <div className="flex items-center gap-2 font-semibold text-sm text-[var(--text-primary)]">
              <Plus className="w-4 h-4 text-[var(--accent-mars)]" />
              <span>Create New Surface Mission</span>
            </div>
            <input
              type="text"
              required
              minLength={3}
              value={newMissionName}
              onChange={(e) => setNewMissionName(e.target.value)}
              placeholder="Mission name (e.g., Sol 410 Boxwork Reconnaissance)"
              className="w-full ms-input"
            />
            <textarea
              rows={2}
              value={newMissionObjective}
              onChange={(e) => setNewMissionObjective(e.target.value)}
              placeholder="Scientific & EVA objective"
              className="w-full ms-input"
            />
            <button
              type="submit"
              className="px-4 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold"
            >
              Create Mission (MISSION_LEAD)
            </button>
          </form>

          <form onSubmit={handleJoinMission} className="ms-panel p-5 space-y-3 text-xs">
            <div className="flex items-center gap-2 font-semibold text-sm text-[var(--text-primary)]">
              <KeyRound className="w-4 h-4 text-[var(--accent-telemetry)]" />
              <span>Join Existing Mission via Invitation Token</span>
            </div>
            <input
              type="text"
              required
              minLength={12}
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="Paste single-use or multi-use invitation token"
              className="w-full ms-input font-mono"
            />
            <button
              type="submit"
              className="px-4 py-2 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold"
            >
              Join Mission Crew
            </button>
          </form>
        </div>
      ) : (
        <>
          {astronaut?.is_demo && (
            <div className="rounded-[8px] border border-[#FF6A1A]/50 bg-[#0B0B0B] p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-[4px] bg-[#FF6A1A] text-white font-mono font-bold text-[10px] tracking-wider">
                    DEMO MODE
                  </span>
                  <span className="text-[11px] font-mono text-[#A1A1AA]">
                    DEMONSTRATION MISSION • ISOLATED SANDBOX
                  </span>
                </div>
                <h2 className="text-base font-semibold text-white">
                  Welcome to the MARSCOPE demonstration mission.
                </h2>
                <p className="text-xs text-[#A1A1AA] max-w-2xl">
                  This prepared mission demonstrates crew collaboration, field observations, emergency response,
                  spatial exploration and scientific evidence inspection.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 shrink-0">
                <button
                  type="button"
                  onClick={() => startDemoTour(0)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-[4px] bg-[#FF6A1A] hover:bg-[#FF7F32] text-white text-xs font-semibold transition-colors"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>START GUIDED TOUR</span>
                </button>
                <button
                  type="button"
                  disabled={demoResetBusy}
                  onClick={async () => {
                    setDemoResetBusy(true);
                    try {
                      await resetDemoMission();
                    } finally {
                      setDemoResetBusy(false);
                    }
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[4px] border border-[#242424] bg-[#111111] hover:border-[#FF6A1A]/60 text-[#A1A1AA] hover:text-white text-xs font-medium disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>{demoResetBusy ? "Resetting..." : "Reset Demo Mission"}</span>
                </button>
              </div>
            </div>
          )}

          {/* Summary Metric Row (max 4 concise cards, no visual bloat) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <div className="ms-panel p-4 flex flex-col justify-between gap-2">
              <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span>Crew Roster</span>
                <Users className="w-4 h-4 text-[var(--accent-telemetry)]" />
              </div>
              <div className="text-2xl font-mono font-bold text-[var(--text-primary)]">{crew.length}</div>
              <div className="text-[11px] font-mono text-[var(--text-muted)]">
                Active members in {activeMission.my_role}
              </div>
            </div>

            <div className="ms-panel p-4 flex flex-col justify-between gap-2">
              <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span>Landing Site</span>
                <Flag className="w-4 h-4 text-[var(--accent-mars)]" />
              </div>
              <div>
                <StatusIndicator
                  label={
                    landingSiteBundle?.landing_site_status === "REGISTERED"
                      ? landingSiteBundle.landing_site?.dem_coverage_state || "REGISTERED"
                      : "UNCONFIGURED"
                  }
                  tone={
                    landingSiteBundle?.landing_site_status === "REGISTERED"
                      ? landingSiteBundle.landing_site?.dem_coverage_state === "COVERED_DEM"
                        ? "success"
                        : "warning"
                      : "unknown"
                  }
                />
              </div>
              <div className="text-[11px] font-mono text-[var(--text-muted)] truncate">
                {landingSiteBundle?.landing_site
                  ? `${landingSiteBundle.landing_site.latitude.toFixed(4)}, ${landingSiteBundle.landing_site.longitude_east.toFixed(4)} E`
                  : "Register explicit Mars coordinates"}
              </div>
            </div>

            <div className="ms-panel p-4 flex flex-col justify-between gap-2">
              <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span>Field Observations</span>
                <Microscope className="w-4 h-4 text-[var(--accent-telemetry)]" />
              </div>
              <div className="text-2xl font-mono font-bold text-[var(--text-primary)]">{observations.length}</div>
              <div className="text-[11px] font-mono text-[var(--text-muted)]">
                Vocabulary-validated mission notes
              </div>
            </div>

            <div className="ms-panel p-4 flex flex-col justify-between gap-2">
              <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span>Emergency SOS</span>
                <AlertOctagon className={`w-4 h-4 ${activeAlerts.length > 0 ? "text-[#ff6b7a]" : "text-[var(--text-muted)]"}`} />
              </div>
              <div className="text-2xl font-mono font-bold text-[var(--text-primary)]">{activeAlerts.length}</div>
              <div className="text-[11px] font-mono text-[var(--text-muted)]">
                {activeAlerts.length > 0 ? "Requires crew acknowledgement" : "No active distress alerts"}
              </div>
            </div>
          </div>

          {/* Workspace Tabs */}
          <div className="flex flex-wrap items-center gap-1 border-b border-[var(--border-subtle)] pb-2 text-xs">
            {(
              [
                ["overview", "Overview"],
                ["crew", `Crew (${crew.length})`],
                ["observations", `Observations (${observations.length})`],
                ["landing", "Landing Site & Perimeter"],
                ["activity", `Audit Log (${missionEvents.length})`],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setOverviewTab(id)}
                className={`px-3 py-1.5 rounded-[4px] font-medium ${
                  overviewTab === id
                    ? "bg-[var(--accent-mars)]/15 text-[var(--text-primary)] border border-[var(--accent-mars)]/45"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {overviewTab === "overview" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
              <Link href="/crew" className="ms-panel p-4 hover:border-[var(--accent-telemetry)] transition-colors space-y-1.5">
                <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
                  <Users className="w-4 h-4 text-[var(--accent-telemetry)]" />
                  <span>Manage Crew & Positions</span>
                </div>
                <p className="text-[var(--text-secondary)]">
                  Ingest validated IAU2000:49900 telemetry positions, manage location sharing, and inspect connection staleness.
                </p>
              </Link>
              <Link href="/observations" className="ms-panel p-4 hover:border-[var(--accent-mars)] transition-colors space-y-1.5">
                <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
                  <Microscope className="w-4 h-4 text-[var(--accent-mars)]" />
                  <span>Log Field Observations</span>
                </div>
                <p className="text-[var(--text-secondary)]">
                  Submit crew mineral/hazard notes against the controlled planetary species vocabulary with voice memos.
                </p>
              </Link>
              <Link href="/landing-site" className="ms-panel p-4 hover:border-[#1F9D68] transition-colors space-y-1.5">
                <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
                  <Compass className="w-4 h-4 text-[#4ade80]" />
                  <span>3D Landing-Site Perimeter</span>
                </div>
                <p className="text-[var(--text-secondary)]">
                  Register landing coordinates from real datasets and compute DEM slope/roughness planning boundaries in 3D.
                </p>
              </Link>
            </div>
          )}

          {overviewTab === "crew" && (
            <div className="ms-panel overflow-hidden">
              <div className="divide-y divide-[var(--border-subtle)] text-xs">
                {crew.map((member) => (
                  <div key={member.astronaut_id} className="p-3.5 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold text-[var(--text-primary)]">
                        {member.display_name}{" "}
                        <span className="font-mono text-[10px] text-[var(--text-muted)]">({member.role})</span>
                      </div>
                      <div className="font-mono text-[11px] text-[var(--text-secondary)] mt-0.5">
                        {member.latest_position
                          ? `${member.latest_position.latitude.toFixed(5)}, ${member.latest_position.longitude_east.toFixed(5)} E (${member.latest_position.source_classification})`
                          : "No Mars coordinate received"}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
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
                          className="px-2 py-1 rounded-[4px] border border-[var(--border-strong)] text-[11px] hover:border-[var(--accent-telemetry)]"
                        >
                          Focus Map
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {overviewTab === "observations" && (
            <div className="space-y-2">
              {observations.length === 0 ? (
                <EmptyState
                  icon={Microscope}
                  title="No crew field observations yet"
                  description="Log mineral discoveries, hazard reports, or sample notes in Field Observations."
                />
              ) : (
                observations.slice(0, 12).map((o) => (
                  <div key={o.observation_id} className="ms-panel p-3.5 text-xs flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[var(--text-primary)]">{o.category}</span>
                        {o.species_display_name && (
                          <span className="font-mono text-[11px] text-[var(--accent-telemetry)]">
                            {o.species_display_name}
                          </span>
                        )}
                      </div>
                      <p className="text-[var(--text-secondary)] mt-1">{o.description}</p>
                    </div>
                    <StatusIndicator
                      label={o.epistemic_state}
                      tone={o.epistemic_state === "CORROBORATED_BY_EVIDENCE" ? "success" : "warning"}
                    />
                  </div>
                ))
              )}
            </div>
          )}

          {overviewTab === "landing" && (
            <div className="ms-panel p-4 text-xs space-y-2">
              {landingSiteBundle?.landing_site ? (
                <>
                  <div className="font-semibold text-sm text-[var(--text-primary)]">
                    {landingSiteBundle.landing_site.name}
                  </div>
                  <div className="font-mono text-[var(--text-secondary)]">
                    {landingSiteBundle.landing_site.latitude.toFixed(5)},{" "}
                    {landingSiteBundle.landing_site.longitude_east.toFixed(5)} E ({landingSiteBundle.landing_site.crs}) —{" "}
                    {landingSiteBundle.landing_site.dem_coverage_state}
                  </div>
                  {landingSiteBundle.perimeter && (
                    <div className="p-2.5 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] font-mono text-[11px]">
                      {landingSiteBundle.perimeter.status} — {landingSiteBundle.perimeter.classification_label}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-[var(--text-secondary)]">
                  Landing site is unconfigured (`LANDING_SITE_UNCONFIGURED`).{" "}
                  <Link href="/landing-site" className="text-[var(--accent-telemetry)] underline">
                    Register explicit landing coordinates
                  </Link>
                  .
                </div>
              )}
            </div>
          )}

          {overviewTab === "activity" && (
            <div className="ms-panel divide-y divide-[var(--border-subtle)] text-xs font-mono">
              {missionEvents.slice(0, 25).map((ev) => (
                <div key={ev.event_id} className="p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-[var(--accent-telemetry)]">#{ev.event_seq}</span>{" "}
                    <span className="text-[var(--text-primary)] font-semibold">{ev.event_type}</span>
                  </div>
                  <span className="text-[11px] text-[var(--text-muted)] shrink-0">
                    {new Date(ev.server_timestamp_utc).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {missionMsg && (
        <div className="p-3 rounded-[6px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-xs font-mono text-[var(--accent-telemetry)]">
          {missionMsg}
        </div>
      )}
    </div>
  );
}
