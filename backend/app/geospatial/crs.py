"""
MARSCOPE Planetary Coordinate Reference Systems (CRS) Module
Martian Surface Intelligence & Exploration System

Implements authoritative cartographic frames for Mars adhering to IAU/IAG conventions.
Never assumes Earth WGS84 for Martian data.
"""

import math
from typing import Dict, Tuple, Optional
from pyproj import CRS, Transformer

# Canonical Mars Radii (IAU 2000)
MARS_EQUATORIAL_RADIUS_M = 3396190.0
MARS_POLAR_RADIUS_M = 3376200.0
MARS_MEAN_RADIUS_M = 3389500.0

# Authoritative PROJ strings for Mars
MARS_CRS_DEFINITIONS: Dict[str, str] = {
    # IAU 2000 Mars Spheroid / Ellipsoid (Standard PDS3 & PDS4 datum)
    "IAU2000:49900": "+proj=longlat +a=3396190 +b=3376200 +no_defs",
    # IAU 2000 Mars Sphere (often used in simple cylindrical MOLA MEGDR)
    "IAU2000:MARS_SPHERE": "+proj=longlat +a=3396000 +b=3396000 +no_defs",
    # Gale Crater Local Equirectangular / Plate Carree (Metric planar frame)
    "MARS:GALE_EQUIRECTANGULAR": "+proj=eqc +lat_ts=-4.65 +lat_0=0 +lon_0=137.4 +a=3396190 +b=3376200 +units=m +no_defs",
}


def get_mars_crs(crs_identifier: str = "IAU2000:49900") -> CRS:
    """
    Get a pyproj.CRS object for a supported Martian coordinate system.
    """
    if crs_identifier in MARS_CRS_DEFINITIONS:
        return CRS.from_proj4(MARS_CRS_DEFINITIONS[crs_identifier])
    
    # Attempt parsing user-supplied PROJ or WKT string
    try:
        parsed = CRS.from_user_input(crs_identifier)
        return parsed
    except Exception as e:
        raise ValueError(f"Unsupported or invalid Mars CRS identifier: '{crs_identifier}'. Error: {e}")


def validate_mars_crs(crs_string: str) -> bool:
    """
    Validates whether a CRS definition contains Martian ellipsoidal radii or IAU Mars keywords.
    Rejects Earth WGS84 when Mars coordinates are expected.
    """
    if not crs_string:
        return False
    
    lower = crs_string.lower()
    if "wgs84" in lower or "epsg:4326" in lower:
        return False  # Strict rejection of Earth WGS84 for Mars products
    
    if "49900" in lower or "mars" in lower:
        return True
    
    try:
        c = CRS.from_user_input(crs_string)
        # Check if semi-major axis is approximately Mars (~3396 km)
        a_axis = c.ellipsoid.semi_major_metre if c.ellipsoid else None
        if a_axis and 3300000.0 < a_axis < 3500000.0:
            return True
    except Exception:
        pass
    
    return False


def angular_displacement_to_metric(
    center_latitude_deg: float,
    delta_lon_deg: float,
    delta_lat_deg: float,
    radius_m: float = MARS_EQUATORIAL_RADIUS_M,
) -> Tuple[float, float]:
    """
    Convert angular displacements (delta_lon, delta_lat) in degrees to metric displacements (dx, dy) in meters
    on the Martian surface at a specified reference latitude.
    
    Formula:
        dx = R * cos(lat_rad) * delta_lon_rad
        dy = R * delta_lat_rad
    """
    lat_rad = math.radians(center_latitude_deg)
    d_lon_rad = math.radians(delta_lon_deg)
    d_lat_rad = math.radians(delta_lat_deg)
    
    dx_m = radius_m * math.cos(lat_rad) * d_lon_rad
    dy_m = radius_m * d_lat_rad
    
    return abs(dx_m), abs(dy_m)
