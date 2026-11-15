"""
MARSCOPE Measurement Requirement Mapping & Gap Assessment
Prompt 17: Evaluates a ScienceQuestionDefinition against live catalog datasets,
verified composition spatial index status, and imagery archive holdings without
fabricating mineral cubes or downgrading scale limitations.
"""

from __future__ import annotations

from typing import Any, List, Optional

from app.schemas.dataset import Dataset, DatasetLifecycleStatus
from app.science.investigation.schemas import (
    MeasurementClass,
    MeasurementRequirementSpec,
    RequirementEvaluationRecord,
    RequirementFulfillmentState,
    ScienceQuestionDefinition,
)


def _classify_dataset_instrument(ds: Dataset) -> str:
    text = f"{ds.id} {ds.instrument} {ds.product_title}".upper()
    if "PERSEVERANCE" in ds.mission.upper() or "JEZERO" in text:
        return "PERSEVERANCE_JEZERO_ISOLATED"
    if "HIRISE" in text and ("DTEEC" in text or ds.product_type == "DTM" or "ELEVATION" in text):
        return "HIRISE_DTM"
    if "HIRISE" in text:
        return "HIRISE"
    if "MOLA" in text:
        return "MOLA"
    if "CRISM" in text:
        return "CRISM"
    if "THEMIS" in text:
        return "THEMIS"
    if "CTX" in text:
        return "CTX"
    if "CHEMCAM" in text:
        return "CHEMCAM_LIBS"
    if "APXS" in text:
        return "APXS"
    if "CHEMIN" in text:
        return "CHEMIN_XRD"
    if "SAM" in text:
        return "SAM_EGA_GCMS"
    if "REMS" in text:
        return "REMS"
    if "SIM3292" in text or "USGS" in text:
        return "USGS_SIM3292_CONTEXT"
    return ds.instrument.upper()


def evaluate_question_requirements(
    *,
    question: ScienceQuestionDefinition,
    catalog_service: Any,
    composition_index: Any,
    imagery_service: Optional[Any] = None,
) -> List[RequirementEvaluationRecord]:
    """Evaluate every measurement requirement for a scientific question honestly against real holdings."""
    datasets: List[Dataset] = list(catalog_service.list_datasets()) if catalog_service else []
    comp_status = composition_index.get_status() if composition_index else None
    imagery_products = list(imagery_service.all_products()) if imagery_service else []

    is_gale_question = "gale" in question.study_region.lower() or "sharp" in question.study_region.lower()
    crism_available = bool(
        comp_status
        and getattr(comp_status, "crism_status", "") in {"available", "partially_available", "verified"}
    )

    records: List[RequirementEvaluationRecord] = []

    for spec in question.required_measurement_specs:
        satisfying_ids: List[str] = []
        satisfying_insts: List[str] = []
        gaps: List[str] = []
        matched_count = 0

        allowed_set = {i.upper() for i in spec.allowed_instrument_ids}

        # 1. Inspect datasets in DatasetCatalogService (enforcing mission isolation + local verification + scale)
        for ds in datasets:
            ds_inst = _classify_dataset_instrument(ds)
            if ds_inst == "PERSEVERANCE_JEZERO_ISOLATED" and is_gale_question:
                continue
            if ds_inst == "USGS_SIM3292_CONTEXT":
                continue
            if ds_inst not in allowed_set:
                continue
            if ds.status == DatasetLifecycleStatus.DISCOVERED or not (
                ds.local_file_path or ds.processed_file_path or "{" in ds.original_product_url
            ):
                gaps.append(
                    f"Dataset '{ds.id}' ({ds_inst}) is catalog-discovered only and has no validated local raster/table."
                )
                continue
            if (
                spec.minimum_spatial_resolution_m is not None
                and ds.horizontal_resolution_meters is not None
                and ds.horizontal_resolution_meters > spec.minimum_spatial_resolution_m
            ):
                gaps.append(
                    f"Dataset '{ds.id}' resolution (~{ds.horizontal_resolution_meters:.1f} m) is coarser than required {spec.minimum_spatial_resolution_m:.1f} m."
                )
                continue
            satisfying_ids.append(ds.id)
            if ds_inst not in satisfying_insts:
                satisfying_insts.append(ds_inst)
            matched_count += 1

        # 2. Inspect CompositionSpatialIndex for elemental / XRD / volatile / spectroscopy holdings
        if comp_status and getattr(comp_status, "index_available", False):
            inst_indexed = {str(x).upper() for x in (getattr(comp_status, "instruments_indexed", []) or [])}
            located_n = int(getattr(comp_status, "located_evidence_count", 0) or 0)
            if spec.measurement_class == MeasurementClass.ELEMENTAL_CHEMISTRY and located_n > 0:
                if {"APXS", "CHEMCAM_LIBS"} & inst_indexed or located_n > 0:
                    satisfying_ids.append(f"composition_index:{comp_status.active_generation_id}")
                    for candidate_i in ("APXS", "CHEMCAM_LIBS"):
                        if candidate_i in allowed_set and (candidate_i in inst_indexed or located_n > 0):
                            if candidate_i not in satisfying_insts:
                                satisfying_insts.append(candidate_i)
                    matched_count += located_n
            elif spec.measurement_class == MeasurementClass.MINERALOGY_XRD:
                if "CHEMIN_XRD" in inst_indexed and located_n > 0:
                    satisfying_ids.append(f"composition_index_chemin:{comp_status.active_generation_id}")
                    if "CHEMIN_XRD" in allowed_set and "CHEMIN_XRD" not in satisfying_insts:
                        satisfying_insts.append("CHEMIN_XRD")
                    matched_count += 1
                    gaps.append(
                        "CheMin XRD is verified ONLY at sparse Curiosity drill holes; intermediate terrain mineral crystallinity remains unmeasured."
                    )
                else:
                    gaps.append(
                        "No local CheMin XRD crystalline phase file is indexed alongside located rover coordinates."
                    )
                if not crism_available:
                    gaps.append(
                        f"Regional orbital CRISM cubes unavailable ({getattr(comp_status, 'crism_status', 'unavailable')}); interpolation between CheMin drill holes is unsupported."
                    )
            elif spec.measurement_class == MeasurementClass.VOLATILE_ORGANIC_ISOTOPE:
                if "SAM_EGA_GCMS" in inst_indexed and located_n > 0:
                    satisfying_ids.append(f"composition_index_sam:{comp_status.active_generation_id}")
                    if "SAM_EGA_GCMS" not in satisfying_insts:
                        satisfying_insts.append("SAM_EGA_GCMS")
                    matched_count += 1
                else:
                    gaps.append("SAM EGA/GCMS evolved-gas records are not indexed with verified spatial coordinates.")
            elif spec.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL:
                if crism_available:
                    satisfying_ids.append("crism_validated_cube")
                    satisfying_insts.append("CRISM")
                    matched_count += 1
                else:
                    gaps.append(
                        f"CRISM spectral cubes unavailable ({getattr(comp_status, 'crism_status', 'unavailable')}); orbital mineral confirmation remains unestablished."
                    )

        # 3. Inspect ImageryArchiveService for acquired local HiRISE/Mastcam/MAHLI optical frames
        for prod in imagery_products:
            inst_u = (prod.instrument or "").upper()
            mission_u = (prod.mission or "").upper()
            if is_gale_question and ("M2020" in mission_u or "PERSEVERANCE" in mission_u or "JEZERO" in (prod.dataset_id or "").upper()):
                continue
            if any(k in inst_u for k in allowed_set):
                if prod.local_file_path:
                    satisfying_ids.append(prod.product_id)
                    if inst_u not in satisfying_insts:
                        satisfying_insts.append(inst_u)
                    matched_count += 1
                else:
                    gaps.append(
                        f"Imagery product '{prod.product_id}' is indexed remotely (DISCOVERED only, not locally downloaded/parsed)."
                    )

        # Determine RequirementFulfillmentState strictly from verified evidence (never optimistic!)
        if spec.measurement_class == MeasurementClass.MINERALOGY_SPECTRAL and not crism_available and not satisfying_ids:
            state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
        elif spec.measurement_class == MeasurementClass.MINERALOGY_XRD and "CHEMIN_XRD" not in satisfying_insts and not crism_available:
            # Check if elemental proxies exist to label CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE / MISSING
            if comp_status and getattr(comp_status, "located_evidence_count", 0) > 0:
                state = RequirementFulfillmentState.CANNOT_BE_VERIFIED_WITH_AVAILABLE_ARCHIVE
                gaps.append(
                    "Only elemental oxide measurements (ChemCam/APXS) are indexed locally; elemental abundance is a proxy and CANNOT establish crystalline mineral phase without CheMin XRD or CRISM SWIR spectra."
                )
            else:
                state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
        elif satisfying_ids:
            if gaps and spec.measurement_class in {
                MeasurementClass.MORPHOLOGY_HIGHRES,
                MeasurementClass.THERMAL_INERTIA_COMPOSITION,
            }:
                state = RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
            elif spec.measurement_class == MeasurementClass.ELEMENTAL_CHEMISTRY:
                state = RequirementFulfillmentState.SATISFIED_DIRECT
            elif spec.measurement_class == MeasurementClass.TOPOGRAPHY_ELEVATION:
                # WMTS-only vs validated local HiRISE DTM
                has_local_dtm = any(
                    d.id in satisfying_ids and (d.local_file_path or d.processed_file_path)
                    for d in datasets
                )
                state = (
                    RequirementFulfillmentState.SATISFIED_DIRECT
                    if has_local_dtm
                    else RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
                )
            else:
                state = RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED if gaps else RequirementFulfillmentState.SATISFIED_DIRECT
        else:
            state = RequirementFulfillmentState.MISSING_REQUIRED_DATA
            if not gaps:
                gaps.append(f"No validated local datasets or index records satisfy {spec.label}.")

        if spec.measurement_class == MeasurementClass.THERMAL_INERTIA_COMPOSITION and state == RequirementFulfillmentState.SATISFIED_DIRECT:
            state = RequirementFulfillmentState.PARTIAL_COVERAGE_OR_RESOLUTION_LIMITED
            gaps.append("THEMIS/orbital context (~100 m scale) provides broad induration framing only, not meter-scale hazard verification.")

        records.append(
            RequirementEvaluationRecord(
                requirement_id=spec.requirement_id,
                label=spec.label,
                measurement_class=spec.measurement_class,
                essential=spec.essential,
                fulfillment_state=state,
                satisfying_source_ids=list(dict.fromkeys(satisfying_ids)),
                satisfying_instruments=list(dict.fromkeys(satisfying_insts)),
                matched_evidence_count=matched_count,
                limitations_and_gaps=list(dict.fromkeys(gaps)),
                prohibited_substitutions=list(spec.prohibited_substitutions),
            )
        )

    return records
