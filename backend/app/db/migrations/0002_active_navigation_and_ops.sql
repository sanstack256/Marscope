-- MARSCOPE Prompt 2 Migration: Active Navigation Sessions & Obstruction Reports
-- Forward-only, transactional, preserves all Prompt 1 mission_foundation tables.

CREATE TABLE IF NOT EXISTS navigation_sessions (
    nav_session_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    astronaut_id TEXT NOT NULL REFERENCES astronauts(astronaut_id),
    state TEXT NOT NULL,
    navigation_mode TEXT NOT NULL,
    route_id TEXT,
    route_dataset_id TEXT NOT NULL,
    route_crs TEXT NOT NULL,
    return_destination_name TEXT NOT NULL,
    return_destination_lat REAL NOT NULL,
    return_destination_lon REAL NOT NULL,
    deviation_threshold_m REAL,
    active_segment_index INTEGER NOT NULL DEFAULT 0,
    route_snapshot_json TEXT NOT NULL,
    operational_params_json TEXT NOT NULL,
    candidate_replan_json TEXT,
    last_turnback_json TEXT,
    approved_by TEXT REFERENCES astronauts(astronaut_id),
    approved_at_utc TEXT,
    last_state_reason TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nav_sessions_mission_updated
    ON navigation_sessions(mission_id, updated_at_utc DESC);

CREATE TABLE IF NOT EXISTS navigation_obstructions (
    obstruction_id TEXT PRIMARY KEY,
    nav_session_id TEXT NOT NULL REFERENCES navigation_sessions(nav_session_id) ON DELETE CASCADE,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    reported_by TEXT NOT NULL REFERENCES astronauts(astronaut_id),
    segment_index INTEGER,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    location_source TEXT NOT NULL,
    description TEXT NOT NULL,
    voice_note_id TEXT,
    attachment_note TEXT,
    review_state TEXT NOT NULL,
    epistemic_classification TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nav_obstructions_session
    ON navigation_obstructions(nav_session_id, created_at_utc DESC);
