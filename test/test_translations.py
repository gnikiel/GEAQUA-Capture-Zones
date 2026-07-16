# -*- coding: utf-8 -*-
"""Pure-Python tests for the dynamic Polish/English interface translations."""

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from translations import DEFAULT_LANGUAGE, _TRANSLATIONS, translate, zone_display_name  # noqa: E402


class TestTranslations(unittest.TestCase):
    def test_default_language_is_polish(self):
        self.assertEqual(DEFAULT_LANGUAGE, "pl")

    def test_polish_and_english_labels(self):
        self.assertEqual(translate("calculate", "pl"), "Oblicz strefę dopływu")
        self.assertEqual(translate("calculate", "en"), "Calculate capture zone")

    def test_formatting(self):
        self.assertIn("EPSG:2180", translate(
            "layer_selected", "pl", layer="S1", crs="EPSG:2180", crs_note="PUWG 1992"
        ))

    def test_zone_names(self):
        self.assertEqual(zone_display_name("uniform_flow", "pl"), "Strefa dopływu w jednorodnym polu przepływu")
        self.assertEqual(zone_display_name("uniform_flow", "en"), "Well in Uniform Flow")
        self.assertEqual(zone_display_name("centric_circular", "en"), "Centric Circle")
        self.assertEqual(zone_display_name("eccentric_circular", "en"), "Eccentric Circle")

    def test_unknown_language_falls_back_to_polish(self):
        self.assertEqual(translate("calculate", "de"), "Oblicz strefę dopływu")

    def test_language_dictionaries_have_identical_keys(self):
        self.assertEqual(set(_TRANSLATIONS["pl"]), set(_TRANSLATIONS["en"]))
        self.assertEqual(translate("clear_preview", "pl"), "Usuń podgląd")
        self.assertEqual(translate("clear_preview", "en"), "Remove Preview")

    def test_language_selector_label_is_always_bilingual(self):
        expected = "Język interfejsu / Interface language:"
        self.assertEqual(translate("language_label", "pl"), expected)
        self.assertEqual(translate("language_label", "en"), expected)


if __name__ == "__main__":
    unittest.main()
