"""
MARSCOPE Routing Domain Models & Mode Policies (Prompt 13, 16, 20 Part 4).

Defines deterministic, inspectable multi-term cost policies for Conservative,
Balanced, and Science-Priority Mars surface routing, plus 9 explicit RouteObjectives,
configurable objective weight overrides, and UnknownTerrainPolicy.
"""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, Optional


ROUTE_OBJECTIVES_VERSION = "p20_route_objectives_v2.0"


class RoutingMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    SCIENCE_PRIORITY = "science_priority"


class RouteObjective(str, Enum):
    """Explicit route optimization objectives (Prompt 16 & Prompt 20 Part 4.2)."""

    SHORTEST_TRAVERSABLE = "SHORTEST_TRAVERSABLE"
    LOWEST_SLOPE = "LOWEST_SLOPE"
    LOWEST_CLIMB_ENERGY = "LOWEST_CLIMB_ENERGY"
    LOWEST_ROUGHNESS = "LOWEST_ROUGHNESS"
    HIGHEST_EVIDENCE_COVERAGE = "HIGHEST_EVIDENCE_COVERAGE"
    SCIENCE_CORRIDOR = "SCIENCE_CORRIDOR"
    BALANCED_MULTIOBJECTIVE = "BALANCED_MULTIOBJECTIVE"
    LOWEST_UNCERTAINTY_EXPOSURE = "LOWEST_UNCERTAINTY_EXPOSURE"
    RETURN_RESERVE_FRIENDLY = "RETURN_RESERVE_FRIENDLY"

    @classmethod
    def _missing_(cls, value: Any) -> Optional["RouteObjective"]:
        if isinstance(value, str):
            norm = value.strip().upper()
            for member in cls:
                if member.value == norm or member.name == norm:
                    return member
        return None


class UnknownTerrainPolicy(str, Enum):
    """Explicit policy for handling unknown / insufficiently observed terrain cells (Prompt 20 Part 4.3)."""

    EXCLUDE_UNKNOWN = "EXCLUDE_UNKNOWN"
    ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE = "ALLOW_WITH_EXPLICIT_OPERATOR_OVERRIDE"
    REQUIRE_ADDITIONAL_OBSERVATION = "REQUIRE_ADDITIONAL_OBSERVATION"
    ROUTE_THROUGH_WITH_LIMITATION = "ROUTE_THROUGH_WITH_LIMITATION"


class PathAlgorithm(str, Enum):
    ASTAR = "astar"
    DIJKSTRA = "dijkstra"


@dataclass(frozen=True)
class RoutingModePolicy:
    """
    Deterministic multi-term traversal cost weights for a routing mode / objective.
    Edge cost C(e) = d_horiz * max(min_cost_multiplier,
        1.0
        + slope_weight * (slope_deg / effective_max_slope_deg)^2
        + uphill_weight * max(0, dz / d_horiz)
        + downhill_weight * max(0, -dz / d_horiz)
        + roughness_weight * (tri_m / ref_cell_m)
        + uncertainty_weight * uncertainty_score
        + nodata_proximity_weight * nodata_adj_penalty
        - science_corridor_bonus * science_corridor_score
    )
    Guaranteed positive (>= min_cost_multiplier * d_horiz) so A* heuristic remains strictly admissible.
    """

    mode: RoutingMode
    label: str
    description: str
    effective_slope_limit_factor: float  # Multiplier applied to user's max_slope_deg (<= 1.0)
    slope_weight: float
    uphill_weight: float
    downhill_weight: float
    roughness_weight: float
    uncertainty_weight: float
    nodata_proximity_weight: float
    science_corridor_bonus: float
    min_cost_multiplier: float = 0.72
    objective: Optional[RouteObjective] = None
    policy_version: str = ROUTE_OBJECTIVES_VERSION


MODE_POLICIES: Dict[RoutingMode, RoutingModePolicy] = {
    RoutingMode.CONSERVATIVE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        label="Conservative (Low-Risk Corridor)",
        description=(
            "Enforces a tighter 0.80x effective slope cap, heavily penalizes steep gradients, "
            "roughness, and no-data boundary proximity."
        ),
        effective_slope_limit_factor=0.80,
        slope_weight=3.8,
        uphill_weight=4.5,
        downhill_weight=2.4,
        roughness_weight=2.6,
        uncertainty_weight=1.5,
        nodata_proximity_weight=2.5,
        science_corridor_bonus=0.10,
        min_cost_multiplier=0.85,
        objective=RouteObjective.LOWEST_SLOPE,
    ),
    RoutingMode.BALANCED: RoutingModePolicy(
        mode=RoutingMode.BALANCED,
        label="Balanced (Standard EVA)",
        description=(
            "Balances horizontal path length against slope, climb work, TRI roughness, "
            "and moderate attraction toward verified science targets."
        ),
        effective_slope_limit_factor=1.00,
        slope_weight=1.8,
        uphill_weight=2.5,
        downhill_weight=1.1,
        roughness_weight=1.3,
        uncertainty_weight=0.8,
        nodata_proximity_weight=1.2,
        science_corridor_bonus=0.22,
        min_cost_multiplier=0.76,
        objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
    ),
    RoutingMode.SCIENCE_PRIORITY: RoutingModePolicy(
        mode=RoutingMode.SCIENCE_PRIORITY,
        label="Science Priority (Evidence Corridor)",
        description=(
            "Favors corridors passing near high-priority geological targets and verified "
            "mineral/chemistry observations while strictly obeying hard slope and no-data limits."
        ),
        effective_slope_limit_factor=1.00,
        slope_weight=1.1,
        uphill_weight=1.5,
        downhill_weight=0.7,
        roughness_weight=0.8,
        uncertainty_weight=0.5,
        nodata_proximity_weight=0.9,
        science_corridor_bonus=0.38,
        min_cost_multiplier=0.60,
        objective=RouteObjective.SCIENCE_CORRIDOR,
    ),
}


OBJECTIVE_POLICIES: Dict[RouteObjective, RoutingModePolicy] = {
    RouteObjective.SHORTEST_TRAVERSABLE: RoutingModePolicy(
        mode=RoutingMode.BALANCED,
        objective=RouteObjective.SHORTEST_TRAVERSABLE,
        label="Shortest Traversable Distance",
        description="Minimizes horizontal/surface path distance while strictly obeying hard slope, roughness, and no-data exclusions.",
        effective_slope_limit_factor=1.00,
        slope_weight=0.25,
        uphill_weight=0.30,
        downhill_weight=0.15,
        roughness_weight=0.20,
        uncertainty_weight=0.15,
        nodata_proximity_weight=0.40,
        science_corridor_bonus=0.0,
        min_cost_multiplier=0.95,
    ),
    RouteObjective.LOWEST_SLOPE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_SLOPE,
        label="Lowest Slope Exposure",
        description="Enforces 0.80x tighter slope ceiling and strongly penalizes local and chord slope gradients.",
        effective_slope_limit_factor=0.80,
        slope_weight=5.2,
        uphill_weight=3.2,
        downhill_weight=2.8,
        roughness_weight=1.6,
        uncertainty_weight=1.2,
        nodata_proximity_weight=2.2,
        science_corridor_bonus=0.05,
        min_cost_multiplier=0.90,
    ),
    RouteObjective.LOWEST_CLIMB_ENERGY: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_CLIMB_ENERGY,
        label="Lowest Cumulative Climb Work",
        description="Heavily penalizes positive elevation gain (Delta E_p = m*g*Delta h_pos) to minimize uphill climb work.",
        effective_slope_limit_factor=0.92,
        slope_weight=2.0,
        uphill_weight=8.5,
        downhill_weight=1.0,
        roughness_weight=1.2,
        uncertainty_weight=0.8,
        nodata_proximity_weight=1.2,
        science_corridor_bonus=0.05,
        min_cost_multiplier=0.90,
    ),
    RouteObjective.LOWEST_ROUGHNESS: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_ROUGHNESS,
        label="Lowest Surface Roughness (TRI)",
        description="Strongly penalizes 3x3 Terrain Ruggedness Index (TRI) variations to favor smoother local corridors.",
        effective_slope_limit_factor=0.90,
        slope_weight=2.1,
        uphill_weight=2.2,
        downhill_weight=1.2,
        roughness_weight=6.5,
        uncertainty_weight=1.4,
        nodata_proximity_weight=1.8,
        science_corridor_bonus=0.05,
        min_cost_multiplier=0.88,
    ),
    RouteObjective.HIGHEST_EVIDENCE_COVERAGE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.HIGHEST_EVIDENCE_COVERAGE,
        label="Highest Evidence & Lowest Uncertainty",
        description="Maximizes distance from missing-data boundaries and minimizes epistemic/derivative uncertainty exposure.",
        effective_slope_limit_factor=0.88,
        slope_weight=2.4,
        uphill_weight=2.4,
        downhill_weight=1.4,
        roughness_weight=2.0,
        uncertainty_weight=4.8,
        nodata_proximity_weight=5.5,
        science_corridor_bonus=0.28,
        min_cost_multiplier=0.72,
    ),
    RouteObjective.SCIENCE_CORRIDOR: MODE_POLICIES[RoutingMode.SCIENCE_PRIORITY],
    RouteObjective.BALANCED_MULTIOBJECTIVE: MODE_POLICIES[RoutingMode.BALANCED],
    RouteObjective.LOWEST_UNCERTAINTY_EXPOSURE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_UNCERTAINTY_EXPOSURE,
        label="Lowest Epistemic Uncertainty Exposure",
        description="Minimizes traversal across cells with high derivative uncertainty or NoData proximity.",
        effective_slope_limit_factor=0.86,
        slope_weight=2.2,
        uphill_weight=2.2,
        downhill_weight=1.4,
        roughness_weight=2.0,
        uncertainty_weight=6.2,
        nodata_proximity_weight=6.0,
        science_corridor_bonus=0.10,
        min_cost_multiplier=0.82,
    ),
    RouteObjective.RETURN_RESERVE_FRIENDLY: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.RETURN_RESERVE_FRIENDLY,
        label="Return-Reserve Friendly Corridor",
        description="Penalizes both uphill and steep downhill grades so both outbound and return traverses preserve time/reserve margins.",
        effective_slope_limit_factor=0.85,
        slope_weight=3.4,
        uphill_weight=5.0,
        downhill_weight=4.5,
        roughness_weight=2.2,
        uncertainty_weight=1.8,
        nodata_proximity_weight=2.4,
        science_corridor_bonus=0.08,
        min_cost_multiplier=0.86,
    ),
}


def resolve_routing_policy(
    mode: RoutingMode,
    objective: Optional[RouteObjective] = None,
    custom_weights: Optional[Dict[str, float]] = None,
) -> RoutingModePolicy:
    """Resolve explicit RouteObjective policy if supplied, otherwise legacy RoutingMode policy, with optional user weight overrides."""
    base = OBJECTIVE_POLICIES[objective] if (objective is not None and objective in OBJECTIVE_POLICIES) else MODE_POLICIES[mode]
    if not custom_weights:
        return base
    updates: Dict[str, Any] = {}
    for k in (
        "effective_slope_limit_factor",
        "slope_weight",
        "uphill_weight",
        "downhill_weight",
        "roughness_weight",
        "uncertainty_weight",
        "nodata_proximity_weight",
        "science_corridor_bonus",
        "min_cost_multiplier",
    ):
        if k in custom_weights and custom_weights[k] is not None:
            updates[k] = float(custom_weights[k])
    if updates:
        updates["policy_version"] = f"{ROUTE_OBJECTIVES_VERSION}+user_custom_weights"
        return replace(base, **updates)
    return base
