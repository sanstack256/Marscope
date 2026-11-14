"""
Scientific Target Schemas
Martian Surface Intelligence & Exploration System

Strictly separates reproducible evidence-backed generated targets from
explicitly labeled unverified manual/administrative target registrations.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TargetProvenanceStatus(str, Enum):
    EVIDENCE_BACKED = "evidence_backed"
    MANUAL_UNVERIFIED_ADMINISTRATIVE = "manual_unverified_administrative"


class ScienceTarget(BaseModel):
    id: str = Field(..., description="Unique scientific target identifier")
    name: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    elevation_m: Optional[float] = None
    crs: str = Field("IAU2000:49900")
    geology_type: str
    scientific_value: float = Field(..., ge=0.0, le=1.0)
    instrument_source: str
    provenance_product_id: str
    target_status: TargetProvenanceStatus = Field(
        TargetProvenanceStatus.MANUAL_UNVERIFIED_ADMINISTRATIVE,
        description="Distinguishes evidence-backed generated targets from manual administrative entries",
    )
    evidence_ids: List[str] = Field(default_factory=list)
    matched_species: Optional[str] = None
    distance_from_astronaut_m: Optional[float] = None
    explanation: Optional[str] = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TargetGenerationRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Element or mineral query to generate targets from")
    max_targets: int = Field(10, ge=1, le=50)
    max_distance_m: Optional[float] = Field(None, gt=0.0)
    astronaut_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    astronaut_longitude: Optional[float] = Field(None, ge=-180.0, le=360.0)
    include_element_bearing_minerals: bool = False
