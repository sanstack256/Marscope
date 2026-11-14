"""
MARSCOPE Data Sources & Provenance Register API
Martian Surface Intelligence & Exploration System

Returns authoritative dataset inventory matching DATA_SOURCES.md.
"""

from typing import List, Dict, Any
from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["Data Sources & Provenance"])

_SOURCES_REGISTER: List[Dict[str, Any]] = [
    {
        "name": "HiRISE RDR Orthorectified Imagery",
        "mission": "Mars Reconnaissance Orbiter (MRO)",
        "instrument": "HiRISE",
        "purpose": "Sub-meter optical surface terrain, boulder hazards, and fracture characterization",
        "official_archive_source": "NASA PDS / University of Arizona HiRISE",
        "source_url": "https://www.uahirise.org/",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "PENDING VERIFICATION (Specific DTM overlap required)",
        "integration_priority": "P0 (Core Visual & Hazard)",
    },
    {
        "name": "HiRISE Digital Terrain Model (DTM)",
        "mission": "Mars Reconnaissance Orbiter (MRO)",
        "instrument": "HiRISE Stereo",
        "purpose": "1-meter high-precision micro-topography for local slope and roughness analysis",
        "official_archive_source": "NASA PDS Geosciences Node",
        "source_url": "https://pds-geosciences.wustl.edu/missions/mro/hirise.htm",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "PENDING VERIFICATION (Footprint check required)",
        "integration_priority": "P0 (Micro-Traversability)",
    },
    {
        "name": "CTX Controlled Mosaics",
        "mission": "Mars Reconnaissance Orbiter (MRO)",
        "instrument": "CTX",
        "purpose": "6-meter regional optical context linking HiRISE swaths across Gale Crater",
        "official_archive_source": "NASA PDS / WUSTL ODE",
        "source_url": "https://ode.rsl.wustl.edu/mars/",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "VERIFIED (Global & regional Gale basin coverage confirmed)",
        "integration_priority": "P0 (Regional Basemap)",
    },
    {
        "name": "MOLA MEGDR Topography (128 ppd)",
        "mission": "Mars Global Surveyor (MGS)",
        "instrument": "MOLA",
        "purpose": "Regional elevation datum, areoid reference elevation, and regional basin slope modeling",
        "official_archive_source": "NASA PDS Geosciences Node",
        "source_url": "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "VERIFIED (Continuous global Gale Crater coverage)",
        "integration_priority": "P0 (Elevation Datum)",
    },
    {
        "name": "MSL Curiosity ChemCam LIBS / RMI",
        "mission": "Mars Science Laboratory (MSL)",
        "instrument": "ChemCam",
        "purpose": "In-situ laser-induced breakdown spectroscopy for elemental rock/vein chemistry",
        "official_archive_source": "NASA PDS Geosciences Node",
        "source_url": "https://pds-geosciences.wustl.edu/missions/msl/",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "VERIFIED (Curiosity traverse in Gale Crater)",
        "integration_priority": "P1 (Field Ground Truth)",
    },
    {
        "name": "MSL Curiosity REMS Atmospheric Data",
        "mission": "Mars Science Laboratory (MSL)",
        "instrument": "REMS",
        "purpose": "In-situ diurnal atmospheric pressure, ambient temperature, and wind speed",
        "official_archive_source": "NASA PDS Atmospheres Node",
        "source_url": "https://pds-atmospheres.nmsu.edu/",
        "license_verification_status": "VERIFIED OPEN (NASA Public Domain / CC0)",
        "coverage_verification_status": "VERIFIED (Continuous mission environmental log)",
        "integration_priority": "P1 (Atmospheric Model)",
    },
    {
        "name": "NASA Mars Trek WMTS Reference Tiles",
        "mission": "NASA Solar System Treks",
        "instrument": "Cartographic Pipeline",
        "purpose": "Rapid map tile streaming and visual verification of global Mars layers",
        "official_archive_source": "NASA Mars Trek API",
        "source_url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars",
        "license_verification_status": "VERIFIED OPEN (US Govt Open API)",
        "coverage_verification_status": "VERIFIED (Mars Trek global endpoint active)",
        "integration_priority": "P1 (Tile Reference Stream)",
    },
]


@router.get("")
async def list_data_sources() -> List[Dict[str, Any]]:
    """
    Returns the complete dataset register matching DATA_SOURCES.md.
    """
    return _SOURCES_REGISTER
