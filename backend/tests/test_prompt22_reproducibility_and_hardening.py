"""
Prompt 22 Reproducibility, Data Integrity, Persistence & Cross-System Hardening Tests.

Covers Prompt 22 Section 13 test classes:
  - 13.1 Dataset Reproducibility & Corruption Detection
  - 13.2 Canonical Serialization, Dossier Content/Export Digests & NaN Rejection
  - 13.3 Atomic Persistence, Concurrent Locking, Corrupt JSON Recovery & HTTP 409 Conflicts
  - 13.4 Cross-System Invalidation Propagation (all 5 chains)
  - 13.6 Security Boundaries (Operator Auth, Path Traversal, Zero Secret Leak)
  - Section 12 4-Pillar System Readiness & 12-Property Dataset Readiness Audit
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

from fastapi.testclient import TestClient
import pytest

from app.core.persistence import atomic_write_json, atomic_write_text, locked_resource
from app.eva_operations.replanning import MissionEventIngestRequest, MissionEventType
from app.ingestion.bootstrap import verify_local_datasets
from app.ingestion.catalog import DatasetCatalogService
from app.main import app
from app.routing.schemas import RouteCoordinateInput, RoutingMode
from app.schemas.dataset import DatasetLifecycleStatus
from app.science.composition.index import CompositionSpatialIndex
from app.science.investigation.canonical import (
    canonicalize_value,
    compute_export_artifact_digest,
    compute_mission_content_digest,
    evaluate_dossier_reproducibility,
    verify_campaign_dossier,
)
from app.science.investigation.schemas import (
    CampaignBuildRequest,
    CampaignFreshnessState,
    RecordObservationRequest,
)
from app.services.container import PROCESSED_DIR, RAW_DIR, catalog_service, science_investigation_service


# ── 13.1 Dataset Reproducibility & Corruption Detection ─────────────────────────


def test_clean_checkout_dataset_reconciliation_and_bootstrap_verify(tmp_path: Path):
    """Simulate fresh Git checkout with empty datasets/raw and datasets/processed."""
    ds_root = tmp_path / "datasets"
    for sub in ("catalog", "manifests", "raw", "processed", "index"):
        (ds_root / sub).mkdir(parents=True, exist_ok=True)
    # Copy tracked catalog metadata and bootstrap manifest only
    repo_ds = Path(__file__).resolve().parents[2] / "datasets"
    shutil.copy2(repo_ds / "bootstrap_manifest.json", ds_root / "bootstrap_manifest.json")
    for jf in (repo_ds / "catalog").glob("*.json"):
        shutil.copy2(jf, ds_root / "catalog" / jf.name)

    cat = DatasetCatalogService(ds_root / "catalog", raw_data_dir=ds_root / "raw")
    idx = CompositionSpatialIndex(ds_root / "index" / "composition_index.sqlite")

    ver_non_strict = verify_local_datasets(datasets_dir=ds_root, strict=False)
    assert ver_non_strict.verified_count == 0
    assert ver_non_strict.missing_mandatory_count >= 1
    assert ver_non_strict.preflight_passed is True

    ver_strict = verify_local_datasets(datasets_dir=ds_root, strict=True)
    assert ver_strict.preflight_passed is False

    audit = cat.audit_dataset_readiness(composition_index=idx)
    assert audit["mandatory_gale_ready"] is False
    assert audit["index_available"] is False
    hirise_row = next(r for r in audit["datasets"] if r["dataset_id"] == "hirise_dteec_009149_1750")
    assert hirise_row["raw_file_exists"] is False
    assert hirise_row["lifecycle_state"] == "CHECKSUM_PINNED"
    assert hirise_row["checksum_status"]["checksum_source"] == "manifest_pinned"
    assert "bootstrap_datasets.py" in hirise_row["remediation_hint"]


def test_sha256_mismatch_and_corrupt_processing_manifest_rejected(tmp_path: Path):
    """Tampered raw size/checksum or corrupt .processing.json must mark CORRUPT / FAILED_*."""
    ds_root = tmp_path / "datasets"
    for sub in ("catalog", "manifests", "raw", "processed"):
        (ds_root / sub).mkdir(parents=True, exist_ok=True)

    raw_file = ds_root / "raw" / "fake_dtm.img"
    raw_file.write_bytes(b"PDS_VERSION_ID = PDS3\nEND\n")
    expected_sha = hashlib.sha256(b"ORIGINAL_EXPECTED_BYTES").hexdigest()

    cat_file = ds_root / "catalog" / "test_dtm.json"
    cat_file.write_text(
        json.dumps(
            {
                "id": "test_dtm",
                "product_id": "TEST_DTM_001",
                "product_title": "Test DTM",
                "product_type": "DEM",
                "mission": "MRO",
                "instrument": "HiRISE",
                "source_archive": "NASA PDS",
                "original_product_url": "https://hirise-pds.lpl.arizona.edu/test.img",
                "attribution": "NASA/JPL/UArizona",
                "coverage": {
                    "min_latitude": -5.0,
                    "max_latitude": -4.5,
                    "min_longitude": 137.3,
                    "max_longitude": 137.5,
                    "crs": "IAU2000:49900",
                },
                "file_size_bytes": len(raw_file.read_bytes()),
                "sha256_checksum": expected_sha,
                "local_file_path": "raw/fake_dtm.img",
                "status": "downloaded",
            }
        ),
        encoding="utf-8",
    )

    cat = DatasetCatalogService(ds_root / "catalog", raw_data_dir=ds_root / "raw")
    ds = cat.get_dataset("test_dtm")
    assert ds is not None
    assert ds.status == DatasetLifecycleStatus.FAILED_VALIDATION
    assert ds.sha256_checksum == expected_sha  # Never overwritten silently

    audit = cat.audit_dataset_readiness(verify_checksums=True)
    row = audit["datasets"][0]
    assert row["lifecycle_state"] == "CORRUPT"
    assert row["checksum_status"]["checksum_verified"] is False

    # Now fix raw sha256 to match bytes, but supply corrupt .processing.json
    real_sha = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    cat_payload = json.loads(cat_file.read_text(encoding="utf-8"))
    cat_payload["sha256_checksum"] = real_sha
    cat_payload["processed_file_path"] = "processed/test_dtm_dem.tif"
    cat_payload["status"] = "processed"
    cat_file.write_text(json.dumps(cat_payload), encoding="utf-8")
    (ds_root / "processed" / "test_dtm_dem.tif").write_bytes(b"II*\x00fake")
    (ds_root / "processed" / "test_dtm.processing.json").write_text("{CORRUPT_JSON", encoding="utf-8")

    cat2 = DatasetCatalogService(ds_root / "catalog", raw_data_dir=ds_root / "raw")
    ds2 = cat2.get_dataset("test_dtm")
    assert ds2 is not None
    assert ds2.status == DatasetLifecycleStatus.FAILED_PROCESSING
    assert ds2.processed_file_path is None


def test_composition_index_failed_rebuild_preserves_previous_generation(tmp_path: Path):
    """A staged index build failure must preserve the previous active generation intact."""
    from app.science.composition.index import compute_deterministic_evidence_id
    from app.science.composition.models import (
        CompositionEvidence,
        EvidenceStatus,
        EvidenceType,
        LocationSemanticType,
        SpeciesCategory,
    )

    idx_dir = tmp_path / "index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    idx = CompositionSpatialIndex(idx_dir / "composition_index.sqlite")

    ev = CompositionEvidence(
        evidence_id="ev_p22_001",
        source_dataset_id="msl_apxs",
        product_id="DS01_TEST",
        source_record_ref="row_1",
        instrument_id="APXS",
        instrument_name="Alpha Particle X-Ray Spectrometer",
        processing_level="RDR",
        calibration_status="calibrated",
        target_name="P22_Rock",
        sol=100,
        canonical_species_id="sio2",
        canonical_species_name="Silica",
        raw_species_name="SiO2",
        species_category=SpeciesCategory.OXIDE,
        evidence_type=EvidenceType.OXIDE_COMPOSITION_MEASUREMENT,
        evidence_status=EvidenceStatus.MEASURED,
        raw_value=48.2,
        raw_unit="wt%",
        normalized_value=48.2,
        normalized_unit="wt%",
        uncertainty_value=0.5,
        location_semantic_type=LocationSemanticType.INSTRUMENT_TARGET_LOCATION,
        latitude=-4.75,
        longitude_east=137.41,
        coordinate_reference_system="IAU2000:49900",
        location_verified=True,
        methodology="APXS calibrated oxide test record",
        source_reference="NASA PDS MSL APXS",
    )
    ev = ev.model_copy(update={"evidence_id": compute_deterministic_evidence_id(ev)})

    res1 = idx.publish_generation([ev], [])
    gen1 = res1.active_generation_id
    assert gen1 is not None

    with pytest.raises(RuntimeError, match="Simulated failure"):
        idx.publish_generation(
            [ev],
            [],
            failure_stage="before_db_commit",
        )

    st_after = idx.get_status()
    assert st_after.active_generation_id == gen1
    assert st_after.checksum_valid is True


# ── 13.2 Canonical Serialization & Dossier Verification ───────────────────────


def test_canonical_dossier_digest_invariance_tamper_and_nan_rejection():
    base_dossier = {
        "dossier_version": "3.1.0-p22",
        "exported_at_utc": "2026-11-15T01:00:00+00:00",
        "operational_safety_certified": False,
        "campaign_id": "camp_demo",
        "plan_version": 2,
        "freshness": {
            "freshness_state": "current",
            "checked_at_utc": "2026-11-15T01:00:00+00:00",
            "stored_signature": "abc",
            "current_signature": "abc",
            "staleness_reasons": [],
        },
        "campaign": {
            "b": 2,
            "a": 1.5,
            "dependency_signature": "sig_test_123",
            "dependency_snapshot": {
                "dataset": {
                    "raw_file": {"exists": True},
                    "processed_file": {"exists": True},
                }
            },
            "constraint_evaluation_complete": True,
        },
        "provenance_graph": {"input_datasets": ["hirise_dteec_009149_1750"]},
        "missing_inputs": [],
        "uncertainty_and_gaps": [],
    }
    variant_dossier = {
        "dossier_version": "3.1.0-p22",
        "exported_at_utc": "2026-11-16T09:30:00+00:00",  # Volatile export timestamp changed
        "operational_safety_certified": False,
        "campaign_id": "camp_demo",
        "plan_version": 2,
        "freshness": {
            "checked_at_utc": "2026-11-16T09:30:00+00:00",  # Volatile check timestamp changed
            "current_signature": "abc",
            "freshness_state": "current",
            "staleness_reasons": [],
            "stored_signature": "abc",
        },
        "campaign": {
            "a": 1.5,
            "b": 2,
            "constraint_evaluation_complete": True,
            "dependency_signature": "sig_test_123",
            "dependency_snapshot": {
                "dataset": {
                    "processed_file": {"exists": True},
                    "raw_file": {"exists": True},
                }
            },
        },
        "provenance_graph": {"input_datasets": ["hirise_dteec_009149_1750"]},
        "missing_inputs": [],
        "uncertainty_and_gaps": [],
    }
    d1 = compute_mission_content_digest(base_dossier)
    d2 = compute_mission_content_digest(variant_dossier)
    assert d1 == d2

    base_dossier["mission_content_digest"] = d1
    base_dossier["sha256_integrity_digest"] = d1
    base_dossier["export_artifact_digest"] = compute_export_artifact_digest(base_dossier)

    ok_rep = verify_campaign_dossier(base_dossier)
    assert ok_rep["valid"] is True
    assert ok_rep["content_digest_valid"] is True
    assert ok_rep["export_digest_valid"] is True

    tampered = dict(base_dossier)
    tampered["plan_version"] = 999
    bad_rep = verify_campaign_dossier(tampered)
    assert bad_rep["valid"] is False
    assert bad_rep["content_digest_valid"] is False

    status_label, warnings = evaluate_dossier_reproducibility({"operational_safety_certified": True})
    assert status_label == "NOT_REPRODUCIBLE_UNVERIFIED_DATA"
    assert warnings

    with pytest.raises(ValueError, match="Non-finite"):
        canonicalize_value({"bad_val": float("nan")})
    with pytest.raises(ValueError, match="Non-finite"):
        canonicalize_value({"bad_inf": float("inf")})


# ── 13.3 Atomic Persistence, Locking & Optimistic Concurrency ──────────────────


def test_atomic_persistence_reentrant_and_concurrent_locking(tmp_path: Path):
    target = tmp_path / "state.json"
    lock_file = tmp_path / ".state.lock"
    atomic_write_json(target, {"count": 0})

    # Re-entrant same-thread lock must not deadlock
    with locked_resource(lock_file):
        with locked_resource(lock_file):
            data = json.loads(target.read_text(encoding="utf-8"))
            data["count"] += 1
            atomic_write_json(target, data)

    # NaN rejection preserves prior file cleanly without leaving tmp files
    with pytest.raises(ValueError):
        atomic_write_json(target, {"count": float("nan")})
    assert json.loads(target.read_text(encoding="utf-8"))["count"] == 1

    # Concurrent worker threads incrementing cleanly
    def _bump(_: int) -> None:
        with locked_resource(lock_file):
            cur = json.loads(target.read_text(encoding="utf-8"))
            cur["count"] += 1
            atomic_write_json(target, cur)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_bump, range(18)))

    assert json.loads(target.read_text(encoding="utf-8"))["count"] == 19
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_campaign_json_raises_and_idempotency_conflict_returns_409():
    client = TestClient(app)
    corrupt_id = f"corrupt_p22_{uuid.uuid4().hex[:6]}"
    corrupt_path = science_investigation_service._campaign_path(corrupt_id)
    atomic_write_text(corrupt_path, "{INVALID_JSON")
    try:
        r = client.get(f"/api/science-investigation/campaigns/{corrupt_id}")
        assert r.status_code == 422
        assert "Corrupted persisted science campaign JSON" in r.text
    finally:
        corrupt_path.unlink(missing_ok=True)

    sub_id = f"p22_obs_idem_{uuid.uuid4().hex[:8]}"
    payload_a = {
        "instrument_id": "CHEMCAM",
        "measurement_type": "libs_oxide",
        "species_or_feature": "CaO",
        "measured_value": 12.4,
        "units": "wt%",
        "latitude": -4.75,
        "longitude_east": 137.41,
        "observer_identity": "crew_p22",
        "client_submission_id": sub_id,
    }
    r1 = client.post("/api/science-investigation/observations", json=payload_a)
    assert r1.status_code == 201
    obs_id = r1.json()["observation_id"]

    # Exact replay returns same observation_id
    r_same = client.post("/api/science-investigation/observations", json=payload_a)
    assert r_same.status_code == 201
    assert r_same.json()["observation_id"] == obs_id

    # Altered payload with same client_submission_id -> 409 Conflict
    payload_diff = {**payload_a, "measured_value": 99.9}
    r_conflict = client.post("/api/science-investigation/observations", json=payload_diff)
    assert r_conflict.status_code == 409

    # Clean up synthetic test observation from persisted store
    with locked_resource(science_investigation_service._observations_lock()):
        obs_map = science_investigation_service._load_observations_map()
        if obs_id in obs_map:
            obs_map.pop(obs_id)
            science_investigation_service._save_observations_map(obs_map)


# ── 13.4 Cross-System Invalidation & Optimistic Plan Versioning ───────────────


def test_campaign_stale_propagation_version_conflict_and_dossier_verify():
    ds = catalog_service.get_dataset("hirise_dteec_009149_1750")
    if not (ds and ds.processed_file_path and (RAW_DIR.parent / ds.processed_file_path).exists()):
        pytest.skip("hirise_dteec_009149_1750 processed DEM not locally present.")

    cid = f"camp_p22_{uuid.uuid4().hex[:6]}"
    plan = science_investigation_service.build_campaign(
        CampaignBuildRequest(
            campaign_id=cid,
            campaign_name="Prompt 22 Verification Campaign",
            question_id="gale_boxwork_origin",
            dataset_id="hirise_dteec_009149_1750",
            start=RouteCoordinateInput(lat=-4.765, lon_east=137.415, label="Hab"),
            routing_mode=RoutingMode.BALANCED,
            walking_speed_mps=0.8,
            mission_duration_limit_s=18000,
            return_reserve_fraction=0.25,
            default_stop_dwell_s=600,
        )
    )
    assert plan.plan_version == 1

    # Optimistic concurrency conflict (stale expected_plan_version)
    with pytest.raises(LookupError, match="Plan version conflict"):
        science_investigation_service.approve_campaign(
            cid, operator_id="qa_op", expected_plan_version=99
        )

    # Approve v1 then propagate external invalidation -> transitions to STALE
    approved = science_investigation_service.approve_campaign(
        cid, operator_id="qa_op", expected_plan_version=1
    )
    assert approved.operator_approved is True

    affected = science_investigation_service.propagate_external_invalidation(
        source_type="composition_index_rebuilt",
        description="Synthetic P22 test invalidation",
        dataset_id="hirise_dteec_009149_1750",
    )
    assert cid in affected
    fresh = science_investigation_service.check_campaign_freshness(cid)
    assert fresh.freshness_state == CampaignFreshnessState.STALE_UPSTREAM_DEPENDENCY_CHANGED

    # Cannot approve stale campaign without recompute
    with pytest.raises(ValueError, match="Cannot approve stale campaign"):
        science_investigation_service.approve_campaign(cid, operator_id="qa_op", expected_plan_version=1)

    recomputed = science_investigation_service.recompute_campaign(cid, expected_plan_version=1)
    assert recomputed.plan_version == 2
    assert recomputed.operator_approved is False

    # Export canonical unified dossier & verify via POST /dossiers/verify
    client = TestClient(app)
    exp = client.get(f"/api/science-investigation/campaigns/{cid}/unified-dossier")
    assert exp.status_code == 200
    dossier = exp.json()
    assert dossier["mission_content_digest"] == dossier["sha256_integrity_digest"]
    assert "export_artifact_digest" in dossier

    ver = client.post("/api/science-investigation/dossiers/verify", json={"dossier": dossier})
    assert ver.status_code == 200
    assert ver.json()["valid"] is True

    # Clean up test artifacts
    science_investigation_service._campaign_path(cid).unlink(missing_ok=True)
    if plan.linked_mission_id and science_investigation_service.eva_operations_service:
        sess_path = science_investigation_service.eva_operations_service.sessions_dir / f"{plan.linked_mission_id}.json"
        sess_path.unlink(missing_ok=True)


# ── 13.6 Security, Auth & Readiness Audit ─────────────────────────────────────


def test_security_auth_path_traversal_and_readiness_endpoints(monkeypatch: pytest.MonkeyPatch):
    client = TestClient(app)

    # 1. Fail-closed auth on protected orchestration invalidation & index rebuild + no secret leak
    secret_token = "p22_secret_operator_token_9988"
    monkeypatch.setenv("MARSCOPE_OPERATOR_TOKEN", secret_token)

    r_unauth = client.post(
        "/api/science-investigation/orchestration/invalidate",
        json={"source_type": "manual_test", "description": "Auth check"},
    )
    assert r_unauth.status_code == 401
    assert secret_token not in r_unauth.text

    r_bad = client.post(
        "/api/composition/index/rebuild",
        headers={"X-Mars-Operator-Token": "wrong_token"},
    )
    assert r_bad.status_code == 403
    assert secret_token not in r_bad.text

    # 2. Readiness audit endpoints (Section 12) never leak secret token
    r_ready = client.get("/api/health/readiness")
    assert r_ready.status_code == 200
    ready_body = r_ready.json()
    assert set(ready_body["pillars"].keys()) == {"data", "science", "spatial", "mission"}
    assert ready_body["pillars"]["mission"]["operator_token_configured"] is True
    assert secret_token not in r_ready.text

    r_ds_audit = client.get("/api/datasets/readiness-audit?verify_checksums=false")
    assert r_ds_audit.status_code == 200
    audit_body = r_ds_audit.json()
    assert audit_body["total_catalog_datasets"] >= 1
    assert secret_token not in r_ds_audit.text

    # 3. Imagery path traversal guard on /api/imagery/products/{id}/image
    from app.api import imagery as imagery_api
    from app.schemas.imagery import ImageryProduct

    fake_pid = f"p22_trav_{uuid.uuid4().hex[:6]}"
    rec = ImageryProduct(
        product_id=fake_pid,
        source_archive="pds_atlas",
        mission="MSL",
        instrument="NAVCAM",
        dataset_id="MSL-TEST",
        local_file_path="/etc/passwd",
        source_payload={},
    )
    orig_get = imagery_api.service.get
    monkeypatch.setattr(
        imagery_api.service,
        "get",
        lambda pid: rec if pid == fake_pid else orig_get(pid),
    )
    r_trav = client.get(f"/api/imagery/products/{fake_pid}/image")
    assert r_trav.status_code == 403
    assert "outside_allowed_directory" in r_trav.text
