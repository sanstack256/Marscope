"""
MARSCOPE Spatially Explicit Traversal Cost Surface Engine (Prompt 13, 16, 20 Part 3)
Martian Surface Intelligence & Exploration System

Generates a verifiable per-cell TraversalCostSurface over a bounded study window:
  - Retains source DEM identity, processing version, traversal model version,
    and scenario ID/version.
  - Preserves null cost on unknown/no-data terrain (never assigns zero cost).
  - Explicitly distinguishes unknown terrain from user-configured scenario
    exclusions and never emits 'safe' or 'unsafe' labels.
  - Classifies each cell with the 10-state TraversabilityEvidenceState (Prompt 20 Part 3.3)
    and surfaces unmeasured soil/material properties (bearing capacity, shear strength,
    boot traction, sinkage, dust stability, subsurface voids = UNKNOWN_UNMEASURED).
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from app.mobility.models import (
    CellTraversalAvailabilityState,
    TerrainCoverageState,
    TraversabilityEvidenceState,
    UNMEASURED_SOIL_PROPERTIES_DEFAULT,
)
from app.mobility.schemas import (
    CostSurfaceCellRecord,
    CostSurfaceSummary,
    MobilityScenario,
)
from app.mobility.terrain_features import extract_windowed_terrain_features
from app.mobility.traversal_model import (
    TRAVERSAL_MODEL_ID,
    TRAVERSAL_MODEL_VERSION,
    evaluate_cell_or_segment_traversal,
)
from app.schemas.dataset import Dataset
from app.terrain.optical_analysis import PAIRED_ORTHO_MAP
from app.terrain.processor import PROCESSING_VERSION
from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty


def _classify_cell_traversability_evidence(
    *,
    coverage_state: TerrainCoverageState,
    avail_state: CellTraversalAvailabilityState,
    native_res_m: float,
    has_optical: bool,
    registration_failed: bool,
    has_candidate_obstacle: bool,
) -> TraversabilityEvidenceState:
    if registration_failed:
        return TraversabilityEvidenceState.UNKNOWN_REGISTRATION_FAILURE
    if coverage_state != TerrainCoverageState.VALID_SOURCE_DATA:
        return TraversabilityEvidenceState.UNKNOWN_NO_VALID_TERRAIN
    if avail_state == CellTraversalAvailabilityState.EXPLICIT_SCENARIO_EXCLUSION:
        return TraversabilityEvidenceState.KNOWN_GEOMETRIC_CONSTRAINT
    if has_candidate_obstacle:
        return TraversabilityEvidenceState.CANDIDATE_OBSTACLE_PRESENT
    if native_res_m > 5.0:
        return TraversabilityEvidenceState.UNKNOWN_INSUFFICIENT_RESOLUTION
    if avail_state == CellTraversalAvailabilityState.INSUFFICIENT_SCENARIO_PARAMETERS:
        return TraversabilityEvidenceState.NOT_EVALUATED
    if not has_optical:
        return TraversabilityEvidenceState.UNKNOWN_NO_OPTICAL_EVIDENCE
    if avail_state == CellTraversalAvailabilityState.EVALUATED:
        return TraversabilityEvidenceState.EVALUATED_WITH_AVAILABLE_EVIDENCE
    return TraversabilityEvidenceState.EVALUATED_WITH_LIMITATIONS


def build_traversal_cost_surface(
    *,
    dataset: Dataset,
    raw_dir: Path,
    requested_bounds: Dict[str, float],
    scenario: MobilityScenario,
    max_returned_cells: int = 2500,
    candidate_obstacles: Optional[List[Dict[str, Any]]] = None,
    spatial_registration_status: str = "ALIGNED_HIGH_PRECISION",
) -> CostSurfaceSummary:
    """
    Build a spatially explicit `CostSurfaceSummary` over `requested_bounds`
    for `dataset` and `scenario`.
    """
    win_features = extract_windowed_terrain_features(
        dataset=dataset,
        raw_dir=raw_dir,
        requested_bounds=requested_bounds,
        roughness_radius_meters=scenario.roughness_window_radius_m,
        max_returned_cells=max_returned_cells,
    )

    dx_m = win_features.dx_meters
    dy_m = win_features.dy_meters
    diag_m = math.hypot(dx_m, dy_m)
    nominal_crossing_m = 0.5 * (dx_m + dy_m)
    native_res_m = float(dataset.horizontal_resolution_meters or nominal_crossing_m)

    paired_ortho_id = PAIRED_ORTHO_MAP.get(dataset.id)
    has_optical = bool(paired_ortho_id)
    reg_failed = spatial_registration_status.upper() in {"REGISTRATION_FAILED", "MISALIGNED_UNUSABLE"}

    obs_list = candidate_obstacles or []
    accepted_obs_count = sum(1 for o in obs_list if str(o.get("review_status", "")).lower() == "accepted")

    avail_counts: Dict[str, int] = {s.value: 0 for s in CellTraversalAvailabilityState}
    ev_state_counts: Dict[str, int] = {s.value: 0 for s in TraversabilityEvidenceState}
    cost_cells: List[CostSurfaceCellRecord] = []
    eff_speeds: List[float] = []
    crossing_times: List[float] = []

    for tf_cell in win_features.cells:
        seg_eval = evaluate_cell_or_segment_traversal(
            segment_index=(tf_cell.row * win_features.grid_shape["cols"]) + tf_cell.col,
            lat=tf_cell.center_lat,
            lon_east=tf_cell.center_lon_east,
            horizontal_distance_meters=nominal_crossing_m,
            coverage_state=tf_cell.coverage_state,
            elevation_meters=tf_cell.elevation_meters,
            elevation_delta_meters=None,
            slope_deg=tf_cell.slope_deg,
            aspect_deg=tf_cell.aspect_deg,
            roughness_tri_meters=tf_cell.roughness_tri_meters,
            scenario=scenario,
        )

        avail_state = seg_eval.traversal_availability_state
        avail_counts[avail_state.value] += 1

        matched_obs_ids: List[str] = []
        for obs in obs_list:
            b = obs.get("bounds") or {}
            if (
                b.get("min_lat", 999.0) <= tf_cell.center_lat <= b.get("max_lat", -999.0)
                and b.get("min_lon", 999.0) <= tf_cell.center_lon_east <= b.get("max_lon", -999.0)
            ):
                if str(obs.get("review_status", "")).lower() != "rejected":
                    matched_obs_ids.append(str(obs.get("candidate_id", "obs")))

        ev_st = _classify_cell_traversability_evidence(
            coverage_state=tf_cell.coverage_state,
            avail_state=avail_state,
            native_res_m=native_res_m,
            has_optical=has_optical,
            registration_failed=reg_failed,
            has_candidate_obstacle=(len(matched_obs_ids) > 0),
        )
        ev_state_counts[ev_st.value] += 1

        cost_s_per_m: Optional[float] = None
        crossing_time_s: Optional[float] = None
        if (
            avail_state == CellTraversalAvailabilityState.EVALUATED
            and seg_eval.effective_speed_m_per_s is not None
            and seg_eval.effective_speed_m_per_s > 0.0
        ):
            cost_s_per_m = round(1.0 / seg_eval.effective_speed_m_per_s, 6)
            crossing_time_s = seg_eval.adjusted_time_seconds
            eff_speeds.append(seg_eval.effective_speed_m_per_s)
            if crossing_time_s is not None:
                crossing_times.append(crossing_time_s)

        cost_cells.append(
            CostSurfaceCellRecord(
                row=tf_cell.row,
                col=tf_cell.col,
                center_lat=tf_cell.center_lat,
                center_lon_east=tf_cell.center_lon_east,
                cell_width_meters=round(dx_m, 3),
                cell_height_meters=round(dy_m, 3),
                cell_diagonal_meters=round(diag_m, 3),
                coverage_state=tf_cell.coverage_state,
                elevation_meters=tf_cell.elevation_meters,
                slope_deg=tf_cell.slope_deg,
                aspect_deg=tf_cell.aspect_deg,
                roughness_tri_meters=tf_cell.roughness_tri_meters,
                traversal_availability_state=avail_state,
                traversability_evidence_state=ev_st,
                candidate_obstacle_ids=matched_obs_ids,
                effective_speed_m_per_s=seg_eval.effective_speed_m_per_s,
                traversal_cost_seconds_per_meter=cost_s_per_m,
                cell_crossing_time_seconds=crossing_time_s,
                slope_speed_factor=seg_eval.slope_speed_factor,
                roughness_speed_factor=seg_eval.roughness_speed_factor,
                reason=seg_eval.unavailable_or_exclusion_reason,
            )
        )

    cs_seed = json.dumps(
        {
            "dataset_id": dataset.id,
            "bounds": win_features.requested_bounds,
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.version,
            "model": TRAVERSAL_MODEL_ID,
            "model_version": TRAVERSAL_MODEL_VERSION,
        },
        sort_keys=True,
    )
    cs_id = f"cs_{hashlib.sha256(cs_seed.encode('utf-8')).hexdigest()[:12]}"

    limitations = list(win_features.limitations)
    limitations.append(
        "Cost surface provides per-cell traversal effort inputs for future mission planning; "
        "route optimization and pathfinding are intentionally not performed in this engine."
    )
    if not eff_speeds:
        limitations.append(
            "No cells produced numeric traversal times (either reference_walking_speed_m_per_s was not "
            "configured, or all cells were unknown/excluded)."
        )

    elev_prof = inspect_dataset_elevation_uncertainty(
        dataset=dataset,
        raw_dir=raw_dir,
        processed_dir=raw_dir.parent / "processed",
    )
    unc_status = elev_prof.overall_elevation_uncertainty_status.value

    trav_notes = [
        "3-state traversability preserves UNKNOWN_TERRAIN, EXPLICIT_SCENARIO_EXCLUSION, and EVALUATED without merging unknown gaps into safe terrain.",
        "10-state TraversabilityEvidenceState explicitly distinguishes EVALUATED_WITH_AVAILABLE_EVIDENCE, "
        "EVALUATED_WITH_LIMITATIONS, KNOWN_GEOMETRIC_CONSTRAINT, CANDIDATE_OBSTACLE_PRESENT, "
        "UNKNOWN_INSUFFICIENT_RESOLUTION, UNKNOWN_NO_VALID_TERRAIN, UNKNOWN_NO_OPTICAL_EVIDENCE, "
        "UNKNOWN_REGISTRATION_FAILURE, UNKNOWN_UNMEASURED_MATERIAL_PROPERTIES, and NOT_EVALUATED.",
        "Elevation uncertainty status is strictly separated from cost-surface speed calculations.",
    ]

    return CostSurfaceSummary(
        cost_surface_id=cs_id,
        dataset_id=dataset.id,
        source_product_id=dataset.product_id,
        processing_version=PROCESSING_VERSION,
        traversal_model_id=TRAVERSAL_MODEL_ID,
        traversal_model_version=TRAVERSAL_MODEL_VERSION,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.version,
        crs=win_features.crs,
        requested_bounds=win_features.requested_bounds,
        analysis_footprint_bounds=win_features.analysis_footprint_bounds,
        grid_shape=win_features.grid_shape,
        dx_meters=win_features.dx_meters,
        dy_meters=win_features.dy_meters,
        coverage_state_counts=win_features.coverage_state_counts,
        traversal_availability_counts=avail_counts,
        traversability_evidence_state_counts=ev_state_counts,
        evaluated_cell_count=avail_counts[CellTraversalAvailabilityState.EVALUATED.value],
        unknown_terrain_cell_count=avail_counts[CellTraversalAvailabilityState.UNKNOWN_TERRAIN.value],
        excluded_by_scenario_cell_count=avail_counts[
            CellTraversalAvailabilityState.EXPLICIT_SCENARIO_EXCLUSION.value
        ],
        candidate_obstacle_count=len(obs_list),
        accepted_obstacle_count=accepted_obs_count,
        optical_coverage_available=has_optical,
        spatial_registration_status=spatial_registration_status,
        unmeasured_soil_properties=dict(UNMEASURED_SOIL_PROPERTIES_DEFAULT),
        min_effective_speed_m_per_s=round(float(np.min(eff_speeds)), 4) if eff_speeds else None,
        max_effective_speed_m_per_s=round(float(np.max(eff_speeds)), 4) if eff_speeds else None,
        mean_effective_speed_m_per_s=round(float(np.mean(eff_speeds)), 4) if eff_speeds else None,
        min_cell_crossing_time_seconds=round(float(np.min(crossing_times)), 3) if crossing_times else None,
        max_cell_crossing_time_seconds=round(float(np.max(crossing_times)), 3) if crossing_times else None,
        mean_cell_crossing_time_seconds=round(float(np.mean(crossing_times)), 3) if crossing_times else None,
        cells=cost_cells,
        limitations=limitations,
        uncertainty_status=unc_status,
        nominal_vertical_precision_m=dataset.vertical_resolution_meters,
        has_per_pixel_error_raster=False,
        traversability_state_notes=trav_notes,
    )
