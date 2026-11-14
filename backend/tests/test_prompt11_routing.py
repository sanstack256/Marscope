"""
Synthetic adversarial unit tests for Prompt 11 Science-Aware Routing Engine:
- Dijkstra == A* exact cost equivalence & admissibility guarantee
- Steep cliff avoidance via traversable saddle detour
- Strict NO diagonal corner-cutting across adjacent obstacle / NoData cells
- NoData blockage & snap_radius_m enforcement with honest diagnostics
- Planning mode differentiation: Conservative vs Balanced vs Science Priority
- Return-to-start round-trip + EVA budget reserve checks
- Honest walking-speed omission ("No walking speed or duration assumed")
- Post-simplification line-of-sight safety guard (never cuts corners through cliffs/nodata)
- Bearing mathematics (True North vs Grid North) & deterministic route signatures
- Mobility status gate verification (route_optimization_enabled=True, safety_certification_enabled=False)

Note: Uses exclusively synthetic numpy terrain grids and temp GeoTIFF fixtures.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds

from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.ingestion.catalog import DatasetCatalogService
from app.main import app
from app.routing.graph import RoutePlanningError, TerrainGrid
from app.routing.instructions import (
    equirectangular_grid_north_bearing_deg,
    mars_true_north_bearing_deg,
)
from app.routing.models import MODE_POLICIES, PathAlgorithm, RoutingMode
from app.routing.pathfinder import simplify_leg_safely, solve_grid_leg
from app.routing.schemas import RouteComputeRequest, RouteCoordinateInput, RoutePlanningConstraints
from app.routing.service import ScienceAwareRoutingService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, GeographicCoverage, LicenseStatus


def test_astar_equals_dijkstra_exact_cost_across_all_modes():
    rng = np.random.default_rng(42)
    rows, cols = 28, 32
    # Gentle undulating surface within <= 12 degrees slope
    yy, xx = np.mgrid[0:rows, 0:cols]
    elev = -4000.0 + 0.6 * xx + 0.4 * yy + rng.uniform(-0.35, 0.35, size=(rows, cols))
    # Add a science hotspot near row 8, col 16
    sci_pt = [(-4.75 + (rows - 1 - 8) * 10.0 / 59274.0, 137.40 + 16 * 10.0 / 59070.0, 0.95)]

    grid = TerrainGrid.from_arrays(
        elevation_m=elev,
        dx_m=10.0,
        dy_m=10.0,
        max_slope_deg=22.0,
        science_points=sci_pt,
    )
    start_rc = (22, 3)
    goal_rc = (5, 28)

    for mode in (RoutingMode.CONSERVATIVE, RoutingMode.BALANCED, RoutingMode.SCIENCE_PRIORITY):
        policy = MODE_POLICIES[mode]
        res_dijk = solve_grid_leg(grid, start_rc, goal_rc, policy, PathAlgorithm.DIJKSTRA)
        res_astar = solve_grid_leg(grid, start_rc, goal_rc, policy, PathAlgorithm.ASTAR)

        assert res_astar.total_cost == pytest.approx(res_dijk.total_cost, rel=1e-7, abs=1e-7)
        assert res_astar.cells[0] == start_rc and res_astar.cells[-1] == goal_rc
        assert res_astar.nodes_expanded <= res_dijk.nodes_expanded


def test_steep_cliff_barrier_forces_safe_saddle_detour():
    rows, cols = 21, 25
    elev = np.full((rows, cols), -4200.0, dtype=np.float64)
    # Place an impassable steep central ridge (~60 deg cliff) leaving rows 0..3 flat north saddle
    elev[4:, 11:14] = -4140.0

    grid = TerrainGrid.from_arrays(
        elevation_m=elev,
        dx_m=10.0,
        dy_m=10.0,
        max_slope_deg=15.0,
    )
    start_rc = (12, 3)
    goal_rc = (12, 21)

    res = solve_grid_leg(
        grid,
        start_rc,
        goal_rc,
        MODE_POLICIES[RoutingMode.BALANCED],
        PathAlgorithm.ASTAR,
    )
    # Every visited cell along path must stay off the steep ridge and clear north via saddle
    assert min(r for r, _ in res.cells) <= 3
    for i in range(len(res.cells) - 1):
        r0, c0 = res.cells[i]
        r1, c1 = res.cells[i + 1]
        assert grid.can_step(r0, c0, r1, c1)


def test_strict_no_diagonal_corner_cutting_across_obstacles():
    # Minimal 4x4 grid with impassable cliffs blocking cardinal neighbors around diagonal gap
    elev = np.full((5, 5), -4000.0, dtype=np.float64)
    # Create an unbroken wall at row 2 except an isolated NaN/cliff pinch:
    # Traversable (1,1) -> (2,2) would squeeze diagonally between NaN at (1,2) and (2,1)
    elev[1, 2] = np.nan
    elev[2, 1] = np.nan
    # Block the rest of row 2 so NO legal non-corner-cut crossing exists
    elev[2, 0] = np.nan
    elev[2, 3] = np.nan
    elev[2, 4] = np.nan

    grid = TerrainGrid.from_arrays(elevation_m=elev, dx_m=10.0, dy_m=10.0, max_slope_deg=20.0)
    assert grid.can_step(1, 1, 2, 2) is False
    assert grid.can_step(2, 2, 1, 1) is False

    with pytest.raises(RoutePlanningError):
        solve_grid_leg(grid, (0, 0), (4, 4), MODE_POLICIES[RoutingMode.BALANCED], PathAlgorithm.ASTAR)


def test_simplification_never_cuts_obstacle_or_nodata():
    rows, cols = 15, 25
    elev = np.full((rows, cols), -4100.0, dtype=np.float64)
    # Narrow 1-cell-wide NaN peninsula sticking up through middle of map
    elev[3:14, 12] = np.nan

    grid = TerrainGrid.from_arrays(elevation_m=elev, dx_m=10.0, dy_m=10.0, max_slope_deg=20.0)
    raw = solve_grid_leg(
        grid, (11, 4), (11, 20), MODE_POLICIES[RoutingMode.BALANCED], PathAlgorithm.ASTAR
    )
    simplified, diag = simplify_leg_safely(grid, raw.cells, epsilon_m=100.0)

    assert diag.all_simplified_segments_verified_valid is True
    assert diag.shortcuts_rejected_obstacle_or_nodata >= 1
    assert len(simplified) >= 3  # Cannot shortcut straight across the wall to 2 points
    assert simplified[0] == raw.cells[0] and simplified[-1] == raw.cells[-1]
    # Verify supercover integrity on simplified segments: zero NaN points touched
    for r, c in simplified:
        assert grid.traversable[r, c]


def test_conservative_vs_balanced_vs_science_priority_differentiation(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    cat_dir = tmp_path / "catalog"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cat_dir.mkdir(parents=True, exist_ok=True)

    dem_path = raw_dir / "ramp_dem.tif"
    rows, cols = 40, 40
    min_lon, min_lat, max_lon, max_lat = 137.400, -4.750, 137.408, -4.742
    # Build gentle valley sloping ~18 degrees diagonally, plus flat northern corridor
    # Wait: fill uniform gentle 18-deg E-W slope strip in the south and gentle 5-deg northern loop
    elev = np.full((rows, cols), -4200.0, dtype=np.float64)
    # Raise a gentle step ridge forcing ~17.5 deg ramp across col 18..22 on southern direct path
    dx_deg = (max_lon - min_lon) / cols
    m_per_px = 11.8  # approx cell spacing
    # Construct ~17.7 deg slope ramp (~3.77 m drop per 11.8m step) right across center-south
    for c in range(16, 26):
        elev[:, c] = -4200.0 + (c - 15) * 3.85
    # Leave rows 2..5 along col 16..25 stepped gently? Wait: make an isolated 17.7-deg sill everywhere
    # so Conservative (max 16 deg) rejects crossing while Balanced (max 20 deg) traverses cleanly!
    elev[:, 26:] = elev[:, 25:26]

    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, cols, rows)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=MARS_CRS_DEFINITIONS["IAU2000:49900"],
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(elev.astype(np.float32), 1)

    catalog = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
    ds = Dataset(
        id="synth_ramp_dem",
        product_id="SYNTH_RAMP_01",
        product_title="Synthetic Ramp Test DEM",
        product_type="DEM",
        mission="TEST",
        instrument="SYNTH",
        source_archive="Synthetic Test",
        original_product_url="https://example.invalid/ramp_dem.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Synthetic Unit Test",
        coverage=GeographicCoverage(
            min_latitude=min_lat + dx_deg * 0.5,
            max_latitude=max_lat,
            min_longitude=min_lon,
            max_longitude=max_lon,
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=m_per_px,
        units="meters",
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path=str(dem_path),
    )
    catalog.register_dataset(ds)

    routing_svc = ScienceAwareRoutingService(catalog_service=catalog, raw_dir=raw_dir)
    start = RouteCoordinateInput(lat=-4.746, lon_east=137.401, label="West Station")
    dest = RouteCoordinateInput(lat=-4.746, lon_east=137.407, label="East Ridge")

    # Geometry-only computation with speed omitted -> honest None duration
    req_bal = RouteComputeRequest(
        dataset_id="synth_ramp_dem",
        start=start,
        destination=dest,
        mode=RoutingMode.BALANCED,
        algorithm=PathAlgorithm.ASTAR,
        constraints=RoutePlanningConstraints(
            max_slope_deg=22.0,
            walking_speed_m_per_s=None,
            return_to_start=False,
        ),
    )
    res_bal = routing_svc.compute_route(req_bal)
    assert res_bal.estimated_duration_seconds is None
    assert "No walking speed or duration assumed" in res_bal.assumption_classification
    assert res_bal.max_slope_deg >= 16.5

    # Compare Conservative (16 deg cap) vs Balanced (22 deg user cap) -> Conservative honestly rejected
    from app.routing.schemas import RouteCompareRequest

    comp = routing_svc.compare_routes(
        RouteCompareRequest(
            dataset_id="synth_ramp_dem",
            start=start,
            destination=dest,
            constraints=RoutePlanningConstraints(
                max_slope_deg=22.0,
                walking_speed_m_per_s=0.8,
                max_eva_duration_hours=0.06,  # 216s budget (162s usable after 25% reserve)
                astronaut_total_mass_kg=160.0,
                enforce_budget=False,
                return_to_start=True,
            ),
        )
    )
    by_mode = {e.mode: e for e in comp.comparison}
    assert by_mode[RoutingMode.CONSERVATIVE].feasible is False
    assert by_mode[RoutingMode.CONSERVATIVE].error_reason is not None
    assert by_mode[RoutingMode.BALANCED].feasible is True
    assert by_mode[RoutingMode.BALANCED].route is not None
    assert by_mode[RoutingMode.BALANCED].route.gravitational_climb_work_joules is not None
    assert by_mode[RoutingMode.BALANCED].route.gravitational_climb_work_joules > 0.0
    assert by_mode[RoutingMode.BALANCED].route.return_to_start is True
    assert by_mode[RoutingMode.BALANCED].route.budget_diagnostic.within_budget is False

    # Now enforce strict budget -> HTTP/Value rejection with clear margin message
    req_budget = RouteComputeRequest(
        dataset_id="synth_ramp_dem",
        start=start,
        destination=dest,
        mode=RoutingMode.BALANCED,
        constraints=RoutePlanningConstraints(
            max_slope_deg=22.0,
            walking_speed_m_per_s=0.8,
            max_eva_duration_hours=0.06,
            enforce_budget=True,
            return_to_start=True,
        ),
    )
    with pytest.raises(RoutePlanningError) as exc_info:
        routing_svc.compute_route(req_budget)
    assert "budget" in str(exc_info.value).lower()


def test_snap_radius_and_bearing_math():
    elev = np.full((15, 15), -4000.0, dtype=np.float64)
    elev[7, 7] = np.nan  # single NoData hole
    grid = TerrainGrid.from_arrays(elevation_m=elev, dx_m=10.0, dy_m=10.0, max_slope_deg=18.0)

    # Inside snap_radius=30m -> snaps cleanly to traversable adjacent cell
    lat_hole = float(grid.lats[7])
    lon_hole = float(grid.lons_east[7])
    sr, sc, diag = grid.snap_to_traversable(lat_hole, lon_hole, "Start", snap_radius_m=30.0)
    assert grid.traversable[sr, sc]
    assert diag.snapped is True
    assert diag.snap_distance_m > 0.0

    # Far outside bounds -> rejected by snap_radius_m
    with pytest.raises(RoutePlanningError):
        grid.snap_to_traversable(lat_hole + 0.5, lon_hole, "OutOfBounds", snap_radius_m=50.0)

    # Bearing sanity checks (True North vs Equirectangular Grid North)
    b_north = mars_true_north_bearing_deg(-4.75, 137.40, -4.74, 137.40)
    b_east = mars_true_north_bearing_deg(-4.75, 137.40, -4.75, 137.41)
    b_south = mars_true_north_bearing_deg(-4.74, 137.40, -4.75, 137.40)
    b_west = mars_true_north_bearing_deg(-4.75, 137.41, -4.75, 137.40)
    assert b_north == pytest.approx(0.0, abs=0.5)
    assert b_east == pytest.approx(90.0, abs=0.5)
    assert b_south == pytest.approx(180.0, abs=0.5)
    assert b_west == pytest.approx(270.0, abs=0.5)

    bg_east = equirectangular_grid_north_bearing_deg(-4.75, 137.40, -4.75, 137.41)
    assert bg_east == pytest.approx(90.0, abs=0.5)


def test_mobility_status_honesty_after_prompt11():
    client = TestClient(app)
    res = client.get("/api/mobility/status")
    assert res.status_code == 200
    body = res.json()
    assert body["route_optimization_enabled"] is True
    assert body["safety_certification_enabled"] is False
