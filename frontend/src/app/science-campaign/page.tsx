"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  Compass,
  Database,
  FlaskConical,
  Layers,
  Microscope,
  Plus,
  RefreshCw,
  Route as RouteIcon,
  ShieldAlert,
  Trash2,
  XCircle,
} from "lucide-react";
import { LocalTerrain3DViewer, type InvestigationPinMarker } from "../../components/LocalTerrain3DViewer";
import { useInvestigationStore } from "../../stores/useInvestigationStore";
import type {
  CampaignBuildRequest,
  MeasurementClass,
  PlanningMode,
} from "../../types";

const MEASUREMENT_CLASS_OPTIONS: Array<{ value: MeasurementClass; label: string }> = [
  { value: "topography_elevation", label: "Topography / Elevation (HiRISE DTM)" },
  { value: "morphology_highres", label: "High-Res Morphology (HiRISE / Mastcam / MAHLI)" },
  { value: "elemental_chemistry", label: "Elemental Chemistry (ChemCam LIBS / APXS)" },
  { value: "mineralogy_xrd", label: "Crystalline XRD Mineralogy (CheMin)" },
  { value: "mineralogy_spectral", label: "Orbital SWIR Mineralogy (CRISM)" },
  { value: "volatile_organic_isotope", label: "Volatiles & Isotopes (SAM EGA/GCMS)" },
  { value: "thermal_inertia_composition", label: "Thermal Inertia (THEMIS)" },
  { value: "hydrated_neutron_subsurface", label: "Subsurface Hydration (DAN / GRS)" },
  { value: "meteorology_environment", label: "Environment / Wind / Dust (REMS / MEDA)" },
];

function stateBadgeClass(state: string): string {
  switch (state) {
    case "confirmed_local_observation":
    case "satisfied_direct":
    case "complete_constrained_plan":
    case "current":
    case "consistent_with_archive":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "orbital_detection_only":
    case "satisfied_proxy_only":
    case "extends_archive_coverage":
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-300";
    case "partial_coverage_or_resolution_limited":
    case "partial_missing_observations":
    case "inferred_regional_context_only":
    case "stale_upstream_dependency_changed":
    case "differs_from_orbital_scale_expectation":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    case "conflicting_evidence":
    case "differs_from_prior_local_measurement":
    case "infeasible_under_constraints":
    case "missing_required_data":
    case "mission_isolated_rejected":
    case "conflict_unresolved":
      return "border-rose-500/40 bg-rose-500/15 text-rose-300";
    default:
      return "border-slate-600/50 bg-slate-800/70 text-slate-300";
  }
}

export default function ScienceCampaignPage() {
  const {
    instruments,
    inferenceValidation,
    questions,
    activeQuestionId,
    discovery,
    evaluatedBatch,
    selectedStopTargetIds,
    campaigns,
    activeCampaign,
    activeLifecycle,
    freshnessReport,
    observations,
    activeComparison,
    ledger,
    loadingQuestions,
    loadingDiscovery,
    loadingTargets,
    loadingCampaign,
    loadingApprove,
    loadingFreshness,
    loadingObservations,
    loadingComparison,
    loadingProductInspect,
    inspectedProduct,
    error,
    clearError,
    setActiveQuestionId,
    toggleStopTargetId,
    setSelectedStopTargetIds,
    fetchInstruments,
    validateInference,
    fetchQuestions,
    createCustomQuestion,
    deleteCustomQuestion,
    discoverEvidence,
    inspectProductDetail,
    evaluateTargets,
    buildCampaign,
    fetchCampaigns,
    loadCampaign,
    checkFreshness,
    recomputeCampaign,
    approveCampaign,
    exportCampaignDossier,
    exportUnifiedDossier,
    recordObservation,
    fetchObservations,
    compareObservation,
    fetchIngestionLedger,
  } = useInvestigationStore();

  // Work Area A UI State
  const [showInstrumentMatrix, setShowInstrumentMatrix] = useState(false);
  const [showNewQuestionForm, setShowNewQuestionForm] = useState(false);
  const [newQTitle, setNewQTitle] = useState("");
  const [newQHypothesis, setNewQHypothesis] = useState("");
  const [newQPhenomena, setNewQPhenomena] = useState("SO3, CaO, MgO");
  const [newQClasses, setNewQClasses] = useState<MeasurementClass[]>([
    "topography_elevation",
    "morphology_highres",
    "elemental_chemistry",
  ]);
  const [newQStops, setNewQStops] = useState(3);
  const [valInstrument, setValInstrument] = useState("HIRISE");
  const [valClaim, setValClaim] = useState("Confirm gypsum composition from bright ridge tone");

  // Work Area C Filter State
  const [restrictToHiriseDem, setRestrictToHiriseDem] = useState(true);
  const [searchRadiusM, setSearchRadiusM] = useState(250);
  const [maxCandidates, setMaxCandidates] = useState(12);

  // Work Area D Campaign Builder State
  const [campaignName, setCampaignName] = useState("Mount Sharp Boxwork Field Traverse");
  const [datasetId, setDatasetId] = useState("hirise_dteec_009149_1750");
  const [startLat, setStartLat] = useState("-4.7330");
  const [startLon, setStartLon] = useState("137.4025");
  const [destLat, setDestLat] = useState("");
  const [destLon, setDestLon] = useState("");
  const [routingMode, setRoutingMode] = useState<PlanningMode>("balanced");
  const [maxSlopeDeg, setMaxSlopeDeg] = useState("22");
  const [walkingSpeedMps, setWalkingSpeedMps] = useState("0.75");
  const [durationLimitMin, setDurationLimitMin] = useState("240");
  const [returnReservePct, setReturnReservePct] = useState("25");
  const [defaultDwellMin, setDefaultDwellMin] = useState("15");
  const [suitMassKg, setSuitMassKg] = useState("120");
  const [payloadMassKg, setPayloadMassKg] = useState("15");
  const [showLedger, setShowLedger] = useState(false);
  const [show3DPreview, setShow3DPreview] = useState(false);

  // Work Area E Observation Capture State
  const [obsTargetId, setObsTargetId] = useState("");
  const [obsInstrument, setObsInstrument] = useState("CHEMCAM_LIBS");
  const [obsMeasType, setObsMeasType] = useState("elemental_oxide_wt_pct");
  const [obsSpecies, setObsSpecies] = useState("SO3");
  const [obsValue, setObsValue] = useState("12.4");
  const [obsUnits, setObsUnits] = useState("wt%");
  const [obsLat, setObsLat] = useState("-4.73429");
  const [obsLon, setObsLon] = useState("137.41166");
  const [obsNotes, setObsNotes] = useState("Fracture vein cement sample spot");
  const [compareRadiusM, setCompareRadiusM] = useState(500);

  useEffect(() => {
    void fetchInstruments(true);
    void fetchQuestions();
    void fetchCampaigns();
    void fetchObservations();
  }, [fetchInstruments, fetchQuestions, fetchCampaigns, fetchObservations]);

  const activeQuestion = useMemo(
    () => questions.find((q) => q.question_id === activeQuestionId) ?? questions[0] ?? null,
    [questions, activeQuestionId]
  );

  // Keep Work Area D start anchored safely near selected stop 0 when inside HiRISE DEM
  const handleRunTargetEval = async () => {
    const parsedLat = startLat.trim() !== "" ? Number(startLat) : NaN;
    const parsedLon = startLon.trim() !== "" ? Number(startLon) : NaN;
    const batch = await evaluateTargets({
      question_id: activeQuestionId,
      include_discovered_candidates: true,
      astronaut_latitude: Number.isFinite(parsedLat) ? parsedLat : null,
      astronaut_longitude: Number.isFinite(parsedLon) ? parsedLon : null,
      search_radius_m: searchRadiusM,
      max_candidates: maxCandidates,
      study_bounds: restrictToHiriseDem
        ? { min_lat: -4.752, max_lat: -4.706, min_lon: 137.386, max_lon: 137.433 }
        : null,
    });
    if (batch && batch.targets.length > 0 && selectedStopTargetIds.length === 0) {
      const initialIds = batch.targets
        .slice(0, Math.min(2, batch.targets.length))
        .map((t) => t.target_id);
      setSelectedStopTargetIds(initialIds);
      const first = batch.targets[0];
      setObsTargetId(first.target_id);
      setObsLat(first.latitude.toFixed(5));
      setObsLon(first.longitude_east.toFixed(5));
      setStartLat((first.latitude + 0.001).toFixed(5));
      setStartLon((first.longitude_east - 0.001).toFixed(5));
    }
  };

  const [uiValidationError, setUiValidationError] = useState<string | null>(null);

  const handleBuildCampaign = async () => {
    setUiValidationError(null);
    const parsedStartLat = Number(startLat);
    const parsedStartLon = Number(startLon);
    if (!startLat.trim() || !startLon.trim() || !Number.isFinite(parsedStartLat) || !Number.isFinite(parsedStartLon)) {
      setUiValidationError("EVA Start Latitude and Longitude (°E) must be valid numbers before building a campaign.");
      return;
    }
    const selectedObjects = (evaluatedBatch?.targets ?? []).filter((t) =>
      selectedStopTargetIds.includes(t.target_id)
    );
    const req: CampaignBuildRequest = {
      campaign_name: campaignName.trim() || "Gale Boxwork Investigation",
      question_id: activeQuestionId,
      dataset_id: datasetId,
      start: {
        lat: parsedStartLat,
        lon_east: parsedStartLon,
        label: "EVA Start",
      },
      destination:
        destLat.trim() && destLon.trim()
          ? { lat: Number(destLat), lon_east: Number(destLon), label: "EVA Destination" }
          : null,
      selected_target_ids: selectedStopTargetIds,
      candidate_targets: selectedObjects,
      routing_mode: routingMode,
      constraints: {
        max_slope_deg: Number(maxSlopeDeg) || 22,
        optimize_target_order: true,
        return_to_start: false,
      },
      walking_speed_mps: walkingSpeedMps.trim() ? Number(walkingSpeedMps) : null,
      mission_duration_limit_s: durationLimitMin.trim() ? Number(durationLimitMin) * 60 : null,
      return_reserve_fraction: returnReservePct.trim() ? Number(returnReservePct) / 100 : null,
      default_stop_dwell_s: (Number(defaultDwellMin) || 15) * 60,
      astronaut_suit_mass_kg: suitMassKg.trim() ? Number(suitMassKg) : null,
      payload_mass_kg: payloadMassKg.trim() ? Number(payloadMassKg) : null,
      include_alternatives: true,
      optimize_stop_order: true,
    };
    const plan = await buildCampaign(req);
    if (plan) {
      await fetchObservations(plan.campaign_id);
    }
  };

  const handleRecordObservation = async () => {
    setUiValidationError(null);
    const parsedObsLat = Number(obsLat);
    const parsedObsLon = Number(obsLon);
    if (!obsLat.trim() || !obsLon.trim() || !Number.isFinite(parsedObsLat) || !Number.isFinite(parsedObsLon)) {
      setUiValidationError("Observation Latitude and Longitude (°E) must be valid numbers before recording.");
      return;
    }
    const parsedNum = Number(obsValue);
    const measuredValue = Number.isFinite(parsedNum) && obsValue.trim() !== "" ? parsedNum : obsValue;
    await recordObservation({
      campaign_id: activeCampaign?.campaign_id ?? null,
      target_id: obsTargetId || null,
      instrument_id: obsInstrument,
      measurement_type: obsMeasType,
      species_or_feature: obsSpecies.trim() || "SO3",
      measured_value: measuredValue,
      units: obsUnits,
      latitude: parsedObsLat,
      longitude_east: parsedObsLon,
      notes: obsNotes || null,
    });
  };

  const handleExportDossier = async (campId: string) => {
    const dossier = await exportCampaignDossier(campId);
    if (!dossier || typeof window === "undefined") return;
    const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${campId}-dossier-p18.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportUnifiedDossier = async (campId: string) => {
    const dossier = await exportUnifiedDossier(campId);
    if (!dossier || typeof window === "undefined") return;
    const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${campId}-unified-dossier-p21.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const viewerPins: InvestigationPinMarker[] = useMemo(() => {
    const pins: InvestigationPinMarker[] = [];
    if (activeCampaign) {
      activeCampaign.stop_plans.forEach((sp) => {
        pins.push({
          id: sp.target_id,
          label: `Stop ${sp.stop_index}: ${sp.name}`,
          latitude: sp.latitude,
          longitude_east: sp.longitude_east,
          kind: "campaign_stop",
          evidence_state: sp.evidence_state,
        });
      });
    }
    observations.slice(0, 12).forEach((o) => {
      pins.push({
        id: o.observation_id,
        label: `Field Obs (${o.instrument_id}: ${o.species_or_feature})`,
        latitude: o.latitude,
        longitude_east: o.longitude_east,
        kind: "field_observation",
      });
    });
    return pins;
  }, [activeCampaign, observations]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-[#f16f4d]">
            <FlaskConical className="w-4 h-4" />
            <span>MARSCOPE Prompt 17 · Evidence-Driven Science Investigation Engine</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">
            Executable Science Campaign &amp; Multi-Instrument Target Workstation
          </h1>
          <p className="text-xs text-slate-400 max-w-3xl">
            Gale Crater / Mount Sharp investigation platform integrating 16 orbital &amp; in-situ instrument boundaries,
            validated NASA PDS indices, 7-state epistemic target classification, HiRISE terrain-routed stops, and crew
            archive comparisons. Operational planning tool only — never certified for life support.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowInstrumentMatrix((v) => !v)}
            className="px-3 py-1.5 rounded-lg border border-[#2a344c] bg-[#0d111a] hover:bg-[#161d2e] text-xs font-mono text-slate-200 flex items-center gap-1.5"
          >
            <Microscope className="w-3.5 h-3.5 text-cyan-400" />
            Instruments ({instruments.length})
          </button>
          <button
            onClick={() => {
              const next = !showLedger;
              setShowLedger(next);
              if (next) void fetchIngestionLedger(30);
            }}
            className="px-3 py-1.5 rounded-lg border border-[#2a344c] bg-[#0d111a] hover:bg-[#161d2e] text-xs font-mono text-slate-200 flex items-center gap-1.5"
          >
            <Database className="w-3.5 h-3.5 text-amber-400" />
            Acquisition Ledger
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-950/30 p-3 flex items-center justify-between text-xs text-rose-200">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            {error}
          </span>
          <button onClick={clearError} className="text-[11px] font-mono underline">
            Dismiss
          </button>
        </div>
      )}

      {uiValidationError && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-950/30 p-3 flex items-center justify-between text-xs text-amber-200">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            {uiValidationError}
          </span>
          <button onClick={() => setUiValidationError(null)} className="text-[11px] font-mono underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Optional Drawers: Instrument Capability & Ledger */}
      {showInstrumentMatrix && (
        <section className="rounded-xl border border-cyan-500/30 bg-[#0d111a] p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <Microscope className="w-4 h-4 text-cyan-400" />
              16-Instrument Measurement Capability Matrix &amp; Inference Firewall
            </h2>
            <span className="text-[10px] font-mono text-slate-400">
              Visual/Optical tones NEVER establish mineralogy · Jezero Mars 2020 quarantined from Gale
            </span>
          </div>

          {/* Interactive Inference Guard Checker */}
          <div className="rounded-lg border border-[#1e2638] bg-[#121622] p-3 grid grid-cols-1 lg:grid-cols-12 gap-2 items-center">
            <select
              value={valInstrument}
              onChange={(e) => setValInstrument(e.target.value)}
              className="lg:col-span-3 bg-[#0b0e17] border border-[#2a344c] rounded px-2.5 py-1.5 text-xs text-slate-200 font-mono"
            >
              {instruments.map((inst) => (
                <option key={inst.instrument_id} value={inst.instrument_id}>
                  {inst.instrument_id} ({inst.mission_host})
                </option>
              ))}
            </select>
            <input
              type="text"
              value={valClaim}
              onChange={(e) => setValClaim(e.target.value)}
              placeholder="Claimed scientific inference to test..."
              className="lg:col-span-6 bg-[#0b0e17] border border-[#2a344c] rounded px-2.5 py-1.5 text-xs text-slate-200"
            />
            <button
              onClick={() =>
                void validateInference({ instrument_id: valInstrument, claimed_inference: valClaim })
              }
              className="lg:col-span-3 px-3 py-1.5 rounded bg-cyan-500/20 border border-cyan-500/40 hover:bg-cyan-500/30 text-xs font-mono font-semibold text-cyan-200"
            >
              Validate Inference Boundary
            </button>
          </div>
          {inferenceValidation && (
            <div
              className={`rounded-lg border p-3 text-xs flex items-start gap-2 ${
                inferenceValidation.allowed
                  ? "border-emerald-500/40 bg-emerald-950/20 text-emerald-200"
                  : "border-rose-500/40 bg-rose-950/30 text-rose-200"
              }`}
            >
              {inferenceValidation.allowed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-mono font-bold">
                  {inferenceValidation.instrument_id} · {inferenceValidation.classification} (
                  {inferenceValidation.allowed ? "ALLOWED" : "PROHIBITED"})
                </div>
                <div className="text-[11px] opacity-90 mt-0.5">{inferenceValidation.rationale}</div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2.5 max-h-80 overflow-y-auto pr-1">
            {instruments.map((inst) => (
              <div
                key={inst.instrument_id}
                className={`rounded-lg border p-2.5 text-[11px] space-y-1.5 ${
                  inst.mission_isolated_from_gale
                    ? "border-rose-500/40 bg-rose-950/15"
                    : "border-[#1e2638] bg-[#121622]"
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-mono font-bold text-white">{inst.instrument_id}</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                    {inst.typical_spatial_scale_m != null
                      ? `~${inst.typical_spatial_scale_m} m`
                      : "Product-specific"} · {inst.verification_status ?? "VERIFIED"}
                  </span>
                </div>
                <div className="text-[10px] text-slate-400">
                  {inst.mission_host} · {inst.platform_kind} · {inst.measurement_class}
                </div>
                {inst.mission_isolated_from_gale && (
                  <div className="text-[10px] font-mono text-rose-300 font-semibold">
                    ISOLATED (Jezero Crater — excluded from Gale)
                  </div>
                )}
                <div className="text-[10px] text-amber-300/90">
                  Prohibited: {inst.prohibited_inferences[0] ?? "N/A"}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {showLedger && ledger && (
        <section className="rounded-xl border border-amber-500/30 bg-[#0d111a] p-4 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-white">
              Part 9 Acquisition &amp; Query Provenance Ledger (DISCOVERED != ACQUIRED != VALIDATED)
            </h2>
            <span className="text-[10px] font-mono text-amber-300">
              {ledger.acquisition_ledger.length} download events · {ledger.query_provenance.length} archive queries
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-48 overflow-y-auto text-[11px] font-mono">
            <div className="bg-[#121622] border border-[#1e2638] rounded p-2.5 space-y-1">
              <div className="text-slate-400">Recent Acquisition Events</div>
              {ledger.acquisition_ledger.length === 0 ? (
                <div className="text-slate-500">No download ledger writes in active session.</div>
              ) : (
                ledger.acquisition_ledger.slice(-8).map((ev, i) => (
                  <div key={i} className="text-slate-300 truncate">
                    {JSON.stringify(ev)}
                  </div>
                ))
              )}
            </div>
            <div className="bg-[#121622] border border-[#1e2638] rounded p-2.5 space-y-1">
              <div className="text-slate-400">Recent External Archive Queries</div>
              {ledger.query_provenance.length === 0 ? (
                <div className="text-slate-500">No ODE/NASA API queries recorded yet.</div>
              ) : (
                ledger.query_provenance.slice(-8).map((q, i) => (
                  <div key={i} className="text-slate-300 truncate">
                    {JSON.stringify(q)}
                  </div>
                ))
              )}
            </div>
          </div>
        </section>
      )}

      {/* =================================================================== */}
      {/* WORK AREA A — SCIENTIFIC QUESTION SELECTION & CUSTOM CREATION       */}
      {/* =================================================================== */}
      <section className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Work Area A</div>
            <h2 className="text-base font-bold text-white">
              Scientific Question Selection &amp; Measurement Requirements
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowNewQuestionForm((v) => !v)}
              className="px-3 py-1.5 rounded-lg border border-[#e25b38]/40 bg-[#e25b38]/15 hover:bg-[#e25b38]/25 text-xs font-semibold text-[#f16f4d] flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              Create Custom Question
            </button>
            <button
              onClick={() => void discoverEvidence(activeQuestionId)}
              disabled={loadingDiscovery || !activeQuestionId}
              className="px-3.5 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#d14c29] disabled:opacity-50 text-xs font-semibold text-white flex items-center gap-1.5"
            >
              <Compass className="w-3.5 h-3.5" />
              {loadingDiscovery ? "Discovering..." : "Discover Question Evidence"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-5 space-y-2 max-h-72 overflow-y-auto pr-1">
            {loadingQuestions && <div className="text-xs text-slate-400">Loading questions...</div>}
            {questions.map((q) => {
              const selected = q.question_id === activeQuestionId;
              return (
                <div
                  key={q.question_id}
                  onClick={() => setActiveQuestionId(q.question_id)}
                  className={`cursor-pointer rounded-lg border p-3 transition space-y-1 ${
                    selected
                      ? "border-[#e25b38] bg-[#e25b38]/10"
                      : "border-[#1e2638] bg-[#0d111a] hover:border-slate-600"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-bold text-white">{q.title}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      <span
                        className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${
                          q.is_user_defined
                            ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                            : "border-slate-600 bg-slate-800 text-slate-300"
                        }`}
                      >
                        {q.is_user_defined ? "USER_DEFINED" : "CURATED"}
                      </span>
                      {q.is_user_defined && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            void deleteCustomQuestion(q.question_id);
                          }}
                          title="Delete custom question"
                          className="p-1 text-slate-400 hover:text-rose-400"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="text-[10px] font-mono text-slate-400">
                    {q.study_region} · {q.required_measurement_specs.length} measurement specs
                  </div>
                </div>
              );
            })}
          </div>

          <div className="lg:col-span-7 rounded-lg border border-[#1e2638] bg-[#0d111a] p-4 space-y-3 text-xs">
            {activeQuestion ? (
              <>
                <div>
                  <div className="text-[10px] font-mono text-[#f16f4d] uppercase">Hypothesis</div>
                  <div className="text-slate-200 leading-relaxed mt-0.5">{activeQuestion.hypothesis}</div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-400">Geological Setting: </span>
                    <span className="text-slate-200">{activeQuestion.geological_setting}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Target Phenomena: </span>
                    <span className="font-mono text-cyan-300">
                      {activeQuestion.target_phenomena.join(", ")}
                    </span>
                  </div>
                </div>
                <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2 text-[11px] text-amber-200">
                  <strong>Minimum Evidence Standard:</strong> {activeQuestion.minimum_evidence_note}
                </div>
                {(activeQuestion.competing_hypotheses?.length ||
                  activeQuestion.alternative_explanations?.length ||
                  activeQuestion.contradicting_evidence_criteria?.length ||
                  activeQuestion.unresolved_assumptions?.length) ? (
                  <div className="rounded border border-[#1e2638] bg-[#121622] p-2.5 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                    {activeQuestion.competing_hypotheses && activeQuestion.competing_hypotheses.length > 0 && (
                      <div>
                        <span className="font-semibold text-amber-200">Competing Hypotheses: </span>
                        <span className="text-slate-300">{activeQuestion.competing_hypotheses.join(" · ")}</span>
                      </div>
                    )}
                    {activeQuestion.alternative_explanations && activeQuestion.alternative_explanations.length > 0 && (
                      <div>
                        <span className="font-semibold text-cyan-200">Alternative Explanations: </span>
                        <span className="text-slate-300">{activeQuestion.alternative_explanations.join(" · ")}</span>
                      </div>
                    )}
                    {activeQuestion.contradicting_evidence_criteria &&
                      activeQuestion.contradicting_evidence_criteria.length > 0 && (
                        <div>
                          <span className="font-semibold text-rose-200">Contradicting Criteria: </span>
                          <span className="text-slate-300">
                            {activeQuestion.contradicting_evidence_criteria.join(" · ")}
                          </span>
                        </div>
                      )}
                    {activeQuestion.unresolved_assumptions && activeQuestion.unresolved_assumptions.length > 0 && (
                      <div>
                        <span className="font-semibold text-slate-200">Unresolved Assumptions: </span>
                        <span className="text-slate-400">{activeQuestion.unresolved_assumptions.join(" · ")}</span>
                      </div>
                    )}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-slate-400">Select a scientific question to inspect requirements.</div>
            )}
          </div>
        </div>

        {showNewQuestionForm && (
          <div className="rounded-lg border border-cyan-500/30 bg-[#0d111a] p-4 space-y-3 text-xs">
            <div className="font-bold text-white">New USER_DEFINED Investigation Question</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                type="text"
                value={newQTitle}
                onChange={(e) => setNewQTitle(e.target.value)}
                placeholder="Question title (e.g. Sulfated Vein Cement Diagenesis)"
                className="bg-[#121622] border border-[#2a344c] rounded px-3 py-2 text-slate-100"
              />
              <input
                type="text"
                value={newQPhenomena}
                onChange={(e) => setNewQPhenomena(e.target.value)}
                placeholder="Target species/phenomena (comma-separated)"
                className="bg-[#121622] border border-[#2a344c] rounded px-3 py-2 text-slate-100 font-mono"
              />
            </div>
            <textarea
              value={newQHypothesis}
              onChange={(e) => setNewQHypothesis(e.target.value)}
              rows={2}
              placeholder="Testable planetary science hypothesis..."
              className="w-full bg-[#121622] border border-[#2a344c] rounded px-3 py-2 text-slate-100"
            />
            <div className="flex flex-wrap gap-2">
              {MEASUREMENT_CLASS_OPTIONS.map((opt) => {
                const checked = newQClasses.includes(opt.value);
                return (
                  <label
                    key={opt.value}
                    className={`cursor-pointer px-2.5 py-1 rounded border text-[11px] flex items-center gap-1.5 ${
                      checked
                        ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-200"
                        : "border-[#2a344c] bg-[#121622] text-slate-400"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        setNewQClasses((prev) =>
                          prev.includes(opt.value)
                            ? prev.filter((x) => x !== opt.value)
                            : [...prev, opt.value]
                        )
                      }
                      className="accent-cyan-500"
                    />
                    {opt.label}
                  </label>
                );
              })}
            </div>
            <div className="flex items-center justify-between pt-1">
              <div className="flex items-center gap-2 text-[11px] text-slate-300">
                <span>Preferred Stops:</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={newQStops}
                  onChange={(e) => setNewQStops(Number(e.target.value) || 2)}
                  className="w-16 bg-[#121622] border border-[#2a344c] rounded px-2 py-1 font-mono"
                />
              </div>
              <button
                onClick={async () => {
                  const res = await createCustomQuestion({
                    title: newQTitle,
                    hypothesis: newQHypothesis,
                    target_phenomena: newQPhenomena
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                    required_measurement_classes: newQClasses,
                    preferred_stop_count: newQStops,
                  });
                  if (res) {
                    setShowNewQuestionForm(false);
                    setNewQTitle("");
                    setNewQHypothesis("");
                  }
                }}
                disabled={newQTitle.trim().length < 4 || newQHypothesis.trim().length < 8}
                className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 font-semibold text-white"
              >
                Save &amp; Select Question
              </button>
            </div>
          </div>
        )}
      </section>

      {/* =================================================================== */}
      {/* WORK AREA B — EVIDENCE DISCOVERY & DATA GAP MATRIX                  */}
      {/* =================================================================== */}
      {discovery && (
        <section className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Work Area B</div>
              <h2 className="text-base font-bold text-white">
                Multi-Instrument Evidence Discovery &amp; Explicit Data Gaps
              </h2>
            </div>
            <span className="px-2.5 py-1 rounded border border-amber-500/40 bg-amber-500/15 font-mono text-[11px] text-amber-200">
              {discovery.overall_evidence_readiness}
            </span>
          </div>

          {discovery.evidence_synthesis && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-[11px] font-mono">
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">DIRECT ELIGIBLE</div>
                <div className="text-sm font-bold text-emerald-300">
                  {discovery.evidence_synthesis.eligible_direct_count}
                </div>
              </div>
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">SUPPORTING</div>
                <div className="text-sm font-bold text-cyan-300">
                  {discovery.evidence_synthesis.eligible_supporting_count}
                </div>
              </div>
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">LIMITED / INDIRECT</div>
                <div className="text-sm font-bold text-amber-200">
                  {discovery.evidence_synthesis.limited_or_indirect_count}
                </div>
              </div>
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">CONTRADICTING</div>
                <div className="text-sm font-bold text-rose-300">
                  {discovery.evidence_synthesis.contradicting_count}
                </div>
              </div>
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">INDEP / DUPES</div>
                <div className="text-sm font-bold text-slate-200">
                  {discovery.evidence_synthesis.independent_record_count} /{" "}
                  {discovery.evidence_synthesis.duplicate_count}
                </div>
              </div>
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-2">
                <div className="text-[9px] text-slate-400">REJECTED / INELIG</div>
                <div className="text-sm font-bold text-slate-300">
                  {discovery.evidence_synthesis.ineligible_or_rejected_count}
                </div>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] border-collapse">
              <thead>
                <tr className="border-b border-[#1e2638] text-slate-400 font-mono">
                  <th className="py-2 pr-3">Requirement</th>
                  <th className="py-2 pr-3">Class</th>
                  <th className="py-2 pr-3">Essential</th>
                  <th className="py-2 pr-3">State / Canonical</th>
                  <th className="py-2 pr-3">Instruments</th>
                  <th className="py-2">Limitations, Threshold Class &amp; Resolution Path</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e2638]">
                {discovery.requirements_evaluation.map((req) => (
                  <tr key={req.requirement_id} className="text-slate-300 align-top">
                    <td className="py-2 pr-3 font-semibold text-white">
                      {req.label}
                      {req.required_spatial_scale_m != null && (
                        <div className="text-[10px] font-mono text-slate-400">
                          Req scale: &le;{req.required_spatial_scale_m} m
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 font-mono text-cyan-300">{req.measurement_class}</td>
                    <td className="py-2 pr-3 font-mono">{req.essential ? "YES" : "OPTIONAL"}</td>
                    <td className="py-2 pr-3 space-y-1">
                      <span
                        className={`inline-block px-2 py-0.5 rounded border font-mono text-[10px] ${stateBadgeClass(
                          req.fulfillment_state
                        )}`}
                      >
                        {req.fulfillment_state}
                      </span>
                      {req.canonical_state && (
                        <div className="text-[10px] font-mono text-slate-400">
                          Canonical: {req.canonical_state}
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 font-mono">
                      {req.satisfying_instruments.length > 0 ? req.satisfying_instruments.join(", ") : "None"}
                    </td>
                    <td className="py-2 text-slate-400 space-y-0.5">
                      <div>{req.limitations_and_gaps[0] || req.prohibited_substitutions[0] || "—"}</div>
                      {(req.threshold_rule_classification || req.coverage_status || req.quality_status) && (
                        <div className="text-[10px] font-mono text-slate-500">
                          {req.threshold_rule_classification ? `Threshold: ${req.threshold_rule_classification} · ` : ""}
                          {req.coverage_status ? `Cov: ${req.coverage_status} · ` : ""}
                          {req.quality_status ? `Qual: ${req.quality_status}` : ""}
                        </div>
                      )}
                      {req.resolution_path && req.resolution_path.length > 0 && (
                        <div className="text-[10px] text-cyan-300">Next: {req.resolution_path[0]}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {discovery.matched_records.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-bold text-slate-200">
                Evaluated Evidence Products &amp; 17-Dimension Eligibility ({discovery.matched_records.length})
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-64 overflow-y-auto pr-1 text-[11px]">
                {discovery.matched_records.map((rec) => (
                  <div
                    key={rec.match_id}
                    className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-2.5 space-y-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-bold text-white truncate">
                        {rec.instrument_id} · {rec.product_id || rec.source_id}
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {rec.eligibility_state && (
                          <span
                            className={`px-1.5 py-0.5 rounded border font-mono text-[9px] uppercase ${stateBadgeClass(
                              rec.eligibility_state
                            )}`}
                          >
                            {rec.eligibility_state}
                          </span>
                        )}
                        {rec.source_type === "dataset" && (
                          <button
                            type="button"
                            onClick={() => void inspectProductDetail(rec.source_id, activeQuestionId)}
                            disabled={loadingProductInspect}
                            className="px-2 py-0.5 rounded border border-cyan-500/40 bg-cyan-500/10 text-[9px] font-mono text-cyan-200 hover:bg-cyan-500/20"
                          >
                            Inspect Product
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">
                      Role: {rec.evidence_role || "supporting"} · Reg:{" "}
                      {rec.spatial_registration_state || "unknown"} · Res:{" "}
                      {rec.product_spatial_resolution_m != null
                        ? `${rec.product_spatial_resolution_m} m`
                        : rec.spatial_scale_m != null
                        ? `${rec.spatial_scale_m} m`
                        : "Unstated"}
                      {rec.duplication_or_correlation?.is_duplicate ? " · DUPLICATE NON-INDEPENDENT" : ""}
                    </div>
                    {rec.product_limitations && rec.product_limitations[0] && (
                      <div className="text-[10px] text-amber-200/90 truncate" title={rec.product_limitations[0]}>
                        Limit: {rec.product_limitations[0]}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {inspectedProduct && (
            <div className="rounded-lg border border-cyan-500/40 bg-[#0d111a] p-3.5 space-y-2 text-[11px]">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-bold text-cyan-200">
                  Product Integrity &amp; 17-Dimension Audit: {inspectedProduct.dataset.product_id} (
                  {inspectedProduct.dataset.id})
                </div>
                <span className="font-mono text-[10px] text-slate-300">
                  Acq: {inspectedProduct.dataset.acquisition_state || inspectedProduct.dataset.status} · Eligibility:{" "}
                  {inspectedProduct.eligibility_state} · Reg: {inspectedProduct.spatial_registration_state}
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-400">
                CRS: {inspectedProduct.dataset.coordinate_reference_system || "Unknown"} · Units:{" "}
                {inspectedProduct.dataset.units} · Level: {inspectedProduct.dataset.processing_level} · Calibration:{" "}
                {inspectedProduct.dataset.calibration_status} · SHA-256:{" "}
                {inspectedProduct.dataset.sha256_checksum || "None"}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-1.5 max-h-48 overflow-y-auto">
                {inspectedProduct.eligibility_dimensions.map((d) => (
                  <div key={d.dimension} className="rounded border border-[#1e2638] bg-[#121622] px-2 py-1 text-[10px]">
                    <div className="flex items-center justify-between font-mono">
                      <span className="text-slate-200 font-semibold">{d.dimension}</span>
                      <span className="text-cyan-300">{d.status}</span>
                    </div>
                    <div className="text-slate-400">{d.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-lg border border-amber-500/30 bg-[#0d111a] p-3 space-y-1.5">
              <div className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" />
                Critical Data Gaps &amp; Unresolved Spectral Constraints ({discovery.critical_data_gaps.length})
              </div>
              <ul className="space-y-1 text-[11px] text-slate-300 list-disc list-inside">
                {discovery.critical_data_gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>

            <div className="rounded-lg border border-rose-500/35 bg-rose-950/15 p-3 space-y-1.5">
              <div className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5" />
                Strict Mission Isolation Quarantine ({discovery.isolated_or_rejected_records.length})
              </div>
              {discovery.isolated_or_rejected_records.length === 0 ? (
                <div className="text-[11px] text-slate-400">No out-of-region datasets detected.</div>
              ) : (
                <div className="space-y-1.5 max-h-32 overflow-y-auto text-[11px]">
                  {discovery.isolated_or_rejected_records.map((rec) => (
                    <div key={rec.match_id} className="border-b border-rose-500/20 pb-1">
                      <span className="font-mono font-bold text-rose-200">{rec.instrument_id}</span>{" "}
                      <span className="text-slate-400">({rec.study_region}): </span>
                      <span className="text-rose-200/90">{rec.rejected_for_gale_reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* =================================================================== */}
      {/* WORK AREA C — 7-STATE TARGET EVALUATION & STOP SELECTION            */}
      {/* =================================================================== */}
      <section className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Work Area C</div>
            <h2 className="text-base font-bold text-white">
              7-State Target Evidence Evaluation &amp; Stop Selection
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1.5 text-slate-300 font-mono">
              <input
                type="checkbox"
                checked={restrictToHiriseDem}
                onChange={(e) => setRestrictToHiriseDem(e.target.checked)}
                className="accent-[#e25b38]"
              />
              Inside 1 m HiRISE DEM Bounds
            </label>
            <div className="flex items-center gap-1.5 font-mono text-slate-300">
              <span>Radius m:</span>
              <input
                type="number"
                value={searchRadiusM}
                onChange={(e) => setSearchRadiusM(Number(e.target.value) || 250)}
                className="w-16 bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1"
              />
            </div>
            <div className="flex items-center gap-1.5 font-mono text-slate-300">
              <span>Max:</span>
              <input
                type="number"
                value={maxCandidates}
                onChange={(e) => setMaxCandidates(Number(e.target.value) || 12)}
                className="w-14 bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1"
              />
            </div>
            <button
              onClick={() => void handleRunTargetEval()}
              disabled={loadingTargets}
              className="px-3.5 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#d14c29] disabled:opacity-50 font-semibold text-white"
            >
              {loadingTargets ? "Evaluating..." : "Evaluate Gale Targets"}
            </button>
          </div>
        </div>

        {evaluatedBatch && (
          <div className="space-y-3">
            <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-200 flex flex-wrap items-center justify-between gap-2">
              <span>{evaluatedBatch.prioritization_disclaimer}</span>
              <span className="font-mono text-cyan-300">
                Selected Stops: {selectedStopTargetIds.length}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[34rem] overflow-y-auto pr-1">
              {evaluatedBatch.targets.map((tgt) => {
                const checked = selectedStopTargetIds.includes(tgt.target_id);
                return (
                  <div
                    key={tgt.target_id}
                    className={`rounded-lg border p-3.5 space-y-2 transition ${
                      checked
                        ? "border-cyan-400/70 bg-cyan-950/15"
                        : "border-[#1e2638] bg-[#0d111a]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <label className="flex items-start gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleStopTargetId(tgt.target_id)}
                          className="mt-1 accent-cyan-400"
                        />
                        <div>
                          <div className="text-xs font-bold text-white">{tgt.name}</div>
                          <div className="text-[10px] font-mono text-slate-400">
                            {tgt.latitude.toFixed(5)}°, {tgt.longitude_east.toFixed(5)}°E ·{" "}
                            {tgt.distinct_instruments.join(", ") || "No instrument"}
                          </div>
                        </div>
                      </label>
                      <span
                        className={`px-2 py-0.5 rounded border font-mono text-[9px] uppercase shrink-0 ${stateBadgeClass(
                          tgt.evidence_state
                        )}`}
                      >
                        {tgt.evidence_state}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-amber-200">
                        Heuristic Priority:{" "}
                        {tgt.heuristic_priority_score != null
                          ? tgt.heuristic_priority_score.toFixed(3)
                          : "Unprioritized"}{" "}
                        (is_heuristic=
                        {String(tgt.prioritization_is_heuristic)})
                      </span>
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        Sampling: {tgt.eligibility_for_sampling}
                      </span>
                      {tgt.eligibility_decision && (
                        <span className="px-1.5 py-0.5 rounded bg-cyan-950/50 border border-cyan-500/30 text-cyan-200">
                          {tgt.eligibility_decision}
                        </span>
                      )}
                      {tgt.scientific_confidence_state && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">
                          {tgt.scientific_confidence_state}
                        </span>
                      )}
                      {tgt.spatial_registration_state && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-400">
                          Reg: {tgt.spatial_registration_state}
                        </span>
                      )}
                      {tgt.spatial_coverage_category && (
                        <span className="px-1.5 py-0.5 rounded bg-indigo-950/50 border border-indigo-500/30 text-indigo-200">
                          Cov: {tgt.spatial_coverage_category}
                        </span>
                      )}
                      {tgt.terrain_slope_deg != null && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 text-cyan-200">
                          Elev: {tgt.terrain_elevation_m != null ? `${tgt.terrain_elevation_m.toFixed(1)}m` : "—"} · Slope: {tgt.terrain_slope_deg.toFixed(1)}°
                        </span>
                      )}
                      {tgt.morphology_review_status && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 text-amber-200">
                          Morph: {tgt.morphology_review_status}
                        </span>
                      )}
                    </div>

                    {tgt.known_facts[0] && (
                      <div className="text-[11px] text-emerald-300/90">
                        <strong>Known:</strong> {tgt.known_facts[0]}
                      </div>
                    )}
                    {tgt.unknowns_and_gaps[0] && (
                      <div className="text-[11px] text-amber-200/90">
                        <strong>Unknown / Gap:</strong> {tgt.unknowns_and_gaps[0]}
                      </div>
                    )}
                    {tgt.conflicting_records.length > 0 && (
                      <div className="text-[11px] text-rose-300">
                        <strong>Conflict:</strong> {tgt.conflicting_records[0]}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {evaluatedBatch.rejected_targets && evaluatedBatch.rejected_targets.length > 0 && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-950/15 p-3 space-y-1.5 text-[11px]">
                <div className="font-bold text-rose-200">
                  Rejected / Ineligible Targets ({evaluatedBatch.rejected_targets.length})
                </div>
                {evaluatedBatch.rejected_targets.map((rt) => (
                  <div key={rt.target_id} className="text-rose-200/90 font-mono">
                    {rt.name}: {rt.eligibility_decision || "REJECTED"} —{" "}
                    {rt.eligibility_decision_rationale || rt.unknowns_and_gaps[0] || "Missing eligible evidence"}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* =================================================================== */}
      {/* WORK AREA D — EXECUTABLE CAMPAIGN BUILDER, ALTERNATIVES & 3D VIEW   */}
      {/* =================================================================== */}
      <section className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Work Area D</div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <RouteIcon className="w-4 h-4 text-[#e25b38]" />
              Executable Multi-Stop Traverse, Return Check &amp; Protocol Planner
            </h2>
          </div>

          {campaigns.length > 0 && (
            <select
              value={activeCampaign?.campaign_id ?? ""}
              onChange={(e) => e.target.value && void loadCampaign(e.target.value)}
              className="bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-xs font-mono text-slate-200"
            >
              <option value="">Load Saved Campaign ({campaigns.length})...</option>
              {campaigns.map((c) => (
                <option key={c.campaign_id} value={c.campaign_id}>
                  {c.campaign_name} ({c.stop_count} stops · {c.freshness_state})
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Campaign Builder Config Form */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2.5 text-xs">
          <div className="col-span-2">
            <label className="block text-[10px] text-slate-400 mb-1">Campaign Name</label>
            <input
              type="text"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Terrain DEM ID</label>
            <input
              type="text"
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Routing Policy</label>
            <select
              value={routingMode}
              onChange={(e) => setRoutingMode(e.target.value as PlanningMode)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            >
              <option value="balanced">balanced</option>
              <option value="conservative">conservative</option>
              <option value="science_priority">science_priority</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Start Lat (°N)</label>
            <input
              type="text"
              value={startLat}
              onChange={(e) => setStartLat(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Start Lon (°E)</label>
            <input
              type="text"
              value={startLon}
              onChange={(e) => setStartLon(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>

          <div>
            <label className="block text-[10px] text-slate-400 mb-1">End Lat (opt)</label>
            <input
              type="text"
              value={destLat}
              onChange={(e) => setDestLat(e.target.value)}
              placeholder="last stop"
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">End Lon (opt)</label>
            <input
              type="text"
              value={destLon}
              onChange={(e) => setDestLon(e.target.value)}
              placeholder="last stop"
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Max Slope (°)</label>
            <input
              type="text"
              value={maxSlopeDeg}
              onChange={(e) => setMaxSlopeDeg(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Walk Speed (m/s)</label>
            <input
              type="text"
              value={walkingSpeedMps}
              onChange={(e) => setWalkingSpeedMps(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Time Limit (min)</label>
            <input
              type="text"
              value={durationLimitMin}
              onChange={(e) => setDurationLimitMin(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Return Res (%)</label>
            <input
              type="text"
              value={returnReservePct}
              onChange={(e) => setReturnReservePct(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>

          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Stop Dwell (min)</label>
            <input
              type="text"
              value={defaultDwellMin}
              onChange={(e) => setDefaultDwellMin(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Suit Mass (kg)</label>
            <input
              type="text"
              value={suitMassKg}
              onChange={(e) => setSuitMassKg(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Payload (kg)</label>
            <input
              type="text"
              value={payloadMassKg}
              onChange={(e) => setPayloadMassKg(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2.5 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div className="col-span-3 flex items-end justify-end gap-2">
            <button
              onClick={() => void handleBuildCampaign()}
              disabled={loadingCampaign}
              className="px-4 py-2 rounded-lg bg-[#e25b38] hover:bg-[#d14c29] disabled:opacity-50 font-semibold text-white"
            >
              {loadingCampaign
                ? "Computing Route & Protocols..."
                : `Build Campaign (${selectedStopTargetIds.length} stops)`}
            </button>
          </div>
        </div>

        {activeCampaign && (
          <div className="space-y-4 pt-2 border-t border-[#1e2638]">
            {/* Campaign Status & Freshness Bar */}
            <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-mono font-bold text-white">
                  {activeCampaign.campaign_id} · v{activeCampaign.plan_version ?? 1}
                </span>
                <span className="px-2 py-0.5 rounded border border-cyan-500/40 bg-cyan-500/15 font-mono text-[10px] uppercase text-cyan-200">
                  {activeLifecycle?.integrated_lifecycle_state ??
                    activeCampaign.integrated_lifecycle_state ??
                    "EVA_OPERATIONAL_EVALUATION"}
                </span>
                {activeCampaign.linked_mission_id && (
                  <Link
                    href={`/mission-readiness?missionId=${encodeURIComponent(
                      activeCampaign.linked_mission_id
                    )}&campaignId=${encodeURIComponent(activeCampaign.campaign_id)}`}
                    className="px-2 py-0.5 rounded border border-indigo-500/40 bg-indigo-500/15 hover:bg-indigo-500/25 font-mono text-[10px] text-indigo-200"
                  >
                    Linked EVA: {activeCampaign.linked_mission_id} →
                  </Link>
                )}
                {activeCampaign.operator_approved ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/15 font-mono text-[10px] text-emerald-200">
                    <CheckCircle2 className="w-3 h-3" />
                    APPROVED ({activeCampaign.operator_approved_by ?? "operator"})
                  </span>
                ) : (
                  <button
                    onClick={() => void approveCampaign(activeCampaign.campaign_id)}
                    disabled={loadingApprove}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/20 hover:bg-emerald-500/30 font-mono text-[10px] text-emerald-200 disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    {loadingApprove ? "Approving..." : "Operator Approve"}
                  </button>
                )}
                <span
                  className={`px-2 py-0.5 rounded border font-mono text-[10px] uppercase ${stateBadgeClass(
                    activeCampaign.plan_status
                  )}`}
                >
                  {activeCampaign.plan_status}
                </span>
                <span
                  className={`px-2 py-0.5 rounded border font-mono text-[10px] uppercase ${stateBadgeClass(
                    activeCampaign.freshness_state
                  )}`}
                >
                  {activeCampaign.freshness_state}
                </span>
                {activeCampaign.feasibility_state && (
                  <span
                    className={`px-2 py-0.5 rounded border font-mono text-[10px] uppercase ${stateBadgeClass(
                      activeCampaign.feasibility_state
                    )}`}
                  >
                    Feasibility: {activeCampaign.feasibility_state}
                  </span>
                )}
                <span className="px-2 py-0.5 rounded border border-rose-500/30 bg-rose-950/20 font-mono text-[10px] text-rose-200">
                  NOT SAFETY CERTIFIED ({activeCampaign.data_classification})
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setShow3DPreview((v) => !v)}
                  className="px-2.5 py-1 rounded border border-cyan-500/40 bg-cyan-500/10 text-xs font-mono text-cyan-200 flex items-center gap-1"
                >
                  <Layers className="w-3.5 h-3.5" />
                  {show3DPreview ? "Hide 3D Terrain" : "Preview 3D Traverse"}
                </button>
                <button
                  onClick={() => void checkFreshness(activeCampaign.campaign_id)}
                  disabled={loadingFreshness}
                  className="px-2.5 py-1 rounded border border-[#2a344c] bg-[#121622] text-xs font-mono text-slate-200 flex items-center gap-1"
                >
                  <RefreshCw className={`w-3 h-3 ${loadingFreshness ? "animate-spin" : ""}`} />
                  Check Freshness
                </button>
                <button
                  onClick={() => void recomputeCampaign(activeCampaign.campaign_id)}
                  disabled={loadingCampaign}
                  className="px-2.5 py-1 rounded border border-amber-500/40 bg-amber-500/15 text-xs font-mono text-amber-200"
                >
                  Recompute Plan
                </button>
                <button
                  onClick={() => void handleExportDossier(activeCampaign.campaign_id)}
                  className="px-2.5 py-1 rounded border border-emerald-500/40 bg-emerald-500/15 text-xs font-mono text-emerald-200"
                >
                  Export Dossier (JSON)
                </button>
                <button
                  onClick={() => void handleExportUnifiedDossier(activeCampaign.campaign_id)}
                  className="px-2.5 py-1 rounded border border-indigo-500/40 bg-indigo-500/15 text-xs font-mono text-indigo-200"
                >
                  Unified Dossier (P21)
                </button>
              </div>
            </div>

            {activeCampaign.survivability_disclaimer && (
              <div className="rounded-lg border border-rose-500/30 bg-rose-950/20 px-3 py-2 text-[11px] text-rose-200">
                {activeCampaign.survivability_disclaimer}
              </div>
            )}

            {activeCampaign.freshness_state === "stale_upstream_dependency_changed" && (
              <div className="rounded-lg border border-amber-500/40 bg-amber-950/25 p-3 text-xs text-amber-200">
                <strong>Staleness Detected:</strong>{" "}
                {(freshnessReport?.staleness_reasons ?? activeCampaign.staleness_reasons).join(" · ")}
              </div>
            )}

            {((activeCampaign.hypothesis_reassessments?.length ?? 0) > 0 ||
              (activeCampaign.linked_invalidation_events?.length ?? 0) > 0) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-[11px]">
                {(activeCampaign.hypothesis_reassessments?.length ?? 0) > 0 && (
                  <div className="rounded-lg border border-cyan-500/30 bg-cyan-950/15 p-3 space-y-1.5">
                    <div className="font-bold text-cyan-200">
                      Hypothesis Reassessments ({activeCampaign.hypothesis_reassessments?.length ?? 0})
                    </div>
                    {(activeCampaign.hypothesis_reassessments ?? []).slice(0, 5).map((hr) => (
                      <div key={hr.reassessment_id} className="font-mono text-[10px] text-slate-300 border-b border-cyan-900/40 pb-1">
                        <span className="text-cyan-300">{hr.outcome}</span>: {hr.hypothesis_impact}
                      </div>
                    ))}
                  </div>
                )}
                {(activeCampaign.linked_invalidation_events?.length ?? 0) > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-950/15 p-3 space-y-1.5">
                    <div className="font-bold text-amber-200">
                      Cross-Subsystem Invalidation Events ({activeCampaign.linked_invalidation_events?.length ?? 0})
                    </div>
                    {(activeCampaign.linked_invalidation_events ?? []).slice(0, 5).map((ie) => (
                      <div key={ie.invalidation_id} className="font-mono text-[10px] text-slate-300 border-b border-amber-900/40 pb-1">
                        <span className="text-amber-300">[{ie.source_subsystem}] {ie.event_type}</span>: {ie.detail}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {show3DPreview && (
              <div className="h-[26rem] rounded-xl overflow-hidden border border-[#1e2638]">
                <LocalTerrain3DViewer
                  compact
                  investigationPins={viewerPins}
                  campaignRouteVertices={activeCampaign.outbound_vertices}
                />
              </div>
            )}

            {/* Key Metrics Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
              <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3">
                <div className="text-[10px] text-slate-400">Outbound Multi-Stop</div>
                <div className="text-sm font-bold text-white mt-0.5">
                  {activeCampaign.outbound_route_summary?.surface_distance_m != null
                    ? `${Number(activeCampaign.outbound_route_summary.surface_distance_m).toFixed(1)} m`
                    : "UNAVAILABLE"}
                </div>
                <div className="text-[10px] text-slate-400">
                  Max Slope:{" "}
                  {activeCampaign.outbound_route_summary?.max_slope_deg != null
                    ? `${Number(activeCampaign.outbound_route_summary.max_slope_deg).toFixed(1)}°`
                    : "—"}
                </div>
              </div>
              <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3">
                <div className="text-[10px] text-slate-400">Independent Return</div>
                <div className="text-sm font-bold text-white mt-0.5">
                  {activeCampaign.return_plan?.return_route_computed
                    ? `${activeCampaign.return_plan.return_surface_distance_m.toFixed(1)} m`
                    : "NOT COMPUTED"}
                </div>
                <div className="text-[10px] text-slate-400">
                  {activeCampaign.return_plan?.return_status ?? "No return check"}
                </div>
              </div>
              <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3">
                <div className="text-[10px] text-slate-400">EVA Envelope</div>
                <div className="text-sm font-bold text-white mt-0.5">
                  {activeCampaign.eva_envelope?.envelope_status ?? "INCOMPLETE"}
                </div>
                <div className="text-[10px] text-slate-400">
                  Req:{" "}
                  {activeCampaign.eva_envelope?.time_budget?.total_required_s != null
                    ? `${(activeCampaign.eva_envelope.time_budget.total_required_s / 60).toFixed(1)} min`
                    : "—"}
                </div>
              </div>
              <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3">
                <div className="text-[10px] text-slate-400">Unconfigured Inputs</div>
                <div className="text-sm font-bold text-amber-200 mt-0.5">
                  {activeCampaign.missing_inputs.length} Missing
                </div>
                <div className="text-[10px] text-slate-400 truncate">
                  {activeCampaign.missing_inputs.join(", ") || "All configured"}
                </div>
              </div>
            </div>

            {(activeCampaign.evaluated_inputs_and_constraints || activeCampaign.epistemic_classification) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-[11px]">
                {activeCampaign.evaluated_inputs_and_constraints && (
                  <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3 space-y-1.5">
                    <div className="font-bold text-slate-200 flex items-center justify-between">
                      <span>Evaluated Inputs vs User-Assumed Constraints</span>
                      <span className="font-mono text-[10px] text-slate-400">
                        Complete: {String(Boolean(activeCampaign.constraint_evaluation_complete))}
                      </span>
                    </div>
                    <pre className="text-[10px] font-mono text-slate-300 whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                      {JSON.stringify(activeCampaign.evaluated_inputs_and_constraints, null, 2)}
                    </pre>
                  </div>
                )}
                {activeCampaign.epistemic_classification && (
                  <div className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3 space-y-1.5">
                    <div className="font-bold text-slate-200">
                      Epistemic Classification (Measured vs Modeled vs Inferred vs Unknown)
                    </div>
                    <div className="space-y-1 text-[10px] font-mono">
                      {Object.entries(activeCampaign.epistemic_classification).map(([bucket, items]) => (
                        <div key={bucket} className="text-slate-300">
                          <span className="text-cyan-300">{bucket}:</span>{" "}
                          {Array.isArray(items) && items.length > 0 ? items.join("; ") : "None"}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Route Alternatives */}
            {activeCampaign.alternatives.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-bold text-slate-200">
                  Campaign Route &amp; Scope Alternatives ({activeCampaign.alternatives.length})
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {activeCampaign.alternatives.map((alt) => (
                    <div
                      key={alt.alternative_id}
                      className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3 space-y-1.5 text-[11px]"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-white">{alt.label}</span>
                        <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300">
                          {alt.routing_mode}
                        </span>
                      </div>
                      <div className="font-mono text-slate-300">
                        Out: {alt.outbound_distance_m != null ? `${alt.outbound_distance_m.toFixed(1)} m` : "—"} · Ret:{" "}
                        {alt.return_distance_m != null ? `${alt.return_distance_m.toFixed(1)} m` : "—"} · Dwell:{" "}
                        {(alt.science_dwell_s / 60).toFixed(0)} min
                      </div>
                      <div className="text-slate-400">{alt.explanation}</div>
                      {alt.failure_reason && (
                        <div className="text-rose-300 font-mono">Block: {alt.failure_reason}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ordered Stop Plans with Observation & Sampling Protocols */}
            <div className="space-y-2.5">
              <div className="text-xs font-bold text-slate-200">
                Sequenced Field Stops, Observation Action Plans &amp; Sampling Pre-Screening (
                {activeCampaign.stop_plans.length})
              </div>
              {activeCampaign.stop_plans.map((sp) => (
                <div
                  key={sp.stop_id}
                  className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3.5 space-y-2 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-[#e25b38]/20 text-[#f16f4d] font-mono font-bold">
                        Stop #{sp.stop_index}
                      </span>
                      <span className="font-bold text-white">{sp.name}</span>
                      <span className="font-mono text-[10px] text-slate-400">
                        ({sp.latitude.toFixed(5)}°, {sp.longitude_east.toFixed(5)}°E · Dwell{" "}
                        {(sp.dwell_s / 60).toFixed(0)} min)
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`px-2 py-0.5 rounded border font-mono text-[9px] uppercase ${stateBadgeClass(
                          sp.evidence_state
                        )}`}
                      >
                        {sp.evidence_state}
                      </span>
                      <button
                        onClick={() => {
                          setObsTargetId(sp.target_id);
                          setObsLat(sp.latitude.toFixed(5));
                          setObsLon(sp.longitude_east.toFixed(5));
                        }}
                        className="px-2 py-0.5 rounded border border-pink-500/40 bg-pink-500/15 text-[10px] font-mono text-pink-200"
                      >
                        Log Obs Here
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-[11px]">
                    <div className="rounded border border-[#1e2638] bg-[#121622] p-2.5 space-y-1">
                      <div className="font-semibold text-cyan-300 flex items-center justify-between gap-1.5">
                        <span className="flex items-center gap-1.5">
                          <Beaker className="w-3.5 h-3.5" />
                          Observation Protocol ({sp.observation_plan.recommended_instruments.join(", ")})
                        </span>
                        {sp.observation_plan.observation_lifecycle_state && (
                          <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 font-mono text-[9px] text-cyan-200">
                            {sp.observation_plan.observation_lifecycle_state}
                          </span>
                        )}
                      </div>
                      {sp.observation_plan.platform_mismatch_disclosed && (
                        <div className="rounded border border-amber-500/40 bg-amber-950/30 px-2 py-1 text-[10px] text-amber-200">
                          <strong>Platform Notice:</strong>{" "}
                          {sp.observation_plan.platform_disclosure_note || sp.observation_plan.platform_compatibility}
                        </div>
                      )}
                      <div className="text-slate-300">
                        Measurements: {sp.observation_plan.measurements_to_collect.slice(0, 3).join("; ")}
                      </div>
                      <div className="text-slate-400 font-mono text-[10px]">
                        Data Vol:{" "}
                        {sp.observation_plan.estimated_data_volume_mb != null
                          ? `${sp.observation_plan.estimated_data_volume_mb} MB`
                          : sp.observation_plan.data_volume_status || "UNAVAILABLE (no bitrate configured)"}
                      </div>
                      <div className="text-amber-300/90">
                        Guard: {sp.observation_plan.prohibited_shortcut_notes[0] ?? "Separate visual morphology from spectroscopy."}
                      </div>
                    </div>

                    <div className="rounded border border-[#1e2638] bg-[#121622] p-2.5 space-y-1">
                      <div className="font-semibold text-amber-200">
                        Sampling Protocol · {sp.sampling_protocol.eligibility_state}
                      </div>
                      <div className="text-slate-300">{sp.sampling_protocol.scientific_rationale}</div>
                      <div className="text-slate-400">
                        Contamination Controls: {sp.sampling_protocol.contamination_controls.slice(0, 2).join("; ")}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* =================================================================== */}
      {/* WORK AREA E — CREW FIELD OBSERVATION CAPTURE & ARCHIVE COMPARISON   */}
      {/* =================================================================== */}
      <section className="rounded-xl border border-[#1e2638] bg-[#121622] p-5 space-y-4">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400">Work Area E</div>
          <h2 className="text-base font-bold text-white">
            Crew Field Observation Capture &amp; Scale-Aware Archive Comparison
          </h2>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2.5 text-xs">
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Instrument</label>
            <select
              value={obsInstrument}
              onChange={(e) => setObsInstrument(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            >
              {instruments
                .filter((i) => !i.mission_isolated_from_gale)
                .map((i) => (
                  <option key={i.instrument_id} value={i.instrument_id}>
                    {i.instrument_id}
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Measurement</label>
            <input
              type="text"
              value={obsMeasType}
              onChange={(e) => setObsMeasType(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Species / Feature</label>
            <input
              type="text"
              value={obsSpecies}
              onChange={(e) => setObsSpecies(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Measured Value</label>
            <input
              type="text"
              value={obsValue}
              onChange={(e) => setObsValue(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Units</label>
            <input
              type="text"
              value={obsUnits}
              onChange={(e) => setObsUnits(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Latitude</label>
            <input
              type="text"
              value={obsLat}
              onChange={(e) => setObsLat(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div>
            <label className="block text-[10px] text-slate-400 mb-1">Longitude (°E)</label>
            <input
              type="text"
              value={obsLon}
              onChange={(e) => setObsLon(e.target.value)}
              className="w-full bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1.5 text-slate-100 font-mono"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => void handleRecordObservation()}
              disabled={loadingObservations}
              className="w-full px-3 py-1.5 rounded bg-pink-600 hover:bg-pink-500 disabled:opacity-50 font-semibold text-white"
            >
              {loadingObservations ? "Saving..." : "Record Field Obs"}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <input
            type="text"
            value={obsNotes}
            onChange={(e) => setObsNotes(e.target.value)}
            placeholder="Field context notes..."
            className="flex-1 min-w-[16rem] bg-[#0d111a] border border-[#2a344c] rounded px-3 py-1.5 text-slate-200"
          />
          <div className="flex items-center gap-1.5 font-mono text-slate-300">
            <span>Compare Radius (m):</span>
            <input
              type="number"
              value={compareRadiusM}
              onChange={(e) => setCompareRadiusM(Number(e.target.value) || 150)}
              className="w-20 bg-[#0d111a] border border-[#2a344c] rounded px-2 py-1"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-6 space-y-2 max-h-72 overflow-y-auto pr-1">
            <div className="text-xs font-bold text-slate-300">
              Recorded Field Observations ({observations.length}) — Pending Archive Lab Validation
            </div>
            {observations.length === 0 ? (
              <div className="rounded border border-[#1e2638] bg-[#0d111a] p-3 text-xs text-slate-400">
                No field observations recorded yet. Record an in-situ or visual observation above to compare against NASA
                PDS archives.
              </div>
            ) : (
              observations.map((obs) => (
                <div
                  key={obs.observation_id}
                  className="rounded-lg border border-[#1e2638] bg-[#0d111a] p-3 space-y-1.5 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-bold text-white">
                      {obs.instrument_id}: {obs.species_or_feature} = {String(obs.measured_value)} {obs.units}
                    </span>
                    <button
                      onClick={() => void compareObservation(obs.observation_id, compareRadiusM)}
                      disabled={loadingComparison}
                      className="px-2.5 py-1 rounded border border-cyan-500/40 bg-cyan-500/15 hover:bg-cyan-500/25 text-[10px] font-mono text-cyan-200"
                    >
                      Compare With Archive
                    </button>
                  </div>
                  <div className="text-[10px] font-mono text-slate-400">
                    {obs.latitude.toFixed(5)}°, {obs.longitude_east.toFixed(5)}°E · Flag: {obs.quality_flag}
                  </div>
                  {obs.prohibited_inference_warning && (
                    <div className="text-[11px] text-rose-300">
                      Warning: {obs.prohibited_inference_warning}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          <div className="lg:col-span-6 rounded-lg border border-[#1e2638] bg-[#0d111a] p-4 space-y-2.5 text-xs">
            <div className="text-xs font-bold text-white">Scale-Aware Archive Comparison Report</div>
            {!activeComparison ? (
              <div className="text-slate-400">
                Click &quot;Compare With Archive&quot; on any field observation to inspect co-located same-scale NASA PDS
                records separately from coarse orbital context.
              </div>
            ) : (
              <div className="space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span
                    className={`px-2 py-0.5 rounded border font-mono text-[10px] uppercase ${stateBadgeClass(
                      activeComparison.outcome
                    )}`}
                  >
                    {activeComparison.outcome}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">
                    Same-scale: {activeComparison.same_scale_archive_records.length} · Orbital context:{" "}
                    {activeComparison.orbital_context_records.length}
                  </span>
                </div>
                <div className="text-slate-200 leading-relaxed">{activeComparison.explanation}</div>
                {activeComparison.scale_disparity_notes.length > 0 && (
                  <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2 text-[11px] text-amber-200 space-y-1">
                    <strong>Scale Disparity Warnings:</strong>
                    {activeComparison.scale_disparity_notes.map((n, i) => (
                      <div key={i}>• {n}</div>
                    ))}
                  </div>
                )}
                {activeComparison.next_verification_steps.length > 0 && (
                  <div className="text-[11px] text-cyan-300">
                    <strong>Next Verification Steps:</strong>{" "}
                    {activeComparison.next_verification_steps.join(" · ")}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
