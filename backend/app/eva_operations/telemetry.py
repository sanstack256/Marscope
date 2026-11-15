"""
MARSCOPE Conditional Telemetry Adapter Architecture (Prompt 20 Part 9).

Provides a provider-neutral telemetry adapter interface that defaults honestly to:
  - connection_status: 'TELEMETRY NOT CONNECTED'
  - crew_state_status: 'LIVE CREW STATE UNAVAILABLE'
  - freshness_state: 'NOT_CONNECTED'

Enforces:
  - 7 explicit freshness states: LIVE, RECENT, STALE, EXPIRED, INVALID, UNAVAILABLE, NOT_CONNECTED
  - Strict Mars planetocentric CRS validation (IAU2000:49900 / IAU:49900 / EPSG:104905)
  - Rejection of consumer/browser GPS or simulated telemetry providers
  - Monotonic sequence_number and timestamp ordering (duplicate/out-of-order rejection)
  - Unit validation on optional consumables channels
  - Operator/tracking token authentication on ingestion
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hmac
import math
import os
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


ALLOWED_MARS_TELEMETRY_CRS = {"IAU2000:49900", "IAU:49900", "EPSG:104905"}
PROHIBITED_TELEMETRY_PROVIDERS = {
    "browser_geolocation",
    "navigator.geolocation",
    "device_gps",
    "fake_gps",
    "mock_telemetry",
    "simulated_stream",
}


class TelemetryFreshnessState(str, Enum):
    """7 explicit telemetry freshness states (Prompt 20 Part 9.2)."""

    LIVE = "LIVE"
    RECENT = "RECENT"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONNECTED = "NOT_CONNECTED"


class TelemetryConsumableSample(BaseModel):
    """Optional authenticated consumable channel reading with explicit unit check."""

    channel_name: str = Field(..., min_length=1, max_length=64)
    value: float
    unit: str = Field(..., min_length=1, max_length=24)


class TelemetryPacketIngestRequest(BaseModel):
    """Authenticated Mars surface telemetry packet from an external mission provider."""

    provider_id: str = Field(..., min_length=2, max_length=80)
    session_id: str = Field(..., min_length=2, max_length=80)
    sequence_number: int = Field(..., ge=1)
    timestamp_utc: datetime
    crs: str = Field(default="IAU2000:49900")
    lat: float
    lon_east: float
    elevation_m: Optional[float] = None
    horizontal_uncertainty_m: Optional[float] = Field(default=None, ge=0.0)
    heading_deg: Optional[float] = Field(default=None, ge=0.0, lt=360.0)
    consumables: List[TelemetryConsumableSample] = Field(default_factory=list)
    live_threshold_s: float = Field(default=15.0, gt=0.0, le=300.0)
    stale_threshold_s: float = Field(default=60.0, gt=1.0, le=1800.0)
    expired_threshold_s: float = Field(default=300.0, gt=5.0, le=7200.0)


class TelemetryAdapterStatusResponse(BaseModel):
    """Honest status report for the conditional telemetry adapter (Part 9.1 & 9.2)."""

    adapter_name: str = "MARSCOPE Provider-Neutral Surface Telemetry Adapter"
    adapter_version: str = "2.0.0"
    connected: bool = False
    connection_status: str = "TELEMETRY NOT CONNECTED"
    crew_state_status: str = "LIVE CREW STATE UNAVAILABLE"
    freshness_state: TelemetryFreshnessState = TelemetryFreshnessState.NOT_CONNECTED
    classification: str = "UNAVAILABLE"
    auth_token_configured: bool = False
    provider_id: Optional[str] = None
    session_id: Optional[str] = None
    sequence_number: Optional[int] = None
    crs: Optional[str] = None
    lat: Optional[float] = None
    lon_east: Optional[float] = None
    elevation_m: Optional[float] = None
    horizontal_uncertainty_m: Optional[float] = None
    heading_deg: Optional[float] = None
    packet_timestamp_utc: Optional[str] = None
    age_seconds: Optional[float] = None
    consumables: List[TelemetryConsumableSample] = Field(default_factory=list)
    rejected_packet_count: int = 0
    last_rejection_reason: Optional[str] = None
    disclosures: List[str] = Field(
        default_factory=lambda: [
            "TELEMETRY NOT CONNECTED — No live astronaut tracking or suit telemetry stream is active by default.",
            "LIVE CREW STATE UNAVAILABLE — MARSCOPE never fabricates heart rate, suit pressure, O2 reserve, or simulated GPS positions.",
        ]
    )


_ALLOWED_CONSUMABLE_UNITS = {"kg", "g", "l", "wh", "kj", "kpa", "pa", "v", "a", "w", "%"}


class ConditionalTelemetryAdapter:
    """Provider-neutral telemetry adapter enforcing strict freshness, CRS, sequence, and unit rules."""

    def __init__(self, explicit_token: Optional[str] = None) -> None:
        self._explicit_token = explicit_token
        self._latest_packet: Optional[TelemetryPacketIngestRequest] = None
        self._configured_provider_id: Optional[str] = None
        self._rejected_count: int = 0
        self._last_rejection_reason: Optional[str] = None

    def get_expected_token(self) -> Optional[str]:
        if self._explicit_token and self._explicit_token.strip():
            return self._explicit_token.strip()
        for env_key in ("MARSCOPE_TRACKING_TOKEN", "MARSCOPE_OPERATOR_TOKEN"):
            val = os.getenv(env_key)
            if val and val.strip():
                return val.strip()
        return None

    def verify_auth(
        self,
        authorization_header: Optional[str] = None,
        x_operator_token: Optional[str] = None,
        x_tracking_token: Optional[str] = None,
    ) -> Tuple[bool, int, str]:
        expected = self.get_expected_token()
        if not expected:
            return (
                False,
                403,
                "Telemetry ingestion is disabled because no server token is configured (MARSCOPE_OPERATOR_TOKEN / MARSCOPE_TRACKING_TOKEN).",
            )
        provided: Optional[str] = None
        for cand in (x_tracking_token, x_operator_token):
            if cand and cand.strip():
                provided = cand.strip()
                break
        if not provided and authorization_header and authorization_header.strip():
            parts = authorization_header.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                provided = parts[1].strip()
        if not provided:
            return False, 401, "Missing telemetry authentication token."
        if not hmac.compare_digest(provided, expected):
            return False, 403, "Invalid telemetry authentication token."
        return True, 200, "ok"

    def reset(self) -> TelemetryAdapterStatusResponse:
        self._latest_packet = None
        self._configured_provider_id = None
        self._last_rejection_reason = None
        return self.get_status()

    def connect_provider(self, provider_id: str) -> TelemetryAdapterStatusResponse:
        prov_clean = provider_id.strip().lower()
        if prov_clean in PROHIBITED_TELEMETRY_PROVIDERS:
            self._rejected_count += 1
            self._last_rejection_reason = f"Prohibited consumer/simulated telemetry provider '{provider_id}'."
            raise ValueError(self._last_rejection_reason)
        self._configured_provider_id = provider_id.strip()
        self._last_rejection_reason = None
        return self.get_current_state()

    def disconnect_provider(self) -> TelemetryAdapterStatusResponse:
        return self.reset()

    def get_current_state(self, mission_id: Optional[str] = None) -> TelemetryAdapterStatusResponse:
        status = self.get_status()
        if self._latest_packet is None and self._configured_provider_id is not None:
            status.provider_id = self._configured_provider_id
            status.connection_status = f"REGISTERED ({self._configured_provider_id}) — AWAITING PACKET"
            status.crew_state_status = "LIVE CREW STATE UNAVAILABLE"
            status.freshness_state = TelemetryFreshnessState.UNAVAILABLE
        return status

    def ingest_packet(
        self,
        packet: TelemetryPacketIngestRequest,
        *,
        now_utc: Optional[datetime] = None,
    ) -> TelemetryAdapterStatusResponse:
        now = now_utc or datetime.now(timezone.utc)

        def _reject(reason: str) -> None:
            self._rejected_count += 1
            self._last_rejection_reason = reason
            raise ValueError(reason)

        prov_clean = packet.provider_id.strip().lower()
        if prov_clean in PROHIBITED_TELEMETRY_PROVIDERS:
            _reject(f"Prohibited consumer/simulated telemetry provider '{packet.provider_id}'.")

        crs_clean = packet.crs.strip().upper()
        if crs_clean not in ALLOWED_MARS_TELEMETRY_CRS:
            _reject(f"Invalid telemetry CRS '{packet.crs}'; must be Mars planetocentric IAU2000:49900.")

        if not (math.isfinite(packet.lat) and -90.0 <= packet.lat <= 90.0):
            _reject(f"Telemetry latitude {packet.lat} out of valid [-90, 90] deg range.")

        if not (math.isfinite(packet.lon_east) and 0.0 <= packet.lon_east < 360.0):
            _reject(f"Telemetry lon_east {packet.lon_east} out of valid [0, 360) deg range.")

        if packet.timestamp_utc.tzinfo is None:
            _reject("Telemetry timestamp_utc must include an explicit UTC timezone.")

        ts_utc = packet.timestamp_utc.astimezone(timezone.utc)
        if (ts_utc - now).total_seconds() > 60.0:
            _reject("Telemetry timestamp_utc is more than 60s in the future.")

        for c in packet.consumables:
            if not math.isfinite(c.value) or c.value < 0.0:
                _reject(f"Invalid negative or non-finite consumable value for '{c.channel_name}'.")
            if c.unit.strip().lower() not in _ALLOWED_CONSUMABLE_UNITS:
                _reject(
                    f"Unsupported consumable unit '{c.unit}' for '{c.channel_name}'; allowed: {sorted(_ALLOWED_CONSUMABLE_UNITS)}."
                )

        if self._latest_packet is not None and self._latest_packet.session_id == packet.session_id:
            if packet.sequence_number <= self._latest_packet.sequence_number:
                self._rejected_count += 1
                self._last_rejection_reason = (
                    f"Duplicate or out-of-order sequence_number={packet.sequence_number} "
                    f"(expected > {self._latest_packet.sequence_number})."
                )
                raise LookupError(self._last_rejection_reason)
            prev_ts = self._latest_packet.timestamp_utc.astimezone(timezone.utc)
            if ts_utc < prev_ts:
                _reject("Telemetry packet timestamp regressed earlier than previous packet.")

        self._latest_packet = packet
        self._last_rejection_reason = None
        return self.get_status(now_utc=now)

    def get_status(self, *, now_utc: Optional[datetime] = None) -> TelemetryAdapterStatusResponse:
        now = now_utc or datetime.now(timezone.utc)
        tok_ok = self.get_expected_token() is not None

        if self._latest_packet is None:
            fresh = (
                TelemetryFreshnessState.INVALID
                if self._last_rejection_reason is not None
                else TelemetryFreshnessState.NOT_CONNECTED
            )
            return TelemetryAdapterStatusResponse(
                connected=False,
                connection_status="TELEMETRY NOT CONNECTED",
                crew_state_status="LIVE CREW STATE UNAVAILABLE",
                freshness_state=fresh,
                classification="UNAVAILABLE",
                auth_token_configured=tok_ok,
                rejected_packet_count=self._rejected_count,
                last_rejection_reason=self._last_rejection_reason,
            )

        pkt = self._latest_packet
        ts_utc = pkt.timestamp_utc.astimezone(timezone.utc)
        age_s = max(0.0, (now - ts_utc).total_seconds())

        if age_s <= pkt.live_threshold_s:
            fresh = TelemetryFreshnessState.LIVE
            conn_str = f"CONNECTED ({pkt.provider_id} — LIVE)"
            crew_str = "AUTHENTICATED TELEMETRY FIX AVAILABLE"
        elif age_s <= pkt.stale_threshold_s:
            fresh = TelemetryFreshnessState.RECENT
            conn_str = f"CONNECTED ({pkt.provider_id} — RECENT)"
            crew_str = "RECENT AUTHENTICATED TELEMETRY FIX"
        elif age_s <= pkt.expired_threshold_s:
            fresh = TelemetryFreshnessState.STALE
            conn_str = f"TELEMETRY STALE ({age_s:.1f}s > {pkt.stale_threshold_s:.0f}s)"
            crew_str = "LIVE CREW STATE STALE"
        else:
            fresh = TelemetryFreshnessState.EXPIRED
            conn_str = f"TELEMETRY EXPIRED ({age_s:.1f}s > {pkt.expired_threshold_s:.0f}s)"
            crew_str = "LIVE CREW STATE UNAVAILABLE (EXPIRED)"

        return TelemetryAdapterStatusResponse(
            connected=fresh in (TelemetryFreshnessState.LIVE, TelemetryFreshnessState.RECENT),
            connection_status=conn_str,
            crew_state_status=crew_str,
            freshness_state=fresh,
            classification="DIRECTLY_MEASURED" if fresh in (TelemetryFreshnessState.LIVE, TelemetryFreshnessState.RECENT) else "UNAVAILABLE",
            auth_token_configured=tok_ok,
            provider_id=pkt.provider_id,
            session_id=pkt.session_id,
            sequence_number=pkt.sequence_number,
            crs="IAU2000:49900",
            lat=pkt.lat,
            lon_east=pkt.lon_east,
            elevation_m=pkt.elevation_m,
            horizontal_uncertainty_m=pkt.horizontal_uncertainty_m,
            heading_deg=pkt.heading_deg,
            packet_timestamp_utc=ts_utc.isoformat(),
            age_seconds=round(age_s, 2),
            consumables=list(pkt.consumables),
            rejected_packet_count=self._rejected_count,
            last_rejection_reason=self._last_rejection_reason,
            disclosures=[
                f"Telemetry freshness state: {fresh.value} (packet age {age_s:.1f}s).",
                "Only authenticated provider channels are reported; unprovided suit metrics remain UNAVAILABLE.",
            ],
        )


TelemetryPacketInput = TelemetryPacketIngestRequest
TelemetryIngestResult = TelemetryAdapterStatusResponse
