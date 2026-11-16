"""
Pydantic Schemas for Multi-Astronaut Mission Foundation, Auth, Collaboration,
Emergency SOS, Voice Notes, Field Observations, Landing-Site Intelligence & Audit Events.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


MissionRole = Literal["MISSION_LEAD", "ASTRONAUT", "MISSION_OPERATOR"]
MembershipStatus = Literal["ACTIVE", "LEFT", "REMOVED"]
CrewConnectionStatus = Literal[
    "CONNECTED",
    "DISCONNECTED",
    "POSITION_STALE",
    "POSITION_UNAVAILABLE",
    "LOCATION_SHARING_DISABLED",
    "UNKNOWN",
]
ObservationCategory = Literal[
    "MINERAL_DISCOVERY",
    "HAZARD_REPORT",
    "SAMPLE_NOTE",
    "TERRAIN_ANOMALY",
    "SCIENCE_NOTE",
]
ObservationEpistemicState = Literal[
    "USER_REPORTED",
    "UNVERIFIED",
    "CORROBORATED_BY_EVIDENCE",
    "CONTESTED",
    "RETRACTED",
]
SosStatus = Literal[
    "ACTIVE",
    "DELIVERED_TO_CREW_DEVICE",
    "ACKNOWLEDGED_BY_CREW",
    "RESOLVED",
    "CANCELLED",
]
LandingSiteRegistrationState = Literal["LANDING_SITE_UNCONFIGURED", "REGISTERED"]


# ---------------------------------------------------------------------------
# Astronaut Auth & Profile
# ---------------------------------------------------------------------------


class OperationalAssumedField(BaseModel):
    value: Optional[float] = None
    unit: str = "kg"
    classification: Literal["USER_ASSUMED", "NOT_PROVIDED"] = "NOT_PROVIDED"
    updated_at_utc: Optional[str] = None
    source: Optional[str] = None


class AstronautProfileResponse(BaseModel):
    astronaut_id: str
    email: str
    display_name: str
    is_active: bool
    body_mass_kg: Optional[float] = None
    body_mass_meta: OperationalAssumedField
    suit_mass_kg: Optional[float] = None
    suit_mass_meta: OperationalAssumedField
    equipment_mass_kg: Optional[float] = None
    equipment_mass_meta: OperationalAssumedField
    total_mass_kg: Optional[float] = None
    mobility_constraints: Optional[str] = None
    emergency_contact: Optional[str] = None
    profile_visibility: Literal["mission_members", "private"] = "mission_members"
    profile_edit_history: List[Dict[str, Any]] = Field(default_factory=list)
    is_demo: bool = False
    created_at_utc: str
    updated_at_utc: str


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=10, max_length=128)
    display_name: str = Field(..., min_length=2, max_length=80)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        s = v.strip().lower()
        if "@" not in s or "." not in s.split("@", 1)[1]:
            raise ValueError("A valid email address is required.")
        return s

    @field_validator("display_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Display name must contain at least 2 visible characters.")
        return s


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        return v.strip().lower()


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    body_mass_kg: Optional[float] = Field(default=None, gt=20.0, le=250.0)
    suit_mass_kg: Optional[float] = Field(default=None, gt=5.0, le=250.0)
    equipment_mass_kg: Optional[float] = Field(default=None, ge=0.0, le=250.0)
    clear_body_mass: bool = False
    clear_suit_mass: bool = False
    clear_equipment_mass: bool = False
    mobility_constraints: Optional[str] = Field(default=None, max_length=500)
    emergency_contact: Optional[str] = Field(default=None, max_length=300)
    profile_visibility: Optional[Literal["mission_members", "private"]] = None


class SessionInfoResponse(BaseModel):
    session_id: str
    user_agent: Optional[str] = None
    created_at_utc: str
    expires_at_utc: str
    last_seen_at_utc: str
    revoked_at_utc: Optional[str] = None
    is_current: bool = False


class AuthSessionResponse(BaseModel):
    authenticated: bool
    astronaut: Optional[AstronautProfileResponse] = None
    csrf_token: Optional[str] = None
    session_id: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        return v.strip().lower()


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=256)
    new_password: str = Field(..., min_length=10, max_length=128)


# ---------------------------------------------------------------------------
# Missions, Memberships & Invitations
# ---------------------------------------------------------------------------


class CreateMissionRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    description: str = Field(default="", max_length=1000)
    objective: str = Field(default="", max_length=500)
    operating_region: Optional[str] = Field(default=None, max_length=160)
    planned_start_utc: Optional[str] = None
    planned_end_utc: Optional[str] = None
    visibility: Literal["private", "invite_only"] = "private"


class UpdateMissionRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    objective: Optional[str] = Field(default=None, max_length=500)
    operating_region: Optional[str] = Field(default=None, max_length=160)
    planned_start_utc: Optional[str] = None
    planned_end_utc: Optional[str] = None
    status: Optional[Literal["ACTIVE", "PLANNING", "ARCHIVED"]] = None


class MissionSummaryResponse(BaseModel):
    mission_id: str
    name: str
    description: str
    objective: str
    lead_astronaut_id: str
    operating_region: Optional[str] = None
    planned_start_utc: Optional[str] = None
    planned_end_utc: Optional[str] = None
    visibility: str
    membership_policy: str
    status: str
    landing_site_status: LandingSiteRegistrationState
    my_role: MissionRole
    active_member_count: int
    active_sos_count: int = 0
    is_demo: bool = False
    created_at_utc: str
    updated_at_utc: str


class CreateInvitationRequest(BaseModel):
    role_on_join: MissionRole = "ASTRONAUT"
    expires_in_hours: int = Field(default=24, ge=1, le=720)
    single_use: bool = False
    max_uses: Optional[int] = Field(default=None, ge=1, le=100)


class InvitationResponse(BaseModel):
    invite_id: str
    mission_id: str
    created_by: str
    role_on_join: MissionRole
    single_use: bool
    max_uses: Optional[int] = None
    uses_count: int
    expires_at_utc: str
    revoked_at_utc: Optional[str] = None
    created_at_utc: str
    invite_token: Optional[str] = None


class JoinMissionRequest(BaseModel):
    invite_token: str = Field(..., min_length=12, max_length=256)


class UpdateMemberRoleRequest(BaseModel):
    role: MissionRole


class CrewMemberResponse(BaseModel):
    astronaut_id: str
    display_name: str
    role: MissionRole
    membership_status: MembershipStatus
    location_sharing_enabled: bool
    connection_status: CrewConnectionStatus
    joined_at_utc: str
    latest_position: Optional["CrewPositionResponse"] = None
    body_mass_kg: Optional[float] = None
    suit_mass_kg: Optional[float] = None
    equipment_mass_kg: Optional[float] = None
    total_mass_kg: Optional[float] = None
    mass_classification: Optional[str] = None
    emergency_contact: Optional[str] = None
    is_demo: bool = False


# ---------------------------------------------------------------------------
# Crew Positions (IAU2000:49900)
# ---------------------------------------------------------------------------


class IngestPositionRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-360.0, le=360.0)
    crs: str = Field(default="IAU2000:49900", max_length=64)
    latitude_convention: Literal["planetocentric", "planetographic"] = "planetocentric"
    longitude_direction: Literal["east_0_360", "east_signed_180"] = "east_0_360"
    uncertainty_m: Optional[float] = Field(default=None, ge=0.0, le=100000.0)
    source_id: str = Field(..., min_length=2, max_length=120)
    source_classification: Literal["TELEMETRY_PROVIDER", "LOCALIZATION_SOLVER", "USER_PROVIDED"]
    sequence_number: int = Field(default=0, ge=0)
    measured_at_utc: Optional[str] = None
    client_event_id: Optional[str] = Field(default=None, max_length=128)


class ToggleLocationSharingRequest(BaseModel):
    location_sharing_enabled: bool


class CrewPositionResponse(BaseModel):
    position_id: str
    mission_id: str
    astronaut_id: str
    display_name: Optional[str] = None
    latitude: float
    longitude_east: float
    crs: str
    latitude_convention: str
    longitude_direction: str
    elevation_m: Optional[float] = None
    elevation_source: Optional[str] = None
    uncertainty_m: Optional[float] = None
    source_id: str
    source_classification: str
    sequence_number: int
    measured_at_utc: str
    received_at_utc: str
    age_seconds: float
    is_stale: bool
    validation_status: str


# ---------------------------------------------------------------------------
# Emergency SOS & Voice Notes
# ---------------------------------------------------------------------------


class TriggerSosRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=1000)
    voice_note_id: Optional[str] = Field(default=None, max_length=128)
    explicit_latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    explicit_longitude: Optional[float] = Field(default=None, ge=-360.0, le=360.0)
    explicit_crs: str = Field(default="IAU2000:49900", max_length=64)
    client_event_id: Optional[str] = Field(default=None, max_length=128)
    client_timestamp_utc: Optional[str] = None


class SosActionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class SosAcknowledgementResponse(BaseModel):
    ack_id: str
    sos_id: str
    astronaut_id: str
    display_name: str
    ack_type: Literal["DELIVERED_TO_CREW_DEVICE", "ACKNOWLEDGED_BY_CREW", "RESOLVED", "CANCELLED"]
    note: Optional[str] = None
    created_at_utc: str


class VoiceNoteResponse(BaseModel):
    voice_note_id: str
    mission_id: str
    astronaut_id: str
    display_name: Optional[str] = None
    linked_event_type: Optional[str] = None
    linked_event_id: Optional[str] = None
    mime_type: str
    file_size_bytes: int
    duration_seconds: Optional[float] = None
    sha256_checksum: str
    upload_status: str
    playback_url: str
    created_at_utc: str


class SosEventResponse(BaseModel):
    sos_id: str
    mission_id: str
    astronaut_id: str
    astronaut_display_name: str
    event_type: str
    status: SosStatus
    client_event_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude_east: Optional[float] = None
    elevation_m: Optional[float] = None
    crs: Optional[str] = None
    position_source: Optional[str] = None
    position_classification: Optional[str] = None
    position_age_s: Optional[float] = None
    position_status: str
    message: Optional[str] = None
    voice_note: Optional[VoiceNoteResponse] = None
    acknowledgements: List[SosAcknowledgementResponse] = Field(default_factory=list)
    created_at_utc: str
    server_received_at_utc: str
    updated_at_utc: str


# ---------------------------------------------------------------------------
# Field Observations
# ---------------------------------------------------------------------------


class CreateFieldObservationRequest(BaseModel):
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-360.0, le=360.0)
    crs: str = Field(default="IAU2000:49900", max_length=64)
    coordinate_source: Literal["USER_REPORTED", "ACTIVE_POSITION_SNAPSHOT", "UNKNOWN"] = "USER_REPORTED"
    uncertainty_m: Optional[float] = Field(default=None, ge=0.0, le=100000.0)
    target_id: Optional[str] = Field(default=None, max_length=120)
    category: ObservationCategory
    species_name: Optional[str] = Field(default=None, max_length=160)
    description: str = Field(..., min_length=2, max_length=2000)
    instrument_id: Optional[str] = Field(default=None, max_length=120)
    source_product_id: Optional[str] = Field(default=None, max_length=160)
    calibration_metadata: Optional[str] = Field(default=None, max_length=400)
    evidence_ids: List[str] = Field(default_factory=list, max_length=32)
    voice_note_id: Optional[str] = Field(default=None, max_length=128)
    offline_created_at_utc: Optional[str] = None
    client_event_id: Optional[str] = Field(default=None, max_length=128)


class UpdateFieldObservationRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    description: Optional[str] = Field(default=None, min_length=2, max_length=2000)
    target_id: Optional[str] = Field(default=None, max_length=120)
    species_name: Optional[str] = Field(default=None, max_length=160)
    annotation_note: Optional[str] = Field(default=None, max_length=500)


class ReviewFieldObservationRequest(BaseModel):
    expected_version: int = Field(..., ge=1)
    epistemic_state: ObservationEpistemicState
    review_note: Optional[str] = Field(default=None, max_length=500)
    evidence_ids: List[str] = Field(default_factory=list, max_length=32)


class FieldObservationResponse(BaseModel):
    observation_id: str
    mission_id: str
    astronaut_id: str
    astronaut_display_name: str
    client_event_id: Optional[str] = None
    version: int
    latitude: Optional[float] = None
    longitude_east: Optional[float] = None
    elevation_m: Optional[float] = None
    crs: str
    coordinate_source: str
    uncertainty_m: Optional[float] = None
    target_id: Optional[str] = None
    category: ObservationCategory
    species_canonical_id: Optional[str] = None
    species_display_name: Optional[str] = None
    description: str
    epistemic_state: ObservationEpistemicState
    instrument_id: Optional[str] = None
    source_product_id: Optional[str] = None
    calibration_metadata: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    voice_note: Optional[VoiceNoteResponse] = None
    offline_created_at_utc: Optional[str] = None
    synced_at_utc: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    audit_history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at_utc: str
    updated_at_utc: str


# ---------------------------------------------------------------------------
# Landing-Site Intelligence & Algorithmic 3D Perimeter
# ---------------------------------------------------------------------------


class RegisterLandingSiteRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-360.0, le=360.0)
    crs: str = Field(default="IAU2000:49900", max_length=64)
    latitude_convention: Literal["planetocentric", "planetographic"] = "planetocentric"
    longitude_direction: Literal["east_0_360", "east_signed_180"] = "east_0_360"
    source: Literal["USER_PROVIDED", "DATASET_CATALOG_MATCH", "GAZETTEER_CATALOG"] = "USER_PROVIDED"
    source_record_id: Optional[str] = Field(default=None, max_length=160)
    uncertainty_m: Optional[float] = Field(default=None, ge=0.0, le=100000.0)


class ComputePerimeterRequest(BaseModel):
    max_slope_deg: Optional[float] = Field(default=None, gt=0.0, le=60.0)
    max_roughness_m: Optional[float] = Field(default=None, gt=0.0, le=50.0)
    max_radius_m: Optional[float] = Field(default=None, gt=10.0, le=20000.0)
    min_contiguous_cells: int = Field(default=4, ge=1, le=500)


class GazetteerSiteRecord(BaseModel):
    record_id: str
    name: str
    region: Optional[str] = None
    latitude: float
    longitude_east: float
    crs: str
    source: str
    dataset_id: str
    coverage_verified: bool
    elevation_m: Optional[float] = None
    uncertainty_m: Optional[float] = None


class LandingSiteResponse(BaseModel):
    landing_site_id: str
    mission_id: str
    name: str
    latitude: float
    longitude_east: float
    crs: str
    latitude_convention: str
    longitude_direction: str
    source: str
    source_record_id: Optional[str] = None
    uncertainty_m: Optional[float] = None
    elevation_m: Optional[float] = None
    terrain_dataset_id: Optional[str] = None
    dem_coverage_state: Literal["COVERED_DEM", "OUTSIDE_EVALUATED_DEM_COVERAGE", "UNVERIFIED_EXTERNAL"]
    registration_state: LandingSiteRegistrationState
    dataset_selection_reason: Optional[str] = None
    native_resolution_m: Optional[float] = None
    vertical_datum: Optional[str] = None
    sample_is_nodata: bool = False
    nodata_reason: Optional[str] = None
    updated_by: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    created_at_utc: str
    updated_at_utc: str


class LandingSitePerimeterResponse(BaseModel):
    perimeter_id: str
    mission_id: str
    landing_site_id: str
    status: Literal[
        "EVALUATED_WITH_VALIDATED_DEM",
        "INDETERMINATE_OUTSIDE_DEM",
        "INDETERMINATE_MISSING_CONSTRAINTS",
    ]
    classification_label: str
    algorithm_id: str
    algorithm_version: str
    terrain_dataset_id: Optional[str] = None
    native_resolution_m: Optional[float] = None
    coverage_fraction: Optional[float] = None
    geometry_geojson: Optional[Dict[str, Any]] = None
    excluded_regions_geojson: Optional[Dict[str, Any]] = None
    unknown_regions_geojson: Optional[Dict[str, Any]] = None
    constraints_used: Dict[str, Any] = Field(default_factory=dict)
    constraints_missing: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    operator_approved: bool
    approved_by: Optional[str] = None
    approved_at_utc: Optional[str] = None
    created_at_utc: str


class CoveringDemCandidate(BaseModel):
    dataset_id: str
    product_id: str
    product_title: str
    native_resolution_m: Optional[float] = None
    crs: str = "IAU2000:49900"
    vertical_datum: Optional[str] = None
    provenance: Optional[str] = None
    source_type: Literal["PROCESSED_DEM", "CATALOG_DEM"] = "CATALOG_DEM"
    local_slope_suitable: bool = False
    suitability_summary: Optional[str] = None
    selection_reason: str


class LandingSiteCoverageDiscoveryResponse(BaseModel):
    latitude: float
    longitude_east: float
    crs: str = "IAU2000:49900"
    covered: bool
    selected_dataset: Optional[CoveringDemCandidate] = None
    covering_datasets: List[CoveringDemCandidate] = Field(default_factory=list)
    elevation_m: Optional[float] = None
    sample_is_nodata: bool = False
    unavailable_reason: Optional[str] = None


class LandingSiteBundleResponse(BaseModel):
    mission_id: str
    landing_site_status: LandingSiteRegistrationState
    landing_site: Optional[LandingSiteResponse] = None
    perimeter: Optional[LandingSitePerimeterResponse] = None


# ---------------------------------------------------------------------------
# Mission Events Audit Timeline
# ---------------------------------------------------------------------------


class MissionEventResponse(BaseModel):
    event_id: str
    mission_id: str
    actor_id: str
    event_type: str
    client_timestamp_utc: Optional[str] = None
    server_timestamp_utc: str
    payload_schema_version: str
    event_seq: int
    correlation_id: str
    client_event_id: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)
    auth_context: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)


class DemoCredentialsConfigResponse(BaseModel):
    enabled: bool
    demo_mission_id: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    account_label: str = "DEMO"
    disclaimer: str = (
        "Public sandbox demonstration account. Isolated from production astronaut missions and global configuration."
    )
