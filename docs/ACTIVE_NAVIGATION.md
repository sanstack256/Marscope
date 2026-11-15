# MARSCOPE Active Surface Navigation (`Prompt 2`)

## Overview
`/active-navigation` provides an integrated Marswalk surface navigation workstation backed by `NavigationService` (`backend/app/services/navigation_service.py`) and persisted in SQLite (`0002_active_navigation_and_ops.sql`).

## Prerequisites
A navigation session cannot be created unless:
1. The astronaut is authenticated and an active member of the mission.
2. A landing/return destination is explicitly configured (`/landing-site`).
3. An actual terrain-backed route (`>= 2` vertices, valid `dataset_id`, valid Mars CRS such as `IAU2000:49900`) is computed (`/planner`).
4. A `navigation_mode` (`OPERATOR_SUPERVISED_EVA`, `MANUAL_WAYPOINT_CHECK`, or `RETURN_TO_BASE`) is explicitly selected.

## State Machine
Centralized transitions in `ALLOWED_NAV_TRANSITIONS` enforce:
`NOT_CONFIGURED`, `READY_FOR_OPERATOR_REVIEW`, `AWAITING_OPERATOR_APPROVAL`, `ACTIVE`, `POSITION_UNAVAILABLE`, `POSITION_STALE`, `ROUTE_DEVIATION_DETECTED`, `OBSTRUCTION_REPORTED`, `REPLANNING_REQUIRED`, `RETURN_REQUESTED`, `RETURN_ROUTE_ACTIVE`, `PAUSED`, `COMPLETED`, `ABORTED`, `EMERGENCY`.

Operator-gated transitions (`ACTIVE`, `RETURN_ROUTE_ACTIVE`, `ABORTED` from review/replan/return/emergency states) require `MISSION_LEAD` or `MISSION_OPERATOR` role. Every transition writes an append-only `mission_events` record and publishes over SSE.

## Localization & Turn-by-Turn Guidance
- Browser geolocation is **never** used as Mars localization.
- When no fresh Mars position packet is available, the UI displays `LIVE MARS LOCALIZATION UNAVAILABLE` and `PROGRESS UNAVAILABLE`.
- Operator-entered coordinates are classified `USER_REPORTED`.
- Deviation checks require both an operator-configured `deviation_threshold_m` and provider-supplied `uncertainty_m`.
- Turn-by-turn instructions (`backend/app/routing/instructions.py`) distinguish Mars True-North bearing from equirectangular Grid-North bearing and report `heading_status: UNAVAILABLE` when no heading sensor is connected.

## Obstructions, Replanning & Independent Return
- Crew obstruction reports are recorded as `USER_REPORTED` / `UNVERIFIED` and never automatically treated as scientifically verified obstacles.
- Candidate replans are computed via `ScienceAwareRoutingService` and stored separately until explicitly approved or rejected by `MISSION_LEAD` or `MISSION_OPERATOR`.
- Return/turnback assessments call `plan_eva_return_route` independently (never `2 × outbound`) and report explicit decision-support states (`WITHIN_CONFIGURED_PLANNING_CONSTRAINTS`, `TURNBACK_REVIEW_REQUIRED`, `RETURN_ROUTE_UNAVAILABLE`, `RESOURCE_BUDGET_INCOMPLETE`, `INSUFFICIENT_LOCALIZATION`, `INSUFFICIENT_TERRAIN_EVIDENCE`, `INDETERMINATE`).
