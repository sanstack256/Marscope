"""
MARSCOPE Stop-Level Field Observation Protocol Generator
Prompt 17: Produces concrete instrument sequences, calibration checks, context
imaging requirements, and prohibited-shortcut guards per investigation stop.
"""

from __future__ import annotations

from typing import List

from app.schemas.target import InvestigationTargetEvidenceState
from app.science.investigation.measurement_registry import get_instrument
from app.science.investigation.schemas import (
    CandidateTargetEvaluation,
    InstrumentPlatformKind,
    ObservationActionPlan,
    ObservationLifecycleState,
    RequirementEvaluationRecord,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
    SpatialRegistrationState,
)


def _assess_platform_compatibility(instruments: List[str]) -> tuple[str, bool, str]:
    rover_insts = []
    orbital_insts = []
    eva_insts = []
    for iid in instruments:
        rec = get_instrument(iid)
        if rec is None:
            continue
        if rec.platform_kind == InstrumentPlatformKind.SURFACE_IN_SITU:
            host_u = (rec.mission_host or "").upper()
            if any(tok in host_u for tok in ("MSL", "CURIOSITY", "PERSEVERANCE", "M2020", "ROVER")):
                rover_insts.append(f"{rec.instrument_id} ({rec.mission_host})")
            else:
                eva_insts.append(rec.instrument_id)
        elif rec.platform_kind == InstrumentPlatformKind.ORBITAL:
            orbital_insts.append(f"{rec.instrument_id} ({rec.mission_host})")
        else:
            eva_insts.append(rec.instrument_id)

    if rover_insts and not eva_insts:
        return (
            "rover_surface_payload_not_human_eva_handheld",
            True,
            (
                f"Platform compatibility disclosure: {', '.join(rover_insts)} are MSL rover-mounted payloads, "
                "NOT astronaut EVA handheld tools. Action plan requires rover-proximal measurements or a validated "
                "crew-operated portable equivalent rather than assuming astronauts carry rover instrumentation."
            ),
        )
    if orbital_insts and not eva_insts and not rover_insts:
        return (
            "orbital_asset_only",
            True,
            f"Platform compatibility disclosure: {', '.join(orbital_insts)} are orbital remote-sensing assets only.",
        )
    return ("human_eva_and_multi_asset_compatible", False, "Compatible with configured campaign platform rules.")


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
    plat_compat, plat_mismatch, plat_note = _assess_platform_compatibility(dedup_insts)
    if plat_mismatch:
        uncertainty_notes.append(plat_note)

    if (target.eligibility_decision or "").upper().startswith("REJECTED") or (
        target.eligibility_decision or ""
    ).upper() == "INELIGIBLE":
        obs_state = ObservationLifecycleState.MEASUREMENT_NOT_SUPPORTED
    elif (
        target.spatial_registration_state
        in {
            SpatialRegistrationState.REGISTERED_VALIDATED,
            SpatialRegistrationState.REGISTERED_WITH_LIMITATIONS,
            SpatialRegistrationState.PARTIALLY_OVERLAPPING,
            SpatialRegistrationState.REGISTRATION_UNVERIFIED,
        }
        and target.covering_datasets
        and dedup_insts
    ):
        obs_state = ObservationLifecycleState.OBSERVATION_PLANNED
    elif dedup_insts:
        obs_state = ObservationLifecycleState.CAPABILITY_DOCUMENTED
    else:
        obs_state = ObservationLifecycleState.MEASUREMENT_NOT_SUPPORTED

    return ObservationActionPlan(
        stop_id=stop_id,
        target_id=target.target_id,
        target_name=target.name,
        observation_lifecycle_state=obs_state,
        platform_compatibility=plat_compat,
        platform_mismatch_disclosed=plat_mismatch,
        platform_disclosure_note=plat_note,
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
