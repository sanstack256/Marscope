"""
Missions, Memberships, Secure CSPRNG Invitations & Crew Roster Service.
Enforces mission-scoped isolation, RBAC (MISSION_LEAD, ASTRONAUT, MISSION_OPERATOR),
last-lead protection, hashed revocable expiring invitations, and honest crew freshness states.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import uuid
from typing import List, Optional

from fastapi import HTTPException, status

from app.core.security import generate_opaque_token, hash_token
from app.db.database import MissionDatabase
from app.schemas.mission_collab import (
    CreateInvitationRequest,
    CreateMissionRequest,
    CrewMemberResponse,
    InvitationResponse,
    MissionRole,
    MissionSummaryResponse,
    UpdateMissionRequest,
)
from app.services.mission_event_service import MissionEventService
from app.services.position_service import CrewPositionService
from app.services.realtime_hub import MissionRealtimeHub


class MissionService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        realtime_hub: MissionRealtimeHub,
        position_service: CrewPositionService,
    ) -> None:
        self._db = db
        self._events = event_service
        self._hub = realtime_hub
        self._positions = position_service

    def create_mission(self, lead_astronaut_id: str, req: CreateMissionRequest) -> MissionSummaryResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        mission_id = str(uuid.uuid4())
        membership_id = str(uuid.uuid4())

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO missions (
                    mission_id, name, description, objective, lead_astronaut_id,
                    operating_region, planned_start_utc, planned_end_utc,
                    visibility, membership_policy, status, landing_site_status,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'invite_only', 'ACTIVE', 'LANDING_SITE_UNCONFIGURED', ?, ?)
                """,
                (
                    mission_id,
                    req.name.strip(),
                    req.description.strip(),
                    req.objective.strip(),
                    lead_astronaut_id,
                    req.operating_region.strip() if req.operating_region else None,
                    req.planned_start_utc,
                    req.planned_end_utc,
                    req.visibility,
                    now_iso,
                    now_iso,
                ),
            )
            conn.execute(
                """
                INSERT INTO mission_memberships (
                    membership_id, mission_id, astronaut_id, role, status,
                    location_sharing_enabled, joined_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, 'MISSION_LEAD', 'ACTIVE', 1, ?, ?)
                """,
                (membership_id, mission_id, lead_astronaut_id, now_iso, now_iso),
            )
            self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=lead_astronaut_id,
                event_type="MISSION_CREATED",
                payload={"name": req.name.strip(), "landing_site_status": "LANDING_SITE_UNCONFIGURED"},
            )

        return self.get_mission(mission_id, lead_astronaut_id)

    def list_missions_for_astronaut(self, astronaut_id: str) -> List[MissionSummaryResponse]:
        with self._db.read() as conn:
            rows = conn.execute(
                """
                SELECT m.*, mm.role AS my_role,
                       (SELECT COUNT(*) FROM mission_memberships x WHERE x.mission_id = m.mission_id AND x.status = 'ACTIVE') AS active_member_count,
                       (SELECT COUNT(*) FROM sos_events s WHERE s.mission_id = m.mission_id AND s.status NOT IN ('RESOLVED', 'CANCELLED')) AS active_sos_count
                FROM missions m
                JOIN mission_memberships mm ON mm.mission_id = m.mission_id
                WHERE mm.astronaut_id = ? AND mm.status = 'ACTIVE'
                ORDER BY m.updated_at_utc DESC
                """,
                (astronaut_id,),
            ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def get_mission(self, mission_id: str, astronaut_id: str) -> MissionSummaryResponse:
        with self._db.read() as conn:
            row = conn.execute(
                """
                SELECT m.*, mm.role AS my_role,
                       (SELECT COUNT(*) FROM mission_memberships x WHERE x.mission_id = m.mission_id AND x.status = 'ACTIVE') AS active_member_count,
                       (SELECT COUNT(*) FROM sos_events s WHERE s.mission_id = m.mission_id AND s.status NOT IN ('RESOLVED', 'CANCELLED')) AS active_sos_count
                FROM missions m
                JOIN mission_memberships mm ON mm.mission_id = m.mission_id
                WHERE m.mission_id = ? AND mm.astronaut_id = ? AND mm.status = 'ACTIVE'
                """,
                (mission_id, astronaut_id),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found or inaccessible.")
        return self._row_to_summary(row)

    def update_mission(
        self,
        mission_id: str,
        actor_id: str,
        req: UpdateMissionRequest,
    ) -> MissionSummaryResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            cur_row = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if cur_row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")
            name = req.name.strip() if req.name is not None else cur_row["name"]
            desc = req.description.strip() if req.description is not None else cur_row["description"]
            obj = req.objective.strip() if req.objective is not None else cur_row["objective"]
            reg = (req.operating_region.strip() or None) if req.operating_region is not None else cur_row["operating_region"]
            start = req.planned_start_utc if req.planned_start_utc is not None else cur_row["planned_start_utc"]
            end = req.planned_end_utc if req.planned_end_utc is not None else cur_row["planned_end_utc"]
            m_status = req.status if req.status is not None else cur_row["status"]

            conn.execute(
                """
                UPDATE missions
                SET name = ?, description = ?, objective = ?, operating_region = ?,
                    planned_start_utc = ?, planned_end_utc = ?, status = ?, updated_at_utc = ?
                WHERE mission_id = ?
                """,
                (name, desc, obj, reg, start, end, m_status, now_iso, mission_id),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="MISSION_UPDATED",
                payload={"name": name, "status": m_status},
            )
        self._hub.publish_mission_event(
            mission_id, event_type="MISSION_UPDATED", payload={"name": name, "status": m_status}, event_seq=ev.event_seq
        )
        return self.get_mission(mission_id, actor_id)

    def create_invitation(
        self,
        mission_id: str,
        created_by: str,
        req: CreateInvitationRequest,
    ) -> InvitationResponse:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(hours=req.expires_in_hours)).isoformat()
        invite_id = str(uuid.uuid4())
        raw_token = generate_opaque_token(24)
        max_uses = 1 if req.single_use else req.max_uses

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mission_invitations (
                    invite_id, mission_id, created_by, token_hash, role_on_join,
                    single_use, max_uses, uses_count, expires_at_utc, revoked_at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, NULL, ?)
                """,
                (
                    invite_id,
                    mission_id,
                    created_by,
                    hash_token(raw_token),
                    req.role_on_join,
                    1 if req.single_use else 0,
                    max_uses,
                    expires_iso,
                    now_iso,
                ),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=created_by,
                event_type="INVITATION_CREATED",
                payload={"invite_id": invite_id, "role_on_join": req.role_on_join, "expires_at_utc": expires_iso},
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="INVITATION_CREATED",
            payload={"invite_id": invite_id},
            event_seq=ev.event_seq,
        )
        return InvitationResponse(
            invite_id=invite_id,
            mission_id=mission_id,
            created_by=created_by,
            role_on_join=req.role_on_join,
            single_use=req.single_use,
            max_uses=max_uses,
            uses_count=0,
            expires_at_utc=expires_iso,
            revoked_at_utc=None,
            created_at_utc=now_iso,
            invite_token=raw_token,
        )

    def list_invitations(self, mission_id: str) -> List[InvitationResponse]:
        with self._db.read() as conn:
            rows = conn.execute(
                """
                SELECT * FROM mission_invitations
                WHERE mission_id = ?
                ORDER BY created_at_utc DESC
                """,
                (mission_id,),
            ).fetchall()
        return [
            InvitationResponse(
                invite_id=r["invite_id"],
                mission_id=r["mission_id"],
                created_by=r["created_by"],
                role_on_join=r["role_on_join"],
                single_use=bool(r["single_use"]),
                max_uses=r["max_uses"],
                uses_count=int(r["uses_count"]),
                expires_at_utc=r["expires_at_utc"],
                revoked_at_utc=r["revoked_at_utc"],
                created_at_utc=r["created_at_utc"],
                invite_token=None,
            )
            for r in rows
        ]

    def revoke_invitation(self, mission_id: str, invite_id: str, actor_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE mission_invitations
                SET revoked_at_utc = ?
                WHERE invite_id = ? AND mission_id = ? AND revoked_at_utc IS NULL
                """,
                (now_iso, invite_id, mission_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active invitation not found.")
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="INVITATION_REVOKED",
                payload={"invite_id": invite_id},
            )
        self._hub.publish_mission_event(
            mission_id, event_type="INVITATION_REVOKED", payload={"invite_id": invite_id}, event_seq=ev.event_seq
        )

    def join_by_invite(self, raw_invite_token: str, astronaut_id: str) -> MissionSummaryResponse:
        token_h = hash_token(raw_invite_token.strip())
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._db.transaction() as conn:
            inv = conn.execute(
                "SELECT * FROM mission_invitations WHERE token_hash = ?",
                (token_h,),
            ).fetchone()
            if inv is None or inv["revoked_at_utc"] is not None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or revoked invitation token.")
            if datetime.fromisoformat(inv["expires_at_utc"]) <= now:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Mission invitation has expired.")
            if inv["max_uses"] is not None and int(inv["uses_count"]) >= int(inv["max_uses"]):
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Mission invitation usage limit reached.")

            mission_id = inv["mission_id"]
            existing = conn.execute(
                """
                SELECT membership_id, status FROM mission_memberships
                WHERE mission_id = ? AND astronaut_id = ?
                """,
                (mission_id, astronaut_id),
            ).fetchone()
            if existing is not None:
                if existing["status"] == "ACTIVE":
                    return self.get_mission(mission_id, astronaut_id)
                conn.execute(
                    """
                    UPDATE mission_memberships
                    SET role = ?, status = 'ACTIVE', updated_at_utc = ?
                    WHERE membership_id = ?
                    """,
                    (inv["role_on_join"], now_iso, existing["membership_id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO mission_memberships (
                        membership_id, mission_id, astronaut_id, role, status,
                        location_sharing_enabled, joined_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, 'ACTIVE', 1, ?, ?)
                    """,
                    (str(uuid.uuid4()), mission_id, astronaut_id, inv["role_on_join"], now_iso, now_iso),
                )

            conn.execute(
                "UPDATE mission_invitations SET uses_count = uses_count + 1 WHERE invite_id = ?",
                (inv["invite_id"],),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="CREW_MEMBER_JOINED",
                payload={"astronaut_id": astronaut_id, "role": inv["role_on_join"], "invite_id": inv["invite_id"]},
            )

        self._hub.publish_mission_event(
            mission_id,
            event_type="CREW_MEMBER_JOINED",
            payload={"astronaut_id": astronaut_id, "role": inv["role_on_join"]},
            event_seq=ev.event_seq,
        )
        return self.get_mission(mission_id, astronaut_id)

    def leave_mission(self, mission_id: str, astronaut_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            mem = conn.execute(
                "SELECT role, status FROM mission_memberships WHERE mission_id = ? AND astronaut_id = ?",
                (mission_id, astronaut_id),
            ).fetchone()
            if mem is None or mem["status"] != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active membership not found.")
            if mem["role"] == "MISSION_LEAD":
                other_leads = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM mission_memberships
                    WHERE mission_id = ? AND role = 'MISSION_LEAD' AND status = 'ACTIVE' AND astronaut_id != ?
                    """,
                    (mission_id, astronaut_id),
                ).fetchone()
                if int(other_leads["cnt"]) == 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cannot leave mission while you are the sole MISSION_LEAD. Promote another member first.",
                    )
            conn.execute(
                """
                UPDATE mission_memberships SET status = 'LEFT', updated_at_utc = ?
                WHERE mission_id = ? AND astronaut_id = ?
                """,
                (now_iso, mission_id, astronaut_id),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=astronaut_id,
                event_type="CREW_MEMBER_LEFT",
                payload={"astronaut_id": astronaut_id},
            )
        self._hub.publish_mission_event(
            mission_id, event_type="CREW_MEMBER_LEFT", payload={"astronaut_id": astronaut_id}, event_seq=ev.event_seq
        )

    def remove_member(self, mission_id: str, target_astronaut_id: str, actor_id: str) -> None:
        if target_astronaut_id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Use the leave-mission action instead of removing yourself.",
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE mission_memberships SET status = 'REMOVED', updated_at_utc = ?
                WHERE mission_id = ? AND astronaut_id = ? AND status = 'ACTIVE'
                """,
                (now_iso, mission_id, target_astronaut_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active mission member not found.")
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="CREW_MEMBER_REMOVED",
                payload={"astronaut_id": target_astronaut_id},
            )
        self._hub.publish_mission_event(
            mission_id,
            event_type="CREW_MEMBER_REMOVED",
            payload={"astronaut_id": target_astronaut_id},
            event_seq=ev.event_seq,
        )

    def update_member_role(
        self,
        mission_id: str,
        target_astronaut_id: str,
        new_role: MissionRole,
        actor_id: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            mem = conn.execute(
                "SELECT role, status FROM mission_memberships WHERE mission_id = ? AND astronaut_id = ?",
                (mission_id, target_astronaut_id),
            ).fetchone()
            if mem is None or mem["status"] != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active mission member not found.")
            if mem["role"] == "MISSION_LEAD" and new_role != "MISSION_LEAD":
                other_leads = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM mission_memberships
                    WHERE mission_id = ? AND role = 'MISSION_LEAD' AND status = 'ACTIVE' AND astronaut_id != ?
                    """,
                    (mission_id, target_astronaut_id),
                ).fetchone()
                if int(other_leads["cnt"]) == 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Mission must retain at least one active MISSION_LEAD.",
                    )
            conn.execute(
                "UPDATE mission_memberships SET role = ?, updated_at_utc = ? WHERE mission_id = ? AND astronaut_id = ?",
                (new_role, now_iso, mission_id, target_astronaut_id),
            )
            ev = self._events.record_event_tx(
                conn,
                mission_id=mission_id,
                actor_id=actor_id,
                event_type="CREW_ROLE_UPDATED",
                payload={"astronaut_id": target_astronaut_id, "role": new_role},
            )
        self._hub.publish_mission_event(
            mission_id,
            event_type="CREW_ROLE_UPDATED",
            payload={"astronaut_id": target_astronaut_id, "role": new_role},
            event_seq=ev.event_seq,
        )

    def list_crew_roster(self, mission_id: str, requester_id: str) -> List[CrewMemberResponse]:
        with self._db.read() as conn:
            rows = conn.execute(
                """
                SELECT mm.astronaut_id, mm.role, mm.status AS membership_status,
                       mm.location_sharing_enabled, mm.joined_at_utc,
                       a.display_name, a.body_mass_kg, a.suit_mass_kg, a.equipment_mass_kg,
                       a.emergency_contact, a.profile_visibility
                FROM mission_memberships mm
                JOIN astronauts a ON a.astronaut_id = mm.astronaut_id
                WHERE mm.mission_id = ? AND mm.status = 'ACTIVE'
                ORDER BY CASE mm.role WHEN 'MISSION_LEAD' THEN 0 WHEN 'MISSION_OPERATOR' THEN 1 ELSE 2 END, a.display_name ASC
                """,
                (mission_id,),
            ).fetchall()

            roster: List[CrewMemberResponse] = []
            for r in rows:
                astro_id = r["astronaut_id"]
                sharing = bool(r["location_sharing_enabled"])
                latest_pos = (
                    self._positions.get_latest_position(mission_id, astro_id, conn=conn) if sharing else None
                )
                conn_status = self._positions.derive_connection_status(
                    mission_id=mission_id,
                    astronaut_id=astro_id,
                    location_sharing_enabled=sharing,
                    latest_position=latest_pos,
                )
                can_see_profile = r["profile_visibility"] == "mission_members" or astro_id == requester_id
                b = r["body_mass_kg"] if can_see_profile else None
                s = r["suit_mass_kg"] if can_see_profile else None
                e = r["equipment_mass_kg"] if can_see_profile else None
                tot = (
                    round(float(b) + float(s) + float(e), 3)
                    if (b is not None and s is not None and e is not None)
                    else None
                )
                roster.append(
                    CrewMemberResponse(
                        astronaut_id=astro_id,
                        display_name=r["display_name"],
                        role=r["role"],
                        membership_status=r["membership_status"],
                        location_sharing_enabled=sharing,
                        connection_status=conn_status,
                        joined_at_utc=r["joined_at_utc"],
                        latest_position=latest_pos,
                        body_mass_kg=b,
                        suit_mass_kg=s,
                        equipment_mass_kg=e,
                        total_mass_kg=tot,
                        mass_classification="USER_ASSUMED" if (b is not None or s is not None or e is not None) else "NOT_PROVIDED",
                        emergency_contact=r["emergency_contact"] if can_see_profile else None,
                    )
                )
            return roster

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> MissionSummaryResponse:
        return MissionSummaryResponse(
            mission_id=row["mission_id"],
            name=row["name"],
            description=row["description"],
            objective=row["objective"],
            lead_astronaut_id=row["lead_astronaut_id"],
            operating_region=row["operating_region"],
            planned_start_utc=row["planned_start_utc"],
            planned_end_utc=row["planned_end_utc"],
            visibility=row["visibility"],
            membership_policy=row["membership_policy"],
            status=row["status"],
            landing_site_status=row["landing_site_status"],
            my_role=row["my_role"],
            active_member_count=int(row["active_member_count"]),
            active_sos_count=int(row["active_sos_count"]),
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )
