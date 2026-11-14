"""
USGS-NASA Planetary Geologic Mapping Program Source Adapter
Authoritative global and regional planetary geologic mapping references with explicit scale constraints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.ingestion.sources.base import SourceAdapter
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)


class UsgsPlanetaryGeologicMappingAdapter(SourceAdapter):
    """
    Exposes verified USGS-NASA Planetary Geologic Mapping Program publications (SIM 3292).
    Global/regional geologic units are strictly stratigraphic context — NEVER used as local route hazards.
    """

    SIM3292_PUBLICATION_URL = "https://pubs.usgs.gov/sim/3292/"

    @property
    def source_name(self) -> str:
        return "USGS-NASA Planetary Geologic Mapping Program"

    @property
    def base_url(self) -> str:
        return "https://pubs.usgs.gov/sim/3292/"

    def discover_products(self, target_region: Optional[Dict[str, float]] = None) -> List[Dataset]:
        gale_env = GeographicCoverage(
            min_latitude=-90.0,
            max_latitude=90.0,
            min_longitude=-180.0,
            max_longitude=180.0,
            center_latitude=-4.9,
            center_longitude=137.4,
            longitude_range="[-180, 180]",
        )
        return [
            Dataset(
                id="usgs_sim3292_mars_geology",
                product_id="USGS_SIM3292_MARS_GEOL_20M",
                product_title="USGS SIM 3292: Geologic Map of Mars (1:20,000,000, Tanaka et al., 2014)",
                product_type="GEOLOGIC_MAP / Global Publication (1:20,000,000)",
                mission="USGS Astrogeology / NASA Planetary Geologic Mapping Program",
                instrument="MOLA + THEMIS + CTX Multi-Mission Geologic Synthesis",
                source_archive=self.source_name,
                original_product_url=self.SIM3292_PUBLICATION_URL,
                original_label_url="https://pubs.usgs.gov/sim/3292/pdf/sim3292_pamphlet.pdf",
                doi_or_pds_id="DOI:10.3133/sim3292",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="U.S. Geological Survey / NASA Planetary Geologic Mapping Program (Tanaka et al., 2014)",
                acquisition_timestamp=datetime(2014, 7, 1, tzinfo=timezone.utc),
                processing_level="Peer-Reviewed Global Geologic Map & ArcGIS Shapefile Package",
                calibration_status="1:20,000,000 global stratigraphic unit synthesis",
                coverage=gale_env,
                coordinate_reference_system="IAU2000:49900",
                latitude_convention="Planetocentric",
                longitude_direction="East",
                map_projection="Equirectangular + Polar Stereographic Map Sheets",
                planetary_radii_m={"a": 3396190.0, "b": 3376200.0, "c": 3376200.0},
                horizontal_resolution_meters=20000.0,
                units="geologic_map_unit_polygons",
                data_format="PDF / GIS Package (SIM 3292)",
                status=DatasetLifecycleStatus.DISCOVERED,
                verification=MetadataVerification(
                    archive_availability=VerificationState.UNVERIFIED,
                    product_discovery=VerificationState.VERIFIED,
                    metadata_verification=VerificationState.VERIFIED,
                    license_verification=VerificationState.VERIFIED,
                    coverage_verification=VerificationState.UNVERIFIED,
                    download_verification=VerificationState.NOT_APPLICABLE,
                    processing_verification=VerificationState.NOT_APPLICABLE,
                    field_verification={
                        "crs": VerificationState.VERIFIED,
                        "resolution": VerificationState.VERIFIED,
                        "coverage": VerificationState.UNVERIFIED,
                    },
                    evidence_notes=[
                        "USGS SIM 3292 publication verified at https://pubs.usgs.gov/sim/3292/.",
                        "Global map scale is 1:20,000,000 (~20 km minimum mapping unit); NOT suitable for local slope or astronaut hazard checks.",
                    ],
                ),
                quality_flags=["Peer-Reviewed Stratigraphic Reference", "Macro-Scale Context Only"],
                known_limitations=[
                    "SCALE CONSTRAINT: 1:20,000,000 global geologic map (~20 km polygon generality) cannot resolve meter-scale obstacles, cliffs, boxwork ridges, or local EVA traversal hazards.",
                    "Excluded automatically from route cost computation and slope limit gating; informational geologic context only.",
                ],
                processing_history=["Registered via UsgsPlanetaryGeologicMappingAdapter"],
            )
        ]

    @staticmethod
    def get_scale_constraint_metadata() -> Dict[str, Any]:
        return {
            "source_name": "USGS-NASA Planetary Geologic Mapping Program",
            "primary_reference": "USGS SIM 3292 (Tanaka et al., 2014)",
            "publication_url": UsgsPlanetaryGeologicMappingAdapter.SIM3292_PUBLICATION_URL,
            "scale": "1:20,000,000",
            "map_scale": "1:20,000,000",
            "suitable_for_regional_stratigraphy": True,
            "suitable_for_local_route_hazards": False,
            "excluded_from_traversal_cost": True,
            "warning": (
                "USGS SIM 3292 is a 1:20,000,000 global geologic map. Regional unit boundaries "
                "must NEVER be interpreted as local engineering hazards or traversability certification."
            ),
        }
