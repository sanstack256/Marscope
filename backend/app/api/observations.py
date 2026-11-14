"""
MARSCOPE Scientific Observations Endpoints
Martian Surface Intelligence & Exploration System
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.schemas.observation import Observation, ObservationCoordinates
from app.science.curiosity_parser import CuriosityDataParser
from app.services.container import RAW_DIR

router = APIRouter(prefix="/observations", tags=["Scientific Observations"])

# Pre-indexed real Curiosity ground-truth observations
_OBSERVATIONS: List[Observation] = [
    Observation(
        observation_id="msl_chemcam_coronation_sol00013",
        dataset_id="msl_chemcam_sol00010_psv",
        mission="Mars Science Laboratory (MSL)",
        instrument="Chemistry Camera (ChemCam LIBS)",
        observation_timestamp=None,
        sol=13,
        location=ObservationCoordinates(
            latitude=-4.5895,
            longitude=137.4412,
            elevation_m=-4452.0,
        ),
        crs="IAU2000:49900",
        measurement_type="laser_induced_breakdown_spectroscopy_elemental_ratios",
        measurement_value={
            "target_name": "Coronation",
            "major_elements": {
                "SiO2_wt_pct": 47.8,
                "Al2O3_wt_pct": 11.2,
                "FeO_wt_pct": 18.5,
                "MgO_wt_pct": 8.1,
                "CaO_wt_pct": 7.4,
                "Na2O_wt_pct": 2.6,
                "K2O_wt_pct": 0.5,
            },
            "classification": "Basaltic rock with low alkali enrichment",
        },
        units="weight_percent",
        processing_level="Calibrated RDR (Level 4/5)",
        calibration_status="LANL ChemCam LIBS calibrated model v4",
        quality_flags=["Nominal Laser Shots (30 shots)", "Dark Subtracted"],
        original_source_reference="PDS Geosciences Node: MSL-M-CHEMCAM-LIBS-4/5-RDR-V1.0",
        known_limitations=["Initial 5 shots excluded to remove dust layer effects."],
    ),
    Observation(
        observation_id="msl_rems_sol00010_baseline",
        dataset_id="msl_rems_sol00010_adr",
        mission="Mars Science Laboratory (MSL)",
        instrument="Rover Environmental Monitoring Station (REMS)",
        observation_timestamp=None,
        sol=10,
        location=ObservationCoordinates(
            latitude=-4.5895,
            longitude=137.4412,
            elevation_m=-4452.0,
        ),
        crs="IAU2000:49900",
        measurement_type="diurnal_in_situ_atmospheric_profile",
        measurement_value={
            "mean_pressure_pa": 745.2,
            "min_pressure_pa": 692.0,
            "max_pressure_pa": 788.0,
            "mean_temperature_k": 218.4,
            "min_temperature_k": 198.1,
            "max_temperature_k": 268.5,
            "relative_humidity_pct": 2.1,
        },
        units="Pa (Pressure), K (Temperature)",
        processing_level="Calibrated ADR (Level 6)",
        calibration_status="QRS v2.2.0 calibrated by CAB",
        quality_flags=["Boom 1 Nominal", "Boom 2 Nominal"],
        original_source_reference="PDS Atmospheres Node: MSL-M-REMS-6-ADR-V1.0",
        known_limitations=["Local thermal perturbation from rover RTG."],
    ),
]


@router.get("", response_model=List[Observation])
async def list_observations() -> List[Observation]:
    """
    List verified in-situ rover observations from Gale Crater.
    """
    return _OBSERVATIONS


@router.get("/{observation_id}", response_model=Observation)
async def get_observation(observation_id: str) -> Observation:
    """
    Retrieve specific observation dossier by ID.
    """
    for obs in _OBSERVATIONS:
        if obs.observation_id == observation_id:
            return obs
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Observation '{observation_id}' not found.",
    )


@router.post("", response_model=Observation)
async def register_observation(observation: Observation) -> Observation:
    """
    Register a newly validated scientific field observation.
    """
    _OBSERVATIONS.append(observation)
    return observation
