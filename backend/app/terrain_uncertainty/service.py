"""
MARSCOPE Terrain Uncertainty Service
Provides catalog uncertainty profiles, bounded corridor analysis, point query propagation,
and transparent overlay PNG textures aligned to tile UV grids.
"""

from __future__ import annotations

from collections import OrderedDict
import io
import math
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
import rasterio
from rasterio.crs import CRS
from rasterio.vrt import WarpedVRT

from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path, is_dataset_asset_available
from app.schemas.dataset import Dataset
from app.terrain.mesh import DEFAULT_GALE_STUDY_BOUNDS, MARS_GEOG_CRS, PAIRED_ORTHO_MAP, TerrainMeshService
from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty
from app.terrain_uncertainty.models import UNCERTAINTY_MODEL_VERSION, UncertaintyStatus
from app.terrain_uncertainty.schemas import (
    CorridorUncertaintyProfile,
    DatasetUncertaintyProfile,
)
from app.terrain_uncertainty.uncertainty_propagation import evaluate_coupled_corridor_uncertainty


class TerrainUncertaintyService:
    """Service coordinating PDS3 uncertainty extraction, propagation, and texture rendering."""

    def __init__(self, catalog_service: DatasetCatalogService, raw_dir: Path, processed_dir: Path):
        self.catalog_service = catalog_service
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self._lock = threading.Lock()
        self._cache: "OrderedDict[str, object]" = OrderedDict()
        self._max_cache_items = 48

    def _cache_get(self, key: str) -> Optional[object]:
        with self._lock:
            val = self._cache.get(key)
            if val is not None:
                self._cache.move_to_end(key)
            return val

    def _cache_put(self, key: str, value: object) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_cache_items:
                self._cache.popitem(last=False)

    def _resolve_dem_dataset(self, dataset_id: Optional[str]) -> Dataset:
        if dataset_id:
            ds = self.catalog_service.get_dataset(dataset_id)
            if not ds:
                raise FileNotFoundError(f"Dataset '{dataset_id}' not found in catalog.")
            return ds
        for pref in ("hirise_dteec_009149_1750", "hirise_dteec_040770_1755", "mola_megt00n090hb"):
            ds = self.catalog_service.get_dataset(pref)
            if ds and ds.local_file_path:
                return ds
        for ds in self.catalog_service.list_datasets():
            if "DEM" in ds.product_type.upper():
                return ds
        raise FileNotFoundError("No DEM datasets registered in catalog.")

    def inspect_dataset_uncertainty(self, dataset_id: str) -> DatasetUncertaintyProfile:
        cache_key = f"ds_unc:{dataset_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]
        ds = self.catalog_service.get_dataset(dataset_id)
        if not ds:
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found in catalog.")
        prof = inspect_dataset_elevation_uncertainty(
            dataset=ds,
            raw_dir=self.raw_dir,
            processed_dir=self.processed_dir,
        )
        self._cache_put(cache_key, prof)
        return prof

    def _sample_corridor_window(
        self,
        *,
        dataset: Dataset,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        grid_size: int = 97,
    ) -> Tuple[np.ndarray, np.ndarray, float, float]:
        open_path, _lbl = _resolve_raw_dem_open_path(dataset, self.raw_dir)
        if not open_path.exists():
            raise FileNotFoundError(f"DEM raster not found locally for '{dataset.id}'.")

        grid_size = max(17, min(512, int(grid_size)))
        with rasterio.open(open_path) as src:
            nodata_val = float(src.nodata) if src.nodata is not None else -32768.0
            if src.crs and src.crs.is_projected:
                with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                    padded, dx_m, dy_m = TerrainMeshService._sample_dem_grid(
                        vrt, nodata_val, min_lat, max_lat, min_lon, max_lon, grid_size, grid_size
                    )
            else:
                padded, dx_m, dy_m = TerrainMeshService._sample_dem_grid(
                    src, nodata_val, min_lat, max_lat, min_lon, max_lon, grid_size, grid_size
                )

        elev = padded[1:-1, 1:-1]
        nodata_mask = ~np.isfinite(elev)
        return elev, nodata_mask, float(dx_m), float(dy_m)

    def _resolve_supporting_optical(
        self,
        dem_dataset: Dataset,
        optical_dataset_id: Optional[str],
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> Optional[Dataset]:
        cand_id = optical_dataset_id or PAIRED_ORTHO_MAP.get(dem_dataset.id)
        if not cand_id:
            return None
        opt_ds = self.catalog_service.get_dataset(cand_id)
        if not opt_ds or not is_dataset_asset_available(opt_ds, self.raw_dir):
            return None
        cov = opt_ds.coverage
        # Verify spatial intersection before claiming optical support
        o_min_lon = cov.min_longitude + 360.0 if (cov.min_longitude < 0 and min_lon >= 0) else cov.min_longitude
        o_max_lon = cov.max_longitude + 360.0 if (cov.max_longitude < 0 and max_lon >= 0) else cov.max_longitude
        if (
            cov.max_latitude <= min_lat
            or cov.min_latitude >= max_lat
            or o_max_lon <= min_lon
            or o_min_lon >= max_lon
        ):
            return None
        return opt_ds

    def analyze_corridor_uncertainty(
        self,
        *,
        dataset_id: Optional[str] = None,
        optical_dataset_id: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        max_slope_deg: float = 20.0,
        grid_size: int = 97,
    ) -> CorridorUncertaintyProfile:
        t0 = time.perf_counter()
        dem_ds = self._resolve_dem_dataset(dataset_id)
        bounds = {
            "min_lat": min_lat if min_lat is not None else max(dem_ds.coverage.min_latitude, DEFAULT_GALE_STUDY_BOUNDS["min_lat"]),
            "max_lat": max_lat if max_lat is not None else min(dem_ds.coverage.max_latitude, DEFAULT_GALE_STUDY_BOUNDS["max_lat"]),
            "min_lon": min_lon if min_lon is not None else max(dem_ds.coverage.min_longitude, DEFAULT_GALE_STUDY_BOUNDS["min_lon"]),
            "max_lon": max_lon if max_lon is not None else min(dem_ds.coverage.max_longitude, DEFAULT_GALE_STUDY_BOUNDS["max_lon"]),
        }
        if bounds["min_lat"] >= bounds["max_lat"] or bounds["min_lon"] >= bounds["max_lon"]:
            bounds = {
                "min_lat": dem_ds.coverage.min_latitude,
                "max_lat": dem_ds.coverage.max_latitude,
                "min_lon": dem_ds.coverage.min_longitude,
                "max_lon": dem_ds.coverage.max_longitude,
            }

        cache_key = (
            f"corr:{dem_ds.id}:{optical_dataset_id or 'auto'}:"
            f"{bounds['min_lat']:.6f}:{bounds['max_lat']:.6f}:{bounds['min_lon']:.6f}:{bounds['max_lon']:.6f}:"
            f"{max_slope_deg:.2f}:{grid_size}"
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        dem_profile = self.inspect_dataset_uncertainty(dem_ds.id)
        opt_ds = self._resolve_supporting_optical(
            dem_ds, optical_dataset_id, bounds["min_lat"], bounds["max_lat"], bounds["min_lon"], bounds["max_lon"]
        )
        additional: List[Dataset] = []
        for sec_id in ("usgs_sim3292_mars_geology", "mola_megt00n090hb"):
            if sec_id != dem_ds.id:
                s_ds = self.catalog_service.get_dataset(sec_id)
                if s_ds:
                    additional.append(s_ds)

        elev, nodata_mask, dx_m, dy_m = self._sample_corridor_window(
            dataset=dem_ds,
            min_lat=bounds["min_lat"],
            max_lat=bounds["max_lat"],
            min_lon=bounds["min_lon"],
            max_lon=bounds["max_lon"],
            grid_size=max(17, min(193, int(grid_size))),
        )
        _slope, _sig, _tri, _states, _tri_sig, profile = evaluate_coupled_corridor_uncertainty(
            elevation_grid=elev,
            dx_meters=dx_m,
            dy_meters=dy_m,
            dem_dataset=dem_ds,
            dem_profile=dem_profile,
            optical_dataset=opt_ds,
            additional_datasets=additional,
            nodata_mask=nodata_mask,
            max_slope_deg=max_slope_deg,
        )
        profile.compute_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        self._cache_put(cache_key, profile)
        return profile

    def render_uncertainty_overlay_png(
        self,
        *,
        dataset_id: str,
        overlay: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        size: int = 256,
        max_slope_deg: float = 20.0,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> bytes:
        """
        Render strictly registered PNG textures for Prompt 16 uncertainty, 3-state traversability,
        feature observability, or Horn 3x3 slope sigma sensitivity overlays.
        """
        overlay_l = overlay.strip().lower()
        size = max(64, min(512, int(size)))
        cache_key = (
            f"u_tex:{dataset_id}:{overlay_l}:{min_lat:.7f}:{max_lat:.7f}:"
            f"{min_lon:.7f}:{max_lon:.7f}:{size}:{max_slope_deg:.2f}:{vmin}:{vmax}"
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        dem_ds = self._resolve_dem_dataset(dataset_id)
        dem_profile = self.inspect_dataset_uncertainty(dem_ds.id)
        opt_ds = self._resolve_supporting_optical(dem_ds, None, min_lat, max_lat, min_lon, max_lon)

        elev, nodata_mask, dx_m, dy_m = self._sample_corridor_window(
            dataset=dem_ds,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            grid_size=size,
        )
        slope_deg, slope_sigma_deg, _tri, state_grid, _tri_sig, _prof = evaluate_coupled_corridor_uncertainty(
            elevation_grid=elev,
            dx_meters=dx_m,
            dy_meters=dy_m,
            dem_dataset=dem_ds,
            dem_profile=dem_profile,
            optical_dataset=opt_ds,
            nodata_mask=nodata_mask,
            max_slope_deg=max_slope_deg,
        )

        h_grid, w_grid = elev.shape
        rgba = np.zeros((h_grid, w_grid, 4), dtype=np.uint8)
        valid_elev = np.isfinite(elev) & (~nodata_mask)
        valid_slope = np.isfinite(slope_deg)

        if overlay_l == "traversability_state":
            # 1 -> EVALUATED (#10b981), 2 -> KNOWN_CONSTRAINT_EXCLUSION (#ef4444), 0 -> UNKNOWN (#f59e0b or transparent on pure no-data)
            eval_m = state_grid == 1
            excl_m = state_grid == 2
            unk_obs_m = (state_grid == 0) & valid_elev
            rgba[eval_m] = [16, 185, 129, 255]
            rgba[excl_m] = [239, 68, 68, 255]
            rgba[unk_obs_m] = [245, 158, 11, 255]
        elif overlay_l == "uncertainty_status":
            if dem_profile.has_per_pixel_error_raster:
                rgba[valid_slope] = [22, 163, 74, 255]
            elif dem_profile.overall_elevation_uncertainty_status in {
                UncertaintyStatus.QUANTIFIED_FROM_METADATA,
                UncertaintyStatus.QUANTIZATION_LOWER_BOUND_ONLY,
            }:
                rgba[valid_slope] = [234, 179, 8, 255]
            else:
                rgba[valid_slope] = [220, 38, 38, 255]
            # Border/partial-kernel cells inside DEM footprint lack complete 3x3 Horn stencil
            edge_unquant = valid_elev & (~valid_slope)
            rgba[edge_unquant] = [220, 38, 38, 255]
        elif overlay_l == "observability":
            dem_res = float(dem_ds.horizontal_resolution_meters or 999.0)
            if dem_res > 5.0:
                rgba[valid_elev] = [168, 85, 247, 255]  # purple: coarse regional DEM only
            elif opt_ds is not None:
                rgba[valid_elev] = [6, 182, 212, 255]   # cyan: m-scale slope + sub-meter ortho (sub-0.5m still unresolved)
            else:
                rgba[valid_elev] = [59, 130, 246, 255]  # blue: m-scale slope only
        elif overlay_l == "slope_uncertainty_probe":
            fin_sig = np.isfinite(slope_sigma_deg)
            lo = 0.0 if vmin is None else float(vmin)
            if vmax is not None:
                hi = float(vmax)
            elif np.any(fin_sig):
                hi = max(lo + 1.0, float(np.percentile(slope_sigma_deg[fin_sig], 98)))
            else:
                hi = 15.0
            t = np.where(fin_sig, np.clip((slope_sigma_deg - lo) / max(1e-6, hi - lo), 0.0, 1.0), 0.0)
            # Ramp: #1e40af -> #06b6d4 -> #f59e0b -> #dc2626
            ts = [0.0, 0.4, 0.75, 1.0]
            rs = np.interp(t, ts, [30.0, 6.0, 245.0, 220.0])
            gs = np.interp(t, ts, [64.0, 182.0, 158.0, 38.0])
            bs = np.interp(t, ts, [175.0, 212.0, 11.0, 38.0])
            rgba[..., 0] = np.clip(rs, 0, 255).astype(np.uint8)
            rgba[..., 1] = np.clip(gs, 0, 255).astype(np.uint8)
            rgba[..., 2] = np.clip(bs, 0, 255).astype(np.uint8)
            rgba[..., 3] = np.where(fin_sig, 255, 0).astype(np.uint8)
        else:
            raise ValueError(f"Unsupported uncertainty overlay '{overlay}'.")

        buf = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
        png_bytes = buf.getvalue()
        self._cache_put(cache_key, png_bytes)
        return png_bytes
