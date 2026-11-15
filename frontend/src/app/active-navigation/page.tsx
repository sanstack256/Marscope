"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {
  AlertOctagon,
  AlertTriangle,
  Compass,
  MapPin,
  Navigation,
  RefreshCw,
  RotateCcw,
  Route,
  ShieldAlert,
} from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { useEvaOperationsStore } from "../../stores/useEvaOperationsStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { NavigationSessionRecord, NavigationState } from "../../types";

const LocalTerrain3DViewer = dynamic(
  () => import("../../components/LocalTerrain3DViewer").then((m) => m.LocalTerrain3DViewer),
  { ssr: false }
);

export default function ActiveNavigationPage() {
  const {
    authenticated,
    activeMissionId,
    activeMission,
    landingSiteBundle,
    ingestPosition,
    setSosDrawerOpen,
  } = useAuthMissionStore();
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const evaEnvelope = useEvaOperationsStore((s) => s.evaEnvelope);

  const [sessions, setSessions] = useState<NavigationSessionRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // New session configuration
  const [navMode, setNavMode] = useState<"OPERATOR_SUPERVISED_EVA" | "MANUAL_WAYPOINT_CHECK" | "RETURN_TO_BASE">(
    "OPERATOR_SUPERVISED_EVA"
  );
  const [deviationThresholdM, setDeviationThresholdM] = useState("");
  const [walkingSpeedMps, setWalkingSpeedMps] = useState("");
  const [maxDurationMin, setMaxDurationMin] = useState("");

  // Manual position entry (USER_REPORTED)
  const [posLat, setPosLat] = useState("");
  const [posLon, setPosLon] = useState("");
  const [posAccM, setPosAccM] = useState("");

  // Transition & obstruction inputs
  const [transitionReason, setTransitionReason] = useState("");
  const [obsLat, setObsLat] = useState("");
  const [obsLon, setObsLon] = useState("");
  const [obsSegIdx, setObsSegIdx] = useState("0");
  const [obsDesc, setObsDesc] = useState("");

  const fetchSessions = useCallback(async () => {
    if (!authenticated || !activeMissionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/missions/${activeMissionId}/navigation`);
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Failed to load navigation sessions.");
        return;
      }
      const list = (await res.json()) as NavigationSessionRecord[];
      setSessions(list);
      if (list.length > 0 && !selectedId) {
        setSelectedId(list[0].nav_session_id);
      }
    } catch {
      setError("Network error while loading navigation sessions.");
    } finally {
      setLoading(false);
    }
  }, [authenticated, activeMissionId, selectedId]);

  useEffect(() => {
    if (!authenticated || !activeMissionId) return;
    let active = true;
    apiFetch(`/missions/${activeMissionId}/navigation`)
      .then(async (res) => {
        if (!active || !res.ok) return;
        const list = (await res.json()) as NavigationSessionRecord[];
        if (!active) return;
        setSessions(list);
        if (list.length > 0) {
          setSelectedId((prev) => prev || list[0].nav_session_id);
        }
      })
      .catch(() => null);
    return () => {
      active = false;
    };
  }, [authenticated, activeMissionId]);

  if (!authenticated || !activeMissionId || !activeMission) {
    return (
      <div className="max-w-5xl mx-auto">
        <EmptyState
          icon={Navigation}
          title="Authenticated Mission Required"
          description="Sign in and select an active mission to configure and monitor Marswalk navigation."
          action={
            <Link href="/missions" className="px-3 py-1.5 rounded-[4px] bg-[var(--accent-mars)] text-white text-xs font-semibold">
              Open Missions
            </Link>
          }
        />
      </div>
    );
  }

  const activeNav = sessions.find((s) => s.nav_session_id === selectedId) || sessions[0] || null;
  const landingSite = landingSiteBundle?.landing_site || null;
  const hasRoute = Boolean(activeRoute && activeRoute.vertices && activeRoute.vertices.length >= 2);
  const canLaunch = Boolean(landingSite && hasRoute);

  const missingPrereqs: string[] = [];
  if (!landingSite) missingPrereqs.push("Registered landing/return destination (/landing-site)");
  if (!hasRoute) missingPrereqs.push("Computed terrain-backed route (/planner)");

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!landingSite || !activeRoute) return;
    setBusy(true);
    setError(null);
    setStatusMsg(null);
    try {
      const devVal = deviationThresholdM.trim() ? Number(deviationThresholdM) : null;
      const spdVal = walkingSpeedMps.trim() ? Number(walkingSpeedMps) : null;
      const durVal = maxDurationMin.trim() ? Number(maxDurationMin) * 60.0 : null;
      if (
        (devVal !== null && (!Number.isFinite(devVal) || devVal <= 0)) ||
        (spdVal !== null && (!Number.isFinite(spdVal) || spdVal <= 0)) ||
        (durVal !== null && (!Number.isFinite(durVal) || durVal <= 0))
      ) {
        setError("Numeric configuration parameters must be strictly positive.");
        return;
      }

      const res = await apiFetch(`/missions/${activeMissionId}/navigation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          route_id: activeRoute.route_id,
          route_dataset_id: activeRoute.dataset_id,
          route_crs: activeRoute.crs,
          navigation_mode: navMode,
          return_destination_name: landingSite.name,
          return_destination_lat: landingSite.latitude,
          return_destination_lon: landingSite.longitude_east,
          deviation_threshold_m: devVal,
          route_payload: activeRoute,
          operational_params: {
            walking_speed_mps: spdVal,
            max_duration_s: durVal,
            resource_budgets_configured: Boolean(evaEnvelope),
          },
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Could not create navigation session.");
        return;
      }
      const created = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => [created, ...prev]);
      setSelectedId(created.nav_session_id);
      setStatusMsg(`Navigation session ${created.nav_session_id.slice(0, 8)} initialized (${created.state}).`);
    } finally {
      setBusy(false);
    }
  };

  const handleTransition = async (targetState: NavigationState) => {
    if (!activeNav) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/missions/${activeMissionId}/navigation/${activeNav.nav_session_id}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_state: targetState, reason: transitionReason.trim() || null }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || `Transition to ${targetState} rejected.`);
        return;
      }
      const updated = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => prev.map((s) => (s.nav_session_id === updated.nav_session_id ? updated : s)));
      setTransitionReason("");
      setStatusMsg(`State transitioned to ${updated.state}.`);
    } finally {
      setBusy(false);
    }
  };

  const handleIngestManualPosition = async (e: React.FormEvent) => {
    e.preventDefault();
    const lat = Number(posLat);
    const lon = Number(posLon);
    const acc = posAccM.trim() ? Number(posAccM) : null;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setError("Latitude and longitude must be valid Mars degrees.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await ingestPosition({
        latitude: lat,
        longitude: lon,
        uncertainty_m: acc ?? undefined,
        source_id: "OPERATOR_MANUAL_ENTRY",
        source_classification: "USER_PROVIDED",
      });
      if (!r.ok) {
        setError(r.error || "Position ingest failed.");
        return;
      }
      await fetchSessions();
      setStatusMsg("USER_REPORTED position recorded and navigation progress re-evaluated.");
    } finally {
      setBusy(false);
    }
  };

  const handleEvaluateTurnback = async () => {
    if (!activeNav) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/missions/${activeMissionId}/navigation/${activeNav.nav_session_id}/turnback`, {
        method: "POST",
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Turnback evaluation failed.");
        return;
      }
      const updated = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => prev.map((s) => (s.nav_session_id === updated.nav_session_id ? updated : s)));
    } finally {
      setBusy(false);
    }
  };

  const handleReportObstruction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeNav) return;
    const lat = Number(obsLat);
    const lon = Number(obsLon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || !obsDesc.trim()) {
      setError("Obstruction coordinates and description are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/missions/${activeMissionId}/navigation/${activeNav.nav_session_id}/obstructions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          segment_index: Number(obsSegIdx) || 0,
          latitude: lat,
          longitude: lon,
          location_source: "USER_REPORTED",
          description: obsDesc.trim(),
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Obstruction report failed.");
        return;
      }
      const updated = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => prev.map((s) => (s.nav_session_id === updated.nav_session_id ? updated : s)));
      setObsDesc("");
      setStatusMsg("Obstruction recorded as USER_REPORTED / UNVERIFIED.");
    } finally {
      setBusy(false);
    }
  };

  const handleComputeReplan = async () => {
    if (!activeNav) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/missions/${activeMissionId}/navigation/${activeNav.nav_session_id}/replan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: "safest", reason: "Operator/crew requested candidate replan" }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Candidate replan failed.");
        return;
      }
      const updated = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => prev.map((s) => (s.nav_session_id === updated.nav_session_id ? updated : s)));
      setStatusMsg("Candidate replan computed; awaiting operator approval.");
    } finally {
      setBusy(false);
    }
  };

  const handleReplanDecision = async (decision: "APPROVE" | "REJECT") => {
    if (!activeNav) return;
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/missions/${activeMissionId}/navigation/${activeNav.nav_session_id}/replan/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, reason: `Operator ${decision.toLowerCase()}ed candidate replan` }),
        }
      );
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Replan decision failed.");
        return;
      }
      const updated = (await res.json()) as NavigationSessionRecord;
      setSessions((prev) => prev.map((s) => (s.nav_session_id === updated.nav_session_id ? updated : s)));
      setStatusMsg(`Candidate replan ${decision.toLowerCase()}ed.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Active Marswalk Navigation Workstation"
        badge={activeNav ? activeNav.state : activeMission.name}
        description="Operational turn-by-turn surface guidance backed by computed DEM routes, explicit Mars CRS, live position freshness, obstruction replanning, and independent return assessment."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void fetchSessions()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[4px] bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-xs font-mono"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => setSosDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[4px] bg-[#DC3545] text-white text-xs font-semibold"
            >
              <AlertOctagon className="w-3.5 h-3.5" />
              Emergency SOS
            </button>
          </div>
        }
      />

      {error && (
        <div role="alert" className="ms-panel p-3 border-[#DC3545]/50 text-xs text-[#ff6b7a] font-mono">
          {error}
        </div>
      )}
      {statusMsg && (
        <div role="status" className="ms-panel p-3 border-[#1F9D68]/50 text-xs text-[#4ade80] font-mono">
          {statusMsg}
        </div>
      )}

      {/* Prerequisite & Launch Panel */}
      <div className="ms-panel p-4 space-y-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
            <Route className="w-4 h-4 text-[var(--accent-telemetry)]" />
            <span>Initialize Navigation Session from Computed Route</span>
          </div>
          <StatusIndicator
            label={canLaunch ? "PREREQUISITES MET" : "PREREQUISITES INCOMPLETE"}
            tone={canLaunch ? "success" : "warning"}
          />
        </div>

        {!canLaunch ? (
          <div className="p-3 rounded-[4px] bg-[var(--bg-void)] border border-[#D98A1F]/40 space-y-1.5 text-[var(--text-secondary)]">
            <div className="font-mono text-[#f5b041]">Missing prerequisites (no synthetic defaults will be substituted):</div>
            <ul className="list-disc pl-5 space-y-1">
              {missingPrereqs.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
            <div className="flex gap-3 pt-1">
              <Link href="/landing-site" className="text-[var(--accent-telemetry)] underline">
                Configure Landing Site
              </Link>
              <Link href="/planner" className="text-[var(--accent-telemetry)] underline">
                Compute Route in Planner
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleCreateSession} className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
            <div>
              <label className="block text-[var(--text-secondary)] mb-1">Navigation Mode</label>
              <select
                value={navMode}
                onChange={(e) => setNavMode(e.target.value as typeof navMode)}
                className="w-full ms-input"
              >
                <option value="OPERATOR_SUPERVISED_EVA">OPERATOR_SUPERVISED_EVA</option>
                <option value="MANUAL_WAYPOINT_CHECK">MANUAL_WAYPOINT_CHECK</option>
                <option value="RETURN_TO_BASE">RETURN_TO_BASE</option>
              </select>
            </div>
            <div>
              <label className="block text-[var(--text-secondary)] mb-1">Deviation Threshold (m, optional)</label>
              <input
                type="number"
                step="any"
                value={deviationThresholdM}
                onChange={(e) => setDeviationThresholdM(e.target.value)}
                placeholder="e.g. 25"
                className="w-full ms-input"
              />
            </div>
            <div>
              <label className="block text-[var(--text-secondary)] mb-1">Assumed Speed (m/s, optional)</label>
              <input
                type="number"
                step="any"
                value={walkingSpeedMps}
                onChange={(e) => setWalkingSpeedMps(e.target.value)}
                placeholder="USER_ASSUMED"
                className="w-full ms-input"
              />
            </div>
            <div>
              <label className="block text-[var(--text-secondary)] mb-1">Max Duration (min, optional)</label>
              <input
                type="number"
                step="any"
                value={maxDurationMin}
                onChange={(e) => setMaxDurationMin(e.target.value)}
                placeholder="USER_ASSUMED"
                className="w-full ms-input"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="px-3 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold"
            >
              {busy ? "Creating..." : "Create Nav Session"}
            </button>
          </form>
        )}
      </div>

      {activeNav && (
        <>
          {/* Localization & Progress Banner */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
            <div className="ms-panel p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)] font-mono">LOCALIZATION STATE</span>
                <StatusIndicator
                  label={activeNav.progress.localization_freshness}
                  tone={activeNav.progress.localization_freshness === "FRESH" ? "success" : "warning"}
                />
              </div>
              <div className="font-mono font-bold text-sm text-[var(--text-primary)]">
                {activeNav.progress.localization_banner}
              </div>
              <div className="text-[var(--text-secondary)] font-mono">
                {activeNav.progress.position_timestamp_utc
                  ? `Last packet: ${activeNav.progress.position_timestamp_utc} (${activeNav.progress.position_source || "unknown"})`
                  : "No Mars position packet received (browser GPS is never used)."}
              </div>
            </div>

            <div className="ms-panel p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)] font-mono">ROUTE PROGRESS</span>
                <StatusIndicator
                  label={activeNav.progress.progress_status}
                  tone={activeNav.progress.progress_status === "AVAILABLE" ? "telemetry" : "warning"}
                />
              </div>
              {activeNav.progress.progress_status === "AVAILABLE" ? (
                <div className="space-y-1 font-mono">
                  <div className="text-lg font-bold text-[var(--text-primary)]">
                    {((activeNav.progress.completed_fraction || 0) * 100).toFixed(1)}% ·{" "}
                    {activeNav.progress.remaining_route_distance_m?.toFixed(1)} m remaining
                  </div>
                  <div className="text-[var(--text-secondary)]">
                    Next waypoint: {activeNav.progress.distance_to_next_waypoint_m?.toFixed(1)} m · Deviation:{" "}
                    {activeNav.progress.deviation_state}
                  </div>
                </div>
              ) : (
                <div className="text-[#f5b041] font-mono">
                  PROGRESS UNAVAILABLE — {activeNav.progress.deviation_limitation}
                </div>
              )}
            </div>

            <div className="ms-panel p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)] font-mono">STATE MACHINE</span>
                <StatusIndicator label={activeNav.state} tone={activeNav.state === "EMERGENCY" ? "danger" : "telemetry"} />
              </div>
              <input
                type="text"
                value={transitionReason}
                onChange={(e) => setTransitionReason(e.target.value)}
                placeholder="Transition / audit reason..."
                className="w-full ms-input"
              />
              <div className="flex flex-wrap gap-1.5">
                {activeNav.allowed_transitions.map((nextSt) => (
                  <button
                    key={nextSt}
                    type="button"
                    disabled={busy}
                    onClick={() => void handleTransition(nextSt)}
                    className="px-2 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] hover:border-[var(--accent-telemetry)] font-mono text-[10px]"
                  >
                    → {nextSt}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 3D Terrain Viewport + Manual Position / Return Turnback */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 ms-panel overflow-hidden h-[380px] relative">
              {selectedDemDatasetId ? (
                <LocalTerrain3DViewer />
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-[var(--text-secondary)] font-mono">
                  Select a processed DEM in Route Planner to render synchronized 3D terrain.
                </div>
              )}
            </div>

            <div className="space-y-4 text-xs">
              {/* Operator-Entered Position (USER_REPORTED) */}
              <form onSubmit={handleIngestManualPosition} className="ms-panel p-4 space-y-2.5">
                <div className="flex items-center justify-between font-semibold text-[var(--text-primary)]">
                  <span className="flex items-center gap-1.5">
                    <MapPin className="w-4 h-4 text-[var(--accent-telemetry)]" />
                    Operator Position Input
                  </span>
                  <span className="font-mono text-[10px] text-[#f5b041]">USER_REPORTED</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="number"
                    step="any"
                    value={posLat}
                    onChange={(e) => setPosLat(e.target.value)}
                    placeholder="Mars Lat (°)"
                    className="ms-input"
                  />
                  <input
                    type="number"
                    step="any"
                    value={posLon}
                    onChange={(e) => setPosLon(e.target.value)}
                    placeholder="Mars Lon (°E)"
                    className="ms-input"
                  />
                </div>
                <input
                  type="number"
                  step="any"
                  value={posAccM}
                  onChange={(e) => setPosAccM(e.target.value)}
                  placeholder="Provider accuracy_m (optional)"
                  className="w-full ms-input"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full py-1.5 rounded-[4px] bg-[var(--accent-telemetry)]/20 border border-[var(--accent-telemetry)]/50 text-[var(--accent-telemetry)] font-semibold"
                >
                  Record USER_REPORTED Position
                </button>
              </form>

              {/* Independent Return & Turnback */}
              <div className="ms-panel p-4 space-y-2.5">
                <div className="flex items-center justify-between font-semibold text-[var(--text-primary)]">
                  <span className="flex items-center gap-1.5">
                    <RotateCcw className="w-4 h-4 text-[var(--accent-mars)]" />
                    Independent Return & Turnback
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleEvaluateTurnback()}
                    className="px-2 py-1 rounded-[4px] bg-[var(--accent-mars)] text-white text-[10px] font-semibold"
                  >
                    Evaluate
                  </button>
                </div>
                {activeNav.turnback ? (
                  <div className="space-y-1.5 font-mono">
                    <StatusIndicator
                      label={activeNav.turnback.state}
                      tone={
                        activeNav.turnback.state === "WITHIN_CONFIGURED_PLANNING_CONSTRAINTS"
                          ? "telemetry"
                          : "warning"
                      }
                    />
                    <p className="text-[var(--text-secondary)] font-sans">{activeNav.turnback.decision_support_note}</p>
                    {activeNav.turnback.return_distance_m !== null && activeNav.turnback.return_distance_m !== undefined && (
                      <div className="text-[var(--text-primary)]">
                        Return distance: {activeNav.turnback.return_distance_m.toFixed(1)} m
                      </div>
                    )}
                    {activeNav.turnback.missing_inputs.length > 0 && (
                      <div className="text-[#f5b041]">
                        Missing: {activeNav.turnback.missing_inputs.join(", ")}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-[var(--text-secondary)]">
                    Evaluates an independent terrain-backed return leg to {activeNav.return_destination_name}.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Obstruction Report & Candidate Replan */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
            <form onSubmit={handleReportObstruction} className="ms-panel p-4 space-y-2.5">
              <div className="font-semibold text-[var(--text-primary)] flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[#f5b041]" />
                <span>Report Field Obstruction (USER_REPORTED / UNVERIFIED)</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="number"
                  value={obsSegIdx}
                  onChange={(e) => setObsSegIdx(e.target.value)}
                  placeholder="Seg #"
                  className="ms-input"
                />
                <input
                  type="number"
                  step="any"
                  value={obsLat}
                  onChange={(e) => setObsLat(e.target.value)}
                  placeholder="Lat (°)"
                  className="ms-input"
                />
                <input
                  type="number"
                  step="any"
                  value={obsLon}
                  onChange={(e) => setObsLon(e.target.value)}
                  placeholder="Lon (°E)"
                  className="ms-input"
                />
              </div>
              <textarea
                rows={2}
                value={obsDesc}
                onChange={(e) => setObsDesc(e.target.value)}
                placeholder="Describe observed obstruction or hazard..."
                className="w-full ms-input"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={busy}
                  className="px-3 py-1.5 rounded-[4px] bg-[#D98A1F] text-white font-semibold"
                >
                  Report Obstruction
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void handleComputeReplan()}
                  className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] text-[var(--text-primary)] font-semibold"
                >
                  Compute Candidate Replan
                </button>
              </div>
            </form>

            <div className="ms-panel p-4 space-y-2.5">
              <div className="font-semibold text-[var(--text-primary)] flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-[var(--accent-telemetry)]" />
                <span>Candidate Replan Approval Gate</span>
              </div>
              {activeNav.candidate_replan ? (
                <div className="space-y-2 font-mono">
                  <div className="text-[#f5b041]">
                    Candidate route awaiting operator approval (never auto-activated).
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleReplanDecision("APPROVE")}
                      className="px-3 py-1.5 rounded-[4px] bg-[#1F9D68] text-white font-semibold"
                    >
                      Approve Candidate Route
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void handleReplanDecision("REJECT")}
                      className="px-3 py-1.5 rounded-[4px] bg-[#DC3545] text-white font-semibold"
                    >
                      Reject (Keep Current)
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-[var(--text-secondary)]">
                  No pending candidate replan. Obstructions recorded: {activeNav.obstructions.length}.
                </div>
              )}
            </div>
          </div>

          {/* Turn-by-Turn Instructions & Segment Provenance */}
          <div className="ms-panel p-4 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
                <Compass className="w-4 h-4 text-[var(--accent-telemetry)]" />
                <span>Turn-by-Turn Instructions & Segment Evidence ({activeNav.route_crs})</span>
              </div>
              <span className="font-mono text-[var(--text-secondary)]">
                Heading Sensor: UNAVAILABLE · Source DEM: {activeNav.route_dataset_id}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse font-mono text-[11px]">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    <th className="py-2 pr-3">#</th>
                    <th className="py-2 pr-3">Instruction</th>
                    <th className="py-2 pr-3">True-N / Grid-N</th>
                    <th className="py-2 pr-3">Dist (m)</th>
                    <th className="py-2 pr-3">Slope / ΔElev</th>
                    <th className="py-2 pr-3">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {activeNav.instructions.map((inst, i) => {
                    const seg = activeNav.segments[i];
                    return (
                      <tr key={inst.segment_id} className="border-b border-[var(--border-subtle)]/50">
                        <td className="py-2 pr-3">{inst.step_index}</td>
                        <td className="py-2 pr-3 font-sans text-[var(--text-primary)]">
                          <div>{inst.instruction_text}</div>
                          {seg && <div className="text-[10px] text-[var(--text-muted)]">{seg.limitation_note}</div>}
                        </td>
                        <td className="py-2 pr-3">
                          {inst.true_north_bearing_deg.toFixed(1)}° /{" "}
                          {inst.grid_north_bearing_deg !== null && inst.grid_north_bearing_deg !== undefined
                            ? `${inst.grid_north_bearing_deg.toFixed(1)}°`
                            : "N/A"}
                        </td>
                        <td className="py-2 pr-3">{inst.distance_m.toFixed(1)}</td>
                        <td className="py-2 pr-3">
                          {inst.slope_deg !== null && inst.slope_deg !== undefined ? `${inst.slope_deg.toFixed(1)}°` : "N/A"} /{" "}
                          {inst.elevation_change_m !== null && inst.elevation_change_m !== undefined
                            ? `${inst.elevation_change_m.toFixed(1)} m`
                            : "N/A"}
                        </td>
                        <td className="py-2 pr-3">
                          <StatusIndicator
                            label={inst.support_state}
                            tone={inst.support_state === "SUPPORTED" ? "success" : "warning"}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
