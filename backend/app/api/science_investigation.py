"""
MARSCOPE Evidence-Driven Science Investigation & Multi-Instrument Target API
Prompt 17: Exposes 20 endpoints covering Instrument Registry, Scientific Questions,
Evidence Matching, 7-State Target Evaluation, Constrained Multi-Stop Campaign Plans,
Freshness/Staleness Checks, Crew Observation Capture, Scale-Aware Archive Comparison,
and Part 9 Acquisition/Query Provenance Ledger Inspection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

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


# 11
@router.get("/campaigns", response_model=List[CampaignSummary])
async def list_science_campaigns() -> List[CampaignSummary]:
    return science_investigation_service.list_campaigns()


# 12
@router.get("/campaigns/{campaign_id}", response_model=ScienceCampaignPlan)
async def get_science_campaign(campaign_id: str) -> ScienceCampaignPlan:
    plan = science_investigation_service.get_campaign(campaign_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Science campaign '{campaign_id}' not found.",
        )
    return plan


# 13
@router.get("/campaigns/{campaign_id}/freshness", response_model=CampaignFreshnessReport)
async def check_science_campaign_freshness(campaign_id: str) -> CampaignFreshnessReport:
    try:
        return science_investigation_service.check_campaign_freshness(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 14
@router.post("/campaigns/{campaign_id}/recompute", response_model=ScienceCampaignPlan)
async def recompute_science_campaign(campaign_id: str) -> ScienceCampaignPlan:
    try:
        return science_investigation_service.recompute_campaign(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# 15
@router.post("/observations", response_model=RecordedFieldObservation, status_code=201)
async def record_field_observation(
    req: RecordObservationRequest,
) -> RecordedFieldObservation:
    return science_investigation_service.record_observation(req)


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
