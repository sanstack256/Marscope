"""
Mission-Scoped Crew Position Validation, DEM Elevation Sampling & Freshness Service.
Enforces IAU2000:49900 Martian coordinates, rejects Earth/browser geolocation providers,
samples elevation strictly from validated processed DEMs when covered (never 0.0 fallback),
enforces monotonic timestamp/sequence per astronaut+mission, and publishes SSE updates.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.db.database import MissionDatabase
from app.geospatial.crs import (
    CRSError,
    normalize_longitude_360,
    validate_mars_coordinates,
    validate_mars_crs,
)
from app.schemas.mission_collab import (
    CrewConnectionStatus,
    CrewPositionResponse,
    IngestPositionRequest,
)
from app.services.mission_event_service import MissionEventService
from app.services.realtime_hub import MissionRealtimeHub
from app.services.tracking_service import REJECTED_BROWSER_PROVIDERS


class CrewPositionService:
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

    def ingest_position(
        self,
        mission_id: str,
        astronaut_id: str,
        req: IngestPositionRequest,
    ) -> CrewPositionResponse:
        src_norm = req.source_id.strip().lower()
        if any(tok in src_norm for tok in REJECTED_BROWSER_PROVIDERS):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Source '{req.source_id}' represents Earth/browser geolocation which is invalid for Mars operations."
                ),
            )

        if not validate_mars_crs(req.crs):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Rejected unsupported or Earth CRS '{req.crs}'. Use IAU2000:49900.",
            )

        lat_conv = "Planetocentric" if req.latitude_convention == "planetocentric" else "Planetographic"
        try:
            lat, lon_raw = validate_mars_coordinates(req.latitude, req.longitude, lat_conv, "East")
        except CRSError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        lon_east = normalize_longitude_360(lon_raw)

        now = datetime.now(timezone.utc)
        received_iso = now.isoformat()
        if req.measured_at_utc:
            try:
                measured_dt = datetime.fromisoformat(req.measured_at_utc.replace("Z", "+00:00"))
                if measured_dt.tzinfo is None:
                    measured_dt = measured_dt.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid ISO-8601 measured_at_utc timestamp.",
                ) from exc
            measured_iso = measured_dt.astimezone(timezone.utc).isoformat()
        else:
            measured_dt = now
            measured_iso = received_iso

        # Sample real DEM elevation if covered; never fabricate 0.0 when outside DEM
        elevation_m: Optional[float] = None
        elevation_source: Optional[str] = None
        try:
            terrain_pt = self._destination_service.sample_processed_terrain_point(
                latitude=lat,
                longitude=lon_east,
                crs=req.crs,
                latitude_convention=lat_conv,
                longitude_direction="East",
            )
            if terrain_pt.available and terrain_pt.elevation_m is not None:
                elevation_m = float(terrain_pt.elevation_m)
                elevation_source = terrain_pt.source_dataset_id or terrain_pt.source_product_id
        except Exception:
            elevation_m = None

        position_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            mem = conn.execute(
                """
                SELECT location_sharing_enabled, status FROM mission_memberships
                WHERE mission_id = ? AND astronaut_id = ?
                """,
                (mission_id, astronaut_id),
            ).fetchone()
            if mem is None or mem["status"] != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an active mission member.")
            if not bool(mem["location_sharing_enabled"]):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Location sharing is currently disabled for your membership in this mission.",
                )

            latest = conn.execute(
                """
                SELECT measured_at_utc, sequence_number
                FROM crew_positions
                WHERE mission_id = ? AND astronaut_id = ?
                ORDER BY received_at_utc DESC, sequence_number DESC
                LIMIT 1
                """,
                (mission_id, astronaut_id),
            ).fetchone()
            if latest is not None:
                prev_measured = datetime.fromisoformat(latest["measured_at_utc"])
                if measured_dt < prev_measured:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Rejected out-of-order stale measurement ({measured_iso} < latest {latest['measured_at_utc']})."
                        ),
                    )
                if measured_dt == prev_measured and req.sequence_number < int(latest["sequence_number"]):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Rejected out-of-order position sequence number.",
                    )

            conn.execute(
                """
                INSERT INTO crew_positions (
                    position_id, mission_id, astronaut_id, latitude, longitude_east,
                    crs, latitude_convention, longitude_direction, elevation_m,
                    uncertainty_m, source_id, source_classification, sequence_number,
                    measured_at_utc, received_at_utc, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VALIDATED')
                """,
                (
                    position_id,
                    mission_id,
                    astronaut_id,
                    lat,
                    lon_east,
                    "IAU2000:49900",
                    req.latitude_convention,
                    req.longitude_direction,
                    elevation_m,
                    req.uncertainty_m,
                    req.source_id.strip(),
                    req.source_classification,
                    req.sequence_number,
                    measured_iso,
                    received_iso,
                ),
            )

            astro_row = conn.execute(
                "SELECT display_name FROM astronauts WHERE astronaut_id = ?",
                (astronaut_id,),
            ).fetchone()
            display_name = astro_row["display_name"] if astro_row else None

            pos_resp = CrewPositionResponse(
                position_id=position_id,
                mission_id=mission_id,
                astronaut_id=astronaut_id,
                display_name=display_name,
                latitude=lat,
                longitude_east=lon_east,
                crs="IAU2000:49900",
                latitude_convention=req.latitude_convention,
                longitude_direction=req.longitude_direction,
                elevation_m=elevation_m,
                elevation_source=elevation_source,
                uncertainty_m=req.uncertainty_m,
                source_id=req.source_id.strip(),
                source_classification=req.source_classification,
                sequence_number=req.sequence_number,
                measured_at_utc=measured_iso,
                received_at_utc=received_iso,
                age_seconds=max(0.0, (now - measured_dt).total_seconds()),
                is_stale=((now - measured_dt).total_seconds() > settings.POSITION_STALE_AFTER_SECONDS),
                validation_status="VALIDATED",
            )

            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="CREW_POSITION_UPDATED",
                payload=pos_resp.model_dump(),
                provenance={
                    "source_id": req.source_id.strip(),
                    "source_classification": req.source_classification,
                    "elevation_source": elevation_source,
                },
                client_timestamp_utc=measured_iso,
                client_event_id=req.client_event_id,
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="CREW_POSITION_UPDATED",
            payload=pos_resp.model_dump(),
            event_seq=ev.event_seq,
        )
        return pos_resp

    def get_latest_position(
        self,
        mission_id: str,
        astronaut_id: str,
        *,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[CrewPositionResponse]:
        def _query(c: sqlite3.Connection) -> Optional[sqlite3.Row]:
            return c.execute(
                """
                SELECT cp.*, a.display_name
                FROM crew_positions cp
                JOIN astronauts a ON a.astronaut_id = cp.astronaut_id
                WHERE cp.mission_id = ? AND cp.astronaut_id = ?
                ORDER BY cp.received_at_utc DESC, cp.sequence_number DESC
                LIMIT 1
                """,
                (mission_id, astronaut_id),
            ).fetchone()

        if conn is not None:
            row = _query(conn)
        else:
            with self._db.read() as c:
                row = _query(c)

        if row is None:
            return None
        return self.row_to_position(row)

    def list_latest_positions(self, mission_id: str) -> List[CrewPositionResponse]:
        with self._db.read() as conn:
            members = conn.execute(
                """
                SELECT astronaut_id, location_sharing_enabled
                FROM mission_memberships
                WHERE mission_id = ? AND status = 'ACTIVE'
                """,
                (mission_id,),
            ).fetchall()
            out: List[CrewPositionResponse] = []
            for m in members:
                if not bool(m["location_sharing_enabled"]):
                    continue
                pos = self.get_latest_position(mission_id, m["astronaut_id"], conn=conn)
                if pos is not None:
                    out.append(pos)
            return out

    def toggle_location_sharing(
        self,
        mission_id: str,
        astronaut_id: str,
        enabled: bool,
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE mission_memberships
                SET location_sharing_enabled = ?, updated_at_utc = ?
                WHERE mission_id = ? AND astronaut_id = ? AND status = 'ACTIVE'
                """,
                (1 if enabled else 0, now_iso, mission_id, astronaut_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an active mission member.")
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="CREW_LOCATION_SHARING_CHANGED",
                payload={"astronaut_id": astronaut_id, "location_sharing_enabled": enabled},
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="CREW_LOCATION_SHARING_CHANGED",
            payload={"astronaut_id": astronaut_id, "location_sharing_enabled": enabled},
            event_seq=ev.event_seq,
        )
        return {"mission_id": mission_id, "astronaut_id": astronaut_id, "location_sharing_enabled": enabled}

    @staticmethod
    def row_to_position(row: sqlite3.Row) -> CrewPositionResponse:
        now = datetime.now(timezone.utc)
        measured_dt = datetime.fromisoformat(row["measured_at_utc"])
        age_s = max(0.0, (now - measured_dt).total_seconds())
        return CrewPositionResponse(
            position_id=row["position_id"],
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            display_name=row["display_name"] if "display_name" in row.keys() else None,
            latitude=float(row["latitude"]),
            longitude_east=float(row["longitude_east"]),
            crs=row["crs"],
            latitude_convention=row["latitude_convention"],
            longitude_direction=row["longitude_direction"],
            elevation_m=float(row["elevation_m"]) if row["elevation_m"] is not None else None,
            elevation_source=None,
            uncertainty_m=float(row["uncertainty_m"]) if row["uncertainty_m"] is not None else None,
            source_id=row["source_id"],
            source_classification=row["source_classification"],
            sequence_number=int(row["sequence_number"]),
            measured_at_utc=row["measured_at_utc"],
            received_at_utc=row["received_at_utc"],
            age_seconds=round(age_s, 2),
            is_stale=(age_s > settings.POSITION_STALE_AFTER_SECONDS),
            validation_status=row["validation_status"],
        )

    def derive_connection_status(
        self,
        *,
        mission_id: str,
        astronaut_id: str,
        location_sharing_enabled: bool,
        latest_position: Optional[CrewPositionResponse],
    ) -> CrewConnectionStatus:
        if not location_sharing_enabled:
            return "LOCATION_SHARING_DISABLED"
        connected_ids = set(self._hub.active_astronaut_ids(mission_id))
        if latest_position is not None:
            if latest_position.is_stale:
                return "POSITION_STALE"
            return "CONNECTED" if astronaut_id in connected_ids or latest_position.age_seconds <= settings.POSITION_STALE_AFTER_SECONDS else "DISCONNECTED"
        return "POSITION_UNAVAILABLE" if astronaut_id in connected_ids else "DISCONNECTED"
