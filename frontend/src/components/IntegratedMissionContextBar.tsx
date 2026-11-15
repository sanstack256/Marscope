"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Compass, Flag, Layers, Microscope, Route, Users } from "lucide-react";
import { API_BASE_URL } from "../lib/constants";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { useInvestigationStore } from "../stores/useInvestigationStore";
import { useRoutingStore } from "../stores/useRoutingStore";

export function IntegratedMissionContextBar() {
  const { authenticated, activeMission, crew, observations, landingSiteBundle, streamState } =
    useAuthMissionStore();
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const {
    questions,
    activeQuestionId,
    setActiveQuestionId,
    fetchQuestions,
    campaigns,
    activeCampaign,
    loadCampaign,
    fetchCampaigns,
  } = useInvestigationStore();

  const [showScienceStrip, setShowScienceStrip] = useState(false);

  useEffect(() => {
    void fetchQuestions();
    void fetchCampaigns();
  }, [fetchQuestions, fetchCampaigns]);

  const checkReadinessQuick = async () => {
    await fetch(`${API_BASE_URL}/health/readiness`, { cache: "no-store" }).catch(() => null);
  };

  return (
    <div className="min-h-[44px] bg-[var(--bg-void)]/90 border-b border-[var(--border-subtle)] px-4 lg:px-5 py-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px]">
      <div className="flex flex-wrap items-center gap-3">
        {authenticated && activeMission ? (
          <>
            <Link
              href="/crew"
              className="inline-flex items-center gap-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] font-mono"
            >
              <Users className="w-3.5 h-3.5 text-[var(--accent-telemetry)]" />
              <span>CREW: {crew.length}</span>
            </Link>
            <Link
              href="/observations"
              className="inline-flex items-center gap-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] font-mono"
            >
              <Microscope className="w-3.5 h-3.5 text-[var(--accent-mars)]" />
              <span>OBS: {observations.length}</span>
            </Link>
            <Link
              href="/landing-site"
              className="inline-flex items-center gap-1.5 font-mono"
            >
              <Flag
                className={`w-3.5 h-3.5 ${
                  landingSiteBundle?.landing_site_status === "REGISTERED"
                    ? "text-[#1F9D68]"
                    : "text-[#D98A1F]"
                }`}
              />
              <span
                className={
                  landingSiteBundle?.landing_site_status === "REGISTERED"
                    ? "text-[#4ade80]"
                    : "text-[#f5b041]"
                }
              >
                {landingSiteBundle?.landing_site
                  ? `${landingSiteBundle.landing_site.name} (${landingSiteBundle.landing_site.dem_coverage_state})`
                  : "LANDING_SITE_UNCONFIGURED"}
              </span>
            </Link>
            <Link
              href="/active-navigation"
              className="inline-flex items-center gap-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] font-mono"
            >
              <Route className="w-3.5 h-3.5 text-[#4ade80]" />
              <span>
                {activeRoute ? `ROUTE: ${(activeRoute.total_surface_distance_m / 1000).toFixed(2)} km` : "ROUTE: NONE"}
              </span>
            </Link>
            <span className="font-mono text-[10px] text-[var(--text-muted)]">
              STREAM: {streamState.toUpperCase()}
            </span>
          </>
        ) : (
          <span className="inline-flex items-center gap-1.5 font-mono text-[var(--text-muted)]">
            <Compass className="w-3.5 h-3.5 text-[var(--accent-mars)]" />
            <span>
              {authenticated
                ? "Select or create a mission to synchronize crew, landing site & observations"
                : "Sign in to access crew mission workspace — orbital science tools available below"}
            </span>
          </span>
        )}
      </div>

      {/* Expandable Science Question & EVA Session Switcher */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setShowScienceStrip((v) => !v);
            void checkReadinessQuick();
          }}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded-[4px] bg-[var(--bg-surface)] border border-[var(--border-subtle)] font-mono text-[10px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <Layers className="w-3 h-3 text-[var(--accent-telemetry)]" />
          <span>SCIENCE & EVA CONTEXT</span>
        </button>

        {showScienceStrip && (
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Active Science Question"
              value={activeQuestionId || ""}
              onChange={(e) => setActiveQuestionId(e.target.value || "gale_boxwork_origin")}
              className="bg-[var(--bg-surface)] border border-[var(--border-strong)] rounded-[4px] px-2 py-0.5 text-[11px] font-mono text-[var(--text-primary)] max-w-[190px]"
            >
              <option value="">Question: None</option>
              {questions.map((q) => (
                <option key={q.question_id} value={q.question_id}>
                  {q.title}
                </option>
              ))}
            </select>
            <select
              aria-label="Active Science Campaign"
              value={activeCampaign?.campaign_id || ""}
              onChange={(e) => {
                if (e.target.value) void loadCampaign(e.target.value);
              }}
              className="bg-[var(--bg-surface)] border border-[var(--border-strong)] rounded-[4px] px-2 py-0.5 text-[11px] font-mono text-[var(--text-primary)] max-w-[180px]"
            >
              <option value="">Campaign: None</option>
              {campaigns.map((c) => (
                <option key={c.campaign_id} value={c.campaign_id}>
                  {c.campaign_name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
    </div>
  );
}
