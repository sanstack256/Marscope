"""
MARSCOPE EVA Uncertainty & Limitation Synthesizer
"""

from __future__ import annotations

from typing import List

from app.evidence_intelligence.schemas import CorridorAssessment
from app.eva_operations.schemas import MissionConfigRequest, ReturnPlanReport, TimeBudgetBreakdown


def summarize_eva_uncertainties(
    *,
    config: MissionConfigRequest,
    corridor: CorridorAssessment,
    time_budget: TimeBudgetBreakdown,
    return_plan: ReturnPlanReport,
) -> tuple[List[str], List[str]]:
    uncertainties: List[str] = [
        f"DEM posting {corridor.uncertainty.horizontal_resolution_m:.2f} m/px leaves sub-pixel boulders, scarps, and dust pockets unresolved.",
        f"Duration mode ({time_budget.speed_model_used.value}) relies on user speed assumptions rather than validated Martian suit biomechanics.",
    ]
    if return_plan.asymmetric_climb_delta_m > 1.0:
        uncertainties.append(
            f"Return climb exceeds outbound climb by +{return_plan.asymmetric_climb_delta_m:.1f} m; fatigue on return cannot be neglected."
        )
    raw_opt_cov = corridor.coverage_summary.get("mean_optical_coverage_fraction")
    if raw_opt_cov is None or float(raw_opt_cov) < 0.5:
        uncertainties.append("Partial, zero, or unverified HiRISE optical coverage leaves surface blockiness unverified visually.")

    limitations: List[str] = [
        "NOT a certified human astronaut EVA safety system.",
        "No live weather, dust optical depth (tau), radiation dose, or live crew localization is ingested without explicit external feeds.",
        "Regolith bearing capacity, boot sinkage, suit cooling loop heat rejection, and metabolic oxygen spikes remain unmodeled.",
    ]
    return uncertainties, limitations
