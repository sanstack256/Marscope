# MARSCOPE Physical Models & Environmental Formulations

## 1. Physical Constants & Planetary Reference Parameters

All physical calculations in MARSCOPE adhere strictly to the NASA Mars Fact Sheet (NSSDC/GSFC) and IAU standard values:

| Parameter | Symbol | Value | Units | Source |
| :--- | :--- | :--- | :--- | :--- |
| **Mars Standard Gravitational Acceleration** | $g_{\text{Mars}}$ | $3.72076$ | $\text{m/s}^2$ | NASA GSFC Planetary Fact Sheet |
| **Planetary Mass** | $M_{\text{Mars}}$ | $6.4171 \times 10^{23}$ | $\text{kg}$ | NASA GSFC Planetary Fact Sheet |
| **Volumetric Mean Radius** | $R_{\text{mean}}$ | $3,389,500$ | $\text{m}$ | IAU / NASA GSFC |
| **Equatorial Radius** | $R_{\text{eq}}$ | $3,396,190$ | $\text{m}$ | IAU 2000 Mars Spheroid |
| **Polar Radius** | $R_{\text{pol}}$ | $3,376,200$ | $\text{m}$ | IAU 2000 Mars Spheroid |
| **Specific Gas Constant ($\text{CO}_2$)** | $R_{\text{specific}}$ | $188.92$ | $\text{J/(kg}\cdot\text{K)}$ | Standard atmospheric composition ($95.3\%\,\text{CO}_2$) |
| **Mean Atmospheric Pressure (Gale Floor)**| $p_0$ | $750$ | $\text{Pa}$ | MSL REMS in-situ average (seasonal $650\text{--}900\,\text{Pa}$) |
| **Mean Surface Temperature** | $T_{\text{mean}}$ | $210$ | $\text{K}$ | MSL REMS in-situ average (diurnal $190\text{--}260\,\text{K}$) |
| **Nominal GCR Radiation Dose Rate** | $\dot{D}_{\text{nom}}$ | $0.21$ | $\text{mSv/day}$ | MSL RAD surface measurements ($8.75\,\mu\text{Sv/hr}$) |

---

## 2. Mathematical Formulations & Implementations

### 2.1 Gravitational Weight & Potential Energy
- **Surface Weight:**
  $$W = m_{\text{total}} \cdot g_{\text{Mars}}$$
  For an astronaut ($80\text{ kg}$) wearing an advanced planetary exploration suit ($120\text{ kg}$), $m_{\text{total}} = 200\text{ kg}$. On Mars, $W = 200 \times 3.72076 = 744.15\text{ N}$ (equivalent to a mass of $\approx 75.9\text{ kg}$ in Earth gravity).

- **Gravitational Potential Energy:**
  $$\Delta PE = m_{\text{total}} \cdot g_{\text{Mars}} \cdot (z_{\text{target}} - z_{\text{start}})$$
  Calculated across high-resolution DEM cell transitions.

### 2.2 Topographic Gradient & Slope Angle
For a Digital Elevation Model grid with cell dimensions $\Delta x, \Delta y$:
$$\theta = \arctan\left(\sqrt{\left(\frac{\partial z}{\partial x}\right)^2 + \left(\frac{\partial z}{\partial y}\right)^2}\right)$$
Using Horn's 8-neighbor weighted finite-difference gradient operator to minimize raster grid bias.

### 2.3 Uphill and Downhill Resisting Forces
- **Uphill Parallel Force Component:**
  $$F_{\text{parallel}} = m_{\text{total}} \cdot g_{\text{Mars}} \cdot \sin(\theta)$$
- **Normal Force:**
  $$F_{\text{normal}} = m_{\text{total}} \cdot g_{\text{Mars}} \cdot \cos(\theta)$$
- **Optional User-Configured Planning Slope Threshold (`PlanningSlopeThreshold`):**
  MARSCOPE does **not** embed a default $25^\circ$ critical safety slope limit in its physics registry or terrain summaries. Any slope threshold used to highlight steep cells or exclude cells in a `MobilityScenario` (`planning_max_slope_deg`) must be explicitly provided by the user, is tagged `parameter_class = "user_configured_planning_assumption"` with `is_validated_safety_limit = false`, and never certifies terrain as `"safe"` or `"unsafe"`.

### 2.4 Atmospheric Density
Using the ideal gas formulation for the predominant carbon dioxide atmosphere:
$$\rho = \frac{p}{R_{\text{specific}} \cdot T}$$
At $p = 750\text{ Pa}$ and $T = 220\text{ K}$, $\rho \approx 0.0180\text{ kg/m}^3$ (less than $1.5\%$ of Earth sea-level density).

### 2.5 Ionizing Radiation Exposure Accumulation
$$D_{\text{total}} = \int_0^{t} \dot{D}_{\text{RAD}}(\tau) \, d\tau \approx \dot{D}_{\text{measured}} \cdot \Delta t$$
Tracks cumulative Marswalk dose and evaluates against operational mission constraints (e.g., standard threshold of $< 100\text{ mSv}$ for short-duration missions).

### 2.6 3D Traverse Distance, Azimuth Conventions & Route Pathfinder Cost Model (Prompt 11)
- **True 3D Surface Distance:** Across each graph step or simplified leg $(\Delta x_i, \Delta y_i, \Delta z_i)$ in local Mars ENU tangent coordinates ($R_{\text{eq}} = 3,396,190.0\text{ m}$, longitudinal factor $\cos\phi_0$):
  $$d_{\text{3D}} = \sum_{i} \sqrt{\Delta x_i^2 + \Delta y_i^2 + \Delta z_i^2}$$
- **Bearing & Heading Conventions:** Turn-by-turn navigation steps report both **Mars True North Azimuth** $\psi_{\text{T}} \in [0^\circ, 360^\circ)$ (spherical clockwise from geographic North) and **Equirectangular Grid North Azimuth** $\psi_{\text{G}}$ relative to the DEM central meridian ($137.41^\circ\text{ E}$ for `DTEEC_009149_1750`, $137.39^\circ\text{ E}$ for `DTEEC_040770_1755`).
- **Admissible A* Lower Bound & Cost Formulation:** Each directed edge of 3D surface length $\Delta s$ undergoes weighted impedance scaling based on directional grade slope $\tan^{-1}(|\Delta z| / d_{\text{horiz}})$, uphill vs downhill asymmetry (`uphill_weight` vs `downhill_weight`), metric TRI roughness, DEM resolution uncertainty, proximity to NoData boundaries, and optional `Science-Priority` corridor discount floored strictly at `min_cost_multiplier = 0.45`. A* heuristic $h(n) = d_{\text{Euclidean,3D}}(n, \text{goal}) \cdot 0.45$ guarantees admissibility so A* and Dijkstra yield identical optimal route costs.
- **Unmodeled Suit & Metabolic Curves:** Prompt 11 computes optional `estimated_duration_seconds` only when `walking_speed_m_per_s` is user-supplied, and Newtonian climb work $\Delta PE$ only when `astronaut_total_mass_kg` is user-supplied. Oxygen consumption, thermal loads, and battery draw remain intentionally unmodeled.

---

## 3. Scientific Limitations & Boundaries
> [!WARNING]
> These physical models provide foundational environmental approximations for tactical traverse planning. They are **not** an FDA/NASA-certified medical life-support monitoring tool. Human metabolic expenditure models are preliminary engineering estimates based on gravity-scaled terrestrial walking biomechanics and require formal validation with spaceflight telemetry before operational deployment.
