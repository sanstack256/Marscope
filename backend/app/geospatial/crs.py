"""
MARSCOPE Mars Planetary Coordinate Intelligence Engine (Prompt 19 Part 3)
Martian Surface Intelligence & Exploration System

Versioned IAU/IAG/PDS Mars CRS registry, strict planetary reference validation
(never accepting Earth datums or arbitrary radii bands), traceable planetocentric /
planetographic transformations, vertical datum integrity checking, and 8-state
CoordinateValidationState propagation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

import pyproj
from pyproj import CRS, Transformer

from app.geospatial.models import (
    CRS_REGISTRY_VERSION,
    CoordinateTransformationResult,
    CoordinateValidationState,
    CrsCategory,
    CrsValidationResult,
    MarsCrsDefinition,
    VerticalDatumComparisonResult,
    VerticalDatumKind,
)

# Canonical IAU 2000 & NASA MGS MOLA Reference Constants (meters)
MARS_EQUATORIAL_RADIUS_M = 3396190.0
MARS_POLAR_RADIUS_M = 3376200.0
MARS_MEAN_RADIUS_M = 3389500.0
MARS_SPHERE_RADIUS_M = 3396000.0

# Strict documented Martian reference radii (radius tolerance <= 5.0 m ONLY)
_DOCUMENTED_MARS_RADII: List[Tuple[float, float, CrsCategory, str]] = [
    (3396190.0, 3376200.0, CrsCategory.IAU_ELLIPSOID, "IAU/IAG 2000 Mars Ellipsoid"),
    (3396190.0, 3396190.0, CrsCategory.IAU_SPHERE, "IAU/IAG 2000-2015 Mars Equatorial Sphere"),
    (3396000.0, 3396000.0, CrsCategory.IAU_SPHERE, "NASA MGS MOLA Reference Sphere (3396 km)"),
    (3389500.0, 3389500.0, CrsCategory.PRODUCT_SPECIFIC_DATUM, "IAU Mean Volumetric Mars Sphere"),
    (3394000.0, 3394000.0, CrsCategory.PRODUCT_SPECIFIC_DATUM, "Legacy USGS Viking 3394 km Sphere"),
]

_FORBIDDEN_BODY_TOKENS = (
    "WGS84",
    "WGS 84",
    "WGS_84",
    "EARTH",
    "GRS 80",
    "GRS80",
    "EPSG:4326",
    "EPSG:3857",
    "NAD83",
    "NAD27",
    "WEB MERCATOR",
    "PSEUDO-MERCATOR",
    "MOON",
    "LUNA",
    "MERCURY",
    "VENUS",
    "JUPITER",
    "SATURN",
)


# Backwards-compatible minimal dict kept for external imports, derived directly from authoritative registry
MARS_CRS_REGISTRY: Dict[str, MarsCrsDefinition] = {
    "IAU2000:49900": MarsCrsDefinition(
        identifier="IAU2000:49900",
        aliases=["IAU:49900", "IAU2000:49900_ELLIPSOID", "OGC:Mars2000"],
        crs_category=CrsCategory.IAU_ELLIPSOID,
        planetary_body="Mars",
        authority="IAU/IAG 2000 Cartographic Coordinates Working Group",
        authority_document="Seidelmann et al. (2002), Celestial Mechanics and Dynamical Astronomy 82, 83-111",
        specification_version="IAU2000",
        shape_type="ellipsoid",
        semi_major_axis_m=MARS_EQUATORIAL_RADIUS_M,
        semi_minor_axis_m=MARS_POLAR_RADIUS_M,
        reference_radii_m={"a": MARS_EQUATORIAL_RADIUS_M, "b": MARS_EQUATORIAL_RADIUS_M, "c": MARS_POLAR_RADIUS_M},
        coordinate_frame="IAU_MARS_2000_BODY_FIXED",
        latitude_convention="Planetocentric",
        longitude_convention="East",
        longitude_domain="[0, 360)",
        projection="Geographic 2D (Unprojected Aerocentric Long/Lat)",
        proj4_string=f"+proj=longlat +a={MARS_EQUATORIAL_RADIUS_M} +b={MARS_POLAR_RADIUS_M} +no_defs",
        vertical_reference=VerticalDatumKind.ELLIPSOID_RELATIVE_ELEVATION,
        vertical_datum_name="IAU2000 Mars Ellipsoid (or explicit product Areoid where documented)",
        validity_conditions=[
            "Requires explicit Planetocentric vs Planetographic latitude tag before meridional conversions.",
            "Elevations relative to Goddard/MOLA Areoid must NOT be mixed directly with ellipsoid heights without separation surface.",
        ],
        supported_transformations=[
            "IAU2000:MARS_SPHERE",
            "MARS:IAU2015_49900",
            "MARS:GALE_EQUIRECTANGULAR",
            "MARS:HIRISE_LOCAL_EQC",
        ],
        known_limitations=[
            "Oblate flattening (a-c = 19,990 m) produces up to ~0.34 deg latitude shift between Planetographic and Planetocentric near mid-latitudes.",
        ],
    ),
    "IAU2000:MARS_SPHERE": MarsCrsDefinition(
        identifier="IAU2000:MARS_SPHERE",
        aliases=["IAU2000:49901", "MOLA:SPHERE_3396000", "MARS:SPHERE_3396000"],
        crs_category=CrsCategory.IAU_SPHERE,
        planetary_body="Mars",
        authority="NASA GSFC MOLA Team / PDS Geosciences Node",
        authority_document="Smith et al. (2001) MOLA Science Team; MGS-M-MOLA-5-MEGDR-L3-V1.0 SIS",
        specification_version="MEGDR-L3-V1.0",
        shape_type="sphere",
        semi_major_axis_m=MARS_SPHERE_RADIUS_M,
        semi_minor_axis_m=MARS_SPHERE_RADIUS_M,
        reference_radii_m={"a": MARS_SPHERE_RADIUS_M, "b": MARS_SPHERE_RADIUS_M, "c": MARS_SPHERE_RADIUS_M},
        coordinate_frame="IAU_MARS_2000_MOLA_SPHERE",
        latitude_convention="Planetocentric",
        longitude_convention="East",
        longitude_domain="[0, 360)",
        projection="Simple Cylindrical / Geographic 2D Sphere",
        proj4_string=f"+proj=longlat +R={MARS_SPHERE_RADIUS_M} +no_defs",
        vertical_reference=VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
        vertical_datum_name="MOLA Goddard Mars Areoid (GMM-2B / MEGDR L3)",
        validity_conditions=[
            "MEGDR horizontal grid is defined on R = 3,396,000.0 m sphere while topography values represent height above MOLA Areoid.",
        ],
        supported_transformations=["IAU2000:49900", "MARS:GALE_EQUIRECTANGULAR"],
        known_limitations=[
            "Uses R = 3,396,000 m rather than IAU2000 equatorial 3,396,190 m (~0.0056% horizontal scale delta); MEGDR 128 ppd grid spacing is ~463 m/px at equator.",
        ],
    ),
    "MARS:IAU2015_49900": MarsCrsDefinition(
        identifier="MARS:IAU2015_49900",
        aliases=["IAU_2015:49900", "IAU:2015:49900"],
        crs_category=CrsCategory.IAU_SPHERE,
        planetary_body="Mars",
        authority="IAU/IAG 2015 Working Group (Archinal et al., 2018)",
        authority_document="Archinal et al. (2018), Celestial Mechanics and Dynamical Astronomy 130:22",
        specification_version="IAU2015",
        shape_type="sphere",
        semi_major_axis_m=MARS_EQUATORIAL_RADIUS_M,
        semi_minor_axis_m=MARS_EQUATORIAL_RADIUS_M,
        reference_radii_m={"a": MARS_EQUATORIAL_RADIUS_M, "b": MARS_EQUATORIAL_RADIUS_M, "c": MARS_EQUATORIAL_RADIUS_M},
        coordinate_frame="IAU_MARS_2015_BODY_FIXED",
        latitude_convention="Planetocentric",
        longitude_convention="East",
        longitude_domain="[0, 360)",
        projection="Geographic 2D Sphere (Equatorial Radius 3396.19 km)",
        proj4_string=f"+proj=longlat +R={MARS_EQUATORIAL_RADIUS_M} +no_defs",
        vertical_reference=VerticalDatumKind.REFERENCE_SPHERE_ELEVATION,
        vertical_datum_name="IAU 2015 Reference Sphere (R = 3,396,190 m)",
        validity_conditions=[
            "Recommended for IAU 2015 spherical planetary cartography and HiRISE DTM horizontal coordinates.",
        ],
        supported_transformations=["IAU2000:49900", "IAU2000:MARS_SPHERE", "MARS:GALE_EQUIRECTANGULAR", "MARS:HIRISE_LOCAL_EQC"],
        known_limitations=[
            "Identical horizontal sphere radius (3,396,190 m) to HiRISE EQC map projection; vertical datum differs if paired with Areoid heights.",
        ],
    ),
    "MARS:GALE_EQUIRECTANGULAR": MarsCrsDefinition(
        identifier="MARS:GALE_EQUIRECTANGULAR",
        aliases=["IAU2000:104905", "MSL:GALE_EQC"],
        crs_category=CrsCategory.LOCAL_STUDY_AREA_PROJECTION,
        planetary_body="Mars",
        authority="NASA/JPL Mars Science Laboratory MMGIS / Gale Working Group",
        authority_document="NASA/JPL MSL Gale Crater Equirectangular Projection Convention (R=3,396,190 m, clat=0, clon=0)",
        specification_version="MSL-MMGIS-V1",
        shape_type="sphere",
        semi_major_axis_m=MARS_EQUATORIAL_RADIUS_M,
        semi_minor_axis_m=MARS_EQUATORIAL_RADIUS_M,
        reference_radii_m={"a": MARS_EQUATORIAL_RADIUS_M, "b": MARS_EQUATORIAL_RADIUS_M, "c": MARS_EQUATORIAL_RADIUS_M},
        coordinate_frame="IAU_MARS_2000_BODY_FIXED",
        latitude_convention="Planetocentric",
        longitude_convention="East",
        longitude_domain="projected_meters",
        projection="Equirectangular (+lat_ts=0 +lat_0=0 +lon_0=0)",
        proj4_string=f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R={MARS_EQUATORIAL_RADIUS_M} +units=m +no_defs",
        vertical_reference=VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
        vertical_datum_name="MSL Gale Landing Site / MOLA Areoid Elevation Convention",
        validity_conditions=[
            "Valid only for equatorial / Gale Crater MSL planar Easting_m/Northing_m localization tables; distortion increases strongly above +/-15 deg latitude.",
        ],
        supported_transformations=["IAU2000:49900", "MARS:IAU2015_49900", "IAU2000:MARS_SPHERE", "MARS:HIRISE_LOCAL_EQC"],
        known_limitations=[
            "True scale preserved only at equator (lat_ts=0); at Gale (~ -4.7 deg) secant distortion is < 0.35%.",
        ],
    ),
    "MARS:HIRISE_LOCAL_EQC": MarsCrsDefinition(
        identifier="MARS:HIRISE_LOCAL_EQC",
        aliases=["HIRISE:GALE_EQC_137_41"],
        crs_category=CrsCategory.PROJECTED_PLANETARY_CRS,
        planetary_body="Mars",
        authority="NASA PDS / University of Arizona HiRISE DTM/Ortho Team",
        authority_document="MRO-M-HIRISE-5-DTM-V1.0 SIS (Equirectangular R=3,396,190 m, center_lon=137.41)",
        specification_version="HIRISE-DTM-V1.0",
        shape_type="sphere",
        semi_major_axis_m=MARS_EQUATORIAL_RADIUS_M,
        semi_minor_axis_m=MARS_EQUATORIAL_RADIUS_M,
        reference_radii_m={"a": MARS_EQUATORIAL_RADIUS_M, "b": MARS_EQUATORIAL_RADIUS_M, "c": MARS_EQUATORIAL_RADIUS_M},
        coordinate_frame="IAU_MARS_2000_BODY_FIXED",
        latitude_convention="Planetocentric",
        longitude_convention="East",
        longitude_domain="projected_meters",
        projection="Equirectangular (central_meridian=137.41, lat_ts=0)",
        proj4_string=f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=137.41 +x_0=0 +y_0=0 +R={MARS_EQUATORIAL_RADIUS_M} +units=m +no_defs",
        vertical_reference=VerticalDatumKind.AREOID_RELATIVE_ELEVATION,
        vertical_datum_name="Tied to MOLA Areoid Reference Surface (DTEEC PDS3 Header)",
        validity_conditions=[
            "Horizontal map grid uses R=3,396,190.0 m Equirectangular centered at 137.41 E; heights are tied to MOLA Areoid in meters.",
        ],
        supported_transformations=["IAU2000:49900", "MARS:IAU2015_49900", "MARS:GALE_EQUIRECTANGULAR"],
        known_limitations=[
            "Product-specific central meridian (137.41 E); oblique stereo swaths contain corner no-data regions inside bounding rectangle.",
        ],
    ),
}

MARS_CRS_DEFINITIONS: Dict[str, str] = {
    k: v.proj4_string for k, v in MARS_CRS_REGISTRY.items()
}


class CRSError(ValueError):
    """Raised when an invalid, Earth-bound, or unverified planetary coordinate system is supplied."""


def _resolve_registry_entry(crs_string: Optional[str]) -> Optional[MarsCrsDefinition]:
    if not crs_string:
        return None
    cleaned = crs_string.strip()
    if cleaned in MARS_CRS_REGISTRY:
        return MARS_CRS_REGISTRY[cleaned]
    upper = cleaned.upper()
    for entry in MARS_CRS_REGISTRY.values():
        if entry.identifier.upper() == upper:
            return entry
        if any(a.upper() == upper for a in entry.aliases):
            return entry
    return None


def _radii_match_documented_mars(a_m: float, b_m: float, tol_m: float = 5.0) -> Optional[Tuple[CrsCategory, str, str]]:
    """
    Strictly check whether parsed (semi_major_axis, semi_minor_axis) match an authoritative
    Martian ellipsoid or sphere within <= 5.0 m tolerance (NO arbitrary 150 km range band).
    """
    for doc_a, doc_b, cat, label in _DOCUMENTED_MARS_RADII:
        if abs(a_m - doc_a) <= tol_m and abs(b_m - doc_b) <= tol_m:
            shape = "sphere" if abs(doc_a - doc_b) <= tol_m else "ellipsoid"
            return cat, shape, label
    return None


def get_mars_crs(crs_identifier: Optional[str] = None) -> CRS:
    """Resolve an authoritative Martian pyproj.CRS object or raise CRSError."""
    res = validate_mars_crs_detailed(crs_identifier, require_conventions=False)
    if not res.valid:
        raise CRSError("; ".join(res.blockers) or f"Unsupported Mars CRS: {crs_identifier!r}")

    reg = _resolve_registry_entry(crs_identifier)
    if reg is not None:
        return CRS.from_proj4(reg.proj4_string)
    return CRS.from_user_input(str(crs_identifier).strip())


def _infer_vertical_datum_kind(val: Any) -> Optional[VerticalDatumKind]:
    if val is None:
        return None
    if isinstance(val, VerticalDatumKind):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return VerticalDatumKind(s)
    except Exception:
        pass
    low = s.lower()
    if "areoid" in low or "geoid" in low:
        return VerticalDatumKind.AREOID_RELATIVE_ELEVATION
    if "ellipsoid" in low:
        return VerticalDatumKind.ELLIPSOID_RELATIVE_ELEVATION
    if "sphere" in low or "3396000" in low:
        return VerticalDatumKind.REFERENCE_SPHERE_ELEVATION
    if "unknown" in low or "unverified" in low:
        return VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
    return None


def validate_mars_crs_detailed(
    crs_string: Optional[str],
    *,
    latitude_convention: Optional[str] = None,
    longitude_direction: Optional[str] = None,
    vertical_reference: Optional[Any] = None,
    require_conventions: bool = False,
    require_vertical_datum: bool = False,
) -> CrsValidationResult:
    """
    Strictly validate a coordinate reference system against authoritative IAU/IAG/PDS
    Mars definitions and explicit conventions, returning one of 8 CoordinateValidationStates.
    """
    if not crs_string or not str(crs_string).strip() or str(crs_string).strip().lower() in {"unknown", "none", "null"}:
        return CrsValidationResult(
            input_crs=crs_string,
            valid=False,
            validation_state=CoordinateValidationState.CRS_UNVERIFIED,
            crs_category=CrsCategory.UNKNOWN_PLANETARY_REFERENCE,
            blockers=["Missing or unreferenced CRS metadata."],
        )

    raw = str(crs_string).strip()
    upper = raw.upper()

    for tok in _FORBIDDEN_BODY_TOKENS:
        if tok in upper:
            return CrsValidationResult(
                input_crs=raw,
                valid=False,
                validation_state=CoordinateValidationState.CRS_INCOMPATIBLE,
                crs_category=CrsCategory.UNKNOWN_PLANETARY_REFERENCE,
                planetary_body="Earth_or_NonMars",
                blockers=[f"Rejected non-Martian CRS token '{tok}' in '{raw}'."],
            )

    reg = _resolve_registry_entry(raw)
    warnings: List[str] = []
    blockers: List[str] = []
    limitations: List[str] = []

    if reg is not None:
        a_axis = reg.semi_major_axis_m
        b_axis = reg.semi_minor_axis_m
        shape_type = reg.shape_type
        crs_cat = reg.crs_category
        canon_id = reg.identifier
        lat_conv = latitude_convention or reg.latitude_convention
        lon_conv = longitude_direction or reg.longitude_convention
        v_ref = _infer_vertical_datum_kind(vertical_reference) or reg.vertical_reference
        is_proj = reg.projection.lower().startswith("equirectangular") or reg.longitude_domain == "projected_meters"
        limitations.extend(reg.known_limitations)
    else:
        try:
            c = CRS.from_user_input(raw)
        except Exception as exc:
            return CrsValidationResult(
                input_crs=raw,
                valid=False,
                validation_state=CoordinateValidationState.CRS_UNSUPPORTED,
                crs_category=CrsCategory.UNKNOWN_PLANETARY_REFERENCE,
                blockers=[f"Unparseable CRS expression '{raw}': {exc}"],
            )

        if not c.ellipsoid or not c.ellipsoid.semi_major_metre:
            return CrsValidationResult(
                input_crs=raw,
                valid=False,
                validation_state=CoordinateValidationState.CRS_UNVERIFIED,
                crs_category=CrsCategory.UNKNOWN_PLANETARY_REFERENCE,
                blockers=[f"CRS '{raw}' lacks defined planetary reference radii."],
            )

        a_axis = float(c.ellipsoid.semi_major_metre)
        b_axis = float(c.ellipsoid.semi_minor_metre or a_axis)
        matched = _radii_match_documented_mars(a_axis, b_axis)
        if matched is None:
            return CrsValidationResult(
                input_crs=raw,
                valid=False,
                validation_state=CoordinateValidationState.CRS_UNSUPPORTED,
                crs_category=CrsCategory.UNKNOWN_PLANETARY_REFERENCE,
                semi_major_axis_m=a_axis,
                semi_minor_axis_m=b_axis,
                blockers=[
                    f"CRS radii (a={a_axis:.1f} m, b={b_axis:.1f} m) do not match any authoritative Mars "
                    "IAU/IAG/MOLA reference sphere or ellipsoid within 5 m tolerance."
                ],
            )
        crs_cat, shape_type, doc_label = matched
        is_proj = bool(c.is_projected)
        if is_proj and crs_cat not in {CrsCategory.LOCAL_STUDY_AREA_PROJECTION}:
            crs_cat = CrsCategory.PROJECTED_PLANETARY_CRS
        canon_id = f"CUSTOM_MARS_{int(round(a_axis))}_{shape_type.upper()}"
        lat_conv = latitude_convention or "unknown"
        lon_conv = longitude_direction or "unknown"
        v_ref = _infer_vertical_datum_kind(vertical_reference) or VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
        warnings.append(f"Validated geometric radii against '{doc_label}' (a={a_axis:.1f} m, b={b_axis:.1f} m).")
        if "UNKNOWN" in upper and "MARS" not in upper:
            limitations.append("WKT/PROJ string omits explicit 'Mars' datum name; verified strictly by exact Martian radii.")

    if latitude_convention and latitude_convention not in {"Planetocentric", "Planetographic", "unknown"}:
        return CrsValidationResult(
            input_crs=raw,
            canonical_identifier=canon_id,
            valid=False,
            validation_state=CoordinateValidationState.COORDINATE_CONVENTION_UNVERIFIED,
            crs_category=crs_cat,
            planetary_body="Mars",
            shape_type=shape_type,
            semi_major_axis_m=a_axis,
            semi_minor_axis_m=b_axis,
            latitude_convention=latitude_convention,
            longitude_convention=lon_conv,
            vertical_reference=v_ref,
            is_projected=is_proj,
            blockers=[f"Unsupported latitude convention '{latitude_convention}'."],
        )

    if longitude_direction and longitude_direction not in {"East", "West", "unknown"}:
        return CrsValidationResult(
            input_crs=raw,
            canonical_identifier=canon_id,
            valid=False,
            validation_state=CoordinateValidationState.COORDINATE_CONVENTION_UNVERIFIED,
            crs_category=crs_cat,
            planetary_body="Mars",
            shape_type=shape_type,
            semi_major_axis_m=a_axis,
            semi_minor_axis_m=b_axis,
            latitude_convention=lat_conv,
            longitude_convention=longitude_direction,
            vertical_reference=v_ref,
            is_projected=is_proj,
            blockers=[f"Unsupported longitude convention '{longitude_direction}'."],
        )

    conv_missing = lat_conv == "unknown" or lon_conv == "unknown"
    v_missing = v_ref == VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE

    if require_conventions and conv_missing:
        return CrsValidationResult(
            input_crs=raw,
            canonical_identifier=canon_id,
            valid=False,
            validation_state=CoordinateValidationState.COORDINATE_CONVENTION_UNVERIFIED,
            crs_category=crs_cat,
            planetary_body="Mars",
            shape_type=shape_type,
            semi_major_axis_m=a_axis,
            semi_minor_axis_m=b_axis,
            latitude_convention=lat_conv,
            longitude_convention=lon_conv,
            vertical_reference=v_ref,
            is_projected=is_proj,
            blockers=["Missing explicit Planetocentric/Planetographic or East/West longitude convention."],
            warnings=warnings,
            limitations=limitations,
        )

    if require_vertical_datum and v_missing:
        return CrsValidationResult(
            input_crs=raw,
            canonical_identifier=canon_id,
            valid=False,
            validation_state=CoordinateValidationState.VERTICAL_DATUM_UNVERIFIED,
            crs_category=crs_cat,
            planetary_body="Mars",
            shape_type=shape_type,
            semi_major_axis_m=a_axis,
            semi_minor_axis_m=b_axis,
            latitude_convention=lat_conv,
            longitude_convention=lon_conv,
            vertical_reference=v_ref,
            is_projected=is_proj,
            blockers=["Vertical datum is UNKNOWN_VERTICAL_REFERENCE; absolute elevation comparison prohibited."],
            warnings=warnings,
            limitations=limitations,
        )

    if conv_missing or v_missing or limitations or crs_cat == CrsCategory.PRODUCT_SPECIFIC_DATUM:
        state = CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS
    else:
        state = CoordinateValidationState.CRS_VALIDATED

    return CrsValidationResult(
        input_crs=raw,
        canonical_identifier=canon_id,
        valid=True,
        validation_state=state,
        crs_category=crs_cat,
        planetary_body="Mars",
        shape_type=shape_type,
        semi_major_axis_m=a_axis,
        semi_minor_axis_m=b_axis,
        latitude_convention=lat_conv,
        longitude_convention=lon_conv,
        vertical_reference=v_ref,
        is_projected=is_proj,
        blockers=blockers,
        warnings=warnings,
        limitations=limitations,
        verified_event_method="authoritative_registry_and_pyproj_radii_validation",
        verified_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def validate_mars_crs(crs_string: Optional[str]) -> bool:
    """Strict Martian CRS validation (rejects Earth CRSs and unverified non-Mars radii)."""
    return validate_mars_crs_detailed(crs_string, require_conventions=False).valid


def describe_mars_crs(crs_string: Optional[str]) -> Dict[str, Any]:
    """Return structured CRS validation & parameter summary for inspection endpoints."""
    res = validate_mars_crs_detailed(crs_string)
    reg = _resolve_registry_entry(crs_string)
    out = res.model_dump()
    out["registry_entry"] = reg.model_dump() if reg else None
    return out


def check_vertical_datum_compatibility(
    datum_a: Any,
    datum_b: Any,
    *,
    validated_vertical_offset_m: Optional[float] = None,
) -> VerticalDatumComparisonResult:
    """
    Validate vertical reference compatibility before comparing elevations (Part 3.4).
    Horizontal CRS compatibility NEVER guarantees vertical datum compatibility.
    """
    datum_a = _infer_vertical_datum_kind(datum_a) or VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
    datum_b = _infer_vertical_datum_kind(datum_b) or VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
    abs_a = datum_a != VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE
    abs_b = datum_b != VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE

    if datum_a == VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE or datum_b == VerticalDatumKind.UNKNOWN_VERTICAL_REFERENCE:
        return VerticalDatumComparisonResult(
            compatible=False,
            validation_state=CoordinateValidationState.VERTICAL_DATUM_UNVERIFIED,
            datum_a=datum_a,
            datum_b=datum_b,
            is_absolute_elevation_a=abs_a,
            is_absolute_elevation_b=abs_b,
            requires_validated_transformation=True,
            explanation="Cannot compare elevations when one or both products have UNKNOWN_VERTICAL_REFERENCE.",
            warnings=["Unverified vertical datum elevation must NOT be reported as absolute elevation."],
        )

    if datum_a == datum_b:
        return VerticalDatumComparisonResult(
            compatible=True,
            validation_state=CoordinateValidationState.CRS_VALIDATED,
            datum_a=datum_a,
            datum_b=datum_b,
            is_absolute_elevation_a=True,
            is_absolute_elevation_b=True,
            requires_validated_transformation=False,
            explanation=f"Vertical datums match ({datum_a.value}).",
        )

    if validated_vertical_offset_m is not None and math.isfinite(validated_vertical_offset_m):
        return VerticalDatumComparisonResult(
            compatible=True,
            validation_state=CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS,
            datum_a=datum_a,
            datum_b=datum_b,
            is_absolute_elevation_a=True,
            is_absolute_elevation_b=True,
            requires_validated_transformation=False,
            explanation=(
                f"Differing vertical datums ({datum_a.value} vs {datum_b.value}) reconciled using "
                f"explicitly supplied vertical datum offset {validated_vertical_offset_m:.3f} m."
            ),
            warnings=["Vertical offset applied as a scalar shift; local geoid/areoid undulation may vary across large baselines."],
        )

    return VerticalDatumComparisonResult(
        compatible=False,
        validation_state=CoordinateValidationState.CRS_INCOMPATIBLE,
        datum_a=datum_a,
        datum_b=datum_b,
        is_absolute_elevation_a=True,
        is_absolute_elevation_b=True,
        requires_validated_transformation=True,
        explanation=(
            f"Vertical datum mismatch ({datum_a.value} vs {datum_b.value}): horizontal CRS compatibility "
            "does NOT validate elevation subtraction without an areoid-to-ellipsoid transformation."
        ),
        warnings=["Direct elevation subtraction refused until a validated vertical datum transformation is provided."],
    )


def convert_latitude_convention(
    latitude_deg: float,
    from_convention: str,
    to_convention: str,
    semi_major_m: float,
    semi_minor_m: float,
) -> float:
    """
    Explicitly convert between Planetocentric and Planetographic latitude ONLY when both
    conventions and reference ellipsoid radii are known.
    Formula: tan(phi_c) = (b / a)^2 * tan(phi_g).
    """
    if from_convention not in {"Planetocentric", "Planetographic"} or to_convention not in {"Planetocentric", "Planetographic"}:
        raise CRSError(f"Explicit latitude convention required for conversion ({from_convention!r} -> {to_convention!r}).")
    if not (-90.0 <= latitude_deg <= 90.0):
        raise CRSError(f"Latitude {latitude_deg} outside [-90, 90].")
    if semi_major_m <= 0 or semi_minor_m <= 0:
        raise CRSError("Invalid semi-major/semi-minor radii.")
    if from_convention == to_convention or abs(semi_major_m - semi_minor_m) < 1e-6 or abs(abs(latitude_deg) - 90.0) < 1e-9 or abs(latitude_deg) < 1e-12:
        return float(latitude_deg)

    ratio_sq = (semi_minor_m / semi_major_m) ** 2
    tan_val = math.tan(math.radians(latitude_deg))
    if from_convention == "Planetographic" and to_convention == "Planetocentric":
        return math.degrees(math.atan(ratio_sq * tan_val))
    return math.degrees(math.atan(tan_val / ratio_sq))


def validate_crs_transformation(source_crs: str, target_crs: str) -> Transformer:
    """
    Explicitly verify that BOTH source and target CRSs are valid Mars coordinate
    systems and construct a strict always_xy pyproj Transformer.
    """
    if not validate_mars_crs(source_crs):
        raise CRSError(f"Source CRS '{source_crs}' is not a valid Mars CRS.")
    if not validate_mars_crs(target_crs):
        raise CRSError(f"Target CRS '{target_crs}' is not a valid Mars CRS.")
    src = get_mars_crs(source_crs)
    dst = get_mars_crs(target_crs)
    return Transformer.from_crs(src, dst, always_xy=True)


def transform_mars_coordinates(
    *,
    x_or_lon: float,
    y_or_lat: float,
    source_crs: str,
    target_crs: str,
    source_lat_convention: str = "Planetocentric",
    target_lat_convention: str = "Planetocentric",
    source_lon_direction: str = "East",
    target_lon_domain: str = "[0, 360)",
    source_vertical_datum: Optional[VerticalDatumKind] = None,
    target_vertical_datum: Optional[VerticalDatumKind] = None,
) -> CoordinateTransformationResult:
    """
    Execute a fully traceable planetary coordinate transformation with explicit convention,
    ellipsoid, vertical datum, and error propagation metadata (Part 3.3).
    """
    src_val = validate_mars_crs_detailed(
        source_crs,
        latitude_convention=source_lat_convention,
        longitude_direction=source_lon_direction,
        vertical_reference=source_vertical_datum,
        require_conventions=True,
    )
    dst_val = validate_mars_crs_detailed(
        target_crs,
        latitude_convention=target_lat_convention,
        longitude_direction="East",
        vertical_reference=target_vertical_datum,
        require_conventions=True,
    )

    v_src = src_val.vertical_reference
    v_dst = dst_val.vertical_reference
    v_compat = check_vertical_datum_compatibility(v_src, v_dst)

    if not src_val.valid or not dst_val.valid:
        state = src_val.validation_state if not src_val.valid else dst_val.validation_state
        msg = "; ".join(src_val.blockers + dst_val.blockers)
        return CoordinateTransformationResult(
            success=False,
            validation_state=state,
            source_crs=source_crs,
            target_crs=target_crs,
            algorithm="explicit_mars_crs_and_convention_pipeline_v2",
            library_version=pyproj.__version__,
            input_coordinates={"x_or_lon": x_or_lon, "y_or_lat": y_or_lat},
            longitude_normalization=target_lon_domain,
            latitude_convention_in=source_lat_convention,
            latitude_convention_out=target_lat_convention,
            ellipsoid_assumptions="Transformation aborted during CRS/convention pre-validation.",
            vertical_reference_in=v_src,
            vertical_reference_out=v_dst,
            vertical_compatible=v_compat.compatible,
            failure_reason=msg,
            provenance_steps=[f"Rejected before transform: {msg}"],
        )

    if not (math.isfinite(x_or_lon) and math.isfinite(y_or_lat)):
        return CoordinateTransformationResult(
            success=False,
            validation_state=CoordinateValidationState.TRANSFORMATION_FAILED,
            source_crs=source_crs,
            target_crs=target_crs,
            algorithm="explicit_mars_crs_and_convention_pipeline_v2",
            library_version=pyproj.__version__,
            input_coordinates={"x_or_lon": x_or_lon, "y_or_lat": y_or_lat},
            longitude_normalization=target_lon_domain,
            latitude_convention_in=source_lat_convention,
            latitude_convention_out=target_lat_convention,
            ellipsoid_assumptions="Non-finite numeric input coordinates.",
            vertical_reference_in=v_src,
            vertical_reference_out=v_dst,
            vertical_compatible=v_compat.compatible,
            failure_reason="Input coordinates must be finite numeric values.",
            provenance_steps=["Rejected non-finite coordinate inputs."],
        )

    provenance: List[str] = [
        f"Source validated as {src_val.canonical_identifier} ({src_val.validation_state.value})",
        f"Target validated as {dst_val.canonical_identifier} ({dst_val.validation_state.value})",
    ]
    in_x = float(x_or_lon)
    in_y = float(y_or_lat)

    try:
        # Step 1: Normalize geographic input if source is unprojected lon/lat
        if not src_val.is_projected:
            if in_y < -90.0 or in_y > 90.0:
                raise CRSError(f"Input latitude {in_y} outside [-90, 90].")
            if source_lon_direction == "West":
                in_x = (360.0 - in_x) % 360.0
                provenance.append("Converted West-positive input longitude to East-positive [0, 360).")
            if source_lat_convention == "Planetographic":
                in_y = convert_latitude_convention(
                    in_y,
                    "Planetographic",
                    "Planetocentric",
                    float(src_val.semi_major_axis_m or MARS_EQUATORIAL_RADIUS_M),
                    float(src_val.semi_minor_axis_m or MARS_POLAR_RADIUS_M),
                )
                provenance.append("Converted Planetographic latitude to Planetocentric on source radii.")

        transformer = validate_crs_transformation(source_crs, target_crs)
        out_x, out_y = transformer.transform(in_x, in_y)
        if not (math.isfinite(out_x) and math.isfinite(out_y)):
            raise CRSError("pyproj produced non-finite output coordinates.")

        # Step 2: Convert output conventions if target is geographic
        if not dst_val.is_projected:
            if target_lat_convention == "Planetographic":
                out_y = convert_latitude_convention(
                    out_y,
                    "Planetocentric",
                    "Planetographic",
                    float(dst_val.semi_major_axis_m or MARS_EQUATORIAL_RADIUS_M),
                    float(dst_val.semi_minor_axis_m or MARS_POLAR_RADIUS_M),
                )
                provenance.append("Converted Planetocentric latitude to Planetographic on destination ellipsoid.")
            if target_lon_domain == "[-180, 180]":
                out_x = normalize_longitude_180(out_x)
                norm_label = "normalized_[-180,180]"
            else:
                out_x = normalize_longitude_360(out_x)
                norm_label = "normalized_[0,360)"
            out_dict = {"lon_deg": round(out_x, 8), "lat_deg": round(out_y, 8)}
            axis_order = "lon_east_deg, lat_deg"
        else:
            norm_label = "projected_meters"
            out_dict = {"easting_m": round(out_x, 4), "northing_m": round(out_y, 4)}
            axis_order = "easting_m, northing_m"

        lim_notes: List[str] = []
        if (src_val.semi_major_axis_m or 0) != (dst_val.semi_major_axis_m or 0):
            lim_notes.append(
                f"Source semi-major axis ({src_val.semi_major_axis_m} m) differs from destination ({dst_val.semi_major_axis_m} m); "
                "no 3D datum shift applied unless explicit Helmert parameters specified."
            )
        if not v_compat.compatible:
            lim_notes.append(v_compat.explanation)

        final_state = CoordinateValidationState.CRS_VALIDATED
        if lim_notes or src_val.validation_state == CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS or dst_val.validation_state == CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS:
            final_state = CoordinateValidationState.CRS_VALID_WITH_LIMITATIONS

        provenance.append(f"Executed pyproj Transformer(always_xy=True) -> {out_dict}")
        return CoordinateTransformationResult(
            success=True,
            validation_state=final_state,
            source_crs=src_val.canonical_identifier or source_crs,
            target_crs=dst_val.canonical_identifier or target_crs,
            algorithm="pyproj_always_xy + explicit_centric_graphic_formula",
            library_version=pyproj.__version__,
            input_coordinates={"x_or_lon": x_or_lon, "y_or_lat": y_or_lat},
            output_coordinates=out_dict,
            axis_order=axis_order,
            longitude_normalization=norm_label,
            latitude_convention_in=source_lat_convention,
            latitude_convention_out=target_lat_convention if not dst_val.is_projected else "projected_planar",
            ellipsoid_assumptions=(
                f"src(a={src_val.semi_major_axis_m}, b={src_val.semi_minor_axis_m}) -> "
                f"dst(a={dst_val.semi_major_axis_m}, b={dst_val.semi_minor_axis_m})"
            ),
            vertical_reference_in=v_src,
            vertical_reference_out=v_dst,
            vertical_compatible=v_compat.compatible,
            known_error_or_limitation="; ".join(lim_notes) if lim_notes else None,
            provenance_steps=provenance,
        )
    except Exception as exc:
        return CoordinateTransformationResult(
            success=False,
            validation_state=CoordinateValidationState.TRANSFORMATION_FAILED,
            source_crs=source_crs,
            target_crs=target_crs,
            algorithm="pyproj_always_xy + explicit_centric_graphic_formula",
            library_version=pyproj.__version__,
            input_coordinates={"x_or_lon": x_or_lon, "y_or_lat": y_or_lat},
            longitude_normalization=target_lon_domain,
            latitude_convention_in=source_lat_convention,
            latitude_convention_out=target_lat_convention,
            ellipsoid_assumptions="Transformation failed at runtime.",
            vertical_reference_in=v_src,
            vertical_reference_out=v_dst,
            vertical_compatible=v_compat.compatible,
            failure_reason=str(exc),
            provenance_steps=provenance + [f"Failure: {exc}"],
        )


def validate_mars_coordinates(
    latitude: float,
    longitude: float,
    latitude_convention: str = "Planetocentric",
    longitude_direction: str = "East",
) -> Tuple[float, float]:
    """
    Validate planetary coordinate bounds and conventions.
    Rejects non-finite coordinates, West-positive unless normalized, or out-of-range values.
    """
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise CRSError("Coordinates must be finite numeric values.")
    if latitude < -90.0 or latitude > 90.0:
        raise CRSError(f"Latitude {latitude} outside valid [-90, 90] range.")
    if longitude < -180.0 or longitude > 360.0:
        raise CRSError(f"Longitude {longitude} outside valid [-180, 360] range.")
    if latitude_convention not in {"Planetocentric", "Planetographic"}:
        raise CRSError(f"Unsupported latitude convention: '{latitude_convention}'.")
    if longitude_direction not in {"East", "West"}:
        raise CRSError(f"Unsupported longitude direction: '{longitude_direction}'.")

    lon_east = (360.0 - longitude) % 360.0 if longitude_direction == "West" else longitude
    return float(latitude), float(lon_east)


def normalize_longitude_180(lon_deg: float) -> float:
    """Normalize East-positive longitude into [-180, 180)."""
    norm = ((lon_deg + 180.0) % 360.0) - 180.0
    return 180.0 if math.isclose(norm, -180.0) and lon_deg > 0 else norm


def normalize_longitude_360(lon_deg: float) -> float:
    """Normalize East-positive longitude into [0, 360)."""
    return lon_deg % 360.0


def angular_displacement_to_metric(
    center_latitude_deg: float,
    delta_lon_deg: float,
    delta_lat_deg: float,
    radius_m: float = MARS_EQUATORIAL_RADIUS_M,
) -> Tuple[float, float]:
    """
    Convert angular displacements (delta_lon, delta_lat) in degrees to metric displacements (dx, dy) in meters
    on the Martian surface at a specified reference latitude.
    """
    if not (-90.0 <= center_latitude_deg <= 90.0):
        raise CRSError(f"Invalid reference latitude {center_latitude_deg}")
    if radius_m <= 0:
        raise CRSError("Planetary radius must be positive.")

    lat_rad = math.radians(center_latitude_deg)
    d_lon_rad = math.radians(delta_lon_deg)
    d_lat_rad = math.radians(delta_lat_deg)

    dx_m = radius_m * math.cos(lat_rad) * d_lon_rad
    dy_m = radius_m * d_lat_rad

    return abs(dx_m), abs(dy_m)


def evaluate_spatial_registration(
    *,
    product_a_id: str,
    product_b_id: str,
    crs_a: Optional[str],
    crs_b: Optional[str],
    bounds_a: Optional[Dict[str, float]],
    bounds_b: Optional[Dict[str, float]],
    resolution_a_m: Optional[float],
    resolution_b_m: Optional[float],
    lat_conv_a: str = "unknown",
    lat_conv_b: str = "unknown",
    lon_dir_a: str = "unknown",
    lon_dir_b: str = "unknown",
    projection_a: str = "unknown",
    projection_b: str = "unknown",
    radii_a_m: Optional[Dict[str, float]] = None,
    radii_b_m: Optional[Dict[str, float]] = None,
    registration_method: str = "coordinate_transform_and_footprint_intersection",
    resampling_method: Optional[str] = None,
    declared_registration_error_m: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Backwards-compatible spatial registration evaluator now powered by strict Mars CRS
    validation (Part 3) and non-arbitrary coordinate/radii checks.
    For complete 12-step polygon footprint & tie-point registration assessment, use
    app.geospatial.registration.evaluate_multimission_registration().
    """
    warnings: List[str] = []
    blockers: List[str] = []
    provenance_steps: List[str] = []

    if not crs_a or not crs_b or bounds_a is None or bounds_b is None:
        return {
            "product_a_id": product_a_id,
            "product_b_id": product_b_id,
            "registration_state": "INSUFFICIENT_METADATA",
            "crs_compatible": False,
            "projection_compatible": False,
            "overlap_ratio": None,
            "resolution_ratio": None,
            "registration_method": registration_method,
            "registration_error_m": None,
            "registration_error_status": "UNQUANTIFIED_INSUFFICIENT_METADATA",
            "resampling_method": resampling_method,
            "warnings": warnings,
            "blockers": ["Missing CRS or spatial footprint metadata for spatial registration check."],
            "transformation_provenance": ["Registration halted: missing CRS or coverage bounds."],
        }

    val_a = validate_mars_crs_detailed(crs_a, latitude_convention=lat_conv_a, longitude_direction=lon_dir_a)
    val_b = validate_mars_crs_detailed(crs_b, latitude_convention=lat_conv_b, longitude_direction=lon_dir_b)
    if not val_a.valid or not val_b.valid:
        blockers.extend(val_a.blockers + val_b.blockers)
        return {
            "product_a_id": product_a_id,
            "product_b_id": product_b_id,
            "registration_state": "INCOMPATIBLE_REFERENCE_SYSTEM",
            "crs_compatible": False,
            "projection_compatible": False,
            "overlap_ratio": None,
            "resolution_ratio": None,
            "registration_method": registration_method,
            "registration_error_m": None,
            "registration_error_status": "REJECTED_INVALID_CRS",
            "resampling_method": resampling_method,
            "warnings": warnings + val_a.warnings + val_b.warnings,
            "blockers": blockers,
            "transformation_provenance": ["Rejected invalid/non-Martian CRS prior to coordinate transformation."],
        }

    if lat_conv_a != "unknown" and lat_conv_b != "unknown" and lat_conv_a != lat_conv_b:
        blockers.append(
            f"Latitude convention mismatch without conversion ({lat_conv_a} vs {lat_conv_b}): "
            "Planetographic vs Planetocentric shift reaches ~0.35 deg at mid-latitudes."
        )
    elif "unknown" in {lat_conv_a, lat_conv_b}:
        warnings.append(f"Unverified latitude convention ({lat_conv_a} vs {lat_conv_b}).")

    if lon_dir_a != "unknown" and lon_dir_b != "unknown" and lon_dir_a != lon_dir_b:
        warnings.append(
            f"Longitude direction differs ({lon_dir_a} vs {lon_dir_b}); requires explicit East-positive normalization."
        )

    if radii_a_m and radii_b_m:
        a1 = float(radii_a_m.get("a", 0.0))
        a2 = float(radii_b_m.get("a", 0.0))
        c1 = float(radii_a_m.get("c", a1))
        c2 = float(radii_b_m.get("c", a2))
        if a1 > 0 and a2 > 0 and abs(a1 - a2) > 50000.0:
            blockers.append(f"Major planetary radius incompatible ({a1} m vs {a2} m).")
        elif (a1 > 0 and c1 > 0) and (a2 > 0 and c2 > 0) and abs((a1 - c1) - (a2 - c2)) > 5000.0:
            warnings.append(
                f"Spherical MOLA vs oblate IAU2000 ellipsoid polar flattening difference ({abs((a1-c1)-(a2-c2)):.0f} m)."
            )

    proj_compatible = True
    if projection_a != "unknown" and projection_b != "unknown" and projection_a.lower() != projection_b.lower():
        proj_compatible = False
        warnings.append(f"Map projections differ ({projection_a} vs {projection_b}); explicit reprojection required.")

    try:
        validate_crs_transformation(crs_a, crs_b)
        provenance_steps.append(f"Verified pyproj CRS transform path: {crs_a} <-> {crs_b}")
    except CRSError as exc:
        blockers.append(str(exc))

    try:
        min_lat_a = float(bounds_a["min_latitude"])
        max_lat_a = float(bounds_a["max_latitude"])
        min_lon_a = normalize_longitude_360(float(bounds_a["min_longitude"]))
        max_lon_a = normalize_longitude_360(float(bounds_a["max_longitude"]))
        min_lat_b = float(bounds_b["min_latitude"])
        max_lat_b = float(bounds_b["max_latitude"])
        min_lon_b = normalize_longitude_360(float(bounds_b["min_longitude"]))
        max_lon_b = normalize_longitude_360(float(bounds_b["max_longitude"]))
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "product_a_id": product_a_id,
            "product_b_id": product_b_id,
            "registration_state": "INSUFFICIENT_METADATA",
            "crs_compatible": True,
            "projection_compatible": proj_compatible,
            "overlap_ratio": None,
            "resolution_ratio": None,
            "registration_method": registration_method,
            "registration_error_m": None,
            "registration_error_status": "UNQUANTIFIED_MALFORMED_BOUNDS",
            "resampling_method": resampling_method,
            "warnings": warnings,
            "blockers": [f"Malformed bounds structure: {exc}"],
            "transformation_provenance": provenance_steps,
        }

    if max_lon_b == 0.0 and float(bounds_b.get("max_longitude", 0.0)) >= 360.0:
        max_lon_b = 360.0
    if max_lon_a == 0.0 and float(bounds_a.get("max_longitude", 0.0)) >= 360.0:
        max_lon_a = 360.0

    i_min_lat = max(min_lat_a, min_lat_b)
    i_max_lat = min(max_lat_a, max_lat_b)
    i_min_lon = max(min_lon_a, min_lon_b)
    i_max_lon = min(max_lon_a, max_lon_b)
    area_a = max(1e-12, (max_lat_a - min_lat_a) * max(1e-9, max_lon_a - min_lon_a))
    if i_min_lat < i_max_lat and i_min_lon < i_max_lon:
        inter_area = (i_max_lat - i_min_lat) * (i_max_lon - i_min_lon)
        overlap_ratio = min(1.0, inter_area / area_a)
    else:
        overlap_ratio = 0.0

    res_ratio: Optional[float] = None
    if resolution_a_m and resolution_b_m and min(resolution_a_m, resolution_b_m) > 0:
        res_ratio = max(resolution_a_m, resolution_b_m) / min(resolution_a_m, resolution_b_m)
        if res_ratio > 10.0:
            warnings.append(
                f"Large resolution disparity ({resolution_a_m:.2f} m vs {resolution_b_m:.2f} m; {res_ratio:.1f}x): "
                "coarse grid must NEVER be treated as high-resolution evidence."
            )

    if blockers:
        state = "INCOMPATIBLE_REFERENCE_SYSTEM"
    elif overlap_ratio == 0.0:
        state = "NOT_REGISTERED"
        blockers.append("Spatial footprints do not intersect.")
    elif "unknown" in {lat_conv_a, lat_conv_b, lon_dir_a, lon_dir_b} or declared_registration_error_m is None:
        state = "PARTIALLY_OVERLAPPING" if overlap_ratio < 0.99 else "REGISTRATION_UNVERIFIED"
        if declared_registration_error_m is None:
            warnings.append("Inter-product tie-point registration residual error is not reported (UNQUANTIFIED).")
    elif overlap_ratio < 0.99:
        state = "PARTIALLY_OVERLAPPING"
    elif warnings:
        state = "REGISTERED_WITH_LIMITATIONS"
    else:
        state = "REGISTERED_VALIDATED"

    provenance_steps.append(
        f"Overlap ratio={overlap_ratio:.4f}; resampling={resampling_method or 'none_applied'}; state={state}"
    )
    return {
        "product_a_id": product_a_id,
        "product_b_id": product_b_id,
        "registration_state": state,
        "crs_compatible": not any("crs" in b.lower() or "radius" in b.lower() or "convention" in b.lower() for b in blockers),
        "projection_compatible": proj_compatible,
        "overlap_ratio": round(overlap_ratio, 4),
        "resolution_ratio": round(res_ratio, 2) if res_ratio is not None else None,
        "registration_method": registration_method,
        "registration_error_m": declared_registration_error_m,
        "registration_error_status": (
            "QUANTIFIED" if declared_registration_error_m is not None else "UNQUANTIFIED_NO_TIEPOINT_RESIDUAL"
        ),
        "resampling_method": resampling_method,
        "warnings": warnings,
        "blockers": blockers,
        "transformation_provenance": provenance_steps,
    }
