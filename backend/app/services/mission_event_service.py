"""
Append-Only Mission Event Timeline Service.
Records immutable mission_events inside active ACID DB transactions with strict monotonic
per-mission event_seq and idempotent client_event_id deduplication.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from app.db.database import MissionDatabase
from app.schemas.mission_collab import MissionEventResponse


class MissionEventService:
    def __init__(self, db: MissionDatabase) -> None:
        self._db = db

    def record_event_tx(
        self,
        conn: sqlite3.Connection,
        *,
        mission_id: str,
        actor_id: str,
        event_type: str,
        payload: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        client_timestamp_utc: Optional[str] = None,
        client_event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> MissionEventResponse:
        if client_event_id:
            existing = conn.execute(
                """
                SELECT * FROM mission_events
                WHERE mission_id = ? AND event_type = ? AND client_event_id = ?
                """,
                (mission_id, event_type, client_event_id),
            ).fetchone()
            if existing is not None:
                return self._row_to_response(existing)

        seq_row = conn.execute(
            "SELECT COALESCE(MAX(event_seq), 0) AS max_seq FROM mission_events WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        next_seq = int(seq_row["max_seq"]) + 1 if seq_row else 1

        event_id = str(uuid.uuid4())
        server_ts = datetime.now(timezone.utc).isoformat()
        corr = correlation_id or event_id

        conn.execute(
            """
            INSERT INTO mission_events (
                event_id, mission_id, actor_id, event_type,
                client_timestamp_utc, server_timestamp_utc, payload_schema_version,
                event_seq, correlation_id, client_event_id,
                provenance_json, auth_context_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, '1.0', ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                mission_id,
                actor_id,
                event_type,
                client_timestamp_utc,
                server_ts,
                next_seq,
                corr,
                client_event_id,
                json.dumps(provenance or {}),
                json.dumps(auth_context or {}),
                json.dumps(payload),
            ),
        )
        return MissionEventResponse(
            event_id=event_id,
            mission_id=mission_id,
            actor_id=actor_id,
            event_type=event_type,
            client_timestamp_utc=client_timestamp_utc,
            server_timestamp_utc=server_ts,
            payload_schema_version="1.0",
            event_seq=next_seq,
            correlation_id=corr,
            client_event_id=client_event_id,
            provenance=provenance or {},
            auth_context=auth_context or {},
            payload=payload,
        )

    def list_events(
        self,
        mission_id: str,
        *,
        event_type: Optional[str] = None,
        limit: int = 100,
        before_seq: Optional[int] = None,
    ) -> List[MissionEventResponse]:
        clauses = ["mission_id = ?"]
        params: List[Any] = [mission_id]
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if before_seq is not None:
            clauses.append("event_seq < ?")
            params.append(int(before_seq))

        sql = f"""
            SELECT * FROM mission_events
            WHERE {' AND '.join(clauses)}
            ORDER BY event_seq DESC
            LIMIT ?
        """
        params.append(max(1, min(limit, 500)))
        with self._db.read() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_response(r) for r in rows]

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> MissionEventResponse:
        return MissionEventResponse(
            event_id=row["event_id"],
            mission_id=row["mission_id"],
            actor_id=row["actor_id"],
            event_type=row["event_type"],
            client_timestamp_utc=row["client_timestamp_utc"],
            server_timestamp_utc=row["server_timestamp_utc"],
            payload_schema_version=row["payload_schema_version"],
            event_seq=int(row["event_seq"]),
            correlation_id=row["correlation_id"],
            client_event_id=row["client_event_id"],
            provenance=json.loads(row["provenance_json"] or "{}"),
            auth_context=json.loads(row["auth_context_json"] or "{}"),
            payload=json.loads(row["payload_json"] or "{}"),
        )
