"""
MARSCOPE Unit-Aware Explicit Resource Budget Evaluator
Computes Q_used = Q_dot * t ONLY when the user explicitly configures resource
quantities, compatible rate units, and mission duration. Never invents oxygen,
battery, CO2 scrubber, or cooling consumption rates.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.eva_operations.schemas import (
    ExplicitResourceSpec,
    ResourceBudgetReport,
    ResourceEvaluationEntry,
)
from app.science.provenance_graph import ScientificDataClassification

# Canonical family conversion factors into base unit of each family
_UNIT_FAMILY: Dict[str, Tuple[str, float]] = {
    "kg": ("mass", 1.0),
    "g": ("mass", 0.001),
    "l": ("volume", 1.0),
    "L": ("volume", 1.0),
    "mL": ("volume", 0.001),
    "ml": ("volume", 0.001),
    "J": ("energy", 1.0),
    "j": ("energy", 1.0),
    "kJ": ("energy", 1000.0),
    "kj": ("energy", 1000.0),
    "Wh": ("energy", 3600.0),
    "wh": ("energy", 3600.0),
    "kWh": ("energy", 3600000.0),
    "kwh": ("energy", 3600000.0),
    "kPa": ("pressure", 1.0),
    "kpa": ("pressure", 1.0),
    "bar": ("pressure", 100.0),
    "psi": ("pressure", 6.894757),
    "s": ("time", 1.0),
    "min": ("time", 60.0),
    "h": ("time", 3600.0),
    "hr": ("time", 3600.0),
}

_TIME_DIVISORS: Dict[str, float] = {
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
}


def _convert_rate_to_quantity_per_second(
    rate_val: float, rate_unit: str, target_qty_unit: str
) -> Tuple[Optional[float], Optional[str]]:
    """
    Convert `rate_val` in `rate_unit` into `target_qty_unit / second`.
    Handles compound units (e.g. 'kg/h', 'Wh/h', 'L/min', 'kJ/s') and aliases ('W' -> 'J/s', 'kW' -> 'kJ/s').
    """
    ru = rate_unit.strip()
    if ru == "W":
        ru = "J/s"
    elif ru == "kW":
        ru = "kJ/s"

    if "/" not in ru:
        return None, f"Rate unit '{rate_unit}' must be expressed per time (e.g. 'kg/h', 'Wh/h', 'L/min', 'W')."

    num_str, den_str = [p.strip() for p in ru.split("/", 1)]
    if num_str not in _UNIT_FAMILY or target_qty_unit.strip() not in _UNIT_FAMILY:
        return None, f"Unsupported unit pair: quantity '{target_qty_unit}' vs rate numerator '{num_str}'."
    if den_str not in _TIME_DIVISORS:
        return None, f"Unsupported time divisor '/{den_str}' in rate unit '{rate_unit}'."

    num_fam, num_scale = _UNIT_FAMILY[num_str]
    qty_fam, qty_scale = _UNIT_FAMILY[target_qty_unit.strip()]
    if num_fam != qty_fam:
        return (
            None,
            f"Incompatible physical unit families: quantity '{target_qty_unit}' ({qty_fam}) vs rate '{rate_unit}' ({num_fam}).",
        )

    # Convert rate_val * num_scale / qty_scale / time_div
    rate_in_target_per_s = float(rate_val) * (num_scale / qty_scale) / _TIME_DIVISORS[den_str]
    return rate_in_target_per_s, None


def evaluate_eva_resource_budget(
    *,
    resources: List[ExplicitResourceSpec],
    exposure_duration_s: Optional[float],
) -> ResourceBudgetReport:
    if not resources:
        return ResourceBudgetReport(
            overall_status="UNAVAILABLE",
            entries=[],
            missing_inputs=["explicit_resource_limits"],
            limitations=[
                "No user-supplied consumable/energy resource budgets configured (O2, power, cooling water); "
                "MARSCOPE never guesses human physiological or suit consumption rates."
            ],
        )

    entries: List[ResourceEvaluationEntry] = []
    any_fail = False
    any_unavailable = False

    for spec in resources:
        rate_per_s, err = _convert_rate_to_quantity_per_second(
            spec.consumption_rate, spec.rate_unit, spec.unit
        )
        if err or rate_per_s is None:
            any_unavailable = True
            entries.append(
                ResourceEvaluationEntry(
                    resource_name=spec.resource_name,
                    status="UNIT_MISMATCH",
                    initial_quantity=round(spec.initial_quantity, 4),
                    unit=spec.unit,
                    exposure_duration_s=exposure_duration_s,
                    explanation=err or "Unit mismatch.",
                )
            )
            continue

        if exposure_duration_s is None:
            any_unavailable = True
            entries.append(
                ResourceEvaluationEntry(
                    resource_name=spec.resource_name,
                    status="UNAVAILABLE",
                    initial_quantity=round(spec.initial_quantity, 4),
                    unit=spec.unit,
                    normalized_rate_per_second=round(rate_per_s, 8),
                    exposure_duration_s=None,
                    explanation=(
                        "Mission exposure duration unavailable (configure walking_speed_mps) to evaluate Q_used = Q_dot * t."
                    ),
                )
            )
            continue

        consumed = rate_per_s * float(exposure_duration_s)
        reserve_req = spec.initial_quantity * spec.reserve_fraction
        remaining = spec.initial_quantity - consumed
        margin = remaining - reserve_req
        ok = margin >= 0.0
        if not ok:
            any_fail = True

        entries.append(
            ResourceEvaluationEntry(
                resource_name=spec.resource_name,
                status="WITHIN_LIMIT" if ok else "EXCEEDS_LIMIT",
                initial_quantity=round(spec.initial_quantity, 4),
                unit=spec.unit,
                normalized_rate_per_second=round(rate_per_s, 8),
                exposure_duration_s=round(float(exposure_duration_s), 1),
                reserve_required=round(reserve_req, 4),
                estimated_consumed=round(consumed, 4),
                remaining_after_eva=round(remaining, 4),
                margin_above_reserve=round(margin, 4),
                assumption_classification=ScientificDataClassification.USER_ASSUMED,
                explanation=(
                    f"Q_used = {rate_per_s:.6g} {spec.unit}/s * {exposure_duration_s:.1f} s = "
                    f"{consumed:.3f} {spec.unit}; remaining {remaining:.3f} {spec.unit} "
                    f"({'meets' if ok else 'violates'} protected reserve {reserve_req:.3f} {spec.unit})."
                ),
            )
        )

    if any_fail:
        overall = "EXCEEDS_CONSTRAINTS"
    elif any_unavailable:
        overall = "UNAVAILABLE"
    else:
        overall = "WITHIN_CONSTRAINTS"

    return ResourceBudgetReport(
        overall_status=overall,
        entries=entries,
        missing_inputs=[] if exposure_duration_s is not None else ["walking_speed_mps"],
        limitations=[
            "Evaluates linear user-configured rate Q_used = Q_dot * t strictly; does not model slope-dependent metabolic oxygen spike or suit thermal load."
        ],
    )
