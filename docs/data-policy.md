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
