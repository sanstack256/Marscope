"""
MARSCOPE Multi-Instrument Target Evidence Evaluator
Prompt 17 & 18: Evaluates registered ScienceTargets and spatially bounded candidate
locations against a ScienceQuestionDefinition, computing the 7-state epistemic
InvestigationTargetEvidenceState, separated evidence/relevance/priority/utility/confidence,
spatial registration status, explicit Known/Inferred/Unknown/Conflict lists, and strict
candidate eligibility gating (ELIGIBLE_CANDIDATE | CANDIDATE_WITH_LIMITATIONS | REJECTED_FOR_CAMPAIGN).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from app.geospatial.crs import evaluate_spatial_registration, validate_mars_crs
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.schemas.dataset import DatasetLifecycleStatus
from app.schemas.target import InvestigationTargetEvidenceState, ScienceTarget
from app.science.composition.search import StructuredCompositionQuery
from app.science.composition.species import list_all_species
from app.science.investigation.requirements import _classify_dataset_instrument
from app.science.investigation.schemas import (
    CandidateTargetEvaluation,
    EvidenceEligibilityState,
    ScienceQuestionDefinition,
    SpatialRegistrationState,
    TargetEvaluationBatchResponse,
    TargetEvaluationRequest,
)


_IN_SITU_INSTRUMENTS = {
    "CHEMCAM",
    "CHEMCAM_LIBS",
    "APXS",
    "CHEMIN",
    "CHEMIN_XRD",
    "SAM",
    "SAM_EGA_GCMS",
    "MASTCAM",
    "MAHLI",
    "REMS",
}
_ORBITAL_SPECTRAL = {"CRISM", "THEMIS", "OMEGA"}


def _covers_point(ds: Any, lat: float, lon_east: float) -> bool:
    cov = getattr(ds, "coverage", None)
    if cov is None:
        return False
    lon_360 = lon_east % 360.0
    min_lon = float(cov.min_longitude) % 360.0
    max_lon = float(cov.max_longitude) % 360.0
    if not (float(cov.min_latitude) <= lat <= float(cov.max_latitude)):
        return False
    if min_lon <= max_lon:
        return min_lon <= lon_360 <= max_lon
    return lon_360 >= min_lon or lon_360 <= max_lon


def _is_gale_coordinate(lat: float, lon_east: float) -> bool:
    lon360 = lon_east % 360.0
    return -6.5 <= lat <= -3.5 and 136.5 <= lon360 <= 138.8


def _compute_heuristic_priority(
    *,
    evidence_state: InvestigationTargetEvidenceState,
    aligned_phenomena_count: int,
    nearest_distance_m: Optional[float],
    distinct_instrument_count: int,
    has_highres_dtm_coverage: bool,
) -> Tuple[float, Dict[str, Any]]:
    state_scores = {
        InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION: 0.90,
        InvestigationTargetEvidenceState.CONFLICTING_EVIDENCE: 0.85,
        InvestigationTargetEvidenceState.ORBITAL_DETECTION_ONLY: 0.65,
        InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY: 0.40,
        InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED: 0.30,
        InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED: 0.25,
        InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED: 0.15,
    }
    base_weights = {
        "evidence_directness": 0.40,
        "phenomena_alignment": 0.25,
        "instrument_diversity": 0.15,
        "astronaut_proximity": 0.10,
        "terrain_dtm_coverage": 0.10,
    }
    direct_comp = state_scores[evidence_state]
    phenom_comp = min(1.0, aligned_phenomena_count / 3.0) if aligned_phenomena_count > 0 else 0.0
    inst_comp = min(1.0, distinct_instrument_count / 3.0)
    dtm_comp = 1.0 if has_highres_dtm_coverage else 0.0

    # Prompt 18 honesty: NEVER fabricate 0.5 proximity when astronaut coordinate is missing!
    active_weights = dict(base_weights)
    omitted_components: List[str] = []
    if nearest_distance_m is None:
        prox_comp: Optional[float] = None
        w_omit = active_weights.pop("astronaut_proximity")
        omitted_components.append("astronaut_proximity (unavailable: no astronaut coordinate supplied)")
        denom = sum(active_weights.values()) or 1.0
        active_weights = {k: round(v / denom, 4) for k, v in active_weights.items()}
        score = (
            active_weights["evidence_directness"] * direct_comp
            + active_weights["phenomena_alignment"] * phenom_comp
            + active_weights["instrument_diversity"] * inst_comp
            + active_weights["terrain_dtm_coverage"] * dtm_comp
        )
    else:
        prox_comp = max(0.0, min(1.0, 1.0 - (nearest_distance_m / 5000.0)))
        score = (
            active_weights["evidence_directness"] * direct_comp
            + active_weights["phenomena_alignment"] * phenom_comp
            + active_weights["instrument_diversity"] * inst_comp
            + active_weights["astronaut_proximity"] * prox_comp
            + active_weights["terrain_dtm_coverage"] * dtm_comp
        )

    score = round(min(1.0, max(0.0, score)), 4)
    breakdown = {
        "is_heuristic": True,
        "label": "engineering_exploration_priority_heuristic",
        "weights": active_weights,
        "omitted_components": omitted_components,
        "components": {
            "evidence_directness": round(direct_comp, 4),
            "phenomena_alignment": round(phenom_comp, 4),
            "instrument_diversity": round(inst_comp, 4),
            "astronaut_proximity": round(prox_comp, 4) if prox_comp is not None else None,
            "terrain_dtm_coverage": round(dtm_comp, 4),
        },
        "composite_priority_score": score,
    }
    return score, breakdown


def _sample_dem_terrain_at_point(
    ref_dtm: Any,
    ds_root: Any,
    latitude: float,
    longitude_east: float,
) -> Dict[str, Any]:
    """Sample real local DEM elevation, slope, and TRI roughness around target without nodata interpolation."""
    try:
        from pathlib import Path as _P
        from app.terrain.spatial_terrain import compute_terrain_derivatives_window

        raw_dir = _P(ds_root) / "raw"
        half_deg = 0.0005  # ~30m window around target
        rep = compute_terrain_derivatives_window(
            ref_dtm,
            raw_dir=raw_dir,
            min_lat=latitude - half_deg,
            max_lat=latitude + half_deg,
            min_lon=(longitude_east % 360.0) - half_deg,
            max_lon=(longitude_east % 360.0) + half_deg,
        )
        elev_d = rep.derivatives.get("elevation")
        slope_d = rep.derivatives.get("slope")
        tri_d = rep.derivatives.get("tri")
        elev = elev_d.stats.get("mean") if (elev_d and elev_d.available and elev_d.stats) else None
        slope = slope_d.stats.get("mean") if (slope_d and slope_d.available and slope_d.stats) else None
        tri = tri_d.stats.get("mean") if (tri_d and tri_d.available and tri_d.stats) else None
        return {
            "dem_dataset_id": ref_dtm.id,
            "elevation_m": round(float(elev), 2) if elev is not None else None,
            "slope_deg": round(float(slope), 2) if slope is not None else None,
            "roughness_tri_m": round(float(tri), 3) if tri is not None else None,
            "classification": "MARSCOPE_DERIVED" if elev is not None else "UNAVAILABLE",
        }
    except Exception:
        return {
            "dem_dataset_id": getattr(ref_dtm, "id", None),
            "elevation_m": None,
            "slope_deg": None,
            "roughness_tri_m": None,
            "classification": "UNAVAILABLE",
        }


def _evaluate_single_location(
    *,
    target_id: str,
    name: str,
    latitude: float,
    longitude_east: float,
    elevation_m: Optional[float],
    crs: str,
    matched_species: Optional[str],
    initial_evidence_state: Optional[InvestigationTargetEvidenceState],
    initial_instruments: List[str],
    initial_evidence_ids: List[str],
    geology_type: str,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    composition_index: Any,
    recorded_observations: List[Any],
    astronaut_lat: Optional[float],
    astronaut_lon: Optional[float],
    search_radius_m: float,
    pair_reg_cache: Optional[Dict[str, Any]] = None,
    morph_reviews: Optional[Dict[str, Any]] = None,
    spatial_coverage_service: Optional[Any] = None,
) -> CandidateTargetEvaluation:
    is_gale_q = "gale" in question.study_region.lower() or "sharp" in question.study_region.lower()
    known_facts: List[str] = []
    inferred_context: List[str] = []
    unknowns_gaps: List[str] = []
    conflicts: List[str] = []
    prohibited_flags: List[str] = []
    uncertainty_notes: List[str] = []
    eligibility_states: List[EvidenceEligibilityState] = []

    mission_isolated = any(
        k in f"{name} {geology_type} {' '.join(initial_instruments)}".upper()
        for k in ("PERSEVERANCE", "JEZERO", "MARS 2020", "PIXL", "SHERLOC", "SUPERCAM", "MASTCAMZ")
    )
    crs_valid = validate_mars_crs(crs)
    coords_valid = -90.0 <= float(latitude) <= 90.0 and -180.0 <= float(longitude_east) <= 360.0

    datasets = list(catalog_service.list_datasets()) if catalog_service else []
    covering_ds: List[str] = []
    covering_dtms: List[Any] = []
    has_highres_dtm = False
    for ds in datasets:
        inst_cls = _classify_dataset_instrument(ds)
        if is_gale_q and (inst_cls == "PERSEVERANCE_JEZERO_ISOLATED" or "perseverance" in ds.mission.lower() or "jezero" in ds.id.lower()):
            continue
        is_wmts = "{" in (ds.original_product_url or "")
        # Never treat failed datasets or WMTS streaming mosaics as verified covering terrain!
        if ds.failure_reason or ds.status in {
            DatasetLifecycleStatus.FAILED_VALIDATION,
            DatasetLifecycleStatus.FAILED_DOWNLOAD,
            DatasetLifecycleStatus.FAILED_PROCESSING,
        }:
            continue
        if is_wmts:
            if _covers_point(ds, latitude, longitude_east):
                inferred_context.append(
                    f"WMTS visual mosaic '{ds.id}' overlaps coordinate (unverified visual basemap only; excluded from terrain/mineral verification)."
                )
                eligibility_states.append(EvidenceEligibilityState.PRODUCT_UNVERIFIED)
            continue
        if _covers_point(ds, latitude, longitude_east) and (ds.local_file_path or ds.processed_file_path):
            # Prompt 19 Part 12.2: verify point lies in true valid swath polygon, never oblique NoData bbox corner!
            from pathlib import Path as _P
            from app.geospatial.footprints import get_or_extract_dataset_footprint, point_intersects_footprint

            ds_root = (
                _P(catalog_service.catalog_storage_dir).parent
                if getattr(catalog_service, "catalog_storage_dir", None)
                else _P(__file__).resolve().parents[4] / "datasets"
            )
            in_valid_swath = True
            swath_reason = "bbox_only"
            try:
                fp_rec = get_or_extract_dataset_footprint(ds, dataset_root_dir=ds_root)
                in_valid_swath, swath_reason = point_intersects_footprint(
                    fp_rec, latitude, longitude_east, require_valid_pixels_if_known=True
                )
            except Exception:
                in_valid_swath = True

            if not in_valid_swath and swath_reason == "bbox_only_outside_valid_swath_pixels":
                eligibility_states.append(EvidenceEligibilityState.SPATIALLY_UNVERIFIED)
                unknowns_gaps.append(
                    f"Target lies in NoData corner of '{ds.id}' bounding box outside valid swath pixels — NOT counted as co-registered coverage."
                )
                continue

            covering_ds.append(ds.id)
            if inst_cls == "HIRISE_DTM":
                has_highres_dtm = True
                covering_dtms.append(ds)
                eligibility_states.append(EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS)
                known_facts.append(
                    f"Co-registered local DEM swath coverage via '{ds.id}' ({ds.horizontal_resolution_meters or '1.0'} m/px, check={swath_reason})."
                )
            elif inst_cls in {"MOLA", "USGS_SIM3292_CONTEXT", "THEMIS", "CTX"}:
                eligibility_states.append(EvidenceEligibilityState.SCALE_INCOMPATIBLE)
                inferred_context.append(
                    f"Regional context frame from '{ds.id}' (~{ds.horizontal_resolution_meters or 'regional'} m/px scale; not valid for local hazard or mineral confirmation)."
                )

    # Spatial registration assessment against primary HiRISE DTM using Prompt 19 pair registration when paired optical exists
    reg_detail: Optional[Dict[str, Any]] = None
    terrain_sample: Dict[str, Any] = {
        "elevation_m": None,
        "slope_deg": None,
        "roughness_tri_m": None,
        "classification": "UNAVAILABLE",
    }
    coverage_cat: Optional[str] = None
    morph_cids: List[str] = []
    morph_status: Optional[str] = None

    if not crs_valid:
        reg_state = SpatialRegistrationState.INCOMPATIBLE_REFERENCE_SYSTEM
        eligibility_states.append(EvidenceEligibilityState.SPATIALLY_UNVERIFIED)
        uncertainty_notes.append(f"Target CRS '{crs}' is incompatible with Mars IAU2000 reference datum.")
    elif covering_dtms:
        ref_dtm = covering_dtms[0]
        from pathlib import Path as _P
        ds_root = (
            _P(catalog_service.catalog_storage_dir).parent
            if getattr(catalog_service, "catalog_storage_dir", None)
            else _P(__file__).resolve().parents[4] / "datasets"
        )
        ortho_pair = next(
            (d for d in datasets if d.id in covering_ds and d.id != ref_dtm.id and "ortho" in d.id.lower()),
            None,
        )
        reg_rep = evaluate_spatial_registration(
            product_a_id=target_id,
            product_b_id=ref_dtm.id,
            crs_a=crs,
            crs_b=ref_dtm.coordinate_reference_system,
            bounds_a={
                "min_latitude": latitude - 1e-5,
                "max_latitude": latitude + 1e-5,
                "min_longitude": (longitude_east % 360.0) - 1e-5,
                "max_longitude": (longitude_east % 360.0) + 1e-5,
            },
            bounds_b=ref_dtm.coverage.model_dump(),
            resolution_a_m=ref_dtm.horizontal_resolution_meters,
            resolution_b_m=ref_dtm.horizontal_resolution_meters,
        )
        if ortho_pair is not None:
            pair_key = f"{ref_dtm.id}|{ortho_pair.id}"
            pair_assess = pair_reg_cache.get(pair_key) if pair_reg_cache is not None else None
            if pair_assess is None:
                try:
                    from app.geospatial.registration import evaluate_product_pair_registration

                    pair_assess = evaluate_product_pair_registration(
                        ref_dtm,
                        ortho_pair,
                        dataset_root_dir=ds_root,
                        intended_analysis="target_science_co_registration",
                        attempt_image_matching=False,
                    )
                    if pair_reg_cache is not None:
                        pair_reg_cache[pair_key] = pair_assess
                except Exception:
                    pair_assess = None
            if pair_assess is not None:
                reg_detail = {
                    "reference_dtm_id": ref_dtm.id,
                    "companion_ortho_id": ortho_pair.id,
                    "pair_registration_state": pair_assess.overall_state.value,
                    "datum_compatible": (
                        pair_assess.vertical_datum_comparison.compatible
                        if pair_assess.vertical_datum_comparison is not None
                        else None
                    ),
                    "crs_compatible": pair_assess.crs_compatible,
                    "pixel_scale_ratio": pair_assess.pixel_alignment.resolution_ratio,
                    "relative_alignment_uncertainty_m": (
                        pair_assess.uncertainty_breakdown.relative_alignment_uncertainty_m
                    ),
                    "relative_registration_accuracy": pair_assess.relative_registration_accuracy,
                }
        try:
            reg_state = SpatialRegistrationState(reg_rep["registration_state"])
        except Exception:
            reg_state = SpatialRegistrationState.REGISTERED_WITH_LIMITATIONS
        uncertainty_notes.append(reg_rep["registration_error_status"])
        terrain_sample = _sample_dem_terrain_at_point(ref_dtm, ds_root, latitude, longitude_east)
        if terrain_sample.get("elevation_m") is None:
            coverage_cat = "UNOBSERVED"
            uncertainty_notes.append(
                f"Target coordinate falls in DEM nodata inside '{ref_dtm.id}' swath; terrain metrics UNAVAILABLE."
            )
        else:
            coverage_cat = "MULTI_SENSOR_CO_REGISTERED" if ortho_pair is not None else "DEM_ONLY"
    elif _is_gale_coordinate(latitude, longitude_east):
        reg_state = SpatialRegistrationState.INSUFFICIENT_METADATA
        coverage_cat = "REGIONAL_LOW_RESOLUTION_ONLY" if covering_ds else "UNOBSERVED"
        uncertainty_notes.append("Target lies inside Gale Crater bounds without a covering verified <=2 m local DTM.")
    else:
        reg_state = SpatialRegistrationState.NOT_REGISTERED
        coverage_cat = "UNOBSERVED"
        uncertainty_notes.append("No verified local Mars raster covers this coordinate.")

    if morph_reviews:
        for cid, rec in morph_reviews.items():
            # Include any operator morphology review linked to the same study dataset/target context
            c_status = getattr(getattr(rec, "review_status", None), "value", str(getattr(rec, "review_status", "")))
            if cid:
                morph_cids.append(cid)
                morph_status = c_status or morph_status

    # Query nearby verified composition index evidence within search_radius_m
    nearby_ev: List[Any] = []
    nearest_obs_m: Optional[float] = None
    distinct_insts = list(dict.fromkeys([i for i in initial_instruments if i and i.lower() != "manual"]))

    comp_status = composition_index.get_status() if composition_index else None
    comp_integrity_ok = bool(
        comp_status
        and getattr(comp_status, "index_available", False)
        and getattr(comp_status, "checksum_valid", False)
    )
    if comp_integrity_ok:
        deg_pad = max(0.01, search_radius_m / 59200.0 + 0.005)
        all_species_ids = [s.canonical_id for s in list_all_species()]
        bbox_hits = composition_index.query_evidence(
            species_ids=all_species_ids,
            located_only=True,
            bbox=(
                latitude - deg_pad,
                latitude + deg_pad,
                (longitude_east - deg_pad) % 360.0,
                (longitude_east + deg_pad) % 360.0,
            ),
        )[:400]

        for ev in bbox_hits:
            if ev.latitude is None or ev.longitude_east is None:
                continue
            d_m = mars_great_circle_distance_meters(
                latitude, longitude_east, float(ev.latitude), float(ev.longitude_east)
            )
            if d_m <= search_radius_m:
                nearby_ev.append((d_m, ev))
        nearby_ev.sort(key=lambda pair: pair[0])
        if nearby_ev:
            nearest_obs_m = round(nearby_ev[0][0], 2)
            eligibility_states.append(EvidenceEligibilityState.ELIGIBLE_WITH_LIMITATIONS)
            for _d, ev in nearby_ev:
                inst_val = str(getattr(ev, "instrument_id", None) or getattr(ev, "instrument", "")).strip()
                if inst_val and inst_val not in distinct_insts:
                    distinct_insts.append(inst_val)
    elif comp_status and getattr(comp_status, "index_available", False) and not comp_integrity_ok:
        eligibility_states.append(EvidenceEligibilityState.REJECTED)
        unknowns_gaps.append("Composition spatial index failed checksum/integrity validation; local chemical records withheld.")

    # Check any crew-recorded field observations within search_radius_m
    local_obs_hits = []
    for obs in recorded_observations:
        d_m = mars_great_circle_distance_meters(
            latitude, longitude_east, float(obs.latitude), float(obs.longitude_east)
        )
        if d_m <= search_radius_m:
            local_obs_hits.append((d_m, obs))
            if obs.instrument_id not in distinct_insts:
                distinct_insts.append(obs.instrument_id)

    evidence_ids = list(dict.fromkeys([*initial_evidence_ids, *(ev.evidence_id for _, ev in nearby_ev[:10])]))

    species_values_by_name: Dict[str, List[float]] = {}
    has_direct_mineral_local = False
    has_elemental_local = False
    has_orbital_spectral = False
    for _d_m, ev in nearby_ev[:30]:
        ev_type_val = getattr(ev.evidence_type, "value", str(ev.evidence_type)).lower()
        inst_u = str(getattr(ev, "instrument_id", None) or getattr(ev, "instrument", "")).upper()
        sp = getattr(ev, "canonical_species_id", None) or getattr(ev, "canonical_species_name", None) or getattr(ev, "raw_species_name", "")
        rep_val = getattr(ev, "normalized_value", None)
        if rep_val is None:
            rep_val = getattr(ev, "raw_value", None)
        if rep_val is not None:
            try:
                species_values_by_name.setdefault(str(sp), []).append(float(rep_val))
            except (TypeError, ValueError):
                pass
        if inst_u in _ORBITAL_SPECTRAL:
            has_orbital_spectral = True
        if inst_u in _IN_SITU_INSTRUMENTS:
            if ev_type_val == "direct_mineral_detection":
                has_direct_mineral_local = True
            elif ev_type_val in {"elemental_proxy_detection", "direct_element_measurement", "oxide_composition_measurement"}:
                has_elemental_local = True

    if nearby_ev:
        top_species = sorted(
            {
                str(getattr(ev, "canonical_species_id", None) or getattr(ev, "raw_species_name", ""))
                for _, ev in nearby_ev[:20]
            }
        )
        known_facts.append(
            f"{len(nearby_ev)} verified NASA PDS composition observation(s) within {search_radius_m:.0f} m "
            f"(closest {nearest_obs_m:.1f} m; instruments: {', '.join(distinct_insts)}; species: {', '.join(top_species[:6])})."
        )
        if has_elemental_local and not has_direct_mineral_local:
            unknowns_gaps.append(
                "Local measurements are elemental proxies (APXS/ChemCam); crystalline mineral phases (XRD/SWIR) remain unconfirmed at this coordinate."
            )
            prohibited_flags.append("do_not_claim_crystalline_mineral_from_elemental_proxy_alone")

    # Material divergence across co-located records
    for sp, vals in species_values_by_name.items():
        if len(vals) >= 2:
            v_min, v_max = min(vals), max(vals)
            if v_min > 0 and (v_max / v_min) >= 3.0 and (v_max - v_min) >= 5.0:
                conflicts.append(
                    f"Co-located observations of {sp} span {v_min:.2f}..{v_max:.2f} within {search_radius_m:.0f} m (heterogeneous host/vein contrast requiring target-level spot discrimination)."
                )

    for d_m, obs in local_obs_hits:
        known_facts.append(
            f"Crew-recorded observation '{obs.observation_id}' ({obs.instrument_id}: {obs.species_or_feature}={obs.measured_value} {obs.units}) at {d_m:.1f} m ({obs.quality_flag})."
        )
        sp_vals = species_values_by_name.get(obs.species_or_feature)
        if sp_vals and isinstance(obs.measured_value, (int, float)):
            mean_arch = sum(sp_vals) / len(sp_vals)
            if abs(float(obs.measured_value) - mean_arch) > max(5.0, 0.5 * abs(mean_arch)):
                conflicts.append(
                    f"Crew measurement {obs.species_or_feature}={obs.measured_value} differs substantially from co-located archive mean (~{mean_arch:.2f})."
                )

    if comp_status and getattr(comp_status, "crism_status", "") != "available":
        unknowns_gaps.append("Validated CRISM orbital spectral cube absent over corridor (mineral spectroscopy unverified regionally).")
    if not has_highres_dtm:
        unknowns_gaps.append("No verified <=2 m HiRISE DTM coverage verified over this coordinate.")
    if not nearby_ev and not local_obs_hits:
        unknowns_gaps.append(f"No verified in-situ geochemical or mineral observations within {search_radius_m:.0f} m.")

    # Resolve 7-state InvestigationTargetEvidenceState honestly (NEVER upgrade optical candidates)
    geol_l = geology_type.lower()
    if conflicts:
        ev_state = InvestigationTargetEvidenceState.CONFLICTING_EVIDENCE
    elif initial_evidence_state == InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED or (
        "optical" in geol_l and not nearby_ev
    ):
        ev_state = InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED
        prohibited_flags.append("optical_candidate_cannot_receive_mineral_or_routing_science_bonus")
        eligibility_states.append(EvidenceEligibilityState.PRODUCT_UNVERIFIED)
    elif has_direct_mineral_local or has_elemental_local or local_obs_hits:
        ev_state = InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION
    elif has_orbital_spectral:
        ev_state = InvestigationTargetEvidenceState.ORBITAL_DETECTION_ONLY
    elif initial_evidence_state == InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY or (
        covering_ds
        and any("mola" in d.lower() or "usgs" in d.lower() or "themis" in d.lower() for d in covering_ds)
        and "manual" not in geol_l
        and initial_evidence_state != InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED
    ):
        ev_state = InvestigationTargetEvidenceState.INFERRED_REGIONAL_CONTEXT_ONLY
    elif initial_evidence_state == InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED or "manual" in geol_l:
        ev_state = InvestigationTargetEvidenceState.MANUAL_WAYPOINT_UNVERIFIED
    elif not nearby_ev and not has_highres_dtm:
        ev_state = InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED
        eligibility_states.append(EvidenceEligibilityState.UNAVAILABLE)
    else:
        ev_state = initial_evidence_state or InvestigationTargetEvidenceState.DATA_GAP_UNASSESSED

    out_of_gale = is_gale_q and not _is_gale_coordinate(latitude, longitude_east)
    if out_of_gale:
        unknowns_gaps.append(
            f"Target coordinate ({latitude:.3f}, {longitude_east:.3f}) lies outside standard Gale Crater study bounds."
        )

    phenom_l = [p.lower() for p in question.target_phenomena]
    aligned = 0
    cand_terms = " ".join(
        [
            matched_species or "",
            geology_type,
            *(
                str(getattr(ev, "canonical_species_id", None) or getattr(ev, "raw_species_name", ""))
                for _, ev in nearby_ev[:10]
            ),
        ]
    ).lower()
    for p in phenom_l:
        if p in cand_terms:
            aligned += 1

    dist_astronaut = (
        round(mars_great_circle_distance_meters(astronaut_lat, astronaut_lon, latitude, longitude_east), 2)
        if astronaut_lat is not None and astronaut_lon is not None
        else None
    )

    # Candidate eligibility gate (ELIGIBLE_CANDIDATE | CANDIDATE_WITH_LIMITATIONS | REJECTED_FOR_CAMPAIGN)
    if not coords_valid or not crs_valid or (is_gale_q and mission_isolated) or out_of_gale:
        elig_decision = "REJECTED_FOR_CAMPAIGN"
        reasons = []
        if not coords_valid or not crs_valid:
            reasons.append(f"invalid coordinates/CRS ({crs})")
        if is_gale_q and mission_isolated:
            reasons.append("mission-isolated Jezero/Mars 2020 record")
        if out_of_gale:
            reasons.append("outside Gale Crater study bounds")
        elig_rationale = "Rejected for campaign: " + "; ".join(reasons) + "."
        if is_gale_q and mission_isolated:
            eligibility_states.append(EvidenceEligibilityState.MISSION_INCOMPATIBLE)
        priority_score: Optional[float] = None
        breakdown: Dict[str, Any] = {
            "is_heuristic": True,
            "status": "UNCOMPUTED_TARGET_REJECTED",
            "reason": elig_rationale,
        }
    else:
        priority_score, breakdown = _compute_heuristic_priority(
            evidence_state=ev_state,
            aligned_phenomena_count=aligned,
            nearest_distance_m=dist_astronaut,
            distinct_instrument_count=len(distinct_insts),
            has_highres_dtm_coverage=has_highres_dtm,
        )
        if ev_state == InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION and not conflicts and has_highres_dtm:
            elig_decision = "ELIGIBLE_CANDIDATE"
            elig_rationale = "Confirmed in-situ observation co-registered with verified HiRISE DTM within Gale study bounds."
        else:
            elig_decision = "CANDIDATE_WITH_LIMITATIONS"
            elig_rationale = (
                f"Retained with explicit limitations ({ev_state.value}): "
                + (conflicts[0] if conflicts else (unknowns_gaps[0] if unknowns_gaps else "partial archive coverage."))
            )

    if ev_state == InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION:
        sampling_elig = "ELIGIBLE_AFTER_PRE_SCREENING"
    elif ev_state == InvestigationTargetEvidenceState.CONFLICTING_EVIDENCE:
        sampling_elig = "PRIORITY_VERIFICATION_SCREENING_BEFORE_SAMPLING"
    else:
        sampling_elig = "DEFERRED_PENDING_IN_SITU_SCREENING"

    if elig_decision == "REJECTED_FOR_CAMPAIGN":
        sci_rel = "NOT_ELIGIBLE: " + elig_rationale
        route_role = "rejected_excluded"
    elif ev_state == InvestigationTargetEvidenceState.CONFIRMED_LOCAL_OBSERVATION:
        sci_rel = f"Directly addresses {aligned} question phenomena via verified local measurements."
        route_role = "confirmed_science_corridor_anchor"
    elif ev_state == InvestigationTargetEvidenceState.OPTICAL_MORPHOLOGY_CANDIDATE_UNVERIFIED:
        sci_rel = "Unverified optical morphology candidate only — no mineral or elemental confirmation."
        route_role = "non_prioritized_optical_screening_stop"
    else:
        sci_rel = f"Partial/contextual alignment ({aligned} phenomena terms); requires in-situ verification."
        route_role = "exploratory_verification_stop"

    if conflicts:
        sci_conf_state = "CONFLICTING_UNRESOLVED"
    elif nearby_ev:
        sci_conf_state = "QUALITATIVE_ONLY_NO_STATISTICAL_CONFIDENCE"
    else:
        sci_conf_state = "UNVERIFIED_NO_LOCAL_GEOCHEMICAL_DATA"

    if not eligibility_states:
        eligibility_states = [EvidenceEligibilityState.UNAVAILABLE]

    return CandidateTargetEvaluation(
        target_id=target_id,
        name=name,
        latitude=latitude,
        longitude_east=longitude_east % 360.0,
        elevation_m=elevation_m,
        crs=crs,
        evidence_state=ev_state,
        study_region=question.study_region,
        matched_species=matched_species,
        distinct_instruments=distinct_insts,
        local_observation_count=len(nearby_ev) + len(local_obs_hits),
        nearest_observation_distance_m=nearest_obs_m,
        covering_datasets=covering_ds,
        known_facts=list(dict.fromkeys(known_facts)) or ["No verified local factual measurements recorded at this location yet."],
        inferred_context=list(dict.fromkeys(inferred_context)),
        unknowns_and_gaps=list(dict.fromkeys(unknowns_gaps)),
        conflicting_records=list(dict.fromkeys(conflicts)),
        heuristic_priority_score=priority_score,
        exploration_priority=priority_score,
        scientific_evidence_summary={
            "local_pds_observations": len(nearby_ev),
            "crew_field_observations": len(local_obs_hits),
            "distinct_instruments": distinct_insts,
            "covering_local_datasets": covering_ds,
            "conflicts_detected": len(conflicts),
        },
        scientific_relevance=sci_rel,
        route_utility={
            "routing_role": route_role,
            "heuristic_priority": priority_score,
            "astronaut_distance_m": dist_astronaut,
            "has_highres_dtm_coverage": has_highres_dtm,
        },
        scientific_confidence_state=sci_conf_state,
        scientific_confidence_score=None,
        evidence_eligibility_states=list(dict.fromkeys(eligibility_states)),
        spatial_registration_state=reg_state,
        spatial_registration_detail=reg_detail,
        terrain_elevation_m=terrain_sample.get("elevation_m"),
        terrain_slope_deg=terrain_sample.get("slope_deg"),
        terrain_roughness_tri_m=terrain_sample.get("roughness_tri_m"),
        terrain_data_classification=terrain_sample.get("classification"),
        spatial_coverage_category=coverage_cat,
        morphology_candidate_ids=morph_cids[:5],
        morphology_review_status=morph_status,
        uncertainty_notes=list(dict.fromkeys(uncertainty_notes + unknowns_gaps[:2])),
        eligibility_decision=elig_decision,
        eligibility_decision_rationale=elig_rationale,
        prioritization_is_heuristic=True,
        prioritization_breakdown=breakdown,
        eligibility_for_sampling=sampling_elig,
        prohibited_inference_flags=list(dict.fromkeys(prohibited_flags)),
        evidence_ids=evidence_ids,
    )


def evaluate_targets_for_question(
    *,
    req: TargetEvaluationRequest,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    target_registry: Any,
    composition_search_service: Any,
    composition_index: Any,
    recorded_observations: List[Any],
    morphology_service: Optional[Any] = None,
    spatial_coverage_service: Optional[Any] = None,
) -> TargetEvaluationBatchResponse:
    evaluated_map: Dict[str, CandidateTargetEvaluation] = {}
    rejected_map: Dict[str, CandidateTargetEvaluation] = {}
    pair_reg_cache: Dict[str, Any] = {}
    morph_reviews: Optional[Dict[str, Any]] = None
    if morphology_service is not None and getattr(morphology_service, "review_store", None) is not None:
        try:
            morph_reviews = morphology_service.review_store.load_all()
        except Exception:
            morph_reviews = None

    registry_targets: List[ScienceTarget] = []
    if req.target_ids:
        for tid in req.target_ids:
            t = target_registry.get_target(tid)
            if t is not None:
                registry_targets.append(t)
    else:
        registry_targets = list(target_registry.list_targets())

    for t in registry_targets:
        ev = _evaluate_single_location(
            target_id=t.id,
            name=t.name,
            latitude=t.latitude,
            longitude_east=t.longitude,
            elevation_m=t.elevation_m,
            crs=t.crs,
            matched_species=t.matched_species,
            initial_evidence_state=t.evidence_state,
            initial_instruments=[s.strip() for s in t.instrument_source.split(",") if s.strip()],
            initial_evidence_ids=t.evidence_ids,
            geology_type=t.geology_type,
            question=question,
            catalog_service=catalog_service,
            composition_index=composition_index,
            recorded_observations=recorded_observations,
            astronaut_lat=req.astronaut_latitude,
            astronaut_lon=req.astronaut_longitude,
            search_radius_m=req.search_radius_m,
            pair_reg_cache=pair_reg_cache,
            morph_reviews=morph_reviews,
            spatial_coverage_service=spatial_coverage_service,
        )
        if ev.eligibility_decision == "REJECTED_FOR_CAMPAIGN" and not (req.target_ids and ev.target_id in req.target_ids):
            rejected_map[ev.target_id] = ev
        else:
            evaluated_map[ev.target_id] = ev

    # Discover genuine evidence-backed candidate locations across ALL question.target_phenomena
    comp_status = composition_index.get_status() if composition_index else None
    if (
        req.include_discovered_candidates
        and composition_search_service
        and comp_status
        and getattr(comp_status, "index_available", False)
        and getattr(comp_status, "checksum_valid", False)
    ):
        for term in question.target_phenomena:
            t_clean = term.strip()
            if not t_clean or t_clean.lower() in {"boxwork", "bedrock", "vein"}:
                continue
            try:
                sres = composition_search_service.search(
                    StructuredCompositionQuery(
                        query=t_clean,
                        include_element_bearing_minerals=True,
                        astronaut_latitude=req.astronaut_latitude,
                        astronaut_longitude=req.astronaut_longitude,
                        limit=50 if req.target_ids else max(10, req.max_candidates),
                    )
                )
            except Exception:
                continue
            target_id_set = set(req.target_ids) if req.target_ids else None
            spec_label = sres.resolution.species.canonical_id if sres.resolution.species else t_clean
            for cand in sres.candidate_locations:
                if not target_id_set and len(evaluated_map) >= req.max_candidates:
                    break
                if req.study_bounds:
                    lat_ok = req.study_bounds.get("min_lat", -90) <= cand.latitude <= req.study_bounds.get("max_lat", 90)
                    lon_ok = req.study_bounds.get("min_lon", 0) <= (cand.longitude_east % 360.0) <= req.study_bounds.get("max_lon", 360)
                    if not (lat_ok and lon_ok):
                        continue
                tid = "tgt_" + hashlib.sha256(f"{spec_label}|{cand.candidate_id}".encode("utf-8")).hexdigest()[:12]
                if target_id_set and tid not in target_id_set:
                    continue
                if tid in evaluated_map or tid in rejected_map:
                    continue
                ev = _evaluate_single_location(
                    target_id=tid,
                    name=f"{cand.cluster_label} [{spec_label}]",
                    latitude=cand.latitude,
                    longitude_east=cand.longitude_east,
                    elevation_m=cand.elevation_m,
                    crs=cand.crs,
                    matched_species=spec_label,
                    initial_evidence_state=None,
                    initial_instruments=list(cand.distinct_instruments),
                    initial_evidence_ids=list(cand.evidence_ids),
                    geology_type=f"{spec_label} ({cand.best_evidence_type.value})",
                    question=question,
                    catalog_service=catalog_service,
                    composition_index=composition_index,
                    recorded_observations=recorded_observations,
                    astronaut_lat=req.astronaut_latitude,
                    astronaut_lon=req.astronaut_longitude,
                    search_radius_m=req.search_radius_m,
                    pair_reg_cache=pair_reg_cache,
                    morph_reviews=morph_reviews,
                    spatial_coverage_service=spatial_coverage_service,
                )
                if ev.eligibility_decision == "REJECTED_FOR_CAMPAIGN" and not (target_id_set and tid in target_id_set):
                    rejected_map[tid] = ev
                else:
                    evaluated_map[tid] = ev

    ordered = sorted(
        evaluated_map.values(),
        key=lambda x: (-(x.heuristic_priority_score or 0.0), x.target_id),
    )[: req.max_candidates]

    counts: Dict[str, int] = {}
    for item in ordered:
        k = item.evidence_state.value
        counts[k] = counts.get(k, 0) + 1

    return TargetEvaluationBatchResponse(
        question_id=question.question_id,
        targets=ordered,
        rejected_targets=list(rejected_map.values()),
        state_counts=counts,
    )
