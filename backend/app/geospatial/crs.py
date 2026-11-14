"""
MARSCOPE Planetary Coordinate Reference Systems (CRS) Module
Martian Surface Intelligence & Exploration System

Implements authoritative cartographic frames for Mars adhering to IAU/IAG conventions.
Never assumes Earth WGS84 for Martian data and rejects ambiguous/unreferenced CRS.
"""

import math
from typing import Any, Dict, Optional, Tuple
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
