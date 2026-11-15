"""
Emergency SOS Dispatch, Private Voice Note Storage & Crew Acknowledgement Lifecycle Service.
Separates server receipt, crew device delivery, crew acknowledgement, resolution, and audit-only cancellation.
Stores audio attachments strictly outside public webroot with MIME allowlist, size limit, SHA-256 checksum,
and short-lived HMAC-signed playback authorization.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import create_signed_attachment_token, verify_signed_attachment_token
from app.db.database import MissionDatabase
from app.geospatial.crs import CRSError, normalize_longitude_360, validate_mars_coordinates, validate_mars_crs
from app.schemas.mission_collab import (
    SosAcknowledgementResponse,
    SosEventResponse,
    TriggerSosRequest,
    VoiceNoteResponse,
)
from app.services.mission_event_service import MissionEventService
from app.services.position_service import CrewPositionService
from app.services.realtime_hub import MissionRealtimeHub


ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/ogg": ".ogg",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}


class SosService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        realtime_hub: MissionRealtimeHub,
        position_service: CrewPositionService,
        private_attachments_dir: Path,
    ) -> None:
        self._db = db
        self._events = event_service
        self._hub = realtime_hub
        self._positions = position_service
        self._attachments_dir = private_attachments_dir
        self._attachments_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Voice Note Private Storage & Signed Retrieval
    # ------------------------------------------------------------------

    def store_voice_note(
        self,
        *,
        mission_id: str,
        astronaut_id: str,
        raw_bytes: bytes,
        mime_type: str,
        duration_seconds: Optional[float] = None,
        linked_event_type: Optional[str] = None,
        linked_event_id: Optional[str] = None,
    ) -> VoiceNoteResponse:
        clean_mime = (mime_type or "").split(",")[0].strip().lower()
        base_mime = clean_mime.split(";")[0].strip()
        ext = ALLOWED_AUDIO_MIME_TYPES.get(clean_mime) or ALLOWED_AUDIO_MIME_TYPES.get(base_mime)
        if not ext:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported audio MIME type '{mime_type}'. Allowed: webm, ogg, wav, mp4, mpeg.",
            )
        if len(raw_bytes) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voice note audio payload is empty.")
        if len(raw_bytes) > settings.AUDIO_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Voice note exceeds maximum allowed size ({settings.AUDIO_UPLOAD_MAX_BYTES} bytes).",
            )

        voice_note_id = str(uuid.uuid4())
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        now_iso = datetime.now(timezone.utc).isoformat()
        rel_path = f"{mission_id}/{voice_note_id}{ext}"
        dest = (self._attachments_dir / rel_path).resolve()
        # Path traversal guard
        if self._attachments_dir.resolve() not in dest.parents:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment storage path.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw_bytes)

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO voice_notes (
                    voice_note_id, mission_id, astronaut_id, linked_event_type, linked_event_id,
                    mime_type, file_size_bytes, duration_seconds, sha256_checksum,
                    storage_rel_path, upload_status, created_at_utc, deleted_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UPLOADED', ?, NULL)
                """,
                (
                    voice_note_id,
                    mission_id,
                    astronaut_id,
                    linked_event_type,
                    linked_event_id,
                    base_mime,
                    len(raw_bytes),
                    duration_seconds,
                    checksum,
                    rel_path,
                    now_iso,
                ),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="VOICE_NOTE_UPLOADED",
                payload={
                    "voice_note_id": voice_note_id,
                    "file_size_bytes": len(raw_bytes),
                    "mime_type": base_mime,
                    "sha256_checksum": checksum,
                },
            )
            row = conn.execute(
                """
                SELECT vn.*, a.display_name FROM voice_notes vn
                JOIN astronauts a ON a.astronaut_id = vn.astronaut_id
                WHERE vn.voice_note_id = ?
                """,
                (voice_note_id,),
            ).fetchone()

        self._hub.publish_mission_event(
            mission_id,
            event_type="VOICE_NOTE_UPLOADED",
            payload={"voice_note_id": voice_note_id, "astronaut_id": astronaut_id},
            event_seq=ev.event_seq,
        )
        return self.row_to_voice_note(row, requester_id=astronaut_id)

    def resolve_voice_note_file(
        self,
        *,
        mission_id: str,
        voice_note_id: str,
        requester_id: str,
        signed_token: Optional[str] = None,
    ) -> Tuple[Path, str]:
        with self._db.read() as conn:
            row = conn.execute(
                """
                SELECT * FROM voice_notes
                WHERE voice_note_id = ? AND mission_id = ? AND deleted_at_utc IS NULL
                """,
                (voice_note_id, mission_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note not found.")

        if signed_token is not None:
            ok = verify_signed_attachment_token(
                signed_token,
                voice_note_id=voice_note_id,
                mission_id=mission_id,
                astronaut_id=requester_id,
            )
            if not ok:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Expired or invalid voice-note access token.")

        full_path = (self._attachments_dir / row["storage_rel_path"]).resolve()
        if self._attachments_dir.resolve() not in full_path.parents or not full_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note media file is missing.")
        return full_path, row["mime_type"]

    # ------------------------------------------------------------------
    # SOS Activation & Lifecycle
    # ------------------------------------------------------------------

    def trigger_sos(
        self,
        mission_id: str,
        astronaut_id: str,
        req: TriggerSosRequest,
    ) -> SosEventResponse:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._db.transaction() as conn:
            if req.client_event_id:
                existing = conn.execute(
                    "SELECT * FROM sos_events WHERE mission_id = ? AND client_event_id = ?",
                    (mission_id, req.client_event_id),
                ).fetchone()
                if existing is not None:
                    return self._hydrate_sos(conn, existing, requester_id=astronaut_id)

            # Resolve best position snapshot without fabricating coordinates
            lat: Optional[float] = None
            lon_east: Optional[float] = None
            elev: Optional[float] = None
            crs: Optional[str] = None
            pos_src: Optional[str] = None
            pos_cls: Optional[str] = None
            pos_age_s: Optional[float] = None
            pos_status = "POSITION_UNAVAILABLE"

            if req.explicit_latitude is not None and req.explicit_longitude is not None:
                if not validate_mars_crs(req.explicit_crs):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Rejected invalid Mars CRS '{req.explicit_crs}'.",
                    )
                try:
                    lat_v, lon_v = validate_mars_coordinates(req.explicit_latitude, req.explicit_longitude, "Planetocentric", "East")
                except CRSError as exc:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
                lat = lat_v
                lon_east = normalize_longitude_360(lon_v)
                crs = "IAU2000:49900"
                pos_src = "sos_explicit_input"
                pos_cls = "USER_PROVIDED"
                pos_age_s = 0.0
                pos_status = "EXPLICIT_SOS_COORDINATES"
            else:
                latest_pos = self._positions.get_latest_position(mission_id, astronaut_id, conn=conn)
                if latest_pos is not None:
                    lat = latest_pos.latitude
                    lon_east = latest_pos.longitude_east
                    elev = latest_pos.elevation_m
                    crs = latest_pos.crs
                    pos_src = latest_pos.source_id
                    pos_cls = latest_pos.source_classification
                    pos_age_s = latest_pos.age_seconds
                    pos_status = "STALE_LAST_KNOWN_POSITION" if latest_pos.is_stale else "VALIDATED_RECENT_POSITION"

            if req.voice_note_id:
                vn = conn.execute(
                    "SELECT voice_note_id FROM voice_notes WHERE voice_note_id = ? AND mission_id = ?",
                    (req.voice_note_id, mission_id),
                ).fetchone()
                if vn is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referenced SOS voice note not found in mission.")

            sos_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO sos_events (
                    sos_id, mission_id, astronaut_id, event_type, status, client_event_id,
                    latitude, longitude_east, elevation_m, crs,
                    position_source, position_classification, position_age_s, position_status,
                    message, voice_note_id, created_at_utc, server_received_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, 'SOS_ACTIVATED', 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sos_id,
                    mission_id,
                    astronaut_id,
                    req.client_event_id,
                    lat,
                    lon_east,
                    elev,
                    crs,
                    pos_src,
                    pos_cls,
                    pos_age_s,
                    pos_status,
                    req.message.strip() if req.message else None,
                    req.voice_note_id,
                    req.client_timestamp_utc or now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            if req.voice_note_id:
                conn.execute(
                    "UPDATE voice_notes SET linked_event_type = 'SOS', linked_event_id = ? WHERE voice_note_id = ?",
                    (sos_id, req.voice_note_id),
                )

            row = conn.execute("SELECT * FROM sos_events WHERE sos_id = ?", (sos_id,)).fetchone()
            sos_resp = self._hydrate_sos(conn, row, requester_id=astronaut_id)
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="SOS_ACTIVATED",
                payload=sos_resp.model_dump(),
                client_timestamp_utc=req.client_timestamp_utc,
                client_event_id=req.client_event_id,
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="SOS_ACTIVATED",
            payload=sos_resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return sos_resp

    def record_sos_action(
        self,
        *,
        mission_id: str,
        sos_id: str,
        actor_id: str,
        ack_type: str,
        note: Optional[str] = None,
    ) -> SosEventResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM sos_events WHERE sos_id = ? AND mission_id = ?",
                (sos_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SOS event not found.")

            conn.execute(
                """
                INSERT OR IGNORE INTO sos_acknowledgements (
                    ack_id, sos_id, astronaut_id, ack_type, note, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), sos_id, actor_id, ack_type, note, now_iso),
            )

            next_status = row["status"]
            if ack_type == "DELIVERED_TO_CREW_DEVICE" and row["status"] == "ACTIVE":
                next_status = "DELIVERED_TO_CREW_DEVICE"
            elif ack_type == "ACKNOWLEDGED_BY_CREW" and row["status"] in {"ACTIVE", "DELIVERED_TO_CREW_DEVICE"}:
                next_status = "ACKNOWLEDGED_BY_CREW"
            elif ack_type == "RESOLVED":
                next_status = "RESOLVED"
            elif ack_type == "CANCELLED":
                next_status = "CANCELLED"

            conn.execute(
                "UPDATE sos_events SET status = ?, updated_at_utc = ? WHERE sos_id = ?",
                (next_status, now_iso, sos_id),
            )
            fresh = conn.execute("SELECT * FROM sos_events WHERE sos_id = ?", (sos_id,)).fetchone()
            sos_resp = self._hydrate_sos(conn, fresh, requester_id=actor_id)
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type=f"SOS_{ack_type}",
                payload=sos_resp.model_dump(),
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type=f"SOS_{ack_type}",
            payload=sos_resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return sos_resp

    def list_sos_events(
        self,
        mission_id: str,
        *,
        requester_id: str,
        include_closed: bool = True,
    ) -> List[SosEventResponse]:
        with self._db.read() as conn:
            if include_closed:
                rows = conn.execute(
                    "SELECT * FROM sos_events WHERE mission_id = ? ORDER BY server_received_at_utc DESC LIMIT 100",
                    (mission_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM sos_events
                    WHERE mission_id = ? AND status NOT IN ('RESOLVED', 'CANCELLED')
                    ORDER BY server_received_at_utc DESC
                    """,
                    (mission_id,),
                ).fetchall()
            return [self._hydrate_sos(conn, r, requester_id=requester_id) for r in rows]

    def _hydrate_sos(self, conn: sqlite3.Connection, row: sqlite3.Row, *, requester_id: str) -> SosEventResponse:
        astro = conn.execute(
            "SELECT display_name FROM astronauts WHERE astronaut_id = ?",
            (row["astronaut_id"],),
        ).fetchone()
        acks = conn.execute(
            """
            SELECT sa.*, a.display_name
            FROM sos_acknowledgements sa
            JOIN astronauts a ON a.astronaut_id = sa.astronaut_id
            WHERE sa.sos_id = ?
            ORDER BY sa.created_at_utc ASC
            """,
            (row["sos_id"],),
        ).fetchall()
        voice_note: Optional[VoiceNoteResponse] = None
        if row["voice_note_id"]:
            vn_row = conn.execute(
                """
                SELECT vn.*, a.display_name FROM voice_notes vn
                JOIN astronauts a ON a.astronaut_id = vn.astronaut_id
                WHERE vn.voice_note_id = ? AND vn.deleted_at_utc IS NULL
                """,
                (row["voice_note_id"],),
            ).fetchone()
            if vn_row is not None:
                voice_note = self.row_to_voice_note(vn_row, requester_id=requester_id)

        return SosEventResponse(
            sos_id=row["sos_id"],
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            astronaut_display_name=astro["display_name"] if astro else row["astronaut_id"],
            event_type=row["event_type"],
            status=row["status"],
            client_event_id=row["client_event_id"],
            latitude=row["latitude"],
            longitude_east=row["longitude_east"],
            elevation_m=row["elevation_m"],
            crs=row["crs"],
            position_source=row["position_source"],
            position_classification=row["position_classification"],
            position_age_s=row["position_age_s"],
            position_status=row["position_status"],
            message=row["message"],
            voice_note=voice_note,
            acknowledgements=[
                SosAcknowledgementResponse(
                    ack_id=a["ack_id"],
                    sos_id=a["sos_id"],
                    astronaut_id=a["astronaut_id"],
                    display_name=a["display_name"],
                    ack_type=a["ack_type"],
                    note=a["note"],
                    created_at_utc=a["created_at_utc"],
                )
                for a in acks
            ],
            created_at_utc=row["created_at_utc"],
            server_received_at_utc=row["server_received_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )

    @staticmethod
    def row_to_voice_note(row: sqlite3.Row, *, requester_id: str) -> VoiceNoteResponse:
        sig = create_signed_attachment_token(
            row["voice_note_id"],
            row["mission_id"],
            requester_id,
            ttl_seconds=900,
        )
        return VoiceNoteResponse(
            voice_note_id=row["voice_note_id"],
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            display_name=row["display_name"] if "display_name" in row.keys() else None,
            linked_event_type=row["linked_event_type"],
            linked_event_id=row["linked_event_id"],
            mime_type=row["mime_type"],
            file_size_bytes=int(row["file_size_bytes"]),
            duration_seconds=float(row["duration_seconds"]) if row["duration_seconds"] is not None else None,
            sha256_checksum=row["sha256_checksum"],
            upload_status=row["upload_status"],
            playback_url=f"/api/missions/{row['mission_id']}/voice-notes/{row['voice_note_id']}?token={sig}",
            created_at_utc=row["created_at_utc"],
        )
