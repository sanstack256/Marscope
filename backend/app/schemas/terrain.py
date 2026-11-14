"""
Terrain Intelligence & Processing Schemas
Martian Surface Intelligence & Exploration System
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class RasterBandStats(BaseModel):
    available: bool = Field(True, description="True if band has >= 1 valid pixel")
    min_value: Optional[float] = Field(None, description="Minimum valid pixel value (None when unavailable)")
    max_value: Optional[float] = Field(None, description="Maximum valid pixel value (None when unavailable)")
    mean_value: Optional[float] = Field(None, description="Mean valid pixel value (None when unavailable)")
    std_dev: Optional[float] = Field(None, description="Standard deviation of valid pixels (None when unavailable)")
    valid_pixel_count: int = Field(..., description="Number of valid pixels")
    nodata_pixel_count: int = Field(..., description="Number of masked no-data pixels")
    valid_data_percentage: float = Field(..., description="Percentage of valid pixels in bounding raster [0, 100]")
    units: str = Field(..., description="Physical units of band (e.g., meters, degrees, unknown)")


class PlanningSlopeThreshold(BaseModel):
    """User-configured planning parameter. NOT a validated human safety limit."""

    threshold_deg: float = Field(..., gt=0.0, lt=90.0, description="Slope angle in degrees")
    parameter_class: Literal["user_configured_planning_assumption"] = "user_configured_planning_assumption"
    label: str = Field(..., min_length=1, description="Human-readable name of this planning scenario threshold")
    provenance: str = Field(..., min_length=1, description="Who/what defined this value and why (required)")
    version: str = Field(..., min_length=1, description="Version of this parameter definition")
    is_validated_safety_limit: Literal[False] = False


class TerrainSummary(BaseModel):
    source_dem_id: str = Field(..., description="Parent DEM dataset identifier")
    source_product_id: Optional[str] = Field(None, description="Official archive product identifier")
    processing_version: str = Field("1.0.0", description="Terrain processing pipeline version")
    study_area_name: str = Field(..., description="Active exploration region")
    resolution_meters_per_pixel: float = Field(..., description="Spatial resolution in meters")
    roughness_window_radius_meters: Optional[float] = Field(None, description="Physical neighborhood radius used for TRI")
    crs: str = Field(..., description="Coordinate reference system")
    elevation_stats: RasterBandStats = Field(..., description="Elevation statistics across valid pixels")
    slope_stats: RasterBandStats = Field(..., description="Calculated slope statistics (degrees)")
    aspect_stats: Optional[RasterBandStats] = Field(None, description="Calculated aspect statistics (degrees from North)")
    roughness_stats: Optional[RasterBandStats] = Field(None, description="Calculated Terrain Ruggedness Index statistics")
    planning_threshold: Optional["PlanningSlopeThreshold"] = Field(
        None,
        description=(
            "Optional USER-CONFIGURED planning slope threshold. Absent unless explicitly supplied. "
            "It is a planning assumption, never a validated astronaut safety limit."
        ),
    )
    planning_threshold_coverage_pct: Optional[float] = Field(
        None,
        description=(
            "Percentage of valid slope cells exceeding the user-configured planning threshold; "
            "null when no threshold was configured. Not a safety classification."
        ),
    )
    quality_warnings: List[str] = Field(default_factory=list, description="Quality or interpolation warnings")


class TerrainSummaryResponse(BaseModel):
    available: bool = Field(..., description="True only when derived from a validated real DEM raster")
    unavailable_reason: Optional[str] = Field(None, description="Explicit explanation when no valid DEM is available")
    summary: Optional[TerrainSummary] = Field(None, description="Calculated summary if available is True")


class TerrainPointResponse(BaseModel):
    available: bool = Field(..., description="True only when a validated DEM covers the coordinate and pixel is valid")
    latitude: float
    longitude: float
    crs: str
    latitude_convention: str = "Planetocentric"
    longitude_direction: str = "East"
    elevation_m: Optional[float] = Field(None, description="Sampled elevation in meters (None if unavailable/nodata)")
    slope_deg: Optional[float] = Field(None, description="Local Horn 3x3 slope in degrees if 3x3 valid")
    aspect_deg: Optional[float] = Field(None, description="Local compass aspect clockwise from North (-1.0 if flat)")
    roughness_tri_m: Optional[float] = Field(None, description="Local TRI roughness in meters")
    source_dataset_id: Optional[str] = None
    source_product_id: Optional[str] = None
    resolution_m: Optional[float] = None
    units: Optional[str] = None
    unavailable_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class TerrainLayerMetadata(BaseModel):
    layer_id: str = Field(..., description="Unique layer identifier")
    name: str = Field(..., description="Human-readable layer name")
    layer_type: str = Field(..., description="elevation | slope | aspect | roughness")
    source_dataset_id: str = Field(..., description="Source dataset ID")
    source_product_id: str = Field(..., description="Official archive product ID")
    units: str = Field(..., description="Physical units")
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    width: int
    height: int
    bounds: List[float] = Field(..., description="[min_lon, min_lat, max_lon, max_lat]")
    resolution_m: float
    crs: str
    processing_version: str = "1.0.0"
    preview_url: Optional[str] = None


class InsufficientCoverageReport(BaseModel):
    """Structured result returned when a requested footprint cannot support the requested analysis."""

    status: Literal["insufficient_coverage"] = "insufficient_coverage"
    requested_bounds: dict = Field(..., description="Exactly as requested: min_lon,min_lat,max_lon,max_lat (degrees)")
    requested_bounds_modified: Literal[False] = False
    source_coverage_bounds: Optional[dict] = None
    intersecting_bounds: Optional[dict] = None
    requested_pixel_dimensions: Optional[dict] = Field(None, description="Requested span divided by source pixel size (fractional)")
    available_pixel_dimensions: Optional[dict] = Field(None, description="Whole source pixels inside the requested footprint")
    source_resolution: Optional[dict] = None
    minimum_resolution_requirement: Optional[dict] = None
    insufficient_coverage_reason: str
    supported_products: List[str] = Field(default_factory=list)
    unsupported_derivative_products: List[str] = Field(default_factory=list)
    next_action: str
