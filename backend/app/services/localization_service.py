"""
MARSCOPE Location Acquisition Service
Martian Surface Intelligence & Exploration System

Implements localization provider architecture supporting:
- Mission live positioning feed (disconnected / unavailable until authorized integration)
- Suit or rover telemetry adapter (disconnected / unavailable until authorized integration)
- Manual operator coordinate selection
- Explicit isolated test fixtures for automated test suites only

Never uses browser GPS and never invents a default Martian coordinate.
"""

from datetime import datetime, timezone
from typing import Optional
from app.geospatial.crs import validate_mars_coordinates, validate_mars_crs
from app.schemas.localization import (
    LocalizationProviderDescriptor,
    LocalizationStatusResponse,
    ManualPositionRequest,
    PositionRecord,
    PositionSourceType,
    PositionValidityState,
)


class LocalizationService:
    def __init__(self) -> None:
        self._current_position: Optional[PositionRecord] = None
        self._mission_feed_connected: bool = False
        self._suit_adapter_connected: bool = False

    def get_status(self) -> LocalizationStatusResponse:
        providers = [
            LocalizationProviderDescriptor(
                provider_id="mission_live_feed",
                provider_type=PositionSourceType.MISSION_LIVE_FEED,
                name="Mission Operations Positioning Feed",
                connected=self._mission_feed_connected,
                status_detail="Unavailable — no authorized live mission telemetry feed connected.",
            ),
            LocalizationProviderDescriptor(
                provider_id="suit_rover_telemetry",
                provider_type=PositionSourceType.SUIT_ROVER_TELEMETRY,
                name="EVA Suit / Rover Telemetry Adapter",
                connected=self._suit_adapter_connected,
                status_detail="Unavailable — no authorized suit/rover telemetry hardware linked.",
            ),
            LocalizationProviderDescriptor(
                provider_id="manual_selection",
                provider_type=PositionSourceType.MANUAL_SELECTION,
                name="Manual Operator Coordinate Selection",
                connected=True,
                status_detail="Ready for validated operator-selected IAU2000 coordinates.",
            ),
        ]

        live_available = self._mission_feed_connected or self._suit_adapter_connected
        active_provider = (
            self._current_position.position_source
            if self._current_position is not None
            else PositionSourceType.UNAVAILABLE
        )
        unavailable_reason = None
        if not live_available:
            unavailable_reason = (
                "Live Mars positioning is unavailable: no authorized mission feed or suit/rover telemetry adapter "
                "is connected. Browser GPS cannot locate an explorer on Mars. Use manual map coordinate selection."
            )

        return LocalizationStatusResponse(
            live_localization_available=live_available,
            active_provider=active_provider,
            unavailable_reason=unavailable_reason,
            current_position=self._current_position,
            supported_providers=providers,
        )

    def set_manual_position(
        self,
        req: ManualPositionRequest,
        sampled_elevation_m: Optional[float] = None,
    ) -> PositionRecord:
        if not validate_mars_crs(req.crs):
            raise ValueError(f"Rejected invalid or non-Martian CRS '{req.crs}' for position selection.")

        lat, lon = validate_mars_coordinates(
            req.latitude,
            req.longitude,
            latitude_convention=req.latitude_convention,
            longitude_direction=req.longitude_direction,
        )

        notes = [
            "Manually positioned by operator; not a live telemetry fix.",
        ]
        if sampled_elevation_m is None:
            notes.append("Elevation is unknown/unavailable at this location from validated local DEMs.")

        record = PositionRecord(
            position_source=PositionSourceType.MANUAL_SELECTION,
            latitude=lat,
            longitude=lon,
            elevation_m=sampled_elevation_m,
            crs=req.crs,
            latitude_convention=req.latitude_convention,
            longitude_direction="East",
            timestamp_utc=datetime.now(timezone.utc),
            accuracy_meters=req.accuracy_meters,
            validity_state=PositionValidityState.VALID,
            provenance=req.provenance,
            notes=notes,
        )
        self._current_position = record
        return record

    def set_test_fixture_position(self, latitude: float, longitude: float, crs: str = "IAU2000:49900") -> PositionRecord:
        """Strictly isolated helper for automated unit/integration test fixtures."""
        lat, lon = validate_mars_coordinates(latitude, longitude)
        record = PositionRecord(
            position_source=PositionSourceType.TEST_FIXTURE,
            latitude=lat,
            longitude=lon,
            elevation_m=None,
            crs=crs,
            latitude_convention="Planetocentric",
            longitude_direction="East",
            timestamp_utc=datetime.now(timezone.utc),
            accuracy_meters=None,
            validity_state=PositionValidityState.UNVERIFIED,
            provenance="Automated unit test fixture (non-operational)",
            notes=["ISOLATED TEST FIXTURE — NOT OPERATIONAL DATA"],
        )
        self._current_position = record
        return record

    def clear_position(self) -> LocalizationStatusResponse:
        self._current_position = None
        return self.get_status()
