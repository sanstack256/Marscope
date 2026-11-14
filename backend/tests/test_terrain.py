"""
Automated Terrain Intelligence Tests
Validates Horn slope gradients, true compass aspect orientation, resolution-aware TRI,
strict no-data boundary handling, and unit validation.
"""

import numpy as np
import pytest
from app.terrain.aspect import calculate_aspect
from app.terrain.fixtures import generate_flat_surface, generate_planar_slope
from app.terrain.roughness import (
    calculate_roughness_tri,
    calculate_roughness_tri_with_metadata,
)
from app.terrain.slope import calculate_slope
from app.terrain.summary import compute_band_stats


def test_flat_surface_slope_is_zero():
    """Assert that an analytically flat surface yields 0.0 degrees slope in valid interior."""
    flat = generate_flat_surface(elevation_m=100.0, shape=(15, 15))
    slope_deg, _ = calculate_slope(flat, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")

    valid_slopes = slope_deg[1:-1, 1:-1]
    assert np.allclose(valid_slopes, 0.0, atol=1e-5)


def test_planar_slope_recovery():
    """Assert Horn gradients analytically recover exact known slope angles (15, 30, 45 deg)."""
    for expected_angle in [15.0, 30.0, 45.0]:
        tilted = generate_planar_slope(slope_deg=expected_angle, dx_m=10.0, dy_m=10.0, shape=(25, 25))
        slope_deg, _ = calculate_slope(tilted, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")

        interior = slope_deg[2:-2, 2:-2]
        mean_calc = float(np.mean(interior))
        assert np.isclose(mean_calc, expected_angle, atol=0.01)


def test_flat_surface_aspect_is_negative_one():
    """Assert flat terrain aspect is -1.0 in interior and NaN on borders."""
    flat = generate_flat_surface(elevation_m=50.0, shape=(10, 10))
    aspect = calculate_aspect(flat, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")
    assert np.all(aspect[1:-1, 1:-1] == -1.0)
    assert np.all(np.isnan(aspect[0, :]))
    assert np.all(np.isnan(aspect[-1, :]))


def test_compass_aspect_directions():
    """
    Verify clockwise-from-North aspect convention on North/East/South/West sloping planes.
    Row 0 = North, Row N-1 = South; Col 0 = West, Col M-1 = East.
    """
    dx, dy = 10.0, 10.0
    rows, cols = np.mgrid[0:10, 0:10]

    # Higher in South (large row), lower in North (row 0) -> steepest descent faces North (0 deg)
    slope_north = rows.astype(np.float64) * 5.0
    asp_north = calculate_aspect(slope_north, dx, dy, vertical_units="meters")
    assert np.isclose(asp_north[5, 5], 0.0, atol=1e-4) or np.isclose(asp_north[5, 5], 360.0, atol=1e-4)

    # Higher in West (col 0), lower in East -> steepest descent faces East (90 deg)
    slope_east = -cols.astype(np.float64) * 5.0
    asp_east = calculate_aspect(slope_east, dx, dy, vertical_units="meters")
    assert np.isclose(asp_east[5, 5], 90.0, atol=1e-4)

    # Higher in North (row 0), lower in South -> steepest descent faces South (180 deg)
    slope_south = -rows.astype(np.float64) * 5.0
    asp_south = calculate_aspect(slope_south, dx, dy, vertical_units="meters")
    assert np.isclose(asp_south[5, 5], 180.0, atol=1e-4)

    # Higher in East (large col), lower in West -> steepest descent faces West (270 deg)
    slope_west = cols.astype(np.float64) * 5.0
    asp_west = calculate_aspect(slope_west, dx, dy, vertical_units="meters")
    assert np.isclose(asp_west[5, 5], 270.0, atol=1e-4)


def test_nodata_never_leaks_into_slope_aspect_tri():
    """A single NaN/no-data cell must yield NaN across all derivatives touching that cell."""
    grid = np.ones((12, 12), dtype=np.float64) * 100.0
    grid[6, 6] = np.nan

    slope_deg, _ = calculate_slope(grid, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")
    aspect = calculate_aspect(grid, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")
    tri = calculate_roughness_tri(grid, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")

    # Every cell in 3x3 centered on (6,6) must be NaN; distant interior pixel remains valid
    assert np.all(np.isnan(slope_deg[5:8, 5:8]))
    assert np.all(np.isnan(aspect[5:8, 5:8]))
    assert np.all(np.isnan(tri[5:8, 5:8]))
    assert np.isclose(slope_deg[2, 2], 0.0, atol=1e-6)
    assert np.isclose(tri[2, 2], 0.0, atol=1e-6)


def test_roughness_tri_on_flat_and_step():
    """Verify TRI = 0 on flat surfaces and captures vertical elevation discontinuities."""
    flat = generate_flat_surface(elevation_m=200.0, shape=(10, 10))
    tri_flat = calculate_roughness_tri(flat, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")
    assert np.allclose(tri_flat[1:-1, 1:-1], 0.0, atol=1e-6)

    step = np.zeros((10, 10), dtype=np.float64)
    step[:, 5:] = 100.0
    tri_step = calculate_roughness_tri(step, dx_meters=10.0, dy_meters=10.0, vertical_units="meters")
    assert np.nanmax(tri_step) > 30.0


def test_roughness_tri_resolution_aware_metric_window():
    """Verify physical TRI window adapts pixel half-window to horizontal meter spacing."""
    grid = np.zeros((25, 25), dtype=np.float64)
    _, meta_fine = calculate_roughness_tri_with_metadata(
        grid,
        dx_meters=10.0,
        dy_meters=10.0,
        neighborhood_radius_meters=50.0,
        vertical_units="meters",
    )
    _, meta_coarse = calculate_roughness_tri_with_metadata(
        grid,
        dx_meters=25.0,
        dy_meters=25.0,
        neighborhood_radius_meters=50.0,
        vertical_units="meters",
    )
    assert meta_fine["window_half_pixels_x"] == 5
    assert meta_coarse["window_half_pixels_x"] == 2


def test_terrain_rejects_unknown_or_nonmetric_units_and_empty_stats():
    """Verify unknown/non-metric vertical units raise ValueError and empty grids report unavailable."""
    flat = generate_flat_surface(elevation_m=10.0, shape=(8, 8))
    with pytest.raises(ValueError, match="vertical elevation units"):
        calculate_slope(flat, dx_meters=10.0, dy_meters=10.0, vertical_units="unknown")
    with pytest.raises(ValueError, match="vertical elevation units"):
        calculate_slope(flat, dx_meters=10.0, dy_meters=10.0, vertical_units="feet")
    with pytest.raises(ValueError, match="positive"):
        calculate_slope(flat, dx_meters=-5.0, dy_meters=10.0, vertical_units="meters")

    empty = np.full((6, 6), np.nan, dtype=np.float64)
    stats = compute_band_stats(empty, units="meters")
    assert stats.available is False
    assert stats.min_value is None
    assert stats.max_value is None
    assert stats.mean_value is None
    assert stats.valid_pixel_count == 0
