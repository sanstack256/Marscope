"""
MARSCOPE Authentication, Cryptography, CSRF & Rate-Limiting Core
Uses memory-hard scrypt password hashing, CSPRNG opaque tokens stored SHA-256 hashed,
HttpOnly SameSite cookies with double-submit X-CSRF-Token protection, and sliding-window throttling.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Deque, Dict, Optional, Tuple

from fastapi import Cookie, Header, HTTPException, Request, status

from app.core.config import settings


SESSION_COOKIE_NAME = "marscope_session"
CSRF_COOKIE_NAME = "marscope_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

_PROCESS_FALLBACK_SECRET = secrets.token_hex(32)


def get_signing_secret() -> bytes:
    configured = (settings.MARSCOPE_SECRET_KEY or os.getenv("MARSCOPE_SECRET_KEY") or "").strip()
    if configured:
        return configured.encode("utf-8")
    return _PROCESS_FALLBACK_SECRET.encode("utf-8")


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_lower and has_upper and has_digit):
        raise ValueError("Password must contain at least one uppercase letter, one lowercase letter, and one digit.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    salt = os.urandom(16)
    n, r, p = 16384, 8, 1
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, n_s, r_s, p_s, salt_hex, hash_hex = encoded_hash.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def create_signed_attachment_token(voice_note_id: str, mission_id: str, astronaut_id: str, ttl_seconds: int = 300) -> str:
    exp = int(time.time()) + max(10, int(ttl_seconds))
    msg = f"{voice_note_id}|{mission_id}|{astronaut_id}|{exp}"
    sig = hmac.new(get_signing_secret(), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify_signed_attachment_token(
    token: str, *, voice_note_id: str, mission_id: str, astronaut_id: str
) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
        if exp < int(time.time()):
            return False
        msg = f"{voice_note_id}|{mission_id}|{astronaut_id}|{exp}"
        expected = hmac.new(get_signing_secret(), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


class SlidingWindowRateLimiter:
    """In-process per-key sliding-window rate limiter for auth & SOS endpoints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str, max_attempts: int, window_seconds: int) -> Tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - float(window_seconds)
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= max_attempts:
                retry_after = max(1, int(math.ceil(dq[0] + window_seconds - now))) if dq else window_seconds
                return False, retry_after
            dq.append(now)
            return True, 0

    def reset(self, prefix: Optional[str] = None) -> None:
        with self._lock:
            if prefix is None:
                self._hits.clear()
            else:
                for k in [k for k in self._hits if k.startswith(prefix)]:
                    self._hits.pop(k, None)


import math  # noqa: E402

rate_limiter = SlidingWindowRateLimiter()


def enforce_rate_limit(bucket_key: str, *, max_attempts: int, window_seconds: int) -> None:
    allowed, retry_after = rate_limiter.check_and_record(bucket_key, max_attempts, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def client_ip_from_request(request: Request) -> str:
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def verify_csrf_if_cookie_mutating(
    request: Request,
    session_cookie: Optional[str],
    csrf_cookie: Optional[str],
    csrf_header: Optional[str],
    session_csrf_token: str,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if not session_cookie:
        return
    if not csrf_header or not csrf_cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing CSRF protection header or cookie.",
        )
    if not hmac.compare_digest(csrf_header, csrf_cookie) or not hmac.compare_digest(csrf_header, session_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token.",
        )


# ---------------------------------------------------------------------------
# Preserved Prompt 18 Operator Token & Identifier Guards
# ---------------------------------------------------------------------------

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
