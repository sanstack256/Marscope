"""
MARSCOPE Optical Image Feature & Texture Analyzer
Martian Surface Intelligence & Exploration System

Analyzes real orthorectified HiRISE imagery (e.g. PSP_009149_1750 / ESP_040770_1755)
within a requested geographic bounding box to derive:
- Image-quality metrics (valid coverage, dynamic range, local contrast)
- Sobel edge / lineament magnitude summary
- Local texture variance
- Candidate ridge and candidate dark-hollow detections

Every detected feature is explicitly labelled MARSCOPE_DERIVED with status
'candidate_requiring_interpretation' and never presented as a confirmed
geological discovery. Original ortho imagery remains unmodified.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
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
    candidate_type: str  # "candidate_ridge_or_bright_lineament" | "candidate_dark_hollow"
    latitude: float
    longitude_east: float
    score: float
    edge_magnitude_dn: float
    local_contrast_zscore: float
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED
    validation_state: str = "candidate_requiring_interpretation"
    disclaimer: str = "Automated optical candidate only; requires geological verification."


class OpticalAnalysisResponse(BaseModel):
    available: bool
    ortho_dataset_id: Optional[str] = None
    product_id: Optional[str] = None
    bounds: Dict[str, float]
    valid_coverage_fraction: float = 0.0
    mean_dn: Optional[float] = None
    std_dn: Optional[float] = None
    mean_sobel_edge_dn: Optional[float] = None
    texture_variance: Optional[float] = None
    candidates: List[OpticalCandidateFeature] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
    provenance_graph: Optional[ProvenanceDependencyGraph] = None


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
        patch = np.where(patch <= 0.0, np.nan, patch)

        valid = np.isfinite(patch)
        cov_frac = round(float(np.count_nonzero(valid)) / float(patch.size), 4)
        if np.count_nonzero(valid) < 64:
            return OpticalAnalysisResponse(
                available=False,
                ortho_dataset_id=ds.id,
                product_id=ds.product_id,
                bounds=bounds,
                valid_coverage_fraction=cov_frac,
                unavailable_reason="Insufficient valid optical pixels in requested bounds.",
            )

        vals = patch[valid]
        mean_dn = float(np.mean(vals))
        std_dn = max(1e-6, float(np.std(vals)))
        tex_var = float(np.var(vals))

        # 3x3 Sobel edge magnitude strictly where all 9 pixels are valid
        gx = (
            -patch[:-2, :-2] + patch[:-2, 2:]
            - 2.0 * patch[1:-1, :-2] + 2.0 * patch[1:-1, 2:]
            - patch[2:, :-2] + patch[2:, 2:]
        ) / 8.0
        gy = (
            patch[:-2, :-2] + 2.0 * patch[:-2, 1:-1] + patch[:-2, 2:]
            - patch[2:, :-2] - 2.0 * patch[2:, 1:-1] - patch[2:, 2:]
        ) / 8.0
        edge = np.sqrt(gx * gx + gy * gy)
        edge_valid = np.isfinite(edge)
        mean_edge = float(np.mean(edge[edge_valid])) if np.any(edge_valid) else 0.0
        edge_std = float(np.std(edge[edge_valid])) if np.any(edge_valid) else 1.0

        # Sample non-overlapping 16x16 blocks to identify top candidate ridges / dark hollows
        candidates: List[OpticalCandidateFeature] = []
        block = 16
        center_core = patch[1:-1, 1:-1]
        for br in range(0, center_core.shape[0] - block + 1, block):
            for bc in range(0, center_core.shape[1] - block + 1, block):
                sub_dn = center_core[br : br + block, bc : bc + block]
                sub_edge = edge[br : br + block, bc : bc + block]
                if np.count_nonzero(np.isfinite(sub_dn)) < (block * block) // 2:
                    continue
                if np.count_nonzero(np.isfinite(sub_edge)) < (block * block) // 2:
                    continue
                b_dn = float(np.nanmean(sub_dn))
                b_edge = float(np.nanmean(sub_edge))
                z_dn = (b_dn - mean_dn) / std_dn
                z_edge = (b_edge - mean_edge) / max(1e-6, edge_std)

                lat_c = max_lat - ((br + block * 0.5 + 1.0) / float(out_size)) * (max_lat - min_lat)
                lon_c = normalize_longitude_360(
                    min_lon + ((bc + block * 0.5 + 1.0) / float(out_size)) * (max_lon - min_lon)
                )

                if z_edge > 0.75 and z_dn > 0.45:
                    candidates.append(
                        OpticalCandidateFeature(
                            feature_id=f"opt_ridge_{br}_{bc}",
                            candidate_type="candidate_ridge_or_bright_lineament",
                            latitude=round(lat_c, 6),
                            longitude_east=round(lon_c, 6),
                            score=round(0.6 * z_edge + 0.4 * z_dn, 3),
                            edge_magnitude_dn=round(b_edge, 3),
                            local_contrast_zscore=round(z_dn, 3),
                        )
                    )
                elif z_dn < -1.15:
                    candidates.append(
                        OpticalCandidateFeature(
                            feature_id=f"opt_hollow_{br}_{bc}",
                            candidate_type="candidate_dark_hollow",
                            latitude=round(lat_c, 6),
                            longitude_east=round(lon_c, 6),
                            score=round(abs(z_dn), 3),
                            edge_magnitude_dn=round(b_edge, 3),
                            local_contrast_zscore=round(z_dn, 3),
                        )
                    )

        candidates.sort(key=lambda c: c.score, reverse=True)
        candidates = candidates[:max(1, min(50, int(max_candidates)))]

        res_m = float(ds.horizontal_resolution_meters or 0.25)
        graph = ProvenanceDependencyGraph(
            output_id=f"optical:{ds.id}:{min_lat:.4f}:{min_lon:.4f}",
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[ds.id],
            input_product_ids=[ds.product_id],
            input_variables=["orthorectified_dn_reflectance"],
            input_units=["DN (8-bit calibrated reflectance)"],
            input_crs="IAU2000:49900",
            input_resolution_m=res_m,
            method="3x3 Sobel gradient magnitude + block z-score contrast anomaly detection",
            algorithm_version="optical_candidate_v1",
            parameters={"sample_grid": out_size, "block_px": block},
            assumptions=[
                "Bright high-gradient patches are candidate ridges/lineaments only, not confirmed mineral veins.",
                "Low-DN patches are candidate dark hollows only, not confirmed pits or craters.",
            ],
            intermediate_steps=[
                ProvenanceStep(
                    step_id="step_ortho_read",
                    label="Read source HiRISE orthorectified image window",
                    classification=ScientificDataClassification.ARCHIVE_DERIVED,
                    input_ids=[ds.product_id],
                    method="Windowed raster read",
                    algorithm_version="rasterio_v1",
                    output_variable="dn_reflectance",
                    output_units="DN",
                    output_resolution_m=res_m,
                ),
                ProvenanceStep(
                    step_id="step_sobel_candidates",
                    label="Extract Sobel edge texture and contrast candidates",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=["step_ortho_read"],
                    method="3x3 Sobel + block contrast z-score",
                    algorithm_version="optical_candidate_v1",
                    output_variable="candidate_features",
                    output_units="dimensionless z-score",
                ),
            ],
            output_units="DN / z-score",
            uncertainty_method="descriptive_block_variance",
            validation_state="candidate_requiring_interpretation",
        )

        return OpticalAnalysisResponse(
            available=True,
            ortho_dataset_id=ds.id,
            product_id=ds.product_id,
            bounds=bounds,
            valid_coverage_fraction=cov_frac,
            mean_dn=round(mean_dn, 3),
            std_dn=round(std_dn, 3),
            mean_sobel_edge_dn=round(mean_edge, 3),
            texture_variance=round(tex_var, 3),
            candidates=candidates,
            provenance_graph=graph,
        )

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _run(vrt)
        return _run(src)
