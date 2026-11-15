"""
MARSCOPE Geological Sampling & Contamination Control Planner
Prompt 17: Produces stop-level sampling eligibility & protocols grounded
strictly in verified target evidence state (never blind core/scooping on
unverified optical anomalies).
"""

from __future__ import annotations

from app.schemas.target import InvestigationTargetEvidenceState
from app.science.investigation.schemas import (
    CandidateTargetEvaluation,
    SamplingProtocolSpec,
    ScienceQuestionDefinition,
)


def build_sampling_protocol(
    *,
    stop_id: str,
    target: CandidateTargetEvaluation,
    question: ScienceQuestionDefinition,
) -> SamplingProtocolSpec:
    controls = [
        "Pre-clean sampling contact tool / scoop face and photograph blank brush surface",
        "Separate resistant fracture-fill ridge material from surrounding host mudstone powder",
        "Record sterile containment bag/cache ID, GPS-less terrain fix, and paired witness photograph",
    ]
    preservation = [
        "Minimize atmospheric moisture desorption & UV oxidation between extraction and sealed canister storage",
        "Maintain chain-of-custody metadata linking sample container ID -> stop_id -> terrain route coordinates",
    ]

    if target.evidence_state == InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION:
        return SamplingProtocolSpec(
            stop_id=stop_id,
            target_id=target.target_id,
            sample_type="paired_fracture_cement_and_host_chip_or_powder",
            eligibility_state="ELIGIBLE_AFTER_PRE_SCREENING",
            scientific_rationale=(
                f"Co-located observations ({target.local_observation_count} records) support '{question.title}'; "
                "paired ridge-vs-host sampling directly tests differential mineral cementation."
            ),
            required_pre_sample_measurements=[
                "Close-up texture imaging (MAHLI-grade) confirming intact fracture cement",
                "Spot elemental verification (APXS/ChemCam) documenting ridge vs host contrast",
            ],
            contamination_controls=controls,
            sample_preservation_notes=preservation,
            prohibited_without_evidence=True,
        )

    if target.evidence_state == InvestigationTargetEvidenceState.CONFLICTING_EVIDENCE:
        return SamplingProtocolSpec(
            stop_id=stop_id,
            target_id=target.target_id,
            sample_type="verification_sub_sample_pending_conflict_resolution",
            eligibility_state="PRIORITY_VERIFICATION_SCREENING_BEFORE_SAMPLING",
            scientific_rationale=(
                "Co-located archive values show heterogeneity/divergence; collect paired spot spectra before physical extraction."
            ),
            required_pre_sample_measurements=[
                "Minimum 3 spaced elemental/spectral readings resolving conflict cause",
            ],
            contamination_controls=controls,
            sample_preservation_notes=preservation,
            prohibited_without_evidence=True,
        )

    return SamplingProtocolSpec(
        stop_id=stop_id,
        target_id=target.target_id,
        sample_type="non_destructive_screening_only_no_bulk_collection_yet",
        eligibility_state="DEFERRED_PENDING_IN_SITU_SCREENING",
        scientific_rationale=(
            f"Target currently holds epistemic state '{target.evidence_state.value}'; visual/orbital/manual indicators "
            "cannot justify bulk extraction prior to in-situ elemental and micro-textural screening."
        ),
        required_pre_sample_measurements=[
            "Contact close-up imaging verifying undisturbed bedrock/ridge fabric",
            "Quantitative in-situ elemental scan (SiO2, CaO, SO3, FeO) confirming question-relevant chemistry",
        ],
        contamination_controls=controls,
        sample_preservation_notes=preservation,
        prohibited_without_evidence=True,
    )
