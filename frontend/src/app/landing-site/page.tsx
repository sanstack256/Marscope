"use client";

import React, { useState } from "react";
import { CheckCircle2, Compass, Flag, Search, ShieldAlert } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { LocalTerrain3DViewer } from "../../components/LocalTerrain3DViewer";
import { GazetteerSiteRecord } from "../../types";

export default function LandingSitePage() {
  const {
    authenticated,
    activeMissionId,
    activeMission,
    landingSiteBundle,
    refreshMissionWorkspace,
  } = useAuthMissionStore();
  const setSelectedDemDatasetId = useRoutingStore((s) => s.setSelectedDemDatasetId);
  const fetchMeshManifest = useRoutingStore((s) => s.fetchMeshManifest);
  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const [gazQuery, setGazQuery] = useState("");
  const [gazResults, setGazResults] = useState<GazetteerSiteRecord[]>([]);
  const [siteName, setSiteName] = useState("");
  const [latStr, setLatStr] = useState("");
  const [lonStr, setLonStr] = useState("");
  const [sourceType, setSourceType] = useState<"USER_PROVIDED" | "DATASET_CATALOG_MATCH" | "GAZETTEER_CATALOG">(
    "USER_PROVIDED"
  );
  const [sourceRecordId, setSourceRecordId] = useState("");

  // Explicit constraint inputs (never hidden or silently invented)
  const [maxSlopeDeg, setMaxSlopeDeg] = useState("");
  const [maxRoughnessM, setMaxRoughnessM] = useState("");
  const [maxRadiusM, setMaxRadiusM] = useState("");

  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  if (!authenticated || !activeMissionId || !activeMission) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={Flag}
          title="Mission Workspace Required"
          description="Sign in and select a mission to register landing-site coordinates and compute DEM-backed 3D perimeters."
        />
      </div>
    );
  }

  const canModify = ["MISSION_LEAD", "MISSION_OPERATOR"].includes(activeMission.my_role);
  const site = landingSiteBundle?.landing_site;
  const perimeter = landingSiteBundle?.perimeter;

  const handleGazetteerSearch = async () => {
    setErrMsg(null);
    const res = await apiFetch(`/missions/gazetteer/search?q=${encodeURIComponent(gazQuery.trim())}`);
    if (res.ok) {
      setGazResults(await res.json());
    }
  };

  const applyGazRecord = (rec: GazetteerSiteRecord) => {
    setSiteName(rec.name);
    setLatStr(String(rec.latitude));
    setLonStr(String(rec.longitude_east));
    setSourceType("DATASET_CATALOG_MATCH");
    setSourceRecordId(rec.record_id);
  };

  const handleRegisterSite = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrMsg(null);
    setStatusMsg(null);
    try {
      const lat = Number(latStr);
      const lon = Number(lonStr);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        setErrMsg("Valid Mars latitude and east longitude are required.");
        return;
      }
      const res = await apiFetch(`/missions/${activeMissionId}/landing-site`, {
        method: "PUT",
        body: JSON.stringify({
          name: siteName.trim(),
          latitude: lat,
          longitude: lon,
          crs: "IAU2000:49900",
          source: sourceType,
          source_record_id: sourceRecordId.trim() || undefined,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErrMsg(body.detail || "Failed to register landing site.");
        return;
      }
      await refreshMissionWorkspace(activeMissionId);
      setFocusCoordinate({ lat, lon, label: siteName.trim() });
      const covDataset = body?.landing_site?.terrain_dataset_id;
      if (covDataset) {
        setSelectedDemDatasetId(covDataset);
        void fetchMeshManifest(covDataset);
      }
      setStatusMsg("Landing site registered against IAU2000:49900 and sampled against validated DEM coverage.");
    } finally {
      setBusy(false);
    }
  };

  const handleComputePerimeter = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrMsg(null);
    setStatusMsg(null);
    try {
      const payload: Record<string, number> = {};
      if (maxSlopeDeg.trim()) payload.max_slope_deg = Number(maxSlopeDeg);
      if (maxRoughnessM.trim()) payload.max_roughness_m = Number(maxRoughnessM);
      if (maxRadiusM.trim()) payload.max_radius_m = Number(maxRadiusM);

      const res = await apiFetch(`/missions/${activeMissionId}/landing-site/perimeter`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErrMsg(body.detail || "Perimeter computation failed.");
        return;
      }
      await refreshMissionWorkspace(activeMissionId);
      setStatusMsg(`Perimeter status: ${body?.perimeter?.status || "evaluated"}`);
    } finally {
      setBusy(false);
    }
  };

  const handleApprovePerimeter = async () => {
    if (!perimeter) return;
    const res = await apiFetch(
      `/missions/${activeMissionId}/landing-site/perimeter/${perimeter.perimeter_id}/approve`,
      { method: "POST" }
    );
    if (res.ok) {
      await refreshMissionWorkspace(activeMissionId);
      setStatusMsg("Operator planning boundary approval recorded.");
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Landing-Site Intelligence & 3D Perimeter"
        badge={landingSiteBundle?.landing_site_status || "LANDING_SITE_UNCONFIGURED"}
        description="Explicit landing-site registration backed by real catalog coverage and algorithmic DEM-grid BFS traversal boundaries (never arbitrary circular fallbacks)."
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

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        {/* Left Control Column */}
        <div className="xl:col-span-5 space-y-4">
          {/* Catalog-Backed Gazetteer Search */}
          <div className="ms-panel p-4 space-y-3 text-xs">
            <div className="font-semibold text-sm flex items-center gap-2 text-[var(--text-primary)]">
              <Search className="w-4 h-4 text-[var(--accent-telemetry)]" />
              <span>Catalog-Backed Mars Site Lookup</span>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={gazQuery}
                onChange={(e) => setGazQuery(e.target.value)}
                placeholder="Search processed DEM & catalog regions (e.g. Gale, MOLA)..."
                className="flex-1 ms-input text-xs"
              />
              <button
                type="button"
                onClick={() => void handleGazetteerSearch()}
                className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)]"
              >
                Search
              </button>
            </div>
            {gazResults.length > 0 && (
              <div className="max-h-40 overflow-y-auto divide-y divide-[var(--border-subtle)] border border-[var(--border-subtle)] rounded-[4px]">
                {gazResults.map((rec) => (
                  <button
                    key={rec.record_id}
                    type="button"
                    onClick={() => applyGazRecord(rec)}
                    className="w-full p-2 text-left hover:bg-white/5 flex items-center justify-between gap-2"
                  >
                    <div>
                      <div className="font-medium text-[var(--text-primary)]">{rec.name}</div>
                      <div className="font-mono text-[10px] text-[var(--text-muted)]">
                        {rec.latitude.toFixed(4)}, {rec.longitude_east.toFixed(4)} E · {rec.dataset_id}
                      </div>
                    </div>
                    <span className="font-mono text-[10px] text-[var(--accent-telemetry)]">Select</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Landing Site Registration Form */}
          <form onSubmit={handleRegisterSite} className="ms-panel p-4 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Flag className="w-4 h-4 text-[var(--accent-mars)]" />
                <span>Register Mission Landing Site</span>
              </h2>
              {!canModify && <StatusIndicator label="READ ONLY" tone="unknown" />}
            </div>

            <input
              type="text"
              required
              disabled={!canModify}
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
              placeholder="Site label (e.g. Boxwork Landing Pad Alpha)"
              className="w-full ms-input"
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                required
                disabled={!canModify}
                value={latStr}
                onChange={(e) => setLatStr(e.target.value)}
                placeholder="Latitude (-90..90)"
                className="ms-input font-mono"
              />
              <input
                type="text"
                required
                disabled={!canModify}
                value={lonStr}
                onChange={(e) => setLonStr(e.target.value)}
                placeholder="East Lon (0..360)"
                className="ms-input font-mono"
              />
            </div>

            {site && (
              <div className="p-2.5 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] space-y-1 font-mono text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--text-primary)] font-semibold">{site.name}</span>
                  <StatusIndicator
                    label={site.dem_coverage_state}
                    tone={site.dem_coverage_state === "COVERED_DEM" ? "success" : "warning"}
                  />
                </div>
                <div className="text-[var(--text-secondary)]">
                  {site.latitude.toFixed(5)}, {site.longitude_east.toFixed(5)} E · Elev:{" "}
                  {site.elevation_m != null ? `${site.elevation_m.toFixed(1)} m` : "Outside DEM"} · Dataset:{" "}
                  {site.terrain_dataset_id || "None"}
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={!canModify || busy}
              className="w-full py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold disabled:opacity-45"
            >
              {busy ? "Saving..." : "Save Registered Landing Site"}
            </button>
          </form>

          {/* Algorithmic 3D Perimeter Computation */}
          <form onSubmit={handleComputePerimeter} className="ms-panel p-4 space-y-3 text-xs">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <Compass className="w-4 h-4 text-[var(--accent-telemetry)]" />
              <span>Algorithmic DEM Perimeter Evaluation</span>
            </h2>
            <p className="text-[11px] text-[var(--text-muted)]">
              All three engineering constraints must be explicitly supplied. No hidden radius or fake safety buffer is generated.
            </p>
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.5"
                disabled={!canModify}
                value={maxSlopeDeg}
                onChange={(e) => setMaxSlopeDeg(e.target.value)}
                placeholder="Max slope (deg)"
                className="ms-input font-mono text-xs"
              />
              <input
                type="number"
                step="0.1"
                disabled={!canModify}
                value={maxRoughnessM}
                onChange={(e) => setMaxRoughnessM(e.target.value)}
                placeholder="Max TRI (m)"
                className="ms-input font-mono text-xs"
              />
              <input
                type="number"
                step="10"
                disabled={!canModify}
                value={maxRadiusM}
                onChange={(e) => setMaxRadiusM(e.target.value)}
                placeholder="Max radius (m)"
                className="ms-input font-mono text-xs"
              />
            </div>

            <button
              type="submit"
              disabled={!canModify || !site || busy}
              className="w-full py-2 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold disabled:opacity-45"
            >
              Compute 3D DEM Perimeter
            </button>

            {perimeter && (
              <div className="p-3 rounded-[6px] bg-[var(--bg-void)] border border-[var(--border-strong)] space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <StatusIndicator
                    label={perimeter.status}
                    tone={perimeter.status === "EVALUATED_WITH_VALIDATED_DEM" ? "success" : "warning"}
                  />
                  {perimeter.coverage_fraction != null && (
                    <span className="font-mono text-[11px] text-[var(--text-secondary)]">
                      DEM Valid Coverage: {Math.round(perimeter.coverage_fraction * 100)}%
                    </span>
                  )}
                </div>
                <div className="flex items-start gap-1.5 text-[11px] font-mono text-[#f5b041]">
                  <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>{perimeter.classification_label}</span>
                </div>
                <ul className="space-y-0.5 text-[10px] font-mono text-[var(--text-muted)]">
                  {perimeter.limitations.map((lim, idx) => (
                    <li key={idx}>• {lim}</li>
                  ))}
                </ul>
                {canModify &&
                  perimeter.status === "EVALUATED_WITH_VALIDATED_DEM" &&
                  !perimeter.operator_approved && (
                    <button
                      type="button"
                      onClick={() => void handleApprovePerimeter()}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[4px] bg-[#1F9D68] text-white font-semibold"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Approve Evaluated Planning Boundary</span>
                    </button>
                  )}
                {perimeter.operator_approved && (
                  <div className="text-[11px] font-mono text-[#4ade80]">
                    Approved at {perimeter.approved_at_utc ? new Date(perimeter.approved_at_utc).toLocaleString() : ""}
                  </div>
                )}
              </div>
            )}
          </form>
        </div>

        {/* Right Live 3D Terrain Perimeter Viewport */}
        <div className="xl:col-span-7 ms-panel overflow-hidden min-h-[600px] flex flex-col">
          <div className="px-4 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)]/60 flex items-center justify-between text-xs font-mono">
            <span>3D DEM LANDING-SITE PERIMETER VIEWPORT</span>
            <span className="text-[var(--text-muted)]">
              {site ? `${site.name} (${site.terrain_dataset_id || "No DEM"})` : "LANDING_SITE_UNCONFIGURED"}
            </span>
          </div>
          <div className="flex-1 min-h-[540px]">
            <LocalTerrain3DViewer />
          </div>
        </div>
      </div>
    </div>
  );
}
