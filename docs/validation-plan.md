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
