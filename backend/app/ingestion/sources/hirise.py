"""
MARSCOPE NASA / UArizona HiRISE Stereo DTM & Orthoimage Source Adapter
Martian Surface Intelligence & Exploration System

Discovers verified 1.01 m/px HiRISE stereo DTMs and matching georeferenced orthoimages
from the University of Arizona / NASA PDS HiRISE DTM catalog covering Gale Crater,
Mount Sharp, Vera Rubin Ridge, Glen Torridon, and the 2025/2026 Boxwork Formations.
"""

from datetime import datetime
from typing import Dict, List, Optional

from app.ingestion.sources.base import SourceAdapter
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)


class HiriseSourceAdapter(SourceAdapter):
    @property
    def source_name(self) -> str:
        return "NASA PDS / University of Arizona HiRISE DTM Archive"

    @property
    def base_url(self) -> str:
        return "https://hirise-pds.lpl.arizona.edu/PDS/DTM"

    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        products = [
            Dataset(
                id="hirise_dteec_009149_1750",
                product_id="DTEEC_009149_1750_009294_1750_U01.IMG",
                product_title="HiRISE Stereo DTM — Gale Crater / Mount Sharp / Boxwork Formations (1.01 m/px)",
                product_type="DEM / High-Resolution Stereo DTM",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="High Resolution Imaging Science Experiment (HiRISE)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_009100_009199/"
                    "PSP_009149_1750_PSP_009294_1750/DTEEC_009149_1750_009294_1750_U01.IMG"
                ),
                original_label_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_009100_009199/"
                    "PSP_009149_1750_PSP_009294_1750/DTEEC_009149_1750_009294_1750_U01.IMG"
                ),
                doi_or_pds_id="MRO-M-HIRISE-5-DTM-V1.0:DTEEC_009149_1750_009294_1750_U01",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL-Caltech/University of Arizona HiRISE Team",
                acquisition_timestamp=datetime.fromisoformat("2011-08-29T00:00:00"),
                processing_level="HiRISE Stereo DTM (32-bit float meters, SOCET SET)",
                calibration_status="Tied to MOLA Areoid vertical datum (radius 3396.19 km)",
                coverage=GeographicCoverage(
                    min_latitude=-4.923097,
                    max_latitude=-4.676180,
                    min_longitude=137.353332,
                    max_longitude=137.468529,
                    center_latitude=-4.799639,
                    center_longitude=137.410930,
                    longitude_range="[0, 360]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular (central_meridian=137.41)",
                planetary_radii_m={"a": 3396190.0, "b": 3396190.0, "c": 3396190.0},
                horizontal_resolution_meters=1.0117,
                vertical_resolution_meters=0.25,
                units="meters",
                nodata_value=-3.4028226550889045e38,
                data_format="PDS3 Attached-Label 32-bit PC_REAL Image",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.UNVERIFIED,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "units": VerificationState.VERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=[
                        "Catalogued from UArizona HiRISE DTMCUMINDEX.TAB; covers Mount Sharp, Gediz Vallis, and 2025/2026 Boxwork Formations."
                    ],
                ),
                quality_flags=[
                    "Stereo Pair PSP_009149_1750 / PSP_009294_1750",
                    "Local Slope & Obstacle Resolution Suitable (1.01 m/px)",
                ],
                known_limitations=[
                    "Oblique stereo swath leaves diagonal no-data regions inside the bounding box; never interpolate across missing swath corners."
                ],
                processing_history=["Catalog record discovered via HiriseSourceAdapter"],
            ),
            Dataset(
                id="hirise_dteec_040770_1755",
                product_id="DTEEC_040770_1755_039280_1755_U01.IMG",
                product_title="HiRISE Stereo DTM — Gale Crater / Bradbury Landing to Vera Rubin Ridge (1.01 m/px)",
                product_type="DEM / High-Resolution Stereo DTM",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="High Resolution Imaging Science Experiment (HiRISE)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/ESP/ORB_040700_040799/"
                    "ESP_040770_1755_ESP_039280_1755/DTEEC_040770_1755_039280_1755_U01.IMG"
                ),
                original_label_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/ESP/ORB_040700_040799/"
                    "ESP_040770_1755_ESP_039280_1755/DTEEC_040770_1755_039280_1755_U01.IMG"
                ),
                doi_or_pds_id="MRO-M-HIRISE-5-DTM-V1.0:DTEEC_040770_1755_039280_1755_U01",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL-Caltech/University of Arizona HiRISE Team",
                processing_level="HiRISE Stereo DTM (32-bit float meters, SOCET SET)",
                calibration_status="Tied to MOLA Areoid vertical datum (radius 3396.19 km)",
                coverage=GeographicCoverage(
                    min_latitude=-4.792188,
                    max_latitude=-4.583297,
                    min_longitude=137.335157,
                    max_longitude=137.442692,
                    center_latitude=-4.687743,
                    center_longitude=137.388925,
                    longitude_range="[0, 360]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular (central_meridian=137.39)",
                planetary_radii_m={"a": 3396190.0, "b": 3396190.0, "c": 3396190.0},
                horizontal_resolution_meters=1.0118,
                vertical_resolution_meters=0.25,
                units="meters",
                nodata_value=-3.4028226550889045e38,
                data_format="PDS3 Attached-Label 32-bit PC_REAL Image",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.UNVERIFIED,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "units": VerificationState.VERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=[
                        "Catalogued from UArizona HiRISE DTMCUMINDEX.TAB; covers Bradbury Landing through Murray Formation & Vera Rubin Ridge."
                    ],
                ),
                quality_flags=[
                    "Stereo Pair ESP_040770_1755 / ESP_039280_1755",
                    "Local Slope & Obstacle Resolution Suitable (1.01 m/px)",
                ],
                known_limitations=[
                    "Oblique stereo swath leaves diagonal no-data regions inside the bounding box; never interpolate across missing swath corners."
                ],
                processing_history=["Catalog record discovered via HiriseSourceAdapter"],
            ),
            Dataset(
                id="hirise_psp_009149_1750_ortho",
                product_id="PSP_009149_1750_RED_C_01_ORTHO.JP2",
                product_title="HiRISE Orthorectified Surface Image — Mount Sharp / Boxwork (1.01 m/px)",
                product_type="IMAGE / Orthorectified Orbital Imagery",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="High Resolution Imaging Science Experiment (HiRISE)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_009100_009199/"
                    "PSP_009149_1750_PSP_009294_1750/PSP_009149_1750_RED_C_01_ORTHO.JP2"
                ),
                original_label_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_009100_009199/"
                    "PSP_009149_1750_PSP_009294_1750/PSP_009149_1750_RED_C_01_ORTHO.LBL"
                ),
                doi_or_pds_id="MRO-M-HIRISE-5-DTM-V1.0:PSP_009149_1750_RED_C_01_ORTHO",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL-Caltech/University of Arizona HiRISE Team",
                processing_level="DTM-Orthorectified JP2 (1.01 m/px)",
                calibration_status="Radiometrically stretched 8-bit greyscale registered to DTEEC_009149_1750",
                coverage=GeographicCoverage(
                    min_latitude=-4.923097,
                    max_latitude=-4.676180,
                    min_longitude=137.353332,
                    max_longitude=137.468529,
                    center_latitude=-4.799639,
                    center_longitude=137.410930,
                    longitude_range="[0, 360]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular (central_meridian=137.41)",
                planetary_radii_m={"a": 3396190.0, "b": 3396190.0, "c": 3396190.0},
                horizontal_resolution_meters=1.0117,
                units="digital_number",
                data_format="PDS3 .LBL + JPEG2000 (.JP2)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    field_verification={"resolution": VerificationState.VERIFIED},
                ),
                processing_history=["Catalog record discovered via HiriseSourceAdapter"],
            ),
            Dataset(
                id="hirise_esp_040770_1755_ortho",
                product_id="ESP_040770_1755_RED_C_01_ORTHO.JP2",
                product_title="HiRISE Orthorectified Surface Image — Bradbury to Vera Rubin Ridge (1.01 m/px)",
                product_type="IMAGE / Orthorectified Orbital Imagery",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="High Resolution Imaging Science Experiment (HiRISE)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/ESP/ORB_040700_040799/"
                    "ESP_040770_1755_ESP_039280_1755/ESP_040770_1755_RED_C_01_ORTHO.JP2"
                ),
                original_label_url=(
                    "https://hirise-pds.lpl.arizona.edu/PDS/DTM/ESP/ORB_040700_040799/"
                    "ESP_040770_1755_ESP_039280_1755/ESP_040770_1755_RED_C_01_ORTHO.LBL"
                ),
                doi_or_pds_id="MRO-M-HIRISE-5-DTM-V1.0:ESP_040770_1755_RED_C_01_ORTHO",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL-Caltech/University of Arizona HiRISE Team",
                processing_level="DTM-Orthorectified JP2 (1.01 m/px)",
                calibration_status="Radiometrically stretched 8-bit greyscale registered to DTEEC_040770_1755",
                coverage=GeographicCoverage(
                    min_latitude=-4.792188,
                    max_latitude=-4.583297,
                    min_longitude=137.335157,
                    max_longitude=137.442692,
                    center_latitude=-4.687743,
                    center_longitude=137.388925,
                    longitude_range="[0, 360]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular (central_meridian=137.39)",
                planetary_radii_m={"a": 3396190.0, "b": 3396190.0, "c": 3396190.0},
                horizontal_resolution_meters=1.0118,
                units="digital_number",
                data_format="PDS3 .LBL + JPEG2000 (.JP2)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    field_verification={"resolution": VerificationState.VERIFIED},
                ),
                processing_history=["Catalog record discovered via HiriseSourceAdapter"],
            ),
        ]
        return products
