"""
Scientific Observation Schema
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class ObservationCoordinates(BaseModel):
    latitude: float = Field(..., description="Planetocentric latitude in degrees")
    longitude: float = Field(..., description="East-positive longitude in degrees")
    elevation_m: Optional[float] = Field(None, description="Areoid elevation in meters if documented")


class Observation(BaseModel):
    observation_id: str = Field(..., description="Unique observation identifier")
    dataset_id: str = Field(..., description="Parent dataset identifier")
    mission: str = Field(..., description="Host mission (e.g., Mars Science Laboratory)")
    instrument: str = Field(..., description="Instrument designation (e.g., ChemCam LIBS, REMS)")
    observation_timestamp: Optional[datetime] = Field(None, description="UTC acquisition timestamp if documented")
    sol: Optional[int] = Field(None, description="Mission sol number if documented")
    location: Optional[ObservationCoordinates] = Field(
        None,
        description="Physical coordinates of observation when present in source metadata",
    )
    crs: Optional[str] = Field(None, description="Documented coordinate reference system")
    measurement_type: str = Field(..., description="Nature of measurement")
    measurement_value: Any = Field(..., description="Measured physical value or structured spectrum")
    units: str = Field(..., description="Explicit physical unit (e.g., Pa, K, counts, unknown)")
    processing_level: str = Field(..., description="Processing pipeline level")
    calibration_status: str = Field(..., description="Physical sensor calibration information")
    quality_flags: List[str] = Field(default_factory=list, description="Data quality flags")
    original_source_reference: str = Field(..., description="Product ID or table row reference in archive")
    known_limitations: List[str] = Field(default_factory=list, description="Sensor noise or environmental limitations")
