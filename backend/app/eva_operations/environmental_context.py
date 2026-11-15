"""
MARSCOPE Environmental & Radiation Context Engine (Prompt 20 Part 10).

Strictly separates:
  1. Historical NASA archive observations (Curiosity MSL RAD & REMS in Gale Crater),
     labeled explicitly as ARCHIVE_OBSERVATION / ARCHIVE_DERIVED.
  2. Live surface weather and real-time solar energetic particle (SEP) radiation telemetry,
     labeled honestly as UNAVAILABLE unless an authenticated live environmental provider is connected.

Never interpolates point archive records into live global weather forecasts or physiological hazard scores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.eva_operations.locomotion import EpistemicClassification
from app.physics.registry.parameters import get_parameter


class EnvironmentalObservationRecord(BaseModel):
    """Single historical archive environmental or radiation reference record."""

    record_id: str
    instrument: str
    mission: str
    modality: str  # radiation_dose_rate | atmospheric_pressure | surface_temperature
    observation_type: str = "ARCHIVE_OBSERVATION"
    classification: str = EpistemicClassification.ARCHIVE_DERIVED.value
    location_description: str
    sol_or_epoch_range: str
    value: Optional[float] = None
    value_range: Optional[List[float]] = None
    unit: str
    source_citation: str
    scientific_caveat: str


class EvaEnvironmentalContextReport(BaseModel):
    """Environmental and radiation context report for an EVA mission (Part 10)."""

    study_region: str
    live_weather_available: bool = False
    live_weather_status: str = "LIVE SURFACE WEATHER UNAVAILABLE"
    live_radiation_available: bool = False
    live_radiation_status: str = "LIVE RADIATION TELEMETRY UNAVAILABLE"
    archive_observations: List[EnvironmentalObservationRecord] = Field(default_factory=list)
    eva_duration_s: Optional[float] = None
    archive_reference_gcr_dose_msv: Optional[float] = None
    archive_reference_gcr_dose_usv: Optional[float] = None
    radiation_calculation_note: str
    prohibited_inferences: List[str] = Field(
        default_factory=lambda: [
            "Historical REMS/RAD archive measurements are NOT live weather or real-time space-weather forecasts.",
            "Point rover measurements inside Gale Crater cannot be interpolated into global or regional meteorology.",
            "No physiological radiation sickness, cancer probability, or suit thermal comfort score is fabricated.",
        ]
    )


def evaluate_eva_environmental_context(
    *,
    study_region: str = "Gale Crater / Mount Sharp",
    mission_duration_s: Optional[float] = None,
) -> EvaEnvironmentalContextReport:
    rad_param = get_parameter("nominal_gcr_dose_rate")
    rad_val_msv_per_day: Optional[float] = (
        float(rad_param.value)
        if (rad_param is not None and rad_param.value is not None)
        else None
    )

    records: List[EnvironmentalObservationRecord] = []
    if rad_val_msv_per_day is not None and rad_param is not None:
        records.append(
            EnvironmentalObservationRecord(
                record_id="msl_rad_gcr_surface_baseline",
                instrument="RAD (Radiation Assessment Detector)",
                mission="Mars Science Laboratory (Curiosity)",
                modality="radiation_dose_rate",
                observation_type="ARCHIVE_OBSERVATION",
                classification=EpistemicClassification.ARCHIVE_DERIVED.value,
                location_description="Gale Crater floor / Bradbury Landing — Mount Sharp traverse",
                sol_or_epoch_range="Sols 13–300 (solar quiet period GCR baseline)",
                value=rad_val_msv_per_day,
                unit=rad_param.units,
                source_citation=rad_param.source,
                scientific_caveat=(
                    f"Historical Galactic Cosmic Ray (GCR) surface dose rate ({rad_val_msv_per_day:.2f} {rad_param.units}). "
                    "Excludes transient Solar Energetic Particle (SEP) events and suit shielding attenuation."
                ),
            )
        )

    press_param = get_parameter("nominal_gale_surface_pressure")
    records.append(
        EnvironmentalObservationRecord(
            record_id="msl_rems_gale_pressure_archive",
            instrument="REMS (Rover Environmental Monitoring Station)",
            mission="Mars Science Laboratory (Curiosity)",
            modality="atmospheric_pressure",
            observation_type="ARCHIVE_OBSERVATION",
            classification=EpistemicClassification.ARCHIVE_DERIVED.value,
            location_description="Gale Crater / Aeolis Mons lower slopes",
            sol_or_epoch_range="Multi-year seasonal cycle (PDS Atmospheres Node archive)",
            value=float(press_param.value) if press_param is not None else None,
            value_range=list(press_param.validity_range) if (press_param is not None and press_param.validity_range) else [700.0, 920.0],
            unit=press_param.units if press_param is not None else "Pa",
            source_citation=press_param.source if press_param is not None else "Haberle et al. (2014); NASA PDS Atmospheres MSL-M-REMS-2/4/5.",
            scientific_caveat=(
                "Historical seasonal surface pressure range observed by Curiosity REMS in Gale Crater; "
                "NOT a live barometric reading."
            ),
        )
    )
    temp_param = get_parameter("nominal_gale_surface_temp")
    records.append(
        EnvironmentalObservationRecord(
            record_id="msl_rems_gale_temperature_archive",
            instrument="REMS (Rover Environmental Monitoring Station)",
            mission="Mars Science Laboratory (Curiosity)",
            modality="surface_temperature",
            observation_type="ARCHIVE_OBSERVATION",
            classification=EpistemicClassification.ARCHIVE_DERIVED.value,
            location_description="Gale Crater / Aeolis Mons lower slopes",
            sol_or_epoch_range="Multi-year diurnal/seasonal cycle (PDS Atmospheres Node archive)",
            value=float(temp_param.value) if temp_param is not None else None,
            value_range=list(temp_param.validity_range) if (temp_param is not None and temp_param.validity_range) else [180.0, 275.0],
            unit=temp_param.units if temp_param is not None else "K",
            source_citation=temp_param.source if temp_param is not None else "NASA PDS Atmospheres MSL-M-REMS-2/4/5.",
            scientific_caveat=(
                "Historical diurnal/seasonal near-surface air temperature range in Gale Crater; "
                "NOT a live temperature forecast."
            ),
        )
    )

    dose_msv: Optional[float] = None
    dose_usv: Optional[float] = None
    if rad_val_msv_per_day is not None and mission_duration_s is not None and mission_duration_s >= 0.0:
        dose_msv = round(rad_val_msv_per_day * (float(mission_duration_s) / 86400.0), 6)
        dose_usv = round(dose_msv * 1000.0, 3)
        rad_note = (
            f"Archive-reference GCR exposure over {mission_duration_s / 3600.0:.2f} h EVA: "
            f"D_GCR = {rad_val_msv_per_day:.2f} mSv/day * ({mission_duration_s:.1f} s / 86400 s/day) = "
            f"{dose_usv:.3f} uSv ({dose_msv:.6f} mSv). Historical GCR baseline only; excludes SEP events."
        )
    elif rad_val_msv_per_day is None:
        rad_note = "Registry parameter 'nominal_gcr_dose_rate' is unavailable."
    else:
        rad_note = (
            f"Historical Curiosity RAD GCR rate is {rad_val_msv_per_day:.2f} mSv/day (ARCHIVE_OBSERVATION); "
            "supply walking_speed_mps to integrate EVA duration exposure."
        )

    return EvaEnvironmentalContextReport(
        study_region=study_region,
        live_weather_available=False,
        live_weather_status="LIVE SURFACE WEATHER UNAVAILABLE",
        live_radiation_available=False,
        live_radiation_status="LIVE RADIATION TELEMETRY UNAVAILABLE",
        archive_observations=records,
        eva_duration_s=round(mission_duration_s, 2) if mission_duration_s is not None else None,
        archive_reference_gcr_dose_msv=dose_msv,
        archive_reference_gcr_dose_usv=dose_usv,
        radiation_calculation_note=rad_note,
    )
