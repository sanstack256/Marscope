"""
MARSCOPE Science Investigation Schemas
Prompt 17: Evidence-Driven Science Campaign Planning, Multi-Instrument Target Intelligence & Executable Marswalk Investigation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.eva_operations.schemas import (
    EvaMissionEnvelopeResponse,
    ExplicitResourceSpec,
    ReturnPlanReport,
)
from app.routing.schemas import (
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RoutingMode,
)
from app.schemas.target import InvestigationTargetEvidenceState
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ScientificDataClassification,
)


class InstrumentPlatformKind(str, Enum):
    ORBITAL = "orbital"
    SURFACE_IN_SITU = "surface_in_situ"


class MeasurementClass(str, Enum):
    MINERALOGY_SPECTRAL = "mineralogy_spectral"
    MINERALOGY_XRD = "mineralogy_xrd"
    ELEMENTAL_CHEMISTRY = "elemental_chemistry"
    VOLATILE_ORGANIC_ISOTOPE = "volatile_organic_isotope"
    MORPHOLOGY_HIGHRES = "morphology_highres"
    TOPOGRAPHY_ELEVATION = "topography_elevation"
    THERMAL_INERTIA_COMPOSITION = "thermal_inertia_composition"
    HYDRATED_NEUTRON_SUBSURFACE = "hydrated_neutron_subsurface"
    METEOROLOGY_ENVIRONMENT = "meteorology_environment"


class RequirementFulfillmentState(str, Enum):
    SATISFIED_DIRECT = "satisfied_direct"
    SATISFIED_PROXY_ONLY = "satisfied_proxy_only"
    PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED = "partial_coverage_or_resolution_limited"
    MISSING_REQUIRED_DATA = "missing_required_data"
    CONFLICT_REQUIRES_RESOLUTION = "conflict_requires_resolution"
    CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE = "cannot_be_verified_with_available_archive"


class EvidenceMatchStrength(str, Enum):
    DIRECT_LOCAL_IN_SITU = "direct_local_in_situ"
    ORBITAL_FOOTPRINT_INTERSECTION = "orbital_footprint_intersection"
    CONTEXT_ONLY_SCALE_MISMATCH = "context_only_scale_mismatch"
    UNVERIFIED_OPTICAL_ONLY = "unverified_optical_only"
    ABSENT_DATA_GAP = "absent_data_gap"
    MISSION_ISOLATED_REJECTED = "mission_isolated_rejected"


class CampaignFreshnessState(str, Enum):
    CURRENT = "current"
    STALE_UPSTREAM_DEPENDENCY_CHANGED = "stale_upstream_dependency_changed"


class CampaignPlanStatus(str, Enum):
    COMPLETE_CONSTRAINED_PLAN = "complete_constrained_plan"
    PARTIAL_MISSING_OBSERVATIONS = "partial_missing_observations"
    INFEASIBLE_UNDER_CONSTRAINTS = "infeasible_under_constraints"
    DATA_INSUFFICIENT = "data_insufficient"


class ArchiveComparisonOutcome(str, Enum):
    CONSISTENT_WITH_ARCHIVE = "consistent_with_archive"
    EXTENDS_ARCHIVE_COVERAGE = "extends_archive_coverage"
    DIFFERS_FROM_PRIOR_LOCAL_MEASUREMENT = "differs_from_prior_local_measurement"
    DIFFERS_FROM_ORBITAL_SCALE_EXPECTATION = "differs_from_orbital_scale_expectation"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    NO_CO_LOCATED_ARCHIVE_FOR_COMPARISON = "no_co_located_archive_for_comparison"


class RegistryVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class ThresholdRuleClassification(str, Enum):
    SCIENTIFIC_REQUIREMENT = "scientific_requirement"
    INSTRUMENT_LIMITATION = "instrument_limitation"
    PRODUCT_SELECTION_PREFERENCE = "product_selection_preference"
    ENGINEERING_POLICY = "engineering_policy"
    USER_ASSUMED = "USER_ASSUMED"


class CanonicalRequirementState(str, Enum):
    SATISFIED = "SATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    BLOCKED_BY_DATA_GAP = "BLOCKED_BY_DATA_GAP"


class EvidenceEligibilityState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    ELIGIBLE_WITH_LIMITATIONS = "ELIGIBLE_WITH_LIMITATIONS"
    SPATIALLY_UNVERIFIED = "SPATIALLY_UNVERIFIED"
    CALIBRATION_UNVERIFIED = "CALIBRATION_UNVERIFIED"
    PRODUCT_UNVERIFIED = "PRODUCT_UNVERIFIED"
    MEASUREMENT_SEMANTICS_UNVERIFIED = "MEASUREMENT_SEMANTICS_UNVERIFIED"
    SCALE_INCOMPATIBLE = "SCALE_INCOMPATIBLE"
    MISSION_INCOMPATIBLE = "MISSION_INCOMPATIBLE"
    TEMPORALLY_INCOMPATIBLE = "TEMPORALLY_INCOMPATIBLE"
    SCIENTIFICALLY_IRRELEVANT = "SCIENTIFICALLY_IRRELEVANT"
    DUPLICATE_OR_CORRELATED = "DUPLICATE_OR_CORRELATED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceRole(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    CONTEXTUAL = "CONTEXTUAL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RELEVANT = "NOT_RELEVANT"
    UNAVAILABLE = "UNAVAILABLE"


class SpatialRegistrationState(str, Enum):
    REGISTERED_VALIDATED = "REGISTERED_VALIDATED"
    REGISTERED_WITH_LIMITATIONS = "REGISTERED_WITH_LIMITATIONS"
    PARTIALLY_OVERLAPPING = "PARTIALLY_OVERLAPPING"
    NOT_REGISTERED = "NOT_REGISTERED"
    REGISTRATION_UNVERIFIED = "REGISTRATION_UNVERIFIED"
    INCOMPATIBLE_REFERENCE_SYSTEM = "INCOMPATIBLE_REFERENCE_SYSTEM"
    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"


class CampaignFeasibilityModelState(str, Enum):
    FEASIBLE_UNDER_CONFIGURED_MODEL = "FEASIBLE_UNDER_CONFIGURED_MODEL"
    INFEASIBLE_UNDER_CONFIGURED_MODEL = "INFEASIBLE_UNDER_CONFIGURED_MODEL"
    INCOMPLETE_CONSTRAINT_EVALUATION = "INCOMPLETE_CONSTRAINT_EVALUATION"
    BLOCKED_BY_UNKNOWN_INPUTS = "BLOCKED_BY_UNKNOWN_INPUTS"
    NOT_EVALUATED = "NOT_EVALUATED"


class EvidenceEligibilityDimensionResult(BaseModel):
    dimension: str
    status: str  # PASS | PASS_WITH_LIMITATION | FAIL | UNVERIFIED | UNAVAILABLE | NOT_EVALUATED
    detail: str
    source_reference: Optional[str] = None


class InstrumentCapabilityRecord(BaseModel):
    registry_entry_id: str = ""
    registry_version: str = "2.0.0-p18"
    verification_status: RegistryVerificationStatus = RegistryVerificationStatus.UNVERIFIED
    last_verified_utc: Optional[str] = None
    source_references: List[Dict[str, str]] = Field(default_factory=list)
    unresolved_fields: List[str] = Field(default_factory=list)
    instrument_id: str
    instrument_name: str
    mission_host: str
    study_region_scope: str
    platform_kind: InstrumentPlatformKind
    measurement_class: MeasurementClass
    measurement_modality: str = "unspecified"
    physical_quantity_measured: str = "unspecified"
    measurement_method: str = "unspecified"
    supported_measurement_types: List[str] = Field(default_factory=list)
    applicable_product_types: List[str] = Field(default_factory=list)
    calibration_requirements: List[str] = Field(default_factory=list)
    processing_requirements: List[str] = Field(default_factory=list)
    spatial_applicability: str = "unspecified"
    temporal_applicability: str = "unspecified"
    validity_conditions: List[str] = Field(default_factory=list)
    typical_spatial_scale_m: Optional[float] = Field(
        default=None,
        description="Nominal instrument capability scale ONLY; product-specific spatial resolution always takes precedence.",
    )
    measured_observables: List[str] = Field(default_factory=list)
    allowed_inferences: List[str] = Field(default_factory=list)
    prohibited_inferences: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    mission_isolated_from_gale: bool = False
    mission_isolation_note: Optional[str] = None


class InferenceValidationRequest(BaseModel):
    instrument_id: str
    claimed_inference: str


class InferenceValidationResponse(BaseModel):
    instrument_id: str
    claimed_inference: str
    allowed: bool
    classification: str
    rationale: str
    prohibited_inferences: List[str] = Field(default_factory=list)
    required_evidence_types: List[str] = Field(default_factory=list)
    required_processing_or_calibration: List[str] = Field(default_factory=list)
    applicable_spatial_scale: Optional[str] = None
    required_contextual_evidence: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    prohibited_conclusions: List[str] = Field(default_factory=list)


class MeasurementRequirementSpec(BaseModel):
    requirement_id: str
    label: str
    measurement_class: MeasurementClass
    required_observables: List[str] = Field(default_factory=list)
    allowed_instrument_ids: List[str] = Field(default_factory=list)
    prohibited_substitutions: List[str] = Field(default_factory=list)
    essential: bool = True
    minimum_spatial_resolution_m: Optional[float] = None
    required_calibration_state: str = "calibrated_with_verified_metadata"
    required_product_characteristics: List[str] = Field(default_factory=list)
    threshold_rule_classification: ThresholdRuleClassification = ThresholdRuleClassification.PRODUCT_SELECTION_PREFERENCE
    threshold_source_reference: Optional[str] = None
    threshold_rationale: Optional[str] = None
    user_configurable_threshold: bool = True
    user_assumed: bool = False
    justification: str


class ScienceQuestionDefinition(BaseModel):
    question_id: str
    title: str
    study_region: str = "Gale Crater / Mount Sharp"
    hypothesis: str
    competing_hypotheses: List[str] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)
    contradicting_evidence_criteria: List[str] = Field(default_factory=list)
    unresolved_assumptions: List[str] = Field(default_factory=list)
    current_evidence_state: str = "UNRESOLVED_REQUIRES_MULTI_INSTRUMENT_EVIDENCE"
    geological_setting: str
    is_user_defined: bool = False
    target_phenomena: List[str] = Field(default_factory=list)
    required_measurement_specs: List[MeasurementRequirementSpec] = Field(default_factory=list)
    preferred_stop_count: int = 3
    minimum_evidence_note: str
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CustomScienceQuestionCreateRequest(BaseModel):
    title: str = Field(..., min_length=4, max_length=180)
    study_region: str = Field(default="Gale Crater / Mount Sharp")
    hypothesis: str = Field(..., min_length=8, max_length=1000)
    competing_hypotheses: List[str] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)
    unresolved_assumptions: List[str] = Field(default_factory=list)
    geological_setting: str = Field(default="Mount Sharp / Boxwork-Bearing Strata")
    target_phenomena: List[str] = Field(default_factory=list)
    required_measurement_classes: List[MeasurementClass] = Field(
        default_factory=lambda: [
            MeasurementClass.MORPHOLOGY_HIGHRES,
            MeasurementClass.TOPOGRAPHY_ELEVATION,
            MeasurementClass.ELEMENTAL_CHEMISTRY,
        ]
    )
    preferred_stop_count: int = Field(default=3, ge=1, le=10)


class RequirementEvaluationRecord(BaseModel):
    requirement_id: str
    label: str
    measurement_class: MeasurementClass
    essential: bool
    fulfillment_state: RequirementFulfillmentState
    canonical_state: CanonicalRequirementState = CanonicalRequirementState.NOT_EVALUATED
    required_measurement: List[str] = Field(default_factory=list)
    required_spatial_scale_m: Optional[float] = None
    threshold_rule_classification: Optional[ThresholdRuleClassification] = None
    threshold_rationale: Optional[str] = None
    required_calibration_state: str = "calibrated_with_verified_metadata"
    required_product_characteristics: List[str] = Field(default_factory=list)
    satisfying_source_ids: List[str] = Field(default_factory=list)
    satisfying_instruments: List[str] = Field(default_factory=list)
    evidence_eligibility_summary: Dict[str, int] = Field(default_factory=dict)
    coverage_status: str = "UNVERIFIED"
    quality_status: str = "UNVERIFIED"
    matched_evidence_count: int = 0
    limitations_and_gaps: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    resolution_path: List[str] = Field(default_factory=list)
    prohibited_substitutions: List[str] = Field(default_factory=list)


class EvidenceMatchRecord(BaseModel):
    match_id: str
    source_type: str  # dataset_catalog | composition_index | imagery_catalog | absent_archive_slot
    source_id: str
    product_id: Optional[str] = None
    instrument_id: str
    mission_host: str
    study_region: str
    dataset_status: str
    evidence_strength: EvidenceMatchStrength
    eligibility_state: EvidenceEligibilityState = EvidenceEligibilityState.PRODUCT_UNVERIFIED
    eligibility_dimensions: List[EvidenceEligibilityDimensionResult] = Field(default_factory=list)
    evidence_role: EvidenceRole = EvidenceRole.INCONCLUSIVE
    evidence_role_rationale: Optional[str] = None
    scientific_relevance: str = "UNVERIFIED"
    spatial_scale_m: Optional[float] = None
    product_spatial_resolution_m: Optional[float] = None
    product_footprint_bounds: Optional[Dict[str, float]] = None
    acquisition_time_utc: Optional[str] = None
    processing_level: Optional[str] = None
    coordinate_reference: Optional[str] = None
    units: Optional[str] = None
    calibration_status: Optional[str] = None
    integrity_status: Optional[str] = None
    spatial_registration_state: SpatialRegistrationState = SpatialRegistrationState.INSUFFICIENT_METADATA
    data_quality_flags: List[str] = Field(default_factory=list)
    product_limitations: List[str] = Field(default_factory=list)
    uncertainty_summary: Dict[str, Any] = Field(default_factory=dict)
    duplication_or_correlation: Optional[Dict[str, Any]] = None
    matched_observables: List[str] = Field(default_factory=list)
    scale_mismatch_warning: Optional[str] = None
    prohibited_inference_guard: Optional[str] = None
    rejected_for_gale_reason: Optional[str] = None
    provenance_chain: List[str] = Field(default_factory=list)
    citation: Optional[str] = None


class EvidenceSynthesisSummary(BaseModel):
    qualitative_evidence_state: str
    statistical_confidence_state: str = "UNAVAILABLE_NO_VALIDATED_STATISTICAL_MODEL"
    statistical_confidence_score: Optional[float] = None
    supporting_count: int = 0
    contradicting_count: int = 0
    contextual_count: int = 0
    inconclusive_count: int = 0
    not_relevant_count: int = 0
    unavailable_count: int = 0
    duplicate_or_correlated_count: int = 0
    independent_evidence_count: int = 0
    supporting_observations: List[str] = Field(default_factory=list)
    contradicting_observations: List[str] = Field(default_factory=list)
    inconclusive_observations: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    competing_hypotheses: List[str] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)
    unresolved_contradictions: List[str] = Field(default_factory=list)
    duplication_notes: List[str] = Field(default_factory=list)
    synthesis_rationale: str = ""


class QuestionEvidenceDiscoveryResponse(BaseModel):
    question: ScienceQuestionDefinition
    matched_records: List[EvidenceMatchRecord] = Field(default_factory=list)
    isolated_or_rejected_records: List[EvidenceMatchRecord] = Field(default_factory=list)
    requirements_evaluation: List[RequirementEvaluationRecord] = Field(default_factory=list)
    evidence_synthesis: Optional[EvidenceSynthesisSummary] = None
    spatial_registrations: List[Dict[str, Any]] = Field(default_factory=list)
    overall_evidence_readiness: str
    critical_data_gaps: List[str] = Field(default_factory=list)
    provenance_graph: Optional[ProvenanceDependencyGraph] = None
    discovered_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TargetEvaluationRequest(BaseModel):
    question_id: str = "gale_boxwork_origin"
    target_ids: List[str] = Field(default_factory=list)
    include_discovered_candidates: bool = True
    astronaut_latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    astronaut_longitude: Optional[float] = Field(default=None, ge=-180.0, le=360.0)
    search_radius_m: float = Field(default=250.0, ge=10.0, le=10000.0)
    max_candidates: int = Field(default=12, ge=1, le=50)
    study_bounds: Optional[Dict[str, float]] = None


class CandidateTargetEvaluation(BaseModel):
    target_id: str
    name: str
    latitude: float
    longitude_east: float
    elevation_m: Optional[float] = None
    crs: str = "IAU2000:49900"
    evidence_state: InvestigationTargetEvidenceState
    study_region: str
    matched_species: Optional[str] = None
    distinct_instruments: List[str] = Field(default_factory=list)
    local_observation_count: int = 0
    nearest_observation_distance_m: Optional[float] = None
    covering_datasets: List[str] = Field(default_factory=list)
    known_facts: List[str] = Field(default_factory=list)
    inferred_context: List[str] = Field(default_factory=list)
    unknowns_and_gaps: List[str] = Field(default_factory=list)
    conflicting_records: List[str] = Field(default_factory=list)
    heuristic_priority_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    exploration_priority: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Alias of optional heuristic priority score for mission ordering; NEVER intrinsic scientific truth.",
    )
    scientific_evidence_summary: Optional[Dict[str, Any]] = None
    scientific_relevance: str = "UNVERIFIED"
    route_utility: Optional[Dict[str, Any]] = None
    scientific_confidence_state: str = "QUALITATIVE_ONLY_NO_STATISTICAL_CONFIDENCE"
    scientific_confidence_score: Optional[float] = None
    evidence_eligibility_states: List[EvidenceEligibilityState] = Field(default_factory=list)
    spatial_registration_state: SpatialRegistrationState = SpatialRegistrationState.INSUFFICIENT_METADATA
    spatial_registration_detail: Optional[Dict[str, Any]] = None
    terrain_elevation_m: Optional[float] = None
    terrain_slope_deg: Optional[float] = None
    terrain_roughness_tri_m: Optional[float] = None
    terrain_data_classification: Optional[str] = None
    spatial_coverage_category: Optional[str] = None
    morphology_candidate_ids: List[str] = Field(default_factory=list)
    morphology_review_status: Optional[str] = None
    uncertainty_notes: List[str] = Field(default_factory=list)
    eligibility_decision: str = "CANDIDATE_WITH_LIMITATIONS"
    eligibility_decision_rationale: str = ""
    prioritization_is_heuristic: bool = True
    prioritization_breakdown: Dict[str, Any] = Field(default_factory=dict)
    eligibility_for_sampling: str
    prohibited_inference_flags: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


class IntegratedMissionLifecycleState(str, Enum):
    """18 explicit integrated end-to-end lifecycle states (Prompt 21 Part 1.1)."""

    SCIENTIFIC_QUESTION = "SCIENTIFIC_QUESTION"
    MEASUREMENT_REQUIREMENTS = "MEASUREMENT_REQUIREMENTS"
    EVIDENCE_DISCOVERY = "EVIDENCE_DISCOVERY"
    EVIDENCE_ASSESSMENT = "EVIDENCE_ASSESSMENT"
    TARGET_EVALUATION = "TARGET_EVALUATION"
    CAMPAIGN_DESIGN = "CAMPAIGN_DESIGN"
    OBSERVATION_PLAN = "OBSERVATION_PLAN"
    SPATIAL_ASSESSMENT = "SPATIAL_ASSESSMENT"
    MOBILITY_ASSESSMENT = "MOBILITY_ASSESSMENT"
    EVA_OPERATIONAL_EVALUATION = "EVA_OPERATIONAL_EVALUATION"
    MISSION_REVIEW = "MISSION_REVIEW"
    OPERATOR_APPROVAL = "OPERATOR_APPROVAL"
    EXECUTION_NOT_STARTED = "EXECUTION_NOT_STARTED"
    FIELD_OBSERVATION = "FIELD_OBSERVATION"
    EVIDENCE_UPDATE = "EVIDENCE_UPDATE"
    HYPOTHESIS_REASSESSMENT = "HYPOTHESIS_REASSESSMENT"
    CAMPAIGN_FRESHNESS_CHECK = "CAMPAIGN_FRESHNESS_CHECK"
    REPLAN_IF_REQUIRED = "REPLAN_IF_REQUIRED"


class ObservationLifecycleState(str, Enum):
    """8 explicit observation action lifecycle states (Prompt 21 Part 6.2)."""

    CAPABILITY_DOCUMENTED = "CAPABILITY_DOCUMENTED"
    PRODUCT_AVAILABLE = "PRODUCT_AVAILABLE"
    SPATIALLY_CO_REGISTERED = "SPATIALLY_CO_REGISTERED"
    OBSERVATION_PLANNED = "OBSERVATION_PLANNED"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    EVIDENCE_VALIDATED = "EVIDENCE_VALIDATED"
    ARCHIVE_COMPARED = "ARCHIVE_COMPARED"
    MEASUREMENT_NOT_SUPPORTED = "MEASUREMENT_NOT_SUPPORTED"


class TargetEvaluationBatchResponse(BaseModel):
    question_id: str
    evaluated_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    targets: List[CandidateTargetEvaluation] = Field(default_factory=list)
    rejected_targets: List[CandidateTargetEvaluation] = Field(default_factory=list)
    state_counts: Dict[str, int] = Field(default_factory=dict)
    prioritization_disclaimer: str = (
        "Target ordering uses an optional engineering exploration-priority heuristic for planning only; "
        "heuristic scores NEVER establish mineral confirmation, scientific confidence, or safety."
    )


class ObservationActionPlan(BaseModel):
    stop_id: str
    target_id: str
    target_name: str
    observation_lifecycle_state: ObservationLifecycleState = ObservationLifecycleState.OBSERVATION_PLANNED
    platform_compatibility: str = "unspecified"
    platform_mismatch_disclosed: bool = False
    platform_disclosure_note: str = ""
    recommended_instruments: List[str] = Field(default_factory=list)
    measurements_to_collect: List[str] = Field(default_factory=list)
    context_imaging_checks: List[str] = Field(default_factory=list)
    calibration_or_reference_checks: List[str] = Field(default_factory=list)
    expected_dwell_s: float
    estimated_data_volume_mb: Optional[float] = Field(
        default=None,
        description="Explicit None/UNAVAILABLE unless telemetry bit-rate/frame spec is supplied.",
    )
    data_volume_status: str = "UNAVAILABLE_NO_TELEMETRY_BITRATE_CONFIGURED"
    explicit_uncertainty_notes: List[str] = Field(default_factory=list)
    prohibited_shortcut_notes: List[str] = Field(default_factory=list)


class SamplingProtocolSpec(BaseModel):
    stop_id: str
    target_id: str
    sample_type: str
    eligibility_state: str  # ELIGIBLE_AFTER_PRE_SCREENING | DEFERRED_PENDING_IN_SITU_SCREENING | NOT_RECOMMENDED_OPTICAL_ONLY
    scientific_rationale: str
    required_pre_sample_measurements: List[str] = Field(default_factory=list)
    contamination_controls: List[str] = Field(default_factory=list)
    sample_preservation_notes: List[str] = Field(default_factory=list)
    prohibited_without_evidence: bool = True


class CampaignStopPlan(BaseModel):
    stop_index: int
    stop_id: str
    target_id: str
    name: str
    latitude: float
    longitude_east: float
    evidence_state: InvestigationTargetEvidenceState
    dwell_s: float
    heuristic_priority_score: Optional[float] = None
    known_summary: List[str] = Field(default_factory=list)
    unknown_summary: List[str] = Field(default_factory=list)
    observation_plan: ObservationActionPlan
    sampling_protocol: SamplingProtocolSpec


class CampaignRouteCandidate(BaseModel):
    alternative_id: str
    label: str
    objective: str
    routing_mode: RoutingMode
    stop_order_ids: List[str] = Field(default_factory=list)
    outbound_route_id: Optional[str] = None
    outbound_distance_m: Optional[float] = None
    outbound_elevation_gain_m: Optional[float] = None
    max_slope_deg: Optional[float] = None
    outbound_duration_s: Optional[float] = None
    science_dwell_s: float
    return_route_computed: bool = False
    return_distance_m: Optional[float] = None
    return_duration_s: Optional[float] = None
    total_duration_s: Optional[float] = None
    total_climb_work_j: Optional[float] = None
    feasible_within_constraints: Optional[bool] = None
    scientific_coverage_summary: str
    explanation: str
    failure_reason: Optional[str] = None


class CampaignBuildRequest(BaseModel):
    campaign_id: Optional[str] = None
    campaign_name: str = "Gale Boxwork Field Investigation"
    question_id: str = "gale_boxwork_origin"
    dataset_id: str = "hirise_dteec_009149_1750"
    start: RouteCoordinateInput
    destination: Optional[RouteCoordinateInput] = None
    selected_target_ids: List[str] = Field(default_factory=list)
    candidate_targets: List[CandidateTargetEvaluation] = Field(default_factory=list)
    routing_mode: RoutingMode = RoutingMode.BALANCED
    constraints: RoutePlanningConstraints = Field(default_factory=RoutePlanningConstraints)
    walking_speed_mps: Optional[float] = Field(default=None, gt=0.0, le=5.0)
    use_tobler_grade_approximation: bool = False
    mission_duration_limit_s: Optional[float] = Field(default=None, gt=0.0)
    return_reserve_fraction: Optional[float] = Field(default=None, ge=0.0, le=0.95)
    operational_overhead_s: float = Field(default=0.0, ge=0.0)
    stop_dwell_seconds: Dict[str, float] = Field(default_factory=dict)
    default_stop_dwell_s: float = Field(default=600.0, ge=60.0, le=7200.0)
    astronaut_suit_mass_kg: Optional[float] = Field(default=None, gt=0.0, le=500.0)
    payload_mass_kg: Optional[float] = Field(default=None, ge=0.0, le=500.0)
    resources: List[ExplicitResourceSpec] = Field(default_factory=list)
    include_alternatives: bool = True
    optimize_stop_order: bool = True
    locomotion_category: Optional[str] = None
    unknown_terrain_policy: str = "EXCLUDE_UNKNOWN"
    operator_unknown_override_reason: Optional[str] = None
    confirm_default_policies: bool = False
    expected_plan_version: Optional[int] = None


class CampaignSummary(BaseModel):
    campaign_id: str
    campaign_name: str
    question_id: str
    dataset_id: str
    linked_mission_id: Optional[str] = None
    plan_version: int = 1
    integrated_lifecycle_state: IntegratedMissionLifecycleState = IntegratedMissionLifecycleState.EVA_OPERATIONAL_EVALUATION
    operator_approved: bool = False
    plan_status: CampaignPlanStatus
    feasibility_state: CampaignFeasibilityModelState = CampaignFeasibilityModelState.NOT_EVALUATED
    freshness_state: CampaignFreshnessState
    stop_count: int
    total_distance_m: Optional[float] = None
    total_duration_s: Optional[float] = None
    created_at_utc: str


class CampaignFreshnessReport(BaseModel):
    campaign_id: str
    freshness_state: CampaignFreshnessState
    stored_signature: str
    current_signature: str
    staleness_reasons: List[str] = Field(default_factory=list)
    checked_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScienceCampaignPlan(BaseModel):
    campaign_id: str
    campaign_name: str
    linked_mission_id: Optional[str] = None
    plan_version: int = 1
    integrated_lifecycle_state: IntegratedMissionLifecycleState = IntegratedMissionLifecycleState.EVA_OPERATIONAL_EVALUATION
    operator_approved: bool = False
    operator_approved_by: Optional[str] = None
    operator_approved_at_utc: Optional[str] = None
    operator_approval_note: Optional[str] = None
    hypothesis_reassessments: List[Dict[str, Any]] = Field(default_factory=list)
    lifecycle_transitions: List[Dict[str, Any]] = Field(default_factory=list)
    linked_invalidation_events: List[Dict[str, Any]] = Field(default_factory=list)
    question: ScienceQuestionDefinition
    dataset_id: str
    study_region: str
    plan_status: CampaignPlanStatus
    feasibility_state: CampaignFeasibilityModelState = CampaignFeasibilityModelState.NOT_EVALUATED
    freshness_state: CampaignFreshnessState = CampaignFreshnessState.CURRENT
    staleness_reasons: List[str] = Field(default_factory=list)
    dependency_signature: str
    dependency_snapshot: Dict[str, Any] = Field(default_factory=dict)
    evaluated_inputs_and_constraints: Dict[str, Any] = Field(default_factory=dict)
    epistemic_classification: Dict[str, List[str]] = Field(default_factory=dict)
    constraint_evaluation_complete: bool = False
    survivability_disclaimer: str = (
        "MARSCOPE evaluates traverse geometry and user-configured engineering resource budgets ONLY; "
        "a computed route or return path NEVER certifies astronaut survivability or operational safety."
    )
    operational_safety_certified: bool = False
    request: CampaignBuildRequest
    requirements_evaluation: List[RequirementEvaluationRecord] = Field(default_factory=list)
    stop_plans: List[CampaignStopPlan] = Field(default_factory=list)
    outbound_route_id: Optional[str] = None
    outbound_route_summary: Dict[str, Any] = Field(default_factory=dict)
    outbound_vertices: List[Dict[str, Any]] = Field(default_factory=list)
    return_plan: Optional[ReturnPlanReport] = None
    eva_envelope: Optional[EvaMissionEnvelopeResponse] = None
    alternatives: List[CampaignRouteCandidate] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    uncertainty_and_gaps: List[str] = Field(default_factory=list)
    decision_justification: List[str] = Field(default_factory=list)
    provenance_graph: ProvenanceDependencyGraph
    data_classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    compute_time_ms: float = 0.0


class RecordObservationRequest(BaseModel):
    campaign_id: Optional[str] = None
    stop_id: Optional[str] = None
    target_id: Optional[str] = None
    instrument_id: str
    measurement_type: str
    species_or_feature: str = Field(..., min_length=1, max_length=160)
    measured_value: Any
    units: str = "dimensionless"
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude_east: float = Field(..., ge=-180.0, le=360.0)
    coordinate_reference: str = "IAU2000:49900"
    observer_identity: str = "crew_geologist"
    calibration_metadata: Optional[str] = None
    raw_attachment_ref: Optional[str] = None
    client_submission_id: Optional[str] = None
    expected_plan_version: Optional[int] = None
    sol_or_timestamp: Optional[str] = None
    notes: Optional[str] = None
    measurement_scale_m: Optional[float] = Field(default=None, gt=0.0)
    quality_flag: str = Field(
        default="field_recorded_unvalidated_pending_lab",
        description="Explicit classification distinguishing field measurements from validated archive records.",
    )


class RecordedFieldObservation(BaseModel):
    observation_id: str
    campaign_id: Optional[str] = None
    stop_id: Optional[str] = None
    target_id: Optional[str] = None
    instrument_id: str
    measurement_type: str
    species_or_feature: str
    measured_value: Any
    units: str
    latitude: float
    longitude_east: float
    coordinate_reference: str = "IAU2000:49900"
    observer_identity: str = "crew_geologist"
    calibration_metadata: Optional[str] = None
    raw_attachment_ref: Optional[str] = None
    client_submission_id: Optional[str] = None
    sol_or_timestamp: Optional[str] = None
    notes: Optional[str] = None
    measurement_scale_m: Optional[float] = None
    quality_flag: str
    validation_state: str = "RECORDED_UNVALIDATED"
    lifecycle_state: ObservationLifecycleState = ObservationLifecycleState.OBSERVATION_RECORDED
    reassessment_impact: Optional[str] = None
    prohibited_inference_warning: Optional[str] = None
    recorded_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ObservationArchiveComparison(BaseModel):
    comparison_id: str
    observation_id: str
    outcome: ArchiveComparisonOutcome
    search_radius_m: float
    same_scale_archive_records: List[Dict[str, Any]] = Field(default_factory=list)
    orbital_context_records: List[Dict[str, Any]] = Field(default_factory=list)
    scale_disparity_notes: List[str] = Field(default_factory=list)
    value_comparison_summary: Dict[str, Any] = Field(default_factory=dict)
    explanation: str
    next_verification_steps: List[str] = Field(default_factory=list)
    compared_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
