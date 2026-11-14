"""
MARSCOPE Physics Models & Parameter Registry API
Martian Surface Intelligence & Exploration System
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.schemas.physics import PhysicsParameter, PhysicsCalculationResult, PhysicsCalculationRequest
from app.physics.registry.parameters import list_parameters, get_parameter
from app.physics.models.surface import (
    calculate_surface_weight,
    calculate_gravitational_potential_energy,
    calculate_atmospheric_density,
    calculate_aerodynamic_drag,
    calculate_uphill_parallel_force,
)

router = APIRouter(prefix="", tags=["Physics & Biophysical Engine"])


@router.get("/parameters", response_model=List[PhysicsParameter])
async def get_parameters() -> List[PhysicsParameter]:
    """
    Retrieve the versioned scientific parameter registry (gravitational constants, radii, gas constants, dose rates).
    """
    params = list_parameters()
    return list(params.values())


@router.get("/physics/models")
async def list_models() -> List[Dict[str, Any]]:
    """
    List available validated physical models, mathematical formulations, and required inputs.
    """
    return [
        {
            "model_name": "martian_surface_weight",
            "equation": "W = m * g_mars",
            "required_inputs": ["mass_kg"],
            "output_units": "N",
            "description": "Computes explorer weight on Martian surface using GSFC standard gravity.",
        },
        {
            "model_name": "gravitational_potential_energy_delta",
            "equation": "delta_PE = m * g_mars * delta_h",
            "required_inputs": ["mass_kg", "delta_h_m"],
            "output_units": "J",
            "description": "Computes gravitational potential energy change climbing/descending terrain.",
        },
        {
            "model_name": "martian_atmospheric_density_ideal_gas",
            "equation": "rho = p / (R_co2 * T)",
            "required_inputs": ["pressure_pa", "temperature_k"],
            "output_units": "kg/m^3",
            "description": "Computes hypobaric Martian atmospheric density under pure CO2 approximation.",
        },
        {
            "model_name": "aerodynamic_drag_force",
            "equation": "F_d = 0.5 * rho * C_d * A * v^2",
            "required_inputs": ["pressure_pa", "temperature_k", "velocity_m_s"],
            "output_units": "N",
            "description": "Computes aerodynamic drag during dust storms or windy surface operations.",
        },
        {
            "model_name": "uphill_gravitational_resisting_force",
            "equation": "F_parallel = m * g_mars * sin(theta)",
            "required_inputs": ["mass_kg", "slope_degrees"],
            "output_units": "N",
            "description": "Computes gravity component resisting astronaut or rover motion along a slope.",
        },
    ]


@router.post("/physics/calculate", response_model=PhysicsCalculationResult)
async def calculate_physics(request: PhysicsCalculationRequest) -> PhysicsCalculationResult:
    """
    Execute a validated physical model calculation, returning the result with full provenance, units, and warnings.
    """
    try:
        if request.model_name == "weight":
            if request.mass_kg is None:
                raise ValueError("mass_kg is required for weight calculation.")
            return calculate_surface_weight(request.mass_kg)

        elif request.model_name == "potential_energy":
            if request.mass_kg is None or request.delta_h_m is None:
                raise ValueError("mass_kg and delta_h_m are required for potential energy calculation.")
            return calculate_gravitational_potential_energy(request.mass_kg, request.delta_h_m)

        elif request.model_name == "atmospheric_density":
            if request.pressure_pa is None or request.temperature_k is None:
                raise ValueError("pressure_pa and temperature_k are required for density calculation.")
            return calculate_atmospheric_density(request.pressure_pa, request.temperature_k)

        elif request.model_name == "drag":
            if request.pressure_pa is None or request.temperature_k is None or request.velocity_m_s is None:
                raise ValueError("pressure_pa, temperature_k, and velocity_m_s are required for drag.")
            density_res = calculate_atmospheric_density(request.pressure_pa, request.temperature_k)
            return calculate_aerodynamic_drag(density_res.calculated_value, request.velocity_m_s)

        elif request.model_name == "uphill_force":
            if request.mass_kg is None or request.slope_degrees is None:
                raise ValueError("mass_kg and slope_degrees are required for uphill force.")
            return calculate_uphill_parallel_force(request.mass_kg, request.slope_degrees)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model_name: '{request.model_name}'. See /api/physics/models for supported models.",
            )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
