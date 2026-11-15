# MARSCOPE — Mission Foundation Architecture (Prompt 1)

This document specifies the **Prompt 1 Multi-Astronaut Mission Foundation** implemented inside MARSCOPE (`backend/` and `frontend/`). It is designed so **Prompt 2** (real-time operational surface navigation, active survival envelopes, and dynamic turn-back alerts) integrates directly onto these schemas, persistence tables, SSE streams, and UI contracts without refactoring the foundation.

---

## 1. Relational Database & Migration Architecture

MARSCOPE stores multi-astronaut, mission-scoped operational records in an ACID-compliant relational store managed by [`backend/app/db/database.py`](../backend/app/db/database.py) and [`backend/app/db/migrations/0001_mission_foundation.sql`](../backend/app/db/migrations/0001_mission_foundation.sql).

- **Local Development Backend:** Durable SQLite in WAL mode (`PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, explicit `BEGIN IMMEDIATE` write transactions) at `datasets/index/marscope_mission.sqlite` when `DATABASE_URL` is unset in development/test.
- **Production Fail-Closed Behavior:** Setting `ENVIRONMENT=production` without a configured `DATABASE_URL`, or configuring an unsupported scheme (`postgres://` without an installed async/sync PostgreSQL driver), raises `DatabaseConfigurationError` rather than falling back silently to memory.
- **Applied Migrations Tracking:** `_schema_migrations` records applied filenames and UTC timestamps idempotently on startup (`ensure_migrations()`), and readiness is exposed via `GET /api/health/readiness` (`pillars.mission` -> `mission_db_ready`, `mission_db_backend`, `mission_db_migrations`).

### Relational Schema (`0001_mission_foundation.sql` — 14 Tables)

1. `astronauts` — Astronaut identity (`astronaut_id`, `email`, `display_name`), password hash/salt, `is_active`, nullable operational parameters (`body_mass_kg`, `suit_mass_kg`, `equipment_mass_kg`, each strictly `NULL` until explicitly submitted and audited in `profile_edit_history_json` as `USER_ASSUMED`), `mobility_constraints`, `emergency_contact`, `profile_visibility`.
2. `auth_sessions` — Hashed bearer/cookie session tokens, CSRF secret tokens, expiry (`expires_at_utc`), revocation timestamp, user agent/IP audit.
3. `password_reset_tokens` — CSPRNG SHA-256 hashed single-use expiring reset tokens.
4. `missions` — Multi-astronaut workspaces (`mission_id`, `name`, `description`, `objective`, `operating_region`, `status`, `created_by`).
5. `mission_memberships` — Membership & RBAC (`MISSION_LEAD`, `ASTRONAUT`, `MISSION_OPERATOR`), `location_sharing_enabled`, `last_seen_at_utc`.
6. `mission_invitations` — CSPRNG SHA-256 hashed single/multi-use expiring & revocable invite tokens.
7. `crew_positions` — Time-ordered planetary coordinates (`IAU2000:49900`, `planetocentric` latitude, `positive_east_0_360` longitude), explicit source provenance (`TELEMETRY_PROVIDER`, `LOCALIZATION_SOLVER`, `USER_PROVIDED`), `uncertainty_m`, `elevation_m`, monotonic `sequence_number` + `client_event_id` idempotency.
8. `voice_notes` — Private audio attachments stored outside webroot (`datasets/private_attachments/missions/{mission_id}/...`) with `sha256`, `byte_size`, `mime_type`, `storage_relpath`.
9. `sos_events` — Emergency SOS dispatches (`ACTIVE` -> `DELIVERED_TO_CREW_DEVICE` -> `ACKNOWLEDGED_BY_CREW` -> `RESOLVED` / `CANCELLED`), idempotent `client_event_id`, optional linked `voice_note_id`.
10. `sos_acknowledgements` — Per-astronaut emergency receipts and timestamps (`UNIQUE(sos_id, astronaut_id)`).
11. `field_observations` — Georeferenced field discoveries with `category`, `title`, `notes`, optional validated compositional species (`canonical_species_id` verified against `app/science/composition/species.py`), `epistemic_state` (`USER_REPORTED` / `UNVERIFIED` / `CORROBORATED_BY_EVIDENCE` / `CONTESTED` / `RETRACTED`), `version` optimistic concurrency, linked `voice_note_id`, `audit_history_json`.
12. `landing_sites` — Per-mission landing site configuration (`LANDING_SITE_UNCONFIGURED` initially, or `REGISTERED` with explicit coordinates/gazetteer citation and DEM coverage classification `COVERED_DEM` / `OUTSIDE_EVALUATED_DEM_COVERAGE` / `UNVERIFIED_EXTERNAL`).
13. `landing_site_perimeters` — Evaluated 3D DEM traversal boundaries (`EVALUATED_WITH_VALIDATED_DEM`, `INDETERMINATE_OUTSIDE_DEM`, `INDETERMINATE_MISSING_CONSTRAINTS`), explicit `classification_label = "CURRENTLY EVALUATED PLANNING BOUNDARY — NOT A CERTIFIED SAFETY LIMIT"`, GeoJSON geometry & excluded regions, constraints used/missing, and operator approval audit (`operator_approved`, `approved_by`, `approved_at_utc`).
14. `mission_events` — Monotonically sequenced append-only mission ledger (`event_seq`, `event_type`, `payload_json`) backing reconnect catch-up and real-time SSE fan-out.

---

## 2. Authentication, Security & Mission RBAC

- **Password Hashing:** `hashlib.scrypt` (`n=16384, r=8, p=1`) with per-user 16-byte CSPRNG salt and constant-time `hmac.compare_digest` verification ([`backend/app/core/security.py`](../backend/app/core/security.py)). Minimum 10 characters enforcing uppercase, lowercase, digit, and symbol variety.
- **Session Cookies & Double-Submit CSRF:** `HttpOnly`, `SameSite` configurable (`AUTH_COOKIE_SAMESITE`), `Secure` in production (`AUTH_COOKIE_SECURE`), paired with a readable CSRF cookie and mandatory `X-CSRF-Token` verification on mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
- **Rate Limiting:** `SlidingWindowRateLimiter` protects `/api/auth/login`, `/api/auth/register`, and `/api/auth/password-reset/request` against brute force.
- **Password Reset Preview Guard:** Reset tokens are SHA-256 hashed at rest; optional preview response is strictly disabled unless `ALLOW_TEST_PASSWORD_RESET_TOKEN_PREVIEW=true` in non-production environments.
- **Mission Membership Isolation & RBAC:** Every `/api/missions/{mission_id}/*` endpoint calls `load_mission_membership` or `require_mission_roles`, rejecting non-members with `HTTP 403`. `MISSION_LEAD` and `MISSION_OPERATOR` hold administrative capabilities (invitations, role assignments, perimeter computation/approval, observation review).
- **Private Voice Notes:** Audio uploads read raw HTTP request bodies (`await request.body()`) up to `AUDIO_UPLOAD_MAX_BYTES` (default 10 MB), verify magic bytes / audio MIME types (`audio/webm`, `audio/ogg`, `audio/wav`, `audio/mpeg`, `audio/mp4`), write atomically outside the static webroot, and serve authorized crew via either authenticated session cookies or personal HMAC-SHA256 `?token=` signatures bound to `astronaut_id` and `voice_note_id` (cross-astronaut replay returns `403`).

### Key API Endpoints

- **Auth & Profile (`/api/auth`):** `POST /register`, `POST /login`, `POST /logout`, `POST /refresh`, `GET /session`, `GET /sessions`, `DELETE /sessions/{session_id}`, `PUT /profile`, `POST /password-reset/request`, `POST /password-reset/confirm`, `POST /account/deactivate`.
- **Missions & Crew (`/api/missions`):** `POST ""`, `GET ""`, `POST /join`, `GET /{mission_id}`, `PATCH /{mission_id}`, `POST /{mission_id}/invitations`, `GET /{mission_id}/invitations`, `POST /{mission_id}/invitations/{invite_id}/revoke`, `POST /{mission_id}/leave`, `DELETE /{mission_id}/crew/{astronaut_id}`, `PATCH /{mission_id}/crew/{astronaut_id}/role`, `GET /{mission_id}/crew`, `POST /{mission_id}/positions`, `GET /{mission_id}/positions`, `PUT /{mission_id}/positions/sharing`, `GET /{mission_id}/events`, `GET /{mission_id}/stream`.
- **SOS & Voice Notes (`/api/missions`):** `POST /{mission_id}/sos`, `GET /{mission_id}/sos`, `POST /{mission_id}/sos/{sos_id}/delivered`, `POST /{mission_id}/sos/{sos_id}/acknowledge`, `POST /{mission_id}/sos/{sos_id}/resolve`, `POST /{mission_id}/sos/{sos_id}/cancel`, `POST /{mission_id}/voice-notes`, `GET /{mission_id}/voice-notes/{voice_note_id}`.
- **Field Observations (`/api/missions`):** `GET /missions/vocabulary/species`, `POST /missions/{mission_id}/observations`, `GET /missions/{mission_id}/observations`, `PATCH /missions/{mission_id}/observations/{observation_id}` (checks `expected_version` optimistic lock -> `409`), `POST /missions/{mission_id}/observations/{observation_id}/review`.
- **Landing Site & 3D Perimeter (`/api/missions`):** `GET /missions/gazetteer/search`, `GET /missions/{mission_id}/landing-site`, `PUT /missions/{mission_id}/landing-site`, `POST /missions/{mission_id}/landing-site/perimeter`, `POST /missions/{mission_id}/landing-site/perimeter/{perimeter_id}/approve`.

---

## 3. Real-Time Crew Positions, SOS, Observations & Landing-Site Intelligence

- **Position Validation & Freshness:** Incoming positions validate strictly against `IAU2000:49900` (`validate_mars_coordinates`), sample processed local DEM elevation when covered (`sample_processed_terrain_point`), reject stale out-of-order `sequence_number` values with `409`, and derive server-side freshness states (`CONNECTED`, `POSITION_STALE` when age > `POSITION_STALE_AFTER_SECONDS`, `POSITION_UNAVAILABLE`, `LOCATION_SHARING_DISABLED`).
- **SSE Isolation (`realtime_hub.py`):** Per-mission asyncio pub/sub queues broadcast events strictly to authenticated active mission members and support `?since_seq=` catch-up from `mission_events`.
- **Persistent Emergency SOS UI (`EmergencySosOverlay.tsx` + `/emergency`):** A `56x56px` press-and-hold (1.2s continuous hold, keyboard accessible) SOS trigger persists bottom-right across views when inside an active mission, prevents accidental single-click dispatch, captures optional `VoiceRecorderWidget` (`MediaRecorder`) audio notes, marks device delivery (`DELIVERED_TO_CREW_DEVICE`), records acknowledgements (`ACKNOWLEDGED_BY_CREW`), and supports resolution/cancellation lifecycle.
- **3D DEM Perimeter Algorithm (`landing_site_service.py`):** Loads the active processed `*_dem.tif`, `*_slope.tif`, and `*_roughness.tif` window around the registered landing site, enforces explicit user-configured slope (`max_slope_deg`), roughness (`max_roughness_tri_m`), and range/time limits (withholding geometry cleanly as `INDETERMINATE_MISSING_CONSTRAINTS` or `INDETERMINATE_OUTSIDE_DEM` if constraints or DEM coverage are absent), runs 8-connected BFS across verified contiguous traversable DEM cells (checking diagonal corner passability), extracts boundary + excluded terrain contours, and stamps every perimeter `CURRENTLY EVALUATED PLANNING BOUNDARY — NOT A CERTIFIED SAFETY LIMIT`.

---

## 4. Synchronized Interface, Design System & Offline Sync Foundation

- **Centralized Design Tokens (`frontend/src/app/globals.css`):** Unifies the entire interface around Atmospheric Carbon Slate (`--bg-void: #07090C`, `--bg-canvas: #0B0F14`, `--bg-surface: #121821`, `--bg-elevated: #18212C`), Mars Regolith Oxide (`--accent-mars: #E25B38`), Telemetry Cyan (`--accent-telemetry: #22B8CF`), and semantic status states (`--accent-success`, `--accent-warning`, `--accent-danger`, `--accent-unknown`). Legacy purple accents have been eliminated across all pages.
- **Unified Navigation & Spatial Engine:** `Sidebar.tsx` organizes routes cleanly into 6 operational groups (`Command`, `Field Ops`, `Terrain & Map`, `Planning & Routes`, `Science & Evidence`, `System`), paired with `TopNav.tsx` (`Cmd/Ctrl+K` Command Palette, mission selector, offline queue/stream badge), `IntegratedMissionContextBar.tsx`, and synchronized `MarsGlobeViewer.tsx` + `LocalTerrain3DViewer.tsx` overlays via `useSpatialStore` (`focusCoordinate`, `showLandingSiteOverlay`, `showCrewOverlay`, `showFieldObservationsOverlay`).
- **IndexedDB Offline Queue (`frontend/src/lib/offlineQueue.ts`):** Persists failed/offline position updates, observations, and SOS dispatches under `marscope_offline_v1` with explicit status transitions (`QUEUED_OFFLINE` -> `PENDING_DELIVERY` -> `DELIVERED_TO_SERVER` / `FAILED_RETRYABLE`) and idempotent `client_event_id` deduplication.

---

## 5. Configuration Environment Variables (`backend/.env.example`)

| Variable | Default / Development | Notes |
| :--- | :--- | :--- |
| `DATABASE_URL` | Empty -> `sqlite:///.../marscope_mission.sqlite` | Required in `production`. |
| `MARSCOPE_SECRET_KEY` | Dev ephemeral CSPRNG | Required stable secret in `production` for sessions & HMAC voice-note URLs. |
| `AUTH_SESSION_TTL_SECONDS` | `604800` (7 days) | Session expiration horizon. |
| `AUTH_COOKIE_SECURE` | `false` (dev) | Should be `true` behind HTTPS in production. |
| `AUTH_COOKIE_SAMESITE` | `lax` | Session & CSRF cookie SameSite policy. |
| `POSITION_STALE_AFTER_SECONDS` | `120` | Threshold transitioning active crew position to `POSITION_STALE`. |
| `AUDIO_UPLOAD_MAX_BYTES` | `10485760` (10 MB) | Maximum binary voice-note payload. |
| `ALLOW_TEST_PASSWORD_RESET_TOKEN_PREVIEW` | `false` | Development/test helper only; disabled in production. |

---

## 6. Known Limitations & Prompt 2 Handoff

- **No Certified Safety Limits:** 3D landing-site perimeters represent current DEM planning boundaries conditioned strictly on user-declared limits (`safety_certification_enabled = false`), not geological/regolith bearing-capacity certification.
- **Prompt 2 Deferred Scope (`/active-navigation`):** Live field turn-by-turn astronaut guidance, dynamic return-to-base countdowns, live turn-back divergence alerts, and survival-envelope recomputation in active EVA navigation are deferred to Prompt 2 and consume the Prompt 1 mission, landing-site, crew-position, and SSE contracts documented here.
