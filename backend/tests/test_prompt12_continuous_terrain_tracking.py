"""
Prompt 12 Adversarial & Regression Verification Suite
Covers:
- Cross-tile continuous normals & global normalized elevation/roughness overlays (zero seam jumps)
- Route provenance block & compare_routes algorithm forwarding
- Authenticated live mission tracking (/api/tracking/*): auth, IAU2000:49900 validation,
  monotonic sequence, Mars-sphere cross-track/off-route math, stale timeout, confirmation-gated replan diff, SSE
- Clean-checkout catalog & layer honesty with empty RAW_DIR / PROCESSED_DIR
- NASA Worldview exclusion, USGS SIM 3292 1:20M metadata, Perseverance Jezero isolation
"""

from __future__ import annotations

import io
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from PIL import Image
from rasterio.transform import from_bounds

from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, GeographicCoverage, LicenseStatus
from app.ingestion.sources.perseverance_gallery import PerseveranceGalleryService
from app.main import app
from app.routing.schemas import (
    PathAlgorithm,
    RouteCompareRequest,
    RouteComputeRequest,
    RouteCoordinateInput,
    RoutePlanningConstraints,
    RoutingMode,
)
from app.routing.service import ScienceAwareRoutingService
from app.schemas.tracking import (
    DISCONNECTED_LIVE_MESSAGE,
    TelemetryFixIngestRequest,
    TrackingReplanPreviewRequest,
)
from app.services.layer_service import LayerCatalogService
from app.services.tracking_service import TrackingService
from app.terrain.mesh import TerrainMeshService


def _build_synthetic_continuous_dem(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    cat_dir = tmp_path / "catalog"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cat_dir.mkdir(parents=True, exist_ok=True)

    dem_path = raw_dir / "smooth_slope_dem.tif"
    rows, cols = 64, 64
    min_lon, min_lat, max_lon, max_lat = 137.400, -4.760, 137.416, -4.744
    y = np.linspace(0.0, 1.0, rows)[:, None]
    x = np.linspace(0.0, 1.0, cols)[None, :]
    # Smooth curved hillslope so gradients vary continuously across tile seams
    elev = -4100.0 + 30.0 * np.sin(x * math.pi * 0.85) + 18.0 * np.cos(y * math.pi * 0.75)

    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, cols, rows)
    with rasterio.open(
        dem_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs=MARS_CRS_DEFINITIONS["IAU2000:49900"],
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(elev.astype(np.float32), 1)

    catalog = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
    ds = Dataset(
        id="synth_seam_dem",
        product_id="SYNTH_SEAM_01",
        product_title="Synthetic Smooth Slope Seam Test DEM",
        product_type="DEM",
        mission="TEST",
        instrument="SYNTH",
        source_archive="Synthetic Test",
        original_product_url="https://example.invalid/smooth_slope_dem.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Synthetic Unit Test",
        coverage=GeographicCoverage(
            min_latitude=min_lat,
            max_latitude=max_lat,
            min_longitude=min_lon,
            max_longitude=max_lon,
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=14.8,
        units="meters",
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path=str(dem_path),
    )
    catalog.register_dataset(ds)
    return raw_dir, cat_dir, catalog, ds


def test_cross_tile_normals_and_elevation_color_continuity(tmp_path: Path):
    """
    Prompt 12 Part 2: Adjacent tiles MUST have matching vertex normals along shared edges
    (zero facet discontinuity / lighting crease) AND global vmin/vmax color normalization.
    """
    raw_dir, _, catalog, ds = _build_synthetic_continuous_dem(tmp_path)
    mesh_svc = TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)
    manifest = mesh_svc.get_mesh_manifest(dataset_id=ds.id)

    assert manifest.elevation_range_m is not None
    assert "min_m" in manifest.elevation_range_m and "max_m" in manifest.elevation_range_m
    vmin = float(manifest.elevation_range_m["min_m"])
    vmax = float(manifest.elevation_range_m["max_m"])

    # LOD 1 has a 2x2 grid of tiles
    tile_w = next(t for t in manifest.tiles if t.tile_id == "L1_R0_C0")
    tile_e = next(t for t in manifest.tiles if t.tile_id == "L1_R0_C1")
    tile_s = next(t for t in manifest.tiles if t.tile_id == "L1_R1_C0")

    def _load(t):
        return mesh_svc.get_mesh_tile(
            t.tile_id,
            dataset_id=ds.id,
            min_lat=manifest.requested_bounds["min_lat"],
            max_lat=manifest.requested_bounds["max_lat"],
            min_lon=manifest.requested_bounds["min_lon"],
            max_lon=manifest.requested_bounds["max_lon"],
            origin_lat=manifest.origin["lat"],
            origin_lon_east=manifest.origin["lon_east"],
            grid_size=t.grid_rows,
        )

    west = _load(tile_w)
    east = _load(tile_e)
    south = _load(tile_s)

    assert west.normals is not None and len(west.normals) == len(west.elevations_m) * 3
    assert east.normals is not None and len(east.normals) == len(east.elevations_m) * 3

    # Verify West tile right column normals == East tile left column normals
    rows, cols = west.grid_rows, west.grid_cols
    max_normal_diff = 0.0
    max_elev_diff = 0.0
    for r in range(rows):
        idx_w = r * cols + (cols - 1)
        idx_e = r * east.grid_cols + 0
        ew = west.elevations_m[idx_w]
        ee = east.elevations_m[idx_e]
        assert ew is not None and ee is not None
        max_elev_diff = max(max_elev_diff, abs(ew - ee))
        for k in range(3):
            nw = west.normals[idx_w * 3 + k]
            ne = east.normals[idx_e * 3 + k]
            max_normal_diff = max(max_normal_diff, abs(nw - ne))

    assert max_elev_diff < 1e-4, f"Shared E/W border elevation mismatch: {max_elev_diff}"
    assert max_normal_diff < 1e-3, f"Shared E/W border normal discontinuity: {max_normal_diff}"

    # Verify North tile bottom row normals == South tile top row normals
    assert south.normals is not None
    for c in range(cols):
        idx_n = (rows - 1) * cols + c
        idx_s = 0 * south.grid_cols + c
        for k in range(3):
            assert abs(west.normals[idx_n * 3 + k] - south.normals[idx_s * 3 + k]) < 1e-3

    # Verify global vmin/vmax texture shading across adjacent tile border matches identically
    tile_w = next(t for t in manifest.tiles if t.tile_id == "L1_R0_C0")
    tile_e = next(t for t in manifest.tiles if t.tile_id == "L1_R0_C1")
    png_w = mesh_svc.render_region_texture_png(
        ds.id,
        "elevation",
        tile_w.bounds["min_lat"],
        tile_w.bounds["max_lat"],
        tile_w.bounds["min_lon"],
        tile_w.bounds["max_lon"],
        size=128,
        vmin=vmin,
        vmax=vmax,
    )
    png_e = mesh_svc.render_region_texture_png(
        ds.id,
        "elevation",
        tile_e.bounds["min_lat"],
        tile_e.bounds["max_lat"],
        tile_e.bounds["min_lon"],
        tile_e.bounds["max_lon"],
        size=128,
        vmin=vmin,
        vmax=vmax,
    )
    arr_w = np.asarray(Image.open(io.BytesIO(png_w)).convert("RGB"), dtype=np.int16)
    arr_e = np.asarray(Image.open(io.BytesIO(png_e)).convert("RGB"), dtype=np.int16)
    # Right edge column of west tile and left edge column of east tile must align closely
    border_color_diff = float(np.mean(np.abs(arr_w[:, -1, :] - arr_e[:, 0, :])))
    assert border_color_diff < 3.0, f"Border color jump across global ramp: {border_color_diff}"


def test_route_provenance_and_compare_algorithm_forwarding(tmp_path: Path):
    """
    Prompt 12 Part 4/6: RouteComputeResponse includes full provenance dictionary,
    and compare_routes forwards requested algorithm (e.g. dijkstra vs astar).
    """
    raw_dir, _, catalog, ds = _build_synthetic_continuous_dem(tmp_path)
    routing_svc = ScienceAwareRoutingService(catalog_service=catalog, raw_dir=raw_dir)
    start = RouteCoordinateInput(lat=-4.756, lon_east=137.403, label="Start A")
    dest = RouteCoordinateInput(lat=-4.748, lon_east=137.412, label="Dest B")

    cmp_res = routing_svc.compare_routes(
        RouteCompareRequest(
            dataset_id=ds.id,
            start=start,
            destination=dest,
            algorithm=PathAlgorithm.DIJKSTRA,
            constraints=RoutePlanningConstraints(max_slope_deg=25.0, walking_speed_m_per_s=None),
        )
    )
    feasible_routes = [e.route for e in cmp_res.comparison if e.feasible and e.route is not None]
    assert len(feasible_routes) >= 2
    for rt in feasible_routes:
        assert rt.algorithm == PathAlgorithm.DIJKSTRA
        assert isinstance(rt.provenance, dict)
        assert rt.provenance["crs"] == "IAU2000:49900"
        assert rt.provenance["dem_dataset_id"] == ds.id
        assert "None" in rt.provenance["safety_certification"]


def test_authenticated_live_tracking_lifecycle_and_replan_preview(tmp_path: Path):
    """
    Prompt 12 Part 5: Authenticated telemetry ingest, strict IAU2000:49900 + monotonic seq validation,
    Mars-sphere cross-track/off-route error, stale timeout, and confirmation-gated replan diff.
    """
    raw_dir, _, catalog, ds = _build_synthetic_continuous_dem(tmp_path)
    routing_svc = ScienceAwareRoutingService(catalog_service=catalog, raw_dir=raw_dir)
    route = routing_svc.compute_route(
        RouteComputeRequest(
            dataset_id=ds.id,
            start=RouteCoordinateInput(lat=-4.752, lon_east=137.403, label="Alpha"),
            destination=RouteCoordinateInput(lat=-4.752, lon_east=137.412, label="Beta"),
            mode=RoutingMode.BALANCED,
            constraints=RoutePlanningConstraints(max_slope_deg=25.0),
        )
    )

    # 1. Default disconnected honesty (no ingest token configured -> disabled for ingest too)
    svc_unconfigured = TrackingService(routing_service=routing_svc, ingest_token="")
    st0 = svc_unconfigured.get_status()
    assert st0.status == "disconnected"
    assert st0.live_available is False
    assert st0.is_simulation is False
    assert st0.message == DISCONNECTED_LIVE_MESSAGE

    ok, code, _ = svc_unconfigured.verify_ingest_auth("Bearer any", None)
    assert not ok and code == 403

    # 2. Configured token authentication checks
    svc = TrackingService(routing_service=routing_svc, ingest_token="secret-dsn-token")
    ok_missing, code_missing, _ = svc.verify_ingest_auth(None, None)
    assert not ok_missing and code_missing == 401
    ok_wrong, code_wrong, _ = svc.verify_ingest_auth("Bearer wrong-tok", None)
    assert not ok_wrong and code_wrong == 403
    ok_valid, code_valid, _ = svc.verify_ingest_auth("Bearer secret-dsn-token", None)
    assert ok_valid and code_valid == 200

    base_now = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 3. Validation rejections: browser GPS, Earth CRS, West-negative lon
    with pytest.raises(ValueError, match="prohibited"):
        svc.ingest_fix(
            TelemetryFixIngestRequest(
                provider_id="navigator.geolocation",
                sequence_number=1,
                timestamp_utc=base_now,
                crs="IAU2000:49900",
                lat=-4.752,
                lon_east=137.404,
            ),
            now_utc=base_now,
        )
    with pytest.raises(ValueError, match="IAU2000:49900"):
        svc.ingest_fix(
            TelemetryFixIngestRequest(
                provider_id="dsn_nav",
                sequence_number=1,
                timestamp_utc=base_now,
                crs="EPSG:4326",
                lat=-4.752,
                lon_east=137.404,
            ),
            now_utc=base_now,
        )
    with pytest.raises(ValueError, match="East-positive"):
        svc.ingest_fix(
            TelemetryFixIngestRequest(
                provider_id="dsn_nav",
                sequence_number=1,
                timestamp_utc=base_now,
                crs="IAU2000:49900",
                lat=-4.752,
                lon_east=-222.5,
            ),
            now_utc=base_now,
        )

    # 4. Ingest valid on-route fix seq 1 & consecutive fix seq 2 (azimuth ~90 deg East)
    st1 = svc.ingest_fix(
        TelemetryFixIngestRequest(
            provider_id="dsn_surface_beacon",
            sequence_number=1,
            timestamp_utc=base_now,
            crs="IAU2000:49900",
            lat=route.vertices[0].lat,
            lon_east=route.vertices[0].lon_east,
            active_route_id=route.route_id,
            corridor_threshold_m=20.0,
            stale_after_seconds=30.0,
        ),
        now_utc=base_now,
    )
    assert st1.status == "live" and st1.live_available is True
    assert st1.route_relative is not None
    assert st1.route_relative.cross_track_error_m < 2.0
    assert st1.route_relative.off_route is False

    # Duplicate sequence must fail with LookupError (mapped to 409 Conflict in HTTP API)
    with pytest.raises(LookupError, match="Out-of-order"):
        svc.ingest_fix(
            TelemetryFixIngestRequest(
                provider_id="dsn_surface_beacon",
                sequence_number=1,
                timestamp_utc=base_now + timedelta(seconds=2),
                crs="IAU2000:49900",
                lat=-4.752,
                lon_east=137.405,
            ),
            now_utc=base_now + timedelta(seconds=2),
        )

    # 5. Off-route excursion (shift ~120 m North -> cross_track_error_m > 20 m threshold)
    st2 = svc.ingest_fix(
        TelemetryFixIngestRequest(
            provider_id="dsn_surface_beacon",
            sequence_number=2,
            timestamp_utc=base_now + timedelta(seconds=5),
            crs="IAU2000:49900",
            lat=-4.750,
            lon_east=137.406,
            active_route_id=route.route_id,
            corridor_threshold_m=20.0,
            stale_after_seconds=30.0,
        ),
        now_utc=base_now + timedelta(seconds=5),
    )
    assert st2.heading_deg is not None
    assert st2.route_relative is not None
    assert st2.route_relative.cross_track_error_m > 50.0
    assert st2.route_relative.off_route is True

    # 6. Confirmation-gated replan preview (does NOT overwrite original route)
    replan = svc.preview_replan_from_live_fix(
        TrackingReplanPreviewRequest(active_route_id=route.route_id),
        now_utc=base_now + timedelta(seconds=6),
    )
    assert replan.requires_user_confirmation is True
    assert replan.coverage_verified is True
    assert replan.previous_route_id == route.route_id
    assert replan.proposed_route.route_id != route.route_id
    # Original cached route unchanged
    assert routing_svc.get_route(route.route_id).route_id == route.route_id

    # 7. Stale timeout after 45 seconds without a fix (> 30s threshold)
    st_stale = svc.get_status(
        active_route_id=route.route_id,
        now_utc=base_now + timedelta(seconds=45),
    )
    assert st_stale.status == "stale"
    assert st_stale.live_available is False


def test_clean_checkout_empty_raw_and_processed_honesty(tmp_path: Path):
    """
    Prompt 12 Part 1.2: Simulated clean git checkout with tracked catalog JSONs pointing to
    absent raw/processed binaries must demote missing files cleanly without mutating tracked JSONs.
    """
    repo_root = tmp_path / "clean_repo"
    cat_dir = repo_root / "datasets" / "catalog"
    raw_dir = repo_root / "datasets" / "raw"
    proc_dir = repo_root / "datasets" / "processed"
    cat_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    proc_dir.mkdir(parents=True)

    sample_catalog = {
        "id": "hirise_dteec_missing",
        "product_id": "DTEEC_MISSING",
        "product_title": "Clean Checkout Test DEM",
        "product_type": "DEM",
        "mission": "MRO",
        "instrument": "HiRISE",
        "source_archive": "HiRISE PDS",
        "original_product_url": "https://example.invalid/missing.img",
        "license": LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN.value,
        "attribution": "NASA/JPL",
        "coverage": {
            "min_latitude": -4.8,
            "max_latitude": -4.6,
            "min_longitude": 137.3,
            "max_longitude": 137.5,
        },
        "coordinate_reference_system": "IAU2000:49900",
        "horizontal_resolution_meters": 1.0,
        "units": "meters",
        "status": "processed",
        "local_file_path": "datasets/raw/nonexistent.img",
        "processed_file_path": "datasets/processed/nonexistent.tif",
    }
    json_path = cat_dir / "hirise_dteec_missing.json"
    original_text = json.dumps(sample_catalog, indent=2)
    json_path.write_text(original_text, encoding="utf-8")

    catalog = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
    loaded = catalog.get_dataset("hirise_dteec_missing")
    assert loaded is not None
    # Missing files reconciled in memory -> not downloadable/renderable
    assert loaded.local_file_path is None
    assert loaded.processed_file_path is None
    assert loaded.status == DatasetLifecycleStatus.DISCOVERED
    # Tracked catalog JSON file on disk MUST remain completely unmutated!
    assert json_path.read_text(encoding="utf-8") == original_text

    layer_svc = LayerCatalogService(catalog_service=catalog, processed_dir=proc_dir, raw_dir=raw_dir)
    layer_catalog = layer_svc.build_layer_catalog()
    assert not any(layer.layer_id.startswith("dem_elevation") for layer in layer_catalog.available_layers)


def test_http_tracking_endpoints_sources_audit_and_perseverance_isolation():
    """
    Verify /api/tracking/* HTTP auth & validation, /api/sources/audit (NASA Worldview exclusion &
    USGS SIM 3292 scale disclosure), and /api/imagery/perseverance strict Jezero isolation.
    """
    client = TestClient(app)

    # Disconnected live status by default
    res_status = client.get("/api/tracking/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "disconnected"
    assert res_status.json()["message"] == DISCONNECTED_LIVE_MESSAGE

    # Sources audit (all 5 challenge sources)
    res_audit = client.get("/api/sources/audit")
    assert res_audit.status_code == 200
    audit_body = res_audit.json()
    by_id = {s["id"]: s for s in audit_body["sources"]}
    assert by_id["nasa_worldview"]["status"] == "excluded_no_mars_dataset"
    assert by_id["nasa_worldview"]["included_in_mars_pipeline"] is False
    assert "1:20,000,000" in by_id["usgs_planetary_geologic_mapping"]["scale"]
    assert by_id["perseverance_raw_images_gallery"]["isolated_from_gale_planning"] is True
    assert "Mars_MGS_TES_Albedo_mosaic_global_7410m" in by_id["jpl_mars_trek"]["layers"]

    # SSE stream emits initial tracking_status frame cleanly
    with client.stream("GET", "/api/tracking/stream") as sse:
        assert sse.status_code == 200
        lines = []
        for raw_line in sse.iter_lines():
            lines.append(raw_line)
            if raw_line.startswith("data:"):
                break
        data_line = next(line for line in lines if line.startswith("data:"))
        parsed = json.loads(data_line.split("data:", 1)[1].strip())
        assert parsed["status"] == "disconnected"


@pytest.mark.asyncio
async def test_perseverance_gallery_mocked_isolation():
    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "total_results": 1,
                "images": [
                    {
                        "imageid": "SI2_2031_0847292_TEST",
                        "sol": 2031,
                        "title": "Sol 2031: SuperCam Remote Micro-Imager",
                        "caption": "Jezero Crater delta outcrop",
                        "date_taken_utc": "2026-11-10T10:00:00Z",
                        "camera": {"instrument": "SUPERCAM_RMI", "filter_name": "UNK"},
                        "image_files": {"medium": "https://mars.nasa.gov/test_med.jpg"},
                    }
                ],
            }

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _FakeResp()

    data = await PerseveranceGalleryService.fetch_raw_images(
        sol=2031,
        camera="SUPERCAM_RMI",
        limit=3,
        client_factory=lambda: _FakeClient(),
    )
    assert data["status"] == "available"
    assert data["site"] == "Jezero Crater"
    assert data["isolated_from_gale_planning"] is True
    assert len(data["images"]) == 1
    assert data["images"][0]["isolated_from_gale_planning"] is True
    assert data["images"][0]["camera_instrument"] == "SUPERCAM_RMI"
