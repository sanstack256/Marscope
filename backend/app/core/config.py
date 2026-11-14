"""
MARSCOPE Configuration Module
Martian Surface Intelligence & Exploration System
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "MARSCOPE"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    TRACKING_INGEST_TOKEN: Optional[str] = None
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    
    # Planetary Context
    PLANETARY_BODY: str = "Mars"
    DEFAULT_CRS: str = "IAU2000:49900"
    STUDY_AREA_NAME: str = "Gale Crater - Mount Sharp Boxwork Exploration Zone"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
