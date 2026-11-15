"""
Astronaut Authentication, Session Management, Password Reset & Operational Profile Endpoints.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    AuthContext,
    clear_auth_cookies,
    get_optional_auth,
    require_auth,
    set_auth_cookies,
)
from app.core.config import settings
from app.core.security import client_ip_from_request, enforce_rate_limit
from app.schemas.mission_collab import (
    AstronautProfileResponse,
    AuthSessionResponse,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    SessionInfoResponse,
    UpdateProfileRequest,
)
from app.services.container import auth_service

router = APIRouter(prefix="/auth", tags=["Astronaut Auth & Profile"])


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
def register_astronaut(
    payload: RegisterRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    enforce_rate_limit(
        f"auth_register:{client_ip_from_request(request)}",
        max_attempts=settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    profile, raw_token, csrf_token, session_id = auth_service.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, raw_token=raw_token, csrf_token=csrf_token)
    return AuthSessionResponse(
        authenticated=True,
        astronaut=profile,
        csrf_token=csrf_token,
        session_id=session_id,
    )


@router.post("/login", response_model=AuthSessionResponse)
def login_astronaut(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    ip = client_ip_from_request(request)
    enforce_rate_limit(
        f"auth_login:{ip}:{payload.email}",
        max_attempts=settings.AUTH_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )
    profile, raw_token, csrf_token, session_id = auth_service.login(
        email=payload.email,
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, raw_token=raw_token, csrf_token=csrf_token)
    return AuthSessionResponse(
        authenticated=True,
        astronaut=profile,
        csrf_token=csrf_token,
        session_id=session_id,
    )


@router.post("/logout")
def logout_astronaut(
    response: Response,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    auth_service.logout(auth.session_id)
    clear_auth_cookies(response)
    return {"logged_out": True}


@router.post("/refresh", response_model=AuthSessionResponse)
def refresh_auth_session(
    response: Response,
    auth: AuthContext = Depends(require_auth),
) -> AuthSessionResponse:
    new_token, new_csrf = auth_service.refresh_session(auth.session_id)
    set_auth_cookies(response, raw_token=new_token, csrf_token=new_csrf)
    return AuthSessionResponse(
        authenticated=True,
        astronaut=auth.profile,
        csrf_token=new_csrf,
        session_id=auth.session_id,
    )


@router.get("/session", response_model=AuthSessionResponse)
def inspect_current_session(
    auth: AuthContext | None = Depends(get_optional_auth),
) -> AuthSessionResponse:
    if auth is None:
        return AuthSessionResponse(authenticated=False)
    return AuthSessionResponse(
        authenticated=True,
        astronaut=auth.profile,
        csrf_token=auth.csrf_token,
        session_id=auth.session_id,
    )


@router.get("/sessions", response_model=List[SessionInfoResponse])
def list_my_sessions(auth: AuthContext = Depends(require_auth)) -> List[SessionInfoResponse]:
    return auth_service.list_sessions(auth.astronaut_id, auth.session_id)


@router.delete("/sessions/{session_id}")
def revoke_my_session(
    session_id: str,
    response: Response,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    auth_service.revoke_session(auth.astronaut_id, session_id)
    if session_id == auth.session_id:
        clear_auth_cookies(response)
    return {"revoked": True, "session_id": session_id}


@router.put("/profile", response_model=AstronautProfileResponse)
def update_my_profile(
    payload: UpdateProfileRequest,
    auth: AuthContext = Depends(require_auth),
) -> AstronautProfileResponse:
    return auth_service.update_profile(auth.astronaut_id, payload)


@router.post("/password-reset/request")
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
) -> dict:
    enforce_rate_limit(
        f"pw_reset:{client_ip_from_request(request)}",
        max_attempts=10,
        window_seconds=60,
    )
    return auth_service.request_password_reset(payload.email)


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest) -> dict:
    auth_service.confirm_password_reset(
        raw_token=payload.token,
        new_password=payload.new_password,
    )
    return {"password_reset": True}


@router.post("/account/deactivate")
def deactivate_my_account(
    response: Response,
    auth: AuthContext = Depends(require_auth),
) -> dict:
    auth_service.revoke_account(auth.astronaut_id)
    clear_auth_cookies(response)
    return {"deactivated": True}
