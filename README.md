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

- **Phase:** Prompt 5 — Scientific Integrity Gate, PDS Schema Correctness & Reproducible Discovery Complete.
- **Geospatial & Terrain Engine:** Verified GeoTIFF/MOLA/PDS3 ingestion pipeline, IAU2000 Mars ellipsoid calculations, slope/aspect/TRI derivation, and deterministic EVA physics engine.
- **Scientific Discovery & Integrity Engine:** Dynamic PDS3 (`.LBL` / `.FMT`) & PDS4 (`.XML`) schema-driven parsers, spatial semantic separation (`instrument_target_location` vs `rover_station_location` vs `unlocated`), 12-stage validation pipeline with deterministic SHA-256 `evidence_id`s, SQLite R*Tree spatial index, and automated integrity drift detection (`IntegrityStatus`).
- **Reproducible Offline Index Rebuild:**
  ```bash
  PYTHONPATH=backend python3 backend/scripts/rebuild_composition_index.py
  ```
  Writes atomic `datasets/index/composition_index.sqlite` and `datasets/index/reproducibility_manifest.json` from local NASA PDS files (pass `--acquire` to fetch missing source files from official NASA PDS / JPL URLs).
- **Automated Verification:** Verified backend unit/integration test suite (`pytest`) and clean Next.js TypeScript/ESLint production build. Route optimization remains scoped out until the next milestone.
