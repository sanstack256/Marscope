"""
Automated Geospatial & CRS Tests
Validates Mars CRS definitions and angular-to-metric conversions.
"""

import math
import pytest
from app.geospatial.crs import (
    validate_mars_crs,
    get_mars_crs,
    angular_displacement_to_metric,
    MARS_EQUATORIAL_RADIUS_M,
)


def test_reject_earth_wgs84():
    """
    Ensure the system strictly rejects Earth WGS84 for Martian planetary products.
    """
    assert not validate_mars_crs("EPSG:4326"), "EPSG:4326 (WGS84) must be rejected."
    assert not validate_mars_crs("WGS84"), "WGS84 must be rejected."
    assert not validate_mars_crs("+proj=longlat +datum=WGS84"), "Earth datum must be rejected."


def test_accept_valid_mars_crs():
    """
    Assert that valid IAU2000 Mars ellipsoids and sphere definitions are accepted.
    """
    assert validate_mars_crs("IAU2000:49900")
    assert validate_mars_crs("IAU2000:MARS_SPHERE")
    assert validate_mars_crs("+proj=longlat +a=3396190 +b=3376200")


def test_angular_displacement_to_metric_at_equator():
    """
    At latitude 0 deg, 1 degree longitude on Mars should equal:
    dx = (2 * pi * R_mars) / 360
    dx = (2 * pi * 3,396,190) / 360 ~= 59,274.69 meters
    """
    dx_m, dy_m = angular_displacement_to_metric(
        center_latitude_deg=0.0,
        delta_lon_deg=1.0,
        delta_lat_deg=1.0,
    )
    expected_m = (2.0 * math.pi * MARS_EQUATORIAL_RADIUS_M) / 360.0
    assert math.isclose(dx_m, expected_m, rel_tol=1e-4)
    assert math.isclose(dy_m, expected_m, rel_tol=1e-4)


def test_angular_displacement_scales_with_latitude():
    """
    At latitude 60 deg, cos(60) = 0.5, so dx should be half of the equatorial width.
    """
    dx_60, _ = angular_displacement_to_metric(center_latitude_deg=60.0, delta_lon_deg=1.0, delta_lat_deg=1.0)
    dx_0, _ = angular_displacement_to_metric(center_latitude_deg=0.0, delta_lon_deg=1.0, delta_lat_deg=1.0)
    assert math.isclose(dx_60, dx_0 * 0.5, rel_tol=1e-3)
