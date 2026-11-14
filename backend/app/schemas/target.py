"""
Scientific Investigation Target Schema
Martian Surface Intelligence & Exploration System
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.observation import ObservationCoordinates


class ScienceTarget(BaseModel):
    target_id: str = Field(..., description="Unique scientific target identifier")
    name: str = Field(..., description="Canonical geological designation (e.g., Mount Sharp Boxwork Crest Alpha)")
    geometry: ObservationCoordinates = Field(..., description="3D coordinates of target")
    classification: str = Field(..., description="Geomorphological unit (e.g., Boxwork Fracture Network, Layered Sulfate Bedrock)")
    scientific_question: str = Field(..., description="Specific paleohydrological or diagenetic investigation question")
    supporting_observation_ids: List[str] = Field(default_factory=list, description="Associated real observation IDs proving target significance")
    supporting_dataset_ids: List[str] = Field(default_factory=list, description="Supporting orbital or rover dataset IDs")
    contradictory_evidence: Optional[str] = Field(None, description="Documented contradictory or ambiguous spectral/morphological findings")
    observation_dates: List[str] = Field(default_factory=list, description="Dates or Sols of supporting observations")
    interpretation_limitations: List[str] = Field(default_factory=list, description="Limitations (e.g., dust cover, steep approach slope)")
    suggested_measurements: List[str] = Field(default_factory=list, description="Recommended in-situ astronaut or rover instruments")
    provenance: str = Field(..., description="Traceable citation to peer-reviewed publication or PDS archive")
