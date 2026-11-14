"use client";

import { useEffect, useState } from "react";
import { AlertOctagon, CheckCircle2, Cpu, Database, Download, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { API_BASE_URL } from "../../lib/constants";
import { CompositionIndexStatus, Dataset, Observation, RejectionRecord, SourceRegistryEntry } from "../../types";

export default function EvidenceProvenancePage() {
  const [sources, setSources] = useState<SourceRegistryEntry[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [indexStatus, setIndexStatus] = useState<CompositionIndexStatus | null>(null);
  const [rejectedRecords, setRejectedRecords] = useState<RejectionRecord[]>([]);
  const [rebuildingIndex, setRebuildingIndex] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [busyDatasetId, setBusyDatasetId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refreshAll() {
    setLoading(true);
    setError(null);
    try {
      const [sRes, dRes, oRes, iRes, rRes] = await Promise.all([
        fetch(`${API_BASE_URL}/sources`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/composition/index/status`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/composition/rejected?limit=25`, { cache: "no-store" }),
      ]);
      if (sRes.ok) setSources(await sRes.json());
      if (dRes.ok) setDatasets(await dRes.json());
      if (oRes.ok) setObservations(await oRes.json());
      if (iRes.ok) setIndexStatus(await iRes.json());
      if (rRes.ok) {
        const rejData = await rRes.json();
        setRejectedRecords(rejData.records || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch provenance records");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        const [sRes, dRes, oRes, iRes, rRes] = await Promise.all([
          fetch(`${API_BASE_URL}/sources`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/composition/index/status`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/composition/rejected?limit=25`, { cache: "no-store" }),
        ]);
        if (!active) return;
        if (sRes.ok) setSources(await sRes.json());
        if (dRes.ok) setDatasets(await dRes.json());
        if (oRes.ok) setObservations(await oRes.json());
        if (iRes.ok) setIndexStatus(await iRes.json());
        if (rRes.ok) {
          const rejData = await rRes.json();
          setRejectedRecords(rejData.records || []);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to fetch provenance records");
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  async function handleRebuildCompositionIndex() {
    setRebuildingIndex(true);
    setActionMessage(null);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/composition/index/rebuild`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status} rebuilding composition index`);
      const st: CompositionIndexStatus = await res.json();
      setIndexStatus(st);
      setActionMessage(
        `Rebuilt SQLite R*Tree composition index (${st.active_generation_id}): ${st.located_evidence_count} located, ${st.unlocated_evidence_count} unlocated, ${st.rejected_record_count} rejected.`
      );
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to rebuild composition index");
    } finally {
      setRebuildingIndex(false);
    }
  }

  async function runDatasetAction(datasetId: string, action: "verify-remote" | "download" | "validate" | "process") {
    setBusyDatasetId(datasetId);
    setActionMessage(null);
    setError(null);
    try {
      const url =
        action === "process"
          ? `${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}/process`
          : `${API_BASE_URL}/datasets/${encodeURIComponent(datasetId)}/${action}`;
      const res = await fetch(url, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status} running ${action} on ${datasetId}`);
      }
      setActionMessage(`${action.toUpperCase()} completed for ${datasetId}: ${data.message || data.status || "OK"}`);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Action ${action} failed`);
    } finally {
      setBusyDatasetId(null);
    }
  }

  async function runDiscoverSources() {
    setLoading(true);
    setActionMessage(null);
    try {
      const res = await fetch(`${API_BASE_URL}/datasets/discover`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status} discovering sources`);
      const discovered = await res.json();
      setActionMessage(`Refreshed catalog from NASA source adapters (${discovered.length} records).`);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Source discovery failed");
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Evidence, Sources & Ingestion Pipeline"
        badge={`${sources.length} NASA Sources · ${datasets.length} Products`}
        description="Live verification matrix separating Archive Availability, Discovery, Metadata, License, Coverage, Download, and Processing state. Execute remote probes, product downloads, and DEM processing directly."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={runDiscoverSources}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-xs font-medium text-slate-200 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Re-Discover Catalog</span>
            </button>
          </div>
        }
      />

      {error && (
        <div className="p-3.5 rounded-xl bg-red-950/40 border border-red-800/50 text-xs text-red-200">
          {error}
        </div>
      )}

      {actionMessage && (
        <div className="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-700/50 text-xs text-emerald-200 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Source Registry Verification Breakdown */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-100 border-b border-[#1e2638] pb-3">
          <ShieldCheck className="w-4 h-4 text-[#38bdf8]" />
          <span>Authoritative NASA Source Verification Matrix</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {sources.map((src) => (
            <div key={src.source_name} className="p-4 rounded-xl bg-[#0d111a] border border-[#1d2536] space-y-2.5">
              <div>
                <div className="text-xs font-bold text-slate-100">{src.source_name}</div>
                <div className="text-[10px] font-mono text-slate-500 truncate">{src.base_url}</div>
              </div>
              <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                {Object.entries(src.verification_breakdown).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-1 bg-[#121622] px-2 py-1 rounded border border-[#1e2638]">
                    <span className="text-slate-400 truncate">{k.replace("_verification", "").replace("_", " ")}</span>
                    <StatusBadge status={v} />
                  </div>
                ))}
              </div>
              {src.evidence_notes.length > 0 && (
                <div className="text-[10px] text-slate-400 pt-1 border-t border-[#1c2436] space-y-0.5">
                  {src.evidence_notes.slice(0, 2).map((note, idx) => (
                    <div key={idx} className="truncate" title={note}>
                      • {note}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Discovered & Acquired Datasets Table */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-[#1e2638] pb-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <Database className="w-4 h-4 text-[#e25b38]" />
            <span>Planetary Products ({datasets.length}) · Parsed Observations ({observations.length})</span>
          </div>
        </div>

        <div className="space-y-3">
          {datasets.map((ds) => {
            const busy = busyDatasetId === ds.id;
            const isWmts = ds.data_format === "WMTS";
            const isElevation =
              ds.product_type.toUpperCase().includes("DEM") ||
              ds.product_type.toUpperCase().includes("ELEVATION");
            const downloaded = ds.verification?.download_verification === "verified";

            return (
              <div key={ds.id} className="p-4 rounded-xl bg-[#0d111a] border border-[#1d2536] space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-bold text-slate-100">{ds.product_title}</span>
                      <StatusBadge status={ds.status === "processed" || ds.status === "validated" ? "verified" : ds.status} label={ds.status} />
                    </div>
                    <div className="text-[11px] font-mono text-slate-400">
                      ID: {ds.id} · Product: {ds.product_id} · {ds.data_format} · {ds.license} · Units: {ds.units}
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Coverage: Lat [{ds.coverage.min_latitude}°, {ds.coverage.max_latitude}°], Lon [{ds.coverage.min_longitude}°, {ds.coverage.max_longitude}°] ({ds.coverage.longitude_range}) · CRS: {ds.coordinate_reference_system || "Unknown"}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 shrink-0">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => runDatasetAction(ds.id, "verify-remote")}
                      className="px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[11px] font-medium text-slate-200 disabled:opacity-50"
                    >
                      Verify Remote
                    </button>
                    {!isWmts && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => runDatasetAction(ds.id, "download")}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[11px] font-medium text-sky-200 disabled:opacity-50"
                        >
                          <Download className="w-3 h-3" />
                          <span>{downloaded ? "Downloaded" : "Download"}</span>
                        </button>
                        <button
                          type="button"
                          disabled={busy || !downloaded}
                          onClick={() => runDatasetAction(ds.id, "validate")}
                          className="px-2.5 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#2a3650] text-[11px] font-medium text-emerald-200 disabled:opacity-40"
                        >
                          Validate
                        </button>
                      </>
                    )}
                    {isElevation && (
                      <button
                        type="button"
                        disabled={busy || !downloaded}
                        onClick={() => runDatasetAction(ds.id, "process")}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#e25b38] hover:bg-[#cf4f2e] text-[11px] font-semibold text-white disabled:opacity-40"
                      >
                        <Cpu className="w-3 h-3" />
                        <span>Process DEM</span>
                      </button>
                    )}
                    <a
                      href={ds.original_product_url}
                      target="_blank"
                      rel="noreferrer"
                      className="p-1.5 rounded-lg bg-[#161c2b] border border-[#252f44] text-slate-400 hover:text-slate-100"
                      title="Open NASA archive product URL"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>

                {/* Separated 7-field Verification Strip */}
                <div className="flex flex-wrap gap-1.5">
                  <StatusBadge status={ds.verification.archive_availability} label={`Archive: ${ds.verification.archive_availability}`} />
                  <StatusBadge status={ds.verification.product_discovery} label={`Discovery: ${ds.verification.product_discovery}`} />
                  <StatusBadge status={ds.verification.metadata_verification} label={`Metadata: ${ds.verification.metadata_verification}`} />
                  <StatusBadge status={ds.verification.license_verification} label={`License: ${ds.verification.license_verification}`} />
                  <StatusBadge status={ds.verification.coverage_verification} label={`Coverage: ${ds.verification.coverage_verification}`} />
                  <StatusBadge status={ds.verification.download_verification} label={`Download: ${ds.verification.download_verification}`} />
                  <StatusBadge status={ds.verification.processing_verification} label={`Processed: ${ds.verification.processing_verification}`} />
                </div>

                {ds.failure_reason && (
                  <div className="text-[11px] text-red-300 font-mono">Error: {ds.failure_reason}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Composition Spatial Index & Rejection Audit Log */}
      <div className="bg-[#121622] border border-[#1e2638] rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1e2638] pb-3">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Composition Spatial Index (SQLite R*Tree) &amp; Validation Audit</span>
          </div>
          <button
            type="button"
            onClick={handleRebuildCompositionIndex}
            disabled={rebuildingIndex}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#161c2b] hover:bg-[#1e263b] border border-[#252f44] text-xs font-medium text-slate-200 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${rebuildingIndex ? "animate-spin" : ""}`} />
            <span>{rebuildingIndex ? "Rebuilding Index..." : "Rebuild Composition Index"}</span>
          </button>
        </div>

        {indexStatus && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[11px] font-mono">
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
              <div className="text-[9px] text-slate-500">GENERATION</div>
              <div className="text-slate-100">{indexStatus.active_generation_id || "None"}</div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
              <div className="text-[9px] text-slate-500">LOCATED EVIDENCE</div>
              <div className="text-emerald-300">{indexStatus.located_evidence_count}</div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
              <div className="text-[9px] text-slate-500">UNLOCATED EVIDENCE</div>
              <div className="text-amber-300">{indexStatus.unlocated_evidence_count}</div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
              <div className="text-[9px] text-slate-500">REJECTED RECORDS</div>
              <div className="text-red-300">{indexStatus.rejected_record_count}</div>
            </div>
            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
              <div className="text-[9px] text-slate-500">CRISM ORBITAL</div>
              <div className="text-amber-200 truncate" title={indexStatus.crism_status}>
                {indexStatus.crism_status}
              </div>
            </div>
          </div>
        )}

        {rejectedRecords.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-red-300">
              <AlertOctagon className="w-3.5 h-3.5" />
              <span>Rejected Non-Composition / Invalid Records ({rejectedRecords.length})</span>
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {rejectedRecords.map((rej) => (
                <div
                  key={rej.rejection_id}
                  className="p-2.5 rounded-lg bg-[#0d111a] border border-red-900/40 text-[10px] font-mono space-y-0.5"
                >
                  <div className="flex items-center justify-between text-red-200">
                    <span>
                      {rej.instrument_id} · {rej.product_id} ({rej.source_record_ref})
                    </span>
                    <span>
                      Stage {rej.rejection_stage}: {rej.rejection_code}
                    </span>
                  </div>
                  <div className="text-slate-400">{rej.reason}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
