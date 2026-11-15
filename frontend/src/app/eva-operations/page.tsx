"use client";

import React from "react";
import Link from "next/link";
import { Activity, CheckCircle2, Gauge, Users } from "lucide-react";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useEvaOperationsStore } from "../../stores/useEvaOperationsStore";
import { useInvestigationStore } from "../../stores/useInvestigationStore";
import { PageHeader } from "../../components/PageHeader";

export default function EvaOperationsHubPage() {
  const { activeMission, crew } = useAuthMissionStore();
  const { evaEnvelope } = useEvaOperationsStore();
  const { campaigns } = useInvestigationStore();

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader
        title="EVA Operations Hub"
        badge={activeMission ? activeMission.name : "MULTI-SYSTEM"}
        description="Unified access to human Marswalk physiological budgets, crew readiness dossiers, and real-time EVA simulations."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
        <Link href="/mission-readiness" className="ms-panel p-5 hover:border-[var(--accent-mars)] transition-colors space-y-2">
          <CheckCircle2 className="w-5 h-5 text-[var(--accent-mars)]" />
          <div className="font-semibold text-sm text-[var(--text-primary)]">Mission Readiness & Dossier</div>
          <p className="text-[var(--text-secondary)]">
            Evaluate EVA feasibility, return reserves, missing parameters, and operator approvals ({campaigns.length} campaigns{evaEnvelope ? ` · active EVA ${evaEnvelope.mission_name}` : ""}).
          </p>
        </Link>

        <Link href="/simulation" className="ms-panel p-5 hover:border-[var(--accent-telemetry)] transition-colors space-y-2">
          <Gauge className="w-5 h-5 text-[var(--accent-telemetry)]" />
          <div className="font-semibold text-sm text-[var(--text-primary)]">EVA Route Simulation</div>
          <p className="text-[var(--text-secondary)]">
            Interactive 3D timeline scrubber synchronized with terrain derivatives and resource models.
          </p>
        </Link>

        <Link href="/crew" className="ms-panel p-5 hover:border-[#1F9D68] transition-colors space-y-2">
          <Users className="w-5 h-5 text-[#4ade80]" />
          <div className="font-semibold text-sm text-[var(--text-primary)]">Crew Status & Mass Profiles</div>
          <p className="text-[var(--text-secondary)]">
            {activeMission ? `${crew.length} active crew members in ${activeMission.name}.` : "Sign in to manage crew positions and profiles."}
          </p>
        </Link>
      </div>

      <div className="ms-panel p-4 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-[var(--text-secondary)]">
          <Activity className="w-4 h-4 text-[var(--accent-telemetry)]" />
          <span>Configure astronaut body/suit/equipment mass (USER_ASSUMED) cleanly on your Astronaut Profile.</span>
        </div>
        <Link href="/profile" className="text-[var(--accent-telemetry)] font-mono underline">
          Edit Profile Mass
        </Link>
      </div>
    </div>
  );
}
