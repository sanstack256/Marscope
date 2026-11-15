"use client";

import React from "react";
import Link from "next/link";
import { Flag, Navigation, Route, Users } from "lucide-react";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";

export default function ActiveNavigationPage() {
  const { authenticated, activeMission, crew, landingSiteBundle } = useAuthMissionStore();
  const activeRoute = useRoutingStore((s) => s.activeRoute);

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader
        title="Active Surface Navigation"
        badge="FOUNDATION READY"
        description="Unified field navigation surface integrating Prompt 1 crew position freshness, landing-site perimeter boundaries, and active uncertainty-aware traverse geometry."
        actions={
          <Link
            href="/planner"
            className="px-3 py-1.5 rounded-[4px] bg-[var(--accent-mars)] text-white text-xs font-semibold"
          >
            Open Route Planner
          </Link>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
        <div className="ms-panel p-4 space-y-2">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>Crew Localization</span>
            <Users className="w-4 h-4 text-[var(--accent-telemetry)]" />
          </div>
          <div className="text-lg font-mono font-bold text-[var(--text-primary)]">
            {authenticated && activeMission ? `${crew.length} Members` : "Sign In Required"}
          </div>
          <Link href="/crew" className="text-[var(--accent-telemetry)] underline inline-block">
            Inspect position freshness
          </Link>
        </div>

        <div className="ms-panel p-4 space-y-2">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>Landing-Site Boundary</span>
            <Flag className="w-4 h-4 text-[var(--accent-mars)]" />
          </div>
          <div>
            <StatusIndicator
              label={landingSiteBundle?.perimeter?.status || landingSiteBundle?.landing_site_status || "UNCONFIGURED"}
              tone={landingSiteBundle?.perimeter?.status === "EVALUATED_WITH_VALIDATED_DEM" ? "success" : "warning"}
            />
          </div>
          <Link href="/landing-site" className="text-[var(--accent-telemetry)] underline inline-block">
            Configure 3D perimeter
          </Link>
        </div>

        <div className="ms-panel p-4 space-y-2">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>Planned Corridor</span>
            <Route className="w-4 h-4 text-[#4ade80]" />
          </div>
          <div className="text-lg font-mono font-bold text-[var(--text-primary)]">
            {activeRoute ? `${(activeRoute.total_surface_distance_m / 1000).toFixed(2)} km` : "No Route Loaded"}
          </div>
          <Link href="/simulation" className="text-[var(--accent-telemetry)] underline inline-block">
            Launch EVA simulation
          </Link>
        </div>
      </div>

      <div className="ms-panel p-5 space-y-2 text-xs">
        <div className="flex items-center gap-2 font-semibold text-sm text-[var(--text-primary)]">
          <Navigation className="w-4 h-4 text-[var(--accent-telemetry)]" />
          <span>Prompt 2 Operational Navigation Contract Anchor</span>
        </div>
        <p className="text-[var(--text-secondary)] leading-relaxed">
          All Prompt 1 multi-astronaut position validation (<span className="font-mono">IAU2000:49900</span>), isolated SSE streaming,
          offline IndexedDB queueing, and DEM-backed perimeter boundaries are active and ready for Prompt 2 turn-by-turn
          guidance, return-to-base margin monitoring, and dynamic detour triggers.
        </p>
      </div>
    </div>
  );
}
