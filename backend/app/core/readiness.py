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
from typing import Any, Dict, List, Optional


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
    dataset_id: Optional[str] = None,
    question_id: Optional[str] = None,
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
    questions = list(science_investigation_service.list_questions())
    questions_count = len(questions)
    instruments_count = len(science_investigation_service.list_instruments())
    targets_count = len(list(target_registry.list_targets()))
    science_store_errors: List[str] = []
    campaigns_count = 0
    observations_count = 0
    try:
        campaigns_count = len(science_investigation_service.list_campaigns(include_freshness=False))
    except TypeError:
        try:
            campaigns_count = len(science_investigation_service.list_campaigns())
        except Exception as exc:
            science_store_errors.append(f"Campaign store error: {exc}")
    except Exception as exc:
        science_store_errors.append(f"Campaign store error: {exc}")
    try:
        observations_count = len(science_investigation_service.list_observations())
    except Exception as exc:
        science_store_errors.append(f"Observations store error: {exc}")
    if science_store_errors:
        degraded_reasons.extend(science_store_errors)

    science_definition_store_ok = questions_count > 0 and instruments_count > 0 and not science_store_errors
    science_pillar = {
        "ready": science_definition_store_ok and comp_ok,
        "definition_store_ready": science_definition_store_ok,
        "evidence_index_ready": comp_ok,
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

    if proc_dem_ready_count == 0:
        data_gaps.append(
            "No locally verified processed DEM is ready; spatial terrain analysis and route planning cannot execute until a DEM is ingested or acquired."
        )

    spatial_pillar = {
        "ready": geospatial_deps_ok and morph_store_ok and proc_dem_ready_count > 0,
        "libraries_ready": geospatial_deps_ok,
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
    from app.services.container import mission_db as _mission_db

    db_status = _mission_db.status()
    mission_pillar = {
        "ready": physics_ok and eva_store_ok and proc_dem_ready_count > 0 and bool(db_status.get("available")),
        "physics_model_ready": physics_ok,
        "physics_parameters_count": len(physics_params),
        "routing_executable_with_local_dem": proc_dem_ready_count > 0,
        "live_telemetry_connected": False,
        "eva_store_readable": eva_store_ok,
        "eva_sessions_count": eva_sessions_count,
        "mission_db_ready": bool(db_status.get("available")),
        "mission_db_backend": db_status.get("engine"),
        "mission_db_migrations": db_status.get("applied_migrations", []),
        "operator_token_configured": op_token_configured,
        "environment": str(getattr(settings, "ENVIRONMENT", "unknown")),
    }

    # ── 5. Optional Contextual Checks (dataset_id / question_id) ────────────────
    context_info: Optional[Dict[str, Any]] = None
    if dataset_id is not None or question_id is not None:
        contextual_blockers: List[str] = []
        ds_ready_flag: Optional[bool] = None
        ds_state: Optional[str] = None
        if dataset_id is not None:
            matched_ds = next((r for r in ds_rows if r.get("dataset_id") == dataset_id), None)
            if matched_ds is None:
                ds_ready_flag = False
                ds_state = "NOT_IN_CATALOG"
                contextual_blockers.append(f"Requested dataset '{dataset_id}' is not registered in the catalog.")
            else:
                ds_state = matched_ds.get("lifecycle_state")
                ds_ready_flag = bool(
                    matched_ds.get("processed_artifact_exists")
                    and matched_ds.get("processing_manifest_valid") is True
                    and ds_state != "CORRUPT"
                )
                if not ds_ready_flag:
                    contextual_blockers.append(
                        f"Dataset '{dataset_id}' is in state '{ds_state}' and is not ready for local terrain/routing execution."
                    )

        q_ready_flag: Optional[bool] = None
        if question_id is not None:
            matched_q = next((q for q in questions if q.question_id == question_id), None)
            if matched_q is None:
                q_ready_flag = False
                contextual_blockers.append(f"Requested science question '{question_id}' is not registered.")
            else:
                q_ready_flag = bool(science_definition_store_ok and comp_ok)
                if not comp_ok:
                    contextual_blockers.append(
                        f"Science question '{question_id}' requires a verified composition spatial index for candidate evaluation."
                    )

        context_info = {
            "dataset_id": dataset_id,
            "dataset_lifecycle_state": ds_state,
            "dataset_ready": ds_ready_flag,
            "question_id": question_id,
            "question_ready": q_ready_flag,
            "contextual_ready": len(contextual_blockers) == 0,
            "contextual_blockers": contextual_blockers,
        }

    # Distinguish application/runtime health from data gaps and mission execution availability
    stores_readable = (not science_store_errors) and morph_store_ok and eva_store_ok
    app_healthy = geospatial_deps_ok and physics_ok and stores_readable and (not corrupt_ids)

    if (
        degraded_reasons
        or not (science_definition_store_ok and geospatial_deps_ok and morph_store_ok and physics_ok and eva_store_ok)
    ):
        overall_state = "DEGRADED_OR_CORRUPT"
    elif data_gaps or not (data_pillar["ready"] and science_pillar["ready"] and spatial_pillar["ready"] and mission_pillar["ready"]):
        overall_state = "READY_WITH_DATA_GAPS"
    else:
        overall_state = "READY_FULL_WORKFLOW"

    return {
        "checked_at_utc": checked_at,
        "system_readiness_state": overall_state,
        "operational_safety_certified": False,
        "application_health": {
            "healthy": app_healthy,
            "status": "HEALTHY" if app_healthy else "DEGRADED",
            "stores_readable": stores_readable,
            "geospatial_libraries_available": geospatial_deps_ok,
            "physics_registry_ready": physics_ok,
        },
        "execution_readiness": {
            "ready": False,
            "status": "UNAVAILABLE",
            "telemetry_connected": False,
            "operational_safety_certified": False,
            "reason": (
                "No live astronaut physiological sensors, suit avionics telemetry, "
                "or certified Mars EVA flight safety loop is connected."
            ),
        },
        "context": context_info,
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
