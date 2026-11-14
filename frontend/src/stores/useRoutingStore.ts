import { create } from "zustand";
import { API_BASE_URL } from "@/lib/constants";
import type {
  PathAlgorithm,
  PickedSurfacePoint,
  PlanningMode,
  RouteCompareResponse,
  RouteComputeResponse,
  RouteCoordinateInput,
  RoutePlanningConstraints,
  ScienceTarget,
  SurfacePickMode,
  TerrainMeshManifest,
  TextureOverlayMode,
} from "@/types";

export interface CameraFocusTarget {
  lat: number;
  lon_east: number;
  elevation_m?: number;
  nonce: number;
}

export type CameraPresetType = "oblique" | "top_down" | "focus_route" | "reset";

export interface CameraPresetRequest {
  preset: CameraPresetType;
  nonce: number;
}

interface RoutingStoreState {
  // DEM & 3D Surface Viewer Controls
  selectedDemDatasetId: string;
  meshManifest: TerrainMeshManifest | null;
  manifestLoading: boolean;
  manifestError: string | null;
  activeLod: number;
  activeOverlayMode: TextureOverlayMode;
  verticalExaggeration: number; // Default 1.0 = True Scale
  surfacePickMode: SurfacePickMode;
  pickedSurfacePoint: PickedSurfacePoint | null;

  // Planning Inputs (explicit coordinates + user constraints)
  startPoint: RouteCoordinateInput | null;
  destinationPoint: RouteCoordinateInput | null;
  selectedTargetIds: string[];
  customWaypoints: RouteCoordinateInput[];
  activeMode: PlanningMode;
  algorithm: PathAlgorithm;
  constraints: RoutePlanningConstraints;

  // Computed Route & Comparison Outputs
  activeRoute: RouteComputeResponse | null;
  comparisonResult: RouteCompareResponse | null;
  routeLoading: boolean;
  compareLoading: boolean;
  routeError: string | null;
  staleRoute: boolean;
  staleReason: string | null;

  // Synchronized Selection & 3D Camera Control
  availableTargets: ScienceTarget[];
  targetsLoaded: boolean;
  selectedWaypointSeq: number | null;
  selectedInstructionStep: number | null;
  cameraFocusRequest: CameraFocusTarget | null;
  cameraPresetRequest: CameraPresetRequest | null;

  // Actions
  fetchAvailableTargets: () => Promise<void>;
  fetchMeshManifest: (datasetId?: string) => Promise<void>;
  setSelectedDemDatasetId: (datasetId: string) => void;
  setActiveLod: (lod: number) => void;
  setActiveOverlayMode: (overlay: TextureOverlayMode) => void;
  setVerticalExaggeration: (exag: number) => void;
  setSurfacePickMode: (mode: SurfacePickMode) => void;
  setPickedSurfacePoint: (pt: PickedSurfacePoint | null) => void;

  setStartPoint: (pt: RouteCoordinateInput | null) => void;
  setDestinationPoint: (pt: RouteCoordinateInput | null) => void;
  setSelectedTargetIds: (ids: string[]) => void;
  toggleTargetId: (id: string) => void;
  addCustomWaypoint: (pt: RouteCoordinateInput) => void;
  removeCustomWaypoint: (idx: number) => void;
  clearCustomWaypoints: () => void;
  setActiveMode: (mode: PlanningMode) => void;
  setAlgorithm: (alg: PathAlgorithm) => void;
  updateConstraints: (patch: Partial<RoutePlanningConstraints>) => void;

  loadRealGaleBoxworkPreset: () => void;
  computeRoute: () => Promise<RouteComputeResponse | null>;
  compareRoutes: () => Promise<RouteCompareResponse | null>;
  selectComparedRoute: (mode: PlanningMode) => void;
  exportActiveGeoJSON: () => Promise<void>;

  selectWaypoint: (seq: number | null, focusCamera?: boolean) => void;
  selectInstructionStep: (stepIndex: number | null, focusCamera?: boolean) => void;
  requestCameraFocus: (lat: number, lon_east: number, elevation_m?: number) => void;
  requestCameraPreset: (preset: CameraPresetType) => void;
}

const DEFAULT_CONSTRAINTS: RoutePlanningConstraints = {
  max_slope_deg: 20.0,
  max_roughness_tri_m: null,
  snap_radius_m: 60.0,
  walking_speed_m_per_s: 0.8,
  walking_speed_provenance: "User-Configured Planning Assumption (Unvalidated)",
  astronaut_total_mass_kg: 130.0,
  max_eva_duration_hours: 4.0,
  safety_reserve_fraction: 0.25,
  enforce_budget: false,
  return_to_start: true,
  optimize_target_order: true,
  simplification_epsilon_m: 6.0,
  max_grid_dim: 220,
};

function _markStaleIfPresent(
  state: RoutingStoreState,
  reason: string
): Partial<RoutingStoreState> {
  if (!state.activeRoute && !state.comparisonResult) {
    return { routeError: null };
  }
  return {
    staleRoute: true,
    staleReason: reason,
    routeError: null,
  };
}

export const useRoutingStore = create<RoutingStoreState>((set, get) => ({
  selectedDemDatasetId: "hirise_dteec_009149_1750",
  meshManifest: null,
  manifestLoading: false,
  manifestError: null,
  activeLod: 1,
  activeOverlayMode: "ortho",
  verticalExaggeration: 1.0,
  surfacePickMode: "inspect",
  pickedSurfacePoint: null,

  // Real Curiosity Sol 4500+ Mount Sharp / Boxwork Crater coordinates inside DTEEC_009149_1750
  startPoint: {
    lat: -4.742,
    lon_east: 137.392,
    label: "Boxwork Station Alpha (Curiosity Sol 4500+)",
  },
  destinationPoint: {
    lat: -4.756,
    lon_east: 137.402,
    label: "Gediz Ridge Sulfate Outcrop",
  },
  selectedTargetIds: [],
  customWaypoints: [],
  activeMode: "balanced",
  algorithm: "astar",
  constraints: { ...DEFAULT_CONSTRAINTS },

  activeRoute: null,
  comparisonResult: null,
  routeLoading: false,
  compareLoading: false,
  routeError: null,
  staleRoute: false,
  staleReason: null,

  availableTargets: [],
  targetsLoaded: false,
  selectedWaypointSeq: null,
  selectedInstructionStep: null,
  cameraFocusRequest: null,
  cameraPresetRequest: null,

  fetchAvailableTargets: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/targets`, { cache: "no-store" });
      if (!res.ok) return;
      const list: ScienceTarget[] = await res.json();
      set({ availableTargets: Array.isArray(list) ? list : [], targetsLoaded: true });
    } catch {
      set({ targetsLoaded: true });
    }
  },

  fetchMeshManifest: async (datasetId) => {
    const ds = datasetId || get().selectedDemDatasetId;
    set({ manifestLoading: true, manifestError: null });
    try {
      const qs = ds ? `?dataset_id=${encodeURIComponent(ds)}` : "";
      const res = await fetch(`${API_BASE_URL}/terrain/mesh/manifest${qs}`, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail || `HTTP ${res.status} loading terrain mesh manifest`);
      }
      const manifest: TerrainMeshManifest = await res.json();
      set({
        meshManifest: manifest,
        selectedDemDatasetId: manifest.dataset_id,
        manifestLoading: false,
        manifestError: null,
      });
    } catch (err: unknown) {
      set({
        manifestLoading: false,
        manifestError: err instanceof Error ? err.message : "Failed to load 3D mesh manifest",
      });
    }
  },

  setSelectedDemDatasetId: (datasetId) => {
    set((s) => ({
      selectedDemDatasetId: datasetId,
      ..._markStaleIfPresent(s, `DEM switched to ${datasetId}`),
    }));
    void get().fetchMeshManifest(datasetId);
  },

  setActiveLod: (lod) => set({ activeLod: Math.max(0, Math.min(2, lod)) }),
  setActiveOverlayMode: (overlay) => set({ activeOverlayMode: overlay }),
  setVerticalExaggeration: (exag) => set({ verticalExaggeration: Math.max(1.0, Math.min(5.0, exag)) }),
  setSurfacePickMode: (mode) => set({ surfacePickMode: mode }),
  setPickedSurfacePoint: (pt) => set({ pickedSurfacePoint: pt }),

  setStartPoint: (pt) =>
    set((s) => ({
      startPoint: pt,
      ..._markStaleIfPresent(s, "Start position changed"),
    })),

  setDestinationPoint: (pt) =>
    set((s) => ({
      destinationPoint: pt,
      ..._markStaleIfPresent(s, "Destination position changed"),
    })),

  setSelectedTargetIds: (ids) =>
    set((s) => ({
      selectedTargetIds: ids,
      ..._markStaleIfPresent(s, "Selected science targets changed"),
    })),

  toggleTargetId: (id) =>
    set((s) => {
      const exists = s.selectedTargetIds.includes(id);
      const next = exists
        ? s.selectedTargetIds.filter((x) => x !== id)
        : [...s.selectedTargetIds, id];
      return {
        selectedTargetIds: next,
        ..._markStaleIfPresent(s, "Selected science targets changed"),
      };
    }),

  addCustomWaypoint: (pt) =>
    set((s) => ({
      customWaypoints: [...s.customWaypoints, pt],
      ..._markStaleIfPresent(s, "Waypoints changed"),
    })),

  removeCustomWaypoint: (idx) =>
    set((s) => ({
      customWaypoints: s.customWaypoints.filter((_, i) => i !== idx),
      ..._markStaleIfPresent(s, "Waypoints changed"),
    })),

  clearCustomWaypoints: () =>
    set((s) => ({
      customWaypoints: [],
      ..._markStaleIfPresent(s, "Waypoints cleared"),
    })),

  setActiveMode: (mode) => {
    const compared = get().comparisonResult?.comparison.find((e) => e.mode === mode);
    if (compared?.feasible && compared.route && !get().staleRoute) {
      set({
        activeMode: mode,
        activeRoute: compared.route,
        selectedWaypointSeq: null,
        selectedInstructionStep: null,
      });
    } else {
      set((s) => ({
        activeMode: mode,
        ..._markStaleIfPresent(s, `Routing mode changed to ${mode}`),
      }));
    }
  },

  setAlgorithm: (alg) =>
    set((s) => ({
      algorithm: alg,
      ..._markStaleIfPresent(s, `Path algorithm switched to ${alg}`),
    })),

  updateConstraints: (patch) =>
    set((s) => ({
      constraints: { ...s.constraints, ...patch },
      ..._markStaleIfPresent(s, "Route constraints updated"),
    })),

  loadRealGaleBoxworkPreset: () =>
    set((s) => ({
      selectedDemDatasetId: "hirise_dteec_009149_1750",
      startPoint: {
        lat: -4.742,
        lon_east: 137.392,
        label: "Boxwork Station Alpha (Sol 4500+)",
      },
      destinationPoint: {
        lat: -4.756,
        lon_east: 137.402,
        label: "Gediz Ridge Sulfate Outcrop",
      },
      customWaypoints: [
        {
          lat: -4.7485,
          lon_east: 137.3972,
          label: "Boxwork Fracture Wall Stop",
        },
      ],
      ..._markStaleIfPresent(s, "Loaded Gale Crater Boxwork preset"),
    })),

  computeRoute: async () => {
    const s = get();
    if (!s.startPoint || !s.destinationPoint) {
      set({ routeError: "Select both a Start and Destination point before computing a route." });
      return null;
    }
    set({ routeLoading: true, routeError: null });
    try {
      const res = await fetch(`${API_BASE_URL}/routing/compute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: s.selectedDemDatasetId || null,
          start: s.startPoint,
          destination: s.destinationPoint,
          target_ids: s.selectedTargetIds,
          waypoints: s.customWaypoints,
          mode: s.activeMode,
          algorithm: s.algorithm,
          constraints: s.constraints,
        }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        const msg =
          typeof errBody?.detail === "string"
            ? errBody.detail
            : errBody?.detail?.reason || JSON.stringify(errBody?.detail || `HTTP ${res.status}`);
        throw new Error(msg);
      }
      const route: RouteComputeResponse = await res.json();
      set({
        activeRoute: route,
        routeLoading: false,
        routeError: null,
        staleRoute: false,
        staleReason: null,
        selectedWaypointSeq: 0,
        selectedInstructionStep: route.instructions.length > 0 ? route.instructions[0].step_index : null,
      });
      return route;
    } catch (err: unknown) {
      set({
        routeLoading: false,
        routeError: err instanceof Error ? err.message : "Route computation failed",
      });
      return null;
    }
  },

  compareRoutes: async () => {
    const s = get();
    if (!s.startPoint || !s.destinationPoint) {
      set({ routeError: "Select both a Start and Destination point before comparing routes." });
      return null;
    }
    set({ compareLoading: true, routeError: null });
    try {
      const res = await fetch(`${API_BASE_URL}/routing/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: s.selectedDemDatasetId || null,
          start: s.startPoint,
          destination: s.destinationPoint,
          target_ids: s.selectedTargetIds,
          waypoints: s.customWaypoints,
          modes: ["conservative", "balanced", "science_priority"],
          constraints: s.constraints,
        }),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `HTTP ${res.status}`);
      }
      const cmp: RouteCompareResponse = await res.json();
      const preferred =
        cmp.comparison.find((e) => e.mode === s.activeMode && e.feasible && e.route)?.route ||
        cmp.comparison.find((e) => e.feasible && e.route)?.route ||
        null;
      set({
        comparisonResult: cmp,
        activeRoute: preferred || s.activeRoute,
        activeMode: preferred ? preferred.mode : s.activeMode,
        compareLoading: false,
        staleRoute: preferred ? false : s.staleRoute,
        staleReason: preferred ? null : s.staleReason,
      });
      return cmp;
    } catch (err: unknown) {
      set({
        compareLoading: false,
        routeError: err instanceof Error ? err.message : "Route comparison failed",
      });
      return null;
    }
  },

  selectComparedRoute: (mode) => {
    const cmp = get().comparisonResult;
    const match = cmp?.comparison.find((e) => e.mode === mode);
    if (match?.feasible && match.route) {
      set({
        activeMode: mode,
        activeRoute: match.route,
        staleRoute: false,
        staleReason: null,
        selectedWaypointSeq: 0,
        selectedInstructionStep:
          match.route.instructions.length > 0 ? match.route.instructions[0].step_index : null,
      });
    }
  },

  exportActiveGeoJSON: async () => {
    const rt = get().activeRoute;
    if (!rt) return;
    const res = await fetch(`${API_BASE_URL}/routing/${encodeURIComponent(rt.route_id)}/geojson`);
    if (!res.ok) return;
    const gj = await res.json();
    const blob = new Blob([JSON.stringify(gj, null, 2)], { type: "application/geo+json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${rt.route_id}.geojson`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  selectWaypoint: (seq, focusCamera = true) => {
    const rt = get().activeRoute;
    set({ selectedWaypointSeq: seq });
    if (seq !== null && rt) {
      const v = rt.vertices.find((item) => item.seq === seq);
      if (v) {
        const inst = rt.instructions.find(
          (ins) => Math.abs(ins.cumulative_distance_m - v.cumulative_distance_m) < 0.5
        );
        if (inst) {
          set({ selectedInstructionStep: inst.step_index });
        }
        if (focusCamera) {
          get().requestCameraFocus(v.lat, v.lon_east, v.elevation_m);
        }
      }
    }
  },

  selectInstructionStep: (stepIndex, focusCamera = true) => {
    const rt = get().activeRoute;
    set({ selectedInstructionStep: stepIndex });
    if (stepIndex !== null && rt) {
      const inst = rt.instructions.find((ins) => ins.step_index === stepIndex);
      if (inst) {
        const matchV = rt.vertices.find(
          (v) =>
            Math.abs(v.lat - inst.to_lat) < 1e-5 &&
            Math.abs(v.lon_east - inst.to_lon_east) < 1e-5
        );
        if (matchV) {
          set({ selectedWaypointSeq: matchV.seq });
        }
        if (focusCamera) {
          get().requestCameraFocus(inst.to_lat, inst.to_lon_east, inst.elevation_end_m);
        }
      }
    }
  },

  requestCameraFocus: (lat, lon_east, elevation_m) =>
    set({
      cameraFocusRequest: {
        lat,
        lon_east,
        elevation_m,
        nonce: Date.now() + Math.random(),
      },
    }),

  requestCameraPreset: (preset) =>
    set({
      cameraPresetRequest: {
        preset,
        nonce: Date.now() + Math.random(),
      },
    }),
}));
