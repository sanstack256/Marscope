# MARSCOPE Scientific Methodology & Investigation Plan

## 1. Primary Investigation Target: Mount Sharp Boxwork Structures (Gale Crater)

### 1.1 Geological Context
Gale Crater ($5.4^\circ\text{ S}, 137.8^\circ\text{ E}$, diameter ~154 km) hosts **Aeolis Mons** (Mount Sharp), a central sedimentary mound rising ~5 km above the crater floor. Mount Sharp exposes a stratified sequence of ancient Martian sedimentary rocks spanning the late Noachian through Hesperian periods, recording the global transition from a warmer, wetter early Mars to the hyperarid environment of today.

Within the upper sulfate-bearing unit, orbital HiRISE imagery and in-situ observations by the **Curiosity rover (MSL)** revealed extensive networks of **boxwork structures**—prominent polygonal, intersecting ridges standing in positive relief above the eroded bedrock.

### 1.2 Scientific Significance of Boxwork Formations
- **Ancient Paleohydrology:** Boxwork ridges represent fracture-controlled mineral precipitation. Subsurface hydrothermal or groundwater fluids circulated through joints in the host rock, depositing hard, erosion-resistant minerals (cemented sulfates and silica).
- **Diagenesis & Biosignature Preservation:** Fracture fills capture late-stage diagenetic fluid chemistry. In Earth analogues, sub-surface mineralizing fractures often serve as protective microenvironments preserving chemical and morphological signatures of ancient microbial life.
- **Stratigraphic Relationship:** Understanding the temporal relationship between boxwork fracturing and the surrounding clay-to-sulfate transition clarifies the duration of groundwater activity into the Hesperian era.

---

## 2. Conceptual Investigation Waypoints

To ground the EVA traversal planning in rigorous field science without inventing arbitrary waypoints:

| Waypoint Classification | Geomorphological Description | Field Science Objective | Sampling Strategy |
| :--- | :--- | :--- | :--- |
| **Boxwork Ridge Crests** | Resistant polygonal ridges standing 1–5 m above surrounding terrain | Structural strike/dip measurement, fracture fill petrology | Contact APXS, close-up MAHLI imaging, core drilling |
| **Inter-Ridge Hollows** | Depressed deflation hollows accumulating loose aeolian sand | Granulometry, soil mechanics, active aeolian transport assessment | Soil scoop, CheMin mineralogy, DAN active neutron sounding |
| **Geological Transitions** | Contact boundary between clay-rich strata and layered sulfates | Environmental transition dating, geochemical continuity | High-resolution vertical stratigraphic column documentation |
| **Habitat Anchor / Base** | Broad, flat deflation pavement with slope $< 3^\circ$ and low boulder density | Safe EVA ingress/egress, high-gain comms link, solar array deployment | Engineering stability, baseline environmental monitoring |

---

## 3. Evidence Requirements & Provenance Tracking

Every science target in the MARSCOPE Target Explorer must provide:
1. **Orbital Evidence:** Direct HiRISE visual morphology and CRISM spectral absorptions (e.g., $1.9\,\mu\text{m}$ band indicating structural $\text{H}_2\text{O}$ in hydrated sulfates).
2. **In-Situ Ground Truth:** Associated Curiosity rover Sol number, ChemCam LIBS targets, or CheMin quantitative mineral percentages (where traversed).
3. **Contradicting / Limiting Factors:** Observation limitations (e.g., dust cover obscuring bedrock, steep approach angles preventing safe astronaut contact).

---

## 4. Controlled Geochemical Discovery, Stoichiometry & Ranking Methodology (Prompt 4)

### 4.1 Strict Ontology Separation
MARSCOPE maintains a canonical vocabulary (`backend/app/science/composition/species.py`) distinguishing:
- **Chemical Elements** (e.g., `Fe`, `S`, `Si`, `Ca`, `Mg`, `Al`, `K`, `Na`, `Ti`, `Mn`, `Cr`, `P`, `Cl`, `Ni`, `Zn`, `Br`)
- **Calibrated Oxides** (`FeO`, `FeOT`, `Fe2O3`, `SO3`, `SiO2`, `CaO`, `MgO`, `Al2O3`, `K2O`, `Na2O`, `TiO2`, `MnO`, `Cr2O3`, `P2O5`)
- **Crystalline Minerals** (`hematite`, `magnetite`, `gypsum`, `bassanite`, `anhydrite`, `jarosite`, `andesine`, `forsterite`, `augite`, `pigeonite`, `montmorillonite`, `quartz`, etc.)
- **Mineral Groups** (`plagioclase`, `olivine`, `pyroxene`, `smectite`, `sulfate`, `carbonate`, `iron_oxide`)

Ambiguous queries such as `"silica"` (`SiO2` vs crystalline `quartz`) or `"iron oxide"` (`FeO`/`Fe2O3` vs `hematite`/`magnetite`) are explicitly flagged rather than silently disambiguated. Searching for an element (`Fe`, `S`) retrieves direct element assays plus stoichiometric oxide conversions (`wt%` scaled by IUPAC atomic mass fractions, e.g., `FeO * 0.77731 -> Fe`, `SO3 * 0.40049 -> S`). Element-bearing host minerals are excluded by default unless `include_element_bearing_minerals=true` is requested, and are assigned a lower evidence tier.

### 4.2 Explainable Non-Probabilistic Candidate Ranking
Candidate locations are ranked strictly by transparent physical and spatial metrics (`backend/app/science/composition/ranking.py`) rather than fabricated probability percentages:
- **Evidence Tier:** `1.0` (direct mineral/element), `0.90` (calibrated oxide/stoichiometric conversion), `0.55` (element-bearing host mineral)
- **Abundance & Quality:** Normalized abundance scaled within query range and penalized for missing error bars or elevated RMSEP
- **Instrument Corroboration:** Higher weight when independent instruments (e.g., `APXS` + `ChemCam_LIBS`) corroborate a location
- **Mars IAU2000 Geodesic Proximity:** Ellipsoidal distance & forward azimuth from active astronaut position computed with `pyproj.Geod` (`a=3396190 m, b=3376200 m`)

### 4.3 Prompt 5 & 6 Heuristic Priority Governance, Uncertainty Compatibility & Stoichiometry

- **Explicitly Heuristic Ranking & Uncertainty Compatibility (`RankingConfiguration` v3 `3.0.0`):** Candidate scores carry `ranking_config_id` (`heuristic_exploration_priority_v3`), `ranking_config_version` (`3.0.0`), `is_heuristic_only = true`, and `ranking_methodology_label = "HEURISTIC_EXPLORATION_PRIORITY_ONLY"`. Quantitative `quality_component` is computed only when records in the query cohort share a compatible statistical uncertainty family (`evaluate_uncertainty_compatibility` in `backend/app/science/composition/uncertainty.py`). When uncertainty is unreported, lacks a quantitative sigma/scale (`chemin_estimated_error_unspecified_sigma`, qualitative APXS `Quality` flags), or mixes incompatible uncertainty types across instruments (`apxs_analytical_precision` vs `chemcam_pls_rmsep` vs `chemin_rietveld_2sigma`), `quality_component` remains `null`, `uncertainty_compatibility_status` reports the incompatibility, and `quality_exclusion_reason` documents the omission with weights renormalized solely over remaining dimensions.
- **Stoichiometric Conversion Lineage (`IUPAC_CIAAW_2021`):** Element queries fulfilled via oxide stoichiometry mark `is_stoichiometric_conversion = true`, `source_oxide_species`, `stoichiometric_factor`, `stoichiometric_weights_version`, and append conversion provenance to `uncertainty_metadata.conversion_history`. `FeO` (APXS) vs `FeOT` (ChemCam LIBS) assumptions and mixed-uncertainty cohort notices are surfaced in `scientific_warnings`.
- **Spatial Semantic Integrity:** `ROVER_STATION_LOCATION` (RMC-joined rover stations for ChemCam LIBS / CheMin) is separated visually and in metadata from `INSTRUMENT_TARGET_LOCATION` (APXS target coordinates).
