import { create } from "zustand";
import { API_BASE_URL } from "../lib/constants";
import { LayerCatalogResponse, MapLayer } from "../types";

export interface LayerControlState {
  visible: boolean;
  opacity: number;
  order: number;
  renderedActive: boolean;
  tileErrorCount: number;
  lastError?: string | null;
}

interface LayerStoreState {
  availableLayers: MapLayer[];
  unavailableLayers: MapLayer[];
  layerStates: Record<string, LayerControlState>;
  layerOrder: string[];
  loading: boolean;
  error: string | null;
  fetchLayers: () => Promise<void>;
  toggleLayer: (id: string) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
  moveLayerOrder: (id: string, direction: "up" | "down") => void;
  markLayerRendered: (id: string, active: boolean) => void;
  recordTileError: (id: string, message?: string) => void;
  clearTileErrors: (id: string) => void;
}

export const useLayerStore = create<LayerStoreState>((set, get) => ({
  availableLayers: [],
  unavailableLayers: [],
  layerStates: {},
  layerOrder: [],
  loading: false,
  error: null,

  fetchLayers: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE_URL}/layers`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} loading layers catalog`);
      }
      const data: LayerCatalogResponse = await res.json();
      const prevStates = get().layerStates;
      const prevOrder = get().layerOrder;

      const nextStates: Record<string, LayerControlState> = {};
      const discoveredIds = data.available_layers.map((l) => l.layer_id);

      // Preserve existing user order for known layers and append newly available ones
      const nextOrder = [
        ...prevOrder.filter((id) => discoveredIds.includes(id)),
        ...discoveredIds.filter((id) => !prevOrder.includes(id)),
      ];

      data.available_layers.forEach((layer, idx) => {
        const existing = prevStates[layer.layer_id];
        nextStates[layer.layer_id] = existing
          ? { ...existing, order: nextOrder.indexOf(layer.layer_id) }
          : {
              visible: layer.default_visible,
              opacity: layer.default_opacity,
              order: idx,
              renderedActive: false,
              tileErrorCount: 0,
              lastError: null,
            };
      });

      set({
        availableLayers: data.available_layers,
        unavailableLayers: data.unavailable_layers,
        layerStates: nextStates,
        layerOrder: nextOrder,
        loading: false,
      });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : "Failed to load layer catalog from backend",
      });
    }
  },

  toggleLayer: (id) =>
    set((state) => {
      const curr = state.layerStates[id];
      if (!curr) return state;
      const nextVisible = !curr.visible;
      return {
        layerStates: {
          ...state.layerStates,
          [id]: {
            ...curr,
            visible: nextVisible,
            renderedActive: nextVisible ? curr.renderedActive : false,
          },
        },
      };
    }),

  setLayerOpacity: (id, opacity) =>
    set((state) => {
      const curr = state.layerStates[id];
      if (!curr) return state;
      return {
        layerStates: {
          ...state.layerStates,
          [id]: { ...curr, opacity },
        },
      };
    }),

  moveLayerOrder: (id, direction) =>
    set((state) => {
      const idx = state.layerOrder.indexOf(id);
      if (idx === -1) return state;
      const swapIdx = direction === "up" ? idx - 1 : idx + 1;
      if (swapIdx < 0 || swapIdx >= state.layerOrder.length) return state;

      const updated = [...state.layerOrder];
      [updated[idx], updated[swapIdx]] = [updated[swapIdx], updated[idx]];

      const nextStates = { ...state.layerStates };
      updated.forEach((lid, orderIdx) => {
        if (nextStates[lid]) {
          nextStates[lid] = { ...nextStates[lid], order: orderIdx };
        }
      });

      return { layerOrder: updated, layerStates: nextStates };
    }),

  markLayerRendered: (id, active) =>
    set((state) => {
      const curr = state.layerStates[id];
      if (!curr || curr.renderedActive === active) return state;
      return {
        layerStates: {
          ...state.layerStates,
          [id]: { ...curr, renderedActive: active },
        },
      };
    }),

  recordTileError: (id, message) =>
    set((state) => {
      const curr = state.layerStates[id];
      if (!curr) return state;
      return {
        layerStates: {
          ...state.layerStates,
          [id]: {
            ...curr,
            tileErrorCount: curr.tileErrorCount + 1,
            lastError: message || "Tile request failed or unavailable",
          },
        },
      };
    }),

  clearTileErrors: (id) =>
    set((state) => {
      const curr = state.layerStates[id];
      if (!curr || (curr.tileErrorCount === 0 && curr.lastError === null)) return state;
      return {
        layerStates: {
          ...state.layerStates,
          [id]: { ...curr, tileErrorCount: 0, lastError: null },
        },
      };
    }),
}));
