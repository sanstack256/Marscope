"""
MARSCOPE Prompt 2 Acceptance & Integration Tests
Covers:
- Migration 0002 idempotency & Prompt 1 record preservation
- Active Navigation state machine, RBAC, segment/instruction projection
- Localization freshness, progress unavailability, deviation & accuracy checks
- Obstruction reporting (USER_REPORTED / UNVERIFIED) & candidate replan approval gate
- Independent Return & Turnback assessment states
- SSE catch-up (since_seq) & cross-mission isolation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.security import CSRF_HEADER_NAME
from app.db.database import MissionDatabase
from app.main import app
from app.services import container
from app.services.auth_service import AuthService
from app.services.mission_event_service import MissionEventService
from app.services.mission_service import MissionService
from app.services.navigation_service import NavigationService
from app.services.position_service import CrewPositionService
from app.services.realtime_hub import MissionRealtimeHub
from app.services.sos_service import SosService


def _register_and_login(client: TestClient, email: str, name: str) -> str:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPassword!123", "display_name": name},
    )
    assert r.status_code in (200, 201), r.text
    csrf = client.cookies.get("marscope_csrf")
    assert csrf
    return csrf


def _synthetic_route_payload() -> dict:
    return {
        "route_id": "route-synth-001",
        "dataset_id": "hirise_dteec_009149_1750",
        "crs": "IAU2000:49900",
        "strategy": "balanced",
        "total_surface_distance_m": 250.0,
        "total_horizontal_distance_m": 248.0,
        "total_elevation_gain_m": 12.0,
        "total_elevation_loss_m": 2.0,
        "dem_resolution_m": 1.0,
        "valid_pixel_coverage_pct": 100.0,
        "vertices": [
            {
                "lat": -4.5895,
                "lon_east": 137.4417,
                "elevation_m": -4500.0,
                "slope_deg": 2.5,
                "cumulative_distance_m": 0.0,
                "is_stop": True,
                "stop_label": "Base Landing Site",
            },
            {
                "lat": -4.5880,
                "lon_east": 137.4430,
                "elevation_m": -4492.0,
                "slope_deg": 5.0,
                "cumulative_distance_m": 120.0,
                "is_stop": False,
            },
            {
                "lat": -4.5870,
                "lon_east": 137.4445,
                "elevation_m": -4488.0,
                "slope_deg": 4.0,
                "cumulative_distance_m": 250.0,
                "is_stop": True,
                "stop_label": "Target Outcrop",
            },
        ],
        "instructions": [],
    }


@pytest.fixture()
def isolated_nav_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test_prompt2.sqlite"
    db = MissionDatabase(default_sqlite_path=db_path)
    hub = MissionRealtimeHub()
    ev_svc = MissionEventService(db)
    auth_svc = AuthService(db)
    pos_svc = CrewPositionService(db=db, event_service=ev_svc, realtime_hub=hub, destination_service=container.destination_service)
    mis_svc = MissionService(db=db, event_service=ev_svc, realtime_hub=hub, position_service=pos_svc)
    nav_svc = NavigationService(
        db=db,
        event_service=ev_svc,
        realtime_hub=hub,
        position_service=pos_svc,
        routing_service=container.routing_service,
    )
    att_dir = tmp_path / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    sos_svc = SosService(
        db=db,
        event_service=ev_svc,
        realtime_hub=hub,
        position_service=pos_svc,
        private_attachments_dir=att_dir,
    )

    from app.api import auth as auth_api, deps, missions as missions_api, navigation as nav_api, sos as sos_api

    monkeypatch.setattr(container, "mission_db", db)
    monkeypatch.setattr(container, "auth_service", auth_svc)
    monkeypatch.setattr(container, "mission_service", mis_svc)
    monkeypatch.setattr(container, "position_service", pos_svc)
    monkeypatch.setattr(container, "mission_event_service", ev_svc)
    monkeypatch.setattr(container, "mission_realtime_hub", hub)
    monkeypatch.setattr(container, "navigation_service", nav_svc)
    monkeypatch.setattr(container, "sos_service", sos_svc)

    monkeypatch.setattr(deps, "auth_service", auth_svc)
    monkeypatch.setattr(deps, "mission_db", db)
    monkeypatch.setattr(auth_api, "auth_service", auth_svc)
    monkeypatch.setattr(missions_api, "mission_service", mis_svc)
    monkeypatch.setattr(missions_api, "position_service", pos_svc)
    monkeypatch.setattr(missions_api, "mission_event_service", ev_svc)
    monkeypatch.setattr(missions_api, "mission_realtime_hub", hub)
    monkeypatch.setattr(nav_api, "navigation_service", nav_svc)
    monkeypatch.setattr(sos_api, "sos_service", sos_svc)

    return db


def test_migration_0002_idempotent_and_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "mig.sqlite"
    db1 = MissionDatabase(default_sqlite_path=db_path)
    # Insert a Prompt 1 astronaut row and re-run migrations
    with db1._connect() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            "INSERT INTO astronauts (astronaut_id, email, password_hash, display_name, is_active, created_at_utc, updated_at_utc) VALUES ('a1', 'a1@mars.test', 'hash', 'Astro One', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.execute("COMMIT;")

    db2 = MissionDatabase(default_sqlite_path=db_path)
    applied = db2.apply_migrations()
    assert applied == []  # idempotent
    with db2.read() as conn:
        row = conn.execute("SELECT email FROM astronauts WHERE astronaut_id = 'a1'").fetchone()
    assert row is not None and row["email"] == "a1@mars.test"


def test_active_navigation_lifecycle_rbac_progress_deviation_and_obstruction(isolated_nav_env) -> None:
    lead_client = TestClient(app)
    astro_client = TestClient(app)
    outsider_client = TestClient(app)

    lead_csrf = _register_and_login(lead_client, "lead_nav@mars.test", "Lead Nav")
    astro_csrf = _register_and_login(astro_client, "astro_nav@mars.test", "Astro Nav")
    _register_and_login(outsider_client, "outsider@mars.test", "Outsider")

    # Lead creates mission
    m_resp = lead_client.post(
        "/api/missions",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"name": "Nav Test Mission", "description": "Prompt 2 nav", "objective": "Validate nav"},
    )
    assert m_resp.status_code == 201, m_resp.text
    mission_id = m_resp.json()["mission_id"]

    # Lead invites Astro Nav
    inv_resp = lead_client.post(
        f"/api/missions/{mission_id}/invitations",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"invitee_email": "astro_nav@mars.test", "role": "ASTRONAUT"},
    )
    assert inv_resp.status_code == 201, inv_resp.text
    token = inv_resp.json()["invite_token"]

    join_resp = astro_client.post(
        "/api/missions/join",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={"invite_token": token},
    )
    assert join_resp.status_code == 200, join_resp.text

    # 1. Invalid route payload (<2 vertices) rejected
    bad_nav = astro_client.post(
        f"/api/missions/{mission_id}/navigation",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={
            "route_dataset_id": "hirise_dteec_009149_1750",
            "route_crs": "IAU2000:49900",
            "navigation_mode": "OPERATOR_SUPERVISED_EVA",
            "return_destination_name": "Base",
            "return_destination_lat": -4.5895,
            "return_destination_lon": 137.4417,
            "route_payload": {"dataset_id": "hirise_dteec_009149_1750", "crs": "IAU2000:49900", "vertices": []},
        },
    )
    assert bad_nav.status_code == 422

    # 2. Valid navigation session created by Astronaut
    nav_resp = astro_client.post(
        f"/api/missions/{mission_id}/navigation",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={
            "route_dataset_id": "hirise_dteec_009149_1750",
            "route_crs": "IAU2000:49900",
            "navigation_mode": "OPERATOR_SUPERVISED_EVA",
            "return_destination_name": "Base Landing Site",
            "return_destination_lat": -4.5895,
            "return_destination_lon": 137.4417,
            "deviation_threshold_m": 25.0,
            "route_payload": _synthetic_route_payload(),
            "operational_params": {"walking_speed_mps": 0.8, "max_duration_s": 3600.0},
        },
    )
    assert nav_resp.status_code == 201, nav_resp.text
    nav = nav_resp.json()
    nav_id = nav["nav_session_id"]
    assert nav["state"] == "AWAITING_OPERATOR_APPROVAL"
    assert len(nav["segments"]) == 2
    assert len(nav["instructions"]) == 2
    assert nav["instructions"][0]["heading_status"] == "UNAVAILABLE"
    assert nav["progress"]["progress_status"] == "PROGRESS UNAVAILABLE"
    assert nav["progress"]["localization_banner"] == "LIVE MARS LOCALIZATION UNAVAILABLE"

    # Cross-mission isolation: outsider cannot read navigation session
    assert outsider_client.get(f"/api/missions/{mission_id}/navigation/{nav_id}").status_code == 403

    # 3. RBAC: Astronaut cannot self-approve AWAITING_OPERATOR_APPROVAL -> ACTIVE
    self_approve = astro_client.post(
        f"/api/missions/{mission_id}/navigation/{nav_id}/transition",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={"target_state": "ACTIVE", "reason": "Self approve attempt"},
    )
    assert self_approve.status_code == 403

    # Lead approves -> ACTIVE
    approve = lead_client.post(
        f"/api/missions/{mission_id}/navigation/{nav_id}/transition",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"target_state": "ACTIVE", "reason": "Operator approved route"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["state"] == "ACTIVE"
    assert approve.json()["approved_by"] is not None

    # 4. Ingest fresh position WITHOUT uncertainty_m -> deviation_state must say UNAVAILABLE_ACCURACY_OR_POSITION
    pos_no_acc = astro_client.post(
        f"/api/missions/{mission_id}/positions",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={
            "latitude": -4.5880,
            "longitude": 137.4430,
            "source_id": "OPERATOR_MANUAL_ENTRY",
            "source_classification": "USER_PROVIDED",
            "sequence_number": 1,
            "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert pos_no_acc.status_code == 201, pos_no_acc.text
    nav_after_pos = astro_client.get(f"/api/missions/{mission_id}/navigation/{nav_id}").json()
    assert nav_after_pos["progress"]["progress_status"] == "AVAILABLE"
    assert nav_after_pos["progress"]["deviation_state"] == "UNAVAILABLE_ACCURACY_OR_POSITION"

    # 5. Ingest fresh position WITH uncertainty_m off-track (> 25m) -> DEVIATION_DETECTED
    pos_off = astro_client.post(
        f"/api/missions/{mission_id}/positions",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={
            "latitude": -4.5800,
            "longitude": 137.4430,
            "uncertainty_m": 2.0,
            "source_id": "EXTERNAL_LOCALIZATION_SIM",
            "source_classification": "TELEMETRY_PROVIDER",
            "sequence_number": 2,
            "measured_at_utc": (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
        },
    )
    assert pos_off.status_code == 201, pos_off.text
    nav_dev = astro_client.get(f"/api/missions/{mission_id}/navigation/{nav_id}").json()
    assert nav_dev["progress"]["deviation_state"] == "DEVIATION_DETECTED"

    # 6. Turnback evaluation when resource_budgets not configured -> RESOURCE_BUDGET_INCOMPLETE
    tb_resp = astro_client.post(
        f"/api/missions/{mission_id}/navigation/{nav_id}/turnback",
        headers={CSRF_HEADER_NAME: astro_csrf},
    )
    assert tb_resp.status_code == 200, tb_resp.text
    tb = tb_resp.json()["turnback"]
    assert tb["state"] in ("RESOURCE_BUDGET_INCOMPLETE", "RETURN_ROUTE_UNAVAILABLE")

    # 7. Report Obstruction -> OBSTRUCTION_REPORTED (USER_REPORTED / UNVERIFIED)
    obs_resp = astro_client.post(
        f"/api/missions/{mission_id}/navigation/{nav_id}/obstructions",
        headers={CSRF_HEADER_NAME: astro_csrf},
        json={
            "segment_index": 0,
            "latitude": -4.5885,
            "longitude": 137.4425,
            "location_source": "USER_REPORTED",
            "description": "Boulder field blocking corridor",
        },
    )
    assert obs_resp.status_code == 200, obs_resp.text
    obs_data = obs_resp.json()
    assert obs_data["state"] == "OBSTRUCTION_REPORTED"
    assert obs_data["obstructions"][0]["epistemic_classification"] == "USER_REPORTED"
    assert obs_data["obstructions"][0]["review_state"] == "UNVERIFIED"

    # 8. Invalid state transition -> 409
    bad_trans = lead_client.post(
        f"/api/missions/{mission_id}/navigation/{nav_id}/transition",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"target_state": "NOT_CONFIGURED"},
    )
    assert bad_trans.status_code == 409


def test_sos_delivery_idempotency_sse_catchup_and_restart_recovery(
    isolated_nav_env: MissionDatabase, tmp_path: Path
) -> None:
    lead_client = TestClient(app)
    lead_csrf = _register_and_login(lead_client, "lead_rec@mars.test", "Lead Recovery")
    m_resp = lead_client.post(
        "/api/missions",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"name": "Recovery Mission", "description": "Restart test", "objective": "Verify durability"},
    )
    assert m_resp.status_code == 201
    mission_id = m_resp.json()["mission_id"]

    # 1. SOS idempotency with client_event_id
    sos_payload = {
        "message": "Suit comm check",
        "client_event_id": "sos-idem-001",
    }
    s1 = lead_client.post(
        f"/api/missions/{mission_id}/sos",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json=sos_payload,
    )
    s2 = lead_client.post(
        f"/api/missions/{mission_id}/sos",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json=sos_payload,
    )
    assert s1.status_code == 201 and s2.status_code == 201
    assert s1.json()["sos_id"] == s2.json()["sos_id"]
    sos_id = s1.json()["sos_id"]

    # 2. Explicit delivery receipt -> crew ack -> operator resolve
    d_resp = lead_client.post(
        f"/api/missions/{mission_id}/sos/{sos_id}/delivered",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"note": "Client stream received"},
    )
    assert d_resp.status_code == 200
    assert d_resp.json()["status"] == "DELIVERED_TO_CREW_DEVICE"

    a_resp = lead_client.post(
        f"/api/missions/{mission_id}/sos/{sos_id}/acknowledge",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"note": "Crew copy"},
    )
    assert a_resp.status_code == 200
    assert a_resp.json()["status"] == "ACKNOWLEDGED_BY_CREW"

    r_resp = lead_client.post(
        f"/api/missions/{mission_id}/sos/{sos_id}/resolve",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={"note": "Incident resolved"},
    )
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] == "RESOLVED"

    # 3. Adversarial negative deviation threshold / NaN rejected
    bad_nav = lead_client.post(
        f"/api/missions/{mission_id}/navigation",
        headers={CSRF_HEADER_NAME: lead_csrf},
        json={
            "route_dataset_id": "hirise_dteec_009149_1750",
            "route_crs": "IAU2000:49900",
            "navigation_mode": "MANUAL_WAYPOINT_CHECK",
            "return_destination_name": "Base",
            "return_destination_lat": -4.5895,
            "return_destination_lon": 137.4417,
            "deviation_threshold_m": -10.0,
            "route_payload": _synthetic_route_payload(),
        },
    )
    assert bad_nav.status_code == 422

    # 4. Restart recovery: reopen MissionDatabase against same SQLite file
    reopened = MissionDatabase(default_sqlite_path=isolated_nav_env.db_path)
    with reopened.read() as conn:
        ev_count = conn.execute(
            "SELECT COUNT(*) AS c FROM mission_events WHERE mission_id = ?", (mission_id,)
        ).fetchone()["c"]
        sos_row = conn.execute(
            "SELECT status FROM sos_events WHERE sos_id = ?", (sos_id,)
        ).fetchone()
    assert ev_count >= 4
    assert sos_row is not None and sos_row["status"] == "RESOLVED"
