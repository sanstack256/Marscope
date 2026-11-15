"""
MARSCOPE Science Question & Hypothesis Repository
Prompt 17: Curated Gale Crater / Mount Sharp investigation questions (including
the 2025 boxwork formations hypothesis) plus persisted USER_DEFINED custom questions.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from app.science.investigation.schemas import (
    CustomScienceQuestionCreateRequest,
    MeasurementClass,
    MeasurementRequirementSpec,
    ScienceQuestionDefinition,
    ThresholdRuleClassification,
)


_DEFAULT_QUESTIONS: List[ScienceQuestionDefinition] = [
    ScienceQuestionDefinition(
        question_id="gale_boxwork_origin",
        title="Origin & Mineralogy of the 2025 Mount Sharp Boxwork Formations",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Investigation Hypothesis H1 (Early Fracture-Cementation): Polygonal boxwork ridges on Mount Sharp "
            "may record mineralized fracture fills (potentially Ca/Mg-sulfate, silica, phyllosilicate, or Fe-oxide "
            "cements) that resisted aeolian erosion relative to surrounding host strata."
        ),
        competing_hypotheses=[
            "H1: Subsurface diagenetic fluid precipitation cemented fracture walls prior to differential wind erosion.",
            "H2: Physical grain-size sorting, tectonic jointing, or early desiccation cracks cemented chiefly by "
            "silica/Fe-oxides rather than sulfate salts.",
            "H3: Multi-stage superimposed fracturing where later Ca-sulfate veins postdate primary indurated walls.",
        ],
        alternative_explanations=[
            "Positive relief could reflect silicified mudstone septa rather than hydrated sulfate veins.",
            "High optical albedo alone may represent dust-free rock faces or late fracture fills, not wall bulk mineralogy.",
        ],
        contradicting_evidence_criteria=[
            "Absence of elevated SO3/CaO/MgO/SiO2 enrichment inside ridge walls compared to adjacent host mudstone.",
            "XRD/SWIR signatures dominated by unaltered basaltic plagioclase+pyroxene without fracture-fill phases.",
        ],
        unresolved_assumptions=[
            "Whether locally sampled Curiosity LIBS/APXS/CheMin spots overlap the specific upper Mount Sharp boxwork corridor.",
            "Sub-meter wall chemistry heterogeneity below orbital CRISM pixel resolution (~18 m/px).",
        ],
        current_evidence_state="UNRESOLVED_REQUIRES_CO_REGISTERED_MULTI_INSTRUMENT_EVIDENCE",
        geological_setting="Mount Sharp Gediz Vallis / Sulfate-Bearing & Boxwork Ridge Facies (Gale Crater)",
        is_user_defined=False,
        target_phenomena=["SO3", "CaO", "FeO", "SiO2", "MgO", "boxwork", "fracture"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires co-registered verified HiRISE optical geometry, verified meter-scale HiRISE DTM relief, "
            "paired ridge-vs-host elemental chemistry (ChemCam/APXS), and crystalline/SWIR spectral phase validation "
            "(CheMin XRD / SAM / CRISM TRDR) before supporting any mineralogical genesis conclusion."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_topo_1m",
                label="Meter-Scale Ridge Relief & Traverse Slope Geometry (Product Selection Preference <=2 m/px DEM)",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg", "roughness_tri_m"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=["MOLA (~463 m/px) cannot resolve boxwork walls or EVA traverse slopes"],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                required_calibration_state="pds3_label_scaling_and_areoid_datum_verified",
                required_product_characteristics=["Local stereo DTM PDS3 .LBL+.IMG with valid Horn 3x3 derivatives"],
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="HiRISE PDS5 DTM grid posting (~1.01 m/px) Nyquist policy",
                threshold_rationale=(
                    "Selected as a configurable product-selection preference (not an intrinsic physical law) so "
                    "topographic ridges broader than ~2-3 m remain resolved; adjustable per study feature width."
                ),
                user_configurable_threshold=True,
                justification="Resolves differential ridge relief and slope constraints along boxwork corridors.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_morph_subm",
                label="Calibrated High-Resolution Outcrop & Fracture Optical Context",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["ridge_polygonal_network", "fracture_width_texture"],
                allowed_instrument_ids=["HIRISE", "MASTCAM", "MAHLI"],
                prohibited_substitutions=[
                    "Optical tone/color CANNOT confirm mineral species without spectroscopy/XRD",
                    "Streaming WMTS basemap tiles do NOT satisfy quantitative radiometric/spatial product verification",
                ],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_radiance_and_map_projection_verified_in_label",
                required_product_characteristics=["Verified local PDS RDR/ORTHO JP2+LBL or calibrated Mastcam/MAHLI RDR"],
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="Replaced ungrounded 0.5 m fixed threshold; actual resolution read from product MAP_SCALE",
                threshold_rationale=(
                    "No arbitrary fixed 0.5 m cutoff imposed because verified HiRISE ORTHO products span ~0.25-1.01 m/px; "
                    "eligibility evaluates actual product MAP_SCALE rather than assuming 0.5 m."
                ),
                user_configurable_threshold=True,
                justification="Maps intersection geometry between polygonal ridges and surrounding troughs without visual-to-mineral overclaiming.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_elem_chem",
                label="In-Situ Ridge vs Host Mudstone Elemental Composition",
                measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
                required_observables=["SiO2", "CaO", "SO3", "FeOT", "MgO"],
                allowed_instrument_ids=["CHEMCAM_LIBS", "APXS"],
                prohibited_substitutions=["Elemental chemistry alone cannot substitute for CheMin XRD crystal phases"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_oxide_wt_percent_with_pds_schema_verified",
                required_product_characteristics=["ChemCam MOC PDS3 or APXS PDS4 XML-verified CSV mapped to Gale IAU2000 coordinates"],
                threshold_rule_classification=ThresholdRuleClassification.INSTRUMENT_LIMITATION,
                threshold_source_reference="ChemCam LIBS (~0.5 mm) / APXS (~17 mm) spot apertures",
                threshold_rationale=(
                    "Removed ungrounded 0.05 m requirement; spot size reflects instrument beam/sensor geometry and point location verification."
                ),
                user_configurable_threshold=False,
                justification="Quantifies whether cementation vs host rock differs in CaO, SO3, MgO, SiO2, or FeOT.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_mineral_xrd",
                label="Crystalline Mineral & Hydrated Salt Verification (XRD / SWIR)",
                measurement_class=MeasurementClass.MINERALOGY_XRD,
                required_observables=["calcium_sulfate_phases", "phyllosilicate_peaks", "iron_oxides"],
                allowed_instrument_ids=["CHEMIN_XRD", "CRISM"],
                prohibited_substitutions=["HIRISE visual brightness or USGS 1:20M map units"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="rietveld_weight_percent_or_atm_corrected_swir_cube_verified",
                required_product_characteristics=["CHEMIN RDR5 + CHEMIN_MIN.FMT or validated local CRISM TRDR/MTRDR cube"],
                threshold_rule_classification=ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
                threshold_source_reference="Modal mineralogy (XRD) or diagnostic vibrational bands (SWIR) required for mineral phase ID",
                threshold_rationale="Scientific necessity: neither optical RGB nor bulk oxide wt% can uniquely separate mineral polymorphs.",
                user_configurable_threshold=False,
                justification="Distinguishes crystalline gypsum/bassanite/anhydrite/smectite from amorphous phases.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_volatiles",
                label="Volatile Water / SO2 Release & Isotopic Constraints",
                measurement_class=MeasurementClass.VOLATILE_ORGANIC_ISOTOPE,
                required_observables=["H2O_evolved", "SO2_evolved", "CO2_evolved"],
                allowed_instrument_ids=["SAM_EGA_GCMS"],
                prohibited_substitutions=["Cannot infer volatile hydration state solely from remote albedo"],
                essential=False,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_qms_ega_blank_corrected_table",
                required_product_characteristics=["Verified local SAM EGA/GCMS PDS product"],
                threshold_rule_classification=ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
                threshold_source_reference="Direct thermal volatile evolution requirement",
                threshold_rationale="Evaluates thermal decomposition host phases when verified SAM drill records exist.",
                user_configurable_threshold=False,
                justification="Evaluates late-stage fluid temperature and volatile host chemistry.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_sulfate_clay_transition",
        title="Mineralogical & Geochemical Transition Across the Mount Sharp Clay-to-Sulfate Boundary",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Investigation Hypothesis H1 (Stratigraphic Aridification Gradient): Transition from clay-bearing mudstones "
            "toward overlying sulfate-enriched strata may reflect changing paleolake/groundwater chemistry."
        ),
        competing_hypotheses=[
            "H1: Depositional brine evolution progressively shifted precipitation from phyllosilicates to hydrated sulfates upsection.",
            "H2: Post-depositional diagenetic sulfur-rich fluids overprinted primary clay-bearing sediments.",
        ],
        alternative_explanations=[
            "Apparent regional sulfate increase in orbital pixels may be modulated by dust cover or aeolian sulfate sand drift.",
        ],
        contradicting_evidence_criteria=[
            "Persistent phyllosilicate dominance or unaltered basaltic mineralogy at upper stratigraphic elevations.",
        ],
        unresolved_assumptions=[
            "Local absence of validated CRISM TRDR/MTRDR spectral cubes prevents pixel-continuous mineral boundary verification.",
        ],
        current_evidence_state="UNRESOLVED_REQUIRES_CO_REGISTERED_MULTI_INSTRUMENT_EVIDENCE",
        geological_setting="Glen Torridon to Sulfate-Bearing Unit Transition (Mount Sharp)",
        is_user_defined=False,
        target_phenomena=["SO3", "MgO", "Al2O3", "FeO", "CaO", "stratigraphy"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires stratigraphic elevation ordering (verified HiRISE DTM), verified orbital/in-situ mineral indicators "
            "(CRISM TRDR + CheMin XRD), and paired bulk MgO/SO3 vs Al2O3 elemental gradients."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_trans_topo",
                label="Stratigraphic Elevation & Dip Continuity (HiRISE DTM)",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=["MOLA 463 m pixel loses thin Marker Band horizons"],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                required_calibration_state="pds3_label_scaling_and_areoid_datum_verified",
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="HiRISE stereo DTM (~1.01 m/px) stratigraphic ordering preference",
                threshold_rationale="Ensures stratigraphic bed elevations are compared above MOLA macro-averaging scales.",
                user_configurable_threshold=True,
                justification="Orders geochemical targets along true stratigraphic elevation.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_trans_orbital_spec",
                label="Orbital SWIR Phyllosilicate-to-Sulfate Spectral Continuity",
                measurement_class=MeasurementClass.MINERALOGY_SPECTRAL,
                required_observables=["1.9_um_H2O", "2.3_um_MgFeOH", "2.4_um_sulfate"],
                allowed_instrument_ids=["CRISM"],
                prohibited_substitutions=["True-color Mastcam/HiRISE cannot substitute for SWIR bands"],
                essential=True,
                minimum_spatial_resolution_m=20.0,
                required_calibration_state="calibrated_atm_corrected_crism_trdr_or_mtrdr",
                required_product_characteristics=["Verified local CRISM FRT/HRL cube with DDR spatial projection"],
                threshold_rule_classification=ThresholdRuleClassification.INSTRUMENT_LIMITATION,
                threshold_source_reference="MRO CRISM FRT nominal IFOV (~18 m/px)",
                threshold_rationale="20.0 m bound reflects CRISM FRT instrument IFOV (~18 m/px), NOT an arbitrarily tight scientific ideal.",
                user_configurable_threshold=False,
                justification="Tracks spatial extent of hydrated clay vs polyhydrated sulfate spectral indicators.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_trans_elem",
                label="In-Situ Sulfate & Major Oxide Stratigraphic Chemistry",
                measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
                required_observables=["SO3", "MgO", "CaO", "Al2O3", "FeO"],
                allowed_instrument_ids=["APXS", "CHEMCAM_LIBS"],
                prohibited_substitutions=["Oxide enrichments cannot confirm crystal mineral species without CheMin XRD"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_oxide_wt_percent_with_pds_schema_verified",
                threshold_rule_classification=ThresholdRuleClassification.INSTRUMENT_LIMITATION,
                threshold_source_reference="APXS/ChemCam contact spot measurements",
                threshold_rationale="Requires verified APXS PDS4 or ChemCam MOC records co-registered to elevation.",
                user_configurable_threshold=False,
                justification="Measures chemical index of alteration and elemental S/Mg trends.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_diagenetic_veins_and_nodules",
        title="Post-Depositional Fluid Chemistry in Light-Toned Diagenetic Veins & Raised Nodules",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Investigation Hypothesis H1 (Late Fracture Fluid Emplacement): Cross-cutting light-toned veins and "
            "raised nodules may record one or more post-depositional fluid events chemically distinct from host mudstone."
        ),
        competing_hypotheses=[
            "H1: Multiple fluid pulses precipitated Ca-sulfate fracture fills and silica/Mn-oxide diagenetic halos.",
            "H2: Apparent tonal brightness differences represent differential surface dust cleaning or differential grain cementation.",
        ],
        alternative_explanations=[
            "Bright fracture fills in HiRISE/Mastcam imagery cannot confirm CaSO4 without paired elemental/XRD confirmation.",
        ],
        contradicting_evidence_criteria=[
            "Paired vein and host bedrock APXS/ChemCam measurements show indistinguishable CaO/SO3/SiO2/MnO distributions.",
        ],
        unresolved_assumptions=[
            "No local MAHLI/Mastcam RDR frames are verified locally to isolate sub-mm vein vs host laser targeting uncertainty.",
        ],
        current_evidence_state="UNRESOLVED_REQUIRES_CO_REGISTERED_MULTI_INSTRUMENT_EVIDENCE",
        geological_setting="Fractured Mudstone & Sandstone Horizons, Gale Crater",
        is_user_defined=False,
        target_phenomena=["CaO", "SO3", "SiO2", "MnO", "FeO", "vein"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires verified micro-scale imaging context (MAHLI/Mastcam RDR) paired with target-resolved LIBS/APXS spots."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_vein_micro_img",
                label="Sub-mm Vein Habit & Cross-Cutting Relationship",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["vein_cross_cutting_order", "halo_width"],
                allowed_instrument_ids=["MAHLI", "MASTCAM", "HIRISE"],
                prohibited_substitutions=["Visual brightness alone cannot identify gypsum/anhydrite/silica mineralogy"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_optical_rdr_with_pointing_metadata",
                threshold_rule_classification=ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
                threshold_source_reference="Vein morphology context requirement",
                threshold_rationale="Requires verified optical frame metadata; HiRISE alone (~1 m) cannot resolve mm veins.",
                user_configurable_threshold=False,
                justification="Establishes relative fracture timing before geochemical interrogation.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_vein_chem",
                label="Paired Vein & Host Bedrock Elemental Composition",
                measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
                required_observables=["CaO", "SO3", "SiO2", "MnO"],
                allowed_instrument_ids=["CHEMCAM_LIBS", "APXS"],
                prohibited_substitutions=["White tone visually != CaSO4 without Ca+S elemental match"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_oxide_wt_percent_with_pds_schema_verified",
                threshold_rule_classification=ThresholdRuleClassification.INSTRUMENT_LIMITATION,
                threshold_source_reference="ChemCam LIBS (~0.5 mm) / APXS (~17 mm)",
                threshold_rationale="ChemCam spot size better isolates narrow veins than APXS FOV; spatial targeting offsets matter.",
                user_configurable_threshold=False,
                justification="Distinguishes Ca-S enrichment from silica- or Mn-enriched alteration halos.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_vein_topo",
                label="Local Meter-Scale Access Terrain Slope & Roughness",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=["MOLA (~463 m) cannot verify local bench slope"],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                required_calibration_state="pds3_label_scaling_and_areoid_datum_verified",
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="HiRISE DTM traverse slope preference",
                threshold_rationale="Product selection filter ensuring meter-scale DTM slope context along bench approaches.",
                user_configurable_threshold=True,
                justification="Confirms local terrain slope context along fracture benches.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_traverse_thermal_induration",
        title="Bedrock Induration, Dust Mantling & Regolith Cohesion Along Mount Sharp Ridge Corridors",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Investigation Hypothesis H1 (Thermal Inertia vs Induration Proxy): Orbital THEMIS nighttime thermal "
            "inertia anomalies may indicate exposed indurated bedrock vs loose dust/sand mantling at ~100 m scale."
        ),
        competing_hypotheses=[
            "H1: Elevated thermal inertia reflects cohesive bedrock ridges along boxwork terrain.",
            "H2: Elevated thermal inertia may also be produced by lag-pebble armor, coarse talus slopes, or steep thermal illumination effects rather than contiguous traversable bedrock.",
        ],
        alternative_explanations=[
            "High thermal inertia is a physical heat-capacity/grain-size proxy, NOT a direct measurement of mineral composition or boot/wheel bearing strength.",
        ],
        contradicting_evidence_criteria=[
            "HiRISE imagery shows mobile dark sand ripples/dunes covering >50% of a high-TI 100 m THEMIS pixel.",
        ],
        unresolved_assumptions=[
            "No calibrated local THEMIS IR brightness temperature or derived thermal inertia raster is currently ingested locally.",
        ],
        current_evidence_state="UNRESOLVED_NO_VALIDATED_THEMIS_RASTER_AVAILABLE",
        geological_setting="Mount Sharp Foothills & Boxwork Troughs",
        is_user_defined=False,
        target_phenomena=["thermal_inertia", "bedrock", "sand_bedforms", "boxwork"],
        preferred_stop_count=2,
        minimum_evidence_note=(
            "Requires verified THEMIS IR/TI raster (~100 m) cross-checked against calibrated HiRISE imagery and 1 m DTM slope/TRI."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_indur_themis",
                label="Regional Thermal Inertia & Induration Contrast (THEMIS)",
                measurement_class=MeasurementClass.THERMAL_INERTIA_COMPOSITION,
                required_observables=["thermal_inertia_proxy", "brightness_temp_contrast"],
                allowed_instrument_ids=["THEMIS"],
                prohibited_substitutions=[
                    "THEMIS 100 m pixel CANNOT guarantee local soil bearing capacity",
                    "Thermal response CANNOT establish chemical composition or mineral identity",
                ],
                essential=True,
                minimum_spatial_resolution_m=150.0,
                required_calibration_state="calibrated_nighttime_ir_radiance_and_ti_model_verified",
                required_product_characteristics=["Local calibrated THEMIS IRRDR/BTR/TI GeoTIFF with solar time metadata"],
                threshold_rule_classification=ThresholdRuleClassification.INSTRUMENT_LIMITATION,
                threshold_source_reference="Odyssey THEMIS IR detector IFOV (~100 m/px)",
                threshold_rationale="150.0 m upper bound reflects THEMIS ~100 m IR pixel scale; cannot validate sub-pixel ground safety.",
                user_configurable_threshold=False,
                justification="Identifies regional thermal contrast when verified THEMIS raster is acquired.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_indur_hirise",
                label="Meter-Scale Ripple/Bedform & Scarp Optical Context (HiRISE)",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["sand_bedform_density", "exposed_bedrock_fractures"],
                allowed_instrument_ids=["HIRISE", "MASTCAM", "MAHLI"],
                prohibited_substitutions=["Visual texture cannot measure regolith cohesion strength quantitatively"],
                essential=True,
                minimum_spatial_resolution_m=None,
                required_calibration_state="calibrated_radiance_and_map_projection_verified_in_label",
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="Actual pixel scale read from product .LBL",
                threshold_rationale="Bridges coarse thermal pixels to sub-meter bedform visibility where RDR/ORTHO labels exist.",
                user_configurable_threshold=True,
                justification="Bridges 100 m thermal pixels to meter-scale bedform hazard indicators.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_indur_dtm",
                label="Local Topographic Slope & Roughness Corridor Geometry",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg", "roughness_tri_m"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=["MOLA (~463 m) is invalid for local corridor slopes"],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                required_calibration_state="pds3_label_scaling_and_areoid_datum_verified",
                threshold_rule_classification=ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
                threshold_source_reference="HiRISE stereo DTM (~1.01 m/px) selection preference",
                threshold_rationale="Product filter ensuring meter-scale DTM slope & TRI uncertainty analysis.",
                user_configurable_threshold=True,
                justification="Quantifies local slope & TRI uncertainty along candidate exploration ridges.",
            ),
        ],
    ),
]


def _measurement_class_default_spec(
    idx: int, mc: MeasurementClass, qid: str
) -> MeasurementRequirementSpec:
    defaults = {
        MeasurementClass.TOPOGRAPHY_ELEVATION: (
            "Local Elevation & Slope Geometry (USER_ASSUMED <=2 m DTM)",
            ["elevation_m", "slope_deg"],
            ["HIRISE_DTM"],
            ["MOLA (~463 m) is restricted to regional context"],
            2.0,
            ThresholdRuleClassification.USER_ASSUMED,
        ),
        MeasurementClass.MORPHOLOGY_HIGHRES: (
            "Calibrated Morphological Imaging",
            ["outcrop_geometry", "fracture_network"],
            ["HIRISE", "MASTCAM", "MAHLI"],
            ["Visual appearance cannot confirm mineral composition"],
            None,
            ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE,
        ),
        MeasurementClass.ELEMENTAL_CHEMISTRY: (
            "In-Situ Elemental Oxide Chemistry",
            ["SiO2", "FeO", "CaO", "SO3"],
            ["CHEMCAM_LIBS", "APXS"],
            ["Elemental enrichment does not prove crystalline XRD phase"],
            None,
            ThresholdRuleClassification.INSTRUMENT_LIMITATION,
        ),
        MeasurementClass.MINERALOGY_XRD: (
            "Crystalline Mineral Phase Identification",
            ["xrd_mineral_phases"],
            ["CHEMIN_XRD"],
            ["Elemental ratios alone cannot substitute for XRD"],
            None,
            ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
        ),
        MeasurementClass.MINERALOGY_SPECTRAL: (
            "VNIR/SWIR Hydrated Mineral Spectroscopy",
            ["swir_hydration_bands"],
            ["CRISM"],
            ["True-color imaging cannot substitute for SWIR spectroscopy"],
            None,
            ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
        ),
        MeasurementClass.VOLATILE_ORGANIC_ISOTOPE: (
            "Volatile Gas Release & Isotope Analysis",
            ["H2O_evolved", "SO2_evolved"],
            ["SAM_EGA_GCMS"],
            [],
            None,
            ThresholdRuleClassification.SCIENTIFIC_REQUIREMENT,
        ),
        MeasurementClass.THERMAL_INERTIA_COMPOSITION: (
            "Thermophysical Induration Context",
            ["thermal_inertia_proxy"],
            ["THEMIS"],
            ["100 m thermal pixels cannot prove chemical composition or meter-scale footing"],
            None,
            ThresholdRuleClassification.INSTRUMENT_LIMITATION,
        ),
        MeasurementClass.HYDRATED_NEUTRON_SUBSURFACE: (
            "Regional Crustal Hydration Context",
            ["H2O_eq_neutron"],
            ["ODYSSEY_GRS_NS"],
            ["300 km footprint cannot characterize individual outcrops"],
            None,
            ThresholdRuleClassification.INSTRUMENT_LIMITATION,
        ),
        MeasurementClass.METEOROLOGY_ENVIRONMENT: (
            "Ambient Barometric & Thermal Context",
            ["pressure_pa", "air_temp_k"],
            ["REMS"],
            [],
            None,
            ThresholdRuleClassification.INSTRUMENT_LIMITATION,
        ),
    }
    label, obs, insts, prohib, min_res, rule_cls = defaults[mc]
    return MeasurementRequirementSpec(
        requirement_id=f"{qid}_req_{idx}_{mc.value}",
        label=label,
        measurement_class=mc,
        required_observables=obs,
        allowed_instrument_ids=insts,
        prohibited_substitutions=prohib,
        essential=True,
        minimum_spatial_resolution_m=min_res,
        threshold_rule_classification=rule_cls,
        threshold_rationale=f"Default specification ({rule_cls.value}) for user-requested {mc.value}.",
        user_configurable_threshold=True,
        user_assumed=(rule_cls == ThresholdRuleClassification.USER_ASSUMED),
        justification=f"User-specified measurement requirement ({mc.value}) for custom investigation question.",
    )


class ScienceQuestionRepository:
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._builtin: Dict[str, ScienceQuestionDefinition] = {
            q.question_id: q for q in _DEFAULT_QUESTIONS
        }

    def _load_custom(self) -> Dict[str, ScienceQuestionDefinition]:
        if not self.storage_path.exists():
            return {}
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            out: Dict[str, ScienceQuestionDefinition] = {}
            for item in raw:
                q = ScienceQuestionDefinition.model_validate(item)
                out[q.question_id] = q
            return out
        except Exception:
            return {}

    def _save_custom(self, custom: Dict[str, ScienceQuestionDefinition]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".questions_", suffix=".tmp", dir=str(self.storage_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as h:
                h.write(
                    json.dumps(
                        [q.model_dump(mode="json") for q in custom.values()],
                        indent=2,
                    )
                )
                h.flush()
                os.fsync(h.fileno())
            os.replace(tmp_name, self.storage_path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def list_questions(self) -> List[ScienceQuestionDefinition]:
        custom = self._load_custom()
        return [*self._builtin.values(), *custom.values()]

    def get_question(self, question_id: str) -> Optional[ScienceQuestionDefinition]:
        if question_id in self._builtin:
            return self._builtin[question_id]
        return self._load_custom().get(question_id)

    def create_custom_question(
        self, req: CustomScienceQuestionCreateRequest
    ) -> ScienceQuestionDefinition:
        slug_seed = f"{req.title}|{req.hypothesis}|{req.study_region}"
        qid = "user_q_" + hashlib.sha256(slug_seed.encode("utf-8")).hexdigest()[:10]
        specs = [
            _measurement_class_default_spec(i, mc, qid)
            for i, mc in enumerate(dict.fromkeys(req.required_measurement_classes))
        ]
        q = ScienceQuestionDefinition(
            question_id=qid,
            title=req.title.strip(),
            study_region=req.study_region.strip(),
            hypothesis=req.hypothesis.strip(),
            competing_hypotheses=[h.strip() for h in req.competing_hypotheses if h.strip()],
            alternative_explanations=[a.strip() for a in req.alternative_explanations if a.strip()],
            unresolved_assumptions=[u.strip() for u in req.unresolved_assumptions if u.strip()],
            current_evidence_state="UNRESOLVED_USER_DEFINED_INVESTIGATION",
            geological_setting=req.geological_setting.strip(),
            is_user_defined=True,
            target_phenomena=list(dict.fromkeys([t.strip() for t in req.target_phenomena if t.strip()])),
            required_measurement_specs=specs,
            preferred_stop_count=req.preferred_stop_count,
            minimum_evidence_note=(
                "USER_DEFINED investigation question: requirements evaluated strictly against verified "
                "MARSCOPE holdings; unacquired orbital spectroscopy or missing local drill data remain flagged as gaps."
            ),
        )
        custom = self._load_custom()
        custom[qid] = q
        self._save_custom(custom)
        return q

    def delete_custom_question(self, question_id: str) -> bool:
        if question_id in self._builtin:
            return False
        custom = self._load_custom()
        if question_id not in custom:
            return False
        del custom[question_id]
        self._save_custom(custom)
        return True
