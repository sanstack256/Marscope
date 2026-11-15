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
)


_DEFAULT_QUESTIONS: List[ScienceQuestionDefinition] = [
    ScienceQuestionDefinition(
        question_id="gale_boxwork_origin",
        title="Origin & Mineralogy of the 2025 Mount Sharp Boxwork Formations",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Polygonal boxwork ridges preserved across Mount Sharp's sulfate-bearing terrain formed when "
            "mineralizing groundwater precipitated cement (Ca/Mg-sulfates, silica, or Fe-rich precipitates) along "
            "tectonic/desiccation fractures in mudstone/sandstone, increasing differential induration against wind erosion."
        ),
        geological_setting="Mount Sharp Gediz Vallis / Sulfate-Bearing & Boxwork Ridge Facies (Gale Crater)",
        is_user_defined=False,
        target_phenomena=["boxwork", "SO3", "CaO", "FeO", "SiO2", "MgO", "gypsum", "smectite", "jarosite"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires co-registered 0.25 m HiRISE optical geometry, 1.0 m HiRISE DTM ridge relief, "
            "in-situ elemental chemistry across wall vs host rock (ChemCam/APXS), and crystalline/volatile "
            "verification (CheMin XRD / SAM / validated CRISM) before assigning mineral genesis."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_topo_1m",
                label="Meter-Scale Ridge Relief & Traverse Slope Geometry (<=2 m/px DEM)",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg", "roughness_tri_m"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=["MOLA (~463 m) cannot resolve boxwork walls or EVA slopes"],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                justification="Resolves differential ridge relief and slope constraints along boxwork corridors.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_morph_subm",
                label="Sub-Meter Fracture Planform & Outcrop Optical Context (<=0.5 m/px)",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["ridge_polygonal_network", "fracture_width_texture"],
                allowed_instrument_ids=["HIRISE", "MASTCAM", "MAHLI"],
                prohibited_substitutions=["Optical tone/color CANNOT confirm mineral species without spectroscopy/XRD"],
                essential=True,
                minimum_spatial_resolution_m=0.5,
                justification="Maps intersection geometry between polygonal ridges and surrounding troughs.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_elem_chem",
                label="In-Situ Ridge vs Host Mudstone Elemental Composition",
                measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
                required_observables=["SiO2", "CaO", "SO3", "FeOT", "MgO"],
                allowed_instrument_ids=["CHEMCAM_LIBS", "APXS"],
                prohibited_substitutions=["Elemental chemistry alone cannot substitute for CheMin XRD crystal phases"],
                essential=True,
                minimum_spatial_resolution_m=0.05,
                justification="Quantifies whether cementation is enriched in Ca+S, Mg+S, SiO2, or Fe oxides.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_mineral_xrd",
                label="Crystalline Mineral & Hydrated Salt Verification (XRD / SWIR)",
                measurement_class=MeasurementClass.MINERALOGY_XRD,
                required_observables=["calcium_sulfate_phases", "phyllosilicate_peaks", "iron_oxides"],
                allowed_instrument_ids=["CHEMIN_XRD", "CRISM"],
                prohibited_substitutions=["HIRISE visual brightness or USGS 1:20M map units"],
                essential=True,
                justification="Distinguishes crystalline gypsum/bassanite/anhydrite/smectite from amorphous gels.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_boxwork_volatiles",
                label="Volatile Water / SO2 Release & Isotopic Constraints",
                measurement_class=MeasurementClass.VOLATILE_ORGANIC_ISOTOPE,
                required_observables=["H2O_evolved", "SO2_evolved", "CO2_evolved"],
                allowed_instrument_ids=["SAM_EGA_GCMS"],
                prohibited_substitutions=["Cannot infer volatile hydration state solely from remote albedo"],
                essential=False,
                justification="Evaluates late-stage fluid temperature and hydration state.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_sulfate_clay_transition",
        title="Mineralogical & Geochemical Transition Across the Mount Sharp Clay-to-Sulfate Boundary",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Vertical progression from smectite-rich Murray/Carolyn Shoemaker mudstones into Mirador/Sulfate-bearing strata "
            "records aridification of ancient Gale paleolake brines with episodic groundwater recharge."
        ),
        geological_setting="Glen Torridon to Sulfate-Bearing Unit Transition (Mount Sharp)",
        is_user_defined=False,
        target_phenomena=["smectite", "SO3", "MgO", "gypsum", "FeO", "hematite", "jarosite"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires stratigraphic elevation ordering (HiRISE DTM), orbital/local mineral indicators (CRISM & CheMin), "
            "and paired bulk MgO/SO3 vs Al2O3 elemental gradients."
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
                justification="Tracks spatial extent of hydrated clay vs polyhydrated sulfate units.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_trans_elem",
                label="In-Situ Sulfate & Major Oxide Stratigraphic Chemistry",
                measurement_class=MeasurementClass.ELEMENTAL_CHEMISTRY,
                required_observables=["SO3", "MgO", "CaO", "Al2O3", "FeO"],
                allowed_instrument_ids=["APXS", "CHEMCAM_LIBS"],
                prohibited_substitutions=[],
                essential=True,
                justification="Measures chemical index of alteration and Mg-sulfate accumulation.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_diagenetic_veins_and_nodules",
        title="Post-Depositional Fluid Chemistry in Light-Toned Diagenetic Veins & Raised Nodules",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Cross-cutting light-toned veins and diagenetic halos formed during multiple fracture-fill events distinct from "
            "primary lacustrine host sedimentation."
        ),
        geological_setting="Fractured Mudstone & Sandstone Horizons, Gale Crater",
        is_user_defined=False,
        target_phenomena=["CaO", "SO3", "SiO2", "MnO", "gypsum", "vein", "FeO"],
        preferred_stop_count=3,
        minimum_evidence_note=(
            "Requires micro-scale texture (MAHLI/Mastcam) paired with paired vein-vs-host LIBS/APXS spots."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_vein_micro_img",
                label="Sub-mm Vein Habit & Cross-Cutting Relationship",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["vein_cross_cutting_order", "halo_width"],
                allowed_instrument_ids=["MAHLI", "MASTCAM", "HIRISE"],
                prohibited_substitutions=[],
                essential=True,
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
                justification="Distinguishes Ca-sulfate fracture fills from silica-enriched alteration halos.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_vein_topo",
                label="Local Meter-Scale Access Terrain Slope & Roughness",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=[],
                essential=True,
                minimum_spatial_resolution_m=2.0,
                justification="Confirms safe EVA approach along fracture benches.",
            ),
        ],
    ),
    ScienceQuestionDefinition(
        question_id="gale_traverse_thermal_induration",
        title="Bedrock Induration, Dust Mantling & Regolith Cohesion Along Mount Sharp Ridge Corridors",
        study_region="Gale Crater / Mount Sharp",
        hypothesis=(
            "Orbital THEMIS high thermal inertia tracks indurated bedrock benches that remain masked below sub-pixel resolution "
            "on steep scarps without HiRISE/MAHLI validation."
        ),
        geological_setting="Mount Sharp Foothills & Boxwork Troughs",
        is_user_defined=False,
        target_phenomena=["SiO2", "FeO", "MgO", "bedrock", "boxwork"],
        preferred_stop_count=2,
        minimum_evidence_note=(
            "Cross-checks 100 m THEMIS thermal induration context against 0.25 m HiRISE bedforms and 1 m DTM slope gradients."
        ),
        required_measurement_specs=[
            MeasurementRequirementSpec(
                requirement_id="req_indur_themis",
                label="Regional Thermal Inertia & Induration Contrast (THEMIS)",
                measurement_class=MeasurementClass.THERMAL_INERTIA_COMPOSITION,
                required_observables=["thermal_inertia_proxy", "brightness_temp_contrast"],
                allowed_instrument_ids=["THEMIS"],
                prohibited_substitutions=["THEMIS 100 m pixel CANNOT guarantee local soil bearing capacity"],
                essential=True,
                minimum_spatial_resolution_m=150.0,
                justification="Identifies regional indurated vs dust-draped sectors.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_indur_hirise",
                label="Meter-Scale Ripple/Bedform & Scarp Optical Context (HiRISE)",
                measurement_class=MeasurementClass.MORPHOLOGY_HIGHRES,
                required_observables=["sand_bedform_density", "exposed_bedrock_fractures"],
                allowed_instrument_ids=["HIRISE", "MASTCAM", "MAHLI"],
                prohibited_substitutions=[],
                essential=True,
                justification="Bridges 100 m thermal pixels to rover/astronaut foot-scale surface character.",
            ),
            MeasurementRequirementSpec(
                requirement_id="req_indur_dtm",
                label="Local Topographic Slope & Roughness Corridor Geometry",
                measurement_class=MeasurementClass.TOPOGRAPHY_ELEVATION,
                required_observables=["elevation_m", "slope_deg", "roughness_tri_m"],
                allowed_instrument_ids=["HIRISE_DTM"],
                prohibited_substitutions=[],
                essential=True,
                minimum_spatial_resolution_m=2.0,
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
            "Local Elevation & Slope Geometry (<=2 m DTM)",
            ["elevation_m", "slope_deg"],
            ["HIRISE_DTM"],
            ["MOLA (~463 m) is restricted to regional context"],
        ),
        MeasurementClass.MORPHOLOGY_HIGHRES: (
            "Sub-Meter Morphological Imaging",
            ["outcrop_geometry", "fracture_network"],
            ["HIRISE", "MASTCAM", "MAHLI"],
            ["Visual appearance cannot confirm mineral composition"],
        ),
        MeasurementClass.ELEMENTAL_CHEMISTRY: (
            "In-Situ Elemental Oxide Chemistry",
            ["SiO2", "FeO", "CaO", "SO3"],
            ["CHEMCAM_LIBS", "APXS"],
            ["Elemental enrichment does not prove crystalline XRD phase"],
        ),
        MeasurementClass.MINERALOGY_XRD: (
            "Crystalline Mineral Phase Identification",
            ["xrd_mineral_phases"],
            ["CHEMIN_XRD"],
            ["Elemental ratios alone cannot substitute for XRD"],
        ),
        MeasurementClass.MINERALOGY_SPECTRAL: (
            "VNIR/SWIR Hydrated Mineral Spectroscopy",
            ["swir_hydration_bands"],
            ["CRISM"],
            ["True-color imaging cannot substitute for SWIR spectroscopy"],
        ),
        MeasurementClass.VOLATILE_ORGANIC_ISOTOPE: (
            "Volatile Gas Release & Isotope Analysis",
            ["H2O_evolved", "SO2_evolved"],
            ["SAM_EGA_GCMS"],
            [],
        ),
        MeasurementClass.THERMAL_INERTIA_COMPOSITION: (
            "Thermophysical Induration Context",
            ["thermal_inertia_proxy"],
            ["THEMIS"],
            ["100 m thermal pixels cannot validate meter-scale footing"],
        ),
        MeasurementClass.HYDRATED_NEUTRON_SUBSURFACE: (
            "Regional Crustal Hydration Context",
            ["H2O_eq_neutron"],
            ["ODYSSEY_GRS_NS"],
            ["300 km footprint cannot characterize individual outcrops"],
        ),
        MeasurementClass.METEOROLOGY_ENVIRONMENT: (
            "Ambient Barometric & Thermal Context",
            ["pressure_pa", "air_temp_k"],
            ["REMS"],
            [],
        ),
    }
    label, obs, insts, prohib = defaults[mc]
    return MeasurementRequirementSpec(
        requirement_id=f"{qid}_req_{idx}_{mc.value}",
        label=label,
        measurement_class=mc,
        required_observables=obs,
        allowed_instrument_ids=insts,
        prohibited_substitutions=prohib,
        essential=True,
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
            geological_setting=req.geological_setting.strip(),
            is_user_defined=True,
            target_phenomena=list(dict.fromkeys([t.strip() for t in req.target_phenomena if t.strip()])) or ["FeO", "SiO2"],
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
