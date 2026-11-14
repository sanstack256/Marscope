"""
MARSCOPE Evidence Intelligence Orchestrator & Persistent Dossier Service
Martian Surface Intelligence & Exploration System

Coordinates corridor geometry, resolution-driven segmentation, windowed DEM
terrain assessment, multi-scale optical analysis, Curiosity observation
association, spatial coverage/gaps, uncertainty, route comparison, and
mission dossier generation with deterministic SHA-256 IDs and JSON persistence.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.evidence_intelligence.corridor import (
    build_route_corridor,
    determine_segment_scale_m,
    segment_route_by_scale,
)
from app.evidence_intelligence.coverage_assessment import assess_coverage_and_gaps
from app.evidence_intelligence.evidence_inventory import audit_dataset_validation_stages
from app.evidence_intelligence.mission_readiness import (
    build_tradeoff_explanations,
    compute_physical_energy_budget,
    evaluate_readiness_state,
)
from app.evidence_intelligence.observation_association import associate_corridor_observations
from app.evidence_intelligence.optical_assessment import assess_corridor_optical_evidence
from app.evidence_intelligence.resolution_assessment import assess_resolution_adequacy
from app.evidence_intelligence.schemas import (
    CorridorAssessRequest,
    CorridorAssessment,
    MissionDossierRequest,
    MissionDossierResponse,
    RouteEvidenceComparisonEntry,
    RouteEvidenceComparisonRequest,
    RouteEvidenceComparisonResponse,
)
from app.evidence_intelligence.terrain_assessment import assess_corridor_terrain
from app.evidence_intelligence.uncertainty_assessment import assess_corridor_uncertainty
from app.routing.schemas import (
    RoutingMode,
    RouteComputeRequest,
    RouteComputeResponse,
    RoutePlanningConstraints,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)


class EvidenceIntelligenceService:
    """Orchestrates Marswalk Evidence Intelligence assessments and Mission Dossiers."""

    def __init__(
        self,
        *,
        catalog_service: Any,
        routing_service: Any,
        raw_dir: Path,
        processed_dir: Path,
    ) -> None:
        self.catalog_service = catalog_service
        self.routing_service = routing_service
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.storage_dir = processed_dir / "evidence_intelligence"
        self.corridor_dir = self.storage_dir / "corridors"
        self.dossier_dir = self.storage_dir / "dossiers"
        self.corridor_dir.mkdir(parents=True, exist_ok=True)
        self.dossier_dir.mkdir(parents=True, exist_ok=True)
        self._corridor_cache: Dict[str, CorridorAssessment] = {}
        self._dossier_cache: Dict[str, MissionDossierResponse] = {}

    def _find_matching_ortho_dataset(self, dem_dataset_id: str) -> Optional[str]:
        """Select locally acquired HiRISE orthophoto covering the DEM region if available."""
        datasets = self.catalog_service.list_datasets()
        tokens = [t for t in dem_dataset_id.split("_") if t.isdigit() and len(t) >= 4]
        for ds in datasets:
            if ds.local_file_path and Path(ds.local_file_path).exists() and ds.product_type in ("HiRISE_ORTHO", "ORTHO", "IMAGE"):
                if any(tok in ds.id for tok in tokens) and "ortho" in ds.id.lower():
                    return ds.id
        for ds in datasets:
            if "ortho" in ds.id.lower() and ds.local_file_path and Path(ds.local_file_path).exists():
                return ds.id
        return None

    def assess_corridor(self, request: CorridorAssessRequest) -> CorridorAssessment:
        t0 = time.perf_counter()

        route: Optional[RouteComputeResponse] = request.route
        if route is None:
            route = self.routing_service.compute_route(
                RouteComputeRequest(
                    dataset_id=request.dataset_id,
                    start=request.start,
                    destination=request.destination,
                    mode=request.mode,
                    constraints=request.constraints or RoutePlanningConstraints(),
                    selected_target_ids=request.selected_target_ids,
                )
            )

        if len(route.vertices) < 2:
            raise ValueError(
                "Cannot assess corridor because no feasible route with >= 2 vertices was computed."
            )

        ds_meta = self.catalog_service.get_dataset(request.dataset_id)
        source_product_id = (
            ds_meta.product_id if ds_meta else route.source_product_id or request.dataset_id
        )
        native_res_m = (
            float(ds_meta.horizontal_resolution_meters)
            if ds_meta and getattr(ds_meta, "horizontal_resolution_meters", None)
            else float(route.native_dem_resolution_m or 1.0)
        )
        dem_path = self.processed_dir / f"{request.dataset_id}_dem.tif"
        if not dem_path.exists():
            raise FileNotFoundError(
                f"Processed DEM {dem_path.name} is not available locally for evidence assessment."
            )

        # Build corridor polygon clipped to DEM footprint
        dem_bounds = (
            {
                "min_lat": float(ds_meta.coverage.min_latitude),
                "max_lat": float(ds_meta.coverage.max_latitude),
                "min_lon": float(ds_meta.coverage.min_longitude),
                "max_lon": float(ds_meta.coverage.max_longitude),
            }
            if ds_meta and getattr(ds_meta, "coverage", None)
            else {
                "min_lat": min(v.lat for v in route.vertices) - 0.05,
                "max_lat": max(v.lat for v in route.vertices) + 0.05,
                "min_lon": min(v.lon_east for v in route.vertices) - 0.05,
                "max_lon": max(v.lon_east for v in route.vertices) + 0.05,
            }
        )
        corridor_poly = build_route_corridor(
            route.vertices,
            corridor_width_m=request.corridor_width_m,
            dem_bounds=dem_bounds,
        )

        seg_scale_m = determine_segment_scale_m(
            native_resolution_m=native_res_m,
            requested_scale_m=request.target_segment_length_m,
        )
        raw_segments = segment_route_by_scale(route.vertices, segment_scale_m=seg_scale_m)

        # Check geological map & spectral/thermal local availability truthfully
        inventory = audit_dataset_validation_stages(
            catalog_service=self.catalog_service,
            raw_dir=self.raw_dir,
            processed_dir=self.processed_dir,
        )
        geological_cov = any(
            d.acquired and "usgs" in d.dataset_id.lower() for d in inventory
        )
        ortho_id = self._find_matching_ortho_dataset(request.dataset_id)

        # First pass terrain assessment
        segments, terrain_candidates, dem_stats = assess_corridor_terrain(
            dem_path=dem_path,
            dataset_id=request.dataset_id,
            source_product_id=source_product_id,
            native_resolution_m=native_res_m,
            raw_segments=raw_segments,
            corridor_width_m=request.corridor_width_m,
            optical_coverage_fraction=0.0,
            optical_quality_note="Pending optical assessment",
            geological_map_coverage=geological_cov,
            spectral_data_available=False,
            thermal_data_available=False,
        )

        # Optical evidence assessment over the corridor DEM window
        (
            optical_candidates,
            rejected_optical,
            opt_cov_frac,
            opt_note,
            opt_meta,
        ) = assess_corridor_optical_evidence(
            catalog_service=self.catalog_service,
            raw_dir=self.raw_dir,
            ortho_dataset_id=ortho_id,
            dem_bounds=dem_stats["dem_window_bounds"],
            segments=segments,
        )
        for seg in segments:
            seg.coverage.optical_coverage_fraction = round(opt_cov_frac, 4)
            seg.coverage.optical_quality_note = opt_note
            seg.unverified_area_present = (
                seg.valid_data_coverage_fraction < 0.95 or opt_cov_frac <= 0.0
            )
            seg.coverage.unverified_regions_present = seg.unverified_area_present

        # Verified rover observations (Curiosity only for Gale)
        try:
            from app.api.observations import _load_verified_observations

            obs_payload = _load_verified_observations()
            obs_raw = obs_payload.get("observations", []) if isinstance(obs_payload, dict) else []
        except Exception:
            obs_raw = []

        associated_obs = associate_corridor_observations(
            observations_raw=obs_raw,
            imagery_records=[],
            segments=segments,
            search_radius_m=request.observation_search_radius_m,
            study_region="Gale Crater / Mount Sharp",
        )
        if associated_obs:
            for seg in segments:
                if seg.coverage.rover_observation_count > 0:
                    seg.coverage.spectral_data_available = any(
                        o.nearest_segment_id == seg.segment_id
                        and ("chemcam" in o.instrument.lower() or "apxs" in o.instrument.lower())
                        for o in associated_obs
                    )
                    seg.coverage.thermal_data_available = any(
                        o.nearest_segment_id == seg.segment_id and "rems" in o.instrument.lower()
                        for o in associated_obs
                    )

        res_adequacy = assess_resolution_adequacy(
            dem_dataset_id=request.dataset_id,
            dem_native_resolution_m=native_res_m,
            optical_dataset_id=ortho_id if opt_cov_frac > 0 else None,
            optical_pixel_scale_m=opt_meta.get("native_pixel_scale_m"),
            geological_map_available=geological_cov,
        )
        coverage_summary, evidence_gaps = assess_coverage_and_gaps(
            segments=segments,
            segment_bounds=dem_stats["segment_bounds"],
            native_resolution_m=native_res_m,
        )
        uncertainty = assess_corridor_uncertainty(
            segments=segments,
            native_resolution_m=native_res_m,
            corridor_valid_fraction=dem_stats["corridor_valid_fraction"],
            optical_available=opt_cov_frac > 0.0,
        )

        # Deterministic assessment ID
        sig_payload = json.dumps(
            {
                "dataset_id": request.dataset_id,
                "start": [round(request.start.lat, 6), round(request.start.lon_east, 6)],
                "dest": [round(request.destination.lat, 6), round(request.destination.lon_east, 6)],
                "mode": request.mode.value,
                "width": request.corridor_width_m,
                "scale": seg_scale_m,
                "radius": request.observation_search_radius_m,
            },
            sort_keys=True,
        )
        assessment_id = f"cor-{hashlib.sha256(sig_payload.encode()).hexdigest()[:14]}"

        prov_graph = ProvenanceDependencyGraph(
            output_id=assessment_id,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[request.dataset_id] + ([ortho_id] if ortho_id else []),
            input_product_ids=[source_product_id]
            + ([str(opt_meta.get("source_product_id"))] if opt_meta.get("source_product_id") else []),
            input_variables=["elevation_m", "orthophoto_dn", "rover_observations"],
            input_units=["m", "DN", "mixed_pds"],
            input_crs="IAU2000:49900",
            input_resolution_m=native_res_m,
            method="corridor_evidence_intelligence_pipeline",
            algorithm_version="1.0.0",
            parameters={
                "corridor_width_m": request.corridor_width_m,
                "segment_scale_m": seg_scale_m,
                "observation_search_radius_m": request.observation_search_radius_m,
            },
            intermediate_steps=[
                ProvenanceStep(
                    step_id="step-dem-corridor",
                    label="Corridor DEM Slope, 5m-TRI & Curvature",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[source_product_id],
                    method="windowed_dem_slope_5m_tri_curvature",
                    algorithm_version="1.0.0",
                    output_variable="segment_terrain_metrics",
                    output_units="deg_and_m",
                    output_resolution_m=native_res_m,
                    parameters={
                        "dataset_id": request.dataset_id,
                        "corridor_width_m": request.corridor_width_m,
                        "segment_scale_m": seg_scale_m,
                    },
                ),
                ProvenanceStep(
                    step_id="step-optical-evidence",
                    label="Multi-Scale HiRISE Optical Candidate Analysis",
                    classification=(
                        ScientificDataClassification.MARSCOPE_DERIVED
                        if opt_cov_frac > 0
                        else ScientificDataClassification.UNAVAILABLE
                    ),
                    input_ids=[str(opt_meta.get("source_product_id") or "NONE")],
                    method="deterministic_multiscale_optical_analysis",
                    algorithm_version="1.0.0",
                    output_variable="optical_candidates",
                    parameters={"optical_dataset_id": ortho_id},
                ),
                ProvenanceStep(
                    step_id="step-rover-observations",
                    label="Gale / Curiosity Observation Association",
                    classification=(
                        ScientificDataClassification.DIRECTLY_MEASURED
                        if associated_obs
                        else ScientificDataClassification.UNAVAILABLE
                    ),
                    input_ids=["MSL_CURIOSITY_PDS_RECORDS"],
                    method="gale_curiosity_observation_association",
                    algorithm_version="1.0.0",
                    output_variable="associated_observations",
                    parameters={"search_radius_m": request.observation_search_radius_m},
                ),
            ],
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        assessment = CorridorAssessment(
            assessment_id=assessment_id,
            dataset_id=request.dataset_id,
            source_product_id=source_product_id,
            local_projection=corridor_poly.projection,
            corridor_width_m=request.corridor_width_m,
            segment_scale_m=seg_scale_m,
            observation_search_radius_m=request.observation_search_radius_m,
            corridor_geometry=corridor_poly,
            route_horizontal_distance_m=route.total_horizontal_distance_m,
            route_surface_distance_m=route.total_surface_distance_m,
            segments=segments,
            terrain_candidates=terrain_candidates,
            optical_candidates=optical_candidates,
            rejected_optical_candidates=rejected_optical,
            observations=associated_obs,
            coverage_summary=coverage_summary,
            resolution_adequacy=res_adequacy,
            evidence_gaps=evidence_gaps,
            uncertainty=uncertainty,
            dataset_inventory=inventory,
            compute_time_ms=elapsed_ms,
            provenance_graph=prov_graph,
        )

        self._corridor_cache[assessment_id] = assessment
        (self.corridor_dir / f"{assessment_id}.json").write_text(
            assessment.model_dump_json(indent=2), encoding="utf-8"
        )
        return assessment

    def get_corridor_assessment(self, assessment_id: str) -> Optional[CorridorAssessment]:
        if assessment_id in self._corridor_cache:
            return self._corridor_cache[assessment_id]
        path = self.corridor_dir / f"{assessment_id}.json"
        if path.exists():
            obj = CorridorAssessment.model_validate_json(path.read_text(encoding="utf-8"))
            self._corridor_cache[assessment_id] = obj
            return obj
        return None

    def compare_routes_evidence(
        self, request: RouteEvidenceComparisonRequest
    ) -> RouteEvidenceComparisonResponse:
        t0 = time.perf_counter()
        ds_meta = self.catalog_service.get_dataset(request.dataset_id)
        source_product_id = ds_meta.product_id if ds_meta else request.dataset_id

        entries: List[RouteEvidenceComparisonEntry] = []
        mode_labels = {
            RoutingMode.CONSERVATIVE: "Safest / Conservative",
            RoutingMode.BALANCED: "Balanced Traverse",
            RoutingMode.SCIENCE_PRIORITY: "Science Priority",
        }

        for mode in request.modes:
            try:
                route = self.routing_service.compute_route(
                    RouteComputeRequest(
                        dataset_id=request.dataset_id,
                        start=request.start,
                        destination=request.destination,
                        mode=mode,
                        constraints=request.constraints or RoutePlanningConstraints(),
                        selected_target_ids=request.selected_target_ids,
                    )
                )
            except Exception as exc:
                entries.append(
                    RouteEvidenceComparisonEntry(
                        mode=mode,
                        mode_label=mode_labels.get(mode, mode.value),
                        feasible=False,
                        error_reason=str(exc),
                    )
                )
                continue

            if len(route.vertices) < 2:
                entries.append(
                    RouteEvidenceComparisonEntry(
                        mode=mode,
                        mode_label=mode_labels.get(mode, mode.value),
                        feasible=False,
                        error_reason="Route infeasible",
                    )
                )
                continue

            corridor = self.assess_corridor(
                CorridorAssessRequest(
                    dataset_id=request.dataset_id,
                    start=request.start,
                    destination=request.destination,
                    route=route,
                    mode=mode,
                    corridor_width_m=request.corridor_width_m,
                    observation_search_radius_m=request.observation_search_radius_m,
                    selected_target_ids=request.selected_target_ids,
                    constraints=request.constraints,
                )
            )
            slopes = [s.max_slope_deg for s in corridor.segments if s.max_slope_deg is not None]
            mean_slopes = [s.mean_slope_deg for s in corridor.segments if s.mean_slope_deg is not None]
            tris = [s.max_tri_m for s in corridor.segments if s.max_tri_m is not None]
            mean_tris = [s.mean_tri_m for s in corridor.segments if s.mean_tri_m is not None]
            reliefs = [s.local_relief_m for s in corridor.segments if s.local_relief_m is not None]

            res_status = (
                corridor.resolution_adequacy[0].status
                if corridor.resolution_adequacy
                else "unverified"
            )
            entries.append(
                RouteEvidenceComparisonEntry(
                    mode=mode,
                    mode_label=mode_labels.get(mode, mode.value),
                    feasible=True,
                    assessment_id=corridor.assessment_id,
                    horizontal_distance_m=route.total_horizontal_distance_m,
                    surface_distance_m=route.total_surface_distance_m,
                    elevation_gain_m=route.total_elevation_gain_m,
                    elevation_loss_m=route.total_elevation_loss_m,
                    max_slope_deg=max(slopes) if slopes else route.max_slope_deg,
                    mean_slope_deg=round(sum(mean_slopes) / len(mean_slopes), 2) if mean_slopes else None,
                    max_tri_m=max(tris) if tris else route.mean_roughness_tri_m,
                    mean_tri_m=round(sum(mean_tris) / len(mean_tris), 2) if mean_tris else None,
                    local_relief_max_m=max(reliefs) if reliefs else None,
                    terrain_coverage_fraction=corridor.coverage_summary.get("mean_dem_coverage_fraction"),
                    optical_coverage_fraction=corridor.coverage_summary.get("mean_optical_coverage_fraction"),
                    unknown_data_fraction=corridor.coverage_summary.get("unknown_data_fraction"),
                    resolution_adequacy_status=res_status,
                    associated_observation_count=len(corridor.observations),
                    science_targets_reached_count=len(route.science_targets_reached),
                    unresolved_candidate_count=len(corridor.terrain_candidates) + len(corridor.optical_candidates),
                    data_gap_count=len(corridor.evidence_gaps),
                    composite_risk_score=None,
                )
            )

        return RouteEvidenceComparisonResponse(
            dataset_id=request.dataset_id,
            source_product_id=source_product_id,
            corridor_width_m=request.corridor_width_m,
            entries=entries,
            tradeoff_explanations=build_tradeoff_explanations(entries),
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    def generate_mission_dossier(
        self, request: MissionDossierRequest
    ) -> MissionDossierResponse:
        route = self.routing_service.compute_route(
            RouteComputeRequest(
                dataset_id=request.dataset_id,
                start=request.start,
                destination=request.destination,
                mode=request.mode,
                constraints=request.constraints or RoutePlanningConstraints(),
                selected_target_ids=request.selected_target_ids,
            )
        )
        corridor = self.assess_corridor(
            CorridorAssessRequest(
                dataset_id=request.dataset_id,
                start=request.start,
                destination=request.destination,
                route=route,
                mode=request.mode,
                corridor_width_m=request.corridor_width_m,
                observation_search_radius_m=request.observation_search_radius_m,
                selected_target_ids=request.selected_target_ids,
                selected_imagery_ids=request.selected_imagery_ids,
                constraints=request.constraints,
            )
        )
        comparison = self.compare_routes_evidence(
            RouteEvidenceComparisonRequest(
                dataset_id=request.dataset_id,
                start=request.start,
                destination=request.destination,
                corridor_width_m=request.corridor_width_m,
                observation_search_radius_m=request.observation_search_radius_m,
                selected_target_ids=request.selected_target_ids,
                constraints=request.constraints,
            )
        )

        energy_budget = compute_physical_energy_budget(
            positive_elevation_gain_m=route.total_elevation_gain_m,
            negative_elevation_loss_m=route.total_elevation_loss_m,
            astronaut_suit_mass_kg=request.astronaut_suit_mass_kg,
            payload_mass_kg=request.payload_mass_kg,
        )

        native_res = float(route.native_dem_resolution_m or 1.0)
        (
            readiness_state,
            readiness_reasons,
            missing_inputs,
            mobility_assessment,
            unmodeled_params,
        ) = evaluate_readiness_state(
            request=request,
            corridor=corridor,
            native_resolution_m=native_res,
        )

        sci_opportunities: List[Dict[str, Any]] = []
        for obs in corridor.observations[:15]:
            sci_opportunities.append(
                {
                    "type": "nearby_rover_observation",
                    "id": obs.observation_id,
                    "mission": obs.mission,
                    "instrument": obs.instrument,
                    "sol": obs.sol,
                    "distance_from_route_m": obs.distance_from_route_m,
                    "nearest_segment_id": obs.nearest_segment_id,
                    "note": obs.spatial_association_note,
                }
            )
        for cand in corridor.optical_candidates[:10]:
            sci_opportunities.append(
                {
                    "type": "optical_surface_candidate",
                    "id": cand.feature_id,
                    "category": cand.candidate_type,
                    "lat": cand.latitude,
                    "lon_east": cand.longitude_east,
                    "note": "Optical contrast anomaly requiring human interpretation.",
                }
            )

        dossier_sig = hashlib.sha256(
            json.dumps(
                {
                    "mission_name": request.mission_name,
                    "corridor_id": corridor.assessment_id,
                    "speed": request.walking_speed_mps,
                    "dur": request.mission_duration_limit_s,
                    "res": request.return_reserve_fraction,
                    "suit": request.astronaut_suit_mass_kg,
                    "payload": request.payload_mass_kg,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:14]
        dossier_id = f"dos-{dossier_sig}"

        dossier = MissionDossierResponse(
            dossier_id=dossier_id,
            mission_name=request.mission_name,
            study_region=request.study_region,
            readiness_state=readiness_state,
            readiness_reasons=readiness_reasons,
            missing_inputs=missing_inputs,
            corridor_assessment=corridor,
            route_comparison=comparison,
            physical_energy_budget=energy_budget,
            mobility_assessment=mobility_assessment,
            scientific_opportunities=sci_opportunities,
            unmodeled_parameters=unmodeled_params,
            provenance_graph=corridor.provenance_graph,
        )
        self._dossier_cache[dossier_id] = dossier
        (self.dossier_dir / f"{dossier_id}.json").write_text(
            dossier.model_dump_json(indent=2), encoding="utf-8"
        )
        return dossier

    def get_mission_dossier(self, dossier_id: str) -> Optional[MissionDossierResponse]:
        if dossier_id in self._dossier_cache:
            return self._dossier_cache[dossier_id]
        path = self.dossier_dir / f"{dossier_id}.json"
        if path.exists():
            obj = MissionDossierResponse.model_validate_json(path.read_text(encoding="utf-8"))
            self._dossier_cache[dossier_id] = obj
            return obj
        return None
