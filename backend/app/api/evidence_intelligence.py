"""
MARSCOPE Evidence Intelligence API Router
Martian Surface Intelligence & Exploration System

Exposes corridor evidence assessment, segment/coverage/feature/observation/
uncertainty/provenance sub-resources, multi-route evidence comparison, and
persistent Marswalk Mission Dossier endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.evidence_intelligence.schemas import (
    CorridorAssessRequest,
    CorridorAssessment,
    MissionDossierRequest,
    MissionDossierResponse,
    RouteEvidenceComparisonRequest,
    RouteEvidenceComparisonResponse,
)
from app.services.container import evidence_intelligence_service

router = APIRouter(prefix="/evidence-intelligence", tags=["Evidence Intelligence"])


def _get_corridor_or_404(assessment_id: str) -> CorridorAssessment:
    assessment = evidence_intelligence_service.get_corridor_assessment(assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Corridor assessment '{assessment_id}' not found.",
        )
    return assessment


@router.post("/corridor/assess", response_model=CorridorAssessment)
def assess_corridor(request: CorridorAssessRequest):
    """Compute a complete evidence-backed Marswalk corridor assessment."""
    try:
        return evidence_intelligence_service.assess_corridor(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/corridor/{assessment_id}", response_model=CorridorAssessment)
def get_corridor_assessment(assessment_id: str):
    """Retrieve a previously computed corridor assessment."""
    return _get_corridor_or_404(assessment_id)


@router.get("/corridor/{assessment_id}/segments")
def get_corridor_segments(assessment_id: str):
    """Return per-segment terrain, coverage, and provenance breakdown."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "segment_scale_m": assessment.segment_scale_m,
        "segments": assessment.segments,
    }


@router.get("/corridor/{assessment_id}/coverage")
def get_corridor_coverage(assessment_id: str):
    """Return corridor spatial coverage summary, resolution adequacy, and evidence gaps."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "coverage_summary": assessment.coverage_summary,
        "resolution_adequacy": assessment.resolution_adequacy,
        "evidence_gaps": assessment.evidence_gaps,
        "dataset_inventory": assessment.dataset_inventory,
    }


@router.get("/corridor/{assessment_id}/features")
def get_corridor_features(assessment_id: str):
    """Return terrain morphology candidates, optical candidates, and rejected optical false positives."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "terrain_candidates": assessment.terrain_candidates,
        "optical_candidates": assessment.optical_candidates,
        "rejected_optical_candidates": assessment.rejected_optical_candidates,
    }


@router.get("/corridor/{assessment_id}/observations")
def get_corridor_observations(assessment_id: str):
    """Return verified rover observations and imagery records associated within the corridor radius."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "observation_search_radius_m": assessment.observation_search_radius_m,
        "observations": assessment.observations,
    }


@router.get("/corridor/{assessment_id}/uncertainty")
def get_corridor_uncertainty(assessment_id: str):
    """Return uncertainty summary, precision limits, and unquantified physical unknowns."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "uncertainty": assessment.uncertainty,
        "resolution_adequacy": assessment.resolution_adequacy,
    }


@router.get("/corridor/{assessment_id}/provenance")
def get_corridor_provenance(assessment_id: str):
    """Return the full provenance dependency graph and dataset validation stages."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "provenance_graph": assessment.provenance_graph,
        "dataset_inventory": assessment.dataset_inventory,
        "dependency_signature": assessment.dependency_signature,
        "cache_validity": assessment.cache_validity,
        "stale_reasons": assessment.stale_reasons,
    }


@router.get("/corridor/{assessment_id}/decision-trace")
def get_corridor_decision_trace(assessment_id: str):
    """Return hard/soft route constraint trace, cell exclusions, and readiness policy version."""
    assessment = _get_corridor_or_404(assessment_id)
    return {
        "assessment_id": assessment.assessment_id,
        "readiness_policy_version": assessment.readiness_policy_version,
        "cache_validity": assessment.cache_validity,
        "stale_reasons": assessment.stale_reasons,
        "dependency_signature": assessment.dependency_signature,
        "convolution_buffer_m": assessment.convolution_buffer_m,
        "convolution_buffer_px": assessment.convolution_buffer_px,
        "route_decision_explainer": assessment.route_decision_explainer,
        "segment_resolution_checks": [
            {
                "segment_id": s.segment_id,
                "resolution_supportable": s.resolution_supportable,
                "resolution_support_note": s.resolution_support_note,
                "terrain_pixel_count": s.terrain_pixel_count,
                "valid_terrain_pixel_count": s.valid_terrain_pixel_count,
            }
            for s in assessment.segments
        ],
    }


@router.get("/corridor/{assessment_id}/dependency-trace")
def get_corridor_dependency_trace(assessment_id: str):
    """Return Prompt 16 assessment dependency signature, version ledger, and cache freshness trace."""
    assessment = _get_corridor_or_404(assessment_id)
    current_sig = None
    if assessment.dependency_signature is not None:
        s = assessment.dependency_signature
        dem_path = evidence_intelligence_service.processed_dir / f"{s.dem_dataset_id}_dem.tif"
        _, obs_sum = evidence_intelligence_service._load_observations_catalog()
        current_sig = evidence_intelligence_service._build_dependency_signature(
            dataset_id=s.dem_dataset_id,
            source_product_id=s.dem_product_id,
            dem_path=dem_path,
            ortho_id=s.optical_dataset_id,
            route=None,
            route_geom_hash=s.route_geometry_hash,
            corridor_width_m=s.corridor_width_m,
            segment_scale_m=s.segment_scale_m,
            observation_search_radius_m=s.observation_search_radius_m,
            obs_catalog_checksum=obs_sum,
            mission_config=None,
        )
    return {
        "assessment_id": assessment.assessment_id,
        "cache_validity": assessment.cache_validity,
        "stale_reasons": assessment.stale_reasons,
        "stored_dependency_signature": assessment.dependency_signature,
        "current_dependency_signature": current_sig,
    }


@router.post("/routes/compare-evidence", response_model=RouteEvidenceComparisonResponse)
def compare_routes_evidence(request: RouteEvidenceComparisonRequest):
    """Compare candidate planning modes using corridor terrain, coverage, and observation evidence."""
    try:
        return evidence_intelligence_service.compare_routes_evidence(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/mission-dossier/generate", response_model=MissionDossierResponse)
def generate_mission_dossier(request: MissionDossierRequest):
    """Generate and persist a reproducible Marswalk Mission Dossier."""
    try:
        return evidence_intelligence_service.generate_mission_dossier(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/mission-dossier/{dossier_id}", response_model=MissionDossierResponse)
def get_mission_dossier(dossier_id: str):
    """Retrieve a persisted Marswalk Mission Dossier."""
    dossier = evidence_intelligence_service.get_mission_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(
            status_code=404,
            detail=f"Mission dossier '{dossier_id}' not found.",
        )
    return dossier
