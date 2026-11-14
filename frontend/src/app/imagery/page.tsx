"use client";

import { FormEvent, useState } from "react";
import { ExternalLink, Search, Download, AlertTriangle } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";

type Product = {
  product_id: string; source_archive: string; source_record_uri?: string | null; mission?: string | null; instrument?: string | null;
  dataset_id?: string | null; product_type?: string | null; observation_time?: string | null; sol?: number | null;
  latitude?: number | null; longitude?: number | null; coordinate_convention?: string | null; coordinate_reference_system?: string | null; footprint?: unknown;
  original_product_url?: string | null; browse_image_url?: string | null; label_url?: string | null;
  file_size_bytes?: number | null; archive_file_size_value?: number | null; archive_file_size_unit?: string | null;
  checksum?: string | null; checksum_algorithm?: string | null; local_sha256_checksum?: string | null;
  local_file_path?: string | null; stages: string[]; metadata_gaps: string[];
  panorama_eligibility: string; provenance: Record<string, unknown>;
};

export default function ImageryCataloguePage() {
  const [archive, setArchive] = useState<"atlas" | "ode">("atlas");
  const [filters, setFilters] = useState({ mission: "", instrument: "", dataset_id: "", product_id: "", product_type: "", sol: "", min_latitude: "", max_latitude: "", western_longitude: "", eastern_longitude: "" });
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [totalRelation, setTotalRelation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, string>>({});

  async function search(event?: FormEvent) {
    event?.preventDefault(); setLoading(true); setError(null); setTotal(null); setTotalRelation(null);
    const params = new URLSearchParams();
    const query = archive === "atlas" ? {
      mission: filters.mission, instrument: filters.instrument, dataset_id: filters.dataset_id,
      product_id: filters.product_id, product_type: filters.product_type, sol: filters.sol,
    } : {
      instrument_host_id: filters.mission, instrument_id: filters.instrument, dataset_id: filters.dataset_id,
      product_id: filters.product_id, product_type: filters.product_type, min_latitude: filters.min_latitude,
      max_latitude: filters.max_latitude, western_longitude: filters.western_longitude,
      eastern_longitude: filters.eastern_longitude,
    };
    Object.entries(query).forEach(([key, value]) => { if (value.trim()) params.set(key, value.trim()); });
    try {
      const response = await fetch(`${API_BASE_URL}/imagery/${archive === "atlas" ? "search" : "ode/search"}?${params.toString()}`, { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message || body.detail?.error || `Archive request failed (${response.status})`);
      setProducts(body.products || []); setTotal(body.total ?? null);
      setTotalRelation(body.total_relation ?? "eq");
    } catch (e) { setProducts([]); setError(e instanceof Error ? e.message : "NASA archive request failed"); }
    finally { setLoading(false); }
  }

  async function acquire(id: string) {
    setStatus((s) => ({ ...s, [id]: "queueing" }));
    try {
      const response = await fetch(`${API_BASE_URL}/imagery/products/${encodeURIComponent(id)}/acquire`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message || body.detail?.error || `HTTP ${response.status}`);
      setStatus((s) => ({ ...s, [id]: body.status }));
    } catch (e) { setStatus((s) => ({ ...s, [id]: e instanceof Error ? e.message : "Acquisition failed" })); }
  }

  async function verify(id: string) {
    setStatus((s) => ({ ...s, [id]: "checking availability" }));
    try {
      const response = await fetch(`${API_BASE_URL}/imagery/products/${encodeURIComponent(id)}/verify`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail?.message || body.detail?.error || `HTTP ${response.status}`);
      setStatus((s) => ({ ...s, [id]: body.accessible ? "download available" : `HTTP ${body.http_status}` }));
      await search();
    } catch (e) { setStatus((s) => ({ ...s, [id]: e instanceof Error ? e.message : "Verification failed" })); }
  }

  async function refreshAcquisition(id: string) {
    const response = await fetch(`${API_BASE_URL}/imagery/products/${encodeURIComponent(id)}/acquisition`, { cache: "no-store" });
    const body = await response.json(); setStatus((s) => ({ ...s, [id]: body.status?.state || "unknown" }));
    if (body.status?.state === "completed") await search();
  }

  const visibleFields: Array<keyof typeof filters> = archive === "atlas"
    ? ["mission", "instrument", "dataset_id", "product_id", "product_type", "sol"]
    : ["mission", "instrument", "dataset_id", "product_id", "product_type", "min_latitude", "max_latitude", "western_longitude", "eastern_longitude"];

  return <div className="space-y-6">
    <PageHeader title="NASA Imagery Catalogue" badge="Archive-backed" description="Search live PDS Imaging Atlas product records. Discovery, metadata, acquisition, verification, and panorama eligibility are shown as separate evidence states." />
    <form onSubmit={search} className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 rounded-xl bg-[#121622] border border-[#1e2638] p-4">
      <label className="text-[11px] text-slate-400">Archive
        <select value={archive} onChange={(e) => setArchive(e.target.value as "atlas" | "ode")} className="mt-1 w-full rounded-lg bg-[#0b0d13] border border-[#293248] px-3 py-2 text-xs text-slate-100"><option value="atlas">NASA PDS Imaging Atlas</option><option value="ode">Mars ODE</option></select>
      </label>
      {visibleFields.map((key) => <label key={key} className="text-[11px] text-slate-400 capitalize">{key.replaceAll("_", " ")}
        <input value={filters[key]} onChange={(e) => setFilters({ ...filters, [key]: e.target.value })} className="mt-1 w-full rounded-lg bg-[#0b0d13] border border-[#293248] px-3 py-2 text-xs text-slate-100 outline-none focus:border-sky-500" placeholder={key === "dataset_id" ? "Archive dataset ID" : key === "product_id" ? "Original product filename or ID" : "Any"} />
      </label>)}
      {archive === "ode" && <div className="md:col-span-2 xl:col-span-4 text-[10px] text-slate-500">ODE bounds use planetocentric latitude and east-positive longitude from 0–360. Enter all four bounds together; MSL Navcam is not an ODE-supported combination in the live query.</div>}
      <button className="md:col-span-2 xl:col-span-4 inline-flex items-center justify-center gap-2 rounded-lg bg-[#e25b38] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50" disabled={loading}><Search className="h-4 w-4" />{loading ? "Querying archive…" : `Search ${archive === "atlas" ? "NASA PDS Imaging Atlas" : "Mars ODE"}`}</button>
    </form>
    {error && <div className="flex gap-2 rounded-xl border border-red-800/50 bg-red-950/30 p-4 text-xs text-red-200"><AlertTriangle className="h-4 w-4 shrink-0" />Archive request failed: {error}</div>}
    {!loading && !error && total !== null && <div className="text-xs text-slate-400">Archive reports {total.toLocaleString()}{totalRelation === "gte" ? "+" : ""} matching indexed image records; this page returned {products.length}. Product search is paginated.</div>}
    {total === 0 && <div className="rounded-xl border border-[#1e2638] bg-[#121622] p-6 text-center text-sm text-slate-400">The archive query succeeded and returned no matching products.</div>}
    <div className="space-y-3">{products.map((p) => <article key={p.product_id} className="rounded-xl border border-[#1e2638] bg-[#121622] p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="font-mono text-sm text-slate-100 break-all">{p.product_id}</div><div className="mt-1 text-[11px] text-slate-400">{p.mission || "mission unavailable"} · {p.instrument || "instrument unavailable"} · {p.dataset_id || "dataset unavailable"}</div><div className="mt-1 text-[10px] text-slate-500">{p.source_archive}</div></div>
      <span className="rounded-md bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200">{p.panorama_eligibility.replaceAll("_", " ")}</span></div>
      <div className="flex flex-wrap gap-2 text-[10px]">{p.stages.map((stage) => <span key={stage} className="rounded-md border border-[#293248] px-2 py-1 text-slate-300">{stage.replaceAll("_", " ")}</span>)}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] text-slate-400"><div>Product type: {p.product_type || "unavailable"}</div><div>Observation: {p.observation_time || "unavailable"}{p.sol == null ? "" : ` · sol ${p.sol}`}</div><div>Center: {p.latitude == null || p.longitude == null ? "unavailable" : `${p.latitude}, ${p.longitude}`}</div><div>Coordinate convention: {p.coordinate_convention || "unavailable"}</div><div>Observed size: {p.file_size_bytes == null ? "not probed/acquired" : `${p.file_size_bytes.toLocaleString()} bytes (HTTP content length or local file)`}</div><div>Archive-reported size: {p.archive_file_size_value == null ? "unavailable" : `${p.archive_file_size_value} ${p.archive_file_size_unit}`}</div><div>Archive checksum: {p.checksum ? `${p.checksum_algorithm || "checksum"} ${p.checksum}` : "unavailable"}</div><div>Locally computed SHA-256: {p.local_sha256_checksum || "not acquired"}</div><div>Local product: {p.local_file_path || "not acquired"}</div><div className="md:col-span-2">Metadata gaps: {p.metadata_gaps.length ? p.metadata_gaps.join(", ") : "none reported by this index record"}</div></div>
      {p.footprint != null && <details className="text-[10px] text-slate-500"><summary className="cursor-pointer">Archive footprint and coordinate reference</summary><div className="mt-1">{p.coordinate_reference_system || "CRS unavailable"}</div><pre className="mt-1 whitespace-pre-wrap break-all">{String(p.footprint)}</pre></details>}
      <div className="flex flex-wrap gap-3 text-[11px]">{p.source_record_uri?.startsWith("https://") && <a className="inline-flex items-center gap-1 text-sky-300 hover:text-sky-200" href={p.source_record_uri} target="_blank" rel="noreferrer">Archive record <ExternalLink className="h-3 w-3" /></a>}{p.source_record_uri?.startsWith("atlas:") && <span className="text-slate-500">Atlas URI: {p.source_record_uri}</span>}{p.browse_image_url && <a className="inline-flex items-center gap-1 text-sky-300 hover:text-sky-200" href={p.browse_image_url} target="_blank" rel="noreferrer">Archive browse URL <ExternalLink className="h-3 w-3" /></a>}{p.label_url && <a className="inline-flex items-center gap-1 text-sky-300 hover:text-sky-200" href={p.label_url} target="_blank" rel="noreferrer">PDS label URL <ExternalLink className="h-3 w-3" /></a>}{p.original_product_url && !p.stages.includes("download_available") && <button onClick={() => verify(p.product_id)} className="text-amber-300">Verify product URL</button>}{p.original_product_url && p.stages.includes("download_available") && <button onClick={() => acquire(p.product_id)} className="inline-flex items-center gap-1 text-emerald-300 hover:text-emerald-200"><Download className="h-3 w-3" />Acquire original</button>}{status[p.product_id] && <button onClick={() => refreshAcquisition(p.product_id)} className="text-slate-300">Acquisition: {status[p.product_id]} · refresh</button>}</div>
    </article>)}</div>
  </div>;
}
