"""
MARSCOPE Spatial Coverage & Evidence Gap Assessment
Martian Surface Intelligence & Exploration System

Aggregates per-segment DEM/optical/rover coverage and emits explicit
EvidenceGapCell records for nodata areas, missing orthophotos, and
resolution-limited segments.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    EvidenceGapCell,
)


def assess_coverage_and_gaps(
    *,
    segments: List[CorridorSegmentAssessment],
    segment_bounds: Dict[str, Dict[str, float]],
    native_resolution_m: float,
) -> Tuple[Dict[str, Any], List[EvidenceGapCell]]:
    """Compute corridor-level coverage statistics and explicit EvidenceGapCell items."""
    if not segments:
        return (
            {
                "segment_count": 0,
                "mean_dem_coverage_fraction": 0.0,
                "mean_optical_coverage_fraction": 0.0,
                "unknown_data_fraction": 1.0,
                "segments_with_gaps": 0,
                "segments_with_rover_observations": 0,
            },
            [],
        )

    gaps: List[EvidenceGapCell] = []
    dem_fracs: List[float] = []
    opt_fracs: List[float] = []
    segments_with_gaps = 0
    segments_with_obs = 0

    for seg in segments:
        dem_f = float(seg.coverage.dem_coverage_fraction)
        opt_f = float(seg.coverage.optical_coverage_fraction)
        dem_fracs.append(dem_f)
        opt_fracs.append(opt_f)
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
        if dem_f < 0.95:
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
                        f"({(1.0 - dem_f) * 100:.1f}% nodata/unmapped)."
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
                    reason=f"Segment {seg.segment_id} has no locally verified HiRISE optical coverage.",
                )
            )
        if native_resolution_m > 2.0:
            had_gap = True
            gid = hashlib.sha256(f"res:{seg.segment_id}".encode()).hexdigest()[:10]
            gaps.append(
                EvidenceGapCell(
                    gap_id=f"gap-{gid}",
                    gap_type="insufficient_resolution",
                    segment_id=seg.segment_id,
                    bounds=bounds,
                    reason=(
                        f"DEM native spacing ({native_resolution_m:.1f} m/px) cannot resolve "
                        "astronaut-scale micro-relief or boulders."
                    ),
                )
            )
        if had_gap:
            segments_with_gaps += 1

    mean_dem = sum(dem_fracs) / float(len(dem_fracs))
    mean_opt = sum(opt_fracs) / float(len(opt_fracs))
    summary = {
        "segment_count": len(segments),
        "mean_dem_coverage_fraction": round(mean_dem, 4),
        "mean_optical_coverage_fraction": round(mean_opt, 4),
        "unknown_data_fraction": round(max(0.0, 1.0 - mean_dem), 4),
        "segments_with_gaps": segments_with_gaps,
        "segments_with_rover_observations": segments_with_obs,
        "gap_count": len(gaps),
    }
    return summary, gaps
