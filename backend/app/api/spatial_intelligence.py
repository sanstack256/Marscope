"""
MARSCOPE Spatial Intelligence API Router (Prompt 19 Part 11).

Unified FastAPI interface for:
- Planetary CRS Registry, Validation, Vertical Datum Comparison & Coordinate Transforms
- True Swath Footprints & Equal-Area Intersection Queries
- 12-Step Multi-Mission Spatial Registration Evaluation & Inspection
- 6-Category Spatial Coverage & Evidence-Gap Intelligence
- Multi-Resolution Terrain Metadata, Windowed Derivatives, Scale Comparison & Gated Change Analysis
- NoData-Hardened Geological Morphology Detection & Auth-Guarded Human Review (USER_PROVIDED)
- Scale-Aware Rover-to-Orbital Spatial Association
- Multi-Resolution Delivery Pyramid & Spatial Cache Status / Invalidation
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.security import validate_identifier, verify_operator_auth
from app.geospatial.coverage import MultiCategorySpatialCoverageReport
from app.geospatial.crs import (
    CRS_REGISTRY_VERSION,
    MARS_CRS_REGISTRY,
    check_vertical_datum_compatibility,
    transform_mars_coordinates,
    validate_mars_crs_detailed,
)
from app.geospatial.footprints import SpatialFootprintRecord
from app.geospatial.models import (
    CoordinateTransformationResult,
    CrsValidationResult,
    MorphologyFeatureClass,
    VerticalDatumComparisonResult,
    VerticalDatumKind,
)
from app.geospatial.registration import SpatialRegistrationAssessment
from app.geospatial.spatial_delivery import (
    CacheInvalidationEvent,
    MultiResolutionPyramidPlan,
)
from app.science.rover_association import RoverOrbitalAssociationRecord
from app.services.container import (
    DATASETS_DIR,
    RAW_DIR,
    catalog_service,
    footprint_index_service,
    morphology_service,
    rover_association_service,
    spatial_coverage_service,
    spatial_delivery_service,
    spatial_registration_service,
)
from app.terrain.morphology import (
    MorphologyDetectionResponse,
    MorphologyReviewRecord,
)
from app.terrain.spatial_terrain import (
    MultiScaleTerrainComparisonResponse,
    NativeDemMetadataRecord,
    TerrainChangeEvaluationResult,
    WindowedTerrainDerivativesReport,
    compare_terrain_scales,
    compute_terrain_derivatives_window,
    evaluate_terrain_change,
    inspect_dem_native_metadata,
)

router = APIRouter(prefix="/spatial", tags=["spatial-intelligence"])


def _validate_study_bounds(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    *,
    max_span_deg: float = 25.0,
) -> None:
    if min_lat < -90.0 or max_lat > 90.0 or min_lat >= max_lat:
        raise HTTPException(
            status_code=422,
            detail="Invalid latitude bounds: -90 <= min_lat < max_lat <= 90 required.",
        )
    if min_lon < -180.0 or max_lon > 360.0 or min_lon == max_lon:
        raise HTTPException(
            status_code=422,
            detail="Invalid longitude bounds: -180 <= min_lon, max_lon <= 360 with non-zero span required.",
        )
    lon_span = abs(max_lon - min_lon)
    if lon_span > max_span_deg or (max_lat - min_lat) > max_span_deg:
        raise HTTPException(
            status_code=422,
            detail=f"Requested study window exceeds bounded maximum span ({max_span_deg} deg) for dense raster processing.",
        )


class CrsValidateRequest(BaseModel):
    crs_string: Optional[str] = None
    latitude_convention: Optional[str] = None
    longitude_direction: Optional[str] = None
    vertical_reference: Optional[str] = None
    require_conventions: bool = False
    require_vertical_datum: bool = False


class VerticalDatumCompareRequest(BaseModel):
    datum_a: str
    datum_b: str
    validated_vertical_offset_m: Optional[float] = None


class CoordinateTransformRequest(BaseModel):
    x_or_lon: float
    y_or_lat: float
    source_crs: str
    target_crs: str
    source_lat_convention: str = "Planetocentric"
    target_lat_convention: str = "Planetocentric"
    source_lon_direction: str = "East"
    target_lon_domain: str = "[0, 360)"
    source_vertical_datum: Optional[VerticalDatumKind] = None
    target_vertical_datum: Optional[VerticalDatumKind] = None


class RegistrationEvaluateRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    intended_analysis: str = Field(
        "spatial_overlay",
        description="spatial_overlay | route_planning | temporal_terrain_change | composition_association",
    )
    control_points: Optional[List[Dict[str, float]]] = None
    attempt_image_matching: bool = False


class TerrainChangeCompareRequest(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    min_lat: float = Field(..., ge=-90.0, le=90.0)
    max_lat: float = Field(..., ge=-90.0, le=90.0)
    min_lon: float = Field(..., ge=-180.0, le=360.0)
    max_lon: float = Field(..., ge=-180.0, le=360.0)
    validated_vertical_offset_m: Optional[float] = None


class MorphologyReviewSubmitRequest(BaseModel):
    candidate_id: str
    dataset_id: str
    action: str = Field(..., description="accept | reject | annotate")
    reviewer_id: str = Field(..., min_length=2, max_length=64)
    annotation_note: Optional[str] = Field(None, max_length=500)
    assigned_feature_class: Optional[MorphologyFeatureClass] = None


class RoverAssociateRequest(BaseModel):
    orbital_dataset_id: str
    observation: Dict[str, Any]
    feature_lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    feature_lon_east: Optional[float] = Field(None, ge=-180.0, le=360.0)
    feature_id: Optional[str] = None
    direct_association_radius_m: float = Field(15.0, ge=0.5, le=200.0)
    regional_context_radius_m: float = Field(500.0, ge=5.0, le=5000.0)


class CacheInvalidateRequest(BaseModel):
    dataset_id: Optional[str] = None
    reason: str = Field("operator_requested_invalidation", max_length=200)


# --- 1. Planetary CRS Registry & Transformations ---


@router.get("/crs/registry")
async def get_planetary_crs_registry() -> Dict[str, Any]:
    return {
        "registry_version": CRS_REGISTRY_VERSION,
        "supported_crs": {k: v.model_dump() for k, v in MARS_CRS_REGISTRY.items()},
        "vertical_datum_kinds": [v.value for v in VerticalDatumKind],
    }


@router.post("/crs/validate", response_model=CrsValidationResult)
async def validate_crs(req: CrsValidateRequest) -> CrsValidationResult:
    return validate_mars_crs_detailed(
        req.crs_string,
        latitude_convention=req.latitude_convention,
        longitude_direction=req.longitude_direction,
        vertical_reference=req.vertical_reference,
        require_conventions=req.require_conventions,
        require_vertical_datum=req.require_vertical_datum,
    )


@router.post("/crs/vertical-datum/compare", response_model=VerticalDatumComparisonResult)
async def compare_vertical_datums(req: VerticalDatumCompareRequest) -> VerticalDatumComparisonResult:
    return check_vertical_datum_compatibility(
        req.datum_a,
        req.datum_b,
        validated_vertical_offset_m=req.validated_vertical_offset_m,
    )


@router.post("/crs/transform", response_model=CoordinateTransformationResult)
async def transform_coordinates(req: CoordinateTransformRequest) -> CoordinateTransformationResult:
    return transform_mars_coordinates(
        x_or_lon=req.x_or_lon,
        y_or_lat=req.y_or_lat,
        source_crs=req.source_crs,
        target_crs=req.target_crs,
        source_lat_convention=req.source_lat_convention,
        target_lat_convention=req.target_lat_convention,
        source_lon_direction=req.source_lon_direction,
        target_lon_domain=req.target_lon_domain,
        source_vertical_datum=req.source_vertical_datum,
        target_vertical_datum=req.target_vertical_datum,
    )


# --- 2. Footprints & Intersection ---


@router.get("/footprints")
async def list_footprints(
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    records = footprint_index_service.list_footprints()
    if category:
        records = [r for r in records if r.category.value == category.lower()]
    total = len(records)
    sliced = records[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "footprints": [r.model_dump() for r in sliced],
    }


@router.get("/footprints/query/intersect")
async def query_intersecting_footprints(
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
) -> Dict[str, Any]:
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=40.0)
    hits = footprint_index_service.query_bounds(
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )
    return {
        "query_bounds": {"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
        "count": len(hits),
        "footprints": [h.model_dump() for h in hits],
    }


@router.get("/footprints/{dataset_id}", response_model=SpatialFootprintRecord)
async def get_dataset_footprint(dataset_id: str) -> SpatialFootprintRecord:
    did = validate_identifier(dataset_id, field_name="dataset_id")
    rec = footprint_index_service.get_footprint(did)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Dataset footprint not found for '{did}'.")
    return rec


# --- 3. Multi-Mission Spatial Registration ---


@router.post("/registration/evaluate", response_model=SpatialRegistrationAssessment)
async def evaluate_registration(req: RegistrationEvaluateRequest) -> SpatialRegistrationAssessment:
    da = validate_identifier(req.dataset_a_id, field_name="dataset_a_id")
    db = validate_identifier(req.dataset_b_id, field_name="dataset_b_id")
    try:
        return spatial_registration_service.evaluate_pair(
            dataset_a_id=da,
            dataset_b_id=db,
            intended_analysis=req.intended_analysis,
            control_points=req.control_points,
            attempt_image_matching=req.attempt_image_matching,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/registration/assessments", response_model=List[SpatialRegistrationAssessment])
async def list_registration_assessments() -> List[SpatialRegistrationAssessment]:
    return spatial_registration_service.list_recent_assessments()


# --- 4. Spatial Coverage & Evidence Gaps ---


@router.get("/coverage/evaluate", response_model=MultiCategorySpatialCoverageReport)
async def evaluate_spatial_coverage(
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    reference_dataset_id: Optional[str] = Query(None),
    intended_resolution_threshold_m: float = Query(5.0, gt=0.05, le=2000.0),
    question_focus: Optional[str] = Query(None, max_length=200),
) -> MultiCategorySpatialCoverageReport:
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=15.0)
    ref_id = validate_identifier(reference_dataset_id, field_name="reference_dataset_id") if reference_dataset_id else None
    try:
        return spatial_coverage_service.assess_coverage(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            reference_dataset_id=ref_id,
            intended_resolution_threshold_m=intended_resolution_threshold_m,
            question_focus=question_focus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- 5. Multi-Resolution Terrain Intelligence ---


@router.get("/terrain/{dataset_id}/metadata", response_model=NativeDemMetadataRecord)
async def get_terrain_native_metadata(dataset_id: str) -> NativeDemMetadataRecord:
    did = validate_identifier(dataset_id, field_name="dataset_id")
    ds = catalog_service.get_dataset(did)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{did}' not found.")
    try:
        return inspect_dem_native_metadata(ds, raw_dir=RAW_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/terrain/{dataset_id}/derivatives", response_model=WindowedTerrainDerivativesReport)
async def get_terrain_derivatives(
    dataset_id: str,
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    max_grid_dim: int = Query(128, ge=16, le=192),
    local_scale_radius_m: float = Query(5.0, gt=0.5, le=500.0),
    coarse_scale_radius_m: float = Query(25.0, gt=1.0, le=5000.0),
) -> WindowedTerrainDerivativesReport:
    did = validate_identifier(dataset_id, field_name="dataset_id")
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=5.0)
    ds = catalog_service.get_dataset(did)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{did}' not found.")
    try:
        return compute_terrain_derivatives_window(
            ds,
            raw_dir=RAW_DIR,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            max_grid_dim=max_grid_dim,
            local_scale_radius_m=local_scale_radius_m,
            coarse_scale_radius_m=coarse_scale_radius_m,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/terrain/compare-scales", response_model=MultiScaleTerrainComparisonResponse)
async def compare_scales(
    dataset_ids: str = Query(..., description="Comma-separated DEM dataset IDs"),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
) -> MultiScaleTerrainComparisonResponse:
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=5.0)
    raw_ids = [validate_identifier(x.strip(), field_name="dataset_id") for x in dataset_ids.split(",") if x.strip()]
    if not raw_ids or len(raw_ids) > 6:
        raise HTTPException(status_code=422, detail="Supply 1 to 6 comma-separated dataset_ids.")
    dsets = []
    for did in raw_ids:
        ds = catalog_service.get_dataset(did)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset '{did}' not found.")
        dsets.append(ds)
    return compare_terrain_scales(
        datasets=dsets,
        raw_dir=RAW_DIR,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )


@router.post("/terrain/compare-change", response_model=TerrainChangeEvaluationResult)
async def evaluate_temporal_terrain_change(req: TerrainChangeCompareRequest) -> TerrainChangeEvaluationResult:
    da = validate_identifier(req.dataset_a_id, field_name="dataset_a_id")
    db = validate_identifier(req.dataset_b_id, field_name="dataset_b_id")
    _validate_study_bounds(req.min_lat, req.max_lat, req.min_lon, req.max_lon, max_span_deg=2.0)
    ds_a = catalog_service.get_dataset(da)
    ds_b = catalog_service.get_dataset(db)
    if not ds_a or not ds_b:
        raise HTTPException(status_code=404, detail="One or both datasets not found in catalog.")
    return evaluate_terrain_change(
        ds_a,
        ds_b,
        dataset_root_dir=DATASETS_DIR,
        raw_dir=RAW_DIR,
        min_lat=req.min_lat,
        max_lat=req.max_lat,
        min_lon=req.min_lon,
        max_lon=req.max_lon,
        validated_vertical_offset_m=req.validated_vertical_offset_m,
    )


# --- 6. Geological Morphology & Auth-Guarded Human Review ---


@router.get("/morphology/detect", response_model=MorphologyDetectionResponse)
async def detect_morphology_candidates(
    dataset_id: str = Query(...),
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    grid_size: int = Query(96, ge=32, le=160),
    max_candidates: int = Query(24, ge=1, le=50),
) -> MorphologyDetectionResponse:
    did = validate_identifier(dataset_id, field_name="dataset_id")
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=1.0)
    try:
        return morphology_service.detect_candidates_in_region(
            dataset_id=did,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            grid_size=grid_size,
            max_candidates=max_candidates,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/morphology/reviews")
async def list_morphology_reviews() -> Dict[str, Any]:
    reviews = morphology_service.review_store.load_all()
    return {
        "classification": "USER_PROVIDED",
        "count": len(reviews),
        "reviews": {k: v.model_dump() for k, v in reviews.items()},
    }


@router.post("/morphology/review", response_model=MorphologyReviewRecord)
async def submit_morphology_review(req: MorphologyReviewSubmitRequest, request: Request) -> MorphologyReviewRecord:
    verify_operator_auth(
        request,
        fail_closed_when_unconfigured=True,
        operation_name="morphology candidate human review",
    )
    cid = validate_identifier(req.candidate_id, field_name="candidate_id")
    did = validate_identifier(req.dataset_id, field_name="dataset_id")
    if not catalog_service.get_dataset(did):
        raise HTTPException(status_code=404, detail=f"Dataset '{did}' not found.")
    try:
        return morphology_service.submit_human_review(
            candidate_id=cid,
            dataset_id=did,
            action=req.action,
            reviewer_id=req.reviewer_id,
            annotation_note=req.annotation_note,
            assigned_feature_class=req.assigned_feature_class,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- 7. Scale-Aware Rover-to-Orbital Association ---


@router.post("/rover/associate", response_model=RoverOrbitalAssociationRecord)
async def associate_rover_observation(req: RoverAssociateRequest) -> RoverOrbitalAssociationRecord:
    oid = validate_identifier(req.orbital_dataset_id, field_name="orbital_dataset_id")
    try:
        return rover_association_service.associate_observation(
            observation=req.observation,
            orbital_dataset_id=oid,
            feature_lat=req.feature_lat,
            feature_lon_east=req.feature_lon_east,
            feature_id=req.feature_id,
            direct_association_radius_m=req.direct_association_radius_m,
            regional_context_radius_m=req.regional_context_radius_m,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/rover/region-associations", response_model=List[RoverOrbitalAssociationRecord])
async def get_region_rover_associations(
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    orbital_dataset_id: str = Query("hirise_dteec_009149_1750"),
    feature_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    feature_lon_east: Optional[float] = Query(None, ge=-180.0, le=360.0),
    limit: int = Query(30, ge=1, le=100),
) -> List[RoverOrbitalAssociationRecord]:
    oid = validate_identifier(orbital_dataset_id, field_name="orbital_dataset_id")
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=5.0)
    try:
        return rover_association_service.associate_region_observations(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            orbital_dataset_id=oid,
            feature_lat=feature_lat,
            feature_lon_east=feature_lon_east,
            limit=limit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --- 8. Multi-Resolution Delivery & Spatial Cache Management ---


@router.get("/delivery/pyramid-plan", response_model=MultiResolutionPyramidPlan)
async def get_delivery_pyramid_plan(
    min_lat: float = Query(..., ge=-90.0, le=90.0),
    max_lat: float = Query(..., ge=-90.0, le=90.0),
    min_lon: float = Query(..., ge=-180.0, le=360.0),
    max_lon: float = Query(..., ge=-180.0, le=360.0),
    viewport_px: int = Query(512, ge=32, le=2048),
    preferred_dataset_id: Optional[str] = Query(None),
) -> MultiResolutionPyramidPlan:
    _validate_study_bounds(min_lat, max_lat, min_lon, max_lon, max_span_deg=60.0)
    pref = validate_identifier(preferred_dataset_id, field_name="preferred_dataset_id") if preferred_dataset_id else None
    try:
        return spatial_delivery_service.get_multi_resolution_pyramid_plan(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            viewport_px=viewport_px,
            preferred_dataset_id=pref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cache/status")
async def get_spatial_cache_status() -> Dict[str, Any]:
    return spatial_delivery_service.get_cache_status()


@router.post("/cache/invalidate", response_model=CacheInvalidationEvent)
async def invalidate_spatial_cache(req: CacheInvalidateRequest, request: Request) -> CacheInvalidationEvent:
    verify_operator_auth(
        request,
        fail_closed_when_unconfigured=True,
        operation_name="spatial cache invalidation",
    )
    did = validate_identifier(req.dataset_id, field_name="dataset_id") if req.dataset_id else None
    if did is not None:
        footprint_index_service.invalidate(reason=req.reason)
    else:
        footprint_index_service.invalidate(reason=req.reason)
    return spatial_delivery_service.invalidate_cache(
        dataset_id=did,
        reason=req.reason,
        operator="operator",
    )
