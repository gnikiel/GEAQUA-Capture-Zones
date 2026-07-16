# Acceptance-test example

The file `GEAQUA_Capture_Zones_example_well.csv` contains one point suitable for loading as a delimited-text point layer in **EPSG:2180**.

Suggested input values:

- calculation name: `Example_Well_25_years`;
- pumping rate `Q`: `1000 m³/d`;
- hydraulic conductivity `k`: `10 m/d`;
- saturated thickness `H`: `20 m`;
- effective porosity `n`: `0.25`;
- hydraulic gradient `I`: `0.001`;
- travel time: `25 years`;
- flow azimuth: `90°`.

Expected key values:

- `Q0 = 0.2 m²/d`;
- `T0 = 19894.367886 d`;
- `T̃ = 0.458986687`;
- eccentric circular zone;
- `Ls = 795.774715 m`;
- radius `R = 793.616754 m`;
- upgradient shift `δ = 240.355254 m`.

Also test `I = 0`: the result must be a centric circular zone with `T0 = ∞` and `T̃ = 0`.
