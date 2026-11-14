"""
MARSCOPE Foundational Surface Physics Models
Martian Surface Intelligence & Exploration System

Implements physical laws adhering strictly to SI units, traceable parameter registries,
and explicit error boundaries.
"""

import math
from typing import Dict, Any, List
from app.schemas.physics import PhysicsCalculationResult
from app.physics.registry.parameters import get_parameter


def calculate_surface_weight(mass_kg: float) -> PhysicsCalculationResult:
    """
    Calculate surface weight W = m * g on Mars.
    
    Args:
        mass_kg: Total explorer system mass (astronaut + suit + equipment) in kilograms.
    """
    if mass_kg <= 0:
        raise ValueError("Mass must be strictly positive (> 0 kg).")
    
    g_param = get_parameter("mars_standard_gravity")
    if not g_param:
        raise RuntimeError("Missing required parameter: mars_standard_gravity")
    
    weight_n = mass_kg * g_param.value
    uncertainty_n = mass_kg * (g_param.uncertainty or 0.0)
    
    warnings: List[str] = []
    if mass_kg > 500.0:
        warnings.append("System mass exceeds nominal suited crew baseline (expected <= 350 kg).")

    return PhysicsCalculationResult(
        model_name="martian_surface_weight",
        model_version="1.0.0",
        calculated_value=round(weight_n, 4),
        units="N",
        inputs={"mass_kg": mass_kg, "g_mars": g_param.value},
        scientific_references=[f"{g_param.name} ({g_param.source})"],
        engineering_assumptions=["Rigid body approximation", "Constant local gravity vector"],
        uncertainty=round(uncertainty_n, 5),
        validity_warnings=warnings,
    )


def calculate_gravitational_potential_energy(mass_kg: float, delta_h_m: float) -> PhysicsCalculationResult:
    """
    Calculate change in gravitational potential energy delta_PE = m * g * delta_h.
    
    Args:
        mass_kg: System mass in kg.
        delta_h_m: Vertical displacement in meters.
    """
    if mass_kg <= 0:
        raise ValueError("Mass must be strictly positive.")
    
    g_param = get_parameter("mars_standard_gravity")
    if not g_param:
        raise RuntimeError("Missing parameter: mars_standard_gravity")
    
    delta_pe_j = mass_kg * g_param.value * delta_h_m
    uncertainty_j = abs(delta_h_m * mass_kg * (g_param.uncertainty or 0.0))
    
    return PhysicsCalculationResult(
        model_name="gravitational_potential_energy_delta",
        model_version="1.0.0",
        calculated_value=round(delta_pe_j, 3),
        units="J",
        inputs={"mass_kg": mass_kg, "delta_h_m": delta_h_m, "g_mars": g_param.value},
        scientific_references=[f"{g_param.name} ({g_param.source})"],
        engineering_assumptions=["Homogeneous gravitational acceleration over delta_h"],
        uncertainty=round(uncertainty_j, 4),
        validity_warnings=[],
    )


def calculate_atmospheric_density(pressure_pa: float, temperature_k: float) -> PhysicsCalculationResult:
    """
    Calculate atmospheric density using the ideal gas law: rho = p / (R_specific * T)
    
    Args:
        pressure_pa: Ambient atmospheric pressure in Pascals.
        temperature_k: Ambient temperature in Kelvin.
    """
    if pressure_pa <= 0:
        raise ValueError("Pressure must be positive (> 0 Pa).")
    if temperature_k <= 0:
        raise ValueError("Temperature must be positive (> 0 K).")
    
    r_param = get_parameter("specific_gas_constant_co2")
    if not r_param:
        raise RuntimeError("Missing parameter: specific_gas_constant_co2")
    
    density_kg_m3 = pressure_pa / (r_param.value * temperature_k)
    
    warnings: List[str] = []
    if pressure_pa < 500.0 or pressure_pa > 1200.0:
        warnings.append(f"Pressure ({pressure_pa} Pa) is outside nominal Martian surface bounds [500, 1200 Pa].")
    if temperature_k < 150.0 or temperature_k > 310.0:
        warnings.append(f"Temperature ({temperature_k} K) is outside nominal Martian surface bounds [150, 310 K].")

    # Propagate first-order uncertainty
    rel_r_unc = (r_param.uncertainty or 0.0) / r_param.value
    rel_total_unc = rel_r_unc  # Assuming perfect pressure/temp sensor for baseline or sensor variance
    density_unc = density_kg_m3 * rel_total_unc

    return PhysicsCalculationResult(
        model_name="martian_atmospheric_density_ideal_gas",
        model_version="1.0.0",
        calculated_value=round(density_kg_m3, 6),
        units="kg/m^3",
        inputs={"pressure_pa": pressure_pa, "temperature_k": temperature_k, "R_specific_co2": r_param.value},
        scientific_references=[f"{r_param.name} ({r_param.source})"],
        engineering_assumptions=["Ideal gas law holds under hypobaric Martian conditions", "Pure CO2 gas approximation"],
        uncertainty=round(density_unc, 7),
        validity_warnings=warnings,
    )


def calculate_aerodynamic_drag(
    density_kg_m3: float,
    velocity_m_s: float,
    drag_coefficient_cd: float = 1.1,
    frontal_area_m2: float = 0.9,
) -> PhysicsCalculationResult:
    """
    Calculate aerodynamic drag force F_d = 0.5 * rho * C_d * A * v^2.
    """
    if density_kg_m3 <= 0:
        raise ValueError("Density must be positive.")
    if velocity_m_s < 0:
        raise ValueError("Velocity must be non-negative.")
    if drag_coefficient_cd <= 0 or frontal_area_m2 <= 0:
        raise ValueError("Drag coefficient and frontal area must be strictly positive.")

    drag_n = 0.5 * density_kg_m3 * drag_coefficient_cd * frontal_area_m2 * (velocity_m_s ** 2)

    return PhysicsCalculationResult(
        model_name="aerodynamic_drag_force",
        model_version="1.0.0",
        calculated_value=round(drag_n, 5),
        units="N",
        inputs={
            "density_kg_m3": density_kg_m3,
            "velocity_m_s": velocity_m_s,
            "C_d": drag_coefficient_cd,
            "area_m2": frontal_area_m2,
        },
        scientific_references=["Classical Aerodynamics / Fluid Dynamics (NASA SP-8005)"],
        engineering_assumptions=["Blunt suited body drag coefficient C_d=1.1", "Cross-sectional frontal area A=0.9 m^2"],
        uncertainty=round(drag_n * 0.1, 5),  # ~10% aerodynamic variance
        validity_warnings=[],
    )


def calculate_uphill_parallel_force(mass_kg: float, slope_degrees: float) -> PhysicsCalculationResult:
    """
    Calculate uphill gravitational resisting force F_parallel = m * g * sin(theta).
    """
    if mass_kg <= 0:
        raise ValueError("Mass must be strictly positive.")
    if slope_degrees < 0 or slope_degrees > 90:
        raise ValueError("Slope angle must be between 0 and 90 degrees.")

    g_param = get_parameter("mars_standard_gravity")
    if not g_param:
        raise RuntimeError("Missing parameter: mars_standard_gravity")

    theta_rad = math.radians(slope_degrees)
    force_n = mass_kg * g_param.value * math.sin(theta_rad)

    warnings: List[str] = []  # No slope safety threshold is asserted (none is validated).

    return PhysicsCalculationResult(
        model_name="uphill_gravitational_resisting_force",
        model_version="1.0.0",
        calculated_value=round(force_n, 4),
        units="N",
        inputs={"mass_kg": mass_kg, "slope_degrees": slope_degrees, "g_mars": g_param.value},
        scientific_references=[f"{g_param.name} ({g_param.source})"],
        engineering_assumptions=["Planar inclined plane mechanics", "Zero wheel/foot regolith compaction sinkage considered"],
        uncertainty=round(force_n * 0.01, 4),
        validity_warnings=warnings,
    )
