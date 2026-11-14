# MARSCOPE Demonstration Script

This walkthrough describes workflows currently available in the repository. It does not imply route optimization, live astronaut telemetry, DEM-derived 3D terrain, or rover panorama coverage.

## Explorer (`/explorer`)

1. Open the explorer. It starts at a global Mars view without silently selecting Gale.
2. Use Cesium's 3D, 2D, and Columbus view controls. The 2D view is the surface-map projection available in the current implementation.
3. Pan and zoom with the Cesium controls or pointer gestures. Inspect the coordinate readout and camera altitude. The scale readout is based on globe intersections and may report unavailable when the view geometry cannot be measured.
4. Select a location on the globe or enter coordinates in the destination form. Location provenance is the manual selection; browser GPS is not used for Mars.
5. Toggle only layers returned by the backend catalog. Review source attribution, bounds, and availability in the layer workbench.
6. Select a composition candidate to inspect its catalog-backed location and evidence.

## Terrain and mobility (`/terrain`, `/routes`, `/planner`)

1. Review DEM inventory and processing coverage in Terrain Intelligence. Distinguish analysis over local rasters from displayed, actual terrain geometry: the Cesium globe still uses an ellipsoid terrain provider.
2. Inspect mobility coverage, elevation profiles, and scenario assumptions when corresponding verified data exist.
3. Treat route planning pages as current UI status only. A user-drawn sketch, optimized traversable route, safety-certified path, and live EVA telemetry are not currently implemented.

## Rover imagery status

The MSL Navcam RDR and RDR Mosaic archives are authoritative sources for investigating rover camera products. No product image or label has been acquired and verified in this workspace, and no panorama catalog/viewer is implemented. Do not demonstrate an imagined ground view or use an unrelated product as a panorama.

## Verification performed for this update

- Frontend ESLint: passed.
- Frontend production build: passed.
- Backend test suite: 71 passed.
- NASA product acquisition, browser gesture testing, terrain mesh verification, and performance measurement: not performed.
