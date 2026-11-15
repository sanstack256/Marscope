"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Crosshair, Microscope, Search } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { useAuthMissionStore } from "../../stores/useAuthMissionStore";
import { useSpatialStore } from "../../stores/useSpatialStore";
import { PageHeader } from "../../components/PageHeader";
import { StatusIndicator } from "../../components/ui/StatusIndicator";
import { EmptyState } from "../../components/ui/EmptyState";
import { VoiceRecorderWidget } from "../../components/ui/VoiceRecorderWidget";
import {
  FieldObservation,
  ObservationCategory,
  ObservationEpistemicState,
  VoiceNoteRecord,
} from "../../types";

interface VocabEntry {
  canonical_id: string;
  canonical_name: string;
  category: string;
}

export default function FieldObservationsPage() {
  const {
    authenticated,
    activeMissionId,
    activeMission,
    observations,
    createFieldObservation,
    refreshMissionWorkspace,
  } = useAuthMissionStore();
  const setFocusCoordinate = useSpatialStore((s) => s.setFocusCoordinate);

  const [category, setCategory] = useState<ObservationCategory>("MINERAL_DISCOVERY");
  const [speciesName, setSpeciesName] = useState("");
  const [speciesSuggestions, setSpeciesSuggestions] = useState<VocabEntry[]>([]);
  const [description, setDescription] = useState("");
  const [latStr, setLatStr] = useState("");
  const [lonStr, setLonStr] = useState("");
  const [targetId, setTargetId] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [voiceNote, setVoiceNote] = useState<VoiceNoteRecord | null>(null);
  const [formMsg, setFormMsg] = useState<string | null>(null);

  const [filterCat, setFilterCat] = useState("");
  const [filterState, setFilterState] = useState("");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  useEffect(() => {
    const q = speciesName.trim();
    const timer = setTimeout(async () => {
      if (!authenticated || q.length < 2) {
        setSpeciesSuggestions([]);
        return;
      }
      const res = await apiFetch(`/missions/vocabulary/species?q=${encodeURIComponent(q)}`);
      if (res.ok) setSpeciesSuggestions(await res.json());
    }, 180);
    return () => clearTimeout(timer);
  }, [authenticated, speciesName]);

  if (!authenticated || !activeMissionId || !activeMission) {
    return (
      <div className="max-w-4xl mx-auto">
        <EmptyState
          icon={Microscope}
          title="Active Mission Required"
          description="Sign in and join an active mission to record or review crew field observations."
        />
      </div>
    );
  }

  const canReview = ["MISSION_LEAD", "MISSION_OPERATOR"].includes(activeMission.my_role);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormMsg(null);
    const payload: Record<string, unknown> = {
      category,
      description: description.trim(),
      coordinate_source: latStr.trim() && lonStr.trim() ? "USER_REPORTED" : "UNKNOWN",
      target_id: targetId.trim() || undefined,
      species_name: speciesName.trim() || undefined,
      evidence_ids: evidenceId.trim() ? [evidenceId.trim()] : [],
      voice_note_id: voiceNote?.voice_note_id || undefined,
    };
    if (latStr.trim() || lonStr.trim()) {
      const lt = Number(latStr);
      const ln = Number(lonStr);
      if (!Number.isFinite(lt) || !Number.isFinite(ln)) {
        setFormMsg("Latitude and East Longitude must be valid decimal degrees.");
        return;
      }
      payload.latitude = lt;
      payload.longitude = ln;
    }
    const res = await createFieldObservation(payload);
    if (!res.ok) {
      setFormMsg(res.error || "Failed to log observation.");
    } else if (res.queuedOffline) {
      setFormMsg("Saved to IndexedDB offline queue (QUEUED_OFFLINE) for automatic sync.");
      setDescription("");
    } else {
      setFormMsg("Observation saved with USER_REPORTED epistemic state.");
      setDescription("");
      setSpeciesName("");
      setEvidenceId("");
      setVoiceNote(null);
    }
  };

  const handleReview = async (obs: FieldObservation, state: ObservationEpistemicState) => {
    const res = await apiFetch(`/missions/${activeMissionId}/observations/${obs.observation_id}/review`, {
      method: "POST",
      body: JSON.stringify({
        expected_version: obs.version,
        epistemic_state: state,
        review_note: reviewNote.trim() || `Reviewed as ${state}`,
      }),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      setFormMsg(b.detail || "Review failed.");
      return;
    }
    setReviewingId(null);
    setReviewNote("");
    await refreshMissionWorkspace(activeMissionId);
  };

  const visible = observations.filter(
    (o) => (!filterCat || o.category === filterCat) && (!filterState || o.epistemic_state === filterState)
  );

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader
        title="Crew Field Observations"
        badge="SPECIES VOCABULARY"
        description="Log surface discoveries, hazards, and sample notes strictly classified as USER_REPORTED until corroborated by attached evidence via authorized review."
      />

      <form onSubmit={handleSubmit} className="ms-panel p-4 space-y-3 text-xs">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as ObservationCategory)}
            className="ms-input text-xs"
          >
            <option value="MINERAL_DISCOVERY">MINERAL_DISCOVERY</option>
            <option value="HAZARD_REPORT">HAZARD_REPORT</option>
            <option value="SAMPLE_NOTE">SAMPLE_NOTE</option>
            <option value="TERRAIN_ANOMALY">TERRAIN_ANOMALY</option>
            <option value="SCIENCE_NOTE">SCIENCE_NOTE</option>
          </select>

          <div className="relative">
            <input
              type="text"
              value={speciesName}
              onChange={(e) => setSpeciesName(e.target.value)}
              placeholder="Species / mineral (e.g. hematite)"
              className="w-full ms-input text-xs"
            />
            {speciesSuggestions.length > 0 && (
              <div className="absolute z-20 left-0 right-0 mt-1 ms-panel-elevated max-h-40 overflow-y-auto divide-y divide-[var(--border-subtle)]">
                {speciesSuggestions.slice(0, 6).map((s) => (
                  <button
                    key={s.canonical_id}
                    type="button"
                    onClick={() => {
                      setSpeciesName(s.canonical_id);
                      setSpeciesSuggestions([]);
                    }}
                    className="w-full px-2.5 py-1.5 text-left hover:bg-white/10 flex justify-between"
                  >
                    <span>{s.canonical_name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{s.category}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <input
            type="text"
            value={latStr}
            onChange={(e) => setLatStr(e.target.value)}
            placeholder="Lat deg (opt)"
            className="ms-input font-mono text-xs"
          />
          <input
            type="text"
            value={lonStr}
            onChange={(e) => setLonStr(e.target.value)}
            placeholder="East Lon deg (opt)"
            className="ms-input font-mono text-xs"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <input
            type="text"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            placeholder="Linked Target ID (optional)"
            className="ms-input font-mono text-xs"
          />
          <input
            type="text"
            value={evidenceId}
            onChange={(e) => setEvidenceId(e.target.value)}
            placeholder="Supporting PDS Product / Evidence ID (optional)"
            className="ms-input font-mono text-xs"
          />
        </div>

        <textarea
          rows={2}
          required
          minLength={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Field report description..."
          className="w-full ms-input"
        />

        <VoiceRecorderWidget
          missionId={activeMissionId}
          linkedEventType="OBSERVATION"
          onUploaded={(rec) => setVoiceNote(rec)}
          compact
        />

        <div className="flex items-center justify-between flex-wrap gap-2">
          <button
            type="submit"
            className="px-4 py-2 rounded-[4px] bg-[var(--accent-mars)] text-white font-semibold"
          >
            Submit Field Observation
          </button>
          {formMsg && <span className="font-mono text-[11px] text-[var(--accent-telemetry)]">{formMsg}</span>}
        </div>
      </form>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Search className="w-4 h-4 text-[var(--text-muted)]" />
        <select value={filterCat} onChange={(e) => setFilterCat(e.target.value)} className="ms-input text-xs py-1">
          <option value="">All Categories</option>
          <option value="MINERAL_DISCOVERY">MINERAL_DISCOVERY</option>
          <option value="HAZARD_REPORT">HAZARD_REPORT</option>
          <option value="SAMPLE_NOTE">SAMPLE_NOTE</option>
          <option value="TERRAIN_ANOMALY">TERRAIN_ANOMALY</option>
          <option value="SCIENCE_NOTE">SCIENCE_NOTE</option>
        </select>
        <select value={filterState} onChange={(e) => setFilterState(e.target.value)} className="ms-input text-xs py-1">
          <option value="">All Epistemic States</option>
          <option value="USER_REPORTED">USER_REPORTED</option>
          <option value="CORROBORATED_BY_EVIDENCE">CORROBORATED_BY_EVIDENCE</option>
          <option value="CONTESTED">CONTESTED</option>
          <option value="RETRACTED">RETRACTED</option>
        </select>
      </div>

      {/* Observation List */}
      <div className="space-y-3">
        {visible.length === 0 ? (
          <EmptyState
            icon={Microscope}
            title="No Matching Field Observations"
            description="Create a crew observation above or adjust filters."
          />
        ) : (
          visible.map((obs) => (
            <div key={obs.observation_id} className="ms-panel p-4 space-y-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm text-[var(--text-primary)]">{obs.category}</span>
                  {obs.species_display_name && (
                    <StatusIndicator label={obs.species_display_name} tone="telemetry" />
                  )}
                  <span className="font-mono text-[11px] text-[var(--text-muted)]">
                    v{obs.version} · {obs.astronaut_display_name}
                  </span>
                </div>
                <StatusIndicator
                  label={obs.epistemic_state}
                  tone={
                    obs.epistemic_state === "CORROBORATED_BY_EVIDENCE"
                      ? "success"
                      : obs.epistemic_state === "CONTESTED"
                      ? "danger"
                      : "warning"
                  }
                />
              </div>

              <p className="text-[var(--text-primary)]">{obs.description}</p>

              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-[var(--text-secondary)]">
                <span>
                  {obs.latitude != null && obs.longitude_east != null
                    ? `${obs.latitude.toFixed(5)}, ${obs.longitude_east.toFixed(5)} E (${obs.coordinate_source})`
                    : "Coordinates: UNKNOWN"}
                  {obs.evidence_ids.length > 0 && ` · Evidence: ${obs.evidence_ids.join(", ")}`}
                </span>
                <div className="flex items-center gap-2">
                  {obs.latitude != null && obs.longitude_east != null && (
                    <button
                      type="button"
                      onClick={() =>
                        setFocusCoordinate({
                          lat: obs.latitude!,
                          lon: obs.longitude_east!,
                          label: obs.species_display_name || obs.category,
                        })
                      }
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-[4px] border border-[var(--border-strong)]"
                    >
                      <Crosshair className="w-3 h-3" />
                      <span>Focus 3D</span>
                    </button>
                  )}
                  {canReview && (
                    <button
                      type="button"
                      onClick={() => setReviewingId(reviewingId === obs.observation_id ? null : obs.observation_id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-strong)]"
                    >
                      <CheckCircle2 className="w-3 h-3 text-[#4ade80]" />
                      <span>Review</span>
                    </button>
                  )}
                </div>
              </div>

              {obs.voice_note && <audio controls src={obs.voice_note.playback_url} className="w-full h-8" />}

              {reviewingId === obs.observation_id && (
                <div className="pt-2 border-t border-[var(--border-subtle)] flex flex-wrap items-center gap-2">
                  <input
                    type="text"
                    value={reviewNote}
                    onChange={(e) => setReviewNote(e.target.value)}
                    placeholder="Review note..."
                    className="flex-1 ms-input text-xs py-1"
                  />
                  <button
                    type="button"
                    onClick={() => void handleReview(obs, "CORROBORATED_BY_EVIDENCE")}
                    className="px-2.5 py-1 rounded-[4px] bg-[#1F9D68] text-white font-semibold"
                  >
                    Corroborate
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReview(obs, "CONTESTED")}
                    className="px-2.5 py-1 rounded-[4px] bg-[#DC3545] text-white font-semibold"
                  >
                    Contest
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
