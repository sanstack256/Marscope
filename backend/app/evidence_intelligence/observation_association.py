"""
MARSCOPE Corridor Observation Association
Martian Surface Intelligence & Exploration System

Uses Shapely STRtree spatial indexing against complete segment LineString and
corridor Polygon geometries in a local Mars Equirectangular metric frame.
Supports point coordinates and spatial footprints, classifies association type
and spatial reference validity honestly, verifies local product availability
(never silently assuming product_available=True), and strictly isolates
Perseverance / Jezero sources from Gale Crater / Mount Sharp studies.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from app.evidence_intelligence.corridor import MarsLocalFrame
from app.evidence_intelligence.schemas import (
    AssociatedObservation,
    CorridorSegmentAssessment,
    ObservationAssociationType,
    ProductAvailabilityStatus,
)
from app.geospatial.crs import normalize_longitude_360, validate_mars_crs
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


def _verify_product_availability(
    record: Dict[str, Any], raw_dir: Optional[Path] = None
) -> Tuple[ProductAvailabilityStatus, bool, str]:
    """
    Strictly verify actual product availability instead of defaulting to True.
    Checks local file existence first; otherwise flags remote URLs as URL_UNVERIFIED
    or missing products as MISSING.
    """
    if record.get("access_denied"):
        return ProductAvailabilityStatus.ACCESS_DENIED, False, "Archive reported access denied."
    if record.get("archive_unavailable"):
        return ProductAvailabilityStatus.ARCHIVE_UNAVAILABLE, False, "Source archive endpoint unavailable."

    for key in ("local_path", "local_file_path", "raw_path", "file_path"):
        val = record.get(key)
        if val:
            p = Path(str(val))
            if not p.is_absolute() and raw_dir is not None:
                p = raw_dir / p
            if p.exists() and p.is_file():
                return (
                    ProductAvailabilityStatus.VERIFIED_LOCAL,
                    True,
                    f"Verified local file at {p.name} ({p.stat().st_size} bytes).",
                )
            return (
                ProductAvailabilityStatus.MISSING,
                False,
                f"Catalogued local path missing on disk: {val}",
            )

    if record.get("verified_remote") is True:
        return ProductAvailabilityStatus.VERIFIED_REMOTE, True, "Remote archive HTTP verification confirmed."

    url = (
        record.get("url")
        or record.get("source_url")
        or record.get("download_url")
        or record.get("archive_url")
    )
    if url:
        return (
            ProductAvailabilityStatus.URL_UNVERIFIED,
            False,
            "Remote URL catalogued; live download/HEAD verification not yet performed.",
        )

    source_file = str(record.get("source_file") or "")
    if raw_dir is not None and source_file:
        for candidate in raw_dir.rglob(Path(source_file).name):
            if candidate.is_file():
                return (
                    ProductAvailabilityStatus.VERIFIED_LOCAL,
                    True,
                    f"Verified local PDS product file {candidate.name}.",
                )

    return (
        ProductAvailabilityStatus.MISSING,
        False,
        "No verified local file or validated remote product reference available.",
    )


def _extract_observation_geometry(
    rec: Dict[str, Any], frame: MarsLocalFrame
) -> Tuple[Optional[Any], Optional[float], Optional[float], Optional[Dict[str, Any]], bool]:
    """
    Build metric Shapely geometry from footprint GeoJSON / bbox or (lat, lon_east).
    Returns (geom_metric, rep_lat, rep_lon_east, footprint_geojson, coords_valid).
    """
    # Optional explicit CRS validation
    crs_tag = rec.get("crs") or rec.get("spatial_reference")
    if crs_tag and not validate_mars_crs(str(crs_tag)):
        return None, None, None, None, False

    fp_geo = rec.get("footprint_geometry")
    if isinstance(fp_geo, dict) and fp_geo.get("type"):
        try:
            g_ll = shape(fp_geo)
            if not g_ll.is_empty and g_ll.is_valid:
                g_m = frame.to_metric_geom(g_ll)
                c = g_ll.centroid
                return g_m, float(c.y), normalize_longitude_360(float(c.x)), fp_geo, True
        except Exception:
            pass

    sf = rec.get("spatial_footprint")
    if isinstance(sf, dict) and all(
        sf.get(k) is not None for k in ("min_lat", "max_lat", "min_lon", "max_lon")
    ):
        try:
            min_lat = float(sf["min_lat"])
            max_lat = float(sf["max_lat"])
            min_lon = float(sf["min_lon"])
            max_lon = float(sf["max_lon"])
            if all(math.isfinite(x) for x in (min_lat, max_lat, min_lon, max_lon)):
                b_ll = box(min_lon, min_lat, max_lon, max_lat)
                g_m = frame.to_metric_geom(b_ll)
                return (
                    g_m,
                    0.5 * (min_lat + max_lat),
                    normalize_longitude_360(0.5 * (min_lon + max_lon)),
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [normalize_longitude_360(min_lon), min_lat],
                                [normalize_longitude_360(max_lon), min_lat],
                                [normalize_longitude_360(max_lon), max_lat],
                                [normalize_longitude_360(min_lon), max_lat],
                                [normalize_longitude_360(min_lon), min_lat],
                            ]
                        ],
                    },
                    True,
                )
        except (TypeError, ValueError):
            pass

    lat = rec.get("latitude") if rec.get("latitude") is not None else rec.get("lat")
    lon = (
        rec.get("longitude_east")
        if rec.get("longitude_east") is not None
        else (
            rec.get("lon_east")
            if rec.get("lon_east") is not None
            else (rec.get("longitude") if rec.get("longitude") is not None else rec.get("lon"))
        )
    )
    if lat is None or lon is None:
        return None, None, None, None, False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None, None, None, None, False
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)) or not (-90.0 <= lat_f <= 90.0):
        return None, None, None, None, False

    lon_norm = normalize_longitude_360(lon_f)
    px, py = frame.to_metric(lon_norm, lat_f)
    return Point(px, py), lat_f, lon_norm, None, True


def associate_corridor_observations(
    *,
    observations_raw: List[Dict[str, Any]],
    imagery_records: Optional[List[Dict[str, Any]]] = None,
    segments: List[CorridorSegmentAssessment],
    search_radius_m: float,
    study_region: str = "Gale Crater / Mount Sharp",
    corridor_width_m: float = 60.0,
    raw_dir: Optional[Path] = None,
    include_unlocated_diagnostics: bool = False,
) -> List[AssociatedObservation]:
    """
    Associate verified mission observations and imagery records against full segment
    LineString and Corridor Polygon geometries using Shapely STRtree indexing.
    """
    if not segments:
        return []

    is_gale_study = "gale" in study_region.lower() or "mount sharp" in study_region.lower()
    mean_lat = sum(0.5 * (s.start_coord.lat + s.end_coord.lat) for s in segments) / len(segments)
    mean_lon = sum(0.5 * (s.start_coord.lon_east + s.end_coord.lon_east) for s in segments) / len(segments)
    frame = MarsLocalFrame(mean_lat, mean_lon)

    seg_lines_m: List[LineString] = []
    seg_polys_m: List[Polygon] = []
    seg_ids: List[str] = []
    half_w = 0.5 * float(corridor_width_m)

    for seg in segments:
        if seg.vertices and len(seg.vertices) >= 2:
            line = LineString([frame.to_metric(v.lon_east, v.lat) for v in seg.vertices])
        else:
            line = LineString(
                [
                    frame.to_metric(seg.start_coord.lon_east, seg.start_coord.lat),
                    frame.to_metric(seg.end_coord.lon_east, seg.end_coord.lat),
                ]
            )
        if seg.corridor_polygon and len(seg.corridor_polygon) >= 4:
            poly = frame.to_metric_geom(Polygon(seg.corridor_polygon))
        else:
            poly = line.buffer(half_w, quad_segs=8, cap_style="round", join_style="round")
        seg_lines_m.append(line)
        seg_polys_m.append(poly)
        seg_ids.append(seg.segment_id)

    line_tree = STRtree(seg_lines_m)
    corridor_union_m = unary_union(seg_polys_m)

    associated: List[AssociatedObservation] = []
    seen_ids = set()

    def _process_record(rec: Dict[str, Any], default_mission: str, default_mtype: str, prefix: str) -> None:
        mission = str(rec.get("mission") or default_mission)
        instrument = str(rec.get("instrument") or "UNKNOWN")
        product_id = str(rec.get("source_file") or rec.get("product_id") or rec.get("id") or "UNSPECIFIED")
        if is_gale_study and (
            _is_jezero_or_perseverance(mission) or _is_jezero_or_perseverance(product_id)
        ):
            return

        crs_tag = rec.get("crs") or rec.get("spatial_reference")
        if crs_tag and not validate_mars_crs(str(crs_tag)):
            if include_unlocated_diagnostics:
                avail_st, avail_bool, avail_note = _verify_product_availability(rec, raw_dir)
                associated.append(
                    AssociatedObservation(
                        observation_id=str(rec.get("observation_id") or f"{prefix}-crs-{len(associated)}"),
                        mission=mission,
                        instrument=instrument,
                        product_id=product_id,
                        association_type=ObservationAssociationType.SPATIAL_REFERENCE_UNVERIFIED,
                        measurement_type=str(rec.get("measurement_type") or default_mtype),
                        availability_status=avail_st,
                        product_available=avail_bool,
                        availability_check_note=avail_note,
                        spatial_reference_verified=False,
                        spatial_association_note=f"Excluded from spatial matching: unverified non-Mars CRS '{crs_tag}'.",
                    )
                )
            return

        geom_m, lat_f, lon_f, fp_geo, coords_ok = _extract_observation_geometry(rec, frame)
        if not coords_ok or geom_m is None or lat_f is None or lon_f is None:
            if include_unlocated_diagnostics:
                avail_st, avail_bool, avail_note = _verify_product_availability(rec, raw_dir)
                associated.append(
                    AssociatedObservation(
                        observation_id=str(rec.get("observation_id") or f"{prefix}-unloc-{len(associated)}"),
                        mission=mission,
                        instrument=instrument,
                        product_id=product_id,
                        association_type=ObservationAssociationType.UNLOCATED,
                        measurement_type=str(rec.get("measurement_type") or default_mtype),
                        availability_status=avail_st,
                        product_available=avail_bool,
                        availability_check_note=avail_note,
                        spatial_association_note="Missing or non-finite coordinates; not invented.",
                    )
                )
            return

        nearest_idx = int(line_tree.nearest(geom_m))
        seg_id = seg_ids[nearest_idx]
        dist_route_m = float(seg_lines_m[nearest_idx].distance(geom_m))
        dist_corridor_m = float(corridor_union_m.distance(geom_m))

        if dist_route_m > search_radius_m and dist_corridor_m > search_radius_m:
            return

        if dist_route_m <= 1.0:
            assoc_type = ObservationAssociationType.INTERSECTS_ROUTE
        elif dist_corridor_m <= 1e-6:
            assoc_type = ObservationAssociationType.INTERSECTS_CORRIDOR
        else:
            assoc_type = ObservationAssociationType.NEAR_CORRIDOR

        obs_id = str(
            rec.get("observation_id")
            or f"{prefix}-{hashlib.sha256(f'{mission}:{instrument}:{product_id}:{lat_f:.6f}:{lon_f:.6f}'.encode()).hexdigest()[:10]}"
        )
        if obs_id in seen_ids:
            return
        seen_ids.add(obs_id)

        avail_st, avail_bool, avail_note = _verify_product_availability(rec, raw_dir)
        coord_unc = rec.get("coordinate_uncertainty_m")
        is_pano = bool(rec.get("is_panorama", False)) or (
            "pano" in str(rec.get("title") or "").lower()
            or "mosaic" in str(rec.get("title") or "").lower()
        )
        mtype = str(rec.get("measurement_type") or rec.get("observation_type") or default_mtype)

        from app.science.rover_association import evaluate_rover_orbital_association

        seg_obj = next((s for s in segments if s.segment_id == seg_id), None)
        feat_lat = seg_obj.start_coord.lat if seg_obj is not None else lat_f
        feat_lon = seg_obj.start_coord.lon_east if seg_obj is not None else lon_f
        rover_assoc = evaluate_rover_orbital_association(
            observation=rec,
            feature_lat=feat_lat,
            feature_lon_east=feat_lon,
            orbital_dataset_id="route_corridor_dem",
            orbital_product_id="CORRIDOR_ORBITAL_DEM",
            orbital_pixel_footprint_m=float(rec.get("orbital_pixel_footprint_m") or 1.0117),
            orbital_crs=str(rec.get("crs") or "IAU2000:49900"),
            feature_id=seg_id,
        )

        associated.append(
            AssociatedObservation(
                observation_id=obs_id,
                mission=mission,
                instrument=instrument,
                sol=int(rec["sol"]) if rec.get("sol") is not None else None,
                observation_time=rec.get("observation_time") or rec.get("utc_time") or rec.get("captured_at"),
                latitude=round(lat_f, 6),
                longitude_east=round(lon_f, 6),
                coordinate_uncertainty_m=float(coord_unc) if coord_unc is not None else None,
                product_id=product_id,
                distance_from_route_m=round(dist_route_m, 2),
                distance_from_corridor_m=round(dist_corridor_m, 2),
                association_type=assoc_type,
                nearest_segment_id=seg_id,
                spatial_footprint=rec.get("spatial_footprint") if isinstance(rec.get("spatial_footprint"), dict) else None,
                footprint_geometry=fp_geo,
                processing_level=rec.get("processing_level"),
                measurement_type=mtype,
                availability_status=avail_st,
                product_available=avail_bool,
                availability_check_note=avail_note,
                spatial_reference_verified=True,
                is_panorama=is_pano,
                panorama_metadata=rec.get("panorama_metadata") or (rec if is_pano else None),
                classification=ScientificDataClassification.DIRECTLY_MEASURED,
                rover_association_state=rover_assoc.association_state.value,
                location_semantic_type=rover_assoc.location_semantic_type,
                scale_disparity_ratio=rover_assoc.scale_disparity_ratio,
                scale_disparity_statement=rover_assoc.scale_disparity_statement,
                confirms_entire_orbital_pixel=rover_assoc.confirms_entire_orbital_pixel,
                spatial_association_note=(
                    f"{assoc_type.value} ({rover_assoc.association_state.value}): {mission} ({instrument}) at {dist_route_m:.1f} m from route "
                    f"(corridor distance {dist_corridor_m:.1f} m) near {seg_id}; {rover_assoc.scale_disparity_statement}"
                ),
            )
        )

    for obs in observations_raw:
        _process_record(obs, "MSL Curiosity", "rover_science_record", "obs")

    for rec in imagery_records or []:
        _process_record(rec, "MSL Curiosity", "surface_imagery_record", "img")

    associated.sort(key=lambda o: o.distance_from_route_m if o.distance_from_route_m is not None else 1e9)

    seg_map = {s.segment_id: s for s in segments}
    for obs in associated:
        if (
            obs.association_type
            in (
                ObservationAssociationType.INTERSECTS_ROUTE,
                ObservationAssociationType.INTERSECTS_CORRIDOR,
                ObservationAssociationType.NEAR_CORRIDOR,
            )
            and obs.nearest_segment_id
            and obs.nearest_segment_id in seg_map
        ):
            seg = seg_map[obs.nearest_segment_id]
            seg.associated_observation_ids.append(obs.observation_id)
            seg.coverage.rover_observation_count += 1
            if obs.is_panorama:
                seg.coverage.panorama_available = True

    return associated
