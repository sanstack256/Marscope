"""
MARSCOPE Configuration Module
Martian Surface Intelligence & Exploration System
"""

import json
import os
from typing import Any, List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_DEV_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def _parse_cors_origins(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("CORS_ORIGINS JSON value must be a list of origin URLs.")
            items = [str(item) for item in parsed]
        else:
            items = [part for part in raw.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    else:
        raise ValueError("CORS_ORIGINS must be a list of origin URLs or a comma-separated string.")

    cleaned: List[str] = []
    for item in items:
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*" or "*" in origin:
            raise ValueError("Wildcard origins ('*') are prohibited in CORS_ORIGINS when credentials are enabled.")
        cleaned.append(origin)
    return cleaned


def _default_cors_origins() -> List[str]:
    env_fallback = os.getenv("BACKEND_CORS_ORIGINS")
    if env_fallback and env_fallback.strip():
        return _parse_cors_origins(env_fallback)

    if os.getenv("VERCEL") == "1":
        vercel_origins: List[str] = []
        for var_name in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_BRANCH_URL", "VERCEL_URL"):
            host = (os.getenv(var_name) or "").strip()
            if host:
                origin = host if host.startswith(("http://", "https://")) else f"https://{host}"
                origin = origin.rstrip("/")
                if origin not in vercel_origins:
                    vercel_origins.append(origin)
        if vercel_origins:
            return vercel_origins

    return list(_DEFAULT_DEV_CORS_ORIGINS)


class Settings(BaseSettings):
    PROJECT_NAME: str = "MARSCOPE"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    MARSCOPE_DATASETS_DIR: Optional[str] = None
    MARSCOPE_GCS_BUCKET: Optional[str] = None
    MARSCOPE_GCS_PREFIX: str = "datasets"
    MARSCOPE_STARTUP_ACQUIRE_DEMS: bool = False
    TRACKING_INGEST_TOKEN: Optional[str] = None
    OPERATOR_ACTION_TOKEN: Optional[str] = None

    # Multi-Astronaut Mission Persistence & Auth Settings
    DATABASE_URL: Optional[str] = None
    MARSCOPE_SECRET_KEY: Optional[str] = None
    AUTH_SESSION_TTL_SECONDS: int = 604800  # 7 days sliding/max session window
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_RATE_LIMIT_MAX_ATTEMPTS: int = 20
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    SOS_RATE_LIMIT_MAX_ATTEMPTS: int = 12
    SOS_RATE_LIMIT_WINDOW_SECONDS: int = 60
    POSITION_STALE_AFTER_SECONDS: int = 120
    AUDIO_UPLOAD_MAX_BYTES: int = 10 * 1024 * 1024
    ALLOW_TEST_PASSWORD_RESET_TOKEN_PREVIEW: bool = False

    # Judge Demonstration Mode Configuration
    MARSCOPE_DEMO_ENABLED: bool = True
    MARSCOPE_DEMO_EMAIL: str = "judge.demo@marscope.local"
    MARSCOPE_DEMO_PASSWORD: Optional[str] = None

    # CORS Configuration (strict explicit origins; wildcards rejected)
    CORS_ORIGINS: List[str] = _default_cors_origins()

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _validate_cors_origins(cls, value: Any) -> List[str]:
        origins = _parse_cors_origins(value)
        return origins

    # Planetary Context
    PLANETARY_BODY: str = "Mars"
    DEFAULT_CRS: str = "IAU2000:49900"
    STUDY_AREA_NAME: str = "Gale Crater - Mount Sharp Boxwork Exploration Zone"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
