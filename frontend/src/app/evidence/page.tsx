"use client";

import { useEffect, useState } from "react";
import { AlertOctagon, CheckCircle2, Cpu, Database, Download, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { API_BASE_URL } from "../../lib/constants";
import {
  CompositionIndexStatus,
  Dataset,
  Observation,
  RejectionRecord,
  ReproducibilityManifest,
  SourceRegistryEntry,
} from "../../types";

export default function EvidenceProvenancePage() {
  const [sources, setSources] = useState<SourceRegistryEntry[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [indexStatus, setIndexStatus] = useState<CompositionIndexStatus | null>(null);
  const [manifest, setManifest] = useState<ReproducibilityManifest | null>(null);
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
      const [sRes, dRes, oRes, iRes, rRes, mRes] = await Promise.all([
        fetch(`${API_BASE_URL}/sources`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/composition/index/status`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/composition/rejected?limit=25`, { cache: "no-store" }),
        fetch(`${API_BASE_URL}/composition/reproducibility-manifest`, { cache: "no-store" }),
      ]);
      if (sRes.ok) setSources(await sRes.json());
      if (dRes.ok) setDatasets(await dRes.json());
      if (oRes.ok) setObservations(await oRes.json());
      if (iRes.ok) setIndexStatus(await iRes.json());
      if (rRes.ok) {
        const rejData = await rRes.json();
        setRejectedRecords(rejData.records || []);
      }
      if (mRes.ok) setManifest(await mRes.json());
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
        const [sRes, dRes, oRes, iRes, rRes, mRes] = await Promise.all([
          fetch(`${API_BASE_URL}/sources`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/observations`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/composition/index/status`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/composition/rejected?limit=25`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/composition/reproducibility-manifest`, { cache: "no-store" }),
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
        if (mRes.ok) setManifest(await mRes.json());
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
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-7 gap-2 text-[11px] font-mono">
              <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
                <div className="text-[9px] text-slate-500">INTEGRITY</div>
                <div
                  className={
                    indexStatus.integrity_status === "verified" &&
                    indexStatus.checksum_valid &&
                    indexStatus.source_dependencies_valid !== false &&
                    indexStatus.manifest_valid !== false &&
                    indexStatus.generation_build_status !== "partial" &&
                    indexStatus.generation_build_status !== "failed"
                      ? "text-emerald-300 font-semibold"
                      : indexStatus.generation_build_status === "partial"
                      ? "text-amber-300 font-semibold"
                      : "text-red-300 font-semibold"
                  }
                >
                  {(indexStatus.integrity_status || (indexStatus.checksum_valid ? "verified" : "mismatch")).toUpperCase()}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536]">
                <div className="text-[9px] text-slate-500">BUILD COMPLETENESS</div>
                <div
                  className={
                    indexStatus.generation_build_status === "complete" ||
                    indexStatus.generation_build_status === "complete_with_declared_unavailable_sources"
                      ? "text-emerald-300 font-semibold truncate"
                      : indexStatus.generation_build_status === "partial"
                      ? "text-amber-300 font-semibold truncate"
                      : "text-red-300 font-semibold truncate"
                  }
                  title={indexStatus.generation_build_status || "unknown"}
                >
                  {(indexStatus.generation_build_status || "unknown").toUpperCase()}
                </div>
              </div>
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

            <div className="p-2.5 rounded-lg bg-[#0d111a] border border-[#1d2536] text-[10px] font-mono text-slate-300 flex flex-wrap gap-x-4 gap-y-1">
              <span>Scope: {indexStatus.discovery_scope || "static_seed_manifest"}</span>
              <span>
                Products: {indexStatus.ingested_products_count}/{indexStatus.expected_products_count ?? "?"} ingested
              </span>
              {indexStatus.rights_summary?.counts && (
                <span>
                  Rights not_verified: {indexStatus.rights_summary.counts.not_verified ?? 0} · verified:{" "}
                  {indexStatus.rights_summary.counts.verified ?? 0}
                </span>
              )}
              {indexStatus.retrieval_metadata && (
                <span>
                  Retrieval timestamps: {indexStatus.retrieval_metadata.verified_retrieval_timestamps ?? 0} recorded /{" "}
                  {indexStatus.retrieval_metadata.unknown_retrieval_timestamps ?? 0} unknown (pre-existing)
                </span>
              )}
            </div>

            {(!indexStatus.checksum_valid ||
              indexStatus.source_dependencies_valid === false ||
              indexStatus.manifest_valid === false ||
              (indexStatus.missing_expected_products && indexStatus.missing_expected_products.length > 0)) && (
              <div className="p-3 rounded-lg bg-red-950/40 border border-red-800/50 text-[11px] font-mono text-red-200 space-y-1">
                <div>
                  Integrity / completeness alert ({indexStatus.integrity_status} · {indexStatus.generation_build_status}):
                </div>
                {indexStatus.missing_source_files && indexStatus.missing_source_files.length > 0 && (
                  <div>Missing source files: {indexStatus.missing_source_files.join(", ")}</div>
                )}
                {indexStatus.checksum_mismatches && indexStatus.checksum_mismatches.length > 0 && (
                  <div>Modified source SHA-256: {indexStatus.checksum_mismatches.join(", ")}</div>
                )}
                {indexStatus.missing_dependency_files && indexStatus.missing_dependency_files.length > 0 && (
                  <div>Missing companion dependencies: {indexStatus.missing_dependency_files.join(", ")}</div>
                )}
                {indexStatus.dependency_checksum_mismatches && indexStatus.dependency_checksum_mismatches.length > 0 && (
                  <div>Modified companion dependencies: {indexStatus.dependency_checksum_mismatches.join(", ")}</div>
                )}
                {indexStatus.missing_expected_products && indexStatus.missing_expected_products.length > 0 && (
                  <div>Missing expected seed products: {indexStatus.missing_expected_products.join(", ")}</div>
                )}
                {indexStatus.manifest_validation_errors && indexStatus.manifest_validation_errors.length > 0 && (
                  <div>Manifest errors: {indexStatus.manifest_validation_errors.join("; ")}</div>
                )}
              </div>
            )}
          </div>
        )}

        {manifest && manifest.products && manifest.products.length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-slate-200">
              Reproducibility Manifest ({manifest.products.length} raw NASA artifacts · {manifest.determinism_version} · Rank Config {manifest.ranking_config_id} v{manifest.ranking_config_version})
            </div>
            <div className="overflow-x-auto rounded-lg border border-[#1d2536]">
              <table className="w-full text-left text-[10px] font-mono">
                <thead className="bg-[#0d111a] text-slate-400 border-b border-[#1d2536]">
                  <tr>
                    <th className="px-2.5 py-1.5">Product</th>
                    <th className="px-2.5 py-1.5">SHA-256</th>
                    <th className="px-2.5 py-1.5">Schema</th>
                    <th className="px-2.5 py-1.5">Parser</th>
                    <th className="px-2.5 py-1.5">Coords Method</th>
                    <th className="px-2.5 py-1.5">License / Retrieval</th>
                    <th className="px-2.5 py-1.5 text-right">Accepted / Rej</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1a2233] text-slate-300">
                  {manifest.products.map((pm) => (
                    <tr key={`${pm.product_id}-${pm.sha256_checksum}`}>
                      <td className="px-2.5 py-1.5 text-slate-100">{pm.product_id}</td>
                      <td className="px-2.5 py-1.5 text-slate-400" title={pm.sha256_checksum}>
                        {pm.sha256_checksum ? `${pm.sha256_checksum.slice(0, 12)}...` : "N/A"}
                      </td>
                      <td className="px-2.5 py-1.5">{pm.schema_version || "N/A"}</td>
                      <td className="px-2.5 py-1.5">
                        {pm.parser_id || "?"} v{pm.parser_version || "?"}
                      </td>
                      <td className="px-2.5 py-1.5">{pm.coordinate_association_method || "N/A"}</td>
                      <td className="px-2.5 py-1.5 text-[10px]">
                        <span className="text-amber-300">{pm.license_status || "not_verified"}</span> ·{" "}
                        <span className="text-slate-400">{pm.retrieval_timestamp_utc || "unknown"}</span>
                      </td>
                      <td className="px-2.5 py-1.5 text-right">
                        <span className="text-emerald-300">{pm.record_count ?? 0}</span> /{" "}
                        <span className="text-red-300">{pm.rejected_count ?? 0}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {manifest.dependency_artifacts && manifest.dependency_artifacts.length > 0 && (
              <div className="space-y-1.5 pt-2">
                <div className="text-xs font-semibold text-slate-200">
                  Tracked Dependency Graph Artifacts ({manifest.dependency_artifacts.length}: primary, PDS3 .LBL/.FMT, PDS4 .XML, waypoints JSON)
                </div>
                <div className="overflow-x-auto rounded-lg border border-[#1d2536] max-h-56 overflow-y-auto">
                  <table className="w-full text-left text-[10px] font-mono">
                    <thead className="bg-[#0d111a] text-slate-400 border-b border-[#1d2536] sticky top-0">
                      <tr>
                        <th className="px-2.5 py-1.5">Role</th>
                        <th className="px-2.5 py-1.5">Artifact</th>
                        <th className="px-2.5 py-1.5">SHA-256</th>
                        <th className="px-2.5 py-1.5">Rights</th>
                        <th className="px-2.5 py-1.5">Retrieved UTC</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1a2233] text-slate-300">
                      {manifest.dependency_artifacts.map((dep) => (
                        <tr key={dep.artifact_id}>
                          <td className="px-2.5 py-1 text-sky-300">{dep.artifact_role}</td>
                          <td className="px-2.5 py-1 text-slate-100">{dep.file_path.split("/").pop() || dep.file_path}</td>
                          <td className="px-2.5 py-1 text-slate-400" title={dep.sha256_checksum || ""}>
                            {dep.sha256_checksum ? `${dep.sha256_checksum.slice(0, 12)}...` : "N/A"}
                          </td>
                          <td className="px-2.5 py-1 text-amber-300" title={dep.rights_statement || ""}>
                            {dep.license_status}
                          </td>
                          <td className="px-2.5 py-1 text-slate-400">{dep.retrieval_timestamp_utc}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
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
