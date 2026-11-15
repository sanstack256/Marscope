"""
MARSCOPE Traceable Multi-Instrument Planetary Measurement Capability Registry
Prompt 18 (v2.0.0-p18): Versioned, source-referenced instrument capability catalog covering
16 orbital and surface instruments across Gale Crater (Curiosity) and mission-isolated
Jezero Crater (Perseverance) archives, with strict product-precedence rules and a
comprehensive scientific inference firewall.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.science.investigation.schemas import (
    InferenceValidationResponse,
    InstrumentCapabilityRecord,
    InstrumentPlatformKind,
    MeasurementClass,
    RegistryVerificationStatus,
)

REGISTRY_VERSION = "2.0.0-p18"

_UNVERIFIED_NOTE = (
    "Instrument capability spec documented from mission/archive overview only; no locally "
    "acquired & validated product label/SIS verified in workspace. Product-level metadata "
    "takes precedence when a real product is acquired."
)

_INSTRUMENTS: Dict[str, InstrumentCapabilityRecord] = {
    "CRISM": InstrumentCapabilityRecord(
        registry_entry_id="inst_mro_crism_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MRO CRISM",
                "url": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
                "archive_id": "MRO-M-CRISM-3-RDR-TARGETED-V1.0 / MTRDR",
            }
        ],
        unresolved_fields=[
            "No local CRISM TRDR/MTRDR cube or PDS label verified in workspace",
            "Atmospheric/volcano-scan correction version and exact pixel footprint require product header",
        ],
        instrument_id="CRISM",
        instrument_name="Compact Reconnaissance Imaging Spectrometer for Mars",
        mission_host="Mars Reconnaissance Orbiter (MRO)",
        study_region_scope="Targeted orbital strips (~18-36 m/px nominal FRT/HRS); no local cube verified",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MINERALOGY_SPECTRAL,
        measurement_modality="hyperspectral_vnir_swir_reflectance",
        physical_quantity_measured="Irradiance / calibrated I/F spectral reflectance (0.362-3.920 um, units: dimensionless I/F)",
        measurement_method="Pushbroom grating imaging spectroscopy (S and L detectors)",
        supported_measurement_types=["VNIR/SWIR reflectance spectroscopy", "spectral summary band indices"],
        applicable_product_types=["CRISM_TRDR", "CRISM_MTRDR"],
        calibration_requirements=[
            "Radiometric I/F calibration verified in PDS label",
            "Volcano-scan atmospheric gas removal & empirical destriping (MTRDR / CAT)",
        ],
        processing_requirements=["Map projection with IAU2000 Mars DDR/GLT spatial lookup table"],
        spatial_applicability="Pixel scale strictly read from product DDR (~18 m/px FRT, ~36 m/px HRL, ~100-200 m MSP); orbital mixtures average sub-pixel outcrops",
        temporal_applicability="MRO primary/extended science phases (2006+; subject to L-detector cooler epochs)",
        validity_conditions=[
            "Requires verified atmospheric correction and noise-spike filtering in MTRDR/TRDR product metadata",
            "Non-detection does NOT rule out sub-pixel (<18 m) or dust-mantled outcrops",
        ],
        typical_spatial_scale_m=None,
        measured_observables=[
            "VNIR/SWIR reflectance spectra (0.36-3.92 um)",
            "Hydrated phyllosilicate & Fe/Mg-smectite absorption bands (1.9, 2.3 um)",
            "Polyhydrated & monohydrated sulfate spectral parameters",
            "Hematite / carbonate spectral indices",
        ],
        allowed_inferences=[
            "Orbital spectral absorption indicators consistent with candidate clay, sulfate, or iron-oxide assemblages when TRDR/MTRDR product is verified",
            "Regional stratigraphic spectral unit mapping across Mount Sharp units",
        ],
        prohibited_inferences=[
            "Sub-meter boxwork wall thickness, fracture aperture, or outcrop hardness",
            "Quantitative oxide weight-percent stoichiometry (SiO2/FeO wt%)",
            "Claiming local rover-target mineral confirmation or absence where CRISM cubes are absent or dust-masked",
        ],
        known_limitations=[_UNVERIFIED_NOTE, "Detector artifacts & dust cover can suppress absorption bands"],
    ),
    "HIRISE": InstrumentCapabilityRecord(
        registry_entry_id="inst_mro_hirise_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS / University of Arizona HiRISE RDR/Ortho",
                "url": "https://hirise-pds.lpl.arizona.edu/PDS/RDR/",
                "archive_id": "MRO-M-HIRISE-3-RDR-V1.1",
            }
        ],
        unresolved_fields=[
            "Exact ground sampling distance (e.g. 0.25 vs 1.01 m/px orthorectified) varies per product and must be read from JP2/LBL MAP_SCALE",
            "Absolute horizontal registration uncertainty depends on stereo tie-point / ISIS control network",
        ],
        instrument_id="HIRISE",
        instrument_name="High Resolution Imaging Science Experiment (Ortho/RDR Optical)",
        mission_host="Mars Reconnaissance Orbiter (MRO)",
        study_region_scope="Gale Crater / Mount Sharp (where RDR/ORTHO JP2+LBL footprints intersect)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        measurement_modality="panchromatic_and_3band_optical_imaging",
        physical_quantity_measured="Calibrated I/F reflectance / 8-bit or 10-bit DN mapped via PDS3 SCALING_FACTOR/OFFSET (BG, RED, IR bandpasses)",
        measurement_method="Pushbroom CCD telescopic imaging (0.5 m primary mirror)",
        supported_measurement_types=["optical_morphology", "orthorectified_albedo_texture"],
        applicable_product_types=["HIRISE_RDR_JP2", "HIRISE_ORTHO_JP2"],
        calibration_requirements=[
            "PDS3 radiometric I/F calibration & CCD bias/flat-field removal (PRODUCT_VERSION_ID)",
            "Orthorectification provenance to stereo DTM when used for map alignment",
        ],
        processing_requirements=["JP2 + companion PDS3 .LBL spatial projection verification (IAU2000 Equirectangular/PS)"],
        spatial_applicability="Sub-meter to ~1.0 m/px orthorectified depending on binning and ortho grid; resolves features >~3x GSD",
        temporal_applicability="MRO imaging epoch recorded in IMAGE_TIME / START_TIME of product label",
        validity_conditions=[
            "Orthorectified product metadata (MAP_SCALE, PROJECTION_TYPE, LINE_PROJECTION_OFFSET) must be parsed from companion .LBL",
            "Illumination/solar incidence angle limits shadow vs albedo interpretation",
        ],
        typical_spatial_scale_m=0.3,
        measured_observables=[
            "Panchromatic RED / IRB calibrated surface radiance & texture",
            "Boxwork polygonal ridge planform geometry & fracture spacing",
            "Bedrock bedding attitude, eolian bedforms & boulder fields (>~3 pixels)",
        ],
        allowed_inferences=[
            "Meter-scale geomorphic structure, fracture patterns, and optical hazard texture cues",
            "Identification of unverified optical morphology candidates requiring spectral/in-situ confirmation",
        ],
        prohibited_inferences=[
            "Inferring mineral species (gypsum/clay/carbonate/jarosite/hematite) or oxide chemistry from visual tone, brightness, or false color",
            "Inferring CheMin XRD crystallinity or hydrated volatile abundance visually",
            "Guaranteeing absence of sub-pixel cobbles, dust pockets, or unconsolidated sand traps",
        ],
        known_limitations=[
            "3 broadband visible-NIR filters (BG/RED/IR) cannot uniquely separate minerals",
            "WMTS streaming tiles lack calibrated raw radiometric provenance and do not replace PDS3 RDR+LBL",
        ],
    ),
    "HIRISE_DTM": InstrumentCapabilityRecord(
        registry_entry_id="inst_mro_hirise_dtm_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS / University of Arizona HiRISE Stereo DTMs",
                "url": "https://hirise-pds.lpl.arizona.edu/PDS/DTM/",
                "archive_id": "MRO-M-HIRISE-5-DTM-V1.0",
            }
        ],
        unresolved_fields=[
            "Spatial correlation of vertical stereo error at short baselines is not supplied pixel-by-pixel in DTEEC PDS3 labels",
        ],
        instrument_id="HIRISE_DTM",
        instrument_name="HiRISE Stereo Digital Terrain Model (PDS DTMs)",
        mission_host="Mars Reconnaissance Orbiter (MRO)",
        study_region_scope="Gale Crater / Mount Sharp (DTEEC_009149_1750 & DTEEC_040770_1755 stereo footprints)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
        measurement_modality="stereo_photogrammetric_digital_terrain_model",
        physical_quantity_measured="Orthometric-like elevation referenced to IAU2000 MOLA areoid/sphere datum (meters)",
        measurement_method="SOCET SET stereo photogrammetric matching between converging HiRISE observations, tied to MOLA shots",
        supported_measurement_types=["elevation_raster_meters", "slope_gradient_deg", "roughness_tri_meters"],
        applicable_product_types=["HIRISE_DTM_PDS3_IMG"],
        calibration_requirements=[
            "MOLA-tied horizontal/vertical bundle adjustment verified in PDS3 .LBL",
            "IEEE_REAL 32-bit float scaling (SCALING_FACTOR/OFFSET/MISSING_CONSTANT) parsed explicitly",
        ],
        processing_requirements=[
            "Windowed/Horn finite-difference derivatives strictly using valid 3x3 neighborhoods without nodata fill",
        ],
        spatial_applicability="~1.01 m/px posting in verified DTEEC labels; smooths micro-relief (<~2-3 m) before Horn 3x3 slope estimation",
        temporal_applicability="Static macro-scale bedrock/landform geometry as of stereo pair epoch; decimeter aeolian ripple migration possible",
        validity_conditions=[
            "Must read MAP_SCALE, SAMPLE_BITS, SAMPLE_TYPE, MISSING_CONSTANT from companion .LBL",
            "Slope/TRI require explicit resolution & Rice-bias uncertainty framing on flat ground",
        ],
        typical_spatial_scale_m=1.0,
        measured_observables=[
            "Surface elevation relative to IAU2000 Mars datum (meters)",
            "Meter-scale Horn slope gradient (deg) and Terrain Ruggedness Index (m)",
            "Positive-relief ridge height across boxwork troughs",
        ],
        allowed_inferences=[
            "Multi-meter topographic relief, slope constraints, and line-of-sight geometry within verified DTM footprint",
            "Quantitative slope & TRI sensitivity when PDS3 metadata and MOLA-tie context are intact",
        ],
        prohibited_inferences=[
            "Compositional, elemental, or mineralogical identity",
            "Centimeter-scale boot/wheel traction or sub-meter soil bearing strength",
        ],
        known_limitations=["Stereo matching artifacts/blunders can occur on smooth sand sheets or deep shadows"],
    ),
    "CTX": InstrumentCapabilityRecord(
        registry_entry_id="inst_mro_ctx_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Imaging / WUSTL ODE — MRO CTX",
                "url": "https://ode.rsl.wustl.edu/mars/",
                "archive_id": "MRO-M-CTX-2-EDR-L0-V1.0",
            }
        ],
        unresolved_fields=[
            "No local calibrated/projected CTX GeoTIFF or PDS3 RDR product verified in workspace (Mars Trek WMTS is visual only)",
        ],
        instrument_id="CTX",
        instrument_name="Context Camera (MRO Panchromatic)",
        mission_host="Mars Reconnaissance Orbiter (MRO)",
        study_region_scope="Regional Gale Crater (unverified locally; visual WMTS mosaic / ODE EDR discovery only)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        measurement_modality="broadband_panchromatic_imaging",
        physical_quantity_measured="Raw DN (EDR) or relative broadband reflectance (RDR)",
        measurement_method="Line-scan pushbroom imaging (500-800 nm panchromatic)",
        supported_measurement_types=["regional_geomorphic_context"],
        applicable_product_types=["CTX_EDR", "CTX_CAL_MOSAIC"],
        calibration_requirements=["ISIS radiometric & geometric bundle calibration (EDR alone is uncalibrated/unprojected)"],
        processing_requirements=["Map projection with SPICE CK/SPK kernels"],
        spatial_applicability="~5-6 m/px nominal; regional geomorphic framing only",
        temporal_applicability="MRO mission epochs (2006+)",
        validity_conditions=["Cannot serve as quantitative radiance or sub-6m hazard verification"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "6 m/px grayscale broadband albedo & mesoscale landform continuity",
            "Regional ridge networks, fans, and channel belts",
        ],
        allowed_inferences=["Multi-kilometer stratigraphic & geomorphic context when map-projected RDR/mosaic is verified"],
        prohibited_inferences=[
            "Meter-scale rover/EVA obstacle clearance or slope estimation",
            "Mineral or chemical composition",
        ],
        known_limitations=[_UNVERIFIED_NOTE],
    ),
    "THEMIS": InstrumentCapabilityRecord(
        registry_entry_id="inst_odyssey_themis_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "ASU / NASA PDS — 2001 Mars Odyssey THEMIS",
                "url": "https://viewer.mars.asu.edu/viewer/themis",
                "archive_id": "ODY-M-THM-3-IRRDR-V1.0 / BTR",
            }
        ],
        unresolved_fields=[
            "No calibrated local THEMIS IR brightness temperature or derived thermal inertia raster ingested/validated",
        ],
        instrument_id="THEMIS",
        instrument_name="Thermal Emission Imaging System (IR & VIS)",
        mission_host="2001 Mars Odyssey",
        study_region_scope="Regional / Global (~100 m/px IR nominal; not locally acquired in workspace)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.THERMAL_INERTIA_COMPOSITION,
        measurement_modality="multispectral_thermal_ir_radiometry",
        physical_quantity_measured="Calibrated spectral radiance (W cm^-2 sr^-1 um^-1), brightness temperature (K), or modelled thermal inertia (J m^-2 K^-1 s^-1/2)",
        measurement_method="Pushbroom microbolometer thermal IR camera (10 bands, 6.78-14.88 um)",
        supported_measurement_types=["brightness_temperature", "thermal_inertia_model"],
        applicable_product_types=["THEMIS_IRRDR", "THEMIS_BTR", "THEMIS_TI_DERIVED"],
        calibration_requirements=["IR radiance calibration, drift/stripe removal & atmospheric dust/CO2 optical depth correction"],
        processing_requirements=["Map-projected mosaic with solar longitude (Ls), local solar time & slope correction"],
        spatial_applicability="~100 m/px IR pixel integrates heterogeneous sand, cobbles, shadows, and bedrock",
        temporal_applicability="Diurnal/seasonal temperature sensitivity depends strongly on local time and solar longitude",
        validity_conditions=["Requires nighttime brightness temperature & thermal model provenance before claiming induration"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "Thermal IR brightness temperature & derived thermal inertia contrast",
            "Broad silicate polymerization emissivity index (100 m/px)",
        ],
        allowed_inferences=[
            "100 m scale thermal induration vs unconsolidated dust mantling contrast when calibrated product verified",
            "Broad bulk silicate polymerization shifts (NOT specific mineral phases or oxide chemistry)",
        ],
        prohibited_inferences=[
            "Inferring quantitative elemental chemistry or oxide weight-percent from thermal inertia/temperature",
            "Inferring trace hydrated mineral identity (clays/gypsum/jarosite) from broadband TIR alone",
            "Meter-scale bedrock strength or EVA footing clearance within a 100 m pixel",
        ],
        known_limitations=[_UNVERIFIED_NOTE, "Thermal inertia is a physical thermophysical property, NOT chemical composition"],
    ),
    "MOLA": InstrumentCapabilityRecord(
        registry_entry_id="inst_mgs_mola_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MGS MOLA MEGDR",
                "url": "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
                "archive_id": "MGS-M-MOLA-5-MEGDR-L3-V1.0",
            }
        ],
        unresolved_fields=[
            "Local sub-pixel relief inside 463 m (128 ppd) / 14.8 km (4 ppd) cells is completely unmeasured",
        ],
        instrument_id="MOLA",
        instrument_name="Mars Orbiter Laser Altimeter (MEGDR Gridded)",
        mission_host="Mars Global Surveyor (MGS)",
        study_region_scope="Verified locally: MEGT00N090HB (128 ppd) & MEGT90N000CB (4 ppd) in Gale sector",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
        measurement_modality="orbital_laser_altimetry_gridded_dem",
        physical_quantity_measured="Topographic planetary radius & elevation relative to MOLA areoid (meters via SCALING_FACTOR/OFFSET)",
        measurement_method="Pulsed 1064 nm laser altimeter binned into cylindrical gridded MEGDR rasters",
        supported_measurement_types=["macro_regional_elevation_meters", "areoid_datum_reference"],
        applicable_product_types=["MOLA_MEGDR_IMG"],
        calibration_requirements=["PDS3 SCALING_FACTOR/OFFSET & IAU2000 sphere radius (3396000.0 m) verified in .LBL"],
        processing_requirements=["Check bounds-transform consistency and exact pixel scale per product"],
        spatial_applicability="Product-specific (~463 m/px for 128 ppd MEGDR; ~14.8 km/px for 4 ppd); macro-basin scale only",
        temporal_applicability="MGS mapping phase (1999-2001)",
        validity_conditions=["Strictly invalid for local EVA traverse slope or micro-hazard assessment"],
        typical_spatial_scale_m=463.0,
        measured_observables=[
            "Gridded planetary elevation (IAU2000 sphere datum)",
            "Basin-to-mountain elevation profile & global tiepoint framing",
        ],
        allowed_inferences=[
            "Macro-basin elevation framing and inter-quadrangle vertical datum tie",
        ],
        prohibited_inferences=[
            "Local EVA traverse slope feasibility or surface roughness (<1 km)",
            "Meter-scale boxwork ridge relief or cliff detection",
        ],
        known_limitations=["Between-track gaps in equatorial MEGDR cells are interpolated; steep walls are heavily smoothed"],
    ),
    "ODYSSEY_GRS_NS": InstrumentCapabilityRecord(
        registry_entry_id="inst_odyssey_grs_ns_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — 2001 Mars Odyssey GRS/NS",
                "url": "https://pds-geosciences.wustl.edu/missions/odyssey/grs.html",
                "archive_id": "ODY-M-GRS-5-ELEMENTS-V1.0",
            }
        ],
        unresolved_fields=["No local GRS/NS element abundance map product ingested/validated in workspace"],
        instrument_id="ODYSSEY_GRS_NS",
        instrument_name="Mars Odyssey Gamma-Ray & Neutron Spectrometer",
        mission_host="2001 Mars Odyssey",
        study_region_scope="Planetary coarse regional (~300,000 m footprint; not acquired locally)",
        platform_kind=InstrumentPlatformKind.ORBITAL,
        measurement_class=MeasurementClass.HYDRATED_NEUTRON_SUBSURFACE,
        measurement_modality="gamma_ray_and_epithermal_neutron_spectroscopy",
        physical_quantity_measured="Sub-decimeter bulk elemental weight-percent / H2O-equivalent mass fraction",
        measurement_method="Passive orbital gamma-ray line & neutron flux sensing from top tens of cm",
        supported_measurement_types=["planetary_bulk_element_concentration"],
        applicable_product_types=["ODYSSEY_GRS_MAP"],
        calibration_requirements=["Cosmic-ray normalization, atmospheric thickness correction, footprint deconvolution"],
        processing_requirements=["5-degree equatorial map binning (~300 km spatial Gaussian FWHM)"],
        spatial_applicability="~300 km half-response footprint; cannot isolate Gale Crater interior units",
        temporal_applicability="Multi-year orbital integration",
        validity_conditions=["Hemispheric/regional trend context only"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "Sub-surface (~10-50 cm) bulk H2O-equivalent hydrogen, K, Th, Fe, Si over ~300 km footprint",
        ],
        allowed_inferences=[
            "Hemispheric-to-regional crustal hydration & bulk elemental background when product verified",
        ],
        prohibited_inferences=[
            "Specific Gale outcrop or Mount Sharp boxwork enrichment",
            "Mineral phase identification or meter-scale targeting",
        ],
        known_limitations=[_UNVERIFIED_NOTE],
    ),
    "CHEMCAM_LIBS": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_chemcam_libs_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MSL ChemCam MOC",
                "url": "https://pds-geosciences.wustl.edu/missions/msl/chemcam.htm",
                "archive_id": "MSL-M-CHEMCAM-5-MOC-V1.0",
            }
        ],
        unresolved_fields=[
            "Target-point absolute IAU2000 coordinates vs rover station coordinates: ChemCam targets are located by rover station RMC + laser standoff",
            "Minor volatile elements (S, H, Cl) in MOC tables lack quantitative oxide wt% calibration columns",
        ],
        instrument_id="CHEMCAM_LIBS",
        instrument_name="Chemistry & Camera (LIBS & RMI)",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity traverse MOC PDS3 CSV + .LBL verified locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        measurement_modality="laser_induced_breakdown_spectroscopy",
        physical_quantity_measured="Major oxide abundances (SiO2, TiO2, Al2O3, FeOT, MgO, CaO, Na2O, K2O wt%) with PLS RMSEP & shot dispersion",
        measurement_method="1067 nm pulsed Nd:KGW laser ablation plasma emission spectroscopy (UV-VNIR)",
        supported_measurement_types=["in_situ_major_oxide_wt_percent"],
        applicable_product_types=["CHEMCAM_MOC_CSV_PDS3"],
        calibration_requirements=[
            "Multivariate PLS+ICA earth-standard calibration model (MOC table, NOT raw uncalibrated CCS/PSV)",
            "Passive sky-spectrum PSV records are strictly excluded from compositional claims",
        ],
        processing_requirements=["RMC site_drive lookup against verified JPL MSL waypoints; retain DISTANCE_TO_TARGET"],
        spatial_applicability="~0.3-0.6 mm laser spot; strictly represents targeted spot at known RMC station, NOT whole orbital pixel",
        temporal_applicability="MSL Curiosity sols matching verified PDS MOC release",
        validity_conditions=[
            "Passive PSV frames without laser shots CANNOT supply composition",
            "Elemental oxides CANNOT uniquely establish crystalline mineral phase without CheMin XRD or vibrational IR",
        ],
        typical_spatial_scale_m=0.0005,
        measured_observables=[
            "Sub-mm laser-induced plasma atomic emission lines -> SiO2..K2O (wt%)",
            "Relative H/S/Cl qualitative indicators where separately calibrated",
        ],
        allowed_inferences=[
            "Sub-mm major-oxide elemental chemistry at targeted rock/vein spot",
            "Geochemical anomalies consistent with Ca-rich, Fe-rich, or high-silica compositions (requires XRD/NIR for mineral confirmation)",
        ],
        prohibited_inferences=[
            "Definitive crystalline mineral phase identification (gypsum vs anhydrite vs bassanite vs smectite vs jarosite)",
            "Claiming a sub-mm LIBS shot represents an entire orbital CRISM/THEMIS pixel or unexplored ridge >50 m away",
            "Inferring mineral absence across an outcrop from one laser raster gap",
        ],
        known_limitations=["Laser pits sample sub-mm surface dust/coatings on initial shots unless shot depth filtered"],
    ),
    "CHEMIN_XRD": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_chemin_xrd_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MSL CheMin RDR5",
                "url": "https://pds-geosciences.wustl.edu/missions/msl/chemin.htm",
                "archive_id": "MSL-M-CHEMIN-5-RDR-V1.0",
            }
        ],
        unresolved_fields=[
            "Drill targets whose RMC is absent from MSL_waypoints.json remain strictly UNLOCATED without map coordinates",
        ],
        instrument_id="CHEMIN_XRD",
        instrument_name="Chemistry & Mineralogy X-Ray Diffractometer",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity drill spots; RDR5 + CHEMIN_MIN.FMT verified locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MINERALOGY_XRD,
        measurement_modality="transmission_x_ray_diffraction",
        physical_quantity_measured="Crystalline mineral modal abundance (wt%, Rietveld refinement) and amorphous/phyllosilicate component",
        measurement_method="Co K-alpha transmission CCD X-ray diffraction of sieved drill powder (<150 um)",
        supported_measurement_types=["definitive_crystalline_mineral_phase_wt_percent"],
        applicable_product_types=["CHEMIN_RDR5_MIN_CSV_PDS3"],
        calibration_requirements=[
            "Rietveld refinement with CHEMIN_MIN.FMT unit=WEIGHT_PERCENT & companion .LBL error model check",
        ],
        processing_requirements=["Strict RMC join to waypoints; keep unlocated drill records isolated from spatial queries"],
        spatial_applicability="Discrete ~1.6 cm drill hole sample (~150 um sieved fines); NEVER continuously mapped across terrain",
        temporal_applicability="MSL Curiosity drill campaigns",
        validity_conditions=["Amorphous component lacks long-range crystal structure and must be reported explicitly"],
        typical_spatial_scale_m=0.016,
        measured_observables=[
            "Definitive crystal d-spacing XRD patterns -> phyllosilicates (smectite), Ca-sulfates (gypsum, bassanite, anhydrite), hematite, magnetite, jarosite, plagioclase, pyroxene + X-ray amorphous fraction",
        ],
        allowed_inferences=[
            "Authoritative crystalline mineral phase identification & modal abundances at the exact drilled horizon",
        ],
        prohibited_inferences=[
            "Direct organic carbon molecular structure",
            "Extrapolating exact modal mineral percentages to unsampled strata or across entire orbital pixels",
            "Inferring mineral absence below CheMin ~1 wt% XRD detection limit",
        ],
        known_limitations=["Detection limit ~1-2 wt% for crystalline phases; X-ray amorphous composition requires APXS/SAM constraints"],
    ),
    "APXS": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_apxs_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MSL APXS PDS4 Supplement",
                "url": "https://pds-geosciences.wustl.edu/missions/msl/apxs.htm",
                "archive_id": "urn:nasa:pds:msl_apxs_derived (ds01_2021je007171r.csv/.xml)",
            }
        ],
        unresolved_fields=[
            "Analytical precision sigma interpretation flagged as unspecified_in_pds4_label when omitted in PDS4 XML",
        ],
        instrument_id="APXS",
        instrument_name="Alpha Particle X-Ray Spectrometer",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater / Mount Sharp (Curiosity contact targets; PDS4 XML+CSV verified locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        measurement_modality="particle_induced_x_ray_emission_and_rbs",
        physical_quantity_measured="Bulk oxide wt% (SiO2..SO3, Cl, MnO) & trace elements (Ni, Zn, Br ppm)",
        measurement_method="244Cm alpha-particle PIXE + X-ray fluorescence over ~1.7 cm sensor contact field",
        supported_measurement_types=["in_situ_bulk_elemental_oxides_and_traces"],
        applicable_product_types=["APXS_PDS4_DELIMITED_CSV"],
        calibration_requirements=[
            "Companion PDS4 .XML <Field_Delimited> schema validated; (0,0) values flagged as <LOD",
        ],
        processing_requirements=["Convert Gale EQC Easting/Northing (R=3396190.0 m) -> IAU2000 Planetocentric lat/lon"],
        spatial_applicability="~1.7 cm contact footprint at specific rover target",
        temporal_applicability="MSL Curiosity contact targets (Sols 0-3076 in verified local table)",
        validity_conditions=["Elemental oxides/SO3 cannot uniquely specify mineral phase without XRD/IR"],
        typical_spatial_scale_m=0.017,
        measured_observables=[
            "Bulk ~1.7 cm contact elemental oxides (SiO2..SO3, Cl, MnO wt%) and Ni/Zn/Br ppm",
        ],
        allowed_inferences=[
            "Quantitative bulk rock elemental geochemistry, sulfur/chlorine enrichment, Mn/Fe ratios at contact target",
        ],
        prohibited_inferences=[
            "Claiming crystalline mineral structure (gypsum vs bassanite vs Mg-sulfate vs smectite) from oxide ratios alone",
            "Organic molecular composition or representing an entire orbital pixel",
        ],
        known_limitations=["Contact-spot surface geometry & dust thickness attenuate light elements (Na, Mg, Si)"],
    ),
    "SAM_EGA_GCMS": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_sam_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — MSL SAM",
                "url": "https://pds-geosciences.wustl.edu/missions/msl/sam.htm",
                "archive_id": "MSL-M-SAM-2-EDR-L0-V1.0",
            }
        ],
        unresolved_fields=["No local SAM EGA/GCMS/TLS PDS tables acquired/parsed in workspace"],
        instrument_id="SAM_EGA_GCMS",
        instrument_name="Sample Analysis at Mars (EGA / QMS / GCMS / TLS)",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater drill/scoop spots (unacquired locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.VOLATILE_ORGANIC_ISOTOPE,
        measurement_modality="evolved_gas_quadrupole_gc_tunable_laser_mass_spec",
        physical_quantity_measured="Thermal volatile release partial pressures, molecular mass fragments & isotope ratios",
        measurement_method="Pyrolysis to ~860 C + QMS / GCMS / TLS isotope spectroscopy",
        supported_measurement_types=["volatile_evolution_isotopes_organics"],
        applicable_product_types=["SAM_EGA_RDR", "SAM_GCMS_RDR"],
        calibration_requirements=["Blank subtraction, MTBSTFA/derivatization background accounting"],
        processing_requirements=["Drill RMC spatial linkage"],
        spatial_applicability="Discrete ~1.6 cm drill fines cup",
        temporal_applicability="MSL Curiosity SAM runs",
        validity_conditions=["Pyrolysis in presence of oxychlorines degrades fragile organics unless wet-derivatized"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "Thermally evolved H2O, SO2, CO2, O2, NO, HCl release temperature curves",
            "D/H, 13C/12C, 18O/16O isotopes and volatile organic fragments",
        ],
        allowed_inferences=[
            "Volatile host decomposition temperatures (oxychlorines, sulfates, clays) & isotopic composition when verified",
        ],
        prohibited_inferences=[
            "Silicate rock hardness, slope mechanics, or visual/regional uniform continuity",
            "Claiming global absence of organics from negative pyrolysis in perchlorate-bearing fines",
        ],
        known_limitations=[_UNVERIFIED_NOTE],
    ),
    "MASTCAM": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_mastcam_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Imaging Node — MSL Mastcam",
                "url": "https://pds-imaging.jpl.nasa.gov/",
                "archive_id": "MSL-M-MASTCAM-5-RDR-V1.0",
            }
        ],
        unresolved_fields=["No local calibrated Mastcam RDR/IOF frames acquired/verified in workspace"],
        instrument_id="MASTCAM",
        instrument_name="Mast Camera (34mm / 100mm Multispectral Stereo)",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater / Mount Sharp (unacquired locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        measurement_modality="surface_multispectral_stereo_optical_imaging",
        physical_quantity_measured="Bayer RGB / 11-filter VNIR radiance or calibrated I/F (445-1013 nm)",
        measurement_method="Mast-mounted stereo telephoto framing camera",
        supported_measurement_types=["outcrop_stereo_morphology", "vnir_ferric_slope_proxy"],
        applicable_product_types=["MASTCAM_RDR_IMG"],
        calibration_requirements=["Bayer de-mosaic, white-balance target calibration, flat-field"],
        processing_requirements=["CAHVOR camera model pointing + rover RMC pose"],
        spatial_applicability="Distance-dependent (~mm at 2 m to ~cm at 30 m)",
        temporal_applicability="MSL surface sols",
        validity_conditions=["Optical color/albedo CANNOT diagnose non-ferric white minerals or sulfates/clays"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "True-color stereo mosaics & narrow-band VNIR filters (445-1013 nm)",
            "Boxwork fracture wall height, cross-cutting diagenetic vein geometry",
        ],
        allowed_inferences=["Outcrop-scale stratigraphy, fracture intersections, broad ferric iron absorption cues"],
        prohibited_inferences=[
            "Mineral species identification (gypsum, anhydrite, smectite, jarosite, carbonate) from bright/white optical tone",
            "Quantitative oxide stoichiometry or extrapolation across unexplored regions",
        ],
        known_limitations=[_UNVERIFIED_NOTE],
    ),
    "MAHLI": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_mahli_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Imaging Node — MSL MAHLI",
                "url": "https://pds-imaging.jpl.nasa.gov/",
                "archive_id": "MSL-M-MAHLI-5-RDR-V1.0",
            }
        ],
        unresolved_fields=["No local MAHLI RDR frames acquired/verified in workspace"],
        instrument_id="MAHLI",
        instrument_name="Mars Hand Lens Imager",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater contact imaging (unacquired locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
        measurement_modality="arm_contact_micro_optical_imaging",
        physical_quantity_measured="RGB Bayer focus-merged macro image DN / radiance",
        measurement_method="Arm-turret focusable RGB CCD imaging (~14-100 um/px)",
        supported_measurement_types=["grain_scale_textural_morphology"],
        applicable_product_types=["MAHLI_RDR_IMG"],
        calibration_requirements=["Standoff distance from stepper-motor focus count + lighting"],
        processing_requirements=["RMC arm pose registration"],
        spatial_applicability="~14-100 um/px within ~2 cm - 2 m focus envelope",
        temporal_applicability="MSL surface sols",
        validity_conditions=["Micro-morphology does not establish elemental or crystal identity"],
        typical_spatial_scale_m=None,
        measured_observables=[
            "~14-100 um/px close-up optical imaging of grain sorting, cement textures, nodules, veins",
        ],
        allowed_inferences=["Micro-textural cementation, sedimentary grain size, diagenetic crystal habit clues"],
        prohibited_inferences=[
            "Elemental, chemical, or crystalline mineral identity from crystal/vein optical appearance",
            "Regional uniformity beyond imaged rock face",
        ],
        known_limitations=[_UNVERIFIED_NOTE],
    ),
    "REMS": InstrumentCapabilityRecord(
        registry_entry_id="inst_msl_rems_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.VERIFIED,
        last_verified_utc="2026-11-15T00:00:00Z",
        source_references=[
            {
                "source_name": "NASA PDS Atmospheres Node — MSL REMS",
                "url": "https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html",
                "archive_id": "MSL-M-REMS-4-ENVCDR-V1.0",
            }
        ],
        unresolved_fields=[
            "Local workspace holds Sol 10 sample (RME_398334213ADR...); continuous multi-sol meteorological time-series is not acquired locally",
            "MODRDR6.FMT boom wind sensor degradation limits horizontal wind validity on later sols",
            "Strictly non-composition instrument; excluded at Stage 2 of mineral chemistry index",
        ],
        instrument_id="REMS",
        instrument_name="Rover Environmental Monitoring Station",
        mission_host="Mars Science Laboratory (MSL Curiosity)",
        study_region_scope="Gale Crater diurnal meteorology (RME ADR PDS3 table + .LBL/.FMT verified locally)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.METEOROLOGY_ENVIRONMENT,
        measurement_modality="in_situ_meteorological_and_uv_radiometry",
        physical_quantity_measured="Barometric pressure (Pa), air & ground brightness temp (K), RH (%), UV irradiance (W/m^2)",
        measurement_method="Boom/deck capacitive barometry, thermopile IR & photodiode UV sensing",
        supported_measurement_types=["in_situ_pressure_temperature_uv_telemetry"],
        applicable_product_types=["REMS_ADR_TAB_PDS3", "REMS_MODRDR_TAB_PDS3"],
        calibration_requirements=["PDS3 .FMT column schema & confidence bitmasks parsed"],
        processing_requirements=["RMC rover location & LMST solar time synchronization"],
        spatial_applicability="Point meteorological station along Curiosity traverse",
        temporal_applicability="Observed Curiosity sols ONLY (historical time-series, not live forecast)",
        validity_conditions=["Ground brightness temperature reflects radiative skin temp, NOT rock chemistry"],
        typical_spatial_scale_m=1.0,
        measured_observables=[
            "Diurnal surface pressure (Pa), air & ground brightness temperature (K), UV irradiance",
        ],
        allowed_inferences=[
            "Measured Gale Crater diurnal thermal/barometric cycles during archived Curiosity sols",
        ],
        prohibited_inferences=[
            "Subsurface soil mineralogy or chemical composition from ground brightness temperature",
            "Real-time future EVA weather/storm forecasting",
        ],
        known_limitations=["Boom 1 wind sensor damaged at landing; purely environmental telemetry"],
    ),
    "PIXL_SHERLOC": InstrumentCapabilityRecord(
        registry_entry_id="inst_m2020_pixl_sherloc_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — Mars 2020 PIXL / SHERLOC",
                "url": "https://pds-geosciences.wustl.edu/missions/mars2020/",
                "archive_id": "urn:nasa:pds:mars2020_pixl / mars2020_sherloc",
            }
        ],
        unresolved_fields=["Strictly isolated Perseverance/Jezero instrument; no local product verified"],
        instrument_id="PIXL_SHERLOC",
        instrument_name="PIXL Micro-XRF & SHERLOC Deep-UV Raman/Fluorescence",
        mission_host="Mars 2020 Perseverance",
        study_region_scope="Jezero Crater ONLY (~18.4 N, 77.5 E — ~3,700 km from Gale)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.MINERALOGY_SPECTRAL,
        measurement_modality="micro_xrf_and_deep_uv_raman",
        physical_quantity_measured="Micro-XRF elemental counts & Raman wavenumber shifts (Jezero ONLY)",
        measurement_method="28 kV Rh micro-XRF & 248.6 nm DUV laser Raman",
        supported_measurement_types=["jezero_only_micro_elemental_and_raman"],
        applicable_product_types=["M2020_PIXL_RDR", "M2020_SHERLOC_RDR"],
        calibration_requirements=["M2020 arm metrology & Jezero Sol ephemeris"],
        processing_requirements=["Mission quarantine verification"],
        spatial_applicability="Jezero Crater ONLY — incompatible with Gale Crater / Mount Sharp",
        temporal_applicability="Mars 2020 Perseverance surface operations",
        validity_conditions=["NEVER valid for Gale Crater evidence or target eligibility"],
        typical_spatial_scale_m=None,
        measured_observables=["Jezero Crater micro-XRF & deep-UV Raman bands"],
        allowed_inferences=["Jezero Crater mission science analysis ONLY"],
        prohibited_inferences=[
            "ANY extrapolation, correlation, target generation, or campaign evidence for Gale Crater / Mount Sharp",
        ],
        known_limitations=[_UNVERIFIED_NOTE, "Mission-isolated to Jezero Crater"],
        mission_isolated_from_gale=True,
        mission_isolation_note=(
            "STRICT MISSION ISOLATION: Perseverance / Jezero instruments operate ~3,700 km from Gale Crater "
            "and NEVER enter Gale Crater science campaigns, target evidence, or route bonuses."
        ),
    ),
    "SUPERCAM_MASTCAMZ": InstrumentCapabilityRecord(
        registry_entry_id="inst_m2020_supercam_mastcamz_v2",
        registry_version=REGISTRY_VERSION,
        verification_status=RegistryVerificationStatus.UNVERIFIED,
        source_references=[
            {
                "source_name": "NASA PDS Geosciences Node — Mars 2020 SuperCam / Mastcam-Z",
                "url": "https://pds-geosciences.wustl.edu/missions/mars2020/",
                "archive_id": "urn:nasa:pds:mars2020_supercam / mars2020_mastcamz",
            }
        ],
        unresolved_fields=["Strictly isolated Perseverance/Jezero instrument; no local product verified"],
        instrument_id="SUPERCAM_MASTCAMZ",
        instrument_name="SuperCam (LIBS/Raman/VISIR) & Mastcam-Z",
        mission_host="Mars 2020 Perseverance",
        study_region_scope="Jezero Crater ONLY (~18.4 N, 77.5 E — ~3,700 km from Gale)",
        platform_kind=InstrumentPlatformKind.SURFACE_IN_SITU,
        measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
        measurement_modality="remote_libs_raman_visir_and_zoom_stereo",
        physical_quantity_measured="Jezero elemental/Raman/VISIR spectra & stereo RGB",
        measurement_method="Mast-mounted remote LIBS, 532 nm Raman, VISIR & zoom stereo",
        supported_measurement_types=["jezero_only_remote_spectroscopy"],
        applicable_product_types=["M2020_SUPERCAM_RDR", "M2020_MASTCAMZ_RDR"],
        calibration_requirements=["Mars 2020 target calibration"],
        processing_requirements=["Mission quarantine verification"],
        spatial_applicability="Jezero Crater ONLY — incompatible with Gale Crater / Mount Sharp",
        temporal_applicability="Mars 2020 Perseverance surface operations",
        validity_conditions=["NEVER valid for Gale Crater evidence or target eligibility"],
        typical_spatial_scale_m=None,
        measured_observables=["Jezero Crater remote LIBS/Raman/VISIR spectroscopy & stereo zoom imaging"],
        allowed_inferences=["Jezero Crater outcrop characterization ONLY"],
        prohibited_inferences=[
            "ANY cross-pollination into Gale Crater / Mount Sharp science plans or mineral evidence",
        ],
        known_limitations=[_UNVERIFIED_NOTE, "Mission-isolated to Jezero Crater"],
        mission_isolated_from_gale=True,
        mission_isolation_note=(
            "STRICT MISSION ISOLATION: Mars 2020 Perseverance Jezero observations remain strictly quarantined from Gale Crater."
        ),
    ),
}

_VISUAL_MINERAL_PATTERN = re.compile(
    r"\b("
    r"gypsum|anhydrite|bassanite|sulfates?|phyllosilicates?|smectites?|kaolinite|"
    r"nontronite|montmorillonite|illite|chlorite|clays?|jarosite|alunite|"
    r"hematite|goethite|magnetite|carbonates?|calcite|magnesite|siderite|"
    r"olivine|pyroxene|feldspar|plagioclase|quartz|silica|halite|perchlorate|"
    r"caso4|mgso4|fe2o3|sio2|xrd|wt%|elemental|salinity|"
    r"mineral\s+(confirm\w*|identit\w*|phase|presence|composition)|"
    r"chemical\s+composition|oxide\s+abund\w*"
    r")\b",
    re.IGNORECASE,
)

_ELEMENTAL_TO_PHASE_PATTERN = re.compile(
    r"\b("
    r"definitive\s+xrd|crystal\s+structure|mineral\s+phase|"
    r"confirmed?\s+(smectite|gypsum|anhydrite|bassanite|jarosite|kaolinite|clay|carbonate|hematite)\s*(phase|mineral)?|"
    r"proves?\s+(gypsum|anhydrite|bassanite|smectite|jarosite|kaolinite|clay|carbonate|hematite)|"
    r"xrd\s+identity|crystalline\s+polymorph"
    r")\b",
    re.IGNORECASE,
)

_THERMAL_TO_CHEM_PATTERN = re.compile(
    r"\b("
    r"chemi(?:cal|stry)|element(?:al)?|oxides?|wt%|"
    r"gypsum|anhydrite|sulfates?|clays?|smectite|jarosite|carbonate|halite|perchlorate|"
    r"mineral\s+(phase|identit\w*|composition)|xrd|"
    r"bearing\s+capacity|soil\s+strength|footing\s+clearance"
    r")\b",
    re.IGNORECASE,
)

_NON_DETECTION_ABSENCE_PATTERN = re.compile(
    r"(proves?\s+absence|proves?\s+no\s+|ruled\s+out|guarantees?\s+absence|"
    r"definitely\s+absent|absent\s+everywhere|zero\s+\w+\s+present|"
    r"non[- ]?detection\s+(?:proves|means|establishes)\s+(?:no|absence|none)|"
    r"missing\s+(?:detection|observation)\s+(?:proves|means|establishes)\s+(?:no|absence|none)|"
    r"not\s+detected\s+therefore\s+(?:absent|none|not\s+present))",
    re.IGNORECASE,
)

_COARSE_TO_LOCAL_PATTERN = re.compile(
    r"\b("
    r"local\s+slope|eva\s+slope|rover\s+hazard|boxwork\s+thickness|wall\s+thickness|"
    r"traversable\s+meter|meter[- ]?scale|centimeter|sub[- ]?meter|"
    r"footing\s+clearance|single\s+rock|individual\s+outcrop|soil\s+bearing"
    r")\b",
    re.IGNORECASE,
)

_LOCAL_TO_REGIONAL_PATTERN = re.compile(
    r"\b("
    r"entire\s+orbital\s+pixel|entire\s+crism\s+pixel|whole\s+mount\s+sharp|"
    r"all\s+of\s+gale|crater[- ]?wide|basin[- ]?wide\s+uniform|kilometer[- ]?scale\s+uniform|"
    r"proves\s+regional\s+uniformity|represents\s+entire\s+unit"
    r")\b",
    re.IGNORECASE,
)


def list_instruments(*, include_mission_isolated: bool = True) -> List[InstrumentCapabilityRecord]:
    items = list(_INSTRUMENTS.values())
    if not include_mission_isolated:
        items = [i for i in items if not i.mission_isolated_from_gale]
    return items


def get_instrument(instrument_id: str) -> Optional[InstrumentCapabilityRecord]:
    return _INSTRUMENTS.get(instrument_id.strip().upper())


def _build_preconditions(inst: InstrumentCapabilityRecord) -> dict:
    return {
        "required_evidence_types": list(inst.supported_measurement_types),
        "required_processing_or_calibration": [*inst.calibration_requirements, *inst.processing_requirements],
        "applicable_spatial_scale": inst.spatial_applicability,
        "required_contextual_evidence": list(inst.validity_conditions),
        "known_limitations": list(inst.known_limitations),
        "prohibited_conclusions": list(inst.prohibited_inferences),
    }


def check_inference_validity(instrument_id: str, claimed_inference: str) -> InferenceValidationResponse:
    """Enforce scientific inference firewall across mission isolation, modality, scale, and non-detection limits."""
    inst = get_instrument(instrument_id)
    if inst is None:
        return InferenceValidationResponse(
            instrument_id=instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="unknown_instrument_rejected",
            rationale=f"Instrument '{instrument_id}' is not registered in the MARSCOPE Planetary Capability Registry.",
        )

    pre = _build_preconditions(inst)
    claim_l = claimed_inference.lower()

    # 1. Mission isolation (Jezero/Perseverance cannot support Gale claims)
    if inst.mission_isolated_from_gale and any(
        tok in claim_l for tok in ("gale", "mount sharp", "aeolis", "curiosity", "boxwork")
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="mission_isolation_violation",
            rationale=inst.mission_isolation_note or "Jezero Crater instrument cannot support Gale Crater claims.",
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 2. Missing detection cannot prove geological/mineral absence
    if _NON_DETECTION_ABSENCE_PATTERN.search(claimed_inference):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_non_detection_absence_claim",
            rationale=(
                f"A missing or sub-threshold detection from {inst.instrument_id} CANNOT establish true absence; "
                "non-detections may reflect dust mantling, spatial sampling gaps, or instrument detection limits."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 3. Optical tone / appearance cannot establish mineral identity or chemistry
    if inst.measurement_class == MeasurementClass.MORPHOLOGY_HIGHRES and _VISUAL_MINERAL_PATTERN.search(claimed_inference):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_visual_to_mineral_inference",
            rationale=(
                f"{inst.instrument_id} measures optical morphology/reflectance only ({inst.measurement_modality}) "
                "and CANNOT establish mineral identity or elemental chemistry without spectral/XRD/LIBS confirmation."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 4. Elemental detection cannot establish crystalline mineral phase
    if inst.measurement_class == MeasurementClass.ELEMENTAL_CHEMISTRY and _ELEMENTAL_TO_PHASE_PATTERN.search(
        claimed_inference
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_elemental_to_mineral_phase_claim",
            rationale=(
                f"{inst.instrument_id} provides elemental abundance only; elemental enrichment (e.g., Ca+S or Mg+S) "
                "requires CheMin XRD or calibrated SWIR vibrational spectroscopy for crystalline phase identification."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 5. Thermal response cannot establish chemical composition or sub-pixel mechanics
    if (
        inst.measurement_class
        in {MeasurementClass.THERMAL_INERTIA_COMPOSITION, MeasurementClass.METEOROLOGY_ENVIRONMENT}
        and _THERMAL_TO_CHEM_PATTERN.search(claimed_inference)
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_thermal_to_composition_inference",
            rationale=(
                f"{inst.instrument_id} senses thermal radiation/temperature ({inst.physical_quantity_measured}) and "
                "CANNOT automatically establish chemical composition, mineral identity, or sub-pixel soil bearing strength."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 6. Coarse orbital resolution -> meter/centimeter local hazard/property claims
    if (
        inst.platform_kind == InstrumentPlatformKind.ORBITAL
        and inst.instrument_id in {"MOLA", "ODYSSEY_GRS_NS", "THEMIS", "CTX", "CRISM"}
        and _COARSE_TO_LOCAL_PATTERN.search(claimed_inference)
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_resolution_extrapolation",
            rationale=(
                f"{inst.instrument_id} spatial applicability ({inst.spatial_applicability}) cannot support "
                "centimeter- or meter-scale outcrop hazard, slope, or fracture-thickness claims."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    # 7. Point/local in-situ observation -> orbital-pixel or crater-wide extrapolation
    if inst.platform_kind == InstrumentPlatformKind.SURFACE_IN_SITU and _LOCAL_TO_REGIONAL_PATTERN.search(
        claimed_inference
    ):
        return InferenceValidationResponse(
            instrument_id=inst.instrument_id,
            claimed_inference=claimed_inference,
            allowed=False,
            classification="prohibited_local_to_regional_extrapolation",
            rationale=(
                f"{inst.instrument_id} samples localized targets ({inst.spatial_applicability}) and CANNOT "
                "represent an entire orbital pixel or Mount Sharp unit without corroborating orbital/distributed evidence."
            ),
            prohibited_inferences=inst.prohibited_inferences,
            **pre,
        )

    scale_desc = (
        f"nominal {inst.typical_spatial_scale_m} m reference (product header takes precedence)"
        if inst.typical_spatial_scale_m is not None
        else "must be read from validated product metadata"
    )
    verif_clause = (
        ""
        if inst.verification_status == RegistryVerificationStatus.VERIFIED
        else " [Registry spec UNVERIFIED locally: requires validated product metadata before qualifying evidence]"
    )
    return InferenceValidationResponse(
        instrument_id=inst.instrument_id,
        claimed_inference=claimed_inference,
        allowed=True,
        classification="within_instrument_capability_scope",
        rationale=(
            f"Inference falls within {inst.instrument_name} ({inst.measurement_class.value}) capability scope "
            f"subject to required calibration/processing preconditions ({scale_desc}).{verif_clause}"
        ),
        prohibited_inferences=inst.prohibited_inferences,
        **pre,
    )
