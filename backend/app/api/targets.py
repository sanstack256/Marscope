"""
MARSCOPE Scientific Targets Endpoints
Martian Surface Intelligence & Exploration System

Strictly distinguishes evidence-backed generated targets from unverified manual coordinates.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.schemas.target import (
    ScienceTarget,
    TargetGenerationRequest,
    TargetProvenanceStatus,
)
from app.services.container import (
    composition_search_service,
    localization_service,
    target_registry,
)

router = APIRouter(prefix="/targets", tags=["Scientific Targets"])


@router.get("", response_model=List[ScienceTarget])
async def list_targets(
    classification: Optional[str] = None,
    target_status: Optional[TargetProvenanceStatus] = None,
) -> List[ScienceTarget]:
    """
    List registered investigation targets with provenance status (`evidence_backed` vs
    `manual_unverified_administrative`).
    """
    return target_registry.list_targets(classification=classification, status_filter=target_status)


@router.get("/{target_id}", response_model=ScienceTarget)
async def get_target(target_id: str) -> ScienceTarget:
    target = target_registry.get_target(target_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scientific target '{target_id}' not found in verified registry.",
        )
    return target


@router.post("", response_model=ScienceTarget)
async def register_target(target: ScienceTarget) -> ScienceTarget:
    """
    Register a target. Without verified index evidence IDs, status is strictly marked
    `manual_unverified_administrative`.
    """
    return target_registry.register_target(target)


@router.post("/generate", response_model=List[ScienceTarget])
async def generate_targets(req: TargetGenerationRequest) -> List[ScienceTarget]:
    """
    Reproducibly generate evidence-backed scientific targets from verified composition search.
    Uses active localization astronaut coordinates when coordinates are not passed explicitly.
    """
    if req.astronaut_latitude is None or req.astronaut_longitude is None:
        loc_status = localization_service.get_status()
        pos = loc_status.current_position
        if pos and pos.latitude is not None and pos.longitude is not None:
            req = req.model_copy(
                update={
                    "astronaut_latitude": pos.latitude,
                    "astronaut_longitude": pos.longitude,
                }
            )
    return target_registry.generate_targets_from_discovery(req, composition_search_service)
