"""
MARSCOPE EVA Mechanical Gravitational Work Model (Prompt 20 Part 2.2)
Explicitly requires user-supplied suit & payload masses and Mars gravity
from the verified PhysicsRegistry without any silent fallback constant.
Never claims metabolic or O2 equivalence.
"""

from __future__ import annotations

from typing import List, Optional

from app.eva_operations.schemas import EnergyBudgetBreakdown
from app.physics.registry.parameters import get_parameter
from app.science.provenance_graph import (
    ParameterProvenanceRecord,
    ScientificDataClassification,
)


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
    g_val: Optional[float] = None
    if g_param is not None and g_param.value is not None:
        g_val = float(g_param.value)

    missing: List[str] = []
    if g_val is None:
        missing.append("mars_standard_gravity")
    if astronaut_suit_mass_kg is None:
        missing.append("astronaut_suit_mass_kg")
    if payload_mass_kg is None:
        missing.append("payload_mass_kg")

    param_prov: List[ParameterProvenanceRecord] = [
        ParameterProvenanceRecord(
            parameter_name="mars_standard_gravity",
            value=g_val,
            units="m/s^2",
            classification=(
                ScientificDataClassification.ARCHIVE_DERIVED
                if g_val is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type=(
                "verified_physics_registry"
                if g_val is not None
                else "missing_verified_parameter"
            ),
            citation=g_param.source if g_param is not None else None,
            validity_domain="Planetary surface mean equatorial/standard gravity for Mars",
            confirmed_by_operator=True,
        ),
        ParameterProvenanceRecord(
            parameter_name="astronaut_suit_mass_kg",
            value=astronaut_suit_mass_kg,
            units="kg",
            classification=(
                ScientificDataClassification.USER_ASSUMED
                if astronaut_suit_mass_kg is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type="user_input" if astronaut_suit_mass_kg is not None else "missing_input",
            validity_domain="Suited crew member mass (> 0 kg)",
            confirmed_by_operator=astronaut_suit_mass_kg is not None,
        ),
        ParameterProvenanceRecord(
            parameter_name="payload_mass_kg",
            value=payload_mass_kg,
            units="kg",
            classification=(
                ScientificDataClassification.USER_ASSUMED
                if payload_mass_kg is not None
                else ScientificDataClassification.UNAVAILABLE
            ),
            source_type="user_input" if payload_mass_kg is not None else "missing_input",
            validity_domain="Carried scientific/EVA equipment mass (>= 0 kg)",
            confirmed_by_operator=payload_mass_kg is not None,
        ),
    ]

    if missing or g_val is None or astronaut_suit_mass_kg is None or payload_mass_kg is None:
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
            parameter_provenance=param_prov,
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
        parameter_provenance=param_prov,
        missing_inputs=[],
    )
