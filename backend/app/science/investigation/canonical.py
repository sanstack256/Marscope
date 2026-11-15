"""
MARSCOPE Canonical Dossier Serialization & Integrity Verification Engine (Prompt 22 Section 4).

Separates:
  - `mission_content_digest`: Deterministic SHA-256 over canonicalized substantive mission
    content (excluding volatile export metadata like `exported_at_utc`, random `dossier_id`,
    and live freshness/telemetry wall-clock check timestamps).
  - `export_artifact_digest`: SHA-256 over the exact serialized export payload bytes/artifact
    (excluding only `export_artifact_digest` itself when stored inline, or exact raw file bytes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONTENT_DIGEST_SCHEMA_VERSION = "p22_canonical_content_v1"

_VOLATILE_TOP_LEVEL_KEYS = {
    "dossier_id",
    "exported_at_utc",
    "sha256_integrity_digest",
    "mission_content_digest",
    "export_artifact_digest",
    "export_metadata",
    "content_digest_schema_version",
    "reproducibility_status",
    "reproducibility_warnings",
}

_VOLATILE_NESTED_KEYS = {
    "checked_at_utc",
    "discovered_at_utc",
    "evaluated_at_utc",
    "generated_at_utc",
    "exported_at_utc",
    "dossier_id",
    "sha256_integrity_digest",
    "mission_content_digest",
    "export_artifact_digest",
}


def canonicalize_value(value: Any, *, _path: str = "$") -> Any:
    """
    Normalize Python/Pydantic structures into strictly deterministic JSON-compatible types.
    Rejects NaN, +Inf, and -Inf explicitly instead of emitting non-standard JSON tokens.
    """
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Non-finite floating-point value at '{_path}' is prohibited.")
        if value == 0.0:
            return 0.0
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Non-finite Decimal value at '{_path}' is prohibited.")
        return float(value)
    if isinstance(value, Enum):
        return canonicalize_value(value.value, _path=_path)
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (set, frozenset)):
        normalized_items = [canonicalize_value(v, _path=f"{_path}[]") for v in value]
        return sorted(normalized_items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
    if isinstance(value, (list, tuple)):
        return [canonicalize_value(v, _path=f"{_path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k in sorted(value.keys(), key=lambda key: str(key)):
            ks = str(k)
            out[ks] = canonicalize_value(value[k], _path=f"{_path}.{ks}")
        return out
    if hasattr(value, "model_dump"):
        return canonicalize_value(value.model_dump(mode="json"), _path=_path)
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize `value` into deterministic UTF-8 canonical JSON bytes (sorted keys, allow_nan=False)."""
    normalized = canonicalize_value(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _strip_volatile_fields(node: Any, *, top_level: bool = False) -> Any:
    if isinstance(node, list):
        return [_strip_volatile_fields(item, top_level=False) for item in node]
    if not isinstance(node, dict):
        return node
    skip = _VOLATILE_TOP_LEVEL_KEYS if top_level else _VOLATILE_NESTED_KEYS
    cleaned: Dict[str, Any] = {}
    for k, v in node.items():
        ks = str(k)
        if ks in skip:
            continue
        cleaned[ks] = _strip_volatile_fields(v, top_level=False)
    return cleaned


def extract_substantive_mission_content(dossier_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return canonical substantive mission content excluding volatile export/wall-clock metadata."""
    stripped = _strip_volatile_fields(dossier_payload, top_level=True)
    return canonicalize_value(stripped)


def compute_mission_content_digest(dossier_payload: Dict[str, Any]) -> str:
    """Compute stable SHA-256 digest of substantive mission content (excludes volatile export metadata)."""
    substantive = extract_substantive_mission_content(dossier_payload)
    return hashlib.sha256(canonical_json_bytes(substantive)).hexdigest()


def compute_export_artifact_digest(dossier_payload: Dict[str, Any]) -> str:
    """Compute SHA-256 over the canonical serialized export payload including export metadata."""
    export_view = {
        k: v for k, v in dossier_payload.items() if k != "export_artifact_digest"
    }
    return hashlib.sha256(canonical_json_bytes(export_view)).hexdigest()


def evaluate_dossier_reproducibility(dossier_payload: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Honest assessment of whether a dossier supports full reconstruction from available inputs.
    Never claims FULL_REPRODUCIBLE if raw/processed source artifacts are absent, constraints
    are incomplete, or dependencies are stale.
    """
    warnings: List[str] = []
    camp = dossier_payload.get("campaign") or {}
    freshness = dossier_payload.get("freshness") or {}
    snap = camp.get("dependency_snapshot") or {}
    ds_snap = snap.get("dataset") or {}
    raw_fp = ds_snap.get("raw_file")
    proc_fp = ds_snap.get("processed_file")

    if dossier_payload.get("operational_safety_certified") is True:
        warnings.append("Invalid safety certification flag: MARSCOPE never certifies operational safety.")
        return "NOT_REPRODUCIBLE_UNVERIFIED_DATA", warnings

    if not raw_fp or raw_fp.get("exists") is False:
        warnings.append("Underlying raw source dataset file is missing or not locally verified.")
    if not proc_fp or proc_fp.get("exists") is False:
        warnings.append("Underlying processed terrain artifact is missing or not locally verified.")
    fstate = str(freshness.get("freshness_state") or "")
    if fstate and fstate.upper() != "CURRENT":
        warnings.append(f"Campaign dependencies are stale ({fstate}).")
    if camp.get("constraint_evaluation_complete") is False or dossier_payload.get("missing_inputs"):
        warnings.append("Mission constraint evaluation is incomplete due to missing explicit user/scientific inputs.")

    # Check if discovery flagged missing/unacquired mandatory artifacts or CRISM unavailability
    ev_disc = dossier_payload.get("evidence_discovery") or {}
    for req_ev in ev_disc.get("requirements_evaluation") or []:
        fstate = str(req_ev.get("fulfillment_state") or "")
        if "missing" in fstate.lower() or "cannot_be_verified" in fstate.lower():
            warnings.append(
                f"Requirement '{req_ev.get('requirement_id')}' remains '{fstate}'."
            )

    if any("stale" in w.lower() or "incomplete" in w.lower() for w in warnings):
        status = "NOT_REPRODUCIBLE_STALE_OR_INCOMPLETE"
    elif any("missing" in w.lower() or "absent" in w.lower() for w in warnings):
        status = "PARTIAL_MISSING_SOURCE_ARTIFACTS"
    else:
        status = "FULL_REPRODUCIBLE"
    return status, warnings


def verify_campaign_dossier(
    dossier_payload: Dict[str, Any],
    *,
    raw_artifact_bytes: Optional[bytes] = None,
    expected_artifact_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify canonical dossier schema, mission content digest, export artifact digest,
    provenance references, dependency signatures, missing sources, stale state, and
    incomplete constraints.
    """
    errors: List[str] = []
    warnings: List[str] = []

    schema_ver = dossier_payload.get("dossier_version") or dossier_payload.get("dossier_schema_version")
    if not schema_ver:
        errors.append("Missing dossier schema version.")

    campaign_id = dossier_payload.get("campaign_id")
    linked_mission_id = dossier_payload.get("linked_mission_id") or dossier_payload.get("mission_id")
    plan_version = dossier_payload.get("plan_version")
    if not campaign_id and not linked_mission_id:
        errors.append("Missing mission/campaign identity.")
    if plan_version is None:
        errors.append("Missing plan_version.")

    # Validate canonical finiteness (raises on NaN/Inf)
    try:
        canonical_json_bytes(dossier_payload)
    except ValueError as exc:
        errors.append(f"Canonical serialization rejected payload: {exc}")

    recomputed_content_digest: Optional[str] = None
    recomputed_export_digest: Optional[str] = None
    content_digest_valid: Optional[bool] = None
    export_digest_valid: Optional[bool] = None
    raw_bytes_valid: Optional[bool] = None

    if not errors:
        recomputed_content_digest = compute_mission_content_digest(dossier_payload)
        recorded_content = dossier_payload.get("mission_content_digest") or dossier_payload.get("sha256_integrity_digest")
        if recorded_content is None:
            content_digest_valid = False
            errors.append("Missing mission_content_digest / sha256_integrity_digest.")
        else:
            content_digest_valid = str(recorded_content).lower() == recomputed_content_digest.lower()
            if not content_digest_valid:
                errors.append(
                    f"mission_content_digest mismatch: expected '{recorded_content}', computed '{recomputed_content_digest}'."
                )

        recomputed_export_digest = compute_export_artifact_digest(dossier_payload)
        recorded_export = dossier_payload.get("export_artifact_digest")
        if recorded_export is not None:
            export_digest_valid = str(recorded_export).lower() == recomputed_export_digest.lower()
            if not export_digest_valid:
                errors.append(
                    f"export_artifact_digest mismatch: expected '{recorded_export}', computed '{recomputed_export_digest}'."
                )

        if raw_artifact_bytes is not None:
            actual_raw_sha = hashlib.sha256(raw_artifact_bytes).hexdigest()
            if expected_artifact_sha256:
                raw_bytes_valid = actual_raw_sha.lower() == expected_artifact_sha256.strip().lower()
                if not raw_bytes_valid:
                    errors.append(
                        f"Supplied raw artifact bytes SHA-256 mismatch: expected '{expected_artifact_sha256}', got '{actual_raw_sha}'."
                    )
            else:
                raw_bytes_valid = True

    prov = dossier_payload.get("provenance_graph") or dossier_payload.get("dataset_provenance")
    if not prov:
        errors.append("Missing provenance references (provenance_graph / dataset_provenance).")
    camp = dossier_payload.get("campaign") or {}
    if isinstance(camp, dict) and camp and not camp.get("dependency_signature"):
        errors.append("Missing campaign dependency_signature.")

    repro_status, repro_warnings = evaluate_dossier_reproducibility(dossier_payload)
    warnings.extend(repro_warnings)

    return {
        "valid": len(errors) == 0,
        "schema_version": schema_ver,
        "content_digest_schema_version": dossier_payload.get(
            "content_digest_schema_version", CONTENT_DIGEST_SCHEMA_VERSION
        ),
        "campaign_id": campaign_id,
        "linked_mission_id": linked_mission_id,
        "plan_version": plan_version,
        "content_digest_valid": content_digest_valid,
        "recomputed_mission_content_digest": recomputed_content_digest,
        "export_digest_valid": export_digest_valid,
        "recomputed_export_artifact_digest": recomputed_export_digest,
        "raw_bytes_valid": raw_bytes_valid,
        "reproducibility_status": repro_status,
        "errors": errors,
        "warnings": warnings,
    }
