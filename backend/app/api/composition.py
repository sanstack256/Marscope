"""
MARSCOPE Verified Composition Discovery & Spatial Index Endpoints
Martian Surface Intelligence & Exploration System
"""

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.models import (
    CompositionEvidence,
    CompositionIndexStatus,
    SpeciesRecord,
    SpeciesResolutionResult,
)
from app.science.composition.search import (
    StructuredCompositionQuery,
    StructuredCompositionSearchResult,
)
from app.science.composition.species import list_all_species, resolve_species_query
from app.services.container import (
    INDEX_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    composition_index,
    composition_search_service,
    localization_service,
)

router = APIRouter(prefix="/composition", tags=["Scientific Composition Discovery"])


@router.get("/species", response_model=List[SpeciesRecord])
async def get_supported_species(q: Optional[str] = Query(None, description="Optional filter prefix/substring")) -> List[SpeciesRecord]:
    """List controlled planetary chemical elements, oxides, minerals, and mineral groups."""
    all_sp = list_all_species()
    if not q or not q.strip():
        return all_sp
    low = q.strip().lower()
    return [
        s
        for s in all_sp
        if low in s.canonical_id.lower()
        or low in s.canonical_name.lower()
        or any(low in a.lower() for a in s.aliases)
    ]


@router.get("/species/resolve", response_model=SpeciesResolutionResult)
async def resolve_species(query: str = Query(..., min_length=1)) -> SpeciesResolutionResult:
    """Resolve a user species string against the controlled vocabulary, flagging ambiguity explicitly."""
    return resolve_species_query(query)


@router.get("/index/status", response_model=CompositionIndexStatus)
async def get_index_status() -> CompositionIndexStatus:
    """Return active SQLite composition spatial index generation status and integrity checks."""
    return composition_index.get_status()


@router.post("/index/rebuild", response_model=CompositionIndexStatus)
async def rebuild_composition_index() -> CompositionIndexStatus:
    """
    Rebuild the SQLite composition spatial index atomically from verified raw NASA PDS
    artifacts currently on disk (APXS, ChemCam MOC/PSV, CheMin RDR5, REMS exclusion audit).
    """
    return composition_index.rebuild_from_raw_directory(raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR)


@router.post("/search", response_model=StructuredCompositionSearchResult)
async def search_composition_structured(req: StructuredCompositionQuery) -> StructuredCompositionSearchResult:
    """
    Execute full structured element/mineral composition discovery with Mars ellipsoidal
    distance ranking and candidate location clustering.
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
    try:
        return composition_search_service.search(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/evidence/{evidence_id}", response_model=CompositionEvidence)
async def inspect_evidence_record(evidence_id: str) -> CompositionEvidence:
    """Retrieve complete provenance, uncertainties, coordinates, and 12-stage audit log for one evidence record."""
    ev = composition_index.get_evidence_by_id(evidence_id)
    if ev is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Composition evidence '{evidence_id}' not found in active index.",
        )
    return ev


@router.get("/rejected")
async def list_rejected_composition_records(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List records explicitly rejected by the 12-stage validation pipeline for audit inspection."""
    total, items = composition_index.list_rejected_records(limit=limit, offset=offset)
    return {
        "total_rejected": total,
        "limit": limit,
        "offset": offset,
        "records": [r.model_dump(mode="json") for r in items],
    }


@router.get("/reproducibility-manifest")
async def get_reproducibility_manifest() -> Dict[str, Any]:
    """
    Return the cryptographically authenticated reproducibility manifest resolved through
    the active generation pointer (`complete_manifest_digest` + DB + pointer verified).
    """
    target_idx = (
        composition_index
        if INDEX_DIR == composition_index.db_path.parent
        else CompositionSpatialIndex(INDEX_DIR / "composition_index.sqlite")
    )
    try:
        return target_idx.get_authenticated_manifest()
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Reproducibility manifest authentication failed: {exc}",
        ) from exc
