"""
MARSCOPE Operator Authentication & Identifier / Endpoint Guards (Prompt 18 Sec 14).
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def validate_identifier(value: str, *, field_name: str = "identifier") -> str:
    cleaned = (value or "").strip()
    if not cleaned or not _SAFE_ID_RE.match(cleaned) or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} '{value}': must be alphanumeric/underscore/dash/dot/colon only.",
        )
    return cleaned


def get_configured_operator_token() -> Optional[str]:
    env_tok = os.getenv("MARSCOPE_OPERATOR_TOKEN")
    if env_tok and env_tok.strip():
        return env_tok.strip()
    cfg_tok = getattr(settings, "OPERATOR_ACTION_TOKEN", None)
    if isinstance(cfg_tok, str) and cfg_tok.strip():
        return cfg_tok.strip()
    return None


def verify_operator_auth(
    request: Request,
    *,
    fail_closed_when_unconfigured: bool = True,
    operation_name: str = "operator mutation",
) -> None:
    """
    Validate X-Mars-Operator-Token or Authorization Bearer token on sensitive/expensive
    mutation endpoints using constant-time comparison.
    """
    expected = get_configured_operator_token()
    x_tok = request.headers.get("x-mars-operator-token")
    auth_hdr = request.headers.get("authorization")

    provided: Optional[str] = None
    if x_tok and x_tok.strip():
        provided = x_tok.strip()
    elif auth_hdr and auth_hdr.strip():
        parts = auth_hdr.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()

    if not expected:
        if fail_closed_when_unconfigured or settings.ENVIRONMENT.lower() == "production":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Operation '{operation_name}' is disabled until server operator authentication "
                    "is configured (set MARSCOPE_OPERATOR_TOKEN and supply X-Mars-Operator-Token or Bearer token)."
                ),
            )
        return

    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing operator credentials (X-Mars-Operator-Token or Bearer token required for {operation_name}).",
        )
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid operator authentication token for '{operation_name}'.",
        )
