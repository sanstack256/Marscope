"""
MARSCOPE Configurable Human Mobility Scenario Registry
Martian Surface Intelligence & Exploration System

Manages user-configured MobilityScenario definitions with strict provenance
separation between source-supported physical constants, user-configured
planning assumptions, model-derived parameters, and unconfigured capabilities.
Never injects arbitrary default walking speeds, slope limits, or physiology models.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from app.mobility.models import ParameterOriginType
from app.mobility.schemas import (
    MobilityScenario,
    MobilityScenarioCreateRequest,
    ScenarioParameterRecord,
)
from app.physics.models.surface import calculate_surface_weight
from app.physics.registry.parameters import get_parameter


class MobilityScenarioRegistry:
    """Persistent registry of provenance-tagged MobilityScenario configurations."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._scenarios: Dict[str, MobilityScenario] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw:
                    sc = MobilityScenario.model_validate(item)
                    self._scenarios[sc.scenario_id] = sc
        except Exception:
            self._scenarios = {}

    def _save(self) -> None:
        payload = [sc.model_dump() for sc in self.list_scenarios()]
        tmp = self.storage_path.parent / f".{self.storage_path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.storage_path)

    @staticmethod
    def build_scenario(
        req: MobilityScenarioCreateRequest,
        scenario_id: Optional[str] = None,
    ) -> MobilityScenario:
        """
        Construct and validate a `MobilityScenario` from `MobilityScenarioCreateRequest`
        with complete parameter provenance records.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        g_param = get_parameter("mars_standard_gravity")
        g_val = g_param.value if g_param else 3.72076

        params: Dict[str, ScenarioParameterRecord] = {
            "mars_standard_gravity": ScenarioParameterRecord(
                name="mars_standard_gravity",
                value=g_val,
                units="m/s^2",
                origin=ParameterOriginType.SOURCE_SUPPORTED_PHYSICAL_PARAMETER,
                valid_range=[3.70, 3.75],
                provenance=(
                    g_param.source
                    if g_param
                    else "NASA Planetary Fact Sheet - Mars (Williams, 2024, NSSDC)"
                ),
                version="1.0.0",
                is_validated_physiological_or_suit_standard=False,
            )
        }

        unconfigured: List[str] = [
            "metabolic_oxygen_consumption_not_modeled_without_validated_biomedical_dataset",
            "fatigue_accumulation_not_modeled",
            "suit_joint_torque_and_thermal_limits_not_modeled",
            "surface_traction_and_slip_hazard_not_modeled",
        ]
        notes: List[str] = list(req.notes or [])

        # Reference walking speed (never defaulted!)
        if req.reference_walking_speed_m_per_s is not None:
            params["reference_walking_speed_m_per_s"] = ScenarioParameterRecord(
                name="reference_walking_speed_m_per_s",
                value=req.reference_walking_speed_m_per_s,
                units="m/s",
                origin=ParameterOriginType.USER_CONFIGURED_ASSUMPTION,
                valid_range=[0.001, 10.0],
                provenance=req.walking_speed_provenance
                or "Explicitly configured by user for scenario traversal-time estimation; not a universal EVA standard.",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
            time_ready = True
        else:
            params["reference_walking_speed_m_per_s"] = ScenarioParameterRecord(
                name="reference_walking_speed_m_per_s",
                value=None,
                units="m/s",
                origin=ParameterOriginType.UNAVAILABLE,
                valid_range=[0.001, 10.0],
                provenance="Not configured; MARSCOPE never injects an arbitrary default walking speed.",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
            time_ready = False
            unconfigured.insert(
                0,
                "traversal_time_estimation_requires_explicit_reference_walking_speed_m_per_s",
            )
            notes.append(
                "No reference_walking_speed_m_per_s configured: physical terrain measurements will be "
                "computed, while traversal time and speed estimates will be reported as unavailable."
            )

        # Planning slope threshold (optional user assumption, never a 25 deg safety default)
        if req.planning_max_slope_deg is not None:
            params["planning_max_slope_deg"] = ScenarioParameterRecord(
                name="planning_max_slope_deg",
                value=req.planning_max_slope_deg,
                units="degrees",
                origin=ParameterOriginType.USER_CONFIGURED_ASSUMPTION,
                valid_range=[0.0, 90.0],
                provenance="User-configured scenario planning slope exclusion threshold (not a validated safety limit).",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
        else:
            params["planning_max_slope_deg"] = ScenarioParameterRecord(
                name="planning_max_slope_deg",
                value=None,
                units="degrees",
                origin=ParameterOriginType.UNAVAILABLE,
                valid_range=[0.0, 90.0],
                provenance="No planning slope threshold configured; no cells are excluded by slope threshold.",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )

        # Planning roughness threshold (optional user assumption)
        if req.planning_max_roughness_m is not None:
            params["planning_max_roughness_m"] = ScenarioParameterRecord(
                name="planning_max_roughness_m",
                value=req.planning_max_roughness_m,
                units="meters",
                origin=ParameterOriginType.USER_CONFIGURED_ASSUMPTION,
                valid_range=[0.0, None],
                provenance="User-configured scenario planning TRI roughness exclusion threshold (not a validated safety limit).",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
        else:
            params["planning_max_roughness_m"] = ScenarioParameterRecord(
                name="planning_max_roughness_m",
                value=None,
                units="meters",
                origin=ParameterOriginType.UNAVAILABLE,
                valid_range=[0.0, None],
                provenance="No planning roughness threshold configured.",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )

        # Mass and Mars surface weight (optional)
        total_mass_kg: Optional[float] = None
        mars_weight_n: Optional[float] = None
        mass_parts = [
            m
            for m in (req.astronaut_body_mass_kg, req.suit_mass_kg, req.carried_load_mass_kg)
            if m is not None
        ]
        if mass_parts:
            total_mass_kg = round(float(sum(mass_parts)), 4)
            mars_weight_n = round(float(calculate_surface_weight(total_mass_kg).calculated_value), 4)
            params["total_mass_kg"] = ScenarioParameterRecord(
                name="total_mass_kg",
                value=total_mass_kg,
                units="kg",
                origin=ParameterOriginType.USER_CONFIGURED_ASSUMPTION,
                valid_range=[0.001, 1500.0],
                provenance="Sum of explicitly configured astronaut_body_mass_kg, suit_mass_kg, and carried_load_mass_kg.",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
            params["mars_surface_weight_n"] = ScenarioParameterRecord(
                name="mars_surface_weight_n",
                value=mars_weight_n,
                units="N",
                origin=ParameterOriginType.MODEL_DERIVED_PARAMETER,
                valid_range=[0.0, None],
                provenance="Derived via W = m_total * g_Mars (g_Mars = 3.72076 m/s^2, NASA Planetary Fact Sheet).",
                version=req.version,
                is_validated_physiological_or_suit_standard=False,
            )
        else:
            unconfigured.append("gravitational_force_and_potential_energy_require_explicit_mass_kg")

        if scenario_id is None:
            digest_seed = json.dumps(
                {
                    "name": req.name,
                    "version": req.version,
                    "speed": req.reference_walking_speed_m_per_s,
                    "max_slope": req.planning_max_slope_deg,
                    "max_rough": req.planning_max_roughness_m,
                    "total_mass": total_mass_kg,
                    "ts": now_utc,
                },
                sort_keys=True,
            )
            scenario_id = f"scen_{hashlib.sha256(digest_seed.encode('utf-8')).hexdigest()[:12]}"

        return MobilityScenario(
            scenario_id=scenario_id,
            name=req.name,
            description=req.description,
            version=req.version,
            created_at_utc=now_utc,
            astronaut_position=req.astronaut_position,
            destination_position=req.destination_position,
            study_bounds=req.study_bounds,
            reference_walking_speed_m_per_s=req.reference_walking_speed_m_per_s,
            walking_speed_provenance=req.walking_speed_provenance,
            planning_max_slope_deg=req.planning_max_slope_deg,
            planning_max_roughness_m=req.planning_max_roughness_m,
            roughness_window_radius_m=req.roughness_window_radius_m,
            slope_speed_adjustment=req.slope_speed_adjustment,
            roughness_speed_adjustment=req.roughness_speed_adjustment,
            astronaut_body_mass_kg=req.astronaut_body_mass_kg,
            suit_mass_kg=req.suit_mass_kg,
            carried_load_mass_kg=req.carried_load_mass_kg,
            total_mass_kg=total_mass_kg,
            mars_surface_weight_n=mars_weight_n,
            parameters=params,
            traversal_time_estimation_ready=time_ready,
            unconfigured_capabilities=unconfigured,
            notes=notes,
        )

    def create_scenario(self, req: MobilityScenarioCreateRequest) -> MobilityScenario:
        sc = self.build_scenario(req)
        self._scenarios[sc.scenario_id] = sc
        self._save()
        return sc

    def get_scenario(self, scenario_id: str) -> Optional[MobilityScenario]:
        return self._scenarios.get(scenario_id)

    def list_scenarios(self) -> List[MobilityScenario]:
        return sorted(self._scenarios.values(), key=lambda s: s.created_at_utc, reverse=True)
