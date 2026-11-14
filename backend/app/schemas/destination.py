"""
Destination Selection & Composition-Search Contract Schemas
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.dataset import VerificationState


class DestinationSelectionRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    crs: str = Field("IAU2000:49900")
    latitude_convention: str = Field("Planetocentric")
    longitude_direction: str = Field("East")
    label: Optional[str] = None


class TerrainPointAssessment(BaseModel):
    available: bool
    elevation_m: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    roughness_tri_m: Optional[float] = None
    source_dataset_id: Optional[str] = None
    source_product_id: Optional[str] = None
    resolution_m: Optional[float] = None
    units: Optional[str] = None
    crs: Optional[str] = None
    unavailable_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class DatasetCoverageMatch(BaseModel):
    dataset_id: str
    product_id: str
    product_title: str
    product_type: str
    horizontal_resolution_meters: Optional[float] = None
    available_for_evaluation: bool
    verification_state: VerificationState
    notes: Optional[str] = None


class DestinationEvaluationResponse(BaseModel):
    valid: bool
    latitude: float
    longitude: float
    normalized_longitude_180: float
    normalized_longitude_360: float
    crs: str
    latitude_convention: str
    longitude_direction: str
    label: Optional[str] = None
    can_evaluate: bool
    evaluation_status: str
    covering_datasets: List[DatasetCoverageMatch] = Field(default_factory=list)
    terrain: TerrainPointAssessment
    warnings: List[str] = Field(default_factory=list)
    selected_at_utc: datetime


class CompositionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Element symbol or mineral name (e.g., Fe, SiO2, gypsum, smectite)")
    study_area_only: bool = True


class CompositionOccurrence(BaseModel):
    observation_id: str
    dataset_id: str
    target_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    crs: Optional[str] = None
    measured_species: str
    value: Optional[float] = None
    units: Optional[str] = None
    source_reference: str


class CompositionSearchResponse(BaseModel):
    query: str
    index_available: bool
    total_matches: int = 0
    results: List[CompositionOccurrence] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
