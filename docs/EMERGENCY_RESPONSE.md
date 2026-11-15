# MARSCOPE Emergency Response & SOS Semantics

## Lifecycle & Delivery Semantics
SOS records (`backend/app/services/sos_service.py`, `backend/app/api/sos.py`) track distinct operational stages:
1. `ACTIVE` — Request accepted and persisted in `sos_events` (with `client_event_id` idempotency).
2. `DELIVERED_TO_CREW_DEVICE` — Recorded only when an authorized client explicitly posts a delivery receipt (`/sos/{sos_id}/delivered`).
3. `ACKNOWLEDGED_BY_CREW` — Recorded when a mission crew member explicitly acknowledges the alert (`/sos/{sos_id}/acknowledge`).
4. `RESOLVED` / `CANCELLED` — Closed by `MISSION_LEAD` or `MISSION_OPERATOR` while preserving permanent audit history.

## Channel Limitations
- Alerts are distributed **only** through the authenticated MARSCOPE application REST/SSE channel.
- No SMS, email, push notification, or satellite provider is configured.
- An offline browser displays `QUEUED_OFFLINE — NOT DELIVERED` and never claims to have contacted remote crew members.

## Controls & Console
- `EmergencySosOverlay.tsx` provides a persistent 56×56px press-and-hold (1.2s) and keyboard-accessible (`Enter`/`Space`) SOS trigger with optional voice-note upload and explicit coordinate entry.
- `/emergency` provides the Emergency Console with status filtering (`ALL`, `ACTIVE`, `CLOSED`), offline queue visibility, crew acknowledgements, operator resolution, and 3D globe focus.
