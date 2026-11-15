"""
Prompt 1 Mission Foundation Backend Integration & Adversarial Verification Suite.
Covers database migrations & restart persistence, scrypt auth, HttpOnly+CSRF enforcement,
rate limiting, password reset, astronaut USER_ASSUMED profile fields (never silent defaults),
missions & CSPRNG invitations, RBAC & cross-mission isolation, Mars IAU2000:49900 positions,
per-mission SSE isolation, SOS + private voice notes + acknowledgements, field observations
(vocabulary + optimistic concurrency + review), landing-site registration + gazetteer +
DEM-backed 3D perimeter computation, and append-only mission_events.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict
import uuid

from fastapi.testclient import TestClient
import pytest

from app.core.security import rate_limiter, verify_signed_attachment_token
from app.db.database import DatabaseConfigurationError, MissionDatabase
from app.main import app
from app.services import container as svc_container


def _csrf_headers(client: TestClient) -> Dict[str, str]:
    token = client.cookies.get("marscope_csrf")
    return {"X-CSRF-Token": token} if token else {}


@pytest.fixture()
def isolated_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Wire a clean temporary SQLite database and private_attachments folder into
    the container singletons and rebind service references cleanly for each test.
    """
    rate_limiter.reset()
    db_path = tmp_path / "test_missions.db"
    att_dir = tmp_path / "private_attachments"
    att_dir.mkdir(parents=True, exist_ok=True)

    fresh_db = MissionDatabase(default_sqlite_path=db_path)
    monkeypatch.setattr(svc_container, "mission_db", fresh_db)
    monkeypatch.setattr("app.api.deps.mission_db", fresh_db)
    monkeypatch.setattr(svc_container.mission_event_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.auth_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.position_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.mission_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.sos_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.sos_service, "_attachments_dir", att_dir)
    monkeypatch.setattr(svc_container.field_observation_service, "_db", fresh_db)
    monkeypatch.setattr(svc_container.landing_site_service, "_db", fresh_db)

    from app.core.config import settings

    monkeypatch.setattr(settings, "ALLOW_TEST_PASSWORD_RESET_TOKEN_PREVIEW", True)

    return TestClient(app), db_path, att_dir


def test_database_config_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    with pytest.raises(DatabaseConfigurationError):
        MissionDatabase(database_url="postgres://user:pw@localhost/db")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(DatabaseConfigurationError):
        MissionDatabase(database_url=None)


def test_auth_csrf_password_reset_rate_limit_and_profile_assumptions(isolated_client) -> None:
    client, db_path, _ = isolated_client

    # Register Lead astronaut
    r = client.post(
        "/api/auth/register",
        json={
            "email": "Commander.Vega@marscope.test",
            "password": "MarsStrongPassword2026!",
            "display_name": "Commander Vega",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["authenticated"] is True
    assert data["astronaut"]["email"] == "commander.vega@marscope.test"
    # Verify NO silent 75/55/10 defaults on new astronaut profile
    assert data["astronaut"]["body_mass_kg"] is None
    assert data["astronaut"]["suit_mass_kg"] is None
    assert data["astronaut"]["equipment_mass_kg"] is None
    assert data["astronaut"]["body_mass_meta"]["classification"] == "NOT_PROVIDED"

    # Mutating without CSRF header must fail 403
    no_csrf = client.put(
        "/api/auth/profile",
        json={"body_mass_kg": 72.5, "suit_mass_kg": 58.0, "equipment_mass_kg": 11.2},
    )
    assert no_csrf.status_code == 403

    # Mutating WITH CSRF succeeds and labels USER_ASSUMED
    ok_prof = client.put(
        "/api/auth/profile",
        headers=_csrf_headers(client),
        json={"body_mass_kg": 72.5, "suit_mass_kg": 58.0, "equipment_mass_kg": 11.2},
    )
    assert ok_prof.status_code == 200
    prof = ok_prof.json()
    assert prof["body_mass_kg"] == 72.5
    assert prof["body_mass_meta"]["classification"] == "USER_ASSUMED"
    assert prof["total_mass_kg"] == 141.7
    assert len(prof["profile_edit_history"]) == 1

    # Duplicate email returns 409
    dup = client.post(
        "/api/auth/register",
        json={
            "email": "commander.vega@marscope.test",
            "password": "AnotherPassword2026!",
            "display_name": "Duplicate",
        },
    )
    assert dup.status_code == 409

    # Password reset flow revokes existing sessions
    reset_req = client.post("/api/auth/password-reset/request", json={"email": "commander.vega@marscope.test"})
    assert reset_req.status_code == 200
    reset_token = reset_req.json()["reset_token_preview"]
    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "UpdatedMarsPassword99!"},
    )
    assert confirm.status_code == 200

    # Previous session must now be unauthorized
    sess_after = client.get("/api/auth/session")
    assert sess_after.json()["authenticated"] is False

    # Re-opening DB directly verifies migration & data persistence on disk
    reloaded = MissionDatabase(default_sqlite_path=db_path)
    assert reloaded.status()["available"] is True
    with reloaded.read() as conn:
        row = conn.execute("SELECT body_mass_kg FROM astronauts WHERE email = ?", ("commander.vega@marscope.test",)).fetchone()
        assert row["body_mass_kg"] == 72.5

    # Brute-force login rate limit check
    rate_limiter.reset()
    for _ in range(20):
        client.post(
            "/api/auth/login",
            json={"email": "commander.vega@marscope.test", "password": "WrongPassword123!"},
        )
    throttled = client.post(
        "/api/auth/login",
        json={"email": "commander.vega@marscope.test", "password": "WrongPassword123!"},
    )
    assert throttled.status_code == 429


def test_missions_invitations_rbac_and_cross_mission_isolation(isolated_client) -> None:
    lead_c, _, _ = isolated_client
    lead_c.post(
        "/api/auth/register",
        json={"email": "lead@mars.test", "password": "StrongPassword123!", "display_name": "Lead"},
    )

    mate_c = TestClient(app)
    mate_c.post(
        "/api/auth/register",
        json={"email": "mate@mars.test", "password": "StrongPassword123!", "display_name": "Mate"},
    )

    outsider_c = TestClient(app)
    outsider_c.post(
        "/api/auth/register",
        json={"email": "outsider@mars.test", "password": "StrongPassword123!", "display_name": "Outsider"},
    )

    # Create Mission A
    m_res = lead_c.post(
        "/api/missions",
        headers=_csrf_headers(lead_c),
        json={"name": "Ares Boxwork Traverse", "objective": "Evaluate phyllosilicate ridge"},
    )
    assert m_res.status_code == 201
    mission_a = m_res.json()
    assert mission_a["landing_site_status"] == "LANDING_SITE_UNCONFIGURED"
    assert mission_a["my_role"] == "MISSION_LEAD"

    # Sole MISSION_LEAD cannot abandon mission
    bad_leave = lead_c.post(f"/api/missions/{mission_a['mission_id']}/leave", headers=_csrf_headers(lead_c))
    assert bad_leave.status_code == 409

    # Create single-use invitation
    inv_res = lead_c.post(
        f"/api/missions/{mission_a['mission_id']}/invitations",
        headers=_csrf_headers(lead_c),
        json={"role_on_join": "ASTRONAUT", "single_use": True, "expires_in_hours": 12},
    )
    assert inv_res.status_code == 201
    invite_token = inv_res.json()["invite_token"]
    invite_id = inv_res.json()["invite_id"]

    # Mate joins Mission A
    join_res = mate_c.post(
        "/api/missions/join",
        headers=_csrf_headers(mate_c),
        json={"invite_token": invite_token},
    )
    assert join_res.status_code == 200
    assert join_res.json()["my_role"] == "ASTRONAUT"

    # Single-use invite exhausted for Outsider
    exhausted = outsider_c.post(
        "/api/missions/join",
        headers=_csrf_headers(outsider_c),
        json={"invite_token": invite_token},
    )
    assert exhausted.status_code == 410

    # Outsider cannot read crew, SOS, observations, positions, landing site, or events of Mission A
    for path in ("", "/crew", "/positions", "/sos", "/observations", "/landing-site", "/events"):
        deny = outsider_c.get(f"/api/missions/{mission_a['mission_id']}{path}")
        assert deny.status_code == 403, f"Expected 403 for outsider on {path}, got {deny.status_code}"

    # Mate (ASTRONAUT) cannot create invitations (LEAD/OPERATOR only)
    mate_inv = mate_c.post(
        f"/api/missions/{mission_a['mission_id']}/invitations",
        headers=_csrf_headers(mate_c),
        json={"role_on_join": "ASTRONAUT"},
    )
    assert mate_inv.status_code == 403

    # Lead creates revocable invite and revokes it
    inv2 = lead_c.post(
        f"/api/missions/{mission_a['mission_id']}/invitations",
        headers=_csrf_headers(lead_c),
        json={"role_on_join": "ASTRONAUT"},
    ).json()
    rev = lead_c.post(
        f"/api/missions/{mission_a['mission_id']}/invitations/{inv2['invite_id']}/revoke",
        headers=_csrf_headers(lead_c),
    )
    assert rev.status_code == 200
    _ = invite_id


def test_positions_dem_elevation_stale_rejection_and_realtime_isolation(isolated_client) -> None:
    lead_c, _, _ = isolated_client
    lead_c.post(
        "/api/auth/register",
        json={"email": "poslead@mars.test", "password": "StrongPassword123!", "display_name": "Pos Lead"},
    )
    m1 = lead_c.post("/api/missions", headers=_csrf_headers(lead_c), json={"name": "Mission One"}).json()
    m2 = lead_c.post("/api/missions", headers=_csrf_headers(lead_c), json={"name": "Mission Two"}).json()

    # Reject browser geolocation provider & Earth CRS
    bad_geo = lead_c.post(
        f"/api/missions/{m1['mission_id']}/positions",
        headers=_csrf_headers(lead_c),
        json={
            "latitude": -4.73,
            "longitude": 137.41,
            "crs": "IAU2000:49900",
            "source_id": "navigator.geolocation",
            "source_classification": "USER_PROVIDED",
        },
    )
    assert bad_geo.status_code == 422

    bad_crs = lead_c.post(
        f"/api/missions/{m1['mission_id']}/positions",
        headers=_csrf_headers(lead_c),
        json={
            "latitude": -4.73,
            "longitude": 137.41,
            "crs": "EPSG:4326",
            "source_id": "suit_nav_imu_1",
            "source_classification": "LOCALIZATION_SOLVER",
        },
    )
    assert bad_crs.status_code == 422

    # Valid position inside Gale HiRISE DEM yields real elevation_m
    now = datetime.now(timezone.utc)
    p_ok = lead_c.post(
        f"/api/missions/{m1['mission_id']}/positions",
        headers=_csrf_headers(lead_c),
        json={
            "latitude": -4.73,
            "longitude": 137.41,
            "crs": "IAU2000:49900",
            "source_id": "suit_nav_imu_1",
            "source_classification": "LOCALIZATION_SOLVER",
            "sequence_number": 5,
            "measured_at_utc": now.isoformat(),
        },
    )
    assert p_ok.status_code == 201, p_ok.text
    pos = p_ok.json()
    assert pos["elevation_m"] is not None
    assert pos["elevation_source"] is not None

    # Out-of-order older timestamp rejected 409
    older = (now - timedelta(seconds=30)).isoformat()
    p_old = lead_c.post(
        f"/api/missions/{m1['mission_id']}/positions",
        headers=_csrf_headers(lead_c),
        json={
            "latitude": -4.731,
            "longitude": 137.411,
            "crs": "IAU2000:49900",
            "source_id": "suit_nav_imu_1",
            "source_classification": "LOCALIZATION_SOLVER",
            "sequence_number": 6,
            "measured_at_utc": older,
        },
    )
    assert p_old.status_code == 409

    # Realtime hub isolation: publish to Mission 1 does NOT deliver to Mission 2 subscriber
    async def _check_hub():
        sub2 = svc_container.mission_realtime_hub.subscribe(m2["mission_id"], "lead")
        svc_container.mission_realtime_hub.publish_mission_event(
            m1["mission_id"], event_type="CREW_POSITION_UPDATED", payload={"test": 1}
        )
        assert sub2.queue.empty()
        svc_container.mission_realtime_hub.unsubscribe(sub2)

    asyncio.run(_check_hub())


def test_sos_voice_note_privacy_ack_observations_and_dem_perimeter(isolated_client) -> None:
    lead_c, _, att_dir = isolated_client
    lead_r = lead_c.post(
        "/api/auth/register",
        json={"email": "opslead@mars.test", "password": "StrongPassword123!", "display_name": "Ops Lead"},
    ).json()
    lead_id = lead_r["astronaut"]["astronaut_id"]

    mate_c = TestClient(app)
    mate_c.post(
        "/api/auth/register",
        json={"email": "opsmate@mars.test", "password": "StrongPassword123!", "display_name": "Ops Mate"},
    )
    outsider_c = TestClient(app)
    outsider_c.post(
        "/api/auth/register",
        json={"email": "outsider2@mars.test", "password": "StrongPassword123!", "display_name": "Outsider2"},
    )

    m = lead_c.post("/api/missions", headers=_csrf_headers(lead_c), json={"name": "Mount Sharp EVA"}).json()
    mid = m["mission_id"]
    inv = lead_c.post(
        f"/api/missions/{mid}/invitations", headers=_csrf_headers(lead_c), json={"role_on_join": "ASTRONAUT"}
    ).json()
    mate_c.post("/api/missions/join", headers=_csrf_headers(mate_c), json={"invite_token": inv["invite_token"]})

    # Upload private audio voice note
    vn_res = mate_c.post(
        f"/api/missions/{mid}/voice-notes?duration_seconds=4.2",
        headers={**_csrf_headers(mate_c), "Content-Type": "audio/webm"},
        content=b"WEBM_SYNTHETIC_AUDIO_FRAME_BYTES",
    )
    assert vn_res.status_code == 201, vn_res.text
    vn = vn_res.json()
    assert (att_dir / mid).exists()

    # Outsider cannot fetch voice note even with URL
    assert outsider_c.get(vn["playback_url"]).status_code == 403
    # Mate's personal signed token cannot be replayed by another astronaut
    assert lead_c.get(vn["playback_url"]).status_code == 403
    # Active crew member can play voice note directly via mission-authorized endpoint & own signed URL
    play_ok = lead_c.get(f"/api/missions/{mid}/voice-notes/{vn['voice_note_id']}")
    assert play_ok.status_code == 200
    assert play_ok.content == b"WEBM_SYNTHETIC_AUDIO_FRAME_BYTES"
    assert mate_c.get(vn["playback_url"]).status_code == 200

    # Tampered signed token rejected
    assert verify_signed_attachment_token("9999999999.bad", voice_note_id=vn["voice_note_id"], mission_id=mid, astronaut_id=lead_id) is False

    # Trigger SOS without location -> must report POSITION_UNAVAILABLE honestly & idempotent deduplication
    client_eid = str(uuid.uuid4())
    sos1 = mate_c.post(
        f"/api/missions/{mid}/sos",
        headers=_csrf_headers(mate_c),
        json={"message": "Boot seal tear near gully", "voice_note_id": vn["voice_note_id"], "client_event_id": client_eid},
    )
    assert sos1.status_code == 201
    sos_id = sos1.json()["sos_id"]
    assert sos1.json()["position_status"] == "POSITION_UNAVAILABLE"

    sos_dup = mate_c.post(
        f"/api/missions/{mid}/sos",
        headers=_csrf_headers(mate_c),
        json={"message": "Boot seal tear near gully", "client_event_id": client_eid},
    )
    assert sos_dup.json()["sos_id"] == sos_id

    # Lead acknowledges & resolves SOS
    ack = lead_c.post(
        f"/api/missions/{mid}/sos/{sos_id}/acknowledge",
        headers=_csrf_headers(lead_c),
        json={"note": "Inbound rover rescue"},
    )
    assert ack.json()["status"] == "ACKNOWLEDGED_BY_CREW"
    res = lead_c.post(f"/api/missions/{mid}/sos/{sos_id}/resolve", headers=_csrf_headers(lead_c), json={})
    assert res.json()["status"] == "RESOLVED"

    # Field observations: species resolution + concurrency conflict 409 + review
    bad_sp = mate_c.post(
        f"/api/missions/{mid}/observations",
        headers=_csrf_headers(mate_c),
        json={"category": "MINERAL_DISCOVERY", "species_name": "Kryptonite", "description": "Fake mineral"},
    )
    assert bad_sp.status_code == 422

    obs_res = mate_c.post(
        f"/api/missions/{mid}/observations",
        headers=_csrf_headers(mate_c),
        json={
            "latitude": -4.73,
            "longitude": 137.41,
            "category": "MINERAL_DISCOVERY",
            "species_name": "hematite",
            "description": "Layered hematite concretions observed on bench.",
            "evidence_ids": ["CRISM_FRT0000B6F1"],
        },
    )
    assert obs_res.status_code == 201
    obs = obs_res.json()
    assert obs["epistemic_state"] == "USER_REPORTED"
    assert obs["species_canonical_id"] == "hematite"

    # Stale expected_version fails 409
    upd_ok = mate_c.patch(
        f"/api/missions/{mid}/observations/{obs['observation_id']}",
        headers=_csrf_headers(mate_c),
        json={"expected_version": 1, "annotation_note": "Photographed from 2m"},
    )
    assert upd_ok.status_code == 200
    assert upd_ok.json()["version"] == 2

    upd_conflict = mate_c.patch(
        f"/api/missions/{mid}/observations/{obs['observation_id']}",
        headers=_csrf_headers(mate_c),
        json={"expected_version": 1, "annotation_note": "Stale edit"},
    )
    assert upd_conflict.status_code == 409

    rev_ok = lead_c.post(
        f"/api/missions/{mid}/observations/{obs['observation_id']}/review",
        headers=_csrf_headers(lead_c),
        json={"expected_version": 2, "epistemic_state": "CORROBORATED_BY_EVIDENCE", "review_note": "Confirmed by CRISM"},
    )
    assert rev_ok.status_code == 200
    assert rev_ok.json()["epistemic_state"] == "CORROBORATED_BY_EVIDENCE"

    # Landing site gazetteer + missing constraints + outside DEM + real DEM perimeter
    gaz = lead_c.get("/api/missions/gazetteer/search?q=Gale").json()
    assert len(gaz) >= 1

    # Register inside Gale DEM
    ls_ok = lead_c.put(
        f"/api/missions/{mid}/landing-site",
        headers=_csrf_headers(lead_c),
        json={"name": "Boxwork Landing Pad", "latitude": -4.73, "longitude": 137.41, "source": "USER_PROVIDED"},
    ).json()
    assert ls_ok["landing_site_status"] == "REGISTERED"
    assert ls_ok["landing_site"]["dem_coverage_state"] == "COVERED_DEM"

    # Missing constraints -> INDETERMINATE_MISSING_CONSTRAINTS (never fake radius)
    miss_p = lead_c.post(
        f"/api/missions/{mid}/landing-site/perimeter",
        headers=_csrf_headers(lead_c),
        json={"max_slope_deg": 15.0},
    ).json()
    assert miss_p["perimeter"]["status"] == "INDETERMINATE_MISSING_CONSTRAINTS"
    assert miss_p["perimeter"]["geometry_geojson"] is None

    # Valid DEM BFS perimeter
    dem_p = lead_c.post(
        f"/api/missions/{mid}/landing-site/perimeter",
        headers=_csrf_headers(lead_c),
        json={"max_slope_deg": 20.0, "max_roughness_m": 2.5, "max_radius_m": 120.0},
    ).json()
    assert dem_p["perimeter"]["status"] == "EVALUATED_WITH_VALIDATED_DEM"
    assert "NOT A CERTIFIED SAFETY LIMIT" in dem_p["perimeter"]["classification_label"]
    assert dem_p["perimeter"]["geometry_geojson"] is not None

    # Operator approval
    app_p = lead_c.post(
        f"/api/missions/{mid}/landing-site/perimeter/{dem_p['perimeter']['perimeter_id']}/approve",
        headers=_csrf_headers(lead_c),
    ).json()
    assert app_p["perimeter"]["operator_approved"] is True

    # Register site strictly outside processed DEM -> INDETERMINATE_OUTSIDE_DEM
    lead_c.put(
        f"/api/missions/{mid}/landing-site",
        headers=_csrf_headers(lead_c),
        json={"name": "Remote Polar Point", "latitude": -88.5, "longitude": 12.0, "source": "USER_PROVIDED"},
    )
    out_p = lead_c.post(
        f"/api/missions/{mid}/landing-site/perimeter",
        headers=_csrf_headers(lead_c),
        json={"max_slope_deg": 20.0, "max_roughness_m": 2.5, "max_radius_m": 120.0},
    ).json()
    assert out_p["perimeter"]["status"] == "INDETERMINATE_OUTSIDE_DEM"
    assert out_p["perimeter"]["geometry_geojson"] is None

    # Verify append-only mission_events monotonic event_seq
    evs = lead_c.get(f"/api/missions/{mid}/events").json()
    seqs = [e["event_seq"] for e in evs]
    assert seqs == sorted(seqs, reverse=True)
    assert len(seqs) >= 8
