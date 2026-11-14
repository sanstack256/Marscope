"""
MARSCOPE Documented Planetary Coordinate Association Service
Martian Surface Intelligence & Exploration System

Resolves observation coordinates strictly through traceable planetary mechanisms:
  1. Explicit verified planetary latitude/longitude from PDS labels or source tables.
  2. Documented planar metric conversion (Gale Crater IAU2000 Equirectangular Easting_m/Northing_m).
  3. Official NASA/JPL MSL Rover Waypoints RMC (Site, Drive) localization lookup.

Never assigns hardcoded Gale Crater fallback coordinates to unlocated products.
"""

import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field
from pyproj import CRS, Transformer
from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, validate_mars_coordinates


# Authoritative JPL/MMGIS MSL Gale Crater Equirectangular projection (R = 3396190.0 m at equator)
GALE_EQC_PROJ4 = "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=3396190.0 +units=m +no_defs"
IAU2000_LONGLAT_PROJ4 = "+proj=longlat +a=3396190 +b=3376200 +no_defs"

_EQC_TO_LONGLAT = Transformer.from_crs(
    CRS.from_proj4(GALE_EQC_PROJ4),
    CRS.from_proj4("+proj=longlat +R=3396190.0 +no_defs"),
    always_xy=True,
)

# Documented MSL PDS filename patterns carrying Rover Motion Counter (Site, Drive):
#   ChemCam: CL[1|5]_<SCLK><PROD>_F<SSS><DDDD><SEQ> -> F0030004 => site=3, drive=4
_CHEMCAM_F_RMC_RE = re.compile(r"_F(\d{3})(\d{4})[A-Z]", re.IGNORECASE)
#   CheMin: CM[A|B]_<SCLK>MIN<SOL4><SITE3><DRIVE4>CH... -> MIN00790050104 => sol=79, site=5, drive=104
_CHEMIN_MIN_RMC_RE = re.compile(r"MIN(\d{4})(\d{3})(\d{4})CH", re.IGNORECASE)


class AssociatedCoordinates(BaseModel):
    latitude: float
    longitude: float
    elevation_m: Optional[float] = None
    easting_m: Optional[float] = None
    northing_m: Optional[float] = None
    crs: str = "IAU2000:49900"
    latitude_convention: str = "Planetocentric"
    longitude_direction: str = "East"
    rmc_key: Optional[str] = None
    coordinate_source: str = Field(..., description="Traceable association mechanism ID")
    coordinate_provenance: str = Field(..., description="Human-readable provenance record")
    coordinate_uncertainty_m: Optional[float] = Field(
        None, description="Estimated horizontal positional uncertainty in meters (e.g., rover station vs mast standoff)"
    )


def gale_eqc_meters_to_lat_lon(easting_m: float, northing_m: float) -> Tuple[float, float]:
    """
    Convert JPL/MMGIS MSL Gale Crater Equirectangular planar coordinates (easting_m, northing_m)
    into IAU2000 East-positive Planetocentric (latitude, longitude) degrees.
    """
    if not (math.isfinite(easting_m) and math.isfinite(northing_m)):
        raise ValueError("Easting and Northing must be finite numbers.")
    lon_deg, lat_deg = _EQC_TO_LONGLAT.transform(easting_m, northing_m)
    return validate_mars_coordinates(lat_deg, lon_deg, "Planetocentric", "East")


def extract_site_drive_from_product_name(product_name: str) -> Optional[Tuple[int, int, str]]:
    """
    Extract (site, drive, documented_rule) from official MSL PDS3 product filenames when
    external label ROVER_MOTION_COUNTER is absent in a summary table (e.g., ChemCam MOC).
    Returns None if pattern does not strictly match documented MSL SIS conventions.
    """
    if not product_name:
        return None
    m_cc = _CHEMCAM_F_RMC_RE.search(product_name)
    if m_cc:
        return int(m_cc.group(1)), int(m_cc.group(2)), "msl_chemcam_sis_F_site3_drive4"

    m_cm = _CHEMIN_MIN_RMC_RE.search(product_name)
    if m_cm:
        return int(m_cm.group(2)), int(m_cm.group(3)), "msl_chemin_sis_MIN_sol4_site3_drive4"

    return None


class CoordinateAssociationService:
    """
    Loads official NASA/JPL MSL rover waypoint tables (indexed by RMC site_drive and sol)
    and resolves verified spatial coordinates without inventing default positions.
    """

    def __init__(self, waypoints_path: Optional[Path] = None):
        self.waypoints_path = waypoints_path
        self._by_rmc: Dict[str, Dict[str, Any]] = {}
        self._source_label: str = "unavailable"
        if waypoints_path is not None and waypoints_path.exists():
            self.load_waypoints_geojson(waypoints_path)

    def load_waypoints_geojson(self, geojson_path: Path) -> int:
        """Load NASA/JPL MMGIS MSL_waypoints.json GeoJSON features indexed by RMC (site_drive)."""
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        loaded: Dict[str, Dict[str, Any]] = {}
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            rmc = props.get("RMC")
            if not rmc and props.get("site") is not None and props.get("drive") is not None:
                rmc = f"{int(props['site'])}_{int(props['drive'])}"
            lat = props.get("lat") if props.get("lat") is not None else (coords[1] if len(coords) >= 2 else None)
            lon = props.get("lon") if props.get("lon") is not None else (coords[0] if len(coords) >= 2 else None)
            elev = props.get("elev_geoid") if props.get("elev_geoid") is not None else (
                coords[2] if len(coords) >= 3 else None
            )
            if rmc and lat is not None and lon is not None:
                loaded[str(rmc)] = {
                    "rmc": str(rmc),
                    "site": props.get("site"),
                    "drive": props.get("drive"),
                    "sol": props.get("sol"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "elev_geoid": float(elev) if elev is not None else None,
                    "easting": float(props["easting"]) if props.get("easting") is not None else None,
                    "northing": float(props["northing"]) if props.get("northing") is not None else None,
                }
        self._by_rmc = loaded
        self.waypoints_path = geojson_path
        self._source_label = f"jpl_msl_waypoints:{geojson_path.name}"
        return len(self._by_rmc)

    @property
    def is_waypoints_loaded(self) -> bool:
        return len(self._by_rmc) > 0

    @property
    def waypoint_count(self) -> int:
        return len(self._by_rmc)

    def resolve_from_rmc(
        self,
        site: Optional[int],
        drive: Optional[int],
        uncertainty_m: Optional[float] = 10.0,
        rmc_source: str = "pds3_label_rover_motion_counter",
    ) -> Optional[AssociatedCoordinates]:
        """Resolve verified rover localization coordinates by (Site, Drive) RMC key."""
        if site is None or drive is None:
            return None
        key = f"{int(site)}_{int(drive)}"
        wp = self._by_rmc.get(key)
        if not wp:
            return None
        lat, lon = validate_mars_coordinates(wp["lat"], wp["lon"], "Planetocentric", "East")
        return AssociatedCoordinates(
            latitude=lat,
            longitude=lon,
            elevation_m=wp.get("elev_geoid"),
            easting_m=wp.get("easting"),
            northing_m=wp.get("northing"),
            crs="IAU2000:49900",
            latitude_convention="Planetocentric",
            longitude_direction="East",
            rmc_key=key,
            coordinate_source=f"{self._source_label}+{rmc_source}",
            coordinate_provenance=(
                f"Matched MSL RMC Site={site}, Drive={drive} against official JPL Curiosity traverse "
                f"waypoints ({self._source_label}); mast/arm target offset represented by ±{uncertainty_m or 10.0:.1f} m uncertainty."
            ),
            coordinate_uncertainty_m=uncertainty_m,
        )

    def resolve_from_pds_metadata(
        self,
        pds_meta: Optional[Dict[str, Any]] = None,
        product_id: Optional[str] = None,
        uncertainty_m: Optional[float] = 10.0,
    ) -> Optional[AssociatedCoordinates]:
        """
        Attempt coordinate association from explicit PDS label fields first, then ROVER_MOTION_COUNTER
        against JPL waypoints, then documented filename RMC token. Returns None when unlocated.
        """
        if pds_meta:
            rmc = pds_meta.get("rover_motion_counter") or {}
            if rmc.get("site") is not None and rmc.get("drive") is not None:
                res = self.resolve_from_rmc(
                    rmc["site"],
                    rmc["drive"],
                    uncertainty_m=uncertainty_m,
                    rmc_source="pds3_label_rover_motion_counter",
                )
                if res:
                    return res

        if product_id:
            parsed_fn = extract_site_drive_from_product_name(product_id)
            if parsed_fn:
                site, drive, rule = parsed_fn
                return self.resolve_from_rmc(
                    site,
                    drive,
                    uncertainty_m=uncertainty_m,
                    rmc_source=rule,
                )
        return None
