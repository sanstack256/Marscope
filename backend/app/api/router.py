"""
Central API Router Registry
"""

from fastapi import APIRouter
from app.api.health import router as health_router

api_router = APIRouter(prefix="/api")

# Register health check
api_router.include_router(health_router)
