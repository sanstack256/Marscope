"""
Authenticated Live Mission Tracking & Route-Relative Telemetry Schemas
MARSCOPE - Strictly separates authenticated Mars positioning telemetry from simulation.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.routing.schemas import PathAlgorithm, RouteComputeResponse, RoutingMode


DISCONNECTED_LIVE_MESSAGE = "Live Mars position unavailable — no mission positioning provider connected."


class TelemetryFixIngestRequest(BaseModel):
    provider_id: str = Field(..., min_length=2, max_length=120, description="Authenticated mission positioning provider ID")
    session_id: str = Field("default_eva_session", min_length=1, max_length=120)
    sequence_number: int = Field(..., ge=0, description="Strictly increasing telemetry packet sequence number")
    timestamp_utc: datetime = Field(..., description="UTC ISO-8601 observation timestamp of the fix")
    crs: str = Field("IAU2000:49900", description="Must be Mars planetary CRS IAU2000:49900")
    lat: float = Field(..., description="Planetocentric latitude in [-90, 90]")
    lon_east: float = Field(..., description="East-positive longitude in [0, 360)")
    elevation_m: Optional[float] = Field(None, description="Optional external altitude/elevation estimate (m)")
    horizontal_uncertainty_m: Optional[float] = Field(None, ge=0.0, description="Reported 1-sigma horizontal position uncertainty (m)")
    heading_deg: Optional[float] = Field(None, ge=0.0, lt=360.0, description="Optional True North heading [0, 360)")
    active_route_id: Optional[str] = Field(None, description="Route ID to project route-relative progress against")
    corridor_threshold_m: float = Field(25.0, ge=5.0, le=500.0, description="Cross-track off-route threshold (m)")
    stale_after_seconds: float = Field(30.0, ge=2.0, le=3600.0, description="Stale fix timeout threshold (seconds)")


class RouteRelativeTelemetry(BaseModel):
    route_id: str
    nearest_segment_index: int
    along_track_distance_m: float
    cross_track_error_m: float
    remaining_distance_m: float
    progress_fraction: float
    corridor_threshold_m: float
    off_route: bool
    heading_deg: Optional[float] = None
    next_waypoint_label: Optional[str] = None
    next_waypoint_lat: Optional[float] = None
    next_waypoint_lon_east: Optional[float] = None
    distance_to_next_waypoint_m: Optional[float] = None


class TrackingStatusResponse(BaseModel):
    status: Literal["disconnected", "live", "stale"]
    live_available: bool
    message: str
    is_simulation: bool = False
    ingest_token_configured: bool
    provider_id: Optional[str] = None
    session_id: Optional[str] = None
    crs: str = "IAU2000:49900"
    sequence_number: Optional[int] = None
    lat: Optional[float] = None
    lon_east: Optional[float] = None
    elevation_m: Optional[float] = None
    horizontal_uncertainty_m: Optional[float] = None
    heading_deg: Optional[float] = None
    fix_timestamp_utc: Optional[str] = None
    age_seconds: Optional[float] = None
    stale_after_seconds: Optional[float] = None
    route_relative: Optional[RouteRelativeTelemetry] = None


class TrackingReplanPreviewRequest(BaseModel):
    active_route_id: str
    dataset_id: Optional[str] = None
    mode: Optional[RoutingMode] = None
    algorithm: Optional[PathAlgorithm] = None
    override_destination_lat: Optional[float] = None
    override_destination_lon_east: Optional[float] = None


class TrackingReplanPreviewResponse(BaseModel):
    requires_user_confirmation: bool = True
    live_fix_used: Dict[str, Any]
    coverage_verified: bool
    dem_dataset_id: str
    dem_source_product_id: str
    dem_resolution_m: float
    previous_route_id: str
    proposed_route: RouteComputeResponse
    distance_delta_m: float
    elevation_gain_delta_m: float
    max_slope_delta_deg: float
    duration_delta_seconds: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    notes: str
