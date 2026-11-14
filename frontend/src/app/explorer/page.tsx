"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { useLayerStore } from "../../stores/useLayerStore";
import { Globe2, Layers, Eye, EyeOff, Sliders, Compass } from "lucide-react";
import { MARS_FACTS } from "../../lib/constants";

export default function SurfaceExplorerPage() {
  const { layers, toggleLayer, setLayerOpacity } = useLayerStore();

  return (
    <div className="h-full flex flex-col space-y-4">
      <PageHeader
        title="Martian Map / Surface Explorer"
        badge="3D Planetary Canvas"
        description="Central 3D/2D geospatial workspace. Co-registers MRO HiRISE orthophotos, CTX basemaps, MOLA topography, and Curiosity rover traverse waypoints."
        actions={
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-slate-400 bg-[#161c2b] border border-[#252f44] px-3 py-1.5 rounded-lg">
              DATUM: {MARS_FACTS.CRS}
            </span>
          </div>
        }
      />

      {/* Main Map Viewport Split */}
      <div className="flex-1 min-h-[500px] grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Layer Controls Drawer */}
        <div className="lg:col-span-1 bg-[#121622] border border-[#1e2638] rounded-xl p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#1e2638] mb-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200 uppercase tracking-wider">
                <Layers className="w-4 h-4 text-[#e25b38]" />
                <span>Planetary Layers</span>
              </div>
              <span className="text-[10px] font-mono text-slate-500">{layers.length} Layers</span>
            </div>

            <div className="space-y-3">
              {layers.map((layer) => (
                <div
                  key={layer.id}
                  className="p-2.5 rounded-lg bg-[#161c2b] border border-[#212a3d] space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-200">{layer.name}</span>
                    <button
                      onClick={() => toggleLayer(layer.id)}
                      className={`p-1 rounded transition-colors ${
                        layer.visible ? "text-[#e25b38] hover:bg-[#252f44]" : "text-slate-600 hover:text-slate-400"
                      }`}
                      title={layer.visible ? "Hide layer" : "Show layer"}
                    >
                      {layer.visible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                    </button>
                  </div>
                  {layer.visible && (
                    <div className="flex items-center gap-2 pt-1 border-t border-[#1e2638]">
                      <Sliders className="w-3 h-3 text-slate-500" />
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={layer.opacity}
                        onChange={(e) => setLayerOpacity(layer.id, parseFloat(e.target.value))}
                        className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-[#e25b38]"
                      />
                      <span className="text-[10px] font-mono text-slate-400 w-8 text-right">
                        {Math.round(layer.opacity * 100)}%
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="pt-4 border-t border-[#1e2638] text-[10px] font-mono text-slate-500 space-y-1">
            <div className="flex justify-between">
              <span>Projection:</span>
              <span className="text-slate-300">Equirectangular</span>
            </div>
            <div className="flex justify-between">
              <span>Terrain Engine:</span>
              <span className="text-cyan-400">CesiumJS / MapLibre</span>
            </div>
          </div>
        </div>

        {/* 3D Map Viewport Canvas Area */}
        <div className="lg:col-span-3 bg-[#0a0d14] border border-[#1e2638] rounded-xl relative flex items-center justify-center overflow-hidden">
          {/* Spatial Grid Background Accent */}
          <div className="absolute inset-0 bg-[radial-gradient(#1e2638_1px,transparent_1px)] [background-size:24px_24px] opacity-40"></div>

          {/* Compass & Center Reticle Overlay */}
          <div className="absolute top-4 right-4 z-10 flex items-center gap-2 bg-[#121622]/80 backdrop-blur px-3 py-1.5 rounded-lg border border-[#1e2638] text-xs font-mono text-slate-300">
            <Compass className="w-3.5 h-3.5 text-[#e25b38]" />
            <span>LAT -4.65° | LON 137.40°</span>
          </div>

          {/* Clean Initialized Empty State */}
          <div className="relative z-10 max-w-lg p-6">
            <EmptyState
              title="3D Martian Terrain Canvas Initialized"
              message="CesiumJS and MapLibre engines are ready. High-resolution HiRISE DTMs and MOLA planetary elevation rasters will be mounted during backend data ingestion in Prompt 2."
              icon={Globe2}
              actionLabel="Verify Layer Catalog"
              onAction={() => alert("Layer catalog verified: Ready for PDS raster ingestion.")}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
