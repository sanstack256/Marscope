"""
MARSCOPE Scalable Spatial Data Delivery, Multi-Resolution Pyramid & Deterministic Cache Invalidation Engine (Prompt 19 Part 8).

Implements:
- Explicit 9-input deterministic cache key hashing (dataset_id, source_sha256, algorithm,
  algorithm_version, parameters, crs, resolution_m, bounds, metadata_hash) so stale
  derived artifacts automatically miss cache on source checksum, calibration, or parameter change.
- Multi-resolution scale-pyramid planning across MOLA global/local grids and HiRISE DTMs/Orthos,
  blocking silent up-sampling of coarse altimetry into meter-scale traversability claims and
  explicitly exposing source transitions.
- Runtime cache telemetry and operator-controlled cache invalidation hooks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
import rasterio

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.schemas.dataset import Dataset

DELIVERY_ENGINE_VERSION = "mars_spatial_delivery_v2.0"


class SpatialCacheKey(BaseModel):
    dataset_id: str
    source_sha256: str
    algorithm: str
    algorithm_version: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    crs: str
    resolution_m: Optional[float] = None
    bounds: Optional[Dict[str, float]] = None
    metadata_hash: str
    digest: str
    composite_key: str


class CacheInvalidationEvent(BaseModel):
    invalidated_at_utc: str
    scope: str
    dataset_id: Optional[str] = None
    cleared_entries: int
    reason: str
    operator: str = "system"


class ScalePyramidTier(BaseModel):
    tier_name: str
    dataset_id: str
    product_id: str
    modality: str  # elevation | optical
    native_resolution_m: float
    min_viewport_span_m: float
    max_viewport_span_m: float
    recommended_grid_dim: int
    intersects_viewport: bool
    has_overviews: bool = False
    overview_factors: List[int] = Field(default_factory=list)
    resampling_warning: Optional[str] = None


class SourceTransitionWarning(BaseModel):
    from_dataset_id: str
    to_dataset_id: str
    transition_span_m: float
    resolution_jump_factor: float
    vertical_datum_warning: str


class MultiResolutionPyramidPlan(BaseModel):
    bounds: Dict[str, float]
    viewport_span_m: float
    requested_viewport_px: int
    target_pixel_size_m: float
    selected_dem_dataset_id: Optional[str] = None
    selected_optical_dataset_id: Optional[str] = None
    selected_native_resolution_m: Optional[float] = None
    upsampling_prevented: bool = False
    available_tiers: List[ScalePyramidTier] = Field(default_factory=list)
    source_transitions: List[SourceTransitionWarning] = Field(default_factory=list)
    delivery_constraints: List[str] = Field(default_factory=list)
    cache_digest_preview: Optional[str] = None


def compute_dataset_metadata_hash(ds: Dataset) -> str:
    """Hash provenance & spatial frame attributes that must invalidate derived caches if altered."""
    payload = {
        "product_id": ds.product_id,
        "crs": ds.coordinate_reference_system,
        "latitude_convention": ds.latitude_convention,
        "longitude_direction": ds.longitude_direction,
        "calibration_status": ds.calibration_status,
        "horizontal_resolution_meters": ds.horizontal_resolution_meters,
        "vertical_resolution_meters": ds.vertical_resolution_meters,
        "nodata_value": ds.nodata_value,
        "units": ds.units,
        "acquisition_timestamp": ds.acquisition_timestamp,
        "coverage": ds.coverage.model_dump() if ds.coverage else None,
        "sha256_checksum": ds.sha256_checksum,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def resolve_source_sha256_token(ds: Dataset, open_path: Optional[Path] = None) -> str:
    """Return authoritative dataset SHA-256 or deterministic file stat fallback when unchecksummed."""
    if ds.sha256_checksum and ds.sha256_checksum.strip():
        return ds.sha256_checksum.strip().lower()
    if open_path is not None and open_path.exists():
        st = open_path.stat()
        return f"unverified_stat_{st.st_size}_{int(st.st_mtime)}"
    return "unverified_no_local_file"


def compute_spatial_cache_digest(
    *,
    dataset: Optional[Dataset] = None,
    dataset_id: Optional[str] = None,
    source_sha256: Optional[str] = None,
    algorithm: str,
    algorithm_version: str,
    parameters: Optional[Dict[str, Any]] = None,
    crs: Optional[str] = None,
    resolution_m: Optional[float] = None,
    bounds: Optional[Dict[str, float]] = None,
    metadata_hash: Optional[str] = None,
) -> SpatialCacheKey:
    """
    Build deterministic cache key & SHA-256 digest from all 9 Part 8.4 invalidation dimensions.
    """
    did = dataset.id if dataset is not None else (dataset_id or "unknown")
    sha = source_sha256 or (resolve_source_sha256_token(dataset) if dataset is not None else "unknown")
    eff_crs = crs or (dataset.coordinate_reference_system if dataset is not None else "unspecified")
    eff_res = resolution_m if resolution_m is not None else (dataset.horizontal_resolution_meters if dataset is not None else None)
    eff_mhash = metadata_hash or (compute_dataset_metadata_hash(dataset) if dataset is not None else "no_meta")
    norm_params = parameters or {}
    norm_bounds = (
        {k: round(float(bounds[k]), 7) for k in ("min_lat", "max_lat", "min_lon", "max_lon") if k in bounds}
        if bounds
        else None
    )

    canonical_obj = {
        "dataset_id": did,
        "source_sha256": sha,
        "algorithm": algorithm,
        "algorithm_version": algorithm_version,
        "parameters": norm_params,
        "crs": eff_crs,
        "resolution_m": round(float(eff_res), 4) if eff_res is not None else None,
        "bounds": norm_bounds,
        "metadata_hash": eff_mhash,
    }
    encoded = json.dumps(canonical_obj, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    composite = f"{algorithm}:{did}:{digest}"
    return SpatialCacheKey(
        dataset_id=did,
        source_sha256=sha,
        algorithm=algorithm,
        algorithm_version=algorithm_version,
        parameters=norm_params,
        crs=eff_crs,
        resolution_m=eff_res,
        bounds=norm_bounds,
        metadata_hash=eff_mhash,
        digest=digest,
        composite_key=composite,
    )


def _bounds_intersect(ds: Dataset, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> bool:
    bb = ds.coverage
    if bb is None:
        return False
    if (bb.max_longitude - bb.min_longitude) >= 359.0:
        return not (max_lat < bb.min_latitude or min_lat > bb.max_latitude)
    b_min_lon = float(bb.min_longitude) % 360.0
    b_max_lon = float(bb.max_longitude) % 360.0
    if b_max_lon < b_min_lon:
        b_max_lon += 360.0
    q_min = float(min_lon) % 360.0
    q_max = float(max_lon) % 360.0
    if q_max < q_min:
        q_max += 360.0
    return not (q_max <= b_min_lon or q_min >= b_max_lon or max_lat <= bb.min_latitude or min_lat >= bb.max_latitude)


class SpatialDeliveryService:
    """
    Coordinates Part 8 multi-resolution delivery planning and tracks live cache state / invalidation
    across MARSCOPE derived terrain/imagery products.
    """

    def __init__(self, catalog_service: DatasetCatalogService, raw_dir: Path) -> None:
        self.catalog_service = catalog_service
        self.raw_dir = Path(raw_dir)
        self._mesh_service: Any = None
        self._invalidation_log: List[CacheInvalidationEvent] = []

    def attach_mesh_service(self, mesh_service: Any) -> None:
        self._mesh_service = mesh_service

    def get_multi_resolution_pyramid_plan(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        viewport_px: int = 512,
        preferred_dataset_id: Optional[str] = None,
    ) -> MultiResolutionPyramidPlan:
        if min_lat >= max_lat:
            raise ValueError("min_lat must be strictly less than max_lat.")
        viewport_px = max(32, min(2048, int(viewport_px)))
        m_per_deg = (math.pi / 180.0) * MARS_EQUATORIAL_RADIUS_M
        mean_lat = 0.5 * (min_lat + max_lat)
        lat_span_m = abs(max_lat - min_lat) * m_per_deg
        lon_span_m = abs(max_lon - min_lon) * m_per_deg * max(0.05, math.cos(math.radians(mean_lat)))
        viewport_span_m = round(max(lat_span_m, lon_span_m), 2)
        target_px_m = round(viewport_span_m / float(viewport_px), 3)

        tiers: List[ScalePyramidTier] = []
        dem_candidates: List[ScalePyramidTier] = []
        opt_candidates: List[ScalePyramidTier] = []

        for ds in self.catalog_service.list_datasets():
            pt = (ds.product_type or "").lower()
            is_opt = pt in {"imagery", "orthorectified_imagery"} or "ortho" in ds.id.lower()
            is_dem = any(k in pt for k in ("dem", "topoph", "elevation")) or "dtm" in ds.id.lower() or "mola" in ds.id.lower()
            if not is_opt and not is_dem:
                continue
            if not _bounds_intersect(ds, min_lat, max_lat, min_lon, max_lon):
                continue
            try:
                open_path, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
            except FileNotFoundError:
                continue
            if not open_path.exists():
                continue

            nat_res = float(ds.horizontal_resolution_meters or 463.0)
            has_ov = False
            ov_factors: List[int] = []
            try:
                with rasterio.open(open_path) as src:
                    ov_factors = list(src.overviews(1) or [])
                    has_ov = len(ov_factors) > 0
            except Exception:
                pass

            if nat_res <= 2.5:
                tier_name = "submeter_optical_ortho" if is_opt else "high_res_stereo_dtm"
                min_span, max_span = 20.0, 25_000.0
                rec_grid = 129
            elif nat_res <= 600.0:
                tier_name = "local_regional_topography"
                min_span, max_span = 10_000.0, 2_000_000.0
                rec_grid = 97
            else:
                tier_name = "global_altimetry"
                min_span, max_span = 250_000.0, 25_000_000.0
                rec_grid = 65

            warn = None
            if nat_res > 100.0 and viewport_span_m < 10_000.0:
                warn = (
                    f"Coarse {nat_res} m/px altimetry is below meter-scale local exploration Nyquist limit "
                    f"for a {viewport_span_m:.0f} m viewport; up-sampling to meter-scale slopes is prohibited."
                )

            tier = ScalePyramidTier(
                tier_name=tier_name,
                dataset_id=ds.id,
                product_id=ds.product_id,
                modality=("optical" if is_opt else "elevation"),
                native_resolution_m=nat_res,
                min_viewport_span_m=min_span,
                max_viewport_span_m=max_span,
                recommended_grid_dim=rec_grid,
                intersects_viewport=True,
                has_overviews=has_ov,
                overview_factors=ov_factors,
                resampling_warning=warn,
            )
            tiers.append(tier)
            if is_opt:
                opt_candidates.append(tier)
            else:
                dem_candidates.append(tier)

        tiers.sort(key=lambda t: (t.modality, t.native_resolution_m))
        dem_candidates.sort(key=lambda t: t.native_resolution_m)
        opt_candidates.sort(key=lambda t: t.native_resolution_m)

        selected_dem: Optional[ScalePyramidTier] = None
        if preferred_dataset_id:
            selected_dem = next((t for t in dem_candidates if t.dataset_id == preferred_dataset_id), None)
        if selected_dem is None and dem_candidates:
            # Choose finest tier whose min/max span matches viewport, else finest when zoomed in, else coarsest for global
            in_range = [t for t in dem_candidates if t.min_viewport_span_m <= viewport_span_m <= t.max_viewport_span_m]
            selected_dem = in_range[0] if in_range else (dem_candidates[0] if viewport_span_m <= 25_000.0 else dem_candidates[-1])

        selected_opt = opt_candidates[0] if opt_candidates else None
        upsampling_prevented = False
        transitions: List[SourceTransitionWarning] = []
        constraints: List[str] = [
            f"Bounded grid read capped <= 129x129 vertices / <= {viewport_px}x{viewport_px} texture pixels.",
            "NoData swath masks are preserved without cross-gap interpolation.",
        ]

        if selected_dem is not None and selected_dem.native_resolution_m > 100.0 and viewport_span_m < 10_000.0:
            upsampling_prevented = True
            constraints.append(
                f"Upsampling prevented: '{selected_dem.dataset_id}' ({selected_dem.native_resolution_m} m/px) "
                "cannot substitute for local meter-scale DTM derivatives."
            )

        if len(dem_candidates) >= 2:
            fine = dem_candidates[0]
            for coarse in dem_candidates[1:]:
                if coarse.native_resolution_m > fine.native_resolution_m * 5.0:
                    transitions.append(
                        SourceTransitionWarning(
                            from_dataset_id=fine.dataset_id,
                            to_dataset_id=coarse.dataset_id,
                            transition_span_m=fine.max_viewport_span_m,
                            resolution_jump_factor=round(coarse.native_resolution_m / max(0.01, fine.native_resolution_m), 1),
                            vertical_datum_warning=(
                                "Transitioning between stereo HiRISE DTM and MOLA MEGDR shifts vertical datum/tie offset (~50-60 m locally in Gale) "
                                "and collapses meter-scale relief. Keep transition visible to operators."
                            ),
                        )
                    )

        preview_digest = None
        if selected_dem is not None:
            ds_obj = self.catalog_service.get_dataset(selected_dem.dataset_id)
            if ds_obj is not None:
                preview_digest = compute_spatial_cache_digest(
                    dataset=ds_obj,
                    algorithm="pyramid_plan",
                    algorithm_version=DELIVERY_ENGINE_VERSION,
                    parameters={"viewport_px": viewport_px},
                    bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
                ).composite_key

        return MultiResolutionPyramidPlan(
            bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
            viewport_span_m=viewport_span_m,
            requested_viewport_px=viewport_px,
            target_pixel_size_m=target_px_m,
            selected_dem_dataset_id=(selected_dem.dataset_id if selected_dem else None),
            selected_optical_dataset_id=(selected_opt.dataset_id if selected_opt else None),
            selected_native_resolution_m=(selected_dem.native_resolution_m if selected_dem else None),
            upsampling_prevented=upsampling_prevented,
            available_tiers=tiers,
            source_transitions=transitions,
            delivery_constraints=constraints,
            cache_digest_preview=preview_digest,
        )

    def get_cache_status(self) -> Dict[str, Any]:
        mesh_stats = self._mesh_service.get_cache_stats() if self._mesh_service and hasattr(self._mesh_service, "get_cache_stats") else {
            "entries": 0,
            "max_entries": 0,
            "hits": 0,
            "misses": 0,
        }
        return {
            "engine_version": DELIVERY_ENGINE_VERSION,
            "key_dimensions": [
                "dataset_id",
                "source_sha256",
                "algorithm",
                "algorithm_version",
                "parameters",
                "crs",
                "resolution_m",
                "bounds",
                "metadata_hash",
            ],
            "mesh_tile_cache": mesh_stats,
            "recent_invalidations": [ev.model_dump() for ev in self._invalidation_log[-10:]],
        }

    def invalidate_cache(
        self,
        *,
        dataset_id: Optional[str] = None,
        reason: str = "operator_requested_invalidation",
        operator: str = "operator",
    ) -> CacheInvalidationEvent:
        cleared = 0
        if self._mesh_service and hasattr(self._mesh_service, "invalidate_cache"):
            cleared = int(self._mesh_service.invalidate_cache(dataset_id=dataset_id))
        ev = CacheInvalidationEvent(
            invalidated_at_utc=datetime.now(timezone.utc).isoformat(),
            scope=("dataset" if dataset_id else "all"),
            dataset_id=dataset_id,
            cleared_entries=cleared,
            reason=reason,
            operator=operator,
        )
        self._invalidation_log.append(ev)
        return ev
