# Changelog

## 0.39 — first public experimental release candidate

- Added the official GitHub homepage, source repository and issue tracker to `metadata.txt`.
- Prepared metadata for submission to the official QGIS Plugin Repository.
- Marked the first public version as experimental.
- Removed internal review reports and publishing checklists from the user distribution package.
- Kept the calculation algorithms and geometry unchanged from version 0.38.

## 0.38 — clean pre-publication identity

- Renamed the plugin and technical package to **GEAQUA Capture Zones** / `GEAQUA_Capture_Zones`.
- Removed all legacy product, acronym and implementation references from user-visible text, code identifiers, project schema, file names, documentation and tests.
- Based methodology, help and reports directly on Ceric and Haitjema (2005).
- Retained Grubb (1993) and Bear and Jacobs (1965) as supporting theoretical sources.
- Replaced the project format with schema `geaqua_capture_zones_project` and extension `.gcz.json`.
- Renamed the main plugin class, dialog module, algorithm module and tests.
- Kept all numerical, geometry, QGIS compatibility and safety corrections from the previous review build.
