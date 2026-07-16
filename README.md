# GEAQUA Capture Zones

A bilingual Polish-English QGIS plugin for analytical delineation of groundwater time-of-travel capture zones around a **single pumping well**.

## Current method

Version 0.41 implements the analytical approximations described by:

> Ceric, A., Haitjema, H. (2005). *On Using Simple Time-of-Travel Capture Zone Delineation Methods*. Ground Water, 43(3), 408–412. DOI: 10.1111/j.1745-6584.2005.0035.x.

The dimensionless travel-time parameter `T̃` selects one of three geometries:

- `T̃ ≤ 0.1` — centric circular zone;
- `0.1 < T̃ ≤ 1` — eccentric circular zone;
- `T̃ > 1` — capture zone in uniform regional flow, bounded by the steady-state dividing streamline and truncated by the approximate upstream extent.

Supporting theoretical references are Grubb (1993) for steady-state capture-zone geometry and Bear and Jacobs (1965) for the underlying uniform-flow isochrone solution.

## Main features

- single-well analytical calculation;
- Polish and English interface;
- support for EPSG:2180, EPSG:2176–2179 and other projected metric CRSs;
- zero ambient-flow case;
- variants for 1, 5, 10, 25 and 50 years in one polygon layer;
- map-canvas preview without temporary project layers;
- result summaries, HTML/PDF reports and `.gcz.json` project files;
- modeless, resizable and scrollable dialog;
- QGIS 3 / Qt5 and QGIS 4 / Qt6 compatibility layer.

## Direction convention

Regional groundwater-flow direction is entered as an azimuth measured clockwise from North:

- `0°` — North;
- `90°` — East;
- `180°` — South;
- `270°` — West.

When the hydraulic gradient is zero, direction does not affect the result.

## Main assumptions and limitations

The current method assumes one fully penetrating well pumping at a constant rate, a homogeneous and isotropic aquifer of constant saturated thickness, steady horizontal flow under the Dupuit assumption, and uniform or zero regional groundwater flow. It does not represent hydrodynamic boundaries, local recharge, leakage, storage, dispersion, sorption or interacting wells.

For `T̃ > 2.85`, the explicit upstream-distance approximation proposed by Ceric and Haitjema (2005) may slightly underestimate the exact implicit value. The plugin displays a warning in that range.

A calculated capture zone is an analytical approximation. It is not automatically a legally designated protection area and requires hydrogeological review of the conceptual model and input data.

## Installation

Install the ZIP in QGIS through **Plugins → Manage and Install Plugins → Install from ZIP**.

## License and authors

GPL-2.0-or-later. Authors: **Maciej Nikiel & Grzegorz Nikiel**.


## Project links

- Source code and documentation: https://github.com/gnikiel/GEAQUA-Capture-Zones
- Bug reports and feature requests: https://github.com/gnikiel/GEAQUA-Capture-Zones/issues

## Release status

Version 0.41 is an experimental release prepared for the official QGIS Plugin Repository. It resolves all reported Flake8 findings and updates the contact email without changing the calculation method or generated geometries.
