"""
MARSCOPE Corridor Uncertainty Assessment
Martian Surface Intelligence & Exploration System

Quantifies DEM spatial/vertical precision limits, nodata fractions, and
unquantified physical unknowns (regolith bearing strength, dust thickness,
subsurface voids, thermal/spectral gaps) without inventing false error bars.
"""

from __future__ import annotations

from typing import List

from app.evidence_intelligence.schemas import (
    CorridorSegmentAssessment,
    CorridorUncertaintySummary,
)


def assess_corridor_uncertainty(
    *,
    segments: List[CorridorSegmentAssessment],
    native_resolution_m: float,
    corridor_valid_fraction: float,
    optical_available: bool,
) -> CorridorUncertaintySummary:
    """Summarize geometric precision, coverage gaps, and unquantified physical unknowns."""
    res_limited = sum(1 for s in segments if s.native_resolution_m > 2.0)
    nodata_segs = sum(1 for s in segments if s.valid_data_coverage_fraction < 0.95)

    dem_note = (
        f"HiRISE DTM ({native_resolution_m:.2f} m/px posting; typical vertical precision ~0.2–0.5 m "
        "relative, not absolute geodetic truth; sub-pixel micro-obstacles < 2 m unresolved)."
        if native_resolution_m <= 2.0
        else f"Regional DEM ({native_resolution_m:.1f} m/px posting; vertical precision coarse; "
        "local astronaut-scale slopes and obstacles unresolved)."
    )

    unquantified: List[str] = [
        "Regolith bearing strength, cohesion, and sinkage (unmeasured from orbital DEM/ortho)",
        "Surface dust thickness and slip/friction coefficient",
        "Subsurface voids or weakly cemented crust",
    ]
    if not optical_available:
        unquantified.append("Local high-resolution optical albedo/shadow verification unavailable")

    return CorridorUncertaintySummary(
        dem_vertical_precision_note=dem_note,
        horizontal_resolution_m=native_resolution_m,
        corridor_valid_fraction=round(corridor_valid_fraction, 4),
        resolution_limited_segments=res_limited,
        nodata_segments=nodata_segs,
        coordinate_uncertainty_note=(
            "IAU2000:49900 planetocentric; rover observation offsets reflect PDS/JPL traverse "
            "localization uncertainty and represent nearby context rather than exact path pixels."
        ),
        unquantified_limitations=unquantified,
    )
