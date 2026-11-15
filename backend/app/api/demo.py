"""
Judge Demonstration Configuration & Isolated Reset API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, require_auth
from app.schemas.mission_collab import DemoCredentialsConfigResponse
from app.services.container import demo_service

router = APIRouter(prefix="/demo", tags=["Judge Demonstration Mode"])


@router.get("/config", response_model=DemoCredentialsConfigResponse)
def get_demo_config() -> DemoCredentialsConfigResponse:
    """
    Returns public judge-demo credentials and mission identifier when MARSCOPE_DEMO_ENABLED=true.
    Passwords are generated/configured via backend provisioning and never hardcoded in frontend source.
    """
    return demo_service.get_public_demo_config()


@router.post("/reset")
def reset_demo_mission(auth: AuthContext = Depends(require_auth)) -> dict:
    """
    Resets ONLY the isolated demonstration mission back to its initial seed state.
    Production missions and astronauts are never affected.
    """
    return demo_service.reset_demo_mission(actor_is_demo=bool(auth.profile.is_demo))

