"""
MARSCOPE Evidence-Driven Science Investigation & Multi-Instrument Target API
Prompt 17: Exposes 20 endpoints covering Instrument Registry, Scientific Questions,
Evidence Matching, 7-State Target Evaluation, Constrained Multi-Stop Campaign Plans,
Freshness/Staleness Checks, Crew Observation Capture, Scale-Aware Archive Comparison,
and Part 9 Acquisition/Query Provenance Ledger Inspection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from app.core.security import validate_identifier, verify_operator_auth

from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignFreshnessReport,
    CampaignSummary,
    CustomScienceQuestionCreateRequest,
    InferenceValidationRequest,
    InferenceValidationResponse,
    InstrumentCapabilityRecord,
    ObservationArchiveComparison,
    QuestionEvidenceDiscoveryResponse,
    RecordedFieldObservation,
    RecordObservationRequest,
    ScienceCampaignPlan,
    ScienceQuestionDefinition,
    TargetEvaluationBatchResponse,
    TargetEvaluationRequest,
)
from app.services.container import (
    acquisition_service,
    science_investigation_service,
)

router = APIRouter(
    prefix="/science-investigation",
    tags=["Science Investigation & Campaign Planning"],
)


# 1
@router.get("/instruments", response_model=List[InstrumentCapabilityRecord])
async def list_registered_instruments(
    include_mission_isolated: bool = Query(True),
) -> List[InstrumentCapabilityRecord]:
    return science_investigation_service.list_instruments(
        include_mission_isolated=include_mission_isolated
    )


# 2
@router.get("/instruments/{instrument_id}", response_model=InstrumentCapabilityRecord)
async def get_registered_instrument(instrument_id: str) -> InstrumentCapabilityRecord:
    validate_identifier(instrument_id, field_name="instrument_id")
    inst = science_investigation_service.get_instrument(instrument_id)
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument '{instrument_id}' not registered.",
        )
    return inst


# 3
@router.post("/instruments/validate-inference", response_model=InferenceValidationResponse)
async def validate_instrument_inference(
    req: InferenceValidationRequest,
) -> InferenceValidationResponse:
    return science_investigation_service.validate_inference(req)


# 4
@router.get("/questions", response_model=List[ScienceQuestionDefinition])
async def list_science_questions() -> List[ScienceQuestionDefinition]:
    return science_investigation_service.list_questions()


# 5
@router.get("/questions/{question_id}", response_model=ScienceQuestionDefinition)
async def get_science_question(question_id: str) -> ScienceQuestionDefinition:
    q = science_investigation_service.get_question(question_id)
    if q is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Science question '{question_id}' not found.",
        )
    return q


# 6
@router.post("/questions", response_model=ScienceQuestionDefinition, status_code=201)
async def create_custom_science_question(
    req: CustomScienceQuestionCreateRequest,
) -> ScienceQuestionDefinition:
    return science_investigation_service.create_custom_question(req)


# 7
@router.delete("/questions/{question_id}")
async def delete_custom_science_question(question_id: str) -> Dict[str, Any]:
    deleted = science_investigation_service.delete_custom_question(question_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Question '{question_id}' is built-in or does not exist.",
        )
    return {"deleted": True, "question_id": question_id}


# 8
@router.get(
    "/questions/{question_id}/discover-evidence",
    response_model=QuestionEvidenceDiscoveryResponse,
)
async def discover_question_evidence(question_id: str) -> QuestionEvidenceDiscoveryResponse:
    try:
        return science_investigation_service.discover_evidence_for_question(question_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 9
@router.post("/targets/evaluate", response_model=TargetEvaluationBatchResponse)
async def evaluate_question_targets(
    req: TargetEvaluationRequest,
) -> TargetEvaluationBatchResponse:
    try:
        return science_investigation_service.evaluate_targets(req)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 10
@router.post("/campaigns/build", response_model=ScienceCampaignPlan)
async def build_science_campaign(req: CampaignBuildRequest) -> ScienceCampaignPlan:
    try:
        return science_investigation_service.build_campaign(req)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# 11
@router.get("/campaigns", response_model=List[CampaignSummary])
async def list_science_campaigns() -> List[CampaignSummary]:
    return science_investigation_service.list_campaigns()


# 12
@router.get("/campaigns/{campaign_id}", response_model=ScienceCampaignPlan)
async def get_science_campaign(campaign_id: str) -> ScienceCampaignPlan:
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        plan = science_investigation_service.get_campaign(campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Science campaign '{campaign_id}' not found.",
        )
    return plan


# 13
@router.get("/campaigns/{campaign_id}/freshness", response_model=CampaignFreshnessReport)
async def check_science_campaign_freshness(campaign_id: str) -> CampaignFreshnessReport:
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.check_campaign_freshness(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# 14
@router.post("/campaigns/{campaign_id}/recompute", response_model=ScienceCampaignPlan)
async def recompute_science_campaign(
    campaign_id: str,
    expected_plan_version: Optional[int] = Query(default=None, ge=1),
) -> ScienceCampaignPlan:
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.recompute_campaign(
            campaign_id, expected_plan_version=expected_plan_version
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# 15
@router.post("/observations", response_model=RecordedFieldObservation, status_code=201)
async def record_field_observation(
    req: RecordObservationRequest,
) -> RecordedFieldObservation:
    try:
        return science_investigation_service.record_observation(req)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# 16
@router.get("/observations", response_model=List[RecordedFieldObservation])
async def list_field_observations(
    campaign_id: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
) -> List[RecordedFieldObservation]:
    return science_investigation_service.list_observations(
        campaign_id=campaign_id, target_id=target_id
    )


# 17
@router.get("/observations/{observation_id}", response_model=RecordedFieldObservation)
async def get_field_observation(observation_id: str) -> RecordedFieldObservation:
    obs = science_investigation_service.get_observation(observation_id)
    if obs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Field observation '{observation_id}' not found.",
        )
    return obs


# 18
@router.post(
    "/observations/{observation_id}/compare",
    response_model=ObservationArchiveComparison,
)
async def compare_field_observation(
    observation_id: str,
    search_radius_m: float = Query(150.0, ge=5.0, le=5000.0),
) -> ObservationArchiveComparison:
    try:
        return science_investigation_service.compare_observation_with_archive(
            observation_id, search_radius_m=search_radius_m
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 19
@router.get("/comparisons", response_model=List[ObservationArchiveComparison])
async def list_observation_comparisons(
    observation_id: Optional[str] = Query(None),
) -> List[ObservationArchiveComparison]:
    return science_investigation_service.list_comparisons(observation_id=observation_id)


# 20
@router.get("/ingestion-ledger")
async def get_ingestion_audit_ledger(
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    return {
        "acquisition_ledger": acquisition_service.get_acquisition_ledger(limit=limit),
        "query_provenance": acquisition_service.get_query_provenance(limit=limit),
    }


# 21
@router.get("/products/{dataset_id}/inspect")
async def inspect_product_detail(
    dataset_id: str,
    question_id: str = Query("gale_boxwork_origin"),
) -> Dict[str, Any]:
    """Return full Prompt 18 product verification, scaling, registration, and 17-dimension eligibility."""
    validate_identifier(dataset_id, field_name="dataset_id")
    validate_identifier(question_id, field_name="question_id")
    try:
        return science_investigation_service.inspect_product_detail(dataset_id, question_id=question_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 22
@router.get("/campaigns/{campaign_id}/export")
async def export_science_campaign_dossier(campaign_id: str) -> Dict[str, Any]:
    """Export a self-contained reproducible JSON scientific & operational dossier for a campaign."""
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.export_campaign_dossier(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


class CampaignApprovalRequest(BaseModel):
    operator_id: str = Field(default="operator", min_length=1, max_length=80)
    note: str = Field(default="", max_length=300)
    expected_plan_version: Optional[int] = Field(default=None, ge=1)


class OrchestrationInvalidationRequest(BaseModel):
    source_type: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., min_length=3, max_length=300)
    dataset_id: Optional[str] = None
    question_id: Optional[str] = None


# 23
@router.post("/campaigns/{campaign_id}/approve", response_model=ScienceCampaignPlan)
async def approve_science_campaign(
    campaign_id: str,
    req: CampaignApprovalRequest,
) -> ScienceCampaignPlan:
    """Explicitly approve a fresh, reviewed science-to-EVA mission baseline (never auto-approved)."""
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.approve_campaign(
            campaign_id,
            operator_id=req.operator_id,
            note=req.note,
            expected_plan_version=req.expected_plan_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# 24
@router.get("/campaigns/{campaign_id}/lifecycle")
async def get_campaign_lifecycle(campaign_id: str) -> Dict[str, Any]:
    """Return synchronized 18-state end-to-end lifecycle, linked EVA session, and stop observation states."""
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.get_mission_lifecycle_summary(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 25
@router.get("/campaigns/{campaign_id}/unified-dossier")
async def export_unified_mission_dossier(campaign_id: str) -> Dict[str, Any]:
    """Return full 28-item SHA-256 checksummed unified science + spatial + EVA dossier."""
    validate_identifier(campaign_id, field_name="campaign_id")
    try:
        return science_investigation_service.export_campaign_dossier(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 26
@router.post("/orchestration/invalidate")
async def trigger_orchestration_invalidation(
    req: OrchestrationInvalidationRequest,
    request: Request,
) -> Dict[str, Any]:
    """Operator-gated invalidation propagation across affected science campaigns and linked EVA sessions."""
    verify_operator_auth(
        request,
        fail_closed_when_unconfigured=True,
        operation_name="orchestration upstream invalidation",
    )
    did = validate_identifier(req.dataset_id, field_name="dataset_id") if req.dataset_id else None
    qid = validate_identifier(req.question_id, field_name="question_id") if req.question_id else None
    affected = science_investigation_service.propagate_external_invalidation(
        source_type=req.source_type,
        description=req.description,
        dataset_id=did,
        question_id=qid,
    )
    return {
        "propagated": True,
        "affected_campaign_ids": affected,
        "count": len(affected),
    }
