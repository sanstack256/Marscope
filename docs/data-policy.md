# MARSCOPE Open Data & Scientific Integrity Policy

## 1. Core Principles

MARSCOPE was conceived as a rigorous, open-science entry for the **NASA Space Apps Challenge**. Scientific credibility, reproducibility, and open data access are foundational pillars of the project.

### 1.1 Unencumbered Open Licensing
Every scientific dataset utilized by MARSCOPE must possess an explicitly verified, legally binding open reuse license:
- **NASA Data:** Pursuant to US Government open science guidelines and NASA Scientific Information Policy (SPD-41a), scientific data produced by NASA missions is placed in the public domain or licensed under Creative Commons Zero (CC0 1.0 Universal).
- **International Partner Data (ESA / JAXA):** Data from partner instruments (e.g., Mars Express HRSC) must comply with their respective open scientific reuse agreements.
- **Strict Prohibition on Commercial Assets:** MARSCOPE strictly prohibits proprietary data, commercial satellite imagery, paid mapping APIs (e.g., Google Maps API keys, Mapbox paid tokens, Cesium Ion paid assets), or data carrying non-commercial/restrictive terms that impede open scientific reproduction.

---

## 2. Mandatory Dataset Metadata Requirements

Every planetary dataset registered in MARSCOPE must have an accompanying entry in `DATA_SOURCES.md` and the machine-readable catalog (`datasets/catalog/`):

1. **Dataset Canonical Name:** Formal mission name and product description.
2. **Product Identifier:** Exact PDS identifier (e.g., `ESP_036128_1755_COLOR`).
3. **Mission & Sensor:** Sponsoring space agency, spacecraft, and instrument suite.
4. **License Status:** Verified open-source or public domain license.
5. **Attribution Text:** Standard institutional citation.
6. **Acquisition Epoch:** UTC acquisition date and Martian Solar Longitude ($L_s$).
7. **Processing Pipeline Level:** Raw (EDR), Calibrated (RDR), or Derived (DDR/DTM).
8. **Coordinate System:** Formal CRS definition and geodetic datum.
9. **Native Resolution:** Spatial pixel scale (m/pixel or pixels/degree).
10. **Data Units:** Physical measurement units (DN, reflectance, meters, Kelvin).
11. **Bounding Extent:** Verified geographic coordinates (Lat/Lon).
12. **Limitations & Artifacts:** Documented sensor noise, shadowing, or interpolation gaps.

---

## 3. Scientific Integrity & Anti-Fabrication Mandate

To preserve absolute scientific authenticity:
- **No Synthesized NASA Data:** Under no circumstance will MARSCOPE synthesize fake spectral peaks, fabricate Curiosity rover geochemical assays, or manufacture artificial hazard points.
- **Clear Demarcation:** The system must strictly distinguish between:
  1. *Direct Physical Measurements* (e.g., REMS ambient pressure, CheMin mineral detections).
  2. *Empirical Derived Products* (e.g., DEM-calculated slope angles).
  3. *Engineering & Mission Assumptions* (e.g., astronaut walking pace, suit mass, safety reserve multipliers).
- **Graceful Missing Data Handling:** Where high-resolution coverage is absent (e.g., HiRISE DTM gap), the system must explicitly present an informative "Coarse Resolution / Data Gap" state rather than silently interpolating or hallucinating terrain.

---

## 4. Prompt 4 Zero-Fabrication Enforcement in Composition Discovery

1. **No Synthetic Coordinate Fallback:** Products without verified coordinates (e.g., REMS telemetry, unlinked ChemCam PSVs, or CheMin drill RMCs missing from JPL `MSL_waypoints.json`) are never assigned Gale Crater defaults (`-4.65°, 137.42°`). Unlocated composition evidence is labeled `EvidenceStatus.UNLOCATED` and counted in `unlocated_matches_count` without entering spatial candidate maps.
2. **12-Stage Validation & Rejection Audit Log:** Every ingested row passes through 12 sequential gates (`validate_composition_evidence`): dataset identity, non-composition instrument exclusion, calibration/passive-DN exclusion, LIBS vs XRD methodology check, controlled vocabulary check, null/NaN/negative/`<LOD` rejection, physical `[0, 100] wt%` bounds, unit normalization, uncertainty integrity, IAU2000 CRS + provenance check, quality flagging, and final admissibility. Failed records emit permanent `RejectionRecord` entries queryable via `GET /api/composition/rejected`.
3. **Strict Target Provenance Demarcation:** Targets created from verified index hits carry `target_status = "evidence_backed"` with immutable `evidence_ids`, whereas manual coordinates without backing composition evidence carry `target_status = "manual_unverified_administrative"`.
4. **Honest Orbital Spectral Status:** When no localized MRO CRISM mineral cube is present, the composition index reports `crism_status = "unavailable_no_validated_mineral_cube"` rather than implying orbital mineral coverage.

---

## 5. Prompt 5 & 6 Reproducibility, Source-Complete Manifests & Atomic Publication

1. **Provenance-Bound Identifiers (`evidence_id_v2`):** `evidence_id` values are computed as SHA-256 digests (`ev_<hex>`) binding `determinism_version|source_dataset_id|product_id|source_record_ref|canonical_species_id|raw_species_name|evidence_type|source_file_checksum|source_artifact_dependency_digest|schema_version|parser_version` and re-verified at Validation Stage 12 (`EVIDENCE_ID_MISMATCH`). Spatial index `generation_id` values derive deterministically from sorted dependency/product SHA-256 digests and validated evidence digests (`gen_<hex>`).
2. **Zero Guessed Quality, Uncertainty, Rights, or Acquisition Dates:** Unreported positional uncertainties remain `null`; qualitative `quality_flag` values never produce numeric ranking floats; CheMin error values without `"2-sigma"` label documentation remain `chemin_estimated_error_unspecified_sigma`; pre-existing local files record `retrieval_timestamp_utc = "unknown"` (never file mtime masquerading as retrieval time); and source artifacts without embedded license metadata record `license_status = "not_verified"`.
3. **Safe Atomic Acquisition & Transaction-Safe Immutable Generation Publication:** Downloads validate non-empty payload, reject HTML error pages for data/JSON extensions, verify JSON syntax and expected SHA-256, write to temp files before `os.replace`, and emit `.{name}.retrieval.json` sidecars without clobbering pre-existing valid files on failure. Index rebuilds serialize under an exclusive `flock` (`.publish.lock`), stage into `generations/.staging_<gen_id>__<nonce>_pid<pid>/`, compute separated `source_artifact_digest` (input artifacts) and `complete_manifest_digest` (SHA-256 over canonical JSON bytes of the entire reproducibility manifest excluding self-digest), verify DB/manifest agreement + deterministic IDs + source dependencies, promote into immutable `generations/<gen_id>__<nonce>/`, and atomically swap `active_generation.json` (`os.replace`), retaining `previous_successful_generation_id`. Any tamper with manifest, pointer, SQLite header, or source files immediately triggers separated status failures (`source_integrity_status`, `manifest_integrity_status`, `pointer_integrity_status`, `database_integrity_status`).
4. **Prompt 8 Reader Lease Protection & Mobility Data Honesty:** Readers acquire per-process leases (`acquire_generation_lease()`) inside `generations/.leases/` so concurrent index rebuild pruning never removes an active generation directory while a reader is in flight. Terrain and mobility endpoints enforce `footprint_policy = "no_expansion_v1"` (never enlarging requested bounds), preserve `null` costs on unknown/no-data pixels, and prohibit default walking speeds, unverified physiological/metabolic models, and safety certifications.
# Prompt 9 imagery and terrain availability

No MSL Navcam panorama products have been acquired, checksummed, or parsed in this workspace. Do not draw panorama stations, imply 360-degree coverage, or infer orientation from product names. The existing Cesium ellipsoid terrain is a reference surface, not DEM geometry. Local DEM analysis and raster display do not mean a ground-level 3D mesh is available. Dataset-level PDS records establish archive existence only; product counts, image coverage, projection, and camera pose remain unknown until verified against actual products and labels.
