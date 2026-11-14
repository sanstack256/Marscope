"""
MARSCOPE Routing Models & Multi-Objective Policies
Defines verified mathematical cost weights for legacy 3-mode routing AND all seven
Prompt 16 explicit RouteObjectives.
All assumptions are explicitly bounded and never encode unvalidated human metabolic rates
or bypass hard slope/nodata/insufficiency constraints.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

ROUTE_OBJECTIVES_VERSION = "routing_objectives_v1.0"


class RoutingMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    SCIENCE_PRIORITY = "science_priority"


class RouteObjective(str, Enum):
    """Seven explicit planetary route-optimization objectives with documented trade-offs."""

    SHORTEST_TRAVERSABLE = "SHORTEST_TRAVERSABLE"
    LOWEST_SLOPE = "LOWEST_SLOPE"
    LOWEST_CLIMB_ENERGY = "LOWEST_CLIMB_ENERGY"
    LOWEST_ROUGHNESS = "LOWEST_ROUGHNESS"
    HIGHEST_EVIDENCE_COVERAGE = "HIGHEST_EVIDENCE_COVERAGE"
    SCIENCE_CORRIDOR = "SCIENCE_CORRIDOR"
    BALANCED_MULTIOBJECTIVE = "BALANCED_MULTIOBJECTIVE"


class PathAlgorithm(str, Enum):
    ASTAR = "astar"
    DIJKSTRA = "dijkstra"


@dataclass(frozen=True)
class RoutingModePolicy:
    mode: RoutingMode
    label: str
    description: str
    effective_slope_limit_factor: float
    slope_weight: float
    uphill_weight: float
    downhill_weight: float
    roughness_weight: float
    uncertainty_weight: float
    nodata_proximity_weight: float
    science_corridor_bonus: float
    min_cost_multiplier: float
    objective: Optional[RouteObjective] = None


MODE_POLICIES: Dict[RoutingMode, RoutingModePolicy] = {
    RoutingMode.CONSERVATIVE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        label="Conservative Terrain-Avoidance",
        description=(
            "Strongly penalizes steep grades, rough terrain (TRI), coarse/unverified DEM cells, "
            "and proximity to no-data boundaries while keeping effective slope limit conservative."
        ),
        effective_slope_limit_factor=0.80,
        slope_weight=4.5,
        uphill_weight=3.2,
        downhill_weight=2.0,
        roughness_weight=1.25,
        uncertainty_weight=0.45,
        nodata_proximity_weight=1.50,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
        objective=RouteObjective.LOWEST_SLOPE,
    ),
    RoutingMode.BALANCED: RoutingModePolicy(
        mode=RoutingMode.BALANCED,
        label="Balanced Traverse",
        description=(
            "Balances horizontal path length against uphill/downhill grade effort and surface "
            "roughness while strictly respecting configured slope limits and valid terrain coverage."
        ),
        effective_slope_limit_factor=1.0,
        slope_weight=1.8,
        uphill_weight=1.6,
        downhill_weight=0.7,
        roughness_weight=0.55,
        uncertainty_weight=0.20,
        nodata_proximity_weight=0.40,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
        objective=RouteObjective.BALANCED_MULTIOBJECTIVE,
    ),
    RoutingMode.SCIENCE_PRIORITY: RoutingModePolicy(
        mode=RoutingMode.SCIENCE_PRIORITY,
        label="Science-Priority Corridor",
        description=(
            "Guides traverse along verified high-value composition evidence and science target "
            "corridors (bounded positive multiplier floor >= 0.45; excluding unverified optical "
            "candidates) without violating configured slope or valid-coverage constraints."
        ),
        effective_slope_limit_factor=1.0,
        slope_weight=1.2,
        uphill_weight=1.1,
        downhill_weight=0.5,
        roughness_weight=0.35,
        uncertainty_weight=0.10,
        nodata_proximity_weight=0.20,
        science_corridor_bonus=0.50,
        min_cost_multiplier=0.45,
        objective=RouteObjective.SCIENCE_CORRIDOR,
    ),
}


OBJECTIVE_POLICIES: Dict[RouteObjective, RoutingModePolicy] = {
    RouteObjective.SHORTEST_TRAVERSABLE: RoutingModePolicy(
        mode=RoutingMode.BALANCED,
        objective=RouteObjective.SHORTEST_TRAVERSABLE,
        label="Shortest Traversable Distance",
        description="Minimizes 3D surface path length across strictly valid traversable terrain with minimal slope tie-breakers.",
        effective_slope_limit_factor=1.0,
        slope_weight=0.10,
        uphill_weight=0.25,
        downhill_weight=0.10,
        roughness_weight=0.05,
        uncertainty_weight=0.05,
        nodata_proximity_weight=0.15,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
    ),
    RouteObjective.LOWEST_SLOPE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_SLOPE,
        label="Lowest-Slope Terrain Avoidance",
        description="Minimizes cumulative steep slopes with a conservative 0.80x effective slope limit factor.",
        effective_slope_limit_factor=0.80,
        slope_weight=5.0,
        uphill_weight=2.8,
        downhill_weight=1.8,
        roughness_weight=0.85,
        uncertainty_weight=0.35,
        nodata_proximity_weight=1.20,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
    ),
    RouteObjective.LOWEST_CLIMB_ENERGY: RoutingModePolicy(
        mode=RoutingMode.BALANCED,
        objective=RouteObjective.LOWEST_CLIMB_ENERGY,
        label="Minimum Gravitational Climb Work",
        description="Strongly penalizes upward delta-Z elevation gains proportional to dPE = m * g * dh+.",
        effective_slope_limit_factor=1.0,
        slope_weight=1.2,
        uphill_weight=5.8,
        downhill_weight=0.35,
        roughness_weight=0.35,
        uncertainty_weight=0.15,
        nodata_proximity_weight=0.35,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
    ),
    RouteObjective.LOWEST_ROUGHNESS: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.LOWEST_ROUGHNESS,
        label="Lowest Surface Roughness (TRI)",
        description="Avoids rugged boulder/fracture relief windows captured by 5 m Riley RMS TRI.",
        effective_slope_limit_factor=0.90,
        slope_weight=1.6,
        uphill_weight=1.2,
        downhill_weight=0.6,
        roughness_weight=3.20,
        uncertainty_weight=0.30,
        nodata_proximity_weight=0.80,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
    ),
    RouteObjective.HIGHEST_EVIDENCE_COVERAGE: RoutingModePolicy(
        mode=RoutingMode.CONSERVATIVE,
        objective=RouteObjective.HIGHEST_EVIDENCE_COVERAGE,
        label="Highest Verified Evidence Coverage",
        description="Prefers cells inside full HiRISE DTM + orthophoto coverage away from nodata/uncertainty edges.",
        effective_slope_limit_factor=0.95,
        slope_weight=1.5,
        uphill_weight=1.2,
        downhill_weight=0.6,
        roughness_weight=0.45,
        uncertainty_weight=2.80,
        nodata_proximity_weight=2.60,
        science_corridor_bonus=0.0,
        min_cost_multiplier=1.0,
    ),
    RouteObjective.SCIENCE_CORRIDOR: MODE_POLICIES[RoutingMode.SCIENCE_PRIORITY],
    RouteObjective.BALANCED_MULTIOBJECTIVE: MODE_POLICIES[RoutingMode.BALANCED],
}


def resolve_routing_policy(
    mode: RoutingMode = RoutingMode.BALANCED,
    objective: Optional[RouteObjective] = None,
) -> RoutingModePolicy:
    """Resolve explicit RouteObjective policy if supplied, otherwise legacy RoutingMode policy."""
    if objective is not None and objective in OBJECTIVE_POLICIES:
        return OBJECTIVE_POLICIES[objective]
    return MODE_POLICIES[mode]
