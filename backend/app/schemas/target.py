"""
Scientific Target Schemas
Martian Surface Intelligence & Exploration System

Strictly separates reproducible evidence-backed generated targets from
explicitly labeled unverified manual/administrative target registrations.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class TargetProvenanceStatus(str, Enum):
    EVIDENCE_BACKED = "evidence_backed"
    MANUAL_UNVERIFIED_ADMINISTRATIVE = "manual_unverified_administrative"


class InvestigationTargetEvidenceState(str, Enum):
    """7-state epistemic classification for scientific investigation targets."""

    CONFIRMED_LOCAL_OBSERVATION = "confirmed_local_observation"
    ORBITAL_DETECTION_ONLY = "orbital_detection_only"
    INFERRED_REGIONAL_CONTEXT_ONLY = "inferred_regional_context_only"
    OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED = "optical_morphology_candidate_unverified"
    MANUAL_WAYPOINT_UNVERIFIED = "manual_waypoint_unverified"
    DATA_GAP_UNASSESSED = "data_gap_unassessed"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class ScienceTarget(BaseModel):
    id: str = Field(..., description="Unique scientific target identifier")
    name: str
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    elevation_m: Optional[float] = None
    crs: str = Field("IAU2000:49900")
    geology_type: str
    scientific_value: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Backward-compatible engineering exploration priority heuristic (not intrinsic scientific truth).",
    )
    exploration_priority_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Explicit transparent engineering exploration priority heuristic (never a scientific truth or safety score).",
    )
    prioritization_is_heuristic: bool = Field(
        default=True,
        description="Always True: indicates exploration priority is a transparent multi-factor engineering ordering heuristic.",
    )
    prioritization_label: str = Field(
        default="engineering_exploration_priority_heuristic",
        description="Explicit classification preventing heuristic scores from being mistaken for scientific truth.",
    )
    prioritization_breakdown: Dict[str, Any] = Field(
        default_factory=dict,
        description="Transparent per-component arithmetic breakdown of the engineering exploration priority score.",
    )
    instrument_source: str
    provenance_product_id: str
    target_status: TargetProvenanceStatus = Field(
        TargetProvenanceStatus.MANUAL_UNVERIFIED_ADMINISTRATIVE,
        description="Distinguishes evidence-backed generated targets from manual administrative entries",
    )
    evidence_state: InvestigationTargetEvidenceState = Field(
        InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED,
        description="7-state epistemic classification distinguishing direct local observations from orbital/inferred/optical/manual/gap/conflicting evidence.",
    )
    study_region: Optional[str] = Field(
        default=None,
        description="Explicit Martian study region provenance (e.g. Gale Crater / Mount Sharp) to preserve mission isolation.",
    )
    evidence_ids: List[str] = Field(default_factory=list)
    matched_species: Optional[str] = None
    distance_from_astronaut_m: Optional[float] = None
    explanation: Optional[str] = None
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _sync_priority_fields(self) -> "ScienceTarget":
        if self.exploration_priority_score is None and self.scientific_value is not None:
            self.exploration_priority_score = float(self.scientific_value)
        elif self.scientific_value is None and self.exploration_priority_score is not None:
            self.scientific_value = float(self.exploration_priority_score)
        elif self.exploration_priority_score is None and self.scientific_value is None:
            self.exploration_priority_score = 0.0
            self.scientific_value = 0.0
        return self


class TargetGenerationRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Element or mineral query to generate targets from")
    max_targets: int = Field(10, ge=1, le=50)
    max_distance_m: Optional[float] = Field(None, gt=0.0)
    astronaut_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    astronaut_longitude: Optional[float] = Field(None, ge=-180.0, le=360.0)
    include_element_bearing_minerals: bool = False
