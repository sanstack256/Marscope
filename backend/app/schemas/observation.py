"""
Scientific Observation Schema
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ObservationCoordinates(BaseModel):
    latitude: float = Field(..., description="Planetocentric latitude in degrees")
    longitude: float = Field(..., description="East-positive longitude in degrees")
    elevation_m: Optional[float] = Field(None, description="Areoid elevation in meters")


class Observation(BaseModel):
    observation_id: str = Field(..., description="Unique observation identifier")
    dataset_id: str = Field(..., description="Parent dataset identifier")
    mission: str = Field(..., description="Host mission (e.g., Mars Science Laboratory)")
    instrument: str = Field(..., description="Instrument designation (e.g., ChemCam LIBS, REMS)")
    observation_timestamp: Optional[datetime] = Field(None, description="UTC acquisition timestamp")
    sol: Optional[int] = Field(None, description="Mission sol number")
    location: ObservationCoordinates = Field(..., description="Physical coordinates of observation")
    crs: str = Field("IAU2000:49900", description="Coordinate reference system")
    measurement_type: str = Field(..., description="Nature of measurement (e.g., atmospheric_pressure, surface_temp, elemental_composition, spectral_reflectance)")
    measurement_value: Any = Field(..., description="Measured physical value or structured spectrum")
    units: str = Field(..., description="Explicit physical unit (e.g., Pa, K, counts, wt_percent)")
    processing_level: str = Field("Calibrated (RDR)", description="Processing pipeline level")
    calibration_status: str = Field("Calibrated", description="Physical sensor calibration information")
    quality_flags: List[str] = Field(default_factory=list, description="Data quality flags")
    original_source_reference: str = Field(..., description="Product ID or table row reference in archive")
    known_limitations: List[str] = Field(default_factory=list, description="Sensor noise or environmental limitations")
