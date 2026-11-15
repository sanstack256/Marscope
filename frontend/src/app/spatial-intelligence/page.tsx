"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Compass,
  Eye,
  Globe2,
  Mountain,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import {
  DEFAULT_GALE_STUDY_BOUNDS,
  useSpatialStore,
  type StudyWindowBounds,
} from "@/stores/useSpatialStore";
import { useRoutingStore } from "@/stores/useRoutingStore";

type WorkbenchSection =
  | "crs"
  | "footprints_coverage"
  | "registration"
  | "terrain_scales"
  | "morphology"
  | "rover_delivery";

const KNOWN_DATASETS = [
  { id: "hirise_dteec_009149_1750", label: "HiRISE DEM 009149_1750 (1.01 m/px)" },
  { id: "hirise_psp_009149_1750_ortho", label: "HiRISE Ortho 009149_1750 (1.01 m/px)" },
  { id: "hirise_dteec_040770_1755", label: "HiRISE DEM 040770_1755 (1.01 m/px)" },
  { id: "hirise_esp_040770_1755_ortho", label: "HiRISE Ortho 040770_1755 (1.01 m/px)" },
  { id: "mola_megt00n090hb", label: "MOLA MEGDR 00N090HB (463 m/px)" },
  { id: "mola_megt90n000cb", label: "MOLA MEGDR 90N000CB (1852 m/px)" },
];

export default function SpatialIntelligencePage() {
  const [activeSection, setActiveSection] = useState<WorkbenchSection>("footprints_coverage");
  const [boundsInput, setBoundsInput] = useState<StudyWindowBounds>(DEFAULT_GALE_STUDY_BOUNDS);

  // CRS form state
  const [crsString, setCrsString] = useState("IAU2000:49900");
  const [latConv, setLatConv] = useState("Planetocentric");
  const [lonDir, setLonDir] = useState("East");
  const vertRef = "AREOID_RELATIVE_ELEVATION";
  const [datumA, setDatumA] = useState("AREOID_RELATIVE_ELEVATION");
  const [datumB, setDatumB] = useState("ELLIPSOID_RELATIVE_ELEVATION");
  const [txLon, setTxLon] = useState("137.42");
  const [txLat, setTxLat] = useState("-4.665");
  const [txSourceCrs, setTxSourceCrs] = useState("IAU2000:49900");
  const [txTargetCrs, setTxTargetCrs] = useState("MARS:IAU2015_49900");
  const [txTargetLatConv, setTxTargetLatConv] = useState("Planetographic");
  const txTargetLonDomain = "[-180, 180]";

  // Registration & Change form state
  const [regDatasetA, setRegDatasetA] = useState("hirise_dteec_009149_1750");
  const [regDatasetB, setRegDatasetB] = useState("hirise_psp_009149_1750_ortho");
  const [regIntended, setRegIntended] = useState("spatial_overlay");
  const [changeDatasetA, setChangeDatasetA] = useState("hirise_dteec_009149_1750");
  const [changeDatasetB, setChangeDatasetB] = useState("mola_megt00n090hb");

  // Morphology & Operator Auth form state
  const [operatorToken, setOperatorToken] = useState<string>(() =>
    typeof window !== "undefined" ? window.sessionStorage.getItem("marscope_operator_token") || "" : ""
  );
  const [reviewerId, setReviewerId] = useState("geology_lead_01");
  const [reviewNote, setReviewNote] = useState("Boxwork ridge morphology verified against DEM & Ortho.");

  const storeTargets = useRoutingStore((s) => s.availableTargets);
  const fetchAvailableTargets = useRoutingStore((s) => s.fetchAvailableTargets);
  const targetsLoaded = useRoutingStore((s) => s.targetsLoaded);

  const {
    studyBounds,
    setStudyBounds,
    primaryDatasetId,
    setPrimaryDatasetId,
    comparisonMode,
    setComparisonMode,
    showFootprintsOverlay,
    showGapsOverlay,
    showMorphologyOverlay,
    showRoverAssocOverlay,
    setOverlayFlag,
    selectedEntity,
    setSelectedEntity,

    crsRegistry,
    crsValidation,
    verticalDatumComparison,
    coordinateTransform,
    footprints,
    intersectingFootprints,
    activeRegistration,
    coverageReport,
    terrainDerivatives,
    scaleComparison,
    changeEvaluation,
    morphologyReport,
    morphologyReviews,
    roverAssociations,
    pyramidPlan,
    cacheStatus,

    loadingFootprints,
    loadingRegistration,
    loadingCoverage,
    loadingTerrain,
    loadingRoverAssoc,
    submittingReview,
    error,
    statusBanner,
    clearMessages,

    fetchCrsRegistry,
    validateCrs,
    compareVerticalDatums,
    transformCoordinates,
    fetchFootprints,
    fetchIntersectingFootprints,
    evaluateRegistration,
    evaluateCoverage,
    fetchTerrainDerivatives,
    compareTerrainScales,
    evaluateTerrainChange,
    detectMorphology,
    fetchMorphologyReviews,
    submitMorphologyReview,
    fetchRoverAssociations,
    fetchPyramidPlan,
    fetchCacheStatus,
    invalidateCache,
  } = useSpatialStore();

  useEffect(() => {
    if (!targetsLoaded) void fetchAvailableTargets();
  }, [targetsLoaded, fetchAvailableTargets]);

  useEffect(() => {
    void fetchCrsRegistry();
    void fetchFootprints();
    void fetchIntersectingFootprints(DEFAULT_GALE_STUDY_BOUNDS);
    void evaluateCoverage(DEFAULT_GALE_STUDY_BOUNDS, "hirise_dteec_009149_1750", 5.0);
    void evaluateRegistration({
      dataset_a_id: "hirise_dteec_009149_1750",
      dataset_b_id: "hirise_psp_009149_1750_ortho",
      intended_analysis: "spatial_overlay",
    });
    void fetchTerrainDerivatives("hirise_dteec_009149_1750", DEFAULT_GALE_STUDY_BOUNDS, 96);
    void compareTerrainScales(
      ["hirise_dteec_009149_1750", "mola_megt00n090hb"],
      DEFAULT_GALE_STUDY_BOUNDS
    );
    void evaluateTerrainChange(
      "hirise_dteec_009149_1750",
      "mola_megt00n090hb",
      DEFAULT_GALE_STUDY_BOUNDS
    );
    void detectMorphology("hirise_dteec_009149_1750", DEFAULT_GALE_STUDY_BOUNDS, 96);
    void fetchMorphologyReviews();
    void fetchRoverAssociations("hirise_dteec_009149_1750", DEFAULT_GALE_STUDY_BOUNDS);
    void fetchPyramidPlan(DEFAULT_GALE_STUDY_BOUNDS, 512);
    void fetchCacheStatus();
  }, [
    fetchCrsRegistry,
    fetchFootprints,
    fetchIntersectingFootprints,
    evaluateCoverage,
    evaluateRegistration,
    fetchTerrainDerivatives,
    compareTerrainScales,
    evaluateTerrainChange,
    detectMorphology,
    fetchMorphologyReviews,
    fetchRoverAssociations,
    fetchPyramidPlan,
    fetchCacheStatus,
  ]);

  function handleSaveToken(val: string) {
    setOperatorToken(val);
    if (typeof window !== "undefined") {
      if (val.trim()) window.sessionStorage.setItem("marscope_operator_token", val.trim());
      else window.sessionStorage.removeItem("marscope_operator_token");
    }
  }

  function handleApplyStudyBounds() {
    setStudyBounds(boundsInput);
    void fetchIntersectingFootprints(boundsInput);
    void evaluateCoverage(boundsInput, primaryDatasetId, 5.0);
    void fetchTerrainDerivatives(primaryDatasetId, boundsInput, 96);
    void detectMorphology(primaryDatasetId, boundsInput, 96);
    void fetchRoverAssociations(primaryDatasetId, boundsInput);
    void fetchPyramidPlan(boundsInput, 512);
  }

  return (
    <div className="space-y-4 pb-8">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#121622] border border-[#1e2638] rounded-xl px-4 py-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-base font-bold text-slate-100 tracking-tight">
              Multi-Mission Spatial Intelligence Workbench
            </h1>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-cyan-500/15 border border-cyan-500/35 text-cyan-300">
              CRS Registry {crsRegistry?.registry_version || "1.0.0-p19"}
            </span>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/35 text-amber-300">
              Non-Certified Scientific Decision Support
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Planetary coordinate integrity, true swath vs. bounding-box footprints, 12-step multi-mission registration,
            6-category coverage &amp; gap mapping, 13-field terrain derivatives, NoData-guarded morphology candidates, and scale-aware rover association.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/explorer"
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-slate-200"
          >
            <Globe2 className="w-3.5 h-3.5 text-cyan-400" />
            <span>Surface Explorer</span>
          </Link>
          <Link
            href="/science-campaign"
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-slate-200"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Science Campaign</span>
          </Link>
          <button
            type="button"
            onClick={handleApplyStudyBounds}
            className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Re-Evaluate Study Window</span>
          </button>
        </div>
      </div>

      {/* Study Window & Operator Token Strip */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 bg-[#101521] border border-[#1e2638] rounded-xl p-3 text-xs font-mono">
        <div className="xl:col-span-8 flex flex-wrap items-center gap-2">
          <span className="text-slate-400 font-semibold uppercase text-[10px]">Study Window (IAU2000:49900):</span>
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            <span>minLat</span>
            <input
              type="number"
              step="0.005"
              value={boundsInput.min_lat}
              onChange={(e) => setBoundsInput({ ...boundsInput, min_lat: Number.parseFloat(e.target.value) || -4.675 })}
              className="w-20 bg-[#0b101b] border border-[#25314a] rounded px-1.5 py-0.5 text-slate-100"
            />
          </label>
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            <span>maxLat</span>
            <input
              type="number"
              step="0.005"
              value={boundsInput.max_lat}
              onChange={(e) => setBoundsInput({ ...boundsInput, max_lat: Number.parseFloat(e.target.value) || -4.655 })}
              className="w-20 bg-[#0b101b] border border-[#25314a] rounded px-1.5 py-0.5 text-slate-100"
            />
          </label>
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            <span>minLon</span>
            <input
              type="number"
              step="0.005"
              value={boundsInput.min_lon}
              onChange={(e) => setBoundsInput({ ...boundsInput, min_lon: Number.parseFloat(e.target.value) || 137.405 })}
              className="w-24 bg-[#0b101b] border border-[#25314a] rounded px-1.5 py-0.5 text-slate-100"
            />
          </label>
          <label className="flex items-center gap-1 text-[11px] text-slate-300">
            <span>maxLon</span>
            <input
              type="number"
              step="0.005"
              value={boundsInput.max_lon}
              onChange={(e) => setBoundsInput({ ...boundsInput, max_lon: Number.parseFloat(e.target.value) || 137.435 })}
              className="w-24 bg-[#0b101b] border border-[#25314a] rounded px-1.5 py-0.5 text-slate-100"
            />
          </label>
          <select
            value={primaryDatasetId}
            onChange={(e) => setPrimaryDatasetId(e.target.value)}
            className="bg-[#0b101b] border border-[#25314a] rounded px-2 py-1 text-[11px] text-cyan-200"
          >
            {KNOWN_DATASETS.filter((d) => d.id.includes("dteec") || d.id.includes("mola")).map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
        </div>

        <div className="xl:col-span-4 flex items-center justify-end gap-2">
          <span className="text-[10px] text-slate-400">Operator Token:</span>
          <input
            type="password"
            placeholder="X-Mars-Operator-Token (for Review/Cache)"
            value={operatorToken}
            onChange={(e) => handleSaveToken(e.target.value)}
            className="flex-1 max-w-[220px] bg-[#0b101b] border border-[#25314a] rounded px-2 py-1 text-[11px] text-slate-200"
          />
        </div>
      </div>

      {(error || statusBanner) && (
        <div
          className={`flex items-center justify-between gap-2 p-3 rounded-xl border text-xs font-mono ${
            error
              ? "bg-rose-950/50 border-rose-700/60 text-rose-200"
              : "bg-emerald-950/50 border-emerald-700/60 text-emerald-200"
          }`}
        >
          <span>{error || statusBanner}</span>
          <button type="button" onClick={clearMessages} className="underline hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Split: Left 3D Spatial Viewport + Right 6-Section Analytical Workbench */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Left Column: Synchronized 3D Terrain Viewport + Overlay Toggles */}
        <div className="xl:col-span-5 flex flex-col gap-3">
          <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-3 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                3D Spatial Evidence &amp; Comparison Canvas
              </span>
              <div className="flex items-center gap-1 text-[10px] font-mono">
                {(["single", "swipe", "blend"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setComparisonMode(m)}
                    className={`px-2 py-0.5 rounded uppercase ${
                      comparisonMode === m
                        ? "bg-sky-600 text-white font-semibold"
                        : "bg-[#0d111a] text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap gap-1.5 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setOverlayFlag("showFootprintsOverlay", !showFootprintsOverlay)}
                className={`px-2 py-1 rounded border ${
                  showFootprintsOverlay
                    ? "bg-cyan-950/70 border-cyan-500/60 text-cyan-200"
                    : "bg-[#0d111a] border-[#243047] text-slate-400"
                }`}
              >
                <Eye className="w-3 h-3 inline mr-1" />
                Swath Footprints ({intersectingFootprints.length})
              </button>
              <button
                type="button"
                onClick={() => setOverlayFlag("showGapsOverlay", !showGapsOverlay)}
                className={`px-2 py-1 rounded border ${
                  showGapsOverlay
                    ? "bg-rose-950/70 border-rose-500/60 text-rose-200"
                    : "bg-[#0d111a] border-[#243047] text-slate-400"
                }`}
              >
                <ShieldAlert className="w-3 h-3 inline mr-1" />
                Evidence Gaps ({coverageReport?.evidence_gaps?.length ?? 0})
              </button>
              <button
                type="button"
                onClick={() => setOverlayFlag("showMorphologyOverlay", !showMorphologyOverlay)}
                className={`px-2 py-1 rounded border ${
                  showMorphologyOverlay
                    ? "bg-amber-950/70 border-amber-500/60 text-amber-200"
                    : "bg-[#0d111a] border-[#243047] text-slate-400"
                }`}
              >
                <Mountain className="w-3 h-3 inline mr-1" />
                Morphology ({morphologyReport?.candidates?.length ?? 0})
              </button>
              <button
                type="button"
                onClick={() => setOverlayFlag("showRoverAssocOverlay", !showRoverAssocOverlay)}
                className={`px-2 py-1 rounded border ${
                  showRoverAssocOverlay
                    ? "bg-sky-950/70 border-sky-500/60 text-sky-200"
                    : "bg-[#0d111a] border-[#243047] text-slate-400"
                }`}
              >
                <Compass className="w-3 h-3 inline mr-1" />
                Rover Assoc ({roverAssociations.length})
              </button>
            </div>

            <div className="h-[460px]">
              <LocalTerrain3DViewer targets={storeTargets} showSpatialTools={true} />
            </div>

            {selectedEntity && (
              <div className="p-3 rounded-lg bg-[#0d121f] border border-cyan-500/50 text-xs font-mono space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-cyan-300 uppercase">
                    Active Spatial Inspector: {selectedEntity.kind}
                  </span>
                  <button
                    type="button"
                    onClick={() => setSelectedEntity(null)}
                    className="text-slate-400 hover:text-white underline text-[10px]"
                  >
                    Clear Selection
                  </button>
                </div>
                {selectedEntity.kind === "footprint" && (
                  <div className="space-y-1 text-[11px] text-slate-300">
                    <div>
                      Product: <strong className="text-white">{selectedEntity.data.product_id}</strong> ({selectedEntity.data.dataset_id})
                    </div>
                    <div>
                      Extraction: {selectedEntity.data.extraction_method} · CRS:{" "}
                      {selectedEntity.data.coordinate_validation.validation_state}
                    </div>
                    <div>
                      Valid Swath Area:{" "}
                      {selectedEntity.data.valid_data_area_m2 != null
                        ? `${(selectedEntity.data.valid_data_area_m2 / 1e6).toFixed(2)} km²`
                        : "Approximate BBox Only"}{" "}
                      · Swath/BBox Ratio:{" "}
                      {selectedEntity.data.swath_to_bbox_ratio != null
                        ? `${(selectedEntity.data.swath_to_bbox_ratio * 100).toFixed(1)}%`
                        : "Withheld"}
                    </div>
                  </div>
                )}
                {selectedEntity.kind === "gap" && (
                  <div className="space-y-1 text-[11px] text-slate-300">
                    <div className="text-rose-300 font-semibold">
                      {selectedEntity.data.category} — {selectedEntity.data.gap_cause}
                    </div>
                    <div>{selectedEntity.data.summary}</div>
                    <div className="text-amber-300">{selectedEntity.data.interpretation_warning}</div>
                    <div className="text-cyan-300">Action: {selectedEntity.data.recommended_action}</div>
                  </div>
                )}
                {selectedEntity.kind === "morphology" && (
                  <div className="space-y-1 text-[11px] text-slate-300">
                    <div className="text-amber-200 font-semibold">
                      {selectedEntity.data.candidate_id} · {selectedEntity.data.feature_class} ({selectedEntity.data.epistemic_state})
                    </div>
                    <div>{selectedEntity.data.descriptive_summary}</div>
                    <div className="text-amber-300 text-[10px]">
                      {selectedEntity.data.geological_interpretation_warning}
                    </div>
                  </div>
                )}
                {selectedEntity.kind === "rover_assoc" && (
                  <div className="space-y-1 text-[11px] text-slate-300">
                    <div className="text-sky-200 font-semibold">
                      {selectedEntity.data.observation_id} ({selectedEntity.data.instrument}) — {selectedEntity.data.association_state}
                    </div>
                    <div>{selectedEntity.data.scale_disparity_statement}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: 6-Module Spatial Intelligence Tabs */}
        <div className="xl:col-span-7 bg-[#121622] border border-[#1e2638] rounded-xl flex flex-col overflow-hidden">
          <div className="flex flex-wrap border-b border-[#1e2638] bg-[#0d111a]">
            {(
              [
                { id: "footprints_coverage", label: "1. Swaths & 6-Category Gaps" },
                { id: "registration", label: "2. 12-Step Registration" },
                { id: "terrain_scales", label: "3. Multi-Scale Terrain & Change Gate" },
                { id: "morphology", label: "4. Morphology & Human Review" },
                { id: "rover_delivery", label: "5. Rover Assoc & Pyramid Cache" },
                { id: "crs", label: "6. CRS & Datum Engine" },
              ] as Array<{ id: WorkbenchSection; label: string }>
            ).map((tab) => (
              <button
                key={tab.id}
                type="button"
                data-testid={`spatial-tab-${tab.id}`}
                onClick={() => setActiveSection(tab.id)}
                className={`px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
                  activeSection === tab.id
                    ? "border-cyan-500 text-cyan-200 bg-[#151b2b]"
                    : "border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="p-4 space-y-4 overflow-y-auto max-h-[760px]">
            {/* SECTION 1: FOOTPRINTS & 6-CATEGORY COVERAGE / GAPS */}
            {activeSection === "footprints_coverage" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-bold text-slate-100">
                      True Valid-Pixel Swath Footprints vs. Bounding-Box Coverage
                    </h2>
                    <p className="text-xs text-slate-400">
                      Distinguishes rectangular PDS bounding boxes from actual rotated valid-pixel swaths in Mars LAEA equal-area projection.
                    </p>
                  </div>
                  <span className="text-[11px] font-mono text-cyan-300">
                    {loadingFootprints || loadingCoverage ? "Evaluating..." : `${footprints.length} products indexed`}
                  </span>
                </div>

                <div className="overflow-x-auto border border-[#1e2638] rounded-lg">
                  <table className="w-full text-left text-[11px] font-mono">
                    <thead className="bg-[#0d111a] text-slate-400 border-b border-[#1e2638]">
                      <tr>
                        <th className="p-2">Dataset / Product</th>
                        <th className="p-2">Category</th>
                        <th className="p-2">Extraction Method</th>
                        <th className="p-2">Valid Swath %</th>
                        <th className="p-2">CRS State</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1e2638]">
                      {footprints.map((fp) => (
                        <tr
                          key={fp.dataset_id}
                          onClick={() => setSelectedEntity({ kind: "footprint", data: fp })}
                          className="hover:bg-[#171f32] cursor-pointer"
                        >
                          <td className="p-2 text-slate-100 font-semibold">{fp.dataset_id}</td>
                          <td className="p-2 text-cyan-300">{fp.category}</td>
                          <td className="p-2 text-slate-300">{fp.extraction_method}</td>
                          <td className="p-2">
                            {fp.valid_data_fraction != null ? (
                              <span className="text-emerald-300">
                                {(fp.valid_data_fraction * 100).toFixed(1)}% (BBox ratio{" "}
                                {fp.swath_to_bbox_ratio != null ? `${(fp.swath_to_bbox_ratio * 100).toFixed(1)}%` : "—"})
                              </span>
                            ) : (
                              <span className="text-amber-300">APPROX BBOX ONLY (Exact % Suppressed)</span>
                            )}
                          </td>
                          <td className="p-2 text-slate-300">{fp.coordinate_validation.validation_state}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {coverageReport && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                        6-Category × 5-Stage Spatial Coverage ({(coverageReport.study_area_m2 / 1e6).toFixed(2)} km²)
                      </h3>
                      <span className="text-[10px] font-mono text-slate-400">
                        Area Method: {coverageReport.area_calculation_method}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {Object.values(coverageReport.categories).map((cat) => (
                        <div
                          key={cat.category}
                          className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-1.5 text-[11px] font-mono"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-cyan-300 uppercase">{cat.category}</span>
                            <span className="text-slate-400">
                              {cat.best_native_resolution_m != null ? `${cat.best_native_resolution_m} m/px` : "Point/No Grid"}
                            </span>
                          </div>
                          {cat.only_approximate_footprints ? (
                            <div className="text-amber-300 text-[10px]">
                              {cat.percentage_reporting_policy}
                            </div>
                          ) : (
                            <div className="grid grid-cols-2 gap-1 text-[10px] text-slate-300">
                              <div>Footprint: {cat.product_footprint_fraction != null ? `${(cat.product_footprint_fraction * 100).toFixed(1)}%` : "—"}</div>
                              <div>Valid Pixels: {cat.valid_pixel_fraction != null ? `${(cat.valid_pixel_fraction * 100).toFixed(1)}%` : "—"}</div>
                              <div>Registered: {cat.spatially_registered_fraction != null ? `${(cat.spatially_registered_fraction * 100).toFixed(1)}%` : "—"}</div>
                              <div>Eligible: {cat.scientifically_eligible_fraction != null ? `${(cat.scientifically_eligible_fraction * 100).toFixed(1)}%` : "—"}</div>
                            </div>
                          )}
                          {cat.rover_point_observation_count > 0 && (
                            <div className="text-[10px] text-sky-300">
                              In-Situ Rover Point Observations: {cat.rover_point_observation_count} (non-areal)
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    <div className="space-y-2">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-rose-300">
                        Explicit Evidence Gap Polygons ({coverageReport.evidence_gaps.length}) — Never Implies Feature Absence
                      </h3>
                      <div className="space-y-2">
                        {coverageReport.evidence_gaps.map((gap) => (
                          <div
                            key={gap.gap_id}
                            onClick={() => setSelectedEntity({ kind: "gap", data: gap })}
                            className="p-2.5 rounded-lg bg-[#141927] hover:bg-[#1a2235] border border-rose-500/35 cursor-pointer space-y-1 text-[11px] font-mono"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-rose-300">
                                {gap.category} · {gap.gap_cause}
                              </span>
                              <span className="text-slate-400">
                                {(gap.area_fraction_of_study_region * 100).toFixed(1)}% of study window
                              </span>
                            </div>
                            <div className="text-slate-200">{gap.summary}</div>
                            <div className="text-[10px] text-amber-300">{gap.interpretation_warning}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* SECTION 2: 12-STEP MULTI-MISSION REGISTRATION */}
            {activeSection === "registration" && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-end gap-2 bg-[#0d111a] border border-[#1e2638] rounded-lg p-3 text-xs font-mono">
                  <label className="space-y-1">
                    <span className="text-[10px] text-slate-400 block">Dataset A (Reference)</span>
                    <select
                      value={regDatasetA}
                      onChange={(e) => setRegDatasetA(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      {KNOWN_DATASETS.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] text-slate-400 block">Dataset B (Target)</span>
                    <select
                      value={regDatasetB}
                      onChange={(e) => setRegDatasetB(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      {KNOWN_DATASETS.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1">
                    <span className="text-[10px] text-slate-400 block">Intended Analysis</span>
                    <select
                      value={regIntended}
                      onChange={(e) => setRegIntended(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      <option value="spatial_overlay">spatial_overlay</option>
                      <option value="route_planning">route_planning</option>
                      <option value="temporal_terrain_change">temporal_terrain_change</option>
                      <option value="composition_association">composition_association</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    disabled={loadingRegistration}
                    onClick={() =>
                      void evaluateRegistration({
                        dataset_a_id: regDatasetA,
                        dataset_b_id: regDatasetB,
                        intended_analysis: regIntended,
                        attempt_image_matching: true,
                      })
                    }
                    className="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold disabled:opacity-50"
                  >
                    {loadingRegistration ? "Evaluating..." : "Run 12-Step Registration"}
                  </button>
                </div>

                {activeRegistration && (
                  <div className="space-y-3 text-xs font-mono">
                    <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-slate-100">
                          {activeRegistration.dataset_a_id} ↔ {activeRegistration.dataset_b_id}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded font-bold ${
                            activeRegistration.suitable_for_intended_analysis
                              ? "bg-emerald-950/70 border border-emerald-500/50 text-emerald-300"
                              : "bg-rose-950/70 border border-rose-500/50 text-rose-300"
                          }`}
                        >
                          {activeRegistration.overall_state}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-slate-300">
                        <div>Overlap: {activeRegistration.footprint_overlap_status}</div>
                        <div>Grid: {activeRegistration.pixel_alignment.grid_alignment_status}</div>
                        <div>Origin Offset: {activeRegistration.pixel_alignment.transform_origin_offset_m ?? "—"} m</div>
                        <div>
                          Rel σ:{" "}
                          {activeRegistration.uncertainty_breakdown.relative_alignment_uncertainty_m != null
                            ? `±${activeRegistration.uncertainty_breakdown.relative_alignment_uncertainty_m.toFixed(2)} m`
                            : "Withheld"}
                        </div>
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Independence Rationale: {activeRegistration.uncertainty_breakdown.independence_rationale}
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <div className="text-[11px] font-bold text-slate-300 uppercase">
                        12-Step Registration Workflow Trace
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                        {activeRegistration.workflow_steps.map((st) => (
                          <div
                            key={st.step_number}
                            className="p-2 rounded bg-[#0d111a] border border-[#1e2638] text-[10px] space-y-0.5"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-slate-200">
                                #{st.step_number} {st.step_name}
                              </span>
                              <span className="text-cyan-300">{st.status}</span>
                            </div>
                            <div className="text-slate-400">{st.detail}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* SECTION 3: MULTI-RESOLUTION TERRAIN & CHANGE GATE */}
            {activeSection === "terrain_scales" && (
              <div className="space-y-4 text-xs font-mono">
                {terrainDerivatives && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="font-bold text-slate-100 uppercase">
                        13-Field Windowed Terrain Derivatives ({terrainDerivatives.dataset_metadata.dataset_id})
                      </h3>
                      <span className="text-emerald-300">
                        Valid Pixels: {terrainDerivatives.valid_pixel_count} (
                        {(terrainDerivatives.valid_coverage_fraction * 100).toFixed(1)}%)
                      </span>
                    </div>
                    <div className="overflow-x-auto border border-[#1e2638] rounded-lg">
                      <table className="w-full text-left text-[10px]">
                        <thead className="bg-[#0d111a] text-slate-400 border-b border-[#1e2638]">
                          <tr>
                            <th className="p-2">Derivative</th>
                            <th className="p-2">Scale / Window</th>
                            <th className="p-2">Min / Mean / Max</th>
                            <th className="p-2">Units</th>
                            <th className="p-2">NoData Handling</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#1e2638]">
                          {Object.values(terrainDerivatives.derivatives).map((d) => (
                            <tr key={d.derivative_name}>
                              <td className="p-2 font-semibold text-cyan-200">{d.derivative_name}</td>
                              <td className="p-2 text-slate-300">{d.window_or_physical_scale}</td>
                              <td className="p-2 text-slate-200">
                                {d.stats.min?.toFixed(2) ?? "—"} / {d.stats.mean?.toFixed(2) ?? "—"} /{" "}
                                {d.stats.max?.toFixed(2) ?? "—"}
                              </td>
                              <td className="p-2 text-slate-400">{d.units}</td>
                              <td className="p-2 text-slate-400">{d.nodata_handling}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {scaleComparison && (
                  <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-amber-200 uppercase">
                        Multi-Scale Slope &amp; Roughness Smoothing Attenuation (HiRISE 1m vs MOLA 463m)
                      </span>
                      <span className="text-[10px] text-emerald-300">
                        Temporal Change Claim Blocked: {String(scaleComparison.never_interprets_scale_diff_as_temporal_change)}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {scaleComparison.compared_datasets.map((entry) => (
                        <div key={entry.dataset_id} className="p-2 rounded bg-[#141a2a] border border-[#243047] space-y-1 text-[10px]">
                          <div className="font-bold text-white">
                            {entry.dataset_id} ({entry.native_resolution_m.toFixed(2)} m/px · {entry.scale_category})
                          </div>
                          <div>
                            Elev Mean: {entry.elevation_mean_m?.toFixed(1) ?? "—"} m · Slope Mean:{" "}
                            {entry.slope_mean_deg?.toFixed(2) ?? "—"}° (P95: {entry.slope_p95_deg?.toFixed(2) ?? "—"}°)
                          </div>
                          <div className="text-slate-400">{entry.smoothing_attenuation_note}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-bold text-rose-300 uppercase">
                      6-Gate Temporal Terrain Change Evaluator
                    </span>
                    <div className="flex items-center gap-1.5">
                      <select
                        value={changeDatasetA}
                        onChange={(e) => setChangeDatasetA(e.target.value)}
                        className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-[10px]"
                      >
                        {KNOWN_DATASETS.filter((d) => d.id.includes("dteec") || d.id.includes("mola")).map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.id}
                          </option>
                        ))}
                      </select>
                      <span>vs</span>
                      <select
                        value={changeDatasetB}
                        onChange={(e) => setChangeDatasetB(e.target.value)}
                        className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-[10px]"
                      >
                        {KNOWN_DATASETS.filter((d) => d.id.includes("dteec") || d.id.includes("mola")).map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.id}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={loadingTerrain}
                        onClick={() => void evaluateTerrainChange(changeDatasetA, changeDatasetB, studyBounds)}
                        className="px-2.5 py-1 rounded bg-rose-700 hover:bg-rose-600 text-white font-semibold"
                      >
                        Test Change Gates
                      </button>
                    </div>
                  </div>

                  {changeEvaluation && (
                    <div className="space-y-2 text-[10px]">
                      <div className="flex items-center justify-between">
                        <span>
                          Status: <strong className="text-amber-300">{changeEvaluation.status}</strong>
                        </span>
                        <span>Evaluable: {String(changeEvaluation.evaluable)}</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                        {changeEvaluation.gates.map((g) => (
                          <div
                            key={g.gate_name}
                            className={`p-1.5 rounded border ${
                              g.passed
                                ? "bg-emerald-950/30 border-emerald-700/50 text-emerald-200"
                                : "bg-rose-950/40 border-rose-700/50 text-rose-200"
                            }`}
                          >
                            <div className="font-semibold">
                              {g.passed ? "PASS" : "BLOCK"} · {g.gate_name}
                            </div>
                            <div className="text-slate-300">{g.detail}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* SECTION 4: GEOLOGICAL MORPHOLOGY & AUTH-GUARDED HUMAN REVIEW */}
            {activeSection === "morphology" && (
              <div className="space-y-4 text-xs font-mono">
                {morphologyReport && (
                  <>
                    <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-amber-200 uppercase">
                          Resolution-Gated Feature Detection ({morphologyReport.dataset_id})
                        </span>
                        <span className="text-slate-300">
                          Accepted Candidates: {morphologyReport.candidates.length} · Rejected NoData-Border Artifacts:{" "}
                          <strong className="text-rose-300">
                            {morphologyReport.rejected_nodata_border_candidates.length}
                          </strong>{" "}
                          (guard={morphologyReport.nodata_border_guard_px}px)
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 text-[10px]">
                        {morphologyReport.resolution_gating.map((rg) => (
                          <span
                            key={rg.feature_class}
                            title={rg.reason}
                            className={`px-2 py-0.5 rounded border ${
                              rg.detectable
                                ? "bg-emerald-950/50 border-emerald-700/50 text-emerald-300"
                                : "bg-rose-950/50 border-rose-700/50 text-rose-300"
                            }`}
                          >
                            {rg.feature_class}: {rg.detectable ? "DETECTABLE" : `BLOCKED (req ≤${rg.required_max_resolution_m}m)`}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                      <div className="text-[11px] font-bold text-slate-200">
                        Human Review Attribution Settings (Strictly Persisted as classification=&quot;USER_PROVIDED&quot;)
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <input
                          type="text"
                          value={reviewerId}
                          onChange={(e) => setReviewerId(e.target.value)}
                          placeholder="Reviewer ID"
                          className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                        />
                        <input
                          type="text"
                          value={reviewNote}
                          onChange={(e) => setReviewNote(e.target.value)}
                          placeholder="Review annotation note"
                          className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      {morphologyReport.candidates.slice(0, 12).map((cand) => {
                        const rev = morphologyReviews[cand.candidate_id] || cand.human_review;
                        return (
                          <div
                            key={cand.candidate_id}
                            onClick={() => setSelectedEntity({ kind: "morphology", data: cand })}
                            className="p-3 rounded-lg bg-[#0d111a] hover:bg-[#141b2d] border border-[#1e2638] cursor-pointer space-y-1.5"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-bold text-amber-300">
                                {cand.candidate_id} · {cand.feature_class}
                              </span>
                              <div className="flex items-center gap-1.5 text-[10px]">
                                <span className="px-1.5 py-0.5 rounded bg-[#161f33] text-cyan-200">
                                  {cand.epistemic_state}
                                </span>
                                {rev && (
                                  <span className="px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-500/50 text-cyan-200">
                                    {rev.classification} ({rev.action} by {rev.reviewer_id})
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="text-[11px] text-slate-300">{cand.descriptive_summary}</div>
                            <div className="text-[10px] text-amber-300/90">
                              {cand.geological_interpretation_warning}
                            </div>
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {(["accept", "reject", "annotate"] as const).map((act) => (
                                <button
                                  key={act}
                                  type="button"
                                  disabled={submittingReview}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void submitMorphologyReview({
                                      candidate_id: cand.candidate_id,
                                      dataset_id: morphologyReport.dataset_id,
                                      action: act,
                                      reviewer_id: reviewerId,
                                      annotation_note: reviewNote,
                                      operator_token: operatorToken,
                                    });
                                  }}
                                  className="px-2.5 py-1 rounded bg-[#182236] hover:bg-[#22304c] border border-[#2d3e5e] text-[10px] text-slate-200 uppercase"
                                >
                                  {act} (USER_PROVIDED)
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* SECTION 5: ROVER SCALE-AWARE ASSOCIATION & PYRAMID / CACHE */}
            {activeSection === "rover_delivery" && (
              <div className="space-y-4 text-xs font-mono">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-sky-300 uppercase">
                      Scale-Aware Rover-to-Orbital Associations ({roverAssociations.length})
                    </h3>
                    <span className="text-[10px] text-slate-400">
                      {loadingRoverAssoc ? "Loading..." : "Sub-cm/mm Rover Spot ≠ Entire 1m² HiRISE Pixel"}
                  </span>
                  </div>
                  <div className="overflow-x-auto border border-[#1e2638] rounded-lg">
                    <table className="w-full text-left text-[10px]">
                      <thead className="bg-[#0d111a] text-slate-400 border-b border-[#1e2638]">
                        <tr>
                          <th className="p-2">Observation</th>
                          <th className="p-2">Instrument</th>
                          <th className="p-2">State</th>
                          <th className="p-2">Location Semantic</th>
                          <th className="p-2">Spot vs Pixel Scale Ratio</th>
                          <th className="p-2">Confirms Whole Pixel?</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#1e2638]">
                        {roverAssociations.slice(0, 12).map((ra) => (
                          <tr
                            key={ra.observation_id}
                            onClick={() => setSelectedEntity({ kind: "rover_assoc", data: ra })}
                            className="hover:bg-[#161e31] cursor-pointer"
                          >
                            <td className="p-2 font-semibold text-slate-100">{ra.observation_id}</td>
                            <td className="p-2 text-cyan-300">{ra.instrument}</td>
                            <td className="p-2 text-emerald-300">{ra.association_state}</td>
                            <td className="p-2 text-slate-300">{ra.location_semantic_type}</td>
                            <td className="p-2 text-amber-300">
                              {ra.observation_footprint_m}m vs {ra.orbital_pixel_footprint_m?.toFixed(2)}m (
                              {ra.scale_disparity_ratio?.toExponential(2)})
                            </td>
                            <td className="p-2 font-bold text-rose-300">
                              {String(ra.confirms_entire_orbital_pixel)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {pyramidPlan && (
                  <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-cyan-300 uppercase">
                        Multi-Resolution Delivery Pyramid Plan
                      </span>
                      <span className="text-[10px] text-emerald-300">
                        Upsampling Prevented: {String(pyramidPlan.upsampling_prevented)} · Selected DEM:{" "}
                        {pyramidPlan.selected_dem_dataset_id}
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-300">
                      Viewport Span: {pyramidPlan.viewport_span_m} m · Target Pixel: {pyramidPlan.target_pixel_size_m} m/px ·
                      Cache Digest Preview: {pyramidPlan.cache_digest_preview}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-[10px]">
                      {pyramidPlan.source_transitions.map((tr, i) => (
                        <div key={i} className="p-2 rounded bg-[#141a2a] border border-[#243047] text-amber-200">
                          Transition {tr.from_dataset_id} → {tr.to_dataset_id} @ {tr.transition_span_m}m (jump{" "}
                          {tr.resolution_jump_factor}x)
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {cacheStatus && (
                  <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-bold text-slate-200 uppercase">
                        9-Input Spatial Cache Status ({cacheStatus.engine_version})
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          void invalidateCache(
                            primaryDatasetId,
                            "workbench_operator_invalidation",
                            operatorToken
                          )
                        }
                        className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-[10px] font-semibold"
                      >
                        Invalidate Cache (Requires Token)
                      </button>
                    </div>
                    <div className="text-[10px] text-slate-300">
                      Tile Cache Entries: {cacheStatus.mesh_tile_cache.entries} / {cacheStatus.mesh_tile_cache.max_entries} ·
                      Hits: {cacheStatus.mesh_tile_cache.hits} · Misses: {cacheStatus.mesh_tile_cache.misses}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      Key Dimensions: {cacheStatus.key_dimensions.join(" · ")}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* SECTION 6: PLANETARY CRS, VERTICAL DATUMS & COORDINATE TRANSFORMATIONS */}
            {activeSection === "crs" && (
              <div className="space-y-4 text-xs font-mono">
                <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2.5">
                  <div className="font-bold text-cyan-300 uppercase">
                    8-State Planetary CRS &amp; Convention Validator
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <input
                      type="text"
                      value={crsString}
                      onChange={(e) => setCrsString(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                      placeholder="CRS (e.g. IAU_2015:49900 or EPSG:4326)"
                    />
                    <select
                      value={latConv}
                      onChange={(e) => setLatConv(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      <option value="Planetocentric">Planetocentric</option>
                      <option value="Planetographic">Planetographic</option>
                    </select>
                    <select
                      value={lonDir}
                      onChange={(e) => setLonDir(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      <option value="East">Positive East</option>
                      <option value="West">Positive West</option>
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        void validateCrs({
                          crs_string: crsString,
                          latitude_convention: latConv,
                          longitude_direction: lonDir,
                          vertical_reference: vertRef,
                          require_conventions: true,
                          require_vertical_datum: true,
                        })
                      }
                      className="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold"
                    >
                      Validate CRS
                    </button>
                  </div>
                  {crsValidation && (
                    <div className="p-2 rounded bg-[#141a29] border border-[#243047] text-[10px] space-y-1">
                      <div>
                        State: <strong className="text-cyan-300">{crsValidation.validation_state}</strong> · Valid:{" "}
                        {String(crsValidation.valid)} · Body: {crsValidation.planetary_body}
                      </div>
                      {crsValidation.blockers.length > 0 && (
                        <div className="text-rose-300">Blockers: {crsValidation.blockers.join("; ")}</div>
                      )}
                    </div>
                  )}
                </div>

                <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2.5">
                  <div className="font-bold text-amber-300 uppercase">
                    Vertical Datum Compatibility Guard (MOLA Areoid vs Ellipsoid vs Relative)
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value={datumA}
                      onChange={(e) => setDatumA(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      {(crsRegistry?.vertical_datum_kinds ?? ["MOLA_AREOID", "REFERENCE_ELLIPSOID", "LOCAL_RELATIVE"]).map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                    <span>vs</span>
                    <select
                      value={datumB}
                      onChange={(e) => setDatumB(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      {(crsRegistry?.vertical_datum_kinds ?? ["MOLA_AREOID", "REFERENCE_ELLIPSOID", "LOCAL_RELATIVE"]).map((k) => (
                        <option key={k} value={k}>
                          {k}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => void compareVerticalDatums(datumA, datumB)}
                      className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white font-semibold"
                    >
                      Compare Datums
                    </button>
                  </div>
                  {verticalDatumComparison && (
                    <div className="p-2 rounded bg-[#141a29] border border-[#243047] text-[10px] space-y-1">
                      <div>
                        Compatible: <strong className="text-amber-300">{String(verticalDatumComparison.compatible)}</strong> (
                        {verticalDatumComparison.validation_state})
                      </div>
                      <div className="text-slate-300">{verticalDatumComparison.explanation}</div>
                    </div>
                  )}
                </div>

                <div className="p-3 rounded-lg bg-[#0d111a] border border-[#1e2638] space-y-2.5">
                  <div className="font-bold text-emerald-300 uppercase">
                    Auditable Planetary Coordinate Transformation
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <input
                      type="number"
                      step="0.01"
                      value={txLon}
                      onChange={(e) => setTxLon(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                      placeholder="Lon / X"
                    />
                    <input
                      type="number"
                      step="0.01"
                      value={txLat}
                      onChange={(e) => setTxLat(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                      placeholder="Lat / Y"
                    />
                    <input
                      type="text"
                      value={txSourceCrs}
                      onChange={(e) => setTxSourceCrs(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                      placeholder="Source CRS"
                    />
                    <input
                      type="text"
                      value={txTargetCrs}
                      onChange={(e) => setTxTargetCrs(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                      placeholder="Target CRS"
                    />
                    <select
                      value={txTargetLatConv}
                      onChange={(e) => setTxTargetLatConv(e.target.value)}
                      className="bg-[#141927] border border-[#26324b] rounded px-2 py-1 text-slate-100"
                    >
                      <option value="Planetocentric">Out: Planetocentric</option>
                      <option value="Planetographic">Out: Planetographic</option>
                    </select>
                    <button
                      type="button"
                      onClick={() =>
                        void transformCoordinates({
                          x_or_lon: Number.parseFloat(txLon) || 137.42,
                          y_or_lat: Number.parseFloat(txLat) || -4.665,
                          source_crs: txSourceCrs,
                          target_crs: txTargetCrs,
                          target_lat_convention: txTargetLatConv,
                          target_lon_domain: txTargetLonDomain,
                        })
                      }
                      className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                    >
                      Transform Coordinates
                    </button>
                  </div>
                  {coordinateTransform && (
                    <div className="p-2 rounded bg-[#141a29] border border-[#243047] text-[10px] space-y-1">
                      <div>
                        Success: <strong className="text-emerald-300">{String(coordinateTransform.success)}</strong> ·{" "}
                        {coordinateTransform.library} {coordinateTransform.library_version} ({coordinateTransform.algorithm})
                      </div>
                      {coordinateTransform.output_coordinates && (
                        <div className="text-white">
                          Output: {JSON.stringify(coordinateTransform.output_coordinates)}
                        </div>
                      )}
                      {coordinateTransform.failure_reason && (
                        <div className="text-rose-300">Blocked: {coordinateTransform.failure_reason}</div>
                      )}
                      <div className="text-slate-400">
                        Steps: {coordinateTransform.provenance_steps.join(" → ")}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
