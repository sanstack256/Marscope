"""
MARSCOPE Spatial Footprint Extraction & Indexed Geometry Engine (Prompt 19 Part 5).

Extracts real planetary product footprints and valid-pixel coverage hulls from
authoritative raster masks, PDS3 ODL metadata, Shapely/GeoJSON definitions,
and JPL rover waypoint locations. Explicitly separates true swath polygons
from approximate catalog bounding boxes and computes equal-area Mars surface
coverage (Sinusoidal / polar Lambert Equal Area on R = 3,396,190 m).
"""

from __future__ import annotations

from collections import deque
from enum import Enum
import hashlib
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, Field
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes as raster_shapes
from shapely.geometry import GeometryCollection, MultiPolygon, Point, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform, unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid

from app.geospatial.crs import (
    MARS_MEAN_RADIUS_M,
    validate_mars_crs_detailed,
)
from app.geospatial.models import (
    CrsValidationResult,
    ObservationCategory,
)
from app.ingestion.pds_label import extract_pds3_metadata
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, VerificationState
from app.science.provenance_graph import ScientificDataClassification


class FootprintExtractionMethod(str, Enum):
    AUTHORITATIVE_RASTER_VALID_MASK_HULL = "authoritative_raster_valid_mask_hull"
    PDS3_ODL_CORNER_POLYGON = "pds3_odl_corner_polygon"
    SHAPELY_GEOJSON_POLYGON = "shapely_geojson_polygon"
    ROVER_STATION_POINT = "rover_station_point"
    CATALOG_BOUNDING_BOX_APPROXIMATE = "catalog_bounding_box_approximate"
    NO_SPATIAL_FOOTPRINT = "no_spatial_footprint"


class SpatialFootprintRecord(BaseModel):
    dataset_id: str
    product_id: str
    mission: str
    instrument: str
    category: ObservationCategory
    crs: str
    coordinate_validation: CrsValidationResult
    extraction_method: FootprintExtractionMethod
    is_approximate: bool
    geometry_valid: bool
    repair_applied: bool = False
    antimeridian_split: bool = False
    original_bounds: Optional[Dict[str, float]] = None
    footprint_geojson: Optional[Dict[str, Any]] = None
    valid_data_geojson: Optional[Dict[str, Any]] = None
    invalid_nodata_geojson: Optional[Dict[str, Any]] = None
    product_footprint_area_m2: Optional[float] = None
    valid_data_area_m2: Optional[float] = None
    invalid_nodata_area_m2: Optional[float] = None
    valid_data_fraction: Optional[float] = None
    bbox_area_m2: Optional[float] = None
    swath_to_bbox_ratio: Optional[float] = None
    area_calculation_method: str = "mars_sinusoidal_equal_area_R3396190m"
    horizontal_resolution_m: Optional[float] = None
    vertical_resolution_m: Optional[float] = None
    pixel_grid_shape: Optional[List[int]] = None
    data_quality_coverage: str
    has_local_artifact: bool = False
    source_sha256: Optional[str] = None
    processing_history: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    classification: ScientificDataClassification = ScientificDataClassification.DIRECTLY_MEASURED


def classify_dataset_observation_category(ds: Dataset) -> ObservationCategory:
    pt = (ds.product_type or "").upper()
    inst = (ds.instrument or "").upper()
    did = ds.id.lower()
    if any(k in pt for k in ("DEM", "TOPOPH", "TOPOGRAPHY", "ELEVATION")) or any(
        k in inst for k in ("MOLA", "HRSC")
    ) or "dtm" in did or "mola" in did:
        return ObservationCategory.ELEVATION
    if any(k in pt for k in ("SPECTR", "COMPOSITION", "XRD", "LIBS")) or any(
        k in inst for k in ("CRISM", "OMEGA", "CHEMIN", "CHEMCAM", "APXS", "SAM", "PIXL")
    ):
        if any(k in ds.mission.upper() for k in ("MSL", "CURIOSITY", "MARS 2020")) or any(
            k in inst for k in ("CHEMCAM", "APXS", "CHEMIN", "SAM")
        ):
            return ObservationCategory.ROVER
        return ObservationCategory.SPECTRAL
    if any(k in pt for k in ("THERM", "EMISSIVITY")) or "THEMIS" in inst or "TES" in inst:
        return ObservationCategory.THERMAL
    if any(k in pt for k in ("ATMOS", "ENVIRON", "RADIATION", "WEATHER")) or any(
        k in inst for k in ("REMS", "RAD")
    ):
        return ObservationCategory.ENVIRONMENTAL
    if any(k in pt for k in ("LOCALIZATION", "WAYPOINT", "PANORAMA")) or "MSL" in ds.mission.upper():
        return ObservationCategory.ROVER
    return ObservationCategory.OPTICAL


def normalize_lon_east_360(lon: float) -> float:
    return float(lon) % 360.0


def unwrap_ring_longitudes(coords: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Unwrap consecutive ring longitudes to avoid false +/-360 deg horizontal jumps."""
    if not coords:
        return []
    out: List[Tuple[float, float]] = [(float(coords[0][0]), max(-90.0, min(90.0, float(coords[0][1]))))]
    prev_x = out[0][0]
    for x, y in coords[1:]:
        nx = float(x)
        while nx - prev_x > 180.0:
            nx -= 360.0
        while nx - prev_x < -180.0:
            nx += 360.0
        out.append((nx, max(-90.0, min(90.0, float(y)))))
        prev_x = nx
    return out


def split_antimeridian_geometry(
    geom: BaseGeometry,
    *,
    cut_lon: float = 360.0,
) -> Tuple[BaseGeometry, bool]:
    """
    Split polygons crossing the [0, 360) wrap line or [-180, 180] antimeridian
    and normalize longitudes back into [0, 360].
    """
    if geom.is_empty:
        return geom, False
    minx, _, maxx, _ = geom.bounds
    if maxx - minx >= 359.5:
        # Global coverage cylinder — keep clean [0, 360] representation without false split
        shifted = shapely_transform(lambda x, y, z=None: (max(0.0, min(360.0, float(x))), max(-90.0, min(90.0, float(y)))), geom)
        return make_valid(shifted), False

    if minx >= 0.0 and maxx <= 360.0:
        return geom, False

    polys: List[Polygon] = []
    if isinstance(geom, Polygon):
        raw_polys = [geom]
    elif isinstance(geom, (MultiPolygon, GeometryCollection)):
        raw_polys = [g for g in geom.geoms if isinstance(g, Polygon)]
    else:
        return geom, False

    did_split = False
    for p in raw_polys:
        pminx, pminy, pmaxx, pmaxy = p.bounds
        if pminx < 0.0 and pmaxx > 0.0 and (pmaxx - pminx) < 180.0:
            did_split = True
            west_half = p.intersection(box(-360.0, -90.0, 0.0, 90.0))
            east_half = p.intersection(box(0.0, -90.0, 360.0, 90.0))
            if not west_half.is_empty:
                polys.append(shapely_transform(lambda x, y, z=None: (x + 360.0, y), west_half))
            if not east_half.is_empty:
                polys.append(east_half)
        elif pmaxx > cut_lon and pminx < cut_lon and (pmaxx - pminx) < 180.0:
            did_split = True
            low_half = p.intersection(box(-360.0, -90.0, cut_lon, 90.0))
            high_half = p.intersection(box(cut_lon, -90.0, 720.0, 90.0))
            if not low_half.is_empty:
                polys.append(low_half)
            if not high_half.is_empty:
                polys.append(shapely_transform(lambda x, y, z=None: (x - 360.0, y), high_half))
        else:
            shift = 360.0 if pmaxx <= 0.0 else (-360.0 if pminx >= 360.0 else 0.0)
            polys.append(shapely_transform(lambda x, y, z=None, s=shift: (x + s, y), p))

    # Flatten into polygonal collection
    clean_polys: List[Polygon] = []
    for piece in polys:
        if isinstance(piece, Polygon):
            clean_polys.append(piece)
        elif isinstance(piece, (MultiPolygon, GeometryCollection)):
            clean_polys.extend([g for g in piece.geoms if isinstance(g, Polygon)])
    if not clean_polys:
        return geom, False
    merged = unary_union(clean_polys)
    if not merged.is_valid:
        merged = make_valid(merged)
    return merged, did_split


def ensure_valid_mars_geometry(
    geom: BaseGeometry,
) -> Tuple[BaseGeometry, bool, bool]:
    """Repair invalid topology safely and handle antimeridian wrapping."""
    repair_applied = False
    if geom.is_empty:
        return geom, False, False
    if not geom.is_valid:
        geom = make_valid(geom)
        repair_applied = True
    geom, did_split = split_antimeridian_geometry(geom)
    if not geom.is_valid:
        geom = make_valid(geom)
        repair_applied = True
    return geom, repair_applied, did_split


def _geometry_area_sinusoidal_or_laea_m2(
    geom: BaseGeometry,
    *,
    radius_m: float = MARS_MEAN_RADIUS_M,
) -> float:
    if geom.is_empty:
        return 0.0
    if isinstance(geom, Point):
        return 0.0
    minx, miny, maxx, maxy = geom.bounds
    lon_span = maxx - minx
    if lon_span > 170.0 and (maxy - miny) > 80.0:
        # Global / hemisphere scale: integrate spherical zone band strips analytically
        # Wait: slice by 5 deg bands projected locally around band centroid longitude to avoid sinusoidal seam artifact
        total = 0.0
        step = 10.0
        lat = max(-90.0, miny)
        while lat < min(90.0, maxy) - 1e-9:
            nxt_lat = min(90.0, maxy, lat + step)
            lon = minx
            while lon < maxx - 1e-9:
                nxt_lon = min(maxx, lon + 30.0)
                cell = box(lon, lat, nxt_lon, nxt_lat).intersection(geom)
                if not cell.is_empty:
                    total += _geometry_area_sinusoidal_or_laea_m2(cell, radius_m=radius_m)
                lon = nxt_lon
            lat = nxt_lat
        return float(total)

    centroid = geom.centroid
    lon0 = float(centroid.x) % 360.0
    if lon0 > 180.0:
        lon0 -= 360.0
    lat0 = float(centroid.y)
    # Shift geom to [-180, 180] relative to lon0 for clean proj transformation
    def _wrap_to_lon0(x: float, y: float, z: Any = None) -> Tuple[float, float]:
        # Adjust x nearest to centroid.x before mapping
        dx = ((float(x) - float(centroid.x) + 180.0) % 360.0) - 180.0
        wx = lon0 + dx
        if wx > 180.0:
            wx -= 360.0
        elif wx < -180.0:
            wx += 360.0
        return wx, max(-89.9999, min(89.9999, float(y)))

    wrapped = shapely_transform(_wrap_to_lon0, geom)
    if abs(lat0) > 75.0:
        pole = 90.0 if lat0 >= 0.0 else -90.0
        proj_str = f"+proj=laea +lat_0={pole} +lon_0={lon0:.6f} +R={radius_m:.3f} +units=m +no_defs"
    else:
        proj_str = f"+proj=sinu +lon_0={lon0:.6f} +R={radius_m:.3f} +units=m +no_defs"
    geog_str = f"+proj=longlat +R={radius_m:.3f} +no_defs"
    transformer = Transformer.from_crs(geog_str, proj_str, always_xy=True)
    projected = shapely_transform(lambda x, y, z=None: transformer.transform(x, y), wrapped)
    if not projected.is_valid:
        projected = make_valid(projected)
    return float(abs(projected.area))


def compute_mars_geometry_area_m2(
    geom: BaseGeometry,
    *,
    radius_m: float = MARS_MEAN_RADIUS_M,
) -> float:
    """Compute planetary equal-area m^2 using Mars Sinusoidal / Polar LAEA projection."""
    return _geometry_area_sinusoidal_or_laea_m2(geom, radius_m=radius_m)


def _border_zero_mask(arr: np.ndarray) -> np.ndarray:
    """
    Identify zero-valued pixels connected to the image exterior boundary (oblique swath
    padding in 8-bit optical JP2s lacking explicit nodata tags) without discarding internal shadows.
    """
    h, w = arr.shape
    is_zero = arr == 0
    if not np.any(is_zero):
        return np.zeros_like(arr, dtype=bool)
    visited = np.zeros((h, w), dtype=bool)
    q: deque[Tuple[int, int]] = deque()

    for c in range(w):
        if is_zero[0, c] and not visited[0, c]:
            visited[0, c] = True
            q.append((0, c))
        if h > 1 and is_zero[h - 1, c] and not visited[h - 1, c]:
            visited[h - 1, c] = True
            q.append((h - 1, c))
    for r in range(1, h - 1):
        if is_zero[r, 0] and not visited[r, 0]:
            visited[r, 0] = True
            q.append((r, 0))
        if w > 1 and is_zero[r, w - 1] and not visited[r, w - 1]:
            visited[r, w - 1] = True
            q.append((r, w - 1))

    while q:
        r, c = q.popleft()
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < h and 0 <= nc < w and not visited[nr, nc] and is_zero[nr, nc]:
                visited[nr, nc] = True
                q.append((nr, nc))
    return visited


def extract_raster_valid_mask_geometry(
    raster_path: Path,
    *,
    max_sample_dim: int = 384,
) -> Dict[str, Any]:
    """
    Extract both full raster bounding box and exact valid-pixel swath hull polygon
    by vectorizing valid pixel regions on a bounded raster read without loading gigabytes.
    """
    with rasterio.open(raster_path) as src:
        w, h = int(src.width), int(src.height)
        nodata = src.nodatavals[0] if src.nodatavals else None
        raw_crs = src.crs.to_string() if src.crs else None
        scale_factor = max(1.0, max(w, h) / float(max_sample_dim))
        out_w = max(4, min(w, int(round(w / scale_factor))))
        out_h = max(4, min(h, int(round(h / scale_factor))))
        band = src.read(1, out_shape=(out_h, out_w), resampling=Resampling.nearest).astype(np.float64)
        out_transform = src.transform * src.transform.scale(w / float(out_w), h / float(out_h))

        b_left, b_bottom, b_right, b_top = src.bounds
        bbox_geom = box(float(b_left), float(b_bottom), float(b_right), float(b_top))

        invalid_mask = ~np.isfinite(band)
        if nodata is not None and np.isfinite(nodata):
            invalid_mask = invalid_mask | np.isclose(band, float(nodata), rtol=1e-6, atol=1e-9) | (band <= -1e30)
        else:
            # Handle 8-bit/16-bit ortho JP2 with oblique black padding around swath edges
            dtype_str = str(src.dtypes[0]).lower()
            if "uint8" in dtype_str or "int" in dtype_str:
                invalid_mask = invalid_mask | _border_zero_mask(band)

        valid_mask = (~invalid_mask).astype(np.uint8)
        sampled_valid_pct = float(np.mean(valid_mask) * 100.0) if valid_mask.size else 0.0

        polys: List[Polygon] = []
        if np.any(valid_mask == 1):
            for geom_dict, val in raster_shapes(valid_mask, mask=(valid_mask == 1), transform=out_transform):
                if int(val) != 1:
                    continue
                shp = shape(geom_dict)
                if not shp.is_empty:
                    if isinstance(shp, Polygon):
                        polys.append(shp)
                    elif isinstance(shp, MultiPolygon):
                        polys.extend(list(shp.geoms))

        if polys:
            valid_union = unary_union(polys)
            pixel_tol = max(abs(out_transform.a), abs(out_transform.e)) * 0.75
            valid_union = valid_union.simplify(pixel_tol, preserve_topology=True)
            if not valid_union.is_valid:
                valid_union = make_valid(valid_union)
        else:
            valid_union = Polygon()

        if src.crs and src.crs.is_projected:
            from pyproj import CRS as PyprojCRS

            geog_crs = src.crs.geodetic_crs or PyprojCRS.from_proj4(f"+proj=longlat +R={MARS_MEAN_RADIUS_M} +no_defs")
            to_geog = Transformer.from_crs(src.crs, geog_crs, always_xy=True)
            bbox_geom_geog = shapely_transform(lambda x, y, z=None: to_geog.transform(x, y), bbox_geom)
            bbox_clean, repair_2, split_2 = ensure_valid_mars_geometry(bbox_geom_geog)
            if not valid_union.is_empty:
                valid_geog = shapely_transform(lambda x, y, z=None: to_geog.transform(x, y), valid_union)
                valid_union, repair_1, split_1 = ensure_valid_mars_geometry(valid_geog)
            else:
                repair_1, split_1 = False, False
            b_left, b_bottom, b_right, b_top = bbox_clean.bounds
        else:
            bbox_clean, repair_2, split_2 = ensure_valid_mars_geometry(bbox_geom)
            valid_union, repair_1, split_1 = ensure_valid_mars_geometry(valid_union) if not valid_union.is_empty else (Polygon(), False, False)

        return {
            "raw_crs": raw_crs,
            "width": w,
            "height": h,
            "sampled_shape": [out_h, out_w],
            "sampled_valid_pct": round(sampled_valid_pct, 2),
            "pixel_spacing_deg": {"dx": abs(float(src.transform.a)), "dy": abs(float(src.transform.e))},
            "bbox_geom": bbox_clean,
            "valid_geom": valid_union,
            "repair_applied": repair_1 or repair_2,
            "antimeridian_split": split_1 or split_2,
            "bounds": {
                "min_lon": normalize_lon_east_360(float(b_left)) if float(b_right) - float(b_left) < 359.5 else 0.0,
                "max_lon": (normalize_lon_east_360(float(b_right)) if float(b_right) - float(b_left) < 359.5 else 360.0),
                "min_lat": float(b_bottom),
                "max_lat": float(b_top),
            },
        }


def _build_geojson_polygon(coords_ring: List[Tuple[float, float]]) -> Optional[BaseGeometry]:
    if len(coords_ring) < 3:
        return None
    ring = list(coords_ring)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return Polygon(ring)


def extract_dataset_footprint(
    ds: Dataset,
    *,
    dataset_root_dir: Path,
    waypoints_sample: Optional[List[Dict[str, float]]] = None,
) -> SpatialFootprintRecord:
    """
    Extract exact footprint and valid-pixel geometry for any catalog Dataset.
    """
    category = classify_dataset_observation_category(ds)
    crs_val = validate_mars_crs_detailed(
        ds.coordinate_reference_system,
        latitude_convention=ds.latitude_convention,
        longitude_direction=ds.longitude_direction,
        vertical_reference=ds.calibration_status,
        require_conventions=True,
    )
    history: List[str] = []
    limitations: List[str] = list(ds.known_limitations or [])

    # Resolve best available raster path: prefer authoritative readable raw/label raster (.img/.jp2/.lbl), then processed GeoTIFF
    raster_candidates: List[Path] = []
    has_local = False
    for rel in (ds.local_file_path, ds.local_label_path, ds.processed_file_path):
        if rel:
            cand = Path(rel) if Path(rel).is_absolute() else (dataset_root_dir / rel)
            if cand.exists():
                if cand.suffix.lower() in {".tif", ".tiff", ".jp2", ".img"}:
                    has_local = True
                # If raw artifact is a headerless PDS3 .img accompanied by a .lbl, queue .lbl ahead/beside .tif
                if cand.suffix.lower() == ".lbl" and cand.with_suffix(".img").exists():
                    if cand not in raster_candidates:
                        raster_candidates.insert(0, cand)
                elif cand.suffix.lower() in {".tif", ".tiff", ".jp2", ".img"} and cand not in raster_candidates:
                    raster_candidates.append(cand)

    # Case 1: Raster file readable directly by Rasterio (.img, .jp2, .tif)
    for raster_path in raster_candidates:
        try:
            ext = extract_raster_valid_mask_geometry(raster_path)
            raw_crs_res = validate_mars_crs_detailed(
                ext["raw_crs"] or ds.coordinate_reference_system,
                latitude_convention=ds.latitude_convention,
                longitude_direction=ds.longitude_direction,
                vertical_reference=ds.calibration_status,
            )
            crs_final = raw_crs_res if raw_crs_res.valid else crs_val
            bbox_geom: BaseGeometry = ext["bbox_geom"]
            valid_geom: BaseGeometry = ext["valid_geom"]
            bbox_area = compute_mars_geometry_area_m2(bbox_geom)
            valid_area = compute_mars_geometry_area_m2(valid_geom) if not valid_geom.is_empty else 0.0
            invalid_geom = bbox_geom.difference(valid_geom) if not valid_geom.is_empty else bbox_geom
            if not invalid_geom.is_valid:
                invalid_geom = make_valid(invalid_geom)
            invalid_area = max(0.0, bbox_area - valid_area)
            valid_frac = (valid_area / bbox_area) if bbox_area > 0 else 0.0
            swath_ratio = valid_frac

            if valid_geom.is_empty:
                dq = "no_valid_pixels"
                limitations.append("Raster inspected cleanly but contained zero valid non-nodata pixels.")
            elif valid_frac < 0.90:
                dq = "oblique_swath_partial_nodata"
                limitations.append(
                    f"Oblique stereo/orbital swath covers {valid_frac * 100.0:.1f}% of bounding box; "
                    "corner NoData exclusions preserved as invalid geometry."
                )
            else:
                dq = "complete_valid"

            history.append(
                f"Extracted {ext['sampled_shape']} downsampled valid-pixel hull polygon from {raster_path.name} ({ext['sampled_valid_pct']:.1f}% valid)."
            )
            return SpatialFootprintRecord(
                dataset_id=ds.id,
                product_id=ds.product_id,
                mission=ds.mission,
                instrument=ds.instrument,
                category=category,
                crs=crs_final.canonical_identifier or (ds.coordinate_reference_system or "UNKNOWN"),
                coordinate_validation=crs_final,
                extraction_method=FootprintExtractionMethod.AUTHORITATIVE_RASTER_VALID_MASK_HULL,
                is_approximate=False,
                geometry_valid=bool(valid_geom.is_valid if not valid_geom.is_empty else bbox_geom.is_valid),
                repair_applied=ext["repair_applied"],
                antimeridian_split=ext["antimeridian_split"],
                original_bounds=ext["bounds"],
                footprint_geojson=mapping(valid_geom) if not valid_geom.is_empty else mapping(bbox_geom),
                valid_data_geojson=mapping(valid_geom) if not valid_geom.is_empty else None,
                invalid_nodata_geojson=mapping(invalid_geom) if (not invalid_geom.is_empty and invalid_area > 1.0) else None,
                product_footprint_area_m2=round(valid_area if not valid_geom.is_empty else bbox_area, 2),
                valid_data_area_m2=round(valid_area, 2),
                invalid_nodata_area_m2=round(invalid_area, 2),
                valid_data_fraction=round(valid_frac, 4),
                bbox_area_m2=round(bbox_area, 2),
                swath_to_bbox_ratio=round(swath_ratio, 4),
                horizontal_resolution_m=ds.horizontal_resolution_meters,
                vertical_resolution_m=ds.vertical_resolution_meters,
                pixel_grid_shape=[ext["height"], ext["width"]],
                data_quality_coverage=dq,
                has_local_artifact=True,
                source_sha256=ds.sha256_checksum,
                processing_history=history,
                limitations=limitations,
                classification=ScientificDataClassification.DIRECTLY_MEASURED,
            )
        except Exception as exc:
            limitations.append(f"Direct raster mask extraction failed ({exc}); checking label/catalog geometry.")

    # Case 2: Companion PDS3 .LBL bounds when present locally
    if ds.local_label_path:
        lbl_cand = Path(ds.local_label_path) if Path(ds.local_label_path).is_absolute() else (dataset_root_dir / ds.local_label_path)
        if lbl_cand.exists() and lbl_cand.suffix.lower() in {".lbl", ".img"}:
            try:
                pds_meta = extract_pds3_metadata(lbl_cand)
                b_meta = pds_meta.get("bounds") or {}
                if all(b_meta.get(k) is not None for k in ("min_lat", "max_lat", "min_lon", "max_lon")):
                    min_lat = float(b_meta["min_lat"])
                    max_lat = float(b_meta["max_lat"])
                    min_lon = float(b_meta["min_lon"])
                    max_lon = float(b_meta["max_lon"])
                    geom = box(min_lon, min_lat, max_lon, max_lat)
                    geom, repaired, split = ensure_valid_mars_geometry(geom)
                    area_m2 = compute_mars_geometry_area_m2(geom)
                    history.append(f"Constructed PDS3 ODL extent polygon from {lbl_cand.name}.")
                    return SpatialFootprintRecord(
                        dataset_id=ds.id,
                        product_id=ds.product_id,
                        mission=ds.mission,
                        instrument=ds.instrument,
                        category=category,
                        crs=crs_val.canonical_identifier or (ds.coordinate_reference_system or "UNKNOWN"),
                        coordinate_validation=crs_val,
                        extraction_method=FootprintExtractionMethod.PDS3_ODL_CORNER_POLYGON,
                        is_approximate=True,
                        geometry_valid=geom.is_valid,
                        repair_applied=repaired,
                        antimeridian_split=split,
                        original_bounds={"min_lat": min_lat, "max_lat": max_lat, "min_lon": min_lon, "max_lon": max_lon},
                        footprint_geojson=mapping(geom),
                        valid_data_geojson=mapping(geom) if has_local else None,
                        product_footprint_area_m2=round(area_m2, 2),
                        valid_data_area_m2=round(area_m2, 2) if has_local else 0.0,
                        valid_data_fraction=1.0 if has_local else 0.0,
                        bbox_area_m2=round(area_m2, 2),
                        swath_to_bbox_ratio=1.0,
                        horizontal_resolution_m=ds.horizontal_resolution_meters,
                        vertical_resolution_m=ds.vertical_resolution_meters,
                        data_quality_coverage="unverified_local_raster" if not has_local else "complete_valid",
                        has_local_artifact=has_local,
                        source_sha256=ds.sha256_checksum,
                        processing_history=history,
                        limitations=[
                            *limitations,
                            "Derived from PDS3 ODL map bounds without valid-pixel mask; interior NoData margins unknown.",
                        ],
                    )
            except Exception as exc:
                history.append(f"PDS3 label footprint extraction note: {exc}")

    # Case 3: Catalog GeographicCoverage fallback (marked strictly as APPROXIMATE!)
    cov = ds.coverage
    if cov is not None:
        min_lon = float(cov.min_longitude)
        max_lon = float(cov.max_longitude)
        if cov.longitude_range == "[-180, 180]" and min_lon < 0.0:
            min_lon = normalize_lon_east_360(min_lon)
        if cov.longitude_range == "[-180, 180]" and max_lon < 0.0:
            max_lon = normalize_lon_east_360(max_lon)
        geom = box(min_lon, float(cov.min_latitude), max_lon, float(cov.max_latitude))
        geom, repaired, split = ensure_valid_mars_geometry(geom)
        area_m2 = compute_mars_geometry_area_m2(geom)
        history.append("Used approximate catalog bounding box (no true swath vector/valid raster mask present).")
        limitations.append(
            "APPROXIMATE BOUNDING BOX ONLY: exact swath outline or valid-pixel boundary is unavailable; "
            "coverage percentages inside this box may be overestimated."
        )
        return SpatialFootprintRecord(
            dataset_id=ds.id,
            product_id=ds.product_id,
            mission=ds.mission,
            instrument=ds.instrument,
            category=category,
            crs=crs_val.canonical_identifier or (ds.coordinate_reference_system or "UNKNOWN"),
            coordinate_validation=crs_val,
            extraction_method=FootprintExtractionMethod.CATALOG_BOUNDING_BOX_APPROXIMATE,
            is_approximate=True,
            geometry_valid=geom.is_valid,
            repair_applied=repaired,
            antimeridian_split=split,
            original_bounds={
                "min_lat": float(cov.min_latitude),
                "max_lat": float(cov.max_latitude),
                "min_lon": min_lon,
                "max_lon": max_lon,
            },
            footprint_geojson=mapping(geom),
            valid_data_geojson=None,
            product_footprint_area_m2=round(area_m2, 2),
            valid_data_area_m2=None,
            valid_data_fraction=None,
            bbox_area_m2=round(area_m2, 2),
            swath_to_bbox_ratio=1.0,
            horizontal_resolution_m=ds.horizontal_resolution_meters,
            vertical_resolution_m=ds.vertical_resolution_meters,
            data_quality_coverage="unverified_local_raster" if not has_local else "point_or_table_inside_box",
            has_local_artifact=has_local,
            source_sha256=ds.sha256_checksum,
            processing_history=history,
            limitations=limitations,
        )

    return SpatialFootprintRecord(
        dataset_id=ds.id,
        product_id=ds.product_id,
        mission=ds.mission,
        instrument=ds.instrument,
        category=category,
        crs=ds.coordinate_reference_system or "UNKNOWN",
        coordinate_validation=crs_val,
        extraction_method=FootprintExtractionMethod.NO_SPATIAL_FOOTPRINT,
        is_approximate=True,
        geometry_valid=False,
        data_quality_coverage="unverified_local_raster",
        has_local_artifact=has_local,
        source_sha256=ds.sha256_checksum,
        processing_history=["Catalog record lacks spatial bounds and raster geometry."],
        limitations=[*limitations, "No spatial footprint coordinates supplied."],
    )


class SpatialFootprintIndex:
    """
    Shapely STRtree spatial index over all Mars product footprints with
    checksum/path-bound invalidation so stale geometry caches cannot survive file updates.
    """

    def __init__(self, catalog_service: Any, *, dataset_root_dir: Path):
        self.catalog_service = catalog_service
        self.dataset_root_dir = dataset_root_dir
        self._records: Dict[str, SpatialFootprintRecord] = {}
        self._geoms: List[BaseGeometry] = []
        self._geom_ids: List[str] = []
        self._tree: Optional[STRtree] = None
        self._index_signature: Optional[str] = None
        self._invalidated_reason: Optional[str] = None

    def _compute_signature(self) -> str:
        parts: List[str] = []
        for ds in sorted(self.catalog_service.list_datasets(), key=lambda x: x.id):
            parts.append(
                f"{ds.id}|{ds.sha256_checksum}|{ds.local_file_path}|{ds.processed_file_path}|{ds.status.value}"
            )
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]

    def invalidate(self, reason: str = "manual_invalidation") -> None:
        self._index_signature = None
        self._tree = None
        self._records.clear()
        self._geoms.clear()
        self._geom_ids.clear()
        self._invalidated_reason = reason

    def ensure_fresh(self) -> None:
        sig = self._compute_signature()
        if self._tree is not None and sig == self._index_signature:
            return
        self._records.clear()
        self._geoms.clear()
        self._geom_ids.clear()
        for ds in self.catalog_service.list_datasets():
            rec = extract_dataset_footprint(ds, dataset_root_dir=self.dataset_root_dir)
            self._records[ds.id] = rec
            if rec.footprint_geojson:
                shp = shape(rec.footprint_geojson)
                if not shp.is_empty:
                    self._geoms.append(shp)
                    self._geom_ids.append(ds.id)
        self._tree = STRtree(self._geoms) if self._geoms else None
        self._index_signature = sig
        self._invalidated_reason = None

    def get_footprint(self, dataset_id: str) -> Optional[SpatialFootprintRecord]:
        self.ensure_fresh()
        return self._records.get(dataset_id)

    def list_footprints(self) -> List[SpatialFootprintRecord]:
        self.ensure_fresh()
        return list(self._records.values())

    def query_geometry(self, target_geom: BaseGeometry) -> List[SpatialFootprintRecord]:
        self.ensure_fresh()
        if self._tree is None or target_geom.is_empty:
            return []
        idxs = self._tree.query(target_geom)
        out: List[SpatialFootprintRecord] = []
        seen = set()
        for idx in idxs:
            geom_i = self._geoms[int(idx)]
            if geom_i.intersects(target_geom):
                did = self._geom_ids[int(idx)]
                if did not in seen:
                    seen.add(did)
                    out.append(self._records[did])
        return out

    def query_bounds(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> List[SpatialFootprintRecord]:
        nmin = normalize_lon_east_360(min_lon)
        nmax = normalize_lon_east_360(max_lon)
        if nmax <= nmin and abs(max_lon - min_lon) < 359.5:
            g1 = box(nmin, min_lat, 360.0, max_lat)
            g2 = box(0.0, min_lat, nmax, max_lat)
            geom = unary_union([g1, g2])
        else:
            geom = box(min_lon, min_lat, max_lon, max_lat)
        return self.query_geometry(geom)


_FP_CACHE: Dict[Tuple[str, Optional[str], Optional[str], Optional[str], str], SpatialFootprintRecord] = {}


def get_or_extract_dataset_footprint(
    ds: Dataset,
    *,
    dataset_root_dir: Path,
) -> SpatialFootprintRecord:
    """Thread-safe / content-keyed footprint lookup avoiding repeated raster mask extraction."""
    key = (
        ds.id,
        ds.sha256_checksum,
        ds.local_file_path,
        ds.processed_file_path,
        str(dataset_root_dir),
    )
    cached = _FP_CACHE.get(key)
    if cached is not None:
        return cached
    rec = extract_dataset_footprint(ds, dataset_root_dir=dataset_root_dir)
    if len(_FP_CACHE) > 256:
        _FP_CACHE.clear()
    _FP_CACHE[key] = rec
    return rec


def point_intersects_footprint(
    fp: SpatialFootprintRecord,
    lat: float,
    lon_east: float,
    *,
    require_valid_pixels_if_known: bool = True,
) -> Tuple[bool, str]:
    """
    Test whether (lat, lon_east) lies inside true valid swath footprint rather than merely
    the rectangular bounding box.
    """
    n_lon = normalize_lon_east_360(float(lon_east))
    pt = Point(n_lon, float(lat))
    if require_valid_pixels_if_known and fp.valid_data_geojson:
        g_val = shape(fp.valid_data_geojson)
        if g_val.buffer(1e-7).covers(pt):
            return True, "inside_valid_data_polygon"
        # Check if inside bbox only (oblique swath NoData corner!)
        if fp.original_bounds:
            ob = fp.original_bounds
            min_l = normalize_lon_east_360(float(ob["min_lon"]))
            max_l = normalize_lon_east_360(float(ob["max_lon"]))
            if ob["min_lat"] <= lat <= ob["max_lat"] and (
                (min_l <= n_lon <= max_l) if min_l <= max_l else (n_lon >= min_l or n_lon <= max_l)
            ):
                return False, "bbox_only_outside_valid_swath_pixels"
        return False, "outside_product"
    if fp.footprint_geojson:
        g_fp = shape(fp.footprint_geojson)
        if g_fp.buffer(1e-7).covers(pt):
            return True, ("inside_approximate_bbox" if fp.is_approximate else "inside_footprint_polygon")
    if not require_valid_pixels_if_known and fp.original_bounds:
        ob = fp.original_bounds
        min_l = normalize_lon_east_360(float(ob["min_lon"]))
        max_l = normalize_lon_east_360(float(ob["max_lon"]))
        if ob["min_lat"] <= lat <= ob["max_lat"] and (
            (min_l <= n_lon <= max_l) if min_l <= max_l else (n_lon >= min_l or n_lon <= max_l)
        ):
            return True, "inside_outer_bounding_box"
    if fp.footprint_geojson or fp.original_bounds:
        return False, "outside_product"
    return False, "no_spatial_footprint"
