import { create } from "zustand";
import { API_BASE_URL } from "@/lib/constants";
import type {
  TrackingReplanPreviewResponse,
  TrackingStatusResponse,
} from "@/types";
import { useRoutingStore } from "@/stores/useRoutingStore";

interface TrackingStoreState {
  trackingStatus: TrackingStatusResponse | null;
  sseConnected: boolean;
  replanPreview: TrackingReplanPreviewResponse | null;
  replanLoading: boolean;
  replanError: string | null;

  fetchTrackingStatus: (activeRouteId?: string | null) => Promise<void>;
  connectTrackingStream: (activeRouteId?: string | null) => () => void;
  requestReplanPreview: (activeRouteId: string) => Promise<TrackingReplanPreviewResponse | null>;
  adoptReplanPreview: () => void;
  dismissReplanPreview: () => void;
  clearLiveSession: () => Promise<void>;
}

let _refCount = 0;
let _eventSource: EventSource | null = null;
let _pollInterval: ReturnType<typeof setInterval> | null = null;
let _boundRouteId: string | null = null;

export const useTrackingStore = create<TrackingStoreState>((set, get) => ({
  trackingStatus: null,
  sseConnected: false,
  replanPreview: null,
  replanLoading: false,
  replanError: null,

  fetchTrackingStatus: async (activeRouteId) => {
    const rid = activeRouteId ?? useRoutingStore.getState().activeRoute?.route_id ?? null;
    try {
      const qs = rid ? `?active_route_id=${encodeURIComponent(rid)}` : "";
      const res = await fetch(`${API_BASE_URL}/tracking/status${qs}`, { cache: "no-store" });
      if (!res.ok) return;
      const data: TrackingStatusResponse = await res.json();
      set({ trackingStatus: data });
    } catch {
      // Preserve last known state cleanly when offline
    }
  },

  connectTrackingStream: (activeRouteId) => {
    const rid = activeRouteId ?? useRoutingStore.getState().activeRoute?.route_id ?? null;
    _refCount += 1;

    const reopenStream = () => {
      if (_eventSource) {
        _eventSource.close();
        _eventSource = null;
      }
      _boundRouteId = rid;
      if (typeof window === "undefined" || typeof EventSource === "undefined") return;
      const qs = rid ? `?active_route_id=${encodeURIComponent(rid)}` : "";
      const es = new EventSource(`${API_BASE_URL}/tracking/stream${qs}`);
      es.onopen = () => set({ sseConnected: true });
      const handlePayload = (ev: MessageEvent) => {
        try {
          const parsed: TrackingStatusResponse = JSON.parse(ev.data);
          set({ trackingStatus: parsed, sseConnected: true });
        } catch {
          // Ignore malformed keepalive chunk
        }
      };
      es.addEventListener("tracking_status", handlePayload as EventListener);
      es.addEventListener("tracking_heartbeat", handlePayload as EventListener);
      es.onerror = () => {
        set({ sseConnected: false });
      };
      _eventSource = es;
    };

    if (_refCount === 1 || rid !== _boundRouteId || !_eventSource) {
      void get().fetchTrackingStatus(rid);
      reopenStream();
    }

    if (!_pollInterval) {
      _pollInterval = setInterval(() => {
        if (!get().sseConnected) {
          void get().fetchTrackingStatus(useRoutingStore.getState().activeRoute?.route_id ?? null);
        }
      }, 6000);
    }

    return () => {
      _refCount = Math.max(0, _refCount - 1);
      if (_refCount === 0) {
        if (_eventSource) {
          _eventSource.close();
          _eventSource = null;
        }
        if (_pollInterval) {
          clearInterval(_pollInterval);
          _pollInterval = null;
        }
        set({ sseConnected: false });
      }
    };
  },

  requestReplanPreview: async (activeRouteId) => {
    set({ replanLoading: true, replanError: null });
    try {
      const routingState = useRoutingStore.getState();
      const res = await fetch(`${API_BASE_URL}/tracking/replan-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          active_route_id: activeRouteId,
          dataset_id: routingState.selectedDemDatasetId || null,
          mode: routingState.activeMode,
          algorithm: routingState.algorithm,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const preview: TrackingReplanPreviewResponse = await res.json();
      set({ replanPreview: preview, replanLoading: false });
      return preview;
    } catch (err: unknown) {
      set({
        replanLoading: false,
        replanError: err instanceof Error ? err.message : "Failed to compute live replan preview",
      });
      return null;
    }
  },

  adoptReplanPreview: () => {
    const preview = get().replanPreview;
    if (!preview) return;
    useRoutingStore.setState({
      activeRoute: preview.proposed_route,
      staleRoute: false,
      staleReason: null,
      routeError: null,
      selectedWaypointSeq: 0,
      selectedInstructionStep:
        preview.proposed_route.instructions.length > 0
          ? preview.proposed_route.instructions[0].step_index
          : null,
    });
    set({ replanPreview: null, replanError: null });
  },

  dismissReplanPreview: () => set({ replanPreview: null, replanError: null }),

  clearLiveSession: async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/tracking/session`, { method: "DELETE" });
      if (res.ok) {
        const data: TrackingStatusResponse = await res.json();
        set({ trackingStatus: data, replanPreview: null });
      }
    } catch {
      // Ignore network errors cleanly
    }
  },
}));
