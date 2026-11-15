"""
MARSCOPE Multi-Scale Terrain Derivatives & Morphology Analyzer
Martian Surface Intelligence & Exploration System

Derives scientifically traceable multi-scale terrain metrics from real NASA DEMs:
- Physical slope (degrees) and aspect (degrees clockwise from North)
- Multi-scale TRI (fine 5.0 m and medium 15.0 m physical radii)
- Terrain Position Index (TPI) and Local Relief over explicit metric windows
- Evans (1979) 3x3 profile and planform curvature (1/m)
- Spatial coverage & no-data fraction

All metrics enforce strict no-data propagation and resolution compatibility.
Mathematical landform metrics are never automatically interpreted as geological discoveries.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field
import rasterio
from rasterio.vrt import WarpedVRT

from app.geospatial.crs import MARS_EQUATORIAL_RADIUS_M, normalize_longitude_360
from app.ingestion.catalog import DatasetCatalogService
from app.ingestion.pds_label import extract_pds3_metadata
from app.mobility.coverage import _resolve_raw_dem_open_path
from app.science.provenance_graph import (
    ProvenanceDependencyGraph,
    ProvenanceStep,
    ScientificDataClassification,
)
from app.terrain.aspect import calculate_aspect
from app.terrain.mesh import MARS_GEOG_CRS
from app.terrain.roughness import calculate_roughness_tri_with_metadata
from app.terrain.slope import calculate_slope


class MultiScaleMetricEntry(BaseModel):
    metric_name: str
    value: Optional[float] = None
    units: str
    classification: ScientificDataClassification
    physical_radius_m: Optional[float] = None
    actual_window_dimensions_m: Optional[Dict[str, float]] = None
    native_resolution_m: float
    processing_resolution_m: float
    status: str  # "valid" | "nodata" | "resolution_limited"
    reason: Optional[str] = None


class MultiScaleTerrainResponse(BaseModel):
    available: bool
    dataset_id: Optional[str] = None
    product_id: Optional[str] = None
    latitude: float
    longitude_east: float
    crs: str = "IAU2000:49900"
    vertical_datum: str = "MOLA_AREOID"
    elevation_m: Optional[float] = None
    slope_deg: Optional[float] = None
    aspect_deg: Optional[float] = None
    profile_curvature_inv_m: Optional[float] = None
    planform_curvature_inv_m: Optional[float] = None
    surface_normal_enu: Optional[Dict[str, float]] = None
    elevation_variability_m: Optional[MultiScaleMetricEntry] = None
    terrain_observability: Optional[str] = None
    native_resolution_m: Optional[float] = None
    tri_fine_m: Optional[MultiScaleMetricEntry] = None
    tri_medium_m: Optional[MultiScaleMetricEntry] = None
    tpi_m: Optional[MultiScaleMetricEntry] = None
    local_relief_m: Optional[MultiScaleMetricEntry] = None
    valid_coverage_fraction: float = 0.0
    unavailable_reason: Optional[str] = None
    provenance_graph: Optional[ProvenanceDependencyGraph] = None


def analyze_multiscale_terrain_point(
    *,
    catalog_service: DatasetCatalogService,
    raw_dir: Any,
    lat: float,
    lon_east: float,
    dataset_id: Optional[str] = None,
    fine_radius_m: float = 5.0,
    medium_radius_m: float = 15.0,
    relief_radius_m: float = 10.0,
) -> MultiScaleTerrainResponse:
    """Compute traceable multi-scale terrain derivatives centered at (lat, lon_east)."""
    from app.terrain.mesh import TerrainMeshService

    mesh_svc = TerrainMeshService(catalog_service=catalog_service, raw_dir=raw_dir)
    try:
        ds = mesh_svc.resolve_dataset(dataset_id)
    except FileNotFoundError as exc:
        return MultiScaleTerrainResponse(
            available=False,
            latitude=lat,
            longitude_east=normalize_longitude_360(lon_east),
            unavailable_reason=str(exc),
        )

    open_path, lbl_path = _resolve_raw_dem_open_path(ds, raw_dir)
    if not open_path.exists():
        return MultiScaleTerrainResponse(
            available=False,
            dataset_id=ds.id,
            product_id=ds.product_id,
            latitude=lat,
            longitude_east=normalize_longitude_360(lon_east),
            unavailable_reason=f"DEM file missing locally for '{ds.id}'.",
        )

    lbl_meta = extract_pds3_metadata(lbl_path) if (lbl_path and lbl_path.exists()) else {}
    lon_norm = normalize_longitude_360(lon_east)

    def _compute_with_reader(reader: Any) -> MultiScaleTerrainResponse:
        nodata_val = reader.nodata
        if nodata_val is None and lbl_meta.get("missing_constant") is not None:
            try:
                nodata_val = float(lbl_meta["missing_constant"])
            except (TypeError, ValueError):
                nodata_val = -32768.0
        elif nodata_val is None:
            nodata_val = -32768.0

        rb = reader.bounds
        q_lon = lon_norm - 360.0 if (rb.right <= 180.0 and lon_norm > 180.0) else lon_norm
        if rb.right > 180.0 and q_lon < 0.0:
            q_lon += 360.0

        if q_lon < rb.left or q_lon > rb.right or lat < rb.bottom or lat > rb.top:
            return MultiScaleTerrainResponse(
                available=False,
                dataset_id=ds.id,
                product_id=ds.product_id,
                latitude=lat,
                longitude_east=lon_norm,
                unavailable_reason="Coordinate lies outside DEM footprint.",
            )

        m_per_deg_lat = MARS_EQUATORIAL_RADIUS_M * math.pi / 180.0
        m_per_deg_lon = MARS_EQUATORIAL_RADIUS_M * math.cos(math.radians(lat)) * math.pi / 180.0
        dx_m = abs(float(reader.transform.a)) * m_per_deg_lon
        dy_m = abs(float(reader.transform.e)) * m_per_deg_lat
        native_res_m = float(ds.horizontal_resolution_meters or 0.5 * (dx_m + dy_m))

        max_rad = max(fine_radius_m, medium_radius_m, relief_radius_m)
        pad_px = max(4, int(math.ceil(max_rad / min(dx_m, dy_m))) + 3)

        inv_t = ~reader.transform
        c_center = int(round(inv_t.a * q_lon + inv_t.b * lat + inv_t.c - 0.5))
        r_center = int(round(inv_t.d * q_lon + inv_t.e * lat + inv_t.f - 0.5))

        if (
            c_center < 0
            or c_center >= reader.width
            or r_center < 0
            or r_center >= reader.height
        ):
            return MultiScaleTerrainResponse(
                available=False,
                dataset_id=ds.id,
                product_id=ds.product_id,
                latitude=lat,
                longitude_east=lon_norm,
                unavailable_reason="Coordinate lies outside raster pixel grid.",
            )

        c0 = max(0, c_center - pad_px)
        c1 = min(reader.width, c_center + pad_px + 1)
        r0 = max(0, r_center - pad_px)
        r1 = min(reader.height, r_center + pad_px + 1)

        win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        patch = reader.read(1, window=win).astype(np.float64)
        valid_mask = np.isfinite(patch) & (patch != float(nodata_val)) & (patch > -32000.0)
        patch_clean = np.where(valid_mask, patch, np.nan)
        nodata_mask = ~valid_mask

        lr = r_center - r0
        lc = c_center - c0
        elev_val = float(patch_clean[lr, lc]) if np.isfinite(patch_clean[lr, lc]) else None
        cov_frac = round(float(np.count_nonzero(valid_mask)) / float(max(1, patch.size)), 4)

        if elev_val is None:
            return MultiScaleTerrainResponse(
                available=False,
                dataset_id=ds.id,
                product_id=ds.product_id,
                latitude=lat,
                longitude_east=lon_norm,
                valid_coverage_fraction=cov_frac,
                unavailable_reason="Center DEM pixel is NO-DATA.",
            )

        slope_arr, _ = calculate_slope(patch_clean, dx_m, dy_m, nodata_mask=nodata_mask)
        aspect_arr = calculate_aspect(patch_clean, dx_m, dy_m, nodata_mask=nodata_mask)
        slope_val = round(float(slope_arr[lr, lc]), 3) if np.isfinite(slope_arr[lr, lc]) else None
        a_raw = float(aspect_arr[lr, lc]) if np.isfinite(aspect_arr[lr, lc]) else None
        aspect_val = None if (a_raw is None or a_raw == -1.0) else round(a_raw, 3)

        # Evans (1979) 3x3 curvature + ENU surface normal + local elevation variability when 3x3 valid
        prof_curv: Optional[float] = None
        plan_curv: Optional[float] = None
        surf_normal: Optional[Dict[str, float]] = None
        elev_var_entry: Optional[MultiScaleMetricEntry] = None
        if 1 <= lr < patch_clean.shape[0] - 1 and 1 <= lc < patch_clean.shape[1] - 1:
            nb = patch_clean[lr - 1 : lr + 2, lc - 1 : lc + 2]
            if np.all(np.isfinite(nb)):
                z1, z2, z3 = nb[0, 0], nb[0, 1], nb[0, 2]
                z4, z5, z6 = nb[1, 0], nb[1, 1], nb[1, 2]
                z7, z8, z9 = nb[2, 0], nb[2, 1], nb[2, 2]
                L = 0.5 * (dx_m + dy_m)
                p = ((z3 + z6 + z9) - (z1 + z4 + z7)) / (6.0 * L)
                q = ((z1 + z2 + z3) - (z7 + z8 + z9)) / (6.0 * L)
                n_den = math.sqrt(p * p + q * q + 1.0)
                surf_normal = {
                    "nx_east": round(float(-p / n_den), 5),
                    "ny_north": round(float(-q / n_den), 5),
                    "nz_up": round(float(1.0 / n_den), 5),
                }
                elev_var_entry = MultiScaleMetricEntry(
                    metric_name="Elevation Variability (3x3 std)",
                    value=round(float(np.std(nb)), 4),
                    units="meters",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    actual_window_dimensions_m={"width_m": round(3.0 * dx_m, 3), "height_m": round(3.0 * dy_m, 3)},
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="valid",
                )
                r_c = (z1 + z3 + z4 + z6 + z7 + z9 - 2.0 * (z2 + z5 + z8)) / (3.0 * L * L)
                t_c = (z1 + z2 + z3 + z7 + z8 + z9 - 2.0 * (z4 + z5 + z6)) / (3.0 * L * L)
                s_c = (z3 + z7 - z1 - z9) / (4.0 * L * L)
                pq2 = p * p + q * q
                if pq2 > 1e-12:
                    prof_curv = round(
                        float(-(r_c * p * p + 2.0 * s_c * p * q + t_c * q * q) / (pq2 * (1.0 + pq2) ** 1.5)),
                        6,
                    )
                    plan_curv = round(
                        float(-(r_c * q * q - 2.0 * s_c * p * q + t_c * p * p) / (pq2 ** 1.5)),
                        6,
                    )

        def _eval_tri(radius_m: float, name: str) -> MultiScaleMetricEntry:
            try:
                tri_arr, tri_meta = calculate_roughness_tri_with_metadata(
                    patch_clean,
                    dx_m,
                    dy_m,
                    nodata_mask=nodata_mask,
                    neighborhood_radius_meters=radius_m,
                    source_product_id=ds.product_id,
                    native_resolution_m=native_res_m,
                )
                val = float(tri_arr[lr, lc]) if np.isfinite(tri_arr[lr, lc]) else None
                return MultiScaleMetricEntry(
                    metric_name=name,
                    value=round(val, 4) if val is not None else None,
                    units="meters",
                    classification=(
                        ScientificDataClassification.MARSCOPE_DERIVED
                        if val is not None
                        else ScientificDataClassification.UNAVAILABLE
                    ),
                    physical_radius_m=radius_m,
                    actual_window_dimensions_m={
                        "width_m": tri_meta["actual_window_width_m"],
                        "height_m": tri_meta["actual_window_height_m"],
                    },
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="valid" if val is not None else "nodata",
                    reason=None if val is not None else "Required neighborhood touches NO-DATA or DEM border.",
                )
            except ValueError as exc:
                return MultiScaleMetricEntry(
                    metric_name=name,
                    value=None,
                    units="meters",
                    classification=ScientificDataClassification.UNAVAILABLE,
                    physical_radius_m=radius_m,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="resolution_limited",
                    reason=str(exc),
                )

        tri_fine = _eval_tri(fine_radius_m, "TRI (Fine Scale)")
        tri_med = _eval_tri(medium_radius_m, "TRI (Medium Scale)")

        # Local Relief & TPI over relief_radius_m
        def _eval_relief_and_tpi() -> tuple[MultiScaleMetricEntry, MultiScaleMetricEntry]:
            max_sp = max(dx_m, dy_m)
            if relief_radius_m < 0.5 * max_sp:
                msg = f"Relief radius ({relief_radius_m} m) is resolution-limited by DEM spacing ({dx_m:.2f} m)."
                res_entry = lambda nm: MultiScaleMetricEntry(
                    metric_name=nm,
                    value=None,
                    units="meters",
                    classification=ScientificDataClassification.UNAVAILABLE,
                    physical_radius_m=relief_radius_m,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="resolution_limited",
                    reason=msg,
                )
                return res_entry("Local Relief"), res_entry("Terrain Position Index (TPI)")

            rx_r = max(1, int(round(relief_radius_m / dx_m)))
            ry_r = max(1, int(round(relief_radius_m / dy_m)))
            dims = {
                "width_m": round((2 * rx_r + 1) * dx_m, 3),
                "height_m": round((2 * ry_r + 1) * dy_m, 3),
            }
            if (
                lr - ry_r < 0
                or lr + ry_r >= patch_clean.shape[0]
                or lc - rx_r < 0
                or lc + rx_r >= patch_clean.shape[1]
            ):
                msg = "Window extends outside DEM boundary."
                nd_entry = lambda nm: MultiScaleMetricEntry(
                    metric_name=nm,
                    value=None,
                    units="meters",
                    classification=ScientificDataClassification.UNAVAILABLE,
                    physical_radius_m=relief_radius_m,
                    actual_window_dimensions_m=dims,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="nodata",
                    reason=msg,
                )
                return nd_entry("Local Relief"), nd_entry("Terrain Position Index (TPI)")

            sub = patch_clean[lr - ry_r : lr + ry_r + 1, lc - rx_r : lc + rx_r + 1]
            if not np.all(np.isfinite(sub)):
                msg = "Required window contains NO-DATA pixels."
                nd_entry = lambda nm: MultiScaleMetricEntry(
                    metric_name=nm,
                    value=None,
                    units="meters",
                    classification=ScientificDataClassification.UNAVAILABLE,
                    physical_radius_m=relief_radius_m,
                    actual_window_dimensions_m=dims,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="nodata",
                    reason=msg,
                )
                return nd_entry("Local Relief"), nd_entry("Terrain Position Index (TPI)")

            relief_v = round(float(np.max(sub) - np.min(sub)), 4)
            tpi_v = round(float(elev_val - np.mean(sub)), 4)
            return (
                MultiScaleMetricEntry(
                    metric_name="Local Relief",
                    value=relief_v,
                    units="meters",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    physical_radius_m=relief_radius_m,
                    actual_window_dimensions_m=dims,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="valid",
                ),
                MultiScaleMetricEntry(
                    metric_name="Terrain Position Index (TPI)",
                    value=tpi_v,
                    units="meters",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    physical_radius_m=relief_radius_m,
                    actual_window_dimensions_m=dims,
                    native_resolution_m=round(native_res_m, 3),
                    processing_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                    status="valid",
                ),
            )

        relief_entry, tpi_entry = _eval_relief_and_tpi()

        graph = ProvenanceDependencyGraph(
            output_id=f"multiscale:{ds.id}:{lat:.6f}:{lon_norm:.6f}",
            classification=ScientificDataClassification.MARSCOPE_DERIVED,
            input_datasets=[ds.id],
            input_product_ids=[ds.product_id],
            input_variables=["elevation_m"],
            input_units=["meters"],
            input_crs="IAU2000:49900",
            input_resolution_m=round(native_res_m, 3),
            method="Finite-difference slope/aspect/curvature + fixed physical-window RMS TRI, TPI, and local relief",
            algorithm_version="multiscale_terrain_v1",
            parameters={
                "fine_radius_m": fine_radius_m,
                "medium_radius_m": medium_radius_m,
                "relief_radius_m": relief_radius_m,
                "nodata_policy": "strict_all_neighbors_valid",
            },
            assumptions=[
                "Spherical Mars radius 3396190.0 m (IAU2000:49900) for metric pixel spacing.",
                "Mathematical landform geometry does not imply a validated geological classification.",
            ],
            intermediate_steps=[
                ProvenanceStep(
                    step_id="step_dem_read",
                    label="Read native DEM elevation window",
                    classification=ScientificDataClassification.ARCHIVE_DERIVED,
                    input_ids=[ds.product_id],
                    method="PDS3/GeoTIFF windowed raster read",
                    algorithm_version="rasterio_v1",
                    output_variable="elevation_m",
                    output_units="meters",
                    output_resolution_m=round(native_res_m, 3),
                ),
                ProvenanceStep(
                    step_id="step_multiscale",
                    label="Derive slope, curvature, TRI (fine & medium), TPI, local relief",
                    classification=ScientificDataClassification.MARSCOPE_DERIVED,
                    input_ids=["step_dem_read"],
                    method="Horn slope + Evans 3x3 curvature + Riley RMS TRI + window relief/TPI",
                    algorithm_version="multiscale_terrain_v1",
                    output_variable="multiscale_terrain_metrics",
                    output_units="degrees / meters / 1/m",
                    output_resolution_m=round(0.5 * (dx_m + dy_m), 3),
                ),
            ],
            output_units="degrees / meters / 1/m",
            output_resolution_m=round(0.5 * (dx_m + dy_m), 3),
            uncertainty_method="strict_nodata_and_resolution_gating",
            validation_state="verified_derivation",
            scientific_notes=[
                "Landform metrics are strictly geometric and require geological context before mission interpretation."
            ],
        )

        obs_cls = (
            "partial_boundary_or_nodata"
            if slope_val is None
            else ("coarse_regional_only_subpixel_features_unresolved" if native_res_m > 50.0 else "resolvable_at_native_scale")
        )
        return MultiScaleTerrainResponse(
            available=True,
            dataset_id=ds.id,
            product_id=ds.product_id,
            latitude=lat,
            longitude_east=lon_norm,
            vertical_datum=ds.calibration_status or "MOLA_AREOID",
            elevation_m=round(elev_val, 3),
            slope_deg=slope_val,
            aspect_deg=aspect_val,
            profile_curvature_inv_m=prof_curv,
            planform_curvature_inv_m=plan_curv,
            surface_normal_enu=surf_normal,
            elevation_variability_m=elev_var_entry,
            terrain_observability=obs_cls,
            native_resolution_m=round(native_res_m, 3),
            tri_fine_m=tri_fine,
            tri_medium_m=tri_med,
            tpi_m=tpi_entry,
            local_relief_m=relief_entry,
            valid_coverage_fraction=cov_frac,
            provenance_graph=graph,
        )

    with rasterio.open(open_path) as src:
        if src.crs and src.crs.is_projected:
            with WarpedVRT(src, crs=MARS_GEOG_CRS) as vrt:
                return _compute_with_reader(vrt)
        return _compute_with_reader(src)
