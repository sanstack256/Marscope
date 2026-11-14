"""
MARSCOPE Corridor Observation Association
Martian Surface Intelligence & Exploration System

Associates verified Gale / Curiosity rover waypoints and instrument observations
(ChemCam, REMS, APXS, CheMin, Mastcam/Navcam catalog entries) within the
configured search radius of the route corridor. Strictly isolates Jezero /
Perseverance sources so they never leak into Gale Crater / Mount Sharp corridors.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from app.evidence_intelligence.schemas import (
    AssociatedObservation,
    CorridorSegmentAssessment,
)
from app.geospatial.crs import normalize_longitude_360
from app.mobility.terrain_features import mars_great_circle_distance_meters
from app.science.provenance_graph import ScientificDataClassification


def _is_jezero_or_perseverance(text: str) -> bool:
    lower = text.lower()
    return (
        "perseverance" in lower
        or "mars 2020" in lower
        or "mars2020" in lower
        or "jezero" in lower
        or "m20" in lower
    )


def associate_corridor_observations(
    *,
    observations_raw: List[Dict[str, Any]],
    imagery_records: Optional[List[Dict[str, Any]]] = None,
    segments: List[CorridorSegmentAssessment],
    search_radius_m: float,
    study_region: str = "Gale Crater / Mount Sharp",
) -> List[AssociatedObservation]:
    """
    Filter and associate verified mission observations within `search_radius_m`
    of any corridor segment. Never fabricates coordinates or panoramas, and never
    mixes Perseverance / Jezero data into Gale Crater studies.
    """
    if not segments:
        return []

    is_gale_study = "gale" in study_region.lower() or "mount sharp" in study_region.lower()
    associated: List[AssociatedObservation] = []
    seen_ids = set()

    def _nearest_seg_dist(lat: float, lon_east: float) -> Tuple[Optional[str], float]:
        best_id: Optional[str] = None
        best_d = float("inf")
        for seg in segments:
            pts = [
                (seg.start_coord.lat, seg.start_coord.lon_east),
                (
                    0.5 * (seg.start_coord.lat + seg.end_coord.lat),
                    0.5 * (seg.start_coord.lon_east + seg.end_coord.lon_east),
                ),
                (seg.end_coord.lat, seg.end_coord.lon_east),
            ]
            for p_lat, p_lon in pts:
                d = mars_great_circle_distance_meters(lat, lon_east, p_lat, p_lon)
                if d < best_d:
                    best_d = d
                    best_id = seg.segment_id
        return best_id, best_d

    for obs in observations_raw:
        mission = str(obs.get("mission") or "Curiosity")
        instrument = str(obs.get("instrument") or "UNKNOWN")
        product_id = str(obs.get("source_file") or obs.get("product_id") or "UNSPECIFIED")
        if is_gale_study and (
            _is_jezero_or_perseverance(mission) or _is_jezero_or_perseverance(product_id)
        ):
            continue

        lat = obs.get("latitude")
        lon = obs.get("longitude_east") if obs.get("longitude_east") is not None else obs.get("longitude")
        if lat is None or lon is None:
            continue
        lat_f = float(lat)
        lon_f = normalize_longitude_360(float(lon))

        seg_id, dist_m = _nearest_seg_dist(lat_f, lon_f)
        if dist_m > search_radius_m or seg_id is None:
            continue

        obs_id = str(
            obs.get("observation_id")
            or f"obs-{hashlib.sha256(f'{mission}:{instrument}:{product_id}:{lat_f:.6f}:{lon_f:.6f}'.encode()).hexdigest()[:10]}"
        )
        if obs_id in seen_ids:
            continue
        seen_ids.add(obs_id)

        coord_unc = obs.get("coordinate_uncertainty_m")
        item = AssociatedObservation(
            observation_id=obs_id,
            mission=mission,
            instrument=instrument,
            sol=int(obs["sol"]) if obs.get("sol") is not None else None,
            observation_time=obs.get("observation_time") or obs.get("utc_time"),
            latitude=round(lat_f, 6),
            longitude_east=round(lon_f, 6),
            coordinate_uncertainty_m=float(coord_unc) if coord_unc is not None else None,
            product_id=product_id,
            distance_from_route_m=round(dist_m, 2),
            nearest_segment_id=seg_id,
            processing_level=obs.get("processing_level"),
            measurement_type=str(obs.get("measurement_type") or obs.get("observation_type") or "rover_science_record"),
            product_available=True,
            is_panorama=bool(obs.get("is_panorama", False)),
            panorama_metadata=obs.get("panorama_metadata"),
            classification=ScientificDataClassification.DIRECTLY_MEASURED,
            spatial_association_note=(
                f"Verified {mission} ({instrument}) record located {dist_m:.1f} m from segment {seg_id}; "
                "nearby context only, not a direct measurement of the entire corridor surface."
            ),
        )
        associated.append(item)

    # Also check any locally recorded Gale imagery metadata with coordinates
    for rec in imagery_records or []:
        mission = str(rec.get("mission") or "")
        product_id = str(rec.get("product_id") or rec.get("id") or "")
        if is_gale_study and (
            _is_jezero_or_perseverance(mission) or _is_jezero_or_perseverance(product_id)
        ):
            continue
        lat = rec.get("lat") if rec.get("lat") is not None else rec.get("latitude")
        lon = rec.get("lon_east") if rec.get("lon_east") is not None else rec.get("lon")
        if lat is None or lon is None:
            continue
        lat_f = float(lat)
        lon_f = normalize_longitude_360(float(lon))
        seg_id, dist_m = _nearest_seg_dist(lat_f, lon_f)
        if dist_m > search_radius_m or seg_id is None:
            continue
        obs_id = f"img-{hashlib.sha256(f'{product_id}:{lat_f:.6f}:{lon_f:.6f}'.encode()).hexdigest()[:10]}"
        if obs_id in seen_ids:
            continue
        seen_ids.add(obs_id)
        is_pano = "pano" in str(rec.get("title") or "").lower() or "mosaic" in str(rec.get("title") or "").lower()
        associated.append(
            AssociatedObservation(
                observation_id=obs_id,
                mission=mission or "MSL Curiosity",
                instrument=str(rec.get("instrument") or "Mastcam/Navcam"),
                sol=int(rec["sol"]) if rec.get("sol") is not None else None,
                observation_time=rec.get("captured_at"),
                latitude=round(lat_f, 6),
                longitude_east=round(lon_f, 6),
                product_id=product_id or obs_id,
                distance_from_route_m=round(dist_m, 2),
                nearest_segment_id=seg_id,
                measurement_type="surface_imagery_record",
                product_available=bool(rec.get("local_path") or rec.get("url")),
                is_panorama=is_pano,
                panorama_metadata=rec if is_pano else None,
                classification=ScientificDataClassification.DIRECTLY_MEASURED,
                spatial_association_note=(
                    f"Surface imagery record {dist_m:.1f} m from segment {seg_id}; directional context only."
                ),
            )
        )

    associated.sort(key=lambda o: o.distance_from_route_m or 0.0)

    seg_map = {s.segment_id: s for s in segments}
    for obs in associated:
        if obs.nearest_segment_id and obs.nearest_segment_id in seg_map:
            seg = seg_map[obs.nearest_segment_id]
            seg.associated_observation_ids.append(obs.observation_id)
            seg.coverage.rover_observation_count += 1
            if obs.is_panorama:
                seg.coverage.panorama_available = True

    return associated
