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

### `POST /api/missions/{mission_id}/replan`
- **Description:** Triggers real-time replanning for an active mission given mid-traverse contingency inputs (e.g. reduced oxygen reserve).

---

## 5. Provenance & Metadata Endpoints

### `GET /api/sources`
- **Description:** Returns complete dataset registry matching `DATA_SOURCES.md`, including PDS product identifiers, licensing status, and citations.
