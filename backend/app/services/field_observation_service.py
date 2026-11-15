"""
Crew-Scoped Field Observation Service.
Enforces controlled geochemical/mineralogical species vocabulary (species.py),
strict epistemic discipline (USER_REPORTED / UNVERIFIED on creation; CORROBORATED_BY_EVIDENCE
only via authorized review with attached evidence_ids), optimistic concurrency (version),
and offline-sync deduplication via client_event_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.db.database import MissionDatabase
from app.geospatial.crs import CRSError, normalize_longitude_360, validate_mars_coordinates, validate_mars_crs
from app.schemas.mission_collab import (
    CreateFieldObservationRequest,
    FieldObservationResponse,
    MissionRole,
    ReviewFieldObservationRequest,
    UpdateFieldObservationRequest,
)
from app.science.composition.species import resolve_species_query
from app.services.mission_event_service import MissionEventService
from app.services.realtime_hub import MissionRealtimeHub
from app.services.sos_service import SosService


class FieldObservationService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        realtime_hub: MissionRealtimeHub,
        destination_service: Any,
    ) -> None:
        self._db = db
        self._events = event_service
        self._hub = realtime_hub
        self._destination_service = destination_service

    @staticmethod
    def _resolve_species_optional(species_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if species_name is None or not species_name.strip():
            return None, None
        res = resolve_species_query(species_name.strip())
        if not res.resolved or res.species is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=res.explanation,
            )
        return res.species.canonical_id, res.species.canonical_name

    def create_observation(
        self,
        mission_id: str,
        astronaut_id: str,
        req: CreateFieldObservationRequest,
    ) -> FieldObservationResponse:
        species_id, species_display = self._resolve_species_optional(req.species_name)

        lat: Optional[float] = None
        lon_east: Optional[float] = None
        elev_m: Optional[float] = None
        if req.latitude is not None or req.longitude is not None:
            if req.latitude is None or req.longitude is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Both latitude and longitude are required when specifying coordinates.",
                )
            if not validate_mars_crs(req.crs):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Rejected invalid Mars CRS '{req.crs}'.",
                )
            try:
                lat_v, lon_v = validate_mars_coordinates(req.latitude, req.longitude, "Planetocentric", "East")
            except CRSError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
            lat = lat_v
            lon_east = normalize_longitude_360(lon_v)
            try:
                pt = self._destination_service.sample_processed_terrain_point(
                    latitude=lat,
                    longitude=lon_east,
                    crs=req.crs,
                    latitude_convention="Planetocentric",
                    longitude_direction="East",
                )
                if pt.available and pt.elevation_m is not None:
                    elev_m = float(pt.elevation_m)
            except Exception:
                elev_m = None

        now_iso = datetime.now(timezone.utc).isoformat()
        epistemic_state = "USER_REPORTED"
        audit_entry = {
            "at_utc": now_iso,
            "actor_id": astronaut_id,
            "action": "CREATED",
            "epistemic_state": epistemic_state,
            "note": "Initial crew report recorded.",
        }

        with self._db.transaction() as conn:
            if req.client_event_id:
                existing = conn.execute(
                    "SELECT * FROM field_observations WHERE mission_id = ? AND client_event_id = ?",
                    (mission_id, req.client_event_id),
                ).fetchone()
                if existing is not None:
                    return self._hydrate(conn, existing, requester_id=astronaut_id)

            obs_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO field_observations (
                    observation_id, mission_id, astronaut_id, client_event_id, version,
                    latitude, longitude_east, elevation_m, crs, coordinate_source, uncertainty_m,
                    target_id, category, species_canonical_id, species_display_name,
                    description, epistemic_state, instrument_id, source_product_id, calibration_metadata,
                    evidence_ids_json, voice_note_id, offline_created_at_utc, synced_at_utc,
                    reviewed_by, review_note, annotations_json, audit_history_json,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'IAU2000:49900', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, '[]', ?, ?, ?)
                """,
                (
                    obs_id,
                    mission_id,
                    astronaut_id,
                    req.client_event_id,
                    lat,
                    lon_east,
                    elev_m,
                    req.coordinate_source,
                    req.uncertainty_m,
                    req.target_id.strip() if req.target_id else None,
                    req.category,
                    species_id,
                    species_display,
                    req.description.strip(),
                    epistemic_state,
                    req.instrument_id.strip() if req.instrument_id else None,
                    req.source_product_id.strip() if req.source_product_id else None,
                    req.calibration_metadata.strip() if req.calibration_metadata else None,
                    json.dumps(req.evidence_ids),
                    req.voice_note_id,
                    req.offline_created_at_utc,
                    now_iso,
                    json.dumps([audit_entry]),
                    req.offline_created_at_utc or now_iso,
                    now_iso,
                ),
            )
            if req.voice_note_id:
                conn.execute(
                    "UPDATE voice_notes SET linked_event_type = 'OBSERVATION', linked_event_id = ? WHERE voice_note_id = ?",
                    (obs_id, req.voice_note_id),
                )
            row = conn.execute("SELECT * FROM field_observations WHERE observation_id = ?", (obs_id,)).fetchone()
            resp = self._hydrate(conn, row, requester_id=astronaut_id)
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="FIELD_OBSERVATION_CREATED",
                payload=resp.model_dump(),
                client_timestamp_utc=req.offline_created_at_utc,
                client_event_id=req.client_event_id,
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="FIELD_OBSERVATION_CREATED",
            payload=resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return resp

    def update_observation(
        self,
        mission_id: str,
        observation_id: str,
        actor_id: str,
        actor_role: MissionRole,
        req: UpdateFieldObservationRequest,
    ) -> FieldObservationResponse:
        species_id: Optional[str] = None
        species_display: Optional[str] = None
        if req.species_name is not None:
            species_id, species_display = self._resolve_species_optional(req.species_name)

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM field_observations WHERE observation_id = ? AND mission_id = ?",
                (observation_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field observation not found.")
            if row["astronaut_id"] != actor_id and actor_role not in {"MISSION_LEAD", "MISSION_OPERATOR"}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the author or mission lead/operator can edit this observation.",
                )
            if int(row["version"]) != req.expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Optimistic concurrency conflict: expected version {req.expected_version}, current version is {row['version']}.",
                )

            annotations: List[Dict[str, Any]] = json.loads(row["annotations_json"] or "[]")
            if req.annotation_note:
                annotations.append(
                    {"at_utc": now_iso, "author_id": actor_id, "note": req.annotation_note.strip()}
                )
            audit: List[Dict[str, Any]] = json.loads(row["audit_history_json"] or "[]")
            audit.append({"at_utc": now_iso, "actor_id": actor_id, "action": "UPDATED", "version": int(row["version"]) + 1})

            new_desc = req.description.strip() if req.description is not None else row["description"]
            new_target = req.target_id.strip() if req.target_id is not None else row["target_id"]
            new_sp_id = species_id if req.species_name is not None else row["species_canonical_id"]
            new_sp_disp = species_display if req.species_name is not None else row["species_display_name"]

            conn.execute(
                """
                UPDATE field_observations
                SET version = version + 1,
                    description = ?,
                    target_id = ?,
                    species_canonical_id = ?,
                    species_display_name = ?,
                    annotations_json = ?,
                    audit_history_json = ?,
                    updated_at_utc = ?
                WHERE observation_id = ? AND version = ?
                """,
                (
                    new_desc,
                    new_target,
                    new_sp_id,
                    new_sp_disp,
                    json.dumps(annotations),
                    json.dumps(audit),
                    now_iso,
                    observation_id,
                    req.expected_version,
                ),
            )
            fresh = conn.execute("SELECT * FROM field_observations WHERE observation_id = ?", (observation_id,)).fetchone()
            resp = self._hydrate(conn, fresh, requester_id=actor_id)
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="FIELD_OBSERVATION_UPDATED",
                payload=resp.model_dump(),
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="FIELD_OBSERVATION_UPDATED",
            payload=resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return resp

    def review_observation(
        self,
        mission_id: str,
        observation_id: str,
        reviewer_id: str,
        req: ReviewFieldObservationRequest,
    ) -> FieldObservationResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM field_observations WHERE observation_id = ? AND mission_id = ?",
                (observation_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field observation not found.")
            if int(row["version"]) != req.expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Optimistic concurrency conflict: expected version {req.expected_version}, current version is {row['version']}.",
                )

            merged_evidence = sorted(set(json.loads(row["evidence_ids_json"] or "[]") + req.evidence_ids))
            if req.epistemic_state == "CORROBORATED_BY_EVIDENCE" and not merged_evidence and not row["source_product_id"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="CORROBORATED_BY_EVIDENCE requires attached evidence_ids or a calibrated source_product_id.",
                )

            audit: List[Dict[str, Any]] = json.loads(row["audit_history_json"] or "[]")
            audit.append(
                {
                    "at_utc": now_iso,
                    "actor_id": reviewer_id,
                    "action": "REVIEWED",
                    "epistemic_state": req.epistemic_state,
                    "review_note": req.review_note,
                }
            )
            conn.execute(
                """
                UPDATE field_observations
                SET version = version + 1,
                    epistemic_state = ?,
                    reviewed_by = ?,
                    review_note = ?,
                    evidence_ids_json = ?,
                    audit_history_json = ?,
                    updated_at_utc = ?
                WHERE observation_id = ? AND version = ?
                """,
                (
                    req.epistemic_state,
                    reviewer_id,
                    req.review_note,
                    json.dumps(merged_evidence),
                    json.dumps(audit),
                    now_iso,
                    observation_id,
                    req.expected_version,
                ),
            )
            fresh = conn.execute("SELECT * FROM field_observations WHERE observation_id = ?", (observation_id,)).fetchone()
            resp = self._hydrate(conn, fresh, requester_id=reviewer_id)
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=reviewer_id,
                event_type="FIELD_OBSERVATION_REVIEWED",
                payload=resp.model_dump(),
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="FIELD_OBSERVATION_REVIEWED",
            payload=resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return resp

    def list_observations(
        self,
        mission_id: str,
        *,
        requester_id: str,
        category: Optional[str] = None,
        species: Optional[str] = None,
        epistemic_state: Optional[str] = None,
        astronaut_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FieldObservationResponse]:
        clauses = ["mission_id = ?"]
        params: List[Any] = [mission_id]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if species:
            clauses.append("LOWER(species_canonical_id) = ?")
            params.append(species.strip().lower())
        if epistemic_state:
            clauses.append("epistemic_state = ?")
            params.append(epistemic_state)
        if astronaut_id:
            clauses.append("astronaut_id = ?")
            params.append(astronaut_id)

        sql = f"""
            SELECT * FROM field_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at_utc DESC
            LIMIT ?
        """
        params.append(max(1, min(limit, 500)))
        with self._db.read() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [self._hydrate(conn, r, requester_id=requester_id) for r in rows]

    def _hydrate(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        requester_id: str,
    ) -> FieldObservationResponse:
        astro = conn.execute(
            "SELECT display_name FROM astronauts WHERE astronaut_id = ?",
            (row["astronaut_id"],),
        ).fetchone()
        voice_note = None
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
                voice_note = SosService.row_to_voice_note(vn_row, requester_id=requester_id)

        return FieldObservationResponse(
            observation_id=row["observation_id"],
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            astronaut_display_name=astro["display_name"] if astro else row["astronaut_id"],
            client_event_id=row["client_event_id"],
            version=int(row["version"]),
            latitude=row["latitude"],
            longitude_east=row["longitude_east"],
            elevation_m=row["elevation_m"],
            crs=row["crs"],
            coordinate_source=row["coordinate_source"],
            uncertainty_m=row["uncertainty_m"],
            target_id=row["target_id"],
            category=row["category"],
            species_canonical_id=row["species_canonical_id"],
            species_display_name=row["species_display_name"],
            description=row["description"],
            epistemic_state=row["epistemic_state"],
            instrument_id=row["instrument_id"],
            source_product_id=row["source_product_id"],
            calibration_metadata=row["calibration_metadata"],
            evidence_ids=json.loads(row["evidence_ids_json"] or "[]"),
            voice_note=voice_note,
            offline_created_at_utc=row["offline_created_at_utc"],
            synced_at_utc=row["synced_at_utc"],
            reviewed_by=row["reviewed_by"],
            review_note=row["review_note"],
            annotations=json.loads(row["annotations_json"] or "[]"),
            audit_history=json.loads(row["audit_history_json"] or "[]"),
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )
