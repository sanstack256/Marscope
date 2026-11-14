"""
Automated Physics Law & Benchmark Tests
Validates physical calculations against NASA Fact Sheet values within 0.1% tolerance.
"""

import math
import pytest
from app.physics.registry.parameters import get_parameter
from app.physics.models.surface import (
    calculate_surface_weight,
    calculate_gravitational_potential_energy,
    calculate_atmospheric_density,
    calculate_aerodynamic_drag,
    calculate_uphill_parallel_force,
)


def test_surface_weight_nasa_benchmark():
    """
    On Earth, a 100 kg mass weighs 980.665 N.
    On Mars, with g = 3.72076 m/s^2, a 100 kg mass must weigh 372.076 N.
    A suited explorer of 200 kg mass must weigh 744.152 N.
    """
    result = calculate_surface_weight(mass_kg=200.0)
    assert result.units == "N"
    assert math.isclose(result.calculated_value, 744.152, rel_tol=1e-4)
    assert len(result.scientific_references) > 0


def test_gravitational_potential_energy_delta():
    """
    delta_PE = m * g * delta_h.
    For m = 100 kg, delta_h = 50 m: delta_PE = 100 * 3.72076 * 50 = 18603.8 J.
    """
    result = calculate_gravitational_potential_energy(mass_kg=100.0, delta_h_m=50.0)
    assert result.units == "J"
    assert math.isclose(result.calculated_value, 18603.8, rel_tol=1e-3)


def test_atmospheric_density_ideal_gas():
    """
    rho = p / (R_co2 * T)
    For p = 750 Pa, T = 215 K, R_co2 = 188.92 J/(kg*K):
    rho = 750 / (188.92 * 215) = 750 / 40617.8 ~= 0.018465 kg/m^3.
    """
    result = calculate_atmospheric_density(pressure_pa=750.0, temperature_k=215.0)
    assert result.units == "kg/m^3"
    expected_rho = 750.0 / (188.92 * 215.0)
    assert math.isclose(result.calculated_value, expected_rho, rel_tol=1e-3)


def test_uphill_parallel_force_slope_invariants():
    """
    F_parallel = m * g * sin(theta)
    At theta = 0 deg: F_parallel = 0 N.
    At theta = 30 deg: sin(30) = 0.5 -> F_parallel = 0.5 * W.
    """
    res_flat = calculate_uphill_parallel_force(mass_kg=100.0, slope_degrees=0.0)
    assert math.isclose(res_flat.calculated_value, 0.0, abs_tol=1e-5)

    res_30 = calculate_uphill_parallel_force(mass_kg=100.0, slope_degrees=30.0)
    w_res = calculate_surface_weight(mass_kg=100.0)
    assert math.isclose(res_30.calculated_value, w_res.calculated_value * 0.5, rel_tol=1e-4)


def test_negative_mass_rejected():
    with pytest.raises(ValueError):
        calculate_surface_weight(mass_kg=-10.0)
