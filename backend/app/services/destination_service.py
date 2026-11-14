"""
MARSCOPE Destination Selection & Point Terrain Assessment Service
Martian Surface Intelligence & Exploration System

Evaluates candidate coordinates against verified catalog datasets and validated
processed terrain GeoTIFFs without ever inventing elevation or fake mineral occurrences.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import rasterio
from app.geospatial.crs import (
    angular_displacement_to_metric,
    normalize_longitude_180,
    normalize_longitude_360,
    validate_mars_coordinates,
    validate_mars_crs,
)
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import VerificationState
from app.schemas.destination import (
    CompositionOccurrence,
    CompositionSearchRequest,
    CompositionSearchResponse,
    DatasetCoverageMatch,
    DestinationEvaluationResponse,
    DestinationSelectionRequest,
    TerrainPointAssessment,
)
from app.schemas.terrain import TerrainPointResponse
from app.science.composition.search import (
    CompositionSearchService,
    StructuredCompositionQuery,
)
from app.terrain.aspect import calculate_aspect
from app.terrain.roughness import calculate_roughness_tri
from app.terrain.slope import calculate_slope


class DestinationEvaluationService:
    def __init__(
        self,
        catalog_service: DatasetCatalogService,
        processed_dir: Path,
        composition_search_service: Optional[CompositionSearchService] = None,
        localization_service: Optional[Any] = None,
    ):
        self.catalog_service = catalog_service
        self.processed_dir = processed_dir
        self.composition_search_service = composition_search_service
        self.localization_service = localization_service

    def _point_covers_coverage(
        self,
        lat: float,
        lon_east: float,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        longitude_range: str = "unknown",
    ) -> bool:
        if not (min_lat <= lat <= max_lat):
            return False

        # Normalize query & bounds cleanly with antimeridian wrap awareness
        if abs(max_lon - min_lon) >= 360.0 - 1e-6:
            return True

        lon_360 = normalize_longitude_360(lon_east)
        lon_180 = normalize_longitude_180(lon_east)

        if longitude_range == "[0, 360]" or max_lon > 180.0:
            b_min = normalize_longitude_360(min_lon)
            b_max = 360.0 if abs(max_lon - 360.0) < 1e-6 else normalize_longitude_360(max_lon)
            if b_min <= b_max:
                return b_min <= lon_360 <= b_max
            # Antimeridian wrap in [0, 360)
            return lon_360 >= b_min or lon_360 <= b_max

        if longitude_range == "[-180, 180]" or min_lon < 0.0:
            if min_lon <= max_lon:
                return min_lon <= lon_180 <= max_lon
            # Antimeridian crossing in [-180, 180], e.g. [170, -170]
            return lon_180 >= min_lon or lon_180 <= max_lon

        if min_lon <= max_lon:
            return (min_lon <= lon_360 <= max_lon) or (min_lon <= lon_180 <= max_lon)
        return (lon_360 >= min_lon or lon_360 <= max_lon) or (lon_180 >= min_lon or lon_180 <= max_lon)

    def sample_processed_terrain_point(
        self,
        latitude: float,
        longitude: float,
        crs: str = "IAU2000:49900",
        latitude_convention: str = "Planetocentric",
        longitude_direction: str = "East",
    ) -> TerrainPointResponse:
        """
        Sample real elevation and local derivatives at (latitude, longitude) using windowed reads
        from validated processed DEM GeoTIFFs in PROCESSED_DIR.
        Highest-resolution covering DEM is preferred.
        If no validated DEM covers the point or the sampled pixel is no-data, returns available=False
        and elevation_m=None (never returns 0.0).
        """
        if not validate_mars_crs(crs):
            raise ValueError(f"Rejected invalid Mars CRS: '{crs}'")
        lat, lon_east = validate_mars_coordinates(latitude, longitude, latitude_convention, longitude_direction)

        manifests: List[Dict[str, Any]] = []
        for mpath in self.processed_dir.glob("*.processing.json"):
            try:
                m = json.loads(mpath.read_text(encoding="utf-8"))
                manifests.append(m)
            except Exception:
                continue

        # Sort by finest resolution first
        manifests.sort(key=lambda m: float(m.get("dx_meters", 1e12)))

        for m in manifests:
            dem_fname = m.get("files", {}).get("dem")
            if not dem_fname:
                continue
            dem_path = self.processed_dir / dem_fname
            if not dem_path.exists():
                continue

            with rasterio.open(dem_path) as src:
                sb = src.bounds
                sample_lon = normalize_longitude_360(lon_east) if sb.right > 180.0 else normalize_longitude_180(lon_east)
                if not (sb.left <= sample_lon <= sb.right and sb.bottom <= lat <= sb.top):
                    continue

                row, col = src.index(sample_lon, lat)
                if row < 0 or row >= src.height or col < 0 or col >= src.width:
                    continue

                # Windowed 3x3 read centered on (row, col)
                r0 = max(0, row - 1)
                c0 = max(0, col - 1)
                r1 = min(src.height, row + 2)
                c1 = min(src.width, col + 2)
                win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
                patch = src.read(1, window=win).astype(np.float64)
                nodata = src.nodatavals[0]

                center_val = float(patch[row - r0, col - c0])
                if not np.isfinite(center_val) or (nodata is not None and np.isfinite(nodata) and center_val == float(nodata)):
                    return TerrainPointResponse(
                        available=False,
                        latitude=lat,
                        longitude=lon_east,
                        crs=m.get("crs", crs),
                        source_dataset_id=m.get("source_dataset_id"),
                        source_product_id=m.get("source_product_id"),
                        resolution_m=float(m.get("dx_meters", 0.0)) or None,
                        units="meters",
                        unavailable_reason=f"Pixel at ({lat:.4f}, {lon_east:.4f}) is marked NO-DATA in source raster '{dem_fname}'.",
                    )

                dx_m = float(m.get("dx_meters") or 0.0)
                dy_m = float(m.get("dy_meters") or 0.0)
                if dx_m <= 0 or dy_m <= 0:
                    center_lat = (sb.bottom + sb.top) / 2.0
                    dx_m, dy_m = angular_displacement_to_metric(center_lat, abs(src.transform.a), abs(src.transform.e))

                slope_val: Optional[float] = None
                aspect_val: Optional[float] = None
                tri_val: Optional[float] = None
                warnings: List[str] = []

                if patch.shape == (3, 3):
                    nodata_mask = ~np.isfinite(patch)
                    if nodata is not None and np.isfinite(nodata):
                        nodata_mask |= patch == float(nodata)
                    s_arr, _ = calculate_slope(patch, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
                    a_arr = calculate_aspect(patch, dx_m, dy_m, nodata_mask=nodata_mask, vertical_units="meters")
                    t_arr = calculate_roughness_tri(patch, dx_meters=dx_m, dy_meters=dy_m, nodata_mask=nodata_mask, vertical_units="meters")
                    if np.isfinite(s_arr[1, 1]):
                        slope_val = round(float(s_arr[1, 1]), 3)
                    if np.isfinite(a_arr[1, 1]):
                        aspect_val = round(float(a_arr[1, 1]), 3)
                    if np.isfinite(t_arr[1, 1]):
                        tri_val = round(float(t_arr[1, 1]), 3)
                else:
                    warnings.append("Point lies on raster boundary; 3x3 slope/aspect/TRI derivatives unavailable.")

                if dx_m > 1000.0:
                    warnings.append(
                        f"Coarse DEM resolution ({round(dx_m, 1)} m/px) — suitable only for regional datum reference, not rover-scale obstacle avoidance."
                    )

                return TerrainPointResponse(
                    available=True,
                    latitude=lat,
                    longitude=lon_east,
                    crs=m.get("crs", crs),
                    elevation_m=round(center_val, 2),
                    slope_deg=slope_val,
                    aspect_deg=aspect_val,
                    roughness_tri_m=tri_val,
                    source_dataset_id=m.get("source_dataset_id"),
                    source_product_id=m.get("source_product_id"),
                    resolution_m=round(dx_m, 2),
                    units="meters",
                    warnings=warnings,
                )

        return TerrainPointResponse(
            available=False,
            latitude=lat,
            longitude=lon_east,
            crs=crs,
            elevation_m=None,
            unavailable_reason="No validated processed DEM covers this coordinate.",
        )

    def evaluate_destination(self, req: DestinationSelectionRequest) -> DestinationEvaluationResponse:
        if not validate_mars_crs(req.crs):
            raise ValueError(f"Rejected invalid Mars CRS '{req.crs}'.")
        lat, lon_east = validate_mars_coordinates(
            req.latitude,
            req.longitude,
            latitude_convention=req.latitude_convention,
            longitude_direction=req.longitude_direction,
        )

        verified_matches: List[DatasetCoverageMatch] = []
        unverified_candidates: List[DatasetCoverageMatch] = []
        for ds in self.catalog_service.list_datasets():
            cov = ds.coverage
            if self._point_covers_coverage(
                lat,
                lon_east,
                cov.min_latitude,
                cov.max_latitude,
                cov.min_longitude,
                cov.max_longitude,
                longitude_range=cov.longitude_range,
            ):
                cov_verified = (
                    ds.verification.coverage_verification == VerificationState.VERIFIED
                    and validate_mars_crs(ds.coordinate_reference_system)
                )
                provenance_str = (
                    f"{ds.source_archive} | CRS={ds.coordinate_reference_system} | {ds.map_projection}"
                )
                entry = DatasetCoverageMatch(
                    dataset_id=ds.id,
                    product_id=ds.product_id,
                    product_title=ds.product_title,
                    product_type=ds.product_type,
                    horizontal_resolution_meters=ds.horizontal_resolution_meters,
                    available_for_evaluation=cov_verified and ds.status.value in {"processed", "available", "downloaded", "validated"},
                    coverage_verified=cov_verified,
                    verification_state=ds.verification.coverage_verification,
                    footprint_provenance=provenance_str if cov_verified else None,
                    crs=ds.coordinate_reference_system,
                    longitude_range=cov.longitude_range,
                    notes=(
                        f"Verified spatial footprint (status: {ds.status.value})"
                        if cov_verified
                        else f"UNVERIFIED catalog envelope only (coverage_verification={ds.verification.coverage_verification.value}); verify .LBL/product before relying on coverage."
                    ),
                )
                if cov_verified:
                    verified_matches.append(entry)
                else:
                    unverified_candidates.append(entry)

        point_terrain = self.sample_processed_terrain_point(
            lat,
            lon_east,
            crs=req.crs,
            latitude_convention=req.latitude_convention,
            longitude_direction="East",
        )

        terrain_assessment = TerrainPointAssessment(
            available=point_terrain.available,
            elevation_m=point_terrain.elevation_m,
            slope_deg=point_terrain.slope_deg,
            aspect_deg=point_terrain.aspect_deg,
            roughness_tri_m=point_terrain.roughness_tri_m,
            source_dataset_id=point_terrain.source_dataset_id,
            source_product_id=point_terrain.source_product_id,
            resolution_m=point_terrain.resolution_m,
            units=point_terrain.units,
            crs=point_terrain.crs,
            unavailable_reason=point_terrain.unavailable_reason,
            warnings=point_terrain.warnings,
        )

        warnings: List[str] = list(point_terrain.warnings)
        if point_terrain.available:
            eval_status = "terrain_evaluable"
        elif verified_matches:
            eval_status = "verified_coverage_dem_unavailable"
            warnings.append("Verified dataset coverage overlaps this coordinate, but no validated local DEM raster is processed yet.")
        elif unverified_candidates:
            eval_status = "unverified_catalog_candidates_only"
            warnings.append(
                "Only unverified catalog placeholders overlap this coordinate (coverage_verification != VERIFIED). Download & inspect .LBL/product to confirm real coverage."
            )
        else:
            eval_status = "insufficient_data_coverage"
            warnings.append("No verified dataset or processed raster covers this coordinate.")

        return DestinationEvaluationResponse(
            valid=True,
            latitude=lat,
            longitude=lon_east,
            normalized_longitude_180=round(normalize_longitude_180(lon_east), 6),
            normalized_longitude_360=round(normalize_longitude_360(lon_east), 6),
            crs=req.crs,
            latitude_convention=req.latitude_convention,
            longitude_direction="East",
            label=req.label,
            can_evaluate=point_terrain.available,
            evaluation_status=eval_status,
            covering_datasets=verified_matches,
            unverified_catalog_candidates=unverified_candidates,
            terrain=terrain_assessment,
            warnings=warnings,
            selected_at_utc=datetime.now(timezone.utc),
        )

    def search_composition(self, request: Union[str, CompositionSearchRequest]) -> CompositionSearchResponse:
        """
        Execute verified geochemical & mineralogical spatial discovery against the persistent
        SQLite composition index. Never fabricates results when the index is unbuilt or empty.
        """
        req = (
            CompositionSearchRequest(query=request.strip())
            if isinstance(request, str)
            else request
        )
        if self.composition_search_service is None:
            return CompositionSearchResponse(
                query=req.query,
                index_available=False,
                total_matches=0,
                results=[],
                unavailable_reason=(
                    "Geochemical & mineralogical spatial search index is not yet built. "
                    "Requires verified APXS/ChemCam MOC/CheMin/CRISM catalog ingestion."
                ),
            )

        astro_lat = req.astronaut_latitude
        astro_lon = req.astronaut_longitude
        if (astro_lat is None or astro_lon is None) and req.use_active_astronaut_position and self.localization_service is not None:
            loc_status = self.localization_service.get_status()
            pos = loc_status.current_position
            if pos and pos.latitude is not None and pos.longitude is not None:
                astro_lat = pos.latitude
                astro_lon = pos.longitude

        structured = self.composition_search_service.search(
            StructuredCompositionQuery(
                query=req.query,
                search_mode=req.search_mode,
                include_element_bearing_minerals=req.include_element_bearing_minerals,
                astronaut_latitude=astro_lat,
                astronaut_longitude=astro_lon,
                max_distance_m=req.max_distance_m,
                instruments=req.instruments,
                sol_min=req.sol_min,
                sol_max=req.sol_max,
                min_value=req.min_value,
                max_value=req.max_value,
                measurement_category_filter=req.measurement_category_filter,
                exclude_low_quality=req.exclude_low_quality,
                sort_by=req.sort_by,
                limit=req.limit,
                offset=req.offset,
            )
        )

        occurrences = [
            CompositionOccurrence(
                evidence_id=h.evidence.evidence_id,
                observation_id=h.evidence.source_record_ref,
                dataset_id=h.evidence.source_dataset_id,
                product_id=h.evidence.product_id,
                instrument_id=h.evidence.instrument_id,
                target_name=h.evidence.target_name,
                sol=h.evidence.sol,
                latitude=h.evidence.latitude,
                longitude=h.evidence.longitude_east,
                elevation_m=h.evidence.elevation_m,
                crs=h.evidence.crs,
                measured_species=h.evidence.canonical_species_id,
                evidence_type=h.evidence.evidence_type.value,
                match_type=h.match_type.value,
                value=h.evidence.normalized_value,
                units=h.evidence.normalized_unit,
                uncertainty=h.evidence.uncertainty_value,
                distance_from_astronaut_m=h.distance_from_astronaut_m,
                composite_rank_score=h.ranking.composite_rank_score,
                location_semantic_type=h.evidence.location_semantic_type.value,
                coordinate_uncertainty_m=h.evidence.coordinate_uncertainty_m,
                is_stoichiometric_conversion=h.evidence.is_stoichiometric_conversion,
                source_oxide_species=h.evidence.source_oxide_species,
                coordinate_source=h.evidence.coordinate_source,
                source_reference=h.evidence.source_reference,
            )
            for h in structured.hits
        ]

        return CompositionSearchResponse(
            query=req.query,
            index_available=structured.index_available,
            total_matches=structured.total_located_matches,
            unlocated_matches_count=structured.unlocated_matches_count,
            measurement_categories_present=structured.measurement_categories_present,
            grouped_counts_by_measurement_category=structured.grouped_counts_by_measurement_category,
            applied_filter_scope_note=structured.applied_filter_scope_note,
            results=occurrences,
            hits=structured.hits,
            candidate_locations=structured.candidate_locations,
            resolution=structured.resolution,
            index_status=structured.index_status,
            ranking_configuration_used=structured.ranking_configuration_used,
            astronaut_position_used=structured.astronaut_position_used,
            unavailable_reason=structured.unavailable_reason,
            scientific_warnings=structured.scientific_warnings,
        )
