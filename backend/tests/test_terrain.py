"""
Automated Terrain Intelligence Tests
Validates slope, aspect, and roughness against mathematical test fixtures.
"""

import math
import numpy as np
import pytest
from app.terrain.slope import calculate_slope
from app.terrain.aspect import calculate_aspect
from app.terrain.roughness import calculate_roughness_tri
from app.terrain.fixtures import generate_flat_surface, generate_planar_slope


def test_flat_surface_slope_is_zero():
    """
    Assert that an analytically flat surface yields exactly 0.0 degrees slope.
    """
    flat = generate_flat_surface(elevation_m=100.0, shape=(15, 15))
    slope_deg, slope_rad = calculate_slope(flat, dx_meters=10.0, dy_meters=10.0)

    # Interior valid pixels (excluding borders)
    valid_slopes = slope_deg[1:-1, 1:-1]
    assert np.allclose(valid_slopes, 0.0, atol=1e-5), "Flat surface must have 0.0 degree slope."


def test_planar_slope_recovery():
    """
    Assert that Horn's gradient method analytically recovers exact known slope angles (30 deg and 45 deg).
    """
    for expected_angle in [15.0, 30.0, 45.0]:
        tilted = generate_planar_slope(slope_deg=expected_angle, dx_m=10.0, dy_m=10.0, shape=(25, 25))
        slope_deg, _ = calculate_slope(tilted, dx_meters=10.0, dy_meters=10.0)

        # Interior pixels
        interior = slope_deg[2:-2, 2:-2]
        mean_calc = float(np.mean(interior))
        assert np.isclose(mean_calc, expected_angle, atol=0.01), (
            f"Expected planar slope of {expected_angle} deg, got {mean_calc} deg."
        )


def test_flat_surface_aspect_is_negative_one():
    """
    Assert that flat terrain has an undefined aspect designated by -1.0.
    """
    flat = generate_flat_surface(elevation_m=50.0, shape=(10, 10))
    aspect = calculate_aspect(flat, dx_meters=10.0, dy_meters=10.0)
    interior_aspect = aspect[1:-1, 1:-1]
    assert np.all(interior_aspect == -1.0), "Aspect of flat terrain must be -1.0."


def test_roughness_tri_on_flat_is_zero():
    """
    Assert that Terrain Ruggedness Index (TRI) on a flat plane is strictly 0.0 meters.
    """
    flat = generate_flat_surface(elevation_m=200.0, shape=(10, 10))
    tri = calculate_roughness_tri(flat)
    interior_tri = tri[1:-1, 1:-1]
    assert np.allclose(interior_tri, 0.0, atol=1e-6), "TRI on flat surface must be 0.0 m."


def test_roughness_tri_on_step():
    """
    Assert that TRI correctly quantifies elevation differences near an abrupt step.
    """
    surface = np.zeros((10, 10), dtype=np.float64)
    surface[:, 5:] = 100.0  # 100m vertical step
    tri = calculate_roughness_tri(surface)
    # Cells immediately adjacent to the step must have positive TRI > 0
    assert np.nanmax(tri) > 30.0, "TRI near a 100m step must reflect significant ruggedness."
