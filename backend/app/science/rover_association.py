"""
MARSCOPE Scale-Aware Rover-to-Orbital Spatial Association Engine (Prompt 19 Part 10).

Evaluates spatial associations between in-situ rover observations (MSL Curiosity APXS,
ChemCam LIBS, CheMin XRD, REMS, Mastcam/MAHLI) and orbital features/pixels without
conflating coordinate proximity with physical identity or single-spot confirmation
of coarse orbital pixels.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.geospatial.crs import MARS_MEAN_RADIUS_M, normalize_longitude_360, validate_mars_crs_detailed
from app.geospatial.models import RoverAssociationState
from app.science.provenance_graph import ScientificDataClassification

ROVER_ASSOCIATION_VERSION = "rover_spatial_assoc_v2.0"

_DEFAULT_INSTRUMENT_FOOTPRINTS_M: Dict[str, Optional[float]] = {
    "APXS": 0.017,          # ~1.7 cm contact spectrometer FOV
    "CHEMCAM_LIBS": 0.0005, # ~0.35-0.55 mm LIBS laser spot
    "CHEMIN_XRD": 0.016,    # ~1.6 cm drill bit / scoop sample diameter
    "MAHLI": 0.05,
    "MASTCAM": None,
    "REMS": 1.0,
}


class RoverLocationComponents(BaseModel):
    rover_position: Optional[Dict[str, Optional[float]]] = None     # {"lat": ..., "lon_east": ..., "elev_m": ...}
    camera_pointing: Optional[Dict[str, Optional[float]]] = None    # {"azimuth_deg": ..., "elevation_deg": ...}
    target_location: Optional[Dict[str, Optional[float]]] = None    # {"lat": ..., "lon_east": ...}
    instrument_footprint_m: Optional[float] = None
    sample_location: Optional[Dict[str, Optional[float]]] = None    # {"lat": ..., "lon_east": ..., "location_name": ...}
    effective_reference_point: str  # target_location | sample_location | rover_position | unlocated


class RoverOrbitalAssociationRecord(BaseModel):
    association_version: str = ROVER_ASSOCIATION_VERSION
    observation_id: str
    mission: str
    instrument: str
    product_id: str
    orbital_dataset_id: str
    orbital_product_id: str
    target_or_feature_id: Optional[str] = None
    association_state: RoverAssociationState

    location_components: RoverLocationComponents
    rover_location_provenance: str
    location_semantic_type: str
    rover_localization_uncertainty_m: Optional[float] = None
    orbital_registration_uncertainty_m: Optional[float] = None
    spatial_distance_to_feature_m: Optional[float] = None

    acquisition_sol: Optional[int] = None
    acquisition_time: Optional[str] = None
    instrument_measurement_type: str

    observation_footprint_m: Optional[float] = None
    orbital_pixel_footprint_m: Optional[float] = None
    scale_disparity_ratio: Optional[float] = None
    confirms_entire_orbital_pixel: bool = False
    scale_disparity_statement: str

    limitations: List[str] = Field(default_factory=list)
    classification: ScientificDataClassification = ScientificDataClassification.MARSCOPE_DERIVED


def _haversine_mars_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * MARS_MEAN_RADIUS_M * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def _infer_instrument_key(instrument: str) -> str:
    u = instrument.upper()
    if "APXS" in u:
        return "APXS"
    if "CHEMCAM" in u or "LIBS" in u:
        return "CHEMCAM_LIBS"
    if "CHEMIN" in u or "XRD" in u:
        return "CHEMIN_XRD"
    if "REMS" in u:
        return "REMS"
    if "MAHLI" in u:
        return "MAHLI"
    if "MASTCAM" in u:
        return "MASTCAM"
    return u


def evaluate_rover_orbital_association(
    *,
    observation: Dict[str, Any],
    feature_lat: float,
    feature_lon_east: float,
    orbital_dataset_id: str,
    orbital_product_id: str,
    orbital_pixel_footprint_m: Optional[float],
    orbital_crs: Optional[str] = "IAU2000:49900",
    orbital_registration_uncertainty_m: Optional[float] = None,
    feature_id: Optional[str] = None,
    direct_association_radius_m: float = 15.0,
    regional_context_radius_m: float = 500.0,
) -> RoverOrbitalAssociationRecord:
    """
    Assess scale-aware spatial association between one rover observation and an orbital
    feature/pixel without substituting rover station position for more precise target coordinates.
    """
    obs_id = str(observation.get("observation_id") or observation.get("evidence_id") or "obs_unknown")
    mission = str(observation.get("mission") or "Mars Science Laboratory (MSL)")
    instrument = str(observation.get("instrument") or "UNKNOWN")
    product_id = str(observation.get("product_id") or observation.get("source_file") or "UNSPECIFIED")
    meas_type = str(observation.get("measurement_type") or observation.get("evidence_type") or "unknown")
    inst_key = _infer_instrument_key(instrument)
    inst_fp_m = observation.get("instrument_footprint_m")
    if inst_fp_m is None:
        inst_fp_m = _DEFAULT_INSTRUMENT_FOOTPRINTS_M.get(inst_key)

    crs_tag = observation.get("crs") or observation.get("spatial_reference")
    crs_ok = True
    if crs_tag:
        crs_res = validate_mars_crs_detailed(str(crs_tag))
        crs_ok = crs_res.valid

    # Preserve distinct coordinate semantics: target_location / sample_location / rover_position / camera_pointing
    rover_pos = observation.get("rover_position")
    if rover_pos is None and observation.get("location_semantic_type") in {None, "rover_station_location"}:
        if observation.get("rover_latitude") is not None and observation.get("rover_longitude_east") is not None:
            rover_pos = {
                "lat": float(observation["rover_latitude"]),
                "lon_east": normalize_longitude_360(float(observation["rover_longitude_east"])),
            }
        elif observation.get("latitude") is not None and observation.get("longitude_east") is not None and observation.get("location_semantic_type") == "rover_station_location":
            rover_pos = {
                "lat": float(observation["latitude"]),
                "lon_east": normalize_longitude_360(float(observation["longitude_east"])),
            }

    target_loc = observation.get("target_location")
    if target_loc is None and observation.get("location_semantic_type") == "instrument_target_location":
        if observation.get("latitude") is not None and observation.get("longitude_east") is not None:
            target_loc = {
                "lat": float(observation["latitude"]),
                "lon_east": normalize_longitude_360(float(observation["longitude_east"])),
            }

    sample_loc = observation.get("sample_location")
    if sample_loc is None and observation.get("location_semantic_type") == "sample_collection_site":
        if observation.get("latitude") is not None and observation.get("longitude_east") is not None:
            sample_loc = {
                "lat": float(observation["latitude"]),
                "lon_east": normalize_longitude_360(float(observation["longitude_east"])),
            }

    cam_pointing = observation.get("camera_pointing")

    # Never substitute rover position when target_location or sample_location is available!
    if target_loc and target_loc.get("lat") is not None and target_loc.get("lon_east") is not None:
        eff_lat = float(target_loc["lat"])
        eff_lon = normalize_longitude_360(float(target_loc["lon_east"]))
        eff_kind = "target_location"
        loc_sem = "instrument_target_location"
    elif sample_loc and sample_loc.get("lat") is not None and sample_loc.get("lon_east") is not None:
        eff_lat = float(sample_loc["lat"])
        eff_lon = normalize_longitude_360(float(sample_loc["lon_east"]))
        eff_kind = "sample_location"
        loc_sem = "sample_collection_site"
    elif rover_pos and rover_pos.get("lat") is not None and rover_pos.get("lon_east") is not None:
        eff_lat = float(rover_pos["lat"])
        eff_lon = normalize_longitude_360(float(rover_pos["lon_east"]))
        eff_kind = "rover_position"
        loc_sem = "rover_station_location"
    elif observation.get("latitude") is not None and observation.get("longitude_east") is not None:
        eff_lat = float(observation["latitude"])
        eff_lon = normalize_longitude_360(float(observation["longitude_east"]))
        eff_kind = "rover_position"
        loc_sem = str(observation.get("location_semantic_type") or "rover_station_location")
    else:
        eff_lat = None
        eff_lon = None
        eff_kind = "unlocated"
        loc_sem = "unlocated"

    components = RoverLocationComponents(
        rover_position=rover_pos,
        camera_pointing=cam_pointing,
        target_location=target_loc,
        instrument_footprint_m=inst_fp_m,
        sample_location=sample_loc,
        effective_reference_point=eff_kind,
    )

    rover_unc_m = (
        float(observation["coordinate_uncertainty_m"])
        if observation.get("coordinate_uncertainty_m") is not None
        else None
    )
    standoff_m = (
        float(observation["instrument_standoff_m"])
        if observation.get("instrument_standoff_m") is not None
        else None
    )
    prov = str(observation.get("coordinate_source") or observation.get("coordinate_provenance") or "unverified_provenance")

    # Scale disparity math
    scale_ratio: Optional[float] = None
    if orbital_pixel_footprint_m is not None and inst_fp_m is not None and inst_fp_m > 0:
        scale_ratio = round(orbital_pixel_footprint_m / inst_fp_m, 1)

    if scale_ratio is not None and scale_ratio > 20.0:
        scale_stmt = (
            f"Scale disparity {scale_ratio:,.1f}x: single in-situ {inst_key} spot (~{inst_fp_m * 1000:.1f} mm) "
            f"samples a minute fraction of one {orbital_pixel_footprint_m:.2f} m orbital pixel and does NOT confirm "
            "mineralogical or elemental uniformity across the entire orbital pixel."
        )
    elif orbital_pixel_footprint_m is not None:
        scale_stmt = f"Orbital pixel size {orbital_pixel_footprint_m:.2f} m compared against rover observation."
    else:
        scale_stmt = "Orbital pixel footprint unspecified."

    limitations: List[str] = []
    if eff_kind == "rover_position" and standoff_m is not None:
        limitations.append(
            f"Using rover station location; instrument target lies ~{standoff_m:.2f} m away along unrecorded/partial pointing."
        )
    if rover_unc_m is None:
        limitations.append("Rover horizontal localization uncertainty is unreported in source metadata.")
    if orbital_registration_uncertainty_m is None:
        limitations.append("Orbital map registration 1-sigma uncertainty is unquantified in source label.")

    if not crs_ok or (orbital_crs and not validate_mars_crs_detailed(orbital_crs).valid):
        state = RoverAssociationState.LOCATION_UNVERIFIED
        dist_m = None
        limitations.append("Unverified or incompatible planetary coordinate system prevents spatial association.")
    elif eff_lat is None or eff_lon is None:
        state = RoverAssociationState.LOCATION_UNVERIFIED
        dist_m = None
        limitations.append("Observation lacks verified planetocentric coordinates (UNLOCATED).")
    elif prov == "unverified_provenance" and not observation.get("rmc_key") and eff_kind == "rover_position":
        state = RoverAssociationState.INSUFFICIENT_METADATA
        dist_m = round(_haversine_mars_m(eff_lat, eff_lon, feature_lat, normalize_longitude_360(feature_lon_east)), 2)
        limitations.append("Coordinate provenance / RMC metadata insufficient for rigorous co-location.")
    else:
        dist_m = round(_haversine_mars_m(eff_lat, eff_lon, feature_lat, normalize_longitude_360(feature_lon_east)), 2)
        combined_unc = (rover_unc_m or 0.0) + (orbital_registration_uncertainty_m or 0.0) + (standoff_m or 0.0)
        # Scale incompatibility gate when coarse orbital pixel (> 20 m) is queried as direct match for mm-cm rover spot!
        if dist_m > regional_context_radius_m:
            state = RoverAssociationState.NOT_ASSOCIATED
        elif scale_ratio is not None and orbital_pixel_footprint_m is not None and orbital_pixel_footprint_m > 20.0:
            state = RoverAssociationState.SCALE_INCOMPATIBLE if dist_m <= direct_association_radius_m + orbital_pixel_footprint_m else RoverAssociationState.REGIONAL_CONTEXT_ONLY
        elif dist_m <= direct_association_radius_m:
            if rover_unc_m is None or orbital_registration_uncertainty_m is None or eff_kind == "rover_position":
                state = RoverAssociationState.ASSOCIATED_WITH_UNCERTAINTY
                if scale_ratio and scale_ratio > 20.0:
                    limitations.append(scale_stmt)
            else:
                state = RoverAssociationState.DIRECT_SPATIAL_ASSOCIATION
                if scale_ratio and scale_ratio > 2.0:
                    limitations.append(scale_stmt)
        elif dist_m <= direct_association_radius_m + max(25.0, combined_unc):
            state = RoverAssociationState.ASSOCIATED_WITH_UNCERTAINTY
        else:
            state = RoverAssociationState.REGIONAL_CONTEXT_ONLY

    return RoverOrbitalAssociationRecord(
        observation_id=obs_id,
        mission=mission,
        instrument=instrument,
        product_id=product_id,
        orbital_dataset_id=orbital_dataset_id,
        orbital_product_id=orbital_product_id,
        target_or_feature_id=feature_id,
        association_state=state,
        location_components=components,
        rover_location_provenance=prov,
        location_semantic_type=loc_sem,
        rover_localization_uncertainty_m=rover_unc_m,
        orbital_registration_uncertainty_m=orbital_registration_uncertainty_m,
        spatial_distance_to_feature_m=dist_m,
        acquisition_sol=observation.get("sol") or observation.get("observation_sol"),
        acquisition_time=observation.get("observation_time"),
        instrument_measurement_type=meas_type,
        observation_footprint_m=inst_fp_m,
        orbital_pixel_footprint_m=orbital_pixel_footprint_m,
        scale_disparity_ratio=scale_ratio,
        confirms_entire_orbital_pixel=bool(scale_ratio is not None and scale_ratio <= 2.0 and state == RoverAssociationState.DIRECT_SPATIAL_ASSOCIATION),
        scale_disparity_statement=scale_stmt,
        limitations=list(dict.fromkeys(limitations)),
    )
