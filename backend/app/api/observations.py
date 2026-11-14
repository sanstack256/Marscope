"""
MARSCOPE Scientific Observations Endpoints
Martian Surface Intelligence & Exploration System

Loads verified observations strictly from downloaded and parsed NASA PDS files.
Never returns hardcoded fake observations.
"""

from typing import List
from fastapi import APIRouter, HTTPException, status
from app.schemas.dataset import DatasetLifecycleStatus
from app.schemas.observation import Observation
from app.science.curiosity_parser import CuriosityDataParser, MalformedObservationError
from app.services.container import RAW_DIR, catalog_service

router = APIRouter(prefix="/observations", tags=["Scientific Observations"])


def _load_verified_observations() -> List[Observation]:
    """
    Scan downloaded observation datasets in the catalog and parse verified raw PDS artifacts.
    Returns empty list when zero observation products have been acquired locally.
    """
    loaded: List[Observation] = []
    raw_root = RAW_DIR.parent

    for ds in catalog_service.list_datasets():
        if not ds.local_file_path:
            continue
        if ds.status not in {
            DatasetLifecycleStatus.DOWNLOADED,
            DatasetLifecycleStatus.VALIDATED,
            DatasetLifecycleStatus.PROCESSED,
            DatasetLifecycleStatus.AVAILABLE,
        }:
            continue

        fpath = raw_root / ds.local_file_path
        if not fpath.exists():
            continue

        lbl_path = (raw_root / ds.local_label_path) if ds.local_label_path else None
        try:
            if "chemcam" in ds.id.lower() or "spectrum" in ds.product_type.lower():
                obs = CuriosityDataParser.parse_chemcam_psv_file(
                    fpath,
                    sol=ds.observation_sol,
                    label_path=lbl_path,
                    dataset_id=ds.id,
                )
                loaded.append(obs)
            elif "rems" in ds.id.lower() or "atmospheric" in ds.product_type.lower():
                obs = CuriosityDataParser.parse_rems_adr_summary(
                    fpath,
                    sol=ds.observation_sol,
                    label_path=lbl_path,
                    dataset_id=ds.id,
                )
                loaded.append(obs)
        except (MalformedObservationError, FileNotFoundError, ValueError):
            continue

    return loaded


@router.get("", response_model=List[Observation])
async def list_observations() -> List[Observation]:
    """
    List verified in-situ observations parsed from acquired PDS datasets.
    Returns an empty list [] when no verified observation artifacts have been downloaded.
    """
    return _load_verified_observations()


@router.get("/{observation_id}", response_model=Observation)
async def get_observation(observation_id: str) -> Observation:
    """Retrieve specific verified observation dossier by ID."""
    for obs in _load_verified_observations():
        if obs.observation_id == observation_id:
            return obs
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Observation '{observation_id}' not found in verified local datasets.",
    )
