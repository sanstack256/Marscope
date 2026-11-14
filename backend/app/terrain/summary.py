"""
MARSCOPE Terrain Summary & Aggregation Service
Martian Surface Intelligence & Exploration System

Compiles statistical metrics over valid pixels, strictly excluding no-data.
"""

from typing import Dict, Any, List
import numpy as np
from app.schemas.terrain import TerrainSummary, RasterBandStats


def compute_band_stats(data: np.ndarray, units: str) -> RasterBandStats:
    """
    Compute rigorous statistics strictly over finite, non-NaN valid pixels.
    """
    valid = data[~np.isnan(data)]
    total = int(data.size)
    valid_count = int(valid.size)
    nodata_count = total - valid_count
    valid_pct = (valid_count / total * 100.0) if total > 0 else 0.0

    if valid_count > 0:
        return RasterBandStats(
            min_value=round(float(np.min(valid)), 4),
            max_value=round(float(np.max(valid)), 4),
            mean_value=round(float(np.mean(valid)), 4),
            std_dev=round(float(np.std(valid)), 4),
            valid_pixel_count=valid_count,
            nodata_pixel_count=nodata_count,
            valid_data_percentage=round(valid_pct, 2),
            units=units,
        )
    else:
        return RasterBandStats(
            min_value=0.0,
            max_value=0.0,
            mean_value=0.0,
            std_dev=0.0,
            valid_pixel_count=0,
            nodata_pixel_count=total,
            valid_data_percentage=0.0,
            units=units,
        )


def compile_terrain_summary(
    source_dem_id: str,
    study_area_name: str,
    resolution_m: float,
    crs: str,
    elevation: np.ndarray,
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray = None,
    roughness_tri: np.ndarray = None,
    critical_slope_threshold: float = 25.0,
    warnings: List[str] = None,
) -> TerrainSummary:
    """
    Compile complete terrain summary with slope threshold assessment.
    """
    elev_stats = compute_band_stats(elevation, "meters")
    slope_stats = compute_band_stats(slope_deg, "degrees")
    
    aspect_stats = compute_band_stats(aspect_deg, "degrees_clockwise_north") if aspect_deg is not None else None
    rough_stats = compute_band_stats(roughness_tri, "meters") if roughness_tri is not None else None

    # Calculate critical slope hazard coverage
    valid_slopes = slope_deg[~np.isnan(slope_deg)]
    if valid_slopes.size > 0:
        critical_count = np.sum(valid_slopes > critical_slope_threshold)
        crit_pct = round(float(critical_count / valid_slopes.size * 100.0), 2)
    else:
        crit_pct = 0.0

    return TerrainSummary(
        source_dem_id=source_dem_id,
        study_area_name=study_area_name,
        resolution_meters_per_pixel=round(resolution_m, 2),
        crs=crs,
        elevation_stats=elev_stats,
        slope_stats=slope_stats,
        aspect_stats=aspect_stats,
        roughness_stats=rough_stats,
        critical_slope_threshold_deg=critical_slope_threshold,
        critical_slope_coverage_pct=crit_pct,
        quality_warnings=warnings or [],
    )
