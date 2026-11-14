"""
Authenticated Live Mission Tracking Service
MARSCOPE - Validates authenticated Mars positioning fixes, computes Mars-sphere
route-relative telemetry, detects off-route corridor excursions, and prepares
confirmation-gated DEM replanning previews. Never fabricates live position.
"""

from __future__ import annotations

import asyncio
import hmac
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M
from app.routing.schemas import RouteComputeRequest, RouteCoordinateInput, RouteVertex
from app.routing.service import ScienceAwareRoutingService
from app.schemas.tracking import (
    DISCONNECTED_LIVE_MESSAGE,
    RouteRelativeTelemetry,
    TelemetryFixIngestRequest,
    TrackingReplanPreviewRequest,
    TrackingReplanPreviewResponse,
    TrackingStatusResponse,
)


ALLOWED_MARS_CRS = {"IAU2000:49900", "IAU:49900", "EPSG:104905"}
REJECTED_BROWSER_PROVIDERS = {"browser_geolocation", "navigator.geolocation", "device_gps", "fake_gps"}


def _mars_sphere_distance_and_azimuth_m(
    lat1: float,
    lon1_east: float,
    lat2: float,
    lon2_east: float,
) -> Tuple[float, Optional[float]]:
    """Compute exact spherical Mars surface distance (m) and True North azimuth [0, 360)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2_east - lon1_east)

    a = math.sin(dp * 0.5) ** 2 + math.cos(p1) * math.cos(p2) * (math.sin(dl * 0.5) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    dist_m = MARS_EQUATORIAL_RADIUS_M * c

    if dist_m < 1e-6:
        return 0.0, None

    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return dist_m, brg


def _point_to_segment_projection_m(
    pt_lat: float,
    pt_lon: float,
    a: RouteVertex,
    b: RouteVertex,
) -> Tuple[float, float, float]:
    """
    Project (pt_lat, pt_lon) onto segment a->b in local Mars-sphere tangent meters.
    Returns (cross_track_m, segment_len_m, fraction_t_in_0_1).
    """
    ref_lat_rad = math.radians(0.5 * (a.lat + b.lat))
    m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
    m_per_deg_lon = max(1e-6, MARS_EQUATORIAL_RADIUS_M * math.cos(ref_lat_rad) * math.pi / 180.0)

    ax = (a.lon_east - pt_lon) * m_per_deg_lon
    ay = (a.lat - pt_lat) * m_per_deg_lat
    bx = (b.lon_east - pt_lon) * m_per_deg_lon
    by = (b.lat - pt_lat) * m_per_deg_lat

    vx = bx - ax
    vy = by - ay
    seg_len_sq = vx * vx + vy * vy
    if seg_len_sq < 1e-9:
        dist = math.hypot(ax, ay)
        return dist, 0.0, 0.0

    # Closest t on segment [0, 1] to origin (0, 0) = P
    t = -((ax * vx) + (ay * vy)) / seg_len_sq
    t_clamped = max(0.0, min(1.0, t))
    cx = ax + t_clamped * vx
    cy = ay + t_clamped * vy
    cross_m = math.hypot(cx, cy)
    seg_len_m = math.sqrt(seg_len_sq)
    return cross_m, seg_len_m, t_clamped


@dataclass
class _StoredTelemetryFix:
    provider_id: str
    session_id: str
    sequence_number: int
    timestamp_utc: datetime
    crs: str
    lat: float
    lon_east: float
    elevation_m: Optional[float]
    horizontal_uncertainty_m: Optional[float]
    heading_deg: Optional[float]
    active_route_id: Optional[str]
    corridor_threshold_m: float
    stale_after_seconds: float


class TrackingService:
    """
    Manages authenticated Mars mission position telemetry and live SSE subscribers.
    Never fabricates fixes or substitutes browser GPS.
    """

    def __init__(
        self,
        routing_service: ScienceAwareRoutingService,
        ingest_token: Optional[str] = None,
    ) -> None:
        self.routing_service = routing_service
        self._explicit_ingest_token = ingest_token
        self._latest_fix: Optional[_StoredTelemetryFix] = None
        self._previous_fix: Optional[_StoredTelemetryFix] = None
        self._subscribers: Set[asyncio.Queue[Dict[str, Any]]] = set()

    def get_configured_token(self) -> Optional[str]:
        if self._explicit_ingest_token is not None and self._explicit_ingest_token.strip():
            return self._explicit_ingest_token.strip()
        env_tok = os.getenv("MARSCOPE_TRACKING_TOKEN")
        if env_tok and env_tok.strip():
            return env_tok.strip()
        cfg_tok = getattr(settings, "TRACKING_INGEST_TOKEN", None)
        if isinstance(cfg_tok, str) and cfg_tok.strip():
            return cfg_tok.strip()
        return None

    def verify_ingest_auth(
        self,
        authorization_header: Optional[str],
        x_tracking_token: Optional[str],
    ) -> Tuple[bool, int, str]:
        expected = self.get_configured_token()
        if not expected:
            return (
                False,
                403,
                "Live telemetry ingest is disabled because no server tracking token is configured (MARSCOPE_TRACKING_TOKEN).",
            )
        provided: Optional[str] = None
        if x_tracking_token and x_tracking_token.strip():
            provided = x_tracking_token.strip()
        elif authorization_header and authorization_header.strip():
            parts = authorization_header.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                provided = parts[1].strip()
        if not provided:
            return False, 401, "Missing mission tracking authentication credentials."
        if not hmac.compare_digest(provided, expected):
            return False, 403, "Invalid mission tracking authentication token."
        return True, 200, "ok"

    def ingest_fix(
        self,
        req: TelemetryFixIngestRequest,
        *,
        now_utc: Optional[datetime] = None,
    ) -> TrackingStatusResponse:
        now = now_utc or datetime.now(timezone.utc)

        if req.provider_id.strip().lower() in REJECTED_BROWSER_PROVIDERS:
            raise ValueError("Browser or terrestrial consumer GPS providers are prohibited for Mars navigation.")
        if req.crs.strip().upper() not in ALLOWED_MARS_CRS:
            raise ValueError(f"Unsupported CRS '{req.crs}'. Live fixes must use Mars reference CRS IAU2000:49900.")
        if not (math.isfinite(req.lat) and -90.0 <= req.lat <= 90.0):
            raise ValueError(f"Planetocentric latitude {req.lat} out of finite [-90, 90] bounds.")
        if not (math.isfinite(req.lon_east) and 0.0 <= req.lon_east < 360.0):
            raise ValueError(f"East-positive longitude {req.lon_east} out of finite [0, 360) bounds.")
        if req.elevation_m is not None and not math.isfinite(req.elevation_m):
            raise ValueError("Elevation estimate must be finite when provided.")

        ts = req.timestamp_utc
        if ts.tzinfo is None:
            raise ValueError("timestamp_utc must include explicit timezone (e.g., trailing 'Z' or '+00:00').")
        ts_utc = ts.astimezone(timezone.utc)
        if (ts_utc - now).total_seconds() > 60.0:
            raise ValueError("Telemetry fix timestamp is too far in the future (> 60s clock skew).")

        if self._latest_fix is not None and self._latest_fix.session_id == req.session_id:
            if req.sequence_number <= self._latest_fix.sequence_number:
                raise LookupError(
                    f"Out-of-order or duplicate sequence_number={req.sequence_number}; expected > {self._latest_fix.sequence_number}."
                )
            if ts_utc < self._latest_fix.timestamp_utc:
                raise ValueError("Telemetry timestamp cannot regress earlier than previous sequence timestamp.")

        computed_heading = req.heading_deg
        if (
            self._latest_fix is not None
            and self._latest_fix.session_id == req.session_id
            and computed_heading is None
        ):
            step_d, az = _mars_sphere_distance_and_azimuth_m(
                self._latest_fix.lat,
                self._latest_fix.lon_east,
                req.lat,
                req.lon_east,
            )
            if step_d >= 0.2 and az is not None:
                computed_heading = round(az, 2)

        stored = _StoredTelemetryFix(
            provider_id=req.provider_id.strip(),
            session_id=req.session_id.strip(),
            sequence_number=req.sequence_number,
            timestamp_utc=ts_utc,
            crs="IAU2000:49900",
            lat=req.lat,
            lon_east=req.lon_east,
            elevation_m=req.elevation_m,
            horizontal_uncertainty_m=req.horizontal_uncertainty_m,
            heading_deg=computed_heading,
            active_route_id=req.active_route_id or (self._latest_fix.active_route_id if self._latest_fix else None),
            corridor_threshold_m=req.corridor_threshold_m,
            stale_after_seconds=req.stale_after_seconds,
        )
        self._previous_fix = self._latest_fix
        self._latest_fix = stored

        status_resp = self.get_status(now_utc=now)
        self._broadcast_status(status_resp)
        return status_resp

    def _lookup_route(self, route_id: Optional[str]):
        if not route_id:
            return None
        try:
            return self.routing_service.get_route(route_id)
        except KeyError:
            return None

    def _compute_route_relative(
        self,
        fix: _StoredTelemetryFix,
        route_id: Optional[str],
    ) -> Optional[RouteRelativeTelemetry]:
        route = self._lookup_route(route_id)
        if not route or len(route.vertices) < 2:
            return None

        verts = route.vertices
        best_seg_idx = 0
        best_cross = float("inf")
        best_along = 0.0

        for idx in range(len(verts) - 1):
            a = verts[idx]
            b = verts[idx + 1]
            cross_m, _, frac = _point_to_segment_projection_m(fix.lat, fix.lon_east, a, b)
            if cross_m < best_cross:
                best_cross = cross_m
                best_seg_idx = idx
                span = max(0.0, b.cumulative_distance_m - a.cumulative_distance_m)
                best_along = a.cumulative_distance_m + frac * span

        remaining = max(0.0, route.total_surface_distance_m - best_along)
        progress_frac = (
            min(1.0, max(0.0, best_along / route.total_surface_distance_m))
            if route.total_surface_distance_m > 0
            else 0.0
        )

        # Find next upcoming stop vertex ahead along track (or final destination)
        next_stop: Optional[RouteVertex] = None
        for v in verts:
            if v.is_stop and v.cumulative_distance_m > best_along + 1.0:
                next_stop = v
                break
        if next_stop is None:
            next_stop = verts[-1]

        dist_to_next, _ = _mars_sphere_distance_and_azimuth_m(
            fix.lat,
            fix.lon_east,
            next_stop.lat,
            next_stop.lon_east,
        )

        return RouteRelativeTelemetry(
            route_id=route.route_id,
            nearest_segment_index=best_seg_idx,
            along_track_distance_m=round(best_along, 2),
            cross_track_error_m=round(best_cross, 2),
            remaining_distance_m=round(remaining, 2),
            progress_fraction=round(progress_frac, 4),
            corridor_threshold_m=round(fix.corridor_threshold_m, 2),
            off_route=best_cross > fix.corridor_threshold_m,
            heading_deg=fix.heading_deg,
            next_waypoint_label=next_stop.stop_label or f"Waypoint #{next_stop.seq}",
            next_waypoint_lat=round(next_stop.lat, 6),
            next_waypoint_lon_east=round(next_stop.lon_east, 6),
            distance_to_next_waypoint_m=round(dist_to_next, 2),
        )

    def get_status(
        self,
        *,
        active_route_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> TrackingStatusResponse:
        now = now_utc or datetime.now(timezone.utc)
        token_configured = self.get_configured_token() is not None

        if self._latest_fix is None:
            return TrackingStatusResponse(
                status="disconnected",
                live_available=False,
                message=DISCONNECTED_LIVE_MESSAGE,
                is_simulation=False,
                ingest_token_configured=token_configured,
            )

        fix = self._latest_fix
        age_s = max(0.0, (now - fix.timestamp_utc).total_seconds())
        is_stale = age_s > fix.stale_after_seconds
        target_route_id = active_route_id or fix.active_route_id
        route_rel = self._compute_route_relative(fix, target_route_id)

        if is_stale:
            return TrackingStatusResponse(
                status="stale",
                live_available=False,
                message=(
                    f"Live Mars telemetry stale ({age_s:.1f}s > {fix.stale_after_seconds:.0f}s threshold) — "
                    "awaiting fresh fix from mission positioning provider."
                ),
                is_simulation=False,
                ingest_token_configured=token_configured,
                provider_id=fix.provider_id,
                session_id=fix.session_id,
                crs=fix.crs,
                sequence_number=fix.sequence_number,
                lat=fix.lat,
                lon_east=fix.lon_east,
                elevation_m=fix.elevation_m,
                horizontal_uncertainty_m=fix.horizontal_uncertainty_m,
                heading_deg=fix.heading_deg,
                fix_timestamp_utc=fix.timestamp_utc.isoformat(),
                age_seconds=round(age_s, 2),
                stale_after_seconds=fix.stale_after_seconds,
                route_relative=route_rel,
            )

        return TrackingStatusResponse(
            status="live",
            live_available=True,
            message=f"Live Mars position active via {fix.provider_id} (seq #{fix.sequence_number})",
            is_simulation=False,
            ingest_token_configured=token_configured,
            provider_id=fix.provider_id,
            session_id=fix.session_id,
            crs=fix.crs,
            sequence_number=fix.sequence_number,
            lat=fix.lat,
            lon_east=fix.lon_east,
            elevation_m=fix.elevation_m,
            horizontal_uncertainty_m=fix.horizontal_uncertainty_m,
            heading_deg=fix.heading_deg,
            fix_timestamp_utc=fix.timestamp_utc.isoformat(),
            age_seconds=round(age_s, 2),
            stale_after_seconds=fix.stale_after_seconds,
            route_relative=route_rel,
        )

    def preview_replan_from_live_fix(
        self,
        req: TrackingReplanPreviewRequest,
        *,
        now_utc: Optional[datetime] = None,
    ) -> TrackingReplanPreviewResponse:
        status_now = self.get_status(active_route_id=req.active_route_id, now_utc=now_utc)
        if not status_now.live_available or self._latest_fix is None:
            raise ValueError(
                "Cannot generate live replan preview without an active, non-stale mission positioning fix."
            )

        prev_route = self._lookup_route(req.active_route_id)
        if prev_route is None:
            raise LookupError(f"Active route '{req.active_route_id}' not found in server route cache.")

        dest_lat = (
            req.override_destination_lat
            if req.override_destination_lat is not None
            else prev_route.vertices[-1].lat
        )
        dest_lon = (
            req.override_destination_lon_east
            if req.override_destination_lon_east is not None
            else prev_route.vertices[-1].lon_east
        )

        # Keep replanning constrained to validated DEM coverage
        ds_id = req.dataset_id or prev_route.dataset_id
        fix = self._latest_fix

        compute_req = RouteComputeRequest(
            dataset_id=ds_id,
            start=RouteCoordinateInput(
                lat=fix.lat,
                lon_east=fix.lon_east,
                label=f"Live Position ({fix.provider_id} seq #{fix.sequence_number})",
            ),
            destination=RouteCoordinateInput(
                lat=dest_lat,
                lon_east=dest_lon,
                label=prev_route.vertices[-1].stop_label or "Objective",
            ),
            target_ids=[],
            waypoints=[],
            mode=req.mode or prev_route.mode,
            algorithm=req.algorithm or prev_route.algorithm,
        )
        proposed = self.routing_service.compute_route(compute_req)

        dur_delta: Optional[float] = None
        if prev_route.estimated_duration_seconds is not None and proposed.estimated_duration_seconds is not None:
            dur_delta = round(proposed.estimated_duration_seconds - prev_route.estimated_duration_seconds, 1)

        warnings: List[str] = []
        if fix.horizontal_uncertainty_m is not None and fix.horizontal_uncertainty_m > proposed.native_dem_resolution_m * 5.0:
            warnings.append(
                f"Live fix 1-sigma uncertainty ({fix.horizontal_uncertainty_m:.1f} m) exceeds 5x DEM cell size ({proposed.native_dem_resolution_m:.2f} m)."
            )

        return TrackingReplanPreviewResponse(
            requires_user_confirmation=True,
            live_fix_used={
                "provider_id": fix.provider_id,
                "sequence_number": fix.sequence_number,
                "lat": fix.lat,
                "lon_east": fix.lon_east,
                "timestamp_utc": fix.timestamp_utc.isoformat(),
                "horizontal_uncertainty_m": fix.horizontal_uncertainty_m,
            },
            coverage_verified=True,
            dem_dataset_id=proposed.dataset_id,
            dem_source_product_id=proposed.source_product_id,
            dem_resolution_m=proposed.native_dem_resolution_m,
            previous_route_id=prev_route.route_id,
            proposed_route=proposed,
            distance_delta_m=round(proposed.total_surface_distance_m - prev_route.total_surface_distance_m, 2),
            elevation_gain_delta_m=round(proposed.total_elevation_gain_m - prev_route.total_elevation_gain_m, 2),
            max_slope_delta_deg=round(proposed.max_slope_deg - prev_route.max_slope_deg, 2),
            duration_delta_seconds=dur_delta,
            warnings=warnings,
            notes=(
                "Preview only — active route is NOT modified automatically. User must explicitly confirm before adopting proposed trajectory."
            ),
        )

    def clear_session(self) -> TrackingStatusResponse:
        self._previous_fix = None
        self._latest_fix = None
        resp = self.get_status()
        self._broadcast_status(resp)
        return resp

    def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=32)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    def _broadcast_status(self, status_resp: TrackingStatusResponse) -> None:
        payload = status_resp.model_dump()
        dead: List[asyncio.Queue[Dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)
