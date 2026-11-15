"""
MARSCOPE Stop-Level Field Observation Protocol Generator
Prompt 17: Produces concrete instrument sequences, calibration checks, context
imaging requirements, and prohibited-shortcut guards per investigation stop.
"""

from __future__ import annotations

from typing import List

from app.schemas.target import InvestigationTargetEvidenceState
from app.science.investigation.schemas import (
    CandidateTargetEvaluation,
    ObservationActionPlan,
    RequirementEvaluationRecord,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
)


def build_observation_action_plan(
    *,
    stop_id: str,
    target: CandidateTargetEvaluation,
    question: ScienceQuestionDefinition,
    requirements: List[RequirementEvaluationRecord],
    dwell_s: float,
) -> ObservationActionPlan:
    recommended: List[str] = []
    measurements: List[str] = []
    context_checks: List[str] = [
        "Stereo context panorama across ridge crest / host bedrock contact prior to contact arm deployment",
        "Close-up scale reference imaging (hand lens >=0.1 mm/px) documenting grain size, cementation, and fracture geometry",
    ]
    cal_checks: List[str] = [
        "Verify pre-shot LIBS/spectrometer calibration target response before quantitative oxide attribution",
        "Record exact waypoint position in IAU2000:49900 (sol/UTC timestamp + local horizon bearing)",
    ]
    uncertainty_notes: List[str] = list(target.unknowns_and_gaps[:3])
    prohibited_notes: List[str] = [
        "NEVER infer Ca-sulfate, phyllosilicate, or silica mineralogy from visual outcrop brightness/color alone.",
        "Record raw measured observables separately from geological interpretation.",
    ]

    # Always recommend closing unresolved requirement gaps first
    missing_classes = {
        r.measurement_class.value
        for r in requirements
        if r.fulfillment_state
        in {
            RequirementFulfillmentState.MISSING_REQUIRED_DATA,
            RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE,
            RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED,
        }
    }

    if target.evidence_state in {
        InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED,
        InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED,
        InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED,
        InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY,
    }:
        recommended.extend(["MASTCAM", "MAHLI", "CHEMCAM_LIBS", "APXS"])
        measurements.extend(
            [
                "First-pass in-situ elemental screening (SiO2, FeO, CaO, SO3, MgO) on both ridge wall and adjacent host mudstone",
                "High-resolution micro-texture check to distinguish cemented fracture fill from wind-sculpted eolian sand/bedrock",
            ]
        )
        prohibited_notes.append(
            "Target currently lacks verified local geochemical confirmation; sampling/drilling prohibited until initial screening passes."
        )
    elif target.evidence_state == InvestigationTargetEvidenceState.CONFLICTING_EVIDENCE:
        recommended.extend(["MAHLI", "CHEMCAM_LIBS", "APXS", "CHEMIN_XRD"])
        measurements.extend(
            [
                "Replicate paired spot measurements (minimum 3 points across vein vs host matrix) to resolve archive discrepancy",
                "Document micro-scale heterogeneity/coatings responsible for divergent archive readings",
            ]
        )
        cal_checks.append("Flag any residual disagreement with archive before updating geological interpretation")
    else:
        recommended.extend(["MASTCAM", "MAHLI", "APXS"])
        if "mineralogy_xrd" in missing_classes or "mineralogy_spectral" in missing_classes:
            recommended.append("CHEMIN_XRD")
            measurements.append(
                "Acquire definitive crystalline mineral identification (smectite vs Ca-sulfate vs amorphous silica) where CheMin absent"
            )
        if "volatile_organic_isotope" in missing_classes:
            recommended.append("SAM_EGA_GCMS")
            measurements.append("Measure thermally evolved H2O/SO2 release profile to constrain hydration phase stability")
        measurements.append(
            f"Paired geochemical transect tied to '{question.title}' ({', '.join(question.target_phenomena[:4])})"
        )

    dedup_insts = list(dict.fromkeys(recommended))

    return ObservationActionPlan(
        stop_id=stop_id,
        target_id=target.target_id,
        target_name=target.name,
        recommended_instruments=dedup_insts,
        measurements_to_collect=list(dict.fromkeys(measurements)),
        context_imaging_checks=context_checks,
        calibration_or_reference_checks=cal_checks,
        expected_dwell_s=float(dwell_s),
        estimated_data_volume_mb=None,
        data_volume_status="UNAVAILABLE_NO_TELEMETRY_BITRATE_CONFIGURED",
        explicit_uncertainty_notes=uncertainty_notes,
        prohibited_shortcut_notes=list(dict.fromkeys(prohibited_notes)),
    )
