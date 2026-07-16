# -*- coding: utf-8 -*-
"""Tests for pure-Python GEAQUA Capture Zones integration helpers."""

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from plugin_utils import (  # noqa: E402
    build_layer_base_name,
    is_preferred_polish_crs,
    make_unique_layer_name,
    sanitize_layer_component,
    assess_zone_scale,
    build_direction_graphics,
    flow_axis_unit_vector,
    polygon_area,
    build_calculation_name,
    zone_dimensions,
    STANDARD_TIME_VARIANTS,
)


class TestPluginUtils(unittest.TestCase):
    def test_preferred_polish_crs(self):
        for epsg in range(2176, 2181):
            self.assertTrue(is_preferred_polish_crs(f"EPSG:{epsg}"))

    def test_crs_normalization(self):
        self.assertTrue(is_preferred_polish_crs(" epsg:2180 "))
        self.assertFalse(is_preferred_polish_crs("EPSG:4326"))

    def test_sanitize_layer_component(self):
        self.assertEqual(sanitize_layer_component("Studnia nr 1 / ujęcie"), "Studnia_nr_1_ujęcie")

    def test_empty_layer_component(self):
        self.assertEqual(sanitize_layer_component("---"), "studnia")

    def test_build_layer_name(self):
        self.assertEqual(build_layer_base_name("Studnia 1", 25), "GEAQUA_CZ_Studnia_1_25lat")
        self.assertEqual(build_layer_base_name("S-2", 2.5), "GEAQUA_CZ_S_2_2_5lat")

    def test_unique_layer_name(self):
        existing = {"GEAQUA_CZ_S1_25lat", "GEAQUA_CZ_S1_25lat_2"}
        self.assertEqual(
            make_unique_layer_name("GEAQUA_CZ_S1_25lat", existing),
            "GEAQUA_CZ_S1_25lat_3",
        )

    def test_polygon_area(self):
        self.assertEqual(polygon_area([(0, 0), (10, 0), (10, 5), (0, 5)]), 50.0)

    def test_flow_axis_cardinal_directions(self):
        north = flow_axis_unit_vector(0)
        east = flow_axis_unit_vector(90)
        self.assertAlmostEqual(north[0], 0.0, places=12)
        self.assertAlmostEqual(north[1], 1.0, places=12)
        self.assertAlmostEqual(east[0], 1.0, places=12)
        self.assertAlmostEqual(east[1], 0.0, places=12)

    def test_direction_graphics_follow_flow_azimuth(self):
        result = {"zone_type": "uniform_flow", "Lu": 1000.0, "Ls": 200.0, "geometry": []}
        params = {"well_x": 500.0, "well_y": 1000.0, "flow_direction": 90.0}
        graphics = build_direction_graphics(result, params)
        self.assertLess(graphics["arrow_start"][0], params["well_x"])
        self.assertGreater(graphics["arrow_end"][0], params["well_x"])
        self.assertAlmostEqual(graphics["arrow_start"][1], params["well_y"], places=8)

    def test_scale_warning_is_advisory_for_extreme_zone(self):
        result = {
            "geometry": [(0, 0), (30000, 0), (30000, 5000), (0, 5000), (0, 0)]
        }
        params = {"k": 1.0, "m": 20.0, "n": 0.25, "Q": 100.0, "I": 0.001, "t": 5.0}
        warning = assess_zone_scale(result, params)
        self.assertIsNotNone(warning)
        self.assertGreaterEqual(warning["max_dimension_m"], 30000.0)

    def test_scale_warning_not_emitted_for_ordinary_zone(self):
        result = {
            "geometry": [(0, 0), (1000, 0), (1000, 500), (0, 500), (0, 0)]
        }
        params = {"k": 10.0, "m": 30.0, "n": 0.25, "Q": 1000.0, "I": 0.005, "t": 25.0}
        self.assertIsNone(assess_zone_scale(result, params))

    def test_standard_time_variants(self):
        self.assertEqual(STANDARD_TIME_VARIANTS, (1.0, 5.0, 10.0, 25.0, 50.0))

    def test_default_calculation_name(self):
        self.assertEqual(build_calculation_name("S1", 25, False), "Studnia_S1_25_lat")
        self.assertEqual(
            build_calculation_name("Studnia S1", 25, True),
            "Studnia_S1_warianty_1_5_10_25_50_lat",
        )

    def test_zone_dimensions_in_flow_axes(self):
        result = {"geometry": [(-100, -20), (50, -20), (50, 20), (-100, 20), (-100, -20)]}
        params = {"well_x": 0.0, "well_y": 0.0, "flow_direction": 90.0}
        dims = zone_dimensions(result, params)
        self.assertAlmostEqual(dims["upstream_m"], 100.0, places=6)
        self.assertAlmostEqual(dims["downstream_m"], 50.0, places=6)
        self.assertAlmostEqual(dims["width_m"], 40.0, places=6)


if __name__ == "__main__":
    unittest.main()
