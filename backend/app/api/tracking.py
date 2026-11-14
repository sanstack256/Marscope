"""
Authenticated Live Mission Tracking & SSE API Endpoints
MARSCOPE - Exposes /api/tracking/* endpoints strictly isolated from simulation playback.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas.tracking import (
    TelemetryFixIngestRequest,
    TrackingReplanPreviewRequest,
    TrackingReplanPreviewResponse,
    TrackingStatusResponse,
)
from app.services.container import tracking_service

router = APIRouter(prefix="/tracking", tags=["Tracking"])


@router.get("/status", response_model=TrackingStatusResponse)
async def get_tracking_status(
    active_route_id: Optional[str] = Query(None, description="Optional route ID for live cross-track comparison"),
) -> TrackingStatusResponse:
    """
    Return honest live mission tracking status.
    Never fabricates a position or uses browser geolocation; reports disconnected when unavailable.
    """
    return tracking_service.get_status(active_route_id=active_route_id)


@router.post("/telemetry", response_model=TrackingStatusResponse)
async def ingest_live_telemetry(
    req: TelemetryFixIngestRequest,
    authorization: Optional[str] = Header(None),
    x_mars_tracking_token: Optional[str] = Header(None),
) -> TrackingStatusResponse:
    """
    Authenticated ingest endpoint for external Mars positioning telemetry.
    Requires MARSCOPE_TRACKING_TOKEN / TRACKING_INGEST_TOKEN match and strict IAU2000:49900 validation.
    """
    ok, code, reason = tracking_service.verify_ingest_auth(authorization, x_mars_tracking_token)
    if not ok:
        raise HTTPException(status_code=code, detail=reason)
    try:
        return tracking_service.ingest_fix(req)
    except LookupError as le:
        raise HTTPException(status_code=409, detail=str(le))
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.post("/replan-preview", response_model=TrackingReplanPreviewResponse)
async def preview_replan(req: TrackingReplanPreviewRequest) -> TrackingReplanPreviewResponse:
    """
    Generate a confirmation-gated route replanning diff from the latest live Mars fix
    within verified DEM coverage. Never automatically mutates the active route.
    """
    try:
        return tracking_service.preview_replan_from_live_fix(req)
    except LookupError as le:
        raise HTTPException(status_code=404, detail=str(le))
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))


@router.delete("/session", response_model=TrackingStatusResponse)
async def clear_tracking_session() -> TrackingStatusResponse:
    """Clear current live telemetry session and return to disconnected state."""
    return tracking_service.clear_session()


@router.get("/stream")
async def stream_tracking_events(
    request: Request,
    active_route_id: Optional[str] = Query(None),
) -> StreamingResponse:
    """
    Server-Sent Events (SSE) stream pushing live mission tracking status & heartbeats.
    Cleanly closes when client disconnects.
    """

    async def event_generator():
        q = tracking_service.subscribe()
        try:
            initial = tracking_service.get_status(active_route_id=active_route_id).model_dump()
            yield f"event: tracking_status\ndata: {json.dumps(initial)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"event: tracking_status\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Emit fresh status heartbeat (also catches stale timeout transitions automatically)
                    hb = tracking_service.get_status(active_route_id=active_route_id).model_dump()
                    yield f"event: tracking_heartbeat\ndata: {json.dumps(hb)}\n\n"
        finally:
            tracking_service.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
