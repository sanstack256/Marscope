"""
MARSCOPE DEM Processing & Manifested Derivative Pipeline
Martian Surface Intelligence & Exploration System

Processes validated raw elevation datasets into clipped study-area GeoTIFFs and derivative
Slope, Aspect and Roughness (TRI) products with verifiable processing manifests.

Footprint policy (Prompt 8): the requested footprint is NEVER enlarged, shifted, or replaced to
satisfy a minimum pixel count. If the footprint cannot support the analysis, a structured
InsufficientCoverageReport is raised and nothing is written. A broader region can only be
analysed through a separate, explicit request that is recorded as its own analysis.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional

import numpy as np
import rasterio

from app.geospatial.alignment import FootprintPlanError, clip_raster_to_bounding_box, plan_clip_to_bounding_box
from app.geospatial.crs import angular_displacement_to_metric, validate_mars_crs
from app.geospatial.raster import RasterInspectionService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.schemas.terrain import InsufficientCoverageReport, PlanningSlopeThreshold
from app.terrain.aspect import calculate_aspect
from app.terrain.dem_validator import DEMValidator
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope
from app.terrain.summary import compile_terrain_summary

PROCESSING_VERSION = "2.0.0"
FOOTPRINT_POLICY = "no_expansion_v1"
MIN_PIXELS_FOR_3X3_DERIVATIVES = 3
MAX_ANALYSIS_CELLS = 16_000_000  # bounded in-memory analysis; larger footprints must be tiled/split


class InsufficientDEMCoverageError(ValueError):
    """Raised with a structured report when the requested footprint cannot support the analysis."""

    def __init__(self, report: InsufficientCoverageReport):
        super().__init__(report.insufficient_coverage_reason)
        self.report = report


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_analysis_cache_key(
    source_sha256: Optional[str],
    requested_bounds: Optional[Dict[str, float]],
    roughness_radius_meters: Optional[float],
    planning_threshold: Optional[PlanningSlopeThreshold],
) -> str:
    payload = json.dumps(
        {
            "source_sha256": source_sha256,
            "requested_bounds": requested_bounds,
            "roughness_radius_meters": roughness_radius_meters,
            "planning_threshold": planning_threshold.model_dump() if planning_threshold else None,
            "processing_version": PROCESSING_VERSION,
            "footprint_policy": FOOTPRINT_POLICY,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        profile.update({"driver": "GTiff", "dtype": "float32", "count": 1, "nodata": nodata_value})
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
    def assess_footprint(
        raster_open_path: Path,
        requested_bounds: Dict[str, float],
        output_crs_str: Optional[str],
    ) -> Dict[str, Any]:
        """Dry-run footprint assessment. Never modifies requested_bounds."""
        return plan_clip_to_bounding_box(
            raster_open_path,
            min_lon=requested_bounds["min_lon"],
            min_lat=requested_bounds["min_lat"],
            max_lon=requested_bounds["max_lon"],
            max_lat=requested_bounds["max_lat"],
            output_crs_str=output_crs_str,
        )

    @staticmethod
    def _insufficient_report(
        requested: Dict[str, float], plan: Optional[Dict[str, Any]], reason: str, next_action: str,
        unsupported: Optional[list] = None, supported: Optional[list] = None,
    ) -> InsufficientCoverageReport:
        res = None
        if plan:
            ps = plan.get("source_pixel_size", {})
            res = {"pixel_size_x": ps.get("x"), "pixel_size_y": ps.get("y"), "pixel_size_units": ps.get("units")}
            if plan.get("source_is_geographic") and ps.get("y"):
                lat_c = (requested["min_lat"] + requested["max_lat"]) / 2.0
                mx, my = angular_displacement_to_metric(lat_c, ps["x"], ps["y"])
                res.update({"approx_pixel_m_east_west": round(mx, 1), "approx_pixel_m_north_south": round(my, 1)})
        return InsufficientCoverageReport(
            requested_bounds=dict(requested),
            source_coverage_bounds=plan.get("source_bounds") if plan else None,
            intersecting_bounds=plan.get("intersecting_bounds") if plan else None,
            requested_pixel_dimensions=plan.get("requested_pixel_dimensions") if plan else None,
            available_pixel_dimensions=plan.get("available_pixel_dimensions") if plan else None,
            source_resolution=res,
            minimum_resolution_requirement={
                "slope_aspect_horn_3x3": f">= {MIN_PIXELS_FOR_3X3_DERIVATIVES}x{MIN_PIXELS_FOR_3X3_DERIVATIVES} valid source pixels "
                "inside the requested footprint (Horn kernel needs a complete 3x3 neighborhood)",
                "elevation_only": ">= 1 valid source pixel",
            },
            insufficient_coverage_reason=reason,
            supported_products=supported or [],
            unsupported_derivative_products=unsupported if unsupported is not None else ["slope", "aspect", "roughness"],
            next_action=next_action,
        )

    @staticmethod
    def process_dem_dataset(
        dataset: Dataset,
        raw_dir: Path,
        processed_dir: Path,
        study_bounds: Optional[Dict[str, float]] = None,
        study_area_name: str = "Gale Crater - Mount Sharp Exploration Zone",
        roughness_radius_meters: Optional[float] = None,
        bounds_origin: str = "default_study_area",
        planning_threshold: Optional[PlanningSlopeThreshold] = None,
    ) -> Dict[str, Any]:
        """
        Validate a downloaded DEM, clip to the requested footprint (never enlarged), compute Horn slope,
        compass aspect, and metric TRI at the DEM's ACTUAL resolution, write GeoTIFFs atomically and
        record a verified processing manifest with checksums and a cache key.

        Raises InsufficientDEMCoverageError (structured report, nothing written) when the footprint
        cannot support slope/aspect/roughness.
        """
        if not dataset.local_file_path:
            raise ValueError(f"Dataset '{dataset.id}' has not been downloaded locally.")

        raw_root = raw_dir.parent
        local_path = raw_root / dataset.local_file_path
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

        out_crs = dataset.coordinate_reference_system or inspection["crs"]

        # ---- Requested footprint (frozen; never modified below) ----
        if study_bounds:
            requested = {k: float(study_bounds[k]) for k in ("min_lon", "min_lat", "max_lon", "max_lat")}
        else:
            with rasterio.open(raster_open_path) as _s:
                requested = {
                    "min_lon": _s.bounds.left, "min_lat": _s.bounds.bottom,
                    "max_lon": _s.bounds.right, "max_lat": _s.bounds.top,
                }
            bounds_origin = "full_source_extent"
        requested_frozen = dict(requested)

        try:
            plan = DEMProcessingService.assess_footprint(raster_open_path, requested, out_crs)
        except FootprintPlanError as fpe:
            raise InsufficientDEMCoverageError(
                DEMProcessingService._insufficient_report(
                    requested_frozen, None, str(fpe),
                    "Request each side of the antimeridian as a separate explicit analysis.",
                )
            ) from fpe

        avail = plan["available_pixel_dimensions"]
        if not plan["overlaps_source"]:
            raise InsufficientDEMCoverageError(
                DEMProcessingService._insufficient_report(
                    requested_frozen, plan,
                    "Requested footprint lies entirely outside the source DEM coverage.",
                    "Choose a footprint inside the source coverage or acquire a DEM covering the study area.",
                    supported=[],
                )
            )
        if avail["width"] < MIN_PIXELS_FOR_3X3_DERIVATIVES or avail["height"] < MIN_PIXELS_FOR_3X3_DERIVATIVES:
            raise InsufficientDEMCoverageError(
                DEMProcessingService._insufficient_report(
                    requested_frozen, plan,
                    (
                        f"Requested footprint contains only {avail['width']}x{avail['height']} whole source pixels at the "
                        f"source resolution; slope/aspect/roughness need at least "
                        f"{MIN_PIXELS_FOR_3X3_DERIVATIVES}x{MIN_PIXELS_FOR_3X3_DERIVATIVES}. The footprint was NOT enlarged."
                    ),
                    (
                        "Use a finer-resolution DEM that covers this footprint, or explicitly submit a separate, "
                        "broader analysis footprint (recorded as its own analysis). Point elevation sampling remains "
                        "available through /api/terrain/point."
                    ),
                    supported=["point_elevation_sampling"] if avail["width"] >= 1 and avail["height"] >= 1 else [],
                )
            )
        if avail["width"] * avail["height"] > MAX_ANALYSIS_CELLS:
            raise InsufficientDEMCoverageError(
                DEMProcessingService._insufficient_report(
                    requested_frozen, plan,
                    f"Requested footprint ({avail['width']}x{avail['height']} px) exceeds the bounded in-memory limit "
                    f"of {MAX_ANALYSIS_CELLS} cells.",
                    "Submit smaller footprints; each is recorded as a separate analysis.",
                    unsupported=["slope", "aspect", "roughness"],
                )
            )

        cache_key = compute_analysis_cache_key(dataset.sha256_checksum, requested_frozen, roughness_radius_meters, planning_threshold)
        manifest_path = processed_dir / f"{dataset.id}.processing.json"
        processed_dir.mkdir(parents=True, exist_ok=True)
        cached = DEMProcessingService._load_valid_cache(manifest_path, processed_dir, cache_key)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

        dem_out = processed_dir / f"{dataset.id}_dem.tif"
        slope_out = processed_dir / f"{dataset.id}_slope.tif"
        aspect_out = processed_dir / f"{dataset.id}_aspect.tif"
        rough_out = processed_dir / f"{dataset.id}_roughness.tif"

        with tempfile.TemporaryDirectory(dir=processed_dir, prefix=".stage_") as stage:
            stage_dir = Path(stage)
            t_dem = stage_dir / dem_out.name
            clipped_info = clip_raster_to_bounding_box(
                source_raster_path=raster_open_path,
                output_geotiff_path=t_dem,
                min_lon=requested_frozen["min_lon"],
                min_lat=requested_frozen["min_lat"],
                max_lon=requested_frozen["max_lon"],
                max_lat=requested_frozen["max_lat"],
                output_crs_str=out_crs,
                units=inspection["units"],
                source_dataset_id=dataset.id,
            )
            with rasterio.open(t_dem) as src:
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
                analysis_bounds = {
                    "min_lon": src.bounds.left, "min_lat": src.bounds.bottom,
                    "max_lon": src.bounds.right, "max_lat": src.bounds.top,
                }

            nodata_mask = ~valid_mask
            slope_deg, _ = calculate_slope(elev, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
            aspect_deg = calculate_aspect(elev, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
            rough_tri, tri_meta = calculate_roughness_tri_with_metadata(
                elev, dx_meters=dx_m, dy_meters=dy_m, nodata_mask=nodata_mask,
                neighborhood_radius_meters=roughness_radius_meters, vertical_units="meters",
            )

            DEMProcessingService._write_derived_geotiff(stage_dir / slope_out.name, slope_deg, template_profile, "degrees", "slope", dataset.id)
            DEMProcessingService._write_derived_geotiff(stage_dir / aspect_out.name, aspect_deg, template_profile, "degrees_clockwise_north", "aspect", dataset.id)
            DEMProcessingService._write_derived_geotiff(stage_dir / rough_out.name, rough_tri, template_profile, "meters", "roughness", dataset.id)

            warnings = list(dataset.known_limitations)
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
                planning_threshold=planning_threshold,
                warnings=warnings,
            )

            snapped_extra = {
                "west_deg": round(requested_frozen["min_lon"] - analysis_bounds["min_lon"], 6),
                "east_deg": round(analysis_bounds["max_lon"] - requested_frozen["max_lon"], 6),
                "south_deg": round(requested_frozen["min_lat"] - analysis_bounds["min_lat"], 6),
                "north_deg": round(analysis_bounds["max_lat"] - requested_frozen["max_lat"], 6),
            }
            file_checksums = {
                dem_out.name: _sha256_file(t_dem),
                slope_out.name: _sha256_file(stage_dir / slope_out.name),
                aspect_out.name: _sha256_file(stage_dir / aspect_out.name),
                rough_out.name: _sha256_file(stage_dir / rough_out.name),
            }
            analysis_id = f"an_{cache_key[:16]}"
            manifest_data: Dict[str, Any] = {
                "manifest_version": PROCESSING_VERSION,
                "footprint_policy": FOOTPRINT_POLICY,
                "analysis_id": analysis_id,
                "cache_key": cache_key,
                "cache_hit": False,
                "processed_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_dataset_id": dataset.id,
                "source_product_id": dataset.product_id,
                "source_sha256": dataset.sha256_checksum,
                "crs": crs_str,
                "units": "meters",
                "dx_meters": dx_m,
                "dy_meters": dy_m,
                "requested_bounds": requested_frozen,
                "requested_bounds_origin": bounds_origin,
                "requested_bounds_modified": False,
                "analysis_footprint_bounds": analysis_bounds,
                "pixel_snapping_extent_deg": snapped_extra,
                "footprint_note": (
                    "analysis_footprint_bounds are the whole-source-pixel footprint nearest to the request; "
                    "differences are pixel snapping only. The footprint was never enlarged to reach a minimum pixel count."
                ),
                "raster_dimensions": clipped_info["dimensions"],
                "nodata_value": clipped_info.get("nodata_value"),
                "roughness_radius_meters_requested": roughness_radius_meters,
                "tri_metadata": tri_meta,
                "slope_method": "Horn 3x3 (8-neighbour weighted finite difference), complete valid 3x3 neighbourhood required",
                "aspect_convention": "degrees clockwise from North [0,360); flat cells are no-data (not a direction)",
                "files": {"dem": dem_out.name, "slope": slope_out.name, "aspect": aspect_out.name, "roughness": rough_out.name},
                "file_sha256": file_checksums,
                "summary": summary.model_dump(),
            }

            # Atomic publication: outputs first, manifest last. Failure before manifest write leaves no complete record.
            for name in (dem_out.name, slope_out.name, aspect_out.name, rough_out.name):
                os.replace(stage_dir / name, processed_dir / name)
            tmp_manifest = stage_dir / "manifest.json"
            tmp_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
            os.replace(tmp_manifest, manifest_path)

        dataset.processed_file_path = f"processed/{dem_out.name}"
        dataset.status = DatasetLifecycleStatus.PROCESSED
        dataset.verification.processing_verification = VerificationState.VERIFIED
        dataset.verification.field_verification["units"] = VerificationState.VERIFIED
        dataset.verification.field_verification["crs"] = VerificationState.VERIFIED
        dataset.verification.evidence_notes.append(f"Processed DEM and terrain derivatives to {dem_out.name}")
        dataset.processing_history.append(f"Processed DEM -> Slope/Aspect/TRI GeoTIFFs (v{PROCESSING_VERSION}, {analysis_id})")
        return manifest_data

    @staticmethod
    def _load_valid_cache(manifest_path: Path, processed_dir: Path, cache_key: str) -> Optional[Dict[str, Any]]:
        """Return an existing manifest only if its cache key matches AND every output checksum verifies."""
        if not manifest_path.exists():
            return None
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            if m.get("cache_key") != cache_key or m.get("manifest_version") != PROCESSING_VERSION:
                return None
            for name, digest in (m.get("file_sha256") or {}).items():
                fp = processed_dir / name
                if not fp.exists() or _sha256_file(fp) != digest:
                    return None
            if not m.get("file_sha256"):
                return None
            return m
        except Exception:
            return None
