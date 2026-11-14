"""
Geospatial Map Layer Schemas
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.dataset import VerificationState


class LayerLegendStop(BaseModel):
    value: str
    color: str
    label: str


class LayerLegend(BaseModel):
    title: str
    units: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    stops: List[LayerLegendStop] = Field(default_factory=list)


class MapLayer(BaseModel):
    layer_id: str
    display_name: str
    layer_type: str = Field(..., description="optical_wmts | topography_wmts | elevation_raster | slope_raster | aspect_raster | roughness_raster | observation_vector")
    category: str = Field(..., description="optical | topography | derived | rover")
    source_dataset_id: str
    source_product_id: str
    data_type: str
    units: str
    crs: str
    spatial_bounds: List[float] = Field(..., description="[min_lon, min_lat, max_lon, max_lat]")
    spatial_resolution_m: Optional[float] = None
    acquisition_date: Optional[datetime] = None
    processing_level: str
    processing_version: str
    valid_data_coverage_pct: Optional[float] = None
    nodata_coverage_pct: Optional[float] = None
    attribution: str
    license: str
    verification_state: VerificationState
    renderable: bool
    rendering_endpoint: Optional[str] = None
    tile_scheme: Optional[str] = Field(None, description="geographic_wmts | xyz_raster | geojson_vector")
    maximum_zoom: Optional[int] = None
    default_visible: bool = False
    default_opacity: float = 1.0
    known_limitations: List[str] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None
    legend: Optional[LayerLegend] = None


class LayerCatalogResponse(BaseModel):
    available_layers: List[MapLayer] = Field(default_factory=list)
    unavailable_layers: List[MapLayer] = Field(default_factory=list)
    total_available: int = 0
    total_unavailable: int = 0
