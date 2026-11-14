"""
NASA Mars Trek WMTS Source Adapter
Martian Surface Intelligence & Exploration System

Provides discovery and verified WMTS endpoints from NASA Solar System Treks.
"""

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
                product_id="Mars_Viking_MDIM21_ClrMosaic_global_232m",
                product_title="NASA Mars Trek Viking MDIM 2.1 Global Color Mosaic (232 m/px)",
                product_type="IMAGERY / Global Optical Basemap",
                mission="Viking 1 & 2 / NASA Planetary Cartography",
                instrument="Viking Orbiter Visual Imaging Subsystem (VIS)",
                source_archive="NASA Solar System Treks API",
                original_product_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
                original_label_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/WMTSCapabilities.xml",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/USGS",
                acquisition_timestamp=None,
                processing_level="Controlled Orthomosaic (Level 3)",
                calibration_status="Radiometrically normalized & photometrically corrected",
                coverage=GeographicCoverage(
                    min_latitude=-90.0,
                    max_latitude=90.0,
                    min_longitude=-180.0,
                    max_longitude=180.0,
                    center_latitude=0.0,
                    center_longitude=0.0,
                    longitude_range="[-180, 180]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Simple Cylindrical Equirectangular (OGC WMTS default028mm)",
                planetary_radii_m={"a": 3396190.0, "b": 3376200.0, "c": 3376200.0},
                horizontal_resolution_meters=232.0,
                units="RGB 8-bit reflectance (visual mosaic)",
                data_format="OGC WMTS / JPEG tiles (Zoom 0-7)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.NOT_APPLICABLE,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=["WMTS endpoint discovered; run live capability check to verify availability."],
                ),
                quality_flags=["Global Orthorectified Optical Baseline"],
                known_limitations=[
                    "Regional optical resolution (~232 m/px); cannot resolve rover-scale rocks or fine fractures."
                ],
                processing_history=["Catalog record discovered via MarsTrekSourceAdapter"],
            ),
            Dataset(
                id="mars_trek_mola_clrshade",
                product_id="Mars_MGS_MOLA_ClrShade_merge_global_463m",
                product_title="NASA Mars Trek MOLA Color Shaded Relief Mosaic (463 m/px)",
                product_type="IMAGERY / Shaded Topographic Visualization",
                mission="Mars Global Surveyor (MGS)",
                instrument="Mars Orbiter Laser Altimeter (MOLA)",
                source_archive="NASA Solar System Treks API",
                original_product_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
                original_label_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/GSFC",
                acquisition_timestamp=None,
                processing_level="Derived Shaded Relief Visualization (RGB)",
                calibration_status="Colorized hillshade (visual only — not raw metric elevation values)",
                coverage=GeographicCoverage(
                    min_latitude=-90.0,
                    max_latitude=90.0,
                    min_longitude=-180.0,
                    max_longitude=180.0,
                    center_latitude=0.0,
                    center_longitude=0.0,
                    longitude_range="[-180, 180]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Simple Cylindrical Equirectangular (OGC WMTS default028mm)",
                planetary_radii_m={"a": 3396190.0, "b": 3376200.0, "c": 3376200.0},
                horizontal_resolution_meters=463.0,
                units="RGB hillshade (visual representation only)",
                data_format="OGC WMTS / JPEG tiles (Zoom 0-7)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.NOT_APPLICABLE,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=["WMTS endpoint discovered; visual hillshade only (no elevation elevation queries)."],
                ),
                quality_flags=["Visual Shaded Relief"],
                known_limitations=[
                    "Visualization-only RGB tiles; cannot provide quantitative elevation in meters.",
                    "Zoom capped at level 7 (~463 m/px).",
                ],
                processing_history=["Catalog record discovered via MarsTrekSourceAdapter"],
            ),
            Dataset(
                id="mars_trek_curiosity_hirise",
                product_id="curiosity_hirise_mosaic",
                product_title="NASA Mars Trek Gale Crater HiRISE 0.25 m/px Basemap Mosaic",
                product_type="IMAGERY / Local High-Resolution Basemap",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="High Resolution Imaging Science Experiment (HiRISE)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://trek.nasa.gov/tiles/Mars/EQ/"
                    "curiosity_hirise_mosaic/1.0.0/default/default028mm/{z}/{y}/{x}.png"
                ),
                original_label_url=(
                    "https://trek.nasa.gov/tiles/Mars/EQ/"
                    "curiosity_hirise_mosaic/1.0.0/WMTSCapabilities.xml"
                ),
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/University of Arizona/Mars Trek",
                processing_level="Controlled Local HiRISE Mosaic (PNG WMTS Zoom 0-16)",
                calibration_status="Visual controlled orbital mosaic (not metric elevation)",
                coverage=GeographicCoverage(
                    min_latitude=-4.9255,
                    max_latitude=-4.2490,
                    min_longitude=137.1225,
                    max_longitude=137.7298,
                    center_latitude=-4.58725,
                    center_longitude=137.42615,
                    longitude_range="[-180, 180]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Simple Cylindrical Equirectangular (OGC WMTS default028mm)",
                planetary_radii_m={"a": 3396190.0, "b": 3376200.0, "c": 3376200.0},
                horizontal_resolution_meters=0.25,
                units="RGBA digital imagery (visual basemap)",
                data_format="OGC WMTS / PNG tiles (Zoom 0-16)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.NOT_APPLICABLE,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=["Regional Gale Crater HiRISE WMTS endpoint (zoom 0..16, bbox 137.1225..137.7298E)."],
                ),
                quality_flags=["High-Resolution Gale Crater Coverage"],
                known_limitations=[
                    "Covers Gale Crater Curiosity corridor only (-4.9255..-4.2490, 137.1225..137.7298).",
                    "Visual RGBA mosaic only; quantitative elevation requires HiRISE/MOLA DEM products.",
                ],
                processing_history=["Catalog record discovered via MarsTrekSourceAdapter"],
            ),
            Dataset(
                id="mars_trek_gale_ctx",
                product_id="Gale_CTX_BlockAdj_dd",
                product_title="NASA Mars Trek Gale Crater Block-Adjusted CTX Mosaic (~5 m/px)",
                product_type="IMAGERY / Regional Context Mosaic",
                mission="Mars Reconnaissance Orbiter (MRO)",
                instrument="Context Camera (CTX)",
                source_archive=self.source_name,
                original_product_url=(
                    "https://trek.nasa.gov/tiles/Mars/EQ/"
                    "Gale_CTX_BlockAdj_dd/1.0.0/default/default028mm/{z}/{y}/{x}.png"
                ),
                original_label_url=(
                    "https://trek.nasa.gov/tiles/Mars/EQ/"
                    "Gale_CTX_BlockAdj_dd/1.0.0/WMTSCapabilities.xml"
                ),
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/MSSS/USGS/Mars Trek",
                processing_level="Block-Adjusted CTX Mosaic (PNG WMTS Zoom 0-12)",
                calibration_status="Visual controlled orbital context mosaic",
                coverage=GeographicCoverage(
                    min_latitude=-6.5733,
                    max_latitude=-2.8078,
                    min_longitude=135.1843,
                    max_longitude=139.2413,
                    center_latitude=-4.69055,
                    center_longitude=137.2128,
                    longitude_range="[-180, 180]",
                ),
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Simple Cylindrical Equirectangular (OGC WMTS default028mm)",
                planetary_radii_m={"a": 3396190.0, "b": 3376200.0, "c": 3376200.0},
                horizontal_resolution_meters=5.0,
                units="RGBA digital imagery (visual context)",
                data_format="OGC WMTS / PNG tiles (Zoom 0-12)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.UNVERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.NOT_APPLICABLE,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.UNVERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=["Gale Crater block-adjusted CTX WMTS endpoint (zoom 0..12)."],
                ),
                quality_flags=["Regional Gale Crater Context (~5 m/px)"],
                known_limitations=["Visual mosaic only; does not supply terrain height."],
                processing_history=["Catalog record discovered via MarsTrekSourceAdapter"],
            ),
        ]
        return products
