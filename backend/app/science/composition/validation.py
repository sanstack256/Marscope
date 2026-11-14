"""
MARSCOPE 12-Stage Scientific Validation Pipeline
Martian Surface Intelligence & Exploration System

Enforces zero-fabrication and scientific defensibility rules on every candidate
composition evidence record. Failed records produce explicit RejectionRecords stored
in the index audit log instead of being silently fixed or dropped.
"""

import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple
from app.geospatial.crs import validate_mars_coordinates, validate_mars_crs
from app.science.composition.models import (
    CompositionEvidence,
    EvidenceStatus,
    EvidenceType,
    LocationSemanticType,
    RejectionRecord,
    SpeciesCategory,
    ValidationStageResult,
)
from app.science.composition.species import get_species_by_id


EVIDENCE_ID_DETERMINISM_VERSION = "evidence_id_v1"
_NON_COMPOSITION_INSTRUMENTS = {"REMS", "RAD", "NAVCAM", "HAZCAM", "MASTCAM", "MARDI", "DAN"}


def compute_deterministic_evidence_id(ev: CompositionEvidence) -> str:
    """
    Compute the canonical content-derived SHA-256 evidence ID exclusively from
    immutable source identity fields (never timestamps, UUIDs, or host filesystem paths).
    """
    ver = (ev.determinism_version or EVIDENCE_ID_DETERMINISM_VERSION).strip()
    key = "|".join(
        [
            ver,
            ev.source_dataset_id.strip(),
            ev.product_id.strip(),
            ev.source_record_ref.strip(),
            ev.canonical_species_id.strip(),
            ev.raw_species_name.strip(),
            ev.evidence_type.value,
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _make_rejection(
    ev: CompositionEvidence,
    stage_num: int,
    code: str,
    reason: str,
    raw_payload: Optional[Dict[str, Any]] = None,
) -> RejectionRecord:
    key = f"{ev.source_dataset_id}|{ev.product_id}|{ev.source_record_ref}|{ev.raw_species_name}|{code}"
    rid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return RejectionRecord(
        rejection_id=rid,
        source_dataset_id=ev.source_dataset_id,
        product_id=ev.product_id,
        source_record_ref=ev.source_record_ref,
        instrument_id=ev.instrument_id,
        raw_species=ev.raw_species_name,
        rejection_stage=stage_num,
        rejection_code=code,
        reason=reason,
        raw_payload=raw_payload or {},
    )


def validate_composition_evidence(
    ev: CompositionEvidence,
    raw_payload: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[ValidationStageResult], Optional[RejectionRecord]]:
    """
    Execute the 12-stage mandatory scientific validation pipeline.
    Returns (passed_all_stages, stage_results, rejection_record_or_none).
    """
    stages: List[ValidationStageResult] = []

    def fail(num: int, name: str, code: str, detail: str) -> Tuple[bool, List[ValidationStageResult], RejectionRecord]:
        stages.append(ValidationStageResult(stage_number=num, stage_name=name, passed=False, detail=detail))
        return False, stages, _make_rejection(ev, num, code, detail, raw_payload)

    def ok(num: int, name: str, detail: str) -> None:
        stages.append(ValidationStageResult(stage_number=num, stage_name=name, passed=True, detail=detail))

    # Stage 1: Source dataset, product & checksum provenance identity
    if not ev.source_dataset_id.strip() or not ev.product_id.strip() or not ev.source_reference.strip():
        return fail(1, "source_dataset_identity", "MISSING_PROVENANCE_IDENTITY", "Missing dataset, product, or reference ID.")
    if not ev.source_file_checksum or not ev.source_file_checksum.strip():
        return fail(
            1,
            "source_dataset_identity",
            "MISSING_SOURCE_CHECKSUM",
            f"Product '{ev.product_id}' missing verifiable source_file_checksum.",
        )
    if not ev.schema_version or not ev.parser_version:
        return fail(
            1,
            "source_dataset_identity",
            "MISSING_PARSER_PROVENANCE",
            f"Product '{ev.product_id}' must declare schema_version and parser_version.",
        )
    ok(1, "source_dataset_identity", f"Dataset '{ev.source_dataset_id}', product '{ev.product_id}', sha256={ev.source_file_checksum[:12]}....")

    # Stage 2: Instrument eligibility (reject meteorology/radiation/imaging from composition assertions)
    inst_upper = ev.instrument_id.upper()
    if any(tok in inst_upper for tok in _NON_COMPOSITION_INSTRUMENTS):
        return fail(
            2,
            "instrument_eligibility",
            "NON_COMPOSITION_INSTRUMENT",
            f"Instrument '{ev.instrument_id}' produces environmental/engineering data and cannot emit surface composition evidence.",
        )
    ok(2, "instrument_eligibility", f"Instrument '{ev.instrument_id}' eligible for composition evidence.")

    # Stage 3: Product calibration level & passive spectrum exclusion
    lvl_upper = ev.processing_level.upper()
    ptype_upper = ev.calibration_status.upper()
    if (
        ev.evidence_type == EvidenceType.UNINTERPRETED_SPECTRAL_RECORD
        or "CHEMCAM-PSV" in ptype_upper
        or "PASSIVE" in lvl_upper
        or "DIGITAL_NUMBER" in str(ev.raw_unit or "").upper()
        or "LEVEL 0" in lvl_upper
        or "EDR" in lvl_upper.split()
    ):
        return fail(
            3,
            "product_calibration_level",
            "UNCALIBRATED_OR_PASSIVE_RECORD",
            f"Product '{ev.product_id}' is raw/passive/uncalibrated ({ev.processing_level}; unit={ev.raw_unit}) and cannot justify elemental or mineral detection.",
        )
    ok(3, "product_calibration_level", f"Calibration verified ({ev.processing_level}).")

    # Stage 4: Spectral methodology & ChemCam guard
    if "CHEMCAM" in inst_upper and ev.evidence_type == EvidenceType.DIRECT_MINERAL_DETECTION:
        return fail(
            4,
            "spectral_methodology_guard",
            "INVALID_MINERAL_CLAIM_FROM_LIBS",
            "ChemCam LIBS measures elemental/oxide abundance, not crystalline XRD mineral phases.",
        )
    if not ev.methodology.strip():
        return fail(4, "spectral_methodology_guard", "MISSING_METHODOLOGY", "Analytical methodology must be explicitly stated.")
    ok(4, "spectral_methodology_guard", f"Methodology verified: {ev.methodology[:80]}.")

    # Stage 5: Controlled species vocabulary validation
    spec = get_species_by_id(ev.canonical_species_id)
    if spec is None:
        return fail(
            5,
            "species_vocabulary_validation",
            "UNKNOWN_SPECIES",
            f"Canonical species '{ev.canonical_species_id}' not in controlled MARSCOPE vocabulary.",
        )
    if spec.category != ev.species_category:
        return fail(
            5,
            "species_vocabulary_validation",
            "SPECIES_CATEGORY_MISMATCH",
            f"Expected category '{spec.category.value}' for '{spec.canonical_id}', got '{ev.species_category.value}'.",
        )
    ok(5, "species_vocabulary_validation", f"Resolved canonical {spec.category.value} '{spec.canonical_id}'.")

    # Stage 6: Numeric, null, negative & <LOD integrity
    if ev.raw_value is None or not math.isfinite(ev.raw_value):
        return fail(
            6,
            "numeric_and_lod_integrity",
            "NULL_OR_NAN_VALUE",
            f"Measurement for '{ev.canonical_species_id}' is missing/NaN and excluded from quantitative evidence.",
        )
    if ev.raw_value < 0.0:
        return fail(
            6,
            "numeric_and_lod_integrity",
            "NEGATIVE_PHYSICAL_VALUE",
            f"Non-physical negative concentration ({ev.raw_value} {ev.raw_unit}) rejected.",
        )
    if ev.evidence_status == EvidenceStatus.BELOW_DETECTION_LIMIT:
        return fail(
            6,
            "numeric_and_lod_integrity",
            "BELOW_DETECTION_LIMIT",
            f"Measurement for '{ev.canonical_species_id}' reported below detection limit (not counted as positive detection).",
        )
    ok(6, "numeric_and_lod_integrity", f"Finite non-negative value {ev.raw_value} {ev.raw_unit}.")

    # Stage 7: Physical abundance bounds check
    if ev.normalized_value is None or not math.isfinite(ev.normalized_value):
        return fail(7, "physical_bounds_check", "MISSING_NORMALIZED_VALUE", "Normalized numeric value is missing or non-finite.")
    if ev.normalized_unit == "wt%" and not (0.0 <= ev.normalized_value <= 100.0):
        return fail(
            7,
            "physical_bounds_check",
            "OUT_OF_PHYSICAL_BOUNDS_WT_PCT",
            f"Normalized concentration {ev.normalized_value} wt% outside physical [0, 100] wt%.",
        )
    if ev.normalized_unit == "ppm" and not (0.0 <= ev.normalized_value <= 1_000_000.0):
        return fail(
            7,
            "physical_bounds_check",
            "OUT_OF_PHYSICAL_BOUNDS_PPM",
            f"Normalized concentration {ev.normalized_value} ppm outside physical [0, 1e6] ppm.",
        )
    ok(7, "physical_bounds_check", f"Within physical bounds ({ev.normalized_value} {ev.normalized_unit}).")

    # Stage 8: Unit normalization validation
    if ev.normalized_unit not in {"wt%", "ppm"}:
        return fail(
            8,
            "unit_normalization_validation",
            "UNSUPPORTED_NORMALIZED_UNIT",
            f"Normalized unit '{ev.normalized_unit}' invalid for composition index.",
        )
    ok(8, "unit_normalization_validation", f"Normalized from {ev.raw_unit} to {ev.normalized_unit}.")

    # Stage 9: Uncertainty & quality metadata integrity
    if ev.uncertainty_value is not None:
        if not math.isfinite(ev.uncertainty_value) or ev.uncertainty_value < 0.0:
            return fail(
                9,
                "uncertainty_and_quality_metadata",
                "INVALID_UNCERTAINTY",
                f"Uncertainty value ({ev.uncertainty_value}) must be finite and non-negative.",
            )
        if not ev.uncertainty_unit or ev.uncertainty_unit != ev.normalized_unit:
            return fail(
                9,
                "uncertainty_and_quality_metadata",
                "UNCERTAINTY_UNIT_MISMATCH",
                f"Uncertainty unit '{ev.uncertainty_unit}' incompatible with measurement unit '{ev.normalized_unit}'.",
            )
        if not ev.uncertainty_type or not ev.uncertainty_type.strip():
            return fail(
                9,
                "uncertainty_and_quality_metadata",
                "MISSING_UNCERTAINTY_TYPE",
                "Uncertainty value reported without documented uncertainty_type.",
            )
    if ev.secondary_uncertainty_value is not None:
        if not math.isfinite(ev.secondary_uncertainty_value) or ev.secondary_uncertainty_value < 0.0:
            return fail(
                9,
                "uncertainty_and_quality_metadata",
                "INVALID_SECONDARY_UNCERTAINTY",
                f"Secondary uncertainty ({ev.secondary_uncertainty_value}) must be finite and non-negative.",
            )
    ok(9, "uncertainty_and_quality_metadata", f"Uncertainty={ev.uncertainty_value} ({ev.uncertainty_type or 'unreported'}).")

    # Stage 10: Coordinate, CRS, semantic type & provenance integrity (located vs unlocated)
    if ev.location_verified:
        if ev.latitude is None or ev.longitude_east is None:
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "LOCATED_FLAG_WITHOUT_COORDS",
                "location_verified=True but latitude or longitude is None.",
            )
        if ev.location_semantic_type == LocationSemanticType.UNLOCATED:
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "LOCATED_SEMANTIC_TYPE_CONFLICT",
                "location_verified=True cannot carry location_semantic_type=unlocated.",
            )
        if not validate_mars_crs(ev.crs):
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "INVALID_OR_EARTH_CRS",
                f"Rejected non-Martian or invalid CRS '{ev.crs}'.",
            )
        try:
            validate_mars_coordinates(
                ev.latitude,
                ev.longitude_east,
                latitude_convention=ev.latitude_convention or "Planetocentric",
                longitude_direction=ev.longitude_direction or "East",
            )
        except Exception as exc:
            return fail(10, "coordinate_and_crs_integrity", "INVALID_MARS_COORDS", str(exc))
        if not ev.coordinate_source or not ev.coordinate_provenance:
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "MISSING_COORDINATE_PROVENANCE",
                "Verified coordinates must cite coordinate_source and coordinate_provenance.",
            )
        ok(
            10,
            "coordinate_and_crs_integrity",
            f"Located [{ev.location_semantic_type.value}] ({ev.latitude:.5f}, {ev.longitude_east:.5f}) via {ev.coordinate_source}.",
        )
    else:
        if ev.latitude is not None or ev.longitude_east is not None:
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "UNVERIFIED_COORDINATES_LEAKED",
                "Unlocated record cannot carry unverified lat/lon coordinates.",
            )
        if ev.location_semantic_type != LocationSemanticType.UNLOCATED:
            return fail(
                10,
                "coordinate_and_crs_integrity",
                "UNLOCATED_SEMANTIC_TYPE_CONFLICT",
                f"Unlocated record must use location_semantic_type='unlocated', got '{ev.location_semantic_type.value}'.",
            )
        ok(10, "coordinate_and_crs_integrity", "Explicitly marked unlocated (excluded from map markers & geodesic ranking).")

    # Stage 11: Evidence type vs species category consistency
    if ev.evidence_type == EvidenceType.DIRECT_MINERAL_DETECTION and spec.category not in {
        SpeciesCategory.MINERAL,
        SpeciesCategory.MINERAL_GROUP,
    }:
        return fail(
            11,
            "evidence_type_consistency",
            "MINERAL_EVIDENCE_NON_MINERAL_SPECIES",
            f"DIRECT_MINERAL_DETECTION incompatible with {spec.category.value} '{spec.canonical_id}'.",
        )
    if ev.evidence_type == EvidenceType.OXIDE_COMPOSITION_MEASUREMENT and spec.category != SpeciesCategory.OXIDE:
        return fail(
            11,
            "evidence_type_consistency",
            "OXIDE_EVIDENCE_NON_OXIDE_SPECIES",
            f"OXIDE_COMPOSITION_MEASUREMENT incompatible with {spec.category.value} '{spec.canonical_id}'.",
        )
    if ev.evidence_type == EvidenceType.DIRECT_ELEMENT_MEASUREMENT and spec.category != SpeciesCategory.ELEMENT:
        return fail(
            11,
            "evidence_type_consistency",
            "ELEMENT_EVIDENCE_NON_ELEMENT_SPECIES",
            f"DIRECT_ELEMENT_MEASUREMENT incompatible with {spec.category.value} '{spec.canonical_id}'.",
        )
    ok(11, "evidence_type_consistency", f"{ev.evidence_type.value} consistent with {spec.category.value}.")

    # Stage 12: Deterministic ID & citation verification
    if not ev.evidence_id.strip():
        return fail(12, "provenance_and_determinism", "MISSING_EVIDENCE_ID", "Evidence record ID is empty.")
    expected_id = compute_deterministic_evidence_id(ev)
    if ev.evidence_id.strip() != expected_id:
        return fail(
            12,
            "provenance_and_determinism",
            "EVIDENCE_ID_MISMATCH",
            f"Non-deterministic or corrupted evidence_id '{ev.evidence_id}' != expected '{expected_id}'.",
        )
    ok(12, "provenance_and_determinism", f"Deterministic evidence ID ({ev.determinism_version}) verified.")

    return True, stages, None
