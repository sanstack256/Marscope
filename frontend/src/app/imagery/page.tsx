"use client";

import { FormEvent, useState } from "react";
import { ExternalLink, Search, Download, AlertTriangle, Camera } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { API_BASE_URL } from "../../lib/constants";
import type { PerseveranceGalleryResponse } from "../../types";

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

  // Isolated Perseverance (Jezero Crater) Raw Images Gallery state
  const [perseveranceSol, setPerseveranceSol] = useState("");
  const [perseveranceCam, setPerseveranceCam] = useState("");
  const [perseveranceLoading, setPerseveranceLoading] = useState(false);
  const [perseveranceGallery, setPerseveranceGallery] = useState<PerseveranceGalleryResponse | null>(null);

  async function fetchPerseveranceGallery() {
    setPerseveranceLoading(true);
    try {
      const p = new URLSearchParams({ limit: "6" });
      if (perseveranceSol.trim()) p.set("sol", perseveranceSol.trim());
      if (perseveranceCam.trim()) p.set("camera", perseveranceCam.trim());
      const res = await fetch(`${API_BASE_URL}/imagery/perseverance?${p.toString()}`, { cache: "no-store" });
      if (res.ok) {
        setPerseveranceGallery(await res.json());
      } else {
        setPerseveranceGallery({
          status: "remote_error",
          mission: "Mars 2020 Perseverance",
          site: "Jezero Crater",
          isolated_from_gale_planning: true,
          isolation_note: "Jezero Crater mission feed only; isolated from Gale planning.",
          source_url: "https://mars.nasa.gov/rss/api/",
          total_results: 0,
          images: [],
          error: `Backend returned HTTP ${res.status}`,
        });
      }
    } catch (e) {
      setPerseveranceGallery({
        status: "remote_unavailable",
        mission: "Mars 2020 Perseverance",
        site: "Jezero Crater",
        isolated_from_gale_planning: true,
        isolation_note: "Jezero Crater mission feed only; isolated from Gale planning.",
        source_url: "https://mars.nasa.gov/rss/api/",
        total_results: 0,
        images: [],
        error: e instanceof Error ? e.message : "Unable to reach Perseverance feed",
      });
    } finally {
      setPerseveranceLoading(false);
    }
  }

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

    {/* Isolated Jezero Crater Perseverance Raw Images Gallery */}
    <section className="rounded-xl border border-amber-500/30 bg-[#121622] p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1e2638] pb-3">
        <div>
          <div className="flex items-center gap-2">
            <Camera className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold text-slate-100">
              NASA Mars 2020 Perseverance Raw Images Gallery
            </h2>
            <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/40 text-amber-300">
              Jezero Crater · Isolated from Gale Planning
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Direct Mars 2020 RSS image browser. Strictly separated from Gale Crater / Curiosity terrain models, targets, and route synthesis.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="number"
            min={0}
            placeholder="Sol (optional)"
            value={perseveranceSol}
            onChange={(e) => setPerseveranceSol(e.target.value)}
            className="w-28 rounded-lg bg-[#0b0d13] border border-[#293248] px-2.5 py-1.5 text-xs text-slate-100"
          />
          <input
            type="text"
            placeholder="Camera (e.g. SUPERCAM_RMI)"
            value={perseveranceCam}
            onChange={(e) => setPerseveranceCam(e.target.value)}
            className="w-44 rounded-lg bg-[#0b0d13] border border-[#293248] px-2.5 py-1.5 text-xs text-slate-100"
          />
          <button
            type="button"
            onClick={() => void fetchPerseveranceGallery()}
            disabled={perseveranceLoading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#1c263b] hover:bg-[#25324d] border border-[#2f3d5d] px-3 py-1.5 text-xs font-semibold text-amber-200 disabled:opacity-50"
          >
            {perseveranceLoading ? "Querying Jezero RSS…" : "Fetch Perseverance Raw Images"}
          </button>
        </div>
      </div>

      {perseveranceGallery && (
        <div className="space-y-3">
          {perseveranceGallery.error ? (
            <div className="rounded-lg border border-amber-500/35 bg-amber-950/30 p-3 text-xs text-amber-200">
              {perseveranceGallery.error} · {perseveranceGallery.isolation_note}
            </div>
          ) : perseveranceGallery.images.length === 0 ? (
            <div className="text-xs text-slate-400">
              No Perseverance raw frames matched that filter ({perseveranceGallery.isolation_note}).
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {perseveranceGallery.images.map((img) => {
                const previewUrl = img.image_url_medium || img.image_url_large || img.image_url_full_res;
                return (
                  <div
                    key={img.imageid}
                    className="rounded-lg bg-[#0d111a] border border-[#1e2638] p-3 space-y-2 text-xs"
                  >
                    {previewUrl && (
                      <a href={img.image_url_full_res || previewUrl} target="_blank" rel="noreferrer">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={previewUrl}
                          alt={img.title || img.imageid}
                          className="w-full h-40 object-cover rounded border border-[#1e2638]"
                        />
                      </a>
                    )}
                    <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
                      <span className="text-amber-300 font-semibold">
                        Sol {img.sol} · {img.camera_instrument || "Camera N/A"}
                      </span>
                      <span className="text-slate-500">Jezero</span>
                    </div>
                    <div className="text-[11px] text-slate-200 line-clamp-2">
                      {img.title || img.imageid}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono truncate">
                      {img.date_taken_utc || "UTC unavailable"}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  </div>;
}
