"""
MARSCOPE Corridor Optical Evidence Assessment
Martian Surface Intelligence & Exploration System

Runs deterministic multi-scale HiRISE optical analysis over the route corridor
bounding box, associates validated candidates and rejected false positives with
corridor segments, and reports genuine optical coverage and product availability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.evidence_intelligence.schemas import CorridorSegmentAssessment
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.terrain.optical_analysis import (
    OpticalCandidateFeature,
    RejectedOpticalCandidate,
    analyze_optical_region,
)


def _nearest_segment_for_point(
    lat: float, lon_east: float, segments: List[CorridorSegmentAssessment]
) -> Optional[str]:
    best_id: Optional[str] = None
    best_d = float("inf")
    for seg in segments:
        mid_lat = 0.5 * (seg.start_coord.lat + seg.end_coord.lat)
        mid_lon = 0.5 * (seg.start_coord.lon_east + seg.end_coord.lon_east)
        d = mars_great_circle_distance_meters(lat, lon_east, mid_lat, mid_lon)
        if d < best_d:
            best_d = d
            best_id = seg.segment_id
    return best_id


def assess_corridor_optical_evidence(
    *,
    catalog_service: Any,
    raw_dir: Path,
    ortho_dataset_id: Optional[str],
    dem_bounds: Dict[str, float],
    segments: List[CorridorSegmentAssessment],
    max_candidates: int = 36,
) -> Tuple[
    List[OpticalCandidateFeature],
    List[RejectedOpticalCandidate],
    float,
    str,
    Dict[str, Any],
]:
    """
    Execute deterministic optical analysis on the corridor's HiRISE ortho product
    (if locally acquired & available) and attach candidate IDs to nearest segments.
    """
    if not ortho_dataset_id:
        return (
            [],
            [],
            0.0,
            "No locally acquired HiRISE orthophoto covering this corridor.",
            {"available": False, "dataset_id": None},
        )

    try:
        res = analyze_optical_region(
            catalog_service=catalog_service,
            raw_dir=raw_dir,
            dataset_id=ortho_dataset_id,
            min_lat=dem_bounds["min_lat"],
            max_lat=dem_bounds["max_lat"],
            min_lon=dem_bounds["min_lon"],
            max_lon=dem_bounds["max_lon"],
            max_candidates=max_candidates,
        )
    except Exception as exc:
        return (
            [],
            [],
            0.0,
            f"Optical analysis unavailable for {ortho_dataset_id}: {exc}",
            {"available": False, "dataset_id": ortho_dataset_id, "error": str(exc)},
        )

    valid_cov = float(res.valid_coverage_fraction) if res.available else 0.0
    note = (
        f"HiRISE ortho {res.product_id or ortho_dataset_id} ({valid_cov * 100:.1f}% valid coverage); "
        f"{len(res.candidates)} candidates, {len(res.rejected_candidates)} rejected false positives."
        if res.available
        else (res.unavailable_reason or f"Optical analysis unavailable for {ortho_dataset_id}.")
    )

    for cand in res.candidates:
        seg_id = _nearest_segment_for_point(cand.latitude, cand.longitude_east, segments)
        if seg_id:
            for seg in segments:
                if seg.segment_id == seg_id:
                    seg.optical_candidate_ids.append(cand.feature_id)
                    break

    meta = {
        "available": res.available,
        "dataset_id": res.ortho_dataset_id or ortho_dataset_id,
        "source_product_id": res.product_id or ortho_dataset_id,
        "native_pixel_scale_m": res.native_pixel_scale_m,
        "bounds": res.bounds,
        "candidate_count": len(res.candidates),
        "rejected_count": len(res.rejected_candidates),
        "analysis_note": note,
    }
    return (
        res.candidates,
        res.rejected_candidates,
        valid_cov,
        note,
        meta,
    )
