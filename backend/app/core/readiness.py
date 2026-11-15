"""
MARSCOPE Operational Health & 4-Pillar System Readiness Evaluator (Prompt 22 Section 12).

Evaluates genuine runtime capability across:
  1. Data Readiness (bootstrap manifest, local raw/processed assets, companion labels, composition index)
  2. Science Readiness (instrument registry, questions, targets, readable campaign/observation stores)
  3. Spatial Readiness (rasterio/GDAL/pyproj/shapely, Mars IAU2000 CRS, processed terrain DEMs, morphology store)
  4. Mission Readiness (physics parameter registry, routing capability vs local DEM presence, EVA store, operator auth config)

Never fakes availability, mutates state, or leaks secrets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Dict, List


def evaluate_system_readiness(
    *,
    catalog_service: Any,
    composition_index: Any,
    science_investigation_service: Any,
    eva_operations_service: Any,
    morphology_service: Any,
    target_registry: Any,
    settings: Any,
    verify_checksums: bool = False,
) -> Dict[str, Any]:
    checked_at = datetime.now(timezone.utc).isoformat()
    degraded_reasons: List[str] = []
    data_gaps: List[str] = []

    # ── 1. Data Readiness ───────────────────────────────────────────────────────
    audit = catalog_service.audit_dataset_readiness(
        composition_index=composition_index,
        verify_checksums=verify_checksums,
    )
    ds_rows = audit.get("datasets", [])
    corrupt_ids = [r["dataset_id"] for r in ds_rows if r["lifecycle_state"] == "CORRUPT"]
    missing_comp_ids = [r["dataset_id"] for r in ds_rows if r["lifecycle_state"] == "MISSING_COMPANION_FILES"]
    raw_present_count = sum(1 for r in ds_rows if r["raw_file_exists"])
    proc_dem_ready_count = sum(
        1 for r in ds_rows if r["processed_artifact_exists"] and r["processing_manifest_valid"] is True
    )
    if corrupt_ids:
        degraded_reasons.append(f"Corrupt or mismatched dataset artifacts: {', '.join(corrupt_ids)}.")
    if missing_comp_ids:
        data_gaps.append(f"Companion files missing for: {', '.join(missing_comp_ids)}.")
    if not audit.get("mandatory_gale_ready"):
        data_gaps.append(
            "Mandatory Gale Crater workflow products are not all locally verified; "
            "run `python3 scripts/bootstrap_datasets.py --acquire --mandatory-only`."
        )
    comp_st = composition_index.get_status() if composition_index else None
    comp_ok = bool(comp_st and getattr(comp_st, "index_available", False) and getattr(comp_st, "checksum_valid", False))
    if not comp_ok:
        data_gaps.append(
            "Composition spatial index unavailable or unverified; run `python3 scripts/bootstrap_datasets.py --rebuild-index`."
        )

    data_pillar = {
        "ready": (not corrupt_ids) and bool(audit.get("mandatory_gale_ready")) and comp_ok,
        "total_catalog_datasets": audit["total_catalog_datasets"],
        "local_raw_present_count": raw_present_count,
        "processed_dem_ready_count": proc_dem_ready_count,
        "mandatory_gale_ready": bool(audit.get("mandatory_gale_ready")),
        "corrupt_dataset_ids": corrupt_ids,
        "missing_companion_dataset_ids": missing_comp_ids,
        "composition_index_available": bool(getattr(comp_st, "index_available", False)) if comp_st else False,
        "composition_index_checksum_valid": bool(getattr(comp_st, "checksum_valid", False)) if comp_st else False,
        "active_index_generation": getattr(comp_st, "active_generation_id", None) if comp_st else None,
        "lifecycle_state_counts": audit.get("lifecycle_state_counts", {}),
    }

    # ── 2. Science Readiness ────────────────────────────────────────────────────
    questions_count = len(science_investigation_service.list_questions())
    instruments_count = len(science_investigation_service.list_instruments())
    targets_count = len(list(target_registry.list_targets()))
    science_store_errors: List[str] = []
    campaigns_count = 0
    observations_count = 0
    try:
        campaigns_count = len(science_investigation_service.list_campaigns())
    except Exception as exc:
        science_store_errors.append(f"Campaign store error: {exc}")
    try:
        observations_count = len(science_investigation_service.list_observations())
    except Exception as exc:
        science_store_errors.append(f"Observations store error: {exc}")
    if science_store_errors:
        degraded_reasons.extend(science_store_errors)

    science_pillar = {
        "ready": questions_count > 0 and instruments_count > 0 and not science_store_errors,
        "instruments_registered": instruments_count,
        "questions_registered": questions_count,
        "targets_registered": targets_count,
        "persisted_campaigns_count": campaigns_count,
        "persisted_observations_count": observations_count,
        "store_errors": science_store_errors,
    }

    # ── 3. Spatial Readiness ────────────────────────────────────────────────────
    geospatial_deps_ok = True
    geospatial_error = None
    try:
        import rasterio  # noqa: F401
        import pyproj  # noqa: F401
        import shapely  # noqa: F401
    except Exception as exc:
        geospatial_deps_ok = False
        geospatial_error = str(exc)
        degraded_reasons.append(f"Geospatial dependencies unavailable: {exc}")

    morph_store_ok = True
    morph_reviews_count = 0
    if morphology_service is not None and getattr(morphology_service, "review_store", None) is not None:
        try:
            morph_reviews_count = len(morphology_service.review_store.load_all())
        except Exception as exc:
            morph_store_ok = False
            degraded_reasons.append(f"Morphology store corrupted: {exc}")

    spatial_pillar = {
        "ready": geospatial_deps_ok and morph_store_ok,
        "geospatial_libraries_available": geospatial_deps_ok,
        "geospatial_error": geospatial_error,
        "processed_dem_ready_count": proc_dem_ready_count,
        "morphology_store_readable": morph_store_ok,
        "morphology_reviews_count": morph_reviews_count,
        "planetary_datum": "Mars IAU2000 (3396190m / 3376200m)",
    }

    # ── 4. Mission Readiness ────────────────────────────────────────────────────
    from app.physics.registry.parameters import list_parameters

    physics_params = list_parameters()
    physics_ok = len(physics_params) >= 8
    if not physics_ok:
        degraded_reasons.append("Physics parameter registry incomplete.")

    eva_store_ok = True
    eva_sessions_count = 0
    try:
        eva_sessions_count = len(eva_operations_service.list_sessions())
    except Exception as exc:
        eva_store_ok = False
        degraded_reasons.append(f"EVA session store corrupted: {exc}")

    op_token_configured = bool(
        (os.getenv("MARSCOPE_OPERATOR_TOKEN") or "").strip()
        or str(getattr(settings, "OPERATOR_ACTION_TOKEN", "") or "").strip()
    )
    mission_pillar = {
        "ready": physics_ok and eva_store_ok,
        "physics_parameters_count": len(physics_params),
        "routing_executable_with_local_dem": proc_dem_ready_count > 0,
        "eva_store_readable": eva_store_ok,
        "eva_sessions_count": eva_sessions_count,
        "operator_token_configured": op_token_configured,
        "environment": str(getattr(settings, "ENVIRONMENT", "unknown")),
    }

    if degraded_reasons or not (science_pillar["ready"] and spatial_pillar["ready"] and mission_pillar["ready"]):
        overall_state = "DEGRADED_OR_CORRUPT"
    elif data_gaps or not data_pillar["ready"]:
        overall_state = "READY_WITH_DATA_GAPS"
    else:
        overall_state = "READY_FULL_WORKFLOW"

    return {
        "checked_at_utc": checked_at,
        "system_readiness_state": overall_state,
        "operational_safety_certified": False,
        "degraded_reasons": degraded_reasons,
        "data_gaps": data_gaps,
        "pillars": {
            "data": data_pillar,
            "science": science_pillar,
            "spatial": spatial_pillar,
            "mission": mission_pillar,
        },
        "dataset_readiness_audit": audit,
    }
