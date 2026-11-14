# MARSCOPE: Martian Surface Intelligence & Exploration System

[![NASA Space Apps Challenge](https://img.shields.io/badge/NASA%20Space%20Apps-Martian%20Map-blue.svg)](https://www.spaceappschallenge.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Open Science](https://img.shields.io/badge/Data-NASA%20Open%20Data%20(CC0)-orange.svg)](DATA_SOURCES.md)
[![TypeScript](https://img.shields.io/badge/Frontend-Next.js%2014%20%7C%20TypeScript-black.svg)](frontend/)
[![Python](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.11+-blue.svg)](backend/)

> **Martian Surface Intelligence & Exploration System** — An integrated, open-science planetary intelligence platform fusing open NASA datasets, physics-based calculations, and constrained route optimization to plan scientifically valuable and operationally informed Marswalks for future explorers.

---

## 1. Challenge Alignment & Vision

- **Competition:** NASA Space Apps Challenge
- **Challenge:** *Interplanetary Survival Guide: Martian Map*
- **Primary Study Region:** Gale Crater — Mount Sharp / Aeolis Mons (Curiosity Rover Boxwork Exploration Zone)
- **Scientific Objective:** Investigate paleohydrological and diagenetic evidence of ancient groundwater circulation and mineralized fracture networks (boxwork ridges).

Future human surface operations on Mars ("Marswalks") will be constrained by hypobaric atmospheric pressures, extreme cryogenic temperature swings, abrasive regolith, unshielded ionizing radiation, rugged geomorphology, and communication latencies to Earth of up to 24 minutes. 

**MARSCOPE** provides an intelligent surface exploration engine. Unlike conventional terrestrial map tools, MARSCOPE introduces **science-aware, human-aware route optimization**: balancing the acquisition of high-value geological targets (e.g., boxwork ridges, sulfate beds, rover-grounded chemical assays) against terrain slope resistance, micro-roughness, metabolic work expenditure, and non-negotiable return-to-base consumable reserves.

---

## 2. Key Capabilities

1. **Multimodal Planetary Data Fusion:** Co-registers sub-meter MRO HiRISE imagery, regional CTX mosaics, MOLA global topography, CRISM hyperspectral mineralogy, THEMIS thermal inertia, and MSL Curiosity in-situ observations.
2. **Topographic & Hazard Modeling:** High-resolution slope, aspect, and Terrain Ruggedness Index (TRI) processing from Digital Elevation Models.
3. **Dedicated Physics Engine:** Deterministic calculation of Martian gravitational forces, potential energy, atmospheric density profiles, uphill climbing resistance, and cumulative radiation doses.
4. **Constrained Path Optimization:** Multi-objective graph pathfinding (A*, Dijkstra) enforcing strict astronaut return-to-base margins ($1.5\times$ return reserve) and critical slope thresholds ($< 25^\circ$).
5. **Interactive 3D Planetary Workspace:** CesiumJS 3D Mars globe with MapLibre GL 2D fallback, elevation profile cross-sections, and step-by-step EVA simulation scrubbers.
6. **Full Provenance & Open-Science Transparency:** Every layer, waypoint, and observation traces directly to an official NASA Planetary Data System (PDS) Product ID and verified open license.

---

## 3. Technology Stack

### Frontend
- **Framework:** Next.js (App Router, React 18+, Server & Client Components)
- **Language:** TypeScript (Strict Type Checking)
- **Styling:** Tailwind CSS (Aerospace Dark Design Token System)
- **3D Geospatial Engine:** CesiumJS (Configured with IAU2000:49900 Mars Reference Ellipsoid)
- **2D Geospatial Engine:** MapLibre GL JS
- **State Management:** Zustand
- **Telemetry & Charts:** Recharts
- **Icons:** Lucide React

### Backend
- **Framework:** Python FastAPI
- **Language:** Python 3.11+
- **Numerical & Scientific:** NumPy, SciPy
- **Geospatial & Planetary GIS:** GDAL, Rasterio, GeoPandas, Shapely, pyproj
- **Graph Optimization:** NetworkX
- **Validation:** Pydantic v2

### Storage & Data Standards
- **Raster Formats:** Cloud-Optimized GeoTIFFs (COG), MOLA Areoid vertical datum
- **Vector Formats:** OGC GeoJSON (IAU2000 / Mars Equidistant Projection)
- **Open Data Services:** NASA Mars Trek WMTS, NASA PDS Geosciences & Atmospheres Nodes

---

## 4. Architecture Overview

```text
Marscope/
├── README.md               # Project documentation and quickstart
├── plan.md                 # Complete Master Project Specification & Architecture
├── DATA_SOURCES.md         # Authoritative dataset inventory & provenance ledger
├── LICENSE                 # Apache License 2.0
├── .env.example            # Environment configuration template
├── docs/                   # Detailed architectural, scientific, and physical specifications
│   ├── architecture.md
│   ├── data-policy.md
│   ├── scientific-methodology.md
│   ├── physics-models.md
│   ├── api-contracts.md
│   ├── validation-plan.md
│   └── demo-script.md
├── datasets/               # Planetary dataset catalogs and manifests
│   ├── catalog/
│   ├── manifests/
│   ├── raw/                # Raw NASA products (git-ignored)
│   └── processed/          # Derived COGs (git-ignored)
├── frontend/               # Next.js 14 / TypeScript / CesiumJS Web Application
│   └── src/
│       ├── app/            # App Router (9 specialized mission pages)
│       ├── components/     # UI components (3D Globe, Navigation, Panels)
│       ├── stores/         # Zustand state stores
│       ├── types/          # TypeScript domain definitions
│       └── styles/         # Tailwind CSS & design tokens
└── backend/                # FastAPI / Python Planetary Intelligence Engine
    └── app/
        ├── api/            # API route controllers
        ├── physics/        # Deterministic physical models & registry
        ├── geospatial/     # Coordinate transformations & raster processors
        ├── terrain/        # Slope, roughness, and traversability calculators
        ├── routing/        # Constrained pathfinding algorithms
        ├── science/        # Target registry & rover observation parser
        ├── schemas/        # Pydantic data schemas
        └── services/       # Core business logic
```

---

## 5. Quickstart & Local Setup

### Prerequisites
- **Node.js:** v18.0.0 or higher (v20+ recommended)
- **npm:** v9.0.0 or higher
- **Python:** v3.11 or higher
- **Git**

### Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/sanstack256/Marscope.git
   cd Marscope
   ```

2. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   cp .env.example .env.local
   npm run build
   ```

3. **Backend Setup:**
   ```bash
   cd ../backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

### Running the Application

1. **Start Backend (FastAPI):**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   *Health Check:* `http://127.0.0.1:8000/api/health`

2. **Start Frontend (Next.js):**
   ```bash
   cd frontend
   npm run dev
   ```
   *Application Workspace:* `http://localhost:3000`

---

## 6. Open-Data & Scientific Integrity Commitment

MARSCOPE strictly enforces an anti-fabrication standard:
- **No Synthesized NASA Data:** We never fabricate spectral bands, manufacture coordinates, or invent rover discoveries.
- **Explicit Provenance:** All targets, orbital imagery, and rover observations link to verified NASA PDS product identifiers.
- **Unencumbered Licenses:** All integrated datasets adhere to NASA Public Domain or CC0 terms. No proprietary or paid commercial mapping dependencies are used.

---

## 7. Current Project Status & Reproducible Build

- **Phase:** Prompt 8 mobility backend remains present; Prompt 9 explorer work is partial. No four-mode terrain/panorama explorer is claimed complete.
- **Pre-Implementation Scientific Corrections (Part A):**
  1. **Zero-Measurement Semantics (`app/science/composition/value_semantics.py`):** Numerical zero values (`0.0`) across APXS, ChemCam MOC, and CheMin RDR5 are never automatically classified as below-detection-limit (`BELOW_DETECTION_LIMIT`). They are preserved with `value_semantics = "reported_numerical_zero_unresolved_semantics"` and `source_interpretation_note` unless the source PDS3/PDS4 label explicitly declares a detection-limit constant (`source_defined_below_detection_limit`) or missing constant (`source_defined_missing`).
  2. **No Silent DEM Footprint Expansion (`app/terrain/processor.py`, `app/geospatial/alignment.py`):** `DEMProcessingService` (`PROCESSING_VERSION = "2.0.0"`, `FOOTPRINT_POLICY = "no_expansion_v1"`) never enlarges a requested study region when it contains fewer than `3x3` whole source pixels on a coarse DEM; it raises `InsufficientDEMCoverageError` with a structured `InsufficientCoverageReport` (`requested_bounds_modified = False`).
  3. **No Default 25° Safety-Threshold Semantics (`app/schemas/terrain.py`, `app/terrain/summary.py`, `app/physics/registry/parameters.py`):** Removed hardcoded `critical_slope_threshold_deg = 25.0` safety-limit defaults; replaced with optional user-configured `PlanningSlopeThreshold` (`parameter_class = "user_configured_planning_assumption"`, `is_validated_safety_limit = False`).
  4. **Reader Lease Protection Across Concurrent Index Rebuilds (`app/science/composition/index.py`):** Readers acquire per-process leases (`acquire_generation_lease()`), preventing `publish_generation()` pruning from deleting an in-flight generation directory while a query or manifest verification is executing.
- **Human Mobility Intelligence Engine (`app/mobility/`, `/api/mobility/*`):**
  - **DEM Inventory & Resolution Suitability (`resolution.py`):** Explicitly distinguishes `regional_elevation_analysis`, `local_slope_analysis`, `regional_roughness_analysis`, and `small_scale_obstacle_detection` so coarse orbital DEMs (MOLA MEGDR 4 ppd, ~14.8 km native / ~6.6 km gridded pixel spacing) are never presented as local human-scale slope or obstacle maps.
  - **Windowed Terrain Features & Spatially Explicit Elevation Profiles (`terrain_features.py`):** Computes elevation (`meters`), Horn (1981) `3x3` slope (`degrees`), compass aspect (`[0, 360)` clockwise from North; flat cells undefined), metric TRI roughness (`meters`), and 2-point or polyline elevation gain/loss transects with contiguous `nodata_gap_segments`.
  - **5-State Spatial Coverage Intelligence (`coverage.py`):** Distinguishes `outside_source_footprint`, `inside_footprint_nodata`, `valid_source_data`, `insufficient_resolution_for_analysis`, and `derivative_unavailable_invalid_neighborhood`.
  - **Configurable `MobilityScenario`, Transparent `TraversalModel` & `TraversalCostSurface` (`mobility_scenario.py`, `traversal_model.py`, `cost_surface.py`):** Strict separation between scenario-independent physical measurements ($W = m \cdot g_{\text{Mars}}$, $\Delta PE = m \cdot g_{\text{Mars}} \cdot \Delta h$, $F_{\parallel} = m \cdot g_{\text{Mars}} \sin\theta$) and scenario-dependent traversal estimates ($t = d / v_{\text{eff}}$), with zero default walking speeds, zero physiological/oxygen/fatigue fabrication, zero safe/unsafe claims, and `null` cost on unknown/no-data terrain.
- **Reproducible Offline Index Rebuild:**
  ```bash
  PYTHONPATH=backend python3 backend/scripts/rebuild_composition_index.py [--strict] [--acquire]
  ```
- **Automated Verification:** Verified backend unit/integration test suite (`pytest`, 71 tests) and clean Next.js TypeScript/ESLint production build. Route optimization and pathfinding remain intentionally outside this milestone's scope.

### Explorer status and limitations (2026-11-14)

- Cesium starts at a global Mars view, supports its 3D/2D/Columbus scene modes, and uses the existing dynamically discovered layer catalog. Clicking the globe still selects a destination.
- Idle scene rendering is disabled through Cesium request-render mode. Camera telemetry is sampled at most every 250 ms while moving and refreshed on move end. The displayed scale is measured from two globe intersections 40 canvas pixels apart; it is unavailable when those rays do not intersect the globe.
- Candidate, destination, and manually configured position markers are diffed by stable IDs in a named `CustomDataSource`; unrelated entities are no longer cleared on every state change.
- No verified local Navcam panorama products or DEM terrain-mesh service are present in this workspace. The current explorer does **not** provide a real panorama viewer, panorama discovery API, synchronized four-mode workflow, or DEM-derived ground 3D. The globe still uses an ellipsoid terrain provider. These are remaining milestone requirements.
- Resolution suitability thresholds now live in `backend/app/mobility/policies/resolution_v1.json` (`1.0.0`). Their provenance and classification are returned with each assessment. They are engineering screens or unvalidated heuristics and do not establish detection capability, source accuracy, or route safety.
- No performance benchmark or NASA panorama acquisition was performed; the interaction claims above describe code changes, not measured FPS improvements.

## NASA imagery catalogue

The product-level imagery catalogue at `/api/imagery` queries the live NASA PDS Imaging Atlas and records only returned archive products. Use `/imagery` in the app or `GET /api/imagery/search?mission=msl&limit=25&offset=0`. Atlas results use bounded pagination and support archive-indexed mission, instrument, dataset, product ID, product type, and sol filters. ODE search adds documented spatial bounding-box filtering. MSL Navcam RDR/RDR Mosaic holdings are not assumed: the tested ODE `MSL + NAVCAM + RDR` combination returned an ODE “Invalid IIPT” response, and the live Atlas queries so far have not established an individual Navcam panorama product. No panorama is eligible without label, projection, coverage, and geographic evidence.

To acquire an indexed original product, use its catalogue action or `POST /api/imagery/products/{product_id}/acquire`; status is available at `/api/imagery/products/{product_id}/acquisition`. Raw images are stored under `datasets/raw/imagery/`, labels under `datasets/raw/imagery_labels/`, and records under `datasets/catalog/imagery_products/catalog.json`. Downloads are host constrained, bounded to 2 GB, streamed to a temporary file, checked against archive MD5 when supplied, hashed with SHA-256, and never overwrite an existing file. Rights remain unverified until product-specific terms are established.

Offline tests: `cd backend && pytest -q`. NASA connectivity test: `NASA_INTEGRATION=1 pytest -m nasa_integration -q -s` (requires network; unsupported ODE combinations are reported as skipped). The integration test does not download image products.

**Live query record (2026-11-14):** PDS Imaging Atlas returned three MSL `.IMG` records for `mission=msl`, `instrument=msam`, `file_extension=img`; the archive reports `10,000+` total matches (`relation=gte`). These are actual indexed records, not Navcam-only. The exact Atlas MSL/Navcam filter returned zero. The three sample products and associated labels returned HTTP 404. ODE also returned one real MRO HiRISE RDR product and one MRO CTX EDR product with archive footprints. One HiRISE PDS3 label was retrieved and parsed, and its 307,736,024-byte original JP2 was acquired; SHA-256 was computed, but no archive checksum was provided. Across the five persisted records, two have ODE center/footprint associations and none are panorama eligible. See [DATA_SOURCES.md](DATA_SOURCES.md) for query scope and evidence.
