"""
MARSCOPE Source Value Semantics (Prompt 8 correction)

A reported numerical zero is NOT automatically a below-detection-limit (BDL) result.
BDL, missing, or invalid meanings are assigned ONLY when the source label/special-constant
declarations establish them. Otherwise a reported zero is preserved exactly with an explicit
"unresolved zero semantics" interpretation limitation. No detection limit is ever invented.
"""

from enum import Enum
from typing import Mapping, Optional, Tuple


class ValueSemantics(str, Enum):
    REPORTED_VALUE = "reported_value"
    REPORTED_NUMERICAL_ZERO_UNRESOLVED = "reported_numerical_zero_unresolved_semantics"
    SOURCE_DEFINED_BELOW_DETECTION_LIMIT = "source_defined_below_detection_limit"
    SOURCE_DEFINED_MISSING = "source_defined_missing"
    NULL_OR_BLANK = "null_or_blank"


_BDL_KEYS = ("detection_limit", "below_detection", "lod")
_MISSING_KEYS = ("missing", "invalid", "unknown", "null", "not_applicable", "saturation")


def _norm_token(tok: Optional[str]) -> str:
    return (tok or "").strip().strip('"').strip("'")


def _numeric_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def classify_value_semantics(
    value: Optional[float],
    raw_token: Optional[str],
    special_constants: Optional[Mapping[str, str]] = None,
) -> Tuple[ValueSemantics, str]:
    """
    Classify a reported cell using ONLY source-declared special constants.

    special_constants maps the source-declared constant name (e.g. PDS4 'missing_constant',
    PDS3 'MISSING_CONSTANT', or a source-documented '..._detection_limit_...' flag) to its token.
    """
    tok = _norm_token(raw_token)
    for name, const_tok in (special_constants or {}).items():
        ct = _norm_token(str(const_tok))
        if not ct or not tok or not _numeric_equal(tok, ct):
            continue
        lname = str(name).lower()
        if any(k in lname for k in _BDL_KEYS):
            return (
                ValueSemantics.SOURCE_DEFINED_BELOW_DETECTION_LIMIT,
                f"Source label declares token '{tok}' as '{name}' (below-detection-limit semantics defined by the source).",
            )
        if any(k in lname for k in _MISSING_KEYS):
            return (
                ValueSemantics.SOURCE_DEFINED_MISSING,
                f"Source label declares token '{tok}' as special constant '{name}' (missing/invalid value).",
            )
        return (
            ValueSemantics.SOURCE_DEFINED_MISSING,
            f"Source label declares token '{tok}' as special constant '{name}' (non-measurement value).",
        )

    if value is None:
        return (
            ValueSemantics.NULL_OR_BLANK,
            "Source cell is blank or a null token that the source label does not define as a measurement.",
        )
    if value == 0.0:
        return (
            ValueSemantics.REPORTED_NUMERICAL_ZERO_UNRESOLVED,
            "Reported numerical zero preserved exactly. The source product/label does not establish that zero "
            "denotes below-detection-limit, missing, or absent; no detection limit is assumed.",
        )
    return ValueSemantics.REPORTED_VALUE, "Reported non-zero numerical value."
