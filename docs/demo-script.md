# MARSCOPE End-to-End Demonstration Script

This document details the recommended demonstration walkthrough for the NASA Space Apps Challenge judges, showcasing the complete workflow from raw NASA planetary datasets to science-aware Marswalk planning.

---

## 1. Demonstration Scenario: Exploring Mount Sharp Boxwork

- **Mission Objective:** Conduct a 6-hour human extravehicular activity (EVA) from a designated landing habitat on Mount Sharp to investigate high-priority boxwork mineralized fracture networks and return safely with rock core samples.
- **Astronaut Configuration:** 2-person crew, planetary exploration suit mass $120\text{ kg}$, astronaut mass $80\text{ kg}$, total system mass $200\text{ kg}$ per explorer. Walking speed baseline $1.0\text{ m/s}$ on flat terrain.

---

## 2. Step-by-Step Demonstration Flow

### Scene 1: Mission Overview & Atmospheric Context (`/`)
1. Open the MARSCOPE homepage.
2. Present the Gale Crater Mount Sharp mission context card.
3. Review current in-situ environmental conditions derived from MSL REMS: ambient pressure ($750\text{ Pa}$), surface temperature ($215\text{ K}$), and RAD radiation baseline ($0.21\text{ mSv/day}$).

### Scene 2: 3D Surface Explorer & Planetary Layers (`/explorer`)
1. Transition into the central 3D Mars globe powered by CesiumJS.
2. Fly into Gale Crater and zoom onto the Mount Sharp boxwork exploration zone.
3. Toggle between orbital layers:
   - High-resolution HiRISE visible orthomosaics displaying sub-meter fracture ridges.
   - Regional CTX basemap providing wide context.
   - MOLA false-color elevation contours highlighting the central mound topography.
   - The verified Curiosity rover traverse path, tracing over 30 kilometers of surface exploration.

### Scene 3: Terrain Intelligence & Slope Inspection (`/terrain`)
1. Activate the Terrain Intelligence view.
2. Display the processed slope gradient heatmap ($0^\circ\text{ to }30^\circ+$).
3. Use the cross-sectional elevation profile tool to draw a traverse across a boxwork ridge, pointing out steep ridge flanks ($> 22^\circ$) and safe low-slope corridors ($< 10^\circ$).

### Scene 4: Scientific Target Explorer (`/targets`)
1. Navigate to the Target Explorer.
2. Filter targets by "Boxwork Formations" and "Sulfate Hydration".
3. Select **Boxwork Ridge Segment Alpha**:
   - Inspect the associated Curiosity Mastcam high-res image showing resistant ridge fins.
   - Review ChemCam elemental composition showing high calcium sulfate enrichment.
   - Note the CRISM spectral signature confirming polyhydrated sulfates.
4. Click "Add to Mission Plan".
5. Select a second target: **Inter-Ridge Hollow Sediment Station**.

### Scene 5: Science-Aware Route Optimization (`/planner`)
1. Navigate to the Route Planner with selected targets in the mission basket.
2. Configure parameters:
   - Max EVA Duration: 6.0 hours.
   - Safety Reserve Buffer: $1.5\times$ return consumable requirement.
   - Mode: "Science-Priority".
3. Click **"Compute Marswalk Route"**.
4. Observe the backend solving the constrained graph traversal in real-time.
5. Inspect the generated 3D route draped onto the terrain:
   - The path routes along gentle slope corridors rather than climbing sheer boxwork walls.
   - Points of interest are visited in optimal sequence.
   - The **Point of No Return** indicator is clearly marked where return consumables reach the $1.5\times$ threshold.

### Scene 6: Route Comparison Matrix (`/routes`)
1. Compare the computed route against "Conservative" (minimum energy, fewer targets) and "Balanced" modes.
2. Walk through the comparative metrics: distance (km), max slope, cumulative elevation gain (m), estimated metabolic energy (MJ), and total science return score.

### Scene 7: Mission Simulation (`/simulation`)
1. Scrub through the EVA timeline.
2. Observe simulated crew progression along the path with dynamic consumable burn rate graphs (oxygen, battery, cooling water).

### Scene 8: Data Provenance & Open Science Ledger (`/evidence`)
1. Conclude the demonstration on the Evidence & Provenance page.
2. Demonstrate that every single layer, waypoint, and observation cites an official NASA PDS Product ID, instrument, acquisition date, and open reuse license.
