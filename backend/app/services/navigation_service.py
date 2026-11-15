"""
MARSCOPE Active Marswalk Navigation Service (Prompt 2)
Manages persistent navigation sessions, centralized state machine transitions,
route-segment & turn-by-turn instruction projection, live position progress &
deviation evaluation, obstruction reporting, candidate replanning, and independent
EVA return / turnback assessment.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException, status

from app.db.database import MissionDatabase
from app.eva_operations.return_planning import plan_eva_return_route
from app.eva_operations.schemas import ReturnPlanStatus
from app.routing.instructions import (
    equirectangular_grid_north_bearing_deg,
    generate_turn_by_turn_instructions,
    mars_true_north_bearing_deg,
)
from app.routing.schemas import RouteComputeRequest, RouteComputeResponse, RouteVertex
from app.schemas.navigation import (
    ApproveReplanRequest,
    CreateNavigationSessionRequest,
    NavigationInstructionDetail,
    NavigationProgressDetail,
    NavigationSegmentDetail,
    NavigationSessionResponse,
    NavigationState,
    NavigationTransitionRequest,
    ObstructionReportResponse,
    ReplanNavigationRequest,
    ReportObstructionRequest,
    TurnbackAssessmentResponse,
    TurnbackState,
)
from app.services.mission_event_service import MissionEventService
from app.services.position_service import CrewPositionService
from app.services.realtime_hub import MissionRealtimeHub


MARS_RADIUS_M = 3_389_500.0

ALLOWED_NAV_TRANSITIONS: Dict[NavigationState, List[NavigationState]] = {
    "NOT_CONFIGURED": ["READY_FOR_OPERATOR_REVIEW"],
    "READY_FOR_OPERATOR_REVIEW": ["AWAITING_OPERATOR_APPROVAL", "ACTIVE", "ABORTED"],
    "AWAITING_OPERATOR_APPROVAL": ["ACTIVE", "PAUSED", "ABORTED", "EMERGENCY"],
    "ACTIVE": [
        "PAUSED",
        "POSITION_UNAVAILABLE",
        "POSITION_STALE",
        "ROUTE_DEVIATION_DETECTED",
        "OBSTRUCTION_REPORTED",
        "REPLANNING_REQUIRED",
        "RETURN_REQUESTED",
        "COMPLETED",
        "ABORTED",
        "EMERGENCY",
    ],
    "POSITION_UNAVAILABLE": ["ACTIVE", "POSITION_STALE", "PAUSED", "RETURN_REQUESTED", "ABORTED", "EMERGENCY"],
    "POSITION_STALE": ["ACTIVE", "POSITION_UNAVAILABLE", "PAUSED", "RETURN_REQUESTED", "ABORTED", "EMERGENCY"],
    "ROUTE_DEVIATION_DETECTED": ["ACTIVE", "REPLANNING_REQUIRED", "RETURN_REQUESTED", "PAUSED", "ABORTED", "EMERGENCY"],
    "OBSTRUCTION_REPORTED": ["REPLANNING_REQUIRED", "ACTIVE", "RETURN_REQUESTED", "PAUSED", "ABORTED", "EMERGENCY"],
    "REPLANNING_REQUIRED": ["AWAITING_OPERATOR_APPROVAL", "ACTIVE", "RETURN_REQUESTED", "PAUSED", "ABORTED", "EMERGENCY"],
    "RETURN_REQUESTED": ["RETURN_ROUTE_ACTIVE", "REPLANNING_REQUIRED", "PAUSED", "ABORTED", "EMERGENCY"],
    "RETURN_ROUTE_ACTIVE": [
        "PAUSED",
        "POSITION_UNAVAILABLE",
        "POSITION_STALE",
        "OBSTRUCTION_REPORTED",
        "REPLANNING_REQUIRED",
        "COMPLETED",
        "ABORTED",
        "EMERGENCY",
    ],
    "PAUSED": ["ACTIVE", "RETURN_ROUTE_ACTIVE", "REPLANNING_REQUIRED", "ABORTED", "EMERGENCY"],
    "EMERGENCY": ["PAUSED", "RETURN_REQUESTED", "ABORTED"],
    "COMPLETED": [],
    "ABORTED": [],
}

OPERATOR_APPROVAL_STATES = {"ACTIVE", "RETURN_ROUTE_ACTIVE", "ABORTED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mars_surface_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(((lon2 - lon1 + 180.0) % 360.0) - 180.0)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * MARS_RADIUS_M * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def _point_to_segment_distance_m(
    plat: float, plon: float, alat: float, alon: float, blat: float, blon: float
) -> float:
    # Local equirectangular projection around segment midpoint on Mars sphere
    mid_lat = math.radians(0.5 * (alat + blat))
    cos_lat = max(1e-6, math.cos(mid_lat))
    ax = math.radians(alon) * MARS_RADIUS_M * cos_lat
    ay = math.radians(alat) * MARS_RADIUS_M
    bx = math.radians(blon) * MARS_RADIUS_M * cos_lat
    by = math.radians(blat) * MARS_RADIUS_M
    px = math.radians(plon) * MARS_RADIUS_M * cos_lat
    py = math.radians(plat) * MARS_RADIUS_M
    dx = bx - ax
    dy = by - ay
    len_sq = dx * dx + dy * dy
    if len_sq <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


class NavigationService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        realtime_hub: MissionRealtimeHub,
        position_service: CrewPositionService,
        routing_service: Any,
    ) -> None:
        self.db = db
        self.event_service = event_service
        self.realtime_hub = realtime_hub
        self.position_service = position_service
        self.routing_service = routing_service

    def create_session(
        self,
        *,
        mission_id: str,
        astronaut_id: str,
        req: CreateNavigationSessionRequest,
    ) -> NavigationSessionResponse:
        raw_vertices = req.route_payload.get("vertices")
        if not isinstance(raw_vertices, list) or len(raw_vertices) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Active navigation requires an actual computed route with at least 2 vertices.",
            )
        payload_dataset = str(req.route_payload.get("dataset_id") or "").strip()
        if payload_dataset and payload_dataset != req.route_dataset_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"route_dataset_id ({req.route_dataset_id}) does not match route_payload.dataset_id ({payload_dataset}).",
            )
        payload_crs = str(req.route_payload.get("crs") or req.route_crs).strip()
        if payload_crs != req.route_crs:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"route_crs ({req.route_crs}) does not match route_payload.crs ({payload_crs}).",
            )

        nav_id = str(uuid.uuid4())
        now = _utc_now()
        initial_state: NavigationState = (
            "AWAITING_OPERATOR_APPROVAL"
            if req.navigation_mode == "OPERATOR_SUPERVISED_EVA"
            else "READY_FOR_OPERATOR_REVIEW"
        )

        snapshot = dict(req.route_payload)
        snapshot.setdefault("dataset_id", req.route_dataset_id)
        snapshot.setdefault("crs", req.route_crs)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO navigation_sessions (
                    nav_session_id, mission_id, astronaut_id, state, navigation_mode,
                    route_id, route_dataset_id, route_crs,
                    return_destination_name, return_destination_lat, return_destination_lon,
                    deviation_threshold_m, active_segment_index,
                    route_snapshot_json, operational_params_json,
                    candidate_replan_json, last_turnback_json,
                    approved_by, approved_at_utc, last_state_reason,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?)
                """,
                (
                    nav_id,
                    mission_id,
                    astronaut_id,
                    initial_state,
                    req.navigation_mode,
                    req.route_id or req.route_payload.get("route_id"),
                    req.route_dataset_id,
                    req.route_crs,
                    req.return_destination_name.strip(),
                    float(req.return_destination_lat),
                    float(req.return_destination_lon),
                    req.deviation_threshold_m,
                    json.dumps(snapshot),
                    json.dumps(req.operational_params or {}),
                    "Navigation session created from computed route geometry.",
                    now,
                    now,
                ),
            )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type="navigation.session_created",
                actor_id=astronaut_id,
                provenance={"source": "NAVIGATION_SERVICE"},
                payload={
                    "nav_session_id": nav_id,
                    "state": initial_state,
                    "navigation_mode": req.navigation_mode,
                    "route_dataset_id": req.route_dataset_id,
                    "route_crs": req.route_crs,
                },
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_id)

    def list_sessions(self, *, mission_id: str) -> List[NavigationSessionResponse]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT nav_session_id FROM navigation_sessions WHERE mission_id = ? ORDER BY updated_at_utc DESC",
                (mission_id,),
            ).fetchall()
            ids = [r["nav_session_id"] for r in rows]
        return [self.get_session(mission_id=mission_id, nav_session_id=nid) for nid in ids]

    def get_session(self, *, mission_id: str, nav_session_id: str) -> NavigationSessionResponse:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT * FROM navigation_sessions WHERE nav_session_id = ? AND mission_id = ?",
                (nav_session_id, mission_id),
            ).fetchone()
            obs_rows = conn.execute(
                "SELECT * FROM navigation_obstructions WHERE nav_session_id = ? ORDER BY created_at_utc DESC",
                (nav_session_id,),
            ).fetchall()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Navigation session not found.")
        return self._hydrate_session(row, obs_rows)

    def transition_state(
        self,
        *,
        mission_id: str,
        nav_session_id: str,
        actor_id: str,
        actor_role: str,
        req: NavigationTransitionRequest,
    ) -> NavigationSessionResponse:
        now = _utc_now()

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM navigation_sessions WHERE nav_session_id = ? AND mission_id = ?",
                (nav_session_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Navigation session not found.")

            cur_state: NavigationState = row["state"]
            target: NavigationState = req.target_state
            allowed = ALLOWED_NAV_TRANSITIONS.get(cur_state, [])
            if target not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Invalid navigation transition: {cur_state} -> {target}. Allowed: {allowed}",
                )

            if target in OPERATOR_APPROVAL_STATES and cur_state in (
                "READY_FOR_OPERATOR_REVIEW",
                "AWAITING_OPERATOR_APPROVAL",
                "REPLANNING_REQUIRED",
                "RETURN_REQUESTED",
                "ROUTE_DEVIATION_DETECTED",
                "OBSTRUCTION_REPORTED",
                "EMERGENCY",
            ):
                if actor_role not in ("MISSION_LEAD", "MISSION_OPERATOR"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Transition {cur_state} -> {target} requires MISSION_LEAD or MISSION_OPERATOR.",
                    )

            if target == "ACTIVE" and cur_state == "REPLANNING_REQUIRED" and row["candidate_replan_json"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Pending candidate replan must be explicitly approved or rejected first.",
                )

            approved_by = row["approved_by"]
            approved_at = row["approved_at_utc"]
            if target in ("ACTIVE", "RETURN_ROUTE_ACTIVE") and actor_role in ("MISSION_LEAD", "MISSION_OPERATOR"):
                approved_by = actor_id
                approved_at = now

            conn.execute(
                """
                UPDATE navigation_sessions
                SET state = ?, approved_by = ?, approved_at_utc = ?, last_state_reason = ?, updated_at_utc = ?
                WHERE nav_session_id = ? AND mission_id = ?
                """,
                (target, approved_by, approved_at, req.reason, now, nav_session_id, mission_id),
            )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type="navigation.state_changed",
                actor_id=actor_id,
                provenance={"source": "NAVIGATION_STATE_MACHINE"},
                payload={
                    "nav_session_id": nav_session_id,
                    "previous_state": cur_state,
                    "new_state": target,
                    "reason": req.reason,
                    "actor_role": actor_role,
                },
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)

    def report_obstruction(
        self,
        *,
        mission_id: str,
        nav_session_id: str,
        actor_id: str,
        req: ReportObstructionRequest,
    ) -> NavigationSessionResponse:
        now = _utc_now()
        obs_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM navigation_sessions WHERE nav_session_id = ? AND mission_id = ?",
                (nav_session_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Navigation session not found.")

            conn.execute(
                """
                INSERT INTO navigation_obstructions (
                    obstruction_id, nav_session_id, mission_id, reported_by,
                    segment_index, latitude, longitude, location_source,
                    description, voice_note_id, attachment_note,
                    review_state, epistemic_classification, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED', 'USER_REPORTED', ?)
                """,
                (
                    obs_id,
                    nav_session_id,
                    mission_id,
                    actor_id,
                    req.segment_index,
                    float(req.latitude),
                    float(req.longitude),
                    req.location_source,
                    req.description.strip(),
                    req.voice_note_id,
                    req.attachment_note,
                    now,
                ),
            )

            cur_state: NavigationState = row["state"]
            next_state: NavigationState = (
                "OBSTRUCTION_REPORTED"
                if "OBSTRUCTION_REPORTED" in ALLOWED_NAV_TRANSITIONS.get(cur_state, [])
                else cur_state
            )
            conn.execute(
                """
                UPDATE navigation_sessions
                SET state = ?, last_state_reason = ?, updated_at_utc = ?
                WHERE nav_session_id = ? AND mission_id = ?
                """,
                (next_state, f"Obstruction reported ({obs_id}): {req.description.strip()[:120]}", now, nav_session_id, mission_id),
            )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type="navigation.obstruction_reported",
                actor_id=actor_id,
                provenance={"source": "CREW_FIELD_REPORT"},
                payload={
                    "nav_session_id": nav_session_id,
                    "obstruction_id": obs_id,
                    "segment_index": req.segment_index,
                    "latitude": float(req.latitude),
                    "longitude": float(req.longitude),
                    "epistemic_classification": "USER_REPORTED",
                    "review_state": "UNVERIFIED",
                },
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)

    def compute_candidate_replan(
        self,
        *,
        mission_id: str,
        nav_session_id: str,
        actor_id: str,
        req: ReplanNavigationRequest,
    ) -> NavigationSessionResponse:
        session = self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)
        if not session.segments:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No route segments to replan from.")

        # Determine start point from fresh position if available, else current segment start
        pos = self.position_service.get_latest_position(mission_id, session.astronaut_id)
        if pos is not None and not pos.is_stale:
            start_lat, start_lon = pos.latitude, pos.longitude_east
            start_source = f"LATEST_VALID_POSITION ({pos.source_classification})"
        else:
            seg = session.segments[min(session.active_segment_index, len(session.segments) - 1)]
            start_lat, start_lon = seg.start_lat, seg.start_lon
            start_source = "ACTIVE_SEGMENT_START (LIVE_LOCALIZATION_UNAVAILABLE)"

        end_seg = session.segments[-1]
        end_lat, end_lon = end_seg.end_lat, end_seg.end_lon

        if self.routing_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Routing engine unavailable; cannot compute candidate replan.",
            )

        route_req = RouteComputeRequest(
            dataset_id=session.route_dataset_id,
            start_lat=start_lat,
            start_lon=start_lon,
            end_lat=end_lat,
            end_lon=end_lon,
            strategy=req.strategy,
        )
        candidate = self.routing_service.compute_route(route_req)
        candidate_dict = candidate.model_dump()
        candidate_payload = {
            "candidate_id": str(uuid.uuid4()),
            "requested_by": actor_id,
            "requested_at_utc": _utc_now(),
            "start_source": start_source,
            "avoid_obstruction_id": req.avoid_obstruction_id,
            "reason": req.reason,
            "status": "AWAITING_OPERATOR_APPROVAL",
            "route": candidate_dict,
        }

        now = _utc_now()

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE navigation_sessions
                SET state = 'REPLANNING_REQUIRED', candidate_replan_json = ?, last_state_reason = ?, updated_at_utc = ?
                WHERE nav_session_id = ? AND mission_id = ?
                """,
                (
                    json.dumps(candidate_payload),
                    req.reason or "Candidate replan computed; awaiting operator approval.",
                    now,
                    nav_session_id,
                    mission_id,
                ),
            )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type="navigation.replan_candidate_computed",
                actor_id=actor_id,
                provenance={"source": "ROUTING_ENGINE"},
                payload={
                    "nav_session_id": nav_session_id,
                    "candidate_id": candidate_payload["candidate_id"],
                    "dataset_id": session.route_dataset_id,
                    "total_surface_distance_m": candidate.total_surface_distance_m,
                },
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)

    def decide_candidate_replan(
        self,
        *,
        mission_id: str,
        nav_session_id: str,
        actor_id: str,
        req: ApproveReplanRequest,
    ) -> NavigationSessionResponse:
        now = _utc_now()

        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM navigation_sessions WHERE nav_session_id = ? AND mission_id = ?",
                (nav_session_id, mission_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Navigation session not found.")
            if not row["candidate_replan_json"]:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending candidate replan exists.")

            cand = json.loads(row["candidate_replan_json"])
            if req.decision == "APPROVE":
                new_route = cand["route"]
                conn.execute(
                    """
                    UPDATE navigation_sessions
                    SET state = 'ACTIVE',
                        route_snapshot_json = ?,
                        active_segment_index = 0,
                        candidate_replan_json = NULL,
                        approved_by = ?,
                        approved_at_utc = ?,
                        last_state_reason = ?,
                        updated_at_utc = ?
                    WHERE nav_session_id = ? AND mission_id = ?
                    """,
                    (
                        json.dumps(new_route),
                        actor_id,
                        now,
                        req.reason or "Operator approved candidate replan.",
                        now,
                        nav_session_id,
                        mission_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE navigation_sessions
                    SET candidate_replan_json = NULL,
                        last_state_reason = ?,
                        updated_at_utc = ?
                    WHERE nav_session_id = ? AND mission_id = ?
                    """,
                    (
                        req.reason or "Operator rejected candidate replan; previous route retained.",
                        now,
                        nav_session_id,
                        mission_id,
                    ),
                )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type=f"navigation.replan_{req.decision.lower()}d",
                actor_id=actor_id,
                provenance={"source": "OPERATOR_REVIEW"},
                payload={
                    "nav_session_id": nav_session_id,
                    "candidate_id": cand.get("candidate_id"),
                    "decision": req.decision,
                    "reason": req.reason,
                },
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)

    def evaluate_turnback(
        self,
        *,
        mission_id: str,
        nav_session_id: str,
        actor_id: str,
    ) -> NavigationSessionResponse:
        session = self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)
        now = _utc_now()
        pos = self.position_service.get_latest_position(mission_id, session.astronaut_id)

        missing_inputs: List[str] = []
        if pos is None or pos.is_stale:
            missing_inputs.append("fresh_astronaut_localization")

        with self.db.read() as conn:
            r = conn.execute(
                "SELECT route_snapshot_json, operational_params_json FROM navigation_sessions WHERE nav_session_id = ?",
                (nav_session_id,),
            ).fetchone()
            snap_raw, params_raw = r["route_snapshot_json"], r["operational_params_json"]
        snap = json.loads(snap_raw)
        params = json.loads(params_raw)

        walking_speed_mps = params.get("walking_speed_mps")
        max_duration_s = params.get("max_duration_s")
        use_tobler = bool(params.get("use_tobler_grade_approximation", False))
        stop_dwell_s = float(params.get("stop_dwell_total_s") or 0.0)
        overhead_s = float(params.get("operational_overhead_s") or 0.0)
        resource_configured = bool(params.get("resource_budgets_configured", False))

        if walking_speed_mps is None and not use_tobler:
            missing_inputs.append("walking_speed_mps_or_locomotion_model")
        if max_duration_s is None:
            missing_inputs.append("max_duration_s")
        if not resource_configured:
            missing_inputs.append("resource_budgets")

        # Build an outbound RouteComputeResponse up to current position (or full route if unavailable)
        outbound_dist = float(snap.get("total_surface_distance_m") or 0.0)
        return_report = None
        if pos is not None and not pos.is_stale and self.routing_service is not None:
            try:
                cur_to_return_route = RouteComputeResponse(
                    route_id=session.route_id or nav_session_id,
                    dataset_id=session.route_dataset_id,
                    crs=session.route_crs,
                    strategy=str(snap.get("strategy") or "balanced"),
                    total_surface_distance_m=outbound_dist,
                    total_horizontal_distance_m=float(snap.get("total_horizontal_distance_m") or outbound_dist),
                    total_elevation_gain_m=float(snap.get("total_elevation_gain_m") or 0.0),
                    total_elevation_loss_m=float(snap.get("total_elevation_loss_m") or 0.0),
                    vertices=[
                        RouteVertex(**v) if isinstance(v, dict) else v
                        for v in [
                            {
                                "lat": session.return_destination_lat,
                                "lon_east": session.return_destination_lon,
                                "elevation_m": snap["vertices"][0].get("elevation_m"),
                                "slope_deg": snap["vertices"][0].get("slope_deg"),
                                "cumulative_distance_m": 0.0,
                                "is_stop": True,
                                "stop_label": session.return_destination_name,
                            },
                            {
                                "lat": pos.latitude,
                                "lon_east": pos.longitude_east,
                                "elevation_m": pos.elevation_m,
                                "slope_deg": None,
                                "cumulative_distance_m": outbound_dist,
                                "is_stop": True,
                                "stop_label": "Current Position",
                            },
                        ]
                    ],
                    instructions=[],
                )
                return_report = plan_eva_return_route(
                    routing_service=self.routing_service,
                    dataset_id=session.route_dataset_id,
                    outbound_route=cur_to_return_route,
                    walking_speed_mps=float(walking_speed_mps) if walking_speed_mps is not None else None,
                    use_tobler_grade_approximation=use_tobler,
                    stop_dwell_total_s=stop_dwell_s,
                    operational_overhead_s=overhead_s,
                    usable_budget_s=float(max_duration_s) if max_duration_s is not None else None,
                    compute_reverse_return_route=True,
                )
            except Exception as exc:
                return_report = None
                missing_inputs.append(f"return_route_evaluation_error: {exc}")

        state: TurnbackState
        if "fresh_astronaut_localization" in missing_inputs:
            state = "INSUFFICIENT_LOCALIZATION"
            note = "Live astronaut localization is unavailable or stale; turnback assessment cannot verify current distance to return destination."
        elif return_report is None or not return_report.return_route_computed:
            state = "RETURN_ROUTE_UNAVAILABLE"
            note = "Independent terrain-backed return route could not be computed to the configured return destination."
        elif return_report.return_status == ReturnPlanStatus.RETURN_DATA_UNAVAILABLE:
            state = "INSUFFICIENT_TERRAIN_EVIDENCE"
            note = return_report.return_strategy_note
        elif not resource_configured or max_duration_s is None:
            state = "RESOURCE_BUDGET_INCOMPLETE"
            note = "Return route geometry evaluated, but explicit mission duration or resource budgets are not configured."
        elif (
            return_report.return_duration_s is not None
            and max_duration_s is not None
            and (return_report.return_duration_s + overhead_s) > float(max_duration_s) * 0.85
        ):
            state = "TURNBACK_REVIEW_REQUIRED"
            note = "Estimated return duration approaches or exceeds configured duration envelope; operator turnback review required."
        else:
            state = "WITHIN_CONFIGURED_PLANNING_CONSTRAINTS"
            note = "Evaluated against configured planning parameters only; this is a decision-support state, not a safety certification."

        assessment = TurnbackAssessmentResponse(
            state=state,
            evaluated_at_utc=now,
            outbound_distance_m=outbound_dist,
            return_distance_m=return_report.return_surface_distance_m if return_report else None,
            return_estimated_duration_s=return_report.return_duration_s if return_report else None,
            configured_max_duration_s=float(max_duration_s) if max_duration_s is not None else None,
            return_route_available=bool(return_report and return_report.return_route_computed),
            return_route_status=str(return_report.return_status.value) if return_report else "RETURN_ROUTE_UNAVAILABLE",
            resource_budget_status="CONFIGURED" if resource_configured else "NOT_CONFIGURED",
            missing_inputs=missing_inputs,
            decision_support_note=note,
            return_route_vertices=[v.model_dump() for v in return_report.return_vertices] if return_report else [],
            provenance={
                "dataset_id": session.route_dataset_id,
                "crs": session.route_crs,
                "return_destination": session.return_destination_name,
                "independent_return_evaluated": True,
            },
        )

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE navigation_sessions SET last_turnback_json = ?, updated_at_utc = ? WHERE nav_session_id = ?",
                (assessment.model_dump_json(), now, nav_session_id),
            )
            ev = self.event_service.record_event_tx(
                conn,
                mission_id=mission_id,
                event_type="navigation.turnback_evaluated",
                actor_id=actor_id,
                provenance={"source": "RETURN_PLANNING_ENGINE"},
                payload={"nav_session_id": nav_session_id, "turnback_state": state},
            )
        self.realtime_hub.publish_mission_event(
            mission_id,
            event_type=ev.event_type,
            payload=ev.model_dump(),
            event_seq=ev.event_seq,
        )
        return self.get_session(mission_id=mission_id, nav_session_id=nav_session_id)

    def _hydrate_session(self, row: sqlite3.Row, obs_rows: List[sqlite3.Row]) -> NavigationSessionResponse:
        snap = json.loads(row["route_snapshot_json"])
        raw_verts = snap.get("vertices") or []
        dataset_id = row["route_dataset_id"]
        crs = row["route_crs"]
        dem_res_m = snap.get("dem_resolution_m")
        terrain_unc_m = snap.get("terrain_uncertainty_m")
        reg_unc_m = snap.get("registration_uncertainty_m")
        coverage_pct = snap.get("valid_pixel_coverage_pct")
        route_limitations: List[str] = list(snap.get("warnings") or snap.get("limitations") or [])

        segments: List[NavigationSegmentDetail] = []
        instructions: List[NavigationInstructionDetail] = []
        total_dist = float(snap.get("total_surface_distance_m") or 0.0)

        for idx in range(max(0, len(raw_verts) - 1)):
            a = raw_verts[idx]
            b = raw_verts[idx + 1]
            alat = float(a.get("lat"))
            alon = float(a.get("lon_east", a.get("lon", 0.0)))
            blat = float(b.get("lat"))
            blon = float(b.get("lon_east", b.get("lon", 0.0)))
            d_cum_a = float(a.get("cumulative_distance_m") or 0.0)
            d_cum_b = float(b.get("cumulative_distance_m") or 0.0)
            seg_dist = max(0.0, d_cum_b - d_cum_a) if d_cum_b > d_cum_a else _mars_surface_distance_m(alat, alon, blat, blon)

            ea = a.get("elevation_m")
            eb = b.get("elevation_m")
            egain = max(0.0, float(eb) - float(ea)) if (ea is not None and eb is not None) else None
            eloss = max(0.0, float(ea) - float(eb)) if (ea is not None and eb is not None) else None
            slope = b.get("slope_deg") if b.get("slope_deg") is not None else a.get("slope_deg")
            rough = b.get("roughness_m") if b.get("roughness_m") is not None else a.get("roughness_m")

            gaps: List[str] = []
            if ea is None or eb is None:
                gaps.append("DEM elevation missing at one or more segment endpoints")
            if slope is None:
                gaps.append("Slope value unavailable at segment")
            support_state = "SUPPORTED" if not gaps else ("LIMITED" if ea is not None or eb is not None else "UNKNOWN")
            trav_state = "DEM_SLOPE_EVALUATED" if slope is not None else "INSUFFICIENT_TERRAIN_EVIDENCE"

            seg_id = f"seg-{idx + 1:03d}"
            limitation = (
                f"Derived from {dataset_id}; coarse orbital DEM cannot certify absence of sub-pixel boulders or regolith failure."
            )
            segments.append(
                NavigationSegmentDetail(
                    segment_id=seg_id,
                    segment_index=idx,
                    start_lat=alat,
                    start_lon=alon,
                    end_lat=blat,
                    end_lon=blon,
                    crs=crs,
                    surface_distance_m=round(seg_dist, 3),
                    start_elevation_m=ea,
                    end_elevation_m=eb,
                    elevation_gain_m=round(egain, 3) if egain is not None else None,
                    elevation_loss_m=round(eloss, 3) if eloss is not None else None,
                    slope_deg=slope,
                    roughness_m=rough,
                    source_dem=dataset_id,
                    effective_resolution_m=dem_res_m,
                    valid_pixel_coverage_pct=coverage_pct,
                    terrain_uncertainty_m=terrain_unc_m,
                    registration_uncertainty_m=reg_unc_m,
                    traversability_evidence_state=trav_state,
                    candidate_obstacles=[],
                    known_data_gaps=gaps,
                    limitation_note=limitation,
                )
            )

            true_brg = mars_true_north_bearing_deg(alat, alon, blat, blon)
            grid_brg = equirectangular_grid_north_bearing_deg(alat, alon, blat, blon)
            rem_dist = max(0.0, total_dist - d_cum_a) if total_dist > 0 else seg_dist
            stop_lbl = b.get("stop_label")
            is_last = idx == len(raw_verts) - 2
            text = (
                f"Proceed {seg_dist:.1f} m at {true_brg:.1f}° True-N (Grid {grid_brg:.1f}°) toward "
                f"{stop_lbl or ('Destination' if is_last else f'Waypoint {idx + 2}')}."
            )
            instructions.append(
                NavigationInstructionDetail(
                    step_index=idx + 1,
                    segment_id=seg_id,
                    instruction_text=text,
                    true_north_bearing_deg=round(true_brg, 2),
                    grid_north_bearing_deg=round(grid_brg, 2),
                    bearing_reference=f"Mars True North & {crs} Equirectangular Grid North",
                    heading_status="UNAVAILABLE",
                    distance_m=round(seg_dist, 2),
                    remaining_distance_m=round(rem_dist, 2),
                    elevation_change_m=round(float(eb) - float(ea), 2) if (ea is not None and eb is not None) else None,
                    slope_deg=slope,
                    support_state=support_state,
                    terrain_limitation=gaps[0] if gaps else None,
                    is_arrival=is_last,
                )
            )

        progress = self._evaluate_progress(
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            segments=segments,
            total_distance_m=total_dist,
            deviation_threshold_m=row["deviation_threshold_m"],
        )

        obstructions = [
            ObstructionReportResponse(
                obstruction_id=o["obstruction_id"],
                nav_session_id=o["nav_session_id"],
                mission_id=o["mission_id"],
                reported_by=o["reported_by"],
                segment_index=o["segment_index"],
                latitude=o["latitude"],
                longitude=o["longitude"],
                location_source=o["location_source"],
                description=o["description"],
                voice_note_id=o["voice_note_id"],
                attachment_note=o["attachment_note"],
                review_state=o["review_state"],
                epistemic_classification=o["epistemic_classification"],
                created_at_utc=o["created_at_utc"],
            )
            for o in obs_rows
        ]

        turnback = (
            TurnbackAssessmentResponse.model_validate_json(row["last_turnback_json"])
            if row["last_turnback_json"]
            else None
        )
        candidate_replan = json.loads(row["candidate_replan_json"]) if row["candidate_replan_json"] else None
        state: NavigationState = row["state"]

        return NavigationSessionResponse(
            nav_session_id=row["nav_session_id"],
            mission_id=row["mission_id"],
            astronaut_id=row["astronaut_id"],
            state=state,
            allowed_transitions=ALLOWED_NAV_TRANSITIONS.get(state, []),
            navigation_mode=row["navigation_mode"],
            route_id=row["route_id"],
            route_dataset_id=dataset_id,
            route_crs=crs,
            return_destination_name=row["return_destination_name"],
            return_destination_lat=row["return_destination_lat"],
            return_destination_lon=row["return_destination_lon"],
            deviation_threshold_m=row["deviation_threshold_m"],
            active_segment_index=row["active_segment_index"],
            segments=segments,
            instructions=instructions,
            progress=progress,
            turnback=turnback,
            obstructions=obstructions,
            candidate_replan=candidate_replan,
            route_limitations=route_limitations,
            approved_by=row["approved_by"],
            approved_at_utc=row["approved_at_utc"],
            last_state_reason=row["last_state_reason"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )

    def _evaluate_progress(
        self,
        *,
        mission_id: str,
        astronaut_id: str,
        segments: List[NavigationSegmentDetail],
        total_distance_m: float,
        deviation_threshold_m: Optional[float],
    ) -> NavigationProgressDetail:
        pos = self.position_service.get_latest_position(mission_id, astronaut_id)
        if pos is None:
            return NavigationProgressDetail(
                progress_status="PROGRESS UNAVAILABLE",
                localization_banner="LIVE MARS LOCALIZATION UNAVAILABLE",
                localization_freshness="UNAVAILABLE",
                localization_epistemic_classification="UNAVAILABLE",
                deviation_state="UNAVAILABLE_ACCURACY_OR_POSITION",
                deviation_limitation="No valid Mars position packet is available.",
            )

        freshness = "STALE" if pos.is_stale else "FRESH"
        epistemic = "USER_REPORTED" if pos.source_classification == "USER_PROVIDED" else "DIRECTLY_MEASURED"

        if pos.is_stale:
            return NavigationProgressDetail(
                progress_status="PROGRESS UNAVAILABLE",
                localization_banner="LIVE MARS LOCALIZATION UNAVAILABLE",
                localization_freshness=freshness,
                localization_epistemic_classification=epistemic,
                position_timestamp_utc=pos.measured_at_utc,
                position_source=pos.source_id,
                accuracy_m=pos.uncertainty_m,
                deviation_state="UNAVAILABLE_ACCURACY_OR_POSITION",
                deviation_limitation=f"Last known position is STALE ({pos.measured_at_utc}); cannot compute live progress.",
            )

        if not segments:
            return NavigationProgressDetail(
                progress_status="PROGRESS UNAVAILABLE",
                localization_banner="LIVE MARS LOCALIZATION AVAILABLE",
                localization_freshness=freshness,
                localization_epistemic_classification=epistemic,
                position_timestamp_utc=pos.measured_at_utc,
                position_source=pos.source_id,
                accuracy_m=pos.uncertainty_m,
                deviation_state="UNAVAILABLE_ACCURACY_OR_POSITION",
                deviation_limitation="Route has no geometry segments.",
            )

        best_idx = 0
        best_dist = float("inf")
        for seg in segments:
            d = _point_to_segment_distance_m(
                pos.latitude, pos.longitude_east, seg.start_lat, seg.start_lon, seg.end_lat, seg.end_lon
            )
            if d < best_dist:
                best_dist = d
                best_idx = seg.segment_index

        cur_seg = segments[best_idx]
        dist_to_next = _mars_surface_distance_m(pos.latitude, pos.longitude_east, cur_seg.end_lat, cur_seg.end_lon)
        remaining = dist_to_next + sum(s.surface_distance_m for s in segments[best_idx + 1 :])
        denom = total_distance_m if total_distance_m > 0 else sum(s.surface_distance_m for s in segments)
        completed_frac = max(0.0, min(1.0, 1.0 - (remaining / denom))) if denom > 0 else None

        if deviation_threshold_m is None:
            dev_state = "NOT_CONFIGURED"
            dev_lim = "Operator deviation_threshold_m is not configured."
        elif pos.uncertainty_m is None:
            dev_state = "UNAVAILABLE_ACCURACY_OR_POSITION"
            dev_lim = "Position provider did not supply uncertainty_m; deviation comparison is not meaningful."
        elif best_dist > float(deviation_threshold_m):
            dev_state = "DEVIATION_DETECTED"
            dev_lim = f"Cross-track offset {best_dist:.1f} m exceeds configured threshold {deviation_threshold_m:.1f} m (±{pos.uncertainty_m:.1f} m)."
        else:
            dev_state = "WITHIN_THRESHOLD"
            dev_lim = None

        return NavigationProgressDetail(
            progress_status="AVAILABLE",
            localization_banner=f"LOCALIZATION {epistemic} ({freshness})",
            localization_freshness=freshness,
            localization_epistemic_classification=epistemic,
            position_timestamp_utc=pos.measured_at_utc,
            position_source=pos.source_id,
            accuracy_m=pos.uncertainty_m,
            nearest_segment_index=best_idx,
            distance_to_next_waypoint_m=round(dist_to_next, 2),
            remaining_route_distance_m=round(remaining, 2),
            completed_fraction=round(completed_frac, 4) if completed_frac is not None else None,
            cross_track_deviation_m=round(best_dist, 2),
            deviation_state=dev_state,
            deviation_limitation=dev_lim,
        )
