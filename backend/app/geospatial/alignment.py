"""
MARSCOPE Raster Alignment & Windowed Clipping Service
Martian Surface Intelligence & Exploration System

Performs memory-efficient windowed extraction of regional study areas from global/regional planetary rasters.
Validates CRS and preserves authoritative measurement units in GeoTIFF tags.
"""

from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict, Optional
import rasterio
from rasterio.crs import CRS
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from app.geospatial.crs import CRSError, get_mars_crs, validate_mars_crs


def clip_raster_to_bounding_box(
    source_raster_path: Path,
    output_geotiff_path: Path,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    output_crs_str: Optional[str] = None,
    units: Optional[str] = None,
    source_dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract a sub-region from source_raster_path strictly bounded by [min_lon, min_lat, max_lon, max_lat].
    Writes output GeoTIFF with verified Mars CRS, affine georeferencing, tags, and no-data mask.
    Rejects unreferenced source rasters or unsupported CRS definitions.
    """
    if not source_raster_path.exists():
        raise FileNotFoundError(f"Source raster not found: {source_raster_path}")

    output_geotiff_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(source_raster_path) as src:
        if src.crs is None:
            raise CRSError(f"Source raster '{source_raster_path.name}' is unreferenced (no CRS). Cannot clip safely.")
        src_crs_str = src.crs.to_string()
        if not validate_mars_crs(src_crs_str):
            raise CRSError(f"Source raster CRS '{src_crs_str}' is not a valid Martian coordinate system.")

        target_crs_str = output_crs_str or src_crs_str
        if not validate_mars_crs(target_crs_str):
            raise CRSError(f"Requested output CRS '{target_crs_str}' is invalid for Mars.")

        pyproj_crs = get_mars_crs(target_crs_str)
        rio_crs = CRS.from_wkt(pyproj_crs.to_wkt())
        src_is_projected = bool(src.crs and src.crs.is_projected)
        need_warp = src_is_projected or (src.crs != rio_crs and not src.crs.is_geographic)

        with ExitStack() as stack:
            reader = src
            # Reproject in-memory via WarpedVRT only when source CRS is projected or differs meaningfully
            if need_warp:
                reader = stack.enter_context(WarpedVRT(src, crs=rio_crs))

            # Handle [0, 360] vs [-180, 180] longitude convention if reader is 0..360
            s_bounds = reader.bounds
            clip_min_lon = min_lon
            clip_max_lon = max_lon
            if s_bounds.right > 180.0 and min_lon < 0.0:
                clip_min_lon = min_lon % 360.0
                clip_max_lon = max_lon % 360.0

            # Check overlap with source bounds
            if (
                clip_max_lon <= s_bounds.left
                or clip_min_lon >= s_bounds.right
                or max_lat <= s_bounds.bottom
                or min_lat >= s_bounds.top
            ):
                raise ValueError(
                    f"Requested bounding box [{clip_min_lon}, {min_lat}, {clip_max_lon}, {max_lat}] "
                    f"does not overlap source raster bounds [{s_bounds.left}, {s_bounds.bottom}, {s_bounds.right}, {s_bounds.top}]."
                )

            # Constrain window inside raster bounds
            eff_left = max(clip_min_lon, s_bounds.left)
            eff_bottom = max(min_lat, s_bounds.bottom)
            eff_right = min(clip_max_lon, s_bounds.right)
            eff_top = min(max_lat, s_bounds.top)

            window = from_bounds(eff_left, eff_bottom, eff_right, eff_top, reader.transform)
            window = window.round_offsets().round_lengths()
            if window.width < 1 or window.height < 1:
                raise ValueError("Clipped window has zero width or height.")

            window_data = reader.read(1, window=window)
            window_transform = reader.window_transform(window)
            nodata_val = reader.nodatavals[0] if reader.nodatavals and reader.nodatavals[0] is not None else -32768.0

            profile = reader.profile.copy()
            if not profile.get("tiled", False):
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
            profile.update({
                "driver": "GTiff",
                "height": int(window.height),
                "width": int(window.width),
                "transform": window_transform,
                "count": 1,
                "nodata": nodata_val,
                "crs": rio_crs,
            })

            with rasterio.open(output_geotiff_path, "w", **profile) as dst:
                dst.write(window_data, 1)
                tags = {}
                if units:
                    tags["VERTICAL_UNITS"] = units
                    tags["UNITS"] = units
                    dst.set_band_unit(1, units)
                if source_dataset_id:
                    tags["SOURCE_DATASET_ID"] = source_dataset_id
                if tags:
                    dst.update_tags(**tags)
                    dst.update_tags(1, **tags)

            return {
                "output_path": str(output_geotiff_path),
                "dimensions": {"width": int(window.width), "height": int(window.height)},
                "bounds": [eff_left, eff_bottom, eff_right, eff_top],
                "crs": target_crs_str,
                "pixel_count": int(window.width * window.height),
                "nodata_value": nodata_val,
                "units": units or "unknown",
            }
