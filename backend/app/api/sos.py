"""
Emergency SOS Dispatch, Crew Acknowledgement & Private Voice Note Upload/Playback Endpoints.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse

from app.api.deps import (
    AuthContext,
    load_mission_membership,
    require_auth,
    require_mission_roles,
)
from app.core.config import settings
from app.core.security import enforce_rate_limit
from app.schemas.mission_collab import (
    SosActionRequest,
    SosEventResponse,
    TriggerSosRequest,
    VoiceNoteResponse,
)
from app.services.container import sos_service

router = APIRouter(prefix="/missions", tags=["Emergency SOS & Voice Notes"])


@router.post("/{mission_id}/sos", response_model=SosEventResponse, status_code=status.HTTP_201_CREATED)
def trigger_emergency_sos(
    mission_id: str,
    payload: TriggerSosRequest,
    auth: AuthContext = Depends(require_auth),
) -> SosEventResponse:
    load_mission_membership(mission_id, auth)
    enforce_rate_limit(
        f"sos:{mission_id}:{auth.astronaut_id}",
        max_attempts=settings.SOS_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.SOS_RATE_LIMIT_WINDOW_SECONDS,
    )
    return sos_service.trigger_sos(mission_id, auth.astronaut_id, payload)


@router.get("/{mission_id}/sos", response_model=List[SosEventResponse])
def list_mission_sos_events(
    mission_id: str,
    include_closed: bool = Query(default=True),
    auth: AuthContext = Depends(require_auth),
) -> List[SosEventResponse]:
    load_mission_membership(mission_id, auth)
    return sos_service.list_sos_events(
        mission_id,
        requester_id=auth.astronaut_id,
        include_closed=include_closed,
    )


@router.post("/{mission_id}/sos/{sos_id}/delivered", response_model=SosEventResponse)
def mark_sos_delivered_to_device(
    mission_id: str,
    sos_id: str,
    payload: SosActionRequest = SosActionRequest(),
    auth: AuthContext = Depends(require_auth),
) -> SosEventResponse:
    load_mission_membership(mission_id, auth)
    return sos_service.record_sos_action(
        mission_id=mission_id,
        sos_id=sos_id,
        actor_id=auth.astronaut_id,
        ack_type="DELIVERED_TO_CREW_DEVICE",
        note=payload.note,
    )


@router.post("/{mission_id}/sos/{sos_id}/acknowledge", response_model=SosEventResponse)
def acknowledge_sos(
    mission_id: str,
    sos_id: str,
    payload: SosActionRequest = SosActionRequest(),
    auth: AuthContext = Depends(require_auth),
) -> SosEventResponse:
    load_mission_membership(mission_id, auth)
    return sos_service.record_sos_action(
        mission_id=mission_id,
        sos_id=sos_id,
        actor_id=auth.astronaut_id,
        ack_type="ACKNOWLEDGED_BY_CREW",
        note=payload.note,
    )


@router.post("/{mission_id}/sos/{sos_id}/resolve", response_model=SosEventResponse)
def resolve_sos(
    mission_id: str,
    sos_id: str,
    payload: SosActionRequest = SosActionRequest(),
    auth: AuthContext = Depends(require_auth),
) -> SosEventResponse:
    require_mission_roles(mission_id, auth, {"MISSION_LEAD", "MISSION_OPERATOR"})
    return sos_service.record_sos_action(
        mission_id=mission_id,
        sos_id=sos_id,
        actor_id=auth.astronaut_id,
        ack_type="RESOLVED",
        note=payload.note,
    )


@router.post("/{mission_id}/sos/{sos_id}/cancel", response_model=SosEventResponse)
def cancel_sos(
    mission_id: str,
    sos_id: str,
    payload: SosActionRequest = SosActionRequest(),
    auth: AuthContext = Depends(require_auth),
) -> SosEventResponse:
    load_mission_membership(mission_id, auth)
    return sos_service.record_sos_action(
        mission_id=mission_id,
        sos_id=sos_id,
        actor_id=auth.astronaut_id,
        ack_type="CANCELLED",
        note=payload.note or "Cancelled with audit retention.",
    )


# ---------------------------------------------------------------------------
# Voice Note Private Upload & Authorized Playback
# ---------------------------------------------------------------------------


@router.post("/{mission_id}/voice-notes", response_model=VoiceNoteResponse, status_code=status.HTTP_201_CREATED)
async def upload_voice_note(
    mission_id: str,
    request: Request,
    duration_seconds: Optional[float] = Query(default=None, ge=0.0, le=3600.0),
    linked_event_type: Optional[str] = Query(default=None, max_length=64),
    linked_event_id: Optional[str] = Query(default=None, max_length=128),
    auth: AuthContext = Depends(require_auth),
) -> VoiceNoteResponse:
    load_mission_membership(mission_id, auth)
    raw_bytes = await request.body()
    mime_type = request.headers.get("content-type", "audio/webm")
    return sos_service.store_voice_note(
        mission_id=mission_id,
        astronaut_id=auth.astronaut_id,
        raw_bytes=raw_bytes,
        mime_type=mime_type,
        duration_seconds=duration_seconds,
        linked_event_type=linked_event_type,
        linked_event_id=linked_event_id,
    )


@router.get("/{mission_id}/voice-notes/{voice_note_id}")
def stream_voice_note(
    mission_id: str,
    voice_note_id: str,
    token: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(require_auth),
):
    load_mission_membership(mission_id, auth)
    file_path, mime_type = sos_service.resolve_voice_note_file(
        mission_id=mission_id,
        voice_note_id=voice_note_id,
        requester_id=auth.astronaut_id,
        signed_token=token,
    )
    return FileResponse(path=str(file_path), media_type=mime_type, filename=file_path.name)
