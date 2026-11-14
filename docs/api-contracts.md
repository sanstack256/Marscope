# MARSCOPE API Contracts & Endpoint Specifications

All endpoints are served under the `/api` prefix by the FastAPI backend. Standard response formats are JSON or OGC GeoJSON.

---

## 1. System & Reference Endpoints

### `GET /api/health`
- **Description:** Returns backend health status, API version, system clock, and loaded scientific engines.
- **Response:**
```json
{
  "status": "healthy",
  "system": "MARSCOPE Martian Surface Intelligence Engine",
  "version": "1.0.0",
  "timestamp_utc": "2026-11-14T03:45:00Z",
  "engines": {
    "physics": "active",
    "geospatial": "active",
    "routing": "active"
  }
}
```

### `GET /api/study-area`
- **Description:** Returns bounding metadata, center coordinates, and CRS definition for the active study region (Gale Crater / Mount Sharp).
- **Response:**
```json
{
  "name": "Gale Crater - Mount Sharp Boxwork Exploration Zone",
  "center": { "latitude": -4.65, "longitude": 137.40 },
  "bounds": {
    "min_latitude": -5.5,
    "max_latitude": -4.3,
    "min_longitude": 137.2,
    "max_longitude": 138.0
  },
  "crs": "IAU2000:49900",
  "elevation_datum": "MOLA Areoid"
}
```

---

## 2. Geospatial & Data Layer Endpoints

### `GET /api/layers`
- **Description:** Lists available orbital and surface imagery layers, tile services, and coverage status.

### `GET /api/terrain/summary`
- **Description:** Returns topographic statistics for the active study bounding box (elevation min/max, mean slope, roughness percentiles).

### `GET /api/terrain/layers`
- **Description:** Returns endpoints and metadata for processed raster layers (Slope, Aspect, Ruggedness Index).

---

## 3. Scientific Target & Observation Endpoints

### `GET /api/targets`
- **Description:** Returns verified geological targets within the study area as GeoJSON FeatureCollection with scientific scores and mineralogy.

### `GET /api/targets/{target_id}`
- **Description:** Returns detailed dossier for a specific target, including associated MSL rover observations, ChemCam/APXS chemistry, and PDS source links.

### `GET /api/observations`
- **Description:** Returns point observations from Curiosity rover traverse stops, environmental readings, and spectral detections.

### `POST /api/observations`
- **Description:** Registers a verified field observation into the local provenance database.

---

## 4. Routing & Mission Optimization Endpoints

### `POST /api/routes/plan`
- **Description:** Computes an optimized Marswalk traverse between base habitat and selected science targets under specified constraint weights.
- **Request Body:**
```json
{
  "base_location": { "latitude": -4.60, "longitude": 137.38 },
  "target_ids": ["target_boxwork_alpha", "target_sulfate_contact"],
  "mode": "balanced",
  "max_duration_seconds": 21600,
  "safety_reserve_factor": 1.5,
  "max_slope_threshold_deg": 25.0
}
```
- **Response:** Detailed GeoJSON LineString path with per-segment slope, distance, metabolic cost, and return-to-base point-of-no-return marker.

### `POST /api/routes/compare`
- **Description:** Generates parallel candidate routes across `conservative`, `balanced`, and `science_priority` modes and returns comparative metrics.

### `GET /api/missions/{mission_id}`
- **Description:** Retrieves persisted mission state, astronaut parameters, active route, and telemetry.

### `POST /api/missions`
- **Description:** Creates and saves a new mission planning scenario.

---

## 5. Prompt 4 Composition Discovery, Spatial Index & Target Provenance Endpoints

### `GET /api/composition/species`
- **Description:** Queries the controlled geochemical vocabulary (`element`, `oxide`, `mineral`, `mineral_group`). Supports optional `?q=` substring/alias filter.

### `GET /api/composition/index/status`
- **Description:** Returns separated integrity, completeness, digest, and pointer telemetry (`integrity_status`, `source_integrity_status`, `manifest_integrity_status`, `pointer_integrity_status`, `database_integrity_status`, `active_generation_id`, `previous_successful_generation_id`, `incomplete_staging_generations`, `source_artifact_digest`, `complete_manifest_digest`, `pointer_path`, `reproducibility_manifest_path`, `rtree_enabled`, `crism_status`).

### `POST /api/composition/index/rebuild`
- **Description:** Acquires `.publish.lock`, scans `datasets/raw/`, runs PDS3/PDS4 adapters + coordinate association + 12-stage validation, and atomically publishes a new immutable generation directory under `datasets/index/generations/<gen_id>__<nonce>/`, updating `active_generation.json`.

### `POST /api/composition/search` (and `POST /api/destinations/search-composition`)
- **Description:** Resolves an element/oxide/mineral query (`search_mode`: `auto | element | mineral | element_bearing_mineral`), supports `measurement_category_filter`, `min_value`/`max_value` (strictly scoped by category & physical unit; raises HTTP `422` on ambiguous mixed-unit bounds), and `sort_by` (`rank | distance | category_abundance | abundance | sol`; raises HTTP `422` on flat `abundance` across mixed categories/units). Returns `measurement_categories_present`, `grouped_counts_by_measurement_category`, `applied_filter_scope_note`, ranked `hits` (each with `quality_component=null` and optional separate `relative_uncertainty`), clustered `candidate_locations`, `unlocated_matches_count`, and `scientific_warnings`.

### `GET /api/composition/evidence/{evidence_id}`
- **Description:** Returns full `CompositionEvidence` provenance, raw vs stoichiometric conversion formula, coordinate derivation source, field-level `uncertainty_metadata` (`source_field_name`, `source_data_type`, `schema_identity`, `is_physical_unit`, `limitations`), and all 12 `validation_stages`.

### `GET /api/composition/rejected`
- **Description:** Returns paginated `RejectionRecord` audit log (`?limit=50&offset=0`) showing why passive PSVs, REMS tables, `<LOD` measurements, unknown CheMin species, or invalid records were excluded.

### `GET /api/composition/reproducibility-manifest`
- **Description:** Atomically resolves the active manifest through `active_generation.json` (`reproducibility_manifest_v3`) and authenticates canonical `complete_manifest_digest` plus SQLite `index_generations` agreement before returning JSON. Contains `generation_id`, `publication_nonce`, `previous_successful_generation_id`, `source_artifact_digest`, `complete_manifest_digest`, `generation_build_status`, `products`, `dependency_artifacts`, `product_audit`, `rights_summary`, `retrieval_metadata`, and `RankingConfiguration` (`heuristic_exploration_priority_v4` `4.0.0`). Raises HTTP `404` if unbuilt or HTTP `422` on any tampering, corruption, or DB/pointer mismatch.

### `POST /api/targets/generate`
- **Description:** Deterministically generates `evidence_backed` `ScienceTarget` records from top-ranked composition discovery clusters, storing immutable `evidence_ids` and distance/rationale metadata. Also `GET /api/sources/msl/archive-query` exposes live NASA PDS/ODE archive product discovery.

### `POST /api/missions/{mission_id}/replan`
- **Description:** Triggers real-time replanning for an active mission given mid-traverse contingency inputs (e.g. reduced oxygen reserve).

---

## 5. Provenance & Metadata Endpoints

### `GET /api/sources`
- **Description:** Returns complete dataset registry matching `DATA_SOURCES.md`, including PDS product identifiers, licensing status, and citations.

---

## 6. Prompt 8 Human Mobility Intelligence Endpoints (`/api/mobility/*`)

### `GET /api/mobility/status`
- **Description:** Returns DEM inventory, download/processing status, per-scale resolution suitability (`regional_elevation_analysis`, `local_slope_analysis`, `regional_roughness_analysis`, `small_scale_obstacle_detection`) annotated with `policy_id`, `policy_version`, `threshold_classification`, and `threshold_rationale` (`backend/app/mobility/policies/resolution_v1.json`), and explicit flags `route_optimization_enabled = true` and `safety_certification_enabled = false`.

### `GET /api/mobility/terrain/features`
- **Description:** Extracts windowed elevation (`meters`), Horn `3x3` slope (`degrees`), compass aspect (`[0, 360)` clockwise from North; flat cells undefined), and metric TRI roughness (`meters`) over `[min_lat, max_lat, min_lon, max_lon]`. Never enlarges requested bounds; raises HTTP `422` with a structured `InsufficientCoverageReport` if the window intersects fewer than `3x3` whole source pixels.

### `GET /api/mobility/coverage`
- **Description:** Returns 5-state spatial coverage intelligence (`outside_source_footprint`, `inside_footprint_nodata`, `valid_source_data`, `insufficient_resolution_for_analysis`, `derivative_unavailable_invalid_neighborhood`), covered/uncovered area in $\text{km}^2$, and optional `insufficient_coverage_report`.

### `POST /api/mobility/scenarios`, `GET /api/mobility/scenarios`, `GET /api/mobility/scenarios/{scenario_id}`
- **Description:** Creates, lists, and inspects versioned `MobilityScenario` configurations. Every parameter records its `ParameterOriginType` (`verified_planetary_constant`, `user_configured_assumption`, `optional_heuristic_rule`, or `unavailable`).

### `POST /api/mobility/elevation-profile`
- **Description:** Computes a geodesic elevation profile and cumulative positive gain / negative loss / net change between `start` and `end` or along `waypoints` (`>= 2` points), including contiguous `nodata_gap_segments`.

### `POST /api/mobility/evaluate`
- **Description:** Evaluates a transect (`waypoints`) or bounding box (`bounds`) under a saved `scenario_id` or `inline_scenario`, strictly separating `physical_measurements` from `scenario_traversal_estimates`.

### `GET /api/mobility/cost-surface/metadata`
- **Description:** Computes and returns a spatially explicit `CostSurfaceSummary` over `[min_lat, max_lat, min_lon, max_lon]` for a given `dataset_id` and `scenario_id`, preserving `null` cost on unknown/no-data terrain and distinguishing `explicit_scenario_exclusion` without emitting `"safe"` or `"unsafe"` labels.

---

## 7. Prompt 11 3D Terrain Mesh & Ortho Texture Endpoints (`/api/terrain/*`)

### `GET /api/terrain/mesh/manifest`
- **Query Params:** `dataset_id` (optional, defaults to highest-res local DEM), optional bbox (`min_lat`, `max_lat`, `min_lon`, `max_lon`), `max_lod` (`0..3`, default `2`), `tile_grid_size` (`17..129`, default `65`).
- **Response (`TerrainMeshManifestResponse`):** Dataset metadata, native resolution (`m/px`), `origin_lat`/`origin_lon_east`, valid elevation bounds (`min_elevation_m`, `max_elevation_m`, `reference_elevation_m`), planetary radius (`3,396,190.0 m`), paired local ortho dataset ID, and LOD tile descriptors (`tile_id`, `lod`, `bounds`, `grid_rows`, `grid_cols`).

### `GET /api/terrain/mesh/tiles/{tile_id}`
- **Response (`TerrainMeshTileResponse`):** Metric ENU vertex arrays (`east_m`, `north_m`, `elevations_m`), strict `valid_mask` (`0` = NoData / outside swath, `1` = valid source pixel), `normals` (`nx, ny, nz`), and optional slope/TRI arrays. Seam vertices share deterministic edge coordinates across neighboring tiles.

### `GET /api/terrain/mesh/heightgrid`
- **Query Params:** Required `min_lat`, `max_lat`, `min_lon`, `max_lon`; optional `dataset_id`, `grid_size` (`9..65`, default `33`).
- **Response (`HeightGridResponse`):** Compact regular elevation matrix (`grid_rows`, `grid_cols`, `elevations_m`, `valid_count`) consumed by CesiumJS `HeightmapTerrainData` (`createMarscopeDemTerrainProvider()`).

### `GET /api/terrain/ortho/{dataset_id}/texture`
- **Query Params:** `overlay` (`ortho | elevation | slope | roughness`), `min_lat`, `max_lat`, `min_lon`, `max_lon`, `size` (`64..1024`, default `512`).
- **Response:** `image/png` (`Cache-Control: public, max-age=3600`) co-registered exactly to the requested tile bounds.

---

## 8. Prompt 11 Science-Aware Route Computation & Navigation Endpoints (`/api/routing/*`)

### `GET /api/routing/status`
- **Description:** Returns available local routing DEMs, supported modes (`conservative`, `balanced`, `science_priority`), supported algorithms (`astar`, `dijkstra`), active constraints policy, and `safety_certification_enabled = false`.

### `POST /api/routing/validate` & `POST /api/routing/compute`
- **Request (`RouteComputeRequest`):** `dataset_id`, `start` & `destination` (`lat`, `lon_east`, optional `label`), `target_ids`, `custom_waypoints`, `mode`, `algorithm`, and `constraints` (`max_slope_deg`, optional `walking_speed_m_per_s` defaulting `null`, `max_eva_duration_hours`, `return_reserve_fraction`, `return_to_start`, `enforce_budget`, `astronaut_total_mass_kg`, `snap_radius_m`).
- **Response (`RouteComputeResponse`):** `route_id`, deterministic `route_signature`, `effective_slope_limit_deg`, `assumption_classification`, `total_horizontal_distance_m`, `total_surface_distance_m`, `total_elevation_gain_m`, `total_elevation_loss_m`, raw-cell `mean_slope_deg`/`max_slope_deg`/`mean_roughness_tri_m`, optional `estimated_duration_seconds` (`null` unless user declares walking speed), `gravitational_climb_work_joules` ($m \cdot g_{\text{Mars}} \cdot \Delta h$), `budget_diagnostic`, `snap_diagnostics`, `simplification_diagnostic`, `science_targets_reached`, `corridor_evidence_hits_within_150m`, `vertices`, `instructions` (True North `°T` & Equirectangular Grid North `°G`), `resolution_suitability`, and explicit `limitations`. Raises HTTP `422` (`RoutePlanningError`) on unfeasible terrain, slope/NoData barriers, or enforced budget overflow.

### `POST /api/routing/compare`
- **Description:** Evaluates `conservative`, `balanced`, and `science_priority` modes over identical DEM graph & user constraints (`RouteCompareResponse`), returning feasible routes and explicit `error_reason` for any rejected mode.

### `GET /api/routing/{route_id}`, `/instructions`, `/profile`, `/geojson`
- **Description:** Retrieves cached route computation details, turn-by-turn navigation steps, 3D elevation profile vertices, or an OGC GeoJSON `FeatureCollection` (`LineString` traverse + `Point` stop features, IAU2000 Mars coordinates) for external GIS export.

---

## 9. NASA Imagery Catalogue Endpoints (`/api/imagery/*`)
- **Routes:** `GET /api/imagery/status`, `/datasets`, `/search` (PDS Imaging Atlas), `/ode-search` (ODE REST), `/products/{product_id}`, `/products/{product_id}/label`, `POST /api/imagery/products/{product_id}/acquire`, `GET /api/imagery/products/{product_id}/acquisition`, `/eligibility`, `/panoramas`, `/coverage`, plus isolated `GET /api/imagery/perseverance` (Mars 2020 Jezero Crater gallery feed, strictly separated from Gale route/DEM planning). Persisted products live in `datasets/catalog/imagery_products/catalog.json` with unverified rights/panorama eligibility kept explicit.

---

## 10. Prompt 12 Continuous Mesh Textures, NASA Source Audit & Live Mission Tracking (`/api/tracking/*`, `/api/sources/audit`)

### `GET /api/sources/audit`
- **Description:** Returns transparent verification/exclusion accounting across JPL Mars Trek WMTS layers (`mars_trek_tes_albedo`), USGS SIM 3292 (`1:20,000,000` global context-only disclosure), Curiosity rover waypoints, Perseverance Jezero Crater isolation (`isolated_from_gale_planning = true`), and NASA Worldview Earth-only exclusion (`excluded_earth_only`).

### Global Ramp & Continuous Seam Parameters (`/api/terrain/*`)
- `GET /api/terrain/mesh/manifest` returns region-wide `elevation_range_m` and `roughness_range_m` (`{ min_m, max_m }`).
- `GET /api/terrain/ortho/{dataset_id}/texture` accepts optional `vmin` and `vmax` parameters so neighboring WebGL tiles share an identical scalar colormap ramp (`Elevation`, `Slope`, `TRI`), plus subpixel bilinear ortho resampling without cross-tile seams.

### Authenticated Live Mission Telemetry (`/api/tracking/*`)
- **`GET /api/tracking/status` (`?active_route_id=`):** Returns live positioning telemetry state (`unavailable`, `active`, `stale`, `disconnected`). Defaults to `live_available = false` (`"Live Mars position unavailable — no mission positioning provider connected."`); browser/terrestrial geolocation (`navigator.geolocation`) is never used.
- **`POST /api/tracking/telemetry`:** Requires `X-Mars-Tracking-Token` or `Authorization: Bearer <token>` matching `MARSCOPE_TRACKING_TOKEN` (HTTP `401`/`403` otherwise). Validates `IAU2000:49900` coordinates, strictly monotonic `sequence_number` (HTTP `409` on out-of-order/duplicate sequence), timezone-aware timestamps, and computes Mars-sphere cross-track error (`R = 3,396,190 m`) and off-route flags against `active_route_id`.
- **`POST /api/tracking/replan-preview`:** Computes a confirmation-gated proposed DEM route diff (`requires_user_confirmation = true`, distance/gain/slope/duration deltas) from the latest verified live fix without automatically mutating the active route.
- **`GET /api/tracking/stream` & `DELETE /api/tracking/session`:** Server-Sent Events (`text/event-stream`) feed broadcasting `tracking_status` and `tracking_heartbeat` events, plus authenticated/operator session teardown restoring disconnected state.
