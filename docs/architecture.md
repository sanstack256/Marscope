# MARSCOPE Technical Architecture

## 1. System Overview

**MARSCOPE (Martian Surface Intelligence & Exploration System)** is engineered as a decoupled, modern scientific web platform designed for high-resolution planetary data processing, physics-grounded terrain analysis, and constrained route optimization.

```mermaid
graph TD
    subgraph Client["Frontend Architecture (Next.js 14 / TypeScript)"]
        UI["Application Pages (9 Specialized Workspaces)"]
        State["Zustand Reactive Stores (Layers, Targets, Route)"]
        Globe["CesiumJS 3D Mars Globe & MapLibre GL 2D Engine"]
        Viz["Recharts Visual Telemetry & Elevation Profiles"]
        UI --> State
        State --> Globe
        State --> Viz
    end

    subgraph API_GW["API & Networking"]
        HTTP["RESTful API (JSON / OGC GeoJSON)"]
        CORS["Strict Local CORS / Security Headers"]
    end

    subgraph Server["Backend Architecture (FastAPI / Python 3.11+)"]
        API["FastAPI Routing Endpoints (/api/*)"]
        Ingest["Ingestion Pipeline & Product Readers (PDS / GDAL)"]
        Geo["Geospatial & Terrain Engine (Rasterio / GeoPandas)"]
        Phys["Physics Engine (Registry, Units, Gravity, Drag, Dose)"]
        Route["Constrained Graph Routing Engine (NetworkX / A*)"]
        API --> Ingest
        API --> Geo
        API --> Phys
        API --> Route
    end

    subgraph Storage["Data Tier & Planetary Archives"]
        COG["Cloud-Optimized GeoTIFFs (MOLA / HiRISE DTM)"]
        Vec["GeoJSON Target Catalog & Observations"]
        PDS["NASA PDS / Mars Trek Open WMTS Services"]
    end

    Client <-->|HTTP REST / GeoJSON| API_GW
    API_GW <--> Server
    Server --> Storage
```

---

## 2. Frontend Subsystem (`frontend/`)

- **Next.js & React 18+ (App Router):** High-performance component-driven interface with hybrid rendering. Server components handle static documentation and initial shell delivery, while client components manage interactive 3D viewports and stateful planners.
- **CesiumJS 3D Surface Engine:** Provides a genuine planetary globe configured with the Mars reference ellipsoid (IAU2000:49900). Supports draping HiRISE and CTX orthorectified imagery over 3D terrain meshes.
- **MapLibre GL JS:** High-speed 2D fallback and specialized planar projection viewer for localized traversability overlays and slope gradient heatmaps.
- **Zustand State Management:** Lightweight, zero-boilerplate reactive stores managing:
  - Active map layer visibility and opacity.
  - Selected scientific targets in the mission planning basket.
  - Active calculated route geometry, elevation profile, and telemetry.
- **Design System:** Custom aerospace dark theme built with Tailwind CSS, utilizing high-contrast data visualization palettes compliant with WCAG accessibility standards.

---

## 3. Backend Subsystem (`backend/`)

- **FastAPI Framework:** Asynchronous, self-documenting (OpenAPI / Swagger) Python backend engineered for low-latency spatial and graph queries.
- **Geospatial & Terrain Processing (`app/geospatial`, `app/terrain`):**
  - Uses `GDAL`, `Rasterio`, `Shapely`, and `pyproj` to reproject and clip Martian rasters.
  - Generates derivative rasters: slope (degrees), aspect (radians), and Terrain Ruggedness Index (TRI).
- **Physics Engine (`app/physics`):**
  - Pure, deterministic Python modules strictly enforcing SI units.
  - Versioned parameter registry defining Martian planetary constants.
  - Computes uphill gravitational force components, atmospheric density variations, and cumulative radiation exposures.
- **Traversability & Routing Engine (`app/routing`):**
  - Transforms processed DEM rasters into 8-connected directed spatial graphs.
  - Employs constrained A* and Dijkstra pathfinding incorporating directional slope penalties, roughness factors, and non-negotiable return-to-base consumable reserves.

---

## 4. Data Pipeline & Persistence

- **Local Storage Strategy:** Raw datasets are stored in `datasets/raw/` (git-ignored), processed into Cloud-Optimized GeoTIFFs (COGs) with overviews in `datasets/processed/`, and referenced through JSON catalogs in `datasets/catalog/`.
- **Coordinate Reference System Uniformity:** All incoming datasets are normalized to the standard Mars reference frame (`IAU2000:49900` or local projected equidistant frame centered at Gale Crater: $137.4^\circ\text{ E}, 4.6^\circ\text{ S}$) prior to analysis.

---

## 5. Prompt 4 Scientific Discovery Engine & Spatial Indexing Subsystem

- **PDS3 / PDS4 Schema-Driven Parsing & Coordinate Association (`app/ingestion/pds_label.py`, `app/science/coordinate_association.py`, `app/science/curiosity_parser.py`):** Full ODL nested structure parser (`^STRUCTURE` `.FMT` includes, byte-offset pointers, `ROVER_MOTION_COUNTER`), Gale Equirectangular metric transformation (`R=3,396,190 m`), and JPL `MSL_waypoints.json` RMC joiner.
- **Validation, Uncertainty & Normalization Engine (`app/science/composition/`):** Controlled IUPAC species registry (`species.py`), `wt%`/`ppm` and oxide-to-element stoichiometry (`normalization.py`), uncertainty compatibility registry (`uncertainty.py`) enforcing statistical comparability in `ranking.py`, 12-stage validation pipeline + `RejectionRecord` emitter + `evidence_id_v2` (`validation.py`), and strict schema-enforced adapters (`adapters.py`) for APXS (PDS4 `.XML`), ChemCam MOC/PSV (`.LBL`), CheMin RDR5 (`.LBL`/`.FMT`), CRISM honesty guard, and REMS exclusion.
- **Transaction-Safe Immutable Generation Publication (`app/science/composition/index.py`):** Exclusive `fcntl.flock` (`.publish.lock`) serializes concurrent rebuilds; builds stage inside `generations/.staging_<gen_id>__<nonce>_pid<pid>/` (`journal_mode=DELETE` self-contained SQLite + canonical JSON manifest authenticated by `complete_manifest_digest` vs `source_artifact_digest`), promote to immutable `generations/<gen_id>__<nonce>/`, and atomically swap `active_generation.json` via `os.replace` while retaining `previous_successful_generation_id` and automatically cleaning incomplete staging directories. Readers resolve `(sqlite_path, reproducibility_manifest_path, complete_manifest_digest)` atomically through `active_generation.json` for tear-free concurrent access.
- **Mars Geodesic Discovery & Interactive Globe Sync:** `CompositionSearchService` clusters spatially verified hits into `CandidateDiscoveryLocation`s using `pyproj.Geod` (`IAU2000`), synchronized with CesiumJS clickable markers in `MarsGlobeViewer.tsx`, Minerals Explorer workbench, Target Explorer (`target_status` provenance badge), and Evidence Audit UI.

---

## 6. Prompt 8 Human Mobility Intelligence Engine (`backend/app/mobility/`)

- **Modular Subsystem Architecture:**
  - `models.py` & `schemas.py`: Domain enumerations (`TerrainCoverageState`, `ResolutionSuitabilityLevel`, `AnalysisScaleType`, `ParameterOriginType`, `CellTraversalAvailabilityState`) and Pydantic request/response contracts.
  - `resolution.py`: Resolution suitability evaluator across `regional_elevation_analysis`, `local_slope_analysis`, `regional_roughness_analysis`, and `small_scale_obstacle_detection`.
  - `coverage.py`: 5-state spatial coverage and unknown-data intelligence (`outside_source_footprint`, `inside_footprint_nodata`, `valid_source_data`, `insufficient_resolution_for_analysis`, `derivative_unavailable_invalid_neighborhood`) with spherical surface area integration on $R = 3,396,190\text{ m}$.
  - `terrain_features.py`: Windowed extraction of elevation, Horn `3x3` slope, compass aspect (`[0, 360)` clockwise from North; flat cells undefined), metric TRI roughness, and geodesic 2-point/polyline elevation gain/loss profiles.
  - `mobility_scenario.py`, `traversal_model.py`, `cost_surface.py`: Persisted `MobilityScenarioRegistry` (`datasets/processed/mobility_scenarios.json`), assumption-transparent `TraversalModel` (`transparent_kinematic_v1`), and per-cell `TraversalCostSurface` generator (`CostSurfaceSummary`) preparing validated inputs for future mission planning without performing route optimization.
# 7. Prompt 11 Real 3D Martian Terrain & Science-Aware Routing Architecture

## 7.1 Dual-Engine 3D Terrain Architecture
- **Local High-Resolution 3D Heightfield Mesh Engine (`backend/app/terrain/mesh.py`, `backend/app/api/terrain_mesh.py`):**
  - Samples real NASA PDS/GeoTIFF DEMs (`hirise_dteec_009149_1750`, `hirise_dteec_040770_1755`, `mola_megt00n090hb`) across hierarchical LOD pyramids (`LOD 0`: `1x1` base tile, `LOD 1`: `2x2`, `LOD 2`: `4x4`, `65x65` vertices per tile).
  - Enforces **seam continuity** via deterministic tile edge coordinates so adjacent tiles share bit-identical `(east_m, north_m, elevation_m)` positions, and emits strict `valid_mask` flags (`1` = finite source elevation, `0` = oblique swath or raster NoData) so no-data regions are omitted rather than triangulated as spikes.
  - Converts planetocentric coordinates to metric East-North-Up (ENU) coordinates anchored at dataset center on $R_{\text{eq}} = 3,396,190.0\text{ m}$ (`cos(origin_lat)` longitudinal scaling) and computes analytical Central-Difference surface normals on valid neighbors.
  - Exposes `/api/terrain/mesh/heightgrid` (`HeightGridResponse` with `grid_rows`, `grid_cols`, `elevations_m`, `valid_count`) feeding CesiumJS `HeightmapTerrainData` via `createMarscopeDemTerrainProvider()`, and `/api/terrain/ortho/{dataset_id}/texture` (`ortho`, `elevation`, `slope`, `roughness` PNGs aligned identically to tile geographic bounds).
- **Frontend Three.js Terrain Viewer (`frontend/src/components/LocalTerrain3DViewer.tsx`) & CesiumJS Sync (`frontend/src/components/MarsGlobeViewer.tsx`):**
  - Renders interactive OrbitControls WebGL DEM meshes with `1x True` default scale (`2x`/`3x` O(1) GPU group scaling), synced HiRISE ortho/derivative UVs (`flipY = true`), raycast hover telemetry (`lat`, `lon`, `elev`, `slope`, `TRI`), `Inspect / Set Start / +Waypt / Set Dest` surface picking, camera focus animations, science target pins, and 3D elevated route ribbons (`+0.8 m` surface offset).
  - `/explorer` unifies Three.js (`3D Terrain DEM`), `Split View`, and CesiumJS (`Mars Globe`) over shared Zustand store `useRoutingStore.ts` (`activeRoute`, `startPoint`, `destinationPoint`, `customWaypoints`, `staleRoute`).

## 7.2 Science-Aware Graph Routing Subsystem (`backend/app/routing/`)
- **`models.py` & `schemas.py`:** Defines `RoutingMode` (`conservative`, `balanced`, `science_priority`), `PathAlgorithm` (`astar`, `dijkstra`), `MODE_POLICIES`, and typed request/response contracts (`RouteComputeRequest`, `RouteComputeResponse`, `RouteCompareRequest`, `RouteCompareResponse`).
- **`graph.py`:** Builds `TerrainGrid` dynamically over requested corridor bounds padded cleanly to stay inside valid source coverage, enforces `effective_slope_limit_deg = min(user_max_slope_deg, mode_cap)` (Conservative scales slope limit by `0.80`), enforces strict **no diagonal corner-cutting** across impassable slopes or NoData cells, tracks distance to NoData cells (`nodata_prox`), and integrates local verified composition evidence bonuses within `150 m` (`Science-Priority` positive multiplier floor `>= 0.45` preserving A* admissibility).
- **`pathfinder.py` & `instructions.py`:** Runs deterministic binary-heap A* (with admissible 3D Euclidean lower bound) or Dijkstra, orders intermediate science/custom stops via exact DP/held-karp TSP (`N <= 10`) or nearest-neighbor refinement, runs obstacle-, NoData-, and **3D elevation-chord-tolerance** (`max_vert_dev_m = min(2.5, max(1.0, epsilon_m * 0.4))`) Ramer-Douglas-Peucker simplification (`simplify_leg_safely`), and emits True North `[0, 360)` and Equirectangular Grid North step-by-step instructions.
- **`service.py`:** Coordinates multi-stop planning, optional return-to-start loop, optional user-configured walking speed and EVA budget margins, computes mean/max slope and TRI across **all raw traversed cells** (`leg_res.cells`), invokes `calculate_gravitational_potential_energy` (`phys_res.calculated_value`) when astronaut mass is supplied, stores session routes for GeoJSON export (`/api/routing/{route_id}/geojson`), and feeds `/planner`, `/routes`, `/simulation`, and `/targets`.

## 7.3 NASA Imagery Catalogue Architecture (`backend/app/imagery/`, `/api/imagery/*`)
Product-level image records live alongside `DatasetCatalogService` in `datasets/catalog/imagery_products/catalog.json`, supporting structured PDS Imaging Atlas & ODE searches, size/host-bounded SHA-256 atomic product acquisition, and honest `panorama_eligibility_unverified` guards (no synthetic MSL Navcam panoramas claimed). Isolated Perseverance raw imagery proxy endpoints live under `/api/imagery/perseverance` (`perseverance_gallery.py`).

---

## 8. Prompt 12 Continuous Terrain Rendering, Exact Polylines & Live Tracking Subsystem

- **Seamless Cross-Tile Terrain Mesh & Overlays (`backend/app/terrain/mesh.py`, `frontend/src/components/LocalTerrain3DViewer.tsx`):**
  - `_sample_dem_grid` evaluates `np.linspace` exact tile boundary coordinates with clamped bilinear interpolation across outer 0.5-pixel rims and 1-ring padded central-difference normals (`normals`), eliminating inter-tile creases and corner elevation steps.
  - `render_region_texture_png` applies bilinear ortho subpixel sampling, half-texel UV alignment, and shared manifest `elevation_range_m`/`roughness_range_m` bounds (`vmin`/`vmax`). `LocalTerrain3DViewer` hot-swaps tile materials in-place without recreating geometry or resetting `OrbitControls` cameras, supports `Auto` camera-distance LOD + manual override and optional diagnostic tile borders, and renders computed routes strictly as exact 3D polyline segments (`THREE.BufferGeometry` from `activeRoute.vertices`, no `CatmullRomCurve3` smoothing).
- **Clean-Checkout Honesty & Opt-In Constraints:** `DatasetCatalogService` and `LayerCatalogService` demote missing local files strictly in memory on clean checkouts; routing starts with explicit `null` endpoints, opt-in reserve/return assumptions, debounced cancellable `AbortController` requests, collapsible Alternative Routes drawer, and `provenance` block linking every route to its source DEM.
- **Authenticated Live Telemetry vs Isolated Simulation (`backend/app/services/tracking_service.py`, `/api/tracking/*`, `useTrackingStore.ts`, `app/simulation/page.tsx`):** Strictly separates authenticated `IAU2000:49900` live tracking feeds (`X-Mars-Tracking-Token` / `Authorization: Bearer`, SSE `/stream`, monotonic sequence checks, stale detection, Mars-sphere cross-track error, confirmation-gated `/replan-preview`) from `Mission Simulation` (`SIMULATION — NOT LIVE MISSION TELEMETRY`).

---

## 9. Prompt 18 Scientific Integrity, Acquisition Resilience & End-to-End Provenance

- **Authoritative Acquisition & Validation Pipeline (`app/ingestion/acquisition.py`, `app/ingestion/pds_label.py`, `app/ingestion/catalog.py`, `app/geospatial/raster.py`):** Implements the 15-state `AcquisitionState` lifecycle, transient `503`/timeout retry + `206` Range resume, persistent `acquisition_ledger.jsonl` & `query_provenance.jsonl`, PDS3/PDS4 schema validation without fabricated defaults, and `RasterInspectionService` GeoTIFF CRS/units/scaling/band stats checks.
- **Mars Spatial Registration & Provenance DAG (`app/geospatial/crs.py`, `app/science/provenance_graph.py`):** Evaluates 7-state spatial registration across datasets/questions (`evaluate_spatial_registration`) and constructs inspectable node/edge `ProvenanceDependencyGraph` structures classifying every node under `ScientificDataClassification`.
- **17-Dimension Evidence Eligibility & Integrity Firewall (`app/science/investigation/eligibility.py`, `measurement_registry.py`, `service.py`):** Connects mission/instrument capability verification (`v2.0.0-p18`), inference firewall rules, 17-dimension eligibility checks, non-corroborating duplicate exclusion, contradiction preservation, target confidence/priority separation, and 5-state campaign feasibility + SHA-256 staleness tracking (`STALE_UPSTREAM_DEPENDENCY_CHANGED`).
- **Security & Fail-Closed API Guards (`app/core/security.py`, `app/api/*.py`):** Enforces `X-Mars-Operator-Token` authentication (`401`/`403` fail-closed when `MARSCOPE_OPERATOR_TOKEN` is configured), path identifier sanitization (`validate_identifier`, HTTP `422`), and strict explicit query/body validation across mobility and investigation endpoints.
- **Frontend Scientific Transparency (`frontend/src/app/{science-campaign,evidence,targets,terrain,explorer}/page.tsx`, `StatusBadge.tsx`, `useInvestigationStore.ts`):** Exposes Product Integrity drawers (`inspectProductDetail`), 17-dimension badges, competing hypotheses & contradiction panels, `feasibility_state` & `epistemic_classification` disclosures, JSON campaign dossier exports (`exportCampaignDossier`), session operator-token input, and removal of silent UI coordinate/priority fallbacks.


---

## Prompt 19: High-Fidelity Multi-Mission Spatial Intelligence Architecture

Prompt 19 upgrades MARSCOPE into an uncertainty-aware, multi-resolution, provenance-preserving planetary spatial intelligence system:

1. **Planetary Coordinate Intelligence (`backend/app/geospatial/models.py`, `backend/app/geospatial/crs.py`)**
   - Authoritative `MARS_CRS_REGISTRY` (`mars_crs_registry_v2.0`) covering `IAU2000:49900` (oblate ellipsoid $a=3,396,190\,\text{m}$, $b=3,376,200\,\text{m}$), `IAU2000:MARS_SPHERE` ($R=3,396,190\,\text{m}$), `MARS:IAU2015_49900`, `MARS:GALE_EQUIRECTANGULAR`, and `MARS:HIRISE_LOCAL_EQC`.
   - 8-state CRS validation (`CRS_VALIDATED`, `CRS_VALID_WITH_LIMITATIONS`, `CRS_UNVERIFIED`, `CRS_INCOMPATIBLE`, `CRS_UNSUPPORTED`, `COORDINATE_CONVENTION_UNVERIFIED`, `VERTICAL_DATUM_UNVERIFIED`, `TRANSFORMATION_FAILED`) with strict rejection of Earth (`EPSG:4326`), lunar (`IAU_2015:30100`), and screen-space systems.
   - Exact Planetocentric $\leftrightarrow$ Planetographic conversion ($\tan\phi_c = (b^2/a^2)\tan\phi_g$), East/West longitude domain normalization, 5-kind `VerticalDatumKind` compatibility engine, and auditable step-by-step coordinate transformations (`transform_mars_coordinates`).

2. **Multi-Mission Spatial Registration & Uncertainty Engine (`backend/app/geospatial/registration.py`)**
   - 12-step spatial registration evaluation (`evaluate_product_pair_registration`) producing 9 explicit states (`VALIDATED_REGISTRATION` through `REGISTRATION_FAILED`).
   - Evaluates 4 registration methods (`stereo_control_network_registration`, `authoritative_map_projection_alignment`, `control_point_registration` with breakdown-resistant median shift + OLS outlier rejection, and `feature_based_image_registration` with a strict modality guard refusing raw pixel correlation between elevation meters and optical reflectance DN).
   - Preserves correlated error structure (`independence_assumption_valid=False` for shared HiRISE stereo bundles) and never fabricates horizontal geolocation sigma from pixel spacing.

3. **Exact Spatial Footprints & 6-Category Coverage/Gap Engine (`backend/app/geospatial/footprints.py`, `backend/app/geospatial/coverage.py`)**
   - `extract_dataset_footprint` extracts true rotated valid-pixel swath hulls (`AUTHORITATIVE_RASTER_VALID_MASK_HULL`) from local HiRISE/MOLA rasters rather than treating oblique stereo swaths as full rectangular bounding boxes (`hirise_dteec_009149_1750` valid swath = `70.9%` of outer bbox; `hirise_dteec_040770_1755` = `73.9%`).
   - Computes areas using a centered Mars Lambert Azimuthal Equal-Area projection (`+proj=laea +R=3396190`) and indexes footprints in an `STRtree` (`SpatialFootprintIndex`) keyed by artifact checksums.
   - `compute_multi_category_spatial_coverage` evaluates 6 observation categories (`elevation`, `optical`, `spectral`, `thermal`, `rover`, `environmental`) across 5 coverage stages (`product_footprint`, `valid_pixel`, `calibrated_data`, `spatially_registered`, `scientifically_eligible`), suppresses exact areal percentages when only approximate bounding boxes or point observations exist, and outputs explicit `SpatialGapRegion` polygons (`never_implies_feature_absence=True`).

4. **Multi-Resolution Terrain Intelligence & Morphology Engine (`backend/app/terrain/spatial_terrain.py`, `backend/app/terrain/morphology.py`)**
   - Computes 13 windowed terrain derivatives (`elevation`, `slope`, `aspect`, `profile_curvature`, `planform_curvature`, `tri`, `local_relief`, `tpi`, `multiscale_roughness`, `elevation_variability`, `surface_normals`, `terrain_observability`, `dem_uncertainty`) with strict 3×3 NoData propagation and Nyquist $2.5\times$ pixel-spacing observability classification.
   - Multi-scale comparison (`compare_terrain_scales`) and 6-gate temporal terrain change evaluation (`evaluate_terrain_change`, returning `CHANGE_NOT_EVALUABLE` across incompatible resolutions, datums, or single-epoch pairs).
   - Resolution-gated morphological candidate detection (`GeologicalMorphologyService`) with a 2-pixel binary dilation NoData border guard that rejects artificial swath-edge cliffs (`rejected_nodata_border_candidates`), strict epistemic separation (`MorphologyEpistemicState`), and atomic `USER_PROVIDED` human review persistence (`datasets/processed/morphology_reviews.json`).

5. **Scale-Aware Rover Association & Scalable Spatial Delivery (`backend/app/science/rover_association.py`, `backend/app/geospatial/spatial_delivery.py`, `backend/app/api/spatial_intelligence.py`)**
   - 7-state rover-to-orbital spatial association (`evaluate_rover_orbital_association`) preserving location semantics (`rover_chassis`, `instrument_target_location`, `drill_or_scoop_sample_site`, `waypoint_station`) and scale disparity (`confirms_entire_orbital_pixel=False`).
   - 9-input SHA-256 deterministic cache key (`compute_spatial_cache_digest`), multi-resolution pyramid planner (`get_multi_resolution_pyramid_plan`, `upsampling_prevented=True`), and fail-closed `X-Mars-Operator-Token` cache invalidation.
   - Cross-engine integration across `eligibility.py`, `target_evaluation.py`, `routing/service.py`, and `evidence_intelligence/report.py`, plus the synchronized `/spatial-intelligence` workbench and `/explorer` 3D/Globe overlays.
