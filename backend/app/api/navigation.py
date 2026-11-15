"""
Active Marswalk Navigation Session, State Machine, Obstruction, Replan,
and Independent Return / Turnback Endpoints.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    AuthContext,
    load_mission_membership,
    require_auth,
    require_mission_roles,
)
from app.schemas.navigation import (
    ApproveReplanRequest,
    CreateNavigationSessionRequest,
    NavigationSessionResponse,
    NavigationTransitionRequest,
    ReplanNavigationRequest,
    ReportObstructionRequest,
)
from app.services.container import navigation_service

router = APIRouter(prefix="/missions", tags=["Active Navigation"])


@router.post("/{mission_id}/navigation", response_model=NavigationSessionResponse, status_code=status.HTTP_201_CREATED)
def create_navigation_session(
    mission_id: str,
    payload: CreateNavigationSessionRequest,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    load_mission_membership(mission_id, auth)
    return navigation_service.create_session(
        mission_id=mission_id,
        astronaut_id=auth.astronaut_id,
        req=payload,
    )


@router.get("/{mission_id}/navigation", response_model=List[NavigationSessionResponse])
def list_navigation_sessions(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> List[NavigationSessionResponse]:
    load_mission_membership(mission_id, auth)
    return navigation_service.list_sessions(mission_id=mission_id)


@router.get("/{mission_id}/navigation/{nav_session_id}", response_model=NavigationSessionResponse)
def get_navigation_session(
    mission_id: str,
    nav_session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    load_mission_membership(mission_id, auth)
    return navigation_service.get_session(mission_id=mission_id, nav_session_id=nav_session_id)


@router.post("/{mission_id}/navigation/{nav_session_id}/transition", response_model=NavigationSessionResponse)
def transition_navigation_session(
    mission_id: str,
    nav_session_id: str,
    payload: NavigationTransitionRequest,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    member = load_mission_membership(mission_id, auth)
    return navigation_service.transition_state(
        mission_id=mission_id,
        nav_session_id=nav_session_id,
        actor_id=auth.astronaut_id,
        actor_role=member.role,
        req=payload,
    )


@router.post("/{mission_id}/navigation/{nav_session_id}/obstructions", response_model=NavigationSessionResponse)
def report_navigation_obstruction(
    mission_id: str,
    nav_session_id: str,
    payload: ReportObstructionRequest,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    load_mission_membership(mission_id, auth)
    return navigation_service.report_obstruction(
        mission_id=mission_id,
        nav_session_id=nav_session_id,
        actor_id=auth.astronaut_id,
        req=payload,
    )


@router.post("/{mission_id}/navigation/{nav_session_id}/replan", response_model=NavigationSessionResponse)
def compute_navigation_replan(
    mission_id: str,
    nav_session_id: str,
    payload: ReplanNavigationRequest,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    load_mission_membership(mission_id, auth)
    return navigation_service.compute_candidate_replan(
        mission_id=mission_id,
        nav_session_id=nav_session_id,
        actor_id=auth.astronaut_id,
        req=payload,
    )


@router.post("/{mission_id}/navigation/{nav_session_id}/replan/decision", response_model=NavigationSessionResponse)
def decide_navigation_replan(
    mission_id: str,
    nav_session_id: str,
    payload: ApproveReplanRequest,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    require_mission_roles(mission_id, auth, ("MISSION_LEAD", "MISSION_OPERATOR"))
    return navigation_service.decide_candidate_replan(
        mission_id=mission_id,
        nav_session_id=nav_session_id,
        actor_id=auth.astronaut_id,
        req=payload,
    )


@router.post("/{mission_id}/navigation/{nav_session_id}/turnback", response_model=NavigationSessionResponse)
def evaluate_navigation_turnback(
    mission_id: str,
    nav_session_id: str,
    auth: AuthContext = Depends(require_auth),
) -> NavigationSessionResponse:
    load_mission_membership(mission_id, auth)
    return navigation_service.evaluate_turnback(
        mission_id=mission_id,
        nav_session_id=nav_session_id,
        actor_id=auth.astronaut_id,
    )
