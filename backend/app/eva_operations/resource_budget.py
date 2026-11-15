"""
MARSCOPE Unit-Aware Explicit Resource Budget Evaluator (Prompt 20 Part 2.4 & Part 6)
Computes Q_used = Q_dot * t (or piecewise phase-integrated Q_used = sum_p Q_dot_p * dt_p)
ONLY when the user explicitly configures resource quantities, compatible rate units,
and mission duration. Never invents oxygen, battery, CO2 scrubber, or cooling consumption rates.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.eva_operations.schemas import (
    ExplicitResourceSpec,
    ExtensibleResourceCategory,
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


def _infer_category(resource_name: str, explicit_cat: Optional[ExtensibleResourceCategory]) -> str:
    if explicit_cat is not None:
        return explicit_cat.value
    rn = resource_name.lower()
    if "o2" in rn or "oxygen" in rn:
        return ExtensibleResourceCategory.OXYGEN_INVENTORY.value
    if "co2" in rn or "scrub" in rn or "liOh" in rn.lower():
        return ExtensibleResourceCategory.CO2_REMOVAL_CAPACITY.value
    if "batt" in rn or "power" in rn or "wh" in rn or "energy" in rn:
        return ExtensibleResourceCategory.BATTERY_ENERGY.value
    if "cool" in rn or "sublim" in rn or "feedwater" in rn:
        return ExtensibleResourceCategory.COOLING_RESOURCES.value
    if "therm" in rn or "heat" in rn:
        return ExtensibleResourceCategory.THERMAL_MANAGEMENT_CAPACITY.value
    if "water" in rn or "h2o" in rn or "drink" in rn:
        return ExtensibleResourceCategory.WATER.value
    if "comm" in rn or "radio" in rn:
        return ExtensibleResourceCategory.COMMUNICATIONS_CAPACITY.value
    if "nav" in rn or "beacon" in rn:
        return ExtensibleResourceCategory.NAVIGATION_LOCALIZATION_AVAILABILITY.value
    if "inst" in rn or "sample" in rn or "drill" in rn:
        return ExtensibleResourceCategory.SCIENTIFIC_INSTRUMENT_CONSUMABLES.value
    if "payload" in rn or "mass" in rn:
        return ExtensibleResourceCategory.PAYLOAD_CONSTRAINTS.value
    return ExtensibleResourceCategory.OXYGEN_CONSUMPTION.value


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

    rate_in_target_per_s = float(rate_val) * (num_scale / qty_scale) / _TIME_DIVISORS[den_str]
    return rate_in_target_per_s, None


def evaluate_eva_resource_budget(
    *,
    resources: List[ExplicitResourceSpec],
    exposure_duration_s: Optional[float],
    phase_durations_s: Optional[Dict[str, float]] = None,
) -> ResourceBudgetReport:
    category_coverage: Dict[str, str] = {
        cat.value: "UNAVAILABLE_NOT_SUPPLIED" for cat in ExtensibleResourceCategory
    }

    if not resources:
        return ResourceBudgetReport(
            overall_status="UNAVAILABLE",
            entries=[],
            category_coverage=category_coverage,
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
        cat_key = _infer_category(spec.resource_name, spec.category)
        rate_per_s, err = _convert_rate_to_quantity_per_second(
            spec.consumption_rate, spec.rate_unit, spec.unit
        )
        if err or rate_per_s is None:
            any_unavailable = True
            category_coverage[cat_key] = "UNIT_MISMATCH"
            entries.append(
                ResourceEvaluationEntry(
                    resource_name=spec.resource_name,
                    category=cat_key,
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
            category_coverage[cat_key] = "UNAVAILABLE_DURATION_MISSING"
            entries.append(
                ResourceEvaluationEntry(
                    resource_name=spec.resource_name,
                    category=cat_key,
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

        # Check if phase-specific rate integration applies
        integration_mode = "CONSTANT_RATE_Q_DOT_T"
        equation_str = "Q_used = Q_dot * t"
        phase_breakdown: Dict[str, float] = {}
        consumed = 0.0

        if spec.phase_rates and phase_durations_s:
            phase_rate_map: Dict[str, float] = {}
            unit_err: Optional[str] = None
            for pr in spec.phase_rates:
                p_rate_s, p_err = _convert_rate_to_quantity_per_second(
                    pr.consumption_rate, pr.rate_unit, spec.unit
                )
                if p_err or p_rate_s is None:
                    unit_err = p_err or "Phase rate unit mismatch."
                    break
                phase_rate_map[pr.phase] = p_rate_s

            if unit_err is not None:
                any_unavailable = True
                category_coverage[cat_key] = "UNIT_MISMATCH"
                entries.append(
                    ResourceEvaluationEntry(
                        resource_name=spec.resource_name,
                        category=cat_key,
                        status="UNIT_MISMATCH",
                        initial_quantity=round(spec.initial_quantity, 4),
                        unit=spec.unit,
                        exposure_duration_s=exposure_duration_s,
                        explanation=unit_err,
                    )
                )
                continue

            integration_mode = "PHASE_INTEGRATED_Q_DOT_T"
            equation_str = "Q_used = sum_phase(Q_dot_phase * dt_phase)"
            accounted_s = 0.0
            for ph_name, ph_dur_s in phase_durations_s.items():
                r_s = phase_rate_map.get(ph_name, rate_per_s)
                q_p = r_s * max(0.0, float(ph_dur_s))
                phase_breakdown[ph_name] = round(q_p, 4)
                consumed += q_p
                accounted_s += max(0.0, float(ph_dur_s))
            rem_s = max(0.0, float(exposure_duration_s) - accounted_s)
            if rem_s > 0.0:
                q_rem = rate_per_s * rem_s
                phase_breakdown["unassigned_duration"] = round(q_rem, 4)
                consumed += q_rem
        else:
            consumed = rate_per_s * float(exposure_duration_s)

        eff_res_frac = (
            spec.reserve_policy.reserve_fraction
            if spec.reserve_policy is not None
            else spec.reserve_fraction
        )
        reserve_req = spec.initial_quantity * eff_res_frac
        if (
            spec.reserve_policy is not None
            and spec.reserve_policy.minimum_absolute_reserve is not None
        ):
            reserve_req = max(reserve_req, float(spec.reserve_policy.minimum_absolute_reserve))
        res_policy_status = (
            f"POLICY:{spec.reserve_policy.policy_id}"
            if spec.reserve_policy is not None
            else "EXPLICIT_FRACTION"
        )

        remaining = spec.initial_quantity - consumed
        margin = remaining - reserve_req
        ok = margin >= 0.0
        if not ok:
            any_fail = True

        st_label = "WITHIN_LIMIT" if ok else "EXCEEDS_LIMIT"
        category_coverage[cat_key] = st_label

        entries.append(
            ResourceEvaluationEntry(
                resource_name=spec.resource_name,
                category=cat_key,
                status=st_label,
                initial_quantity=round(spec.initial_quantity, 4),
                unit=spec.unit,
                normalized_rate_per_second=round(rate_per_s, 8),
                exposure_duration_s=round(float(exposure_duration_s), 1),
                reserve_required=round(reserve_req, 4),
                estimated_consumed=round(consumed, 4),
                remaining_after_eva=round(remaining, 4),
                margin_above_reserve=round(margin, 4),
                equation_applied=equation_str,
                integration_mode=integration_mode,
                reserve_policy_status=res_policy_status,
                phase_breakdown=phase_breakdown,
                assumption_classification=spec.classification,
                explanation=(
                    f"{equation_str}: consumed {consumed:.3f} {spec.unit} over {exposure_duration_s:.1f} s; "
                    f"remaining {remaining:.3f} {spec.unit} "
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
        category_coverage=category_coverage,
        missing_inputs=[] if exposure_duration_s is not None else ["walking_speed_mps"],
        limitations=[
            "Evaluates user-configured consumption rates strictly (Q_used = Q_dot * t or piecewise phase integration); "
            "does not fabricate slope-dependent metabolic oxygen spikes or suit thermal loads."
        ],
    )
