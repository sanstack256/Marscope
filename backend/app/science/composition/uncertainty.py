"""
MARSCOPE Measurement Uncertainty Semantics & Compatibility Registry
Martian Surface Intelligence & Exploration System

Explicitly encodes the statistical definition of each instrument uncertainty
product (APXS precision error, ChemCam PLS RMSEP, ChemCam shot standard
deviation, CheMin TOPAS Rietveld 2-sigma, CheMin unspecified ESTIMATED_ERROR)
and enforces strict comparability guards so heterogeneous statistical metrics
are never merged into a single misleading "quality" or "confidence" score.
"""

from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field


SEMANTIC_NON_DIMENSIONAL_UNCERTAINTY_UNITS = {
    "ESTIMATED_ERROR",
    "UNSPECIFIED_IN_SCHEMA",
    "NON_DIMENSIONAL",
}


class UncertaintyTypeSpec(BaseModel):
    uncertainty_type: str
    statistical_family: str
    statistical_interpretation: str
    coverage_confidence_level: str
    comparability_group: str
    allows_within_family_quality_scoring: bool = False
    allows_relative_uncertainty: bool = False
    default_source_definition: str


UNCERTAINTY_COMPATIBILITY_REGISTRY: Dict[str, UncertaintyTypeSpec] = {
    "apxs_analytical_precision": UncertaintyTypeSpec(
        uncertainty_type="apxs_analytical_precision",
        statistical_family="instrumental_analytical_precision",
        statistical_interpretation=(
            "Per-target analytical precision error reported by the APXS RGFit calibration table; "
            "reflects counting statistics / spectrum fit precision rather than inter-spot spatial variation."
        ),
        coverage_confidence_level="unspecified_in_pds4_label",
        comparability_group="apxs_analytical_precision",
        allows_within_family_quality_scoring=True,
        allows_relative_uncertainty=True,
        default_source_definition="Precision Error in Oxide/Element Concentration (PDS4 Field_Delimited description)",
    ),
    "chemcam_pls_rmsep": UncertaintyTypeSpec(
        uncertainty_type="chemcam_pls_rmsep",
        statistical_family="regression_model_prediction_rmsep",
        statistical_interpretation=(
            "Multivariate PLS+ICA regression Root Mean Square Error of Prediction (RMSEP) derived from "
            "calibration test standards; quantifies model calibration prediction error, NOT single-target "
            "counting precision or shot-to-shot heterogeneity."
        ),
        coverage_confidence_level="model_rmsep_test_set",
        comparability_group="chemcam_pls_rmsep",
        allows_within_family_quality_scoring=True,
        allows_relative_uncertainty=True,
        default_source_definition="Predicted <OXIDE>_RMSEP (ChemCam MOC PDS3 SPREADSHEET FIELD)",
    ),
    "chemcam_shots_stdev": UncertaintyTypeSpec(
        uncertainty_type="chemcam_shots_stdev",
        statistical_family="intra_target_shot_standard_deviation",
        statistical_interpretation=(
            "Sample standard deviation (1-sigma dispersion) across multiple LIBS laser shots at a single "
            "target point; reflects intra-spot heterogeneity / shot repeatability, not calibration accuracy."
        ),
        coverage_confidence_level="1_sigma_sample_stdev",
        comparability_group="chemcam_shots_stdev",
        allows_within_family_quality_scoring=True,
        allows_relative_uncertainty=True,
        default_source_definition="<OXIDE>_SHOTS_STDEV standard deviation (ChemCam MOC PDS3 SPREADSHEET FIELD)",
    ),
    "chemin_rietveld_2sigma": UncertaintyTypeSpec(
        uncertainty_type="chemin_rietveld_2sigma",
        statistical_family="rietveld_refinement_2sigma_error",
        statistical_interpretation=(
            "Estimated 2-sigma analytical uncertainty from TOPAS/JADE Rietveld XRD whole-pattern refinement "
            "(nominal ~95% interval under model assumptions) as explicitly documented in the CheMin PDS3 label. "
            "In CHEMIN_MIN.FMT, ERROR uses semantic UNIT='ESTIMATED_ERROR' rather than an explicit physical wt% unit."
        ),
        coverage_confidence_level="2_sigma_documented",
        comparability_group="chemin_rietveld_2sigma",
        allows_within_family_quality_scoring=True,
        allows_relative_uncertainty=True,
        default_source_definition="CHEMIN_MIN.FMT ERROR (ESTIMATED_ERROR) qualified by PDS3 SPREADSHEET DESCRIPTION (2-sigma analytical errors)",
    ),
    "chemin_estimated_error_unspecified_sigma": UncertaintyTypeSpec(
        uncertainty_type="chemin_estimated_error_unspecified_sigma",
        statistical_family="rietveld_estimated_error_unspecified",
        statistical_interpretation=(
            "CHEMIN_MIN.FMT declares UNIT = ESTIMATED_ERROR without an explicit sigma multiplier in the "
            "companion PDS3 label; statistical coverage level is unspecified and not comparable across instruments."
        ),
        coverage_confidence_level="unspecified",
        comparability_group="incompatible_unspecified",
        allows_within_family_quality_scoring=False,
        allows_relative_uncertainty=False,
        default_source_definition="CHEMIN_MIN.FMT ERROR (UNIT = ESTIMATED_ERROR; sigma not stated in PDS3 label)",
    ),
    "unknown": UncertaintyTypeSpec(
        uncertainty_type="unknown",
        statistical_family="unknown",
        statistical_interpretation=(
            "Uncertainty statistical definition could not be established from verified PDS metadata."
        ),
        coverage_confidence_level="unspecified",
        comparability_group="incompatible_unknown",
        allows_within_family_quality_scoring=False,
        allows_relative_uncertainty=False,
        default_source_definition="Unreported or unverified uncertainty definition",
    ),
}

_UNCERTAINTY_ALIASES: Dict[str, str] = {
    "apxs_analytical_precision": "apxs_analytical_precision",
    "reported_apxs_analytical_error": "apxs_analytical_precision",
    "chemcam_pls_rmsep": "chemcam_pls_rmsep",
    "rmsep": "chemcam_pls_rmsep",
    "chemcam_shots_stdev": "chemcam_shots_stdev",
    "shots_stdev": "chemcam_shots_stdev",
    "chemin_rietveld_2sigma": "chemin_rietveld_2sigma",
    "topas_rietveld_2_sigma_error": "chemin_rietveld_2sigma",
    "topas_rietveld_2sigma": "chemin_rietveld_2sigma",
    "chemin_estimated_error_unspecified_sigma": "chemin_estimated_error_unspecified_sigma",
    "estimated_error": "chemin_estimated_error_unspecified_sigma",
    "unknown": "unknown",
}


@lru_cache(maxsize=256)
def canonicalize_uncertainty_type(raw_type: Optional[str]) -> str:
    """Normalize legacy or raw uncertainty type identifiers to canonical registry keys."""
    if not raw_type:
        return "unknown"
    key = raw_type.strip().lower()
    return _UNCERTAINTY_ALIASES.get(key, raw_type.strip() if raw_type.strip() in UNCERTAINTY_COMPATIBILITY_REGISTRY else "unknown")


def get_uncertainty_spec(uncertainty_type: Optional[str]) -> UncertaintyTypeSpec:
    """Return registry specification for a canonical or legacy uncertainty type."""
    canon = canonicalize_uncertainty_type(uncertainty_type)
    return UNCERTAINTY_COMPATIBILITY_REGISTRY.get(canon, UNCERTAINTY_COMPATIBILITY_REGISTRY["unknown"])


def evaluate_uncertainty_compatibility(
    ev_uncertainty_type: Optional[str],
    ev_uncertainty_value: Optional[float],
    cohort_uncertainty_types: Optional[Sequence[Optional[str]]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Determine whether `quality_component` may be computed legitimately.

    Rules:
    - Missing uncertainty value -> False ("unreported")
    - Unspecified or unknown uncertainty semantics -> False ("unspecified_or_unknown")
    - Cohort containing >= 2 incompatible uncertainty comparability groups -> False ("incompatible_mixed_uncertainty_types")
    - Homogeneous compatible cohort or single verified statistical family -> True ("compatible_single_family")
    """
    if ev_uncertainty_value is None:
        return False, "unreported", "Source record reports no quantitative uncertainty value; quality_component withheld."

    spec = get_uncertainty_spec(ev_uncertainty_type)
    if not spec.allows_within_family_quality_scoring:
        return (
            False,
            "unspecified_or_unknown",
            f"Uncertainty type '{spec.uncertainty_type}' lacks a documented quantitative statistical scale ({spec.coverage_confidence_level}); quality_component withheld.",
        )

    if cohort_uncertainty_types:
        distinct_types = sorted({canonicalize_uncertainty_type(t) for t in cohort_uncertainty_types if t is not None})
        groups = {get_uncertainty_spec(t).comparability_group for t in distinct_types}
        if len(groups) > 1 or any(not get_uncertainty_spec(t).allows_within_family_quality_scoring for t in distinct_types):
            return (
                False,
                "incompatible_mixed_uncertainty_types",
                (
                    f"Query cohort mixes statistically incompatible uncertainty types "
                    f"({', '.join(distinct_types)}); quantitative cross-instrument quality scoring withheld."
                ),
            )

    return True, "compatible_single_family", None


def normalize_uncertainty_unit(raw_unit: Optional[str]) -> Tuple[Optional[str], bool]:
    """
    Canonicalize a schema-declared uncertainty unit without inferring a physical unit from abundance.
    Returns (canonical_unit_or_None, is_physical_concentration_unit).
    """
    if raw_unit is None:
        return None, False
    cleaned = raw_unit.strip()
    if not cleaned:
        return None, False
    up = cleaned.upper()
    if up in {"WEIGHT_PERCENT", "WT%", "WT_PCT", "PERCENT", "%"}:
        return "wt%", True
    if up in {"PPM", "PARTS_PER_MILLION", "UG/G", "MG/KG"}:
        return "ppm", True
    if up in SEMANTIC_NON_DIMENSIONAL_UNCERTAINTY_UNITS or up in {"N/A", "NONE", "UNKNOWN"}:
        if up in {"N/A", "NONE", "UNKNOWN"}:
            return None, False
        return up, False
    return cleaned, False


def convert_uncertainty_to_unit(
    val: Optional[float],
    raw_unit: Optional[str],
    target_physical_unit: Optional[str],
) -> Tuple[Optional[float], Optional[str], List[str], bool]:
    """
    Convert a physical concentration uncertainty strictly when mathematically valid.
    Returns (converted_value, result_unit, conversion_history, converted_or_compatible).
    Never silently casts ESTIMATED_ERROR or missing/non-physical units into wt%.
    """
    if val is None:
        return None, None, [], False
    canon_raw, is_phys = normalize_uncertainty_unit(raw_unit)
    if not is_phys or canon_raw is None:
        return val, canon_raw, [], False
    if not target_physical_unit:
        return val, canon_raw, [], True
    tgt, tgt_phys = normalize_uncertainty_unit(target_physical_unit)
    if not tgt_phys or tgt is None:
        return val, canon_raw, [], False
    if canon_raw == tgt:
        return val, canon_raw, [], True
    if canon_raw == "ppm" and tgt == "wt%":
        conv = round(float(val) / 10000.0, 8)
        return conv, "wt%", [f"unit_conversion:ppm->wt% ({val} ppm -> {conv} wt%)"], True
    if canon_raw == "wt%" and tgt == "ppm":
        conv = round(float(val) * 10000.0, 4)
        return conv, "ppm", [f"unit_conversion:wt%->ppm ({val} wt% -> {conv} ppm)"], True
    return val, canon_raw, [], False
