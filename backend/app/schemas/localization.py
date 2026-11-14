"""
Astronaut / Mission Localization Schemas
Martian Surface Intelligence & Exploration System

Supports mission telemetry, suit/rover adapters, manual coordinate entry,
and isolated test fixtures without ever inventing fake GPS positions.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class PositionSourceType(str, Enum):
    MISSION_LIVE_FEED = "mission_live_feed"
    SUIT_ROVER_TELEMETRY = "suit_rover_telemetry"
    MANUAL_SELECTION = "manual_selection"
    TEST_FIXTURE = "test_fixture"
    UNAVAILABLE = "unavailable"


class PositionValidityState(str, Enum):
    VALID = "valid"
    UNVERIFIED = "unverified"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class PositionRecord(BaseModel):
    position_source: PositionSourceType
    latitude: Optional[float] = Field(None, description="Planetocentric latitude in [-90, 90]")
    longitude: Optional[float] = Field(None, description="East-positive longitude in [-180, 180] or [0, 360]")
    elevation_m: Optional[float] = Field(None, description="Elevation in meters only when resolved from validated DEM")
    crs: str = Field("IAU2000:49900", description="Active Mars coordinate reference system")
    latitude_convention: str = Field("Planetocentric")
    longitude_direction: str = Field("East")
    timestamp_utc: Optional[datetime] = None
    accuracy_meters: Optional[float] = None
    validity_state: PositionValidityState
    provenance: str
    notes: List[str] = Field(default_factory=list)


class ManualPositionRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    crs: str = Field("IAU2000:49900")
    latitude_convention: str = Field("Planetocentric")
    longitude_direction: str = Field("East")
    accuracy_meters: Optional[float] = Field(None, ge=0.0)
    provenance: str = Field("Operator manual map selection")


class LocalizationProviderDescriptor(BaseModel):
    provider_id: str
    provider_type: PositionSourceType
    name: str
    connected: bool
    status_detail: str


class LocalizationStatusResponse(BaseModel):
    live_localization_available: bool
    active_provider: PositionSourceType
    unavailable_reason: Optional[str] = None
    current_position: Optional[PositionRecord] = None
    supported_providers: List[LocalizationProviderDescriptor] = Field(default_factory=list)
