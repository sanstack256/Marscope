"""
MARSCOPE EVA Operational Envelope Orchestrator Service
Coordinates route computation, polygon-masked corridor evidence assessment,
reverse return-route verification, time/energy/unit-aware resource envelopes,
segment schedules, and atomic JSON persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Dict, Optional

from app.evidence_intelligence.schemas import CacheValidityState, CorridorAssessRequest
from app.eva_operations.constraints import evaluate_eva_constraints
from app.eva_operations.energy_budget import evaluate_eva_energy_budget
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.return_planning import plan_eva_return_route
from app.eva_operations.route_schedule import build_eva_schedule
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    EvaMissionEnvelopeResponse,
    MissionConfigRequest,
)
from app.eva_operations.time_budget import evaluate_eva_time_budget
from app.eva_operations.uncertainty import summarize_eva_uncertainties
from app.routing.schemas import RouteComputeRequest, RoutePlanningConstraints
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)


def _atomic_write_json(target_path: Path, text: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.stem}_", suffix=".tmp", dir=str(target_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(text)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp_name, target_path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


class EvaOperationsService:
    """Manages persistent EVA mission configurations and operational envelope evaluations."""

    def __init__(
        self,
        *,
        routing_service: object,
        evidence_service: object,
        processed_dir: Path,
    ) -> None:
        self.routing_service = routing_service
        self.evidence_service = evidence_service
        self.storage_dir = processed_dir / "eva_operations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._configs: Dict[str, MissionConfigRequest] = {}
        self._missions: Dict[str, EvaMissionEnvelopeResponse] = {}

    @staticmethod
    def _derive_mission_id(config: MissionConfigRequest) -> str:
        if config.mission_id and config.mission_id.strip():
            return config.mission_id.strip()
        digest = hashlib.sha256(
            config.model_dump_json(exclude={"mission_id"}).encode("utf-8")
        ).hexdigest()[:12]
        return f"eva-{digest}"

    def configure_mission(self, config: MissionConfigRequest) -> Dict[str, object]:
        mid = self._derive_mission_id(config)
        cfg_stored = config.model_copy(update={"mission_id": mid})
        self._configs[mid] = cfg_stored
        _atomic_write_json(
            self.storage_dir / f"{mid}.config.json",
            cfg_stored.model_dump_json(indent=2),
        )
        return {"mission_id": mid, "configured": True, "config": cfg_stored}

    def evaluate_mission(self, config: MissionConfigRequest) -> EvaMissionEnvelopeResponse:
        t0 = time.perf_counter()
        mid = self._derive_mission_id(config)
        cfg = config.model_copy(update={"mission_id": mid})
        self._configs[mid] = cfg
        _atomic_write_json(
            self.storage_dir / f"{mid}.config.json",
            cfg.model_dump_json(indent=2),
        )

        # Compute outbound route
        base_constraints = cfg.constraints or RoutePlanningConstraints()
        out_constraints = base_constraints.model_copy(
            update={
                "walking_speed_m_per_s": cfg.walking_speed_mps,
                "return_to_start": False,
            }
        )
        route = self.routing_service.compute_route(
            RouteComputeRequest(
                dataset_id=cfg.dataset_id,
                start=cfg.start,
                destination=cfg.destination,
                mode=cfg.mode,
                target_ids=cfg.selected_target_ids,
                constraints=out_constraints,
            )
        )

        corridor = self.evidence_service.assess_corridor(
            CorridorAssessRequest(
                dataset_id=cfg.dataset_id,
                start=cfg.start,
                destination=cfg.destination,
                route=route,
                mode=cfg.mode,
                corridor_width_m=cfg.corridor_width_m,
                target_segment_length_m=cfg.target_segment_length_m,
                observation_search_radius_m=cfg.observation_search_radius_m,
                selected_target_ids=cfg.selected_target_ids,
                constraints=out_constraints,
            )
        )

        stops_total_s = sum(max(0.0, float(v)) for v in cfg.stop_dwell_seconds.values())
        usable_s = (
            round(cfg.mission_duration_limit_s * (1.0 - cfg.return_reserve_fraction), 1)
            if (cfg.mission_duration_limit_s is not None and cfg.return_reserve_fraction is not None)
            else None
        )

        return_plan = plan_eva_return_route(
            routing_service=self.routing_service,
            dataset_id=cfg.dataset_id,
            outbound_route=route,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=cfg.use_tobler_grade_approximation,
            stop_dwell_total_s=stops_total_s,
            operational_overhead_s=cfg.operational_overhead_s,
            usable_budget_s=usable_s,
            compute_reverse_return_route=cfg.compute_reverse_return_route,
        )

        outbound_const_s = (
            round(route.total_surface_distance_m / cfg.walking_speed_mps, 1)
            if (cfg.walking_speed_mps and cfg.walking_speed_mps > 0)
            else None
        )
        outbound_tobler_s = route.estimated_duration_seconds

        time_budget = evaluate_eva_time_budget(
            outbound_constant_s=outbound_const_s,
            outbound_tobler_s=outbound_tobler_s,
            return_constant_s=return_plan.return_duration_constant_s,
            return_tobler_s=return_plan.return_duration_tobler_s,
            stop_dwell_seconds=cfg.stop_dwell_seconds,
            operational_overhead_s=cfg.operational_overhead_s,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=cfg.use_tobler_grade_approximation,
            mission_duration_limit_s=cfg.mission_duration_limit_s,
            return_reserve_fraction=cfg.return_reserve_fraction,
        )

        energy_budget = evaluate_eva_energy_budget(
            outbound_climb_gain_m=route.total_elevation_gain_m,
            outbound_descent_loss_m=route.total_elevation_loss_m,
            return_climb_gain_m=return_plan.return_elevation_gain_m,
            return_descent_loss_m=return_plan.return_elevation_loss_m,
            astronaut_suit_mass_kg=cfg.astronaut_suit_mass_kg,
            payload_mass_kg=cfg.payload_mass_kg,
        )

        resource_budget = evaluate_eva_resource_budget(
            resources=cfg.resources,
            exposure_duration_s=time_budget.total_required_s,
        )

        schedule = build_eva_schedule(
            corridor=corridor,
            return_plan=return_plan,
            walking_speed_mps=cfg.walking_speed_mps,
            use_tobler_grade_approximation=cfg.use_tobler_grade_approximation,
            stop_dwell_seconds=cfg.stop_dwell_seconds,
            operational_overhead_s=cfg.operational_overhead_s,
            surface_weight_n=energy_budget.surface_weight_n,
        )

        constraints = evaluate_eva_constraints(
            config=cfg,
            route=route,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
            resource_budget=resource_budget,
        )

        missing_inputs = list(
            dict.fromkeys(
                time_budget.missing_inputs
                + energy_budget.missing_inputs
                + resource_budget.missing_inputs
            )
        )

        # Determine overall operational envelope status strictly from verified failures/completeness
        any_fail = any(c.status == "FAIL" for c in constraints)
        if any_fail:
            env_status = EnvelopeFeasibilityStatus.EXCEEDS_CONFIGURED_CONSTRAINTS
        elif time_budget.available and energy_budget.available:
            env_status = EnvelopeFeasibilityStatus.FEASIBLE_WITHIN_CONFIGURED_CONSTRAINTS
        else:
            env_status = EnvelopeFeasibilityStatus.INCOMPLETE_USER_CONSTRAINTS

        uncertainties, limitations = summarize_eva_uncertainties(
            config=cfg,
            corridor=corridor,
            time_budget=time_budget,
            return_plan=return_plan,
        )

        prov = ProvenanceDependencyGraph(
            output_id=mid,
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[cfg.dataset_id],
            input_product_ids=[route.source_product_id],
            input_variables=["route_geometry", "dem_corridor", "user_eva_constraints"],
            input_units=["m", "deg", "s_kg_explicit"],
            input_crs="IAU2000:49900",
            input_resolution_m=route.native_dem_resolution_m,
            method="eva_operational_envelope_v1",
            algorithm_version="eva_envelope_v1",
            parameters={
                "speed_model": time_budget.speed_model_used.value,
                "return_strategy": return_plan.return_strategy,
                "walking_speed_mps": cfg.walking_speed_mps,
                "return_reserve_fraction": cfg.return_reserve_fraction,
            },
            assumptions=uncertainties + limitations,
            intermediate_steps=[
                ProvenanceStep(
                    step_id="eva-outbound-route",
                    label="Outbound A*/Dijkstra Surface Traverse",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[route.route_id],
                    method=f"{route.algorithm} ({route.mode.value})",
                    algorithm_version="routing_v2_science_aware",
                    output_variable="outbound_traverse_geometry",
                    output_units="m",
                ),
                ProvenanceStep(
                    step_id="eva-corridor-evidence",
                    label="Polygon-Masked Corridor Evidence Assessment",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=[corridor.assessment_id],
                    method="terrain_optical_observation_evidence_v2",
                    algorithm_version="terrain_corridor_v3",
                    output_variable="corridor_evidence_summary",
                    output_units="fraction_and_m",
                ),
                ProvenanceStep(
                    step_id="eva-return-and-budgets",
                    label="Return-Route & Time/Energy/Resource Envelope",
                    classification=ScientificDataClassification.USER_ASSUMED,
                    input_ids=["USER_EVA_CONSTRAINTS"],
                    method="explicit_unit_aware_envelope",
                    algorithm_version="eva_envelope_v1",
                    output_variable="eva_operational_envelope",
                    output_units="s_J_and_resource_units",
                ),
            ],
            validation_state="analytical_planning_envelope_not_safety_certified",
        )

        resp = EvaMissionEnvelopeResponse(
            mission_id=mid,
            mission_name=cfg.mission_name,
            study_region=cfg.study_region,
            dataset_id=cfg.dataset_id,
            source_product_id=route.source_product_id,
            route_id=route.route_id,
            assessment_id=corridor.assessment_id,
            envelope_status=env_status,
            operational_safety_certified=False,
            missing_inputs=missing_inputs,
            config=cfg,
            outbound_summary={
                "horizontal_distance_m": route.total_horizontal_distance_m,
                "surface_distance_m": route.total_surface_distance_m,
                "elevation_gain_m": route.total_elevation_gain_m,
                "elevation_loss_m": route.total_elevation_loss_m,
                "max_slope_deg": route.max_slope_deg,
                "segment_count": len(corridor.segments),
            },
            time_budget=time_budget,
            energy_budget=energy_budget,
            resource_budget=resource_budget,
            return_plan=return_plan,
            schedule=schedule,
            constraints=constraints,
            uncertainty_notes=uncertainties,
            limitations=limitations,
            cache_validity=CacheValidityState.CURRENT,
            provenance_graph=prov,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )
        self._missions[mid] = resp
        _atomic_write_json(
            self.storage_dir / f"{mid}.envelope.json",
            resp.model_dump_json(indent=2),
        )
        return resp

    def get_mission(self, mission_id: str) -> Optional[EvaMissionEnvelopeResponse]:
        if mission_id in self._missions:
            return self._missions[mission_id]
        path = self.storage_dir / f"{mission_id}.envelope.json"
        if path.exists():
            obj = EvaMissionEnvelopeResponse.model_validate_json(path.read_text(encoding="utf-8"))
            self._missions[mission_id] = obj
            return obj
        return None
