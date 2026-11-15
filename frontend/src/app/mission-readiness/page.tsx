"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  BatteryCharging,
  CheckCircle2,
  Clock,
  Compass,
  Database,
  Eye,
  GitBranch,
  Layers,
  Navigation,
  Play,
  Plus,
  RefreshCw,
  Route as RouteIcon,
  ShieldAlert,
  Sparkles,
  Target,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import { LocalTerrain3DViewer } from "@/components/LocalTerrain3DViewer";
import { PageHeader } from "@/components/PageHeader";
import { Prompt20OperationalPanels } from "@/components/Prompt20OperationalPanels";
import { API_BASE_URL } from "@/lib/constants";
import { useEvaOperationsStore, type EvaEvaluateParams } from "@/stores/useEvaOperationsStore";
import { useEvidenceStore, type EvidenceOverlayToggles } from "@/stores/useEvidenceStore";
import { useRoutingStore } from "@/stores/useRoutingStore";
import type {
  CorridorSegmentAssessment,
  EvaExplicitResourceSpec,
  EvaSegmentScheduleItem,
} from "@/types";

interface EditableResourceRow {
  id: string;
  resource_name: string;
  initial_quantity: string;
  unit: string;
  consumption_rate: string;
  rate_unit: string;
  reserve_fraction: string;
  source_note: string;
}

type SectionFilter = "all" | "spatial" | "timeline" | "resources" | "constraints" | "readiness";

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "Unavailable";
  const rounded = Math.max(0, Math.round(seconds));
  const hrs = Math.floor(rounded / 3600);
  const mins = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatNum(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unavailable";
  return value.toFixed(digits);
}

function parseOptNum(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const val = Number(trimmed);
  return Number.isFinite(val) ? val : null;
}

function badgeClassForStatus(status: string): string {
  switch (status) {
    case "PASS":
    case "ASSESSED":
    case "WITHIN_LIMIT":
    case "WITHIN_CONSTRAINTS":
    case "FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS":
    case "FEASIBLE_UNDER_CONFIGURED_MODEL":
    case "CALCULATED":
    case "CURRENT":
    case "VERIFIED_LOCAL":
    case "RESEARCH_GRADE":
      return "border-emerald-500/40 bg-emerald-500/15 text-emerald-300";
    case "FAIL":
    case "EXCEEDS_LIMIT":
    case "EXCEEDS_CONSTRAINTS":
    case "INFEASIBLE_UNDER_CONFIGURED_MODEL":
    case "INSUFFICIENT_EVIDENCE":
    case "UNIT_MISMATCH":
    case "MISSING":
    case "FAILED":
      return "border-red-500/40 bg-red-500/15 text-red-300";
    case "STALE":
    case "PARTIALLY_ASSESSED":
    case "INCOMPLETE_USER_CONSTRAINTS":
    case "INCOMPLETE_CONSTRAINT_EVALUATION":
    case "BLOCKED_BY_UNKNOWN_INPUTS":
    case "RECOMPUTING":
    case "URL_UNVERIFIED":
    case "CONTEXT_ONLY":
      return "border-amber-500/40 bg-amber-500/15 text-amber-300";
    default:
      return "border-slate-700 bg-slate-800/70 text-slate-300";
  }
}

export default function MissionReadinessPage() {
  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const activeMode = useRoutingStore((s) => s.activeMode);
  const loadBoxworkStudyExample = useRoutingStore((s) => s.loadBoxworkStudyExample);
  const requestCameraFocus = useRoutingStore((s) => s.requestCameraFocus);

  const {
    corridorAssessment,
    routeComparison,
    missionDossier,
    decisionTrace,
    dependencyTrace,
    corridorUncertainty,
    complementarityReport,
    selectedSegmentId,
    loadingCorridor,
    loadingComparison,
    loadingDossier,
    loadingUncertainty,
    loadingComplementarity,
    error: evidenceError,
    overlays,
    setSelectedSegmentId,
    toggleOverlay,
    assessCorridor,
    fetchDecisionTrace,
    fetchDependencyTrace,
    fetchCorridorUncertainty,
    fetchComplementarity,
    compareRoutesEvidence,
    generateMissionDossier,
  } = useEvidenceStore();

  const {
    evaEnvelope,
    selectedTimelineIndex,
    selectedReturnAlternativeId,
    loadingEva,
    error: evaError,
    setSelectedTimelineStep,
    setSelectedReturnAlternativeId,
    fetchReturnAnalysis,
    evaluateMission,
  } = useEvaOperationsStore();

  const [sectionFilter, setSectionFilter] = useState<SectionFilter>("all");
  const [missionName, setMissionName] = useState("Gale Boxwork Traverse & EVA Operational Envelope");
  const [selectedMode, setSelectedMode] = useState<"conservative" | "balanced" | "science_priority">(
    (activeRoute?.mode as "conservative" | "balanced" | "science_priority") ||
      (activeMode as "conservative" | "balanced" | "science_priority") ||
      "balanced"
  );
  const [corridorWidthM, setCorridorWidthM] = useState<number>(60);
  const [searchRadiusM, setSearchRadiusM] = useState<number>(250);
  const [forceRecompute, setForceRecompute] = useState<boolean>(false);

  // Explicit EVA assumption inputs — strictly nullable by default (never silently fabricated)
  const [walkingSpeedMps, setWalkingSpeedMps] = useState<string>("");
  const [locomotionCategory, setLocomotionCategory] = useState<
    | "USER_CONFIGURED_CONSTANT_SPEED"
    | "TERRESTRIAL_HIKING_APPROXIMATION"
    | "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL"
  >("USER_CONFIGURED_CONSTANT_SPEED");
  const [unknownTerrainPolicy, setUnknownTerrainPolicy] = useState<
    | "EXCLUDE_UNKNOWN"
    | "ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE"
    | "REQUIRE_ADDITIONAL_OBSERVATION"
    | "ROUTE_THROUGH_WITH_LIMITATION"
  >("EXCLUDE_UNKNOWN");
  const useToblerApprox = locomotionCategory === "TERRESTRIAL_HIKING_APPROXIMATION";
  const [durationLimitMin, setDurationLimitMin] = useState<string>("");
  const [reserveFrac, setReserveFrac] = useState<string>("");
  const [overheadMin, setOverheadMin] = useState<string>("0");
  const [suitMassKg, setSuitMassKg] = useState<string>("");
  const [payloadMassKg, setPayloadMassKg] = useState<string>("");
  const [computeReverseReturn, setComputeReverseReturn] = useState<boolean>(true);
  const [resourceRows, setResourceRows] = useState<EditableResourceRow[]>([]);
  const [resourceValidationError, setResourceValidationError] = useState<string | null>(null);

  // Refs for Section F Missing Information Drawer direct focus
  const walkingSpeedRef = useRef<HTMLInputElement | null>(null);
  const durationLimitRef = useRef<HTMLInputElement | null>(null);
  const reserveFractionRef = useRef<HTMLInputElement | null>(null);
  const suitMassRef = useRef<HTMLInputElement | null>(null);
  const payloadMassRef = useRef<HTMLInputElement | null>(null);
  const resourcesSectionRef = useRef<HTMLDivElement | null>(null);

  const effectiveStart = startPoint ?? {
    lat: -4.749,
    lon_east: 137.394,
    label: "Gale Boxwork Start",
  };
  const effectiveDest = destinationPoint ?? {
    lat: -4.753,
    lon_east: 137.396,
    label: "Mount Sharp Target",
  };

  const selectedSegment = useMemo(
    () =>
      corridorAssessment?.segments.find((s) => s.segment_id === selectedSegmentId) ??
      corridorAssessment?.segments[0] ??
      null,
    [corridorAssessment, selectedSegmentId]
  );

  const parsedResourcesPreview = useMemo<EvaExplicitResourceSpec[]>(() => {
    const out: EvaExplicitResourceSpec[] = [];
    for (const row of resourceRows) {
      const qty = parseOptNum(row.initial_quantity);
      const rate = parseOptNum(row.consumption_rate);
      const resFrac = parseOptNum(row.reserve_fraction) ?? 0;
      if (!row.resource_name.trim() || qty === null || qty < 0 || rate === null || rate < 0) continue;
      if (resFrac < 0 || resFrac >= 1) continue;
      out.push({
        resource_name: row.resource_name.trim(),
        initial_quantity: qty,
        unit: row.unit.trim(),
        consumption_rate: rate,
        rate_unit: row.rate_unit.trim(),
        reserve_fraction: resFrac,
        source_note: row.source_note.trim() || null,
      });
    }
    return out;
  }, [resourceRows]);

  const buildResourcesPayload = (): { ok: boolean; items: EvaExplicitResourceSpec[] } => {
    const parsed: EvaExplicitResourceSpec[] = [];
    for (const row of resourceRows) {
      const qty = parseOptNum(row.initial_quantity);
      const rate = parseOptNum(row.consumption_rate);
      const resFrac = parseOptNum(row.reserve_fraction) ?? 0;
      if (!row.resource_name.trim() || qty === null || qty < 0 || rate === null || rate < 0) {
        setResourceValidationError(
          `Resource row "${row.resource_name || "Unnamed"}" needs non-negative initial quantity and consumption rate.`
        );
        return { ok: false, items: [] };
      }
      if (resFrac < 0 || resFrac >= 1) {
        setResourceValidationError(
          `Resource row "${row.resource_name}" reserve_fraction must be in [0, 1).`
        );
        return { ok: false, items: [] };
      }
      parsed.push({
        resource_name: row.resource_name.trim(),
        initial_quantity: qty,
        unit: row.unit.trim(),
        consumption_rate: rate,
        rate_unit: row.rate_unit.trim(),
        reserve_fraction: resFrac,
        source_note: row.source_note.trim() || null,
      });
    }
    setResourceValidationError(null);
    return { ok: true, items: parsed };
  };

  const durationLimitSeconds = useMemo(() => {
    const mins = parseOptNum(durationLimitMin);
    return mins !== null && mins > 0 ? mins * 60 : null;
  }, [durationLimitMin]);

  const overheadSeconds = useMemo(() => {
    const mins = parseOptNum(overheadMin);
    return mins !== null && mins >= 0 ? mins * 60 : 0;
  }, [overheadMin]);

  const handleAssessCorridor = async () => {
    const assessed = await assessCorridor({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
      force_recompute: forceRecompute,
    });
    if (assessed?.assessment_id) {
      await fetchDecisionTrace(assessed.assessment_id);
      await fetchDependencyTrace(assessed.assessment_id);
    }
    await fetchCorridorUncertainty({ dataset_id: selectedDemDatasetId });
    await fetchComplementarity();
  };

  const handleCompareRoutes = () => {
    compareRoutesEvidence({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
    });
  };

  const handleGenerateDossier = () => {
    generateMissionDossier({
      mission_name: missionName,
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
      walking_speed_mps: parseOptNum(walkingSpeedMps),
      mission_duration_limit_s: durationLimitSeconds,
      return_reserve_fraction: parseOptNum(reserveFrac),
      astronaut_suit_mass_kg: parseOptNum(suitMassKg),
      payload_mass_kg: parseOptNum(payloadMassKg),
      independent_return_computed: Boolean(evaEnvelope?.return_plan?.return_route_computed),
      force_recompute: forceRecompute,
    });
  };

  const buildEvalParams = (resourcesPayload: EvaExplicitResourceSpec[]): EvaEvaluateParams => ({
    mission_name: missionName,
    dataset_id: selectedDemDatasetId,
    start: effectiveStart,
    destination: effectiveDest,
    mode: selectedMode,
    corridor_width_m: corridorWidthM,
    observation_search_radius_m: searchRadiusM,
    walking_speed_mps: parseOptNum(walkingSpeedMps),
    use_tobler_grade_approximation: useToblerApprox,
    locomotion_category: locomotionCategory,
    unknown_terrain_policy: unknownTerrainPolicy,
    mission_duration_limit_s: durationLimitSeconds,
    return_reserve_fraction: parseOptNum(reserveFrac),
    operational_overhead_s: overheadSeconds,
    astronaut_suit_mass_kg: parseOptNum(suitMassKg),
    payload_mass_kg: parseOptNum(payloadMassKg),
    resources: resourcesPayload,
    compute_reverse_return_route: computeReverseReturn,
  });

  const handleEvaluateEva = async () => {
    const resBuild = buildResourcesPayload();
    if (!resBuild.ok) return;
    const evaRes = await evaluateMission(buildEvalParams(resBuild.items));
    if (evaRes?.mission_id) {
      await fetchReturnAnalysis(evaRes.mission_id);
    }
  };

  const handleRunFullAnalysis = async () => {
    const resBuild = buildResourcesPayload();
    if (!resBuild.ok) return;
    const assessed = await assessCorridor({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
      force_recompute: forceRecompute,
    });
    if (assessed?.assessment_id) {
      await fetchDecisionTrace(assessed.assessment_id);
      await fetchDependencyTrace(assessed.assessment_id);
    }
    await fetchCorridorUncertainty({ dataset_id: selectedDemDatasetId });
    await fetchComplementarity();
    await compareRoutesEvidence({
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
    });
    const evaRes = await evaluateMission(buildEvalParams(resBuild.items));
    if (evaRes?.mission_id) {
      await fetchReturnAnalysis(evaRes.mission_id);
    }
    await generateMissionDossier({
      mission_name: missionName,
      dataset_id: selectedDemDatasetId,
      start: effectiveStart,
      destination: effectiveDest,
      mode: selectedMode,
      corridor_width_m: corridorWidthM,
      observation_search_radius_m: searchRadiusM,
      walking_speed_mps: parseOptNum(walkingSpeedMps),
      mission_duration_limit_s: durationLimitSeconds,
      return_reserve_fraction: parseOptNum(reserveFrac),
      astronaut_suit_mass_kg: parseOptNum(suitMassKg),
      payload_mass_kg: parseOptNum(payloadMassKg),
      independent_return_computed: Boolean(evaRes?.return_plan?.return_route_computed),
      force_recompute: forceRecompute,
    });
  };

  const handleSelectSegment = (seg: CorridorSegmentAssessment) => {
    setSelectedSegmentId(seg.segment_id);
    if (evaEnvelope?.schedule) {
      const idx = evaEnvelope.schedule.findIndex((item) => item.segment_id === seg.segment_id);
      if (idx >= 0) {
        setSelectedTimelineStep(idx, seg.segment_id);
      }
    }
    const midLat = (seg.start_coord.lat + seg.end_coord.lat) / 2;
    const midLon = (seg.start_coord.lon_east + seg.end_coord.lon_east) / 2;
    const elev =
      seg.start_elevation_m !== null &&
      seg.start_elevation_m !== undefined &&
      seg.end_elevation_m !== null &&
      seg.end_elevation_m !== undefined
        ? (seg.start_elevation_m + seg.end_elevation_m) / 2
        : undefined;
    requestCameraFocus(midLat, midLon, elev);
  };

  const handleSelectTimelineStep = (item: EvaSegmentScheduleItem) => {
    setSelectedTimelineStep(item.sequence_index, item.segment_id ?? null);
    if (item.vertices.length > 0) {
      const mid = item.vertices[Math.floor(item.vertices.length / 2)];
      requestCameraFocus(mid.lat, mid.lon_east);
    }
  };

  const addResourcePreset = (kind: "o2" | "battery" | "custom") => {
    const id = `res-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    if (kind === "o2") {
      setResourceRows((prev) => [
        ...prev,
        {
          id,
          resource_name: "oxygen_kg",
          initial_quantity: "",
          unit: "kg",
          consumption_rate: "",
          rate_unit: "kg/h",
          reserve_fraction: "0.2",
          source_note: "Explicit user suit O2 limit",
        },
      ]);
      return;
    }
    if (kind === "battery") {
      setResourceRows((prev) => [
        ...prev,
        {
          id,
          resource_name: "battery_wh",
          initial_quantity: "",
          unit: "Wh",
          consumption_rate: "",
          rate_unit: "W",
          reserve_fraction: "0.2",
          source_note: "Explicit user suit power limit",
        },
      ]);
      return;
    }
    setResourceRows((prev) => [
      ...prev,
      {
        id,
        resource_name: "consumable",
        initial_quantity: "",
        unit: "L",
        consumption_rate: "",
        rate_unit: "L/h",
        reserve_fraction: "0.15",
        source_note: "User custom consumable",
      },
    ]);
  };

  const focusMissingField = (item: string) => {
    const lower = item.toLowerCase();
    if (lower.includes("walking_speed")) {
      walkingSpeedRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      walkingSpeedRef.current?.focus();
    } else if (lower.includes("duration_limit") || lower.includes("time_budget")) {
      durationLimitRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      durationLimitRef.current?.focus();
    } else if (lower.includes("reserve")) {
      reserveFractionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      reserveFractionRef.current?.focus();
    } else if (lower.includes("suit_mass")) {
      suitMassRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      suitMassRef.current?.focus();
    } else if (lower.includes("payload_mass")) {
      payloadMassRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      payloadMassRef.current?.focus();
    } else if (lower.includes("resource")) {
      resourcesSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const combinedMissingInputs = useMemo(() => {
    const items = new Set<string>();
    for (const m of evaEnvelope?.missing_inputs ?? []) items.add(m);
    for (const m of evaEnvelope?.resource_budget.missing_inputs ?? []) items.add(m);
    for (const m of missionDossier?.missing_inputs ?? []) items.add(m);
    if (!parseOptNum(walkingSpeedMps)) items.add("walking_speed_mps (explicit user input)");
    if (!durationLimitSeconds) items.add("mission_duration_limit_s (explicit user input)");
    if (parseOptNum(reserveFrac) === null) items.add("return_reserve_fraction (explicit user input)");
    if (!parseOptNum(suitMassKg)) items.add("astronaut_suit_mass_kg (explicit user input)");
    if (parseOptNum(payloadMassKg) === null) items.add("payload_mass_kg (explicit user input)");
    if (resourceRows.length === 0) items.add("resources (no consumables/power limits supplied yet)");
    return Array.from(items);
  }, [
    evaEnvelope,
    missionDossier,
    walkingSpeedMps,
    durationLimitSeconds,
    reserveFrac,
    suitMassKg,
    payloadMassKg,
    resourceRows.length,
  ]);

  const activeExplainer =
    (decisionTrace?.route_decision_explainer as typeof corridorAssessment extends infer T
      ? T extends { route_decision_explainer?: infer E }
        ? E
        : never
      : never) ??
    corridorAssessment?.route_decision_explainer ??
    null;

  const activeCacheValidity =
    evaEnvelope?.cache_validity ??
    missionDossier?.cache_validity ??
    corridorAssessment?.cache_validity ??
    "UNAVAILABLE";
  const staleReasons =
    missionDossier?.stale_reasons?.length
      ? missionDossier.stale_reasons
      : corridorAssessment?.stale_reasons ?? [];

  const opticalDataset = corridorAssessment?.dataset_inventory.find(
    (d) => d.acquired && (d.product_type === "HiRISE_ORTHO" || d.product_type === "ORTHO")
  );
  const opticalCropUrl =
    selectedSegment && opticalDataset
      ? `${API_BASE_URL}/terrain/optical-crop?dataset_id=${encodeURIComponent(
          opticalDataset.dataset_id
        )}&min_lat=${Math.min(selectedSegment.start_coord.lat, selectedSegment.end_coord.lat) - 0.001}&max_lat=${
          Math.max(selectedSegment.start_coord.lat, selectedSegment.end_coord.lat) + 0.001
        }&min_lon=${Math.min(selectedSegment.start_coord.lon_east, selectedSegment.end_coord.lon_east) - 0.001}&max_lon=${
          Math.max(selectedSegment.start_coord.lon_east, selectedSegment.end_coord.lon_east) + 0.001
        }`
      : null;

  const overlayButtonItems: Array<{ key: keyof EvidenceOverlayToggles; label: string }> = [
    { key: "showCorridor", label: "Corridor Polygon" },
    { key: "showSegments", label: "Segments" },
    { key: "showGaps", label: "Data Gaps" },
    { key: "showTerrainCandidates", label: "DEM Candidates" },
    { key: "showOpticalCandidates", label: "Optical Candidates" },
    { key: "showObservations", label: "Rover Observations" },
    { key: "showReturnRoute", label: "Return Route" },
    { key: "showAlternativeRoutes", label: "Alt Routes" },
    { key: "showTurnbackPonr", label: "PONR Beacon" },
  ];

  const showSection = (s: Exclude<SectionFilter, "all">) =>
    sectionFilter === "all" || sectionFilter === s;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="Marswalk Evidence & EVA Operational Envelope"
        badge="PROMPT 15 · SCIENTIFIC VALIDITY + OPERATIONAL PLANNING"
        description="Spatially masked Gale Crater / Mount Sharp corridor evidence engine paired with explicit constraint-based EVA outbound/return envelopes. Zero fabricated risk scores or hidden safety defaults."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-[11px] font-mono ${badgeClassForStatus(
                activeCacheValidity
              )}`}
            >
              Cache: {activeCacheValidity}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-[11px] font-mono text-red-300">
              <ShieldAlert className="h-3.5 w-3.5" />
              Safety Certified: FALSE (Decision Support Only)
            </span>
            <Link
              href="/planner"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
            >
              Open Route Planner
            </Link>
          </div>
        }
      />

      {(evidenceError || evaError || resourceValidationError) && (
        <div className="rounded-xl border border-red-500/40 bg-red-950/30 p-3 text-xs text-red-200 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            {evidenceError && <div>Evidence Engine: {evidenceError}</div>}
            {evaError && <div>EVA Envelope Engine: {evaError}</div>}
            {resourceValidationError && <div>Resource Input: {resourceValidationError}</div>}
          </div>
        </div>
      )}

      {activeCacheValidity === "STALE" && staleReasons.length > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-950/25 p-3 text-xs text-amber-200">
          <div className="font-semibold flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            Cached Assessment Marked STALE (Underlying Dependencies Changed)
          </div>
          <ul className="mt-1 list-disc pl-5 space-y-0.5 text-[11px]">
            {staleReasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Top Controls + Section F Missing Information Drawer */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-8 rounded-xl border border-slate-800 bg-slate-950/70 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold text-white">Mission & Explicit Operational Parameters</h2>
              <p className="text-[11px] text-slate-400">
                Active DEM: <span className="font-mono text-cyan-300">{selectedDemDatasetId}</span> · Start:{" "}
                <span className="font-mono text-slate-200">
                  {effectiveStart.lat.toFixed(4)}°, {effectiveStart.lon_east.toFixed(4)}°E
                </span>{" "}
                → Dest:{" "}
                <span className="font-mono text-slate-200">
                  {effectiveDest.lat.toFixed(4)}°, {effectiveDest.lon_east.toFixed(4)}°E
                </span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={loadBoxworkStudyExample}
                className="rounded border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1 text-[11px] text-cyan-300 hover:bg-cyan-500/20"
              >
                Load Gale Boxwork Example
              </button>
              <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceRecompute}
                  onChange={(e) => setForceRecompute(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900"
                />
                Force Recompute
              </label>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <label className="col-span-2 space-y-1">
              <span className="text-[11px] text-slate-400">Mission Name</span>
              <input
                type="text"
                value={missionName}
                onChange={(e) => setMissionName(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">Routing Mode</span>
              <select
                value={selectedMode}
                onChange={(e) =>
                  setSelectedMode(e.target.value as "conservative" | "balanced" | "science_priority")
                }
                className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100"
              >
                <option value="conservative">Conservative</option>
                <option value="balanced">Balanced</option>
                <option value="science_priority">Science Priority</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">Corridor Width (m)</span>
              <input
                type="number"
                min={10}
                max={500}
                value={corridorWidthM}
                onChange={(e) => setCorridorWidthM(Number(e.target.value) || 60)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
              />
            </label>

            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">Obs Search Radius (m)</span>
              <input
                type="number"
                min={10}
                max={5000}
                value={searchRadiusM}
                onChange={(e) => setSearchRadiusM(Number(e.target.value) || 250)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-amber-300">Walking Speed (m/s) *</span>
              <input
                ref={walkingSpeedRef}
                type="number"
                step="0.05"
                min="0.05"
                max="5"
                placeholder="Explicit e.g. 0.8"
                value={walkingSpeedMps}
                onChange={(e) => setWalkingSpeedMps(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-amber-300">Time Limit (minutes) *</span>
              <input
                ref={durationLimitRef}
                type="number"
                min="1"
                placeholder="Explicit e.g. 120"
                value={durationLimitMin}
                onChange={(e) => setDurationLimitMin(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-amber-300">Return Reserve (0–0.95) *</span>
              <input
                ref={reserveFractionRef}
                type="number"
                step="0.05"
                min="0"
                max="0.95"
                placeholder="Explicit e.g. 0.25"
                value={reserveFrac}
                onChange={(e) => setReserveFrac(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
              />
            </label>

            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">Op Overhead (minutes)</span>
              <input
                type="number"
                min="0"
                value={overheadMin}
                onChange={(e) => setOverheadMin(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-amber-300">Astronaut + Suit Mass (kg) *</span>
              <input
                ref={suitMassRef}
                type="number"
                min="1"
                placeholder="Explicit e.g. 165"
                value={suitMassKg}
                onChange={(e) => setSuitMassKg(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-amber-300">Science Payload Mass (kg) *</span>
              <input
                ref={payloadMassRef}
                type="number"
                min="0"
                placeholder="Explicit e.g. 20"
                value={payloadMassKg}
                onChange={(e) => setPayloadMassKg(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-slate-100 placeholder:text-slate-600"
              />
            </label>
            <div className="col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label className="space-y-1">
                <span className="text-[11px] text-slate-400">Locomotion Model Category</span>
                <select
                  value={locomotionCategory}
                  onChange={(e) =>
                    setLocomotionCategory(
                      e.target.value as
                        | "USER_CONFIGURED_CONSTANT_SPEED"
                        | "TERRESTRIAL_HIKING_APPROXIMATION"
                        | "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL"
                    )
                  }
                  className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-100"
                >
                  <option value="USER_CONFIGURED_CONSTANT_SPEED">Cat A · User Constant Speed (v0)</option>
                  <option value="TERRESTRIAL_HIKING_APPROXIMATION">Cat B · Tobler 1993 Hiking Approx (Exploratory)</option>
                  <option value="MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL">Cat C · Validated Mars Suit Model (Unavailable)</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-[11px] text-slate-400">Unknown Terrain Policy</span>
                <select
                  value={unknownTerrainPolicy}
                  onChange={(e) =>
                    setUnknownTerrainPolicy(
                      e.target.value as
                        | "EXCLUDE_UNKNOWN"
                        | "ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE"
                        | "REQUIRE_ADDITIONAL_OBSERVATION"
                        | "ROUTE_THROUGH_WITH_LIMITATION"
                    )
                  }
                  className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-100"
                >
                  <option value="EXCLUDE_UNKNOWN">Exclude Unknown Cells</option>
                  <option value="REQUIRE_ADDITIONAL_OBSERVATION">Require Additional Observation</option>
                  <option value="ROUTE_THROUGH_WITH_LIMITATION">Route With Limitation Flag</option>
                  <option value="ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE">Allow With Operator Override</option>
                </select>
              </label>
            </div>
            <div className="flex flex-col justify-end gap-1.5 pb-1">
              <label className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={computeReverseReturn}
                  onChange={(e) => setComputeReverseReturn(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-900"
                />
                <span>Compute reverse return route</span>
              </label>
            </div>
          </div>

          {/* Explicit Unit-Aware Resources Builder */}
          <div ref={resourcesSectionRef} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <BatteryCharging className="h-3.5 w-3.5 text-cyan-400" />
                  Explicit Consumables & Power Limits (Unit-Checked: Q_used = Q_dot · t)
                </div>
                <div className="text-[11px] text-slate-400">
                  Leave empty or add explicit quantities + rates. MarsScope never invents life-support reserves.
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => addResourcePreset("o2")}
                  className="inline-flex items-center gap-1 rounded border border-cyan-500/40 bg-cyan-500/10 px-2 py-1 text-[11px] text-cyan-300 hover:bg-cyan-500/20"
                >
                  <Plus className="h-3 w-3" /> O2 Supply
                </button>
                <button
                  type="button"
                  onClick={() => addResourcePreset("battery")}
                  className="inline-flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-300 hover:bg-emerald-500/20"
                >
                  <Plus className="h-3 w-3" /> Battery Wh
                </button>
                <button
                  type="button"
                  onClick={() => addResourcePreset("custom")}
                  className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
                >
                  <Plus className="h-3 w-3" /> Custom
                </button>
              </div>
            </div>

            {resourceRows.length > 0 && (
              <div className="space-y-2">
                {resourceRows.map((row, idx) => (
                  <div
                    key={row.id}
                    className="grid grid-cols-2 sm:grid-cols-12 gap-2 items-center rounded border border-slate-800 bg-slate-950/70 p-2 text-[11px]"
                  >
                    <input
                      type="text"
                      aria-label={`Resource ${idx + 1} name`}
                      placeholder="name"
                      value={row.resource_name}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, resource_name: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-3 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                    <input
                      type="number"
                      min="0"
                      step="any"
                      placeholder="init qty"
                      value={row.initial_quantity}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, initial_quantity: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                    <select
                      value={row.unit}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, unit: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-1 rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
                    >
                      <option value="kg">kg</option>
                      <option value="g">g</option>
                      <option value="L">L</option>
                      <option value="Wh">Wh</option>
                      <option value="kWh">kWh</option>
                      <option value="J">J</option>
                      <option value="kJ">kJ</option>
                      <option value="min">min</option>
                      <option value="h">h</option>
                    </select>
                    <input
                      type="number"
                      min="0"
                      step="any"
                      placeholder="rate"
                      value={row.consumption_rate}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, consumption_rate: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                    <input
                      type="text"
                      placeholder="kg/h or W"
                      value={row.rate_unit}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, rate_unit: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                    <input
                      type="number"
                      min="0"
                      max="0.95"
                      step="0.05"
                      placeholder="res"
                      value={row.reserve_fraction}
                      onChange={(e) =>
                        setResourceRows((prev) =>
                          prev.map((r) => (r.id === row.id ? { ...r, reserve_fraction: e.target.value } : r))
                        )
                      }
                      className="sm:col-span-1 rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-slate-100"
                    />
                    <button
                      type="button"
                      onClick={() => setResourceRows((prev) => prev.filter((r) => r.id !== row.id))}
                      aria-label={`Remove ${row.resource_name}`}
                      className="sm:col-span-1 inline-flex items-center justify-center rounded border border-red-500/30 bg-red-500/10 p-1 text-red-300 hover:bg-red-500/20"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Primary execution buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleRunFullAnalysis}
              disabled={loadingCorridor || loadingComparison || loadingDossier || loadingEva}
              className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500 px-3.5 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              {loadingCorridor || loadingDossier || loadingEva
                ? "Running Full Analysis..."
                : "Run Full Mission & EVA Analysis"}
            </button>
            <button
              type="button"
              onClick={handleAssessCorridor}
              disabled={loadingCorridor}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              <Compass className="h-3.5 w-3.5 text-cyan-400" />
              {loadingCorridor ? "Assessing..." : "Assess Corridor"}
            </button>
            <button
              type="button"
              onClick={handleCompareRoutes}
              disabled={loadingComparison}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              <GitBranch className="h-3.5 w-3.5 text-emerald-400" />
              {loadingComparison ? "Comparing..." : "Compare Modes"}
            </button>
            <button
              type="button"
              onClick={handleGenerateDossier}
              disabled={loadingDossier}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
            >
              <Database className="h-3.5 w-3.5 text-purple-400" />
              {loadingDossier ? "Generating..." : "Generate 15-Domain Dossier"}
            </button>
            <button
              type="button"
              onClick={handleEvaluateEva}
              disabled={loadingEva}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/15 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-500/25 disabled:opacity-50"
            >
              <Activity className="h-3.5 w-3.5 text-rose-400" />
              {loadingEva ? "Evaluating EVA..." : "Evaluate EVA Envelope"}
            </button>
          </div>
        </div>

        {/* SECTION F: Clickable Missing Information Drawer */}
        <div className="xl:col-span-4 rounded-xl border border-amber-500/30 bg-slate-950/75 p-4 flex flex-col justify-between space-y-3">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-amber-200 flex items-center gap-1.5">
                <Wrench className="h-4 w-4 text-amber-400" />
                Section F · Missing Information Drawer
              </h2>
              <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-mono text-amber-300">
                {combinedMissingInputs.length} missing
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Unconfigured mission constraints stay explicitly missing (never replaced with hidden defaults). Click an
              item to jump to and supply that input:
            </p>
            {combinedMissingInputs.length === 0 ? (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                All explicit user operational & resource parameters supplied for current evaluation.
              </div>
            ) : (
              <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1">
                {combinedMissingInputs.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => focusMissingField(item)}
                    className="w-full text-left rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-200 hover:bg-amber-500/20 flex items-center justify-between gap-2"
                  >
                    <span className="font-mono break-all">{item}</span>
                    <span className="shrink-0 text-[10px] text-cyan-300">Focus →</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {evaEnvelope && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-2.5 text-[11px] space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">EVA Envelope Status</span>
                <span
                  className={`rounded border px-2 py-0.5 font-mono text-[10px] ${badgeClassForStatus(
                    evaEnvelope.envelope_status
                  )}`}
                >
                  {evaEnvelope.envelope_status}
                </span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>Outbound Distance</span>
                <span className="font-mono">{formatNum(evaEnvelope.outbound_summary.horizontal_distance_m, 1)} m</span>
              </div>
              <div className="flex items-center justify-between text-slate-300">
                <span>Compute Time</span>
                <span className="font-mono">{evaEnvelope.compute_time_ms.toFixed(1)} ms</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Synchronized 3D Corridor + Return Route + Overlay Controls */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <Layers className="h-4 w-4 text-cyan-400" />
            <span className="font-semibold text-white">3D Corridor & EVA Return Route Viewport</span>
            {selectedSegment && (
              <span className="rounded border border-yellow-500/40 bg-yellow-500/10 px-2 py-0.5 font-mono text-[11px] text-yellow-300">
                Selected: {selectedSegment.segment_id}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {overlayButtonItems.map(({ key, label }) => {
              const active = overlays[key];
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleOverlay(key)}
                  className={`inline-flex items-center gap-1 rounded border px-2.5 py-1 text-[11px] transition ${
                    active
                      ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-200"
                      : "border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Eye className="h-3 w-3" />
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="h-[460px] w-full overflow-hidden rounded-lg border border-slate-800 bg-black">
          <LocalTerrain3DViewer />
        </div>
      </div>

      {/* Section Filter Navigation */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
        {(
          [
            { id: "all", label: "All Sections (A–E)" },
            { id: "spatial", label: "A · Spatial & Route Explainer" },
            { id: "timeline", label: "B · Timeline & Return Route" },
            { id: "resources", label: "C · Time, Climb Work & Resources" },
            { id: "constraints", label: "D · Constraint Table" },
            { id: "readiness", label: "E · 15-Domain Readiness & Audit" },
          ] as Array<{ id: SectionFilter; label: string }>
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSectionFilter(tab.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              sectionFilter === tab.id
                ? "bg-cyan-500 text-slate-950"
                : "border border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ===================================================================== */}
      {/* SECTION A — ROUTE & SEGMENT SPATIAL ASSESSMENT + DECISION EXPLAINER   */}
      {/* ===================================================================== */}
      {showSection("spatial") && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Compass className="h-4 w-4 text-cyan-400" />
              Section A · Route Decision Explainer, Corridor Segments & Optical/Rover Evidence
            </h2>
            {corridorAssessment && (
              <span className="text-xs font-mono text-slate-400">
                Corridor Area:{" "}
                {corridorAssessment.corridor_geometry.corridor_area_m2
                  ? `${corridorAssessment.corridor_geometry.corridor_area_m2.toFixed(1)} m²`
                  : "N/A"}{" "}
                · Conv Buffer: {corridorAssessment.convolution_buffer_px ?? "—"} px (
                {corridorAssessment.convolution_buffer_m?.toFixed(1) ?? "—"} m)
              </span>
            )}
          </div>

          {/* Route Decision Explainer */}
          {activeExplainer && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-cyan-200">Route Decision Explainer</h3>
                  <p className="text-xs text-slate-300 mt-0.5">{activeExplainer.decision_trace_summary}</p>
                </div>
                <span className="rounded border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1 text-xs font-mono text-cyan-200">
                  Dominant Driver: {activeExplainer.dominant_cost_driver}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                  <div className="text-[11px] font-semibold text-slate-300">Hard Constraints</div>
                  {Object.entries(activeExplainer.hard_constraints).map(([k, v]) => (
                    <div key={k} className="flex justify-between font-mono text-[11px]">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-slate-100">{String(v ?? "none")}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                  <div className="text-[11px] font-semibold text-slate-300">Soft Cost Weights</div>
                  {Object.entries(activeExplainer.soft_cost_weights).map(([k, v]) => (
                    <div key={k} className="flex justify-between font-mono text-[11px]">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-slate-100">{Number(v).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                  <div className="text-[11px] font-semibold text-slate-300">Grid Exclusion Summary</div>
                  {Object.entries(activeExplainer.grid_exclusion_summary).map(([k, v]) => (
                    <div key={k} className="flex justify-between font-mono text-[11px]">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-slate-100">{v}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1">
                  <div className="text-[11px] font-semibold text-slate-300">Total Cost Breakdown</div>
                  {Object.entries(activeExplainer.total_cost_breakdown).map(([k, v]) => (
                    <div key={k} className="flex justify-between font-mono text-[11px]">
                      <span className="text-slate-400">{k}</span>
                      <span className="text-slate-100">{Number(v).toFixed(2)}</span>
                    </div>
                  ))}
                  <div className="pt-1 text-[10px] text-amber-300">
                    Unverified optical excluded from bonus:{" "}
                    {activeExplainer.unverified_optical_candidates_excluded_from_bonus}
                  </div>
                </div>
              </div>

              {activeExplainer.sensitivity_notes?.length > 0 && (
                <div className="text-[11px] text-slate-300 space-y-0.5">
                  <div className="font-semibold text-slate-200">Sensitivity Notes:</div>
                  {activeExplainer.sensitivity_notes.map((n, idx) => (
                    <div key={idx}>• {n}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Segment Table + Segment Inspector */}
          {!corridorAssessment ? (
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-6 text-center text-xs text-slate-400">
              Click <strong>Assess Corridor</strong> or <strong>Run Full Mission & EVA Analysis</strong> to run
              polygon-masked terrain, spatial-union optical coverage, and STRtree observation association.
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
              <div className="xl:col-span-7 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3 overflow-x-auto">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white">
                    Polygon-Masked Corridor Segments ({corridorAssessment.segments.length})
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Click any segment row to highlight & focus 3D camera
                  </span>
                </div>
                <table className="w-full text-left text-[11px] border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-1.5 pr-2">Segment</th>
                      <th className="py-1.5 pr-2">Dist / 3D</th>
                      <th className="py-1.5 pr-2">Area (m²)</th>
                      <th className="py-1.5 pr-2">Slope / TRI</th>
                      <th className="py-1.5 pr-2">DEM Valid</th>
                      <th className="py-1.5 pr-2">Optical Foot / Valid</th>
                      <th className="py-1.5 pr-2">Scale Support</th>
                      <th className="py-1.5">Evidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {corridorAssessment.segments.map((seg) => {
                      const active = selectedSegment?.segment_id === seg.segment_id;
                      const footCov = seg.coverage.optical_footprint_coverage_fraction ?? seg.coverage.optical_coverage_fraction;
                      const validOptCov = seg.coverage.valid_optical_pixel_coverage_fraction ?? seg.coverage.optical_coverage_fraction;
                      const optUnmeasured =
                        seg.coverage.optical_coverage_status === "not_evaluated_no_registered_ortho" ||
                        (footCov == null && validOptCov == null);
                      return (
                        <tr
                          key={seg.segment_id}
                          onClick={() => handleSelectSegment(seg)}
                          className={`cursor-pointer transition ${
                            active ? "bg-yellow-500/10 text-white" : "hover:bg-slate-900/80 text-slate-300"
                          }`}
                        >
                          <td className="py-2 pr-2 font-mono">{seg.segment_id}</td>
                          <td className="py-2 pr-2 font-mono">
                            {(seg.horizontal_distance_m ?? seg.geodesic_distance_m).toFixed(1)} /{" "}
                            {seg.surface_distance_m.toFixed(1)} m
                          </td>
                          <td className="py-2 pr-2 font-mono">
                            {seg.corridor_area_m2 ? seg.corridor_area_m2.toFixed(0) : "—"}
                          </td>
                          <td className="py-2 pr-2 font-mono">
                            {seg.max_slope_deg?.toFixed(1) ?? "—"}° / {seg.max_tri_m?.toFixed(2) ?? "—"} m
                          </td>
                          <td className="py-2 pr-2 font-mono">
                            {(seg.coverage.valid_elevation_fraction * 100).toFixed(0)}%
                          </td>
                          <td className="py-2 pr-2 font-mono">
                            {optUnmeasured
                              ? "UNMEASURED"
                              : `${((footCov ?? 0) * 100).toFixed(0)}% / ${((validOptCov ?? 0) * 100).toFixed(0)}%`}
                          </td>
                          <td className="py-2 pr-2">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${
                                seg.resolution_supportable === false
                                  ? "border-red-500/40 bg-red-500/15 text-red-300"
                                  : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                              }`}
                            >
                              {seg.resolution_supportable === false ? "UNSUPPORTED" : "OK"}
                            </span>
                          </td>
                          <td className="py-2 font-mono">
                            O:{seg.associated_observation_ids.length} · Opt:{seg.optical_candidate_ids.length} · DEM:
                            {seg.morphology_candidate_ids.length}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Selected Segment Optical Crop & Candidate Details */}
              <div className="xl:col-span-5 rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3">
                <h3 className="text-sm font-semibold text-white">Selected Segment Spatial & Optical Audit</h3>
                {selectedSegment ? (
                  <div className="space-y-2.5 text-xs">
                    <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-[11px] font-mono">
                      <div>Segment: {selectedSegment.segment_id}</div>
                      <div>DEM Pixels: {selectedSegment.valid_terrain_pixel_count ?? "—"}/{selectedSegment.terrain_pixel_count ?? "—"}</div>
                      <div>Elev Δ: {selectedSegment.elevation_change_m?.toFixed(1) ?? "—"} m</div>
                      <div>Local Relief: {selectedSegment.local_relief_m?.toFixed(1) ?? "—"} m</div>
                      <div>Profile Curv: {selectedSegment.mean_profile_curvature_inv_m ?? "N/A"} 1/m</div>
                      <div>
                        Opt Area: {selectedSegment.coverage.optical_covered_area_m2?.toFixed(0) ?? "0"} m²
                      </div>
                    </div>
                    {selectedSegment.coverage.optical_contributing_product_ids?.length ? (
                      <div className="text-[11px] text-cyan-300">
                        Contributing Ortho Products:{" "}
                        <span className="font-mono">
                          {selectedSegment.coverage.optical_contributing_product_ids.join(", ")}
                        </span>
                      </div>
                    ) : null}
                    <div className="text-[11px] text-slate-400">
                      {selectedSegment.resolution_support_note ?? selectedSegment.uncertainty_summary}
                    </div>
                    {opticalCropUrl && (
                      <div className="space-y-1">
                        <div className="text-[11px] text-slate-400">
                          Derived HiRISE Optical Candidate Overlay Crop (server PNG):
                        </div>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={opticalCropUrl}
                          alt={`Optical crop for ${selectedSegment.segment_id}`}
                          className="w-full max-h-48 object-contain rounded border border-slate-800 bg-black"
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500">Select a segment to inspect details.</div>
                )}

                <div className="border-t border-slate-800 pt-2 space-y-1.5">
                  <div className="text-xs font-semibold text-amber-200 flex items-center justify-between">
                    <span>In-Corridor Optical Candidates ({corridorAssessment.optical_candidates.length})</span>
                    <span className="text-[10px] text-amber-400">2D Feature Only (Not Confirmed Boulder)</span>
                  </div>
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {corridorAssessment.optical_candidates.slice(0, 12).map((cand) => (
                      <div
                        key={cand.feature_id}
                        className="rounded border border-slate-800 bg-slate-900/60 p-2 text-[11px]"
                      >
                        <div className="flex justify-between font-mono text-amber-300">
                          <span>{cand.candidate_type}</span>
                          <span>
                            {cand.estimated_diameter_m
                              ? `~${cand.estimated_diameter_m.toFixed(1)} m`
                              : `score ${cand.score.toFixed(2)}`}
                          </span>
                        </div>
                        <div className="text-slate-400 truncate">{cand.disclaimer}</div>
                      </div>
                    ))}
                  </div>
                  {corridorAssessment.rejected_optical_candidates.length > 0 && (
                    <div className="text-[10px] text-slate-400">
                      Rejected false positives / edge artifacts:{" "}
                      {corridorAssessment.rejected_optical_candidates.length}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Associated Rover & PDS Observations */}
          {corridorAssessment && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 overflow-x-auto">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-white">
                  Shapely STRtree Associated Observations ({corridorAssessment.observations.length})
                </h3>
                <span className="text-[11px] text-slate-400">
                  Explicit spatial association (INTERSECTS_ROUTE / INTERSECTS_CORRIDOR / NEAR_CORRIDOR) & local product verification
                </span>
              </div>
              {corridorAssessment.observations.length === 0 ? (
                <div className="text-xs text-slate-400">
                  No verified Gale/Curiosity observations fall within {corridorAssessment.observation_search_radius_m} m
                  of the route corridor. (Perseverance Jezero records are strictly isolated.)
                </div>
              ) : (
                <table className="w-full text-left text-[11px] border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-1.5 pr-2">ID</th>
                      <th className="py-1.5 pr-2">Mission / Instrument</th>
                      <th className="py-1.5 pr-2">Association Type</th>
                      <th className="py-1.5 pr-2">Distance</th>
                      <th className="py-1.5 pr-2">Nearest Seg</th>
                      <th className="py-1.5 pr-2">Product Availability</th>
                      <th className="py-1.5">Availability / Boundary Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {corridorAssessment.observations.map((obs) => (
                      <tr key={obs.observation_id} className="text-slate-300">
                        <td className="py-1.5 pr-2 font-mono">{obs.observation_id}</td>
                        <td className="py-1.5 pr-2">
                          {obs.mission} · {obs.instrument} (Sol {obs.sol ?? "—"})
                        </td>
                        <td className="py-1.5 pr-2 font-mono text-cyan-300">
                          {obs.association_type ?? "NEAR_CORRIDOR"}
                        </td>
                        <td className="py-1.5 pr-2 font-mono">
                          {obs.distance_from_route_m !== null && obs.distance_from_route_m !== undefined
                            ? `${obs.distance_from_route_m.toFixed(1)} m`
                            : "UNLOCATED"}
                        </td>
                        <td className="py-1.5 pr-2 font-mono">{obs.nearest_segment_id ?? "—"}</td>
                        <td className="py-1.5 pr-2">
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${badgeClassForStatus(
                              obs.availability_status ??
                                (obs.product_available ? "VERIFIED_LOCAL" : "URL_UNVERIFIED")
                            )}`}
                          >
                            {obs.availability_status ??
                              (obs.product_available ? "VERIFIED_LOCAL" : "UNVERIFIED")}
                          </span>
                        </td>
                        <td className="py-1.5 text-slate-400 max-w-xs truncate">
                          {obs.availability_check_note ?? obs.product_id}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Mode Comparison Matrix */}
          {routeComparison && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 overflow-x-auto">
              <h3 className="text-sm font-semibold text-white">Multi-Mode Corridor Evidence Comparison</h3>
              <table className="w-full text-left text-[11px] border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-1.5 pr-2">Mode</th>
                    <th className="py-1.5 pr-2">Feasible</th>
                    <th className="py-1.5 pr-2">Surface Dist</th>
                    <th className="py-1.5 pr-2">Gain</th>
                    <th className="py-1.5 pr-2">Max Slope / TRI</th>
                    <th className="py-1.5 pr-2">DEM / Optical Cov</th>
                    <th className="py-1.5">Composite Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {routeComparison.entries.map((e) => (
                    <tr key={e.mode} className="text-slate-300">
                      <td className="py-1.5 pr-2 font-semibold">{e.mode_label}</td>
                      <td className="py-1.5 pr-2 font-mono">{e.feasible ? "YES" : `NO (${e.error_reason})`}</td>
                      <td className="py-1.5 pr-2 font-mono">
                        {e.surface_distance_m ? `${e.surface_distance_m.toFixed(1)} m` : "—"}
                      </td>
                      <td className="py-1.5 pr-2 font-mono">
                        {e.elevation_gain_m !== null && e.elevation_gain_m !== undefined
                          ? `${e.elevation_gain_m.toFixed(1)} m`
                          : "—"}
                      </td>
                      <td className="py-1.5 pr-2 font-mono">
                        {e.max_slope_deg?.toFixed(1) ?? "—"}° / {e.max_tri_m?.toFixed(2) ?? "—"} m
                      </td>
                      <td className="py-1.5 pr-2 font-mono">
                        {e.terrain_coverage_fraction !== null && e.terrain_coverage_fraction !== undefined
                          ? `${(e.terrain_coverage_fraction * 100).toFixed(0)}%`
                          : "—"}{" "}
                        /{" "}
                        {e.optical_coverage_fraction !== null && e.optical_coverage_fraction !== undefined
                          ? `${(e.optical_coverage_fraction * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      <td className="py-1.5 text-[10px] font-mono text-amber-300">{e.composite_risk_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ===================================================================== */}
      {/* SECTION B — OPERATIONAL TIMELINE & RETURN ROUTE INSPECTOR             */}
      {/* ===================================================================== */}
      {showSection("timeline") && (
        <section className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Navigation className="h-4 w-4 text-rose-400" />
              Section B · Operational Timeline, Point of No Return & Return Route Inspector
            </h2>
            {evaEnvelope && (
              <span className="text-xs font-mono text-rose-300">
                Strategy: {evaEnvelope.return_plan.return_strategy}
              </span>
            )}
          </div>

          {!evaEnvelope ? (
            <div className="text-xs text-slate-400">
              Run <strong>Evaluate EVA Envelope</strong> above to compute explicit outbound stops, Point-of-No-Return
              distance, and asymmetric return climb route.
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
              <div className="xl:col-span-4 rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-2 text-xs">
                <div className="font-semibold text-rose-200 flex items-center gap-1.5">
                  <RouteIcon className="h-4 w-4 text-rose-400" />
                  Return Path & Asymmetry Report
                </div>
                <div className="space-y-1 text-[11px] font-mono">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Distance (Horiz/3D)</span>
                    <span className="text-slate-100">
                      {evaEnvelope.return_plan.return_horizontal_distance_m.toFixed(1)} /{" "}
                      {evaEnvelope.return_plan.return_surface_distance_m.toFixed(1)} m
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Climb Gain / Loss</span>
                    <span className="text-slate-100">
                      +{evaEnvelope.return_plan.return_elevation_gain_m.toFixed(1)} / -
                      {evaEnvelope.return_plan.return_elevation_loss_m.toFixed(1)} m
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Asymmetric Climb Δ</span>
                    <span className="text-amber-300">
                      {evaEnvelope.return_plan.asymmetric_climb_delta_m >= 0 ? "+" : ""}
                      {evaEnvelope.return_plan.asymmetric_climb_delta_m.toFixed(2)} m
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Duration (Const)</span>
                    <span className="text-slate-100">
                      {formatDuration(evaEnvelope.return_plan.return_duration_constant_s)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Duration (Tobler Approx)</span>
                    <span className="text-slate-100">
                      {formatDuration(evaEnvelope.return_plan.return_duration_tobler_s)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Point of No Return</span>
                    <span className="text-cyan-300">
                      {evaEnvelope.return_plan.point_of_no_return_distance_m !== null &&
                      evaEnvelope.return_plan.point_of_no_return_distance_m !== undefined
                        ? `${evaEnvelope.return_plan.point_of_no_return_distance_m.toFixed(1)} m`
                        : "Requires speed + budget"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Time Margin</span>
                    <span className="text-slate-100">{formatDuration(evaEnvelope.return_plan.return_margin_s)}</span>
                  </div>
                </div>
                {evaEnvelope.return_plan.warnings.length > 0 && (
                  <div className="border-t border-slate-800 pt-2 space-y-1 text-[11px] text-amber-300">
                    {evaEnvelope.return_plan.warnings.map((w, idx) => (
                      <div key={idx}>• {w}</div>
                    ))}
                  </div>
                )}
              </div>

              <div className="xl:col-span-8 overflow-x-auto">
                <div className="text-[11px] text-slate-400 mb-1.5">
                  Click any timeline row to highlight its corridor polygon in the 3D scene and fly the camera:
                </div>
                <table className="w-full text-left text-[11px] border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-1.5 pr-2">#</th>
                      <th className="py-1.5 pr-2">Leg Role</th>
                      <th className="py-1.5 pr-2">Segment / Step</th>
                      <th className="py-1.5 pr-2">Time Window</th>
                      <th className="py-1.5 pr-2">Dur (Const / Tobler)</th>
                      <th className="py-1.5 pr-2">Distance</th>
                      <th className="py-1.5 pr-2">Elev + / -</th>
                      <th className="py-1.5">Cumul. Climb Work</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {evaEnvelope.schedule.map((item) => {
                      const active = selectedTimelineIndex === item.sequence_index;
                      return (
                        <tr
                          key={item.sequence_index}
                          onClick={() => handleSelectTimelineStep(item)}
                          className={`cursor-pointer transition ${
                            active ? "bg-rose-500/15 text-white" : "hover:bg-slate-900/80 text-slate-300"
                          }`}
                        >
                          <td className="py-2 pr-2 font-mono">{item.sequence_index + 1}</td>
                          <td className="py-2 pr-2">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] font-mono ${
                                item.leg_role === "return"
                                  ? "border-rose-500/40 bg-rose-500/15 text-rose-200"
                                  : "border-cyan-500/40 bg-cyan-500/15 text-cyan-200"
                              }`}
                            >
                              {item.leg_role}
                            </span>
                          </td>
                          <td className="py-2 pr-2 font-mono">{item.label}</td>
                          <td className="py-2 pr-2 font-mono">
                            {formatDuration(item.start_time_s)} → {formatDuration(item.end_time_s)}
                          </td>
                          <td className="py-2 pr-2 font-mono">
                            {formatDuration(item.duration_constant_speed_s)} /{" "}
                            {formatDuration(item.duration_tobler_approx_s)}
                          </td>
                          <td className="py-2 pr-2 font-mono">{item.distance_m.toFixed(1)} m</td>
                          <td className="py-2 pr-2 font-mono">
                            +{item.elevation_gain_m.toFixed(1)} / -{item.elevation_loss_m.toFixed(1)} m
                          </td>
                          <td className="py-2 font-mono">
                            {item.cumulative_climb_work_j !== null && item.cumulative_climb_work_j !== undefined
                              ? `${(item.cumulative_climb_work_j / 1000).toFixed(2)} kJ`
                              : "Requires mass"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Prompt 16: Checkpoint-by-Checkpoint Independent Return Turnback PONR & Return Alternatives */}
          {evaEnvelope?.return_plan && (
            <div
              className="rounded-xl border border-cyan-500/35 bg-slate-950/75 p-4 space-y-3"
              data-testid="prompt16-turnback-analysis"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-white">
                    Independent Return Verification &amp; Checkpoint Turnback PONR
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Status:{" "}
                    <span className="font-mono text-cyan-300">
                      {evaEnvelope.return_plan.return_status ?? evaEnvelope.return_plan.return_strategy}
                    </span>{" "}
                    · Method:{" "}
                    <span className="font-mono text-slate-200">
                      {evaEnvelope.return_plan.turnback_ponr_method ?? "single_sweep_reverse_dijkstra"}
                    </span>
                    {evaEnvelope.return_plan.locomotion_model && (
                      <>
                        {" "}
                        · Locomotion:{" "}
                        <span className="font-mono text-amber-300">
                          {evaEnvelope.return_plan.locomotion_model.model_id} (
                          {evaEnvelope.return_plan.locomotion_model.model_version})
                        </span>
                      </>
                    )}
                  </p>
                </div>
                {evaEnvelope.return_plan.return_alternatives && evaEnvelope.return_plan.return_alternatives.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <button
                      type="button"
                      onClick={() => setSelectedReturnAlternativeId(null)}
                      className={`rounded border px-2 py-1 font-mono ${
                        selectedReturnAlternativeId === null
                          ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                          : "border-slate-700 bg-slate-900 text-slate-300"
                      }`}
                    >
                      Primary Return
                    </button>
                    {evaEnvelope.return_plan.return_alternatives.map((alt) => (
                      <button
                        key={alt.alternative_id}
                        type="button"
                        onClick={() => setSelectedReturnAlternativeId(alt.alternative_id)}
                        className={`rounded border px-2 py-1 font-mono ${
                          selectedReturnAlternativeId === alt.alternative_id
                            ? "border-rose-400 bg-rose-500/20 text-rose-200"
                            : "border-slate-700 bg-slate-900 text-slate-300"
                        }`}
                      >
                        {alt.strategy_label} ({alt.surface_distance_m.toFixed(0)} m / +{alt.elevation_gain_m.toFixed(1)} m)
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {evaEnvelope.return_plan.locomotion_model?.unvalidated_note && (
                <div className="rounded border border-amber-500/30 bg-amber-950/20 px-3 py-1.5 text-[11px] text-amber-200">
                  {evaEnvelope.return_plan.locomotion_model.unvalidated_note}
                </div>
              )}

              {evaEnvelope.return_plan.turnback_checkpoints && evaEnvelope.return_plan.turnback_checkpoints.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[11px] border-collapse font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-1.5 pr-2">Checkpoint</th>
                        <th className="py-1.5 pr-2">Outbound Dist</th>
                        <th className="py-1.5 pr-2">Out Elapsed</th>
                        <th className="py-1.5 pr-2">Indep. Return Dist / Gain</th>
                        <th className="py-1.5 pr-2">Indep. Return Time (C/T)</th>
                        <th className="py-1.5 pr-2">Roundtrip Total</th>
                        <th className="py-1.5 pr-2">Differs from Outbound</th>
                        <th className="py-1.5">Budget Fit</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/70">
                      {evaEnvelope.return_plan.turnback_checkpoints.map((cp) => (
                        <tr key={cp.checkpoint_index} className="text-slate-300">
                          <td className="py-1.5 pr-2">
                            #{cp.checkpoint_index} ({cp.lat.toFixed(4)}°, {cp.lon_east.toFixed(4)}°E)
                          </td>
                          <td className="py-1.5 pr-2">{cp.outbound_distance_m.toFixed(1)} m</td>
                          <td className="py-1.5 pr-2">{formatDuration(cp.outbound_elapsed_s)}</td>
                          <td className="py-1.5 pr-2">
                            {cp.return_route_computed
                              ? `${cp.independent_return_distance_m?.toFixed(1) ?? "?"} m / +${cp.independent_return_elevation_gain_m?.toFixed(1) ?? "0"} m`
                              : cp.failure_reason ?? "UNREACHABLE"}
                          </td>
                          <td className="py-1.5 pr-2">
                            {formatDuration(cp.independent_return_duration_constant_s)} /{" "}
                            {formatDuration(cp.independent_return_duration_tobler_s)}
                          </td>
                          <td className="py-1.5 pr-2">{formatDuration(cp.estimated_roundtrip_time_s)}</td>
                          <td className="py-1.5 pr-2">{cp.return_differs_from_outbound ? "YES (Asymmetric)" : "SAME"}</td>
                          <td className="py-1.5">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                cp.fits_usable_budget === true
                                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                                  : cp.fits_usable_budget === false
                                  ? "border-red-500/40 bg-red-500/15 text-red-300"
                                  : "border-slate-700 bg-slate-800 text-slate-300"
                              }`}
                            >
                              {cp.fits_usable_budget === true ? "FITS" : cp.fits_usable_budget === false ? "EXCEEDS" : "UNBOUNDED"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* ===================================================================== */}
      {/* SECTION C — UNIT-AWARE RESOURCE BUDGET & MECHANICAL CLIMB WORK        */}
      {/* ===================================================================== */}
      {showSection("resources") && (
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Clock className="h-4 w-4 text-emerald-400" />
            Section C · Time Budget, Mechanical Climb Work & Unit-Aware Resource Budgets
          </h2>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Time Budget Card */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Time Budget Breakdown</h3>
                <span className="font-mono text-[10px] text-cyan-300">
                  {evaEnvelope?.time_budget.speed_model_used ?? (useToblerApprox ? "TOBLER_STYLE" : "CONSTANT_USER_SPEED")}
                </span>
              </div>
              {evaEnvelope ? (
                <div className="space-y-1 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Outbound Travel</span>
                    <span>{formatDuration(evaEnvelope.time_budget.outbound_travel_s)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Science Stops</span>
                    <span>{formatDuration(evaEnvelope.time_budget.science_stops_s)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Op Overhead</span>
                    <span>{formatDuration(evaEnvelope.time_budget.operational_overhead_s)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Travel</span>
                    <span>{formatDuration(evaEnvelope.time_budget.return_travel_s)}</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-800 pt-1">
                    <span className="text-slate-300">Total Required EVA</span>
                    <span className="text-white">{formatDuration(evaEnvelope.time_budget.total_required_s)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Usable Budget (after reserve)</span>
                    <span>{formatDuration(evaEnvelope.time_budget.usable_budget_s)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Time Margin</span>
                    <span
                      className={
                        (evaEnvelope.time_budget.time_margin_s ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"
                      }
                    >
                      {evaEnvelope.time_budget.time_margin_s !== null &&
                      evaEnvelope.time_budget.time_margin_s !== undefined
                        ? `${(evaEnvelope.time_budget.time_margin_s / 60).toFixed(1)} min`
                        : "Unavailable"}
                    </span>
                  </div>
                  <div className="pt-1 font-sans text-[10px] text-amber-300">
                    {evaEnvelope.time_budget.speed_model_validation_note}
                  </div>
                </div>
              ) : (
                <div className="text-slate-500">Not evaluated yet.</div>
              )}
            </div>

            {/* Mechanical Climb Work Card */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Mechanical Climb Work (W = m g ΣΔh+)</h3>
                <span className="font-mono text-[10px] text-slate-400">
                  g ={" "}
                  {evaEnvelope?.energy_budget.mars_gravity_m_s2 !== null &&
                  evaEnvelope?.energy_budget.mars_gravity_m_s2 !== undefined
                    ? `${evaEnvelope.energy_budget.mars_gravity_m_s2} m/s²`
                    : "UNAVAILABLE"}
                </span>
              </div>
              {evaEnvelope ? (
                <div className="space-y-1 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Mass (Suit + Payload)</span>
                    <span>
                      {evaEnvelope.energy_budget.total_mass_kg !== null &&
                      evaEnvelope.energy_budget.total_mass_kg !== undefined
                        ? `${evaEnvelope.energy_budget.total_mass_kg.toFixed(1)} kg`
                        : "Requires explicit masses"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Mars Surface Weight</span>
                    <span>
                      {evaEnvelope.energy_budget.surface_weight_n !== null &&
                      evaEnvelope.energy_budget.surface_weight_n !== undefined
                        ? `${evaEnvelope.energy_budget.surface_weight_n.toFixed(1)} N`
                        : "Unavailable"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Outbound Climb Work</span>
                    <span>
                      {evaEnvelope.energy_budget.outbound_climb_work_j !== null &&
                      evaEnvelope.energy_budget.outbound_climb_work_j !== undefined
                        ? `${(evaEnvelope.energy_budget.outbound_climb_work_j / 1000).toFixed(2)} kJ`
                        : "Unavailable"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Return Climb Work</span>
                    <span>
                      {evaEnvelope.energy_budget.return_climb_work_j !== null &&
                      evaEnvelope.energy_budget.return_climb_work_j !== undefined
                        ? `${(evaEnvelope.energy_budget.return_climb_work_j / 1000).toFixed(2)} kJ`
                        : "Unavailable"}
                    </span>
                  </div>
                  <div className="flex justify-between border-t border-slate-800 pt-1">
                    <span className="text-slate-200">Total Positive Climb Work</span>
                    <span className="text-cyan-300">
                      {evaEnvelope.energy_budget.total_positive_climb_work_j !== null &&
                      evaEnvelope.energy_budget.total_positive_climb_work_j !== undefined
                        ? `${(evaEnvelope.energy_budget.total_positive_climb_work_j / 1000).toFixed(2)} kJ`
                        : "Unavailable"}
                    </span>
                  </div>
                  <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 p-2 font-sans text-[10px] text-amber-200">
                    {evaEnvelope.energy_budget.disclaimer}
                  </div>
                </div>
              ) : missionDossier?.physical_energy_budget ? (
                <div className="space-y-1 font-mono text-[11px]">
                  <div>
                    Elev Gain: +{missionDossier.physical_energy_budget.positive_elevation_gain_m.toFixed(1)} m
                  </div>
                  <div>
                    PE Increase:{" "}
                    {missionDossier.physical_energy_budget.gravitational_pe_increase_j !== null &&
                    missionDossier.physical_energy_budget.gravitational_pe_increase_j !== undefined
                      ? `${(missionDossier.physical_energy_budget.gravitational_pe_increase_j / 1000).toFixed(2)} kJ`
                      : "Unavailable"}
                  </div>
                  <div className="font-sans text-[10px] text-amber-300">
                    {missionDossier.physical_energy_budget.disclaimer}
                  </div>
                </div>
              ) : (
                <div className="text-slate-500">Not evaluated yet.</div>
              )}
            </div>

            {/* Resource Budget Evaluation Card */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">Explicit Resource Budget</h3>
                {evaEnvelope && (
                  <span
                    className={`rounded border px-2 py-0.5 font-mono text-[10px] ${badgeClassForStatus(
                      evaEnvelope.resource_budget.overall_status
                    )}`}
                  >
                    {evaEnvelope.resource_budget.overall_status}
                  </span>
                )}
              </div>
              {!evaEnvelope || evaEnvelope.resource_budget.entries.length === 0 ? (
                <div className="text-[11px] text-slate-400">
                  No user-supplied consumable or battery limits configured yet. Add an explicit O2 or battery limit in
                  the parameters panel above to compute Q_used = Q_dot · t.
                </div>
              ) : (
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {evaEnvelope.resource_budget.entries.map((entry) => (
                    <div
                      key={entry.resource_name}
                      className="rounded border border-slate-800 bg-slate-900/60 p-2 text-[11px] space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-semibold text-white">{entry.resource_name}</span>
                        <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${badgeClassForStatus(entry.status)}`}>
                          {entry.status}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-1 font-mono text-[10px] text-slate-300">
                        <div>Init: {entry.initial_quantity ?? "—"} {entry.unit}</div>
                        <div>Consumed: {formatNum(entry.estimated_consumed, 3)} {entry.unit}</div>
                        <div>Reserve Req: {formatNum(entry.reserve_required, 3)} {entry.unit}</div>
                        <div>Margin Above Res: {formatNum(entry.margin_above_reserve, 3)} {entry.unit}</div>
                      </div>
                      <div className="text-[10px] text-slate-400">{entry.explanation}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ===================================================================== */}
      {/* SECTION D — CONSTRAINT ANALYSIS TABLE                                 */}
      {/* ===================================================================== */}
      {showSection("constraints") && (
        <section className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-3 overflow-x-auto">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Target className="h-4 w-4 text-cyan-400" />
            Section D · Structured Constraint Analysis Matrix
          </h2>
          {!evaEnvelope ? (
            <div className="text-xs text-slate-400">
              Evaluate EVA operational envelope to inspect structured PASS / FAIL / UNAVAILABLE / UNVALIDATED checks.
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="py-2 pr-3">Constraint ID</th>
                  <th className="py-2 pr-3">Category</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Configured Limit</th>
                  <th className="py-2 pr-3">Evaluated Value</th>
                  <th className="py-2">Explanation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {evaEnvelope.constraints.map((c) => (
                  <tr key={c.constraint_id} className="text-slate-300">
                    <td className="py-2 pr-3 font-mono text-[11px]">{c.constraint_id}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-slate-400">{c.category}</td>
                    <td className="py-2 pr-3">
                      <span className={`rounded border px-2 py-0.5 font-mono text-[10px] ${badgeClassForStatus(c.status)}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px]">{c.configured_limit ?? "—"}</td>
                    <td className="py-2 pr-3 font-mono text-[11px]">{c.evaluated_value ?? "—"}</td>
                    <td className="py-2 text-[11px] text-slate-300">{c.explanation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {/* ===================================================================== */}
      {/* PROMPT 20 — HUMAN MARSWALK OPERATIONAL INTELLIGENCE & REPLANNING      */}
      {/* ===================================================================== */}
      {evaEnvelope && (
        <Prompt20OperationalPanels
          activeParams={buildEvalParams(parsedResourcesPreview)}
        />
      )}

      {/* ===================================================================== */}
      {/* SECTION E — 15-DOMAIN READINESS, CACHE VALIDITY & DATASET AUDIT       */}
      {/* ===================================================================== */}
      {showSection("readiness") && (
        <section className="space-y-4">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-400" />
            Section E · 15-Domain Evidence Readiness, Cache Validity & Dataset Validation Audit
          </h2>

          {/* Explicit Separation Banner */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-3 space-y-1">
              <div className="text-slate-400">Overall Readiness State</div>
              <div className="text-sm font-mono font-semibold text-white">
                {missionDossier?.readiness_state ?? "UNASSESSED"}
              </div>
              <div className="text-[11px] text-slate-400">
                Policy: {missionDossier?.readiness_policy_version ?? corridorAssessment?.readiness_policy_version ?? "readiness-v2.0"}
              </div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-3 space-y-1">
              <div className="text-slate-400">Mathematical Assessment Complete</div>
              <div className="text-sm font-mono font-semibold text-cyan-300 flex items-center gap-1.5">
                {missionDossier?.mathematical_assessment_complete ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                ) : (
                  <RefreshCw className="h-4 w-4 text-amber-400" />
                )}
                {missionDossier?.mathematical_assessment_complete ? "YES (Computations Finished)" : "NO / PENDING"}
              </div>
              <div className="text-[11px] text-slate-400">
                Completeness of terrain/route math never certifies human EVA safety.
              </div>
            </div>
            <div className="rounded-xl border border-red-500/35 bg-red-950/20 p-3 space-y-1">
              <div className="text-red-300 font-semibold">Operational Human Safety Certification</div>
              <div className="text-sm font-mono font-semibold text-red-200 flex items-center gap-1.5">
                <XCircle className="h-4 w-4 text-red-400" />
                UNVALIDATED (operational_safety_certified = false)
              </div>
              <div className="text-[11px] text-red-200/80">
                {missionDossier?.safety_certification_note ??
                  "Engineering & scientific planning workstation only; no flight-certified life-support or physiological validation."}
              </div>
            </div>
          </div>

          {/* 15-Domain Readiness Matrix */}
          {missionDossier?.domain_assessments && missionDossier.domain_assessments.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 overflow-x-auto">
              <h3 className="text-sm font-semibold text-white">
                Explicit 15-Domain Readiness Matrix ({missionDossier.domain_assessments.length} domains)
              </h3>
              <table className="w-full text-left text-[11px] border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-1.5 pr-2">Domain</th>
                    <th className="py-1.5 pr-2">Status</th>
                    <th className="py-1.5 pr-2">Evidence Basis</th>
                    <th className="py-1.5">Threshold / Limitation Rule</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {missionDossier.domain_assessments.map((dom) => (
                    <tr key={dom.domain} className="text-slate-300">
                      <td className="py-1.5 pr-2 font-mono">{dom.domain}</td>
                      <td className="py-1.5 pr-2">
                        <span
                          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${badgeClassForStatus(
                            dom.status
                          )}`}
                        >
                          {dom.status}
                        </span>
                      </td>
                      <td className="py-1.5 pr-2">{dom.evidence_basis}</td>
                      <td className="py-1.5 text-slate-400">
                        <div>{dom.threshold_or_rule}</div>
                        {(dom.spatial_footprint_coverage_fraction != null || dom.resolution_adequacy) && (
                          <div className="text-[10px] font-mono text-cyan-300/90 mt-0.5">
                            {dom.spatial_footprint_coverage_fraction != null &&
                              `Footprint: ${(dom.spatial_footprint_coverage_fraction * 100).toFixed(0)}% `}
                            {dom.valid_measurement_coverage_fraction != null &&
                              `· Valid: ${(dom.valid_measurement_coverage_fraction * 100).toFixed(0)}% `}
                            {dom.resolution_adequacy && `· Scale: ${dom.resolution_adequacy}`}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Dataset Validation Inventory */}
          {corridorAssessment && corridorAssessment.dataset_inventory.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 overflow-x-auto">
              <h3 className="text-sm font-semibold text-white">Dataset Inventory & Validation Stage Audit</h3>
              <table className="w-full text-left text-[11px] border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-1.5 pr-2">Dataset ID</th>
                    <th className="py-1.5 pr-2">Type</th>
                    <th className="py-1.5 pr-2">Validation Stage</th>
                    <th className="py-1.5 pr-2">Resolution</th>
                    <th className="py-1.5 pr-2">Acquired</th>
                    <th className="py-1.5">Authority & Applicability</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {corridorAssessment.dataset_inventory.map((ds) => {
                    const stageLabel = ds.scientifically_validated
                      ? "RESEARCH_GRADE"
                      : ds.processed && ds.renderable
                      ? "ASSESSED"
                      : ds.acquired
                      ? "PARTIALLY_ASSESSED"
                      : "CONTEXT_ONLY";
                    return (
                      <tr key={ds.dataset_id} className="text-slate-300">
                        <td className="py-1.5 pr-2 font-mono">{ds.dataset_id}</td>
                        <td className="py-1.5 pr-2 font-mono">{ds.product_type}</td>
                        <td className="py-1.5 pr-2">
                          <span
                            className={`rounded border px-1.5 py-0.5 font-mono text-[10px] ${badgeClassForStatus(
                              stageLabel
                            )}`}
                          >
                            {ds.scientifically_validated
                              ? "SCIENTIFICALLY_VALIDATED"
                              : ds.processed
                              ? "PROCESSED"
                              : ds.acquired
                              ? "ACQUIRED"
                              : "CATALOGUED_ONLY"}
                          </span>
                        </td>
                        <td className="py-1.5 pr-2 font-mono">
                          {ds.native_resolution_m ? `${ds.native_resolution_m} m/px` : "—"}
                        </td>
                        <td className="py-1.5 pr-2 font-mono">{ds.acquired ? "LOCAL" : "NO"}</td>
                        <td className="py-1.5 text-slate-400">
                          {ds.missing_requirement ?? (ds.renderable ? "Renderable & Verified" : "Pending processing")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Uncertainty & Unmodeled Limitations */}
          {(missionDossier?.unmodeled_parameters.length || evaEnvelope?.limitations.length) && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-[11px]">
              <div>
                <h4 className="font-semibold text-amber-200 mb-1">Explicitly Unmodeled Parameters</h4>
                <ul className="list-disc pl-4 space-y-0.5 text-slate-300">
                  {(missionDossier?.unmodeled_parameters ?? []).map((u, i) => (
                    <li key={i}>{u}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-cyan-200 mb-1">Operational Envelope Limitations & Notes</h4>
                <ul className="list-disc pl-4 space-y-0.5 text-slate-300">
                  {[...(evaEnvelope?.limitations ?? []), ...(evaEnvelope?.uncertainty_notes ?? [])].map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Prompt 16: PDS3 Elevation Uncertainty, Horn 3x3 / TRI Propagation & 7-Scale Feature Observability */}
          <div
            className="rounded-xl border border-cyan-500/35 bg-slate-950/75 p-4 space-y-4"
            data-testid="prompt16-uncertainty-panel"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-white">
                  Prompt 16 · DEM Uncertainty Propagation, 3-State Traversability &amp; Resolution Observability
                </h3>
                <p className="text-[11px] text-slate-400">
                  Separates PDS3 empirical error maps (when absent: UNQUANTIFIED) from metadata nominal precision probes and Nyquist hazard limits.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void fetchCorridorUncertainty({ dataset_id: selectedDemDatasetId })}
                  disabled={loadingUncertainty}
                  className="rounded border border-cyan-500/40 bg-cyan-500/15 px-2.5 py-1 text-[11px] font-mono text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50"
                >
                  {loadingUncertainty ? "Refreshing Uncertainty..." : "Refresh Uncertainty Audit"}
                </button>
                <button
                  type="button"
                  onClick={() => void fetchComplementarity()}
                  disabled={loadingComplementarity}
                  className="rounded border border-purple-500/40 bg-purple-500/15 px-2.5 py-1 text-[11px] font-mono text-purple-200 hover:bg-purple-500/25 disabled:opacity-50"
                >
                  {loadingComplementarity ? "Refreshing Registry..." : "Refresh Complementarity"}
                </button>
              </div>
            </div>

            {corridorUncertainty ? (
              <div className="space-y-4 text-[11px]">
                {/* Negative Evidence Prohibition Callout */}
                <div className="rounded-lg border border-rose-500/40 bg-rose-950/25 p-3 text-rose-200 space-y-1">
                  <div className="font-bold uppercase tracking-wider text-[10px]">
                    Negative Evidence Guarantee · zero_detections_implies_obstacle_free ={" "}
                    {String(corridorUncertainty.negative_evidence.zero_detections_implies_obstacle_free)}
                  </div>
                  <div>{corridorUncertainty.negative_evidence.statement}</div>
                  {corridorUncertainty.negative_evidence.unresolved_hazard_classes.length > 0 && (
                    <div className="font-mono text-[10px] text-rose-300">
                      Unresolved Classes: {corridorUncertainty.negative_evidence.unresolved_hazard_classes.join(", ")}
                    </div>
                  )}
                </div>

                {/* Dataset Uncertainty Inventory + Slope / TRI Summary */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1 font-mono">
                    <div className="font-bold text-cyan-300">Dataset PDS3 / Dtype Inventory</div>
                    <div>Product: {corridorUncertainty.dataset_profile.product_id}</div>
                    <div>Status: {corridorUncertainty.dataset_profile.overall_elevation_uncertainty_status}</div>
                    <div>
                      Per-Pixel Error Raster: {String(corridorUncertainty.dataset_profile.has_per_pixel_error_raster)}
                    </div>
                    <div>
                      Raw PDS / Proc Raster:{" "}
                      {corridorUncertainty.dataset_profile.raw_pds_sample_bits ??
                        corridorUncertainty.dataset_profile.sample_bits ??
                        "?"}
                      -bit{" "}
                      {corridorUncertainty.dataset_profile.raw_pds_sample_type ??
                        corridorUncertainty.dataset_profile.sample_type ??
                        "?"}{" "}
                      / proc={corridorUncertainty.dataset_profile.processed_raster_dtype ?? "?"} (quant available:{" "}
                      {String(corridorUncertainty.dataset_profile.quantization_uncertainty_available ?? corridorUncertainty.dataset_profile.is_integer_quantized)})
                    </div>
                    {corridorUncertainty.dataset_profile.scaling_factor_source && (
                      <div className="text-[10px] text-cyan-300">
                        Scaling: {corridorUncertainty.dataset_profile.scaling_factor ?? "unverified"} (
                        {corridorUncertainty.dataset_profile.scaling_factor_source})
                      </div>
                    )}
                    {corridorUncertainty.dataset_profile.elevation_uncertainty_metrics.map((m) => (
                      <div key={m.metric_name} className="text-[10px] text-slate-300 border-t border-slate-800 pt-1">
                        {m.metric_name}: {m.value != null ? `${m.value} ${m.units ?? ""}` : m.status} ({m.status})
                      </div>
                    ))}
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1 font-mono">
                    <div className="font-bold text-amber-300">Horn 3x3 &amp; Riley TRI Propagation</div>
                    <div>Slope Probe Status: {corridorUncertainty.slope_uncertainty.status}</div>
                    <div>
                      Basis σz:{" "}
                      {corridorUncertainty.slope_uncertainty.basis_sigma_z_m != null
                        ? `${corridorUncertainty.slope_uncertainty.basis_sigma_z_m.toFixed(3)} m`
                        : "Unquantified"}
                    </div>
                    <div>
                      Mean / Max Slope σ:{" "}
                      {corridorUncertainty.slope_uncertainty.mean_slope_sigma_deg != null
                        ? `${corridorUncertainty.slope_uncertainty.mean_slope_sigma_deg.toFixed(2)}° / ${corridorUncertainty.slope_uncertainty.max_slope_sigma_deg?.toFixed(2) ?? "?"}°`
                        : "Unavailable"}
                    </div>
                    <div>
                      Near-Flat Bias Affected:{" "}
                      {corridorUncertainty.slope_uncertainty.near_flat_bias_affected_fraction != null
                        ? `${(corridorUncertainty.slope_uncertainty.near_flat_bias_affected_fraction * 100).toFixed(1)}%`
                        : "—"}
                    </div>
                    <div>
                      TRI Mean / Max σ:{" "}
                      {corridorUncertainty.roughness_uncertainty.mean_tri_sigma_m != null
                        ? `${corridorUncertainty.roughness_uncertainty.mean_tri_sigma_m.toFixed(3)} m / ${corridorUncertainty.roughness_uncertainty.max_tri_sigma_m?.toFixed(3) ?? "?"} m`
                        : "Unavailable"}
                    </div>
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1 font-mono">
                    <div className="font-bold text-emerald-300">3-State Traversability Breakdown</div>
                    <div>
                      Evaluated:{" "}
                      {(corridorUncertainty.traversability_breakdown.evaluated_fraction * 100).toFixed(1)}% (
                      {corridorUncertainty.traversability_breakdown.evaluated_cell_count} cells)
                    </div>
                    <div>
                      Known Exclusion:{" "}
                      {(corridorUncertainty.traversability_breakdown.known_exclusion_fraction * 100).toFixed(1)}% (
                      {corridorUncertainty.traversability_breakdown.known_exclusion_cell_count} cells)
                    </div>
                    <div>
                      Unknown / Insufficient:{" "}
                      {(corridorUncertainty.traversability_breakdown.unknown_insufficient_fraction * 100).toFixed(1)}% (
                      {corridorUncertainty.traversability_breakdown.unknown_insufficient_cell_count} cells)
                    </div>
                    <div className="text-[10px] text-slate-400 border-t border-slate-800 pt-1">
                      Registration: {corridorUncertainty.registration_uncertainty.overall_status}
                    </div>
                  </div>
                </div>

                {/* 7-Scale Feature Observability Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[11px] border-collapse font-mono">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-1.5 pr-2">Feature / Scale Category</th>
                        <th className="py-1.5 pr-2">Observability State</th>
                        <th className="py-1.5 pr-2">Source Dataset</th>
                        <th className="py-1.5 pr-2">Min Resolvable (Nyquist)</th>
                        <th className="py-1.5">Rationale</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/70">
                      {corridorUncertainty.observability.map((obs) => (
                        <tr key={obs.category} className="text-slate-300">
                          <td className="py-1.5 pr-2 font-bold">{obs.category}</td>
                          <td className="py-1.5 pr-2">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                obs.observability_state === "RESOLVABLE"
                                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                                  : obs.observability_state === "MARGINAL"
                                  ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                                  : "border-rose-500/40 bg-rose-500/15 text-rose-300"
                              }`}
                            >
                              {obs.observability_state}
                            </span>
                          </td>
                          <td className="py-1.5 pr-2">{obs.source_dataset_id}</td>
                          <td className="py-1.5 pr-2">
                            {obs.minimum_resolvable_feature_size_m != null
                              ? `${obs.minimum_resolvable_feature_size_m.toFixed(2)} m`
                              : "—"}
                          </td>
                          <td className="py-1.5 font-sans text-slate-400">{obs.rationale}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-400">
                Click &ldquo;Refresh Uncertainty Audit&rdquo; or run full mission evaluation to load PDS3 elevation uncertainty, Horn 3x3 slope sigma, and 7-scale observability checks.
              </div>
            )}
          </div>

          {/* Prompt 16: Data Complementarity Registry (supports vs does_not_support) */}
          {complementarityReport && (
            <div
              className="rounded-xl border border-purple-500/35 bg-slate-950/75 p-4 space-y-3 text-[11px]"
              data-testid="prompt16-complementarity-panel"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-white">
                  Data Complementarity Registry ({complementarityReport.registry_id} · {complementarityReport.registry_version})
                </h3>
                <span className="font-mono text-[10px] text-purple-300">
                  Active Sources: {complementarityReport.active_dataset_ids.length}
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {complementarityReport.dataset_roles.map((role) => (
                  <div
                    key={role.dataset_id_pattern}
                    className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-cyan-200">{role.title}</span>
                      <span className="font-mono text-[10px] text-slate-400">{role.mission_and_instrument}</span>
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">{role.native_scale_description}</div>
                    {role.isolation_warning && (
                      <div className="rounded border border-rose-500/40 bg-rose-950/30 px-2 py-1 text-[10px] text-rose-200">
                        {role.isolation_warning}
                      </div>
                    )}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      <div>
                        <div className="font-mono text-[10px] text-emerald-300 font-bold">Supports:</div>
                        <ul className="list-disc pl-4 space-y-0.5 text-slate-300">
                          {role.supports.map((s, idx) => (
                            <li key={idx}>{s}</li>
                          ))}
                        </ul>
                      </div>
                      <div>
                        <div className="font-mono text-[10px] text-rose-300 font-bold">Does NOT Support:</div>
                        <ul className="list-disc pl-4 space-y-0.5 text-slate-400">
                          {role.does_not_support.map((d, idx) => (
                            <li key={idx}>{d}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Prompt 16: Dependency Signature & Policy Version Trace */}
          {dependencyTrace && (
            <div
              className="rounded-xl border border-slate-800 bg-slate-950/75 p-4 space-y-2 text-[11px] font-mono"
              data-testid="prompt16-dependency-trace"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-sans font-semibold text-white">
                  Assessment Dependency Signature &amp; Policy Trace
                </span>
                <span
                  className={`rounded border px-2 py-0.5 text-[10px] ${badgeClassForStatus(
                    String(dependencyTrace.cache_validity ?? "UNAVAILABLE")
                  )}`}
                >
                  {String(dependencyTrace.cache_validity ?? "UNAVAILABLE")}
                </span>
              </div>
              <pre className="max-h-48 overflow-auto rounded border border-slate-800 bg-black/50 p-2 text-[10px] text-slate-300">
                {JSON.stringify(dependencyTrace.stored_dependency_signature ?? dependencyTrace, null, 2)}
              </pre>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
