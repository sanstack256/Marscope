"""
MARSCOPE Geological Morphology Candidate Detection & Human Review Engine (Prompt 19 Part 7).

Extracts scale-gated, NoData-border-hardened geological morphology candidates across:
- High-resolution stereo topography (HiRISE DTMs -> TPI ridges, networks, troughs,
  scarps, knobs, depressions, crater rims, channels, fans, talus aprons)
- Calibrated orbital orthorectified imagery (HiRISE 0.25 m/px ortho -> linear
  lineaments, layering/bedding bands, outcrop boundaries, aeolian bedforms,
  and strictly resolution-gated boulders <= 0.35 m/px)

Strict scientific guardrails:
- Enforces 2-pixel interior valid-mask erosion so oblique swath/NoData borders NEVER
  create false-positive edges, scarps, or ridge networks.
- Refuses sub-resolution boulder detection on >= 1 m/px DTMs or coarse MOLA products.
- Never promotes morphological resemblance (e.g. polygonal ridge networks) to
  confirmed mineralogy or boxwork diagenesis without independent spectroscopic/in-situ
  measurement evidence.
- Persists human expert review actions (accept / reject / annotate) strictly tagged as
  'USER_PROVIDED' metadata rather than instrument measurements.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.geospatial.models import (
    MorphologyEpistemicState,
    MorphologyFeatureClass,
)
from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.schemas.dataset import Dataset
from app.science.provenance_graph import ScientificDataClassification
from app.terrain.mesh import MARS_GEOG_CRS
from app.terrain.optical_analysis import PAIRED_ORTHO_MAP
from app.terrain.slope import calculate_slope

MORPHOLOGY_ENGINE_VERSION = "mars_morphology_v2.0"
BOULDER_MAX_RESOLUTION_M = 0.35
RIDGE_MIN_RESOLUTION_M = 2.0
BEDFORM_MAX_RESOLUTION_M = 1.5
NODATA_BORDER_GUARD_PX = 2


class MorphologyReviewRecord(BaseModel):
    candidate_id: str
    dataset_id: str
    action: str  # accept | reject | annotate
    reviewer_id: str
    reviewed_at_utc: str
    updated_epistemic_state: MorphologyEpistemicState
    classification: str = "USER_PROVIDED"
    origin_note: str = (
        "USER_PROVIDED expert review annotation — NOT an orbital or in-situ instrument measurement."
    )
    annotation_note: Optional[str] = None
    assigned_feature_class: Optional[MorphologyFeatureClass] = None


class MorphologicalFeatureCandidate(BaseModel):
    candidate_id: str
    feature_class: MorphologyFeatureClass
    epistemic_state: MorphologyEpistemicState
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED
    source_dataset_ids: List[str] = Field(default_factory=list)
    source_product_ids: List[str] = Field(default_factory=list)
    supporting_evidence_modalities: List[str] = Field(default_factory=list)
    centroid_lat: float
    centroid_lon_east: float
    bounds: Dict[str, float]
    geometry_geojson: Dict[str, Any]
    measurable_geometry: Dict[str, Optional[float]] = Field(default_factory=dict)
    min_required_resolution_m: float
    observed_resolution_m: float
    detection_method: str
    descriptive_summary: str
    geological_interpretation_warning: str = (
        "Morphological pattern only. Does NOT confirm mineral composition, boxwork diagenesis, "
        "or subsurface composition without independent spectroscopic/in-situ evidence."
    )
    nodata_border_rejected: bool = False
    rejection_reason: Optional[str] = None
    review_status: str = "pending"
    human_review: Optional[MorphologyReviewRecord] = None


class ResolutionGatedFeatureClassNotice(BaseModel):
    feature_class: MorphologyFeatureClass
    detectable: bool
    required_max_resolution_m: float
    available_resolution_m: Optional[float] = None
    reason: str


class MorphologyDetectionResponse(BaseModel):
    dataset_id: str
    ortho_dataset_id: Optional[str] = None
    bounds: Dict[str, float]
    engine_version: str = MORPHOLOGY_ENGINE_VERSION
    dem_resolution_m: Optional[float] = None
    ortho_resolution_m: Optional[float] = None
    valid_dem_coverage_fraction: float = 0.0
    valid_ortho_coverage_fraction: float = 0.0
    nodata_border_guard_px: int = NODATA_BORDER_GUARD_PX
    candidates: List[MorphologicalFeatureCandidate] = Field(default_factory=list)
    rejected_nodata_border_candidates: List[MorphologicalFeatureCandidate] = Field(default_factory=list)
    resolution_gating: List[ResolutionGatedFeatureClassNotice] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    persisted_review_count: int = 0


def _erode_valid_mask(mask: np.ndarray, radius_px: int) -> np.ndarray:
    """Return boolean mask keeping only pixels >= radius_px away from any False/edge cell."""
    if radius_px <= 0:
        return mask.copy()
    h, w = mask.shape
    if h <= 2 * radius_px or w <= 2 * radius_px:
        return np.zeros_like(mask, dtype=bool)
    out = np.zeros_like(mask, dtype=bool)
    acc = mask[radius_px : h - radius_px, radius_px : w - radius_px].copy()
    for dr in range(-radius_px, radius_px + 1):
        for dc in range(-radius_px, radius_px + 1):
            r0 = radius_px + dr
            r1 = h - radius_px + dr
            c0 = radius_px + dc
            c1 = w - radius_px + dc
            acc &= mask[r0:r1, c0:c1]
    out[radius_px : h - radius_px, radius_px : w - radius_px] = acc
    return out


def _connected_components(binary: np.ndarray, min_pixels: int = 4) -> List[List[Tuple[int, int]]]:
    """8-connected deterministic component extractor without external SciPy dependency."""
    h, w = binary.shape
    visited = np.zeros((h, w), dtype=bool)
    components: List[List[Tuple[int, int]]] = []
    for r in range(h):
        for c in range(w):
            if not binary[r, c] or visited[r, c]:
                continue
            stack = [(r, c)]
            visited[r, c] = True
            comp: List[Tuple[int, int]] = []
            while stack:
                cr, cc = stack.pop()
                comp.append((cr, cc))
                for nr in range(max(0, cr - 1), min(h, cr + 2)):
                    for nc in range(max(0, cc - 1), min(w, cc + 2)):
                        if not visited[nr, nc] and binary[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))
            if len(comp) >= min_pixels:
                components.append(comp)
    components.sort(key=lambda pts: -len(pts))
    return components


def _component_geometry(
    pts: List[Tuple[int, int]],
    *,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    rows: int,
    cols: int,
    grid_lat_m: float,
    grid_lon_m: float,
) -> Dict[str, Any]:
    rs = np.array([p[0] for p in pts], dtype=np.float64)
    cs = np.array([p[1] for p in pts], dtype=np.float64)
    mean_r = float(np.mean(rs))
    mean_c = float(np.mean(cs))

    # Row 0 is max_lat, row rows-1 is min_lat
    c_lat = max_lat - ((mean_r + 0.5) / float(rows)) * (max_lat - min_lat)
    c_lon = min_lon + ((mean_c + 0.5) / float(cols)) * (max_lon - min_lon)

    b_max_lat = max_lat - (float(np.min(rs)) / float(rows)) * (max_lat - min_lat)
    b_min_lat = max_lat - ((float(np.max(rs)) + 1.0) / float(rows)) * (max_lat - min_lat)
    b_min_lon = min_lon + (float(np.min(cs)) / float(cols)) * (max_lon - min_lon)
    b_max_lon = min_lon + ((float(np.max(cs)) + 1.0) / float(cols)) * (max_lon - min_lon)

    # PCA for major/minor axis & orientation in meters
    x_m = (cs - mean_c) * grid_lon_m
    y_m = (mean_r - rs) * grid_lat_m  # +y north
    if len(pts) >= 3:
        cov = np.cov(np.vstack([x_m, y_m]))
        eigvals, eigvecs = np.linalg.eigh(cov)
        idx = int(np.argmax(eigvals))
        major_std = math.sqrt(max(1e-9, float(eigvals[idx])))
        minor_std = math.sqrt(max(1e-9, float(eigvals[1 - idx])))
        vec = eigvecs[:, idx]
        az_rad = math.atan2(float(vec[0]), float(vec[1]))
        orient_deg = (math.degrees(az_rad) + 180.0) % 180.0
        length_m = max(grid_lon_m, 4.0 * major_std)
        width_m = max(grid_lon_m, 4.0 * minor_std)
    else:
        orient_deg = 0.0
        length_m = max(grid_lon_m, grid_lat_m)
        width_m = min(grid_lon_m, grid_lat_m)

    aspect_ratio = length_m / max(0.25, width_m)
    area_m2 = len(pts) * grid_lon_m * grid_lat_m

    poly = {
        "type": "Polygon",
        "coordinates": [
            [
                [round(b_min_lon, 7), round(b_min_lat, 7)],
                [round(b_max_lon, 7), round(b_min_lat, 7)],
                [round(b_max_lon, 7), round(b_max_lat, 7)],
                [round(b_min_lon, 7), round(b_max_lat, 7)],
                [round(b_min_lon, 7), round(b_min_lat, 7)],
            ]
        ],
    }

    return {
        "centroid_lat": round(c_lat, 7),
        "centroid_lon_east": round(c_lon, 7),
        "bounds": {
            "min_lat": round(b_min_lat, 7),
            "max_lat": round(b_max_lat, 7),
            "min_lon": round(b_min_lon, 7),
            "max_lon": round(b_max_lon, 7),
        },
        "geometry_geojson": poly,
        "length_m": round(length_m, 2),
        "width_m": round(width_m, 2),
        "aspect_ratio": round(aspect_ratio, 2),
        "orientation_deg": round(orient_deg, 1),
        "area_m2": round(area_m2, 2),
    }


def _candidate_id(dataset_id: str, feature_class: MorphologyFeatureClass, clat: float, clon: float) -> str:
    raw = f"{dataset_id}|{feature_class.value}|{clat:.5f}|{clon:.5f}"
    return "morph_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _read_aligned_window(
    ds: Dataset,
    raw_dir: Path,
    *,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    out_shape: Tuple[int, int],
    is_optical: bool = False,
) -> Optional[np.ndarray]:
    from rasterio.warp import reproject

    try:
        open_path, _ = _resolve_raw_dem_open_path(ds, raw_dir)
    except FileNotFoundError:
        return None
    if not open_path.exists():
        return None

    with rasterio.open(open_path) as src:
        projected = bool(src.crs and src.crs.is_projected)
        dst_crs = MARS_GEOG_CRS if projected else src.crs
        if projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                rb = vrt.bounds
        else:
            rb = src.bounds

        q_min_lon = min_lon + 360.0 if (rb.right > 180.0 and min_lon < 0.0) else min_lon
        q_max_lon = max_lon + 360.0 if (rb.right > 180.0 and max_lon < 0.0) else max_lon
        if q_max_lon <= rb.left or q_min_lon >= rb.right or max_lat <= rb.bottom or min_lat >= rb.top:
            return None

        out_h, out_w = out_shape
        dst_tf = rasterio.transform.from_bounds(q_min_lon, min_lat, q_max_lon, max_lat, out_w, out_h)
        arr = np.full((out_h, out_w), np.nan, dtype=np.float64)
        src_nd = src.nodata
        if src_nd is None and not is_optical:
            src_nd = -3.4028226550889045e38
        reproject(
            source=rasterio.band(src, 1),
            destination=arr,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nd,
            dst_transform=dst_tf,
            dst_crs=dst_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        if is_optical:
            arr = np.where(arr <= 0.0, np.nan, arr)
        else:
            arr = np.where(arr < -32000.0, np.nan, arr)
        return arr


class MorphologyReviewStore:
    """Atomic JSON persistence for human review records tagged strictly USER_PROVIDED."""

    def __init__(self, reviews_file: Path) -> None:
        self.reviews_file = reviews_file

    def load_all(self) -> Dict[str, MorphologyReviewRecord]:
        if not self.reviews_file.exists():
            return {}
        try:
            payload = json.loads(self.reviews_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        items = payload.get("reviews", {}) if isinstance(payload, dict) else {}
        out: Dict[str, MorphologyReviewRecord] = {}
        for cid, raw in items.items():
            try:
                out[cid] = MorphologyReviewRecord.model_validate(raw)
            except Exception:
                continue
        return out

    def save_review(self, record: MorphologyReviewRecord) -> MorphologyReviewRecord:
        existing = self.load_all()
        existing[record.candidate_id] = record
        self.reviews_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "classification": "USER_PROVIDED",
            "reviews": {k: v.model_dump() for k, v in existing.items()},
        }
        fd, tmp_name = tempfile.mkstemp(dir=str(self.reviews_file.parent), prefix=".morph_rev_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp_name, self.reviews_file)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
        return record


class GeologicalMorphologyService:
    """Part 7 scale-gated, NoData-hardened morphology detection & human review engine."""

    def __init__(self, catalog_service: DatasetCatalogService, raw_dir: Path, processed_dir: Path) -> None:
        self.catalog_service = catalog_service
        self.raw_dir = Path(raw_dir)
        self.review_store = MorphologyReviewStore(Path(processed_dir) / "morphology_reviews.json")

    def detect_candidates_from_arrays(
        self,
        *,
        dataset_id: str,
        product_id: str,
        dem_array: Optional[np.ndarray],
        dem_resolution_m: Optional[float],
        ortho_array: Optional[np.ndarray] = None,
        ortho_dataset_id: Optional[str] = None,
        ortho_product_id: Optional[str] = None,
        ortho_resolution_m: Optional[float] = None,
        bounds: Dict[str, float],
        max_candidates: int = 24,
        border_guard_px: int = NODATA_BORDER_GUARD_PX,
    ) -> MorphologyDetectionResponse:
        min_lat = float(bounds["min_lat"])
        max_lat = float(bounds["max_lat"])
        min_lon = float(bounds["min_lon"])
        max_lon = float(bounds["max_lon"])
        mean_lat_rad = math.radians(0.5 * (min_lat + max_lat))
        m_per_deg = (math.pi / 180.0) * MARS_EQUATORIAL_RADIUS_M

        ref_arr = dem_array if dem_array is not None else ortho_array
        if ref_arr is None:
            return MorphologyDetectionResponse(
                dataset_id=dataset_id,
                ortho_dataset_id=ortho_dataset_id,
                bounds=bounds,
                limitations=["Neither elevation DEM nor optical orthorectified array available in bounds."],
            )

        rows, cols = ref_arr.shape
        grid_lat_m = max(0.05, ((max_lat - min_lat) * m_per_deg) / max(1, rows))
        grid_lon_m = max(0.05, ((max_lon - min_lon) * m_per_deg * max(0.1, math.cos(mean_lat_rad))) / max(1, cols))

        dem_valid = np.isfinite(dem_array) & (dem_array > -32000.0) if dem_array is not None else np.zeros((rows, cols), dtype=bool)
        ortho_valid = np.isfinite(ortho_array) & (ortho_array > 0.0) if ortho_array is not None else np.zeros((rows, cols), dtype=bool)
        dem_cov = round(float(np.mean(dem_valid)), 4) if dem_array is not None else 0.0
        ortho_cov = round(float(np.mean(ortho_valid)), 4) if ortho_array is not None else 0.0

        dem_interior = _erode_valid_mask(dem_valid, border_guard_px)
        ortho_interior = _erode_valid_mask(ortho_valid, border_guard_px)

        reviews = self.review_store.load_all()
        accepted: List[MorphologicalFeatureCandidate] = []
        border_rejected: List[MorphologicalFeatureCandidate] = []
        limitations: List[str] = []
        gating: List[ResolutionGatedFeatureClassNotice] = []

        # Resolution gating ledger
        eff_res = min(
            [r for r in (dem_resolution_m, ortho_resolution_m) if r is not None and r > 0],
            default=9999.0,
        )
        boulder_ok = ortho_resolution_m is not None and ortho_resolution_m <= BOULDER_MAX_RESOLUTION_M and ortho_array is not None
        gating.append(
            ResolutionGatedFeatureClassNotice(
                feature_class=MorphologyFeatureClass.BOULDER,
                detectable=boulder_ok,
                required_max_resolution_m=BOULDER_MAX_RESOLUTION_M,
                available_resolution_m=ortho_resolution_m or dem_resolution_m,
                reason=(
                    f"Calibrated optical resolution ({ortho_resolution_m} m/px) satisfies <= {BOULDER_MAX_RESOLUTION_M} m/px gate."
                    if boulder_ok
                    else f"BOULDER detection blocked: available resolution ({ortho_resolution_m or dem_resolution_m} m/px) exceeds {BOULDER_MAX_RESOLUTION_M} m/px Nyquist threshold; meter-scale blocks unobservable on coarse grids."
                ),
            )
        )
        ridge_ok = dem_resolution_m is not None and dem_resolution_m <= RIDGE_MIN_RESOLUTION_M and dem_array is not None
        gating.append(
            ResolutionGatedFeatureClassNotice(
                feature_class=MorphologyFeatureClass.POLYGONAL_RIDGE_NETWORK,
                detectable=ridge_ok,
                required_max_resolution_m=RIDGE_MIN_RESOLUTION_M,
                available_resolution_m=dem_resolution_m,
                reason=(
                    f"DEM resolution ({dem_resolution_m} m/px) resolves decimeter/meter-scale ridge network patterns."
                    if ridge_ok
                    else f"Polygonal ridge network detection requires <= {RIDGE_MIN_RESOLUTION_M} m/px DEM; unavailable on coarse {dem_resolution_m} m/px grid."
                ),
            )
        )
        bedform_ok = ortho_resolution_m is not None and ortho_resolution_m <= BEDFORM_MAX_RESOLUTION_M and ortho_array is not None
        gating.append(
            ResolutionGatedFeatureClassNotice(
                feature_class=MorphologyFeatureClass.AEOLIAN_BEDFORM,
                detectable=bedform_ok,
                required_max_resolution_m=BEDFORM_MAX_RESOLUTION_M,
                available_resolution_m=ortho_resolution_m or dem_resolution_m,
                reason=(
                    f"Optical ortho ({ortho_resolution_m} m/px) meets <= {BEDFORM_MAX_RESOLUTION_M} m/px crest spacing resolution."
                    if bedform_ok
                    else "Aeolian bedform crest extraction skipped due to missing sub-1.5 m/px optical imagery."
                ),
            )
        )

        def _attach_review(cand: MorphologicalFeatureCandidate) -> MorphologicalFeatureCandidate:
            rev = reviews.get(cand.candidate_id)
            if rev is not None:
                cand.human_review = rev
                cand.epistemic_state = rev.updated_epistemic_state
                cand.review_status = (
                    "accepted"
                    if rev.action == "accept"
                    else "rejected"
                    if rev.action == "reject"
                    else "annotated"
                )
                if rev.assigned_feature_class is not None:
                    cand.feature_class = rev.assigned_feature_class
            return cand

        def _emit_components(
            raw_mask: np.ndarray,
            valid_mask: np.ndarray,
            interior_mask: np.ndarray,
            *,
            fclass: MorphologyFeatureClass,
            epistemic: MorphologyEpistemicState,
            min_px: int,
            max_px: Optional[int],
            min_ar: Optional[float],
            max_ar: Optional[float],
            req_res_m: float,
            obs_res_m: float,
            src_ids: List[str],
            prod_ids: List[str],
            modalities: List[str],
            method_desc: str,
            summary_tmpl: str,
            elev_arr: Optional[np.ndarray],
            slope_arr: Optional[np.ndarray],
            limit_n: int,
        ) -> None:
            # 1) Check raw detections that sit on the NoData/edge guard band -> record as explicit rejections
            masked_raw = raw_mask & valid_mask
            for pts in _connected_components(masked_raw, min_pixels=min_px):
                if max_px is not None and len(pts) > max_px:
                    continue
                touches_border = any(not interior_mask[r, c] for r, c in pts)
                geom = _component_geometry(
                    pts,
                    min_lat=min_lat,
                    max_lat=max_lat,
                    min_lon=min_lon,
                    max_lon=max_lon,
                    rows=rows,
                    cols=cols,
                    grid_lat_m=grid_lat_m,
                    grid_lon_m=grid_lon_m,
                )
                ar = float(geom["aspect_ratio"])
                if min_ar is not None and ar < min_ar:
                    continue
                if max_ar is not None and ar > max_ar:
                    continue

                relief_m: Optional[float] = None
                mean_slp: Optional[float] = None
                if elev_arr is not None:
                    vals = np.array([elev_arr[r, c] for r, c in pts], dtype=np.float64)
                    fin = vals[np.isfinite(vals)]
                    if fin.size > 0:
                        relief_m = round(float(np.max(fin) - np.min(fin)), 2)
                if slope_arr is not None:
                    svals = np.array([slope_arr[r, c] for r, c in pts], dtype=np.float64)
                    sfin = svals[np.isfinite(svals)]
                    if sfin.size > 0:
                        mean_slp = round(float(np.mean(sfin)), 2)

                cid = _candidate_id(src_ids[0], fclass, geom["centroid_lat"], geom["centroid_lon_east"])
                cand = MorphologicalFeatureCandidate(
                    candidate_id=cid,
                    feature_class=fclass,
                    epistemic_state=epistemic,
                    source_dataset_ids=src_ids,
                    source_product_ids=prod_ids,
                    supporting_evidence_modalities=modalities,
                    centroid_lat=geom["centroid_lat"],
                    centroid_lon_east=geom["centroid_lon_east"],
                    bounds=geom["bounds"],
                    geometry_geojson=geom["geometry_geojson"],
                    measurable_geometry={
                        "length_m": geom["length_m"],
                        "width_m": geom["width_m"],
                        "aspect_ratio": geom["aspect_ratio"],
                        "orientation_deg": geom["orientation_deg"],
                        "area_m2": geom["area_m2"],
                        "relief_m": relief_m,
                        "mean_slope_deg": mean_slp,
                    },
                    min_required_resolution_m=req_res_m,
                    observed_resolution_m=obs_res_m,
                    detection_method=method_desc,
                    descriptive_summary=summary_tmpl.format(
                        length_m=geom["length_m"],
                        width_m=geom["width_m"],
                        relief_m=relief_m if relief_m is not None else "n/a",
                        slope=mean_slp if mean_slp is not None else "n/a",
                        orient=geom["orientation_deg"],
                    ),
                    nodata_border_rejected=touches_border,
                    rejection_reason=(
                        f"Rejected candidate touching < {border_guard_px}-pixel NoData / swath border guard ring "
                        "(prevents oblique swath cutoffs from inducing false scarps/ridges)."
                        if touches_border
                        else None
                    ),
                )
                if touches_border:
                    if len(border_rejected) < 16:
                        border_rejected.append(cand)
                else:
                    if sum(1 for c in accepted if c.feature_class == fclass) < limit_n and len(accepted) < max_candidates:
                        accepted.append(_attach_review(cand))

        # --- TOPOGRAPHIC CANDIDATES (Requires DEM) ---
        if dem_array is not None and dem_resolution_m is not None:
            z = np.where(dem_valid, dem_array, np.nan)
            slope_arr = calculate_slope(z, grid_lon_m, grid_lat_m, nodata_mask=~dem_valid)[0]
            # Compute local 7x7 TPI without crossing NoData gaps
            tpi = np.full((rows, cols), np.nan, dtype=np.float64)
            r_rad = 3
            for r in range(r_rad, rows - r_rad):
                for c in range(r_rad, cols - r_rad):
                    sub = z[r - r_rad : r + r_rad + 1, c - r_rad : c + r_rad + 1]
                    if np.all(np.isfinite(sub)):
                        tpi[r, c] = z[r, c] - float(np.mean(sub))

            fin_tpi = tpi[np.isfinite(tpi)]
            if fin_tpi.size > 20 and dem_resolution_m <= 25.0:
                tpi_std = max(0.25, float(np.std(fin_tpi)))
                pos_ridge = np.isfinite(tpi) & (tpi >= max(0.45, 1.35 * tpi_std))
                neg_trough = np.isfinite(tpi) & (tpi <= -max(0.45, 1.35 * tpi_std))
                steep_scarp = np.isfinite(slope_arr) & (slope_arr >= 18.0)
                talus_band = np.isfinite(slope_arr) & (slope_arr >= 14.0) & (slope_arr < 24.0) & np.isfinite(tpi) & (tpi < 0.0)

                src_ids = [dataset_id]
                prod_ids = [product_id]
                mods = [f"topography_dtm_{dem_resolution_m}m"]

                # Intersecting / branched ridge network candidates (Part 7 polygonal ridge network)
                _emit_components(
                    pos_ridge,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.POLYGONAL_RIDGE_NETWORK,
                    epistemic=MorphologyEpistemicState.ALGORITHMIC_CANDIDATE,
                    min_px=12,
                    max_px=None,
                    min_ar=1.0,
                    max_ar=2.1,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Topographic Position Index (TPI > 1.35 sigma) non-linear/branched ridge cluster",
                    summary_tmpl="Interconnected elevated ridge network candidate ({length_m} x {width_m} m, relief ~{relief_m} m).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=3,
                )
                # Linear ridges
                _emit_components(
                    pos_ridge,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.LINEAR_RIDGE,
                    epistemic=MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
                    min_px=5,
                    max_px=None,
                    min_ar=2.15,
                    max_ar=None,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Topographic Position Index ridge crest PCA axis ratio >= 2.15",
                    summary_tmpl="Elongated positive topographic ridge (length ~{length_m} m, azimuth ~{orient} deg).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=4,
                )
                # Compact topographic knobs
                _emit_components(
                    pos_ridge,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.KNOB,
                    epistemic=MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
                    min_px=4,
                    max_px=11,
                    min_ar=1.0,
                    max_ar=1.9,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Compact positive TPI mound",
                    summary_tmpl="Isolated topographic knob/mound ({length_m} x {width_m} m, relief ~{relief_m} m).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=3,
                )
                # Elongated channels / fracture troughs
                _emit_components(
                    neg_trough,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.CHANNEL,
                    epistemic=MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
                    min_px=6,
                    max_px=None,
                    min_ar=2.3,
                    max_ar=None,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Negative TPI incised trough PCA axis ratio >= 2.3",
                    summary_tmpl="Incised elongated channel/trough candidate ({length_m} m, strike ~{orient} deg).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=3,
                )
                # Compact depressions
                _emit_components(
                    neg_trough,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.DEPRESSION,
                    epistemic=MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
                    min_px=5,
                    max_px=35,
                    min_ar=1.0,
                    max_ar=1.9,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Enclosed negative TPI basin",
                    summary_tmpl="Closed topographic depression ({length_m} x {width_m} m, depth ~{relief_m} m).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=3,
                )
                # Scarps
                _emit_components(
                    steep_scarp,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.SCARP,
                    epistemic=MorphologyEpistemicState.OBSERVED_TOPOGRAPHIC_PATTERN,
                    min_px=6,
                    max_px=None,
                    min_ar=2.0,
                    max_ar=None,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Sustained Horn slope >= 18 deg elongated scarp band",
                    summary_tmpl="Steep scarp face (length ~{length_m} m, mean slope {slope} deg).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=3,
                )
                # Talus-like apron deposits below scarps
                _emit_components(
                    talus_band,
                    dem_valid,
                    dem_interior,
                    fclass=MorphologyFeatureClass.TALUS_LIKE_DEPOSIT,
                    epistemic=MorphologyEpistemicState.ALGORITHMIC_CANDIDATE,
                    min_px=6,
                    max_px=80,
                    min_ar=1.1,
                    max_ar=3.5,
                    req_res_m=RIDGE_MIN_RESOLUTION_M,
                    obs_res_m=dem_resolution_m,
                    src_ids=src_ids,
                    prod_ids=prod_ids,
                    modalities=mods,
                    method_desc="Moderate debris apron slope (14-24 deg) below local crest (TPI < 0)",
                    summary_tmpl="Talus-like debris apron candidate ({length_m} x {width_m} m, mean slope {slope} deg).",
                    elev_arr=z,
                    slope_arr=slope_arr,
                    limit_n=2,
                )
            elif dem_resolution_m > 25.0:
                limitations.append(
                    f"DEM resolution ({dem_resolution_m} m/px) is too coarse for meter/decameter landform morphology extraction."
                )

        # --- OPTICAL ORTHO CANDIDATES (Requires <= 1.5 m/px ortho; boulders <= 0.35 m/px) ---
        if ortho_array is not None and ortho_resolution_m is not None:
            o_fin = ortho_array[ortho_valid]
            if o_fin.size > 40:
                mean_dn = float(np.mean(o_fin))
                std_dn = max(1.0, float(np.std(o_fin)))
                gx = np.zeros_like(ortho_array)
                gy = np.zeros_like(ortho_array)
                gx[1:-1, 1:-1] = (ortho_array[1:-1, 2:] - ortho_array[1:-1, :-2]) * 0.5
                gy[1:-1, 1:-1] = (ortho_array[2:, 1:-1] - ortho_array[:-2, 1:-1]) * 0.5
                mag = np.sqrt(gx * gx + gy * gy)
                # Mask only 1-px finite difference boundary with NaN neighbors so any spurious
                # edge sitting in the border guard band triggers rejected_nodata_border_candidates.
                mag_valid_1px = np.isfinite(mag) & ortho_valid
                mag[~mag_valid_1px] = np.nan
                m_fin = mag[np.isfinite(mag)]
                o_src = [ortho_dataset_id or dataset_id]
                o_prod = [ortho_product_id or product_id]
                o_mod = [f"optical_orthorectified_{ortho_resolution_m}m"]

                if m_fin.size > 20:
                    edge_thresh = float(np.percentile(m_fin, 90))
                    # Fracture-like lineaments from sharp elongated optical edges
                    _emit_components(
                        np.isfinite(mag) & (mag >= edge_thresh),
                        ortho_valid,
                        ortho_interior,
                        fclass=MorphologyFeatureClass.FRACTURE_LIKE_LINEAMENT,
                        epistemic=MorphologyEpistemicState.OBSERVED_IMAGE_PATTERN,
                        min_px=5,
                        max_px=None,
                        min_ar=2.6,
                        max_ar=None,
                        req_res_m=1.0,
                        obs_res_m=ortho_resolution_m,
                        src_ids=o_src,
                        prod_ids=o_prod,
                        modalities=o_mod,
                        method_desc="Optical Sobel edge gradient >= 90th pct PCA axis ratio >= 2.6",
                        summary_tmpl="Linear optical fracture/ridge lineament ({length_m} m, strike ~{orient} deg).",
                        elev_arr=None,
                        slope_arr=None,
                        limit_n=3,
                    )

                    # Bright tonal outcrop boundaries
                    bright_outcrop = ortho_valid & (ortho_array >= (mean_dn + 1.4 * std_dn))
                    _emit_components(
                        bright_outcrop,
                        ortho_valid,
                        ortho_interior,
                        fclass=MorphologyFeatureClass.OUTCROP_BOUNDARY,
                        epistemic=MorphologyEpistemicState.OBSERVED_IMAGE_PATTERN,
                        min_px=6,
                        max_px=60,
                        min_ar=1.2,
                        max_ar=3.5,
                        req_res_m=1.0,
                        obs_res_m=ortho_resolution_m,
                        src_ids=o_src,
                        prod_ids=o_prod,
                        modalities=o_mod,
                        method_desc="Calibrated ortho high-albedo coherent patch > +1.4 sigma",
                        summary_tmpl="High-reflectance exposed outcrop boundary candidate ({length_m} x {width_m} m).",
                        elev_arr=None,
                        slope_arr=None,
                        limit_n=2,
                    )

                if bedform_ok and m_fin.size > 20:
                    dark_ripple = ortho_valid & (ortho_array <= (mean_dn - 0.7 * std_dn)) & (mag >= float(np.percentile(m_fin, 65)))
                    _emit_components(
                        dark_ripple,
                        ortho_valid,
                        ortho_interior,
                        fclass=MorphologyFeatureClass.AEOLIAN_BEDFORM,
                        epistemic=MorphologyEpistemicState.OBSERVED_IMAGE_PATTERN,
                        min_px=6,
                        max_px=45,
                        min_ar=2.2,
                        max_ar=None,
                        req_res_m=BEDFORM_MAX_RESOLUTION_M,
                        obs_res_m=ortho_resolution_m,
                        src_ids=o_src,
                        prod_ids=o_prod,
                        modalities=o_mod,
                        method_desc="Low-albedo / crest-trough optical bedform stripe <= 1.5 m/px",
                        summary_tmpl="Elongated dark aeolian bedform / ripple crest pattern ({length_m} m, strike ~{orient} deg).",
                        elev_arr=None,
                        slope_arr=None,
                        limit_n=2,
                    )

                # Strictly resolution-gated BOULDER detection (<= 0.35 m/px only!)
                if boulder_ok:
                    # Compact bright sunward face / shadow contrast blocks strictly inside valid mask
                    boulder_mask = ortho_valid & (np.abs(ortho_array - mean_dn) >= 1.8 * std_dn) & np.isfinite(mag) & (mag >= float(np.percentile(m_fin, 85)) if m_fin.size > 0 else False)
                    _emit_components(
                        boulder_mask,
                        ortho_valid,
                        ortho_interior,
                        fclass=MorphologyFeatureClass.BOULDER,
                        epistemic=MorphologyEpistemicState.ALGORITHMIC_CANDIDATE,
                        min_px=2,
                        max_px=8,
                        min_ar=1.0,
                        max_ar=2.2,
                        req_res_m=BOULDER_MAX_RESOLUTION_M,
                        obs_res_m=ortho_resolution_m,
                        src_ids=o_src,
                        prod_ids=o_prod,
                        modalities=o_mod,
                        method_desc="Compact high-contrast edge/tone dipole on <= 0.35 m/px HiRISE ortho",
                        summary_tmpl="Compact high-contrast block / boulder candidate ({length_m} x {width_m} m; verify sun/shadow geometry).",
                        elev_arr=None,
                        slope_arr=None,
                        limit_n=3,
                    )

        return MorphologyDetectionResponse(
            dataset_id=dataset_id,
            ortho_dataset_id=ortho_dataset_id,
            bounds=bounds,
            dem_resolution_m=dem_resolution_m,
            ortho_resolution_m=ortho_resolution_m,
            valid_dem_coverage_fraction=dem_cov,
            valid_ortho_coverage_fraction=ortho_cov,
            nodata_border_guard_px=border_guard_px,
            candidates=accepted[:max_candidates],
            rejected_nodata_border_candidates=border_rejected,
            resolution_gating=gating,
            limitations=limitations,
            persisted_review_count=len(reviews),
        )

    def detect_candidates_in_region(
        self,
        *,
        dataset_id: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        grid_size: int = 128,
        max_candidates: int = 24,
    ) -> MorphologyDetectionResponse:
        if min_lat >= max_lat or min_lon >= max_lon:
            raise ValueError("Invalid bounding box: min_lat < max_lat and min_lon < max_lon required.")

        ds = self.catalog_service.get_dataset(dataset_id)
        if not ds:
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in catalog.")

        grid_size = max(32, min(192, int(grid_size)))
        bounds = {
            "min_lat": float(min_lat),
            "max_lat": float(max_lat),
            "min_lon": float(min_lon),
            "max_lon": float(max_lon),
        }

        ortho_id = PAIRED_ORTHO_MAP.get(dataset_id)
        ortho_ds = self.catalog_service.get_dataset(ortho_id) if ortho_id else None

        is_ds_optical = (ds.product_type or "").lower() in {"imagery", "orthorectified_imagery"} or "ortho" in ds.id.lower()
        dem_arr = (
            None
            if is_ds_optical
            else _read_aligned_window(
                ds, self.raw_dir, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, out_shape=(grid_size, grid_size), is_optical=False
            )
        )
        ortho_arr = None
        if is_ds_optical:
            ortho_arr = _read_aligned_window(
                ds, self.raw_dir, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, out_shape=(grid_size, grid_size), is_optical=True
            )
            ortho_ds = ds
        elif ortho_ds is not None:
            ortho_arr = _read_aligned_window(
                ortho_ds, self.raw_dir, min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon, out_shape=(grid_size, grid_size), is_optical=True
            )

        return self.detect_candidates_from_arrays(
            dataset_id=ds.id,
            product_id=ds.product_id,
            dem_array=dem_arr,
            dem_resolution_m=(None if is_ds_optical else ds.horizontal_resolution_meters),
            ortho_array=ortho_arr,
            ortho_dataset_id=(ortho_ds.id if ortho_ds else None),
            ortho_product_id=(ortho_ds.product_id if ortho_ds else None),
            ortho_resolution_m=(ortho_ds.horizontal_resolution_meters if ortho_ds else None),
            bounds=bounds,
            max_candidates=max_candidates,
        )

    def submit_human_review(
        self,
        *,
        candidate_id: str,
        dataset_id: str,
        action: str,
        reviewer_id: str,
        annotation_note: Optional[str] = None,
        assigned_feature_class: Optional[MorphologyFeatureClass] = None,
    ) -> MorphologyReviewRecord:
        act = action.strip().lower()
        if act not in {"accept", "reject", "annotate"}:
            raise ValueError(f"Invalid review action '{action}': expected accept, reject, or annotate.")
        if act in {"accept", "annotate"}:
            ep = MorphologyEpistemicState.EXPERT_INTERPRETATION
        else:
            ep = MorphologyEpistemicState.UNRESOLVED

        rec = MorphologyReviewRecord(
            candidate_id=candidate_id,
            dataset_id=dataset_id,
            action=act,
            reviewer_id=reviewer_id.strip() or "operator",
            reviewed_at_utc=datetime.now(timezone.utc).isoformat(),
            updated_epistemic_state=ep,
            classification="USER_PROVIDED",
            annotation_note=annotation_note,
            assigned_feature_class=assigned_feature_class,
        )
        return self.review_store.save_review(rec)
