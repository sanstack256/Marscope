"""
NASA PDS MOLA MEGDR Source Adapter
Martian Surface Intelligence & Exploration System

Provides discovery and metadata verification for MOLA Precision Experiment Data Record elevation maps.
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
from app.ingestion.sources.base import SourceAdapter
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)


class PdsMolaSourceAdapter(SourceAdapter):
    @property
    def source_name(self) -> str:
        return "NASA PDS Geosciences Node (MGS MOLA MEGDR)"

    @property
    def base_url(self) -> str:
        return "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x"

    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        """
        Catalog discovery entries for PDS MOLA MEGDR elevation datasets.
        Metadata verification remains UNVERIFIED/PENDING until the PDS3 label and binary
        raster are inspected locally.
        """
        products: List[Dataset] = []

        p1 = Dataset(
            id="mola_megt00n090hb",
            product_id="MEGT00N090HB.IMG",
            product_title="MOLA Mission Experiment Gridded Data Record (MEGDR) 128 ppd Topography",
            product_type="DEM / Elevation",
            mission="Mars Global Surveyor (MGS)",
            instrument="Mars Orbiter Laser Altimeter (MOLA)",
            source_archive="NASA PDS Geosciences Node",
            original_product_url=f"{self.base_url}/meg128/megt00n090hb.img",
            original_label_url=f"{self.base_url}/meg128/megt00n090hb.lbl",
            doi_or_pds_id="MGS-M-MOLA-5-MEGDR-L3-V1.0:MEGT00N090HB.IMG",
            license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
            attribution="NASA/JPL/Goddard Space Flight Center/PDS Geosciences Node",
            acquisition_timestamp=datetime(2003, 3, 21, 1, 0, 0, tzinfo=timezone.utc),
            processing_level="Calibrated Derived (RDR/DDR Level 3)",
            calibration_status="Radiometrically & Crossover Solution Calibrated to Goddard Areoid",
            coverage=GeographicCoverage(
                min_latitude=-44.0,
                max_latitude=0.0,
                min_longitude=90.0,
                max_longitude=180.0,
                center_latitude=-22.0,
                center_longitude=135.0,
                longitude_range="[0, 360]",
            ),
            coordinate_reference_system="IAU2000:MARS_SPHERE",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            map_projection="Simple Cylindrical (Equirectangular)",
            planetary_radii_m={"a": 3396000.0, "b": 3396000.0, "c": 3396000.0},
            horizontal_resolution_meters=463.0,
            vertical_resolution_meters=1.0,
            units="meters",
            nodata_value=-32768.0,
            data_format="PDS3 Binary Image (MSB_INTEGER 16-bit)",
            file_size_bytes=129761280,
            status=DatasetLifecycleStatus.DISCOVERED,
            verification=MetadataVerification(
                archive_availability=VerificationState.UNVERIFIED,
                product_discovery=VerificationState.VERIFIED,
                metadata_verification=VerificationState.UNVERIFIED,
                license_verification=VerificationState.VERIFIED,
                coverage_verification=VerificationState.UNVERIFIED,
                download_verification=VerificationState.UNVERIFIED,
                processing_verification=VerificationState.UNVERIFIED,
                field_verification={
                    "crs": VerificationState.UNVERIFIED,
                    "units": VerificationState.UNVERIFIED,
                    "resolution": VerificationState.UNVERIFIED,
                    "coverage": VerificationState.UNVERIFIED,
                    "license": VerificationState.VERIFIED,
                },
                evidence_notes=["Catalog reference registered; requires PDS3 .LBL + .IMG acquisition to verify."],
            ),
            quality_flags=["Crossover Solved", "Shot Noise Filtered"],
            known_limitations=[
                "Horizontal resolution (~463 m/px) limits sub-meter rock obstacle detection.",
                "Equatorial track spacing results in ~12 km gap interpolation between orbital ground tracks.",
            ],
            processing_history=["Catalog record discovered via PdsMolaSourceAdapter"],
        )
        products.append(p1)

        p2 = Dataset(
            id="mola_megt90n000cb",
            product_id="MEGT90N000CB.IMG",
            product_title="MOLA Global Reference MEGDR 4 ppd Topography",
            product_type="DEM / Global Reference Elevation",
            mission="Mars Global Surveyor (MGS)",
            instrument="Mars Orbiter Laser Altimeter (MOLA)",
            source_archive="NASA PDS Geosciences Node",
            original_product_url=f"{self.base_url}/meg004/megt90n000cb.img",
            original_label_url=f"{self.base_url}/meg004/megt90n000cb.lbl",
            doi_or_pds_id="MGS-M-MOLA-5-MEGDR-L3-V1.0:MEGT90N000CB.IMG",
            license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
            attribution="NASA/JPL/Goddard Space Flight Center",
            acquisition_timestamp=datetime(2003, 4, 3, 1, 0, 0, tzinfo=timezone.utc),
            processing_level="Derived Global Map (Level 3)",
            calibration_status="Calibrated to MOLA Areoid datum",
            coverage=GeographicCoverage(
                min_latitude=-90.0,
                max_latitude=90.0,
                min_longitude=0.0,
                max_longitude=360.0,
                center_latitude=0.0,
                center_longitude=180.0,
                longitude_range="[0, 360]",
            ),
            coordinate_reference_system="IAU2000:MARS_SPHERE",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            map_projection="Simple Cylindrical",
            planetary_radii_m={"a": 3396000.0, "b": 3396000.0, "c": 3396000.0},
            horizontal_resolution_meters=14818.0,
            vertical_resolution_meters=1.0,
            units="meters",
            nodata_value=-32768.0,
            data_format="PDS3 Binary Image (MSB_INTEGER 16-bit)",
            file_size_bytes=2073600,
            status=DatasetLifecycleStatus.DISCOVERED,
            verification=MetadataVerification(
                archive_availability=VerificationState.UNVERIFIED,
                product_discovery=VerificationState.VERIFIED,
                metadata_verification=VerificationState.UNVERIFIED,
                license_verification=VerificationState.VERIFIED,
                coverage_verification=VerificationState.UNVERIFIED,
                download_verification=VerificationState.UNVERIFIED,
                processing_verification=VerificationState.UNVERIFIED,
                field_verification={
                    "crs": VerificationState.UNVERIFIED,
                    "units": VerificationState.UNVERIFIED,
                    "resolution": VerificationState.UNVERIFIED,
                    "coverage": VerificationState.UNVERIFIED,
                    "license": VerificationState.VERIFIED,
                },
                evidence_notes=["Catalog reference registered; requires PDS3 .LBL + .IMG acquisition to verify."],
            ),
            quality_flags=["Global Continuous Coverage"],
            known_limitations=[
                "Coarse macro-scale elevation only (~14.8 km/pixel). Cannot resolve local obstacles or boxwork ridges."
            ],
            processing_history=["Catalog record discovered via PdsMolaSourceAdapter"],
        )
        products.append(p2)

        return products
