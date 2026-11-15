"""
MARSCOPE EVA Uncertainty & Limitation Synthesizer (Prompt 20 Extended)
"""

from __future__ import annotations

from typing import List

from app.evidence_intelligence.schemas import CorridorAssessment
from app.eva_operations.locomotion import LocomotionModelCategory
from app.eva_operations.schemas import (
    MissionConfigRequest,
    ReturnPlanReport,
    TimeBudgetBreakdown,
)


def summarize_eva_uncertainties(
    *,
    config: MissionConfigRequest,
    corridor: CorridorAssessment,
    time_budget: TimeBudgetBreakdown,
    return_plan: ReturnPlanReport,
) -> tuple[List[str], List[str]]:
    res_m = float(corridor.uncertainty.horizontal_resolution_m)
    min_feature_m = max(1.0, 3.0 * res_m)
    uncertainties: List[str] = [
        f"DEM posting {res_m:.2f} m/px leaves sub-pixel boulders, scarps, and dust pockets smaller than ~{min_feature_m:.1f} m unresolved.",
        f"Duration mode ({time_budget.speed_model_used.value} | {time_budget.locomotion_category}) relies on configured/exploratory speed models rather than validated Martian suit biomechanics.",
    ]
    if config.locomotion_category == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL and not config.validated_suit_model_source:
        uncertainties.append(
            "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL returned MODEL_UNAVAILABLE because no validated pressurized suit locomotion dataset is supplied."
        )
    if return_plan.asymmetric_climb_delta_m > 1.0:
        uncertainties.append(
            f"Return climb exceeds outbound climb by +{return_plan.asymmetric_climb_delta_m:.1f} m; asymmetric return climb load must be tracked."
        )
    raw_opt_cov = corridor.coverage_summary.get("mean_optical_coverage_fraction")
    if raw_opt_cov is None or float(raw_opt_cov) < 0.5:
        uncertainties.append(
            "Partial, zero, or unverified HiRISE optical coverage leaves surface blockiness unverified visually."
        )

    limitations: List[str] = [
        "NOT a certified human astronaut EVA safety system.",
        "Regolith bearing capacity, soil shear strength, boot traction, sinkage, dust layer stability, and subsurface voids are UNKNOWN_UNMEASURED.",
        "No live weather, dust optical depth (tau), solar energetic particle (SEP) radiation dose, or live crew localization is ingested unless an authenticated external telemetry/environment stream is explicitly connected.",
        "Spacesuit metabolic rate, suit cooling loop heat rejection, CO2 scrubbing dynamics, and physiological fatigue remain unmodeled.",
    ]
    return uncertainties, limitations
