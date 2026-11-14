"""
MARSCOPE Cross-Dataset Registration & Spatial Alignment Uncertainty Assessment
Assesses whether orbital DEMs, orthoimages, regional geology, and surface traverse records
share a datum/bundle or exhibit unquantified lateral misregistration sensitivity.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.schemas.dataset import Dataset
from app.terrain_uncertainty.models import UncertaintyStatus
from app.terrain_uncertainty.schemas import (
    RegistrationPairAssessment,
    RegistrationUncertaintyResult,
)


def _extract_orbit_pair_tokens(product_id: str) -> set[str]:
    """Extract 6-digit MRO HiRISE orbit tokens from product IDs like DTEEC_009149_1750_009294_1750_U01."""
    return set(re.findall(r"(?<!\d)(\d{6})(?!\d)", product_id or ""))


def assess_cross_dataset_registration(
    *,
    dem_dataset: Dataset,
    optical_dataset: Optional[Dataset] = None,
    additional_datasets: Optional[List[Dataset]] = None,
) -> RegistrationUncertaintyResult:
    """
    Evaluate spatial alignment and co-registration uncertainty between the primary DEM and
    supporting optical, regional geologic, and rover/point datasets.
    """
    pair_assessments: List[RegistrationPairAssessment] = []
    limitations: List[str] = [
        "No dataset in the local catalog provides an empirical per-pixel X/Y co-registration RMSE raster.",
    ]

    dem_orbits = _extract_orbit_pair_tokens(dem_dataset.product_id)

    if optical_dataset is not None:
        opt_orbits = _extract_orbit_pair_tokens(optical_dataset.product_id)
        shared_bundle = bool(dem_orbits & opt_orbits)
        shared_crs = (dem_dataset.coordinate_reference_system or "") == (
            optical_dataset.coordinate_reference_system or ""
        )
        nom_note = (
            f"Shared HiRISE stereo acquisition orbit(s) {sorted(dem_orbits & opt_orbits)} "
            f"({dem_dataset.product_id} paired with {optical_dataset.product_id}); orthoimage "
            "is projected using the SOCET SET DTM solution, though local tiepoint RMS is not reported in PDS keywords."
            if shared_bundle
            else f"{dem_dataset.product_id} and {optical_dataset.product_id} originate from separate acquisitions without verified shared stereo bundle metadata."
        )
        pair_assessments.append(
            RegistrationPairAssessment(
                primary_dataset_id=dem_dataset.id,
                secondary_dataset_id=optical_dataset.id,
                shared_crs=shared_crs,
                primary_crs=dem_dataset.coordinate_reference_system or "unknown",
                secondary_crs=optical_dataset.coordinate_reference_system or "unknown",
                shared_stereo_bundle=shared_bundle,
                datum_tie_note=f"DEM datum: {dem_dataset.calibration_status}; Optical: {optical_dataset.calibration_status}",
                lateral_misregistration_status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                nominal_co_registration_note=nom_note,
                quantified_rms_offset_m=None,
                cross_layer_boundary_caution=(
                    "At steep crater walls, scarp edges, or sharp ridges, even a 1-2 pixel lateral offset "
                    "between optical shading features and DEM heights can shift apparent slope thresholds."
                ),
            )
        )

    for sec in additional_datasets or []:
        if sec.id in {dem_dataset.id, optical_dataset.id if optical_dataset else ""}:
            continue
        sec_crs = sec.coordinate_reference_system or "unknown"
        dem_crs = dem_dataset.coordinate_reference_system or "unknown"
        shared_crs = sec_crs == dem_crs
        scale_note = (
            f"Secondary product '{sec.product_id}' has ~{sec.horizontal_resolution_meters:.1f} m scale vs "
            f"DEM ~{dem_dataset.horizontal_resolution_meters:.2f} m; point-to-pixel comparisons across scale discontinuities "
            "carry unquantified spatial localization offset."
            if (sec.horizontal_resolution_meters and dem_dataset.horizontal_resolution_meters)
            else f"Secondary dataset '{sec.product_id}' represents localized or regional observations lacking pixel-level co-registration RMS against HiRISE."
        )
        pair_assessments.append(
            RegistrationPairAssessment(
                primary_dataset_id=dem_dataset.id,
                secondary_dataset_id=sec.id,
                shared_crs=shared_crs,
                primary_crs=dem_crs,
                secondary_crs=sec_crs,
                shared_stereo_bundle=False,
                datum_tie_note=sec.calibration_status or "Dataset datum per catalog",
                lateral_misregistration_status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
                nominal_co_registration_note=scale_note,
                quantified_rms_offset_m=None,
                cross_layer_boundary_caution=(
                    "Do not interpret coarse regional polygon boundaries (e.g., 1:20M USGS geologic contacts) or rover telemetry "
                    "offsets as meter-accurate DEM hazard boundaries."
                ),
            )
        )

    if any(p.shared_stereo_bundle for p in pair_assessments):
        limitations.append(
            "Paired HiRISE DTM/Ortho share acquisition orbits, reducing gross relative distortion, but absolute tie to MOLA Areoid remains unquantified locally."
        )

    return RegistrationUncertaintyResult(
        dem_dataset_id=dem_dataset.id,
        optical_dataset_id=optical_dataset.id if optical_dataset else None,
        overall_status=UncertaintyStatus.UNCERTAINTY_UNQUANTIFIED,
        pair_assessments=pair_assessments,
        slope_and_point_sensitivity_note=(
            "Cross-layer boundary comparisons (optical detections or rover point picks projected onto DEM slopes) "
            "are sensitive to lateral offset near steep scarps and shadowed walls."
        ),
        limitations=limitations,
    )
