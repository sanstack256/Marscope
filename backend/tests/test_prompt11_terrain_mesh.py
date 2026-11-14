"""
Synthetic unit tests for Prompt 11 3D Terrain Mesh Service:
- Hierarchical LOD manifest & tile slicing
- Bit-identical shared edge vertices across adjacent LOD tiles (no tearing/seams)
- Omitted NoData vertex mask & elevations_m=None
- Local East/North metric scaling under IAU 2000 Mars equatorial radius
- Cesium HeightGrid row-major ordering & PNG overlay texture generation
- Strict input validation & missing dataset error handling

Note: All tests here run exclusively on synthetic GeoTIFF fixtures inside tmp_path.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from app.geospatial.crs import MARS_CRS_DEFINITIONS
from app.ingestion.catalog import DatasetCatalogService
from app.schemas.dataset import Dataset, DatasetLifecycleStatus, GeographicCoverage, LicenseStatus
from app.terrain.mesh import TerrainMeshService


def _create_synthetic_dem_catalog(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    cat_dir = tmp_path / "catalog"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cat_dir.mkdir(parents=True, exist_ok=True)

    dem_path = raw_dir / "synth_dem.tif"
    rows, cols = 128, 128
    min_lon, min_lat, max_lon, max_lat = 137.390, -4.750, 137.410, -4.730

    yy, xx = np.mgrid[0:rows, 0:cols]
    elev = (-4500.0 + 0.35 * xx + 0.25 * yy + 8.0 * np.sin(xx / 10.0)).astype(np.float32)
    # Introduce a clear diagonal NoData wedge in the SW corner
    elev[96:, :32] = np.nan

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
        dst.write(elev, 1)

    catalog = DatasetCatalogService(catalog_storage_dir=cat_dir, raw_data_dir=raw_dir)
    ds = Dataset(
        id="synth_gale_dem",
        product_id="SYNTH_DEM_01",
        product_title="Synthetic Gale Crater Test DEM",
        product_type="DEM",
        mission="TEST",
        instrument="SYNTH",
        source_archive="Synthetic Test Fixture",
        original_product_url="https://example.invalid/synth_dem.tif",
        license=LicenseStatus.VERIFIED_OPEN_PUBLIC_DOMAIN,
        attribution="Synthetic Unit Test Fixture",
        coverage=GeographicCoverage(
            min_latitude=min_lat,
            max_latitude=max_lat,
            min_longitude=min_lon,
            max_longitude=max_lon,
        ),
        coordinate_reference_system="IAU2000:49900",
        horizontal_resolution_meters=9.25,
        units="meters",
        status=DatasetLifecycleStatus.DOWNLOADED,
        local_file_path=str(dem_path),
    )
    catalog.register_dataset(ds)
    return TerrainMeshService(catalog_service=catalog, raw_dir=raw_dir)


def test_mesh_manifest_and_lod_levels(tmp_path: Path):
    svc = _create_synthetic_dem_catalog(tmp_path)
    manifest = svc.get_mesh_manifest(dataset_id="synth_gale_dem", max_lod=2, tile_grid_size=33)

    assert manifest.dataset_id == "synth_gale_dem"
    assert manifest.product_id == "SYNTH_DEM_01"
    assert len(manifest.lod_levels) == 3  # LOD 0, 1, 2
    assert manifest.lod_levels[0].tiles_x == 1 and manifest.lod_levels[0].tiles_y == 1
    assert manifest.lod_levels[1].tiles_x == 2 and manifest.lod_levels[1].tiles_y == 2
    assert manifest.lod_levels[2].tiles_x == 4 and manifest.lod_levels[2].tiles_y == 4
    assert manifest.physical_extent_m["width_m"] > 800.0
    assert manifest.physical_extent_m["height_m"] > 800.0


def test_adjacent_lod_tiles_share_exact_seam_vertices(tmp_path: Path):
    svc = _create_synthetic_dem_catalog(tmp_path)
    origin_lat = -4.740
    origin_lon = 137.400

    # Adjacent horizontal neighbors at LOD 1 (Row 0, Col 0 vs Col 1)
    t_west = svc.get_mesh_tile(
        tile_id="L1_R0_C0",
        dataset_id="synth_gale_dem",
        origin_lat=origin_lat,
        origin_lon_east=origin_lon,
        grid_size=33,
    )
    t_east = svc.get_mesh_tile(
        tile_id="L1_R0_C1",
        dataset_id="synth_gale_dem",
        origin_lat=origin_lat,
        origin_lon_east=origin_lon,
        grid_size=33,
    )

    assert t_west.bounds["max_lon"] == pytest.approx(t_east.bounds["min_lon"], abs=1e-9)
    assert t_west.local_bounds_m["max_east_m"] == pytest.approx(
        t_east.local_bounds_m["min_east_m"], abs=1e-3
    )

    # Every boundary row along the shared E-W meridian seam must be bit-identical
    rows = t_west.grid_rows
    cols = t_west.grid_cols
    for r in range(rows):
        w_edge_idx = r * cols + (cols - 1)
        e_edge_idx = r * cols + 0
        assert t_west.valid_mask[w_edge_idx] == t_east.valid_mask[e_edge_idx]
        assert t_west.elevations_m[w_edge_idx] == t_east.elevations_m[e_edge_idx]

    # Adjacent vertical neighbors (Row 0 vs Row 1) along shared North-South parallel
    t_south = svc.get_mesh_tile(
        tile_id="L1_R1_C0",
        dataset_id="synth_gale_dem",
        origin_lat=origin_lat,
        origin_lon_east=origin_lon,
        grid_size=33,
    )
    for c in range(cols):
        top_bottom_idx = (rows - 1) * cols + c
        bot_top_idx = 0 * cols + c
        assert t_west.valid_mask[top_bottom_idx] == t_south.valid_mask[bot_top_idx]
        assert t_west.elevations_m[top_bottom_idx] == t_south.elevations_m[bot_top_idx]


def test_nodata_vertices_are_explicitly_masked(tmp_path: Path):
    svc = _create_synthetic_dem_catalog(tmp_path)
    # Row 1 Col 0 covers SW quadrant where nodata wedge exists
    tile = svc.get_mesh_tile(
        tile_id="L1_R1_C0",
        dataset_id="synth_gale_dem",
        grid_size=33,
    )
    assert tile.nodata_vertex_count > 0
    assert tile.valid_vertex_count > 0
    assert tile.nodata_vertex_count + tile.valid_vertex_count == tile.grid_rows * tile.grid_cols
    for mask_bit, z_val in zip(tile.valid_mask, tile.elevations_m):
        if mask_bit == 0:
            assert z_val is None
        else:
            assert z_val is not None


def test_heightgrid_and_overlay_png_outputs(tmp_path: Path):
    svc = _create_synthetic_dem_catalog(tmp_path)
    hg = svc.get_heightgrid(
        min_lat=-4.745,
        max_lat=-4.735,
        min_lon=137.395,
        max_lon=137.405,
        dataset_id="synth_gale_dem",
        grid_size=17,
    )
    assert hg.grid_rows == 17 and hg.grid_cols == 17
    assert len(hg.elevations_m) == 17 * 17
    assert hg.available is True
    assert hg.valid_fraction > 0.0

    for overlay in ("elevation", "slope", "roughness"):
        png = svc.render_region_texture_png(
            dataset_id="synth_gale_dem",
            overlay=overlay,
            min_lat=-4.745,
            max_lat=-4.735,
            min_lon=137.395,
            max_lon=137.405,
            size=64,
        )
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png) > 100


def test_mesh_invalid_requests_raise_honest_errors(tmp_path: Path):
    svc = _create_synthetic_dem_catalog(tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.get_mesh_manifest(dataset_id="nonexistent_dem")
    with pytest.raises(ValueError):
        svc.get_mesh_manifest(
            dataset_id="synth_gale_dem",
            min_lat=-4.73,
            max_lat=-4.75,
            min_lon=137.39,
            max_lon=137.41,
        )
    with pytest.raises(ValueError):
        svc.get_mesh_tile(tile_id="BAD_TILE_FORMAT", dataset_id="synth_gale_dem")
