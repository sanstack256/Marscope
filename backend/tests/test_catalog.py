"""
Automated Catalog & Source Discovery Tests
Validates discovery, lifecycle transitions, spatial coverage checking, and manifests.
"""

from pathlib import Path
import pytest
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import DatasetLifecycleStatus


def test_catalog_discovery_and_registration(tmp_path: Path):
    catalog = DatasetCatalogService(catalog_storage_dir=tmp_path)
    discovered = catalog.discover_all_sources()
    
    assert len(discovered) >= 3, "Catalog must discover products from MOLA, Curiosity, and Mars Trek."
    
    # Check that MOLA MEGDR exists
    mola = catalog.get_dataset("mola_megt00n090hb")
    assert mola is not None
    assert mola.mission == "Mars Global Surveyor (MGS)"
    assert mola.instrument == "Mars Orbiter Laser Altimeter (MOLA)"
    assert "NASA Public Domain" in mola.license.value


def test_spatial_coverage_check(tmp_path: Path):
    catalog = DatasetCatalogService(catalog_storage_dir=tmp_path)
    catalog.discover_all_sources()

    # Gale Crater Mount Sharp study bounds
    gale_bounds = {
        "min_lat": -5.5,
        "max_lat": -4.3,
        "min_lon": 137.2,
        "max_lon": 138.0,
    }

    coverage = catalog.check_study_area_coverage("mola_megt00n090hb", gale_bounds)
    assert coverage["is_covered"], "MOLA megt00n090hb must cover Gale Crater."
    assert coverage["overlap_percentage"] > 99.0, "MOLA regional product must provide 100% coverage of Gale Crater."


def test_status_lifecycle_transition(tmp_path: Path):
    catalog = DatasetCatalogService(catalog_storage_dir=tmp_path)
    catalog.discover_all_sources()

    updated = catalog.update_dataset_status(
        "mola_megt00n090hb",
        DatasetLifecycleStatus.VALIDATED,
        processing_step="Integrity and coordinate checks passed",
    )
    assert updated.status == DatasetLifecycleStatus.VALIDATED
    assert len(updated.processing_history) > 0
