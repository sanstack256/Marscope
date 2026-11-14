"""
MARSCOPE Optical Image Feature & Texture Analyzer
Martian Surface Intelligence & Exploration System

Analyzes real orthorectified HiRISE imagery (e.g. PSP_009149_1750 / ESP_040770_1755)
within a requested geographic bounding box to derive:
- Image-quality metrics (valid coverage, dynamic range, local contrast)
- Multi-scale Sobel edge / lineament continuity & texture variance
- Candidate taxonomy (linear_surface_feature, ridge_like_feature, dark_region,
  bright_region, shadow_candidate, depression_candidate, possible_boulder_feature,
  unclassified_anomaly)
- Deterministic candidate validation & false-positive rejection log

Every detected feature is explicitly labelled MARSCOPE_DERIVED with status
'candidate_requiring_interpretation' and never presented as a confirmed obstacle,
boulder, fissure, or geological discovery. Original ortho imagery remains unmodified.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from app.geospatial.crs import normalize_longitude_360
from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)
from app.terrain.mesh import MARS_GEOG_CRS, PAIRED_ORTHO_MAP


class OpticalCandidateFeature(BaseModel):
    feature_id: str
    candidate_type: str
    latitude: float
    longitude_east: float
    crop_bounds: Dict[str, float] = Field(default_factory=dict)
    score: float
    edge_magnitude_dn: float
    edge_continuity: float = 0.0
    local_contrast_zscore: float
    valid_pixel_fraction: float = 1.0
    area_pixels: int = 0
    estimated_diameter_px: Optional[float] = None
    estimated_diameter_m: Optional[float] = None
    boundary_completeness: float = 1.0
    image_quality_ok: bool = True
    native_pixel_scale_m: Optional[float] = None
    product_id: Optional[str] = None
    ortho_dataset_id: Optional[str] = None
    detection_method: str = "sobel_multiscale_block_contrast_v3"
    detector_version: str = "optical_candidate_v3"
    processing_parameters: Dict[str, Any] = Field(default_factory=dict)
    in_corridor: Optional[bool] = None
    distance_from_route_m: Optional[float] = None
    distance_from_corridor_m: Optional[float] = None
    nearest_segment_id: Optional[str] = None
    association_type: Optional[str] = None
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED
    validation_state: str = "candidate_requiring_interpretation"
    disclaimer: str = (
        "Automated 2D optical contrast candidate only; does not measure object height or volume "
        "and is not a confirmed boulder, obstacle, or geological hazard."
    )


def evaluate_rounded_feature_eligibility(
    *,
    native_pixel_scale_m: float,
    diameter_px: float,
    valid_pixel_fraction: float,
    local_contrast_zscore: float,
    image_std_dn: float,
    boundary_completeness: float,
) -> Dict[str, Any]:
    """
    Resolution-aware object-detection eligibility policy replacing single pixel-scale heuristics.
    Requires >= 4 px spatial object extent, complete footprint (>= 0.85), adequate contrast
    dynamic range (std_dn >= 4.0 and |z| >= 1.0), and fine spatial resolution (<= 0.5 m/px).
    """
    reasons: List[str] = []
    if native_pixel_scale_m > 0.5:
        reasons.append(f"pixel scale {native_pixel_scale_m:.2f} m/px > 0.50 m/px limit")
    if diameter_px < 4.0:
        reasons.append(f"object diameter {diameter_px:.1f} px < 4.0 px Nyquist discrimination minimum")
    if valid_pixel_fraction < 0.85 or boundary_completeness < 0.85:
        reasons.append("incomplete or clipped valid pixel footprint")
    if image_std_dn < 4.0 or abs(local_contrast_zscore) < 1.0:
        reasons.append("insufficient local image quality / dynamic contrast")
    return {
        "eligible": len(reasons) == 0,
        "reasons": reasons,
        "policy_version": "rounded_feature_eligibility_v1",
    }


class RejectedOpticalCandidate(BaseModel):
    feature_id: str
    latitude: float
    longitude_east: float
    rejection_reason: str
    valid_pixel_fraction: float
    local_contrast_zscore: float


class OpticalAnalysisResponse(BaseModel):
    available: bool
    ortho_dataset_id: Optional[str] = None
    product_id: Optional[str] = None
    native_pixel_scale_m: Optional[float] = None
    bounds: Dict[str, float]
    valid_coverage_fraction: float = 0.0
    mean_dn: Optional[float] = None
    std_dn: Optional[float] = None
    mean_sobel_edge_dn: Optional[float] = None
    texture_variance: Optional[float] = None
    candidates: List[OpticalCandidateFeature] = Field(default_factory=list)
    rejected_candidates: List[RejectedOpticalCandidate] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
    provenance_graph: Optional[ProvenanceDependencyGraph] = None


def analyze_optical_array(
    patch: np.ndarray,
    *,
    bounds: Dict[str, float],
    ortho_dataset_id: str,
    product_id: str,
    native_pixel_scale_m: float,
    max_candidates: int = 12,
    min_valid_fraction: float = 0.6,
) -> OpticalAnalysisResponse:
    """
    Pure deterministic optical feature extraction on a 2D calibrated reflectance array.
    Used both by real HiRISE raster analysis and deterministic synthetic unit fixtures.
    """
    out_h, out_w = patch.shape
    min_lat = bounds["min_lat"]
    max_lat = bounds["max_lat"]
    min_lon = bounds["min_lon"]
    max_lon = bounds["max_lon"]

    valid = np.isfinite(patch) & (patch > 0.0)
    cov_frac = round(float(np.count_nonzero(valid)) / float(max(1, patch.size)), 4)
    if np.count_nonzero(valid) < 64 or out_h < 18 or out_w < 18:
        return OpticalAnalysisResponse(
            available=False,
            ortho_dataset_id=ortho_dataset_id,
            product_id=product_id,
            native_pixel_scale_m=native_pixel_scale_m,
            bounds=bounds,
            valid_coverage_fraction=cov_frac,
            unavailable_reason="Insufficient valid optical pixels in requested bounds.",
        )

    clean = np.where(valid, patch.astype(np.float64), np.nan)
    vals = clean[valid]
    mean_dn = float(np.mean(vals))
    std_dn = max(1e-6, float(np.std(vals)))
    tex_var = float(np.var(vals))

    # 3x3 Sobel edge magnitude strictly where all 9 pixels are valid
    gx = (
        -clean[:-2, :-2]
        + clean[:-2, 2:]
        - 2.0 * clean[1:-1, :-2]
        + 2.0 * clean[1:-1, 2:]
        - clean[2:, :-2]
        + clean[2:, 2:]
    ) / 8.0
    gy = (
        clean[:-2, :-2]
        + 2.0 * clean[:-2, 1:-1]
        + clean[:-2, 2:]
        - clean[2:, :-2]
        - 2.0 * clean[2:, 1:-1]
        - clean[2:, 2:]
    ) / 8.0
    edge = np.sqrt(gx * gx + gy * gy)
    edge_valid = np.isfinite(edge)
    mean_edge = float(np.mean(edge[edge_valid])) if np.any(edge_valid) else 0.0
    edge_std = max(1e-6, float(np.std(edge[edge_valid])) if np.any(edge_valid) else 1.0)
    edge_hi_thresh = mean_edge + 0.75 * edge_std

    candidates: List[OpticalCandidateFeature] = []
    rejected: List[RejectedOpticalCandidate] = []
    block = 16
    center_core = clean[1:-1, 1:-1]
    image_quality_ok = bool(std_dn >= 4.0)

    for br in range(0, center_core.shape[0] - block + 1, block):
        for bc in range(0, center_core.shape[1] - block + 1, block):
            sub_dn = center_core[br : br + block, bc : bc + block]
            sub_edge = edge[br : br + block, bc : bc + block]
            sub_valid_frac = float(np.count_nonzero(np.isfinite(sub_dn))) / float(block * block)
            sub_edge_frac = float(np.count_nonzero(np.isfinite(sub_edge))) / float(block * block)
            boundary_complete = min(sub_valid_frac, sub_edge_frac)
            anomaly_px = int(
                np.count_nonzero(
                    np.where(np.isfinite(sub_dn), np.abs(sub_dn - mean_dn) >= 1.25 * std_dn, False)
                )
            )
            est_diam_px = round(2.0 * math.sqrt(max(0, anomaly_px) / math.pi), 2)
            est_diam_m = round(est_diam_px * native_pixel_scale_m, 2) if native_pixel_scale_m > 0 else None

            lat_top = max_lat - ((br + 1.0) / float(out_h)) * (max_lat - min_lat)
            lat_bot = max_lat - ((br + block + 1.0) / float(out_h)) * (max_lat - min_lat)
            lon_left = normalize_longitude_360(min_lon + ((bc + 1.0) / float(out_w)) * (max_lon - min_lon))
            lon_right = normalize_longitude_360(
                min_lon + ((bc + block + 1.0) / float(out_w)) * (max_lon - min_lon)
            )
            lat_c = round(0.5 * (lat_top + lat_bot), 6)
            lon_c = round(0.5 * (lon_left + lon_right), 6)

            if sub_valid_frac < min_valid_fraction or sub_edge_frac < min_valid_fraction:
                if sub_valid_frac > 0.05:
                    rejected.append(
                        RejectedOpticalCandidate(
                            feature_id=f"opt_rej_{br}_{bc}",
                            latitude=lat_c,
                            longitude_east=lon_c,
                            rejection_reason=f"Insufficient valid spatial support ({sub_valid_frac:.2f} < {min_valid_fraction:.2f}) or clipped by no-data.",
                            valid_pixel_fraction=round(sub_valid_frac, 3),
                            local_contrast_zscore=0.0,
                        )
                    )
                continue

            b_dn = float(np.nanmean(sub_dn))
            b_edge = float(np.nanmean(sub_edge))
            z_dn = (b_dn - mean_dn) / std_dn
            z_edge = (b_edge - mean_edge) / edge_std
            edge_cont = float(np.count_nonzero(np.where(np.isfinite(sub_edge), sub_edge > edge_hi_thresh, False))) / float(
                max(1, np.count_nonzero(np.isfinite(sub_edge)))
            )

            rounded_elig = evaluate_rounded_feature_eligibility(
                native_pixel_scale_m=native_pixel_scale_m,
                diameter_px=est_diam_px,
                valid_pixel_fraction=sub_valid_frac,
                local_contrast_zscore=z_dn,
                image_std_dn=std_dn,
                boundary_completeness=boundary_complete,
            )

            # Classify into disciplined optical taxonomy
            ctype: Optional[str] = None
            if z_edge > 0.85 and edge_cont >= 0.25:
                ctype = "linear_surface_feature" if z_dn <= 0.45 else "ridge_like_feature"
            elif z_dn < -1.25:
                ctype = "shadow_candidate" if edge_cont >= 0.15 else "dark_region"
            elif z_dn > 1.35:
                ctype = "candidate_rounded_feature" if rounded_elig["eligible"] else "bright_region"
            elif z_edge > 1.25 and rounded_elig["eligible"]:
                ctype = "candidate_rounded_feature"

            if ctype is None:
                continue

            if abs(z_dn) < 0.25 and edge_cont < 0.2:
                rejected.append(
                    RejectedOpticalCandidate(
                        feature_id=f"opt_rej_{br}_{bc}",
                        latitude=lat_c,
                        longitude_east=lon_c,
                        rejection_reason="Failed local contrast and edge continuity false-positive gate.",
                        valid_pixel_fraction=round(sub_valid_frac, 3),
                        local_contrast_zscore=round(z_dn, 3),
                    )
                )
                continue

            candidates.append(
                OpticalCandidateFeature(
                    feature_id=f"opt_{ctype[:6]}_{br}_{bc}",
                    candidate_type=ctype,
                    latitude=lat_c,
                    longitude_east=lon_c,
                    crop_bounds={
                        "min_lat": round(lat_bot, 7),
                        "max_lat": round(lat_top, 7),
                        "min_lon": round(lon_left, 7),
                        "max_lon": round(lon_right, 7),
                    },
                    score=round(0.55 * max(0.0, z_edge) + 0.45 * abs(z_dn), 3),
                    edge_magnitude_dn=round(b_edge, 3),
                    edge_continuity=round(edge_cont, 3),
                    local_contrast_zscore=round(z_dn, 3),
                    valid_pixel_fraction=round(sub_valid_frac, 3),
                    area_pixels=anomaly_px if anomaly_px > 0 else int(round(sub_valid_frac * block * block)),
                    estimated_diameter_px=est_diam_px,
                    estimated_diameter_m=est_diam_m,
                    boundary_completeness=round(boundary_complete, 3),
                    image_quality_ok=image_quality_ok,
                    native_pixel_scale_m=round(native_pixel_scale_m, 3),
                    product_id=product_id,
                    ortho_dataset_id=ortho_dataset_id,
                    processing_parameters={
                        "sample_grid": [out_h, out_w],
                        "block_px": block,
                        "min_valid_fraction": min_valid_fraction,
                        "rounded_feature_eligibility": rounded_elig,
                    },
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    candidates = candidates[: max(1, min(50, int(max_candidates)))]
    rejected = rejected[:25]

    graph = ProvenanceDependencyGraph(
        output_id=f"optical:{ortho_dataset_id}:{min_lat:.4f}:{min_lon:.4f}",
        classification=ScientificDataClassification.MARSCOPE_DERIVED,
        input_datasets=[ortho_dataset_id],
        input_product_ids=[product_id],
        input_variables=["orthorectified_dn_reflectance"],
        input_units=["DN (8-bit calibrated reflectance)"],
        input_crs="IAU2000:49900",
        input_resolution_m=round(native_pixel_scale_m, 3),
        method="3x3 Sobel gradient magnitude + edge continuity + block contrast z-score + rounded feature eligibility + FP gate",
        algorithm_version="optical_candidate_v3",
        parameters={"sample_grid": [out_h, out_w], "block_px": block, "min_valid_fraction": min_valid_fraction},
        assumptions=[
            "Visual contrast or edge continuity alone never confirms a boulder, fissure, cave, or unstable slope.",
            "Original source reflectance pixels are preserved unmodified.",
        ],
        intermediate_steps=[
            ProvenanceStep(
                step_id="step_ortho_read",
                label="Read source orthorectified image window",
                classification=ScientificDataClassification.ARCHIVE_DERIVED,
                input_ids=[product_id],
                method="Windowed raster read",
                algorithm_version="rasterio_v1",
                output_variable="dn_reflectance",
                output_units="DN",
                output_resolution_m=round(native_pixel_scale_m, 3),
            ),
            ProvenanceStep(
                step_id="step_sobel_candidates",
                label="Extract Sobel edge continuity, contrast candidates, and FP rejections",
                classification=ScientificDataClassification.MARSCOPE_DERIVED,
                input_ids=["step_ortho_read"],
                method="3x3 Sobel + block contrast z-score + deterministic validation",
                algorithm_version="optical_candidate_v2",
                output_variable="candidate_features",
                output_units="dimensionless z-score",
            ),
        ],
        output_units="DN / z-score",
        uncertainty_method="descriptive_block_variance_and_fp_gating",
        validation_state="candidate_requiring_interpretation",
    )

    return OpticalAnalysisResponse(
        available=True,
        ortho_dataset_id=ortho_dataset_id,
        product_id=product_id,
        native_pixel_scale_m=round(native_pixel_scale_m, 3),
        bounds=bounds,
        valid_coverage_fraction=cov_frac,
        mean_dn=round(mean_dn, 3),
        std_dn=round(std_dn, 3),
        mean_sobel_edge_dn=round(mean_edge, 3),
        texture_variance=round(tex_var, 3),
        candidates=candidates,
        rejected_candidates=rejected,
        provenance_graph=graph,
    )


def analyze_optical_region(
    *,
    catalog_service: DatasetCatalogService,
    raw_dir: Path,
    dataset_id: str,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    max_candidates: int = 12,
) -> OpticalAnalysisResponse:
    """Analyze real HiRISE orthorectified imagery in the given bounds."""
    bounds = {
        "min_lat": float(min_lat),
        "max_lat": float(max_lat),
        "min_lon": float(min_lon),
        "max_lon": float(max_lon),
    }
    if min_lat >= max_lat or min_lon >= max_lon:
        return OpticalAnalysisResponse(
            available=False,
            bounds=bounds,
            unavailable_reason="Invalid bounding box: min_lat < max_lat and min_lon < max_lon required.",
        )

    ortho_id = PAIRED_ORTHO_MAP.get(dataset_id, dataset_id)
    ds = catalog_service.get_dataset(ortho_id)
    if not ds:
        return OpticalAnalysisResponse(
            available=False,
            ortho_dataset_id=ortho_id,
            bounds=bounds,
            unavailable_reason=f"Optical dataset '{ortho_id}' not found in catalog.",
        )

    open_path, _ = _resolve_raw_dem_open_path(ds, raw_dir)
    if not open_path.exists():
        return OpticalAnalysisResponse(
            available=False,
            ortho_dataset_id=ds.id,
            product_id=ds.product_id,
            bounds=bounds,
            unavailable_reason=f"Optical raster file missing locally for '{ds.id}'.",
        )

    def _run(reader: Any) -> OpticalAnalysisResponse:
        rb = reader.bounds
        q_min_lon = min_lon + 360.0 if (rb.right > 180.0 and min_lon < 0.0) else min_lon
        q_max_lon = max_lon + 360.0 if (rb.right > 180.0 and max_lon < 0.0) else max_lon
        if q_max_lon <= rb.left or q_min_lon >= rb.right or max_lat <= rb.bottom or min_lat >= rb.top:
            return OpticalAnalysisResponse(
                available=False,
                ortho_dataset_id=ds.id,
                product_id=ds.product_id,
                bounds=bounds,
                unavailable_reason="Requested bounds do not overlap optical image footprint.",
            )

        inv_t = ~reader.transform
        c0_f = inv_t.a * q_min_lon + inv_t.b * min_lat + inv_t.c
        r1_f = inv_t.d * q_min_lon + inv_t.e * min_lat + inv_t.f
        c1_f = inv_t.a * q_max_lon + inv_t.b * max_lat + inv_t.c
        r0_f = inv_t.d * q_max_lon + inv_t.e * max_lat + inv_t.f

        c0 = max(0, int(math.floor(min(c0_f, c1_f))))
        c1 = min(reader.width, int(math.ceil(max(c0_f, c1_f))))
        r0 = max(0, int(math.floor(min(r0_f, r1_f))))
        r1 = min(reader.height, int(math.ceil(max(r0_f, r1_f))))
        if c0 >= c1 or r0 >= r1:
            return OpticalAnalysisResponse(
                available=False,
                ortho_dataset_id=ds.id,
                product_id=ds.product_id,
                bounds=bounds,
                unavailable_reason="Requested bounds fall outside optical raster pixels.",
            )

        out_size = 256
        win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        patch = reader.read(
            1,
            window=win,
            out_shape=(out_size, out_size),
            resampling=Resampling.bilinear,
        ).astype(np.float64)
        if reader.nodata is not None:
            patch = np.where(patch == float(reader.nodata), np.nan, patch)

        res_m = float(ds.horizontal_resolution_meters or 0.25)
        return analyze_optical_array(
            patch,
            bounds=bounds,
            ortho_dataset_id=ds.id,
            product_id=ds.product_id,
            native_pixel_scale_m=res_m,
            max_candidates=max_candidates,
        )

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _run(vrt)
        return _run(src)


def render_optical_derived_crop_png(
    *,
    catalog_service: DatasetCatalogService,
    raw_dir: Path,
    dataset_id: str,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    size: int = 192,
) -> bytes:
    """Render a derived Sobel-edge visualization crop PNG (marked derived, never overwriting source)."""
    ortho_id = PAIRED_ORTHO_MAP.get(dataset_id, dataset_id)
    ds = catalog_service.get_dataset(ortho_id)
    if not ds:
        raise FileNotFoundError(f"Optical dataset '{ortho_id}' not found.")
    open_path, _ = _resolve_raw_dem_open_path(ds, raw_dir)
    if not open_path.exists():
        raise FileNotFoundError(f"Optical raster file missing locally for '{ds.id}'.")

    size = max(64, min(512, int(size)))

    def _render(reader: Any) -> bytes:
        rb = reader.bounds
        q_min_lon = min_lon + 360.0 if (rb.right > 180.0 and min_lon < 0.0) else min_lon
        q_max_lon = max_lon + 360.0 if (rb.right > 180.0 and max_lon < 0.0) else max_lon
        rgba = np.zeros((size, size, 4), dtype=np.uint8)
        if q_max_lon <= rb.left or q_min_lon >= rb.right or max_lat <= rb.bottom or min_lat >= rb.top:
            buf = io.BytesIO()
            Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
            return buf.getvalue()

        inv_t = ~reader.transform
        c0 = max(0, int(math.floor(inv_t.a * q_min_lon + inv_t.b * min_lat + inv_t.c)))
        r1 = min(reader.height, int(math.ceil(inv_t.d * q_min_lon + inv_t.e * min_lat + inv_t.f)))
        c1 = min(reader.width, int(math.ceil(inv_t.a * q_max_lon + inv_t.b * max_lat + inv_t.c)))
        r0 = max(0, int(math.floor(inv_t.d * q_max_lon + inv_t.e * max_lat + inv_t.f)))
        if c0 < c1 and r0 < r1:
            win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
            patch = reader.read(1, window=win, out_shape=(size, size), resampling=Resampling.bilinear).astype(
                np.float64
            )
            if reader.nodata is not None:
                patch = np.where(patch == float(reader.nodata), np.nan, patch)
            patch = np.where(patch <= 0.0, np.nan, patch)
            gx = np.zeros_like(patch)
            gy = np.zeros_like(patch)
            gx[1:-1, 1:-1] = (patch[1:-1, 2:] - patch[1:-1, :-2]) * 0.5
            gy[1:-1, 1:-1] = (patch[2:, 1:-1] - patch[:-2, 1:-1]) * 0.5
            mag = np.sqrt(gx * gx + gy * gy)
            fin = np.isfinite(mag)
            if np.any(fin):
                vmax = max(1.0, float(np.nanpercentile(mag[fin], 98)))
                norm = np.clip(np.where(fin, mag / vmax, 0.0), 0.0, 1.0)
                rgba[..., 0] = np.clip(30 + norm * 225, 0, 255).astype(np.uint8)
                rgba[..., 1] = np.clip(60 + norm * 165, 0, 255).astype(np.uint8)
                rgba[..., 2] = np.clip(110 + norm * 145, 0, 255).astype(np.uint8)
                rgba[..., 3] = np.where(fin, 255, 0).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
        return buf.getvalue()

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _render(vrt)
        return _render(src)
