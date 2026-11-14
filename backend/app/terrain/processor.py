"""
MARSCOPE DEM Processing & Manifested Derivative Pipeline
Martian Surface Intelligence & Exploration System

Processes validated raw elevation datasets into clipped study-area GeoTIFFs and
derivative Slope, Aspect, and Roughness (TRI) products with verifiable processing manifests.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
import rasterio
from rasterio.crs import CRS
from app.geospatial.alignment import clip_raster_to_bounding_box
from app.geospatial.crs import angular_displacement_to_metric, get_mars_crs, validate_mars_crs
from app.geospatial.raster import RasterInspectionService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.terrain.aspect import calculate_aspect
from app.terrain.dem_validator import DEMValidator
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope
from app.terrain.summary import compile_terrain_summary

PROCESSING_VERSION = "1.1.0"


class DEMProcessingService:
    @staticmethod
    def _write_derived_geotiff(
        output_path: Path,
        array: np.ndarray,
        template_profile: Dict[str, Any],
        units: str,
        layer_type: str,
        source_dataset_id: str,
        nodata_value: float = -9999.0,
    ) -> None:
        out_data = np.where(np.isfinite(array), array.astype(np.float32), np.float32(nodata_value))
        profile = template_profile.copy()
        profile.update({
            "driver": "GTiff",
            "dtype": "float32",
            "count": 1,
            "nodata": nodata_value,
        })
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(out_data, 1)
            dst.set_band_unit(1, units)
            tags = {
                "VERTICAL_UNITS": units,
                "UNITS": units,
                "LAYER_TYPE": layer_type,
                "SOURCE_DATASET_ID": source_dataset_id,
                "PROCESSING_VERSION": PROCESSING_VERSION,
            }
            dst.update_tags(**tags)
            dst.update_tags(1, **tags)

    @staticmethod
    def process_dem_dataset(
        dataset: Dataset,
        raw_dir: Path,
        processed_dir: Path,
        study_bounds: Optional[Dict[str, float]] = None,
        study_area_name: str = "Gale Crater - Mount Sharp Exploration Zone",
        roughness_radius_meters: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate a downloaded DEM dataset, clip to target bounds (if specified and large enough),
        compute Horn slope, compass aspect, and metric TRI roughness, write GeoTIFF outputs,
        and record a verified processing manifest.
        """
        if not dataset.local_file_path:
            raise ValueError(f"Dataset '{dataset.id}' has not been downloaded locally.")

        raw_root = raw_dir.parent
        local_path = raw_root / dataset.local_file_path
        # Prefer .lbl for PDS3 binary .img pairs if GDAL PDS driver uses label
        raster_open_path = local_path
        if local_path.suffix.lower() == ".img" and local_path.with_suffix(".lbl").exists():
            raster_open_path = local_path.with_suffix(".lbl")

        if not raster_open_path.exists():
            raise FileNotFoundError(f"Local raster product missing: {raster_open_path}")

        inspection = RasterInspectionService.inspect_raster_file(
            raster_open_path,
            explicit_units=dataset.units if dataset.units != "unknown" else None,
        )
        DEMValidator.validate_dem_metadata(inspection)

        processed_dir.mkdir(parents=True, exist_ok=True)
        dem_out = processed_dir / f"{dataset.id}_dem.tif"

        # If study bounds provided and source covers >= 3x3 cells within bounds, clip; otherwise export validated raster
        clipped_info = None
        if study_bounds:
            try:
                clipped_info = clip_raster_to_bounding_box(
                    source_raster_path=raster_open_path,
                    output_geotiff_path=dem_out,
                    min_lon=study_bounds["min_lon"],
                    min_lat=study_bounds["min_lat"],
                    max_lon=study_bounds["max_lon"],
                    max_lat=study_bounds["max_lat"],
                    output_crs_str=dataset.coordinate_reference_system or inspection["crs"],
                    units=inspection["units"],
                    source_dataset_id=dataset.id,
                )
            except Exception as clip_exc:
                # If study box is smaller than 3x3 pixels (e.g., coarse 4 ppd global product), expand minimally around study center
                with rasterio.open(raster_open_path) as src:
                    raw_px = max(abs(src.transform.a), abs(src.transform.e))
                    px_deg = raw_px / 59274.69 if (src.crs and src.crs.is_projected) else raw_px
                pad = min(max(px_deg * 6.0, 0.6), 10.0)
                c_lon = (study_bounds["min_lon"] + study_bounds["max_lon"]) / 2.0
                c_lat = (study_bounds["min_lat"] + study_bounds["max_lat"]) / 2.0
                clipped_info = clip_raster_to_bounding_box(
                    source_raster_path=raster_open_path,
                    output_geotiff_path=dem_out,
                    min_lon=c_lon - pad,
                    min_lat=c_lat - pad,
                    max_lon=c_lon + pad,
                    max_lat=c_lat + pad,
                    output_crs_str=dataset.coordinate_reference_system or inspection["crs"],
                    units=inspection["units"],
                    source_dataset_id=dataset.id,
                )
                clipped_info["clip_note"] = (
                    f"Coarse product expanded to minimum 12x12 analysis window around study area ({clip_exc})"
                )

        # Inspect clipped output GeoTIFF and compute terrain derivatives
        with rasterio.open(dem_out) as src:
            raw_elev = src.read(1).astype(np.float64)
            nodata = src.nodatavals[0]
            elev, valid_mask = DEMValidator.extract_valid_elevation_mask(raw_elev, nodata_val=nodata)
            transform = src.transform
            crs_str = dataset.coordinate_reference_system or (src.crs.to_string() if src.crs else "")
            if not validate_mars_crs(crs_str):
                raise ValueError(f"Invalid Mars CRS on processed DEM: '{crs_str}'")

            center_lat = (src.bounds.bottom + src.bounds.top) / 2.0
            if src.crs and src.crs.is_geographic:
                dx_m, dy_m = angular_displacement_to_metric(center_lat, abs(transform.a), abs(transform.e))
            else:
                dx_m, dy_m = abs(float(transform.a)), abs(float(transform.e))

            template_profile = src.profile.copy()

        nodata_mask = ~valid_mask
        slope_deg, _ = calculate_slope(elev, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
        aspect_deg = calculate_aspect(elev, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
        rough_tri, tri_meta = calculate_roughness_tri_with_metadata(
            elev,
            dx_meters=dx_m,
            dy_meters=dy_m,
            nodata_mask=nodata_mask,
            neighborhood_radius_meters=roughness_radius_meters,
            vertical_units="meters",
        )

        slope_out = processed_dir / f"{dataset.id}_slope.tif"
        aspect_out = processed_dir / f"{dataset.id}_aspect.tif"
        rough_out = processed_dir / f"{dataset.id}_roughness.tif"

        DEMProcessingService._write_derived_geotiff(slope_out, slope_deg, template_profile, "degrees", "slope", dataset.id)
        DEMProcessingService._write_derived_geotiff(aspect_out, aspect_deg, template_profile, "degrees_clockwise_north", "aspect", dataset.id)
        DEMProcessingService._write_derived_geotiff(rough_out, rough_tri, template_profile, "meters", "roughness", dataset.id)

        warnings = list(dataset.known_limitations)
        if clipped_info and "clip_note" in clipped_info:
            warnings.append(clipped_info["clip_note"])

        summary = compile_terrain_summary(
            source_dem_id=dataset.id,
            source_product_id=dataset.product_id,
            processing_version=PROCESSING_VERSION,
            study_area_name=study_area_name,
            resolution_m=dx_m,
            roughness_window_radius_meters=tri_meta.get("requested_radius_meters") or tri_meta["physical_half_width_m"],
            crs=crs_str,
            elevation=elev,
            slope_deg=slope_deg,
            aspect_deg=aspect_deg,
            roughness_tri=rough_tri,
            warnings=warnings,
        )

        manifest_data = {
            "manifest_version": PROCESSING_VERSION,
            "processed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_dataset_id": dataset.id,
            "source_product_id": dataset.product_id,
            "source_sha256": dataset.sha256_checksum,
            "crs": crs_str,
            "units": "meters",
            "dx_meters": dx_m,
            "dy_meters": dy_m,
            "tri_metadata": tri_meta,
            "files": {
                "dem": dem_out.name,
                "slope": slope_out.name,
                "aspect": aspect_out.name,
                "roughness": rough_out.name,
            },
            "summary": summary.model_dump(),
        }
        manifest_path = processed_dir / f"{dataset.id}.processing.json"
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        dataset.processed_file_path = f"processed/{dem_out.name}"
        dataset.status = DatasetLifecycleStatus.PROCESSED
        dataset.verification.processing_verification = VerificationState.VERIFIED
        dataset.verification.field_verification["units"] = VerificationState.VERIFIED
        dataset.verification.field_verification["crs"] = VerificationState.VERIFIED
        dataset.verification.evidence_notes.append(f"Processed DEM and terrain derivatives to {dem_out.name}")
        dataset.processing_history.append(f"Processed DEM -> Slope/Aspect/TRI GeoTIFFs (v{PROCESSING_VERSION})")

        return manifest_data
