"""
MARSCOPE Spatial Coverage & Evidence-Gap Intelligence Engine (Prompt 19 Part 5).

Computes polygon-union spatial coverage across 6 observation categories and
5 distinct validation stages (footprint, valid pixels, calibrated, registered,
scientifically eligible) and derives exact SpatialGapCause regions where absence
of usable evidence is never conflated with absence of geological features.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from app.geospatial.footprints import (
    SpatialFootprintIndex,
    SpatialFootprintRecord,
    compute_mars_geometry_area_m2,
    ensure_valid_mars_geometry,
    normalize_lon_east_360,
)
from app.geospatial.models import (
    ObservationCategory,
    SpatialGapCause,
    SpatialRegistrationAssessmentState,
)
from app.geospatial.registration import evaluate_product_pair_registration
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.science.provenance_graph import ScientificDataClassification


class CategorySpatialCoverage(BaseModel):
    category: ObservationCategory
    matching_product_ids: List[str] = Field(default_factory=list)
    local_verified_product_ids: List[str] = Field(default_factory=list)
    best_native_resolution_m: Optional[float] = None

    # Areas (equal-area m^2)
    study_area_m2: float
    product_footprint_area_m2: Optional[float] = None
    valid_pixel_area_m2: Optional[float] = None
    calibrated_data_area_m2: Optional[float] = None
    spatially_registered_area_m2: Optional[float] = None
    scientifically_eligible_area_m2: Optional[float] = None

    # Exact fractions are suppressed (None) when only approximate bounding boxes exist!
    product_footprint_fraction: Optional[float] = None
    valid_pixel_fraction: Optional[float] = None
    calibrated_data_fraction: Optional[float] = None
    spatially_registered_fraction: Optional[float] = None
    scientifically_eligible_fraction: Optional[float] = None

    has_approximate_footprints: bool = False
    only_approximate_footprints: bool = False
    percentage_reporting_policy: str
    rover_point_observation_count: int = 0
    footprint_union_geojson: Optional[Dict[str, Any]] = None
    valid_pixel_union_geojson: Optional[Dict[str, Any]] = None
    limitations: List[str] = Field(default_factory=list)


class SpatialGapRegion(BaseModel):
    gap_id: str
    category: ObservationCategory
    gap_cause: SpatialGapCause
    area_m2: float
    area_fraction_of_study_region: float
    contributing_product_ids: List[str] = Field(default_factory=list)
    summary: str
    never_implies_feature_absence: bool = True
    interpretation_warning: str = (
        "Absence of usable observations in this region indicates an evidence gap ONLY "
        "and NEVER implies absence of hazards, minerals, or geological structures."
    )
    recommended_action: str
    geometry_geojson: Optional[Dict[str, Any]] = None


class MultiCategorySpatialCoverageReport(BaseModel):
    study_bounds: Dict[str, float]
    study_area_m2: float
    area_calculation_method: str = "mars_sinusoidal_equal_area_R3396190m"
    reference_dataset_id: Optional[str] = None
    intended_resolution_threshold_m: float
    question_focus: Optional[str] = None
    categories: Dict[str, CategorySpatialCoverage] = Field(default_factory=dict)
    evidence_gaps: List[SpatialGapRegion] = Field(default_factory=list)
    overall_limitations: List[str] = Field(default_factory=list)
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED


def _clip_polygons_only(geom: BaseGeometry) -> BaseGeometry:
    if geom.is_empty:
        return Polygon()
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, GeometryCollection):
        polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
        return unary_union(polys) if polys else Polygon()
    return Polygon()


def _union_intersections(geoms: List[BaseGeometry], roi: BaseGeometry) -> Tuple[Optional[BaseGeometry], float]:
    clipped: List[BaseGeometry] = []
    for g in geoms:
        if g.is_empty:
            continue
        inter = _clip_polygons_only(g.intersection(roi))
        if not inter.is_empty and inter.area > 0:
            if not inter.is_valid:
                inter = make_valid(inter)
            clipped.append(inter)
    if not clipped:
        return None, 0.0
    u = _clip_polygons_only(unary_union(clipped))
    if not u.is_valid:
        u = make_valid(u)
    area_m2 = round(compute_mars_geometry_area_m2(u), 2)
    return u, area_m2


def _is_product_calibrated_scientific(ds: Dataset, fp: SpatialFootprintRecord) -> bool:
    is_wmts = "{" in (ds.original_product_url or "")
    if is_wmts:
        return False
    if "psv" in ds.id.lower():
        return False
    if not fp.has_local_artifact:
        return False
    if ds.status == DatasetLifecycleStatus.FAILED_VALIDATION or ds.failure_reason:
        return False
    cal = (ds.calibration_status or "unknown").lower()
    if cal in {"unknown", "", "uncalibrated", "raw dn"}:
        return False
    return ds.verification.download_verification == VerificationState.VERIFIED


def _is_scientifically_eligible_for_focus(
    ds: Dataset,
    fp: SpatialFootprintRecord,
    question_focus: Optional[str],
) -> bool:
    if not _is_product_calibrated_scientific(ds, fp):
        return False
    focus = (question_focus or "general").lower()
    if focus in {"mineralogy", "hydrated_minerals", "sulfates_clays"}:
        # Optical RGB/pan images and environmental telemetry alone cannot confirm mineral phase!
        if fp.category in {ObservationCategory.OPTICAL, ObservationCategory.ENVIRONMENTAL, ObservationCategory.ELEVATION}:
            return False
    elif focus in {"trafficability", "boxwork_morphology", "eva_hazard"}:
        if ds.horizontal_resolution_meters is not None and ds.horizontal_resolution_meters > 5.0 and fp.category == ObservationCategory.ELEVATION:
            return False
    return True


def _build_roi_geometry(
    *,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
) -> BaseGeometry:
    nmin = normalize_lon_east_360(min_lon)
    nmax = normalize_lon_east_360(max_lon)
    if abs(max_lon - min_lon) >= 359.5:
        geom = box(0.0, min_lat, 360.0, max_lat)
    elif nmax <= nmin:
        geom = unary_union([box(nmin, min_lat, 360.0, max_lat), box(0.0, min_lat, nmax, max_lat)])
    else:
        geom = box(nmin, min_lat, nmax, max_lat)
    geom, _, _ = ensure_valid_mars_geometry(geom)
    return geom


def compute_multi_category_spatial_coverage(
    *,
    catalog_service: Any,
    footprint_index: SpatialFootprintIndex,
    dataset_root_dir: Path,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    reference_dataset_id: Optional[str] = None,
    intended_resolution_threshold_m: float = 5.0,
    question_focus: Optional[str] = None,
    rover_points: Optional[List[Dict[str, Any]]] = None,
    composition_index: Any = None,
) -> MultiCategorySpatialCoverageReport:
    """
    Compute 6-category, 5-stage spatial coverage and explicit SpatialGapRegion geometries
    over any Mars study bounding box.
    """
    roi_geom = _build_roi_geometry(min_lat=min_lat, max_lat=max_lat, min_lon=min_lon, max_lon=max_lon)
    study_area_m2 = round(compute_mars_geometry_area_m2(roi_geom), 2)
    intersecting = footprint_index.query_geometry(roi_geom)
    datasets_by_id = {ds.id: ds for ds in catalog_service.list_datasets()}

    ref_ds = datasets_by_id.get(reference_dataset_id) if reference_dataset_id else None
    if ref_ds is None:
        # Default Gale high-res reference DTM when present and intersecting
        cand = datasets_by_id.get("hirise_dteec_009149_1750")
        if cand is not None:
            ref_ds = cand

    ref_fp = footprint_index.get_footprint(ref_ds.id) if ref_ds else None

    # Pre-gather real rover point locations inside ROI (either explicitly supplied or from composition_index)
    rover_pts_in_roi: List[Dict[str, Any]] = []
    if rover_points:
        for rp in rover_points:
            lat = rp.get("lat")
            lon = rp.get("lon_east") if rp.get("lon_east") is not None else rp.get("lon")
            if lat is not None and lon is not None and roi_geom.covers(Point(normalize_lon_east_360(float(lon)), float(lat))):
                rover_pts_in_roi.append(rp)
    elif composition_index is not None:
        try:
            from app.science.composition.species import list_all_species

            sp_ids = [s.canonical_id for s in list_all_species()]
            evs = composition_index.query_evidence(
                species_ids=sp_ids,
                located_only=True,
                bbox=(min_lat, max_lat, min_lon, max_lon),
            )[:500]
            for ev in evs:
                if ev.latitude is not None and ev.longitude_east is not None:
                    rover_pts_in_roi.append(
                        {
                            "id": ev.evidence_id,
                            "lat": float(ev.latitude),
                            "lon_east": normalize_lon_east_360(float(ev.longitude_east)),
                            "instrument": getattr(ev, "instrument_id", None) or getattr(ev, "instrument", "MSL"),
                        }
                    )
        except Exception:
            pass

    categories_out: Dict[str, CategorySpatialCoverage] = {}
    gaps_out: List[SpatialGapRegion] = []
    overall_lims: List[str] = []

    for cat in ObservationCategory:
        cat_fps = [fp for fp in intersecting if fp.category == cat]
        matching_ids = [fp.dataset_id for fp in cat_fps]
        local_ids = [fp.dataset_id for fp in cat_fps if fp.has_local_artifact]
        res_vals = [fp.horizontal_resolution_m for fp in cat_fps if fp.horizontal_resolution_m is not None]
        best_res = min(res_vals) if res_vals else None

        any_approx = any(fp.is_approximate for fp in cat_fps)
        only_approx = bool(cat_fps) and all(fp.is_approximate for fp in cat_fps)

        fp_geoms: List[BaseGeometry] = []
        valid_geoms: List[BaseGeometry] = []
        cal_geoms: List[BaseGeometry] = []
        reg_geoms: List[BaseGeometry] = []
        elig_geoms: List[BaseGeometry] = []
        fine_valid_geoms: List[BaseGeometry] = []
        irrelevant_geoms: List[BaseGeometry] = []
        unreg_geoms: List[BaseGeometry] = []

        cat_lims: List[str] = []
        for fp in cat_fps:
            ds = datasets_by_id.get(fp.dataset_id)
            if ds is None:
                continue
            if fp.footprint_geojson:
                g_fp = shape(fp.footprint_geojson)
                fp_geoms.append(g_fp)
            else:
                g_fp = Polygon()

            if fp.valid_data_geojson:
                g_val = shape(fp.valid_data_geojson)
                valid_geoms.append(g_val)
            else:
                g_val = Polygon()

            is_cal = _is_product_calibrated_scientific(ds, fp)
            if is_cal and not g_val.is_empty:
                cal_geoms.append(g_val)

            # Pairwise registration to reference frame (or self if ref_ds)
            is_reg = False
            if ref_ds is not None and ref_ds.id == ds.id:
                is_reg = fp.coordinate_validation.valid and fp.has_local_artifact
            elif ref_ds is not None:
                reg = evaluate_product_pair_registration(
                    ds,
                    ref_ds,
                    dataset_root_dir=dataset_root_dir,
                    footprint_a=fp,
                    footprint_b=ref_fp,
                    intended_analysis=question_focus or "spatial_overlay",
                )
                is_reg = reg.overall_state in {
                    SpatialRegistrationAssessmentState.VALIDATED_REGISTRATION,
                    SpatialRegistrationAssessmentState.VALIDATED_WITH_LIMITATIONS,
                    SpatialRegistrationAssessmentState.PARTIAL_OVERLAP,
                    SpatialRegistrationAssessmentState.RELATIVE_ALIGNMENT_ONLY,
                }
            else:
                is_reg = fp.coordinate_validation.valid and fp.has_local_artifact

            if is_reg and not g_val.is_empty:
                reg_geoms.append(g_val)
            elif not g_fp.is_empty and not is_reg:
                unreg_geoms.append(g_fp)

            is_elig = _is_scientifically_eligible_for_focus(ds, fp, question_focus)
            if is_elig and is_reg and not g_val.is_empty:
                elig_geoms.append(g_val)
            elif not is_elig and not g_fp.is_empty:
                irrelevant_geoms.append(g_fp)

            if not g_val.is_empty and (
                fp.horizontal_resolution_m is None or fp.horizontal_resolution_m <= intended_resolution_threshold_m
            ):
                fine_valid_geoms.append(g_val)

        fp_union, fp_area = _union_intersections(fp_geoms, roi_geom)
        val_union, val_area = _union_intersections(valid_geoms, roi_geom)
        _, cal_area = _union_intersections(cal_geoms, roi_geom)
        _, reg_area = _union_intersections(reg_geoms, roi_geom)
        _, elig_area = _union_intersections(elig_geoms, roi_geom)
        _, fine_area = _union_intersections(fine_valid_geoms, roi_geom)

        def _frac(a: Optional[float]) -> Optional[float]:
            if a is None or study_area_m2 <= 0:
                return None
            return round(min(1.0, a / study_area_m2), 4)

        # Prompt 19 Part 5.3 rule: "Do not report an exact percentage if the input footprint itself is only approximate."
        if only_approx:
            fp_frac = None
            reporting_policy = "approximate_bbox_exact_percentage_suppressed"
            cat_lims.append(
                "Category contains ONLY approximate bounding-box footprints; exact footprint coverage % suppressed."
            )
        else:
            fp_frac = _frac(fp_area)
            reporting_policy = (
                "mixed_exact_and_approximate_footprints"
                if any_approx
                else "authoritative_polygon_equal_area"
            )

        val_frac = _frac(val_area)
        cal_frac = _frac(cal_area)
        reg_frac = _frac(reg_area)
        elig_frac = _frac(elig_area)

        rover_count = len(rover_pts_in_roi) if cat == ObservationCategory.ROVER else 0
        if cat == ObservationCategory.ROVER and rover_count > 0 and only_approx:
            cat_lims.append(
                f"{rover_count} localized rover point observations inside ROI cannot substantiate regional areal coverage."
            )

        categories_out[cat.value] = CategorySpatialCoverage(
            category=cat,
            matching_product_ids=matching_ids,
            local_verified_product_ids=local_ids,
            best_native_resolution_m=best_res,
            study_area_m2=study_area_m2,
            product_footprint_area_m2=fp_area if not only_approx else None,
            valid_pixel_area_m2=val_area,
            calibrated_data_area_m2=cal_area,
            spatially_registered_area_m2=reg_area,
            scientifically_eligible_area_m2=elig_area,
            product_footprint_fraction=fp_frac,
            valid_pixel_fraction=val_frac,
            calibrated_data_fraction=cal_frac,
            spatially_registered_fraction=reg_frac,
            scientifically_eligible_fraction=elig_frac,
            has_approximate_footprints=any_approx,
            only_approximate_footprints=only_approx,
            percentage_reporting_policy=reporting_policy,
            rover_point_observation_count=rover_count,
            footprint_union_geojson=mapping(fp_union) if fp_union is not None else None,
            valid_pixel_union_geojson=mapping(val_union) if val_union is not None else None,
            limitations=cat_lims,
        )

        # Evidence-Gap Polygon Engine for this category
        # Determine uncovered ROI residual (using scientifically eligible geoms when a specific question focus excludes a category)
        use_elig_for_gap = bool(
            question_focus
            and question_focus.lower() not in {"general", "all"}
            and irrelevant_geoms
            and not elig_geoms
        )
        usable_geoms = elig_geoms if use_elig_for_gap else fine_valid_geoms
        usable_union = _clip_polygons_only(unary_union(usable_geoms)) if usable_geoms else Polygon()
        if not usable_union.is_empty and not usable_union.is_valid:
            usable_union = make_valid(usable_union)
        missing_usable = _clip_polygons_only(roi_geom.difference(usable_union)) if not usable_union.is_empty else roi_geom

        if not missing_usable.is_empty and missing_usable.area > 1e-12:
            gap_area = round(compute_mars_geometry_area_m2(missing_usable), 2)
            gap_frac = round(min(1.0, gap_area / study_area_m2), 4) if study_area_m2 > 0 else 0.0
            if gap_area >= 1.0:
                if not cat_fps or (cat == ObservationCategory.ROVER and rover_count == 0):
                    cause = SpatialGapCause.NO_OBSERVATION
                    summary = (
                        f"No in-situ {cat.value} point observations intersect the selected study bounds."
                        if cat == ObservationCategory.ROVER
                        else f"No {cat.value} products intersect the selected study bounds."
                    )
                    action = f"Discover and acquire NASA PDS {cat.value} observations intersecting these bounds."
                elif cat == ObservationCategory.ROVER and rover_count > 0:
                    cause = SpatialGapCause.NO_OBSERVATION
                    summary = f"{rover_count} localized rover stations lie inside study bounds; surrounding unvisited terrain remains unsampled in-situ."
                    action = "Do not extrapolate point rover chemistry/mineralogy across unvisited orbital terrain."
                elif use_elig_for_gap:
                    cause = SpatialGapCause.SCIENTIFICALLY_IRRELEVANT
                    summary = f"Present {cat.value} layer is scientifically ineligible for '{question_focus}' investigation."
                    action = "Supply direct composition/spectral/mineralogical evidence rather than relying on ineligible imagery or telemetry."
                elif fp_union is not None and val_union is None:
                    if unreg_geoms:
                        cause = SpatialGapCause.NOT_SPATIALLY_REGISTERED
                        summary = f"{cat.value} products intersect study bounds via catalog boxes/tiles, but spatial registration or local calibrated acquisition is unverified."
                        action = "Acquire local archive product + companion PDS label and verify registration."
                    else:
                        cause = SpatialGapCause.INVALID_DATA_ONLY
                        summary = f"{cat.value} catalog region lacks validated pixels/records inside the study bounds."
                        action = "Acquire calibrated local raster/table artifact."
                elif val_union is not None and not usable_union.is_empty and _clip_polygons_only(val_union.difference(usable_union)).area > 1e-12:
                    if fp_union is not None and _clip_polygons_only(fp_union.difference(val_union)).area > 1e-12:
                        cause = SpatialGapCause.INVALID_DATA_ONLY
                        summary = f"Oblique {cat.value} NoData corners leave missing pixels inside nominal product bounds."
                        action = "Avoid interpolating across swath edges; acquire overlapping stereo/optical strips."
                    else:
                        cause = SpatialGapCause.INSUFFICIENT_RESOLUTION
                        summary = (
                            f"Only coarse-resolution {cat.value} data (> {intended_resolution_threshold_m:.1f} m/px, "
                            f"best={best_res} m/px) exists in residual gap zones."
                        )
                        action = f"Acquire sub-{intended_resolution_threshold_m:.1f} m/px local product."
                elif val_union is not None and usable_union.is_empty and best_res is not None and best_res > intended_resolution_threshold_m:
                    cause = SpatialGapCause.INSUFFICIENT_RESOLUTION
                    summary = f"Available {cat.value} resolution ({best_res} m/px) is too coarse for <= {intended_resolution_threshold_m:.1f} m analysis."
                    action = f"Acquire <= {intended_resolution_threshold_m:.1f} m/px product."
                elif unreg_geoms and not reg_geoms:
                    cause = SpatialGapCause.NOT_SPATIALLY_REGISTERED
                    summary = f"{cat.value} observations exist but are not spatially registered to the active reference frame."
                    action = "Run spatial registration & tie-point verification."
                elif fp_union is not None and val_union is not None:
                    cause = SpatialGapCause.INVALID_DATA_ONLY
                    summary = f"Swath margins / NoData border pixels leave unmeasured gap inside {cat.value} coverage."
                    action = "Clip corridor outside NoData swath boundary."
                else:
                    cause = SpatialGapCause.NO_OBSERVATION
                    summary = f"Uncovered {cat.value} evidence gap inside study bounds."
                    action = f"Acquire verified {cat.value} data."

                gaps_out.append(
                    SpatialGapRegion(
                        gap_id=f"gap_{cat.value}_{cause.value.lower()}",
                        category=cat,
                        gap_cause=cause,
                        area_m2=gap_area,
                        area_fraction_of_study_region=gap_frac,
                        contributing_product_ids=matching_ids,
                        summary=summary,
                        recommended_action=action,
                        geometry_geojson=mapping(missing_usable),
                    )
                )

    return MultiCategorySpatialCoverageReport(
        study_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
        study_area_m2=study_area_m2,
        reference_dataset_id=ref_ds.id if ref_ds else None,
        intended_resolution_threshold_m=intended_resolution_threshold_m,
        question_focus=question_focus,
        categories=categories_out,
        evidence_gaps=gaps_out,
        overall_limitations=overall_lims,
    )


def irr_only(geoms: List[BaseGeometry]) -> bool:
    return len(geoms) > 0
