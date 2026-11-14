import { create } from "zustand";

export interface MapLayer {
  id: string;
  name: string;
  category: "optical" | "topography" | "geology" | "rover";
  visible: boolean;
  opacity: number;
}

interface LayerStoreState {
  layers: MapLayer[];
  toggleLayer: (id: string) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
}

export const useLayerStore = create<LayerStoreState>((set) => ({
  layers: [
    { id: "ctx_mosaic", name: "CTX Controlled Mosaic", category: "optical", visible: true, opacity: 1.0 },
    { id: "hirise_rdr", name: "HiRISE RDR Orthomosaic", category: "optical", visible: true, opacity: 1.0 },
    { id: "mola_dem", name: "MOLA Elevation Hillshade", category: "topography", visible: true, opacity: 0.7 },
    { id: "msl_traverse", name: "Curiosity Rover Traverse", category: "rover", visible: true, opacity: 1.0 },
    { id: "slope_layer", name: "Computed Slope Gradient", category: "topography", visible: false, opacity: 0.8 },
  ],
  toggleLayer: (id) =>
    set((state) => ({
      layers: state.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)),
    })),
  setLayerOpacity: (id, opacity) =>
    set((state) => ({
      layers: state.layers.map((l) => (l.id === id ? { ...l, opacity } : l)),
    })),
}));
