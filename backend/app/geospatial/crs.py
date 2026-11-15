"""
MARSCOPE Planetary Coordinate Reference Systems (CRS) Module
Martian Surface Intelligence & Exploration System

Implements authoritative cartographic frames for Mars adhering to IAU/IAG conventions.
Never assumes Earth WGS84 for Martian data and rejects ambiguous/unreferenced CRS.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from pyproj import CRS, Transformer

# Canonical Mars Radii (IAU 2000)
MARS_EQUATORIAL_RADIUS_M = 3396190.0
MARS_POLAR_RADIUS_M = 3376200.0
MARS_MEAN_RADIUS_M = 3389500.0
MARS_SPHERE_RADIUS_M = 3396000.0

# Authoritative PROJ strings for Mars
MARS_CRS_DEFINITIONS: Dict[str, str] = {
    # IAU 2000 Mars Spheroid / Ellipsoid (Standard PDS3 & PDS4 datum)
    "IAU2000:49900": "+proj=longlat +a=3396190 +b=3376200 +no_defs",
    # IAU 2000 Mars Sphere (MOLA MEGDR & NASA Mars Trek EQ datum)
    "IAU2000:MARS_SPHERE": "+proj=longlat +a=3396000 +b=3396000 +no_defs",
    # OGC URN / NASA Mars Trek EPSG alias
    "EPSG:104905": "+proj=longlat +a=3396190 +b=3376200 +no_defs",
    # Gale Crater Local Equirectangular / Plate Carree (Metric planar frame)
    "MARS:GALE_EQUIRECTANGULAR": "+proj=eqc +lat_ts=-4.65 +lat_0=0 +lon_0=137.4 +a=3396190 +b=3376200 +units=m +no_defs",
}


class CRSError(ValueError):
    """Raised on invalid, unreferenced, Earth-bound, or ambiguous coordinate systems."""


def get_mars_crs(crs_identifier: str = "IAU2000:49900") -> CRS:
    """
    Get a pyproj.CRS object for a supported Martian coordinate system.
    Rejects Earth WGS84 and empty/unknown strings.
    """
    if not crs_identifier or not crs_identifier.strip():
        raise CRSError("CRS identifier cannot be empty or unreferenced.")

    if not validate_mars_crs(crs_identifier):
        raise CRSError(f"Rejected non-Martian or invalid CRS: '{crs_identifier}'.")

    if crs_identifier in MARS_CRS_DEFINITIONS:
        return CRS.from_proj4(MARS_CRS_DEFINITIONS[crs_identifier])

    try:
        return CRS.from_user_input(crs_identifier)
    except Exception as e:
        raise CRSError(f"Unsupported or invalid Mars CRS identifier: '{crs_identifier}'. Error: {e}") from e


def validate_mars_crs(crs_string: Optional[str]) -> bool:
    """
    Validates whether a CRS definition contains Martian ellipsoidal radii (~3396 km) or IAU Mars keywords.
    Strictly rejects Earth WGS84 and empty/unprojected strings.
    """
    if not crs_string or not isinstance(crs_string, str):
        return False

    lower = crs_string.strip().lower()
    if not lower or lower in {"unprojected", "unknown", "none", "n/a"}:
        return False

    # Reject Earth datums explicitly
    earth_tokens = ["wgs84", "wgs 84", "epsg:4326", "epsg:3857", "nad83", "etrs89"]
    if any(tok in lower for tok in earth_tokens):
        return False

    if crs_string in MARS_CRS_DEFINITIONS:
        return True

    if "49900" in lower or "104905" in lower or "49901" in lower:
        return True

    try:
        c = CRS.from_user_input(crs_string)
        a_axis = c.ellipsoid.semi_major_metre if c.ellipsoid else None
        if a_axis is not None and 3300000.0 <= a_axis <= 3450000.0:
            return True
        if "mars" in lower and a_axis is None:
            return False
    except Exception:
        if "iau2000" in lower and "mars" in lower:
            return True
        return False

    return False


def describe_mars_crs(
    crs_string: Optional[str],
    latitude_type: str = "Planetocentric",
    longitude_direction: str = "East",
    longitude_range: str = "[-180, 180]",
) -> Dict[str, Any]:
    """
    Extract structured planetary CRS parameters (radii, projection, conventions) without guessing.
    """
    if not validate_mars_crs(crs_string):
        raise CRSError(f"Cannot describe invalid or unreferenced CRS: '{crs_string}'")

    crs_obj = get_mars_crs(crs_string)
    ellipsoid = crs_obj.ellipsoid
    return {
        "original_crs": crs_string,
        "latitude_type": latitude_type,
        "longitude_direction": longitude_direction,
        "longitude_range": longitude_range,
        "semi_major_radius_m": float(ellipsoid.semi_major_metre) if ellipsoid else None,
        "semi_minor_radius_m": float(ellipsoid.semi_minor_metre) if ellipsoid else None,
        "projection": crs_obj.coordinate_operation.name if crs_obj.coordinate_operation else ("Geographic" if crs_obj.is_geographic else "Projected"),
        "is_geographic": bool(crs_obj.is_geographic),
        "is_projected": bool(crs_obj.is_projected),
    }


def validate_crs_transformation(source_crs: Optional[str], target_crs: Optional[str]) -> Transformer:
    """
    Build a pyproj Transformer only after verifying both CRSs are valid Mars frames
    with compatible planetary radii (no ambiguous Earth-Mars datum shifts).
    """
    if not validate_mars_crs(source_crs):
        raise CRSError(f"Source CRS is invalid or unreferenced for Mars transformation: '{source_crs}'")
    if not validate_mars_crs(target_crs):
        raise CRSError(f"Target CRS is invalid or unreferenced for Mars transformation: '{target_crs}'")

    src = get_mars_crs(source_crs)  # type: ignore[arg-type]
    dst = get_mars_crs(target_crs)  # type: ignore[arg-type]

    if src.ellipsoid and dst.ellipsoid:
        diff_a = abs(src.ellipsoid.semi_major_metre - dst.ellipsoid.semi_major_metre)
        if diff_a > 50000.0:
            raise CRSError(
                f"Ambiguous planetary radii mismatch between source ({src.ellipsoid.semi_major_metre} m) "
                f"and target ({dst.ellipsoid.semi_major_metre} m)."
            )

    return Transformer.from_crs(src, dst, always_xy=True)


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

    # Convert West-positive to East-positive internally if explicitly tagged West
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
    Evaluate formal Mars spatial registration compatibility between two products
    (Prompt 18 Section 10). Never treats overlapping bounding boxes alone as proof
    of accurate registration and never treats resampled coarse rasters as high-res evidence.
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

    # 1. CRS & Earth datum rejection
    crs_a_ok = validate_mars_crs(crs_a)
    crs_b_ok = validate_mars_crs(crs_b)
    if not crs_a_ok or not crs_b_ok:
        blockers.append(
            f"Non-Martian or invalid CRS detected (a={crs_a!r} valid={crs_a_ok}, b={crs_b!r} valid={crs_b_ok})."
        )
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
            "warnings": warnings,
            "blockers": blockers,
            "transformation_provenance": ["Rejected Earth/unreferenced CRS prior to coordinate transformation."],
        }

    # 2. Planetary coordinate convention checks
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

    # 3. Ellipsoid / radii comparison
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

    # 4. Projection compatibility & transform verification
    proj_compatible = True
    if projection_a != "unknown" and projection_b != "unknown" and projection_a.lower() != projection_b.lower():
        proj_compatible = False
        warnings.append(f"Map projections differ ({projection_a} vs {projection_b}); explicit reprojection required.")

    try:
        validate_crs_transformation(crs_a, crs_b)
        provenance_steps.append(f"Verified pyproj CRS transform path: {crs_a} <-> {crs_b}")
    except CRSError as exc:
        blockers.append(str(exc))

    # 5. Spatial footprint overlap
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

    # Global wrap handling
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

    # 6. Resolution disparity check
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
