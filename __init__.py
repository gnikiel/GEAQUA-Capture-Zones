# -*- coding: utf-8 -*-
"""GEAQUA Capture Zones — QGIS plugin entry point."""


def classFactory(iface):  # pylint: disable=invalid-name
    """Create the QGIS plugin instance."""
    from .capture_zones_plugin import GEAQUACaptureZonesPlugin
    return GEAQUACaptureZonesPlugin(iface)
