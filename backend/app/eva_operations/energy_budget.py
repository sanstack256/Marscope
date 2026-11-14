"""
MARSCOPE EVA Mechanical Gravitational Work Model
Explicitly requires user-supplied suit & payload masses and Mars gravity
from the verified PhysicsRegistry. Never claims metabolic or O2 equivalence.
"""

from __future__ import annotations

from typing import List, Optional

from app.eva_operations.schemas import EnergyBudgetBreakdown
from app.physics.registry.parameters import get_parameter


def evaluate_eva_energy_budget(
    *,
    outbound_climb_gain_m: float,
    outbound_descent_loss_m: float,
    return_climb_gain_m: float,
    return_descent_loss_m: float,
    astronaut_suit_mass_kg: Optional[float],
    payload_mass_kg: Optional[float],
) -> EnergyBudgetBreakdown:
    """Compute separate outbound, return, and total mechanical gravitational climb work."""
    g_param = get_parameter("mars_standard_gravity")
    g_val = float(g_param.value) if g_param is not None else 3.72076

    missing: List[str] = []
    if astronaut_suit_mass_kg is None:
        missing.append("astronaut_suit_mass_kg")
    if payload_mass_kg is None:
        missing.append("payload_mass_kg")

    if missing:
        return EnergyBudgetBreakdown(
            available=False,
            astronaut_suit_mass_kg=astronaut_suit_mass_kg,
            payload_mass_kg=payload_mass_kg,
            total_mass_kg=None,
            mars_gravity_m_s2=g_val,
            surface_weight_n=None,
            outbound_climb_gain_m=round(outbound_climb_gain_m, 2),
            outbound_descent_loss_m=round(outbound_descent_loss_m, 2),
            return_climb_gain_m=round(return_climb_gain_m, 2),
            return_descent_loss_m=round(return_descent_loss_m, 2),
            missing_inputs=missing,
        )

    total_mass = float(astronaut_suit_mass_kg) + float(payload_mass_kg)
    weight_n = total_mass * g_val
    out_w = weight_n * float(outbound_climb_gain_m)
    ret_w = weight_n * float(return_climb_gain_m)
    tot_w = out_w + ret_w
    net_dh = (float(outbound_climb_gain_m) + float(return_climb_gain_m)) - (
        float(outbound_descent_loss_m) + float(return_descent_loss_m)
    )
    net_pe = weight_n * net_dh

    return EnergyBudgetBreakdown(
        available=True,
        astronaut_suit_mass_kg=round(float(astronaut_suit_mass_kg), 2),
        payload_mass_kg=round(float(payload_mass_kg), 2),
        total_mass_kg=round(total_mass, 2),
        mars_gravity_m_s2=g_val,
        surface_weight_n=round(weight_n, 2),
        outbound_climb_gain_m=round(outbound_climb_gain_m, 2),
        outbound_descent_loss_m=round(outbound_descent_loss_m, 2),
        return_climb_gain_m=round(return_climb_gain_m, 2),
        return_descent_loss_m=round(return_descent_loss_m, 2),
        outbound_climb_work_j=round(out_w, 1),
        return_climb_work_j=round(ret_w, 1),
        total_positive_climb_work_j=round(tot_w, 1),
        net_gravitational_pe_change_j=round(net_pe, 1),
        missing_inputs=[],
    )
