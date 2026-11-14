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
