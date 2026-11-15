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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.ingestion.catalog import DatasetCatalogService
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.mobility.resolution import evaluate_dem_resolution_suitability
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.physics.models.surface import calculate_gravitational_potential_energy
from app.routing.graph import RoutePlanningError, TerrainGrid, build_terrain_grid_from_dataset
from app.routing.instructions import generate_turn_by_turn_instructions
from app.routing.models import (
    MODE_POLICIES,
    PathAlgorithm,
    ROUTE_OBJECTIVES_VERSION,
    RouteObjective,
    RoutingMode,
    resolve_routing_policy,
)
from app.routing.pathfinder import (
    optimize_intermediate_stop_order,
    reconstruct_reverse_dijkstra_path,
    simplify_leg_safely,
    solve_grid_leg,
)
from app.routing.schemas import (
    BudgetDiagnostic,
    DistinctRouteCandidate,
    EdgeEvaluationDetail,
    NavigationInstruction,
    RobustRouteCompareRequest,
    RobustRouteCompareResponse,
    RouteCompareEntry,
    RouteCompareRequest,
    RouteCompareResponse,
    RouteComputeRequest,
    RouteComputeResponse,
    RouteCoordinateInput,
    RouteCostDecomposition,
    RouteDecisionExplainer,
    RouteLegSummary,
    RoutePlanningConstraints,
    RouteStatusResponse,
    RouteTraversabilitySummary,
    RouteValidationResponse,
    RouteVertex,
    ScienceStopSummary,
    SimplificationDiagnostic,
    SnapDiagnostic,
)
if TYPE_CHECKING:
    from app.eva_operations.schemas import (
        IndependentReturnAlternative,
        TurnbackCheckpointRecord,
    )
from app.terrain_uncertainty.sensitivity import (
    DEFAULT_SENSITIVITY_POLICY,
    DEFAULT_SENSITIVITY_SCENARIOS,
    RouteSensitivityReport,
    ScenarioSensitivityOutcome,
    SensitivityCategory,
    SensitivityPolicyConfig,
    summarize_sensitivity_outcomes,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
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
        self._route_contexts: Dict[str, Tuple[TerrainGrid, RouteComputeRequest]] = {}
        self._science_cache: "OrderedDict[Any, Tuple[List[Any], List[Tuple[float, float, float]], List[Tuple[str, float, float]], int]]" = OrderedDict()
        self._grid_cache: "OrderedDict[Any, TerrainGrid]" = OrderedDict()
        self._lock = threading.Lock()

    def _store_route(
        self,
        route: RouteComputeResponse,
        grid: Optional[TerrainGrid] = None,
        req: Optional[RouteComputeRequest] = None,
    ) -> None:
        with self._lock:
            self._routes[route.route_id] = route
            self._routes.move_to_end(route.route_id)
            if grid is not None and req is not None:
                self._route_contexts[route.route_id] = (grid, req)
            while len(self._routes) > self._max_stored:
                evicted_id, _ = self._routes.popitem(last=False)
                self._route_contexts.pop(evicted_id, None)

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

        # Automatically select highest-resolution local DEM whose true valid swath footprint covers ALL requested stops
        from app.geospatial.footprints import get_or_extract_dataset_footprint, point_intersects_footprint

        ds_root = Path(self.raw_dir).parent
        for ds in local_dems:
            try:
                fp = get_or_extract_dataset_footprint(ds, dataset_root_dir=ds_root)
                if all(point_intersects_footprint(fp, lat, lon, require_valid_pixels_if_known=True)[0] for lat, lon in points):
                    return ds
            except Exception:
                cov = ds.coverage
                if all(
                    cov.min_latitude <= lat <= cov.max_latitude and cov.min_longitude <= lon <= cov.max_longitude
                    for lat, lon in points
                ):
                    return ds

        # Fallback: best DEM overlapping the bounding box / valid swath centroid
        c_lat = sum(p[0] for p in points) / float(len(points))
        c_lon = sum(p[1] for p in points) / float(len(points))
        for ds in local_dems:
            try:
                fp = get_or_extract_dataset_footprint(ds, dataset_root_dir=ds_root)
                if point_intersects_footprint(fp, c_lat, c_lon, require_valid_pixels_if_known=True)[0]:
                    return ds
            except Exception:
                pass
            cov = ds.coverage
            if cov.min_latitude <= c_lat <= cov.max_latitude and cov.min_longitude <= c_lon <= cov.max_longitude:
                return ds
        return local_dems[0]

    def _get_or_build_terrain_grid(
        self,
        *,
        ds: Dataset,
        all_pts: List[Tuple[float, float]],
        constraints: RoutePlanningConstraints,
        effective_slope_limit_factor: float,
        science_points: Optional[List[Tuple[float, float, float]]] = None,
    ) -> TerrainGrid:
        """Content/parameter-keyed bounded cache avoiding duplicate raster I/O, Horn slope, and TRI computation."""
        try:
            open_path, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
            mtime_ns = open_path.stat().st_mtime_ns if open_path.exists() else 0
        except Exception:
            mtime_ns = 0
        sci_sig = hash(tuple((round(lat, 6), round(lon, 6), round(score, 4)) for lat, lon, score in (science_points or [])))
        pts_sig = tuple((round(lat, 6), round(lon, 6)) for lat, lon in all_pts)
        base_key = (
            ds.id,
            mtime_ns,
            pts_sig,
            round(float(constraints.max_slope_deg), 4),
            round(float(constraints.max_roughness_tri_m), 4) if constraints.max_roughness_tri_m is not None else None,
            int(constraints.max_grid_dim),
            round(float(constraints.snap_radius_m), 2),
            sci_sig,
        )
        eff_lim = max(1.0, float(constraints.max_slope_deg) * float(effective_slope_limit_factor))
        with self._lock:
            cached = self._grid_cache.get(base_key)
            if cached is not None:
                self._grid_cache.move_to_end(base_key)
                if abs(cached.effective_slope_limit_deg - eff_lim) < 1e-6:
                    return cached
                return cached.clone_with_overrides(effective_slope_limit_deg=eff_lim)

        built = build_terrain_grid_from_dataset(
            ds,
            self.raw_dir,
            all_pts,
            constraints,
            effective_slope_limit_factor,
            science_points=science_points,
        )
        with self._lock:
            self._grid_cache[base_key] = built
            self._grid_cache.move_to_end(base_key)
            while len(self._grid_cache) > 16:
                self._grid_cache.popitem(last=False)
        return built

    def _gather_stops_and_science(
        self, req: RouteComputeRequest
    ) -> Tuple[List[Tuple[str, float, float, Optional[str], Optional[Dict[str, Any]]]], List[Tuple[float, float, float]], List[Tuple[str, float, float]], int]:
        """Resolve Start, Target stops, Destination, and nearby science corridor points (cached across sweeps)."""
        tgt_count = len(self.target_registry.list_targets()) if self.target_registry else 0
        cache_key = (
            tuple(req.target_ids),
            tuple((round(w.lat, 6), round(w.lon_east, 6), w.label, w.target_id) for w in req.waypoints),
            round(req.start.lat, 5),
            round(req.start.lon_east, 5),
            round(req.destination.lat, 5),
            round(req.destination.lon_east, 5),
            tgt_count,
        )
        with self._lock:
            cached = self._science_cache.get(cache_key)
            if cached is not None:
                self._science_cache.move_to_end(cache_key)
                return list(cached[0]), list(cached[1]), list(cached[2]), int(cached[3])

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
                    "exploration_priority_score": tgt.exploration_priority_score,
                    "route_utility_role": "registered_science_target_stop",
                    "matched_species": tgt.matched_species,
                    "instrument_source": tgt.instrument_source,
                }
                stops.append(("target", tgt.latitude, tgt.longitude, tgt.name, meta))
                if tgt.exploration_priority_score is not None:
                    science_corridor.append(
                        (tgt.latitude, tgt.longitude, max(0.0, float(tgt.exploration_priority_score)))
                    )
                nearby_lookup.append((tgt.name, tgt.latitude, tgt.longitude))

            # Include other registered targets near corridor for Science-Priority context
            for tgt in self.target_registry.list_targets()[:80]:
                if tgt.exploration_priority_score is not None:
                    science_corridor.append(
                        (tgt.latitude, tgt.longitude, max(0.0, float(tgt.exploration_priority_score) * 0.85))
                    )
                nearby_lookup.append((tgt.name, tgt.latitude, tgt.longitude))

        # Explicit user waypoint stops
        for idx, wp in enumerate(req.waypoints):
            label = wp.label or f"Waypoint {idx + 1}"
            meta = {
                "target_id": wp.target_id,
                "name": label,
                "exploration_priority_score": None,
                "route_utility_role": "explicit_waypoint_with_target" if wp.target_id else "explicit_waypoint",
            }
            stops.append(("waypoint", wp.lat, wp.lon_east, label, meta))
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

        res_tuple = (stops, science_corridor, nearby_lookup, ev_hits_count)
        with self._lock:
            self._science_cache[cache_key] = res_tuple
            self._science_cache.move_to_end(cache_key)
            while len(self._science_cache) > 32:
                self._science_cache.popitem(last=False)
        return list(stops), list(science_corridor), list(nearby_lookup), ev_hits_count

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
        grid = self._get_or_build_terrain_grid(
            ds=ds,
            all_pts=all_pts,
            constraints=req.constraints,
            effective_slope_limit_factor=policy.effective_slope_limit_factor,
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
        penalty_grid: Optional[np.ndarray] = None,
    ) -> RouteComputeResponse:
        """
        Compute a full multi-leg science-aware surface route over real DEMs (or an injected
        TerrainGrid for deterministic unit tests).
        """
        t0 = time.perf_counter()
        policy = resolve_routing_policy(req.mode, req.objective)
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
            grid = self._get_or_build_terrain_grid(
                ds=ds,
                all_pts=all_pts,
                constraints=req.constraints,
                effective_slope_limit_factor=policy.effective_slope_limit_factor,
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
        traversed_edge_expls: List[Dict[str, Any]] = []
        rejected_neighbor_expls: List[Dict[str, Any]] = []
        seen_rejected_pairs: set = set()

        for leg_i in range(len(node_chain) - 1):
            n_from = node_chain[leg_i]
            n_to = node_chain[leg_i + 1]
            leg_res = solve_grid_leg(
                grid,
                n_from["rc"],
                n_to["rc"],
                policy,
                req.algorithm,
                penalty_grid=penalty_grid,
            )
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
                    traversed_edge_expls.append(grid.explain_edge(pr, pc, rc_r, rc_c, policy))
                    if len(rejected_neighbor_expls) < 24:
                        for dr_n in (-1, 0, 1):
                            for dc_n in (-1, 0, 1):
                                if dr_n == 0 and dc_n == 0:
                                    continue
                                nr, nc = pr + dr_n, pc + dc_n
                                if 0 <= nr < grid.rows and 0 <= nc < grid.cols:
                                    key = (pr, pc, nr, nc)
                                    if key not in seen_rejected_pairs and not grid.can_step(pr, pc, nr, nc):
                                        seen_rejected_pairs.add(key)
                                        rejected_neighbor_expls.append(grid.explain_edge(pr, pc, nr, nc, policy))
                                        if len(rejected_neighbor_expls) >= 24:
                                            break
                            if len(rejected_neighbor_expls) >= 24:
                                break
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
                    exploration_priority_score=meta.get("exploration_priority_score"),
                    route_utility_role=meta.get("route_utility_role"),
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
                "algorithm": req.algorithm.value,
                "constraints": req.constraints.model_dump(),
            },
            sort_keys=True,
        )
        sig_hash = hashlib.sha256(sig_payload.encode("utf-8")).hexdigest()[:16]
        route_id = f"rt_{req.mode.value}_{uuid.uuid4().hex[:10]}"

        ds_obj = self.catalog_service.get_dataset(ds_id)
        provenance_block: Dict[str, Any] = {
            "dem_dataset_id": ds_id,
            "dem_product_id": prod_id,
            "crs": "IAU2000:49900",
            "vertical_datum": ds_obj.calibration_status if ds_obj else "MOLA Areoid / Ellipsoid (dataset-defined)",
            "coordinate_convention": "Planetocentric latitude (-90..90), East-positive longitude [0..360)",
            "algorithm": req.algorithm.value,
            "mode": req.mode.value,
            "mode_label": policy.label,
            "policy_weights": {
                "slope_weight": policy.slope_weight,
                "uphill_weight": policy.uphill_weight,
                "downhill_weight": policy.downhill_weight,
                "roughness_weight": policy.roughness_weight,
                "uncertainty_weight": policy.uncertainty_weight,
                "science_corridor_bonus": policy.science_corridor_bonus,
            },
            "effective_slope_limit_deg": round(grid.effective_slope_limit_deg, 2),
            "speed_assumption": assumption_cls,
            "return_to_start": req.constraints.return_to_start,
            "route_signature": sig_hash,
            "safety_certification": "None — terrain optimization reflects DEM geometry & planning constraints only",
        }

        route_prov_graph = ProvenanceDependencyGraph(
            output_id=route_id,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[ds_id],
            input_product_ids=[prod_id],
            input_variables=["elevation_m", "slope_deg", "roughness_tri_m"],
            input_units=["meters", "degrees", "meters"],
            input_crs="IAU2000:49900",
            input_resolution_m=round(grid.native_resolution_m, 3),
            method=f"{req.algorithm} on weighted 8-connected terrain cost grid ({policy.label})",
            algorithm_version="routing_v2_science_aware",
            parameters={
                "mode": req.mode.value,
                "algorithm": req.algorithm,
                "effective_slope_limit_deg": round(grid.effective_slope_limit_deg, 2),
                "solver_grid_spacing_m": round(0.5 * (grid.dx_m + grid.dy_m), 3),
                "return_to_start": req.constraints.return_to_start,
            },
            assumptions=list(limitations),
            intermediate_steps=[
                ProvenanceStep(
                    step_id="step_dem",
                    label="Load verified NASA DEM elevation raster",
                    classification=ScientificDataClassification.ARCHIVE_DERIVED,
                    input_ids=[prod_id],
                    method="PDS3/GeoTIFF raster read",
                    algorithm_version="rasterio_v1",
                    output_variable="elevation_m",
                    output_units="meters",
                    output_resolution_m=round(grid.native_resolution_m, 3),
                ),
                ProvenanceStep(
                    step_id="step_derivatives",
                    label="Derive cell slope and TRI",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=["step_dem"],
                    method="Horn slope + Riley RMS TRI",
                    algorithm_version="terrain_derivatives_v2",
                    output_variable="slope_deg, roughness_tri_m",
                    output_units="degrees, meters",
                    output_resolution_m=round(0.5 * (grid.dx_m + grid.dy_m), 3),
                ),
                ProvenanceStep(
                    step_id="step_cost_path",
                    label="Evaluate terrain edge costs and compute path",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=["step_derivatives"],
                    method=f"{req.algorithm} pathfinder with line-of-sight obstacle/nodata checks",
                    algorithm_version="pathfinder_v2",
                    output_variable="computed_route_geometry",
                    output_units="meters",
                ),
            ],
            output_units="meters",
            output_resolution_m=round(0.5 * (grid.dx_m + grid.dy_m), 3),
            uncertainty_method="coverage_and_nodata_gating",
            validation_state="verified_terrain_route_not_safety_certified",
        )

        explainer_obj = self._build_decision_explainer(
            req=req,
            policy=policy,
            grid=grid,
            traversed_edge_expls=traversed_edge_expls,
            rejected_neighbor_expls=rejected_neighbor_expls,
            sci_reached=sci_reached,
            tot_horiz=tot_horiz,
            tot_secs=tot_secs,
            total_cost=total_cost,
            ev_hits=ev_hits,
        )
        t_counts = grid.traversability_state_counts()
        t_total = max(1, t_counts["evaluated"] + t_counts["known_exclusion"] + t_counts["unknown_insufficient"])
        sci_sources: List[str] = []
        if policy.science_corridor_bonus > 0 and sci_corridor:
            if req.target_ids:
                sci_sources.append("verified_target_registry")
            if ev_hits > 0:
                sci_sources.append("curiosity_msl_composition_archive")
            if not sci_sources:
                sci_sources.append("verified_waypoint_coordinates")

        ct_totals = explainer_obj.total_cost_breakdown
        cost_decomp = RouteCostDecomposition(
            base_distance_cost=round(float(ct_totals.get("base_distance_cost", 0.0)), 3),
            slope_penalty_cost=round(float(ct_totals.get("slope_penalty_cost", 0.0)), 3),
            uphill_climb_cost=round(float(ct_totals.get("uphill_penalty_cost", 0.0)), 3),
            downhill_descent_cost=round(float(ct_totals.get("downhill_penalty_cost", 0.0)), 3),
            roughness_penalty_cost=round(float(ct_totals.get("roughness_penalty_cost", 0.0)), 3),
            uncertainty_penalty_cost=round(float(ct_totals.get("uncertainty_penalty_cost", 0.0)), 3),
            nodata_proximity_cost=round(float(ct_totals.get("nodata_proximity_penalty_cost", 0.0)), 3),
            science_corridor_reduction=round(float(ct_totals.get("science_corridor_bonus_credit", 0.0)), 3),
            total_objective_cost=round(float(total_cost), 3),
            dominant_cost_driver=explainer_obj.dominant_cost_driver,
            science_bonus_sources_used=sci_sources,
            unverified_optical_candidates_excluded=bool(req.exclude_optical_candidates_from_science_bonus),
        )
        trav_summary = RouteTraversabilitySummary(
            evaluated_cell_count=t_counts["evaluated"],
            known_exclusion_cell_count=t_counts["known_exclusion"],
            unknown_insufficient_cell_count=t_counts["unknown_insufficient"],
            evaluated_fraction=round(t_counts["evaluated"] / t_total, 4),
            known_exclusion_fraction=round(t_counts["known_exclusion"] / t_total, 4),
            unknown_insufficient_fraction=round(t_counts["unknown_insufficient"] / t_total, 4),
            unverified_optical_candidates_excluded_from_bonus=bool(req.exclude_optical_candidates_from_science_bonus),
        )

        resp = RouteComputeResponse(
            route_id=route_id,
            route_signature=sig_hash,
            dataset_id=ds_id,
            source_product_id=prod_id,
            bearing_convention=(
                f"Mars True North [0, 360) CW azimuth; Equirectangular Grid North also reported relative to lon0={central_meridian:.2f}E"
            ),
            mode=policy.mode,
            objective=policy.objective or req.objective,
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
            provenance=provenance_block,
            provenance_graph=route_prov_graph,
            decision_explainer=explainer_obj,
            cost_decomposition=cost_decomp,
            traversability_summary=trav_summary,
            uncertainty_status=grid.uncertainty_status,
        )
        self._store_route(resp, grid=grid, req=req)
        return resp

    @staticmethod
    def _build_decision_explainer(
        *,
        req: RouteComputeRequest,
        policy: Any,
        grid: TerrainGrid,
        traversed_edge_expls: List[Dict[str, Any]],
        rejected_neighbor_expls: List[Dict[str, Any]],
        sci_reached: List[ScienceStopSummary],
        tot_horiz: float,
        tot_secs: Optional[float],
        total_cost: float,
        ev_hits: int,
    ) -> RouteDecisionExplainer:
        excl = grid.exclusion_statistics()
        keys = (
            "base_distance_cost",
            "slope_penalty_cost",
            "uphill_penalty_cost",
            "downhill_penalty_cost",
            "roughness_penalty_cost",
            "uncertainty_penalty_cost",
            "nodata_proximity_penalty_cost",
            "science_corridor_bonus_credit",
        )
        totals = {k: round(sum(float(e.get(k) or 0.0) for e in traversed_edge_expls), 3) for k in keys}
        totals["total_raw_grid_cost"] = round(float(total_cost), 3)

        penalty_items = {
            "base_distance": totals["base_distance_cost"],
            "slope_penalty": totals["slope_penalty_cost"],
            "uphill_effort": totals["uphill_penalty_cost"],
            "downhill_effort": totals["downhill_penalty_cost"],
            "roughness_penalty": totals["roughness_penalty_cost"],
            "uncertainty_penalty": totals["uncertainty_penalty_cost"],
            "nodata_proximity_penalty": totals["nodata_proximity_penalty_cost"],
        }
        dominant = max(penalty_items.items(), key=lambda kv: kv[1])[0] if traversed_edge_expls else "base_distance"

        # Sample representative traversed edges (evenly spaced + peak slope + peak cost)
        sampled_indices: List[int] = []
        n_edges = len(traversed_edge_expls)
        if n_edges > 0:
            step = max(1, n_edges // 16)
            sampled_indices.extend(range(0, n_edges, step))
            max_slope_idx = max(range(n_edges), key=lambda i: traversed_edge_expls[i]["effective_slope_deg"])
            max_cost_idx = max(range(n_edges), key=lambda i: float(traversed_edge_expls[i]["total_edge_cost"] or 0.0))
            for extra in (max_slope_idx, max_cost_idx, n_edges - 1):
                if extra not in sampled_indices:
                    sampled_indices.append(extra)
        sampled_edges = [EdgeEvaluationDetail(**traversed_edge_expls[i]) for i in sampled_indices[:24]]
        rejected_edges = [EdgeEvaluationDetail(**e) for e in rejected_neighbor_expls[:24]]

        verified_applied = [
            {
                "target_id": s.target_id,
                "name": s.name,
                "matched_species": s.matched_species,
                "instrument_source": s.instrument_source,
                "exploration_priority_score": s.exploration_priority_score,
                "role": s.route_utility_role or "verified_science_target_or_composition_stop",
            }
            for s in sci_reached
        ]

        # Deterministic sensitivity notes from actual grid distribution
        eff_limit = grid.effective_slope_limit_deg
        tight_cap = max(1.0, eff_limit - 3.0)
        relaxed_cap = min(45.0, eff_limit + 3.0)
        valid_slopes = grid.valid_elev & np.isfinite(grid.slope_deg)
        tight_pass = int(np.count_nonzero(valid_slopes & (grid.slope_deg <= tight_cap)))
        base_pass = int(excl["traversable_cells"])
        relax_pass = int(np.count_nonzero(valid_slopes & (grid.slope_deg <= relaxed_cap)))

        sens_notes: List[str] = [
            (
                f"Slope limit sensitivity: tightening limit by 3.0 deg (to {tight_cap:.1f} deg) changes slope-eligible cells "
                f"from {base_pass} to {tight_pass}; relaxing by 3.0 deg (to {relaxed_cap:.1f} deg) expands to {relax_pass}."
            ),
            (
                f"DEM resolution sensitivity: active grid uses ~{grid.native_resolution_m:.2f} m/px native elevation; "
                f"relief features smaller than ~{grid.native_resolution_m * 2.0:.1f} m are smoothed before slope/TRI gating."
            ),
            (
                "Corridor width sensitivity: widening assessment corridor increases optical & observation capture area "
                "for evidence evaluation without altering A*/Dijkstra centerline cost."
            ),
        ]
        if req.constraints.walking_speed_m_per_s and tot_secs is not None:
            flat_sec = tot_horiz / req.constraints.walking_speed_m_per_s
            grade_delta = tot_secs - flat_sec
            sens_notes.append(
                f"Walking speed assumption ({req.constraints.walking_speed_m_per_s:.2f} m/s unvalidated): "
                f"flat-ground time would be {flat_sec / 60.0:.1f} min vs {tot_secs / 60.0:.1f} min with Tobler-style grade attenuation (+{grade_delta / 60.0:.1f} min)."
            )
        else:
            sens_notes.append(
                "Walking speed sensitivity: walking_speed_m_per_s is omitted, so traverse duration stays null until configured."
            )

        summary = (
            f"Computed with {req.algorithm.value.upper()} in {policy.label} mode under effective hard slope cap "
            f"{eff_limit:.1f} deg; excluded {excl['nodata_excluded_cells']} nodata, {excl['slope_excluded_cells']} steep, "
            f"and {excl['roughness_excluded_cells']} rough cells. Dominant cost term: {dominant}. "
            f"Verified composition hits in search halo: {ev_hits}; unverified optical detections excluded from routing bonus."
        )

        return RouteDecisionExplainer(
            mode=req.mode,
            algorithm=req.algorithm,
            hard_constraints={
                "effective_slope_limit_deg": round(eff_limit, 2),
                "configured_max_slope_deg": req.constraints.max_slope_deg,
                "max_roughness_tri_m": req.constraints.max_roughness_tri_m,
                "nodata_cells_forbidden": True,
                "diagonal_corner_cutting_forbidden": True,
                "simplify_line_of_sight_verified": True,
                "snap_radius_m": req.constraints.snap_radius_m,
            },
            soft_cost_weights={
                "slope_weight": float(policy.slope_weight),
                "uphill_weight": float(policy.uphill_weight),
                "downhill_weight": float(policy.downhill_weight),
                "roughness_weight": float(policy.roughness_weight),
                "uncertainty_weight": float(policy.uncertainty_weight),
                "nodata_proximity_weight": float(policy.nodata_proximity_weight),
                "science_corridor_bonus": float(policy.science_corridor_bonus),
                "min_cost_multiplier": float(policy.min_cost_multiplier),
            },
            grid_exclusion_summary=excl,
            total_cost_breakdown=totals,
            dominant_cost_driver=dominant,
            sampled_traversed_edges=sampled_edges,
            rejected_neighbor_edges=rejected_edges,
            verified_science_targets_applied=verified_applied,
            unverified_optical_candidates_excluded_from_bonus=0,
            sensitivity_notes=sens_notes,
            decision_trace_summary=summary,
        )

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
                algorithm=req.algorithm,
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

    @staticmethod
    def _polyline_overlap_fraction(
        verts_a: List[RouteVertex],
        verts_b: List[RouteVertex],
        tolerance_m: float = 12.0,
    ) -> float:
        """Vectorized symmetric vertex-buffer overlap fraction [0.0, 1.0] measuring corridor distinctness."""
        if not verts_a or not verts_b:
            return 0.0
        lats_a = np.fromiter((v.lat for v in verts_a), dtype=np.float64, count=len(verts_a))
        lons_a = np.fromiter((v.lon_east for v in verts_a), dtype=np.float64, count=len(verts_a))
        lats_b = np.fromiter((v.lat for v in verts_b), dtype=np.float64, count=len(verts_b))
        lons_b = np.fromiter((v.lon_east for v in verts_b), dtype=np.float64, count=len(verts_b))
        mean_lat_rad = math.radians(0.5 * (float(lats_a.mean()) + float(lats_b.mean())))
        m_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
        m_lon = m_lat * math.cos(mean_lat_rad)
        dlat = (lats_a[:, None] - lats_b[None, :]) * m_lat
        dlon = ((lons_a[:, None] - lons_b[None, :] + 180.0) % 360.0 - 180.0) * m_lon
        within = (dlat * dlat + dlon * dlon) <= (tolerance_m * tolerance_m)
        hits_a = int(np.count_nonzero(np.any(within, axis=1)))
        hits_b = int(np.count_nonzero(np.any(within, axis=0)))
        return round(min(hits_a / len(verts_a), hits_b / len(verts_b)), 4)

    @staticmethod
    def _build_corridor_penalty_grid(
        grid: TerrainGrid,
        verts: List[RouteVertex],
        *,
        penalty_factor: float = 3.5,
        corridor_radius_m: float = 20.0,
    ) -> np.ndarray:
        """Apply interior corridor penalty mask while keeping start/destination terminals unpenalized."""
        pen = np.ones((grid.rows, grid.cols), dtype=np.float64)
        if len(verts) < 3:
            return pen
        rad_r = max(1, int(round(corridor_radius_m / max(0.5, grid.dy_m))))
        rad_c = max(1, int(round(corridor_radius_m / max(0.5, grid.dx_m))))
        sr, sc, _ = grid.latlon_to_rc(verts[0].lat, verts[0].lon_east)
        gr, gc, _ = grid.latlon_to_rc(verts[-1].lat, verts[-1].lon_east)

        # Penalize interior vertices (skipping start/goal buffers)
        for v in verts[1:-1]:
            r, c, in_b = grid.latlon_to_rc(v.lat, v.lon_east)
            if not in_b:
                continue
            r0 = max(0, r - rad_r)
            r1 = min(grid.rows, r + rad_r + 1)
            c0 = max(0, c - rad_c)
            c1 = min(grid.cols, c + rad_c + 1)
            pen[r0:r1, c0:c1] = np.maximum(pen[r0:r1, c0:c1], penalty_factor)

        for tr, tc in ((sr, sc), (gr, gc)):
            r0 = max(0, tr - 2)
            r1 = min(grid.rows, tr + 3)
            c0 = max(0, tc - 2)
            c1 = min(grid.cols, tc + 3)
            pen[r0:r1, c0:c1] = 1.0
        return pen

    def evaluate_route_sensitivity(
        self,
        route_id: str,
        *,
        override_grid: Optional[TerrainGrid] = None,
        override_req: Optional[RouteComputeRequest] = None,
        policy_config: Optional[SensitivityPolicyConfig] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> RouteSensitivityReport:
        """
        Execute Prompt 17 categorized deterministic scenario perturbation suite over a stored route's
        TerrainGrid without regenerating rasters, fabricating Monte Carlo draws, or using hardcoded TRI fallbacks.
        """
        pol_cfg = policy_config or DEFAULT_SENSITIVITY_POLICY
        base_route = self.get_route(route_id)
        with self._lock:
            ctx = self._route_contexts.get(route_id)
        if ctx is not None:
            base_grid, base_req = ctx
        elif override_grid is not None and override_req is not None:
            base_grid, base_req = override_grid, override_req
        else:
            raise KeyError(f"Routing context grid for '{route_id}' is not cached in active session.")

        base_policy = resolve_routing_policy(base_req.mode, base_req.objective)
        sig_fallback_deg = float(pol_cfg.unquantified_slope_probe_deg)
        has_slope_sigma = bool(
            base_grid.slope_sigma_grid is not None and np.any(np.isfinite(base_grid.slope_sigma_grid))
        )
        has_tri_sigma = bool(
            base_grid.tri_sigma_grid is not None and np.any(np.isfinite(base_grid.tri_sigma_grid))
        )
        if has_slope_sigma:
            sig_grid = np.where(np.isfinite(base_grid.slope_sigma_grid), base_grid.slope_sigma_grid, sig_fallback_deg)
            basis_note = (
                f"Analytical Horn 3x3 slope sigma propagation from {base_route.source_product_id} "
                f"({base_grid.uncertainty_status}; policy {pol_cfg.policy_version}); not a per-pixel empirical stereo error map."
            )
        else:
            sig_grid = np.full_like(base_grid.slope_deg, sig_fallback_deg)
            basis_note = (
                f"DEM vertical uncertainty is UNQUANTIFIED on {base_route.source_product_id}: slope perturbation uses labeled "
                f"MEASUREMENT_SENSITIVITY_ANALYSIS parametric probe +/-{sig_fallback_deg:.1f} deg; unpropagated TRI delta omitted."
            )

        outcomes: List[ScenarioSensitivityOutcome] = []
        base_budget = base_route.within_budget
        overlap_thresh = float(pol_cfg.path_change_overlap_threshold)
        for sc in DEFAULT_SENSITIVITY_SCENARIOS:
            if cancel_event is not None and cancel_event.is_set():
                raise RoutePlanningError("Sensitivity evaluation cancelled.", detail={"reason": "cancelled"})
            sc_cat = sc.category
            eff_unc_quantified: Optional[bool] = None

            # Prompt 17 Defect 1.4: strictly separate quantified uncertainty propagation vs parametric probe vs omitted TRI
            if sc.slope_sigma_multiplier != 0.0:
                if has_slope_sigma:
                    sc_cat = SensitivityCategory.MEASUREMENT_UNCERTAINTY_PROPAGATION
                    eff_unc_quantified = True
                else:
                    sc_cat = SensitivityCategory.MEASUREMENT_SENSITIVITY_ANALYSIS
                    eff_unc_quantified = False

            if sc.tri_sigma_multiplier != 0.0 and not has_tri_sigma:
                outcomes.append(
                    ScenarioSensitivityOutcome(
                        scenario_id=sc.scenario_id,
                        label=sc.label,
                        category=SensitivityCategory.MEASUREMENT_UNCERTAINTY_PROPAGATION,
                        perturbation_parameter=sc.perturbation_parameter,
                        perturbation_description=sc.perturbation_description,
                        evaluated=False,
                        uncertainty_quantified=False,
                        route_found=True,
                        path_changed_from_baseline=False,
                        path_signature_diff_fraction=0.0,
                        total_distance_m=base_route.total_surface_distance_m,
                        estimated_time_s=base_route.estimated_duration_seconds,
                        max_slope_deg=base_route.max_slope_deg,
                        total_objective_cost=base_route.total_cost,
                        constraint_status_changed=False,
                        notes=[
                            "TRI uncertainty propagation skipped: dataset lacks quantified vertical/TRI sigma "
                            "(sensitivity_v2.0 removes arbitrary +0.25 m fallback)."
                        ],
                    )
                )
                continue

            slope_arr = base_grid.slope_deg
            if sc.slope_sigma_multiplier != 0.0:
                slope_arr = np.maximum(0.0, base_grid.slope_deg + sc.slope_sigma_multiplier * sig_grid)

            tri_arr = base_grid.tri_m
            if sc.tri_sigma_multiplier != 0.0 and has_tri_sigma and base_grid.tri_sigma_grid is not None:
                eff_unc_quantified = True
                tri_sigma_clean = np.where(np.isfinite(base_grid.tri_sigma_grid), base_grid.tri_sigma_grid, 0.0)
                tri_arr = np.where(
                    np.isfinite(base_grid.tri_m),
                    np.maximum(0.0, base_grid.tri_m + sc.tri_sigma_multiplier * tri_sigma_clean),
                    np.nan,
                )

            slope_delta = sc.max_slope_delta_deg
            if sc.scenario_id == "strict_slope_cap":
                slope_delta = float(pol_cfg.strict_slope_cap_delta_deg)
            elif sc.scenario_id == "relaxed_slope_cap":
                slope_delta = float(pol_cfg.relaxed_slope_cap_delta_deg)
            eff_cap = max(1.0, base_grid.effective_slope_limit_deg + slope_delta)
            sc_grid = base_grid.clone_with_overrides(
                effective_slope_limit_deg=eff_cap,
                slope_deg_override=slope_arr,
                tri_m_override=tri_arr,
            )

            sc_policy = base_policy
            if sc.science_weight_scale != 1.0:
                from dataclasses import replace

                sc_policy = replace(
                    base_policy,
                    science_corridor_bonus=max(0.0, min(0.85, base_policy.science_corridor_bonus * sc.science_weight_scale)),
                )

            speed_scale = pol_cfg.walking_speed_degraded_scale if sc.scenario_id == "walking_speed_degraded" else sc.walking_speed_scale

            # Analytical fast path when ONLY walking speed varies (identical grid & edge costs)
            if (
                sc.slope_sigma_multiplier == 0.0
                and sc.tri_sigma_multiplier == 0.0
                and slope_delta == 0.0
                and sc.science_weight_scale == 1.0
                and sc.uncertainty_penalty_scale == 1.0
            ):
                scaled_time: Optional[float] = (
                    round(base_route.estimated_duration_seconds / max(0.05, speed_scale), 1)
                    if base_route.estimated_duration_seconds is not None
                    else None
                )
                sc_within_budget: Optional[bool] = None
                if base_req.constraints.max_eva_duration_hours is not None and scaled_time is not None:
                    usable = (base_req.constraints.max_eva_duration_hours * 3600.0) * (1.0 - base_req.constraints.safety_reserve_fraction)
                    sc_within_budget = scaled_time <= usable
                outcomes.append(
                    ScenarioSensitivityOutcome(
                        scenario_id=sc.scenario_id,
                        label=sc.label,
                        category=sc_cat,
                        perturbation_parameter=sc.perturbation_parameter,
                        perturbation_description=sc.perturbation_description,
                        evaluated=True,
                        uncertainty_quantified=eff_unc_quantified,
                        route_found=True,
                        path_changed_from_baseline=False,
                        path_signature_diff_fraction=0.0,
                        total_distance_m=base_route.total_surface_distance_m,
                        estimated_time_s=scaled_time,
                        max_slope_deg=base_route.max_slope_deg,
                        total_objective_cost=base_route.total_cost,
                        constraint_status_changed=(sc_within_budget != base_budget),
                    )
                )
                continue

            sc_constraints = base_req.constraints.model_copy(
                update={
                    "max_slope_deg": round(eff_cap / max(0.1, base_policy.effective_slope_limit_factor), 2),
                    "walking_speed_m_per_s": (
                        base_req.constraints.walking_speed_m_per_s * speed_scale
                        if base_req.constraints.walking_speed_m_per_s
                        else None
                    ),
                }
            )
            sc_req = base_req.model_copy(update={"constraints": sc_constraints})

            try:
                if sc.science_weight_scale != 1.0:
                    sr, sc_c, _ = sc_grid.snap_to_traversable(sc_req.start.lat, sc_req.start.lon_east, "start", sc_constraints.snap_radius_m)
                    gr, gc, _ = sc_grid.snap_to_traversable(sc_req.destination.lat, sc_req.destination.lon_east, "dest", sc_constraints.snap_radius_m)
                    leg = solve_grid_leg(sc_grid, (sr, sc_c), (gr, gc), sc_policy, sc_req.algorithm)
                    simp_cells, _ = simplify_leg_safely(sc_grid, leg.cells, epsilon_m=sc_constraints.simplification_epsilon_m)
                    sc_verts = [
                        RouteVertex(
                            seq=idx,
                            lat=round(float(sc_grid.lats[r]), 7),
                            lon_east=round(float(sc_grid.lons_east[c]), 7),
                            elevation_m=round(float(sc_grid.elevation_m[r, c]), 2),
                            slope_deg=round(float(sc_grid.slope_deg[r, c]), 2) if np.isfinite(sc_grid.slope_deg[r, c]) else None,
                            cumulative_distance_m=0.0,
                            segment_distance_m=0.0,
                        )
                        for idx, (r, c) in enumerate(simp_cells)
                    ]
                    ov = self._polyline_overlap_fraction(base_route.vertices, sc_verts)
                    outcomes.append(
                        ScenarioSensitivityOutcome(
                            scenario_id=sc.scenario_id,
                            label=sc.label,
                            category=sc_cat,
                            perturbation_parameter=sc.perturbation_parameter,
                            perturbation_description=sc.perturbation_description,
                            evaluated=True,
                            uncertainty_quantified=eff_unc_quantified,
                            route_found=True,
                            path_changed_from_baseline=(ov < overlap_thresh),
                            path_signature_diff_fraction=round(1.0 - ov, 4),
                            total_distance_m=base_route.total_surface_distance_m,
                            total_objective_cost=round(leg.total_cost, 2),
                            constraint_status_changed=False,
                        )
                    )
                else:
                    sc_rt = self.compute_route(
                        sc_req,
                        override_grid=sc_grid,
                        override_dataset_id=base_route.dataset_id,
                        override_product_id=base_route.source_product_id,
                    )
                    ov = self._polyline_overlap_fraction(base_route.vertices, sc_rt.vertices)
                    outcomes.append(
                        ScenarioSensitivityOutcome(
                            scenario_id=sc.scenario_id,
                            label=sc.label,
                            category=sc_cat,
                            perturbation_parameter=sc.perturbation_parameter,
                            perturbation_description=sc.perturbation_description,
                            evaluated=True,
                            uncertainty_quantified=eff_unc_quantified,
                            route_found=True,
                            path_changed_from_baseline=(ov < overlap_thresh),
                            path_signature_diff_fraction=round(1.0 - ov, 4),
                            total_distance_m=sc_rt.total_surface_distance_m,
                            estimated_time_s=sc_rt.estimated_duration_seconds,
                            max_slope_deg=sc_rt.max_slope_deg,
                            total_objective_cost=sc_rt.total_cost,
                            constraint_status_changed=(sc_rt.within_budget != base_budget),
                        )
                    )
            except RoutePlanningError as exc:
                outcomes.append(
                    ScenarioSensitivityOutcome(
                        scenario_id=sc.scenario_id,
                        label=sc.label,
                        category=sc_cat,
                        perturbation_parameter=sc.perturbation_parameter,
                        perturbation_description=sc.perturbation_description,
                        evaluated=True,
                        uncertainty_quantified=eff_unc_quantified,
                        route_found=False,
                        path_changed_from_baseline=True,
                        path_signature_diff_fraction=1.0,
                        constraint_status_changed=True,
                        notes=[exc.message],
                    )
                )

        return summarize_sensitivity_outcomes(
            baseline_route_id=route_id,
            outcomes=outcomes,
            uncertainty_basis_note=basis_note,
            policy_config=pol_cfg,
        )

    def compute_robust_comparison(
        self,
        req: RobustRouteCompareRequest,
        override_grid: Optional[TerrainGrid] = None,
        override_dataset_id: str = "synthetic_test_dem",
        override_product_id: str = "SYNTHETIC_DEM",
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> RobustRouteCompareResponse:
        """
        Generate genuinely distinct route alternatives across explicit objectives plus spatial
        penalty diversification, rejecting near-duplicate corridors or reporting bottlenecks.
        """
        t0 = time.perf_counter()
        stage_timings: Dict[str, float] = {}
        all_pts = [(req.start.lat, req.start.lon_east), (req.destination.lat, req.destination.lon_east)]
        req_stub = RouteComputeRequest(
            dataset_id=req.dataset_id,
            start=req.start,
            destination=req.destination,
            target_ids=req.target_ids,
            waypoints=req.waypoints,
            mode=RoutingMode.BALANCED,
            objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
            algorithm=req.algorithm,
            constraints=req.constraints.model_copy(update={"walking_speed_m_per_s": req.walking_speed_mps}),
        )
        t_sci = time.perf_counter()
        stops, sci_corridor, _nl, _ev = self._gather_stops_and_science(req_stub)
        stage_timings["science_gather_ms"] = round((time.perf_counter() - t_sci) * 1000.0, 2)
        all_pts.extend((s[1], s[2]) for s in stops)

        t_grid = time.perf_counter()
        if override_grid is not None:
            base_grid = override_grid
            ds_id = override_dataset_id
            prod_id = override_product_id
        else:
            ds = self._select_dem_for_points(req.dataset_id, all_pts)
            ds_id = ds.id
            prod_id = ds.product_id
            base_grid = self._get_or_build_terrain_grid(
                ds=ds,
                all_pts=all_pts,
                constraints=req.constraints,
                effective_slope_limit_factor=1.0,
                science_points=sci_corridor,
            )
        stage_timings["terrain_grid_ms"] = round((time.perf_counter() - t_grid) * 1000.0, 2)
        if progress_callback:
            progress_callback("grid_ready", 1, len(req.objectives) + 2)

        accepted: List[Tuple[DistinctRouteCandidate, RouteComputeResponse, TerrainGrid]] = []
        rejected: List[Dict[str, Any]] = []
        failure_reasons: List[str] = []

        def _consider_candidate(
            cand_id: str,
            obj: RouteObjective,
            label: str,
            method: str,
            rt: RouteComputeResponse,
            cand_grid: TerrainGrid,
        ) -> bool:
            max_ov = 0.0
            match_id = None
            for prev_cand, prev_rt, _pg in accepted:
                ov = self._polyline_overlap_fraction(rt.vertices, prev_rt.vertices)
                if ov > max_ov:
                    max_ov = ov
                    match_id = prev_cand.candidate_id
            if accepted and max_ov > req.max_overlap_threshold:
                rejected.append(
                    {
                        "candidate_id": cand_id,
                        "objective": obj.value,
                        "method": method,
                        "overlap_with": match_id,
                        "overlap_fraction": max_ov,
                        "reason": f"Spatial overlap {max_ov*100:.1f}% exceeds distinctness threshold ({req.max_overlap_threshold*100:.0f}%).",
                    }
                )
                return False

            ret_ok = False
            ret_stat = None
            ret_dist = None
            ret_gain = None
            ret_ov = None
            if req.include_independent_return:
                try:
                    rev_req = RouteComputeRequest(
                        dataset_id=ds_id,
                        start=req.destination,
                        destination=req.start,
                        mode=rt.mode,
                        objective=obj,
                        algorithm=req.algorithm,
                        constraints=req_stub.constraints.model_copy(update={"return_to_start": False}),
                    )
                    ret_rt = self.compute_route(
                        rev_req,
                        override_grid=cand_grid,
                        override_dataset_id=ds_id,
                        override_product_id=prod_id,
                    )
                    ret_ok = True
                    ret_stat = "INDEPENDENT_RETURN_COMPUTED"
                    ret_dist = ret_rt.total_surface_distance_m
                    ret_gain = ret_rt.total_elevation_gain_m
                    ret_ov = self._polyline_overlap_fraction(rt.vertices, ret_rt.vertices)
                except RoutePlanningError as ret_exc:
                    ret_ok = False
                    ret_stat = "RETURN_COMPUTATION_FAILED"
                    failure_reasons.append(f"{cand_id} independent return failed: {ret_exc.message}")

            sens_rep = (
                self.evaluate_route_sensitivity(rt.route_id, override_grid=cand_grid, override_req=req_stub)
                if req.include_sensitivity
                else None
            )
            highlights = [
                f"Objective {obj.value}: {rt.total_surface_distance_m:.1f} m surface | +{rt.total_elevation_gain_m:.1f} m climb | max slope {rt.max_slope_deg:.1f} deg",
                f"Uncertain/unquantified status: {rt.uncertainty_status or cand_grid.uncertainty_status}",
            ]
            if ret_ok:
                highlights.append(f"Independent return verified ({ret_dist:.1f} m, +{ret_gain:.1f} m climb).")
            else:
                highlights.append("Independent return trajectory unverified or blocked.")

            cand = DistinctRouteCandidate(
                candidate_id=cand_id,
                objective=obj,
                objective_label=label,
                diversification_method=method,
                max_overlap_with_prior_routes=max_ov,
                route=rt,
                return_computed=ret_ok,
                return_status=ret_stat,
                return_distance_m=ret_dist,
                return_elevation_gain_m=ret_gain,
                return_overlap_with_outbound_fraction=ret_ov,
                sensitivity_summary=sens_rep,
                evidence_highlights=highlights,
            )
            accepted.append((cand, rt, cand_grid))
            return True

        # 1. Objective-diversified exploration
        for idx, obj in enumerate(req.objectives):
            pol = resolve_routing_policy(RoutingMode.BALANCED, obj)
            obj_grid = base_grid.clone_with_overrides(
                effective_slope_limit_deg=max(1.0, req.constraints.max_slope_deg * pol.effective_slope_limit_factor)
            )
            s_req = req_stub.model_copy(update={"mode": pol.mode, "objective": obj})
            try:
                rt = self.compute_route(
                    s_req,
                    override_grid=obj_grid,
                    override_dataset_id=ds_id,
                    override_product_id=prod_id,
                )
                _consider_candidate(f"cand-{idx+1}-{obj.value.lower()}", obj, pol.label, "objective_weight", rt, obj_grid)
            except RoutePlanningError as exc:
                failure_reasons.append(f"{obj.value}: {exc.message}")
                rejected.append(
                    {
                        "candidate_id": f"cand-{idx+1}-{obj.value.lower()}",
                        "objective": obj.value,
                        "method": "objective_weight",
                        "reason": exc.message,
                    }
                )

        # 2. Spatially penalized diversification passes if < 2 distinct corridors found
        if len(accepted) == 1:
            prim_cand, prim_rt, prim_grid = accepted[0]
            pen_grid = self._build_corridor_penalty_grid(prim_grid, prim_rt.vertices, penalty_factor=4.0, corridor_radius_m=18.0)
            alt_req = req_stub.model_copy(update={"objective": RouteObjective.BALANCED_MULTIOBJECTIVE})
            try:
                alt_rt = self.compute_route(
                    alt_req,
                    override_grid=prim_grid,
                    override_dataset_id=ds_id,
                    override_product_id=prod_id,
                    penalty_grid=pen_grid,
                )
                _consider_candidate(
                    "cand-spatial-alt-1",
                    RouteObjective.BALANCED_MULTIOBJECTIVE,
                    "Spatially Diversified Alternate Corridor",
                    "spatial_corridor_penalty",
                    alt_rt,
                    prim_grid,
                )
            except RoutePlanningError as exc:
                failure_reasons.append(f"cand-spatial-alt-1: {exc.message}")
                rejected.append({"candidate_id": "cand-spatial-alt-1", "method": "spatial_corridor_penalty", "reason": exc.message})

        # Pairwise spatial overlap matrix across accepted candidates
        matrix: Dict[str, Dict[str, float]] = {}
        for c1, r1, _ in accepted:
            matrix[c1.candidate_id] = {}
            for c2, r2, _ in accepted:
                matrix[c1.candidate_id][c2.candidate_id] = (
                    1.0 if c1.candidate_id == c2.candidate_id else self._polyline_overlap_fraction(r1.vertices, r2.vertices)
                )

        if len(accepted) >= 2:
            status = "DISTINCT_ALTERNATIVES_AVAILABLE"
        elif len(accepted) == 1:
            status = "SINGLE_CORRIDOR_BOTTLENECK"
        else:
            status = "INSUFFICIENT_FEASIBLE_ROUTES"

        rec_id = None
        rationale = "No traversable route exists under the configured terrain and coverage constraints."
        if accepted:
            def _rank_key(item: Tuple[DistinctRouteCandidate, RouteComputeResponse, TerrainGrid]) -> Tuple[int, int, float, float]:
                cand, rt, _g = item
                ret_score = 0 if cand.return_computed else 1
                stab_changes = cand.sensitivity_summary.scenarios_where_path_changed if cand.sensitivity_summary else 5
                return (ret_score, stab_changes, rt.max_slope_deg, rt.total_surface_distance_m)

            best_cand, best_rt, _ = sorted(accepted, key=_rank_key)[0]
            rec_id = best_cand.candidate_id
            rationale = (
                f"Recommended '{best_cand.objective_label}' ({rec_id}): independent return={'yes' if best_cand.return_computed else 'no'}, "
                f"peak slope={best_rt.max_slope_deg:.1f} deg, climb=+{best_rt.total_elevation_gain_m:.1f} m, "
                f"surface distance={best_rt.total_surface_distance_m:.1f} m"
                + (
                    f", stability={best_cand.sensitivity_summary.stability_status.value} ({best_cand.sensitivity_summary.scenarios_where_path_changed}/{best_cand.sensitivity_summary.evaluated_scenario_count} scenarios varied)."
                    if best_cand.sensitivity_summary
                    else "."
                )
            )
            if status == "SINGLE_CORRIDOR_BOTTLENECK":
                rationale += " Terrain forms a topological single-corridor bottleneck; rejected near-duplicate variations are explicitly separated."

        return RobustRouteCompareResponse(
            dataset_id=ds_id,
            source_product_id=prod_id,
            alternative_generation_status=status,
            search_algorithm=f"8_neighbor_terrain_grid_{req.algorithm}",
            diversification_strategy="multi_objective_weights_plus_corridor_spatial_penalty_pass",
            search_limits={
                "objectives_tested": [o.value for o in req.objectives],
                "spatial_penalty_passes": 1,
                "spatial_penalty_factor": 4.0,
                "spatial_corridor_radius_m": 18.0,
                "max_overlap_threshold": req.max_overlap_threshold,
                "overlap_vertex_tolerance_m": 12.0,
                "max_grid_dim": req.constraints.max_grid_dim,
            },
            overlap_metric_definition=(
                "Symmetric vertex proximity overlap: min(frac vertices of route A within 12.0 m of route B, "
                "frac vertices of route B within 12.0 m of route A) on Mars IAU2000 great circle."
            ),
            global_optimality_disclaimer=(
                "Generates feasible alternative routes across explicitly tested objectives and one 18 m interior spatial penalty pass "
                "bounded by DEM grid resolution and max_overlap_threshold; does NOT claim exhaustive global optimality."
            ),
            recommended_candidate_id=rec_id,
            recommendation_rationale=rationale,
            distinct_candidate_count=len(accepted),
            duplicate_candidates_rejected=len(rejected),
            pairwise_overlap_matrix=matrix,
            candidates=[c for (c, _rt, _g) in accepted],
            rejected_near_duplicates=rejected,
            rejected_candidates=rejected,
            failure_reasons=failure_reasons,
            limitations=[
                "Route comparisons evaluate meter-scale DEM geometry and coverage limits; sub-meter obstacles (< 0.5 m) remain unresolved.",
                "Spatial distinctness verifies corridor separation rather than life-safety certification.",
            ],
            stage_timings_ms=stage_timings,
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    def compute_independent_return_with_checkpoints(
        self,
        *,
        dataset_id: str,
        outbound_route: RouteComputeResponse,
        walking_speed_mps: Optional[float],
        use_tobler_grade_approximation: bool,
        stop_dwell_total_s: float,
        operational_overhead_s: float,
        usable_budget_s: Optional[float],
        override_grid: Optional[TerrainGrid] = None,
    ) -> Tuple[RouteComputeResponse, List[IndependentReturnAlternative], List[TurnbackCheckpointRecord]]:
        """
        Compute the primary independent destination->start return route, distinct return
        alternatives, and checkpoint-by-checkpoint turnback evaluation using single-sweep
        reverse Dijkstra on the directed TerrainGrid.
        """
        from app.eva_operations.schemas import (
            IndependentReturnAlternative,
            TurnbackCheckpointRecord,
        )

        out_verts = outbound_route.vertices
        start_pt = RouteCoordinateInput(
            lat=out_verts[0].lat, lon_east=out_verts[0].lon_east, label=out_verts[0].stop_label or "Origin"
        )
        dest_pt = RouteCoordinateInput(
            lat=out_verts[-1].lat, lon_east=out_verts[-1].lon_east, label=out_verts[-1].stop_label or "Destination"
        )
        ret_constraints = RoutePlanningConstraints(
            max_slope_deg=outbound_route.effective_slope_limit_deg,
            walking_speed_m_per_s=walking_speed_mps,
            return_to_start=False,
        )
        ret_policy = resolve_routing_policy(outbound_route.mode, RouteObjective.BALANCED_MULTIOBJECTIVE)

        if override_grid is not None:
            ret_grid = override_grid
            ds_id = dataset_id
            prod_id = outbound_route.source_product_id
        else:
            with self._lock:
                ctx = self._route_contexts.get(outbound_route.route_id)
            if ctx is not None:
                ret_grid = ctx[0]
                ds_id = outbound_route.dataset_id
                prod_id = outbound_route.source_product_id
            else:
                ds = self._select_dem_for_points(dataset_id, [(v.lat, v.lon_east) for v in out_verts])
                ds_id = ds.id
                prod_id = ds.product_id
                ret_grid = self._get_or_build_terrain_grid(
                    ds=ds,
                    all_pts=[(v.lat, v.lon_east) for v in out_verts],
                    constraints=ret_constraints,
                    effective_slope_limit_factor=1.0,
                )

        rev_req = RouteComputeRequest(
            dataset_id=ds_id,
            start=dest_pt,
            destination=start_pt,
            mode=outbound_route.mode,
            objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
            algorithm=outbound_route.algorithm,
            constraints=ret_constraints,
        )
        primary_ret = self.compute_route(
            rev_req,
            override_grid=ret_grid,
            override_dataset_id=ds_id,
            override_product_id=prod_id,
        )

        # Evaluate distinct independent return alternatives
        ret_alts: List[IndependentReturnAlternative] = []
        alt_candidates: List[Tuple[str, RouteObjective, str, Optional[np.ndarray]]] = [
            ("ret-alt-climb", RouteObjective.LOWEST_CLIMB_ENERGY, "Lowest-Climb Return", None),
            (
                "ret-alt-bypass",
                RouteObjective.BALANCED_MULTIOBJECTIVE,
                "Spatially Diversified Return Corridor",
                self._build_corridor_penalty_grid(ret_grid, primary_ret.vertices, penalty_factor=3.5, corridor_radius_m=18.0),
            ),
        ]
        for aid, aobj, albl, apen in alt_candidates:
            try:
                apol = resolve_routing_policy(outbound_route.mode, aobj)
                alt_req = rev_req.model_copy(update={"mode": apol.mode, "objective": aobj})
                alt_rt = self.compute_route(
                    alt_req,
                    override_grid=ret_grid,
                    override_dataset_id=ds_id,
                    override_product_id=prod_id,
                    penalty_grid=apen,
                )
                ov_p = self._polyline_overlap_fraction(alt_rt.vertices, primary_ret.vertices)
                if ov_p <= 0.85:
                    ret_alts.append(
                        IndependentReturnAlternative(
                            alternative_id=aid,
                            objective=aobj.value,
                            strategy_label=albl,
                            horizontal_distance_m=alt_rt.total_horizontal_distance_m,
                            surface_distance_m=alt_rt.total_surface_distance_m,
                            elevation_gain_m=alt_rt.total_elevation_gain_m,
                            max_slope_deg=alt_rt.max_slope_deg,
                            mean_slope_deg=alt_rt.mean_slope_deg,
                            estimated_time_constant_s=(
                                round(alt_rt.total_surface_distance_m / walking_speed_mps, 1)
                                if (walking_speed_mps and walking_speed_mps > 0)
                                else None
                            ),
                            estimated_time_tobler_s=alt_rt.estimated_duration_seconds,
                            spatial_overlap_with_primary_fraction=ov_p,
                            overlap_with_outbound_fraction=self._polyline_overlap_fraction(alt_rt.vertices, out_verts),
                            vertices=alt_rt.vertices,
                        )
                    )
            except RoutePlanningError:
                pass

        # Checkpoint-by-checkpoint independent reverse-Dijkstra turnback evaluation
        origin_r, origin_c, _ = ret_grid.snap_to_traversable(start_pt.lat, start_pt.lon_east, "origin", ret_constraints.snap_radius_m)
        _dist_map, next_hop = ret_grid.reverse_dijkstra_to_target((origin_r, origin_c), ret_policy)

        n_verts = len(out_verts)
        step = max(1, (n_verts - 1) // 8)
        cp_indices = list(range(1, n_verts, step))
        if (n_verts - 1) not in cp_indices:
            cp_indices.append(n_verts - 1)

        # Precompute outbound cumulative Tobler time
        ref_tobler = math.exp(-3.5 * 0.05)
        out_cum_tobler = [0.0]
        for idx in range(1, n_verts):
            h = mars_great_circle_distance_meters(
                out_verts[idx - 1].lat, out_verts[idx - 1].lon_east, out_verts[idx].lat, out_verts[idx].lon_east
            )
            dz = float(out_verts[idx].elevation_m) - float(out_verts[idx - 1].elevation_m)
            if walking_speed_mps and walking_speed_mps > 0 and h > 1e-6:
                gf = math.exp(-3.5 * abs((dz / h) + 0.05)) / ref_tobler
                slp = float(out_verts[idx].slope_deg) if out_verts[idx].slope_deg is not None else math.degrees(math.atan2(abs(dz), h))
                att = max(0.35, 1.0 - max(0.0, slp) / 55.0)
                out_cum_tobler.append(out_cum_tobler[-1] + h / (walking_speed_mps * max(0.22, min(1.1, min(gf, att)))))
            else:
                out_cum_tobler.append(out_cum_tobler[-1])

        checkpoints: List[TurnbackCheckpointRecord] = []
        for cp_pos, v_idx in enumerate(cp_indices):
            v = out_verts[v_idx]
            out_t = (
                round(out_cum_tobler[v_idx], 1)
                if use_tobler_grade_approximation
                else (round(v.cumulative_distance_m / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None)
            )
            try:
                cp_r, cp_c, _ = ret_grid.snap_to_traversable(v.lat, v.lon_east, f"cp-{cp_pos}", ret_constraints.snap_radius_m)
                cells = reconstruct_reverse_dijkstra_path(next_hop, (cp_r, cp_c), (origin_r, origin_c), ret_grid.cols)
            except RoutePlanningError as exc:
                checkpoints.append(
                    TurnbackCheckpointRecord(
                        checkpoint_index=cp_pos,
                        lat=v.lat,
                        lon_east=v.lon_east,
                        outbound_distance_m=round(v.cumulative_distance_m, 2),
                        outbound_elapsed_s=out_t,
                        return_route_computed=False,
                        fits_usable_budget=False,
                        failure_reason=exc.message,
                    )
                )
                continue

            if cells is None or len(cells) < 1:
                checkpoints.append(
                    TurnbackCheckpointRecord(
                        checkpoint_index=cp_pos,
                        lat=v.lat,
                        lon_east=v.lon_east,
                        outbound_distance_m=round(v.cumulative_distance_m, 2),
                        outbound_elapsed_s=out_t,
                        return_route_computed=False,
                        fits_usable_budget=False,
                        failure_reason="Checkpoint has no valid directed return trajectory to origin under active terrain constraints.",
                    )
                )
                continue

            cp_surf = 0.0
            cp_gain = 0.0
            cp_tob = 0.0
            cp_verts: List[RouteVertex] = []
            for ci, (cr, cc) in enumerate(cells):
                z_cur = float(ret_grid.elevation_m[cr, cc])
                slp_cur = float(ret_grid.slope_deg[cr, cc]) if np.isfinite(ret_grid.slope_deg[cr, cc]) else 0.0
                cp_verts.append(
                    RouteVertex(
                        seq=ci,
                        lat=float(ret_grid.lats[cr]),
                        lon_east=float(ret_grid.lons_east[cc]),
                        elevation_m=z_cur,
                        slope_deg=slp_cur,
                        cumulative_distance_m=cp_surf,
                        segment_distance_m=0.0,
                    )
                )
                if ci > 0:
                    pr, pc = cells[ci - 1]
                    h = math.hypot((cc - pc) * ret_grid.dx_m, (cr - pr) * ret_grid.dy_m)
                    dz = z_cur - float(ret_grid.elevation_m[pr, pc])
                    cp_surf += math.hypot(h, dz)
                    if dz > 0:
                        cp_gain += dz
                    if walking_speed_mps and walking_speed_mps > 0 and h > 1e-6:
                        gf = math.exp(-3.5 * abs((dz / h) + 0.05)) / ref_tobler
                        att = max(0.35, 1.0 - max(0.0, slp_cur) / 55.0)
                        cp_tob += h / (walking_speed_mps * max(0.22, min(1.1, min(gf, att))))

            cp_const_s = round(cp_surf / walking_speed_mps, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
            cp_tob_s = round(cp_tob, 1) if (walking_speed_mps and walking_speed_mps > 0) else None
            active_ret_s = cp_tob_s if use_tobler_grade_approximation else cp_const_s
            dwell_here = stop_dwell_total_s if (v_idx == n_verts - 1) else 0.0
            rt_t = (
                round((out_t or 0.0) + operational_overhead_s + dwell_here + (active_ret_s or 0.0), 1)
                if (out_t is not None and active_ret_s is not None)
                else None
            )
            fits = (rt_t <= usable_budget_s) if (rt_t is not None and usable_budget_s is not None) else None
            checkpoints.append(
                TurnbackCheckpointRecord(
                    checkpoint_index=cp_pos,
                    lat=v.lat,
                    lon_east=v.lon_east,
                    outbound_distance_m=round(v.cumulative_distance_m, 2),
                    outbound_elapsed_s=out_t,
                    return_route_computed=True,
                    independent_return_distance_m=round(cp_surf, 2),
                    independent_return_elevation_gain_m=round(cp_gain, 2),
                    independent_return_duration_constant_s=cp_const_s,
                    independent_return_duration_tobler_s=cp_tob_s,
                    estimated_roundtrip_time_s=rt_t,
                    fits_usable_budget=fits,
                    return_differs_from_outbound=(self._polyline_overlap_fraction(cp_verts, out_verts[: v_idx + 1]) < 0.85),
                )
            )

        return primary_ret, ret_alts, checkpoints
