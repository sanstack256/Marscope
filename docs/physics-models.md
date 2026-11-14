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
- **Terrain Shear Slip Condition (Coulomb-Mohr Criterion):**
  $$\tau_{\text{available}} = c + \sigma \tan(\phi)$$
  Where $c$ is regolith cohesion ($\approx 0.1\text{--}2.0\text{ kPa}$), $\sigma$ is normal stress, and $\phi$ is the internal friction angle ($\approx 30^\circ\text{--}35^\circ$ for basaltic sand). Slopes exceeding $20^\circ$ exhibit severe shear slip hazard for suited human mobility.

### 2.4 Atmospheric Density
Using the ideal gas formulation for the predominant carbon dioxide atmosphere:
$$\rho = \frac{p}{R_{\text{specific}} \cdot T}$$
At $p = 750\text{ Pa}$ and $T = 220\text{ K}$, $\rho \approx 0.0180\text{ kg/m}^3$ (less than $1.5\%$ of Earth sea-level density).

### 2.5 Ionizing Radiation Exposure Accumulation
$$D_{\text{total}} = \int_0^{t} \dot{D}_{\text{RAD}}(\tau) \, d\tau \approx \dot{D}_{\text{measured}} \cdot \Delta t$$
Tracks cumulative Marswalk dose and evaluates against operational mission constraints (e.g., standard threshold of $< 100\text{ mSv}$ for short-duration missions).

---

## 3. Scientific Limitations & Boundaries
> [!WARNING]
> These physical models provide foundational environmental approximations for tactical traverse planning. They are **not** an FDA/NASA-certified medical life-support monitoring tool. Human metabolic expenditure models are preliminary engineering estimates based on gravity-scaled terrestrial walking biomechanics and require formal validation with spaceflight telemetry before operational deployment.
