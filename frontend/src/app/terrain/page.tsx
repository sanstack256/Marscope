"use client";

import { PageHeader } from "../../components/PageHeader";
import { EmptyState } from "../../components/EmptyState";
import { StatusCard } from "../../components/StatusCard";
import { Mountain, TrendingUp, AlertTriangle, ShieldCheck, Activity } from "lucide-react";

export default function TerrainIntelligencePage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <PageHeader
        title="Terrain & Geomorphological Intelligence"
        badge="DEM Processing"
        description="High-resolution digital elevation modeling. Computes slope gradient, aspect orientation, and Terrain Ruggedness Index (TRI) to identify micro-traversability corridors."
      />

      {/* Terrain Hazard Overview Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatusCard
          label="Critical Slope Limit"
          value="25.0"
          unit="deg"
          subValue="Hard traversability boundary"
          icon={AlertTriangle}
          badge="Safety Invariant"
        />
        <StatusCard
          label="Angle of Granular Repose"
          value="30.0"
          unit="deg"
          subValue="Basaltic sand slip threshold"
          icon={Mountain}
        />
        <StatusCard
          label="DEM Resolution Target"
          value="1.0"
          unit="m/pixel"
          subValue="HiRISE Stereo DTM Standard"
          icon={TrendingUp}
        />
        <StatusCard
          label="Areoid Datum"
          value="MOLA GMM-2B"
          subValue="Gravitational Equipotential"
          icon={ShieldCheck}
        />
      </div>

      {/* Main Analysis Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <h2 className="text-sm font-bold text-slate-200 mb-1">Slope Gradient & Roughness Map</h2>
          <p className="text-xs text-slate-400 mb-4">
            Directional gradient operator evaluated across 3x3 local neighbor kernels.
          </p>
          <EmptyState
            title="Scientific Terrain Rasters Not Yet Ingested"
            message="Rasterio/GDAL slope derivation pipeline will process HiRISE DTM into multi-band slope, aspect, and TRI GeoTIFFs in subsequent features."
            icon={Mountain}
          />
        </div>

        <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-6">
          <h2 className="text-sm font-bold text-slate-200 mb-1">Cross-Sectional Elevation Profile</h2>
          <p className="text-xs text-slate-400 mb-4">
            Interactive elevation profile graph showing ascent, descent, and slope transitions across boxwork ridges.
          </p>
          <EmptyState
            title="Profile Transect Tool Ready"
            message="Draw an arbitrary transect line on the 3D surface map to generate real-time elevation cross-sections and gravitational energy estimates."
            icon={Activity}
          />
        </div>
      </div>
    </div>
  );
}
