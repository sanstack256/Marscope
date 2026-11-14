"""
MARSCOPE Data-Driven Map Layer Service & Tile Renderer
Martian Surface Intelligence & Exploration System

Discovers renderable and unavailable layers strictly from verified catalog datasets
and validated processing manifests in PROCESSED_DIR.
Never uses a static hardcoded list of available layers.
"""

from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image
import rasterio
from rasterio.windows import from_bounds
from app.geospatial.crs import normalize_longitude_180, validate_mars_crs
from app.geospatial.raster import RasterInspectionService
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.schemas.layer import LayerCatalogResponse, LayerLegend, LayerLegendStop, MapLayer


def _colorize_raster_band(data: np.ndarray, valid_mask: np.ndarray, layer_type: str, vmin: float, vmax: float) -> np.ndarray:
    """
    Convert a 2D numeric raster tile into RGBA uint8 image.
    No-data / out-of-bounds pixels receive alpha=0 (transparent).
    """
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if not np.any(valid_mask):
        return rgba

    span = vmax - vmin if vmax > vmin else 1.0
    norm = np.clip((data - vmin) / span, 0.0, 1.0)

    if layer_type == "slope":
        # Safe emerald (0) -> amber (0.5) -> critical crimson (1.0)
        r = np.where(norm < 0.5, norm * 2.0 * 245.0, 245.0)
        g = np.where(norm < 0.5, 190.0 - norm * 0.4 * 190.0, 190.0 - (norm - 0.5) * 2.0 * 165.0)
        b = np.where(norm < 0.5, 95.0 * (1.0 - norm * 2.0), 40.0)
    elif layer_type == "roughness":
        # Slate blue (0) -> amber (0.6) -> bright red (1.0)
        r = 40.0 + norm * 210.0
        g = np.where(norm < 0.6, 130.0 + norm * 80.0, 210.0 - (norm - 0.6) * 2.5 * 170.0)
        b = np.where(norm < 0.5, 220.0 * (1.0 - norm * 2.0), 30.0)
    elif layer_type == "aspect":
        # Compass azimuth ramp [0, 360), flat -1 rendered cool slate
        flat = data < 0.0
        ang = np.clip(data / 360.0, 0.0, 1.0)
        r = np.where(flat, 90.0, 128.0 + 115.0 * np.sin(2.0 * np.pi * ang))
        g = np.where(flat, 100.0, 128.0 + 115.0 * np.sin(2.0 * np.pi * ang + 2.094))
        b = np.where(flat, 115.0, 128.0 + 115.0 * np.sin(2.0 * np.pi * ang + 4.188))
    else:
        # Elevation / topography hypsometric tint: navy -> rust -> ochre -> cream
        r = np.clip(45.0 + norm * 205.0, 0, 255)
        g = np.clip(40.0 + np.sin(norm * np.pi * 0.85) * 165.0 + norm * 35.0, 0, 255)
        b = np.clip(110.0 * (1.0 - norm * 0.75) + (norm**2) * 140.0, 0, 255)

    rgba[..., 0] = np.where(valid_mask, np.clip(r, 0, 255).astype(np.uint8), 0)
    rgba[..., 1] = np.where(valid_mask, np.clip(g, 0, 255).astype(np.uint8), 0)
    rgba[..., 2] = np.where(valid_mask, np.clip(b, 0, 255).astype(np.uint8), 0)
    rgba[..., 3] = np.where(valid_mask, 215, 0)
    return rgba


def _legend_for_layer(layer_type: str, units: str, vmin: Optional[float], vmax: Optional[float]) -> LayerLegend:
    if layer_type == "slope":
        return LayerLegend(
            title="Surface Slope Gradient",
            units=units,
            min_value=vmin,
            max_value=vmax,
            stops=[
                LayerLegendStop(value="0°", color="#22c55e", label="Level / Low Risk"),
                LayerLegendStop(value="15°", color="#f59e0b", label="Moderate Grade"),
                LayerLegendStop(value="25°+", color="#ef4444", label="Critical Limit"),
            ],
        )
    if layer_type == "roughness":
        return LayerLegend(
            title="Terrain Ruggedness Index (TRI)",
            units=units,
            min_value=vmin,
            max_value=vmax,
            stops=[
                LayerLegendStop(value="Low", color="#38bdf8", label="Smooth Surface"),
                LayerLegendStop(value="Med", color="#f59e0b", label="Moderately Broken"),
                LayerLegendStop(value="High", color="#ef4444", label="High Relief"),
            ],
        )
    if layer_type == "aspect":
        return LayerLegend(
            title="Steepest Descent Aspect",
            units=units,
            min_value=0.0,
            max_value=360.0,
            stops=[
                LayerLegendStop(value="0° N", color="#38bdf8", label="North"),
                LayerLegendStop(value="90° E", color="#34d399", label="East"),
                LayerLegendStop(value="180° S", color="#f59e0b", label="South"),
                LayerLegendStop(value="270° W", color="#c084fc", label="West"),
            ],
        )
    return LayerLegend(
        title="Elevation Relative to Datum",
        units=units,
        min_value=vmin,
        max_value=vmax,
        stops=[
            LayerLegendStop(value=f"{round(vmin, 0) if vmin is not None else '--'} m", color="#2d286e", label="Basin Low"),
            LayerLegendStop(value="Mid", color="#d46238", label="Flank / Bench"),
            LayerLegendStop(value=f"{round(vmax, 0) if vmax is not None else '--'} m", color="#f2dfc4", label="High Relief"),
        ],
    )


class LayerCatalogService:
    def __init__(self, catalog_service: DatasetCatalogService, processed_dir: Path, raw_dir: Path):
        self.catalog_service = catalog_service
        self.processed_dir = processed_dir
        self.raw_dir = raw_dir
        self._raster_layer_files: Dict[str, Dict[str, Any]] = {}

    def build_layer_catalog(self) -> LayerCatalogResponse:
        """
        Discover available (renderable) and unavailable layers strictly from
        verified catalog entries and validated processing manifests.
        """
        available: List[MapLayer] = []
        unavailable: List[MapLayer] = []
        self._raster_layer_files.clear()

        datasets = self.catalog_service.list_datasets()
        processed_manifests: Dict[str, Dict[str, Any]] = {}
        for mpath in sorted(self.processed_dir.glob("*.processing.json")):
            try:
                pdata = json.loads(mpath.read_text(encoding="utf-8"))
                ds_id = pdata.get("source_dataset_id")
                if ds_id:
                    processed_manifests[ds_id] = pdata
            except Exception:
                continue

        for ds in datasets:
            is_wmts = "{" in ds.original_product_url

            # 1. Remote WMTS products (renderable only if remote archive/capabilities verified & CRS valid)
            if is_wmts:
                crs_ok = validate_mars_crs(ds.coordinate_reference_system)
                remote_verified = ds.verification.archive_availability == VerificationState.VERIFIED
                bounds = [
                    ds.coverage.min_longitude,
                    ds.coverage.min_latitude,
                    ds.coverage.max_longitude,
                    ds.coverage.max_latitude,
                ]
                is_topo_viz = "shaded" in ds.product_type.lower() or "mola" in ds.id.lower()
                layer = MapLayer(
                    layer_id=ds.id,
                    display_name=ds.product_title,
                    layer_type="topography_wmts" if is_topo_viz else "optical_wmts",
                    category="topography" if is_topo_viz else "optical",
                    source_dataset_id=ds.id,
                    source_product_id=ds.product_id,
                    data_type=ds.data_format,
                    units=ds.units,
                    crs=ds.coordinate_reference_system or "unknown",
                    spatial_bounds=bounds,
                    spatial_resolution_m=ds.horizontal_resolution_meters,
                    acquisition_date=ds.acquisition_timestamp,
                    processing_level=ds.processing_level,
                    processing_version="wmts-1.0.0",
                    valid_data_coverage_pct=100.0 if remote_verified else None,
                    nodata_coverage_pct=0.0 if remote_verified else None,
                    attribution=ds.attribution,
                    license=ds.license.value,
                    verification_state=ds.verification.archive_availability,
                    renderable=bool(crs_ok and remote_verified),
                    rendering_endpoint=ds.original_product_url if (crs_ok and remote_verified) else None,
                    tile_scheme="geographic_wmts" if (crs_ok and remote_verified) else None,
                    maximum_zoom=7,
                    default_visible=(ds.id == "mars_trek_viking_color" and remote_verified),
                    default_opacity=1.0 if not is_topo_viz else 0.65,
                    known_limitations=ds.known_limitations,
                    unavailable_reason=(
                        None
                        if (crs_ok and remote_verified)
                        else "Remote WMTS capabilities not verified live yet (run remote capability verification)."
                    ),
                )
                if layer.renderable:
                    available.append(layer)
                else:
                    unavailable.append(layer)
                continue

            # 2. Local processed raster derivatives (elevation, slope, aspect, roughness)
            if ds.id in processed_manifests and "DEM" in ds.product_type.upper():
                p_manifest = processed_manifests[ds.id]
                files_map = p_manifest.get("files", {})
                summary_data = p_manifest.get("summary", {})
                layer_specs = [
                    ("dem", f"{ds.id}_dem", f"{ds.product_title} — Elevation", "elevation_raster", "topography", "meters"),
                    ("slope", f"{ds.id}_slope", f"Slope Gradient ({ds.product_id})", "slope_raster", "derived", "degrees"),
                    ("aspect", f"{ds.id}_aspect", f"Slope Aspect ({ds.product_id})", "aspect_raster", "derived", "degrees_clockwise_north"),
                    ("roughness", f"{ds.id}_roughness", f"Terrain Ruggedness TRI ({ds.product_id})", "roughness_raster", "derived", "meters"),
                ]
                for file_key, lid, label, ltype, cat, expected_units in layer_specs:
                    fname = files_map.get(file_key)
                    if not fname:
                        continue
                    fpath = self.processed_dir / fname
                    if not fpath.exists():
                        unavailable.append(
                            MapLayer(
                                layer_id=lid,
                                display_name=label,
                                layer_type=ltype,
                                category=cat,
                                source_dataset_id=ds.id,
                                source_product_id=ds.product_id,
                                data_type="GeoTIFF float32",
                                units=expected_units,
                                crs=p_manifest.get("crs") or "unknown",
                                spatial_bounds=[0, 0, 0, 0],
                                processing_level=ds.processing_level,
                                processing_version=p_manifest.get("manifest_version", "1.1.0"),
                                attribution=ds.attribution,
                                license=ds.license.value,
                                verification_state=VerificationState.FAILED,
                                renderable=False,
                                unavailable_reason=f"Referenced processed file '{fname}' is missing from disk.",
                            )
                        )
                        continue

                    try:
                        insp = RasterInspectionService.inspect_raster_file(fpath)
                        stats = insp["stats"]
                        if not insp["crs_verified"] or not insp["units_verified"] or not stats["available"]:
                            raise ValueError("Raster failed CRS, units, or valid-pixel verification.")

                        bounds = insp["bounds"]
                        # Normalize bounds to [-180, 180] for tile indexing if 0..360
                        b_left = normalize_longitude_180(bounds[0]) if bounds[2] > 180.0 and bounds[0] >= 180.0 else bounds[0]
                        b_right = normalize_longitude_180(bounds[2]) if bounds[2] > 180.0 else bounds[2]
                        if b_right < b_left:
                            norm_bounds = [bounds[0], bounds[1], bounds[2], bounds[3]]
                        else:
                            norm_bounds = [b_left, bounds[1], b_right, bounds[3]]

                        vmin = stats["min_value"]
                        vmax = stats["max_value"]
                        valid_pct = stats["valid_data_percentage"]
                        res_m = summary_data.get("resolution_meters_per_pixel") or ds.horizontal_resolution_meters

                        self._raster_layer_files[lid] = {
                            "path": fpath,
                            "layer_type": file_key,
                            "vmin": vmin,
                            "vmax": vmax,
                            "bounds": bounds,
                        }

                        available.append(
                            MapLayer(
                                layer_id=lid,
                                display_name=label,
                                layer_type=ltype,
                                category=cat,
                                source_dataset_id=ds.id,
                                source_product_id=ds.product_id,
                                data_type=f"GeoTIFF ({','.join(insp['data_types'])})",
                                units=insp["units"],
                                crs=insp["crs"],
                                spatial_bounds=norm_bounds,
                                spatial_resolution_m=res_m,
                                acquisition_date=ds.acquisition_timestamp,
                                processing_level=ds.processing_level,
                                processing_version=p_manifest.get("manifest_version", "1.1.0"),
                                valid_data_coverage_pct=valid_pct,
                                nodata_coverage_pct=round(100.0 - valid_pct, 2),
                                attribution=ds.attribution,
                                license=ds.license.value,
                                verification_state=VerificationState.VERIFIED,
                                renderable=True,
                                rendering_endpoint=f"/api/layers/{lid}/tiles/{{z}}/{{x}}/{{y}}.png",
                                tile_scheme="geographic_wmts",
                                maximum_zoom=10,
                                default_visible=(file_key == "dem"),
                                default_opacity=0.7,
                                known_limitations=ds.known_limitations,
                                legend=_legend_for_layer(file_key, insp["units"], vmin, vmax),
                            )
                        )
                    except Exception as exc:
                        unavailable.append(
                            MapLayer(
                                layer_id=lid,
                                display_name=label,
                                layer_type=ltype,
                                category=cat,
                                source_dataset_id=ds.id,
                                source_product_id=ds.product_id,
                                data_type="GeoTIFF",
                                units="unknown",
                                crs="unknown",
                                spatial_bounds=[0, 0, 0, 0],
                                processing_level=ds.processing_level,
                                processing_version=p_manifest.get("manifest_version", "1.1.0"),
                                attribution=ds.attribution,
                                license=ds.license.value,
                                verification_state=VerificationState.FAILED,
                                renderable=False,
                                unavailable_reason=f"Processed raster validation failed: {exc}",
                            )
                        )
            else:
                # Discovered but not processed/acquired locally -> explicitly unavailable as a map layer
                unavailable.append(
                    MapLayer(
                        layer_id=ds.id,
                        display_name=ds.product_title,
                        layer_type="unprocessed_product",
                        category="topography" if "DEM" in ds.product_type.upper() else "rover",
                        source_dataset_id=ds.id,
                        source_product_id=ds.product_id,
                        data_type=ds.data_format,
                        units=ds.units,
                        crs=ds.coordinate_reference_system or "unknown",
                        spatial_bounds=[
                            ds.coverage.min_longitude,
                            ds.coverage.min_latitude,
                            ds.coverage.max_longitude,
                            ds.coverage.max_latitude,
                        ],
                        spatial_resolution_m=ds.horizontal_resolution_meters,
                        acquisition_date=ds.acquisition_timestamp,
                        processing_level=ds.processing_level,
                        processing_version="unprocessed",
                        attribution=ds.attribution,
                        license=ds.license.value,
                        verification_state=ds.verification.processing_verification,
                        renderable=False,
                        known_limitations=ds.known_limitations,
                        unavailable_reason=(
                            f"Dataset '{ds.id}' is in status '{ds.status.value}' and has not been "
                            "processed into a validated renderable map layer."
                        ),
                    )
                )

        return LayerCatalogResponse(
            available_layers=available,
            unavailable_layers=unavailable,
            total_available=len(available),
            total_unavailable=len(unavailable),
        )

    def get_layer_metadata(self, layer_id: str) -> Optional[MapLayer]:
        catalog = self.build_layer_catalog()
        for layer in catalog.available_layers + catalog.unavailable_layers:
            if layer.layer_id == layer_id:
                return layer
        return None

    def render_tile_png(self, layer_id: str, z: int, x: int, y: int) -> Optional[bytes]:
        """
        Render a 256x256 GeographicTilingScheme (2:1 Mars Equirectangular) RGBA PNG tile
        from a verified local GeoTIFF raster layer. Returns transparent tile or None if outside bounds.
        """
        if not self._raster_layer_files:
            self.build_layer_catalog()

        spec = self._raster_layer_files.get(layer_id)
        if not spec:
            return None

        if z < 0 or z > 14:
            return None

        # GeographicTilingScheme at level z: matrixWidth = 2 * 2^z, matrixHeight = 2^z
        matrix_w = 2 * (1 << z)
        matrix_h = 1 << z
        if x < 0 or x >= matrix_w or y < 0 or y >= matrix_h:
            return None

        lon_span = 360.0 / matrix_w
        lat_span = 180.0 / matrix_h
        tile_min_lon = -180.0 + x * lon_span
        tile_max_lon = tile_min_lon + lon_span
        tile_max_lat = 90.0 - y * lat_span
        tile_min_lat = tile_max_lat - lat_span

        fpath: Path = spec["path"]
        return _cached_geotiff_tile(
            str(fpath),
            int(fpath.stat().st_mtime_ns),
            spec["layer_type"],
            float(spec["vmin"]),
            float(spec["vmax"]),
            tile_min_lon,
            tile_min_lat,
            tile_max_lon,
            tile_max_lat,
        )


@lru_cache(maxsize=256)
def _cached_geotiff_tile(
    file_path_str: str,
    mtime_ns: int,
    layer_type: str,
    vmin: float,
    vmax: float,
    t_min_lon: float,
    t_min_lat: float,
    t_max_lon: float,
    t_max_lat: float,
) -> bytes:
    """Slice, resample (nearest-neighbor to avoid inventing new surface detail), and colorize a 256x256 PNG tile."""
    with rasterio.open(file_path_str) as src:
        sb = src.bounds
        q_min_lon, q_max_lon = t_min_lon, t_max_lon
        if sb.right > 180.0 and q_min_lon < 0.0:
            q_min_lon = q_min_lon % 360.0
            q_max_lon = q_max_lon % 360.0
            if q_max_lon <= q_min_lon:
                q_max_lon = 360.0

        # Intersection check
        i_left = max(q_min_lon, sb.left)
        i_right = min(q_max_lon, sb.right)
        i_bottom = max(t_min_lat, sb.bottom)
        i_top = min(t_max_lat, sb.top)

        if i_left >= i_right or i_bottom >= i_top:
            empty = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            buf = BytesIO()
            empty.save(buf, format="PNG")
            return buf.getvalue()

        # Sample 256x256 nearest-pixel centers directly within tile coordinates
        lon_centers = np.linspace(q_min_lon + (q_max_lon - q_min_lon) / 512.0, q_max_lon - (q_max_lon - q_min_lon) / 512.0, 256)
        lat_centers = np.linspace(t_max_lat - (t_max_lat - t_min_lat) / 512.0, t_min_lat + (t_max_lat - t_min_lat) / 512.0, 256)

        # Read bounding window covering intersection
        win = from_bounds(i_left, i_bottom, i_right, i_top, src.transform)
        r0 = max(0, int(np.floor(win.row_off)))
        c0 = max(0, int(np.floor(win.col_off)))
        r1 = min(src.height, int(np.ceil(win.row_off + win.height)))
        c1 = min(src.width, int(np.ceil(win.col_off + win.width)))
        if r1 <= r0 or c1 <= c0:
            empty = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            buf = BytesIO()
            empty.save(buf, format="PNG")
            return buf.getvalue()

        win_data = src.read(1, window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float64)
        nodata = src.nodatavals[0]
        inv = src.transform

        # Map tile pixel centers into local window indices without interpolation
        col_coords = ((lon_centers - inv.c) / inv.a).astype(np.int32) - c0
        row_coords = ((lat_centers - inv.f) / inv.e).astype(np.int32) - r0

        in_col = (col_coords >= 0) & (col_coords < win_data.shape[1])
        in_row = (row_coords >= 0) & (row_coords < win_data.shape[0])

        safe_c = np.clip(col_coords, 0, win_data.shape[1] - 1)
        safe_r = np.clip(row_coords, 0, win_data.shape[0] - 1)

        tile_arr = win_data[np.ix_(safe_r, safe_c)]
        in_bounds_mask = np.outer(in_row, in_col)
        valid_mask = in_bounds_mask & np.isfinite(tile_arr)
        if nodata is not None and np.isfinite(nodata):
            valid_mask &= tile_arr != float(nodata)

        rgba = _colorize_raster_band(tile_arr, valid_mask, layer_type, vmin, vmax)
        img = Image.fromarray(rgba, mode="RGBA")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
