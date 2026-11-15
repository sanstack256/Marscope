# MARSCOPE EVA Operations Workstation

## Overview
`/eva-operations` integrates `EvaOperationsService` (`backend/app/eva_operations/mission.py`) with mission crew profiles, computed routes, and recorded mission events.

## Locomotion Models
1. `USER_CONFIGURED_CONSTANT_SPEED` — Uses explicit `USER_ASSUMED` walking speed.
2. `TERRESTRIAL_HIKING_APPROXIMATION` — Uses Tobler grade approximation with explicit disclosure that it is **not** a validated Mars spacesuit locomotion model.
3. `MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL` — Explicitly `UNAVAILABLE` until a validated Mars spacesuit model and parameters are supplied.

## Energy & Resource Accounting
- Mechanical climb work (`m * g_mars * Δh`) is kept strictly separate from human metabolic energy and suit electrical/consumable expenditure.
- Configured resources are evaluated with dimensional analysis (`Q_used = Q_dot * elapsed_time`). Unconfigured resource categories remain `NOT CONFIGURED` (never 0 consumption).
- When no live telemetry adapter is connected, the UI displays `LIVE RESOURCE TELEMETRY NOT CONNECTED`.

## Mission Timeline
Displays `[PLANNED]` route schedule steps alongside `[RECORDED #seq]` server-timestamped `mission_events` without conflating planned durations with observed elapsed time.
