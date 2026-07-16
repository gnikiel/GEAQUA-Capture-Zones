# Methodology — GEAQUA Capture Zones v0.40

## Primary source

The current calculation method is based directly on:

Ceric, A., Haitjema, H. (2005). *On Using Simple Time-of-Travel Capture Zone Delineation Methods*. Ground Water, 43(3), 408–412. DOI: 10.1111/j.1745-6584.2005.0035.x.

## Core equations

For hydraulic conductivity `k`, hydraulic gradient `i`, saturated thickness `H`, effective porosity `n`, pumping rate `Q` and travel time `T`:

- ambient flow per unit width: `Q0 = k i H`;
- stagnation distance: `Ls = Q / (2πQ0)`;
- reference time: `T0 = n H Q / (2πQ0²)`;
- dimensionless travel time: `T̃ = T / T0`.

When `Q0 = 0`, the limiting values are `T0 → ∞` and `T̃ = 0`.

### Centric circular zone — `T̃ ≤ 0.1`

`R = 1.1543 √(Q T / (π H n))`

### Eccentric circular zone — `0.1 < T̃ ≤ 1`

`R = Ls [1.161 + ln(0.39 + T̃)]`

`δ = Ls [0.00278 + 0.652 T̃]`

### Capture zone in uniform flow — `T̃ > 1`

The steady-state dividing streamline is represented in local coordinates by:

`x/Ls = (y/Ls) / tan(y/Ls)`

The upstream truncation distance is approximated by:

`Lu = Ls [T̃ + ln(T̃ + e)]`

Ceric and Haitjema (2005) show that the `Lu` approximation is conservative up to approximately `T̃ = 2.85`; above this value it remains close to the implicit solution but may slightly underestimate upstream extent.

## Direction and coordinates

The plugin uses a GIS azimuth measured clockwise from North. Calculations are performed in the input layer's projected metric CRS and the resulting local geometry is rotated and translated to the well location.

## Supporting references

- Grubb, S. (1993). *Analytical Model for Estimation of Steady-State Capture Zones of Pumping Wells in Confined and Unconfined Aquifers*. Ground Water, 31(1), 27–32.
- Bear, J., Jacobs, M. (1965). *On the movement of water bodies injected into aquifers*. Journal of Hydrology, 3, 37–57.

## Applicability

The method assumes a homogeneous, isotropic aquifer, steady horizontal flow, a fully penetrating well pumping at a constant rate, and no significant interference from boundaries or other wells. The results describe advective travel-time capture and do not model contaminant fate or transport processes.
