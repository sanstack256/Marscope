"""
MARSCOPE Prompt 20 — Adversarial Verification Suite
Advanced Human Marswalk Intelligence, EVA Operational Modelling,
Dynamic Mission Replanning, Conditional Telemetry & Scientific Honesty.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.eva_operations.energy_budget import evaluate_eva_energy_budget
from app.eva_operations.environmental_context import evaluate_eva_environmental_context
from app.eva_operations.locomotion import (
    EpistemicClassification,
    LocomotionEvaluationStatus,
    LocomotionModelCategory,
    compare_locomotion_scenarios,
    evaluate_segment_locomotion,
)
from app.eva_operations.replanning import (
    EVENT_DEPENDENCY_INVALIDATION_MAP,
    MissionEventIngestRequest,
    MissionEventType,
    MissionReplanRequest,
    MissionWorkflowState,
)
from app.eva_operations.resource_budget import evaluate_eva_resource_budget
from app.eva_operations.schemas import (
    EnvelopeFeasibilityStatus,
    ExplicitResourceSpec,
    ExtensibleResourceCategory,
    MissionConfigRequest,
    ReservePolicy,
    ResourceRatePhaseSpec,
    SpeedModelMode,
)
from app.eva_operations.telemetry import (
    ConditionalTelemetryAdapter,
    TelemetryConsumableSample,
    TelemetryFreshnessState,
    TelemetryPacketIngestRequest,
)
from app.mobility.models import (
    TraversabilityEvidenceState,
    UNMEASURED_SOIL_PROPERTIES_DEFAULT,
    UnmeasuredSoilProperty,
)
from app.routing.models import RouteObjective, RoutingMode, UnknownTerrainPolicy
from app.routing.schemas import RouteCoordinateInput
from app.services.container import eva_operations_service, morphology_service
from app.terrain.morphology import MorphologyReviewStore


client = TestClient(app)


# ---------------------------------------------------------------------------
# Part 2.1 — Locomotion Model Separation & Pure Tobler 1993 Math
# ---------------------------------------------------------------------------


def test_part21_three_locomotion_categories_and_pure_tobler_math() -> None:
    # 1) User-configured constant speed
    const_eval = evaluate_segment_locomotion(
        segment_index=0,
        horizontal_distance_m=100.0,
        elevation_change_m=10.0,
        slope_deg=5.71,
        reference_speed_mps=1.0,
        category=LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
    )
    assert const_eval.status == LocomotionEvaluationStatus.EVALUATED
    assert const_eval.classification == EpistemicClassification.USER_ASSUMED
    assert abs(const_eval.duration_s - 100.0) < 1e-6

    # Missing speed refuses silent fallback
    missing_speed = evaluate_segment_locomotion(
        segment_index=1,
        horizontal_distance_m=100.0,
        elevation_change_m=0.0,
        slope_deg=0.0,
        reference_speed_mps=None,
        category=LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
    )
    assert missing_speed.status == LocomotionEvaluationStatus.MISSING_REFERENCE_SPEED
    assert missing_speed.duration_s is None

    # 2) Terrestrial hiking approximation — pure Tobler (1993) factor:
    # W(S) = 6 * exp(-3.5 * |S + 0.05|), W(0) = 6 * exp(-0.175)
    # normalized factor = exp(-3.5 * |S + 0.05| + 0.175)
    # No fabricated 55-deg linear attenuation or 0.22 floor
    import math

    dz = 20.0
    dx = 100.0
    slope_deg = math.degrees(math.atan2(dz, dx))  # ~11.31 deg within [-35, 35]
    tobler_eval = evaluate_segment_locomotion(
        segment_index=2,
        horizontal_distance_m=dx,
        elevation_change_m=dz,
        slope_deg=slope_deg,
        reference_speed_mps=1.0,
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        min_valid_slope_deg=-35.0,
        max_valid_slope_deg=35.0,
    )
    assert tobler_eval.status == LocomotionEvaluationStatus.EVALUATED
    assert tobler_eval.classification == EpistemicClassification.MODELLED
    expected_factor = math.exp(-3.5 * abs((dz / dx) + 0.05) + 0.175)
    expected_speed = 1.0 * expected_factor
    assert abs(tobler_eval.effective_speed_mps - expected_speed) < 1e-4
    assert abs(tobler_eval.duration_s - (dx / tobler_eval.effective_speed_mps)) < 0.05

    # Outside valid slope bounds is explicitly rejected, never silently clamped to 0.22 floor
    out_of_domain = evaluate_segment_locomotion(
        segment_index=3,
        horizontal_distance_m=100.0,
        elevation_change_m=90.0,
        slope_deg=41.99,
        reference_speed_mps=1.0,
        category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
        min_valid_slope_deg=-35.0,
        max_valid_slope_deg=35.0,
    )
    assert out_of_domain.status == LocomotionEvaluationStatus.OUTSIDE_LOCOMOTION_VALID_DOMAIN
    assert out_of_domain.duration_s is None

    # 3) Mission-validated suit locomotion model is explicitly UNAVAILABLE without validated external data
    suit_eval = evaluate_segment_locomotion(
        segment_index=4,
        horizontal_distance_m=100.0,
        elevation_change_m=5.0,
        slope_deg=2.86,
        reference_speed_mps=1.0,
        category=LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL,
        validated_suit_model_source=None,
    )
    assert suit_eval.status == LocomotionEvaluationStatus.MODEL_UNAVAILABLE
    assert suit_eval.classification == EpistemicClassification.UNAVAILABLE
    assert suit_eval.duration_s is None

    # Compare all locomotion scenarios side-by-side
    scenarios = compare_locomotion_scenarios(
        outbound_segments=[{"horizontal_distance_m": 100.0, "elevation_change_m": 10.0, "slope_deg": 5.71}],
        return_segments=[{"horizontal_distance_m": 100.0, "elevation_change_m": -10.0, "slope_deg": -5.71}],
        base_speed_mps=1.0,
        mission_duration_limit_s=1000.0,
        operational_overhead_s=60.0,
    )
    by_cat = {s.category: s for s in scenarios}
    assert LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED in by_cat
    assert LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION in by_cat
    assert LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL in by_cat
    suit_sc = by_cat[LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL]
    assert suit_sc.status == LocomotionEvaluationStatus.MODEL_UNAVAILABLE
    assert suit_sc.classification == EpistemicClassification.UNAVAILABLE


# ---------------------------------------------------------------------------
# Part 2.2 — No Silent Mars Gravity Fallback
# ---------------------------------------------------------------------------


def test_part22_missing_mars_gravity_has_no_silent_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.eva_operations.energy_budget.get_parameter", lambda _key: None)
    report = evaluate_eva_energy_budget(
        astronaut_suit_mass_kg=120.0,
        payload_mass_kg=15.0,
        outbound_climb_gain_m=30.0,
        outbound_descent_loss_m=10.0,
        return_climb_gain_m=10.0,
        return_descent_loss_m=30.0,
    )
    assert report.available is False
    assert report.mars_gravity_m_s2 is None
    assert "mars_standard_gravity" in report.missing_inputs
    assert report.outbound_climb_work_j is None
    assert report.total_positive_climb_work_j is None


def test_part22_registered_mars_gravity_provenance() -> None:
    report = evaluate_eva_energy_budget(
        astronaut_suit_mass_kg=120.0,
        payload_mass_kg=15.0,
        outbound_climb_gain_m=20.0,
        outbound_descent_loss_m=5.0,
        return_climb_gain_m=5.0,
        return_descent_loss_m=20.0,
    )
    assert report.available is True
    assert report.mars_gravity_m_s2 is not None and abs(report.mars_gravity_m_s2 - 3.72076) < 1e-4
    assert any(p.parameter_name == "mars_standard_gravity" for p in report.parameter_provenance)


# ---------------------------------------------------------------------------
# Part 2.4 & Part 6 — 11-Category Extensible Resource Accounting
# ---------------------------------------------------------------------------


def test_part6_eleven_resource_categories_phase_rates_and_unit_rejection() -> None:
    assert len(ExtensibleResourceCategory) == 11

    o2_spec = ExplicitResourceSpec(
        resource_name="Primary O2 Tank",
        category=ExtensibleResourceCategory.OXYGEN_INVENTORY,
        initial_quantity=2.0,
        unit="kg",
        consumption_rate=0.05,
        rate_unit="kg/hr",
        reserve_fraction=0.2,
        reserve_policy=ReservePolicy(
            policy_id="o2_min_res",
            reserve_fraction=0.2,
            minimum_absolute_reserve=0.5,
            rationale="Explicit operator minimum O2 reserve.",
        ),
        phase_rates=[
            ResourceRatePhaseSpec(phase="outbound_traverse", consumption_rate=0.06, rate_unit="kg/hr"),
            ResourceRatePhaseSpec(phase="return_traverse", consumption_rate=0.08, rate_unit="kg/hr"),
            ResourceRatePhaseSpec(phase="science_stops", consumption_rate=0.04, rate_unit="kg/hr"),
            ResourceRatePhaseSpec(phase="overhead", consumption_rate=0.02, rate_unit="kg/hr"),
        ],
    )
    bad_unit_spec = ExplicitResourceSpec(
        resource_name="Battery Pack",
        category=ExtensibleResourceCategory.BATTERY_ENERGY,
        initial_quantity=10.0,
        unit="kWh",
        consumption_rate=0.5,
        rate_unit="kg/hr",  # incompatible with kWh!
        reserve_fraction=0.1,
    )

    report = evaluate_eva_resource_budget(
        resources=[o2_spec, bad_unit_spec],
        exposure_duration_s=7200.0,
        phase_durations_s={
            "outbound_traverse": 1800.0,
            "return_traverse": 1800.0,
            "science_stops": 1800.0,
            "overhead": 1800.0,
        },
    )

    assert len(report.category_coverage) == 11
    unconfigured = [
        cat for cat, status in report.category_coverage.items()
        if cat not in {ExtensibleResourceCategory.OXYGEN_INVENTORY.value, ExtensibleResourceCategory.BATTERY_ENERGY.value}
    ]
    assert all(report.category_coverage[c] == "UNAVAILABLE_NOT_SUPPLIED" for c in unconfigured)

    entries_by_name = {e.resource_name: e for e in report.entries}
    o2_entry = entries_by_name["Primary O2 Tank"]
    assert o2_entry.integration_mode == "PHASE_INTEGRATED_Q_DOT_T"
    # Total O2 consumed = (0.06 + 0.08 + 0.04 + 0.02) * 0.5 hr = 0.10 kg
    assert abs(o2_entry.estimated_consumed - 0.10) < 1e-6
    # max(0.2 * 2.0 = 0.40, minimum_absolute_reserve = 0.50) = 0.50
    assert abs(o2_entry.reserve_required - 0.50) < 1e-6

    batt_entry = entries_by_name["Battery Pack"]
    assert batt_entry.status == "UNIT_MISMATCH"
    assert batt_entry.estimated_consumed is None


# ---------------------------------------------------------------------------
# Part 3 & 4 — 10-State Traversability, 6 Unmeasured Soil Props, 9 Review Actions
# ---------------------------------------------------------------------------


def test_part3_and_part4_traversability_states_and_9_review_actions(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert len(TraversabilityEvidenceState) == 10
    assert len(UnmeasuredSoilProperty) == 6
    assert set(UNMEASURED_SOIL_PROPERTIES_DEFAULT.keys()) == {p.value for p in UnmeasuredSoilProperty}
    assert all(v == "UNKNOWN_UNMEASURED" for v in UNMEASURED_SOIL_PROPERTIES_DEFAULT.values())

    # RouteObjective accepts both Prompt 16 UPPERCASE and lowercase aliases case-insensitively
    assert RouteObjective("BALANCED_MULTIOBJECTIVE") == RouteObjective.BALANCED_MULTIOBJECTIVE
    assert RouteObjective("balanced_multiobjective") == RouteObjective.BALANCED_MULTIOBJECTIVE
    assert len(RouteObjective) == 9
    assert len(UnknownTerrainPolicy) == 4

    # Isolated morphology review store so tests never touch data/
    isolated_store = MorphologyReviewStore(tmp_path / "reviews.json")
    monkeypatch.setattr(morphology_service, "review_store", isolated_store)
    monkeypatch.setenv("MARSCOPE_OPERATOR_TOKEN", "p20-test-operator-token")

    actions_payloads = [
        ("accept", {"annotation_note": "Confirmed boxwork ridge trace."}),
        ("reject", {"annotation_note": "Artifact near shadow edge."}),
        ("annotate", {"annotation_note": "Stratified bench segment."}),
        ("correct_geometry", {"corrected_geometry_geojson": {"type": "Point", "coordinates": [137.395, -4.748]}}),
        ("add_observation", {"observation_record": {"sol": 4120, "note": "Fracture width ~0.4m"}}),
        ("attach_source", {"attached_source_reference": "ESP_009149_1750_RED.JP2"}),
        ("record_uncertainty", {"recorded_uncertainty_m": 1.75}),
        ("add_note", {"annotation_note": "Avoid loose sand ripple trough."}),
        ("mark_unresolved", {"annotation_note": "Sub-pixel overhang requires rover confirmation."}),
    ]
    for idx, (action, extra) in enumerate(actions_payloads):
        body = {
            "candidate_id": f"p20_cand_{idx}",
            "dataset_id": "hirise_dteec_009149_1750",
            "action": action,
            "reviewer_id": "geo_reviewer_p20",
            **extra,
        }
        res = client.post(
            "/api/spatial/morphology/review",
            json=body,
            headers={"X-Mars-Operator-Token": "p20-test-operator-token"},
        )
        assert res.status_code == 200, f"Action {action} failed: {res.text}"
        rec = res.json()
        assert rec["action"] == action
        assert rec["classification"] == "USER_PROVIDED"


# ---------------------------------------------------------------------------
# Part 9 — Conditional Telemetry Adapter (Fail-Closed & Freshness Transitions)
# ---------------------------------------------------------------------------


def test_part9_conditional_telemetry_adapter_security_and_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ConditionalTelemetryAdapter()
    t0 = datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Disconnected by default
    s0 = adapter.get_status(now_utc=t0)
    assert s0.connected is False
    assert s0.connection_status == "TELEMETRY NOT CONNECTED"
    assert s0.crew_state_status == "LIVE CREW STATE UNAVAILABLE"
    assert s0.freshness_state == TelemetryFreshnessState.NOT_CONNECTED

    # Auth fails closed when unconfigured
    monkeypatch.delenv("MARSCOPE_TRACKING_TOKEN", raising=False)
    monkeypatch.delenv("MARSCOPE_OPERATOR_TOKEN", raising=False)
    ok, code, _ = adapter.verify_auth(x_operator_token="any")
    assert ok is False and code == 403

    monkeypatch.setenv("MARSCOPE_TRACKING_TOKEN", "p20-track-secret")
    ok_auth, code_auth, _ = adapter.verify_auth(x_tracking_token="p20-track-secret")
    assert ok_auth is True and code_auth == 200

    # Must connect provider first
    adapter.connect_provider("dsn_surface_relay_mock_test")

    # Reject browser geolocation / fake GPS / non-Mars CRS / unsupported consumable unit
    for bad_kw, expected_fragment in [
        ({"provider_id": "browser_geolocation"}, "Prohibited consumer/simulated telemetry provider"),
        ({"crs": "EPSG:4326"}, "Mars"),
        (
            {"consumables": [TelemetryConsumableSample(channel_name="o2", value=1.2, unit="gallons")]},
            "gallons",
        ),
    ]:
        base_pkt = {
            "provider_id": "dsn_surface_relay_mock_test",
            "session_id": "eva_sol_001",
            "sequence_number": 1,
            "timestamp_utc": t0.isoformat(),
            "crs": "IAU2000:49900",
            "lat": -4.745,
            "lon_east": 137.395,
            "elevation_m": -4210.0,
            "horizontal_uncertainty_m": 1.5,
        }
        base_pkt.update(bad_kw)
        with pytest.raises(ValueError, match=expected_fragment):
            adapter.ingest_packet(TelemetryPacketIngestRequest(**base_pkt), now_utc=t0)

    # Valid packet -> LIVE -> RECENT -> STALE -> EXPIRED
    valid_pkt = TelemetryPacketIngestRequest(
        provider_id="dsn_surface_relay_mock_test",
        session_id="eva_sol_001",
        sequence_number=10,
        timestamp_utc=t0.isoformat(),
        crs="IAU2000:49900",
        lat=-4.745,
        lon_east=137.395,
        elevation_m=-4210.0,
        horizontal_uncertainty_m=1.5,
        consumables=[TelemetryConsumableSample(channel_name="o2", value=1.8, unit="kg")],
        live_threshold_s=15.0,
        stale_threshold_s=60.0,
        expired_threshold_s=300.0,
    )
    res_live = adapter.ingest_packet(valid_pkt, now_utc=t0 + timedelta(seconds=5))
    assert res_live.freshness_state == TelemetryFreshnessState.LIVE
    assert adapter.get_status(now_utc=t0 + timedelta(seconds=30)).freshness_state == TelemetryFreshnessState.RECENT
    assert adapter.get_status(now_utc=t0 + timedelta(seconds=120)).freshness_state == TelemetryFreshnessState.STALE
    assert adapter.get_status(now_utc=t0 + timedelta(seconds=400)).freshness_state == TelemetryFreshnessState.EXPIRED

    # Out-of-order sequence number rejected
    with pytest.raises(LookupError, match="sequence_number"):
        adapter.ingest_packet(valid_pkt, now_utc=t0 + timedelta(seconds=6))

    # HTTP /api/eva-operations/telemetry/ingest auth enforcement
    unauth_res = client.post("/api/eva-operations/telemetry/ingest", json=valid_pkt.model_dump(mode="json"))
    assert unauth_res.status_code == 401
    # Clean disconnect so singleton stays clean
    eva_operations_service.disconnect_telemetry_provider()


# ---------------------------------------------------------------------------
# Part 10 — Environmental Context Separation
# ---------------------------------------------------------------------------


def test_part10_environmental_context_archive_vs_live_separation() -> None:
    report = evaluate_eva_environmental_context(study_region="Gale Crater / Mount Sharp", mission_duration_s=7200.0)
    assert report.live_weather_available is False
    assert report.live_weather_status == "LIVE SURFACE WEATHER UNAVAILABLE"
    assert report.live_radiation_available is False
    assert report.live_radiation_status == "LIVE RADIATION TELEMETRY UNAVAILABLE"
    assert any(obs.observation_type == "ARCHIVE_OBSERVATION" for obs in report.archive_observations)
    assert all(obs.classification == "ARCHIVE_DERIVED" for obs in report.archive_observations)
    assert report.archive_reference_gcr_dose_msv is not None and report.archive_reference_gcr_dose_msv > 0.0
    assert len(report.prohibited_inferences) >= 3


# ---------------------------------------------------------------------------
# Part 2.5, 8, 11, 13 — End-to-End Real HiRISE Mission, Replanning, Sensitivity & SHA-256 Dossier
# ---------------------------------------------------------------------------


def test_real_hirise_mission_replanning_sensitivity_and_dossier(tmp_path) -> None:
    # Step 1a: Missing walking speed input -> INCOMPLETE_CONSTRAINT_EVALUATION
    blocked_req = MissionConfigRequest(
        mission_name="Boxwork P20 Missing Input Check",
        dataset_id="hirise_dteec_009149_1750",
        start=RouteCoordinateInput(lat=-4.749, lon_east=137.394),
        destination=RouteCoordinateInput(lat=-4.753, lon_east=137.396),
        mode=RoutingMode.BALANCED,
        walking_speed_mps=None,
        locomotion_category=LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
        confirm_default_policies=True,
        compute_reverse_return_route=False,
    )
    blocked_env = eva_operations_service.evaluate_mission(blocked_req)
    assert blocked_env.model_feasibility_status in {
        EnvelopeFeasibilityStatus.BLOCKED_BY_UNKNOWN_INPUTS,
        EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION,
    }
    assert "walking_speed_mps" in blocked_env.missing_inputs

    # Step 1b: Unavailable validated suit model -> BLOCKED_BY_UNKNOWN_INPUTS
    unavail_req = blocked_req.model_copy(
        update={
            "walking_speed_mps": 0.9,
            "locomotion_category": LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL,
        }
    )
    unavail_env = eva_operations_service.evaluate_mission(unavail_req)
    assert unavail_env.model_feasibility_status in {
        EnvelopeFeasibilityStatus.BLOCKED_BY_UNKNOWN_INPUTS,
        EnvelopeFeasibilityStatus.INCOMPLETE_CONSTRAINT_EVALUATION,
    }
    assert any("suit_locomotion" in mi or "validated_suit" in mi or "locomotion" in mi for mi in unavail_env.missing_inputs)

    # Step 2: Full real-HiRISE Boxwork mission evaluation via API
    eval_payload = {
        "mission_name": "Boxwork Prompt 20 Traverse",
        "dataset_id": "hirise_dteec_009149_1750",
        "start": {"lat": -4.749, "lon_east": 137.394},
        "destination": {"lat": -4.753, "lon_east": 137.396},
        "mode": "balanced",
        "locomotion_category": "TERRESTRIAL_HIKING_APPROXIMATION",
        "walking_speed_mps": 0.9,
        "use_tobler_grade_approximation": True,
        "unknown_terrain_policy": "EXCLUDE_UNKNOWN",
        "confirm_default_policies": True,
        "mission_duration_limit_s": 14400.0,
        "return_reserve_fraction": 0.2,
        "operational_overhead_s": 600.0,
        "astronaut_suit_mass_kg": 120.0,
        "payload_mass_kg": 20.0,
        "resources": [
            {
                "resource_name": "Primary Oxygen",
                "category": "oxygen_inventory",
                "initial_quantity": 2.4,
                "unit": "kg",
                "consumption_rate": 0.08,
                "rate_unit": "kg/hr",
                "reserve_fraction": 0.2,
            }
        ],
        "compute_reverse_return_route": True,
    }
    res_eval = client.post("/api/eva-operations/mission/evaluate", json=eval_payload)
    assert res_eval.status_code == 200, res_eval.text
    env = res_eval.json()
    mid = env["mission_id"]
    assert env["operational_safety_certified"] is False
    assert env["plan_version"] == 1
    assert env["model_feasibility_status"] in {
        EnvelopeFeasibilityStatus.FEASIBLE_UNDER_CONFIGURED_MODEL.value,
        EnvelopeFeasibilityStatus.INFEASIBLE_UNDER_CONFIGURED_MODEL.value,
    }
    assert env["telemetry_state"]["connection_status"] == "TELEMETRY NOT CONNECTED"
    assert env["environmental_context"]["live_weather_status"] == "LIVE SURFACE WEATHER UNAVAILABLE"
    assert len(env["traversability_analytics"]["unmeasured_soil_properties"]) == 6

    # Step 3: Sensitivity report endpoint
    res_sens = client.get(f"/api/eva-operations/mission/{mid}/sensitivity")
    assert res_sens.status_code == 200, res_sens.text
    sens = res_sens.json()
    assert sens["evaluated_scenario_count"] >= 4
    assert sens["plan_version"] == 1

    # Step 4: Record mission event -> check invalidation & staleness
    assert MissionEventType.WALKING_SPEED_CHANGED in EVENT_DEPENDENCY_INVALIDATION_MAP
    res_evt = client.post(
        f"/api/eva-operations/mission/{mid}/events",
        json={
            "event_type": "WALKING_SPEED_CHANGED",
            "operator_id": "flight_director_p20",
            "description": "Crew pace reduced on fractured ridge.",
            "payload": {"walking_speed_mps": 0.65},
        },
    )
    assert res_evt.status_code == 200, res_evt.text
    sess = res_evt.json()
    assert sess["stale"] is True
    assert sess["workflow_state"] == MissionWorkflowState.REPLANNING_REQUIRED.value

    # Step 5: Preview candidate replan -> reject once -> re-preview -> approve
    updated_cfg = dict(eval_payload)
    updated_cfg["mission_id"] = mid
    updated_cfg["walking_speed_mps"] = 0.65
    res_prev = client.post(
        f"/api/eva-operations/mission/{mid}/replan/preview",
        json={
            "operator_id": "flight_director_p20",
            "reason": "Evaluate slower walking pace",
            "updated_config": updated_cfg,
        },
    )
    assert res_prev.status_code == 200, res_prev.text
    comp = res_prev.json()
    assert comp["previous_plan_version"] == 1
    assert comp["candidate_plan_version"] == 2
    assert comp["total_mission_time_delta_s"] > 0.0

    res_rej = client.post(
        f"/api/eva-operations/mission/{mid}/replan/reject",
        json={"operator_id": "flight_director_p20", "note": "Checking rejection path"},
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["active_plan_version"] == 1

    res_prev2 = client.post(
        f"/api/eva-operations/mission/{mid}/replan/preview",
        json={
            "operator_id": "flight_director_p20",
            "reason": "Apply slower walking pace v2",
            "updated_config": updated_cfg,
        },
    )
    assert res_prev2.status_code == 200

    res_app = client.post(
        f"/api/eva-operations/mission/{mid}/replan/approve",
        json={"operator_id": "flight_director_p20", "note": "Approved candidate v3"},
    )
    assert res_app.status_code == 200, res_app.text
    approved_sess = res_app.json()
    assert approved_sess["active_plan_version"] == 3
    assert approved_sess["stale"] is False
    assert len(approved_sess["plan_history"]) >= 2

    # Step 6: Export SHA-256 Operations Dossier and verify digest integrity over core_payload
    res_dos = client.get(f"/api/eva-operations/mission/{mid}/dossier")
    assert res_dos.status_code == 200, res_dos.text
    dos = res_dos.json()
    digest = dos["sha256_integrity_digest"]
    assert len(digest) == 64
    core_payload = {
        "mission_id": dos["mission_id"],
        "plan_version": dos["plan_version"],
        "dataset_provenance": dos["dataset_provenance"],
        "configured_mission_inputs": dos["configured_mission_inputs"],
        "outbound_route_summary": dos["outbound_route_summary"],
        "return_plan_summary": dos["return_plan_summary"],
        "time_budget": dos["time_budget"],
        "energy_budget": dos["energy_budget"],
        "resource_budget": dos["resource_budget"],
    }
    recomputed = hashlib.sha256(
        json.dumps(core_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    assert recomputed == digest
