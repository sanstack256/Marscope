"""
Judge Demonstration Mode Service & Idempotent Bootstrap.

Provisions:
- 3 isolated demo astronaut identities (DEMO COMMANDER, DEMO ASTRONAUT ALPHA, DEMO ASTRONAUT BRAVO)
- 1 persistent demonstration mission (DEMO_MISSION_ID) in Gale Crater (IAU2000:49900)
- Valid persisted crew positions within HiRISE DTEEC_009149_1750 bounds
- 1 initial ACTIVE SOS event from DEMO ASTRONAUT ALPHA
- 2 distinct USER_REPORTED field observations from Alpha and Bravo
- Persisted mission event timeline entries
- Idempotent startup seeding + demo-only reset without affecting production records
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import MissionDatabase
from app.schemas.mission_collab import DemoCredentialsConfigResponse
from app.services.mission_event_service import MissionEventService

DEMO_MISSION_ID = "demo-mission-gale-001"
DEMO_CMD_ID = "demo-astro-commander-001"
DEMO_ALPHA_ID = "demo-astro-alpha-002"
DEMO_BRAVO_ID = "demo-astro-bravo-003"

DEMO_SOS_ALPHA_ID = "demo-sos-alpha-001"
DEMO_OBS_ALPHA_ID = "demo-obs-alpha-001"
DEMO_OBS_BRAVO_ID = "demo-obs-bravo-002"
DEMO_LANDING_SITE_ID = "demo-landing-gale-001"

# Valid IAU2000:49900 coordinates inside HiRISE DTEEC_009149_1750_009294_1750_U01.IMG
# Coverage: lat [-4.923097, -4.67618], lon_east [137.353332, 137.468529]
DEMO_BASE_LAT = -4.799639
DEMO_BASE_LON = 137.410930
DEMO_ALPHA_LAT = -4.788500
DEMO_ALPHA_LON = 137.418200
DEMO_BRAVO_LAT = -4.810400
DEMO_BRAVO_LON = 137.402500


class DemoService:
    def __init__(
        self,
        db: MissionDatabase,
        event_service: MissionEventService,
        credentials_file: Path,
        processed_dir: Path,
    ) -> None:
        self._db = db
        self._events = event_service
        self._credentials_file = credentials_file
        self._processed_dir = processed_dir

    def _resolve_demo_credentials(self) -> tuple[str, str]:
        email = (settings.MARSCOPE_DEMO_EMAIL or "judge.demo@marscope.local").strip().lower()
        configured_pw = (settings.MARSCOPE_DEMO_PASSWORD or "").strip()
        if configured_pw:
            return email, configured_pw

        if self._credentials_file.exists():
            try:
                data = json.loads(self._credentials_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("email") == email and data.get("password"):
                    return email, str(data["password"])
            except (OSError, ValueError):
                pass

        generated_pw = f"MarsDemo-7a{secrets.token_urlsafe(10)}"
        self._credentials_file.parent.mkdir(parents=True, exist_ok=True)
        self._credentials_file.write_text(
            json.dumps({"email": email, "password": generated_pw}, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(self._credentials_file, 0o600)
        except OSError:
            pass
        return email, generated_pw

    def get_public_demo_config(self) -> DemoCredentialsConfigResponse:
        if not settings.MARSCOPE_DEMO_ENABLED:
            return DemoCredentialsConfigResponse(enabled=False)

        self.ensure_seeded()
        email, password = self._resolve_demo_credentials()
        return DemoCredentialsConfigResponse(
            enabled=True,
            demo_mission_id=DEMO_MISSION_ID,
            email=email,
            password=password,
            display_name="DEMO COMMANDER",
            account_label="DEMO",
        )

    def ensure_seeded(self, *, force_reseed: bool = False) -> Dict[str, Any]:
        if not settings.MARSCOPE_DEMO_ENABLED:
            return {"enabled": False, "seeded": False}

        email, password = self._resolve_demo_credentials()
        now_iso = datetime.now(timezone.utc).isoformat()
        cmd_hash = hash_password(password)
        companion_hash = hash_password(f"DemoCompanion-7a{secrets.token_urlsafe(16)}")

        hirise_dem_exists = (self._processed_dir / "hirise_dteec_009149_1750_dem.tif").exists()
        landing_status = "REGISTERED" if hirise_dem_exists else "LANDING_SITE_UNCONFIGURED"

        with self._db.transaction() as conn:
            # 1. Seed exactly three demo astronaut identities (is_demo = 1)
            astronaut_specs = [
                (DEMO_CMD_ID, email, "DEMO COMMANDER", cmd_hash),
                (DEMO_ALPHA_ID, "alpha.demo@marscope.local", "DEMO ASTRONAUT ALPHA", companion_hash),
                (DEMO_BRAVO_ID, "bravo.demo@marscope.local", "DEMO ASTRONAUT BRAVO", companion_hash),
            ]
            for astro_id, astro_email, display_name, pw_hash in astronaut_specs:
                existing = conn.execute(
                    "SELECT astronaut_id FROM astronauts WHERE astronaut_id = ?",
                    (astro_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO astronauts (
                            astronaut_id, email, display_name, password_hash, is_active,
                            profile_visibility, profile_edit_history_json,
                            body_mass_kg, suit_mass_kg, equipment_mass_kg,
                            is_demo, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, 1, 'mission_members', '[]', 75.0, 120.0, 18.0, 1, ?, ?)
                        """,
                        (astro_id, astro_email, display_name, pw_hash, now_iso, now_iso),
                    )
                elif astro_id == DEMO_CMD_ID:
                    conn.execute(
                        """
                        UPDATE astronauts
                        SET email = ?, password_hash = ?, is_demo = 1, updated_at_utc = ?
                        WHERE astronaut_id = ?
                        """,
                        (astro_email, pw_hash, now_iso, astro_id),
                    )

            # 2. Seed one persistent demo mission (is_demo = 1)
            mission_row = conn.execute(
                "SELECT mission_id FROM missions WHERE mission_id = ?",
                (DEMO_MISSION_ID,),
            ).fetchone()
            if mission_row is None:
                conn.execute(
                    """
                    INSERT INTO missions (
                        mission_id, name, description, objective, lead_astronaut_id,
                        operating_region, visibility, membership_policy, status,
                        landing_site_status, is_demo, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, 'private', 'invite_only', 'ACTIVE', ?, 1, ?, ?)
                    """,
                    (
                        DEMO_MISSION_ID,
                        "Gale Crater Boxwork Survey (DEMONSTRATION MISSION)",
                        "Prepared judge demonstration mission showcasing multi-astronaut field science, active SOS emergency response, terrain-aware route planning, and evidence provenance.",
                        "Inspect boxwork fracture outcrops and basaltic float in Gale Crater while maintaining active EVA crew coordination.",
                        DEMO_CMD_ID,
                        "Gale Crater / Mount Sharp (HiRISE DTEEC_009149_1750)",
                        landing_status,
                        now_iso,
                        now_iso,
                    ),
                )

            # 3. Seed memberships for all 3 demo astronauts
            memberships = [
                ("demo-mem-cmd-001", DEMO_MISSION_ID, DEMO_CMD_ID, "MISSION_LEAD"),
                ("demo-mem-alpha-002", DEMO_MISSION_ID, DEMO_ALPHA_ID, "ASTRONAUT"),
                ("demo-mem-bravo-003", DEMO_MISSION_ID, DEMO_BRAVO_ID, "ASTRONAUT"),
            ]
            for mem_id, m_id, a_id, role in memberships:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO mission_memberships (
                        membership_id, mission_id, astronaut_id, role, status,
                        location_sharing_enabled, joined_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, 'ACTIVE', 1, ?, ?)
                    """,
                    (mem_id, m_id, a_id, role, now_iso, now_iso),
                )

            # 4. Register Gale Crater landing site if local HiRISE DEM is present
            if hirise_dem_exists:
                ls_row = conn.execute(
                    "SELECT landing_site_id FROM landing_sites WHERE mission_id = ?",
                    (DEMO_MISSION_ID,),
                ).fetchone()
                if ls_row is None:
                    conn.execute(
                        """
                        INSERT INTO landing_sites (
                            landing_site_id, mission_id, name, latitude, longitude_east,
                            crs, latitude_convention, longitude_direction, source,
                            source_record_id, uncertainty_m, elevation_m,
                            terrain_dataset_id, dem_coverage_state, registration_state,
                            updated_by, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, ?, 'IAU2000:49900', 'planetocentric', 'east_0_360',
                                  'USER_PROVIDED', 'demo-gale-base', 5.0, -4510.0,
                                  'hirise_dteec_009149_1750', 'COVERED_DEM', 'REGISTERED',
                                  ?, ?, ?)
                        """,
                        (
                            DEMO_LANDING_SITE_ID,
                            DEMO_MISSION_ID,
                            "Boxwork Survey Base (Demo Landing Site)",
                            DEMO_BASE_LAT,
                            DEMO_BASE_LON,
                            DEMO_CMD_ID,
                            now_iso,
                            now_iso,
                        ),
                    )
                    conn.execute(
                        "UPDATE missions SET landing_site_status = 'REGISTERED' WHERE mission_id = ?",
                        (DEMO_MISSION_ID,),
                    )
                else:
                    conn.execute(
                        "UPDATE landing_sites SET dem_coverage_state = 'COVERED_DEM' WHERE mission_id = ? AND dem_coverage_state = 'COVERED'",
                        (DEMO_MISSION_ID,),
                    )

            # 5. Seed initial crew positions if missing (or on force_reseed)
            pos_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM crew_positions WHERE mission_id = ?",
                (DEMO_MISSION_ID,),
            ).fetchone()["cnt"]
            if pos_count == 0 or force_reseed:
                pos_specs = [
                    ("demo-pos-cmd-001", DEMO_CMD_ID, DEMO_BASE_LAT, DEMO_BASE_LON, -4510.0, 4.0, "demo-sim-cmd"),
                    ("demo-pos-alpha-002", DEMO_ALPHA_ID, DEMO_ALPHA_LAT, DEMO_ALPHA_LON, -4482.5, 6.5, "demo-sim-alpha"),
                    ("demo-pos-bravo-003", DEMO_BRAVO_ID, DEMO_BRAVO_LAT, DEMO_BRAVO_LON, -4496.0, 5.2, "demo-sim-bravo"),
                ]
                for p_id, a_id, lat, lon, elev, unc, src_id in pos_specs:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO crew_positions (
                            position_id, mission_id, astronaut_id, latitude, longitude_east,
                            crs, latitude_convention, longitude_direction, elevation_m,
                            uncertainty_m, source_id, source_classification, sequence_number,
                            measured_at_utc, received_at_utc, validation_status
                        ) VALUES (?, ?, ?, ?, ?, 'IAU2000:49900', 'planetocentric', 'east_0_360',
                                  ?, ?, ?, 'USER_PROVIDED', 1, ?, ?, 'VALIDATED')
                        """,
                        (p_id, DEMO_MISSION_ID, a_id, lat, lon, elev, unc, src_id, now_iso, now_iso),
                    )

            # 6. Seed Alpha's initial ACTIVE SOS (idempotent via client_event_id / primary key)
            sos_exists = conn.execute(
                "SELECT sos_id FROM sos_events WHERE sos_id = ?",
                (DEMO_SOS_ALPHA_ID,),
            ).fetchone()
            if sos_exists is None:
                conn.execute(
                    """
                    INSERT INTO sos_events (
                        sos_id, mission_id, astronaut_id, event_type, status,
                        client_event_id, latitude, longitude_east, elevation_m, crs,
                        position_source, position_classification, position_age_s, position_status,
                        message, voice_note_id, is_demo, created_at_utc, server_received_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, 'SOS_ACTIVATED', 'ACTIVE', 'demo-sos-alpha-seed-v1',
                              ?, ?, -4482.5, 'IAU2000:49900',
                              'demo-sim-alpha', 'USER_PROVIDED', 0.0, 'VALIDATED',
                              ?, NULL, 1, ?, ?, ?)
                    """,
                    (
                        DEMO_SOS_ALPHA_ID,
                        DEMO_MISSION_ID,
                        DEMO_ALPHA_ID,
                        DEMO_ALPHA_LAT,
                        DEMO_ALPHA_LON,
                        "DEMONSTRATION SOS: DEMO ASTRONAUT ALPHA requests support at Boxwork Ridge East (ankle strain reported during outcrop survey).",
                        now_iso,
                        now_iso,
                        now_iso,
                    ),
                )
                self._events.record_event_tx(
                    conn,
                    mission_id=DEMO_MISSION_ID,
                    actor_id=DEMO_ALPHA_ID,
                    event_type="SOS_ACTIVATED",
                    client_event_id="demo-event-sos-alpha-seed-v1",
                    provenance={"source": "DEMO_SEED", "classification": "USER_REPORTED"},
                    payload={
                        "sos_id": DEMO_SOS_ALPHA_ID,
                        "status": "ACTIVE",
                        "latitude": DEMO_ALPHA_LAT,
                        "longitude_east": DEMO_ALPHA_LON,
                        "crs": "IAU2000:49900",
                        "note": "DEMO ASTRONAUT ALPHA raised an active demonstration SOS.",
                    },
                )

            # 7. Seed Alpha & Bravo Field Observations (USER_REPORTED — DEMONSTRATION DATA)
            obs_specs = [
                (
                    DEMO_OBS_ALPHA_ID,
                    DEMO_ALPHA_ID,
                    "demo-obs-alpha-seed-v1",
                    DEMO_ALPHA_LAT,
                    DEMO_ALPHA_LON,
                    -4482.5,
                    "Calcium-sulfate fracture fill / layered mudstone (USER_REPORTED demo)",
                    "Reported material: Calcium-sulfate veinlets in laminated mudstone (USER_REPORTED — DEMONSTRATION DATA). Scientific verification: NOT ESTABLISHED.",
                    "DEMO ASTRONAUT ALPHA reported layered mudstone & sulfate fracture fill at Boxwork Ridge East.",
                ),
                (
                    DEMO_OBS_BRAVO_ID,
                    DEMO_BRAVO_ID,
                    "demo-obs-bravo-seed-v1",
                    DEMO_BRAVO_LAT,
                    DEMO_BRAVO_LON,
                    -4496.0,
                    "Vesicular basaltic float (USER_REPORTED demo)",
                    "Reported material: Vesicular dark-toned basaltic float clast (USER_REPORTED — DEMONSTRATION DATA). Scientific verification: NOT ESTABLISHED.",
                    "DEMO ASTRONAUT BRAVO reported vesicular basaltic float near Gediz Vallis margin.",
                ),
            ]
            for obs_id, a_id, client_eid, lat, lon, elev, mat_name, desc, evt_note in obs_specs:
                obs_row = conn.execute(
                    "SELECT observation_id FROM field_observations WHERE observation_id = ?",
                    (obs_id,),
                ).fetchone()
                if obs_row is None:
                    conn.execute(
                        """
                        INSERT INTO field_observations (
                            observation_id, mission_id, astronaut_id, client_event_id, version,
                            latitude, longitude_east, elevation_m, crs, coordinate_source,
                            uncertainty_m, target_id, category, species_canonical_id, species_display_name,
                            description, epistemic_state, instrument_id, source_product_id,
                            calibration_metadata, evidence_ids_json, is_demo,
                            created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'IAU2000:49900', 'USER_PROVIDED',
                                  6.0, NULL, 'MINERAL_DISCOVERY', NULL, ?,
                                  ?, 'USER_REPORTED', NULL, NULL,
                                  'DEMONSTRATION DATA — Scientific verification NOT ESTABLISHED', '[]', 1,
                                  ?, ?)
                        """,
                        (obs_id, DEMO_MISSION_ID, a_id, client_eid, lat, lon, elev, mat_name, desc, now_iso, now_iso),
                    )
                    self._events.record_event_tx(
                        conn,
                        mission_id=DEMO_MISSION_ID,
                        actor_id=a_id,
                        event_type="OBSERVATION_CREATED",
                        client_event_id=f"demo-event-{client_eid}",
                        provenance={"source": "DEMO_SEED", "classification": "USER_REPORTED"},
                        payload={
                            "observation_id": obs_id,
                            "reported_material": mat_name,
                            "epistemic_state": "USER_REPORTED",
                            "latitude": lat,
                            "longitude_east": lon,
                            "crs": "IAU2000:49900",
                            "note": evt_note,
                        },
                    )

        return {"enabled": True, "seeded": True, "demo_mission_id": DEMO_MISSION_ID}

    def reset_demo_mission(self, *, actor_is_demo: bool) -> Dict[str, Any]:
        if not settings.MARSCOPE_DEMO_ENABLED:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is disabled.")
        if not actor_is_demo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the isolated demonstration account can reset the demonstration mission.",
            )

        with self._db.transaction() as conn:
            conn.execute("DELETE FROM sos_acknowledgements WHERE sos_id IN (SELECT sos_id FROM sos_events WHERE mission_id = ?)", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM sos_events WHERE mission_id = ?", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM field_observations WHERE mission_id = ?", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM crew_positions WHERE mission_id = ?", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM mission_events WHERE mission_id = ?", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM navigation_obstructions WHERE mission_id = ?", (DEMO_MISSION_ID,))
            conn.execute("DELETE FROM navigation_sessions WHERE mission_id = ?", (DEMO_MISSION_ID,))

        res = self.ensure_seeded(force_reseed=True)
        return {"reset": True, **res}
