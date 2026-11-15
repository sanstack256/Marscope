"""
Landing-Site Registration, Real-Catalog Gazetteer Search & Algorithmic DEM Perimeter Service.
- No silent Gale Crater default: newly created missions start as LANDING_SITE_UNCONFIGURED.
- Gazetteer search returns verified dataset-backed Mars feature records and processed DEM coverage entries
  from catalog_service / PROCESSED_DIR without ever inventing coordinates.
- 3D Landing-Site Perimeter is computed strictly inside validated DEM coverage via BFS connected-component
  extraction over precomputed slope/roughness/DEM grids + explicit planning constraints, returning GeoJSON
  and explicit limitations ('CURRENTLY EVALUATED PLANNING BOUNDARY — NOT A CERTIFIED SAFETY LIMIT').
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
import numpy as np
import rasterio
from rasterio.windows import Window
from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from app.db.database import MissionDatabase
from app.geospatial.crs import (
    CRSError,
    angular_displacement_to_metric,
    normalize_longitude_180,
    normalize_longitude_360,
    validate_mars_coordinates,
    validate_mars_crs,
)
from app.schemas.mission_collab import (
    ComputePerimeterRequest,
    GazetteerSiteRecord,
    LandingSiteBundleResponse,
    LandingSitePerimeterResponse,
    LandingSiteResponse,
    RegisterLandingSiteRequest,
)
from app.services.mission_event_service import MissionEventService
from app.services.realtime_hub import MissionRealtimeHub


ALGORITHM_ID = "dem_bfs_slope_roughness_boundary"
ALGORITHM_VERSION = "1.0.0"
PLANNING_BOUNDARY_LABEL = "CURRENTLY EVALUATED PLANNING BOUNDARY — NOT A CERTIFIED SAFETY LIMIT"


class LandingSiteService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        realtime_hub: MissionRealtimeHub,
        catalog_service: Any,
        destination_service: Any,
        processed_dir: Path,
    ) -> None:
        self._db = db
        self._events = event_service
        self._hub = realtime_hub
        self._catalog = catalog_service
        self._destination = destination_service
        self._processed_dir = processed_dir

    # ------------------------------------------------------------------
    # Catalog-Backed Mars Gazetteer Search (No Hardcoded Fake Coordinates)
    # ------------------------------------------------------------------

    def search_gazetteer(self, query: Optional[str] = None) -> List[GazetteerSiteRecord]:
        q = (query or "").strip().lower()
        records: List[GazetteerSiteRecord] = []

        # 1. Validated processed DEM centroids/study zones from real manifests
        for mpath in sorted(self._processed_dir.glob("*.processing.json")):
            try:
                manifest = json.loads(mpath.read_text(encoding="utf-8"))
                bounds = manifest.get("analysis_footprint_bounds") or manifest.get("requested_bounds")
                if not bounds:
                    continue
                center_lat = (float(bounds["min_lat"]) + float(bounds["max_lat"])) / 2.0
                center_lon = normalize_longitude_360((float(bounds["min_lon"]) + float(bounds["max_lon"])) / 2.0)
                ds_id = manifest.get("source_dataset_id", mpath.stem.replace(".processing", ""))
                summary = manifest.get("summary") or {}
                label = summary.get("study_area_name") or ds_id
                elev_stats = summary.get("elevation_stats") or {}
                elev = float(elev_stats["mean_value"]) if elev_stats.get("mean_value") is not None else None
                records.append(
                    GazetteerSiteRecord(
                        record_id=f"processed_dem:{ds_id}",
                        name=f"{label} (Validated DEM Center)",
                        region=summary.get("study_area_name"),
                        latitude=round(center_lat, 6),
                        longitude_east=round(center_lon, 6),
                        crs=manifest.get("crs", "IAU2000:49900"),
                        source="PROCESSED_DEM_COVERAGE",
                        dataset_id=ds_id,
                        coverage_verified=True,
                        elevation_m=round(elev, 2) if elev is not None else None,
                        uncertainty_m=float(manifest.get("dx_meters")) if manifest.get("dx_meters") else None,
                    )
                )
            except Exception:
                continue

        # 2. Catalog datasets that provide explicit verified planetary bounding boxes
        try:
            for ds in self._catalog.list_datasets():
                bbox = getattr(ds, "bounding_box", None)
                if not bbox:
                    continue
                min_lat = getattr(bbox, "min_lat", None)
                max_lat = getattr(bbox, "max_lat", None)
                min_lon = getattr(bbox, "min_lon", None)
                max_lon = getattr(bbox, "max_lon", None)
                if None in (min_lat, max_lat, min_lon, max_lon):
                    continue
                c_lat = (float(min_lat) + float(max_lat)) / 2.0
                c_lon = normalize_longitude_360((float(min_lon) + float(max_lon)) / 2.0)
                records.append(
                    GazetteerSiteRecord(
                        record_id=f"catalog:{ds.dataset_id}",
                        name=f"{ds.name} Center",
                        region=ds.region,
                        latitude=round(c_lat, 6),
                        longitude_east=round(c_lon, 6),
                        crs="IAU2000:49900",
                        source="DATASET_CATALOG_MATCH",
                        dataset_id=ds.dataset_id,
                        coverage_verified=True,
                        elevation_m=None,
                        uncertainty_m=None,
                    )
                )
        except Exception:
            pass

        if q:
            records = [
                r
                for r in records
                if q in r.name.lower()
                or q in (r.region or "").lower()
                or q in r.dataset_id.lower()
            ]
        return records

    # ------------------------------------------------------------------
    # Landing-Site Registration & Read
    # ------------------------------------------------------------------

    def get_bundle(self, mission_id: str) -> LandingSiteBundleResponse:
        with self._db.read() as conn:
            m = conn.execute(
                "SELECT mission_id, landing_site_status FROM missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if m is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")
            ls = conn.execute(
                "SELECT * FROM landing_sites WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            perim = conn.execute(
                """
                SELECT * FROM landing_site_perimeters
                WHERE mission_id = ?
                ORDER BY created_at_utc DESC
                LIMIT 1
                """,
                (mission_id,),
            ).fetchone()

        return LandingSiteBundleResponse(
            mission_id=mission_id,
            landing_site_status=m["landing_site_status"],
            landing_site=self._row_to_landing_site(ls) if ls else None,
            perimeter=self._row_to_perimeter(perim) if perim else None,
        )

    def register_landing_site(
        self,
        mission_id: str,
        actor_id: str,
        req: RegisterLandingSiteRequest,
    ) -> LandingSiteBundleResponse:
        if not validate_mars_crs(req.crs):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rejected invalid Mars CRS '{req.crs}'.",
            )
        lat_conv = "Planetocentric" if req.latitude_convention == "planetocentric" else "Planetographic"
        try:
            lat, lon_v = validate_mars_coordinates(req.latitude, req.longitude, lat_conv, "East")
        except CRSError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        lon_east = normalize_longitude_360(lon_v)

        elev_m: Optional[float] = None
        dataset_id: Optional[str] = None
        coverage_state = "OUTSIDE_EVALUATED_DEM_COVERAGE"
        try:
            pt = self._destination.sample_processed_terrain_point(
                latitude=lat,
                longitude=lon_east,
                crs=req.crs,
                latitude_convention=lat_conv,
                longitude_direction="East",
            )
            if pt.available and pt.elevation_m is not None:
                elev_m = float(pt.elevation_m)
                dataset_id = pt.source_dataset_id or pt.source_product_id
                coverage_state = "COVERED_DEM"
        except Exception:
            coverage_state = "OUTSIDE_EVALUATED_DEM_COVERAGE"

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM landing_sites WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()

            if existing is None:
                ls_id = str(uuid.uuid4())
                history = [
                    {
                        "updated_at_utc": now_iso,
                        "actor_id": actor_id,
                        "action": "REGISTERED",
                        "name": req.name.strip(),
                        "latitude": lat,
                        "longitude_east": lon_east,
                        "dem_coverage_state": coverage_state,
                    }
                ]
                conn.execute(
                    """
                    INSERT INTO landing_sites (
                        landing_site_id, mission_id, name, latitude, longitude_east,
                        crs, latitude_convention, longitude_direction, source, source_record_id,
                        uncertainty_m, elevation_m, terrain_dataset_id, dem_coverage_state,
                        registration_state, updated_by, history_json, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, 'IAU2000:49900', ?, ?, ?, ?, ?, ?, ?, ?, 'REGISTERED', ?, ?, ?, ?)
                    """,
                    (
                        ls_id,
                        mission_id,
                        req.name.strip(),
                        lat,
                        lon_east,
                        req.latitude_convention,
                        req.longitude_direction,
                        req.source,
                        req.source_record_id,
                        req.uncertainty_m,
                        elev_m,
                        dataset_id,
                        coverage_state,
                        actor_id,
                        json.dumps(history),
                        now_iso,
                        now_iso,
                    ),
                )
            else:
                history = json.loads(existing["history_json"] or "[]")
                history.append(
                    {
                        "updated_at_utc": now_iso,
                        "actor_id": actor_id,
                        "action": "UPDATED",
                        "name": req.name.strip(),
                        "latitude": lat,
                        "longitude_east": lon_east,
                        "dem_coverage_state": coverage_state,
                    }
                )
                conn.execute(
                    """
                    UPDATE landing_sites
                    SET name = ?, latitude = ?, longitude_east = ?, crs = 'IAU2000:49900',
                        latitude_convention = ?, longitude_direction = ?, source = ?, source_record_id = ?,
                        uncertainty_m = ?, elevation_m = ?, terrain_dataset_id = ?, dem_coverage_state = ?,
                        registration_state = 'REGISTERED', updated_by = ?, history_json = ?, updated_at_utc = ?
                    WHERE mission_id = ?
                    """,
                    (
                        req.name.strip(),
                        lat,
                        lon_east,
                        req.latitude_convention,
                        req.longitude_direction,
                        req.source,
                        req.source_record_id,
                        req.uncertainty_m,
                        elev_m,
                        dataset_id,
                        coverage_state,
                        actor_id,
                        json.dumps(history[-100:]),
                        now_iso,
                        mission_id,
                    ),
                )

            conn.execute(
                "UPDATE missions SET landing_site_status = 'REGISTERED', updated_at_utc = ? WHERE mission_id = ?",
                (now_iso, mission_id),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="LANDING_SITE_REGISTERED",
                payload={
                    "name": req.name.strip(),
                    "latitude": lat,
                    "longitude_east": lon_east,
                    "dem_coverage_state": coverage_state,
                    "terrain_dataset_id": dataset_id,
                },
            )

        bundle = self.get_bundle(mission_id)
        self._hub.publish_mission_event(
            mission_id,
            event_type="LANDING_SITE_REGISTERED",
            payload=bundle.model_dump(),
            event_seq=ev.event_seq,
        )
        return bundle

    # ------------------------------------------------------------------
    # Algorithmic 3D DEM Landing-Site Perimeter Computation
    # ------------------------------------------------------------------

    def compute_perimeter(
        self,
        mission_id: str,
        actor_id: str,
        req: ComputePerimeterRequest,
    ) -> LandingSiteBundleResponse:
        with self._db.read() as conn:
            ls = conn.execute(
                "SELECT * FROM landing_sites WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
        if ls is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Landing site must be explicitly registered before evaluating a perimeter.",
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        perimeter_id = str(uuid.uuid4())

        missing_constraints: List[str] = []
        if req.max_slope_deg is None:
            missing_constraints.append("max_slope_deg")
        if req.max_roughness_m is None:
            missing_constraints.append("max_roughness_m")
        if req.max_radius_m is None:
            missing_constraints.append("max_radius_m")

        if missing_constraints:
            return self._persist_perimeter_result(
                mission_id=mission_id,
                landing_site_id=ls["landing_site_id"],
                perimeter_id=perimeter_id,
                actor_id=actor_id,
                status_val="INDETERMINATE_MISSING_CONSTRAINTS",
                terrain_dataset_id=ls["terrain_dataset_id"],
                native_resolution_m=None,
                coverage_fraction=0.0,
                geometry_geojson=None,
                excluded_regions_geojson=None,
                constraints_used={},
                constraints_missing=missing_constraints,
                limitations=[
                    "All traversal threshold inputs (max_slope_deg, max_roughness_m, max_radius_m) must be explicitly specified.",
                    "Perimeter cannot be computed with missing or unconfigured physical limits.",
                ],
                provenance={"method": ALGORITHM_ID, "version": ALGORITHM_VERSION},
                now_iso=now_iso,
            )

        manifest_info = self._select_covering_manifest(float(ls["latitude"]), float(ls["longitude_east"]))
        if manifest_info is None:
            return self._persist_perimeter_result(
                mission_id=mission_id,
                landing_site_id=ls["landing_site_id"],
                perimeter_id=perimeter_id,
                actor_id=actor_id,
                status_val="INDETERMINATE_OUTSIDE_DEM",
                terrain_dataset_id=None,
                native_resolution_m=None,
                coverage_fraction=0.0,
                geometry_geojson=None,
                excluded_regions_geojson=None,
                constraints_used={
                    "max_slope_deg": req.max_slope_deg,
                    "max_roughness_m": req.max_roughness_m,
                    "max_radius_m": req.max_radius_m,
                },
                constraints_missing=[],
                limitations=[
                    "Landing site falls outside validated processed DEM coverage; cannot verify terrain slope or roughness.",
                    "An arbitrary circular buffer was explicitly refused to preserve scientific validity.",
                ],
                provenance={"method": ALGORITHM_ID, "version": ALGORITHM_VERSION},
                now_iso=now_iso,
            )

        computed = self._run_dem_bfs_perimeter(
            manifest=manifest_info,
            center_lat=float(ls["latitude"]),
            center_lon_east=float(ls["longitude_east"]),
            max_slope_deg=float(req.max_slope_deg),
            max_roughness_m=float(req.max_roughness_m),
            max_radius_m=float(req.max_radius_m),
            min_contiguous_cells=req.min_contiguous_cells,
        )

        return self._persist_perimeter_result(
            mission_id=mission_id,
            landing_site_id=ls["landing_site_id"],
            perimeter_id=perimeter_id,
            actor_id=actor_id,
            status_val=computed["status"],
            terrain_dataset_id=computed["dataset_id"],
            native_resolution_m=computed["native_resolution_m"],
            coverage_fraction=computed["coverage_fraction"],
            geometry_geojson=computed["geometry_geojson"],
            excluded_regions_geojson=computed["excluded_regions_geojson"],
            constraints_used={
                "max_slope_deg": float(req.max_slope_deg),
                "max_roughness_m": float(req.max_roughness_m),
                "max_radius_m": float(req.max_radius_m),
                "min_contiguous_cells": req.min_contiguous_cells,
            },
            constraints_missing=[],
            limitations=computed["limitations"],
            provenance=computed["provenance"],
            now_iso=now_iso,
        )

    def approve_perimeter(
        self,
        mission_id: str,
        perimeter_id: str,
        actor_id: str,
    ) -> LandingSiteBundleResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM landing_site_perimeters WHERE perimeter_id = ? AND mission_id = ?",
                (perimeter_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perimeter evaluation not found.")
            if row["status"] != "EVALUATED_WITH_VALIDATED_DEM":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot approve an indeterminate perimeter without validated DEM coverage.",
                )
            conn.execute(
                """
                UPDATE landing_site_perimeters
                SET operator_approved = 1, approved_by = ?, approved_at_utc = ?
                WHERE perimeter_id = ?
                """,
                (actor_id, now_iso, perimeter_id),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="LANDING_SITE_PERIMETER_APPROVED",
                payload={"perimeter_id": perimeter_id, "approved_at_utc": now_iso},
            )
        bundle = self.get_bundle(mission_id)
        self._hub.publish_mission_event(
            mission_id,
            event_type="LANDING_SITE_PERIMETER_APPROVED",
            payload=bundle.model_dump(),
            event_seq=ev.event_seq,
        )
        return bundle

    # ------------------------------------------------------------------
    # Internals: DEM Selection & Grid BFS Polygon Extraction
    # ------------------------------------------------------------------

    def _select_covering_manifest(self, lat: float, lon_east: float) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for mpath in self._processed_dir.glob("*.processing.json"):
            try:
                m = json.loads(mpath.read_text(encoding="utf-8"))
                files = m.get("files") or {}
                if not all(files.get(k) for k in ("dem", "slope", "roughness")):
                    continue
                dem_path = self._processed_dir / files["dem"]
                if not dem_path.exists():
                    continue
                with rasterio.open(dem_path) as src:
                    sb = src.bounds
                    s_lon = normalize_longitude_360(lon_east) if sb.right > 180.0 else normalize_longitude_180(lon_east)
                    if sb.left <= s_lon <= sb.right and sb.bottom <= lat <= sb.top:
                        m["_resolved_lon"] = s_lon
                        candidates.append(m)
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort(key=lambda item: float(item.get("dx_meters", 1e12)))
        return candidates[0]

    def _run_dem_bfs_perimeter(
        self,
        *,
        manifest: Dict[str, Any],
        center_lat: float,
        center_lon_east: float,
        max_slope_deg: float,
        max_roughness_m: float,
        max_radius_m: float,
        min_contiguous_cells: int,
    ) -> Dict[str, Any]:
        files = manifest["files"]
        dem_path = self._processed_dir / files["dem"]
        slope_path = self._processed_dir / files["slope"]
        rough_path = self._processed_dir / files["roughness"]
        dataset_id = manifest.get("source_dataset_id", "unknown")

        with rasterio.open(dem_path) as dem_src, rasterio.open(slope_path) as slope_src, rasterio.open(rough_path) as rough_src:
            dx_native = float(manifest.get("dx_meters") or 0.0)
            dy_native = float(manifest.get("dy_meters") or 0.0)
            if dx_native <= 0 or dy_native <= 0:
                dx_native, dy_native = angular_displacement_to_metric(
                    center_lat, abs(dem_src.transform.a), abs(dem_src.transform.e)
                )

            # Determine bounding pixel window around max_radius_m
            deg_per_px_x = abs(dem_src.transform.a)
            deg_per_px_y = abs(dem_src.transform.e)
            half_cols = max(8, int(math.ceil(max_radius_m / max(dx_native, 0.5))) + 2)
            half_rows = max(8, int(math.ceil(max_radius_m / max(dy_native, 0.5))) + 2)

            s_lon = float(manifest.get("_resolved_lon", center_lon_east))
            c_row, c_col = dem_src.index(s_lon, center_lat)

            r0 = max(0, c_row - half_rows)
            r1 = min(dem_src.height, c_row + half_rows + 1)
            c0 = max(0, c_col - half_cols)
            c1 = min(dem_src.width, c_col + half_cols + 1)
            win = Window(c0, r0, c1 - c0, r1 - r0)

            dem_arr = dem_src.read(1, window=win).astype(np.float64)
            slope_arr = slope_src.read(1, window=win).astype(np.float64)
            rough_arr = rough_src.read(1, window=win).astype(np.float64)

            dem_nodata = dem_src.nodatavals[0]
            slope_nodata = slope_src.nodatavals[0]
            rough_nodata = rough_src.nodatavals[0]

            # Stride downsample if window is very large (keep execution deterministic and crisp <= 90x90 grid)
            h, w = dem_arr.shape
            stride = max(1, int(math.ceil(max(h, w) / 72.0)))
            dem_g = dem_arr[::stride, ::stride]
            slope_g = slope_arr[::stride, ::stride]
            rough_g = rough_arr[::stride, ::stride]

            gh, gw = dem_g.shape
            seed_r = min(gh - 1, max(0, (c_row - r0) // stride))
            seed_c = min(gw - 1, max(0, (c_col - c0) // stride))

            valid_dem = np.isfinite(dem_g)
            if dem_nodata is not None and np.isfinite(dem_nodata):
                valid_dem &= dem_g != float(dem_nodata)

            valid_slope = np.isfinite(slope_g)
            if slope_nodata is not None and np.isfinite(slope_nodata):
                valid_slope &= slope_g != float(slope_nodata)

            valid_rough = np.isfinite(rough_g)
            if rough_nodata is not None and np.isfinite(rough_nodata):
                valid_rough &= rough_g != float(rough_nodata)

            known_mask = valid_dem & valid_slope & valid_rough
            step_m_x = dx_native * stride
            step_m_y = dy_native * stride

            # Distance filter inside requested max_radius_m
            rr, cc = np.ogrid[:gh, :gw]
            dist_m = np.hypot((rr - seed_r) * step_m_y, (cc - seed_c) * step_m_x)
            in_radius = dist_m <= max_radius_m

            passable = known_mask & in_radius & (slope_g <= max_slope_deg) & (rough_g <= max_roughness_m)

            visited = np.zeros((gh, gw), dtype=bool)
            q: deque[Tuple[int, int]] = deque()
            if passable[seed_r, seed_c]:
                visited[seed_r, seed_c] = True
                q.append((seed_r, seed_c))
            while q:
                cr, cc_i = q.popleft()
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = cr + dr, cc_i + dc
                    if 0 <= nr < gh and 0 <= nc < gw and not visited[nr, nc] and passable[nr, nc]:
                        visited[nr, nc] = True
                        q.append((nr, nc))

            passable_count = int(visited.sum())
            radius_cells = max(1, int(in_radius.sum()))
            coverage_fraction = round(float(known_mask[in_radius].sum()) / float(radius_cells), 4)

            cell_dlon = deg_per_px_x * stride
            cell_dlat = deg_per_px_y * stride

            def _cell_box(gr: int, gc: int) -> Polygon:
                raw_r = r0 + gr * stride
                raw_c = c0 + gc * stride
                lon_w, lat_n = dem_src.xy(raw_r - 0.5, raw_c - 0.5, offset="ul")
                lon_e = lon_w + cell_dlon
                lat_s = lat_n - cell_dlat
                lon_w_360 = normalize_longitude_360(lon_w)
                lon_e_360 = lon_w_360 + cell_dlon
                return Polygon(
                    [
                        (lon_w_360, lat_s),
                        (lon_e_360, lat_s),
                        (lon_e_360, lat_n),
                        (lon_w_360, lat_n),
                        (lon_w_360, lat_s),
                    ]
                )

            if passable_count < min_contiguous_cells:
                return {
                    "status": "INDETERMINATE_OUTSIDE_DEM" if not bool(known_mask[seed_r, seed_c]) else "EVALUATED_WITH_VALIDATED_DEM",
                    "dataset_id": dataset_id,
                    "native_resolution_m": round(dx_native, 3),
                    "coverage_fraction": coverage_fraction,
                    "geometry_geojson": None,
                    "excluded_regions_geojson": None,
                    "limitations": [
                        f"Only {passable_count} contiguous DEM cells satisfy slope <= {max_slope_deg} deg and roughness <= {max_roughness_m} m.",
                        "Center cell or contiguous corridor violates terrain constraints; no traversable polygon emitted.",
                        f"Coarse evaluation stride={stride} ({round(step_m_x, 2)} m/cell).",
                    ],
                    "provenance": {
                        "method": ALGORITHM_ID,
                        "version": ALGORITHM_VERSION,
                        "dataset_id": dataset_id,
                        "stride": stride,
                        "effective_cell_m": round(step_m_x, 3),
                        "passable_cells": passable_count,
                    },
                }

            passable_polys = [_cell_box(int(r), int(c)) for r, c in np.argwhere(visited)]
            perimeter_geom = unary_union(passable_polys)

            excluded_mask = in_radius & (~visited)
            excluded_polys = [_cell_box(int(r), int(c)) for r, c in np.argwhere(excluded_mask)]
            excluded_geom = unary_union(excluded_polys) if excluded_polys else None

            return {
                "status": "EVALUATED_WITH_VALIDATED_DEM",
                "dataset_id": dataset_id,
                "native_resolution_m": round(dx_native, 3),
                "coverage_fraction": coverage_fraction,
                "geometry_geojson": {
                    "type": "Feature",
                    "properties": {
                        "classification": PLANNING_BOUNDARY_LABEL,
                        "dataset_id": dataset_id,
                        "passable_cells": passable_count,
                        "area_approx_m2": round(passable_count * step_m_x * step_m_y, 1),
                        "effective_cell_m": round(step_m_x, 2),
                    },
                    "geometry": mapping(perimeter_geom),
                },
                "excluded_regions_geojson": (
                    {
                        "type": "Feature",
                        "properties": {
                            "reason": "Exceeds slope/roughness limits, disconnected, or DEM no-data",
                            "excluded_cells": len(excluded_polys),
                        },
                        "geometry": mapping(excluded_geom),
                    }
                    if excluded_geom is not None
                    else None
                ),
                "limitations": [
                    PLANNING_BOUNDARY_LABEL,
                    f"Sub-resolution hazards below {round(dx_native, 2)} m native DEM pixel spacing cannot be resolved.",
                    "Boundary reflects DEM slope and TRI roughness constraints only; regolith bearing strength and radiation are excluded.",
                ],
                "provenance": {
                    "method": ALGORITHM_ID,
                    "version": ALGORITHM_VERSION,
                    "dataset_id": dataset_id,
                    "source_product_id": manifest.get("source_product_id"),
                    "stride": stride,
                    "effective_cell_m": round(step_m_x, 3),
                    "passable_cells": passable_count,
                    "coverage_fraction": coverage_fraction,
                },
            }

    def _persist_perimeter_result(
        self,
        *,
        mission_id: str,
        landing_site_id: str,
        perimeter_id: str,
        actor_id: str,
        status_val: str,
        terrain_dataset_id: Optional[str],
        native_resolution_m: Optional[float],
        coverage_fraction: Optional[float],
        geometry_geojson: Optional[Dict[str, Any]],
        excluded_regions_geojson: Optional[Dict[str, Any]],
        constraints_used: Dict[str, Any],
        constraints_missing: List[str],
        limitations: List[str],
        provenance: Dict[str, Any],
        now_iso: str,
    ) -> LandingSiteBundleResponse:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO landing_site_perimeters (
                    perimeter_id, mission_id, landing_site_id, status,
                    algorithm_id, algorithm_version, terrain_dataset_id,
                    native_resolution_m, coverage_fraction,
                    geometry_geojson, excluded_regions_geojson,
                    constraints_used_json, constraints_missing_json,
                    limitations_json, provenance_json,
                    operator_approved, approved_by, approved_at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, ?)
                """,
                (
                    perimeter_id,
                    mission_id,
                    landing_site_id,
                    status_val,
                    ALGORITHM_ID,
                    ALGORITHM_VERSION,
                    terrain_dataset_id,
                    native_resolution_m,
                    coverage_fraction,
                    json.dumps(geometry_geojson) if geometry_geojson else None,
                    json.dumps(excluded_regions_geojson) if excluded_regions_geojson else None,
                    json.dumps(constraints_used),
                    json.dumps(constraints_missing),
                    json.dumps(limitations),
                    json.dumps(provenance),
                    now_iso,
                ),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="LANDING_SITE_PERIMETER_COMPUTED",
                payload={
                    "perimeter_id": perimeter_id,
                    "status": status_val,
                    "terrain_dataset_id": terrain_dataset_id,
                    "coverage_fraction": coverage_fraction,
                },
            )
        bundle = self.get_bundle(mission_id)
        self._hub.publish_mission_event(
            mission_id,
            event_type="LANDING_SITE_PERIMETER_COMPUTED",
            payload=bundle.model_dump(),
            event_seq=ev.event_seq,
        )
        return bundle

    @staticmethod
    def _row_to_landing_site(row: sqlite3.Row) -> LandingSiteResponse:
        return LandingSiteResponse(
            landing_site_id=row["landing_site_id"],
            mission_id=row["mission_id"],
            name=row["name"],
            latitude=float(row["latitude"]),
            longitude_east=float(row["longitude_east"]),
            crs=row["crs"],
            latitude_convention=row["latitude_convention"],
            longitude_direction=row["longitude_direction"],
            source=row["source"],
            source_record_id=row["source_record_id"],
            uncertainty_m=float(row["uncertainty_m"]) if row["uncertainty_m"] is not None else None,
            elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
            terrain_dataset_id=row["terrain_dataset_id"],
            dem_coverage_state=row["dem_coverage_state"],
            registration_state=row["registration_state"],
            updated_by=row["updated_by"],
            history=json.loads(row["history_json"] or "[]"),
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )

    @staticmethod
    def _row_to_perimeter(row: sqlite3.Row) -> LandingSitePerimeterResponse:
        return LandingSitePerimeterResponse(
            perimeter_id=row["perimeter_id"],
            mission_id=row["mission_id"],
            landing_site_id=row["landing_site_id"],
            status=row["status"],
            classification_label=PLANNING_BOUNDARY_LABEL,
            algorithm_id=row["algorithm_id"],
            algorithm_version=row["algorithm_version"],
            terrain_dataset_id=row["terrain_dataset_id"],
            native_resolution_m=float(row["native_resolution_m"]) if row["native_resolution_m"] is not None else None,
            coverage_fraction=float(row["coverage_fraction"]) if row["coverage_fraction"] is not None else None,
            geometry_geojson=json.loads(row["geometry_geojson"]) if row["geometry_geojson"] else None,
            excluded_regions_geojson=json.loads(row["excluded_regions_geojson"]) if row["excluded_regions_geojson"] else None,
            constraints_used=json.loads(row["constraints_used_json"] or "{}"),
            constraints_missing=json.loads(row["constraints_missing_json"] or "[]"),
            limitations=json.loads(row["limitations_json"] or "[]"),
            provenance=json.loads(row["provenance_json"] or "{}"),
            operator_approved=bool(row["operator_approved"]),
            approved_by=row["approved_by"],
            approved_at_utc=row["approved_at_utc"],
            created_at_utc=row["created_at_utc"],
        )
