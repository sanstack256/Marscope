"""
Astronaut Authentication, Session Lifecycle, Password Reset, and Operational Profile Service.
All operational profile mass parameters are NULL unless explicitly entered by the user,
in which case they carry explicit USER_ASSUMED metadata and append to profile_edit_history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import (
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.database import MissionDatabase
from app.schemas.mission_collab import (
    AstronautProfileResponse,
    OperationalAssumedField,
    SessionInfoResponse,
    UpdateProfileRequest,
)


class AuthService:
    def __init__(self, db: MissionDatabase) -> None:
        self._db = db

    def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[AstronautProfileResponse, str, str, str]:
        try:
            pw_hash = hash_password(password)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        astronaut_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        raw_token = generate_opaque_token(32)
        csrf_token = generate_opaque_token(24)
        expires_iso = (now + timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS)).isoformat()

        with self._db.transaction() as conn:
            dup = conn.execute("SELECT astronaut_id FROM astronauts WHERE email = ?", (email,)).fetchone()
            if dup is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An astronaut account with that email already exists.",
                )

            conn.execute(
                """
                INSERT INTO astronauts (
                    astronaut_id, email, display_name, password_hash, is_active,
                    profile_visibility, profile_edit_history_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, 1, 'mission_members', '[]', ?, ?)
                """,
                (astronaut_id, email, display_name, pw_hash, now_iso, now_iso),
            )
            conn.execute(
                """
                INSERT INTO auth_sessions (
                    session_id, astronaut_id, token_hash, csrf_token, user_agent,
                    created_at_utc, expires_at_utc, last_seen_at_utc, revoked_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session_id,
                    astronaut_id,
                    hash_token(raw_token),
                    csrf_token,
                    user_agent,
                    now_iso,
                    expires_iso,
                    now_iso,
                ),
            )
            row = conn.execute("SELECT * FROM astronauts WHERE astronaut_id = ?", (astronaut_id,)).fetchone()

        return self.row_to_profile(row), raw_token, csrf_token, session_id

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: Optional[str] = None,
    ) -> Tuple[AstronautProfileResponse, str, str, str]:
        with self._db.read() as conn:
            row = conn.execute("SELECT * FROM astronauts WHERE email = ?", (email,)).fetchone()

        if row is None or not bool(row["is_active"]) or not verify_password(password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid astronaut credentials or deactivated account.",
            )

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        session_id = str(uuid.uuid4())
        raw_token = generate_opaque_token(32)
        csrf_token = generate_opaque_token(24)
        expires_iso = (now + timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS)).isoformat()

        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (
                    session_id, astronaut_id, token_hash, csrf_token, user_agent,
                    created_at_utc, expires_at_utc, last_seen_at_utc, revoked_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session_id,
                    row["astronaut_id"],
                    hash_token(raw_token),
                    csrf_token,
                    user_agent,
                    now_iso,
                    expires_iso,
                    now_iso,
                ),
            )
            fresh = conn.execute("SELECT * FROM astronauts WHERE astronaut_id = ?", (row["astronaut_id"],)).fetchone()

        return self.row_to_profile(fresh), raw_token, csrf_token, session_id

    def get_session(self, raw_token: str) -> Optional[Dict[str, Any]]:
        if not raw_token:
            return None
        token_h = hash_token(raw_token)
        now = datetime.now(timezone.utc)
        with self._db.read() as conn:
            row = conn.execute(
                """
                SELECT s.*, a.email, a.display_name, a.is_active,
                       a.body_mass_kg, a.body_mass_meta_json,
                       a.suit_mass_kg, a.suit_mass_meta_json,
                       a.equipment_mass_kg, a.equipment_mass_meta_json,
                       a.mobility_constraints, a.emergency_contact,
                       a.profile_visibility, a.profile_edit_history_json, a.is_demo,
                       a.created_at_utc AS astro_created_at_utc,
                       a.updated_at_utc AS astro_updated_at_utc
                FROM auth_sessions s
                JOIN astronauts a ON a.astronaut_id = s.astronaut_id
                WHERE s.token_hash = ?
                """,
                (token_h,),
            ).fetchone()

        if row is None or row["revoked_at_utc"] is not None or not bool(row["is_active"]):
            return None

        expires_at = datetime.fromisoformat(row["expires_at_utc"])
        if expires_at <= now:
            return None

        return {
            "session_id": row["session_id"],
            "astronaut_id": row["astronaut_id"],
            "csrf_token": row["csrf_token"],
            "profile": self.row_to_profile(row, prefix_created="astro_created_at_utc", prefix_updated="astro_updated_at_utc"),
        }

    def refresh_session(self, session_id: str) -> Tuple[str, str]:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        new_expires = (now + timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS)).isoformat()
        new_raw_token = generate_opaque_token(32)
        new_csrf = generate_opaque_token(24)
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE auth_sessions
                SET token_hash = ?, csrf_token = ?, expires_at_utc = ?, last_seen_at_utc = ?
                WHERE session_id = ? AND revoked_at_utc IS NULL
                """,
                (hash_token(new_raw_token), new_csrf, new_expires, now_iso, session_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked.")
        return new_raw_token, new_csrf

    def logout(self, session_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at_utc = ? WHERE session_id = ? AND revoked_at_utc IS NULL",
                (now_iso, session_id),
            )

    def list_sessions(self, astronaut_id: str, current_session_id: str) -> List[SessionInfoResponse]:
        with self._db.read() as conn:
            rows = conn.execute(
                """
                SELECT session_id, user_agent, created_at_utc, expires_at_utc, last_seen_at_utc, revoked_at_utc
                FROM auth_sessions
                WHERE astronaut_id = ?
                ORDER BY created_at_utc DESC
                LIMIT 25
                """,
                (astronaut_id,),
            ).fetchall()
        return [
            SessionInfoResponse(
                session_id=r["session_id"],
                user_agent=r["user_agent"],
                created_at_utc=r["created_at_utc"],
                expires_at_utc=r["expires_at_utc"],
                last_seen_at_utc=r["last_seen_at_utc"],
                revoked_at_utc=r["revoked_at_utc"],
                is_current=(r["session_id"] == current_session_id),
            )
            for r in rows
        ]

    def revoke_session(self, astronaut_id: str, target_session_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at_utc = ?
                WHERE session_id = ? AND astronaut_id = ? AND revoked_at_utc IS NULL
                """,
                (now_iso, target_session_id, astronaut_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active session not found.")

    def update_profile(self, astronaut_id: str, req: UpdateProfileRequest) -> AstronautProfileResponse:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM astronauts WHERE astronaut_id = ?", (astronaut_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Astronaut account not found.")

            history: List[Dict[str, Any]] = json.loads(row["profile_edit_history_json"] or "[]")
            changes: Dict[str, Any] = {}

            display_name = row["display_name"]
            if req.display_name is not None and req.display_name.strip() != display_name:
                display_name = req.display_name.strip()
                changes["display_name"] = display_name

            def _apply_mass(
                cur_val: Optional[float],
                cur_meta_json: Optional[str],
                new_val: Optional[float],
                clear_flag: bool,
                field_key: str,
            ) -> Tuple[Optional[float], Optional[str]]:
                if clear_flag:
                    if cur_val is not None:
                        changes[field_key] = None
                    return None, None
                if new_val is not None:
                    meta = {
                        "value": float(new_val),
                        "unit": "kg",
                        "classification": "USER_ASSUMED",
                        "updated_at_utc": now_iso,
                        "source": "astronaut_profile_form",
                    }
                    changes[field_key] = float(new_val)
                    return float(new_val), json.dumps(meta)
                return cur_val, cur_meta_json

            body_mass, body_meta = _apply_mass(
                row["body_mass_kg"], row["body_mass_meta_json"], req.body_mass_kg, req.clear_body_mass, "body_mass_kg"
            )
            suit_mass, suit_meta = _apply_mass(
                row["suit_mass_kg"], row["suit_mass_meta_json"], req.suit_mass_kg, req.clear_suit_mass, "suit_mass_kg"
            )
            equip_mass, equip_meta = _apply_mass(
                row["equipment_mass_kg"],
                row["equipment_mass_meta_json"],
                req.equipment_mass_kg,
                req.clear_equipment_mass,
                "equipment_mass_kg",
            )

            mobility_constraints = row["mobility_constraints"]
            if req.mobility_constraints is not None:
                mobility_constraints = req.mobility_constraints.strip() or None
                changes["mobility_constraints"] = mobility_constraints

            emergency_contact = row["emergency_contact"]
            if req.emergency_contact is not None:
                emergency_contact = req.emergency_contact.strip() or None
                changes["emergency_contact"] = emergency_contact

            profile_visibility = row["profile_visibility"]
            if req.profile_visibility is not None and req.profile_visibility != profile_visibility:
                profile_visibility = req.profile_visibility
                changes["profile_visibility"] = profile_visibility

            if changes:
                history.append(
                    {
                        "updated_at_utc": now_iso,
                        "actor_id": astronaut_id,
                        "changes": changes,
                    }
                )
                history = history[-100:]

            conn.execute(
                """
                UPDATE astronauts
                SET display_name = ?,
                    body_mass_kg = ?, body_mass_meta_json = ?,
                    suit_mass_kg = ?, suit_mass_meta_json = ?,
                    equipment_mass_kg = ?, equipment_mass_meta_json = ?,
                    mobility_constraints = ?,
                    emergency_contact = ?,
                    profile_visibility = ?,
                    profile_edit_history_json = ?,
                    updated_at_utc = ?
                WHERE astronaut_id = ?
                """,
                (
                    display_name,
                    body_mass,
                    body_meta,
                    suit_mass,
                    suit_meta,
                    equip_mass,
                    equip_meta,
                    mobility_constraints,
                    emergency_contact,
                    profile_visibility,
                    json.dumps(history),
                    now_iso,
                    astronaut_id,
                ),
            )
            updated = conn.execute("SELECT * FROM astronauts WHERE astronaut_id = ?", (astronaut_id,)).fetchone()
        return self.row_to_profile(updated)

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        """Creates a single-use short-lived reset token without leaking account existence."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(minutes=30)).isoformat()
        preview_token: Optional[str] = None

        with self._db.transaction() as conn:
            row = conn.execute("SELECT astronaut_id, is_active, is_demo FROM astronauts WHERE email = ?", (email,)).fetchone()
            if row is not None and bool(row["is_active"]) and not bool(row["is_demo"]):
                raw_token = generate_opaque_token(24)
                conn.execute(
                    """
                    INSERT INTO password_reset_tokens (
                        reset_id, astronaut_id, token_hash, expires_at_utc, used_at_utc, created_at_utc
                    ) VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (str(uuid.uuid4()), row["astronaut_id"], hash_token(raw_token), expires_iso, now_iso),
                )
                if settings.ALLOW_TEST_PASSWORD_RESET_TOKEN_PREVIEW or settings.ENVIRONMENT == "test":
                    preview_token = raw_token

        out: Dict[str, Any] = {
            "accepted": True,
            "message": "If an active astronaut account matches that email, a reset token has been generated.",
            "expires_in_minutes": 30,
        }
        if preview_token is not None:
            out["reset_token_preview"] = preview_token
        return out

    def confirm_password_reset(self, *, raw_token: str, new_password: str) -> None:
        try:
            new_hash = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        token_h = hash_token(raw_token)
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token_hash = ?",
                (token_h,),
            ).fetchone()
            if row is None or row["used_at_utc"] is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or already used reset token.")
            if datetime.fromisoformat(row["expires_at_utc"]) <= now:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset token has expired.")

            conn.execute(
                "UPDATE astronauts SET password_hash = ?, updated_at_utc = ? WHERE astronaut_id = ?",
                (new_hash, now_iso, row["astronaut_id"]),
            )
            conn.execute(
                "UPDATE password_reset_tokens SET used_at_utc = ? WHERE reset_id = ?",
                (now_iso, row["reset_id"]),
            )
            conn.execute(
                "UPDATE auth_sessions SET revoked_at_utc = ? WHERE astronaut_id = ? AND revoked_at_utc IS NULL",
                (now_iso, row["astronaut_id"]),
            )

    def revoke_account(self, astronaut_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE astronauts SET is_active = 0, updated_at_utc = ? WHERE astronaut_id = ?",
                (now_iso, astronaut_id),
            )
            conn.execute(
                "UPDATE auth_sessions SET revoked_at_utc = ? WHERE astronaut_id = ? AND revoked_at_utc IS NULL",
                (now_iso, astronaut_id),
            )

    @staticmethod
    def _parse_mass_meta(val: Optional[float], meta_json: Optional[str]) -> OperationalAssumedField:
        if val is None:
            return OperationalAssumedField(value=None, unit="kg", classification="NOT_PROVIDED")
        meta = json.loads(meta_json) if meta_json else {}
        return OperationalAssumedField(
            value=float(val),
            unit=meta.get("unit", "kg"),
            classification="USER_ASSUMED",
            updated_at_utc=meta.get("updated_at_utc"),
            source=meta.get("source"),
        )

    @classmethod
    def row_to_profile(
        cls,
        row: sqlite3.Row,
        *,
        prefix_created: str = "created_at_utc",
        prefix_updated: str = "updated_at_utc",
    ) -> AstronautProfileResponse:
        b_meta = cls._parse_mass_meta(row["body_mass_kg"], row["body_mass_meta_json"])
        s_meta = cls._parse_mass_meta(row["suit_mass_kg"], row["suit_mass_meta_json"])
        e_meta = cls._parse_mass_meta(row["equipment_mass_kg"], row["equipment_mass_meta_json"])

        masses = [m for m in (row["body_mass_kg"], row["suit_mass_kg"], row["equipment_mass_kg"]) if m is not None]
        # Total mass is ONLY computed if at least body + suit are explicitly provided; never substitute missing as 0.
        total_mass: Optional[float] = None
        if row["body_mass_kg"] is not None and row["suit_mass_kg"] is not None:
            total_mass = round(float(row["body_mass_kg"]) + float(row["suit_mass_kg"]) + float(row["equipment_mass_kg"] or 0.0), 3)
            if row["equipment_mass_kg"] is None and len(masses) == 2:
                # Explicitly require equipment_mass_kg if you want full 3-part sum, OR mark None if any is missing
                total_mass = None

        return AstronautProfileResponse(
            astronaut_id=row["astronaut_id"],
            email=row["email"],
            display_name=row["display_name"],
            is_active=bool(row["is_active"]),
            body_mass_kg=row["body_mass_kg"],
            body_mass_meta=b_meta,
            suit_mass_kg=row["suit_mass_kg"],
            suit_mass_meta=s_meta,
            equipment_mass_kg=row["equipment_mass_kg"],
            equipment_mass_meta=e_meta,
            total_mass_kg=total_mass,
            mobility_constraints=row["mobility_constraints"],
            emergency_contact=row["emergency_contact"],
            profile_visibility=row["profile_visibility"],
            profile_edit_history=json.loads(row["profile_edit_history_json"] or "[]"),
            is_demo=bool(row["is_demo"]) if "is_demo" in row.keys() else False,
            created_at_utc=row[prefix_created],
            updated_at_utc=row[prefix_updated],
        )
