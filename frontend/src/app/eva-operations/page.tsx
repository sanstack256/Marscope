"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, CheckCircle2, Clock, Gauge, Layers, Plus, Trash2, Users } from "lucide-react";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useEvaOperationsStore } from "../../stores/useEvaOperationsStore";
import { useInvestigationStore } from "../../stores/useInvestigationStore";
import { useRoutingStore } from "../../stores/useRoutingStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EvaExplicitResourceSpec } from "../../types";

export default function EvaOperationsWorkstationPage() {
  const { authenticated, astronaut, activeMission, crew, missionEvents } = useAuthMissionStore();
  const {
    evaEnvelope,
    telemetryStatus,
    loadingEva,
    error,
    evaluateMission,
    fetchTelemetryStatus,
  } = useEvaOperationsStore();
  const { campaigns } = useInvestigationStore();
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);

  const [locomotionCategory, setLocomotionCategory] = useState<
    | "USER_CONFIGURED_CONSTANT_SPEED"
    | "TERRESTRIAL_HIKING_APPROXIMATION"
    | "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL"
  >("USER_CONFIGURED_CONSTANT_SPEED");
  const [walkingSpeedMps, setWalkingSpeedMps] = useState("");
  const [durationLimitMin, setDurationLimitMin] = useState("");
  const [overheadMin, setOverheadMin] = useState("0");
  const [returnReservePct, setReturnReservePct] = useState("");
  const [suitPlusBodyMassKg, setSuitPlusBodyMassKg] = useState(() =>
    astronaut?.body_mass_kg != null && astronaut?.suit_mass_kg != null
      ? String(astronaut.body_mass_kg + astronaut.suit_mass_kg)
      : ""
  );
  const [payloadMassKg, setPayloadMassKg] = useState(() =>
    astronaut?.equipment_mass_kg != null ? String(astronaut.equipment_mass_kg) : ""
  );
  const [unknownPolicy, setUnknownPolicy] = useState<
    "EXCLUDE_UNKNOWN" | "ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE" | "REQUIRE_ADDITIONAL_OBSERVATION"
  >("EXCLUDE_UNKNOWN");
  const [formError, setFormError] = useState<string | null>(null);

  // Explicit resource spec rows (empty by default -> unconfigured resources show NOT CONFIGURED)
  const [resources, setResources] = useState<EvaExplicitResourceSpec[]>([]);
  const [resCategory, setResCategory] = useState("OXYGEN");
  const [resInitial, setResInitial] = useState("");
  const [resUnit, setResUnit] = useState("kg");
  const [resRate, setResRate] = useState("");
  const [resRateUnit, setResRateUnit] = useState("kg/h");

  useEffect(() => {
    void fetchTelemetryStatus(activeMission?.mission_id);
  }, [fetchTelemetryStatus, activeMission?.mission_id]);

  const handleAddResource = () => {
    const initVal = Number(resInitial);
    const rateVal = Number(resRate);
    if (!Number.isFinite(initVal) || initVal <= 0 || !Number.isFinite(rateVal) || rateVal <= 0) {
      setFormError("Resource initial inventory and consumption rate must be positive numbers.");
      return;
    }
    const resFrac = returnReservePct.trim() ? Number(returnReservePct) / 100.0 : 0.0;
    setFormError(null);
    setResources((prev) => [
      ...prev,
      {
        resource_name: resCategory,
        category: resCategory,
        unit: resUnit,
        initial_quantity: initVal,
        consumption_rate: rateVal,
        rate_unit: resRateUnit,
        reserve_fraction: Number.isFinite(resFrac) && resFrac >= 0 && resFrac < 1 ? resFrac : 0.0,
        source_note: "USER_ASSUMED",
      },
    ]);
    setResInitial("");
    setResRate("");
  };

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (locomotionCategory === "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL") {
      setFormError(
        "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL is UNAVAILABLE: no validated Mars spacesuit locomotion model is configured."
      );
      return;
    }
    if (!activeRoute || activeRoute.vertices.length < 2) {
      setFormError("Compute a terrain-backed route in /planner first (no default Gale Crater route will be substituted).");
      return;
    }
    const datasetId = activeRoute.dataset_id || selectedDemDatasetId;
    if (!datasetId) {
      setFormError("A valid DEM dataset_id is required.");
      return;
    }

    const startV = activeRoute.vertices[0];
    const endV = activeRoute.vertices[activeRoute.vertices.length - 1];
    const spd = walkingSpeedMps.trim() ? Number(walkingSpeedMps) : null;
    const durS = durationLimitMin.trim() ? Number(durationLimitMin) * 60.0 : null;
    const ovhS = overheadMin.trim() ? Number(overheadMin) * 60.0 : 0.0;
    const resFrac = returnReservePct.trim() ? Number(returnReservePct) / 100.0 : null;
    const massKg = suitPlusBodyMassKg.trim() ? Number(suitPlusBodyMassKg) : null;
    const payKg = payloadMassKg.trim() ? Number(payloadMassKg) : null;

    if (
      (spd !== null && (!Number.isFinite(spd) || spd <= 0)) ||
      (durS !== null && (!Number.isFinite(durS) || durS <= 0)) ||
      (resFrac !== null && (!Number.isFinite(resFrac) || resFrac < 0 || resFrac >= 1))
    ) {
      setFormError("Check numeric EVA parameters: speed/duration must be > 0 and reserve must be 0–99%.");
      return;
    }

    await evaluateMission({
      mission_id: activeMission?.mission_id,
      mission_name: activeMission?.name || "Configured EVA",
      dataset_id: datasetId,
      start: { lat: startV.lat, lon_east: startV.lon_east, label: startV.stop_label || "Start" },
      destination: { lat: endV.lat, lon_east: endV.lon_east, label: endV.stop_label || "Destination" },
      walking_speed_mps: spd,
      use_tobler_grade_approximation: locomotionCategory === "TERRESTRIAL_HIKING_APPROXIMATION",
      locomotion_category: locomotionCategory,
      unknown_terrain_policy: unknownPolicy,
      mission_duration_limit_s: durS,
      return_reserve_fraction: resFrac,
      operational_overhead_s: ovhS,
      astronaut_suit_mass_kg: massKg,
      payload_mass_kg: payKg,
      resources,
      compute_reverse_return_route: true,
    });
  };

  const timelineSteps = evaEnvelope?.schedule || [];

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <PageHeader
        title="EVA Operations Workstation"
        badge={activeMission ? activeMission.name : "EXPLICIT ASSUMPTIONS"}
        description="Unified Marswalk configuration, locomotion model separation, dimensional resource accounting, mechanical vs metabolic energy distinction, and operational timeline."
        actions={
          <div className="flex flex-wrap gap-2 text-xs">
            <Link href="/active-navigation" className="px-3 py-1.5 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold">
              Active Navigation
            </Link>
            <Link href="/mission-readiness" className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-surface)] border border-[var(--border-subtle)]">
              Readiness Dossier
            </Link>
          </div>
        }
      />

      {/* Telemetry & Links Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
        <div className="ms-panel p-3.5 space-y-1">
          <div className="text-[var(--text-secondary)] font-mono">RESOURCE TELEMETRY</div>
          <StatusIndicator
            label={telemetryStatus?.connected ? "PROVIDER CONNECTED" : "LIVE RESOURCE TELEMETRY NOT CONNECTED"}
            tone={telemetryStatus?.connected ? "success" : "warning"}
          />
        </div>
        <Link href="/simulation" className="ms-panel p-3.5 hover:border-[var(--accent-telemetry)] space-y-1">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>3D EVA Simulation</span>
            <Gauge className="w-4 h-4 text-[var(--accent-telemetry)]" />
          </div>
          <div className="font-mono text-[var(--text-primary)]">Launch interactive scrubber</div>
        </Link>
        <Link href="/crew" className="ms-panel p-3.5 hover:border-[#1F9D68] space-y-1">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>Crew & Mass Profiles</span>
            <Users className="w-4 h-4 text-[#4ade80]" />
          </div>
          <div className="font-mono text-[var(--text-primary)]">
            {authenticated && activeMission ? `${crew.length} crew members` : "Sign in for crew"}
          </div>
        </Link>
        <Link href="/science-campaign" className="ms-panel p-3.5 hover:border-[var(--accent-mars)] space-y-1">
          <div className="flex items-center justify-between text-[var(--text-secondary)]">
            <span>Science Campaigns</span>
            <CheckCircle2 className="w-4 h-4 text-[var(--accent-mars)]" />
          </div>
          <div className="font-mono text-[var(--text-primary)]">{campaigns.length} campaigns loaded</div>
        </Link>
      </div>

      {/* Unified EVA Configuration Form */}
      <form onSubmit={handleEvaluate} className="ms-panel p-5 space-y-4 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-semibold text-sm text-[var(--text-primary)] flex items-center gap-2">
            <Layers className="w-4 h-4 text-[var(--accent-telemetry)]" />
            <span>Mission & Locomotion Assumptions (Classified USER_ASSUMED)</span>
          </div>
          <span className="font-mono text-[11px] text-[var(--text-secondary)]">
            {activeRoute
              ? `Active Route: ${activeRoute.dataset_id} (${(activeRoute.total_surface_distance_m / 1000).toFixed(2)} km)`
              : "No computed route loaded (/planner)"}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Locomotion Model Category</label>
            <select
              value={locomotionCategory}
              onChange={(e) => setLocomotionCategory(e.target.value as typeof locomotionCategory)}
              className="w-full ms-input"
            >
              <option value="USER_CONFIGURED_CONSTANT_SPEED">1. User-Configured Constant Speed</option>
              <option value="TERRESTRIAL_HIKING_APPROXIMATION">2. Terrestrial Hiking Approximation (NOT Mars suit)</option>
              <option value="MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL">3. Mission-Validated Suit Model (UNAVAILABLE)</option>
            </select>
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Reference Speed (m/s, USER_ASSUMED)</label>
            <input
              type="number"
              step="any"
              value={walkingSpeedMps}
              onChange={(e) => setWalkingSpeedMps(e.target.value)}
              placeholder="Explicit m/s"
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Unknown Terrain Policy</label>
            <select
              value={unknownPolicy}
              onChange={(e) => setUnknownPolicy(e.target.value as typeof unknownPolicy)}
              className="w-full ms-input"
            >
              <option value="EXCLUDE_UNKNOWN">EXCLUDE_UNKNOWN</option>
              <option value="REQUIRE_ADDITIONAL_OBSERVATION">REQUIRE_ADDITIONAL_OBSERVATION</option>
              <option value="ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE">ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE</option>
            </select>
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Duration Limit (min, optional)</label>
            <input
              type="number"
              step="any"
              value={durationLimitMin}
              onChange={(e) => setDurationLimitMin(e.target.value)}
              placeholder="Not configured if blank"
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Operational Overhead (min)</label>
            <input
              type="number"
              step="any"
              value={overheadMin}
              onChange={(e) => setOverheadMin(e.target.value)}
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Return Reserve (%, optional)</label>
            <input
              type="number"
              step="any"
              value={returnReservePct}
              onChange={(e) => setReturnReservePct(e.target.value)}
              placeholder="e.g. 20"
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Astronaut + Suit Mass (kg, USER_ASSUMED)</label>
            <input
              type="number"
              step="any"
              value={suitPlusBodyMassKg}
              onChange={(e) => setSuitPlusBodyMassKg(e.target.value)}
              placeholder="Link via /profile or enter"
              className="w-full ms-input"
            />
          </div>
          <div>
            <label className="block text-[var(--text-secondary)] mb-1">Equipment / Payload Mass (kg, USER_ASSUMED)</label>
            <input
              type="number"
              step="any"
              value={payloadMassKg}
              onChange={(e) => setPayloadMassKg(e.target.value)}
              placeholder="Optional"
              className="w-full ms-input"
            />
          </div>
        </div>

        {locomotionCategory === "TERRESTRIAL_HIKING_APPROXIMATION" && (
          <div className="p-2.5 rounded-[4px] bg-[#D98A1F]/10 border border-[#D98A1F]/40 text-[#f5b041] font-mono">
            Warning: Terrestrial hiking (Tobler) approximation is NOT a validated Mars spacesuit locomotion model.
          </div>
        )}

        {/* Explicit Resource Inventory Builder */}
        <div className="pt-2 border-t border-[var(--border-subtle)] space-y-2.5">
          <div className="font-semibold text-[var(--text-primary)]">
            Explicit Resource Budgets (Unconfigured categories remain NOT CONFIGURED — never 0 consumption)
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
            <select value={resCategory} onChange={(e) => setResCategory(e.target.value)} className="ms-input">
              <option value="OXYGEN">OXYGEN</option>
              <option value="BATTERY">BATTERY</option>
              <option value="WATER">WATER</option>
              <option value="COOLING">COOLING</option>
              <option value="CO2_SCRUBBER">CO2_SCRUBBER</option>
              <option value="COMMUNICATION">COMMUNICATION</option>
            </select>
            <input
              type="number"
              step="any"
              value={resInitial}
              onChange={(e) => setResInitial(e.target.value)}
              placeholder="Initial inventory"
              className="ms-input"
            />
            <input value={resUnit} onChange={(e) => setResUnit(e.target.value)} placeholder="Unit (kg, Wh, L)" className="ms-input" />
            <input
              type="number"
              step="any"
              value={resRate}
              onChange={(e) => setResRate(e.target.value)}
              placeholder="Rate Q_dot"
              className="ms-input"
            />
            <input
              value={resRateUnit}
              onChange={(e) => setResRateUnit(e.target.value)}
              placeholder="Rate unit (kg/h, W)"
              className="ms-input"
            />
            <button
              type="button"
              onClick={handleAddResource}
              className="inline-flex items-center justify-center gap-1 py-2 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-strong)] hover:border-[var(--accent-telemetry)] font-semibold"
            >
              <Plus className="w-3.5 h-3.5" /> Add
            </button>
          </div>
          {resources.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {resources.map((r, idx) => (
                <div
                  key={`${r.category}-${idx}`}
                  className="inline-flex items-center gap-2 px-2.5 py-1 rounded-[4px] bg-[var(--bg-void)] border border-[var(--border-subtle)] font-mono"
                >
                  <span>
                    {r.category}: {r.initial_quantity} {r.unit} @ {r.consumption_rate} {r.rate_unit}
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove ${r.category}`}
                    onClick={() => setResources((prev) => prev.filter((_, i) => i !== idx))}
                    className="text-[#ff6b7a]"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {(formError || error) && (
          <div role="alert" className="text-[#ff6b7a] font-mono">
            {formError || error}
          </div>
        )}

        <button
          type="submit"
          disabled={loadingEva}
          className="px-4 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold"
        >
          {loadingEva ? "Evaluating EVA Envelope..." : "Evaluate EVA Mission Envelope"}
        </button>
      </form>

      {/* Evaluated Envelope & Energy/Resource Separation */}
      {evaEnvelope && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
          <div className="ms-panel p-4 space-y-2.5">
            <div className="flex items-center justify-between font-semibold text-sm text-[var(--text-primary)]">
              <span>Feasibility, Energy Separation & Return Plan</span>
              <StatusIndicator label={evaEnvelope.envelope_status} tone="telemetry" />
            </div>
            <div className="font-mono space-y-1 text-[var(--text-secondary)]">
              <div>
                Mechanical climb work: {evaEnvelope.energy_budget?.total_positive_climb_work_j != null
                  ? `${evaEnvelope.energy_budget.total_positive_climb_work_j.toFixed(0)} J (NOT metabolic expenditure)`
                  : "UNAVAILABLE (mass or elevation missing)"}
              </div>
              <div>
                Metabolic / Suit Electrical:{" "}
                {evaEnvelope.resource_budget?.entries?.length
                  ? `${evaEnvelope.resource_budget.entries.length} configured resource models`
                  : "NOT CONFIGURED (no metabolic or suit electrical rate assumed)"}
              </div>
              <div>
                Independent Return:{" "}
                {evaEnvelope.return_plan
                  ? `${evaEnvelope.return_plan.return_status} (${evaEnvelope.return_plan.return_surface_distance_m.toFixed(1)} m)`
                  : "UNAVAILABLE"}
              </div>
            </div>
          </div>

          <div className="ms-panel p-4 space-y-2.5">
            <div className="flex items-center gap-2 font-semibold text-sm text-[var(--text-primary)]">
              <Clock className="w-4 h-4 text-[var(--accent-telemetry)]" />
              <span>Mission Timeline (Planned Steps vs Recorded Events)</span>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1.5 font-mono text-[11px]">
              {timelineSteps.map((st) => {
                const dur = st.duration_constant_speed_s ?? st.duration_tobler_approx_s;
                return (
                  <div key={st.sequence_index} className="flex justify-between border-b border-[var(--border-subtle)]/40 pb-1">
                    <span>
                      [PLANNED] Step {st.sequence_index}: {st.label}
                    </span>
                    <span className="text-[var(--text-secondary)]">
                      {dur != null ? `${(dur / 60).toFixed(1)} min` : "DURATION_UNAVAILABLE"}
                    </span>
                  </div>
                );
              })}
              {missionEvents.slice(0, 10).map((ev) => (
                <div key={ev.event_id} className="flex justify-between text-[var(--accent-telemetry)]">
                  <span>
                    [RECORDED #{ev.event_seq}] {ev.event_type}
                  </span>
                  <span>{new Date(ev.server_timestamp_utc).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="ms-panel p-4 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-[var(--text-secondary)]">
          <Activity className="w-4 h-4 text-[var(--accent-telemetry)]" />
          <span>Astronaut body, suit, and equipment masses are stored as USER_ASSUMED on your Astronaut Profile.</span>
        </div>
        <Link href="/profile" className="text-[var(--accent-telemetry)] font-mono underline">
          Edit Profile Mass
        </Link>
      </div>
    </div>
  );
}
