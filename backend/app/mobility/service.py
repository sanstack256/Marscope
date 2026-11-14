"""
MARSCOPE Human Mobility Intelligence Orchestration Service
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ingestion.catalog import DatasetCatalogService
from app.mobility.cost_surface import build_traversal_cost_surface
from app.mobility.coverage import evaluate_region_coverage_intelligence
from app.mobility.mobility_scenario import MobilityScenarioRegistry
from app.mobility.provenance import build_terrain_data_inventory
from app.mobility.schemas import (
    CostSurfaceSummary,
    CoverageIntelligenceResponse,
    ElevationProfileRequest,
    ElevationProfileResponse,
    GeoPoint,
    MobilityEngineStatusResponse,
    MobilityEvaluationRequest,
    MobilityEvaluationResponse,
    MobilityScenario,
    MobilityScenarioCreateRequest,
    TerrainFeaturesWindowResponse,
)
from app.mobility.terrain_features import (
    compute_elevation_profile,
    extract_windowed_terrain_features,
)
from app.mobility.traversal_model import (
    TRAVERSAL_MODEL_ID,
    TRAVERSAL_MODEL_VERSION,
    evaluate_cell_or_segment_traversal,
    evaluate_transect_traversal,
)
from app.mobility.uncertainty import build_mobility_uncertainty_summary
from app.schemas.dataset import Dataset
from app.terrain.processor import PROCESSING_VERSION


class HumanMobilityService:
    """
    Coordinates terrain inventory, resolution suitability, windowed feature extraction,
    spatial coverage intelligence, elevation gain/loss profiles, explicit mobility
    scenarios, and traversal cost surfaces.
    """

    def __init__(
        self,
        *,
        catalog_service: DatasetCatalogService,
        raw_dir: Path,
        processed_dir: Path,
    ):
        self.catalog_service = catalog_service
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.scenario_registry = MobilityScenarioRegistry(
            processed_dir / "mobility_scenarios.json"
        )

    def _resolve_dem_dataset(self, dataset_id: str) -> Dataset:
        ds = self.catalog_service.get_dataset(dataset_id)
        if ds is None:
            raise LookupError(f"DEM dataset '{dataset_id}' not found in MARSCOPE catalog.")
        if "DEM" not in ds.product_type.upper() and "ELEVATION" not in ds.product_type.upper():
            raise ValueError(
                f"Dataset '{dataset_id}' (product_type='{ds.product_type}') is not a DEM raster product."
            )
        return ds

    def get_status(self) -> MobilityEngineStatusResponse:
        inventory = build_terrain_data_inventory(
            catalog_service=self.catalog_service,
            raw_dir=self.raw_dir,
            processed_dir=self.processed_dir,
        )
        local_dems = [item for item in inventory if item.present_locally]
        proc_dems = [item for item in inventory if item.processed_locally]
        active_id = (
            proc_dems[0].dataset_id
            if proc_dems
            else (local_dems[0].dataset_id if local_dems else None)
        )

        return MobilityEngineStatusResponse(
            processing_version=PROCESSING_VERSION,
            traversal_model_id=TRAVERSAL_MODEL_ID,
            traversal_model_version=TRAVERSAL_MODEL_VERSION,
            route_optimization_enabled=True,
            safety_certification_enabled=False,
            active_dem_dataset_id=active_id,
            available_dem_count=len(inventory),
            locally_downloaded_dem_count=len(local_dems),
            processed_dem_count=len(proc_dems),
            registered_scenarios_count=len(self.scenario_registry.list_scenarios()),
            terrain_inventory=inventory,
            capabilities={
                "windowed_terrain_features": len(local_dems) > 0,
                "horn_3x3_slope_and_aspect": len(local_dems) > 0,
                "metric_tri_roughness": len(local_dems) > 0,
                "spatial_coverage_5_state_intelligence": len(local_dems) > 0,
                "elevation_gain_loss_profile": len(local_dems) > 0,
                "configurable_mobility_scenarios": True,
                "transparent_kinematic_traversal_model": len(local_dems) > 0,
                "spatially_explicit_cost_surface": len(local_dems) > 0,
                "route_optimization": False,
                "physiological_or_oxygen_consumption_model": False,
            },
            scientific_constraints=[
                "Requested DEM bounding boxes are never silently expanded; regions smaller than 3x3 source pixels return a structured InsufficientCoverageReport.",
                "MOLA 4 ppd (~6.6 km/pixel) supports regional elevation and regional TRI roughness only, never local human-scale slope or foot-level obstacle detection.",
                "No arbitrary default walking speed, default 25 deg safety threshold, fatigue model, oxygen model, or 'safe/unsafe' terrain classification is used.",
                "Unknown or no-data terrain cells preserve null traversal cost and are never assigned zero cost.",
            ],
        )

    def get_terrain_features(
        self,
        *,
        dataset_id: str,
        bounds: Dict[str, float],
        roughness_radius_meters: Optional[float] = None,
    ) -> TerrainFeaturesWindowResponse:
        ds = self._resolve_dem_dataset(dataset_id)
        return extract_windowed_terrain_features(
            dataset=ds,
            raw_dir=self.raw_dir,
            requested_bounds=bounds,
            roughness_radius_meters=roughness_radius_meters,
        )

    def get_coverage_intelligence(
        self,
        *,
        dataset_id: str,
        bounds: Dict[str, float],
        roughness_radius_meters: Optional[float] = None,
    ) -> CoverageIntelligenceResponse:
        ds = self._resolve_dem_dataset(dataset_id)
        return evaluate_region_coverage_intelligence(
            dataset=ds,
            raw_dir=self.raw_dir,
            requested_bounds=bounds,
            roughness_radius_meters=roughness_radius_meters,
        )

    def create_scenario(self, req: MobilityScenarioCreateRequest) -> MobilityScenario:
        return self.scenario_registry.create_scenario(req)

    def list_scenarios(self) -> List[MobilityScenario]:
        return self.scenario_registry.list_scenarios()

    def get_scenario(self, scenario_id: str) -> MobilityScenario:
        sc = self.scenario_registry.get_scenario(scenario_id)
        if sc is None:
            raise LookupError(f"MobilityScenario '{scenario_id}' not found.")
        return sc

    def compute_profile(self, req: ElevationProfileRequest) -> ElevationProfileResponse:
        ds = self._resolve_dem_dataset(req.dataset_id)
        wps: List[GeoPoint] = (
            list(req.waypoints)
            if (req.waypoints and len(req.waypoints) >= 2)
            else [req.start, req.end]  # type: ignore[list-item]
        )
        return compute_elevation_profile(
            dataset=ds,
            raw_dir=self.raw_dir,
            waypoints=wps,
            sample_count=req.sample_count,
            sampling_method=req.sampling_method,
        )

    def get_cost_surface_metadata(
        self,
        *,
        dataset_id: str,
        bounds: Dict[str, float],
        scenario_id: Optional[str] = None,
        reference_walking_speed_m_per_s: Optional[float] = None,
        planning_max_slope_deg: Optional[float] = None,
        planning_max_roughness_m: Optional[float] = None,
    ) -> CostSurfaceSummary:
        ds = self._resolve_dem_dataset(dataset_id)
        if scenario_id:
            scenario = self.get_scenario(scenario_id)
        else:
            scenario = self.scenario_registry.build_scenario(
                MobilityScenarioCreateRequest(
                    name="Ad-hoc Cost Surface Inspection Scenario",
                    reference_walking_speed_m_per_s=reference_walking_speed_m_per_s,
                    planning_max_slope_deg=planning_max_slope_deg,
                    planning_max_roughness_m=planning_max_roughness_m,
                )
            )
        return build_traversal_cost_surface(
            dataset=ds,
            raw_dir=self.raw_dir,
            requested_bounds=bounds,
            scenario=scenario,
        )

    def evaluate_mobility(self, req: MobilityEvaluationRequest) -> MobilityEvaluationResponse:
        ds = self._resolve_dem_dataset(req.dataset_id)
        if req.scenario_id:
            scenario = self.get_scenario(req.scenario_id)
        elif req.inline_scenario is not None:
            scenario = self.scenario_registry.build_scenario(req.inline_scenario)
        else:
            scenario = self.scenario_registry.build_scenario(
                MobilityScenarioCreateRequest(
                    name="Unconfigured Physical-Only Inspection Scenario",
                    description="No walking speed or planning exclusions configured; evaluates physical terrain measurements only.",
                )
            )

        now_utc = datetime.now(timezone.utc).isoformat()
        eval_id = f"mev_{hashlib.sha256(f'{ds.id}|{scenario.scenario_id}|{now_utc}'.encode()).hexdigest()[:12]}"

        # Determine evaluation mode:
        # 1. Study window (cost surface)
        # 2. Transect (waypoints or scenario start->destination)
        # 3. Single point
        if req.study_bounds is not None or (
            req.point is None
            and req.waypoints is None
            and scenario.study_bounds is not None
        ):
            sb = req.study_bounds or scenario.study_bounds
            assert sb is not None
            b_dict = {
                "min_lat": sb.min_lat,
                "max_lat": sb.max_lat,
                "min_lon": sb.min_lon,
                "max_lon": sb.max_lon,
            }
            win_features = extract_windowed_terrain_features(
                dataset=ds,
                raw_dir=self.raw_dir,
                requested_bounds=b_dict,
                roughness_radius_meters=scenario.roughness_window_radius_m,
            )
            cs = build_traversal_cost_surface(
                dataset=ds,
                raw_dir=self.raw_dir,
                requested_bounds=b_dict,
                scenario=scenario,
            )
            phys_meas: Dict[str, Any] = {
                "requested_bounds": win_features.requested_bounds,
                "analysis_footprint_bounds": win_features.analysis_footprint_bounds,
                "dx_meters": win_features.dx_meters,
                "dy_meters": win_features.dy_meters,
                "grid_shape": win_features.grid_shape,
                "elevation_stats": win_features.elevation_stats.model_dump(),
                "slope_stats": win_features.slope_stats.model_dump(),
                "aspect_stats": win_features.aspect_stats.model_dump(),
                "roughness_stats": win_features.roughness_stats.model_dump(),
                "coverage_state_counts": win_features.coverage_state_counts,
            }
            scen_est: Dict[str, Any] = {
                "cost_surface_id": cs.cost_surface_id,
                "traversal_time_available": cs.evaluated_cell_count > 0,
                "evaluated_cell_count": cs.evaluated_cell_count,
                "unknown_terrain_cell_count": cs.unknown_terrain_cell_count,
                "excluded_by_scenario_cell_count": cs.excluded_by_scenario_cell_count,
                "traversal_availability_counts": cs.traversal_availability_counts,
                "min_effective_speed_m_per_s": cs.min_effective_speed_m_per_s,
                "max_effective_speed_m_per_s": cs.max_effective_speed_m_per_s,
                "mean_effective_speed_m_per_s": cs.mean_effective_speed_m_per_s,
                "min_cell_crossing_time_seconds": cs.min_cell_crossing_time_seconds,
                "max_cell_crossing_time_seconds": cs.max_cell_crossing_time_seconds,
                "mean_cell_crossing_time_seconds": cs.mean_cell_crossing_time_seconds,
                "safety_assessment": "not_performed_no_validated_safety_limits",
            }
            return MobilityEvaluationResponse(
                evaluation_id=eval_id,
                evaluated_at_utc=now_utc,
                evaluation_mode="study_window",
                dataset_id=ds.id,
                source_product_id=ds.product_id,
                crs=win_features.crs,
                traversal_model_id=TRAVERSAL_MODEL_ID,
                traversal_model_version=TRAVERSAL_MODEL_VERSION,
                scenario=scenario,
                physical_terrain_measurements=phys_meas,
                scenario_traversal_estimates=scen_est,
                segments=[],
                cost_surface=cs,
                resolution_suitability=win_features.resolution_suitability,
                uncertainty=win_features.uncertainty,
                provenance=win_features.provenance,
                limitations=cs.limitations,
            )

        waypoints: Optional[List[GeoPoint]] = None
        if req.waypoints and len(req.waypoints) >= 2:
            waypoints = list(req.waypoints)
        elif scenario.astronaut_position is not None and scenario.destination_position is not None and req.point is None:
            waypoints = [scenario.astronaut_position, scenario.destination_position]

        if waypoints is not None:
            prof = compute_elevation_profile(
                dataset=ds,
                raw_dir=self.raw_dir,
                waypoints=waypoints,
                sample_count=req.sample_count,
                sampling_method="nearest",
                roughness_radius_meters=scenario.roughness_window_radius_m,
            )
            segments, scen_est = evaluate_transect_traversal(
                profile_samples=prof.samples,
                scenario=scenario,
            )
            phys_meas = {
                "geometry_type": prof.geometry_type,
                "waypoint_count": prof.waypoint_count,
                "sample_count": prof.sample_count,
                "valid_sample_count": prof.valid_sample_count,
                "nodata_sample_count": prof.nodata_sample_count,
                "complete_coverage": prof.complete_coverage,
                "total_horizontal_distance_meters": prof.total_horizontal_distance_meters,
                "evaluated_horizontal_distance_meters": prof.evaluated_horizontal_distance_meters,
                "total_positive_elevation_gain_meters": prof.total_positive_elevation_gain_meters,
                "total_negative_elevation_change_meters": prof.total_negative_elevation_change_meters,
                "net_elevation_change_meters": prof.net_elevation_change_meters,
                "min_elevation_meters": prof.min_elevation_meters,
                "max_elevation_meters": prof.max_elevation_meters,
                "mean_slope_along_profile_deg": prof.mean_slope_along_profile_deg,
                "max_slope_along_profile_deg": prof.max_slope_along_profile_deg,
                "nodata_gap_segments": [g.model_dump() for g in prof.nodata_gap_segments],
            }
            return MobilityEvaluationResponse(
                evaluation_id=eval_id,
                evaluated_at_utc=now_utc,
                evaluation_mode="transect",
                dataset_id=ds.id,
                source_product_id=ds.product_id,
                crs=prof.crs,
                traversal_model_id=TRAVERSAL_MODEL_ID,
                traversal_model_version=TRAVERSAL_MODEL_VERSION,
                scenario=scenario,
                physical_terrain_measurements=phys_meas,
                scenario_traversal_estimates=scen_est,
                segments=segments,
                cost_surface=None,
                resolution_suitability=prof.resolution_suitability,
                uncertainty=prof.uncertainty,
                provenance={
                    "source_dataset_id": ds.id,
                    "source_product_id": ds.product_id,
                    "source_url": ds.original_product_url,
                    "processing_version": PROCESSING_VERSION,
                    "traversal_model_id": TRAVERSAL_MODEL_ID,
                    "traversal_model_version": TRAVERSAL_MODEL_VERSION,
                },
                limitations=prof.limitations,
            )

        # Single-point evaluation
        pt = req.point or scenario.astronaut_position or scenario.destination_position
        if pt is None:
            raise ValueError(
                "MobilityEvaluationRequest requires `point`, `waypoints` (>=2), `study_bounds`, "
                "or a scenario with positions/study_bounds."
            )
        prof = compute_elevation_profile(
            dataset=ds,
            raw_dir=self.raw_dir,
            waypoints=[pt, pt],
            sample_count=2,
            sampling_method="nearest",
            roughness_radius_meters=scenario.roughness_window_radius_m,
        )
        s0 = prof.samples[0]
        seg0 = evaluate_cell_or_segment_traversal(
            segment_index=0,
            lat=s0.lat,
            lon_east=s0.lon_east,
            horizontal_distance_meters=0.0,
            coverage_state=s0.coverage_state,
            elevation_meters=s0.elevation_meters,
            elevation_delta_meters=0.0,
            slope_deg=s0.slope_deg,
            aspect_deg=s0.aspect_deg,
            roughness_tri_meters=s0.roughness_tri_meters,
            scenario=scenario,
        )
        phys_meas = {
            "lat": s0.lat,
            "lon_east": s0.lon_east,
            "coverage_state": s0.coverage_state.value,
            "elevation_meters": s0.elevation_meters,
            "slope_deg": s0.slope_deg,
            "aspect_deg": s0.aspect_deg,
            "roughness_tri_meters": s0.roughness_tri_meters,
            "uphill_parallel_gravity_force_newtons": seg0.uphill_parallel_gravity_force_newtons,
            "mars_surface_weight_newtons": scenario.mars_surface_weight_n,
        }
        scen_est = {
            "traversal_availability_state": seg0.traversal_availability_state.value,
            "reference_speed_m_per_s": seg0.reference_speed_m_per_s,
            "slope_speed_factor": seg0.slope_speed_factor,
            "roughness_speed_factor": seg0.roughness_speed_factor,
            "effective_speed_m_per_s": seg0.effective_speed_m_per_s,
            "traversal_cost_seconds_per_meter": (
                round(1.0 / seg0.effective_speed_m_per_s, 6)
                if (seg0.effective_speed_m_per_s is not None and seg0.effective_speed_m_per_s > 0.0)
                else None
            ),
            "unavailable_or_exclusion_reason": seg0.unavailable_or_exclusion_reason,
            "safety_assessment": "not_performed_no_validated_safety_limits",
        }
        return MobilityEvaluationResponse(
            evaluation_id=eval_id,
            evaluated_at_utc=now_utc,
            evaluation_mode="point",
            dataset_id=ds.id,
            source_product_id=ds.product_id,
            crs=prof.crs,
            traversal_model_id=TRAVERSAL_MODEL_ID,
            traversal_model_version=TRAVERSAL_MODEL_VERSION,
            scenario=scenario,
            physical_terrain_measurements=phys_meas,
            scenario_traversal_estimates=scen_est,
            segments=[seg0],
            cost_surface=None,
            resolution_suitability=prof.resolution_suitability,
            uncertainty=build_mobility_uncertainty_summary(
                dataset_id=ds.id,
                product_id=ds.product_id,
                dx_meters=ds.horizontal_resolution_meters,
                dy_meters=ds.horizontal_resolution_meters,
                scenario=scenario,
            ),
            provenance={
                "source_dataset_id": ds.id,
                "source_product_id": ds.product_id,
                "source_url": ds.original_product_url,
                "processing_version": PROCESSING_VERSION,
                "traversal_model_id": TRAVERSAL_MODEL_ID,
                "traversal_model_version": TRAVERSAL_MODEL_VERSION,
            },
            limitations=prof.limitations,
        )
