"""
MARSCOPE Routing Models & Mode Policies
Defines verified mathematical cost weights for Conservative, Balanced, and Science-Priority routing.
All assumptions are explicitly bounded and never encode unvalidated human metabolic rates.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class RoutingMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    SCIENCE_PRIORITY = "science_priority"


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
    ),
    RoutingMode.SCIENCE_PRIORITY: RoutingModePolicy(
        mode=RoutingMode.SCIENCE_PRIORITY,
        label="Science-Priority Corridor",
        description=(
            "Guides traverse along verified high-value composition evidence and science target "
            "corridors (bounded positive multiplier floor >= 0.45 for admissible optimality) "
            "without violating configured slope or valid-coverage constraints."
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
    ),
}
