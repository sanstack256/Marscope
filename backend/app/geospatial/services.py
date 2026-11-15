"""
MARSCOPE Geospatial Facade Singletons (Prompt 19 Part 4, 5, 10, 11).

Provides stateful container-managed facades wrapping product-pair spatial registration,
multi-category spatial coverage & evidence-gap analysis, and scale-aware rover association.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.geospatial.coverage import (
    MultiCategorySpatialCoverageReport,
    compute_multi_category_spatial_coverage,
)
from app.geospatial.footprints import SpatialFootprintIndex
from app.geospatial.registration import (
    SpatialRegistrationAssessment,
    evaluate_product_pair_registration,
)
from app.science.rover_association import (
    RoverOrbitalAssociationRecord,
    evaluate_rover_orbital_association,
)


class SpatialRegistrationService:
    """Evaluates and caches inspected pairwise product registration assessments."""

    def __init__(
        self,
        *,
        catalog_service: Any,
        footprint_index: SpatialFootprintIndex,
        dataset_root_dir: Path,
        max_history: int = 48,
    ) -> None:
        self.catalog_service = catalog_service
        self.footprint_index = footprint_index
        self.dataset_root_dir = Path(dataset_root_dir)
        self._max_history = max_history
        self._assessments: "OrderedDict[str, SpatialRegistrationAssessment]" = OrderedDict()

    def evaluate_pair(
        self,
        *,
        dataset_a_id: str,
        dataset_b_id: str,
        intended_analysis: str = "spatial_overlay",
        control_points: Optional[List[Dict[str, float]]] = None,
        attempt_image_matching: bool = False,
    ) -> SpatialRegistrationAssessment:
        ds_a = self.catalog_service.get_dataset(dataset_a_id)
        if not ds_a:
            raise FileNotFoundError(f"Dataset '{dataset_a_id}' not found in catalog.")
        ds_b = self.catalog_service.get_dataset(dataset_b_id)
        if not ds_b:
            raise FileNotFoundError(f"Dataset '{dataset_b_id}' not found in catalog.")

        fp_a = self.footprint_index.get_footprint(dataset_a_id)
        fp_b = self.footprint_index.get_footprint(dataset_b_id)
        assessment = evaluate_product_pair_registration(
            ds_a,
            ds_b,
            dataset_root_dir=self.dataset_root_dir,
            footprint_a=fp_a,
            footprint_b=fp_b,
            intended_analysis=intended_analysis,
            control_points=control_points,
            attempt_image_matching=attempt_image_matching,
        )
        key = f"{dataset_a_id}__{dataset_b_id}__{intended_analysis}"
        self._assessments[key] = assessment
        self._assessments.move_to_end(key)
        while len(self._assessments) > self._max_history:
            self._assessments.popitem(last=False)
        return assessment

    def list_recent_assessments(self) -> List[SpatialRegistrationAssessment]:
        return list(reversed(self._assessments.values()))


class SpatialCoverageService:
    """Computes polygon-union 6-category spatial coverage & evidence-gap reports."""

    def __init__(
        self,
        *,
        catalog_service: Any,
        footprint_index: SpatialFootprintIndex,
        dataset_root_dir: Path,
        composition_index: Any = None,
    ) -> None:
        self.catalog_service = catalog_service
        self.footprint_index = footprint_index
        self.dataset_root_dir = Path(dataset_root_dir)
        self.composition_index = composition_index

    def assess_coverage(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        reference_dataset_id: Optional[str] = None,
        intended_resolution_threshold_m: float = 5.0,
        question_focus: Optional[str] = None,
        rover_points: Optional[List[Dict[str, Any]]] = None,
    ) -> MultiCategorySpatialCoverageReport:
        return compute_multi_category_spatial_coverage(
            catalog_service=self.catalog_service,
            footprint_index=self.footprint_index,
            dataset_root_dir=self.dataset_root_dir,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            reference_dataset_id=reference_dataset_id,
            intended_resolution_threshold_m=intended_resolution_threshold_m,
            question_focus=question_focus,
            rover_points=rover_points,
            composition_index=self.composition_index,
        )


class RoverSpatialAssociationService:
    """Evaluates scale-aware in-situ rover observation associations against orbital products."""

    def __init__(
        self,
        *,
        catalog_service: Any,
        composition_index: Any = None,
    ) -> None:
        self.catalog_service = catalog_service
        self.composition_index = composition_index

    def associate_observation(
        self,
        *,
        observation: Dict[str, Any],
        orbital_dataset_id: str,
        feature_lat: Optional[float] = None,
        feature_lon_east: Optional[float] = None,
        feature_id: Optional[str] = None,
        direct_association_radius_m: float = 15.0,
        regional_context_radius_m: float = 500.0,
    ) -> RoverOrbitalAssociationRecord:
        ds = self.catalog_service.get_dataset(orbital_dataset_id)
        if not ds:
            raise FileNotFoundError(f"Orbital dataset '{orbital_dataset_id}' not found in catalog.")

        f_lat = feature_lat
        f_lon = feature_lon_east
        if f_lat is None or f_lon is None:
            f_lat = observation.get("latitude")
            f_lon = observation.get("longitude_east")
        if f_lat is None or f_lon is None:
            raise ValueError("feature_lat and feature_lon_east (or observation coordinates) are required.")

        return evaluate_rover_orbital_association(
            observation=observation,
            feature_lat=float(f_lat),
            feature_lon_east=float(f_lon),
            orbital_dataset_id=ds.id,
            orbital_product_id=ds.product_id,
            orbital_pixel_footprint_m=ds.horizontal_resolution_meters,
            orbital_crs=ds.coordinate_reference_system,
            feature_id=feature_id,
            direct_association_radius_m=direct_association_radius_m,
            regional_context_radius_m=regional_context_radius_m,
        )

    def associate_region_observations(
        self,
        *,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        orbital_dataset_id: str,
        feature_lat: Optional[float] = None,
        feature_lon_east: Optional[float] = None,
        limit: int = 30,
    ) -> List[RoverOrbitalAssociationRecord]:
        ds = self.catalog_service.get_dataset(orbital_dataset_id)
        if not ds:
            raise FileNotFoundError(f"Orbital dataset '{orbital_dataset_id}' not found in catalog.")
        if self.composition_index is None:
            return []

        from app.science.composition.species import list_all_species

        species_ids = [s.canonical_id for s in list_all_species()]
        evs = self.composition_index.query_evidence(
            species_ids=species_ids,
            located_only=True,
            bbox=(min_lat, max_lat, min_lon % 360.0, max_lon % 360.0),
        )[: max(1, min(100, int(limit)))]

        ref_lat = feature_lat if feature_lat is not None else 0.5 * (min_lat + max_lat)
        ref_lon = feature_lon_east if feature_lon_east is not None else 0.5 * (min_lon + max_lon)
        out: List[RoverOrbitalAssociationRecord] = []
        for ev in evs:
            if ev.latitude is None or ev.longitude_east is None:
                continue
            obs_dict = {
                "observation_id": ev.evidence_id,
                "mission": getattr(ev, "mission_host", None) or "MSL Curiosity",
                "instrument": getattr(ev, "instrument_id", None) or "ChemCam",
                "product_id": getattr(ev, "product_id", None) or getattr(ev, "source_file", "PDS"),
                "measurement_type": getattr(ev.evidence_type, "value", str(ev.evidence_type)),
                "latitude": float(ev.latitude),
                "longitude_east": float(ev.longitude_east),
                "location_semantic_type": getattr(ev, "location_semantic_type", None) or "instrument_target_location",
                "crs": "IAU2000:49900",
                "acquisition_sol": getattr(ev, "sol", None),
            }
            out.append(
                self.associate_observation(
                    observation=obs_dict,
                    orbital_dataset_id=ds.id,
                    feature_lat=ref_lat,
                    feature_lon_east=ref_lon,
                )
            )
        return out
