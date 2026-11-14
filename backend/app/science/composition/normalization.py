"""
MARSCOPE Geochemical Unit Normalization & Oxide Stoichiometry Module
Martian Surface Intelligence & Exploration System

Performs documented, reproducible unit normalization and IUPAC stoichiometric oxide-to-element
conversions while always preserving the original reported value, unit, and formula.
"""

import math
from typing import Optional, Tuple
from app.science.composition.models import SpeciesCategory, SpeciesRecord
from app.science.composition.species import get_species_by_id


class NormalizationError(ValueError):
    """Raised when a unit or stoichiometric conversion is physically invalid or undocumented."""


_WT_PCT_ALIASES = {"wt%", "wt_pct", "weight_percent", "pct", "%", "percent"}
_PPM_ALIASES = {"ppm", "ug/g", "mg/kg", "parts_per_million"}


def canonicalize_unit(raw_unit: Optional[str]) -> str:
    if not raw_unit or not str(raw_unit).strip():
        raise NormalizationError("Measurement unit is empty or missing.")
    low = str(raw_unit).strip().lower()
    if low in _WT_PCT_ALIASES:
        return "wt%"
    if low in _PPM_ALIASES:
        return "ppm"
    raise NormalizationError(
        f"Unsupported or non-compositional unit '{raw_unit}'; expected 'wt%' or 'ppm'."
    )


def normalize_concentration_value(
    species: SpeciesRecord,
    raw_value: float,
    raw_unit: str,
    target_unit: Optional[str] = None,
) -> Tuple[float, str, Optional[str]]:
    """
    Normalize concentration into canonical unit ('wt%' or 'ppm') without converting minerals
    to elemental mass fractions.
    Returns (normalized_value, normalized_unit, formula_note).
    """
    if not math.isfinite(raw_value):
        raise NormalizationError("Non-finite measurement value cannot be normalized.")

    canon_src = canonicalize_unit(raw_unit)
    dest = canon_src if target_unit is None else canonicalize_unit(target_unit)

    if canon_src == dest:
        return round(float(raw_value), 6), dest, f"identity ({dest})"

    if canon_src == "ppm" and dest == "wt%":
        # 10,000 ppm == 1 wt%
        return round(float(raw_value) / 10000.0, 6), "wt%", "ppm / 10000 -> wt%"

    if canon_src == "wt%" and dest == "ppm":
        return round(float(raw_value) * 10000.0, 4), "ppm", "wt% * 10000 -> ppm"

    raise NormalizationError(f"Unsupported unit conversion from '{canon_src}' to '{dest}'.")


def oxide_wt_pct_to_element_wt_pct(
    oxide_species_id: str,
    oxide_wt_pct: float,
    oxide_uncertainty_wt_pct: Optional[float] = None,
) -> Tuple[str, float, Optional[float], str]:
    """
    Convert calibrated oxide concentration (wt%) into elemental mass concentration (wt%)
    using exact IUPAC stoichiometric atomic weights from species vocabulary.
    """
    if not math.isfinite(oxide_wt_pct):
        raise NormalizationError("Oxide value must be finite.")
    ox_spec = get_species_by_id(oxide_species_id)
    if not ox_spec or ox_spec.category != SpeciesCategory.OXIDE:
        raise NormalizationError(f"'{oxide_species_id}' is not a registered stoichiometric oxide.")
    if not ox_spec.stoichiometric_element or not ox_spec.stoichiometric_mass_fraction:
        raise NormalizationError(f"Missing stoichiometric factor for oxide '{oxide_species_id}'.")

    factor = ox_spec.stoichiometric_mass_fraction
    elem_val = round(float(oxide_wt_pct) * factor, 6)
    elem_err = (
        round(float(oxide_uncertainty_wt_pct) * factor, 6)
        if oxide_uncertainty_wt_pct is not None and math.isfinite(oxide_uncertainty_wt_pct)
        else None
    )
    formula = f"{ox_spec.canonical_id} wt% * {factor} (IUPAC stoichiometry) -> {ox_spec.stoichiometric_element} wt%"
    return ox_spec.stoichiometric_element, elem_val, elem_err, formula
