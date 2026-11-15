"""
FastAPI Dependencies for Cookie+CSRF Authentication and Mission-Scoped Authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import Cookie, Header, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.security import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    verify_csrf_if_cookie_mutating,
)
from app.schemas.mission_collab import AstronautProfileResponse, MissionRole
from app.services.container import auth_service, mission_db


@dataclass
class AuthContext:
    session_id: str
    astronaut_id: str
    csrf_token: str
    profile: AstronautProfileResponse


@dataclass
class MissionMembershipContext:
    mission_id: str
    astronaut_id: str
    role: MissionRole
    location_sharing_enabled: bool
    auth: AuthContext


def set_auth_cookies(response: Response, *, raw_token: str, csrf_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.AUTH_SESSION_TTL_SECONDS,
        httponly=False,  # readable by frontend to send X-CSRF-Token header
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, path="/")


def get_optional_auth(
    request: Request,
    session_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_cookie: Optional[str] = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    csrf_header: Optional[str] = Header(default=None, alias=CSRF_HEADER_NAME),
) -> Optional[AuthContext]:
    if not session_cookie:
        return None
    sess = auth_service.get_session(session_cookie)
    if sess is None:
        return None
    verify_csrf_if_cookie_mutating(
        request,
        session_cookie=session_cookie,
        csrf_cookie=csrf_cookie,
        csrf_header=csrf_header,
        session_csrf_token=sess["csrf_token"],
    )
    return AuthContext(
        session_id=sess["session_id"],
        astronaut_id=sess["astronaut_id"],
        csrf_token=sess["csrf_token"],
        profile=sess["profile"],
    )


def require_auth(
    request: Request,
    session_cookie: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_cookie: Optional[str] = Cookie(default=None, alias=CSRF_COOKIE_NAME),
    csrf_header: Optional[str] = Header(default=None, alias=CSRF_HEADER_NAME),
) -> AuthContext:
    ctx = get_optional_auth(
        request,
        session_cookie=session_cookie,
        csrf_cookie=csrf_cookie,
        csrf_header=csrf_header,
    )
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Astronaut authentication is required.",
        )
    return ctx


def load_mission_membership(mission_id: str, auth: AuthContext) -> MissionMembershipContext:
    with mission_db.read() as conn:
        mission_row = conn.execute(
            "SELECT mission_id FROM missions WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        if mission_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found.")

        mem_row = conn.execute(
            """
            SELECT role, status, location_sharing_enabled
            FROM mission_memberships
            WHERE mission_id = ? AND astronaut_id = ?
            """,
            (mission_id, auth.astronaut_id),
        ).fetchone()

    if mem_row is None or mem_row["status"] != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an active member of this mission.",
        )

    return MissionMembershipContext(
        mission_id=mission_id,
        astronaut_id=auth.astronaut_id,
        role=mem_row["role"],
        location_sharing_enabled=bool(mem_row["location_sharing_enabled"]),
        auth=auth,
    )


def require_mission_roles(
    mission_id: str,
    auth: AuthContext,
    allowed_roles: Iterable[MissionRole],
) -> MissionMembershipContext:
    mem = load_mission_membership(mission_id, auth)
    if mem.role not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{mem.role}' is not permitted for this mission action.",
        )
    return mem
