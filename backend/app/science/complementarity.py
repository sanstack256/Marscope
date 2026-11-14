"""
MARSCOPE Multi-Dataset Physical & Scientific Complementarity Registry
Defines explicit scope, resolution applicability, supported claims, prohibited inferences,
and cross-validation rules across orbital, geologic, and surface datasets.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

COMPLEMENTARITY_REGISTRY_ID = "MARSCOPE-COMPLEMENTARITY"
COMPLEMENTARITY_REGISTRY_VERSION = "complementarity_v1.0"


class DatasetRoleDescriptor(BaseModel):
    """Explicit scientific contract for one planetary dataset family."""

    dataset_id_pattern: str
    title: str
    mission_and_instrument: str
    native_scale_description: str
    primary_measurement_domain: str
    supports: List[str] = Field(default_factory=list)
    does_not_support: List[str] = Field(default_factory=list)
    complementary_role: str
    isolation_warning: Optional[str] = None


class CrossValidationRule(BaseModel):
    """Explicit rule governing how two dataset families constrain or caution against each other."""

    primary_source: str
    secondary_source: str
    relationship: str
    scientific_caution: str


class ComplementarityAssessmentReport(BaseModel):
    """Complete Data Complementarity Registry evaluation for a corridor or mission dossier."""

    registry_id: str = COMPLEMENTARITY_REGISTRY_ID
    registry_version: str = COMPLEMENTARITY_REGISTRY_VERSION
    active_dataset_ids: List[str] = Field(default_factory=list)
    dataset_roles: List[DatasetRoleDescriptor] = Field(default_factory=list)
    cross_validation_rules: List[CrossValidationRule] = Field(default_factory=list)
    coverage_caveats: List[str] = Field(default_factory=list)


_DATASET_ROLES: List[DatasetRoleDescriptor] = [
    DatasetRoleDescriptor(
        dataset_id_pattern="mola_megt00n090hb",
        title="MOLA MEGDR Gridded Topography (~463 m/px)",
        mission_and_instrument="Mars Global Surveyor (MGS) / MOLA",
        native_scale_description="128 ppd (~463 m/pixel at equator); 16-bit integer elevation (1 m step); equatorial inter-track gaps up to ~12 km.",
        primary_measurement_domain="Regional macro-scale planetary elevation baseline & datum reference (MOLA Areoid)",
        supports=[
            "Regional Gale Crater basin & Aeolis Mons context beyond local HiRISE footprints",
            "Regional elevation framing and dataset datum continuity verification",
            "Fallback macro-scale path visualization ONLY when labeled coarse regional context",
        ],
        does_not_support=[
            "Meter-scale local slope screening for rover or human Marswalk safety",
            "Ridge, boxwork polygon, boulder, or gully hazard detection",
            "Per-pixel inter-track elevation accuracy certainty between sparse ground tracks",
        ],
        complementary_role="Provides global Areoid vertical datum and basin-wide context surrounding high-resolution HiRISE swaths.",
    ),
    DatasetRoleDescriptor(
        dataset_id_pattern="hirise_dteec_*",
        title="HiRISE Stereo DTM (~1.01 m/px)",
        mission_and_instrument="Mars Reconnaissance Orbiter (MRO) / HiRISE (SOCET SET)",
        native_scale_description="~1.01 m/pixel float32 elevations; nominal catalog precision ~0.25 m; no per-pixel sigma raster in PDS3 IMG.",
        primary_measurement_domain="Local meter-scale topography, Horn 3x3 slopes, Riley ~5 m TRI ruggedness, and traversability graph",
        supports=[
            "Engineering traversability slope & climb estimation (>= 2-3 m baseline)",
            "Multi-meter Relief / TRI ruggedness characterization across 5 m windows",
            "Independent outbound & return surface pathfinding across Gale Crater / Mount Sharp boxwork terrain",
        ],
        does_not_support=[
            "Sub-meter boulder or cobble hazard detection (< 0.5-1.0 m)",
            "Empirical per-pixel vertical RMSE bounds without stereo quality correlation maps",
            "Sub-surface bearing strength, loose sand sinkage, or cliff overhang certification",
        ],
        complementary_role="Primary geometric foundation for MARSCOPE 3D terrain mesh, Horn slopes, TRI roughness, and directional A*/Dijkstra routing.",
    ),
    DatasetRoleDescriptor(
        dataset_id_pattern="hirise_*_ortho",
        title="HiRISE Orthorectified Image (~0.25 m/px)",
        mission_and_instrument="MRO / HiRISE (Co-projected RDR)",
        native_scale_description="~0.25 m/pixel grayscale intensity; co-projected on matching HiRISE stereo DTM geometry.",
        primary_measurement_domain="Sub-meter albedo, shadow/outcrop morphology, and optical verification inside stereo swath",
        supports=[
            "Visual context for ridge crests, dune ripplings, fractures, and tonal contacts",
            "Qualitative optical cross-check of >= 0.75-1.0 m candidate boulders (unvalidated optical detections)",
        ],
        does_not_support=[
            "Autonomous certified obstacle-free surface claims when zero anomalies are tagged",
            "Direct terrain slope or elevation extraction without stereo DTM elevation",
            "Sub-0.3 m boot-scale hazard verification",
        ],
        complementary_role="Adds high-frequency texture & outcrop context atop matching HiRISE DTMs; optical candidates stay excluded from route rewards unless externally validated.",
    ),
    DatasetRoleDescriptor(
        dataset_id_pattern="usgs_sim3292_mars_geology",
        title="USGS SIM 3292 Global Geologic Map (1:20,000,000)",
        mission_and_instrument="USGS Planetary Geologic Mapping Program",
        native_scale_description="Continental / global polygon compilation at 1:20M cartographic scale.",
        primary_measurement_domain="Broad regional geologic unit context and regional stratigraphic epoch framing",
        supports=[
            "Macro-scale Gale Crater / Aeolis Quadrangle stratigraphic framing",
            "Background geologic context annotation in mission dossiers",
        ],
        does_not_support=[
            "Local meter-scale outcrop contact placement or traverse boundary assignment",
            "Slope, regolith bearing capacity, or traversability inference",
        ],
        complementary_role="Provides broad geologic unit framing; explicitly quarantined from high-resolution route traversability gating.",
    ),
    DatasetRoleDescriptor(
        dataset_id_pattern="curiosity_msl_*",
        title="MSL Curiosity Surface Traverse & Geochemical Records",
        mission_and_instrument="Mars Science Laboratory / Curiosity (APXS, ChemCam, Mastcam, REMS, SPICE)",
        native_scale_description="Localized waypoints, drive segments, and point target analyses along Curiosity's traversed path.",
        primary_measurement_domain="In-situ surface mineral/geochemical observations, meteorological bounds, and localized ground-truth anchor points",
        supports=[
            "Ground-truth compositional & boxwork science priority anchoring near traversed sites",
            "Verified REMS ambient pressure, ground/air temperature, and seasonal environmental context",
        ],
        does_not_support=[
            "Spatial extrapolation of soil strength or mineralogy into unvisited adjacent corridors",
            "Continuous regional obstacle clearance across broad Gale Crater swaths",
        ],
        complementary_role="Grounds high-priority scientific targets cleanly when spatially within verified proximity bounds; gaps outside traverse remain marked absent.",
    ),
    DatasetRoleDescriptor(
        dataset_id_pattern="perseverance_jezero_*",
        title="Mars 2020 Perseverance Jezero Raw Image Stream",
        mission_and_instrument="Mars 2020 / Perseverance (Jezero Crater)",
        native_scale_description="Mission-isolated engineering/science image gallery at ~18.4 N, 77.5 E (~3,700 km from Gale).",
        primary_measurement_domain="Separate Jezero Crater mission reference gallery ONLY",
        supports=[
            "Independent Jezero Crater image browsing in isolated Jezero UI module",
        ],
        does_not_support=[
            "Any Gale Crater / Mount Sharp hazard, geological, atmospheric, or science correlation",
        ],
        complementary_role="Maintained strictly isolated from Gale Crater / Mount Sharp operational planning and scoring.",
        isolation_warning="STRICT MISSION ISOLATION ENFORCED: Perseverance Jezero observations never enter Gale Crater assessments.",
    ),
]

_CROSS_RULES: List[CrossValidationRule] = [
    CrossValidationRule(
        primary_source="hirise_dteec_* (1 m DTM)",
        secondary_source="mola_megt00n090hb (~463 m MOLA)",
        relationship="Vertical Datum & Basin Continuity Check",
        scientific_caution="Differences at pixel scale reflect MOLA 463 m smoothing and inter-track gaps rather than HiRISE local inaccuracy; never mix MOLA into local slope gradients.",
    ),
    CrossValidationRule(
        primary_source="hirise_dteec_* (1 m DTM)",
        secondary_source="hirise_*_ortho (0.25 m Ortho)",
        relationship="Co-registered Morphological Cross-Check",
        scientific_caution="Co-projected ortho clarifies linear fractures and bedforms below ~3 m DTM correlation width, yet local X/Y tiepoint error remains unquantified on steep scarps.",
    ),
    CrossValidationRule(
        primary_source="hirise_dteec_* (1 m DTM)",
        secondary_source="curiosity_msl_* (In-Situ)",
        relationship="Localized Ground-Truth vs Orbital Swath Extrapolation Guard",
        scientific_caution="MSL rover measurements strictly anchor local waypoints; absence of MSL records elsewhere is an unvisited observation gap, not benign terrain.",
    ),
    CrossValidationRule(
        primary_source="hirise_dteec_* (1 m DTM)",
        secondary_source="usgs_sim3292_mars_geology (1:20M)",
        relationship="Scale-Mismatch Firewall",
        scientific_caution="1:20M geologic polygons carry ~tens-of-km cartographic generalization; never use SIM 3292 contacts for traverse hazard boundaries.",
    ),
]


def evaluate_data_complementarity(
    *,
    active_dataset_ids: List[str],
    route_distance_m: Optional[float] = None,
) -> ComplementarityAssessmentReport:
    """Evaluate active datasets against the Data Complementarity Registry."""
    caveats: List[str] = [
        "HiRISE 1 m DTMs govern meter-scale geometry; HiRISE 0.25 m orthophotos provide visual morphology where footprints intersect.",
        "USGS SIM 3292 (1:20M) and MOLA MEGDR (~463 m) provide regional framing only and cannot support meter-scale slope or obstacle inference.",
        "Curiosity MSL in-situ measurements apply strictly at localized rover coordinates and cannot be spatially extrapolated.",
    ]
    if "perseverance_jezero" in " ".join(active_dataset_ids).lower():
        caveats.append("Perseverance Jezero data detected in context list and strictly quarantined from Gale Crater routing logic.")

    return ComplementarityAssessmentReport(
        active_dataset_ids=list(dict.fromkeys(active_dataset_ids)),
        dataset_roles=list(_DATASET_ROLES),
        cross_validation_rules=list(_CROSS_RULES),
        coverage_caveats=caveats,
    )
