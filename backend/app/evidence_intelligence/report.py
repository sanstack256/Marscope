"""
MARSCOPE Evidence Intelligence Orchestrator & Persistent Dossier Service
Martian Surface Intelligence & Exploration System

Coordinates Shapely polygon-masked DEM corridor terrain assessment, non-double-counted
per-segment multi-product optical coverage, Shapely STRtree Curiosity observation
association with strict product availability checks, 15-domain readiness policies,
22-field content-aware dependency signature verification (CURRENT / STALE),
atomic JSON persistence, and reproducible Mission Dossier generation.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.evidence_intelligence.corridor import (
    build_route_corridor,
    determine_segment_scale_info,
    segment_route_by_scale,
)
from app.evidence_intelligence.coverage_assessment import assess_coverage_and_gaps
from app.evidence_intelligence.evidence_inventory import audit_dataset_validation_stages
from app.evidence_intelligence.mission_readiness import (
    READINESS_POLICY,
    build_tradeoff_explanations,
    compute_physical_energy_budget,
    evaluate_multidomain_readiness,
    evaluate_readiness_state,
)
from app.evidence_intelligence.observation_association import associate_corridor_observations
from app.evidence_intelligence.optical_assessment import assess_corridor_optical_evidence
from app.evidence_intelligence.resolution_assessment import assess_resolution_adequacy
from app.evidence_intelligence.schemas import (
    AssessmentDependencySignature,
    CacheValidityState,
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
from app.routing.models import ROUTE_OBJECTIVES_VERSION
from app.science.complementarity import (
    COMPLEMENTARITY_REGISTRY_VERSION,
    evaluate_data_complementarity,
)
from app.terrain_uncertainty.elevation_uncertainty import inspect_dataset_elevation_uncertainty
from app.terrain_uncertainty.models import (
    RESOLUTION_OBSERVABILITY_VERSION,
    UNCERTAINTY_MODEL_VERSION,
)
from app.terrain_uncertainty.sensitivity import SENSITIVITY_POLICY_VERSION
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.routing.schemas import (
    RouteComputeRequest,
    RouteComputeResponse,
    RoutePlanningConstraints,
    RoutingMode,
)
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)


def _atomic_write_text(target_path: Path, text: str) -> None:
    """Write JSON atomically via same-directory temporary file + os.replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.stem}_", suffix=".tmp", dir=str(target_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target_path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


class EvidenceIntelligenceService:
    """Orchestrates Marswalk Evidence Intelligence assessments and Mission Dossiers."""

    ROUTING_ALGO_VERSION = "routing_v2_science_aware"
    TERRAIN_ASSESS_VERSION = "terrain_corridor_v3"
    OPTICAL_DETECTOR_VERSION = "optical_candidate_v3"
    OBS_MATCHER_VERSION = "obs_strtree_v2"
    EVA_MODEL_VERSION = "eva_envelope_v1"

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
        self._checksum_memo: Dict[Tuple[str, int, int], str] = {}

    def _file_sha256(self, path: Optional[Path]) -> Optional[str]:
        if path is None or not path.exists() or not path.is_file():
            return None
        st = path.stat()
        if st.st_size <= 16 * 1024 * 1024:
            h = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()[:16]
        key = (str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))
        if key in self._checksum_memo:
            return self._checksum_memo[key]
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()[:16]
        self._checksum_memo[key] = digest
        return digest

    def _find_matching_ortho_datasets(self, dem_dataset_id: str) -> List[str]:
        """Return locally acquired orthophotos matching region tokens first."""
        datasets = self.catalog_service.list_datasets()
        tokens = [t for t in dem_dataset_id.split("_") if t.isdigit() and len(t) >= 4]
        matched: List[str] = []
        fallback: List[str] = []
        for ds in datasets:
            if "ortho" not in ds.id.lower() and ds.product_type not in ("HiRISE_ORTHO", "ORTHO", "IMAGE"):
                continue
            try:
                p, _ = _resolve_raw_dem_open_path(ds, self.raw_dir)
                exists = p.exists()
            except Exception:
                exists = bool(ds.local_file_path and Path(ds.local_file_path).exists())
            if not exists:
                continue
            if any(tok in ds.id for tok in tokens) and "ortho" in ds.id.lower():
                matched.append(ds.id)
            elif "ortho" in ds.id.lower():
                fallback.append(ds.id)
        return matched if matched else fallback

    def _find_matching_ortho_dataset(self, dem_dataset_id: str) -> Optional[str]:
        found = self._find_matching_ortho_datasets(dem_dataset_id)
        return found[0] if found else None

    def _load_observations_catalog(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        try:
            from app.api.observations import _load_verified_observations

            obs_payload = _load_verified_observations()
            obs_raw = obs_payload.get("observations", []) if isinstance(obs_payload, dict) else []
            cat_digest = hashlib.sha256(
                json.dumps(obs_raw, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16]
            return obs_raw, cat_digest
        except Exception:
            return [], None

    def _build_dependency_signature(
        self,
        *,
        dataset_id: str,
        source_product_id: str,
        dem_path: Path,
        ortho_id: Optional[str],
        route: Optional[RouteComputeResponse],
        route_geom_hash: str,
        corridor_width_m: float,
        segment_scale_m: float,
        observation_search_radius_m: float,
        obs_catalog_checksum: Optional[str],
        mission_config: Optional[Dict[str, Any]] = None,
    ) -> AssessmentDependencySignature:
        dem_sum = self._file_sha256(dem_path)
        opt_prod_id: Optional[str] = None
        opt_sum: Optional[str] = None
        if ortho_id:
            ods = self.catalog_service.get_dataset(ortho_id)
            opt_prod_id = ods.product_id if ods else ortho_id
            if ods is not None:
                try:
                    op, _ = _resolve_raw_dem_open_path(ods, self.raw_dir)
                    opt_sum = self._file_sha256(op)
                except Exception:
                    opt_sum = None

        geo_ids: List[str] = []
        geo_sums: Dict[str, Optional[str]] = {}
        for ds in self.catalog_service.list_datasets():
            if "usgs" in ds.id.lower() and ds.local_file_path:
                geo_ids.append(ds.id)
                geo_sums[ds.id] = self._file_sha256(Path(ds.local_file_path))

        m_hash = (
            hashlib.sha256(json.dumps(mission_config, sort_keys=True, default=str).encode()).hexdigest()[:16]
            if mission_config
            else None
        )
        core = {
            "dem_dataset_id": dataset_id,
            "dem_product_id": source_product_id,
            "dem_file_checksum": dem_sum,
            "optical_dataset_id": ortho_id,
            "optical_product_id": opt_prod_id,
            "optical_file_checksum": opt_sum,
            "geology_dataset_ids": sorted(geo_ids),
            "geology_checksums": geo_sums,
            "observation_catalog_checksum": obs_catalog_checksum,
            "route_signature": route.route_signature if route else None,
            "route_geometry_hash": route_geom_hash,
            "corridor_width_m": round(float(corridor_width_m), 3),
            "segment_scale_m": round(float(segment_scale_m), 3),
            "observation_search_radius_m": round(float(observation_search_radius_m), 3),
            "routing_algorithm_version": self.ROUTING_ALGO_VERSION,
            "terrain_assessment_version": self.TERRAIN_ASSESS_VERSION,
            "optical_detector_version": self.OPTICAL_DETECTOR_VERSION,
            "observation_matcher_version": self.OBS_MATCHER_VERSION,
            "eva_model_version": "eva_envelope_v2",
            "readiness_policy_version": READINESS_POLICY["policy_version"],
            "uncertainty_model_version": UNCERTAINTY_MODEL_VERSION,
            "resolution_policy_version": RESOLUTION_OBSERVABILITY_VERSION,
            "traversability_model_version": "traversability_v2.0",
            "locomotion_model_id": "MARSCOPE-LOCO",
            "locomotion_model_version": "locomotion_v1.0",
            "routing_objectives_version": ROUTE_OBJECTIVES_VERSION,
            "return_planning_version": "return_planning_v2.0",
            "sensitivity_policy_version": SENSITIVITY_POLICY_VERSION,
            "complementarity_registry_version": COMPLEMENTARITY_REGISTRY_VERSION,
            "mission_config_hash": m_hash,
        }
        sig_digest = hashlib.sha256(
            json.dumps(core, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        return AssessmentDependencySignature(**core, signature_digest=sig_digest)

    def _compare_signature_against_current(
        self, stored: Optional[AssessmentDependencySignature]
    ) -> Tuple[CacheValidityState, List[str]]:
        if stored is None:
            return CacheValidityState.STALE, ["Missing Prompt 15 dependency signature."]

        dem_path = self.processed_dir / f"{stored.dem_dataset_id}_dem.tif"
        _, cur_obs_sum = self._load_observations_catalog()
        cur_sig = self._build_dependency_signature(
            dataset_id=stored.dem_dataset_id,
            source_product_id=stored.dem_product_id,
            dem_path=dem_path,
            ortho_id=stored.optical_dataset_id,
            route=None,
            route_geom_hash=stored.route_geometry_hash,
            corridor_width_m=stored.corridor_width_m,
            segment_scale_m=stored.segment_scale_m,
            observation_search_radius_m=stored.observation_search_radius_m,
            obs_catalog_checksum=cur_obs_sum,
            mission_config=None,
        )
        reasons: List[str] = []
        if cur_sig.dem_file_checksum != stored.dem_file_checksum:
            reasons.append("DEM file checksum changed on disk.")
        if cur_sig.optical_file_checksum != stored.optical_file_checksum:
            reasons.append("Optical orthophoto checksum changed on disk.")
        if cur_sig.geology_checksums != stored.geology_checksums:
            reasons.append("Geological dataset checksum changed.")
        if cur_sig.observation_catalog_checksum != stored.observation_catalog_checksum:
            reasons.append("Curiosity observations catalog changed.")
        if cur_sig.readiness_policy_version != stored.readiness_policy_version:
            reasons.append("Readiness policy version updated.")
        if cur_sig.terrain_assessment_version != stored.terrain_assessment_version:
            reasons.append("Terrain corridor algorithm version updated.")
        if cur_sig.optical_detector_version != stored.optical_detector_version:
            reasons.append("Optical candidate detector version updated.")
        if cur_sig.observation_matcher_version != stored.observation_matcher_version:
            reasons.append("Observation spatial matcher version updated.")
        for attr, label in (
            ("uncertainty_model_version", "Terrain uncertainty model"),
            ("resolution_policy_version", "Resolution observability policy"),
            ("traversability_model_version", "Traversability classification model"),
            ("locomotion_model_version", "Locomotion planning model"),
            ("routing_objectives_version", "Routing objective policies"),
            ("return_planning_version", "Return planning algorithm"),
            ("sensitivity_policy_version", "Sensitivity policy"),
            ("complementarity_registry_version", "Data complementarity registry"),
        ):
            if getattr(cur_sig, attr, None) != getattr(stored, attr, None):
                reasons.append(f"{label} version updated.")

        if reasons:
            return CacheValidityState.STALE, reasons
        return CacheValidityState.CURRENT, []

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

        seg_scale_m, _, _ = determine_segment_scale_info(
            native_resolution_m=native_res_m,
            requested_scale_m=request.target_segment_length_m,
        )

        # Deterministic assessment ID including route geometry & mode signature
        route_geom_hash = hashlib.sha256(
            json.dumps(
                [[round(v.lat, 6), round(v.lon_east, 6), round(v.elevation_m, 2)] for v in route.vertices],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]

        sig_payload = json.dumps(
            {
                "dataset_id": request.dataset_id,
                "start": [round(request.start.lat, 6), round(request.start.lon_east, 6)],
                "dest": [round(request.destination.lat, 6), round(request.destination.lon_east, 6)],
                "mode": request.mode.value,
                "width": request.corridor_width_m,
                "scale": seg_scale_m,
                "radius": request.observation_search_radius_m,
                "route_geom": route_geom_hash,
            },
            sort_keys=True,
        )
        assessment_id = f"cor-{hashlib.sha256(sig_payload.encode()).hexdigest()[:14]}"

        ortho_ids = self._find_matching_ortho_datasets(request.dataset_id)
        primary_ortho_id = ortho_ids[0] if ortho_ids else None
        obs_raw, obs_cat_checksum = self._load_observations_catalog()

        dep_sig = self._build_dependency_signature(
            dataset_id=request.dataset_id,
            source_product_id=source_product_id,
            dem_path=dem_path,
            ortho_id=primary_ortho_id,
            route=route,
            route_geom_hash=route_geom_hash,
            corridor_width_m=request.corridor_width_m,
            segment_scale_m=seg_scale_m,
            observation_search_radius_m=request.observation_search_radius_m,
            obs_catalog_checksum=obs_cat_checksum,
        )

        if not request.force_recompute:
            existing = self.get_corridor_assessment(assessment_id)
            if (
                existing is not None
                and existing.dependency_signature is not None
                and existing.dependency_signature.signature_digest == dep_sig.signature_digest
                and existing.cache_validity == CacheValidityState.CURRENT
            ):
                return existing

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
        raw_segments = segment_route_by_scale(
            route.vertices,
            segment_scale_m=seg_scale_m,
            corridor_width_m=request.corridor_width_m,
            dem_bounds=dem_bounds,
            native_resolution_m=native_res_m,
        )

        inventory = audit_dataset_validation_stages(
            catalog_service=self.catalog_service,
            raw_dir=self.raw_dir,
            processed_dir=self.processed_dir,
        )
        geological_cov = any(d.acquired and "usgs" in d.dataset_id.lower() for d in inventory)

        segments, terrain_candidates, dem_stats = assess_corridor_terrain(
            dem_path=dem_path,
            dataset_id=request.dataset_id,
            source_product_id=source_product_id,
            native_resolution_m=native_res_m,
            raw_segments=raw_segments,
            corridor_width_m=request.corridor_width_m,
            optical_coverage_fraction=0.0,
            optical_quality_note="Pending per-segment optical assessment",
            geological_map_coverage=geological_cov,
            spectral_data_available=False,
            thermal_data_available=False,
        )

        (
            optical_candidates,
            rejected_optical,
            opt_cov_frac,
            opt_note,
            opt_meta,
        ) = assess_corridor_optical_evidence(
            catalog_service=self.catalog_service,
            raw_dir=self.raw_dir,
            ortho_dataset_id=primary_ortho_id,
            ortho_dataset_ids=ortho_ids,
            dem_bounds=dem_stats["dem_window_bounds"],
            segments=segments,
            corridor_width_m=request.corridor_width_m,
        )

        # Update per-segment unverified status from that segment's own DEM + optical coverage
        for seg in segments:
            seg_opt = seg.coverage.valid_optical_pixel_coverage_fraction
            seg.unverified_area_present = seg.valid_data_coverage_fraction < 0.95 or seg_opt <= 0.0
            seg.coverage.unverified_regions_present = seg.unverified_area_present

        associated_obs = associate_corridor_observations(
            observations_raw=obs_raw,
            imagery_records=[],
            segments=segments,
            search_radius_m=request.observation_search_radius_m,
            study_region="Gale Crater / Mount Sharp",
            corridor_width_m=request.corridor_width_m,
            raw_dir=self.raw_dir,
        )
        if associated_obs:
            for seg in segments:
                if seg.coverage.rover_observation_count > 0:
                    has_spec = any(
                        o.nearest_segment_id == seg.segment_id
                        and ("chemcam" in o.instrument.lower() or "apxs" in o.instrument.lower())
                        for o in associated_obs
                    )
                    has_therm = any(
                        o.nearest_segment_id == seg.segment_id and "rems" in o.instrument.lower()
                        for o in associated_obs
                    )
                    seg.coverage.spectral_data_available = has_spec
                    seg.coverage.spectral_coverage_fraction = 0.25 if has_spec else 0.0
                    seg.coverage.thermal_data_available = has_therm
                    seg.coverage.thermal_coverage_fraction = 0.25 if has_therm else 0.0

        res_adequacy = assess_resolution_adequacy(
            dem_dataset_id=request.dataset_id,
            dem_native_resolution_m=native_res_m,
            optical_dataset_id=primary_ortho_id if opt_cov_frac > 0 else None,
            optical_pixel_scale_m=opt_meta.get("native_pixel_scale_m"),
            geological_map_available=geological_cov,
        )
        coverage_summary, evidence_gaps = assess_coverage_and_gaps(
            segments=segments,
            segment_bounds=dem_stats["segment_bounds"],
            native_resolution_m=native_res_m,
        )
        ds_unc_prof = (
            inspect_dataset_elevation_uncertainty(
                dataset=ds_meta,
                raw_dir=self.raw_dir,
                processed_dir=self.processed_dir,
            )
            if ds_meta is not None
            else None
        )
        uncertainty = assess_corridor_uncertainty(
            segments=segments,
            native_resolution_m=native_res_m,
            corridor_valid_fraction=dem_stats["corridor_valid_fraction"],
            optical_available=opt_cov_frac > 0.0,
            dataset_uncertainty_profile=ds_unc_prof,
        )

        prov_graph = ProvenanceDependencyGraph(
            output_id=assessment_id,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[request.dataset_id] + ortho_ids,
            input_product_ids=[source_product_id]
            + ([str(opt_meta.get("source_product_id"))] if opt_meta.get("source_product_id") else []),
            input_variables=["elevation_m", "orthophoto_dn", "rover_observations"],
            input_units=["m", "DN", "mixed_pds"],
            input_crs="IAU2000:49900",
            input_resolution_m=native_res_m,
            method="corridor_evidence_intelligence_pipeline_v2",
            algorithm_version=self.TERRAIN_ASSESS_VERSION,
            parameters={
                "corridor_width_m": request.corridor_width_m,
                "segment_scale_m": seg_scale_m,
                "observation_search_radius_m": request.observation_search_radius_m,
                "convolution_buffer_m": dem_stats.get("convolution_buffer_m"),
            },
            intermediate_steps=[
                ProvenanceStep(
                    step_id="step-dem-corridor",
                    label="Polygon-Masked Corridor DEM Slope, 5m-TRI & Curvature",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[source_product_id],
                    method="geometry_mask_windowed_dem_slope_5m_tri_curvature",
                    algorithm_version=self.TERRAIN_ASSESS_VERSION,
                    output_variable="segment_terrain_metrics",
                    output_units="deg_and_m",
                    output_resolution_m=native_res_m,
                ),
                ProvenanceStep(
                    step_id="step-optical-evidence",
                    label="Corridor-Constrained Multi-Scale HiRISE Optical Analysis",
                    classification=(
                        ScientificDataClassification.MARSCOPE_DERIVED
                        if opt_cov_frac > 0
                        else ScientificDataClassification.UNAVAILABLE
                    ),
                    input_ids=[str(opt_meta.get("source_product_id") or "NONE")],
                    method="per_segment_unioned_optical_analysis",
                    algorithm_version=self.OPTICAL_DETECTOR_VERSION,
                    output_variable="optical_candidates",
                ),
                ProvenanceStep(
                    step_id="step-rover-observations",
                    label="Shapely STRtree Gale / Curiosity Observation Association",
                    classification=(
                        ScientificDataClassification.DIRECTLY_MEASURED
                        if associated_obs
                        else ScientificDataClassification.UNAVAILABLE
                    ),
                    input_ids=["MSL_CURIOSITY_PDS_RECORDS"],
                    method="shapely_strtree_observation_association",
                    algorithm_version=self.OBS_MATCHER_VERSION,
                    output_variable="associated_observations",
                ),
            ],
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        explainer_dict = (
            route.decision_explainer.model_dump() if getattr(route, "decision_explainer", None) is not None else None
        )

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
            cache_validity=CacheValidityState.CURRENT,
            stale_reasons=[],
            dependency_signature=dep_sig,
            readiness_policy_version=READINESS_POLICY["policy_version"],
            convolution_buffer_m=dem_stats.get("convolution_buffer_m"),
            convolution_buffer_px=dem_stats.get("convolution_buffer_px"),
            route_decision_explainer=explainer_dict,
        )

        self._corridor_cache[assessment_id] = assessment
        _atomic_write_text(
            self.corridor_dir / f"{assessment_id}.json",
            assessment.model_dump_json(indent=2),
        )
        return assessment

    def get_corridor_assessment(self, assessment_id: str) -> Optional[CorridorAssessment]:
        obj: Optional[CorridorAssessment] = None
        if assessment_id in self._corridor_cache:
            obj = self._corridor_cache[assessment_id]
        else:
            path = self.corridor_dir / f"{assessment_id}.json"
            if path.exists():
                obj = CorridorAssessment.model_validate_json(path.read_text(encoding="utf-8"))
                self._corridor_cache[assessment_id] = obj
        if obj is not None:
            validity, reasons = self._compare_signature_against_current(obj.dependency_signature)
            obj.cache_validity = validity
            obj.stale_reasons = reasons
        return obj

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
                force_recompute=request.force_recompute,
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

        domain_records, math_complete = evaluate_multidomain_readiness(
            request=request,
            corridor=corridor,
            native_resolution_m=native_res,
            energy_budget=energy_budget,
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
                    "association_type": obs.association_type.value,
                    "distance_from_route_m": obs.distance_from_route_m,
                    "nearest_segment_id": obs.nearest_segment_id,
                    "availability_status": obs.availability_status.value,
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
                    "nearest_segment_id": cand.nearest_segment_id,
                    "note": "In-corridor optical contrast anomaly requiring human interpretation.",
                }
            )

        mission_cfg = {
            "mission_name": request.mission_name,
            "corridor_id": corridor.assessment_id,
            "speed": request.walking_speed_mps,
            "dur": request.mission_duration_limit_s,
            "res": request.return_reserve_fraction,
            "suit": request.astronaut_suit_mass_kg,
            "payload": request.payload_mass_kg,
        }
        dossier_sig = hashlib.sha256(
            json.dumps(mission_cfg, sort_keys=True).encode()
        ).hexdigest()[:14]
        dossier_id = f"dos-{dossier_sig}"

        active_ds_ids = [request.dataset_id] + [
            d.dataset_id for d in corridor.dataset_inventory if d.acquired
        ]
        comp_report = evaluate_data_complementarity(
            active_dataset_ids=active_ds_ids,
            route_distance_m=route.total_surface_distance_m,
        ).model_dump()

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
            complementarity_report=comp_report,
            provenance_graph=corridor.provenance_graph,
            mathematical_assessment_complete=math_complete,
            operational_safety_certified=False,
            domain_assessments=domain_records,
            readiness_policy_version=READINESS_POLICY["policy_version"],
            cache_validity=corridor.cache_validity,
            stale_reasons=corridor.stale_reasons,
            dependency_signature=corridor.dependency_signature,
        )
        self._dossier_cache[dossier_id] = dossier
        _atomic_write_text(
            self.dossier_dir / f"{dossier_id}.json",
            dossier.model_dump_json(indent=2),
        )
        return dossier

    def get_mission_dossier(self, dossier_id: str) -> Optional[MissionDossierResponse]:
        obj: Optional[MissionDossierResponse] = None
        if dossier_id in self._dossier_cache:
            obj = self._dossier_cache[dossier_id]
        else:
            path = self.dossier_dir / f"{dossier_id}.json"
            if path.exists():
                obj = MissionDossierResponse.model_validate_json(path.read_text(encoding="utf-8"))
                self._dossier_cache[dossier_id] = obj
        if obj is not None:
            validity, reasons = self._compare_signature_against_current(obj.dependency_signature)
            obj.cache_validity = validity
            obj.stale_reasons = reasons
            obj.corridor_assessment.cache_validity = validity
            obj.corridor_assessment.stale_reasons = reasons
        return obj
