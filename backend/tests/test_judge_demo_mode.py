"""
Tests for Judge Demonstration Mode:
- Idempotent demo bootstrap (3 demo astronauts, 1 demo mission, 1 Alpha SOS, 2 observations)
- Demo credentials config & login
- Strict backend isolation between demo and production accounts/missions
- SOS acknowledge/resolve + demo-only reset preserving production data
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services import container
from app.services.demo_service import (
    DEMO_ALPHA_ID,
    DEMO_BRAVO_ID,
    DEMO_CMD_ID,
    DEMO_MISSION_ID,
    DEMO_OBS_ALPHA_ID,
    DEMO_OBS_BRAVO_ID,
    DEMO_SOS_ALPHA_ID,
)


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("marscope_csrf", "")
    return {"X-CSRF-Token": token} if token else {}


@pytest.fixture()
def demo_test_client(tmp_path, monkeypatch):
    db_path = tmp_path / "demo_test.sqlite"
    from app.db.database import MissionDatabase
    from app.services.auth_service import AuthService
    from app.services.demo_service import DemoService
    from app.services.field_observation_service import FieldObservationService
    from app.services.mission_event_service import MissionEventService
    from app.services.mission_service import MissionService
    from app.services.position_service import CrewPositionService
    from app.services.realtime_hub import MissionRealtimeHub
    from app.services.sos_service import SosService

    test_db = MissionDatabase(database_url=f"sqlite:///{db_path}")
    hub = MissionRealtimeHub()
    events = MissionEventService(db=test_db)
    positions = CrewPositionService(
        db=test_db,
        event_service=events,
        realtime_hub=hub,
        destination_service=container.destination_service,
    )
    auth = AuthService(db=test_db)
    missions = MissionService(db=test_db, event_service=events, realtime_hub=hub, position_service=positions)
    sos = SosService(
        db=test_db,
        event_service=events,
        realtime_hub=hub,
        position_service=positions,
        private_attachments_dir=tmp_path / "priv",
    )
    obs = FieldObservationService(
        db=test_db,
        event_service=events,
        realtime_hub=hub,
        destination_service=container.destination_service,
    )
    demo = DemoService(
        db=test_db,
        event_service=events,
        credentials_file=tmp_path / ".demo_credentials.json",
        processed_dir=container.PROCESSED_DIR,
    )

    monkeypatch.setattr(container, "mission_db", test_db)
    monkeypatch.setattr(container, "auth_service", auth)
    monkeypatch.setattr(container, "mission_service", missions)
    monkeypatch.setattr(container, "sos_service", sos)
    monkeypatch.setattr(container, "field_observation_service", obs)
    monkeypatch.setattr(container, "demo_service", demo)
    monkeypatch.setattr(container, "mission_event_service", events)
    monkeypatch.setattr(container, "position_service", positions)

    import app.api.deps as deps_mod
    import app.api.auth as auth_api
    import app.api.demo as demo_api
    import app.api.missions as missions_api
    import app.api.sos as sos_api
    import app.api.field_observations as obs_api

    monkeypatch.setattr(deps_mod, "mission_db", test_db)
    monkeypatch.setattr(deps_mod, "auth_service", auth)
    monkeypatch.setattr(auth_api, "auth_service", auth)
    monkeypatch.setattr(demo_api, "demo_service", demo)
    monkeypatch.setattr(missions_api, "mission_service", missions)
    monkeypatch.setattr(missions_api, "mission_event_service", events)
    monkeypatch.setattr(missions_api, "position_service", positions)
    monkeypatch.setattr(sos_api, "sos_service", sos)
    monkeypatch.setattr(obs_api, "field_observation_service", obs)

    demo.ensure_seeded()
    return TestClient(app), demo, test_db


def test_demo_bootstrap_idempotency_and_seed_contents(demo_test_client) -> None:
    client, demo, db = demo_test_client

    # Re-run ensure_seeded multiple times to prove idempotency
    demo.ensure_seeded()
    demo.ensure_seeded()

    with db.read() as conn:
        demo_astros = conn.execute("SELECT astronaut_id, display_name FROM astronauts WHERE is_demo = 1").fetchall()
        demo_missions = conn.execute("SELECT mission_id, name FROM missions WHERE is_demo = 1").fetchall()
        sos_rows = conn.execute("SELECT sos_id, astronaut_id, status FROM sos_events WHERE mission_id = ?", (DEMO_MISSION_ID,)).fetchall()
        obs_rows = conn.execute("SELECT observation_id, astronaut_id, epistemic_state, crs FROM field_observations WHERE mission_id = ?", (DEMO_MISSION_ID,)).fetchall()

    assert {r["astronaut_id"] for r in demo_astros} == {DEMO_CMD_ID, DEMO_ALPHA_ID, DEMO_BRAVO_ID}
    assert len(demo_missions) == 1
    assert demo_missions[0]["mission_id"] == DEMO_MISSION_ID
    assert len(sos_rows) == 1
    assert sos_rows[0]["sos_id"] == DEMO_SOS_ALPHA_ID
    assert sos_rows[0]["astronaut_id"] == DEMO_ALPHA_ID
    assert sos_rows[0]["status"] == "ACTIVE"

    assert {r["observation_id"] for r in obs_rows} == {DEMO_OBS_ALPHA_ID, DEMO_OBS_BRAVO_ID}
    assert {r["astronaut_id"] for r in obs_rows} == {DEMO_ALPHA_ID, DEMO_BRAVO_ID}
    assert all(r["epistemic_state"] == "USER_REPORTED" and r["crs"] == "IAU2000:49900" for r in obs_rows)

    cfg = client.get("/api/demo/config")
    assert cfg.status_code == 200
    cfg_json = cfg.json()
    assert cfg_json["enabled"] is True
    assert cfg_json["demo_mission_id"] == DEMO_MISSION_ID
    assert cfg_json["account_label"] == "DEMO"
    assert cfg_json["email"]
    assert cfg_json["password"]


def test_demo_and_production_strict_isolation_and_reset(demo_test_client) -> None:
    demo_client, _, _ = demo_test_client
    cfg = demo_client.get("/api/demo/config").json()

    # 1. Sign in as Demo Commander
    login_res = demo_client.post(
        "/api/auth/login",
        json={"email": cfg["email"], "password": cfg["password"]},
    )
    assert login_res.status_code == 200
    assert login_res.json()["astronaut"]["is_demo"] is True

    # Demo sees ONLY the demo mission
    m_list = demo_client.get("/api/missions").json()
    assert [m["mission_id"] for m in m_list] == [DEMO_MISSION_ID]
    assert m_list[0]["is_demo"] is True

    # Demo cannot create production missions
    bad_create = demo_client.post(
        "/api/missions",
        headers=_csrf(demo_client),
        json={"name": "Unauthorized Prod Mission", "objective": "Should fail"},
    )
    assert bad_create.status_code == 403

    # 2. Register a real production astronaut
    prod_client = TestClient(app)
    reg_res = prod_client.post(
        "/api/auth/register",
        json={"email": "real.astro@mars.org", "password": "RealStrongPassword!2026", "display_name": "Real Astro"},
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["astronaut"]["is_demo"] is False

    # Create a real production mission
    prod_m = prod_client.post(
        "/api/missions",
        headers=_csrf(prod_client),
        json={"name": "Real Olympus Survey", "objective": "Production mission"},
    )
    assert prod_m.status_code == 201
    prod_mission_id = prod_m.json()["mission_id"]
    assert prod_m.json()["is_demo"] is False

    # Production user never sees demo mission and gets 403 accessing it
    assert all(m["mission_id"] != DEMO_MISSION_ID for m in prod_client.get("/api/missions").json())
    assert prod_client.get(f"/api/missions/{DEMO_MISSION_ID}").status_code == 403
    assert prod_client.post("/api/demo/reset", headers=_csrf(prod_client)).status_code == 403

    # Demo user never sees production mission and gets 403 accessing it
    assert all(m["mission_id"] != prod_mission_id for m in demo_client.get("/api/missions").json())
    assert demo_client.get(f"/api/missions/{prod_mission_id}").status_code == 403

    # 3. Demo user acknowledges & resolves Alpha's SOS, then resets demo mission
    ack = demo_client.post(
        f"/api/missions/{DEMO_MISSION_ID}/sos/{DEMO_SOS_ALPHA_ID}/acknowledge",
        headers=_csrf(demo_client),
        json={"ack_type": "ACKNOWLEDGED_BY_CREW", "note": "Demo Commander responding"},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "ACKNOWLEDGED_BY_CREW"

    res_sos = demo_client.post(
        f"/api/missions/{DEMO_MISSION_ID}/sos/{DEMO_SOS_ALPHA_ID}/resolve",
        headers=_csrf(demo_client),
        json={"note": "Demo SOS resolved"},
    )
    assert res_sos.status_code == 200, res_sos.text
    assert res_sos.json()["status"] == "RESOLVED"

    # Reset restores ACTIVE SOS while preserving production mission
    reset_res = demo_client.post("/api/demo/reset", headers=_csrf(demo_client))
    assert reset_res.status_code == 200
    assert reset_res.json()["reset"] is True

    sos_after = demo_client.get(f"/api/missions/{DEMO_MISSION_ID}/sos").json()
    assert len(sos_after) == 1
    assert sos_after[0]["status"] == "ACTIVE"

    # Production mission is completely untouched
    assert prod_client.get(f"/api/missions/{prod_mission_id}").status_code == 200
