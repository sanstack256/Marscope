"""
Terrain Intelligence & Processing Schemas
Martian Surface Intelligence & Exploration System
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class RasterBandStats(BaseModel):
    min_value: float = Field(..., description="Minimum valid pixel value")
    max_value: float = Field(..., description="Maximum valid pixel value")
    mean_value: float = Field(..., description="Mean valid pixel value")
    std_dev: float = Field(..., description="Standard deviation of valid pixels")
    valid_pixel_count: int = Field(..., description="Number of valid pixels")
    nodata_pixel_count: int = Field(..., description="Number of masked no-data pixels")
    valid_data_percentage: float = Field(..., description="Percentage of valid pixels in bounding raster [0, 100]")
    units: str = Field(..., description="Physical units of band (e.g., meters, degrees, dimensionless)")


class TerrainSummary(BaseModel):
    source_dem_id: str = Field(..., description="Parent DEM product identifier")
    study_area_name: str = Field(..., description="Active exploration region")
    resolution_meters_per_pixel: float = Field(..., description="Spatial resolution in meters")
    crs: str = Field(..., description="Coordinate reference system")
    elevation_stats: RasterBandStats = Field(..., description="Elevation statistics across valid pixels")
    slope_stats: RasterBandStats = Field(..., description="Calculated slope statistics (degrees)")
    aspect_stats: Optional[RasterBandStats] = Field(None, description="Calculated aspect statistics (degrees from North)")
    roughness_stats: Optional[RasterBandStats] = Field(None, description="Calculated Terrain Ruggedness Index statistics")
    critical_slope_threshold_deg: float = Field(25.0, description="Safety slope threshold")
    critical_slope_coverage_pct: float = Field(..., description="Percentage of study area exceeding critical slope threshold")
    quality_warnings: List[str] = Field(default_factory=list, description="Quality or interpolation warnings")


class TerrainLayerMetadata(BaseModel):
    layer_id: str = Field(..., description="Unique layer identifier (e.g., dem_gale_mola, slope_gale_mola)")
    name: str = Field(..., description="Human-readable layer name")
    layer_type: str = Field(..., description="elevation | slope | aspect | roughness")
    source_dataset_id: str = Field(..., description="Source dataset ID")
    units: str = Field(..., description="Physical units")
    min_val: float
    max_val: float
    width: int
    height: int
    bounds: List[float] = Field(..., description="[min_lon, min_lat, max_lon, max_lat]")
    resolution_m: float
    crs: str
    preview_url: Optional[str] = None
