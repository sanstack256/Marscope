"""Typed, evidence-preserving records for remotely indexed planetary imagery."""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ProductStage(str, Enum):
    DISCOVERED = "discovered_remotely"
    METADATA = "metadata_retrieved"
    DOWNLOAD_AVAILABLE = "download_available"
    DOWNLOADED = "download_completed"
    CHECKSUMMED = "checksum_verified"
    PARSED = "parsed_successfully"
    GEO_VERIFIED = "geospatial_association_verified"


class PanoramaEligibility(str, Enum):
    UNVERIFIED = "panorama_eligibility_unverified"
    SINGLE_FRAME = "ordinary_single_frame"
    MOSAIC = "image_mosaic"
    CYLINDRICAL = "cylindrical_panorama"
    OTHER_PROJECTION = "other_documented_panorama_projection"
    INVALID = "invalid_or_unavailable_image"


class ImageryProduct(BaseModel):
    source_archive: str
    source_record_uri: Optional[str] = None
    mission: Optional[str] = None
    instrument: Optional[str] = None
    dataset_id: Optional[str] = None
    product_id: str
    product_version: Optional[str] = None
    product_type: Optional[str] = None
    observation_time: Optional[str] = None
    sol: Optional[int] = None
    site: Optional[str] = None
    drive: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinate_convention: Optional[str] = None
    coordinate_reference_system: Optional[str] = None
    footprint: Optional[Any] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_format: Optional[str] = None
    projection: Optional[str] = None
    azimuth: Optional[float] = None
    camera_model: Optional[str] = None
    calibration_reference: Optional[str] = None
    processing_level: Optional[str] = None
    original_product_url: Optional[str] = None
    browse_image_url: Optional[str] = None
    label_url: Optional[str] = None
    local_file_path: Optional[str] = None
    local_label_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    archive_file_size_value: Optional[float] = None
    archive_file_size_unit: Optional[str] = None
    checksum: Optional[str] = None
    checksum_algorithm: Optional[str] = None
    local_sha256_checksum: Optional[str] = None
    rights_status: str = "unverified"
    retrieved_at: Optional[datetime] = None
    stages: list[ProductStage] = Field(default_factory=lambda: [ProductStage.DISCOVERED])
    metadata_gaps: list[str] = Field(default_factory=list)
    label_parse_status: str = "not_attempted"
    panorama_eligibility: PanoramaEligibility = PanoramaEligibility.UNVERIFIED
    provenance: dict[str, Any] = Field(default_factory=dict)
    processing_history: list[dict[str, Any]] = Field(default_factory=list)
