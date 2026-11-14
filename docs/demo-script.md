# MARSCOPE Demonstration Script

This walkthrough covers the live Prompt 11 3D terrain explorer, science-aware Marswalk route planner, 3-mode comparison matrix, and trajectory playback. MARSCOPE separates verified NASA terrain geometry from user-configured planning assumptions and never fabricates EVA $\text{O}_2$, battery, or rover panorama coverage.

## 1. Dual-Engine 3D Explorer (`/explorer`)

1. Open `/explorer` (`Split View` shows both the Three.js LOD `0..2` local DEM mesh over Gale Crater / Mount Sharp `DTEEC_009149_1750_009294_1750_U01.IMG` and the CesiumJS 3D Mars globe powered by `createMarscopeDemTerrainProvider`).
2. Switch overlays (`HiRISE Ortho`, `Elevation`, `Slope (°)`, `TRI`), LOD levels (`LOD 0/1/2`), and vertical scale (`1x True` default, `2x`, `3x`). Notice oblique HiRISE swath corners with `valid_mask = 0` are omitted cleanly rather than filled with fake terrain.
3. Click **`Set Start`**, **`+Waypt`**, or **`Set Dest`** and pick points directly on the 3D DEM surface, then click **`Compute Route`** or **`Open Full Route Planner →`**.
4. Inspect verified Curiosity APXS/ChemCam/CheMin composition candidates alongside active Mars Trek WMTS layers (`curiosity_hirise_mosaic`, `Gale_CTX_BlockAdj_dd`).

## 2. Science-Aware Route Planner (`/planner`) & Targets (`/targets`)

1. Load a Gale Crater preset (`Boxwork Preset`) or adjust Start/Destination/Waypoints and select saved targets from `/targets` (`+ Add to Route` / `Route Here`).
2. Compare **Conservative**, **Balanced**, and **Science Priority** policies (`A*` or `Dijkstra`), set max slope, optional walking speed (or leave omitted for honest geometry-only computation), and optional return-to-base loop.
3. Click **`Compute Route`** to render the 3D route polyline directly above the HiRISE terrain, inspect the Recharts elevation profile, click rows in the **True North (`°T`) / Grid North (`°G`)** turn-by-turn instruction table to fly the 3D camera, and export **OGC GeoJSON**.
4. Edit a constraint (e.g., max slope or return-leg toggle) and observe the live **Stale Route Warning** banner until recomputed.

## 3. Route Trade-Off Comparison (`/routes`) & Playback (`/simulation`)

1. Open `/routes` and run **`Compare 3 Modes`** to evaluate `Conservative`, `Balanced`, and `Science Priority` over the identical DEM graph — observing honest infeasibility diagnostics when stricter slope/roughness caps reject a traverse.
2. Open `/simulation` to scrub or animate the astronaut marker along the 3D route vertices with synchronized elevation, slope, bearing cue, and optional Newtonian climb work ($m \cdot g_{\text{Mars}} \cdot \Delta h$). Inspect the **Unmodeled Physiological & Consumables Disclosure** card confirming $\text{O}_2$, $\text{CO}_2$, suit battery SoC, and metabolic curves are intentionally omitted (`Not Modeled (Unvalidated)`).

## 4. Rover Imagery Catalogue Status (`/imagery`)

- `/imagery` queries live NASA PDS Imaging Atlas & ODE archives cleanly. Because no individual MSL Navcam panorama image/label has yet cleared live archive discovery/acquisition, panorama stations and 360° viewer panels remain honestly withheld.

## Verification Performed (Prompt 11)

- **Backend Test Suite:** `pytest` covering geospatial, catalog, PDS composition discovery/integrity (Prompts 4–7), mobility intelligence (Prompt 8), imagery catalogue (Prompt 9), and 3D terrain mesh + A*/Dijkstra routing + real NASA HiRISE/MOLA integration (Prompt 11).
- **Frontend Production Build:** `npx tsc --noEmit`, `npm run lint`, and `npm run build` (`15/15` static routes).
- **Headless Chrome CDP Live Walkthrough:** All 10 routes rendered cleanly with zero console errors, zero page errors, zero React depth errors, and zero HTTP 5xx responses during live DEM/routing flows.
