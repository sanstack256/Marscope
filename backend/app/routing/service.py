"""
MARSCOPE Science-Aware Route Computation & Navigation Service
Integrates verified DEM coverage, TerrainGrid A*/Dijkstra pathfinding,
TargetRegistryService & CompositionSearchService scientific evidence corridors,
transparent Tobler/grade walking assumptions, return-trip budgets, and GeoJSON export.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.physics.models.surface import calculate_gravitational_potential_energy
from app.routing.graph import RoutePlanningError, TerrainGrid, build_terrain_grid_from_dataset
from app.routing.instructions import generate_turn_by_turn_instructions
from app.routing.models import MODE_POLICIES, PathAlgorithm, RoutingMode
from app.routing.pathfinder import optimize_intermediate_stop_order, simplify_leg_safely, solve_grid_leg
from app.routing.schemas import (
    BudgetDiagnostic,
    RouteCompareEntry,
    RouteCompareRequest,
    RouteCompareResponse,
    RouteComputeRequest,
    RouteComputeResponse,
    RouteCoordinateInput,
    RouteLegSummary,
    RoutePlanningConstraints,
    RouteStatusResponse,
    RouteValidationResponse,
    RouteVertex,
    ScienceStopSummary,
    SimplificationDiagnostic,
    SnapDiagnostic,
)
from app.schemas.dataset import Dataset
from app.science.composition.search import CompositionSearchService, StructuredCompositionQuery
from app.science.target_registry import TargetRegistryService


class ScienceAwareRoutingService:
    """Thread-safe stateful orchestrator for Martian EVA surface route planning."""

    def __init__(
        self,
        catalog_service: DatasetCatalogService,
        raw_dir: Path,
        target_registry: Optional[TargetRegistryService] = None,
        composition_search: Optional[CompositionSearchService] = None,
        max_stored_routes: int = 100,
    ):
        self.catalog_service = catalog_service
        self.raw_dir = raw_dir
        self.target_registry = target_registry
        self.composition_search = composition_search
        self._max_stored = max_stored_routes
        self._routes: "OrderedDict[str, RouteComputeResponse]" = OrderedDict()
        self._lock = threading.Lock()

    def _store_route(self, route: RouteComputeResponse) -> None:
        with self._lock:
            self._routes[route.route_id] = route
            self._routes.move_to_end(route.route_id)
            while len(self._routes) > self._max_stored:
                self._routes.popitem(last=False)

    def get_route(self, route_id: str) -> RouteComputeResponse:
        with self._lock:
            r = self._routes.get(route_id)
        if not r:
            raise KeyError(f"Route '{route_id}' not found or expired from session store.")
        return r

    def _list_local_dems(self) -> List[Dataset]:
        dems: List[Dataset] = []
        for ds in self.catalog_service.list_datasets():
            if "DEM" not in ds.product_type.upper():
                continue
            try:
                p, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
                if p.exists():
                    dems.append(ds)
            except FileNotFoundError:
                continue
        # Prefer highest spatial resolution first
        dems.sort(key=lambda d: d.horizontal_resolution_meters if d.horizontal_resolution_meters is not None else 1e9)
        return dems

    def _select_dem_for_points(
        self, dataset_id: Optional[str], points: List[Tuple[float, float]]
    ) -> Dataset:
        local_dems = self._list_local_dems()
        if not local_dems:
            raise RoutePlanningError(
                "No locally downloaded DEM datasets are available for routing.",
                detail={"reason": "no_local_dem_datasets"},
            )
        if dataset_id:
            ds = next((d for d in local_dems if d.id == dataset_id), None)
            if not ds:
                raise RoutePlanningError(
                    f"Requested DEM '{dataset_id}' is not available locally.",
                    detail={"dataset_id": dataset_id, "available_dems": [d.id for d in local_dems]},
                )
            return ds

        # Automatically select highest-resolution local DEM whose footprint covers ALL requested stops
        for ds in local_dems:
            cov = ds.coverage
            if all(
                cov.min_latitude <= lat <= cov.max_latitude and cov.min_longitude <= lon <= cov.max_longitude
                for lat, lon in points
            ):
                return ds

        # Fallback: best DEM overlapping the bounding box centroid
        c_lat = sum(p[0] for p in points) / float(len(points))
        c_lon = sum(p[1] for p in points) / float(len(points))
        for ds in local_dems:
            cov = ds.coverage
            if cov.min_latitude <= c_lat <= cov.max_latitude and cov.min_longitude <= c_lon <= cov.max_longitude:
                return ds
        return local_dems[0]

    def _gather_stops_and_science(
        self, req: RouteComputeRequest
    ) -> Tuple[List[Tuple[str, float, float, Optional[str], Optional[Dict[str, Any]]]], List[Tuple[float, float, float]], List[Tuple[str, float, float]], int]:
        """Resolve Start, Target stops, Destination, and nearby science corridor points."""
        stops: List[Tuple[str, float, float, Optional[str], Optional[Dict[str, Any]]]] = []
        science_corridor: List[Tuple[float, float, float]] = []
        nearby_lookup: List[Tuple[str, float, float]] = []

        # Registered ScienceTarget stops
        if self.target_registry:
            for tid in req.target_ids:
                tgt = self.target_registry.get_target(tid)
                if not tgt:
                    raise RoutePlanningError(
                        f"Science target '{tid}' not found in verified target registry.",
                        detail={"reason": "unknown_target_id", "target_id": tid},
                    )
                meta = {
                    "target_id": tgt.id,
                    "name": tgt.name,
                    "geology_type": tgt.geology_type,
                    "scientific_value": tgt.scientific_value,
                    "matched_species": tgt.matched_species,
                    "instrument_source": tgt.instrument_source,
                }
                stops.append(("target", tgt.latitude, tgt.longitude, tgt.name, meta))
                science_corridor.append((tgt.latitude, tgt.longitude, max(0.5, tgt.scientific_value)))
                nearby_lookup.append((tgt.name, tgt.latitude, tgt.longitude))

            # Include other registered targets near corridor for Science-Priority context
            for tgt in self.target_registry.list_targets()[:80]:
                science_corridor.append((tgt.latitude, tgt.longitude, max(0.25, tgt.scientific_value * 0.85)))
                nearby_lookup.append((tgt.name, tgt.latitude, tgt.longitude))

        # Explicit user waypoint stops
        for idx, wp in enumerate(req.waypoints):
            label = wp.label or f"Waypoint {idx + 1}"
            meta = {"target_id": wp.target_id, "name": label, "scientific_value": 0.7 if wp.target_id else 0.5}
            stops.append(("waypoint", wp.lat, wp.lon_east, label, meta))
            if wp.target_id:
                science_corridor.append((wp.lat, wp.lon_east, 0.75))
            nearby_lookup.append((label, wp.lat, wp.lon_east))

        # Query CompositionSearchService around start/destination corridor if index available
        ev_hits_count = 0
        idx_available = False
        if self.composition_search:
            try:
                idx_available = bool(self.composition_search.index.get_status().index_available)
            except Exception:
                idx_available = False

        if self.composition_search and idx_available:
            mid_lat = 0.5 * (req.start.lat + req.destination.lat)
            mid_lon = 0.5 * (req.start.lon_east + req.destination.lon_east)
            span_m = mars_great_circle_distance_meters(
                req.start.lat, req.start.lon_east, req.destination.lat, req.destination.lon_east
            )
            search_radius = max(500.0, min(5000.0, span_m * 0.75 + 400.0))
            for q_term in ("SiO2", "SO3", "Smectite", "Sulfate"):
                try:
                    res = self.composition_search.search(
                        StructuredCompositionQuery(
                            query=q_term,
                            astronaut_latitude=mid_lat,
                            astronaut_longitude=mid_lon,
                            max_distance_m=search_radius,
                            limit=35,
                        )
                    )
                    for hit in res.hits:
                        ev = hit.evidence
                        if ev.latitude is not None and ev.longitude_east is not None:
                            score = hit.ranking.composite_rank_score if hit.ranking.composite_rank_score is not None else 0.5
                            science_corridor.append(
                                (ev.latitude, ev.longitude_east, min(1.0, max(0.3, float(score))))
                            )
                            tname = ev.target_name or ev.canonical_species_name
                            nearby_lookup.append(
                                (f"{tname} ({ev.canonical_species_name})", ev.latitude, ev.longitude_east)
                            )
                            ev_hits_count += 1
                except Exception:
                    continue

        return stops, science_corridor, nearby_lookup, ev_hits_count

    @staticmethod
    def _estimate_segment_seconds(
        horiz_m: float,
        dz_m: float,
        slope_deg: float,
        walking_speed_m_per_s: Optional[float],
    ) -> Optional[float]:
        if walking_speed_m_per_s is None or walking_speed_m_per_s <= 0:
            return None
        # Grade-sensitive speed scaling anchored cleanly to user-supplied flat-ground walking_speed
        # (Tobler-style grade attenuation factor normalized to 1.0 at zero slope, capped >= 0.25)
        slope_tan = dz_m / max(0.1, horiz_m)
        ref_tobler_flat = math.exp(-3.5 * 0.05)  # exp(-0.175) = 0.83946
        grade_factor = math.exp(-3.5 * abs(slope_tan + 0.05)) / ref_tobler_flat
        # Mild local slope factor so steep side-slopes cannot claim flat-ground speed
        local_atten = max(0.35, 1.0 - (max(0.0, slope_deg) / 55.0))
        eff_speed = walking_speed_m_per_s * max(0.22, min(1.1, min(grade_factor, local_atten)))
        return horiz_m / eff_speed

    def get_status(self) -> RouteStatusResponse:
        return RouteStatusResponse(
            supported_modes=[m.value for m in RoutingMode],
            supported_algorithms=[a.value for a in PathAlgorithm],
            available_dem_datasets=[d.id for d in self._list_local_dems()],
            stored_route_count=len(self._routes),
            safety_certification_enabled=False,
            scientific_constraints=[
                "Routes strictly avoid no-data pixels, out-of-bounds areas, and slopes exceeding effective limits.",
                "Diagonal corner cutting across blocked/no-data pixels is strictly disabled.",
                "Controlled simplification verifies every intermediate DEM cell before accepting shortcuts.",
                "Default mobility speeds represent user-configured planning assumptions (unvalidated physiologically).",
                "No oxygen consumption or metabolic survival certification is fabricated.",
            ],
        )

    def validate_inputs(self, req: RouteComputeRequest) -> RouteValidationResponse:
        stops, sci_corridor, _, _ = self._gather_stops_and_science(req)
        all_pts = [(req.start.lat, req.start.lon_east)] + [(s[1], s[2]) for s in stops] + [(req.destination.lat, req.destination.lon_east)]
        ds = self._select_dem_for_points(req.dataset_id, all_pts)
        policy = MODE_POLICIES[req.mode]
        grid = build_terrain_grid_from_dataset(
            ds,
            self.raw_dir,
            all_pts,
            req.constraints,
            policy.effective_slope_limit_factor,
            science_points=sci_corridor,
        )
        snaps: List[SnapDiagnostic] = []
        issues: List[str] = []
        check_list = (
            [("start", req.start.lat, req.start.lon_east)]
            + [(f"stop_{i}", s[1], s[2]) for i, s in enumerate(stops)]
            + [("destination", req.destination.lat, req.destination.lon_east)]
        )
        for role, lat, lon in check_list:
            try:
                _, _, sd = grid.snap_to_traversable(lat, lon, role, req.constraints.snap_radius_m)
                snaps.append(sd)
            except RoutePlanningError as exc:
                issues.append(exc.message)

        total = float(grid.rows * grid.cols)
        trav_frac = float(grid.traversable.sum()) / max(1.0, total)
        nodata_frac = float((~grid.valid_elev).sum()) / max(1.0, total)
        blocked_slope = float((grid.valid_elev & (~grid.traversable)).sum()) / max(1.0, total)
        return RouteValidationResponse(
            valid=(len(issues) == 0),
            dataset_id=ds.id,
            source_product_id=ds.product_id,
            native_dem_resolution_m=grid.native_resolution_m,
            solver_grid_spacing_m=round(0.5 * (grid.dx_m + grid.dy_m), 3),
            effective_slope_limit_deg=round(grid.effective_slope_limit_deg, 2),
            traversable_cell_fraction=round(trav_frac, 4),
            blocked_slope_cell_fraction=round(blocked_slope, 4),
            nodata_cell_fraction=round(nodata_frac, 4),
            snap_diagnostics=snaps,
            issues=issues,
        )

    def compute_route(
        self,
        req: RouteComputeRequest,
        override_grid: Optional[TerrainGrid] = None,
        override_dataset_id: str = "synthetic_test_dem",
        override_product_id: str = "SYNTHETIC_DEM",
    ) -> RouteComputeResponse:
        """
        Compute a full multi-leg science-aware surface route over real DEMs (or an injected
        TerrainGrid for deterministic unit tests).
        """
        t0 = time.perf_counter()
        policy = MODE_POLICIES[req.mode]
        stops, sci_corridor, nearby_lookup, ev_hits = self._gather_stops_and_science(req)
        all_pts = [(req.start.lat, req.start.lon_east)] + [(s[1], s[2]) for s in stops] + [(req.destination.lat, req.destination.lon_east)]

        if override_grid is not None:
            ds = None
            grid = override_grid
            ds_id = override_dataset_id
            prod_id = override_product_id
        else:
            ds = self._select_dem_for_points(req.dataset_id, all_pts)
            ds_id = ds.id
            prod_id = ds.product_id
            grid = build_terrain_grid_from_dataset(
                ds,
                self.raw_dir,
                all_pts,
                req.constraints,
                policy.effective_slope_limit_factor,
                science_points=sci_corridor,
            )

        snaps: List[SnapDiagnostic] = []
        sr, sc, s_snap = grid.snap_to_traversable(req.start.lat, req.start.lon_east, "start", req.constraints.snap_radius_m)
        snaps.append(s_snap)

        stop_cells: List[Tuple[int, int, Tuple[str, float, float, Optional[str], Optional[Dict[str, Any]]]]] = []
        for idx, s in enumerate(stops):
            role_tag = f"target:{s[4]['target_id']}" if (s[4] and s[4].get("target_id")) else f"waypoint:{idx + 1}"
            rr, cc, snap_d = grid.snap_to_traversable(s[1], s[2], role_tag, req.constraints.snap_radius_m)
            snaps.append(snap_d)
            stop_cells.append((rr, cc, s))

        dr, dc, d_snap = grid.snap_to_traversable(req.destination.lat, req.destination.lon_east, "destination", req.constraints.snap_radius_m)
        snaps.append(d_snap)

        # Order intermediate targets cleanly
        if len(stop_cells) > 1 and req.constraints.optimize_target_order:
            ordered_idx = optimize_intermediate_stop_order(
                grid, (sr, sc), [(x[0], x[1]) for x in stop_cells], (dr, dc), policy, req.algorithm
            )
            ordered_stops = [stop_cells[i] for i in ordered_idx]
        else:
            ordered_stops = list(stop_cells)

        visit_order_ids = [
            (x[2][4].get("target_id") or x[2][3] or f"stop_{i+1}") if x[2][4] else (x[2][3] or f"stop_{i+1}")
            for i, x in enumerate(ordered_stops)
        ]

        # Build sequence of navigation legs
        node_chain: List[Dict[str, Any]] = [
            {"rc": (sr, sc), "role": "start", "label": req.start.label or "Start Position", "meta": None, "is_return": False}
        ]
        for rr, cc, s_info in ordered_stops:
            node_chain.append(
                {
                    "rc": (rr, cc),
                    "role": s_info[0],
                    "label": s_info[3] or "Science Target",
                    "meta": s_info[4],
                    "is_return": False,
                }
            )
        node_chain.append(
            {
                "rc": (dr, dc),
                "role": "destination",
                "label": req.destination.label or "Destination",
                "meta": None,
                "is_return": False,
            }
        )
        if req.constraints.return_to_start:
            node_chain.append(
                {
                    "rc": (sr, sc),
                    "role": "start_return",
                    "label": f"Return to {req.start.label or 'Start'}",
                    "meta": None,
                    "is_return": True,
                }
            )

        # Solve & safely simplify each leg
        all_vertices: List[RouteVertex] = []
        legs: List[RouteLegSummary] = []
        total_raw_nodes = 0
        total_checked = 0
        total_accepted = 0
        total_rejected = 0
        all_simp_valid = True
        total_cost = 0.0
        total_expanded = 0
        cum_dist_m = 0.0
        seq_counter = 0
        all_raw_slopes: List[float] = []
        all_raw_tris: List[float] = []

        for leg_i in range(len(node_chain) - 1):
            n_from = node_chain[leg_i]
            n_to = node_chain[leg_i + 1]
            leg_res = solve_grid_leg(grid, n_from["rc"], n_to["rc"], policy, req.algorithm)
            total_cost += leg_res.total_cost
            total_expanded += leg_res.nodes_expanded

            simp_cells, simp_diag = simplify_leg_safely(
                grid, leg_res.cells, epsilon_m=req.constraints.simplification_epsilon_m
            )
            total_raw_nodes += simp_diag.raw_grid_nodes
            total_checked += simp_diag.segments_checked
            total_accepted += simp_diag.shortcuts_accepted
            total_rejected += simp_diag.shortcuts_rejected_obstacle_or_nodata
            all_simp_valid = all_simp_valid and simp_diag.all_simplified_segments_verified_valid

            leg_horiz = 0.0
            leg_surf = 0.0
            leg_gain = 0.0
            leg_loss = 0.0
            leg_slopes: List[float] = []
            leg_tris: List[float] = []
            for ri in range(len(leg_res.cells)):
                rc_r, rc_c = leg_res.cells[ri]
                if math.isfinite(grid.slope_deg[rc_r, rc_c]):
                    leg_slopes.append(float(grid.slope_deg[rc_r, rc_c]))
                if ri > 0:
                    pr, pc = leg_res.cells[ri - 1]
                    step_h = math.hypot((rc_c - pc) * grid.dx_m, (rc_r - pr) * grid.dy_m)
                    step_dz = abs(float(grid.elevation_m[rc_r, rc_c]) - float(grid.elevation_m[pr, pc]))
                    leg_slopes.append(math.degrees(math.atan2(step_dz, max(0.01, step_h))))
                if math.isfinite(grid.tri_m[rc_r, rc_c]):
                    leg_tris.append(float(grid.tri_m[rc_r, rc_c]))
            all_raw_slopes.extend(leg_slopes)
            all_raw_tris.extend(leg_tris)

            leg_secs = 0.0
            has_time = req.constraints.walking_speed_m_per_s is not None
            v_start_seq = seq_counter

            start_loop = 0 if leg_i == 0 else 1
            if leg_i == 0:
                r0, c0 = simp_cells[0]
                z0 = float(grid.elevation_m[r0, c0])
                slp0 = float(grid.slope_deg[r0, c0]) if math.isfinite(grid.slope_deg[r0, c0]) else None
                tri0 = float(grid.tri_m[r0, c0]) if math.isfinite(grid.tri_m[r0, c0]) else None
                all_vertices.append(
                    RouteVertex(
                        seq=seq_counter,
                        lat=round(float(grid.lats[r0]), 7),
                        lon_east=round(float(grid.lons_east[c0]), 7),
                        elevation_m=round(z0, 3),
                        slope_deg=round(slp0, 3) if slp0 is not None else None,
                        roughness_tri_m=round(tri0, 3) if tri0 is not None else None,
                        cumulative_distance_m=0.0,
                        segment_distance_m=0.0,
                        is_stop=True,
                        stop_role=n_from["role"],
                        stop_label=n_from["label"],
                        target_id=None,
                        science_corridor_score=round(float(grid.science_field[r0, c0]), 3),
                    )
                )
                seq_counter += 1
            else:
                v_start_seq = seq_counter - 1

            for k in range(1, len(simp_cells)):
                rp, cp = simp_cells[k - 1]
                rc_cur, cc_cur = simp_cells[k]
                lat_p, lon_p = float(grid.lats[rp]), float(grid.lons_east[cp])
                lat_c, lon_c = float(grid.lats[rc_cur]), float(grid.lons_east[cc_cur])
                zp = float(grid.elevation_m[rp, cp])
                zc = float(grid.elevation_m[rc_cur, cc_cur])
                seg_h = mars_great_circle_distance_meters(lat_p, lon_p, lat_c, lon_c)
                dz = zc - zp
                seg_s = math.hypot(seg_h, dz)
                leg_horiz += seg_h
                leg_surf += seg_s
                cum_dist_m += seg_h
                if dz > 0:
                    leg_gain += dz
                else:
                    leg_loss += abs(dz)

                slp_c = float(grid.slope_deg[rc_cur, cc_cur]) if math.isfinite(grid.slope_deg[rc_cur, cc_cur]) else 0.0
                chord_slp = math.degrees(math.atan2(abs(dz), max(0.01, seg_h)))
                eff_slp = max(slp_c, chord_slp)
                leg_slopes.append(eff_slp)
                if math.isfinite(grid.tri_m[rc_cur, cc_cur]):
                    leg_tris.append(float(grid.tri_m[rc_cur, cc_cur]))

                seg_t = self._estimate_segment_seconds(
                    seg_h, dz, eff_slp, req.constraints.walking_speed_m_per_s
                )
                if seg_t is not None:
                    leg_secs += seg_t

                is_last_cell = (k == len(simp_cells) - 1)
                tgt_id = n_to["meta"].get("target_id") if (is_last_cell and n_to["meta"]) else None
                all_vertices.append(
                    RouteVertex(
                        seq=seq_counter,
                        lat=round(lat_c, 7),
                        lon_east=round(lon_c, 7),
                        elevation_m=round(zc, 3),
                        slope_deg=round(slp_c, 3),
                        roughness_tri_m=round(float(grid.tri_m[rc_cur, cc_cur]), 3) if math.isfinite(grid.tri_m[rc_cur, cc_cur]) else None,
                        cumulative_distance_m=round(cum_dist_m, 3),
                        segment_distance_m=round(seg_h, 3),
                        is_stop=is_last_cell,
                        stop_role=n_to["role"] if is_last_cell else None,
                        stop_label=n_to["label"] if is_last_cell else None,
                        target_id=tgt_id,
                        science_corridor_score=round(float(grid.science_field[rc_cur, cc_cur]), 3),
                    )
                )
                seq_counter += 1

            legs.append(
                RouteLegSummary(
                    leg_index=leg_i + 1,
                    from_label=n_from["label"],
                    to_label=n_to["label"],
                    is_return_leg=bool(n_to["is_return"]),
                    horizontal_distance_m=round(leg_horiz, 2),
                    surface_distance_m=round(leg_surf, 2),
                    elevation_gain_m=round(leg_gain, 2),
                    elevation_loss_m=round(leg_loss, 2),
                    mean_slope_deg=round(sum(leg_slopes) / max(1, len(leg_slopes)), 2),
                    max_slope_deg=round(max(leg_slopes) if leg_slopes else 0.0, 2),
                    mean_roughness_tri_m=round(sum(leg_tris) / len(leg_tris), 3) if leg_tris else None,
                    estimated_duration_seconds=round(leg_secs, 1) if has_time else None,
                    total_cost=round(leg_res.total_cost, 2),
                    vertex_start_seq=v_start_seq,
                    vertex_end_seq=seq_counter - 1,
                )
            )

        # Aggregate totals across route using all raw traversed DEM cells for honest max/mean slope & TRI
        tot_horiz = sum(l.horizontal_distance_m for l in legs)
        tot_surf = sum(l.surface_distance_m for l in legs)
        tot_gain = sum(l.elevation_gain_m for l in legs)
        tot_loss = sum(l.elevation_loss_m for l in legs)
        elevs = [v.elevation_m for v in all_vertices]
        slopes = all_raw_slopes if all_raw_slopes else [v.slope_deg for v in all_vertices if v.slope_deg is not None]
        tris = all_raw_tris if all_raw_tris else [v.roughness_tri_m for v in all_vertices if v.roughness_tri_m is not None]
        tot_secs = (
            round(sum(l.estimated_duration_seconds for l in legs if l.estimated_duration_seconds is not None), 1)
            if req.constraints.walking_speed_m_per_s is not None
            else None
        )

        # Budget evaluation (outbound + return vs reserve)
        budget_diag = BudgetDiagnostic(
            evaluated=False,
            return_to_start_included=req.constraints.return_to_start,
            safety_reserve_fraction=req.constraints.safety_reserve_fraction,
        )
        within_budget: Optional[bool] = None
        if req.constraints.max_eva_duration_hours is not None and tot_secs is not None:
            max_sec = req.constraints.max_eva_duration_hours * 3600.0
            usable = max_sec * (1.0 - req.constraints.safety_reserve_fraction)
            margin = usable - tot_secs
            ok = margin >= 0.0
            within_budget = ok
            reason = (
                None
                if ok
                else (
                    f"Estimated traverse duration {tot_secs / 60.0:.1f} min exceeds usable EVA budget "
                    f"{usable / 60.0:.1f} min ({req.constraints.safety_reserve_fraction * 100:.0f}% reserve protected)."
                )
            )
            budget_diag = BudgetDiagnostic(
                evaluated=True,
                return_to_start_included=req.constraints.return_to_start,
                max_eva_duration_seconds=round(max_sec, 1),
                safety_reserve_fraction=req.constraints.safety_reserve_fraction,
                usable_budget_seconds=round(usable, 1),
                estimated_total_duration_seconds=tot_secs,
                margin_seconds=round(margin, 1),
                within_budget=ok,
                reason=reason,
            )
            if req.constraints.enforce_budget and not ok:
                raise RoutePlanningError(
                    reason or "Route exceeds usable EVA budget.",
                    detail={
                        "reason": "eva_budget_exceeded",
                        "budget_diagnostic": budget_diag.model_dump(),
                    },
                )

        # Mars gravitational climb work (exact verified physics equation)
        climb_work_j: Optional[float] = None
        if req.constraints.astronaut_total_mass_kg is not None:
            phys_res = calculate_gravitational_potential_energy(
                mass_kg=req.constraints.astronaut_total_mass_kg,
                delta_h_m=tot_gain,
            )
            climb_work_j = round(float(phys_res.calculated_value), 1)

        # Science targets reached summary
        sci_reached: List[ScienceStopSummary] = []
        for idx, (_, _, s_info) in enumerate(ordered_stops):
            meta = s_info[4] or {}
            sci_reached.append(
                ScienceStopSummary(
                    target_id=meta.get("target_id"),
                    name=s_info[3] or f"Stop {idx + 1}",
                    lat=round(s_info[1], 7),
                    lon_east=round(s_info[2], 7),
                    geology_type=meta.get("geology_type"),
                    scientific_value=meta.get("scientific_value"),
                    matched_species=meta.get("matched_species"),
                    instrument_source=meta.get("instrument_source"),
                    visit_order_index=idx + 1,
                    distance_from_route_m=0.0,
                )
            )

        # Central meridian for Grid North reporting
        central_meridian = 137.41 if "009149" in ds_id else (137.39 if "040770" in ds_id else 180.0)
        instructions = generate_turn_by_turn_instructions(
            all_vertices,
            nearby_lookup,
            native_dem_res_m=grid.native_resolution_m,
            central_meridian_lon=central_meridian,
        )

        # Transparent assumptions & limitations
        if req.constraints.walking_speed_m_per_s is not None:
            assumption_cls = (
                req.constraints.walking_speed_provenance
                or f"User-Configured Planning Assumption (Unvalidated): {req.constraints.walking_speed_m_per_s:.2f} m/s nominal walk"
            )
        else:
            assumption_cls = "Objective Terrain Geometry Only (No walking speed or duration assumed)"

        suit = evaluate_dem_resolution_suitability(
            native_resolution_m=grid.native_resolution_m,
            effective_resolution_m=0.5 * (grid.dx_m + grid.dy_m),
            dem_available=True,
        )
        suit_dump = {k: v.model_dump() for k, v in suit.items()}

        limitations: List[str] = [
            "Route feasibility reflects DEM terrain geometry and user constraints only; NOT an autonomous EVA safety certification."
        ]
        if grid.native_resolution_m > 20.0:
            limitations.append(
                f"Active DEM resolution is ~{grid.native_resolution_m:.1f} m/px; meter-scale rocks, sand ripples, and crevasses are unresolved."
            )
        if tot_secs is None:
            limitations.append("Duration withheld because no explicit walking_speed_m_per_s planning assumption was supplied.")

        sig_payload = json.dumps(
            {
                "dataset_id": ds_id,
                "start": [req.start.lat, req.start.lon_east],
                "dest": [req.destination.lat, req.destination.lon_east],
                "targets": req.target_ids,
                "waypoints": [[w.lat, w.lon_east] for w in req.waypoints],
                "mode": req.mode.value,
                "constraints": req.constraints.model_dump(),
            },
            sort_keys=True,
        )
        sig_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()[:16]
        route_id = f"rt_{req.mode.value}_{uuid.uuid4().hex[:10]}"

        resp = RouteComputeResponse(
            route_id=route_id,
            route_signature=sig_hash,
            dataset_id=ds_id,
            source_product_id=prod_id,
            bearing_convention=(
                f"Mars True North [0, 360) CW azimuth; Equirectangular Grid North also reported relative to lon0={central_meridian:.2f}E"
            ),
            mode=req.mode,
            mode_label=policy.label,
            algorithm=req.algorithm,
            effective_slope_limit_deg=round(grid.effective_slope_limit_deg, 2),
            native_dem_resolution_m=round(grid.native_resolution_m, 3),
            solver_grid_spacing_m=round(0.5 * (grid.dx_m + grid.dy_m), 3),
            solver_grid_shape={"rows": grid.rows, "cols": grid.cols},
            assumption_classification=assumption_cls,
            return_to_start=req.constraints.return_to_start,
            within_budget=within_budget,
            budget_diagnostic=budget_diag,
            total_horizontal_distance_m=round(tot_horiz, 2),
            total_surface_distance_m=round(tot_surf, 2),
            total_elevation_gain_m=round(tot_gain, 2),
            total_elevation_loss_m=round(tot_loss, 2),
            net_elevation_change_m=round(all_vertices[-1].elevation_m - all_vertices[0].elevation_m, 2),
            min_elevation_m=round(min(elevs), 2),
            max_elevation_m=round(max(elevs), 2),
            mean_slope_deg=round(sum(slopes) / max(1, len(slopes)), 2),
            max_slope_deg=round(max(slopes) if slopes else 0.0, 2),
            mean_roughness_tri_m=round(sum(tris) / len(tris), 3) if tris else None,
            estimated_duration_seconds=tot_secs,
            gravitational_climb_work_joules=climb_work_j,
            total_cost=round(total_cost, 2),
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            nodes_expanded=total_expanded,
            target_visit_order=visit_order_ids,
            snap_diagnostics=snaps,
            simplification_diagnostic=SimplificationDiagnostic(
                raw_grid_nodes=total_raw_nodes,
                simplified_vertices=len(all_vertices),
                segments_checked=total_checked,
                shortcuts_accepted=total_accepted,
                shortcuts_rejected_obstacle_or_nodata=total_rejected,
                all_simplified_segments_verified_valid=all_simp_valid,
            ),
            science_targets_reached=sci_reached,
            corridor_evidence_hits_within_150m=ev_hits,
            legs=legs,
            vertices=all_vertices,
            instructions=instructions,
            resolution_suitability=suit_dump,
            limitations=limitations,
        )
        self._store_route(resp)
        return resp

    def compare_routes(self, req: RouteCompareRequest) -> RouteCompareResponse:
        entries: List[RouteCompareEntry] = []
        used_ds = req.dataset_id or "auto"
        used_prod = "unknown"
        for mode in req.modes:
            policy = MODE_POLICIES[mode]
            single_req = RouteComputeRequest(
                dataset_id=req.dataset_id,
                start=req.start,
                destination=req.destination,
                target_ids=req.target_ids,
                waypoints=req.waypoints,
                mode=mode,
                constraints=req.constraints,
            )
            try:
                rt = self.compute_route(single_req)
                used_ds = rt.dataset_id
                used_prod = rt.source_product_id
                entries.append(
                    RouteCompareEntry(
                        mode=mode,
                        mode_label=policy.label,
                        feasible=True,
                        route=rt,
                    )
                )
            except RoutePlanningError as exc:
                entries.append(
                    RouteCompareEntry(
                        mode=mode,
                        mode_label=policy.label,
                        feasible=False,
                        error_reason=exc.message,
                        route=None,
                    )
                )
        return RouteCompareResponse(
            dataset_id=used_ds,
            source_product_id=used_prod,
            comparison=entries,
            comparison_notes=[
                "Conservative tightens effective slope limit (0.80x) and penalizes slope^2, TRI roughness, and no-data edge proximity.",
                "Balanced trades horizontal distance against grade burden and local roughness.",
                "Science Priority preserves positive cost floor (>= 0.45) to favor corridors near verified composition observations and science targets.",
            ],
        )

    def export_geojson(self, route_id: str) -> Dict[str, Any]:
        rt = self.get_route(route_id)
        coords_3d = [
            [v.lon_east if v.lon_east <= 180.0 else v.lon_east - 360.0, v.lat, v.elevation_m]
            for v in rt.vertices
        ]
        features: List[Dict[str, Any]] = [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords_3d},
                "properties": {
                    "feature_role": "planned_route",
                    "route_id": rt.route_id,
                    "mode": rt.mode.value,
                    "dataset_id": rt.dataset_id,
                    "source_product_id": rt.source_product_id,
                    "crs": rt.crs,
                    "total_horizontal_distance_m": rt.total_horizontal_distance_m,
                    "total_elevation_gain_m": rt.total_elevation_gain_m,
                    "max_slope_deg": rt.max_slope_deg,
                    "estimated_duration_seconds": rt.estimated_duration_seconds,
                    "assumption_classification": rt.assumption_classification,
                },
            }
        ]
        for v in rt.vertices:
            if not v.is_stop:
                continue
            lon_180 = v.lon_east if v.lon_east <= 180.0 else v.lon_east - 360.0
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_180, v.lat, v.elevation_m]},
                    "properties": {
                        "feature_role": v.stop_role or "waypoint",
                        "label": v.stop_label,
                        "target_id": v.target_id,
                        "elevation_m": v.elevation_m,
                        "slope_deg": v.slope_deg,
                        "cumulative_distance_m": v.cumulative_distance_m,
                    },
                }
            )
        return {
            "type": "FeatureCollection",
            "name": f"marscope_route_{rt.route_id}",
            "crs_note": f"{rt.crs} (East longitude in [-180, 180] for GeoJSON compatibility, elevation in meters above Mars Areoid datum)",
            "features": features,
        }
