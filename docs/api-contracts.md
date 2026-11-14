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
- **Description:** Returns live SQLite R*Tree spatial index generation metadata (`active_generation_id`, `located_evidence_count`, `unlocated_evidence_count`, `rejected_record_count`, `instruments_indexed`, `checksum_valid`, `rtree_enabled`, `crism_status`).

### `POST /api/composition/index/rebuild`
- **Description:** Scans `datasets/raw/`, runs PDS3/PDS4 adapters + coordinate association + 12-stage validation, and atomically publishes a new generation in `datasets/index/composition_index.sqlite`.

### `POST /api/composition/search` (and `POST /api/destinations/search-composition`)
- **Description:** Resolves an element/oxide/mineral query (`search_mode`: `auto | element | mineral | element_bearing_mineral`), applies R*Tree spatial bounding boxes & filters, computes Mars IAU2000 geodesic distance/bearing from astronaut coordinates, and returns ranked `hits`, clustered `candidate_locations`, `unlocated_matches_count`, and `scientific_warnings`.

### `GET /api/composition/evidence/{evidence_id}`
- **Description:** Returns full `CompositionEvidence` provenance, raw vs stoichiometric conversion formula, coordinate derivation source, and all 12 `validation_stages`.

### `GET /api/composition/rejected`
- **Description:** Returns paginated `RejectionRecord` audit log (`?limit=50&offset=0`) showing why passive PSVs, REMS tables, `<LOD` measurements, unknown CheMin species, or invalid records were excluded.

### `GET /api/composition/reproducibility-manifest`
- **Description:** Returns `datasets/index/reproducibility_manifest.json` containing `generation_id`, `generation_build_status` (`complete | complete_with_declared_unavailable_sources | partial | failed`), `discovery_scope`, `source_manifest_checksum`, `products`, `dependency_artifacts` (primary + companion `.LBL`/`.XML`/`.FMT`/`msl_waypoints.json` with `license_status` and `retrieval_timestamp_utc`), `product_audit`, `rights_summary`, `retrieval_metadata`, and `RankingConfiguration` (`heuristic_exploration_priority_v3` `3.0.0`). Raises HTTP `422` if the manifest JSON is malformed or invalid. Also `GET /api/composition/index/status` exposes `integrity_status` (`verified | source_files_missing | checksum_mismatch | manifest_invalid | stale | incomplete | unavailable`), `generation_build_status`, `source_dependencies_valid`, `manifest_valid`, `missing_dependency_files`, `dependency_checksum_mismatches`, `missing_expected_products`, and `manifest_validation_errors`.

### `POST /api/targets/generate`
- **Description:** Deterministically generates `evidence_backed` `ScienceTarget` records from top-ranked composition discovery clusters, storing immutable `evidence_ids` and distance/rationale metadata. Also `GET /api/sources/msl/archive-query` exposes live NASA PDS/ODE archive product discovery.

### `POST /api/missions/{mission_id}/replan`
- **Description:** Triggers real-time replanning for an active mission given mid-traverse contingency inputs (e.g. reduced oxygen reserve).

---

## 5. Provenance & Metadata Endpoints

### `GET /api/sources`
- **Description:** Returns complete dataset registry matching `DATA_SOURCES.md`, including PDS product identifiers, licensing status, and citations.
