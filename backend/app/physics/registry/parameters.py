"""
MARSCOPE Physics Parameter Registry
Martian Surface Intelligence & Exploration System

All constants are traceable to the NASA GSFC Planetary Fact Sheet and peer-reviewed mission publications.
"""

from typing import Dict, Optional
from app.schemas.physics import PhysicsParameter

_REGISTRY: Dict[str, PhysicsParameter] = {
    "mars_standard_gravity": PhysicsParameter(
        id="mars_standard_gravity",
        name="Martian Surface Gravitational Acceleration",
        value=3.72076,
        units="m/s^2",
        source="NASA Goddard Space Flight Center (GSFC) Mars Fact Sheet",
        source_url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        validity_range=[3.69, 3.75],
        applicable_conditions="Global mean surface reference",
        uncertainty=0.0001,
        version="1.0.0",
        verification_status="Verified NASA Fact Sheet",
    ),
    "mars_mean_radius": PhysicsParameter(
        id="mars_mean_radius",
        name="Mars Volumetric Mean Radius",
        value=3389500.0,
        units="m",
        source="IAU/IAG Working Group on Cartographic Coordinates / NASA GSFC",
        source_url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        validity_range=[3376200.0, 3396190.0],
        applicable_conditions="Spherical approximation",
        uncertainty=100.0,
        version="1.0.0",
        verification_status="Verified IAU Standard",
    ),
    "mars_equatorial_radius": PhysicsParameter(
        id="mars_equatorial_radius",
        name="Mars Equatorial Radius (Semi-Major Axis)",
        value=3396190.0,
        units="m",
        source="IAU 2000 Mars Spheroid",
        source_url="https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/pck.html",
        validity_range=[3396000.0, 3396500.0],
        applicable_conditions="IAU2000:49900 Ellipsoid Datum",
        uncertainty=50.0,
        version="1.0.0",
        verification_status="Verified IAU Standard",
    ),
    "mars_polar_radius": PhysicsParameter(
        id="mars_polar_radius",
        name="Mars Polar Radius (Semi-Minor Axis)",
        value=3376200.0,
        units="m",
        source="IAU 2000 Mars Spheroid",
        source_url="https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/pck.html",
        validity_range=[3376000.0, 3376500.0],
        applicable_conditions="IAU2000:49900 Ellipsoid Datum",
        uncertainty=50.0,
        version="1.0.0",
        verification_status="Verified IAU Standard",
    ),
    "specific_gas_constant_co2": PhysicsParameter(
        id="specific_gas_constant_co2",
        name="Specific Gas Constant for Martian Atmosphere (95.3% CO2)",
        value=188.92,
        units="J/(kg*K)",
        source="Standard Atmospheric Thermodynamics / R_universal / M_CO2",
        source_url="https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
        validity_range=[185.0, 192.0],
        applicable_conditions="Pure CO2 approximation (molecular weight 44.01 g/mol)",
        uncertainty=0.5,
        version="1.0.0",
        verification_status="Thermodynamic Standard",
    ),
    "nominal_gale_surface_pressure": PhysicsParameter(
        id="nominal_gale_surface_pressure",
        name="Gale Crater Floor Nominal Surface Pressure",
        value=750.0,
        units="Pa",
        source="MSL REMS In-Situ Environmental Measurements (Haberle et al., 2014)",
        source_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html",
        validity_range=[650.0, 950.0],
        applicable_conditions="Gale Crater floor (~ -4.5 km MOLA elevation)",
        uncertainty=20.0,
        version="1.0.0",
        verification_status="MSL Mission Measurement",
    ),
    "nominal_gale_surface_temp": PhysicsParameter(
        id="nominal_gale_surface_temp",
        name="Gale Crater Mean Ambient Surface Temperature",
        value=215.0,
        units="K",
        source="MSL REMS Ground and Air Temperature Telemetry",
        source_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html",
        validity_range=[180.0, 275.0],
        applicable_conditions="Diurnal mean at Gale Crater",
        uncertainty=5.0,
        version="1.0.0",
        verification_status="MSL Mission Measurement",
    ),
    "nominal_gcr_dose_rate": PhysicsParameter(
        id="nominal_gcr_dose_rate",
        name="Galactic Cosmic Ray Surface Dose Rate (Quiet Solar Period)",
        value=0.21,
        units="mSv/day",
        source="MSL RAD Surface Dosimetry (Hassler et al., Science 2014)",
        source_url="https://pds-ppi.igpp.ucla.edu/",
        validity_range=[0.18, 0.35],
        applicable_conditions="Surface ambient, solar minimum quiet conditions",
        uncertainty=0.03,
        version="1.0.0",
        verification_status="MSL RAD Peer-Reviewed",
    ),
}


def get_parameter(param_id: str) -> Optional[PhysicsParameter]:
    """Retrieve a traceable parameter by its identifier."""
    return _REGISTRY.get(param_id)


def list_parameters() -> Dict[str, PhysicsParameter]:
    """List all registered parameters."""
    return _REGISTRY.copy()
