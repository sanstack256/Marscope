"""
MARSCOPE Scientific Targets API
Martian Surface Intelligence & Exploration System

Exposes evidence-backed scientific targets.
Per project rules, no targets with fabricated coordinates or conclusions are prepopulated.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.schemas.target import ScienceTarget
from app.services.container import target_registry

router = APIRouter(prefix="/targets", tags=["Scientific Targets"])


@router.get("", response_model=List[ScienceTarget])
async def list_targets(classification: Optional[str] = None) -> List[ScienceTarget]:
    """
    List verified evidence-backed scientific investigation targets.
    Returns empty list if zero verified targets have been loaded (adhering to zero-fabrication rules).
    """
    return target_registry.list_targets(classification=classification)


@router.get("/{target_id}", response_model=ScienceTarget)
async def get_target(target_id: str) -> ScienceTarget:
    """
    Retrieve specific scientific target dossier.
    """
    target = target_registry.get_target(target_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target '{target_id}' not found.",
        )
    return target


@router.post("", response_model=ScienceTarget)
async def register_target(target: ScienceTarget) -> ScienceTarget:
    """
    Register an evidence-backed scientific target.
    """
    return target_registry.register_target(target)
