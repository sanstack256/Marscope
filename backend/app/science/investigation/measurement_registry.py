"""
MARSCOPE Multi-Instrument Planetary Measurement Capability Registry
Prompt 17: Covers 16 orbital and surface instruments across Gale Crater (Curiosity)
and explicitly isolated Mars 2020 Jezero Crater (Perseverance) archives, with strict
allowed vs prohibited inference boundaries.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.science.investigation.schemas import (
    InferenceValidationResponse,
    InstrumentCapabilityRecord,
    InstrumentPlatformKind,
    MeasurementClass,
)


_INSTRUMENTS: Dict[str, InstrumentCapabilityRecord] = {
    "CRISM": InstrumentCapabilityRecord(
        instrument_id="CRISM",
        instrument_name="Compact Reconnaissance Imaging Spectrometer for Mars",
        mission_host="MRO",
        study_region_scope="Global / Gale Crater (where targeted FRT/HRS cubes are acquired & validated)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MINERALOGY_SPECTRAL,
        typical_spatial_scale_m=18.0,
        measured_observables=[
            "VNIR/SWIR reflectance spectra (0.36-3.92 um)",
            "Hydrated phyllosilicate & Fe/Mg-smectite absorption bands (1.9, 2.3 um)",
            "Polyhydrated & monohydrated sulfate spectral parameters",
            "Hematite / carbonate spectral indices",
        ],
        allowed_inferences=[
            "Orbital km-to-18m candidate clay, sulfate, and iron-oxide mineral occurrence",
            "Regional stratigraphic mineral mapping across Mount Sharp units",
        ],
        prohibited_inferences=[
            "Sub-meter boxwork wall thickness or fracture network connectivity",
            "Quantitative oxide weight-percent stoichiometry (SiO2/FeO wt%)",
            "Claiming local rover-target confirmation where cubes are absent or noisy",
        ],
    ),
    "HIRISE": InstrumentCapabilityRecord(
        instrument_id="HIRISE",
        instrument_name="High Resolution Imaging Science Experiment (Ortho/RDR Optical)",
        mission_host="MRO",
        study_region_scope="Gale Crater / Mount Sharp (where RDR/ortho footprints intersect)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        typical_spatial_scale_m=0.3,
        measured_observables=[
            "Panchromatic RED / IRB calibrated surface I/F radiance (~0.25-0.30 m/px)",
            "Boxwork polygonal ridge planform geometry & fracture spacing",
            "Bedrock bedding attitude, eolian bedforms & boulder fields (>~0.75 m)",
        ],
        allowed_inferences=[
            "Meter-scale geomorphic structure, fracture patterns, and optical hazard cues",
            "Identification of unverified optical morphology candidates requiring confirmation",
        ],
        prohibited_inferences=[
            "Inferring mineral species, gypsum/clay/carbonate presence, or salinity from tone or false color",
            "Inferring CheMin XRD crystallinity or hydrated volatile abundance visually",
            "Guaranteed absence of sub-pixel (<0.75 m) cobbles or soft dust pockets",
        ],
    ),
    "HIRISE_DTM": InstrumentCapabilityRecord(
        instrument_id="HIRISE_DTM",
        instrument_name="HiRISE Stereo Digital Terrain Model (PDS DTMs)",
        mission_host="MRO",
        study_region_scope="Gale Crater / Mount Sharp (stereo footprint)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
        typical_spatial_scale_m=1.0,
        measured_observables=[
            "Surface elevation relative to IAU2000 Mars datum (meters)",
            "Meter-scale Horn slope gradient (deg) and Terrain Ruggedness Index (m)",
            "Positive-relief ridge height across boxwork troughs",
        ],
        allowed_inferences=[
            "Multi-meter topographic relief, slope constraints, and line-of-sight geometry",
            "Quantitative slope sensitivity and vertical quantization lower bounds when PDS metadata present",
        ],
        prohibited_inferences=[
            "Compositional or mineralogical identity",
            "Centimeter-scale tire/boot traction or dust-depth bearing strength",
        ],
    ),
    "CTX": InstrumentCapabilityRecord(
        instrument_id="CTX",
        instrument_name="Context Camera (MRO Panchromatic)",
        mission_host="MRO",
        study_region_scope="Regional Gale Crater / Aeolis Quadrangle",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        typical_spatial_scale_m=6.0,
        measured_observables=[
            "6 m/px grayscale broadband albedo & mesoscale landform continuity",
            "Regional ridge networks, fans, and channel belts",
        ],
        allowed_inferences=[
            "Multi-kilometer stratigraphic & geomorphic context linking HiRISE DTMs",
        ],
        prohibited_inferences=[
            "Meter-scale rover/EVA obstacle clearance or slope estimation",
            "Mineral or chemical composition",
        ],
    ),
    "THEMIS": InstrumentCapabilityRecord(
        instrument_id="THEMIS",
        instrument_name="Thermal Emission Imaging System (IR & VIS)",
        mission_host="2001 Mars Odyssey",
        study_region_scope="Global / Gale Crater",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.THERMAL_INERTIA_COMPOSITION,
        typical_spatial_scale_m=100.0,
        measured_observables=[
            "Thermal IR brightness temperature & derived qualitative surface thermal inertia contrast",
            "Broad silicate polymerization emissivity index (100 m/px)",
        ],
        allowed_inferences=[
            "100 m scale thermal induration vs unconsolidated dust mantling contrast",
            "Regional felsic vs basaltic emissivity shift indicators",
        ],
        prohibited_inferences=[
            "Meter-scale bedrock strength or EVA footing clearance",
            "Trace hydrated mineral phase identification (clays/gypsum)",
        ],
    ),
    "MOLA": InstrumentCapabilityRecord(
        instrument_id="MOLA",
        instrument_name="Mars Orbiter Laser Altimeter (MEGDR Gridded)",
        mission_host="Mars Global Surveyor (MGS)",
        study_region_scope="Regional / Global (~463 m/px)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
        typical_spatial_scale_m=463.0,
        measured_observables=[
            "Gridded planetary elevation (IAU2000 sphere datum, ~463 m/px)",
            "Basin-to-mountain elevation profile & global tiepoint framing",
        ],
        allowed_inferences=[
            "Macro-basin elevation framing and inter-quadrangle vertical datum tie",
        ],
        prohibited_inferences=[
            "Local EVA traverse slope feasibility (463 m pixel smooths cliffs & scarps)",
            "Meter-scale boxwork ridge relief",
        ],
    ),
    "ODYSSEY_GRS_NS": InstrumentCapabilityRecord(
        instrument_id="ODYSSEY_GRS_NS",
        instrument_name="Mars Odyssey Gamma-Ray & Neutron Spectrometer",
        mission_host="2001 Mars Odyssey",
        study_region_scope="Planetary coarse regional (~300,000 m footprint)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.HYDRATED_NEUTRON_SUBSURFACE,
        typical_spatial_scale_m=300000.0,
        measured_observables=[
            "Sub-meter bulk H2O-equivalent hydrogen, K, Th, Fe, Si over ~300 km footprint",
        ],
        allowed_inferences=[
            "Hemispheric-to-regional crustal hydration & bulk elemental background",
        ],
        prohibited_inferences=[
            "Specific Gale outcrop or Mount Sharp boxwork enrichment",
        ],
    ),
    "CHEMCAM_LIBS": InstrumentCapabilityRecord(
        instrument_id="CHEMCAM_LIBS",
        instrument_name="Chemistry & Camera (LIBS & RMI)",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity traverse)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        typical_spatial_scale_m=0.0005,
        measured_observables=[
            "Sub-mm laser-induced plasma atomic emission lines -> SiO2, TiO2, Al2O3, FeOT, MgO, CaO, Na2O, K2O (wt%)",
            "Relative Hydrogen (H), Sulfur, Chlorine, Lithium, Strontium qualitative emission indicators",
        ],
        allowed_inferences=[
            "Exact sub-mm major-oxide elemental chemistry at targeted rock/vein spot",
            "Elemental proxies consistent with Ca-sulfate (Ca+S+H) or silica enrichment (needs mineral confirmation)",
        ],
        prohibited_inferences=[
            "Unambiguous mineral phase identification (elemental oxide wt% does NOT uniquely prove crystalline clay/jarosite/gypsum vs amorphous phase without CheMin XRD or NIR spectroscopy)",
            "Extrapolation across unexplored terrains >50 m away",
        ],
    ),
    "CHEMIN_XRD": InstrumentCapabilityRecord(
        instrument_id="CHEMIN_XRD",
        instrument_name="Chemistry & Mineralogy X-Ray Diffractometer",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity drill spots)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MINERALOGY_XRD,
        typical_spatial_scale_m=0.016,
        measured_observables=[
            "Definitive crystal d-spacing XRD patterns -> phyllosilicates (smectite), Ca-sulfates (gypsum, bassanite, anhydrite), hematite, magnetite, jarosite, plagioclase, pyroxene + X-ray amorphous fraction",
        ],
        allowed_inferences=[
            "Authoritative definitive mineral phase identification & crystalline modal abundances at drilled target",
        ],
        prohibited_inferences=[
            "Direct organic carbon characterization",
            "Continuity of exact mineral percentages outside sampled drill stratigraphic layer",
        ],
    ),
    "APXS": InstrumentCapabilityRecord(
        instrument_id="APXS",
        instrument_name="Alpha Particle X-Ray Spectrometer",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity contact targets)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        typical_spatial_scale_m=0.017,
        measured_observables=[
            "Bulk ~1.7 cm contact elemental oxides (SiO2, Al2O3, FeO, MgO, CaO, Na2O, K2O, SO3, Cl, MnO, Ni, Zn, Br wt%)",
        ],
        allowed_inferences=[
            "Quantitative bulk rock geochemistry, SO3/Cl salt enrichment, Mn/Fe redox ratios at contact target",
        ],
        prohibited_inferences=[
            "Claiming crystalline mineral structure from oxide ratios alone",
            "Organic molecular composition or isotopic fractionation",
        ],
    ),
    "SAM_EGA_GCMS": InstrumentCapabilityRecord(
        instrument_id="SAM_EGA_GCMS",
        instrument_name="Sample Analysis at Mars (EGA / QMS / GCMS / TLS)",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity drill spots)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.VOLATILE_ORGANIC_ISOTOPE,
        typical_spatial_scale_m=0.016,
        measured_observables=[
            "Thermally evolved H2O, SO2, CO2, O2, NO, HCl release temperature curves",
            "D/H, 13C/12C, 18O/16O isotopes and derivatized/pyrolyzed organic fragments",
        ],
        allowed_inferences=[
            "Volatile host decomposition temperatures (oxychlorines, sulfates, clays), biosignature/organic screening",
        ],
        prohibited_inferences=[
            "Silicate rock hardness or traverse surface cohesion",
        ],
    ),
    "MASTCAM": InstrumentCapabilityRecord(
        instrument_id="MASTCAM",
        instrument_name="Mast Camera (34mm / 100mm Multispectral Stereo)",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        typical_spatial_scale_m=0.002,
        measured_observables=[
            "True-color stereo mosaics & 11 narrow-band VNIR filters (445-1013 nm)",
            "Boxwork fracture wall height, cross-cutting diagenetic vein geometry, 860 nm ferric oxide absorption signature",
        ],
        allowed_inferences=[
            "Outcrop-scale stratigraphy, fracture intersections, ferric iron spectral slope clues",
        ],
        prohibited_inferences=[
            "Mineral identification of non-ferric white veins (e.g., claiming CaSO4 vs MgSO4 without ChemCam/APXS/CheMin)",
        ],
    ),
    "MAHLI": InstrumentCapabilityRecord(
        instrument_id="MAHLI",
        instrument_name="Mars Hand Lens Imager",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp (arm contact imaging)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        typical_spatial_scale_m=0.0001,
        measured_observables=[
            "~14-100 um/px close-up optical imaging of grain sorting, cement textures, nodules, veins",
        ],
        allowed_inferences=[
            "Micro-textural cementation, sedimentary grain size, diagenetic crystal habit clues",
        ],
        prohibited_inferences=[
            "Elemental or crystalline composition from crystal morphology alone",
        ],
    ),
    "REMS": InstrumentCapabilityRecord(
        instrument_id="REMS",
        instrument_name="Rover Environmental Monitoring Station",
        mission_host="MSL Curiosity",
        study_region_scope="Gale Crater / Mount Sharp",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.METEOROLOGY_ENVIRONMENT,
        typical_spatial_scale_m=1.0,
        measured_observables=[
            "Diurnal surface pressure (Pa), air & ground brightness temperature (K), UV irradiance, local wind",
        ],
        allowed_inferences=[
            "Measured Gale Crater diurnal thermal/barometric cycles during Curiosity operations",
        ],
        prohibited_inferences=[
            "Subsurface soil mineralogy or real-time future crewed storm forecasting",
        ],
    ),
    "PIXL_SHERLOC": InstrumentCapabilityRecord(
        instrument_id="PIXL_SHERLOC",
        instrument_name="PIXL Micro-XRF & SHERLOC Deep-UV Raman/Fluorescence",
        mission_host="Mars 2020 Perseverance",
        study_region_scope="Jezero Crater ONLY (~18.4 N, 77.5 E — ~3,700 km from Gale)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MINERALOGY_SPECTRAL,
        typical_spatial_scale_m=0.0001,
        measured_observables=[
            "Jezero Crater micro-XRF elemental maps & deep-UV Raman aromatic/sulfate/carbonate bands",
        ],
        allowed_inferences=[
            "Jezero Crater mission science analysis ONLY",
        ],
        prohibited_inferences=[
            "ANY extrapolation, correlation, target generation, or campaign evidence for Gale Crater / Mount Sharp",
        ],
        mission_isolated_from_gale=True,
        mission_isolation_note=(
            "STRICT MISSION ISOLATION: Perseverance / Jezero instruments operate ~3,700 km from Gale Crater "
            "and NEVER enter Gale Crater science campaigns, target evidence, or route bonuses."
        ),
    ),
    "SUPERCAM_MASTCAMZ": InstrumentCapabilityRecord(
        instrument_id="SUPERCAM_MASTCAMZ",
        instrument_name="SuperCam (LIBS/Raman/VISIR) & Mastcam-Z",
        mission_host="Mars 2020 Perseverance",
        study_region_scope="Jezero Crater ONLY (~18.4 N, 77.5 E — ~3,700 km from Gale)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        typical_spatial_scale_m=0.001,
        measured_observables=[
            "Jezero Crater remote LIBS/Raman/VISIR spectroscopy & stereo zoom imaging",
        ],
        allowed_inferences=[
            "Jezero Crater outcrop characterization ONLY",
        ],
        prohibited_inferences=[
            "ANY cross-pollination into Gale Crater / Mount Sharp science plans or mineral evidence",
        ],
        mission_isolated_from_gale=True,
        mission_isolation_note=(
            "STRICT MISSION ISOLATION: Mars 2020 Perseverance Jezero observations remain strictly quarantined from Gale Crater."
        ),
    ),
}


def list_instruments(*, include_mission_isolated: bool = True) -> List[InstrumentCapabilityRecord]:
    items = list(_INSTRUMENTS.values())
    if not include_mission_isolated:
        items = [i for i in items if not i.mission_isolated_from_gale]
    return items


def get_instrument(instrument_id: str) -> Optional[InstrumentCapabilityRecord]:
    return _INSTRUMENTS.get(instrument_id.strip().upper())


def check_inference_validity(instrument_id: str, claimed_inference: str) -> InferenceValidationResponse:
    """Enforce scientific boundary rules: prevent visual mineral claims or elemental-to-XRD overclaiming."""
    inst = get_instrument(instrument_id)
    if inst is None:
        return InferenceValidationResponse(
            instrument_id=instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="unknown_instrument_rejected",
            rationale=f"Instrument '{instrument_id}' is not registered in the MARSCOPE Planetary Capability Registry.",
        )

    claim_l = claimed_inference.lower()
    if inst.mission_isolated_from_gale and "gale" in claim_l:
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="mission_isolation_violation",
            rationale=inst.mission_isolation_note or "Jezero Crater instrument cannot support Gale Crater claims.",
            prohibited_inferences=inst.prohibited_inferences,
        )

    # Guard visual morphology -> mineralogy hallucination
    if inst.instrument_id in {"HIRISE", "CTX", "MAHLI", "MASTCAM"} and any(
        k in claim_l for k in ("gypsum", "phyllosilicate", "smectite", "jarosite", "xrd", "mineral confirm", "oxide wt%")
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_visual_to_mineral_inference",
            rationale=(
                f"{inst.instrument_id} measures optical morphology/reflectance only ({inst.typical_spatial_scale_m} m/px) "
                "and CANNOT establish mineral identity or elemental chemistry without spectral/XRD/LIBS confirmation."
            ),
            prohibited_inferences=inst.prohibited_inferences,
        )

    # Guard elemental -> definitive XRD crystal mineral overclaim
    if inst.instrument_id in {"CHEMCAM_LIBS", "APXS"} and any(
        k in claim_l for k in ("definitive xrd", "crystal structure", "confirmed smectite mineral", "confirmed gypsum phase")
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_elemental_to_mineral_phase_claim",
            rationale=(
                f"{inst.instrument_id} provides elemental abundance only; elemental Ca+S or Fe+Si indicates a geochemical proxy "
                "and requires CheMin XRD or SWIR vibrational spectroscopy for definitive mineral-phase confirmation."
            ),
            prohibited_inferences=inst.prohibited_inferences,
        )

    # Guard coarse DEM -> meter-scale slope feasibility
    if inst.instrument_id in {"MOLA", "ODYSSEY_GRS_NS", "THEMIS"} and any(
        k in claim_l for k in ("local slope", "rover hazard", "boxwork thickness", "traversable meter")
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_resolution_extrapolation",
            rationale=(
                f"{inst.instrument_id} operates at {inst.typical_spatial_scale_m:.1f} m spatial scale and "
                "cannot support meter-scale hazard or outcrop structure claims."
            ),
            prohibited_inferences=inst.prohibited_inferences,
        )

    return InferenceValidationResponse(
        instrument_id=inst.instrument_id,
        claimed_inference=claimed_inference,
        allowed=True,
        classification="within_instrument_capability_scope",
        rationale=f"Inference is consistent with {inst.instrument_name} ({inst.measurement_class.value}) observables at ~{inst.typical_spatial_scale_m} m scale.",
        prohibited_inferences=inst.prohibited_inferences,
    )
