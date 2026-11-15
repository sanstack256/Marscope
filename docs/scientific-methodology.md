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

---

## 3. Prompt 7 Scientific Integrity Closure (`heuristic_exploration_priority_v4` `4.0.0`)

1. **CheMin Independent Schema Field & Error Unit Resolution:** CheMin `PERCENT` (`WEIGHT_PERCENT`) and `ERROR` are resolved independently from `.LBL` and `CHEMIN_MIN.FMT`. Semantic non-dimensional units such as `ESTIMATED_ERROR` remain `"ESTIMATED_ERROR"` (`is_physical_unit = false`) and are never coerced into `"wt%"`; missing schema units remain `None` with explicit `limitations`; incompatible physical units (e.g., `KELVIN`) fail validation.
2. **Withheld Numerical Quality Scoring & Separate Relative Uncertainty:** Because no cross-instrument calibrated measurement quality model exists, `quality_component` is strictly `null` (`heuristic_exploration_priority_v4` v`4.0.0` normalizes weights solely across `evidence_tier`, `abundance`, `corroboration`, and `spatial_proximity`). Quantitative relative uncertainty (`uncertainty_value / normalized_value`) is computed separately into `RelativeUncertaintySummary` ONLY when physical units match identically, measurement > `0`, and statistical semantics permit it.
3. **Measurement-Category-Aware Search Filtering & Sorting:** Search classifies every hit by `MeasurementCategory` (`direct_elemental_concentration`, `oxide_derived_elemental_concentration`, `direct_oxide_concentration`, `mineral_weight_percent`, `mineral_group_membership_evidence`), scopes elemental numeric bounds (`min_value`/`max_value`) exclusively away from host-mineral `wt%`, computes abundance normalization strictly per `(measurement_category, normalized_unit)`, and rejects flat `sort_by="abundance"` across mixed categories/units (`422`), offering partitioned `sort_by="category_abundance"` instead.

---

## 9. Prompt 8 Zero-Measurement Semantics, Footprint Integrity & Human Mobility Methodology

1. **Source-Faithful Zero-Measurement Classification (`value_semantics.py`):** A reported numerical zero (`0.0`) in APXS, ChemCam MOC, or CheMin RDR5 tables is never automatically converted into `BELOW_DETECTION_LIMIT`. It is preserved as `value_semantics = "reported_numerical_zero_unresolved_semantics"` (`EvidenceStatus.MEASURED` / `UNLOCATED`) with an explicit `source_interpretation_note` stating that the source label does not establish whether `0.0` denotes below-detection-limit, trace, or unmeasured. `BELOW_DETECTION_LIMIT` (`source_defined_below_detection_limit`) and `SOURCE_DEFINED_MISSING_VALUE` (`source_defined_missing`) are assigned only when explicitly declared in the PDS3 `.LBL`/`.FMT` or PDS4 `.XML` special constants.
2. **No Silent DEM Footprint Expansion (`no_expansion_v1`):** Because Horn's (1981) `3x3` slope/aspect kernel and Riley et al.'s (1999) `3x3` metric TRI require at least `3x3` whole source pixels, any study region intersecting fewer than `3x3` pixels on a coarse DEM returns a structured `InsufficientCoverageReport` (`requested_bounds_modified = False`) without ever enlarging the requested bounding box.
3. **Human Mobility Intelligence & Separation of Physical vs Scenario Quantities (`app/mobility/`):**
   - **Physical Measurements (Scenario-Independent):** Elevation $z$ ($\text{m}$), Horn `3x3` slope $\theta$ ($\text{deg}$), compass aspect $\psi \in [0, 360^\circ)$ clockwise from North (flat cells undefined), metric TRI roughness ($\text{m}$), geodesic distance $d$ ($\text{m}$ on $R = 3,396,190\text{ m}$), cumulative positive gain $\Delta z_+$, cumulative negative loss $\Delta z_-$, Mars surface weight $W = m_{\text{total}} g_{\text{Mars}}$ ($g_{\text{Mars}} = 3.72076\text{ m/s}^2$), gravitational potential energy change $\Delta PE = m_{\text{total}} g_{\text{Mars}} \Delta z$ ($\text{J}$), and slope-parallel gravity component $F_{\parallel} = m_{\text{total}} g_{\text{Mars}} \sin\theta$ ($\text{N}$).
   - **Scenario-Dependent Traversal Estimates:** Baseline time $t_0 = d / v_0$ and adjusted time $t_{\text{adj}} = d / (v_0 \cdot f_{\text{slope}} \cdot f_{\text{rough}})$ are computed **only** when the user explicitly provides `reference_walking_speed_m_per_s` ($v_0 > 0$). Optional slope and roughness adjustment rules execute strictly inside their declared `[min_valid, max_valid]` domain and refuse extrapolation (`outside_model_valid_domain`). Unknown/no-data terrain always yields `null` traversal cost (`unknown_terrain`), never `0.0`, and MARSCOPE never labels terrain as `"safe"` or `"unsafe"`.
# Resolution suitability policy (v1.0.0)

`backend/app/mobility/policies/resolution_v1.json` records threshold values, units, version, provenance, rationale, and valid domain. Values are classified as engineering recommendations or unvalidated heuristics. A `supported` result means only that effective pixel spacing passes the named MARSCOPE screen. It does not guarantee feature detection, slope accuracy, source accuracy, or safe traversal. Source accuracy, terrain-feature scale, observation geometry, and product-specific processing are not incorporated by the current policy and remain unavailable. The special 100 m/px regional TRI branch and the 500 m/px local-slope regional-approximation boundary are explicitly policy parameters, not hidden constants.

## Imagery geometry and panorama claims

The imagery catalogue preserves coordinate convention and CRS separately from coordinates. ODE states its search bounding boxes use planetocentric latitude and positive-east longitude 0–360; this convention is not applied to other sources without evidence. Earth WGS84 is not used for Mars image associations.

Panorama eligibility defaults to `panorama_eligibility_unverified`. A product is not considered cylindrical/360-degree eligible unless image content, dimensions, projection, horizontal and vertical angular coverage, orientation when available, camera/instrument metadata, and observation/geographic association are established from the product and label. Dataset or product names alone are insufficient. No indexed record has yet been classified as panorama eligible.

---

## 10. Prompt 11 Science-Aware Route Optimization & Slope Preservation Methodology

1. **Three Explicit Planning Modes (`backend/app/routing/models.py`):**
   - `Conservative Terrain-Avoidance` (`effective_slope_limit_factor = 0.80`, `slope_weight = 4.5`, `uphill_weight = 3.2`, `roughness_weight = 1.25`, `nodata_proximity_weight = 1.50`): Tightens user slope limit by 20% and avoids steep/rough/edge terrain.
   - `Balanced Traverse` (`factor = 1.0`, `slope_weight = 1.8`, `uphill_weight = 1.6`, `roughness_weight = 0.55`): Balances path length against slope effort and terrain ruggedness.
   - `Science-Priority Corridor` (`factor = 1.0`, `science_corridor_bonus = 0.50`, `min_cost_multiplier = 0.45`): Rewards corridors passing within `150 m` of verified APXS, ChemCam LIBS, CheMin XRD composition evidence or selected `ScienceTarget` sites without overriding slope or NoData constraints.
2. **Obstacle & Relief Integrity Along Simplification (`pathfinder.py`, `service.py`):**
   - Orthogonal passability guards prohibit diagonal corner-cutting adjacent to NoData or excessive-slope cells (`strict_no_corner_cutting`).
   - `simplify_leg_safely()` enforces Bresenham/supercover line-of-sight passability checks plus a 3D vertical chord deviation bound ($\le \min(2.5, \max(1.0, 0.4\epsilon))$ m) so steep ridges or troughs are preserved as intermediate vertices.
   - Summary `mean_slope_deg`, `max_slope_deg`, and `mean_roughness_tri_m` aggregate over **all raw traversed DEM grid cells** (`leg_res.cells`) rather than simplified polyline vertices alone.

---

## 11. Prompt 12 Exact Trajectory Geometry, Opt-In Constraints & Telemetry Separation

1. **Exact Polyline Geometry (`LocalTerrain3DViewer.tsx`):** Route trajectories render strictly as exact linear 3D polyline segments connecting graph-verified `activeRoute.vertices` coordinates rather than Catmull-Rom or spline interpolations that could curve into unverified high-slope or NoData cells.
2. **Opt-In Constraint & Metric Grouping:** Mission reserve/return margins (`safety_reserve_fraction = 0.0`, `return_to_start = false`) and walking speed / astronaut mass inputs are strictly opt-in rather than silent assumptions. Route comparison reports four demarcated metric groups (`Terrain Metrics`, `Evidence-Backed Constraints`, `Uncertainty`, `Planning Assumptions`) and tags the lowest numeric-cost candidate strictly as `"Lowest calculated terrain cost"` (`safety_certification_enabled = false`).
3. **Live Telemetry vs Deterministic Simulation (`tracking_service.py`, `simulation/page.tsx`):** Authenticated live mission telemetry (`IAU2000:49900`, monotonic sequences, Mars-sphere cross-track deviation, confirmation-gated replan previews) is strictly separated from `Mission Simulation` playback (`SIMULATION — NOT LIVE MISSION TELEMETRY`).

---

## 12. Prompt 18 Scientific Semantics, 17-Dimension Eligibility & Support Classification

1. **Instrument Capability Registry Governance (`v2.0.0-p18`, `app/science/investigation/measurement_registry.py`):**
   - Every instrument declares `registry_entry_id`, `registry_version`, explicit `verification_status` (`VERIFIED`, `PARTIALLY_VERIFIED`, `UNVERIFIED`), `source_references`, `unresolved_fields`, `typical_spatial_scale_m` (`Optional[float]`, never substituted for missing product resolution), `allowed_inferences`, and `prohibited_inferences`.
   - Active Gale Crater verified instruments include `HIRISE`, `HIRISE_DTM`, `CTX`, `MOLA`, `CHEMCAM_LIBS`, `CHEMIN_XRD`, `APXS`, and `REMS`. `CRISM` is registered as `VERIFIED` for spectral modality but carries no locally validated cube over the active Gale study area. `THEMIS`, `ODYSSEY_GRS_NS`, `SAM_EGA_GCMS`, `MASTCAM`, `MAHLI`, `PIXL_SHERLOC`, and `SUPERCAM_MASTCAMZ` are governed strictly as `UNVERIFIED` or mission-isolated (`mission_isolated_from_gale = true`).
2. **Scientific Inference Firewall (`check_inference_validity`):**
   - Prohibits optical/reflectance (`HIRISE`, `CTX`, `MASTCAM`) mineral phase or chemistry identification; prohibits elemental oxide chemistry (`APXS`, `CHEMCAM_LIBS`) from claiming crystalline mineral phase identification without XRD/IR; prohibits thermal inertia (`THEMIS`) from compositional claims; blocks claims converting missing observations into geological absence; blocks coarse-to-local and local-to-regional scale extrapolations; and isolates Jezero Crater (`Mars 2020`) instruments from Gale claims.
3. **Hypothesis Evaluation, Duplicate Non-Corroboration & Contradiction Retention (`eligibility.py`):**
   - Each `ScienceQuestionDefinition` documents primary `hypothesis`, `competing_hypotheses`, `alternative_explanations`, `contradicting_evidence_criteria`, `unresolved_assumptions`, and `ThresholdRuleClassification` (`scientific_requirement`, `instrument_limitation`, `product_selection_preference`, `engineering_policy`, `USER_ASSUMED`).
   - `evaluate_dataset_eligibility` evaluates 17 explicit dimensions (`1_source_authenticity` .. `17_duplication_or_correlation`) producing `EvidenceEligibilityState` (`ELIGIBLE`, `ELIGIBLE_WITH_LIMITATIONS`, `CONTEXT_ONLY`, `NOT_RELEVANT`, `MISSION_INCOMPATIBLE`, `PRODUCT_UNVERIFIED`, `PRODUCT_CORRUPTED`, `DUPLICATE_OR_CORRELATED`, `UNAVAILABLE`, `REJECTED`) and maps requirements to `CanonicalRequirementState` (`SATISFIED`, `PARTIALLY_SATISFIED`, `UNSATISFIED`, `CONFLICTED`, `BLOCKED_BY_DATA_GAP`, `UNAVAILABLE`, `NOT_EVALUATED`).
   - `synthesize_question_evidence` produces `EvidenceSynthesisSummary` with explicit `statistical_confidence_state = "UNAVAILABLE_NO_VALIDATED_STATISTICAL_MODEL"` (`statistical_confidence_score = None`), excludes `DUPLICATE_OR_CORRELATED` hits from `independent_evidence_count`, and retains all contradicting and inconclusive observations.
4. **Separated Target & Campaign Epistemic Semantics (`target.py`, `campaign.py`):**
   - `ScienceTarget` and `CandidateTargetEvaluation` deprecate `scientific_value` (always `None` unless explicitly supplied as legacy compatibility; never copied from `exploration_priority_score` / `heuristic_priority_score`), reporting separated `scientific_confidence_state` (`UNAVAILABLE_NO_VALIDATED_STATISTICAL_MODEL`) and `eligibility_decision`.
   - `ScienceCampaignPlan` separates five feasibility states (`FEASIBLE_UNDER_CONFIGURED_MODEL`, `FEASIBLE_WITH_DATA_GAPS`, `INCOMPLETE_CONSTRAINT_EVALUATION`, `INFEASIBLE_UNDER_CONFIGURED_MODEL`, `NOT_EVALUATED`), always carries `operational_safety_certified = False`, keeps observation data volume `estimated_data_volume_mb = None` (`UNAVAILABLE_NO_TELEMETRY_BITRATE_CONFIGURED`), and attaches a full `ProvenanceDependencyGraph` (`DIRECTLY_MEASURED`, `ARCHIVE_DERIVED`, `MARSCOPE_DERIVED`, `USER_ASSUMED`, `UNAVAILABLE`).

### Prompt 18 Support-Level Classification Matrix

| Capability / Domain | Support Level | Scientific Basis & Active Boundary |
| :--- | :--- | :--- |
| Gale HiRISE 1.01 m/px DTMs & Orthos (`DTEEC_009149_1750`, `DTEEC_040770_1755`) | **VERIFIED** | Acquired local PDS3 `.IMG`/`.JP2`/`.LBL`, SHA-256 verified, `IAU2000:49900`, processed COGs |
| Gale MSL Traverse Waypoints, APXS PDS4, ChemCam MOC, CheMin XRD (Rocknest + live RDR5) | **VERIFIED** | Schema-parsed (`XML`/`LBL`/`FMT`), RMC-joined, SHA-256 indexed, live PDS acquisition verified |
| MOLA MEGDR (`MEGT00N090HB`, `MEGT90N000CB`) | **PARTIALLY_VERIFIED** | Coarse 463 m / 14.8 km spacing; NASA integer `.LBL` omits `SCALING_FACTOR` (`scaling_factor=None` preserved honestly) |
| Mars Trek WMTS Basemaps (`curiosity_hirise_mosaic`, `Gale_CTX_BlockAdj_dd`) | **PARTIALLY_VERIFIED (CONTEXT ONLY)** | Visual reference layers excluded from quantitative DEM slope routing & mineral evidence |
| MRO CRISM Orbital Spectral Mineralogy | **UNAVAILABLE LOCALLY** | Registered modality; zero local validated cube in workspace -> `BLOCKED_BY_DATA_GAP` |
| MSL Navcam Panoramas, ODYSSEY GRS, THEMIS Thermal, SAM, Mastcam/MAHLI | **UNVERIFIED / NOT ACQUIRED** | Zero acquired local product manifests; withheld cleanly from mineral/panorama claims |
| Mars 2020 Perseverance (`PIXL_SHERLOC`, `SUPERCAM_MASTCAMZ`) | **EXCLUDED (MISSION_INCOMPATIBLE)** | Jezero Crater observations strictly quarantined from Gale Crater |
| Earth CRS (`EPSG:4326` / WGS84), NASA Worldview | **EXCLUDED (`excluded_earth_only`)** | Rejected in CRS registration, geospatial validation, and `/api/sources/audit` |
