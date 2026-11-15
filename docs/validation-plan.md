# MARSCOPE Validation & Quality Assurance Plan

## 1. Automated Verification Architecture

MARSCOPE implements a multi-tier testing and validation framework ensuring scientific integrity, mathematical correctness, and operational stability.

```text
┌────────────────────────────────────────────────────────┐
│ 1. Scientific & Physical Law Benchmark Tests           │
│    - Gravity, Uphill Work, Atmospheric Density         │
├────────────────────────────────────────────────────────┤
│ 2. Geospatial Raster & Coordinate Registration Tests   │
│    - Slope calculation kernels, CRS transforms         │
├────────────────────────────────────────────────────────┤
│ 3. Constrained Pathfinding & Safety Invariant Tests    │
│    - Slope threshold invariants, Return reserve tests  │
├────────────────────────────────────────────────────────┤
│ 4. Backend API Contract Tests                          │
│    - Health check, study area schema, error handling   │
├────────────────────────────────────────────────────────┤
│ 5. Frontend Type Safety & Component Integrity Tests    │
│    - TypeScript compilation, Next.js build verification│
└────────────────────────────────────────────────────────┘
```

---

## 2. Test Specifications

### 2.1 Physics Benchmark Validation (`tests/physics/`)
- **Gravitational Weight Test:** Verifies that a $200\text{ kg}$ total system mass on Mars ($g = 3.72076\text{ m/s}^2$) yields $744.152\text{ N} \pm 0.001\text{ N}$.
- **Potential Energy Test:** Confirms $\Delta PE$ across a $100\text{ m}$ elevation rise equals $74,415.2\text{ J}$.
- **Atmospheric Density Test:** Benchmarks output of $\rho(p=750\text{ Pa}, T=210\text{ K})$ against the ideal gas equation of state ($\approx 0.0189\text{ kg/m}^3 \pm 1\%$).
- **Slope Force Test:** Asserts that on a horizontal surface ($\theta = 0^\circ$), uphill resistance $F_{\text{parallel}} = 0$, and at $\theta = 30^\circ$, $F_{\text{parallel}} = W \sin(30^\circ) = 372.076\text{ N}$.

### 2.2 Geospatial & Terrain Validation (`tests/terrain/`)
- **Slope Kernel Verification:** Synthetic DEM grids with known planar slopes ($0^\circ, 30^\circ, 45^\circ$) are processed through the slope operator to verify output within $0.05^\circ$ error.
- **Coordinate Boundary Assertion:** Validates that study area coordinates fall strictly within $[-90^\circ, +90^\circ]$ latitude and $[0^\circ, 360^\circ]$ or $[-180^\circ, +180^\circ]$ longitude.

### 2.3 Route Optimization & Constraint Invariants (`tests/routing/`)
- **Maximum Slope Invariant:** Any route generated must contain zero segments exceeding $\theta_{\text{critical}}$ ($25^\circ$).
- **Return-to-Base Consumable Invariant:** Verifies that at the furthest waypoint along the path, remaining energy $E_{\text{remain}} \ge 1.5 \cdot E_{\text{return\_cost}}$.
- **No-Fabrication Check:** Verifies that all waypoints and visited targets exist in the curated target registry.

### 2.4 API Integration Validation (`tests/api/`)
- `GET /api/health` must return HTTP 200 with JSON payload specifying active engines.
- `GET /api/study-area` must return bounding coordinates matching the Gale Crater specification.

---

## 3. Continuous Integration & Quality Gates

1. **Static Analysis:** TypeScript strict mode checking with zero errors; Python `flake8` or `ruff` linting.
2. **Automated Unit Testing:** Full `pytest` execution across the backend suite with minimum 90% branch coverage on physics and routing modules.
3. **Reproducibility Guarantee:** Clean installation and startup from repository root must succeed using standard setup commands.

---

## 4. Prompt 4 Scientific Discovery & Validation Suite (`backend/tests/`)

- **`test_pds_parsing_and_coords.py`:** Offline verification of PDS3 ODL pointer/`^STRUCTURE` resolution, ChemCam PSV (`DIGITAL_NUMBER`, full channel read) vs LIBS CCS differentiation, REMS schema-driven parsing without heuristic guesses, Gale Crater Equirectangular metric conversion, and guarantee that unlocated products never receive synthetic Gale coordinates.
- **`test_composition_discovery.py`:** Offline verification of controlled species alias/ambiguity resolution, IUPAC oxide-to-element stoichiometry, all critical failure modes of the 12-stage validation pipeline (`REMS`, `CHEMCAM-PSV`, invalid LIBS mineralogy, negative/`<LOD`/`>100 wt%`, Earth CRS rejection), SQLite R*Tree rebuild & antimeridian bbox wrap, SHA-256 checksum drift detection, `unlocated` spatial exclusion, strict `coverage_verification == VERIFIED` checks in destination evaluation, and `evidence_backed` vs `manual_unverified_administrative` target provenance separation.

---

## 5. Prompt 5 Scientific Integrity & Reproducibility Gate (`backend/tests/test_prompt5_scientific_integrity.py`)

- **Dynamic PDS3/PDS4 Schema Tests:** Verifies reordered ChemCam MOC `.LBL` columns + header mismatch rejection (`MalformedObservationError`), reordered APXS PDS4 `<Field_Delimited>` columns + blank `Quality` preserved as `None`, strict CheMin `^STRUCTURE` `.FMT` enforcement (`FileNotFoundError`), and rejection of unknown CheMin mineral phases (`UNKNOWN_SPECIES`).
- **Validation Gate Adversarial Checks:** Verifies Stage 1 missing provenance (`source_file_checksum`, `schema_version`, `parser_version`), Stage 9 uncertainty unit/type consistency, Stage 10 `location_semantic_type` consistency, and Stage 12 deterministic `evidence_id` verification.
- **Ranking Honesty & Reproducibility Checks:** Confirms `quality_component` and `corroboration_component` remain `None` when unreported/single-observation, custom `RankingConfiguration` provenance attachment, identical `generation_id` and sorted `evidence_id`s across two independent `rebuild_from_raw_directory` runs, and live `CHECKSUM_MISMATCH` / `SOURCE_FILES_MISSING` integrity drift detection.

---

## 6. Prompt 6 Evidence Semantics, Manifest Completeness & Staging Cutover (`backend/tests/test_prompt6_reproducibility_and_semantics.py`)

- **Uncertainty Compatibility & Cross-Type Quality Withholding:** Confirms `evaluate_uncertainty_compatibility` separates incompatible families (`apxs_analytical_precision`, `chemcam_pls_rmsep`, `chemcam_shots_stdev`, `chemin_rietveld_2sigma`, `chemin_estimated_error_unspecified_sigma`), withholds `quality_component = null` on mixed cohorts or qualitative `quality_flag`s without numeric scale, and preserves stoichiometric oxide-to-element `conversion_history`.
- **Strict PDS4 XML & CheMin Contract Adversarial Tests:** Confirms `parse_apxs_csv_with_contract(..., require_xml=True)` rejects missing `.XML`, unit conflicts, and corrupt numerics cleanly while isolating `parse_apxs_csv_unverified_header_only` at `0` accepted rows; verifies CheMin rejects non-quantitative `UNIT` values and labels omitting `"2-sigma"` record `chemin_estimated_error_unspecified_sigma`.
- **Source-Complete Drift, Safe Download & Staging Rollback Tests:** Verifies dependency checksum drift on `msl_waypoints.json` and `CHEMIN_MIN.FMT`, corrupt manifest JSON returning `MANIFEST_INVALID` and HTTP `422`, `safe_write_downloaded_bytes` rejecting HTML/empty/bad-JSON/checksum-mismatch while leaving existing valid files untouched, pre-cutover failure preservation of prior active generation, and `complete_with_declared_unavailable_sources` vs `partial` vs `--strict` failure states.

---

## 7. Prompt 7 Scientific Integrity Closure & Transaction-Safe Publication Suite (`backend/tests/test_prompt7_closure_and_tx_publication.py`)

- **CheMin Independent Uncertainty Unit Resolution:** Verifies `PERCENT` (`WEIGHT_PERCENT`) and `ERROR` (`ESTIMATED_ERROR`) resolve independently without coercing `ESTIMATED_ERROR` into `wt%`, preserves `None` + limitation when `UNIT` is omitted, converts compatible physical error units (`PPM` -> `wt%`), and rejects incompatible physical units (`KELVIN`).
- **Withheld Quality Score & Relative Uncertainty Validity:** Confirms `quality_component` stays `None` under `heuristic_exploration_priority_v4` `4.0.0`, while `RelativeUncertaintySummary` succeeds only for valid identical physical concentration units with `normalized_value > 0` and withholding `None` + explicit `unavailable_reason` for `0`, `ESTIMATED_ERROR`, mismatched units, and unspecified-sigma errors.
- **Measurement-Category-Aware Search & Sorting Guards:** Confirms elemental `min_value` excludes host-mineral `wt%` unless `measurement_category_filter="mineral_weight_percent"` is specified, per-(category, unit) abundance normalization works cleanly, flat mixed `sort_by="abundance"` raises `ValueError` (`422`), and partitioned `sort_by="category_abundance"` succeeds cleanly.
- **Canonical Manifest Authentication & Atomic Directory Publication:** Tests tamper detection across `notes`, `rights_summary`, `retrieval_metadata`, `generation_build_status`, `complete_manifest_digest`, and forged self-consistent manifest JSON (caught by DB/pointer cross-check); tests rollback safety across all 6 failure stages (`before_db_commit`, `after_db_commit`, `before_manifest_write`, `before_staging_validation`, `before_dir_publish`, `before_pointer_replace`); and runs concurrent `ThreadPoolExecutor` writers + readers confirming zero torn reads.

---

## 8. Prompt 8 Pre-Implementation Corrections & Human Mobility Intelligence Suite (`backend/tests/test_prompt8_mobility_and_corrections.py`)

- **Zero-Measurement Semantics (`test_zero_measurement_semantics_across_apxs_chemcam_and_chemin`, `test_validation_stage6_rejects_unsupported_bdl_and_source_missing_constants`):** Verifies that numerical zeros (`0.0`) across APXS, ChemCam MOC, and CheMin RDR5 are preserved as `reported_numerical_zero_unresolved_semantics` (`MEASURED`/`UNLOCATED`) rather than converted into `BELOW_DETECTION_LIMIT`, while Stage 6 rejects unsupported BDL inference (`UNSUPPORTED_BDL_INFERENCE`) and source-defined missing constants (`SOURCE_DEFINED_MISSING_VALUE`).
- **No Silent DEM Footprint Expansion (`test_dem_processor_never_silently_expands_small_footprint`):** Confirms that a small study region (`< 3x3` pixels on MOLA 4 ppd) raises `InsufficientDEMCoverageError` with `requested_bounds_modified = False`.
- **No Default 25° Safety Threshold (`test_no_default_25_deg_safety_threshold_and_explicit_planning_threshold`):** Confirms `critical_slope_threshold` is removed from `PARAMETER_REGISTRY`, `TerrainSummary.planning_threshold` defaults to `None`, and optional `PlanningSlopeThreshold` is tagged `is_validated_safety_limit = False`.
- **Reader Lease Protection (`test_generation_reader_lease_prevents_pruning_of_in_flight_generation`):** Confirms a reader holding `acquire_generation_lease()` prevents active generation deletion across 3 consecutive `publish_generation()` rebuilds until the lease is released.
- **Human Mobility Intelligence Engine (`test_resolution_suitability_distinguishes_regional_and_local_regimes`, `test_coverage_5_states_and_elevation_profile_with_nodata_gaps`, `test_mobility_scenario_and_traversal_model_no_defaults_and_no_extrapolation`, `test_mobility_api_endpoints_live_contracts`):** Verifies resolution suitability across all 4 analysis scales, 5-state coverage intelligence, elevation gain/loss profiles with contiguous `nodata_gap_segments`, `MobilityScenario` & `TraversalModel` domain/extrapolation/null-cost invariants, and all 9 `/api/mobility/*` endpoints.
# Prompt 9 partial explorer verification (2026-11-14)

- `npm run lint` in `frontend`: passed.
- `npm run build` in `frontend`: passed (Next.js 16.4.6, webpack production build).
- `pytest -q` in `backend`: 71 passed, 28 deprecation/pending-deprecation warnings.
- `python3 -m compileall -q app` in `backend`: passed.
- `git diff --check`: passed at the time of the initial check; rerun after documentation edits before committing.
- No browser-based gesture testing or before/after FPS, frame-time, CPU, memory, rerender, switch-time, panorama-load, or terrain-load measurement was performed.
- No real Navcam product integration or acquisition was performed; the acquired MRO HiRISE RDR original is recorded below. No live archive search result is counted as a discovered or acquired MARSCOPE panorama.
- Acceptance items requiring four synchronized modes, dynamic panorama discovery/viewing, DEM-derived terrain geometry, route-sketch synchronization, or actual NASA image verification remain unimplemented.

## Imagery validation

Offline test command: `cd backend && pytest -q`. These tests use small synthetic fixtures explicitly identified as fixtures, and exercise Atlas response normalization, original product identity, dimensions, checksums, metadata gaps, and catalogue persistence. They require no NASA data or network access.

NASA integration test command: `cd backend && NASA_INTEGRATION=1 pytest -m nasa_integration -q -s`. It queries ODE for all three prioritized MSL Navcam datasets and exact PDS Atlas MSL/Navcam, printing found/downloaded/checksum/parsed state. The currently observed live response reports invalid IIPT and is reported as unavailable, not as an empty successful result. No original product has been downloaded by this test.

Panorama validation remains pending until an individual archive product is acquired and its label/image content supports dimensions, projection, angular coverage, orientation, and station association. No synthetic or inferred panorama is accepted.

The live NASA integration run on 2026-11-14 queried ODE for `MSL-M-NAVCAM-5-RDR-V1.0`, `MSL-M-NAVCAM-5-RDR-MOSAIC-V1.0`, and `MSL-M-NAVCAM-2-EDR-V1.0`. All three are reported individually by the test; the current ODE response for the `MSL/NAVCAM/RDR` combination is `Invalid IIPT`, so archive discovery is unavailable there rather than an empty successful result. Atlas independently returned 0 for its exact MSL/Navcam instrument filter. Three broader MSL/MSAM IMG records were returned and persisted; all three image and label URLs returned HTTP 404. ODE also returned one MRO HiRISE RDR and one MRO CTX EDR product with center coordinates and footprints. One HiRISE PDS3 label was retrieved and parsed, and one original 307,736,024-byte JP2 was acquired and verified for HTTP content length and JP2 signature. Its SHA-256 was computed; no archive checksum was supplied, so archive checksum comparisons verified remain 0. Across five persisted records, panorama eligibility is 0 and ODE-sourced geographic associations are 2.

---

## 10. Prompt 11 Real 3D Terrain Mesh & Science-Aware Routing Verification

- **Unit & Adversarial Synthetic Suites (`backend/tests/test_prompt11_terrain_mesh.py`, `test_prompt11_routing.py` — 12 tests passed):**
  - Verifies bit-identical seam coordinates across adjacent LOD `0..2` heightfield tiles, strict `valid_mask == 0` omission on oblique/NoData cells, non-zero finite Horn normals, ortho/elevation/slope/TRI PNG texture rendering, and Cesium `HeightGridResponse` alignment.
  - Verifies A* == Dijkstra exact path cost across all 3 routing modes, steep cliff saddle detours, strict prohibition of diagonal corner-cutting, obstacle/NoData/3D-chord-deviation protection in `simplify_leg_safely`, mode differentiation/honest rejection, omitted walking-speed honesty (`estimated_duration_seconds = None`), `gravitational_climb_work_joules` physics calculation, True/Grid North bearings, and `route_optimization_enabled = True` / `safety_certification_enabled = False`.
- **Real NASA HiRISE & MOLA Integration Suite (`backend/tests/test_prompt11_real_nasa_integration.py` — 4 tests passed):**
  - Exercises real 1.01 m/px HiRISE DTMs (`DTEEC_009149_1750_009294_1750_U01.IMG`, `DTEEC_040770_1755_039280_1755_U01.IMG`), orthorectified JP2s, and 463 m/px MOLA 128ppd (`MEGT00N090HB.IMG`): checks manifest/tile streaming, HiRISE ortho & derivative PNG generation, multi-stop Gale Crater / Boxwork 8-connected pathfinding + 3-mode comparison, corridor evidence hit matching, and valid GeoJSON export.
- **Complete Repository `pytest` Suite:** `95 passed, 2 skipped` (`test_live_ode_navcam_rdr_holdings_report` and `test_live_atlas_navcam_discovery_report` skipped without `NASA_INTEGRATION=1`).
- **Headless Chrome CDP Live E2E Verification (`task-3607`):**
  - Audited all 10 production App Router routes (`/`, `/explorer`, `/planner`, `/routes`, `/simulation`, `/targets`, `/evidence`, `/imagery`, `/terrain`, `/settings`) via production `next start` + live `uvicorn`: **0 console errors, 0 page errors, 0 React update loops, 0 HTTP 5xx responses**.
  - Verified dual Three.js + CesiumJS WebGL canvases on `/explorer` (`Split View`), interactive route computation (`1,452.5 m` 3D surface dist, 40 turn-by-turn rows with True/Grid North headings, elevation profile chart), parameter-change stale-route warning (`staleBannerOnEdit: true`), `/routes` 3-mode trade-off comparison matrix (with honest `Conservative` rejection & `Balanced`/`Science-Priority` feasibility), and `/simulation` 3D playback scrubber with explicit `Not Modeled (Unvalidated)` physiological disclosure.
  - Direct FastAPI endpoint latency sample (`verify_e2e_browser.mjs`): `/api/health` `189.73 ms`, `/api/terrain/mesh/manifest` `11.84 ms`, `/api/terrain/mesh/tiles/L1_R0_C0` `161.32 ms`, `/api/terrain/ortho/.../texture` `278.82 ms`, `/api/routing/compare` (3 modes over HiRISE DTM) `2,115.43 ms`.

---

## 11. Prompt 12 Continuous Terrain, Tracking & Reproducibility Verification

- **Prompt 12 Adversarial Suite (`backend/tests/test_prompt12_continuous_terrain_tracking.py`):**
  - `test_cross_tile_normals_and_elevation_color_continuity`: Verifies cross-tile shared edge elevations (`< 1e-4 m`) and central-difference vertex normals (`< 1e-3`) match cleanly across E/W and N/S tile seams (including raster rim clamped bilinear sampling) plus continuous global `vmin`/`vmax` shaded PNG transitions (`mean diff < 3.0`).
  - `test_route_provenance_and_compare_algorithm_forwarding`: Verifies full route `provenance` metadata and distinct algorithm forwarding (`astar` vs `dijkstra`) in `compare_routes`.
  - `test_authenticated_live_tracking_lifecycle_and_replan_preview` & `test_http_tracking_endpoints_sources_audit_and_perseverance_isolation`: Verifies disconnected default status, HTTP `401`/`403` token enforcement, rejection of browser `navigator.geolocation`/terrestrial providers (`422`), `IAU2000:49900` bounds & monotonic sequence enforcement (`409`), Mars-sphere cross-track / off-route detection, confirmation-gated `/api/tracking/replan-preview`, stale transition, `/api/sources/audit` (`excluded_earth_only` NASA Worldview & USGS SIM 3292 `1:20,000,000`), and `/api/imagery/perseverance` Jezero Crater isolation.
  - `test_clean_checkout_empty_raw_and_processed_honesty`: Verifies empty `RAW_DIR`/`PROCESSED_DIR` isolation demotes absent local DEMs strictly in memory without mutating tracked `datasets/catalog/*.json`.
- **Full Backend Pytest & Clean-Checkout Process Isolation:** `101 passed, 2 skipped` (`NASA_INTEGRATION=1` gated live ODE/Atlas tests). Direct FastAPI endpoint latencies (`bench.py` against `hirise_dteec_009149_1750`): `/api/terrain/mesh/manifest` `0.90 ms`, `/api/terrain/mesh/tiles/L1_R0_C0` `1.70 ms`, uncached PNG overlays (`elevation` `133.79 ms`, `slope` `179.81 ms`, `roughness` `4.78 ms`, `ortho` `345.57 ms`; cached `0.42–1.50 ms`), `/api/routing/compute` `318.84 ms`, `/api/routing/compare` `767.72 ms`, SSE `tracking_status` unbuffered first event `22.04 ms` via Next.js proxy (`Cache-Control: no-cache, no-transform`).
- **Headless Chrome CDP Production E2E Verification (`19/19 passed`, `0` console/runtime exceptions, `0` localhost HTTP 4xx/5xx):** Verified non-overlapping WebGL HUD across `/explorer` Split View & Mars Globe, blank initial `/planner` inputs, `Boxwork Study Example` (`1,631 ms`), hot-swapped `Slope (°)`/`Elevation` overlays without camera reset (`909 ms`), `LOD 2` & `Tiles` seam-free rendering, collapsible Alternative Routes (`Conservative REJECTED`, `Balanced FEASIBLE`, `Science-Priority FEASIBLE` labeled `Lowest calculated terrain cost`), clickable Turn-by-Turn navigation, end-to-end authenticated telemetry SSE UI update (`270 ms`), `/routes` Recharts matrix, isolated `/simulation` (`SIMULATION — NOT LIVE MISSION TELEMETRY`), `/imagery` Jezero Crater banner, and blank `/settings` Physics inputs + example execution.

---

## 12. Prompt 18 Scientific Integrity, Real NASA Acquisition & Benchmark Verification

- **Adversarial Scientific Integrity Suite (`backend/tests/test_prompt18_scientific_integrity.py` — 15/15 passed):**
  - **Semantics (Sec 16.1):** `scientific_value` never copied from `exploration_priority_score`, optical/elemental/non-detection inference firewall enforcement, `UNVERIFIED` / mission-isolated instruments disqualified, duplicate SHA-256 non-corroboration + contradicting observation retention, `estimated_data_volume_mb = None` (`UNAVAILABLE`).
  - **Product Validation (Sec 16.2):** Rejection of integer DEMs lacking `SCALING_FACTOR`, missing measurement `UNIT`s, corrupt GeoTIFF headers, wrong binary signatures, `max_bytes` overflow, SHA-256 mismatch, invalid raster dimensions, malformed PDS4 XML, unverified calibration states, and WMTS exclusion from quantitative slope/mineral evidence.
  - **CRS & Spatial Registration (Sec 16.3):** Rejection of `EPSG:4326`/Earth CRS, Planetocentric vs Planetographic and East vs West longitude mismatches, axis radii checks, partial/disjoint bounding overlap detection, resolution incompatibility, and resampling provenance.
  - **Targets, Campaigns & API Security (Sec 16.4):** Wrong-mission/irrelevant dataset gating, missing constraints (`INCOMPLETE_CONSTRAINT_EVALUATION`), tight budget infeasibility (`INFEASIBLE_UNDER_CONFIGURED_MODEL`), `STALE_UPSTREAM_DEPENDENCY_CHANGED` signature detection + recomputation, fail-closed `403`/`401` rebuild auth, and HTTP `422` guards.
  - **Acquisition Resilience (Sec 16.5):** HTTP `503` retry + simulated mid-stream TCP reset recovery via HTTP `206` Range resumption (`aiter_bytes(chunk_size=None)`), artifact reuse, non-overwrite `FileExistsError` protection, and append-only ledger/query provenance persistence.
- **Real NASA Workspace & Live PDS Archive Suite (`backend/tests/test_prompt18_real_nasa_integration.py`):**
  - **Layer A Offline Workspace End-to-End (`PASSED`):** Verifies authentic HiRISE DTM (`DTEEC_009149_1750_009294_1750_U01.IMG` + `hirise_dteec_009149_1750_dem.tif` raster stats), PDS4 APXS (`DS01_2021JE007171R.xml` 20+ columns), MOLA MEGDR (`MEGT00N090HB.LBL` `scaling_factor = None` honesty), 17-dimension inspection, provenance graph construction, multi-stop campaign planning, and campaign dossier export.
  - **Layer B Live NASA Archive Integration (`NASA_INTEGRATION=1`, `PASSED` in 5.16s):** Live query against `https://pds-geosciences.wustl.edu/msl/msl-m-chemin-4-rdr-v1/mslcmn_1xxx/data/rdr5/` (`sol_min=75..90`), live acquisition of `CMA_404470826MIN00790050104CH11503P1` (`152 bytes`, SHA-256 `0e4cbfa2b190148966a92b499710cbc7bcd51ad856c3490a08de02f929d2954b`), companion `.lbl` verification, and `DatasetCatalogService.validate_dataset_integrity` (`PRODUCT_VALIDATED`).
- **Complete Repository Verification & Measured Benchmarks:**
  - **Full Backend Suite (`pytest -q`):** `158 passed, 3 skipped` (3 network-gated NASA live tests skipped without `NASA_INTEGRATION=1`; live CheMin test verified separately with `NASA_INTEGRATION=1`).
  - **Frontend Production Build:** `npx tsc --noEmit`, `npm run lint`, and `npm run build` exited `0` (`17` App Router routes).
  - **Real Gale HiRISE Benchmarks (`hirise_dteec_009149_1750`):** GeoTIFF inspection across `2,143,296` pixels `31.56 ms`; outbound route (`128.4 m`, `5` vertices) `257.79 ms`; `8`-scenario sensitivity evaluation `72.54 ms`; distinct multi-route comparison (`2` alternatives) `402.58 ms`; independent return + `4` turnback checkpoints (`129.96 m`) `234.28 ms`.
