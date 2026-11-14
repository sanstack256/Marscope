"""
NASA Mars Trek WMTS Source Adapter
Martian Surface Intelligence & Exploration System

Provides discovery and tile endpoint metadata for the official NASA Mars Trek planetary tile server.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.ingestion.sources.base import SourceAdapter
from app.schemas.dataset import Dataset, GeographicCoverage, LicenseStatus, DatasetLifecycleStatus


class MarsTrekSourceAdapter(SourceAdapter):
    @property
    def source_name(self) -> str:
        return "NASA Solar System Treks (Mars Trek WMTS)"

    @property
    def base_url(self) -> str:
        return "https://trek.nasa.gov/tiles/Mars/EQ"

    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        products: List[Dataset] = [
            Dataset(
                id="mars_trek_viking_color",
                product_id="MARS_TREK_VIKING_MOSAIC_COLOR",
                product_title="NASA Mars Trek Viking Global Color Base Map (232 m/px)",
                product_type="IMAGERY / Global Optical Basemap",
                mission="Viking 1 & 2 / NASA Planetary Cartography",
                instrument="Viking Orbiter Visual Imaging Subsystem (VIS)",
                source_archive="NASA Solar System Treks API",
                original_product_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/USGS",
                acquisition_timestamp=datetime(1980, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                processing_level="Controlled Orthomosaic (Level 3)",
                calibration_status="Radiometrically normalized & photometrically corrected",
                coverage=GeographicCoverage(
                    min_latitude=-90.0,
                    max_latitude=90.0,
                    min_longitude=-180.0,
                    max_longitude=180.0,
                    center_latitude=0.0,
                    center_longitude=0.0,
                ),
                coordinate_reference_system="IAU2000:MARS_SPHERE",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular WMTS",
                horizontal_resolution_meters=232.0,
                units="RGB 8-bit reflectance",
                data_format="OGC WMTS / JPEG tiles",
                status=DatasetLifecycleStatus.AVAILABLE,
                quality_flags=["Global Orthorectified Baseline"],
                known_limitations=["Low resolution (~232 m/px) relative to modern HiRISE/CTX orbital imagery."],
                processing_history=["Viking MDIM 2.1 controlled cartographic mosaic"],
            ),
        ]
        return products
