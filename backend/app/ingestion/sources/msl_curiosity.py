"""
NASA MSL Curiosity In-Situ Science Source Adapter
Martian Surface Intelligence & Exploration System

Provides discovery for MSL ChemCam (LIBS elemental chemistry)
and REMS (environmental / atmospheric monitoring station) PDS records.
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


class MslCuriositySourceAdapter(SourceAdapter):
    @property
    def source_name(self) -> str:
        return "NASA PDS Geosciences & Atmospheres Nodes (MSL Curiosity)"

    @property
    def base_url(self) -> str:
        return "https://pds-geosciences.wustl.edu/missions/msl"

    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        products: List[Dataset] = []

        ccam_p = Dataset(
            id="msl_chemcam_sol00010_psv",
            product_id="CL1_398380611PSV_F0030000CCAM04010P3",
            product_title="MSL ChemCam Laser-Induced Breakdown Spectrometer Calibrated Spectra (Sol 10)",
            product_type="SPECTRUM / In-Situ Chemistry",
            mission="Mars Science Laboratory (MSL)",
            instrument="Chemistry Camera (ChemCam LIBS)",
            source_archive="NASA PDS Geosciences Node",
            original_product_url="https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/sol00010/cl1_398380611psv_f0030000ccam04010p3.tab",
            original_label_url="https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/sol00010/cl1_398380611psv_f0030000ccam04010p3.lbl",
            doi_or_pds_id="MSL-M-CHEMCAM-LIBS-4/5-RDR-V1.0:CL1_398380611PSV_F0030000CCAM04010P3",
            license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
            attribution="NASA/JPL-Caltech/LANL/CNES/IRAP",
            acquisition_timestamp=None,
            observation_sol=10,
            processing_level="Calibrated Spectra (RDR Level 4/5)",
            calibration_status="Dark-subtracted, wavelength-calibrated, instrument-response corrected",
            coverage=GeographicCoverage(
                min_latitude=-4.595,
                max_latitude=-4.590,
                min_longitude=137.440,
                max_longitude=137.445,
                center_latitude=-4.592,
                center_longitude=137.442,
                longitude_range="[-180, 180]",
            ),
            coordinate_reference_system="IAU2000:49900",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            map_projection="Rover Local Frame / Topocentric",
            units="photons / (s * cm^2 * sr * nm)",
            data_format="PDS3 ASCII Table (.TAB)",
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
                    "acquisition_timestamp": VerificationState.UNKNOWN,
                    "coverage": VerificationState.UNVERIFIED,
                    "units": VerificationState.UNVERIFIED,
                },
                evidence_notes=["Catalog reference registered; download product & .LBL to parse spectra."],
            ),
            quality_flags=["Calibrated Emission Lines"],
            known_limitations=[
                "Point observation sampled at ~1.5 m standoff distance.",
                "Surface dust coating can attenuate bedrock signal on initial laser shots.",
            ],
            processing_history=["Catalog record discovered via MslCuriositySourceAdapter"],
        )
        products.append(ccam_p)

        rems_p = Dataset(
            id="msl_rems_sol00010_adr",
            product_id="RME_398334213ADR00100000000_______P9",
            product_title="MSL REMS Atmospheric Data Record (Pressure, Ambient Temp, Wind - Sol 10)",
            product_type="ATMOSPHERIC / Environmental In-Situ",
            mission="Mars Science Laboratory (MSL)",
            instrument="Rover Environmental Monitoring Station (REMS)",
            source_archive="NASA PDS Atmospheres Node",
            original_product_url="https://atmos.nmsu.edu/PDS/data/mslrem_1001/DATA/SOL_00001_00089/SOL00010/RME_398334213ADR00100000000_______P9.TAB",
            original_label_url="https://atmos.nmsu.edu/PDS/data/mslrem_1001/DATA/SOL_00001_00089/SOL00010/RME_398334213ADR00100000000_______P9.LBL",
            doi_or_pds_id="MSL-M-REMS-6-ADR-V1.0:RME_398334213ADR00100000000_______P9",
            license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
            attribution="NASA/JPL-Caltech/CAB (INTA-CSIC)",
            acquisition_timestamp=None,
            observation_sol=10,
            processing_level="Calibrated RDR (Level 6 ADR)",
            calibration_status="Calibrated by Centro de Astrobiologia (CAB)",
            coverage=GeographicCoverage(
                min_latitude=-4.595,
                max_latitude=-4.590,
                min_longitude=137.440,
                max_longitude=137.445,
                center_latitude=-4.592,
                center_longitude=137.442,
                longitude_range="[-180, 180]",
            ),
            coordinate_reference_system="IAU2000:49900",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            map_projection="Rover Site Frame",
            units="Pa (Pressure), K (Temperature), m/s (Wind)",
            data_format="PDS3 Fixed Length Table (.TAB)",
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
                    "acquisition_timestamp": VerificationState.UNKNOWN,
                    "coverage": VerificationState.UNVERIFIED,
                    "units": VerificationState.UNVERIFIED,
                },
                evidence_notes=["Catalog reference registered; download product & .LBL to parse measurements."],
            ),
            quality_flags=["Continuous Diurnal Log"],
            known_limitations=[
                "Thermal perturbation from rover radioisotope thermoelectric generator (RTG).",
                "Wind sensor boom 1 partial sensor damage on landing sol.",
            ],
            processing_history=["Catalog record discovered via MslCuriositySourceAdapter"],
        )
        products.append(rems_p)

        return products
