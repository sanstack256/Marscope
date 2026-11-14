"""
Automated API Endpoints & Scientific Integrity Tests
Verifies zero fabricated defaults, honest unavailable states, observation parsing,
layer catalog integrity, localization architecture, destination evaluation, and real raster tiling.
All tests run in isolated tmp_path storage and never mutate repository catalog files.
"""

from pathlib import Path
import numpy as np
import pytest
import rasterio
from httpx import ASGITransport, AsyncClient
from rasterio.transform import from_bounds

import app.api.datasets as api_datasets
import app.api.observations as api_observations
import app.api.terrain as api_terrain
import app.services.container as container
from app.geospatial.crs import MARS_CRS_DEFINITIONS

MARS_CRS_PROJ4 = MARS_CRS_DEFINITIONS["IAU2000:49900"]
from app.ingestion.acquisition import AcquisitionService
from app.ingestion.catalog import DatasetCatalogService
from app.main import app
from app.schemas.dataset import (
    Dataset,
    DatasetLifecycleStatus,
    GeographicCoverage,
    LicenseStatus,
    MetadataVerification,
    VerificationState,
)
from app.services.destination_service import DestinationEvaluationService
from app.services.layer_service import LayerCatalogService
from app.services.localization_service import LocalizationService
from app.science.composition.index import CompositionSpatialIndex
from app.science.composition.search import CompositionSearchService
from app.science.target_registry import TargetRegistryService


@pytest.fixture(autouse=True)
def isolated_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate catalog, raw, processed, index, localization, layer, target, and destination state per test."""
    catalog_dir = tmp_path / "catalog"
    manifests_dir = tmp_path / "manifests"
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    index_dir = tmp_path / "index"
    for d in (catalog_dir, manifests_dir, raw_dir, processed_dir, index_dir):
        d.mkdir(parents=True, exist_ok=True)

    cat_svc = DatasetCatalogService(catalog_storage_dir=catalog_dir, raw_data_dir=raw_dir)
    acq_svc = AcquisitionService(raw_data_dir=raw_dir, manifests_dir=manifests_dir)
    comp_idx = CompositionSpatialIndex(db_path=index_dir / "composition_index.sqlite")
    comp_search = CompositionSearchService(index=comp_idx)
    tgt_reg = TargetRegistryService(composition_index=comp_idx)
    lay_svc = LayerCatalogService(catalog_service=cat_svc, processed_dir=processed_dir, raw_dir=raw_dir)
    loc_svc = LocalizationService()
    dest_svc = DestinationEvaluationService(
        catalog_service=cat_svc,
        processed_dir=processed_dir,
        composition_search_service=comp_search,
        localization_service=loc_svc,
    )

    for mod in (container, api_datasets, api_terrain, api_observations):
        if hasattr(mod, "RAW_DIR"):
            monkeypatch.setattr(mod, "RAW_DIR", raw_dir)
        if hasattr(mod, "PROCESSED_DIR"):
            monkeypatch.setattr(mod, "PROCESSED_DIR", processed_dir)
        if hasattr(mod, "catalog_service"):
            monkeypatch.setattr(mod, "catalog_service", cat_svc)
        if hasattr(mod, "acquisition_service"):
            monkeypatch.setattr(mod, "acquisition_service", acq_svc)
        if hasattr(mod, "layer_service"):
            monkeypatch.setattr(mod, "layer_service", lay_svc)
        if hasattr(mod, "localization_service"):
            monkeypatch.setattr(mod, "localization_service", loc_svc)
        if hasattr(mod, "destination_service"):
            monkeypatch.setattr(mod, "destination_service", dest_svc)
        if hasattr(mod, "composition_index"):
            monkeypatch.setattr(mod, "composition_index", comp_idx)
        if hasattr(mod, "composition_search_service"):
            monkeypatch.setattr(mod, "composition_search_service", comp_search)
        if hasattr(mod, "target_registry"):
            monkeypatch.setattr(mod, "target_registry", tgt_reg)

    import app.api.layers as api_layers
    import app.api.sources as api_sources
    import app.api.localization as api_localization
    import app.api.destinations as api_destinations
    import app.api.composition as api_composition
    import app.api.targets as api_targets

    monkeypatch.setattr(api_layers, "layer_service", lay_svc)
    monkeypatch.setattr(api_sources, "catalog_service", cat_svc)
    monkeypatch.setattr(api_localization, "localization_service", loc_svc)
    monkeypatch.setattr(api_destinations, "destination_service", dest_svc)
    monkeypatch.setattr(api_composition, "RAW_DIR", raw_dir)
    monkeypatch.setattr(api_composition, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(api_composition, "composition_index", comp_idx)
    monkeypatch.setattr(api_composition, "composition_search_service", comp_search)
    monkeypatch.setattr(api_composition, "localization_service", loc_svc)
    monkeypatch.setattr(api_targets, "target_registry", tgt_reg)
    monkeypatch.setattr(api_targets, "composition_search_service", comp_search)
    monkeypatch.setattr(api_targets, "localization_service", loc_svc)

    yield {
        "catalog_dir": catalog_dir,
        "raw_dir": raw_dir,
        "processed_dir": processed_dir,
        "index_dir": index_dir,
        "catalog_service": cat_svc,
        "localization_service": loc_svc,
        "composition_index": comp_idx,
        "target_registry": tgt_reg,
    }


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["engines"]["physics"] == "ready"
        assert data["engines"]["geospatial"] == "ready"
        assert data["engines"]["terrain"] == "ready"


@pytest.mark.asyncio
async def test_no_synthetic_terrain_fallback():
    """Empty processed directory must never return a 30x30 synthetic grid."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/terrain/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["available"] is False
        assert data["summary"] is None
        assert data["unavailable_reason"]

        res_layers = await client.get("/api/terrain/layers")
        assert res_layers.status_code == 200
        assert res_layers.json() == []


@pytest.mark.asyncio
async def test_terrain_point_missing_dem_returns_unavailable():
    """Point inspection without covering DEM returns available=False, elevation_m=None (never 0.0)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/terrain/point?lat=-4.65&lon=137.42")
        assert res.status_code == 200
        data = res.json()
        assert data["available"] is False
        assert data["elevation_m"] is None
        assert data["slope_deg"] is None


@pytest.mark.asyncio
async def test_no_hardcoded_observations_and_real_parsing(isolated_services):
    """When no raw observation products exist, /api/observations returns []; when present, parses cleanly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_empty = await client.get("/api/observations")
        assert res_empty.status_code == 200
        assert res_empty.json() == []

        # Write a realistic ChemCam CSV observation sample without fabricating coordinates
        raw_dir: Path = isolated_services["raw_dir"]
        cat_svc: DatasetCatalogService = isolated_services["catalog_service"]
        chemcam_csv = raw_dir / "cl5_398601105ccs0020000001.csv"
        chemcam_csv.write_text(
            "# ChemCam LIBS calibrated sample\n"
            "# Begin Processed Spectral Data\n"
            "240.1,1.25e12,0.0,0.95e12\n"
            "240.2,1.30e12,0.0,1.02e12\n",
            encoding="utf-8",
        )
        cat_svc.register_dataset(
            Dataset(
                id="msl_chemcam_fixture",
                product_id="CL5_TEST_PSV",
                product_title="Fixture ChemCam LIBS Spectrum",
                product_type="Spectral Observation (PSV CSV)",
                mission="Mars Science Laboratory (MSL)",
                instrument="ChemCam",
                source_archive="NASA PDS Geosciences Node",
                original_product_url="https://example.invalid/chemcam.csv",
                license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
                attribution="NASA/JPL/LANL",
                observation_sol=10,
                processing_level="Calibrated (CCS)",
                calibration_status="Calibrated",
                coverage=GeographicCoverage(
                    min_latitude=-5.0,
                    max_latitude=-4.0,
                    min_longitude=137.0,
                    max_longitude=138.0,
                ),
                units="photons/mm2/sr/um",
                data_format="CSV",
                status=DatasetLifecycleStatus.DOWNLOADED,
                local_file_path=f"raw/{chemcam_csv.name}",
            )
        )
        res_loaded = await client.get("/api/observations")
        assert res_loaded.status_code == 200
        obs = res_loaded.json()
        assert len(obs) == 1
        assert obs[0]["instrument"] == "Chemistry Camera (ChemCam LIBS)"
        assert obs[0]["location"] is None  # Coordinates absent in raw CSV -> preserved as None
        assert obs[0]["measurement_value"]["sampled_channel_count"] == 2

        # Replace with malformed ChemCam file -> gracefully skipped instead of inventing fallback pressure/temp
        chemcam_csv.write_text("header_only\n", encoding="utf-8")
        res_malformed = await client.get("/api/observations")
        assert res_malformed.status_code == 200
        assert res_malformed.json() == []


@pytest.mark.asyncio
async def test_no_fabricated_layers_when_unverified():
    """Undiscovered or unverified/unprocessed datasets must never populate available_layers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/datasets/discover")
        res = await client.get("/api/layers")
        assert res.status_code == 200
        data = res.json()
        assert data["available_layers"] == []
        assert data["total_available"] == 0
        assert data["total_unavailable"] >= 4


@pytest.mark.asyncio
async def test_dataset_validation_and_sources_breakdown():
    """Validation without local file must honestly report missing file & unverified metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/datasets/discover")
        res = await client.post("/api/datasets/mola_megt00n090hb/validate")
        assert res.status_code == 200
        val = res.json()
        assert val["crs_valid"] is True
        assert val["coverage_check"]["is_covered"] is True
        assert val["local_file_present"] is False

        res_sources = await client.get("/api/sources")
        assert res_sources.status_code == 200
        sources = res_sources.json()
        assert len(sources) >= 3
        for s in sources:
            vb = s["verification_breakdown"]
            assert vb["archive_availability"] in {"verified", "unverified", "pending", "unknown", "failed", "not_applicable"}
            assert vb["download_verification"] in {"unverified", "not_applicable"}


@pytest.mark.asyncio
async def test_localization_manual_and_clear_and_validation():
    """Live localization must default unavailable/None; manual entry validates Mars CRS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_init = await client.get("/api/localization/status")
        assert res_init.status_code == 200
        status_data = res_init.json()
        assert status_data["live_localization_available"] is False
        assert status_data["current_position"] is None

        # Reject Earth CRS
        bad_pos = await client.post(
            "/api/localization/manual",
            json={"latitude": -4.65, "longitude": 137.42, "crs": "EPSG:4326"},
        )
        assert bad_pos.status_code == 422

        # Accept Mars CRS manual coordinate
        good_pos = await client.post(
            "/api/localization/manual",
            json={"latitude": -4.65, "longitude": 137.42, "crs": "IAU2000:49900"},
        )
        assert good_pos.status_code == 200
        pos_data = good_pos.json()
        assert pos_data["position_source"] == "manual_selection"
        assert pos_data["latitude"] == pytest.approx(-4.65)

        res_clear = await client.delete("/api/localization")
        assert res_clear.status_code == 200
        res_after = await client.get("/api/localization/status")
        assert res_after.json()["current_position"] is None


@pytest.mark.asyncio
async def test_destination_evaluate_and_composition_search_honesty(isolated_services):
    """
    Destination evaluate strictly enforces coverage_verification == VERIFIED before reporting
    verified coverage, and search-composition returns empty honest state when index is unbuilt.
    """
    cat_svc: DatasetCatalogService = isolated_services["catalog_service"]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/datasets/discover")
        res = await client.post(
            "/api/destinations/evaluate",
            json={"latitude": -4.65, "longitude": 137.42, "label": "Gale Check"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["crs"] == "IAU2000:49900"
        assert data["terrain"]["available"] is False
        assert data["terrain"]["elevation_m"] is None
        # Unverified catalog placeholders must NEVER enter covering_datasets as verified overlap
        assert data["covering_datasets"] == []
        assert len(data["unverified_catalog_candidates"]) >= 1
        assert data["evaluation_status"] == "unverified_catalog_candidates_only"

        # Once a dataset has VERIFIED coverage_verification, it becomes verified coverage with provenance
        ds = cat_svc.get_dataset("mola_megt00n090hb")
        assert ds is not None
        ds.verification.coverage_verification = VerificationState.VERIFIED
        cat_svc.register_dataset(ds)

        res_ver = await client.post(
            "/api/destinations/evaluate",
            json={"latitude": -4.65, "longitude": 137.42, "label": "Gale Verified Check"},
        )
        assert res_ver.status_code == 200
        d_ver = res_ver.json()
        assert len(d_ver["covering_datasets"]) == 1
        assert d_ver["covering_datasets"][0]["coverage_verified"] is True
        assert d_ver["covering_datasets"][0]["footprint_provenance"] is not None

        comp = await client.post("/api/destinations/search-composition", json={"query": "smectite"})
        assert comp.status_code == 200
        cdata = comp.json()
        assert cdata["index_available"] is False
        assert cdata["results"] == []
        assert cdata["total_matches"] == 0


@pytest.mark.asyncio
async def test_processed_dem_pipeline_tiles_and_point_sampling(isolated_services):
    """Process an isolated real GeoTIFF DEM fixture, then verify stats, PNG tiles, and NoData sampling."""
    raw_dir: Path = isolated_services["raw_dir"]
    cat_svc: DatasetCatalogService = isolated_services["catalog_service"]

    dem_file = raw_dir / "fixture_gale_dem.tif"
    rows, cols = np.mgrid[0:20, 0:20]
    elev = (-4500.0 + cols * 5.0).astype(np.float32)
    # Explicit NoData corner patch covering bottom-left cell near (min_lon=137.2, min_lat=-5.5)
    elev[18:20, 0:2] = -9999.0
    transform = from_bounds(137.2, -5.5, 138.0, -4.3, 20, 20)
    with rasterio.open(
        dem_file,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=1,
        dtype="float32",
        crs=MARS_CRS_PROJ4,
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(elev, 1)
        dst.update_tags(1, UNITS="meters")

    ds = Dataset(
        id="fixture_dem_test",
        product_id="FIXTURE_DEM_01",
        product_title="Fixture DEM Test Product",
        product_type="DEM / Elevation",
        mission="Test Mission",
        instrument="Test Altimeter",
        source_archive="Fixture",
        original_product_url="https://example.invalid/fixture.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Test",
        processing_level="Level 3",
        calibration_status="Calibrated",
        coverage=GeographicCoverage(
            min_latitude=-5.5,
            max_latitude=-4.3,
            min_longitude=137.2,
            max_longitude=138.0,
            center_latitude=-4.9,
            center_longitude=137.6,
            longitude_range="137.2..138.0",
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=2300.0,
        units="meters",
        nodata_value=-9999.0,
        data_format="GeoTIFF",
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path=str(dem_file),
        verification=MetadataVerification(
            archive_availability=VerificationState.VERIFIED,
            product_discovery=VerificationState.VERIFIED,
            metadata_verification=VerificationState.VERIFIED,
            license_verification=VerificationState.VERIFIED,
            coverage_verification=VerificationState.VERIFIED,
            download_verification=VerificationState.VERIFIED,
        ),
    )
    cat_svc.register_dataset(ds)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_proc = await client.post("/api/datasets/fixture_dem_test/process")
        assert res_proc.status_code == 200
        proc_data = res_proc.json()
        assert "dem" in proc_data["files"]

        res_sum = await client.get("/api/terrain/summary")
        assert res_sum.status_code == 200
        sdata = res_sum.json()
        assert sdata["available"] is True
        assert sdata["summary"]["source_dem_id"] == "fixture_dem_test"
        assert sdata["summary"]["elevation_stats"]["valid_pixel_count"] == 396  # 400 - 4 NoData cells

        res_layers = await client.get("/api/layers")
        assert res_layers.status_code == 200
        avail = res_layers.json()["available_layers"]
        assert len(avail) == 4

        # Serve real raster PNG tile covering east hemisphere (z=0, x=1, y=0 covers [0..180E])
        elev_layer = next(l for l in avail if l["layer_type"] == "elevation_raster")
        res_tile = await client.get(f"{elev_layer['rendering_endpoint'].replace('{z}/{x}/{y}', '0/1/0')}")
        assert res_tile.status_code == 200
        assert res_tile.headers["content-type"] == "image/png"

        # Valid pixel query near center
        res_valid = await client.get("/api/terrain/point?lat=-4.9&lon=137.6")
        assert res_valid.status_code == 200
        vdata = res_valid.json()
        assert vdata["available"] is True
        assert vdata["elevation_m"] is not None
        assert vdata["slope_deg"] > 0.0

        # NoData corner query near (-5.48, 137.22) -> must NOT become 0.0
        res_nd = await client.get("/api/terrain/point?lat=-5.48&lon=137.22")
        assert res_nd.status_code == 200
        ndata = res_nd.json()
        assert ndata["elevation_m"] is None


@pytest.mark.asyncio
async def test_physics_calculation_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/physics/calculate", json={"model_name": "weight", "mass_kg": 200.0})
        assert res.status_code == 200
        data = res.json()
        assert data["units"] == "N"
        assert abs(data["calculated_value"] - 744.152) < 0.01

        res_bad = await client.post("/api/physics/calculate", json={"model_name": "weight", "mass_kg": -10.0})
        assert res_bad.status_code == 422
