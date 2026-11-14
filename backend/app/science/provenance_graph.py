"""
MARSCOPE Provenance-Aware Scientific Data Dependency Graph & Classification
Martian Surface Intelligence & Exploration System

Implements the 7-tier scientific data classification and traceable dependency
graphs required so every derived value, terrain product, optical candidate,
physics calculation, and computed route can be traced back to authoritative
NASA source observations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScientificDataClassification(str, Enum):
    DIRECTLY_MEASURED = "DIRECTLY_MEASURED"
    ARCHIVE_DERIVED = "ARCHIVE_DERIVED"
    MARSCOPE_DERIVED = "MARSCOPE_DERIVED"
    MODELLED = "MODELLED"
    USER_ASSUMED = "USER_ASSUMED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


class ProvenanceStep(BaseModel):
    step_id: str
    label: str
    classification: ScientificDataClassification
    input_ids: List[str] = Field(default_factory=list)
    method: str
    algorithm_version: str
    output_variable: str
    output_units: Optional[str] = None
    output_resolution_m: Optional[float] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)


class ProvenanceDependencyGraph(BaseModel):
    output_id: str
    classification: ScientificDataClassification
    input_datasets: List[str] = Field(default_factory=list)
    input_product_ids: List[str] = Field(default_factory=list)
    input_variables: List[str] = Field(default_factory=list)
    input_units: List[str] = Field(default_factory=list)
    input_crs: str = "IAU2000:49900"
    input_resolution_m: Optional[float] = None
    input_timestamps: List[str] = Field(default_factory=list)
    method: str
    algorithm_version: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    intermediate_steps: List[ProvenanceStep] = Field(default_factory=list)
    output_units: Optional[str] = None
    output_resolution_m: Optional[float] = None
    uncertainty_method: str = "unpropagated_or_bounded_by_source"
    validation_state: str = "verified_derivation"
    processing_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    scientific_notes: List[str] = Field(default_factory=list)
