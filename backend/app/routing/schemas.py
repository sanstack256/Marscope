"""
MARSCOPE Science-Aware Routing API & Domain Schemas
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.science.provenance_graph import ProvenanceDependencyGraph

from app.routing.models import PathAlgorithm, RouteObjective, RoutingMode
from app.terrain_uncertainty.sensitivity import RouteSensitivityReport


class RouteCoordinateInput(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Mars planetocentric latitude [-90, 90]")
    lon_east: float = Field(..., ge=-180.0, le=360.0, description="East longitude")
    label: Optional[str] = Field(None, description="Optional user/site label")
    target_id: Optional[str] = Field(None, description="Optional registered ScienceTarget id")


class RoutePlanningConstraints(BaseModel):
    max_slope_deg: float = Field(15.0, ge=1.0, le=45.0, description="Planning maximum traversable slope (deg)")
    max_roughness_tri_m: Optional[float] = Field(
        None, gt=0.0, description="Optional max Terrain Ruggedness Index (m)"
    )
    snap_radius_m: float = Field(
        50.0, ge=0.0, le=500.0, description="Max snap radius (m) if input point lands on nodata/blocked pixel"
    )
    walking_speed_m_per_s: Optional[float] = Field(
        None, gt=0.05, le=5.0,
        description="Explicit user-configured walking speed assumption (m/s). Withheld unless provided."
    )
    walking_speed_provenance: Optional[str] = Field(
        None,
        description="Provenance note (e.g. 'User-Configured Planning Assumption (Unvalidated)')",
    )
    astronaut_total_mass_kg: Optional[float] = Field(
        None, gt=10.0, le=500.0,
        description="Optional astronaut + suit mass (kg) for exact Mars gravitational climb work (J)."
    )
    max_eva_duration_hours: Optional[float] = Field(
        None, gt=0.05, le=24.0,
        description="Optional max EVA time budget (hours) for outbound + return verification."
    )
    safety_reserve_fraction: float = Field(
        0.0, ge=0.0, le=0.75,
        description="Fraction of EVA budget held in reserve (must remain unspent)."
    )
    enforce_budget: bool = Field(
        False,
        description="If true, route fails cleanly when estimated time exceeds usable budget.",
    )
    return_to_start: bool = Field(
        False,
        description="Whether to plan closed round-trip return leg from destination back to start (explicitly opt-in).",
    )
    optimize_target_order: bool = Field(
        True,
        description="Reorder selected intermediate science targets to minimize total traverse cost.",
    )
    simplification_epsilon_m: float = Field(
        6.0, ge=0.0, le=100.0,
        description="Controlled line-of-sight simplification tolerance (m), verified against all DEM cells."
    )
    max_grid_dim: int = Field(
        220, ge=40, le=450,
        description="Upper grid axis cap so DEM solver stays fast and bounded in RAM."
    )


class RouteComputeRequest(BaseModel):
    dataset_id: Optional[str] = Field(
        None, description="Preferred DEM dataset_id (defaults to best local high-res DEM covering points)"
    )
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    target_ids: List[str] = Field(default_factory=list, description="Registered science targets to visit")
    waypoints: List[RouteCoordinateInput] = Field(
        default_factory=list, description="Explicit extra coordinate stops (or custom science stops)"
    )
    mode: RoutingMode = Field(RoutingMode.BALANCED)
    objective: Optional[RouteObjective] = Field(
        None,
        description="Explicit Prompt 16 route objective (overrides legacy mode weights when supplied)",
    )
    exclude_optical_candidates_from_science_bonus: bool = Field(
        True,
        description="Strict science hierarchy: unverified optical contrast anomalies never receive routing bonus",
    )
    algorithm: PathAlgorithm = Field(PathAlgorithm.ASTAR)
    constraints: RoutePlanningConstraints = Field(default_factory=RoutePlanningConstraints)


class RouteCompareRequest(BaseModel):
    dataset_id: Optional[str] = None
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    target_ids: List[str] = Field(default_factory=list)
    waypoints: List[RouteCoordinateInput] = Field(default_factory=list)
    modes: List[RoutingMode] = Field(
        default_factory=lambda: [RoutingMode.CONSERVATIVE, RoutingMode.BALANCED, RoutingMode.SCIENCE_PRIORITY]
    )
    algorithm: PathAlgorithm = Field(PathAlgorithm.ASTAR)
    constraints: RoutePlanningConstraints = Field(default_factory=RoutePlanningConstraints)


class SnapDiagnostic(BaseModel):
    point_role: str
    requested_lat: float
    requested_lon_east: float
    snapped: bool = False
    snapped_lat: float
    snapped_lon_east: float
    snap_distance_m: float
    source_cell_state: str
    elevation_m: Optional[float] = None


class SimplificationDiagnostic(BaseModel):
    raw_grid_nodes: int
    simplified_vertices: int
    segments_checked: int
    shortcuts_accepted: int
    shortcuts_rejected_obstacle_or_nodata: int
    all_simplified_segments_verified_valid: bool


class BudgetDiagnostic(BaseModel):
    evaluated: bool = False
    return_to_start_included: bool = False
    max_eva_duration_seconds: Optional[float] = None
    safety_reserve_fraction: float
    usable_budget_seconds: Optional[float] = None
    estimated_total_duration_seconds: Optional[float] = None
    margin_seconds: Optional[float] = None
    within_budget: Optional[bool] = None
    reason: Optional[str] = None


class RouteVertex(BaseModel):
    seq: int
    lat: float
    lon_east: float
    elevation_m: float
    slope_deg: Optional[float] = None
    roughness_tri_m: Optional[float] = None
    cumulative_distance_m: float
    segment_distance_m: float
    is_stop: bool = False
    stop_role: Optional[str] = None
    stop_label: Optional[str] = None
    target_id: Optional[str] = None
    science_corridor_score: float = 0.0


class RouteLegSummary(BaseModel):
    leg_index: int
    from_label: str
    to_label: str
    is_return_leg: bool = False
    horizontal_distance_m: float
    surface_distance_m: float
    elevation_gain_m: float
    elevation_loss_m: float
    mean_slope_deg: float
    max_slope_deg: float
    mean_roughness_tri_m: Optional[float] = None
    estimated_duration_seconds: Optional[float] = None
    total_cost: float
    vertex_start_seq: int
    vertex_end_seq: int


class NavigationInstruction(BaseModel):
    step_index: int
    action: str
    bearing_true_north_deg: Optional[float] = None
    bearing_grid_north_deg: Optional[float] = None
    cardinal_direction: Optional[str] = None
    turn_angle_deg: Optional[float] = None
    from_lat: float
    from_lon_east: float
    to_lat: float
    to_lon_east: float
    segment_distance_m: float
    cumulative_distance_m: float
    elevation_start_m: float
    elevation_end_m: float
    elevation_delta_m: float
    grade_percent: float
    segment_slope_deg: float
    local_roughness_tri_m: Optional[float] = None
    terrain_context: str
    nearby_science_targets: List[str] = Field(default_factory=list)
    caution_notes: List[str] = Field(default_factory=list)
    instruction_text: str


class ScienceStopSummary(BaseModel):
    target_id: Optional[str] = None
    name: str
    lat: float
    lon_east: float
    geology_type: Optional[str] = None
    exploration_priority_score: Optional[float] = None
    route_utility_role: Optional[str] = None
    scientific_relevance_note: Optional[str] = None
    scientific_value: Optional[float] = Field(
        default=None,
        deprecated=True,
        description="Deprecated legacy field; never populated from exploration_priority_score.",
    )
    matched_species: Optional[str] = None
    instrument_source: Optional[str] = None
    visit_order_index: int
    distance_from_route_m: float


class EdgeEvaluationDetail(BaseModel):
    from_rc: List[int]
    to_rc: List[int]
    from_lat: float
    from_lon_east: float
    to_lat: float
    to_lon_east: float
    horizontal_distance_m: float
    elevation_change_m: float
    effective_slope_deg: float
    allowed_by_hard_constraints: bool
    rejection_reasons: List[str] = Field(default_factory=list)
    base_distance_cost: float
    slope_penalty_cost: float
    uphill_penalty_cost: float
    downhill_penalty_cost: float
    roughness_penalty_cost: float
    uncertainty_penalty_cost: float
    nodata_proximity_penalty_cost: float
    science_corridor_bonus_credit: float
    clamped_multiplier: float
    total_edge_cost: Optional[float] = None


class RouteDecisionExplainer(BaseModel):
    mode: RoutingMode
    algorithm: PathAlgorithm
    hard_constraints: Dict[str, Any] = Field(default_factory=dict)
    soft_cost_weights: Dict[str, float] = Field(default_factory=dict)
    grid_exclusion_summary: Dict[str, int] = Field(default_factory=dict)
    total_cost_breakdown: Dict[str, float] = Field(default_factory=dict)
    dominant_cost_driver: str
    sampled_traversed_edges: List[EdgeEvaluationDetail] = Field(default_factory=list)
    rejected_neighbor_edges: List[EdgeEvaluationDetail] = Field(default_factory=list)
    verified_science_targets_applied: List[Dict[str, Any]] = Field(default_factory=list)
    unverified_optical_candidates_excluded_from_bonus: int = 0
    sensitivity_notes: List[str] = Field(default_factory=list)
    decision_trace_summary: str


class RouteCostDecomposition(BaseModel):
    """Explicit itemized traversal objective components summed across route edges."""

    base_distance_cost: float
    slope_penalty_cost: float
    uphill_climb_cost: float
    downhill_descent_cost: float
    roughness_penalty_cost: float
    uncertainty_penalty_cost: float
    nodata_proximity_cost: float
    science_corridor_reduction: float
    total_objective_cost: float
    dominant_cost_driver: str
    science_bonus_sources_used: List[str] = Field(default_factory=list)
    unverified_optical_candidates_excluded: bool = True


class RouteTraversabilitySummary(BaseModel):
    """3-state traversability & uncertainty separation across solver grid."""

    evaluated_cell_count: int
    known_exclusion_cell_count: int
    unknown_insufficient_cell_count: int
    evaluated_fraction: float
    known_exclusion_fraction: float
    unknown_insufficient_fraction: float
    unverified_optical_candidates_excluded_from_bonus: bool = True


class RouteComputeResponse(BaseModel):
    route_id: str
    route_signature: str
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dataset_id: str
    source_product_id: str
    crs: str = "IAU2000:49900"
    bearing_convention: str
    mode: RoutingMode
    objective: Optional[RouteObjective] = None
    mode_label: str
    algorithm: PathAlgorithm
    effective_slope_limit_deg: float
    native_dem_resolution_m: float
    solver_grid_spacing_m: float
    solver_grid_shape: Dict[str, int]
    assumption_classification: str
    return_to_start: bool
    within_budget: Optional[bool] = None
    budget_diagnostic: BudgetDiagnostic
    total_horizontal_distance_m: float
    total_surface_distance_m: float
    total_elevation_gain_m: float
    total_elevation_loss_m: float
    net_elevation_change_m: float
    min_elevation_m: float
    max_elevation_m: float
    mean_slope_deg: float
    max_slope_deg: float
    mean_roughness_tri_m: Optional[float] = None
    estimated_duration_seconds: Optional[float] = None
    gravitational_climb_work_joules: Optional[float] = None
    total_cost: float
    compute_time_ms: float
    nodes_expanded: int
    target_visit_order: List[str] = Field(default_factory=list)
    snap_diagnostics: List[SnapDiagnostic] = Field(default_factory=list)
    simplification_diagnostic: SimplificationDiagnostic
    science_targets_reached: List[ScienceStopSummary] = Field(default_factory=list)
    corridor_evidence_hits_within_150m: int = 0
    legs: List[RouteLegSummary] = Field(default_factory=list)
    vertices: List[RouteVertex] = Field(default_factory=list)
    instructions: List[NavigationInstruction] = Field(default_factory=list)
    resolution_suitability: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    provenance_graph: Optional[ProvenanceDependencyGraph] = None
    decision_explainer: Optional[RouteDecisionExplainer] = None
    cost_decomposition: Optional[RouteCostDecomposition] = None
    traversability_summary: Optional[RouteTraversabilitySummary] = None
    uncertainty_status: Optional[str] = None


class RouteCompareEntry(BaseModel):
    mode: RoutingMode
    mode_label: str
    feasible: bool
    error_reason: Optional[str] = None
    route: Optional[RouteComputeResponse] = None


class RouteCompareResponse(BaseModel):
    dataset_id: str
    source_product_id: str
    comparison: List[RouteCompareEntry]
    comparison_notes: List[str] = Field(default_factory=list)


class RouteValidationResponse(BaseModel):
    valid: bool
    dataset_id: str
    source_product_id: str
    native_dem_resolution_m: float
    solver_grid_spacing_m: float
    effective_slope_limit_deg: float
    traversable_cell_fraction: float
    blocked_slope_cell_fraction: float
    nodata_cell_fraction: float
    snap_diagnostics: List[SnapDiagnostic] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class RouteStatusResponse(BaseModel):
    engine_name: str = "MARSCOPE Science-Aware Route Computation & Navigation Engine"
    engine_version: str = "1.0.0"
    supported_modes: List[str]
    supported_algorithms: List[str]
    available_dem_datasets: List[str]
    stored_route_count: int
    safety_certification_enabled: bool = False
    scientific_constraints: List[str]


class RobustRouteCompareRequest(BaseModel):
    """Request multi-objective distinct alternative route generation, return check, and stability testing."""

    dataset_id: Optional[str] = None
    start: RouteCoordinateInput
    destination: RouteCoordinateInput
    target_ids: List[str] = Field(default_factory=list)
    waypoints: List[RouteCoordinateInput] = Field(default_factory=list)
    objectives: List[RouteObjective] = Field(
        default_factory=lambda: [
            RouteObjective.BALANCED_MULTIOBJECTIVE,
            RouteObjective.SHORTEST_TRAVERSABLE,
            RouteObjective.LOWEST_SLOPE,
            RouteObjective.LOWEST_CLIMB_ENERGY,
            RouteObjective.LOWEST_ROUGHNESS,
            RouteObjective.HIGHEST_EVIDENCE_COVERAGE,
            RouteObjective.SCIENCE_CORRIDOR,
        ]
    )
    algorithm: PathAlgorithm = Field(PathAlgorithm.ASTAR)
    constraints: RoutePlanningConstraints = Field(default_factory=RoutePlanningConstraints)
    walking_speed_mps: Optional[float] = Field(default=None, gt=0.0, le=5.0)
    use_tobler_grade_approximation: bool = False
    mission_duration_limit_s: Optional[float] = Field(default=None, gt=0.0)
    return_reserve_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_overlap_threshold: float = Field(default=0.85, ge=0.1, le=0.99)
    include_sensitivity: bool = True
    include_independent_return: bool = True


class DistinctRouteCandidate(BaseModel):
    """One spatially distinct computed route candidate with uncertainty, return, and sensitivity metrics."""

    candidate_id: str
    objective: RouteObjective
    objective_label: str
    diversification_method: str  # objective_weight | spatial_corridor_penalty
    max_overlap_with_prior_routes: float = 0.0
    route: RouteComputeResponse
    return_computed: bool = False
    return_status: Optional[str] = None
    return_distance_m: Optional[float] = None
    return_elevation_gain_m: Optional[float] = None
    return_overlap_with_outbound_fraction: Optional[float] = None
    sensitivity_summary: Optional[RouteSensitivityReport] = None
    evidence_highlights: List[str] = Field(default_factory=list)


class RobustRouteCompareResponse(BaseModel):
    """Robust multi-route comparison matrix distinguishing genuine alternatives from bottlenecks."""

    dataset_id: str
    source_product_id: str
    alternative_generation_status: str  # DISTINCT_ALTERNATIVES_AVAILABLE | SINGLE_CORRIDOR_BOTTLENECK | INSUFFICIENT_FEASIBLE_ROUTES
    search_algorithm: str = "8_neighbor_terrain_grid_pathfinder"
    diversification_strategy: str = "multi_objective_weights_plus_corridor_spatial_penalty_pass"
    search_limits: Dict[str, Any] = Field(default_factory=dict)
    overlap_metric_definition: str = (
        "Symmetric vertex proximity overlap fraction: min(frac A vertices within tolerance_m of B, frac B vertices within tolerance_m of A)."
    )
    global_optimality_disclaimer: str = (
        "Generates heuristic feasible alternatives bounded by DEM grid resolution, configured objectives, and spatial penalty passes; "
        "does NOT guarantee discovery of every globally Pareto-optimal corridor."
    )
    recommended_candidate_id: Optional[str] = None
    recommendation_rationale: str
    distinct_candidate_count: int
    duplicate_candidates_rejected: int
    pairwise_overlap_matrix: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    candidates: List[DistinctRouteCandidate] = Field(default_factory=list)
    rejected_near_duplicates: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    stage_timings_ms: Dict[str, float] = Field(default_factory=dict)
    compute_time_ms: float = 0.0
