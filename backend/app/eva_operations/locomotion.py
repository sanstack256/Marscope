"""
MARSCOPE Locomotion & Human Surface Traversal Modelling Engine (Prompt 20 Parts 1, 2.1, 5).

Strictly separates three locomotion model categories:
  1. USER_CONFIGURED_CONSTANT_SPEED (Category A):
     Explicit user-supplied reference walking speed v0 (m/s), with optional explicit
     user-defined slope/roughness penalty rules. Classified as USER_ASSUMED.
  2. TERRESTRIAL_HIKING_APPROXIMATION (Category B):
     Documented Tobler (1993) terrestrial hiking grade function anchored to user v0:
       v(s) = v0 * exp(-3.5 * |s + 0.05|) / exp(-3.5 * 0.05)
     where s = dz / d_horiz is the signed directional grade.
     Contains NO undocumented 55-degree linear attenuation or arbitrary 0.22 speed floor.
     Enforces an explicit valid slope domain [min_valid_slope_deg, max_valid_slope_deg]
     and labels outputs as exploratory terrestrial comparison only (NOT a Mars suit model).
  3. MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL (Category C):
     Returns MODEL_UNAVAILABLE unless a source-backed, validated pressurized spacesuit
     locomotion dataset is explicitly supplied. Never fabricates suit biomechanics.
"""

from __future__ import annotations

from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence
from pydantic import BaseModel, Field


from app.science.provenance_graph import ScientificDataClassification

# Unify EpistemicClassification to the single canonical ScientificDataClassification vocabulary.
EpistemicClassification = ScientificDataClassification


class ParameterProvenanceRecord(BaseModel):
    """Complete provenance and classification metadata for an operational or physical parameter (Part 1.3)."""

    parameter_name: str
    value: Optional[Any] = None
    unit: str
    classification: EpistemicClassification
    source_reference: str
    valid_domain: Optional[str] = None
    notes: str
    user_modified: bool = False
    version: str = "2.0.0"


class LocomotionModelCategory(str, Enum):
    """Explicit locomotion model categories (Part 2.1 & Part 5.1)."""

    USER_CONFIGURED_CONSTANT_SPEED = "USER_CONFIGURED_CONSTANT_SPEED"
    TERRESTRIAL_HIKING_APPROXIMATION = "TERRESTRIAL_HIKING_APPROXIMATION"
    TERRESTRIAL_WALKING_APPROXIMATION = "TERRESTRIAL_WALKING_APPROXIMATION"
    MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL = "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL"
    MISSION_VALIDATED_LOCOMOTION_MODEL = "MISSION_VALIDATED_LOCOMOTION_MODEL"


class LocomotionEvaluationStatus(str, Enum):
    """Explicit evaluation status for a locomotion calculation."""

    EVALUATED = "EVALUATED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MISSING_REFERENCE_SPEED = "MISSING_REFERENCE_SPEED"
    OUTSIDE_LOCOMOTION_VALID_DOMAIN = "OUTSIDE_LOCOMOTION_VALID_DOMAIN"
    BLOCKED_BY_UNKNOWN_TERRAIN = "BLOCKED_BY_UNKNOWN_TERRAIN"
    NOT_EVALUATED = "NOT_EVALUATED"


TOBLER_1993_FLAT_NORMALIZATION = math.exp(-3.5 * 0.05)  # exp(-0.175) = 0.8394570207693855
TOBLER_1993_CITATION = (
    "Tobler, W. (1993), 'Three Presentations on Geographical Analysis and Modeling: "
    "Non-Isotropic Geographic Modeling; Speculations on the Geometry of Geography; "
    "and Global Spatial Analysis', Technical Report 93-1, NCGIA, UC Santa Barbara."
)


class LocomotionModelDescriptor(BaseModel):
    """Inspectable metadata describing a locomotion model's equations, domain, and limitations."""

    model_id: str
    model_version: str
    category: LocomotionModelCategory
    available: bool
    classification: EpistemicClassification
    mathematical_formulation: str
    citation_or_source: str
    valid_slope_domain_deg: Optional[List[float]] = None
    valid_roughness_domain_m: Optional[List[float]] = None
    is_validated_mars_suit_model: bool = False
    limitations: List[str] = Field(default_factory=list)


class SegmentLocomotionEvaluation(BaseModel):
    """Segment-level locomotion speed and duration evaluation (Part 5.2)."""

    segment_index: int
    horizontal_distance_m: float
    surface_distance_m: float
    elevation_change_m: float
    signed_grade: float
    slope_deg: float
    roughness_tri_m: Optional[float] = None
    traversability_evidence_state: str = "EVALUATED_WITH_AVAILABLE_EVIDENCE"
    locomotion_category: LocomotionModelCategory
    model_id: str
    model_version: str
    status: LocomotionEvaluationStatus
    classification: EpistemicClassification
    reference_speed_mps: Optional[float] = None
    grade_speed_factor: Optional[float] = None
    roughness_speed_factor: Optional[float] = None
    effective_speed_mps: Optional[float] = None
    duration_s: Optional[float] = None
    notes: List[str] = Field(default_factory=list)


class LocomotionScenarioComparisonEntry(BaseModel):
    """Comparison entry for a single locomotion scenario across outbound and return paths (Part 5.4)."""

    scenario_id: str
    scenario_label: str
    category: LocomotionModelCategory
    model_id: str
    reference_speed_mps: Optional[float] = None
    status: LocomotionEvaluationStatus
    classification: EpistemicClassification
    outbound_duration_s: Optional[float] = None
    return_duration_s: Optional[float] = None
    total_traverse_duration_s: Optional[float] = None
    mean_effective_speed_mps: Optional[float] = None
    min_effective_speed_mps: Optional[float] = None
    max_effective_speed_mps: Optional[float] = None
    within_mission_duration_limit: Optional[bool] = None
    disclosure: str


def normalize_locomotion_category(
    category: Optional[str | LocomotionModelCategory],
    use_tobler_grade_approximation: bool = False,
) -> LocomotionModelCategory:
    """Resolve locomotion category from explicit category or legacy boolean flag."""
    if category is not None:
        val = category.value if isinstance(category, LocomotionModelCategory) else str(category).strip().upper()
        if val in {
            LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION.value,
            LocomotionModelCategory.TERRESTRIAL_WALKING_APPROXIMATION.value,
            "TOBLER",
            "TOBLER_1993",
        }:
            return LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
        if val in {
            LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL.value,
            LocomotionModelCategory.MISSION_VALIDATED_LOCOMOTION_MODEL.value,
            "VALIDATED_SUIT",
        }:
            return LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL
        return LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED
    if use_tobler_grade_approximation:
        return LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
    return LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED


def get_locomotion_model_descriptor(
    category: LocomotionModelCategory,
    *,
    min_valid_slope_deg: float = -35.0,
    max_valid_slope_deg: float = 35.0,
    validated_suit_model_source: Optional[str] = None,
) -> LocomotionModelDescriptor:
    """Return complete inspectable model metadata for the selected locomotion category."""
    norm_cat = normalize_locomotion_category(category)
    if norm_cat == LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED:
        return LocomotionModelDescriptor(
            model_id="MARSCOPE-LOCO-CONST-v2.0",
            model_version="2.0.0",
            category=LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
            available=True,
            classification=EpistemicClassification.USER_ASSUMED,
            mathematical_formulation="v_eff = v_0; t_seg = d_horiz / v_0 (for v_0 > 0 m/s)",
            citation_or_source="User-configured operational reference walking speed (explicit operator input).",
            valid_slope_domain_deg=[min_valid_slope_deg, max_valid_slope_deg],
            is_validated_mars_suit_model=False,
            limitations=[
                "Assumes constant horizontal ground speed equal to user-configured v_0 across all traversable slopes.",
                "Does not model pressurized spacesuit joint torque, metabolic fatigue, or regolith sinkage/slip.",
            ],
        )

    if norm_cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION:
        return LocomotionModelDescriptor(
            model_id="MARSCOPE-LOCO-TOBLER-1993-v2.0",
            model_version="2.0.0",
            category=LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
            available=True,
            classification=EpistemicClassification.MODELLED,
            mathematical_formulation=(
                "s = dz / d_horiz; f_Tobler(s) = exp(-3.5 * |s + 0.05|) / exp(-3.5 * 0.05); "
                "v_eff(s) = v_0 * f_Tobler(s); t_seg = d_horiz / v_eff(s)"
            ),
            citation_or_source=TOBLER_1993_CITATION,
            valid_slope_domain_deg=[min_valid_slope_deg, max_valid_slope_deg],
            is_validated_mars_suit_model=False,
            limitations=[
                "Empirical terrestrial unencumbered human footpath hiking formulation (Tobler, 1993).",
                "NOT a validated Martian pressurized spacesuit or 0.38g partial-gravity locomotion model.",
                "Provided strictly for exploratory sensitivity and asymmetric uphill/downhill grade comparison.",
                f"Segments outside valid slope domain [{min_valid_slope_deg:.1f} deg, {max_valid_slope_deg:.1f} deg] are flagged OUTSIDE_LOCOMOTION_VALID_DOMAIN rather than clamped to an arbitrary speed floor.",
            ],
        )

    has_suit_source = bool(validated_suit_model_source and validated_suit_model_source.strip())
    return LocomotionModelDescriptor(
        model_id="MARSCOPE-LOCO-VALIDATED-SUIT-v2.0",
        model_version="2.0.0",
        category=LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL,
        available=has_suit_source,
        classification=(
            EpistemicClassification.MODELLED if has_suit_source else EpistemicClassification.UNAVAILABLE
        ),
        mathematical_formulation=(
            "Requires empirical pressurized spacesuit biomechanics lookup table v_suit(grade, roughness, load) "
            "from authenticated human-in-the-loop partial-gravity test data."
        ),
        citation_or_source=(
            validated_suit_model_source.strip()
            if has_suit_source and validated_suit_model_source
            else "MODEL_UNAVAILABLE — No validated Martian pressurized EVA suit locomotion dataset is loaded in the repository."
        ),
        valid_slope_domain_deg=[min_valid_slope_deg, max_valid_slope_deg] if has_suit_source else None,
        is_validated_mars_suit_model=has_suit_source,
        limitations=[
            "No validated Martian EVA spacesuit biomechanics model is bundled with MARSCOPE.",
            "System refuses to fabricate suit joint resistances, center-of-mass shifts, or partial-gravity gait speeds.",
        ],
    )


def evaluate_segment_locomotion(
    *,
    segment_index: int,
    horizontal_distance_m: float,
    elevation_change_m: float,
    slope_deg: float,
    roughness_tri_m: Optional[float] = None,
    reference_speed_mps: Optional[float] = None,
    category: LocomotionModelCategory | str = LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
    use_tobler_grade_approximation: bool = False,
    min_valid_slope_deg: float = -35.0,
    max_valid_slope_deg: float = 35.0,
    roughness_penalty_per_m: Optional[float] = None,
    traversability_evidence_state: str = "EVALUATED_WITH_AVAILABLE_EVIDENCE",
    validated_suit_model_source: Optional[str] = None,
) -> SegmentLocomotionEvaluation:
    """
    Evaluate segment locomotion speed and duration honestly under the selected model category.
    Never injects arbitrary speed floors or undocumented linear slope attenuations.
    """
    norm_cat = normalize_locomotion_category(category, use_tobler_grade_approximation)
    desc = get_locomotion_model_descriptor(
        norm_cat,
        min_valid_slope_deg=min_valid_slope_deg,
        max_valid_slope_deg=max_valid_slope_deg,
        validated_suit_model_source=validated_suit_model_source,
    )

    horiz = max(0.0, float(horizontal_distance_m))
    dz = float(elevation_change_m)
    surf = math.hypot(horiz, dz)
    signed_grade = dz / max(0.1, horiz) if horiz > 0.0 else 0.0
    signed_slope_deg = math.degrees(math.atan(signed_grade)) if horiz > 0.0 else 0.0
    eff_slope_mag = max(abs(float(slope_deg)), abs(signed_slope_deg))

    if norm_cat == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL and not desc.available:
        return SegmentLocomotionEvaluation(
            segment_index=segment_index,
            horizontal_distance_m=round(horiz, 3),
            surface_distance_m=round(surf, 3),
            elevation_change_m=round(dz, 3),
            signed_grade=round(signed_grade, 5),
            slope_deg=round(eff_slope_mag, 3),
            roughness_tri_m=round(roughness_tri_m, 3) if roughness_tri_m is not None else None,
            traversability_evidence_state=traversability_evidence_state,
            locomotion_category=norm_cat,
            model_id=desc.model_id,
            model_version=desc.model_version,
            status=LocomotionEvaluationStatus.MODEL_UNAVAILABLE,
            classification=EpistemicClassification.UNAVAILABLE,
            reference_speed_mps=reference_speed_mps,
            notes=[
                "MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL is MODEL_UNAVAILABLE: no validated Martian spacesuit locomotion model is supplied."
            ],
        )

    if reference_speed_mps is None or reference_speed_mps <= 0.0:
        return SegmentLocomotionEvaluation(
            segment_index=segment_index,
            horizontal_distance_m=round(horiz, 3),
            surface_distance_m=round(surf, 3),
            elevation_change_m=round(dz, 3),
            signed_grade=round(signed_grade, 5),
            slope_deg=round(eff_slope_mag, 3),
            roughness_tri_m=round(roughness_tri_m, 3) if roughness_tri_m is not None else None,
            traversability_evidence_state=traversability_evidence_state,
            locomotion_category=norm_cat,
            model_id=desc.model_id,
            model_version=desc.model_version,
            status=LocomotionEvaluationStatus.MISSING_REFERENCE_SPEED,
            classification=EpistemicClassification.UNAVAILABLE,
            reference_speed_mps=None,
            notes=["User reference walking speed (walking_speed_mps) was not supplied."],
        )

    if traversability_evidence_state in {
        "UNKNOWN_NO_VALID_TERRAIN",
        "UNKNOWN_REGISTRATION_FAILURE",
    }:
        return SegmentLocomotionEvaluation(
            segment_index=segment_index,
            horizontal_distance_m=round(horiz, 3),
            surface_distance_m=round(surf, 3),
            elevation_change_m=round(dz, 3),
            signed_grade=round(signed_grade, 5),
            slope_deg=round(eff_slope_mag, 3),
            roughness_tri_m=round(roughness_tri_m, 3) if roughness_tri_m is not None else None,
            traversability_evidence_state=traversability_evidence_state,
            locomotion_category=norm_cat,
            model_id=desc.model_id,
            model_version=desc.model_version,
            status=LocomotionEvaluationStatus.BLOCKED_BY_UNKNOWN_TERRAIN,
            classification=EpistemicClassification.UNAVAILABLE,
            reference_speed_mps=round(float(reference_speed_mps), 4),
            notes=[f"Segment blocked by unknown terrain state: {traversability_evidence_state}"],
        )

    if signed_slope_deg < min_valid_slope_deg or signed_slope_deg > max_valid_slope_deg or eff_slope_mag > max(abs(min_valid_slope_deg), abs(max_valid_slope_deg)):
        return SegmentLocomotionEvaluation(
            segment_index=segment_index,
            horizontal_distance_m=round(horiz, 3),
            surface_distance_m=round(surf, 3),
            elevation_change_m=round(dz, 3),
            signed_grade=round(signed_grade, 5),
            slope_deg=round(eff_slope_mag, 3),
            roughness_tri_m=round(roughness_tri_m, 3) if roughness_tri_m is not None else None,
            traversability_evidence_state=traversability_evidence_state,
            locomotion_category=norm_cat,
            model_id=desc.model_id,
            model_version=desc.model_version,
            status=LocomotionEvaluationStatus.OUTSIDE_LOCOMOTION_VALID_DOMAIN,
            classification=EpistemicClassification.UNAVAILABLE,
            reference_speed_mps=round(float(reference_speed_mps), 4),
            notes=[
                f"Segment slope ({eff_slope_mag:.2f} deg) lies outside configured locomotion valid domain [{min_valid_slope_deg:.1f}, {max_valid_slope_deg:.1f}] deg."
            ],
        )

    v0 = float(reference_speed_mps)
    notes: List[str] = []
    if norm_cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION:
        grade_factor = math.exp(-3.5 * abs(signed_grade + 0.05)) / TOBLER_1993_FLAT_NORMALIZATION
        classification = EpistemicClassification.MODELLED
        notes.append(
            "Evaluated using pure Tobler (1993) terrestrial hiking grade formula f(s) = exp(-3.5*|s+0.05|)/exp(-0.175) (exploratory terrestrial comparison, not a Mars suit model)."
        )
    else:
        grade_factor = 1.0
        classification = EpistemicClassification.USER_ASSUMED
        notes.append("Evaluated using user-configured constant horizontal walking speed v_0.")

    rough_factor = 1.0
    if roughness_penalty_per_m is not None and roughness_penalty_per_m > 0.0 and roughness_tri_m is not None:
        rough_factor = max(0.1, 1.0 - float(roughness_penalty_per_m) * max(0.0, float(roughness_tri_m)))
        notes.append(f"Applied explicit user roughness speed factor f_rough={rough_factor:.4f}.")

    v_eff = v0 * grade_factor * rough_factor
    dur_s = horiz / v_eff if (horiz > 0.0 and v_eff > 0.0) else 0.0

    return SegmentLocomotionEvaluation(
        segment_index=segment_index,
        horizontal_distance_m=round(horiz, 3),
        surface_distance_m=round(surf, 3),
        elevation_change_m=round(dz, 3),
        signed_grade=round(signed_grade, 5),
        slope_deg=round(eff_slope_mag, 3),
        roughness_tri_m=round(roughness_tri_m, 3) if roughness_tri_m is not None else None,
        traversability_evidence_state=traversability_evidence_state,
        locomotion_category=norm_cat,
        model_id=desc.model_id,
        model_version=desc.model_version,
        status=LocomotionEvaluationStatus.EVALUATED,
        classification=classification,
        reference_speed_mps=round(v0, 4),
        grade_speed_factor=round(grade_factor, 4),
        roughness_speed_factor=round(rough_factor, 4),
        effective_speed_mps=round(v_eff, 4),
        duration_s=round(dur_s, 2),
        notes=notes,
    )


def compare_locomotion_scenarios(
    *,
    outbound_segments: Sequence[Dict[str, Any]],
    return_segments: Sequence[Dict[str, Any]],
    base_speed_mps: Optional[float],
    mission_duration_limit_s: Optional[float] = None,
    operational_overhead_s: float = 0.0,
) -> List[LocomotionScenarioComparisonEntry]:
    """
    Compare multiple locomotion speed & model scenarios across the exact outbound and return segments (Part 5.4).
    """
    v_ref = base_speed_mps if (base_speed_mps is not None and base_speed_mps > 0.0) else 0.75
    scenarios = [
        (
            "const_conservative_speed",
            f"Constant Reference Speed ({max(0.25, round(v_ref * 0.75, 2)):.2f} m/s, -25%)",
            LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
            max(0.25, round(v_ref * 0.75, 4)),
        ),
        (
            "const_nominal_speed",
            f"Constant Reference Speed ({v_ref:.2f} m/s, User Baseline)",
            LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
            v_ref,
        ),
        (
            "const_brisk_speed",
            f"Constant Reference Speed ({min(2.5, round(v_ref * 1.25, 2)):.2f} m/s, +25%)",
            LocomotionModelCategory.USER_CONFIGURED_CONSTANT_SPEED,
            min(2.5, round(v_ref * 1.25, 4)),
        ),
        (
            "tobler_1993_terrestrial_grade",
            f"Terrestrial Hiking Grade Approximation (Tobler 1993 @ {v_ref:.2f} m/s)",
            LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION,
            v_ref,
        ),
        (
            "validated_mars_suit_model",
            "Mission-Validated Pressurized Suit Locomotion Model",
            LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL,
            v_ref,
        ),
    ]

    results: List[LocomotionScenarioComparisonEntry] = []
    for scen_id, label, cat, spd in scenarios:
        desc = get_locomotion_model_descriptor(cat)
        if cat == LocomotionModelCategory.MISSION_VALIDATED_SUIT_LOCOMOTION_MODEL:
            results.append(
                LocomotionScenarioComparisonEntry(
                    scenario_id=scen_id.strip(),
                    scenario_label=label,
                    category=cat,
                    model_id=desc.model_id,
                    reference_speed_mps=None,
                    status=LocomotionEvaluationStatus.MODEL_UNAVAILABLE,
                    classification=EpistemicClassification.UNAVAILABLE,
                    outbound_duration_s=None,
                    return_duration_s=None,
                    total_traverse_duration_s=None,
                    mean_effective_speed_mps=None,
                    min_effective_speed_mps=None,
                    max_effective_speed_mps=None,
                    within_mission_duration_limit=None,
                    disclosure=(
                        "MODEL_UNAVAILABLE — No validated Martian pressurized suit biomechanics dataset is loaded; "
                        "MARSCOPE refuses to fabricate suit locomotion speeds."
                    ),
                )
            )
            continue

        out_evals = [
            evaluate_segment_locomotion(
                segment_index=i,
                horizontal_distance_m=float(s.get("horizontal_distance_m", 0.0)),
                elevation_change_m=float(s.get("elevation_change_m", 0.0)),
                slope_deg=float(s.get("slope_deg", 0.0)),
                roughness_tri_m=s.get("roughness_tri_m"),
                reference_speed_mps=spd,
                category=cat,
            )
            for i, s in enumerate(outbound_segments)
        ]
        ret_evals = [
            evaluate_segment_locomotion(
                segment_index=i,
                horizontal_distance_m=float(s.get("horizontal_distance_m", 0.0)),
                elevation_change_m=float(s.get("elevation_change_m", 0.0)),
                slope_deg=float(s.get("slope_deg", 0.0)),
                roughness_tri_m=s.get("roughness_tri_m"),
                reference_speed_mps=spd,
                category=cat,
            )
            for i, s in enumerate(return_segments)
        ]

        all_ok = all(e.status == LocomotionEvaluationStatus.EVALUATED for e in out_evals + ret_evals)
        if not all_ok:
            results.append(
                LocomotionScenarioComparisonEntry(
                    scenario_id=scen_id.strip(),
                    scenario_label=label,
                    category=cat,
                    model_id=desc.model_id,
                    reference_speed_mps=spd,
                    status=LocomotionEvaluationStatus.OUTSIDE_LOCOMOTION_VALID_DOMAIN,
                    classification=desc.classification,
                    disclosure="One or more segments exceeded the valid slope domain of this locomotion model.",
                )
            )
            continue

        out_s = sum(e.duration_s or 0.0 for e in out_evals)
        ret_s = sum(e.duration_s or 0.0 for e in ret_evals)
        tot_s = out_s + ret_s + max(0.0, float(operational_overhead_s))
        speeds = [e.effective_speed_mps for e in (out_evals + ret_evals) if e.effective_speed_mps is not None and e.horizontal_distance_m > 0]
        within = (tot_s <= mission_duration_limit_s) if mission_duration_limit_s is not None else None

        results.append(
            LocomotionScenarioComparisonEntry(
                scenario_id=scen_id.strip(),
                scenario_label=label,
                category=cat,
                model_id=desc.model_id,
                reference_speed_mps=spd,
                status=LocomotionEvaluationStatus.EVALUATED,
                classification=desc.classification,
                outbound_duration_s=round(out_s, 2),
                return_duration_s=round(ret_s, 2),
                total_traverse_duration_s=round(tot_s, 2),
                mean_effective_speed_mps=round(sum(speeds) / len(speeds), 4) if speeds else spd,
                min_effective_speed_mps=round(min(speeds), 4) if speeds else spd,
                max_effective_speed_mps=round(max(speeds), 4) if speeds else spd,
                within_mission_duration_limit=within,
                disclosure=(
                    "Exploratory terrestrial hiking grade comparison (Tobler, 1993) — NOT a validated Mars suit model."
                    if cat == LocomotionModelCategory.TERRESTRIAL_HIKING_APPROXIMATION
                    else "User-configured constant flat-ground walking speed assumption (USER_ASSUMED)."
                ),
            )
        )

    return results
