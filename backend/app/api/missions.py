"""
Mission Management, Invitations, Crew Roster, Mars Position Ingest,
Mission Audit Event Timeline, and Isolated Real-Time SSE Stream Endpoints.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    AuthContext,
    load_mission_membership,
    require_auth,
    require_mission_roles,
)
from app.schemas.mission_collab import (
    CreateInvitationRequest,
    CreateMissionRequest,
    CrewMemberResponse,
    CrewPositionResponse,
    IngestPositionRequest,
    InvitationResponse,
    JoinMissionRequest,
    MissionEventResponse,
    MissionSummaryResponse,
    ToggleLocationSharingRequest,
    UpdateMemberRoleRequest,
    UpdateMissionRequest,
)
from app.services.container import (
    mission_event_service,
    mission_realtime_hub,
    mission_service,
    position_service,
)

router = APIRouter(prefix="/missions", tags=["Missions, Crew & Real-Time Operations"])


@router.post("", response_model=MissionSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_mission(
    payload: CreateMissionRequest,
    auth: AuthContext = Depends(require_auth),
) -> MissionSummaryResponse:
    return mission_service.create_mission(auth.astronaut_id, payload)


@router.get("", response_model=List[MissionSummaryResponse])
def list_my_missions(auth: AuthContext = Depends(require_auth)) -> List[MissionSummaryResponse]:
    return mission_service.list_missions_for_astronaut(auth.astronaut_id)


@router.post("/join", response_model=MissionSummaryResponse)
def join_mission_with_invite(
    payload: JoinMissionRequest,
    auth: AuthContext = Depends(require_auth),
) -> MissionSummaryResponse:
    return mission_service.join_by_invite(payload.invite_token, auth.astronaut_id)


@router.get("/{mission_id}", response_model=MissionSummaryResponse)
def get_mission_details(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> MissionSummaryResponse:
    load_mission_membership(mission_id, auth)
    return mission_service.get_mission(mission_id, auth.astronaut_id)


@router.patch("/{mission_id}", response_model=MissionSummaryResponse)
def update_mission(
    mission_id: str,
    payload: UpdateMissionRequest,
    auth: AuthContext = Depends(require_auth),
) -> MissionSummaryResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return mission_service.update_mission(mission_id, auth.astronaut_id, payload)


# ---------------------------------------------------------------------------
# Invitations & Membership Lifecycle
# ---------------------------------------------------------------------------


@router.post("/{mission_id}/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def create_mission_invitation(
    mission_id: str,
    payload: CreateInvitationRequest,
    auth: AuthContext = Depends(require_auth),
) -> InvitationResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return mission_service.create_invitation(mission_id, auth.astronaut_id, payload)


@router.get("/{mission_id}/invitations", response_model=List[InvitationResponse])
def list_mission_invitations(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> List[InvitationResponse]:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return mission_service.list_invitations(mission_id)


@router.post("/{mission_id}/invitations/{invite_id}/revoke")
def revoke_mission_invitation(
    mission_id: str,
    invite_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    mission_service.revoke_invitation(mission_id, invite_id, auth.astronaut_id)
    return {"revoked": True, "invite_id": invite_id}


@router.post("/{mission_id}/leave")
def leave_mission(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    load_mission_membership(mission_id, auth)
    mission_service.leave_mission(mission_id, auth.astronaut_id)
    return {"left": True, "mission_id": mission_id}


@router.delete("/{mission_id}/crew/{astronaut_id}")
def remove_crew_member(
    mission_id: str,
    astronaut_id: str,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD"})
    mission_service.remove_member(mission_id, astronaut_id, auth.astronaut_id)
    return {"removed": True, "astronaut_id": astronaut_id}


@router.patch("/{mission_id}/crew/{astronaut_id}/role")
def change_crew_role(
    mission_id: str,
    astronaut_id: str,
    payload: UpdateMemberRoleRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD"})
    mission_service.update_member_role(mission_id, astronaut_id, payload.role, auth.astronaut_id)
    return {"updated": True, "astronaut_id": astronaut_id, "role": payload.role}


@router.get("/{mission_id}/crew", response_model=List[CrewMemberResponse])
def get_mission_crew_roster(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> List[CrewMemberResponse]:
    load_mission_membership(mission_id, auth)
    return mission_service.list_crew_roster(mission_id, auth.astronaut_id)


# ---------------------------------------------------------------------------
# Mars Crew Positions (IAU2000:49900)
# ---------------------------------------------------------------------------


@router.post("/{mission_id}/positions", response_model=CrewPositionResponse, status_code=status.HTTP_201_CREATED)
def ingest_my_position(
    mission_id: str,
    payload: IngestPositionRequest,
    auth: AuthContext = Depends(require_auth),
) -> CrewPositionResponse:
    load_mission_membership(mission_id, auth)
    return position_service.ingest_position(mission_id, auth.astronaut_id, payload)


@router.get("/{mission_id}/positions", response_model=List[CrewPositionResponse])
def list_crew_positions(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
) -> List[CrewPositionResponse]:
    load_mission_membership(mission_id, auth)
    return position_service.list_latest_positions(mission_id)


@router.put("/{mission_id}/positions/sharing")
def toggle_my_location_sharing(
    mission_id: str,
    payload: ToggleLocationSharingRequest,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    load_mission_membership(mission_id, auth)
    return position_service.toggle_location_sharing(
        mission_id, auth.astronaut_id, payload.location_sharing_enabled
    )


# ---------------------------------------------------------------------------
# Mission Audit Events & Isolated Real-Time SSE Stream
# ---------------------------------------------------------------------------


@router.get("/{mission_id}/events", response_model=List[MissionEventResponse])
def list_mission_events(
    mission_id: str,
    event_type: Optional[str] = Query(default=None),
    before_seq: Optional[int] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    auth: AuthContext = Depends(require_auth),
) -> List[MissionEventResponse]:
    load_mission_membership(mission_id, auth)
    return mission_event_service.list_events(
        mission_id,
        event_type=event_type,
        before_seq=before_seq,
        limit=limit,
    )


@router.get("/{mission_id}/stream")
async def stream_mission_realtime_events(
    mission_id: str,
    auth: AuthContext = Depends(require_auth),
):
    load_mission_membership(mission_id, auth)
    sub = mission_realtime_hub.subscribe(mission_id, auth.astronaut_id)

    async def event_generator():
        try:
            yield mission_realtime_hub.format_sse(
                "connected",
                {
                    "mission_id": mission_id,
                    "astronaut_id": auth.astronaut_id,
                    "server_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "active_subscribers": mission_realtime_hub.active_subscriber_count(mission_id),
                },
            )
            while True:
                try:
                    msg = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield mission_realtime_hub.format_sse(msg["event_type"], msg)
                except asyncio.TimeoutError:
                    yield mission_realtime_hub.format_sse(
                        "heartbeat",
                        {
                            "mission_id": mission_id,
                            "server_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        },
                    )
        finally:
            mission_realtime_hub.unsubscribe(sub)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
