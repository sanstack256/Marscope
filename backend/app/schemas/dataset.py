"""
MARSCOPE Dataset & Provenance Metadata Schemas
Martian Surface Intelligence & Exploration System
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, HttpUrl


class DatasetLifecycleStatus(str, Enum):
    DISCOVERED = "discovered"
    METADATA_VERIFIED = "metadata_verified"
    LICENSE_VERIFIED = "license_verified"
    DOWNLOADED = "downloaded"
    VALIDATED = "validated"
    PROCESSED = "processed"
    AVAILABLE = "available"
    FAILED_DOWNLOAD = "failed_download"
    FAILED_VALIDATION = "failed_validation"
    FAILED_PROCESSING = "failed_processing"


class LicenseStatus(str, Enum):
    VERIFIED_OPEN_PUBLIC_DOMAIN = "NASA Public Domain / US Govt Open"
    VERIFIED_OPEN_CC0 = "Creative Commons CC0 1.0"
    VERIFIED_OPEN_RESEARCH = "Open Scientific Research Reuse"
    PENDING_VERIFICATION = "Pending Verification"
    RESTRICTED = "Restricted / Proprietary"


class GeographicCoverage(BaseModel):
    min_latitude: float = Field(..., description="Minimum latitude in decimal degrees [-90, +90]")
    max_latitude: float = Field(..., description="Maximum latitude in decimal degrees [-90, +90]")
    min_longitude: float = Field(..., description="Minimum longitude in decimal degrees [-180, +180] or [0, 360]")
    max_longitude: float = Field(..., description="Maximum longitude in decimal degrees [-180, +180] or [0, 360]")
    center_latitude: Optional[float] = Field(None, description="Center latitude")
    center_longitude: Optional[float] = Field(None, description="Center longitude")


class Dataset(BaseModel):
    id: str = Field(..., description="Unique internal dataset slug (e.g., mola_megt00n090hb)")
    product_id: str = Field(..., description="Official NASA/ESA PDS product identifier")
    product_title: str = Field(..., description="Descriptive human-readable product title")
    product_type: str = Field(..., description="Type of data (e.g., DEM, IMAGE, SPECTRUM, ATMOSPHERIC)")
    mission: str = Field(..., description="Originating mission (e.g., Mars Global Surveyor, MSL)")
    instrument: str = Field(..., description="Originating sensor/instrument (e.g., MOLA, ChemCam, REMS)")
    source_archive: str = Field(..., description="Archive source name (e.g., NASA PDS Geosciences, Atmospheres)")
    original_product_url: str = Field(..., description="Direct archive URL for product download")
    original_label_url: Optional[str] = Field(None, description="Direct URL to PDS label (.lbl / .xml)")
    doi_or_pds_id: Optional[str] = Field(None, description="Permanent DOI or PDS dataset identifier")
    license: LicenseStatus = Field(LicenseStatus.PENDING_VERIFICATION, description="Legal reuse terms")
    attribution: str = Field(..., description="Mandatory attribution / citation statement")
    
    # Temporal & Acquisition metadata
    acquisition_timestamp: Optional[datetime] = Field(None, description="UTC observation timestamp")
    observation_sol: Optional[int] = Field(None, description="Mission Mars Sol number if applicable")
    processing_level: str = Field("Calibrated (RDR)", description="Processing pipeline level (EDR, RDR, DDR, DTM)")
    calibration_status: str = Field("Calibrated", description="Physical calibration description")
    
    # Spatial & Projection metadata
    coverage: GeographicCoverage = Field(..., description="Bounding box coverage in planetary coordinates")
    coordinate_reference_system: str = Field("IAU2000:49900", description="Documented Mars CRS")
    latitude_convention: str = Field("Planetocentric", description="Latitude convention (Planetocentric / Planetographic)")
    longitude_direction: str = Field("East", description="Positive longitude direction (East / West)")
    map_projection: str = Field("Equirectangular", description="Planetary cartographic projection")
    horizontal_resolution_meters: Optional[float] = Field(None, description="Pixel resolution in meters")
    vertical_resolution_meters: Optional[float] = Field(None, description="Vertical resolution in meters where applicable")
    units: str = Field(..., description="Physical measurement units (e.g., meters, Pa, K, counts)")
    nodata_value: Optional[float] = Field(None, description="Explicit no-data representation")
    data_format: str = Field("PDS3 / GeoTIFF", description="Native binary or container format")
    
    # Lifecycle & Verification tracking
    file_size_bytes: Optional[int] = Field(None, description="File size on disk or archive")
    sha256_checksum: Optional[str] = Field(None, description="SHA-256 verification hash")
    status: DatasetLifecycleStatus = Field(DatasetLifecycleStatus.DISCOVERED, description="Current lifecycle state")
    failure_reason: Optional[str] = Field(None, description="Reason for failure if status is in FAILED_* state")
    quality_flags: List[str] = Field(default_factory=list, description="Quality indicators or flags")
    known_limitations: List[str] = Field(default_factory=list, description="Documented instrument or interpolation limitations")
    processing_history: List[str] = Field(default_factory=list, description="Audit log of pipeline processing steps")
    local_file_path: Optional[str] = Field(None, description="Relative local path when downloaded")
    processed_file_path: Optional[str] = Field(None, description="Relative local path when processed to COG/GeoTIFF")


class DatasetManifest(BaseModel):
    product_id: str
    dataset_id: str
    source_url: str
    download_timestamp_utc: datetime
    file_size_bytes: int
    sha256_checksum: str
    storage_path: str
    verified_integrity: bool
    manifest_version: str = "1.0.0"
