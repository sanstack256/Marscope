"""
Destination Selection & Composition-Search Contract Schemas
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.dataset import VerificationState
from app.science.composition.models import (
    CandidateDiscoveryLocation,
    CompositionIndexStatus,
    CompositionSearchMode,
    RankedCompositionHit,
    SpeciesResolutionResult,
)


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
    coverage_verified: bool = False
    verification_state: VerificationState
    footprint_provenance: Optional[str] = None
    crs: Optional[str] = None
    longitude_range: Optional[str] = None
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
    unverified_catalog_candidates: List[DatasetCoverageMatch] = Field(default_factory=list)
    terrain: TerrainPointAssessment
    warnings: List[str] = Field(default_factory=list)
    selected_at_utc: datetime


class CompositionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Element symbol, oxide formula, or mineral name")
    search_mode: CompositionSearchMode = CompositionSearchMode.AUTO
    include_element_bearing_minerals: bool = False
    astronaut_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    astronaut_longitude: Optional[float] = Field(None, ge=-180.0, le=360.0)
    use_active_astronaut_position: bool = True
    max_distance_m: Optional[float] = Field(None, gt=0.0)
    instruments: Optional[List[str]] = None
    sol_min: Optional[int] = Field(None, ge=0)
    sol_max: Optional[int] = Field(None, ge=0)
    min_value: Optional[float] = Field(None, ge=0.0)
    exclude_low_quality: bool = False
    sort_by: str = Field("rank")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class CompositionOccurrence(BaseModel):
    evidence_id: str
    observation_id: str
    dataset_id: str
    product_id: str
    instrument_id: str
    target_name: Optional[str] = None
    sol: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation_m: Optional[float] = None
    crs: Optional[str] = None
    measured_species: str
    evidence_type: str
    match_type: str
    value: Optional[float] = None
    units: Optional[str] = None
    uncertainty: Optional[float] = None
    distance_from_astronaut_m: Optional[float] = None
    composite_rank_score: float = 0.0
    coordinate_source: Optional[str] = None
    source_reference: str


class CompositionSearchResponse(BaseModel):
    query: str
    index_available: bool
    total_matches: int = 0
    unlocated_matches_count: int = 0
    results: List[CompositionOccurrence] = Field(default_factory=list)
    hits: List[RankedCompositionHit] = Field(default_factory=list)
    candidate_locations: List[CandidateDiscoveryLocation] = Field(default_factory=list)
    resolution: Optional[SpeciesResolutionResult] = None
    index_status: Optional[CompositionIndexStatus] = None
    astronaut_position_used: Optional[Dict[str, Any]] = None
    unavailable_reason: Optional[str] = None
    scientific_warnings: List[str] = Field(default_factory=list)
