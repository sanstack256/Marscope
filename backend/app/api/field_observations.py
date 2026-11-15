"""
Crew-Scoped Field Observations & Species Vocabulary Endpoints.
Does NOT alter /api/observations (PDS orbital/rover data). Mounted at /api/missions/{mission_id}/observations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    AuthContext,
    load_mission_membership,
    require_auth,
    require_mission_roles,
)
from app.schemas.mission_collab import (
    CreateFieldObservationRequest,
    FieldObservationResponse,
    ReviewFieldObservationRequest,
    UpdateFieldObservationRequest,
)
from app.science.composition.species import list_all_species
from app.services.container import field_observation_service

router = APIRouter(tags=["Crew Field Observations"])


@router.get("/missions/vocabulary/species")
def list_observation_species_vocabulary(
    q: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(require_auth),
) -> List[Dict[str, Any]]:
    _ = auth
    items = list_all_species()
    if q:
        needle = q.strip().lower()
        items = [
            s
            for s in items
            if needle in s.canonical_id.lower()
            or needle in s.canonical_name.lower()
            or any(needle in a.lower() for a in s.aliases)
        ]
    return [
        {
            "canonical_id": s.canonical_id,
            "canonical_name": s.canonical_name,
            "category": s.category.value,
            "symbol_or_formula": s.symbol_or_formula,
            "aliases": s.aliases,
        }
        for s in items[:100]
    ]


@router.post(
    "/missions/{mission_id}/observations",
    response_model=FieldObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_field_observation(
    mission_id: str,
    payload: CreateFieldObservationRequest,
    auth: AuthContext = Depends(require_auth),
) -> FieldObservationResponse:
    load_mission_membership(mission_id, auth)
    return field_observation_service.create_observation(mission_id, auth.astronaut_id, payload)


@router.get("/missions/{mission_id}/observations", response_model=List[FieldObservationResponse])
def list_field_observations(
    mission_id: str,
    category: Optional[str] = Query(default=None),
    species: Optional[str] = Query(default=None),
    epistemic_state: Optional[str] = Query(default=None),
    astronaut_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_auth),
) -> List[FieldObservationResponse]:
    load_mission_membership(mission_id, auth)
    return field_observation_service.list_observations(
        mission_id,
        requester_id=auth.astronaut_id,
        category=category,
        species=species,
        epistemic_state=epistemic_state,
        astronaut_id=astronaut_id,
        limit=limit,
    )


@router.patch(
    "/missions/{mission_id}/observations/{observation_id}",
    response_model=FieldObservationResponse,
)
def update_field_observation(
    mission_id: str,
    observation_id: str,
    payload: UpdateFieldObservationRequest,
    auth: AuthContext = Depends(require_auth),
) -> FieldObservationResponse:
    mem = load_mission_membership(mission_id, auth)
    return field_observation_service.update_observation(
        mission_id,
        observation_id,
        auth.astronaut_id,
        mem.role,
        payload,
    )


@router.post(
    "/missions/{mission_id}/observations/{observation_id}/review",
    response_model=FieldObservationResponse,
)
def review_field_observation(
    mission_id: str,
    observation_id: str,
    payload: ReviewFieldObservationRequest,
    auth: AuthContext = Depends(require_auth),
) -> FieldObservationResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return field_observation_service.review_observation(
        mission_id,
        observation_id,
        auth.astronaut_id,
        payload,
    )
