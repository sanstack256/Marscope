"use client";

import React, { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Compass,
  Flag,
  Globe2,
  Loader2,
  Mountain,
  Search,
  ShieldAlert,
} from "lucide-react";
import { apiFetch } from "../../lib/constants";
import {
  deriveLandingSiteWorkflowState,
  isSiteEligibleForLocalDemView,
  validateMarsCoordinateInputs,
} from "../../lib/landingSiteWorkflow";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { LocalTerrain3DViewer } from "../../components/LocalTerrain3DViewer";
import { MarsGlobeViewer } from "../../components/MarsGlobeViewer";
import type { GazetteerSiteRecord, LandingSiteCoverageDiscovery } from "../../types";

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
  const meshManifest = useRoutingStore((s) => s.meshManifest);
  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const site = landingSiteBundle?.landing_site ?? null;
  const perimeter = landingSiteBundle?.perimeter ?? null;

  const [viewMode, setViewMode] = useState<"global" | "local">("global");
  const [gazQuery, setGazQuery] = useState("");
  const [gazResults, setGazResults] = useState<GazetteerSiteRecord[]>([]);
  const [siteNameDraft, setSiteNameDraft] = useState<string | null>(null);
  const [latDraft, setLatDraft] = useState<string | null>(null);
  const [lonDraft, setLonDraft] = useState<string | null>(null);
  const siteName = siteNameDraft ?? site?.name ?? "";
  const latStr = latDraft ?? (site ? String(site.latitude) : "");
  const lonStr = lonDraft ?? (site ? String(site.longitude_east) : "");
  const setSiteName = (val: string) => setSiteNameDraft(val);
  const setLatStr = (val: string) => setLatDraft(val);
  const setLonStr = (val: string) => setLonDraft(val);
  const [sourceType, setSourceType] = useState<
    "USER_PROVIDED" | "DATASET_CATALOG_MATCH" | "GAZETTEER_CATALOG"
  >("USER_PROVIDED");
  const [sourceRecordId, setSourceRecordId] = useState("");

  // Explicit constraint inputs (never hidden or silently invented)
  const [maxSlopeDeg, setMaxSlopeDeg] = useState("");
  const [maxRoughnessM, setMaxRoughnessM] = useState("");
  const [maxRadiusM, setMaxRadiusM] = useState("");

  const [discovery, setDiscovery] = useState<LandingSiteCoverageDiscovery | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isEvaluatingPerimeter, setIsEvaluatingPerimeter] = useState(false);
  const [terrainReady, setTerrainReady] = useState(false);
  const [terrainLoadError, setTerrainLoadError] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const runCoverageDiscovery = useCallback(
    async (lat: number, lonEast: number): Promise<LandingSiteCoverageDiscovery | null> => {
      setIsValidating(true);
      setErrMsg(null);
      try {
        const res = await apiFetch(
          `/missions/landing-site/discover-coverage?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lonEast)}`
        );
        const body = await res.json().catch(() => null);
        if (!res.ok || !body) {
          setErrMsg(body?.detail || "Failed to query catalog DEM coverage.");
          setDiscovery(null);
          return null;
        }
        const disc = body as LandingSiteCoverageDiscovery;
        setDiscovery(disc);
        return disc;
      } catch (err) {
        setErrMsg(err instanceof Error ? err.message : "Network error while checking DEM coverage.");
        setDiscovery(null);
        return null;
      } finally {
        setIsValidating(false);
      }
    },
    []
  );

  const handleGlobeCoordinateSelect = useCallback(
    (lat: number, lonEast: number) => {
      setLatStr(lat.toFixed(6));
      setLonStr(lonEast.toFixed(6));
      setSourceType("USER_PROVIDED");
      setSourceRecordId("");
      setStatusMsg(null);
      void runCoverageDiscovery(lat, lonEast);
    },
    [runCoverageDiscovery]
  );

  const handleTerrainReadyChange = useCallback((ready: boolean, error: string | null) => {
    setTerrainReady(ready);
    setTerrainLoadError(error);
  }, []);

  const parsedCoordCheck = useMemo(() => {
    if (!latStr.trim() && !lonStr.trim()) return null;
    return validateMarsCoordinateInputs(latStr, lonStr);
  }, [latStr, lonStr]);

  const constraintsComplete = Boolean(
    maxSlopeDeg.trim() && maxRoughnessM.trim() && maxRadiusM.trim()
  );

  const workflowState = deriveLandingSiteWorkflowState({
    viewMode,
    hasEnteredCoordinates: Boolean(latStr.trim() && lonStr.trim()),
    isValidating,
    isLoadingTerrain: viewMode === "local" && !terrainReady && !terrainLoadError,
    terrainLoadError,
    terrainReady,
    isEvaluatingPerimeter,
    evaluationError: null,
    discovery,
    bundle: landingSiteBundle ?? null,
    constraintsComplete,
  });

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

  const handleGazetteerSearch = async () => {
    setErrMsg(null);
    const res = await apiFetch(
      `/missions/gazetteer/search?q=${encodeURIComponent(gazQuery.trim())}`
    );
    if (res.ok) {
      setGazResults(await res.json());
    } else {
      setErrMsg("Gazetteer catalog search failed.");
    }
  };

  const applyGazRecord = (rec: GazetteerSiteRecord) => {
    setSiteName(rec.name);
    setLatStr(String(rec.latitude));
    setLonStr(String(rec.longitude_east));
    setSourceType("DATASET_CATALOG_MATCH");
    setSourceRecordId(rec.record_id);
    setStatusMsg(null);
    void runCoverageDiscovery(rec.latitude, rec.longitude_east);
  };

  const handleValidateCoordinates = async () => {
    setStatusMsg(null);
    const check = validateMarsCoordinateInputs(latStr, lonStr);
    if (!check.valid || check.latitude == null || check.longitudeEast == null) {
      setErrMsg(check.error || "Invalid coordinates.");
      return;
    }
    const disc = await runCoverageDiscovery(check.latitude, check.longitudeEast);
    if (disc && !disc.covered) {
      setViewMode("global");
      setErrMsg(disc.unavailable_reason || "Coordinates lie outside all available DEM coverage.");
    }
  };

  const transitionToLocalDem = (
    datasetId: string,
    lat: number,
    lonEast: number,
    label: string
  ) => {
    setTerrainReady(false);
    setTerrainLoadError(null);
    setFocusCoordinate({ lat, lon: lonEast, label });
    setSelectedDemDatasetId(datasetId);
    void fetchMeshManifest(datasetId);
    setViewMode("local");
  };

  const handleRegisterSite = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrMsg(null);
    setStatusMsg(null);

    const check = validateMarsCoordinateInputs(latStr, lonStr);
    if (!check.valid || check.latitude == null || check.longitudeEast == null) {
      setErrMsg(check.error || "Valid Mars latitude (-90..90) and east longitude (0..360) are required.");
      return;
    }
    if (!siteName.trim()) {
      setErrMsg("Landing-site name is required.");
      return;
    }

    setIsRegistering(true);
    try {
      const disc = await runCoverageDiscovery(check.latitude, check.longitudeEast);
      const res = await apiFetch(`/missions/${activeMissionId}/landing-site`, {
        method: "PUT",
        body: JSON.stringify({
          name: siteName.trim(),
          latitude: check.latitude,
          longitude: check.longitudeEast,
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

      const savedSite = body?.landing_site;
      const covDataset: string | undefined =
        savedSite?.terrain_dataset_id || disc?.selected_dataset?.dataset_id;
      const isCovered = savedSite?.dem_coverage_state === "COVERED_DEM" && Boolean(covDataset);

      if (isCovered && covDataset) {
        transitionToLocalDem(covDataset, check.latitude, check.longitudeEast, siteName.trim());
        setStatusMsg(
          `Registered "${siteName.trim()}" against ${covDataset}. Local 3D DEM loaded — supply explicit engineering constraints below to evaluate the perimeter.`
        );
      } else {
        setViewMode("global");
        setErrMsg(
          savedSite?.nodata_reason ||
            disc?.unavailable_reason ||
            "Coordinates registered, but no valid DEM sample covers this location. Remaining in global Mars globe view; perimeter evaluation is unavailable."
        );
      }
    } finally {
      setIsRegistering(false);
    }
  };

  const handleComputePerimeter = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrMsg(null);
    setStatusMsg(null);
    setIsEvaluatingPerimeter(true);
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
      const pStatus = body?.perimeter?.status;
      if (pStatus === "EVALUATED_WITH_VALIDATED_DEM") {
        setStatusMsg(
          "Algorithmic DEM-grid BFS perimeter evaluated. Review the boundary, excluded zones, and scientific limitations."
        );
      } else {
        setErrMsg(
          body?.perimeter?.limitations?.[0] ||
            `Perimeter evaluation returned ${pStatus || "INDETERMINATE"}.`
        );
      }
    } finally {
      setIsEvaluatingPerimeter(false);
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
    } else {
      setErrMsg("Failed to record operator boundary approval.");
    }
  };

  const pendingMarker =
    parsedCoordCheck?.valid &&
    parsedCoordCheck.latitude != null &&
    parsedCoordCheck.longitudeEast != null
      ? {
          lat: parsedCoordCheck.latitude,
          lonEast: parsedCoordCheck.longitudeEast,
          label: siteName.trim() || "Selected Coordinate",
        }
      : site
      ? { lat: site.latitude, lonEast: site.longitude_east, label: site.name }
      : null;

  const canEnterLocalView = isSiteEligibleForLocalDemView(discovery, site);
  const activeDatasetId = site?.terrain_dataset_id || discovery?.selected_dataset?.dataset_id || null;
  const prov = (perimeter?.provenance || {}) as Record<string, unknown>;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="Landing-Site Intelligence & 3D Perimeter"
        badge={workflowState}
        description="Interactive global-to-local Mars landing-site registration backed by dynamic catalog DEM discovery and algorithmic DEM-grid BFS perimeter evaluation."
      />

      {errMsg && (
        <div
          role="alert"
          className="p-3 rounded-[6px] border border-[#DC3545]/45 bg-[#DC3545]/10 text-xs text-[#ff6b7a] flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{errMsg}</span>
        </div>
      )}
      {statusMsg && (
        <div className="p-3 rounded-[6px] border border-[#1F9D68]/45 bg-[#1F9D68]/10 text-xs text-[#4ade80] flex items-start gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{statusMsg}</span>
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
                placeholder="Search verified DEM & catalog regions (e.g. Gale, MOLA)..."
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

          {/* Coordinate Entry, Dynamic Discovery & Registration */}
          <form onSubmit={handleRegisterSite} className="ms-panel p-4 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Flag className="w-4 h-4 text-[var(--accent-mars)]" />
                <span>Landing-Site Coordinates &amp; DEM Discovery</span>
              </h2>
              {!canModify && <StatusIndicator label="READ ONLY" tone="unknown" />}
            </div>

            <p className="text-[11px] text-[var(--text-muted)]">
              Click directly on the Mars globe or enter IAU2000:49900 coordinates (Lat -90..90, East Lon 0..360).
            </p>

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

            <div className="flex gap-2">
              <button
                type="button"
                disabled={isValidating || !latStr.trim() || !lonStr.trim()}
                onClick={() => void handleValidateCoordinates()}
                className="flex-1 py-1.5 px-3 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)] text-[var(--text-primary)] font-medium disabled:opacity-45"
              >
                {isValidating ? "Checking Catalog..." : "Validate & Discover DEM"}
              </button>
              {canEnterLocalView && activeDatasetId && pendingMarker && viewMode === "global" && (
                <button
                  type="button"
                  onClick={() =>
                    transitionToLocalDem(
                      activeDatasetId,
                      pendingMarker.lat,
                      pendingMarker.lonEast,
                      pendingMarker.label
                    )
                  }
                  className="py-1.5 px-3 rounded-[4px] bg-[var(--accent-telemetry)]/20 border border-[var(--accent-telemetry)]/50 text-[var(--accent-telemetry)] font-medium inline-flex items-center gap-1"
                >
                  <Mountain className="w-3.5 h-3.5" />
                  <span>Open 3D DEM</span>
                </button>
              )}
            </div>

            {/* Dynamic Coverage Discovery Readout */}
            {discovery && (
              <div className="p-2.5 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[var(--text-secondary)]">
                    {discovery.latitude.toFixed(5)}, {discovery.longitude_east.toFixed(5)} E ({discovery.crs})
                  </span>
                  <StatusIndicator
                    label={
                      !discovery.covered
                        ? "OUTSIDE_DEM_COVERAGE"
                        : discovery.selected_dataset?.local_slope_suitable
                        ? "LOCAL_DEM_SUITABLE"
                        : "REGIONAL_DEM_ONLY"
                    }
                    tone={
                      !discovery.covered
                        ? "warning"
                        : discovery.selected_dataset?.local_slope_suitable
                        ? "success"
                        : "warning"
                    }
                  />
                </div>
                {discovery.selected_dataset ? (
                  <>
                    <div className="text-[var(--text-primary)] font-medium">
                      {discovery.selected_dataset.dataset_id} (
                      {discovery.selected_dataset.native_resolution_m != null
                        ? `${discovery.selected_dataset.native_resolution_m.toFixed(2)} m/px`
                        : "unknown res"}
                      )
                    </div>
                    <div className="text-[var(--text-muted)]">
                      {discovery.selected_dataset.selection_reason}
                    </div>
                    <div className="font-mono text-[10px] text-[var(--text-muted)]">
                      Elevation:{" "}
                      {discovery.elevation_m != null
                        ? `${discovery.elevation_m.toFixed(2)} m`
                        : discovery.sample_is_nodata
                        ? "No-data at exact coordinate"
                        : "Unavailable"}{" "}
                      · Datum: {discovery.selected_dataset.vertical_datum || "MOLA Areoid"}
                    </div>
                    {discovery.covering_datasets.length > 1 && (
                      <div className="text-[10px] text-[var(--text-muted)]">
                        Other covering DEMs:{" "}
                        {discovery.covering_datasets
                          .slice(1)
                          .map(
                            (d) =>
                              `${d.dataset_id} (${
                                d.native_resolution_m != null ? `${d.native_resolution_m.toFixed(1)} m/px` : "?"
                              })`
                          )
                          .join(", ")}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-[#f5b041]">{discovery.unavailable_reason}</div>
                )}
              </div>
            )}

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
                  {site.elevation_m != null ? `${site.elevation_m.toFixed(1)} m` : "Unavailable / Outside DEM"} · Dataset:{" "}
                  {site.terrain_dataset_id || "None"}
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={!canModify || isRegistering || isValidating}
              className="w-full py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold disabled:opacity-45 inline-flex items-center justify-center gap-2"
            >
              {isRegistering && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{isRegistering ? "Registering..." : "Save Registered Landing Site"}</span>
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
              disabled={!canModify || !site || isEvaluatingPerimeter || site.dem_coverage_state !== "COVERED_DEM"}
              className="w-full py-2 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] font-semibold disabled:opacity-45 inline-flex items-center justify-center gap-2"
            >
              {isEvaluatingPerimeter && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{isEvaluatingPerimeter ? "Evaluating DEM Grid..." : "Compute 3D DEM Perimeter"}</span>
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
                      Known DEM Coverage: {Math.round(perimeter.coverage_fraction * 100)}%
                    </span>
                  )}
                </div>

                {perimeter.status === "EVALUATED_WITH_VALIDATED_DEM" && (
                  <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px] text-[var(--text-secondary)] bg-[#0b101b] p-2 rounded border border-[var(--border-subtle)]">
                    <div>
                      Area:{" "}
                      {prov.area_approx_m2 != null
                        ? `${Number(prov.area_approx_m2).toLocaleString()} m²`
                        : "N/A"}
                    </div>
                    <div>
                      Max Radius:{" "}
                      {prov.max_boundary_distance_m != null
                        ? `${Number(prov.max_boundary_distance_m).toFixed(1)} m`
                        : "N/A"}
                    </div>
                    <div>
                      Evaluated / Excluded:{" "}
                      {String(prov.passable_cells ?? 0)} / {String(prov.excluded_cells ?? 0)} cells
                    </div>
                    <div>
                      Unknown (No-Data): {String(prov.unknown_cells ?? 0)} cells
                    </div>
                    <div>
                      Source: {perimeter.terrain_dataset_id || "Unknown"}
                    </div>
                    <div>
                      Grid Spacing:{" "}
                      {prov.effective_cell_m != null ? `${String(prov.effective_cell_m)} m/cell` : "N/A"}
                    </div>
                  </div>
                )}

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
                    Approved at{" "}
                    {perimeter.approved_at_utc
                      ? new Date(perimeter.approved_at_utc).toLocaleString()
                      : ""}
                  </div>
                )}
              </div>
            )}
          </form>
        </div>

        {/* Right Primary Viewport: Global Mars Globe -> Local 3D DEM + Marker + Perimeter */}
        <div className="xl:col-span-7 ms-panel overflow-hidden min-h-[640px] flex flex-col">
          <div className="px-4 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)]/60 flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
            <div className="flex items-center gap-2">
              {viewMode === "local" ? (
                <button
                  type="button"
                  onClick={() => setViewMode("global")}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--bg-void)] border border-[var(--border-strong)] text-[var(--text-primary)] hover:border-[var(--accent-telemetry)]"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Return to Mars Globe</span>
                </button>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-[var(--accent-telemetry)]">
                  <Globe2 className="w-3.5 h-3.5" />
                  <span>GLOBAL MARS GLOBE (IAU2000:49900)</span>
                </span>
              )}
              {viewMode === "local" && (
                <span className="text-[var(--text-primary)]">
                  3D DEM PERIMETER · {activeDatasetId || meshManifest?.dataset_id || "Loading..."}
                </span>
              )}
            </div>

            <div className="text-[11px] text-[var(--text-muted)]">
              {site
                ? `${site.name} (${site.latitude.toFixed(4)}, ${site.longitude_east.toFixed(4)} E)`
                : pendingMarker
                ? `${pendingMarker.lat.toFixed(4)}, ${pendingMarker.lonEast.toFixed(4)} E`
                : "Click Mars globe or enter coordinates"}
            </div>
          </div>

          {viewMode === "local" && perimeter?.status === "EVALUATED_WITH_VALIDATED_DEM" && (
            <div className="px-4 py-1.5 border-b border-[var(--border-subtle)] bg-[#090d16] flex flex-wrap items-center gap-4 text-[10px] font-mono text-[var(--text-secondary)]">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#38bdf8]" /> Landing Site
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#22c55e]" /> Evaluated Permitted Perimeter
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#f97316]" /> Excluded by Constraints
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-[#a855f7]" /> Unknown (DEM No-Data)
              </span>
            </div>
          )}

          <div className="flex-1 min-h-[560px] relative">
            {viewMode === "global" ? (
              <MarsGlobeViewer
                selectionMode
                onSelectCoordinate={handleGlobeCoordinateSelect}
                pendingMarker={pendingMarker}
              />
            ) : (
              <LocalTerrain3DViewer
                landingSiteMarker={
                  site
                    ? {
                        lat: site.latitude,
                        lonEast: site.longitude_east,
                        name: site.name,
                        elevationM: site.elevation_m ?? null,
                        isNoData: site.sample_is_nodata,
                      }
                    : pendingMarker
                    ? {
                        lat: pendingMarker.lat,
                        lonEast: pendingMarker.lonEast,
                        name: pendingMarker.label,
                        elevationM: discovery?.elevation_m ?? null,
                        isNoData: discovery?.sample_is_nodata,
                      }
                    : null
                }
                perimeterData={perimeter}
                onTerrainReadyChange={handleTerrainReadyChange}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
