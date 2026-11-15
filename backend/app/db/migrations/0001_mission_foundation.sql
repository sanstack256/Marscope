-- MARSCOPE Mission Foundation Schema (Migration 0001)
-- Enforces foreign keys, unique constraints, and indexed queries for multi-astronaut operations.

CREATE TABLE IF NOT EXISTS astronauts (
    astronaut_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    body_mass_kg REAL,
    body_mass_meta_json TEXT,
    suit_mass_kg REAL,
    suit_mass_meta_json TEXT,
    equipment_mass_kg REAL,
    equipment_mass_meta_json TEXT,
    mobility_constraints TEXT,
    emergency_contact TEXT,
    profile_visibility TEXT NOT NULL DEFAULT 'mission_members',
    profile_edit_history_json TEXT NOT NULL DEFAULT '[]',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_astronauts_email ON astronauts(email);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    user_agent TEXT,
    created_at_utc TEXT NOT NULL,
    expires_at_utc TEXT NOT NULL,
    last_seen_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_astronaut ON auth_sessions(astronaut_id, revoked_at_utc);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    reset_id TEXT PRIMARY KEY,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at_utc TEXT NOT NULL,
    used_at_utc TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    lead_astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id),
    operating_region TEXT,
    planned_start_utc TEXT,
    planned_end_utc TEXT,
    visibility TEXT NOT NULL DEFAULT 'private',
    membership_policy TEXT NOT NULL DEFAULT 'invite_only',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    landing_site_status TEXT NOT NULL DEFAULT 'LANDING_SITE_UNCONFIGURED',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_missions_lead ON missions(lead_astronaut_id);

CREATE TABLE IF NOT EXISTS mission_memberships (
    membership_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('MISSION_LEAD', 'ASTRONAUT', 'MISSION_OPERATOR')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'LEFT', 'REMOVED')),
    location_sharing_enabled INTEGER NOT NULL DEFAULT 1,
    joined_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(mission_id, astronaut_id)
);

CREATE INDEX IF NOT EXISTS idx_memberships_mission ON mission_memberships(mission_id, status);
CREATE INDEX IF NOT EXISTS idx_memberships_astronaut ON mission_memberships(astronaut_id, status);

CREATE TABLE IF NOT EXISTS mission_invitations (
    invite_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    created_by TEXT NOT NULL REFERENCES astronauts(astronaut_id),
    token_hash TEXT NOT NULL UNIQUE,
    role_on_join TEXT NOT NULL DEFAULT 'ASTRONAUT' CHECK(role_on_join IN ('MISSION_LEAD', 'ASTRONAUT', 'MISSION_OPERATOR')),
    single_use INTEGER NOT NULL DEFAULT 0,
    max_uses INTEGER,
    uses_count INTEGER NOT NULL DEFAULT 0,
    expires_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invitations_mission ON mission_invitations(mission_id);
CREATE INDEX IF NOT EXISTS idx_invitations_hash ON mission_invitations(token_hash);

CREATE TABLE IF NOT EXISTS crew_positions (
    position_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    latitude REAL NOT NULL,
    longitude_east REAL NOT NULL,
    crs TEXT NOT NULL,
    latitude_convention TEXT NOT NULL,
    longitude_direction TEXT NOT NULL,
    elevation_m REAL,
    uncertainty_m REAL,
    source_id TEXT NOT NULL,
    source_classification TEXT NOT NULL,
    sequence_number INTEGER NOT NULL DEFAULT 0,
    measured_at_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'VALIDATED'
);

CREATE INDEX IF NOT EXISTS idx_crew_pos_mission_astro ON crew_positions(mission_id, astronaut_id, received_at_utc DESC, sequence_number DESC);

CREATE TABLE IF NOT EXISTS voice_notes (
    voice_note_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    linked_event_type TEXT,
    linked_event_id TEXT,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    duration_seconds REAL,
    sha256_checksum TEXT NOT NULL,
    storage_rel_path TEXT NOT NULL,
    upload_status TEXT NOT NULL DEFAULT 'UPLOADED',
    created_at_utc TEXT NOT NULL,
    deleted_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_voice_notes_mission ON voice_notes(mission_id, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS sos_events (
    sos_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL DEFAULT 'SOS_ACTIVATED',
    status TEXT NOT NULL,
    client_event_id TEXT,
    latitude REAL,
    longitude_east REAL,
    elevation_m REAL,
    crs TEXT,
    position_source TEXT,
    position_classification TEXT,
    position_age_s REAL,
    position_status TEXT NOT NULL,
    message TEXT,
    voice_note_id TEXT REFERENCES voice_notes(voice_note_id),
    created_at_utc TEXT NOT NULL,
    server_received_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(mission_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_sos_mission ON sos_events(mission_id, server_received_at_utc DESC);

CREATE TABLE IF NOT EXISTS sos_acknowledgements (
    ack_id TEXT PRIMARY KEY,
    sos_id TEXT NOT NULL REFERENCES sos_events(sos_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    ack_type TEXT NOT NULL CHECK(ack_type IN ('DELIVERED_TO_CREW_DEVICE', 'ACKNOWLEDGED_BY_CREW', 'RESOLVED', 'CANCELLED')),
    note TEXT,
    created_at_utc TEXT NOT NULL,
    UNIQUE(sos_id, astronaut_id, ack_type)
);

CREATE TABLE IF NOT EXISTS field_observations (
    observation_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id) ON DELETE CASCADE,
    client_event_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    latitude REAL,
    longitude_east REAL,
    elevation_m REAL,
    crs TEXT NOT NULL DEFAULT 'IAU2000:49900',
    coordinate_source TEXT NOT NULL,
    uncertainty_m REAL,
    target_id TEXT,
    category TEXT NOT NULL,
    species_canonical_id TEXT,
    species_display_name TEXT,
    description TEXT NOT NULL,
    epistemic_state TEXT NOT NULL,
    instrument_id TEXT,
    source_product_id TEXT,
    calibration_metadata TEXT,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    voice_note_id TEXT REFERENCES voice_notes(voice_note_id),
    offline_created_at_utc TEXT,
    synced_at_utc TEXT,
    reviewed_by TEXT REFERENCES astronauts(astronaut_id),
    review_note TEXT,
    annotations_json TEXT NOT NULL DEFAULT '[]',
    audit_history_json TEXT NOT NULL DEFAULT '[]',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(mission_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_obs_mission ON field_observations(mission_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_obs_species ON field_observations(mission_id, species_canonical_id);

CREATE TABLE IF NOT EXISTS landing_sites (
    landing_site_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL UNIQUE REFERENCES missions(mission_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude_east REAL NOT NULL,
    crs TEXT NOT NULL,
    latitude_convention TEXT NOT NULL,
    longitude_direction TEXT NOT NULL,
    source TEXT NOT NULL,
    source_record_id TEXT,
    uncertainty_m REAL,
    elevation_m REAL,
    terrain_dataset_id TEXT,
    dem_coverage_state TEXT NOT NULL,
    registration_state TEXT NOT NULL DEFAULT 'REGISTERED',
    updated_by TEXT NOT NULL REFERENCES astronauts(astronaut_id),
    history_json TEXT NOT NULL DEFAULT '[]',
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS landing_site_perimeters (
    perimeter_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    landing_site_id TEXT NOT NULL REFERENCES landing_sites(landing_site_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    algorithm_id TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    terrain_dataset_id TEXT,
    native_resolution_m REAL,
    coverage_fraction REAL,
    geometry_geojson TEXT,
    excluded_regions_geojson TEXT,
    constraints_used_json TEXT NOT NULL DEFAULT '{}',
    constraints_missing_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    operator_approved INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT REFERENCES astronauts(astronaut_id),
    approved_at_utc TEXT,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_perim_mission ON landing_site_perimeters(mission_id, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS mission_events (
    event_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    client_timestamp_utc TEXT,
    server_timestamp_utc TEXT NOT NULL,
    payload_schema_version TEXT NOT NULL DEFAULT '1.0',
    event_seq INTEGER NOT NULL,
    correlation_id TEXT NOT NULL,
    client_event_id TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    auth_context_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(mission_id, event_type, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_events_mission_seq ON mission_events(mission_id, event_seq DESC);
