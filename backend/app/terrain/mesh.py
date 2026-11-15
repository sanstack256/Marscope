"""
MARSCOPE Real 3D Terrain Mesh Tile & Ortho/Derivative Texture Service
Martian Surface Intelligence & Exploration System

Generates hierarchical LOD heightfield mesh tiles, exact neighbor-stitched boundary
vertices, explicit nodata validity masks (zero silent gap interpolation), Cesium
HeightmapTerrainData grids, and georeferenced RGBA overlay/ortho textures directly
from verified NASA MOLA and HiRISE Stereo DTM datasets.
"""

from __future__ import annotations

from collections import OrderedDict
import io
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, angular_displacement_to_metric
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.coverage import _resolve_raw_dem_open_path, is_dataset_asset_available
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.schemas.dataset import Dataset, DatasetLifecycleStatus
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


DEFAULT_GALE_STUDY_BOUNDS: Dict[str, float] = {
    "min_lat": -5.5,
    "max_lat": -4.3,
    "min_lon": 137.2,
    "max_lon": 138.0,
}

# Recommended default operational windows per high-res HiRISE DTM covering Curiosity + Boxwork traverse
HIRISE_DEFAULT_FOCUS_BOUNDS: Dict[str, Dict[str, float]] = {
    "hirise_dteec_009149_1750": {
        "min_lat": -4.795,
        "max_lat": -4.685,
        "min_lon": 137.360,
        "max_lon": 137.450,
    },
    "hirise_dteec_040770_1755": {
        "min_lat": -4.765,
        "max_lat": -4.585,
        "min_lon": 137.340,
        "max_lon": 137.440,
    },
}

PAIRED_ORTHO_MAP: Dict[str, str] = {
    "hirise_dteec_009149_1750": "hirise_psp_009149_1750_ortho",
    "hirise_dteec_040770_1755": "hirise_esp_040770_1755_ortho",
}

DEFAULT_TRI_PHYSICAL_RADIUS_M = 5.0
COLOR_NORM_PROCESSING_VERSION = "color_norm_v2"

# Perceptually coherent, colorblind-aware sequential palettes shared identically
# between backend PNG rendering and frontend legend rendering.
PALETTE_STOPS: Dict[str, Dict[str, Any]] = {
    "elevation": {
        "palette_id": "elevation_sequential_v2",
        "stops": [
            (0.0, (30, 58, 95), "#1e3a5f"),
            (0.33, (43, 122, 120), "#2b7a78"),
            (0.67, (201, 150, 76), "#c9964c"),
            (1.0, (243, 229, 171), "#f3e5ab"),
        ],
    },
    "slope": {
        "palette_id": "slope_sequential_v2",
        "stops": [
            (0.0, (31, 111, 120), "#1f6f78"),
            (0.5, (217, 130, 43), "#d9822b"),
            (1.0, (185, 28, 28), "#b91c1c"),
        ],
    },
    "roughness": {
        "palette_id": "tri_sequential_v2",
        "stops": [
            (0.0, (27, 31, 59), "#1b1f3b"),
            (0.5, (33, 145, 140), "#21918c"),
            (1.0, (253, 231, 37), "#fde725"),
        ],
    },
}


def _apply_palette_lut(
    t: np.ndarray,
    stops: List[Tuple[float, Tuple[int, int, int], str]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate [0, 1] normalized values through exact RGB palette stops."""
    ts = [s[0] for s in stops]
    rs = [float(s[1][0]) for s in stops]
    gs = [float(s[1][1]) for s in stops]
    bs = [float(s[1][2]) for s in stops]
    tc = np.clip(t, 0.0, 1.0)
    r_ch = np.interp(tc, ts, rs)
    g_ch = np.interp(tc, ts, gs)
    b_ch = np.interp(tc, ts, bs)
    return r_ch, g_ch, b_ch

MARS_GEOG_CRS = rasterio.crs.CRS.from_proj4(
    f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_EQUATORIAL_RADIUS_M} +no_defs"
)


class MeshDemSummary(BaseModel):
    dataset_id: str
    product_id: str
    product_title: str
    native_resolution_m: Optional[float] = None
    ortho_dataset_id: Optional[str] = None
    bounds: Dict[str, float]
    recommended_focus_bounds: Dict[str, float]
    local_slope_suitable: bool = False


class MeshLodLevel(BaseModel):
    lod: int
    tiles_x: int
    tiles_y: int
    tile_grid_cols: int
    tile_grid_rows: int
    approx_vertex_spacing_m: float


class MeshTileDescriptor(BaseModel):
    tile_id: str
    lod: int
    row: int
    col: int
    bounds: Dict[str, float]
    grid_rows: int
    grid_cols: int
    approx_vertex_spacing_m: float


class ColorNormalizationSpec(BaseModel):
    overlay: str
    dataset_id: str
    region_bounds: Dict[str, float]
    processing_version: str = COLOR_NORM_PROCESSING_VERSION
    scale_type: str = "sequential"
    palette_id: str
    palette_stops: List[Dict[str, Any]] = Field(default_factory=list)
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    units: Optional[str] = None
    nodata_label: str = "No-Data (Transparent)"
    nodata_rgba: List[int] = Field(default_factory=lambda: [0, 0, 0, 0])
    physical_radius_m: Optional[float] = None
    source_resolution_m: Optional[float] = None
    window_dimensions_m: Optional[Dict[str, float]] = None
    note: Optional[str] = None


class TerrainMeshManifestResponse(BaseModel):
    dataset_id: str
    product_id: str
    product_title: str
    crs: str = "IAU2000:49900"
    vertical_units: str = "meters"
    vertical_datum: str
    native_resolution_m: Optional[float] = None
    ortho_dataset_id: Optional[str] = None
    requested_bounds: Dict[str, float]
    requested_bounds_modified: bool = False
    dataset_bounds: Dict[str, float]
    origin: Dict[str, float]
    physical_extent_m: Dict[str, float]
    lod_levels: List[MeshLodLevel]
    tiles: List[MeshTileDescriptor]
    available_dems: List[MeshDemSummary]
    resolution_suitability: Dict[str, Any] = Field(default_factory=dict)
    elevation_range_m: Optional[Dict[str, float]] = None
    roughness_range_m: Optional[Dict[str, float]] = None
    tri_metadata: Optional[Dict[str, Any]] = None
    color_normalizations: Dict[str, ColorNormalizationSpec] = Field(default_factory=dict)
    overlay_legends: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class TerrainMeshTileResponse(BaseModel):
    tile_id: str
    dataset_id: str
    product_id: str
    crs: str = "IAU2000:49900"
    vertical_units: str = "meters"
    bounds: Dict[str, float]
    origin: Dict[str, float]
    local_bounds_m: Dict[str, float]
    grid_rows: int
    grid_cols: int
    sample_spacing_m: Dict[str, float]
    native_resolution_m: Optional[float] = None
    elevations_m: List[Optional[float]]
    valid_mask: List[int]
    normals: Optional[List[float]] = None
    slope_deg: Optional[List[Optional[float]]] = None
    roughness_tri_m: Optional[List[Optional[float]]] = None
    tri_status: str = "valid"
    tri_metadata: Optional[Dict[str, Any]] = None
    valid_vertex_count: int
    nodata_vertex_count: int
    elevation_min_m: Optional[float] = None
    elevation_max_m: Optional[float] = None
    slope_max_deg: Optional[float] = None
    generation_ms: float


class HeightGridResponse(BaseModel):
    """
    Cesium heightgrid response contract:
    - elevations_m[i] is a finite float (including 0.0) when valid_mask[i] == 1.
    - elevations_m[i] is None (JSON null) when valid_mask[i] == 0 (unavailable/nodata).
    - Missing samples are NEVER converted to 0.0; nodata_fill_value is None.
    - native_resolution_m reports source DEM pixel size; sample_spacing_m reports
      the actual delivered grid spacing after resampling.
    """
    dataset_id: str
    product_id: str
    available: bool
    crs: str = "IAU2000:49900"
    vertical_units: str = "meters"
    bounds: Dict[str, float]
    grid_rows: int
    grid_cols: int
    valid_fraction: float
    nodata_fill_value: Optional[float] = None
    elevations_m: List[Optional[float]]
    valid_mask: List[int] = Field(default_factory=list)
    sample_spacing_m: Optional[Dict[str, float]] = None
    native_resolution_m: Optional[float] = None
    min_elevation_m: Optional[float] = None
    max_elevation_m: Optional[float] = None


class TerrainMeshService:
    """Thread-safe, memory-bounded DEM mesh & overlay renderer."""

    def __init__(
        self,
        catalog_service: DatasetCatalogService,
        raw_dir,
        max_cache_items: int = 72,
        uncertainty_service: Optional[Any] = None,
    ):
        self.catalog_service = catalog_service
        self.raw_dir = raw_dir
        self._max_cache_items = max_cache_items
        self._tile_cache: "OrderedDict[str, Any]" = OrderedDict()
        self._ortho_avail_cache: Dict[str, Tuple[float, bool]] = {}
        self._lock = threading.Lock()
        self.uncertainty_service = uncertainty_service

    def _get_uncertainty_service(self) -> Any:
        if self.uncertainty_service is None:
            from app.terrain_uncertainty.service import TerrainUncertaintyService

            self.uncertainty_service = TerrainUncertaintyService(
                catalog_service=self.catalog_service,
                raw_dir=Path(self.raw_dir),
                processed_dir=Path(self.raw_dir).parent / "processed",
            )
        return self.uncertainty_service

    def _cache_get(self, key: str) -> Optional[Any]:
        with self._lock:
            val = self._tile_cache.get(key)
            if val is not None:
                self._tile_cache.move_to_end(key)
            return val

    def _cache_put(self, key: str, value: Any) -> None:
        with self._lock:
            self._tile_cache[key] = value
            self._tile_cache.move_to_end(key)
            while len(self._tile_cache) > self._max_cache_items:
                self._tile_cache.popitem(last=False)

    def clear_cache(self) -> None:
        with self._lock:
            self._tile_cache.clear()
            self._ortho_avail_cache.clear()

    def _resolve_catalog_dataset(self, dataset_id: str) -> Optional[Dataset]:
        ds = self.catalog_service.get_dataset(dataset_id)
        if ds is not None:
            return ds
        from app.ingestion.gcs_storage import GCSDatasetStore

        gcs_store = GCSDatasetStore.from_env()
        if gcs_store is None:
            return None
        try:
            payload = gcs_store.read_json_object(f"catalog/{dataset_id}.json")
            if payload is None:
                return None
            ds = Dataset.model_validate(payload)
            if hasattr(self.catalog_service, "_datasets"):
                self.catalog_service._datasets[ds.id] = ds
            return ds
        except Exception:
            return None

    def _resolve_paired_ortho_dataset_id(self, dem_dataset_id: str) -> Optional[str]:
        ortho_id = PAIRED_ORTHO_MAP.get(dem_dataset_id)
        if not ortho_id:
            return None
        ortho_ds = self._resolve_catalog_dataset(ortho_id)
        if not ortho_ds:
            return None
        now = time.monotonic()
        with self._lock:
            cached = self._ortho_avail_cache.get(ortho_id)
            if cached is not None and (now - cached[0]) < 60.0:
                return ortho_id if cached[1] else None
        available = is_dataset_asset_available(ortho_ds, Path(self.raw_dir))
        with self._lock:
            self._ortho_avail_cache[ortho_id] = (now, available)
        return ortho_id if available else None

    def list_available_dem_summaries(self) -> List[MeshDemSummary]:
        datasets = self.catalog_service.list_datasets()
        summaries: List[MeshDemSummary] = []
        for ds in datasets:
            if "DEM" not in ds.product_type.upper():
                continue
            try:
                open_path, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
                if not open_path.exists():
                    continue
            except FileNotFoundError:
                continue

            ds_bounds = {
                "min_lat": ds.coverage.min_latitude,
                "max_lat": ds.coverage.max_latitude,
                "min_lon": ds.coverage.min_longitude,
                "max_lon": ds.coverage.max_longitude,
            }
            focus = HIRISE_DEFAULT_FOCUS_BOUNDS.get(ds.id) or {
                "min_lat": max(ds_bounds["min_lat"], DEFAULT_GALE_STUDY_BOUNDS["min_lat"]),
                "max_lat": min(ds_bounds["max_lat"], DEFAULT_GALE_STUDY_BOUNDS["max_lat"]),
                "min_lon": max(ds_bounds["min_lon"], DEFAULT_GALE_STUDY_BOUNDS["min_lon"]),
                "max_lon": min(ds_bounds["max_lon"], DEFAULT_GALE_STUDY_BOUNDS["max_lon"]),
            }
            if focus["min_lat"] >= focus["max_lat"] or focus["min_lon"] >= focus["max_lon"]:
                focus = dict(ds_bounds)
            suit = evaluate_dem_resolution_suitability(
                native_resolution_m=ds.horizontal_resolution_meters,
                effective_resolution_m=ds.horizontal_resolution_meters,
                dem_available=True,
            )
            ortho_id = self._resolve_paired_ortho_dataset_id(ds.id)
            summaries.append(
                MeshDemSummary(
                    dataset_id=ds.id,
                    product_id=ds.product_id,
                    product_title=ds.product_title,
                    native_resolution_m=ds.horizontal_resolution_meters,
                    ortho_dataset_id=ortho_id,
                    bounds=ds_bounds,
                    recommended_focus_bounds=focus,
                    local_slope_suitable=suit["local_slope_analysis"].supported,
                )
            )

        # Highest spatial resolution first so HiRISE DTMs lead
        summaries.sort(key=lambda s: s.native_resolution_m if s.native_resolution_m is not None else 1e9)
        return summaries

    def resolve_dataset(self, dataset_id: Optional[str] = None) -> Dataset:
        if dataset_id:
            ds = self.catalog_service.get_dataset(dataset_id)
            if not ds:
                raise FileNotFoundError(f"DEM dataset '{dataset_id}' not found in catalog.")
            return ds
        avail = self.list_available_dem_summaries()
        if not avail:
            raise FileNotFoundError("No locally downloaded DEM datasets available for 3D terrain mesh generation.")
        preferred = self.catalog_service.get_dataset(avail[0].dataset_id)
        if not preferred:
            raise FileNotFoundError("Preferred DEM dataset could not be resolved.")
        return preferred

    @staticmethod
    def _parse_tile_id(tile_id: str) -> Tuple[int, int, int]:
        # Expected format: L{lod}_R{row}_C{col}
        parts = tile_id.strip().upper().split("_")
        if len(parts) != 3 or not (parts[0].startswith("L") and parts[1].startswith("R") and parts[2].startswith("C")):
            raise ValueError(f"Invalid tile_id '{tile_id}'. Expected format L<lod>_R<row>_C<col>.")
        lod = int(parts[0][1:])
        row = int(parts[1][1:])
        col = int(parts[2][1:])
        if lod < 0 or lod > 5 or row < 0 or col < 0:
            raise ValueError(f"Out-of-range tile coordinates in '{tile_id}'.")
        return lod, row, col

    @staticmethod
    def _partition_edges(min_v: float, max_v: float, n: int) -> List[float]:
        # Bit-exact shared interior edges across adjacent tiles
        return [min_v + (max_v - min_v) * (k / float(n)) for k in range(n + 1)]

    def get_mesh_manifest(
        self,
        dataset_id: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        max_lod: int = 2,
        tile_grid_size: int = 65,
    ) -> TerrainMeshManifestResponse:
        ds = self.resolve_dataset(dataset_id)
        open_path, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
        if not open_path.exists():
            raise FileNotFoundError(f"DEM binary missing locally for '{ds.id}'.")

        ds_bounds = {
            "min_lat": ds.coverage.min_latitude,
            "max_lat": ds.coverage.max_latitude,
            "min_lon": ds.coverage.min_longitude,
            "max_lon": ds.coverage.max_longitude,
        }
        has_explicit = None not in (min_lat, max_lat, min_lon, max_lon)
        if has_explicit:
            req_bounds = {
                "min_lat": float(min_lat),
                "max_lat": float(max_lat),
                "min_lon": float(min_lon),
                "max_lon": float(max_lon),
            }
            if req_bounds["min_lat"] >= req_bounds["max_lat"] or req_bounds["min_lon"] >= req_bounds["max_lon"]:
                raise ValueError("Invalid study bounds: min_lat < max_lat and min_lon < max_lon required.")
            # Verify overlap without silently mutating requested_bounds
            if (
                req_bounds["max_lat"] <= ds_bounds["min_lat"]
                or req_bounds["min_lat"] >= ds_bounds["max_lat"]
                or req_bounds["max_lon"] <= ds_bounds["min_lon"]
                or req_bounds["min_lon"] >= ds_bounds["max_lon"]
            ):
                raise ValueError(
                    f"Requested bounds {req_bounds} do not overlap DEM '{ds.id}' footprint {ds_bounds}."
                )
        else:
            req_bounds = HIRISE_DEFAULT_FOCUS_BOUNDS.get(ds.id) or {
                "min_lat": max(ds_bounds["min_lat"], DEFAULT_GALE_STUDY_BOUNDS["min_lat"]),
                "max_lat": min(ds_bounds["max_lat"], DEFAULT_GALE_STUDY_BOUNDS["max_lat"]),
                "min_lon": max(ds_bounds["min_lon"], DEFAULT_GALE_STUDY_BOUNDS["min_lon"]),
                "max_lon": min(ds_bounds["max_lon"], DEFAULT_GALE_STUDY_BOUNDS["max_lon"]),
            }
            if req_bounds["min_lat"] >= req_bounds["max_lat"] or req_bounds["min_lon"] >= req_bounds["max_lon"]:
                req_bounds = dict(ds_bounds)

        center_lat = 0.5 * (req_bounds["min_lat"] + req_bounds["max_lat"])
        center_lon = 0.5 * (req_bounds["min_lon"] + req_bounds["max_lon"])
        width_m, height_m = angular_displacement_to_metric(
            center_lat,
            req_bounds["max_lon"] - req_bounds["min_lon"],
            req_bounds["max_lat"] - req_bounds["min_lat"],
        )

        # Build LOD descriptors: LOD 0 = 1x1, LOD 1 = 2x2, LOD 2 = 4x4
        tile_grid_size = max(17, min(129, int(tile_grid_size)))
        lod_levels: List[MeshLodLevel] = []
        tiles: List[MeshTileDescriptor] = []
        bounded_max_lod = max(0, min(3, int(max_lod)))

        for lod in range(bounded_max_lod + 1):
            n_div = 1 << lod
            segs = tile_grid_size - 1
            spacing_x = width_m / float(n_div * segs)
            spacing_y = height_m / float(n_div * segs)
            approx_spacing = 0.5 * (spacing_x + spacing_y)
            lod_levels.append(
                MeshLodLevel(
                    lod=lod,
                    tiles_x=n_div,
                    tiles_y=n_div,
                    tile_grid_cols=tile_grid_size,
                    tile_grid_rows=tile_grid_size,
                    approx_vertex_spacing_m=round(approx_spacing, 3),
                )
            )
            lon_edges = self._partition_edges(req_bounds["min_lon"], req_bounds["max_lon"], n_div)
            # Row 0 is North (top), increasing Southward matching standard raster ordering
            lat_edges_ns = [
                req_bounds["max_lat"] - (req_bounds["max_lat"] - req_bounds["min_lat"]) * (r / float(n_div))
                for r in range(n_div + 1)
            ]
            for r in range(n_div):
                for c in range(n_div):
                    tiles.append(
                        MeshTileDescriptor(
                            tile_id=f"L{lod}_R{r}_C{c}",
                            lod=lod,
                            row=r,
                            col=c,
                            bounds={
                                "min_lat": lat_edges_ns[r + 1],
                                "max_lat": lat_edges_ns[r],
                                "min_lon": lon_edges[c],
                                "max_lon": lon_edges[c + 1],
                            },
                            grid_rows=tile_grid_size,
                            grid_cols=tile_grid_size,
                            approx_vertex_spacing_m=round(approx_spacing, 3),
                        )
                    )

        ortho_id = self._resolve_paired_ortho_dataset_id(ds.id)

        suit = evaluate_dem_resolution_suitability(
            native_resolution_m=ds.horizontal_resolution_meters,
            effective_resolution_m=ds.horizontal_resolution_meters,
            dem_available=True,
        )
        suit_dump = {k: v.model_dump() for k, v in suit.items()}

        region_stats = self._get_region_render_stats(
            ds.id,
            req_bounds["min_lat"],
            req_bounds["max_lat"],
            req_bounds["min_lon"],
            req_bounds["max_lon"],
        )
        color_normalizations = self._build_color_normalizations(
            dataset_id=ds.id,
            product_id=ds.product_id,
            ortho_dataset_id=ortho_id,
            native_resolution_m=ds.horizontal_resolution_meters,
            region_bounds=req_bounds,
            region_stats=region_stats,
        )

        from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty
        from app.terrain_uncertainty.uncertainty_propagation import build_prompt16_overlay_legends

        dem_profile = inspect_dataset_elevation_uncertainty(
            dataset=ds,
            raw_dir=Path(self.raw_dir),
            processed_dir=Path(self.raw_dir).parent / "processed",
        )
        el_r = region_stats.get("elevation_range_m") or {}
        tri_r = region_stats.get("roughness_range_m") or {}
        el_tuple = (float(el_r["min_m"]), float(el_r["max_m"])) if ("min_m" in el_r and "max_m" in el_r) else None
        tri_tuple = (float(tri_r["min_m"]), float(tri_r["max_m"])) if ("min_m" in tri_r and "max_m" in tri_r) else None
        raw_legends = build_prompt16_overlay_legends(
            dataset=ds,
            optical_available=ortho_id is not None,
            dem_profile=dem_profile,
            elev_range=el_tuple,
            tri_range=tri_tuple,
        )
        overlay_legends = {k: v.model_dump() for k, v in raw_legends.items()}

        return TerrainMeshManifestResponse(
            dataset_id=ds.id,
            product_id=ds.product_id,
            product_title=ds.product_title,
            vertical_datum=ds.calibration_status,
            native_resolution_m=ds.horizontal_resolution_meters,
            ortho_dataset_id=ortho_id,
            requested_bounds=req_bounds,
            requested_bounds_modified=False,
            dataset_bounds=ds_bounds,
            origin={"lat": round(center_lat, 7), "lon_east": round(center_lon, 7)},
            physical_extent_m={"width_m": round(width_m, 2), "height_m": round(height_m, 2)},
            lod_levels=lod_levels,
            tiles=tiles,
            available_dems=self.list_available_dem_summaries(),
            resolution_suitability=suit_dump,
            elevation_range_m=region_stats.get("elevation_range_m"),
            roughness_range_m=region_stats.get("roughness_range_m"),
            tri_metadata=region_stats.get("tri_metadata"),
            color_normalizations=color_normalizations,
            overlay_legends=overlay_legends,
        )

    @staticmethod
    def _build_color_normalizations(
        *,
        dataset_id: str,
        product_id: str,
        ortho_dataset_id: Optional[str],
        native_resolution_m: Optional[float],
        region_bounds: Dict[str, float],
        region_stats: Dict[str, Any],
    ) -> Dict[str, ColorNormalizationSpec]:
        def _stops_payload(key: str) -> List[Dict[str, Any]]:
            return [
                {"t": t_val, "color": hex_col, "rgb": list(rgb)}
                for t_val, rgb, hex_col in PALETTE_STOPS[key]["stops"]
            ]

        el_r = region_stats.get("elevation_range_m") or {}
        tri_r = region_stats.get("roughness_range_m") or {}
        tri_meta = region_stats.get("tri_metadata") or {}

        specs: Dict[str, ColorNormalizationSpec] = {
            "elevation": ColorNormalizationSpec(
                overlay="elevation",
                dataset_id=dataset_id,
                region_bounds=region_bounds,
                scale_type="sequential",
                palette_id=PALETTE_STOPS["elevation"]["palette_id"],
                palette_stops=_stops_payload("elevation"),
                vmin=el_r.get("min_m"),
                vmax=el_r.get("max_m"),
                units="meters",
                source_resolution_m=native_resolution_m,
                note="Height relative to MOLA areoid (IAU2000:49900), normalized across full study region.",
            ),
            "slope": ColorNormalizationSpec(
                overlay="slope",
                dataset_id=dataset_id,
                region_bounds=region_bounds,
                scale_type="sequential",
                palette_id=PALETTE_STOPS["slope"]["palette_id"],
                palette_stops=_stops_payload("slope"),
                vmin=0.0,
                vmax=35.0,
                units="degrees",
                source_resolution_m=native_resolution_m,
                note="Physical terrain slope in degrees; independent of 3D vertical exaggeration.",
            ),
            "roughness": ColorNormalizationSpec(
                overlay="roughness",
                dataset_id=dataset_id,
                region_bounds=region_bounds,
                scale_type="sequential",
                palette_id=PALETTE_STOPS["roughness"]["palette_id"],
                palette_stops=_stops_payload("roughness"),
                vmin=tri_r.get("min_m", 0.0),
                vmax=tri_r.get("max_m", 5.0),
                units="meters",
                physical_radius_m=tri_meta.get("physical_radius_m", DEFAULT_TRI_PHYSICAL_RADIUS_M),
                source_resolution_m=native_resolution_m,
                window_dimensions_m=(
                    {
                        "width_m": tri_meta["actual_window_width_m"],
                        "height_m": tri_meta["actual_window_height_m"],
                    }
                    if tri_meta.get("actual_window_width_m") and tri_meta.get("actual_window_height_m")
                    else None
                ),
                note="RMS elevation difference (TRI) over fixed physical window; lower to higher local elevation variation.",
            ),
        }
        if ortho_dataset_id:
            specs["ortho"] = ColorNormalizationSpec(
                overlay="ortho",
                dataset_id=ortho_dataset_id,
                region_bounds=region_bounds,
                scale_type="source_imagery",
                palette_id="hirise_source_reflectance",
                palette_stops=[],
                source_resolution_m=native_resolution_m,
                note=f"Source HiRISE orthorectified reflectance ({product_id}); RGB values are not physical elevation or slope measurements.",
            )
        return specs

    def _get_region_render_stats(
        self,
        dataset_id: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> Dict[str, Any]:
        """
        Compute dataset/region-wide min/max elevation and 98th-percentile TRI so all
        adjacent LOD tiles render with identical color normalization across seams.
        """
        from app.geospatial.spatial_delivery import compute_dataset_metadata_hash, compute_spatial_cache_digest

        ds_meta = self.catalog_service.get_dataset(dataset_id)
        mhash = compute_dataset_metadata_hash(ds_meta) if ds_meta else "no_meta"
        cache_key = compute_spatial_cache_digest(
            dataset=ds_meta,
            dataset_id=dataset_id,
            algorithm="region_render_stats",
            algorithm_version="mesh_v2",
            parameters={},
            resolution_m=(ds_meta.horizontal_resolution_meters if ds_meta else None),
            bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
        ).composite_key
        cached = self._tracked_cache_get(cache_key)
        if cached is not None:
            return cached

        grid_n = 65
        tile = self.get_mesh_tile(
            tile_id="custom",
            dataset_id=dataset_id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            grid_size=grid_n,
            include_derivatives=True,
        )
        elev_fin = [float(v) for v in tile.elevations_m if v is not None]
        tri_fin = [float(v) for v in (tile.roughness_tri_m or []) if v is not None]

        elev_range = None
        if elev_fin:
            e_min = float(min(elev_fin))
            e_max = max(e_min + 1.0, float(max(elev_fin)))
            elev_range = {"min_m": round(e_min, 3), "max_m": round(e_max, 3)}

        tri_range = None
        if tri_fin:
            t_min = float(min(tri_fin))
            t_p98 = max(t_min + 0.5, float(np.percentile(np.array(tri_fin, dtype=np.float64), 98)))
            tri_range = {"min_m": round(t_min, 3), "max_m": round(t_p98, 3)}

        stats = {
            "elevation_range_m": elev_range,
            "roughness_range_m": tri_range,
            "tri_metadata": tile.tri_metadata,
        }
        self._cache_put(cache_key, stats)
        self._cache_put(f"stats_default:{dataset_id}:{mhash}", stats)
        return stats

    @staticmethod
    def _sample_physical_tri_grid(
        reader: Any,
        nodata_val: float,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        grid_rows: int,
        grid_cols: int,
        radius_m: float = DEFAULT_TRI_PHYSICAL_RADIUS_M,
        source_product_id: Optional[str] = None,
        native_resolution_m: Optional[float] = None,
    ) -> Tuple[np.ndarray, str, Dict[str, Any]]:
        """
        Compute LOD-invariant Terrain Ruggedness Index (TRI) at each tile vertex (lat, lon)
        by evaluating the exact fixed-radius physical neighborhood on native DEM pixels.
        """
        out = np.full((grid_rows, grid_cols), np.nan, dtype=np.float64)
        rb = reader.bounds
        q_lons = np.linspace(min_lon, max_lon, grid_cols, dtype=np.float64)
        if rb.right > 180.0 and min_lon < 0.0:
            q_lons = q_lons + 360.0
        lats = np.linspace(max_lat, min_lat, grid_rows, dtype=np.float64)

        center_lat = 0.5 * (min_lat + max_lat)
        m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
        m_per_deg_lon = MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(center_lat)) * math.pi / 180.0
        nat_dx_m = abs(float(reader.transform.a)) * m_per_deg_lon
        nat_dy_m = abs(float(reader.transform.e)) * m_per_deg_lat

        max_spacing = max(nat_dx_m, nat_dy_m)
        if radius_m < 0.5 * max_spacing:
            return (
                out,
                "resolution_limited",
                {
                    "metric": "Terrain Ruggedness Index (RMS elevation difference)",
                    "formula_id": "riley_1999_rms_elevation_difference_v1",
                    "neighborhood_shape": "rectangular_metric_window",
                    "units": "meters",
                    "physical_radius_m": round(float(radius_m), 3),
                    "source_product_id": source_product_id,
                    "native_resolution_m": native_resolution_m or round(max_spacing, 3),
                    "processing_resolution_m": round(0.5 * (nat_dx_m + nat_dy_m), 3),
                    "nodata_policy": "strict_all_neighbors_valid",
                    "processing_version": "tri_v2_fixed_physical_window",
                    "status": "resolution_limited",
                    "reason": (
                        f"Requested physical radius ({radius_m} m) is smaller than half the native DEM "
                        f"spacing ({nat_dx_m:.2f} m x {nat_dy_m:.2f} m)."
                    ),
                },
            )

        rx = max(1, int(round(radius_m / nat_dx_m)))
        ry = max(1, int(round(radius_m / nat_dy_m)))
        neighbor_total = (2 * ry + 1) * (2 * rx + 1) - 1
        meta = {
            "metric": "Terrain Ruggedness Index (RMS elevation difference)",
            "formula_id": "riley_1999_rms_elevation_difference_v1",
            "neighborhood_shape": "rectangular_metric_window",
            "units": "meters",
            "window_half_pixels_x": rx,
            "window_half_pixels_y": ry,
            "window_shape_pixels": [2 * ry + 1, 2 * rx + 1],
            "neighbor_count_required": neighbor_total,
            "physical_radius_m": round(float(radius_m), 3),
            "physical_half_width_m": round(rx * nat_dx_m, 3),
            "physical_half_height_m": round(ry * nat_dy_m, 3),
            "actual_window_width_m": round((2 * rx + 1) * nat_dx_m, 3),
            "actual_window_height_m": round((2 * ry + 1) * nat_dy_m, 3),
            "source_product_id": source_product_id,
            "native_resolution_m": native_resolution_m or round(0.5 * (nat_dx_m + nat_dy_m), 3),
            "processing_resolution_m": round(0.5 * (nat_dx_m + nat_dy_m), 3),
            "nodata_policy": "strict_all_neighbors_valid",
            "processing_version": "tri_v2_fixed_physical_window",
            "status": "valid",
        }

        inv_t = ~reader.transform
        col_coords = inv_t.a * q_lons + inv_t.b * center_lat + inv_t.c - 0.5
        row_coords = inv_t.d * float(q_lons[0]) + inv_t.e * lats + inv_t.f - 0.5
        c_nat = np.rint(col_coords).astype(np.int64)
        r_nat = np.rint(row_coords).astype(np.int64)

        valid_c_mask = (c_nat - rx >= 0) & (c_nat + rx < int(reader.width))
        if not np.any(valid_c_mask):
            return out, "valid", meta
        c_min_req = int(np.min(c_nat[valid_c_mask])) - rx
        c_max_req = int(np.max(c_nat[valid_c_mask])) + rx + 1

        strip_rows = 16
        for r_start in range(0, grid_rows, strip_rows):
            r_end = min(grid_rows, r_start + strip_rows)
            r_sub = r_nat[r_start:r_end]
            valid_r_mask = (r_sub - ry >= 0) & (r_sub + ry < int(reader.height))
            if not np.any(valid_r_mask):
                continue

            r_min_req = int(np.min(r_sub[valid_r_mask])) - ry
            r_max_req = int(np.max(r_sub[valid_r_mask])) + ry + 1
            win = rasterio.windows.Window(c_min_req, r_min_req, c_max_req - c_min_req, r_max_req - r_min_req)
            patch = reader.read(1, window=win).astype(np.float64)
            valid_patch = np.isfinite(patch) & (patch != float(nodata_val)) & (patch > -32000.0)

            rr, cc = np.meshgrid(r_sub - r_min_req, c_nat - c_min_req, indexing="ij")
            in_grid = valid_r_mask[:, None] & valid_c_mask[None, :]
            if not np.any(in_grid):
                continue

            rr_v = rr[in_grid]
            cc_v = cc[in_grid]
            z0 = patch[rr_v, cc_v]
            all_ok = valid_patch[rr_v, cc_v].copy()
            sum_sq = np.zeros(z0.shape, dtype=np.float64)

            for dr in range(-ry, ry + 1):
                for dc in range(-rx, rx + 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr = rr_v + dr
                    nc = cc_v + dc
                    n_ok = valid_patch[nr, nc]
                    all_ok &= n_ok
                    nz = patch[nr, nc]
                    diff = np.where(all_ok, z0 - nz, 0.0)
                    sum_sq += diff * diff

            tri_vals = np.where(all_ok, np.sqrt(sum_sq / float(neighbor_total)), np.nan)
            strip_out = np.full((r_end - r_start, grid_cols), np.nan, dtype=np.float64)
            strip_out[in_grid] = tri_vals
            out[r_start:r_end, :] = strip_out

        return out, "valid", meta

    @staticmethod
    def _sample_dem_grid(
        reader: Any,
        nodata_val: float,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        grid_rows: int,
        grid_cols: int,
    ) -> Tuple[np.ndarray, float, float]:
        """
        Sample exact vertex coordinates row-major (North->South, West->East) using bilinear
        interpolation across 4 valid source neighbors (or exact nearest fallback ONLY on edges
        if center pixel itself is valid). Because shared edges evaluate at identical (lon, lat)
        coordinates on identical raster pixels, neighboring tiles stitch with zero cracks!
        Any sample outside the footprint or missing valid neighbors remains NaN.
        """
        # Pad 1 ring outward for derivative kernel edge stitching across neighbor tiles
        d_lon = (max_lon - min_lon) / float(max(1, grid_cols - 1))
        d_lat = (max_lat - min_lat) / float(max(1, grid_rows - 1))

        p_rows = grid_rows + 2
        p_cols = grid_cols + 2
        lons = np.empty(p_cols, dtype=np.float64)
        lats = np.empty(p_rows, dtype=np.float64)
        lons[1:-1] = np.linspace(min_lon, max_lon, grid_cols, dtype=np.float64)
        lons[0] = min_lon - d_lon
        lons[-1] = max_lon + d_lon
        lats[1:-1] = np.linspace(max_lat, min_lat, grid_rows, dtype=np.float64)
        lats[0] = max_lat + d_lat
        lats[-1] = min_lat - d_lat

        rb = reader.bounds
        q_lons = np.where((rb.right > 180.0) & (lons < 0.0), lons + 360.0, lons)

        # Compute bounding pixel window covering padded grid + 2px interpolation margin
        inv_t = ~reader.transform
        x_min, x_max = float(np.min(q_lons)), float(np.max(q_lons))
        y_min, y_max = float(np.min(lats)), float(np.max(lats))
        c_min_f = inv_t.a * x_min + inv_t.b * y_min + inv_t.c
        r_max_f = inv_t.d * x_min + inv_t.e * y_min + inv_t.f
        c_max_f = inv_t.a * x_max + inv_t.b * y_max + inv_t.c
        r_min_f = inv_t.d * x_max + inv_t.e * y_max + inv_t.f

        c0_raw = int(math.floor(min(c_min_f, c_max_f))) - 2
        c1_raw = int(math.ceil(max(c_min_f, c_max_f))) + 3
        r0_raw = int(math.floor(min(r_min_f, r_max_f))) - 2
        r1_raw = int(math.ceil(max(r_min_f, r_max_f))) + 3

        out = np.full((p_rows, p_cols), np.nan, dtype=np.float64)
        center_lat = 0.5 * (min_lat + max_lat)
        dx_m, dy_m = angular_displacement_to_metric(center_lat, d_lon, d_lat)

        if c1_raw <= 0 or r1_raw <= 0 or c0_raw >= int(reader.width) or r0_raw >= int(reader.height):
            return out, dx_m, dy_m

        # Compute global aligned stride from desired sample spacing vs raster pixel size
        # so adjacent tiles at the same LOD align to the exact same coarse pixel lattice!
        res_x, res_y = abs(float(reader.res[0])), abs(float(reader.res[1]))
        stride = max(1, int(math.floor(0.5 * min(d_lon / max(1e-12, res_x), d_lat / max(1e-12, res_y)))))
        if stride > 1:
            # Cap raw stride only if window would still be tiny anyway
            c0 = max(0, (c0_raw // stride) * stride)
            r0 = max(0, (r0_raw // stride) * stride)
            max_c = min(int(reader.width), ((c1_raw + stride - 1) // stride) * stride)
            max_r = min(int(reader.height), ((r1_raw + stride - 1) // stride) * stride)
            # Trim to exact integer multiple of stride inside raster bounds
            out_w = (max_c - c0) // stride
            out_h = (max_r - r0) // stride
            if out_w < 2 or out_h < 2:
                stride = 1
        if stride <= 1:
            c0 = max(0, c0_raw)
            c1 = min(int(reader.width), c1_raw)
            r0 = max(0, r0_raw)
            r1 = min(int(reader.height), r1_raw)
            out_w = c1 - c0
            out_h = r1 - r0
            if out_h <= 0 or out_w <= 0:
                return out, dx_m, dy_m
            win = rasterio.windows.Window(c0, r0, out_w, out_h)
            patch = reader.read(1, window=win).astype(np.float64)
            patch_inv = ~reader.window_transform(win)
        else:
            c1 = c0 + out_w * stride
            r1 = r0 + out_h * stride
            win = rasterio.windows.Window(c0, r0, out_w * stride, out_h * stride)
            patch = reader.read(
                1,
                window=win,
                out_shape=(out_h, out_w),
                resampling=Resampling.nearest,
            ).astype(np.float64)
            w_left, w_bottom, w_right, w_top = rasterio.windows.bounds(win, reader.transform)
            patch_inv = ~rasterio.transform.from_bounds(w_left, w_bottom, w_right, w_top, out_w, out_h)

        valid_patch = np.isfinite(patch) & (patch != float(nodata_val)) & (patch > -32000.0)
        patch_clean = np.where(valid_patch, patch, np.nan)
        ph, pw = patch_clean.shape

        # Vectorized fractional pixel coordinates (pixel centers are at +0.5)
        col_coords = patch_inv.a * q_lons + patch_inv.b * center_lat + patch_inv.c
        row_coords = patch_inv.d * float(q_lons[0]) + patch_inv.e * lats + patch_inv.f

        # In-bounds mask across the valid [-0.5, ph-0.5] x [-0.5, pw-0.5] raster footprint.
        # Clamped bilinear on the outer 0.5px boundary rim ensures continuous border sampling
        # across adjacent tiles instead of nearest-pixel 0.5 rounding discontinuities.
        c_grid = np.broadcast_to(col_coords[None, :], (p_rows, p_cols)) - 0.5
        r_grid = np.broadcast_to(row_coords[:, None], (p_rows, p_cols)) - 0.5

        eps = 1e-6
        in_extent = (
            (r_grid >= -0.5 - eps)
            & (r_grid <= (ph - 0.5) + eps)
            & (c_grid >= -0.5 - eps)
            & (c_grid <= (pw - 0.5) + eps)
        )
        if np.any(in_extent):
            rc = np.clip(r_grid[in_extent], 0.0, max(0.0, float(ph - 1)))
            cc = np.clip(c_grid[in_extent], 0.0, max(0.0, float(pw - 1)))
            r0_idx = (
                np.minimum(np.floor(rc).astype(np.int64), ph - 2)
                if ph > 1
                else np.zeros(rc.shape, dtype=np.int64)
            )
            c0_idx = (
                np.minimum(np.floor(cc).astype(np.int64), pw - 2)
                if pw > 1
                else np.zeros(cc.shape, dtype=np.int64)
            )
            r1_idx = np.minimum(ph - 1, r0_idx + 1)
            c1_idx = np.minimum(pw - 1, c0_idx + 1)
            drc = rc - r0_idx
            dcc = cc - c0_idx
            z00 = patch_clean[r0_idx, c0_idx]
            z01 = patch_clean[r0_idx, c1_idx]
            z10 = patch_clean[r1_idx, c0_idx]
            z11 = patch_clean[r1_idx, c1_idx]
            all4 = np.isfinite(z00) & np.isfinite(z01) & np.isfinite(z10) & np.isfinite(z11)
            vals = (
                np.where(all4, z00, 0.0) * (1.0 - drc) * (1.0 - dcc)
                + np.where(all4, z01, 0.0) * (1.0 - drc) * dcc
                + np.where(all4, z10, 0.0) * drc * (1.0 - dcc)
                + np.where(all4, z11, 0.0) * drc * dcc
            )
            # If on swath border where nearest pixel itself is valid, fall back to nearest
            near_r = np.clip(np.rint(rc).astype(np.int64), 0, ph - 1)
            near_c = np.clip(np.rint(cc).astype(np.int64), 0, pw - 1)
            z_near = patch_clean[near_r, near_c]
            out[in_extent] = np.where(all4, vals, z_near)

        return out, dx_m, dy_m

    def get_mesh_tile(
        self,
        tile_id: str,
        dataset_id: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        origin_lat: Optional[float] = None,
        origin_lon_east: Optional[float] = None,
        grid_size: int = 65,
        include_derivatives: bool = True,
    ) -> TerrainMeshTileResponse:
        t0 = time.perf_counter()
        ds = self.resolve_dataset(dataset_id)
        open_path, lbl_path = _resolve_raw_dem_open_path(ds, self.raw_dir)
        if not open_path.exists():
            raise FileNotFoundError(f"DEM binary missing locally for '{ds.id}'.")

        grid_size = max(9, min(129, int(grid_size)))
        if tile_id.lower() == "custom":
            if None in (min_lat, max_lat, min_lon, max_lon):
                raise ValueError("Custom mesh tile requires min_lat, max_lat, min_lon, max_lon.")
            tile_bounds = {
                "min_lat": float(min_lat),
                "max_lat": float(max_lat),
                "min_lon": float(min_lon),
                "max_lon": float(max_lon),
            }
            if tile_bounds["min_lat"] >= tile_bounds["max_lat"] or tile_bounds["min_lon"] >= tile_bounds["max_lon"]:
                raise ValueError("Invalid tile bounds.")
            manifest_origin_lat = float(origin_lat) if origin_lat is not None else 0.5 * (tile_bounds["min_lat"] + tile_bounds["max_lat"])
            manifest_origin_lon = float(origin_lon_east) if origin_lon_east is not None else 0.5 * (tile_bounds["min_lon"] + tile_bounds["max_lon"])
        else:
            lod, row, col = self._parse_tile_id(tile_id)
            n_div = 1 << lod
            if row >= n_div or col >= n_div:
                raise ValueError(f"Tile row/col ({row},{col}) out of range for LOD {lod} ({n_div}x{n_div}).")
            manifest = self.get_mesh_manifest(
                dataset_id=ds.id,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                max_lod=max(lod, 2),
                tile_grid_size=grid_size,
            )
            match = next((t for t in manifest.tiles if t.tile_id == tile_id.upper()), None)
            if not match:
                raise ValueError(f"Tile '{tile_id}' not found in manifest.")
            tile_bounds = match.bounds
            manifest_origin_lat = float(origin_lat) if origin_lat is not None else manifest.origin["lat"]
            manifest_origin_lon = float(origin_lon_east) if origin_lon_east is not None else manifest.origin["lon_east"]

        from app.geospatial.spatial_delivery import compute_spatial_cache_digest

        cache_key = compute_spatial_cache_digest(
            dataset=ds,
            algorithm="mesh_tile",
            algorithm_version="mesh_v2",
            parameters={
                "tile_id": tile_id,
                "origin_lat": round(manifest_origin_lat, 6),
                "origin_lon_east": round(manifest_origin_lon, 6),
                "grid_size": grid_size,
                "include_derivatives": include_derivatives,
            },
            bounds=tile_bounds,
        ).composite_key
        cached = self._tracked_cache_get(cache_key)
        if cached is not None:
            return cached

        lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}
        with rasterio.open(open_path) as src:
            nodata_val = src.nodata
            if nodata_val is None and lbl_meta.get("missing_constant") is not None:
                try:
                    nodata_val = float(lbl_meta["missing_constant"])
                except (TypeError, ValueError):
                    nodata_val = -32768.0
            elif nodata_val is None:
                nodata_val = -32768.0

            if src.crs and src.crs.is_projected:
                with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                    padded_z, dx_m, dy_m = self._sample_dem_grid(
                        vrt,
                        nodata_val,
                        tile_bounds["min_lat"],
                        tile_bounds["max_lat"],
                        tile_bounds["min_lon"],
                        tile_bounds["max_lon"],
                        grid_size,
                        grid_size,
                    )
                    if include_derivatives:
                        tri_core, tri_status, tri_meta = self._sample_physical_tri_grid(
                            vrt,
                            nodata_val,
                            tile_bounds["min_lat"],
                            tile_bounds["max_lat"],
                            tile_bounds["min_lon"],
                            tile_bounds["max_lon"],
                            grid_size,
                            grid_size,
                            radius_m=DEFAULT_TRI_PHYSICAL_RADIUS_M,
                            source_product_id=ds.product_id,
                            native_resolution_m=ds.horizontal_resolution_meters,
                        )
            else:
                padded_z, dx_m, dy_m = self._sample_dem_grid(
                    src,
                    nodata_val,
                    tile_bounds["min_lat"],
                    tile_bounds["max_lat"],
                    tile_bounds["min_lon"],
                    tile_bounds["max_lon"],
                    grid_size,
                    grid_size,
                )
                if include_derivatives:
                    tri_core, tri_status, tri_meta = self._sample_physical_tri_grid(
                        src,
                        nodata_val,
                        tile_bounds["min_lat"],
                        tile_bounds["max_lat"],
                        tile_bounds["min_lon"],
                        tile_bounds["max_lon"],
                        grid_size,
                        grid_size,
                        radius_m=DEFAULT_TRI_PHYSICAL_RADIUS_M,
                        source_product_id=ds.product_id,
                        native_resolution_m=ds.horizontal_resolution_meters,
                    )

        center_z = padded_z[1:-1, 1:-1]
        valid_bool = np.isfinite(center_z)
        valid_count = int(np.count_nonzero(valid_bool))
        nodata_count = int(center_z.size - valid_count)

        slope_list: Optional[List[Optional[float]]] = None
        tri_list: Optional[List[Optional[float]]] = None
        slope_max: Optional[float] = None
        if include_derivatives:
            padded_nodata = ~np.isfinite(padded_z)
            slope_pad, _ = calculate_slope(padded_z, dx_m, dy_m, nodata_mask=padded_nodata)
            slope_core = slope_pad[1:-1, 1:-1]
            slope_flat = slope_core.ravel()
            tri_flat = tri_core.ravel()
            slope_list = [round(float(v), 3) if np.isfinite(v) else None for v in slope_flat]
            tri_list = (
                [round(float(v), 3) if np.isfinite(v) else None for v in tri_flat]
                if tri_status == "valid"
                else None
            )
            s_fin = slope_flat[np.isfinite(slope_flat)]
            if s_fin.size > 0:
                slope_max = round(float(np.max(s_fin)), 3)
        else:
            tri_status = "not_requested"
            tri_meta = None

        # Local tangent-plane East/North meters relative to region origin (exact Mars sphere radius)
        west_dx, north_dy = angular_displacement_to_metric(
            manifest_origin_lat,
            tile_bounds["min_lon"] - manifest_origin_lon,
            tile_bounds["max_lat"] - manifest_origin_lat,
        )
        east_dx, south_dy = angular_displacement_to_metric(
            manifest_origin_lat,
            tile_bounds["max_lon"] - manifest_origin_lon,
            tile_bounds["min_lat"] - manifest_origin_lat,
        )
        # Preserve exact sign for East/North offset from origin
        d_lon_w = tile_bounds["min_lon"] - manifest_origin_lon
        d_lon_e = tile_bounds["max_lon"] - manifest_origin_lon
        d_lat_s = tile_bounds["min_lat"] - manifest_origin_lat
        d_lat_n = tile_bounds["max_lat"] - manifest_origin_lat
        m_per_deg_lon = MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(manifest_origin_lat)) * math.pi / 180.0
        m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
        local_bounds_m = {
            "min_east_m": round(d_lon_w * m_per_deg_lon, 3),
            "max_east_m": round(d_lon_e * m_per_deg_lon, 3),
            "min_north_m": round(d_lat_s * m_per_deg_lat, 3),
            "max_north_m": round(d_lat_n * m_per_deg_lat, 3),
        }

        flat_z = center_z.ravel()
        elev_list = [round(float(v), 3) if np.isfinite(v) else None for v in flat_z]
        mask_list = [1 if np.isfinite(v) else 0 for v in flat_z]
        z_valid = flat_z[valid_bool.ravel()]
        z_min = round(float(np.min(z_valid)), 3) if z_valid.size > 0 else None
        z_max = round(float(np.max(z_valid)), 3) if z_valid.size > 0 else None

        # Cross-tile continuous vertex normals computed from padded_z in Three.js (+X East, +Y Up, +Z South)
        step_dx_m = max(1e-3, (tile_bounds["max_lon"] - tile_bounds["min_lon"]) / float(max(1, grid_size - 1)) * m_per_deg_lon)
        step_dy_m = max(1e-3, (tile_bounds["max_lat"] - tile_bounds["min_lat"]) / float(max(1, grid_size - 1)) * m_per_deg_lat)
        z_c = center_z
        z_w = padded_z[1:-1, :-2]
        z_e = padded_z[1:-1, 2:]
        z_n = padded_z[:-2, 1:-1]
        z_s = padded_z[2:, 1:-1]

        fin_c = np.isfinite(z_c)
        fin_w = np.isfinite(z_w)
        fin_e = np.isfinite(z_e)
        fin_n = np.isfinite(z_n)
        fin_s = np.isfinite(z_s)

        dz_dx = np.where(
            fin_e & fin_w,
            (np.where(fin_e, z_e, 0.0) - np.where(fin_w, z_w, 0.0)) / (2.0 * step_dx_m),
            np.where(
                fin_e & fin_c,
                (np.where(fin_e, z_e, 0.0) - np.where(fin_c, z_c, 0.0)) / step_dx_m,
                np.where(
                    fin_c & fin_w,
                    (np.where(fin_c, z_c, 0.0) - np.where(fin_w, z_w, 0.0)) / step_dx_m,
                    0.0,
                ),
            ),
        )
        dz_dsouth = np.where(
            fin_s & fin_n,
            (np.where(fin_s, z_s, 0.0) - np.where(fin_n, z_n, 0.0)) / (2.0 * step_dy_m),
            np.where(
                fin_s & fin_c,
                (np.where(fin_s, z_s, 0.0) - np.where(fin_c, z_c, 0.0)) / step_dy_m,
                np.where(
                    fin_c & fin_n,
                    (np.where(fin_c, z_c, 0.0) - np.where(fin_n, z_n, 0.0)) / step_dy_m,
                    0.0,
                ),
            ),
        )
        nx = -dz_dx
        ny = np.ones_like(nx, dtype=np.float64)
        nz = -dz_dsouth
        n_len = np.sqrt(nx * nx + ny * ny + nz * nz)
        n_len = np.where(n_len > 1e-12, n_len, 1.0)
        normals_arr = np.stack((nx / n_len, ny / n_len, nz / n_len), axis=-1).reshape(-1)
        normals_list = [round(float(v), 5) for v in normals_arr]

        resp = TerrainMeshTileResponse(
            tile_id=tile_id.upper() if tile_id.lower() != "custom" else "CUSTOM",
            dataset_id=ds.id,
            product_id=ds.product_id,
            bounds=tile_bounds,
            origin={"lat": round(manifest_origin_lat, 7), "lon_east": round(manifest_origin_lon, 7)},
            local_bounds_m=local_bounds_m,
            grid_rows=grid_size,
            grid_cols=grid_size,
            sample_spacing_m={"dx_m": round(dx_m, 3), "dy_m": round(dy_m, 3)},
            native_resolution_m=ds.horizontal_resolution_meters,
            elevations_m=elev_list,
            valid_mask=mask_list,
            normals=normals_list,
            slope_deg=slope_list,
            roughness_tri_m=tri_list,
            tri_status=tri_status,
            tri_metadata=tri_meta,
            valid_vertex_count=valid_count,
            nodata_vertex_count=nodata_count,
            elevation_min_m=z_min,
            elevation_max_m=z_max,
            slope_max_deg=slope_max,
            generation_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )
        self._cache_put(cache_key, resp)
        return resp

    def get_heightgrid(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        dataset_id: Optional[str] = None,
        grid_size: int = 65,
    ) -> HeightGridResponse:
        """
        Return real DEM elevations for a Cesium terrain tile bounding box without
        fabricating heights outside local DEM coverage.
        """
        ds = self.resolve_dataset(dataset_id)
        if (
            max_lat <= ds.coverage.min_latitude
            or min_lat >= ds.coverage.max_latitude
            or max_lon <= ds.coverage.min_longitude
            or min_lon >= ds.coverage.max_longitude
        ):
            return HeightGridResponse(
                dataset_id=ds.id,
                product_id=ds.product_id,
                available=False,
                bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
                grid_rows=0,
                grid_cols=0,
                valid_fraction=0.0,
                nodata_fill_value=None,
                elevations_m=[],
                valid_mask=[],
                native_resolution_m=ds.horizontal_resolution_meters,
            )

        tile = self.get_mesh_tile(
            tile_id="custom",
            dataset_id=ds.id,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            grid_size=max(9, min(65, int(grid_size))),
            include_derivatives=False,
        )
        valid_frac = tile.valid_vertex_count / float(max(1, len(tile.elevations_m)))
        return HeightGridResponse(
            dataset_id=ds.id,
            product_id=ds.product_id,
            available=(tile.valid_vertex_count > 0),
            bounds=tile.bounds,
            grid_rows=tile.grid_rows,
            grid_cols=tile.grid_cols,
            valid_fraction=round(valid_frac, 4),
            nodata_fill_value=None,
            elevations_m=tile.elevations_m,
            valid_mask=tile.valid_mask,
            sample_spacing_m=tile.sample_spacing_m,
            native_resolution_m=tile.native_resolution_m,
            min_elevation_m=tile.elevation_min_m,
            max_elevation_m=tile.elevation_max_m,
        )

    def render_region_texture_png(
        self,
        dataset_id: str,
        overlay: str,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        size: int = 512,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        max_slope_deg: float = 20.0,
    ) -> bytes:
        """
        Render a georeferenced RGBA PNG texture clipped strictly to (min_lat, max_lat, min_lon, max_lon)
        for draping real HiRISE orthoimagery, derived elevation/slope/roughness layers, or
        Prompt 16 uncertainty/3-state traversability/observability overlays onto 3D mesh tiles.
        """
        size = max(64, min(1024, int(size)))
        overlay_l = overlay.strip().lower()
        uncertainty_overlays = {
            "uncertainty_status",
            "traversability_state",
            "observability",
            "slope_uncertainty_probe",
        }
        if overlay_l in uncertainty_overlays:
            return self._get_uncertainty_service().render_uncertainty_overlay_png(
                dataset_id=dataset_id,
                overlay=overlay_l,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                size=min(512, size),
                max_slope_deg=max_slope_deg,
                vmin=vmin,
                vmax=vmax,
            )
        if overlay_l not in {"ortho", "elevation", "slope", "roughness"}:
            raise ValueError(f"Unsupported texture overlay '{overlay}'.")

        from app.geospatial.spatial_delivery import compute_dataset_metadata_hash, compute_spatial_cache_digest

        vmin_tag = f"{vmin:.4f}" if vmin is not None else "auto"
        vmax_tag = f"{vmax:.4f}" if vmax is not None else "auto"
        ds_meta = self.catalog_service.get_dataset(dataset_id)
        cache_key = compute_spatial_cache_digest(
            dataset=ds_meta,
            dataset_id=dataset_id,
            algorithm=f"texture_{overlay_l}",
            algorithm_version="mesh_v2",
            parameters={
                "size": size,
                "vmin": vmin_tag,
                "vmax": vmax_tag,
                "max_slope_deg": round(float(max_slope_deg), 3),
            },
            bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
        ).composite_key
        cached = self._tracked_cache_get(cache_key)
        if cached is not None:
            return cached

        target_ds_id = dataset_id
        if overlay_l == "ortho":
            mapped = PAIRED_ORTHO_MAP.get(dataset_id)
            if mapped:
                target_ds_id = mapped

        ds = self._resolve_catalog_dataset(target_ds_id)
        if not ds:
            raise FileNotFoundError(f"Texture dataset '{target_ds_id}' not found.")
        open_path, lbl_path = _resolve_raw_dem_open_path(ds, self.raw_dir)
        if not open_path.exists():
            raise FileNotFoundError(f"Raster file missing locally for '{ds.id}'.")

        if overlay_l == "ortho":
            try:
                with rasterio.open(open_path) as src:
                    def _read_ortho(reader: Any) -> np.ndarray:
                        rb = reader.bounds
                        q_min_lon = min_lon + 360.0 if (rb.right > 180.0 and min_lon < 0.0) else min_lon
                        q_max_lon = max_lon + 360.0 if (rb.right > 180.0 and max_lon < 0.0) else max_lon
                        rgba = np.zeros((size, size, 4), dtype=np.uint8)
                        if q_max_lon <= rb.left or q_min_lon >= rb.right or max_lat <= rb.bottom or min_lat >= rb.top:
                            return rgba

                        # Continuous exact subpixel bilinear sampling matching tile UV grid [0..size-1]
                        lons = np.linspace(q_min_lon, q_max_lon, size, dtype=np.float64)
                        lats = np.linspace(max_lat, min_lat, size, dtype=np.float64)
                        inv_t = ~reader.transform
                        c_min_f = inv_t.a * float(lons[0]) + inv_t.b * float(lats[-1]) + inv_t.c
                        r_max_f = inv_t.d * float(lons[0]) + inv_t.e * float(lats[-1]) + inv_t.f
                        c_max_f = inv_t.a * float(lons[-1]) + inv_t.b * float(lats[0]) + inv_t.c
                        r_min_f = inv_t.d * float(lons[-1]) + inv_t.e * float(lats[0]) + inv_t.f

                        c0 = max(0, int(math.floor(min(c_min_f, c_max_f))) - 2)
                        c1 = min(reader.width, int(math.ceil(max(c_min_f, c_max_f))) + 3)
                        r0 = max(0, int(math.floor(min(r_min_f, r_max_f))) - 2)
                        r1 = min(reader.height, int(math.ceil(max(r_min_f, r_max_f))) + 3)
                        if c0 >= c1 or r0 >= r1:
                            return rgba

                        win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
                        patch = reader.read(1, window=win).astype(np.float64)
                        if reader.nodata is not None:
                            patch = np.where(patch == float(reader.nodata), np.nan, patch)
                        patch = np.where(patch <= 0.0, np.nan, patch)

                        patch_inv = ~(reader.window_transform(win))
                        center_lat = 0.5 * (min_lat + max_lat)
                        col_coords = patch_inv.a * lons + patch_inv.b * center_lat + patch_inv.c - 0.5
                        row_coords = patch_inv.d * float(lons[0]) + patch_inv.e * lats + patch_inv.f - 0.5

                        in_x = (col_coords >= 0.0) & (col_coords <= float(patch.shape[1] - 1))
                        in_y = (row_coords >= 0.0) & (row_coords <= float(patch.shape[0] - 1))
                        c_clamped = np.clip(col_coords, 0.0, max(0.0, float(patch.shape[1] - 1)))
                        r_clamped = np.clip(row_coords, 0.0, max(0.0, float(patch.shape[0] - 1)))

                        ci0 = np.floor(c_clamped).astype(np.int64)
                        ci1 = np.minimum(ci0 + 1, patch.shape[1] - 1)
                        ri0 = np.floor(r_clamped).astype(np.int64)
                        ri1 = np.minimum(ri0 + 1, patch.shape[0] - 1)
                        dc = (c_clamped - ci0)[None, :]
                        dr = (r_clamped - ri0)[:, None]

                        v00 = patch[np.ix_(ri0, ci0)]
                        v01 = patch[np.ix_(ri0, ci1)]
                        v10 = patch[np.ix_(ri1, ci0)]
                        v11 = patch[np.ix_(ri1, ci1)]
                        valid_4 = (np.isfinite(v00) & np.isfinite(v01) & np.isfinite(v10) & np.isfinite(v11)) & (in_y[:, None] & in_x[None, :])
                        interp = (
                            np.where(valid_4, v00, 0.0) * (1.0 - dr) * (1.0 - dc)
                            + np.where(valid_4, v01, 0.0) * (1.0 - dr) * dc
                            + np.where(valid_4, v10, 0.0) * dr * (1.0 - dc)
                            + np.where(valid_4, v11, 0.0) * dr * dc
                        )
                        val = np.clip(interp, 0.0, 255.0).astype(np.uint8)
                        rgba[..., 0] = val
                        rgba[..., 1] = np.clip(val * 0.92, 0, 255).astype(np.uint8)
                        rgba[..., 2] = np.clip(val * 0.84, 0, 255).astype(np.uint8)
                        rgba[..., 3] = np.where(valid_4, 255, 0).astype(np.uint8)
                        return rgba

                    if src.crs and src.crs.is_projected:
                        with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                            rgba = _read_ortho(vrt)
                    else:
                        rgba = _read_ortho(src)
            except rasterio.errors.RasterioError as exc:
                raise ValueError(f"Failed to decode orthophoto raster '{ds.id}' ({open_path.name}): {exc}") from exc
        else:
            # Sample mesh grid at texture resolution (max 129 for derivative ramp) cleanly
            tex_grid = min(129, max(65, size // 2))
            tile = self.get_mesh_tile(
                tile_id="custom",
                dataset_id=ds.id,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                grid_size=tex_grid,
                include_derivatives=(overlay_l != "elevation"),
            )
            arr_vals = (
                tile.elevations_m
                if overlay_l == "elevation"
                else (tile.slope_deg if overlay_l == "slope" else tile.roughness_tri_m)
            ) or tile.elevations_m
            arr = np.array([float(v) if v is not None else np.nan for v in arr_vals], dtype=np.float64).reshape(
                (tex_grid, tex_grid)
            )
            rgba_small = np.zeros((tex_grid, tex_grid, 4), dtype=np.uint8)
            fin = np.isfinite(arr)
            if np.any(fin):
                from app.geospatial.spatial_delivery import compute_dataset_metadata_hash

                default_stats = self._tracked_cache_get(f"stats_default:{ds.id}:{compute_dataset_metadata_hash(ds)}")
                if default_stats is None and (vmin is None or vmax is None):
                    b_ref = HIRISE_DEFAULT_FOCUS_BOUNDS.get(ds.id) or {
                        "min_lat": min_lat,
                        "max_lat": max_lat,
                        "min_lon": min_lon,
                        "max_lon": max_lon,
                    }
                    default_stats = self._get_region_render_stats(
                        ds.id,
                        b_ref["min_lat"],
                        b_ref["max_lat"],
                        b_ref["min_lon"],
                        b_ref["max_lon"],
                    )
                default_stats = default_stats or {}
                if overlay_l == "slope":
                    s_vmin = float(vmin) if vmin is not None else 0.0
                    s_vmax = float(vmax) if vmax is not None else 35.0
                    s_vmax = max(s_vmin + 1.0, s_vmax)
                    t = np.clip((np.where(fin, arr, s_vmin) - s_vmin) / (s_vmax - s_vmin), 0.0, 1.0)
                    r_ch, g_ch, b_ch = _apply_palette_lut(t, PALETTE_STOPS["slope"]["stops"])
                elif overlay_l == "roughness":
                    tri_r = default_stats.get("roughness_range_m") or {}
                    e_vmin = float(vmin) if vmin is not None else float(tri_r.get("min_m", 0.0))
                    e_vmax = float(vmax) if vmax is not None else float(tri_r.get("max_m", 5.0))
                    e_vmax = max(e_vmin + 0.1, e_vmax)
                    t = np.clip((np.where(fin, arr, e_vmin) - e_vmin) / (e_vmax - e_vmin), 0.0, 1.0)
                    r_ch, g_ch, b_ch = _apply_palette_lut(t, PALETTE_STOPS["roughness"]["stops"])
                else:
                    el_r = default_stats.get("elevation_range_m") or {}
                    e_vmin = float(vmin) if vmin is not None else float(el_r.get("min_m", np.nanmin(arr)))
                    e_vmax = float(vmax) if vmax is not None else float(el_r.get("max_m", np.nanmax(arr)))
                    e_vmax = max(e_vmin + 1.0, e_vmax)
                    t = np.clip((np.where(fin, arr, e_vmin) - e_vmin) / (e_vmax - e_vmin), 0.0, 1.0)
                    r_ch, g_ch, b_ch = _apply_palette_lut(t, PALETTE_STOPS["elevation"]["stops"])
                rgba_small[..., 0] = np.clip(r_ch, 0, 255).astype(np.uint8)
                rgba_small[..., 1] = np.clip(g_ch, 0, 255).astype(np.uint8)
                rgba_small[..., 2] = np.clip(b_ch, 0, 255).astype(np.uint8)
                rgba_small[..., 3] = np.where(fin, 255, 0).astype(np.uint8)

            img = Image.fromarray(rgba_small, mode="RGBA").resize((size, size), resample=Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            self._cache_put(cache_key, png_bytes)
            return png_bytes

        buf = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
        png_bytes = buf.getvalue()
        self._cache_put(cache_key, png_bytes)
        return png_bytes

    def _tracked_cache_get(self, key: str) -> Optional[Any]:
        val = self._cache_get(key)
        if val is not None:
            self._cache_hits = getattr(self, "_cache_hits", 0) + 1
        else:
            self._cache_misses = getattr(self, "_cache_misses", 0) + 1
        return val

    def get_cache_stats(self) -> Dict[str, Any]:
        lock = getattr(self, "_cache_lock", None)
        if lock is not None:
            with lock:
                keys = list(self._tile_cache.keys())
        else:
            keys = list(self._tile_cache.keys())
        return {
            "entries": len(keys),
            "max_entries": self._max_cache_items,
            "hits": int(getattr(self, "_cache_hits", 0)),
            "misses": int(getattr(self, "_cache_misses", 0)),
            "sample_keys": keys[-8:],
        }

    def invalidate_cache(self, dataset_id: Optional[str] = None) -> int:
        if not dataset_id:
            n = len(self._tile_cache)
            self.clear_cache()
            return n
        lock = getattr(self, "_cache_lock", None)
        removed = 0
        if lock is not None:
            with lock:
                doomed = [k for k in self._tile_cache.keys() if f":{dataset_id}:" in k or k.endswith(f":{dataset_id}")]
                for k in doomed:
                    self._tile_cache.pop(k, None)
                    removed += 1
        else:
            doomed = [k for k in list(self._tile_cache.keys()) if f":{dataset_id}:" in k or k.endswith(f":{dataset_id}")]
            for k in doomed:
                self._tile_cache.pop(k, None)
                removed += 1
        return removed
