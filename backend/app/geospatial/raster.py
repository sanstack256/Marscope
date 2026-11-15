"""
MARSCOPE Raster Inspection Service
Martian Surface Intelligence & Exploration System

Uses Rasterio, NumPy, and PDS3 label metadata to inspect planetary rasters.
Never infers measurement units from filenames and never converts missing data to zero.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
import rasterio
from app.geospatial.crs import validate_mars_crs
from app.ingestion.pds_label import extract_pds3_metadata
from app.schemas.terrain import RasterBandStats


class RasterMetadataError(ValueError):
    """Raised when raster CRS, units, or structure cannot be validated."""


class RasterInspectionService:
    @staticmethod
    def _extract_units_from_metadata(
        src: rasterio.DatasetReader,
        file_path: Path,
        band_index: int,
        explicit_units: Optional[str] = None,
    ) -> tuple[str, bool, Optional[str]]:
        """
        Determine physical measurement units strictly from authoritative metadata:
        1) Explicit caller/manifest metadata
        2) GeoTIFF native band units or metadata tags
        3) Sibling PDS3 .lbl/.LBL label file
        Never infers units from the raster filename.
        """
        if explicit_units and explicit_units.strip().lower() not in {"unknown", "none", ""}:
            return explicit_units.strip(), True, "manifest_or_caller"

        # GeoTIFF native units tuple
        src_units = src.units[band_index - 1] if src.units and len(src.units) >= band_index else None
        if src_units and str(src_units).strip().lower() not in {"unknown", "none", ""}:
            return str(src_units).strip(), True, "geotiff_band_units"

        # GeoTIFF tags (file level + band level)
        tags = {}
        tags.update(src.tags() or {})
        tags.update(src.tags(band_index) or {})
        for tag_key in ["VERTICAL_UNITS", "MEASUREMENT_UNITS", "UNIT", "UNITS", "UNITTYPE"]:
            tag_val = tags.get(tag_key)
            if tag_val and str(tag_val).strip().lower() not in {"unknown", "none", ""}:
                return str(tag_val).strip(), True, f"geotiff_tag:{tag_key}"

        # Sibling PDS3 label (.lbl / .LBL)
        for ext in [".lbl", ".LBL"]:
            lbl_path = file_path.with_suffix(ext)
            if lbl_path.exists():
                try:
                    pds_meta = extract_pds3_metadata(lbl_path)
                    if pds_meta.get("units") and pds_meta["units"] != "unknown":
                        return str(pds_meta["units"]), True, f"pds3_label:{lbl_path.name}"
                except Exception:
                    pass
        if file_path.suffix.lower() == ".lbl":
            try:
                pds_meta = extract_pds3_metadata(file_path)
                if pds_meta.get("units") and pds_meta["units"] != "unknown":
                    return str(pds_meta["units"]), True, f"pds3_label:{file_path.name}"
            except Exception:
                pass

        return "unknown", False, None

    @staticmethod
    def inspect_raster_file(
        file_path: Path,
        band_index: int = 1,
        explicit_units: Optional[str] = None,
        max_sample_pixels: int = 4_000_000,
    ) -> Dict[str, Any]:
        """
        Inspect a GeoTIFF or supported planetary raster, computing valid-pixel statistics
        and extracting documented CRS, pixel spacing, scale/offset, and unit metadata.
        Large rasters (> max_sample_pixels) use nearest-neighbor decimated reads for stats
        without inflating full-resolution arrays in RAM.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Raster file not found: {file_path}")

        with rasterio.open(file_path) as src:
            if band_index < 1 or band_index > src.count:
                raise RasterMetadataError(f"Requested band {band_index} out of range [1, {src.count}].")

            width = src.width
            height = src.height
            count = src.count
            if width <= 0 or height <= 0 or count <= 0:
                raise RasterMetadataError(f"Invalid raster dimensions ({width}x{height}, bands={count}).")
            dtypes = [src.dtypes[i] for i in range(count)]
            bounds = src.bounds
            transform = list(src.transform)
            pixel_spacing = {"dx": abs(float(src.transform.a)), "dy": abs(float(src.transform.e))}
            nodata = src.nodatavals[band_index - 1]

            # Physical unit extraction — never infer from filename
            units, units_verified, unit_source = RasterInspectionService._extract_units_from_metadata(
                src, file_path, band_index, explicit_units=explicit_units
            )

            # Scaling/offset metadata: never invent 1.0/0.0 when integer raster lacks label/TIFF calibration tags
            raw_scale = float(src.scales[band_index - 1]) if src.scales and len(src.scales) >= band_index else None
            raw_offset = float(src.offsets[band_index - 1]) if src.offsets and len(src.offsets) >= band_index else None
            pds_scale: Optional[float] = None
            pds_offset: Optional[float] = None
            for ext in (".lbl", ".LBL"):
                lbl_path = file_path.with_suffix(ext)
                if lbl_path.exists():
                    try:
                        pds_meta = extract_pds3_metadata(lbl_path)
                        if pds_meta.get("scaling_factor") is not None:
                            pds_scale = float(pds_meta["scaling_factor"])
                        if pds_meta.get("offset") is not None:
                            pds_offset = float(pds_meta["offset"])
                        break
                    except Exception:
                        pass

            band_dtype = str(dtypes[band_index - 1]).lower()
            is_float_raster = "float" in band_dtype
            tags_all = {**(src.tags() or {}), **(src.tags(band_index) or {})}
            has_tiff_scale_tag = any(k in tags_all for k in ("SCALING_FACTOR", "OFFSET", "SCALE", "UNIT"))
            if pds_scale is not None:
                scale: Optional[float] = pds_scale
                offset: Optional[float] = pds_offset if pds_offset is not None else 0.0
                scaling_verified = True
            elif is_float_raster and units_verified:
                scale = raw_scale if raw_scale is not None else 1.0
                offset = raw_offset if raw_offset is not None else 0.0
                scaling_verified = True
            elif has_tiff_scale_tag and raw_scale is not None:
                scale = raw_scale
                offset = raw_offset if raw_offset is not None else 0.0
                scaling_verified = True
            else:
                scale = None
                offset = None
                scaling_verified = False

            # CRS extraction — never fabricate a CRS for unreferenced files
            raw_crs_str = src.crs.to_string() if src.crs else None
            crs_verified = validate_mars_crs(raw_crs_str)

            # Read raw band (bounded memory via nearest-neighbor decimation on huge rasters)
            total_pixels = width * height
            stats_sampled = False
            sampling_stride = 1
            if total_pixels > max_sample_pixels and max_sample_pixels > 0:
                import math
                from rasterio.enums import Resampling

                sampling_stride = max(2, int(math.ceil(math.sqrt(total_pixels / float(max_sample_pixels)))))
                out_h = max(1, height // sampling_stride)
                out_w = max(1, width // sampling_stride)
                raw_data = src.read(
                    band_index,
                    out_shape=(out_h, out_w),
                    resampling=Resampling.nearest,
                ).astype(np.float64)
                stats_sampled = True
            else:
                raw_data = src.read(band_index).astype(np.float64)

            invalid_mask = ~np.isfinite(raw_data)
            if nodata is not None and np.isfinite(nodata):
                invalid_mask = invalid_mask | (raw_data == float(nodata))

            if scale is not None and offset is not None:
                scaled_data = np.where(invalid_mask, np.nan, raw_data * scale + offset)
            else:
                # Scaling metadata missing on raw integer DN/untagged raster — do not fabricate 1.0/0.0 scaling
                scaled_data = np.full(raw_data.shape, np.nan, dtype=np.float64)
            valid_pixels = scaled_data[~np.isnan(scaled_data)]
            sampled_total = int(raw_data.size)
            valid_count = int(valid_pixels.size)
            nodata_count = int(sampled_total - valid_count)
            valid_pct = (valid_count / sampled_total * 100.0) if sampled_total > 0 else 0.0

            if valid_count > 0:
                stats = RasterBandStats(
                    available=True,
                    min_value=float(np.min(valid_pixels)),
                    max_value=float(np.max(valid_pixels)),
                    mean_value=float(np.mean(valid_pixels)),
                    std_dev=float(np.std(valid_pixels)),
                    valid_pixel_count=valid_count,
                    nodata_pixel_count=nodata_count,
                    valid_data_percentage=round(valid_pct, 2),
                    units=units,
                )
            else:
                stats = RasterBandStats(
                    available=False,
                    min_value=None,
                    max_value=None,
                    mean_value=None,
                    std_dev=None,
                    valid_pixel_count=0,
                    nodata_pixel_count=nodata_count,
                    valid_data_percentage=0.0,
                    units=units,
                )

            return {
                "file_name": file_path.name,
                "file_size_bytes": file_path.stat().st_size,
                "dimensions": {"width": width, "height": height},
                "band_count": count,
                "band_index": band_index,
                "data_types": dtypes,
                "bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
                "crs": raw_crs_str,
                "crs_verified": crs_verified,
                "transform": transform[:6],
                "pixel_spacing": pixel_spacing,
                "scale": scale,
                "offset": offset,
                "scaling_verified": scaling_verified,
                "nodata_value": nodata,
                "units": units,
                "units_verified": units_verified,
                "unit_source": unit_source,
                "band_tags": src.tags(band_index) or {},
                "dataset_tags": src.tags() or {},
                "stats": stats.model_dump(),
                "stats_sampled": stats_sampled,
                "stats_sampling_stride": sampling_stride,
            }
