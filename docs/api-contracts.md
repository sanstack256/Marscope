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
- **Description:** Returns DEM inventory, download/processing status, per-scale resolution suitability (`regional_elevation_analysis`, `local_slope_analysis`, `regional_roughness_analysis`, `small_scale_obstacle_detection`), and explicit confirmation that `route_optimization_enabled = false` and `safety_certification_enabled = false`.

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
