"""
Automated Geospatial, CRS, PDS3 Label, and Raster Integrity Tests
Validates Mars CRS rejection of Earth/unreferenced CRS, angular-to-metric conversions,
no-filename unit inference, and all-nodata statistics behavior.
"""

import math
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from app.geospatial.crs import (
    MARS_CRS_DEFINITIONS,
    MARS_EQUATORIAL_RADIUS_M,
    CRSError,
    angular_displacement_to_metric,
    validate_crs_transformation,
    validate_mars_crs,
)

MARS_CRS_PROJ4 = MARS_CRS_DEFINITIONS["IAU2000:49900"]
from app.geospatial.raster import RasterInspectionService
from app.ingestion.pds_label import extract_pds3_metadata


def test_reject_earth_and_unreferenced_crs():
    """Strictly reject Earth WGS84, None, and empty CRS strings."""
    assert not validate_mars_crs("EPSG:4326")
    assert not validate_mars_crs("WGS84")
    assert not validate_mars_crs("+proj=longlat +datum=WGS84")
    assert not validate_mars_crs(None)
    assert not validate_mars_crs("")


def test_accept_valid_mars_crs():
    """Accept authentic IAU2000 Mars ellipsoids and planetary proj4 definitions."""
    assert validate_mars_crs("IAU2000:49900")
    assert validate_mars_crs("IAU2000:MARS_SPHERE")
    assert validate_mars_crs("+proj=longlat +a=3396190 +b=3376200")


def test_crs_transformation_validation():
    """Reject Earth-target or unreferenced transformations; allow identical valid Mars CRS."""
    transformer = validate_crs_transformation("IAU2000:49900", "IAU2000:49900")
    assert transformer is not None
    with pytest.raises(CRSError):
        validate_crs_transformation(None, "IAU2000:49900")
    with pytest.raises(CRSError):
        validate_crs_transformation("IAU2000:49900", "EPSG:4326")


def test_angular_displacement_to_metric_at_equator_and_latitude():
    """Verify spherical/ellipsoidal angular-to-metric scaling on Mars."""
    dx_m, dy_m = angular_displacement_to_metric(center_latitude_deg=0.0, delta_lon_deg=1.0, delta_lat_deg=1.0)
    expected_m = (2.0 * math.pi * MARS_EQUATORIAL_RADIUS_M) / 360.0
    assert math.isclose(dx_m, expected_m, rel_tol=1e-4)
    assert math.isclose(dy_m, expected_m, rel_tol=1e-4)

    dx_60, _ = angular_displacement_to_metric(center_latitude_deg=60.0, delta_lon_deg=1.0, delta_lat_deg=1.0)
    assert math.isclose(dx_60, dx_m * 0.5, rel_tol=1e-3)


def test_raster_inspection_never_infers_units_from_filename(tmp_path: Path):
    """Even if filename starts with 'dem_', absent metadata leaves units='unknown'."""
    tif_path = tmp_path / "dem_mystery_product.tif"
    data = np.full((6, 6), 120.0, dtype=np.float32)
    transform = from_bounds(137.0, -5.0, 138.0, -4.0, 6, 6)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=6,
        width=6,
        count=1,
        dtype="float32",
        crs=MARS_CRS_PROJ4,
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    report = RasterInspectionService.inspect_raster_file(tif_path)
    assert report["crs_verified"] is True
    assert report["units"] == "unknown"
    assert report["units_verified"] is False
    assert report["unit_source"] is None


def test_raster_inspection_all_nodata_returns_unavailable_none_stats(tmp_path: Path):
    """An all-nodata raster must return available=False and None min/max/mean (never 0.0)."""
    tif_path = tmp_path / "empty_coverage.tif"
    data = np.full((5, 5), -9999.0, dtype=np.float32)
    transform = from_bounds(137.0, -5.0, 138.0, -4.0, 5, 5)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=5,
        width=5,
        count=1,
        dtype="float32",
        crs=MARS_CRS_PROJ4,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(1, UNITS="meters")

    report = RasterInspectionService.inspect_raster_file(tif_path)
    assert report["units"] == "meters"
    assert report["units_verified"] is True
    assert report["stats"]["available"] is False
    assert report["stats"]["valid_pixel_count"] == 0
    assert report["stats"]["min_value"] is None
    assert report["stats"]["max_value"] is None
    assert report["stats"]["mean_value"] is None


def test_pds3_label_parsing_and_sibling_unit_extraction(tmp_path: Path):
    """Extract Mars CRS, positive longitude direction, bounds, and vertical units from sibling .LBL."""
    lbl_path = tmp_path / "test_megdr.lbl"
    lbl_path.write_text(
        """
PDS_VERSION_ID = PDS3
PRODUCT_ID = "MEGT_TEST"
OBJECT = IMAGE
  LINES = 4
  LINE_SAMPLES = 4
  UNIT = METER
  SCALING_FACTOR = 1.0
  OFFSET = 0.0
END_OBJECT = IMAGE
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "SIMPLE CYLINDRICAL"
  COORDINATE_SYSTEM_NAME = "PLANETOCENTRIC"
  POSITIVE_LONGITUDE_DIRECTION = "EAST"
  A_AXIS_RADIUS = 3396.19 <KM>
  MINIMUM_LATITUDE = -10.0 <DEG>
  MAXIMUM_LATITUDE = 0.0 <DEG>
  WESTERNMOST_LONGITUDE = 130.0 <DEG>
  EASTERNMOST_LONGITUDE = 140.0 <DEG>
END_OBJECT = IMAGE_MAP_PROJECTION
END
""",
        encoding="utf-8",
    )

    parsed = extract_pds3_metadata(lbl_path)
    assert parsed["units"] == "meters"
    assert parsed["longitude_direction"] == "East"
    assert parsed["latitude_convention"].lower() == "planetocentric"

    tif_path = tmp_path / "test_megdr.tif"
    data = np.full((4, 4), -4500.0, dtype=np.float32)
    transform = from_bounds(130.0, -10.0, 140.0, 0.0, 4, 4)
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs=MARS_CRS_PROJ4,
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    report = RasterInspectionService.inspect_raster_file(tif_path)
    assert report["units"] == "meters"
    assert report["units_verified"] is True
    assert "pds3_label" in (report["unit_source"] or "")
