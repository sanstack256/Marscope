"""
MARSCOPE Backend Application Entry Point
Martian Surface Intelligence & Exploration System
NASA Space Apps Challenge
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.router import api_router

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("marscope")

# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Martian Surface Intelligence & Exploration System — Surface Intelligence and Route Optimization Engine",
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "X-CSRF-Token",
        "X-Mars-Operator-Token",
        "X-Mars-Tracking-Token",
        "X-Operator-Token",
        "X-Tracking-Token",
    ],
)

# Exception handling
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception during request %s: %s", request.url.path, str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred in the MARSCOPE processing engine.",
            "path": request.url.path,
        },
    )

# Include central API router (/api/...)
app.include_router(api_router)


def _root_payload():
    return {
        "system": settings.PROJECT_NAME,
        "description": "Martian Surface Intelligence & Exploration System",
        "documentation": "/api/docs",
        "health_check": "/api/health",
        "target_region": settings.STUDY_AREA_NAME,
        "planetary_body": settings.PLANETARY_BODY,
    }


@app.get("/", tags=["Root"])
async def root():
    """
    Root entry point directing consumers to API documentation and system health.
    """
    return _root_payload()


@app.get("/api", tags=["Root"])
async def api_root():
    """
    API-prefixed root entry point for multi-service deployments routed under /api/*.
    """
    return _root_payload()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
