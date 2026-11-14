"""
Physics Parameter Registry & Calculation Schemas
Martian Surface Intelligence & Exploration System
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PhysicsParameter(BaseModel):
    id: str = Field(..., description="Unique parameter identifier (e.g., mars_gravity_surface)")
    name: str = Field(..., description="Descriptive parameter name")
    value: float = Field(..., description="Numerical value")
    units: str = Field(..., description="Standard SI unit")
    source: str = Field(..., description="Authoritative reference source")
    source_url: str = Field(..., description="URL to NASA fact sheet or standard")
    validity_range: Optional[List[float]] = Field(None, description="[min_valid, max_valid]")
    applicable_conditions: str = Field(..., description="Context (e.g., Gale Crater floor, nominal solar minimum)")
    uncertainty: Optional[float] = Field(None, description="Reported standard variance or measurement error")
    version: str = Field("1.0.0", description="Parameter registry entry version")
    verification_status: str = Field("Verified NASA GSFC Standard", description="Verification label")


class PhysicsCalculationRequest(BaseModel):
    model_name: str = Field(..., description="weight | potential_energy | atmospheric_density | drag | uphill_force")
    mass_kg: Optional[float] = Field(None, description="Explorer total mass in kg")
    delta_h_m: Optional[float] = Field(None, description="Elevation difference in meters")
    pressure_pa: Optional[float] = Field(None, description="Atmospheric pressure in Pa")
    temperature_k: Optional[float] = Field(None, description="Temperature in Kelvin")
    velocity_m_s: Optional[float] = Field(None, description="Relative velocity in m/s")
    slope_degrees: Optional[float] = Field(None, description="Slope gradient in degrees")


class PhysicsCalculationResult(BaseModel):
    model_name: str = Field(..., description="Mathematical model identifier")
    model_version: str = Field("1.0.0", description="Model implementation version")
    calculated_value: float = Field(..., description="Computed numerical quantity")
    units: str = Field(..., description="SI unit of calculated quantity")
    inputs: Dict[str, Any] = Field(..., description="Actual input parameters supplied to calculation")
    scientific_references: List[str] = Field(..., description="Traceable parameter sources")
    engineering_assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions utilized")
    uncertainty: Optional[float] = Field(None, description="Propagated calculation uncertainty")
    validity_warnings: List[str] = Field(default_factory=list, description="Validity boundary warnings")
