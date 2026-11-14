"""
Health Schema Module
"""

from datetime import datetime
from typing import Dict
from pydantic import BaseModel, Field


class EngineStatus(BaseModel):
    physics: str = Field("ready", description="Physics engine readiness status")
    geospatial: str = Field("ready", description="Geospatial engine readiness status")
    terrain: str = Field("ready", description="Terrain processing readiness status")
    routing: str = Field("ready", description="Constrained routing engine readiness status")


class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Overall backend health status")
    system: str = Field("MARSCOPE Martian Surface Intelligence Engine", description="System designation")
    version: str = Field(..., description="API version")
    environment: str = Field(..., description="Active runtime environment")
    timestamp_utc: datetime = Field(..., description="Current server UTC timestamp")
    engines: EngineStatus = Field(..., description="Subsystem readiness statuses")
