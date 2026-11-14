"""
MARSCOPE Spatial Coverage & Evidence Gap Assessment
Martian Surface Intelligence & Exploration System

Aggregates per-segment DEM/optical/rover coverage without zero-vs-None truthy bugs
or fabricated polygon areas, and emits explicit EvidenceGapCell records backed by
versioned completeness policies.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    EvidenceGapCell,
)


class CoveragePolicySpec(BaseModel):
    """Explicitly versioned coverage and resolution completeness threshold policy."""

    policy_id: str = "MARSCOPE-COV"
    policy_version: str = "coverage_policy_v1.0"
    classification: str = "engineering_screen"
    min_dem_valid_coverage_fraction: float = 0.95
    max_dem_spacing_for_local_slope_m: float = 2.0


COVERAGE_POLICY = CoveragePolicySpec()


def assess_coverage_and_gaps(
    *,
    segments: List[CorridorSegmentAssessment],
    segment_bounds: Dict[str, Dict[str, float]],
    native_resolution_m: float,
    policy: Optional[CoveragePolicySpec] = None,
) -> Tuple[Dict[str, Any], List[EvidenceGapCell]]:
    """Compute corridor-level coverage statistics and explicit EvidenceGapCell items."""
    pol = policy or COVERAGE_POLICY
    if not segments:
        return (
            {
                "segment_count": 0,
                "policy_id": pol.policy_id,
                "policy_version": pol.policy_version,
                "corridor_area_measured": False,
                "mean_dem_coverage_fraction": 0.0,
                "mean_optical_coverage_fraction": 0.0,
                "mean_optical_footprint_coverage_fraction": 0.0,
                "mean_valid_optical_pixel_coverage_fraction": 0.0,
                "unknown_data_fraction": 1.0,
                "segments_with_gaps": 0,
                "segments_with_rover_observations": 0,
                "gap_count": 0,
            },
            [],
        )

    gaps: List[EvidenceGapCell] = []
    dem_fracs: List[float] = []
    opt_fracs: List[float] = []
    opt_foot_fracs: List[float] = []
    area_weights: List[float] = []
    measured_areas: List[float] = []
    segments_with_gaps = 0
    segments_with_obs = 0
    all_areas_measured = True

    for seg in segments:
        dem_f = float(seg.coverage.dem_coverage_fraction)
        # Preserve explicit 0.0 optical coverage! Never use truthy `or` on floats.
        if seg.coverage.valid_optical_pixel_coverage_fraction is not None:
            opt_f = float(seg.coverage.valid_optical_pixel_coverage_fraction)
        elif seg.coverage.optical_coverage_fraction is not None:
            opt_f = float(seg.coverage.optical_coverage_fraction)
        else:
            opt_f = 0.0

        if seg.coverage.optical_footprint_coverage_fraction is not None:
            foot_f = float(seg.coverage.optical_footprint_coverage_fraction)
        else:
            foot_f = 1.0 if opt_f > 0.0 else 0.0

        # Never fabricate polygon m^2 using geodesic_distance_m * 60.0
        raw_area = (
            seg.coverage.segment_corridor_area_m2
            if seg.coverage.segment_corridor_area_m2 is not None
            else seg.corridor_area_m2
        )
        if raw_area is not None and float(raw_area) > 0.0:
            measured_val = float(raw_area)
            measured_areas.append(measured_val)
            area_weights.append(measured_val)
        else:
            all_areas_measured = False
            # Fall back transparently to linear geodesic distance weighting without claiming m^2 polygon area
            area_weights.append(max(1.0, float(seg.geodesic_distance_m)))

        dem_fracs.append(dem_f)
        opt_fracs.append(opt_f)
        opt_foot_fracs.append(foot_f)

        if seg.coverage.rover_observation_count > 0:
            segments_with_obs += 1

        bounds = segment_bounds.get(
            seg.segment_id,
            {
                "min_lat": min(seg.start_coord.lat, seg.end_coord.lat),
                "max_lat": max(seg.start_coord.lat, seg.end_coord.lat),
                "min_lon": min(seg.start_coord.lon_east, seg.end_coord.lon_east),
                "max_lon": max(seg.start_coord.lon_east, seg.end_coord.lon_east),
            },
        )
        had_gap = False
        if dem_f < pol.min_dem_valid_coverage_fraction:
            had_gap = True
            gid = hashlib.sha256(f"nodata:{seg.segment_id}".encode()).hexdigest()[:10]
            gaps.append(
                EvidenceGapCell(
                    gap_id=f"gap-{gid}",
                    gap_type="nodata_region" if dem_f > 0.0 else "no_dem_coverage",
                    segment_id=seg.segment_id,
                    bounds=bounds,
                    reason=(
                        f"Segment {seg.segment_id} valid DEM coverage is {dem_f * 100:.1f}% "
                        f"({(1.0 - dem_f) * 100:.1f}% nodata/unmapped, below {pol.min_dem_valid_coverage_fraction*100:.0f}% policy threshold)."
                    ),
                )
            )
        if opt_f <= 0.0:
            had_gap = True
            gid = hashlib.sha256(f"noopt:{seg.segment_id}".encode()).hexdigest()[:10]
            gaps.append(
                EvidenceGapCell(
                    gap_id=f"gap-{gid}",
                    gap_type="no_optical_coverage",
                    segment_id=seg.segment_id,
                    bounds=bounds,
                    reason=f"Segment {seg.segment_id} has zero locally verified HiRISE optical pixel coverage.",
                )
            )
        if native_resolution_m > pol.max_dem_spacing_for_local_slope_m:
            had_gap = True
            gid = hashlib.sha256(f"res:{seg.segment_id}".encode()).hexdigest()[:10]
            gaps.append(
                EvidenceGapCell(
                    gap_id=f"gap-{gid}",
                    gap_type="insufficient_resolution",
                    segment_id=seg.segment_id,
                    bounds=bounds,
                    reason=(
                        f"DEM native spacing ({native_resolution_m:.1f} m/px) exceeds {pol.max_dem_spacing_for_local_slope_m:.1f} m/px "
                        "engineering screening policy and cannot resolve astronaut-scale micro-relief."
                    ),
                )
            )
        if had_gap:
            segments_with_gaps += 1

    tot_w = max(1e-6, sum(area_weights))
    w_dem = sum(d * w for d, w in zip(dem_fracs, area_weights)) / tot_w
    w_opt = sum(o * w for o, w in zip(opt_fracs, area_weights)) / tot_w
    w_foot = sum(f * w for f, w in zip(opt_foot_fracs, area_weights)) / tot_w

    total_area_m2: Optional[float] = round(sum(measured_areas), 2) if (all_areas_measured and measured_areas) else None
    summary = {
        "segment_count": len(segments),
        "policy_id": pol.policy_id,
        "policy_version": pol.policy_version,
        "policy_classification": pol.classification,
        "corridor_area_measured": bool(all_areas_measured and measured_areas),
        "weighting_basis": "measured_corridor_polygon_area_m2" if (all_areas_measured and measured_areas) else "geodesic_segment_length_m",
        "total_corridor_area_m2": total_area_m2,
        "dem_valid_area_m2": round(total_area_m2 * w_dem, 2) if total_area_m2 is not None else None,
        "optical_covered_area_m2": round(total_area_m2 * w_opt, 2) if total_area_m2 is not None else None,
        "mean_dem_coverage_fraction": round(w_dem, 4),
        "mean_optical_coverage_fraction": round(w_opt, 4),
        "mean_optical_footprint_coverage_fraction": round(w_foot, 4),
        "mean_valid_optical_pixel_coverage_fraction": round(w_opt, 4),
        "unknown_data_fraction": round(max(0.0, 1.0 - w_dem), 4),
        "segments_with_gaps": segments_with_gaps,
        "segments_with_rover_observations": segments_with_obs,
        "gap_count": len(gaps),
    }
    return summary, gaps
