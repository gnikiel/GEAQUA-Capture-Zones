# -*- coding: utf-8 -*-
"""Tests for portable JSON, summaries and report HTML."""

import json
import os
import sys
import tempfile
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from GEAQUA_Capture_Zones.calculation_io import (  # noqa: E402
    SCHEMA_NAME,
    build_document,
    build_report_html,
    build_summary_text,
    load_document,
    result_variants,
    save_document,
)


class TestCalculationIO(unittest.TestCase):
    def setUp(self):
        self.params = {
            "k": 10.0,
            "m": 30.0,
            "n": 0.25,
            "Q": 1000.0,
            "I": 0.005,
            "t": 25.0,
            "flow_direction": 90.0,
            "well_x": 0.0,
            "well_y": 0.0,
            "source_layer": "S1",
            "source_layer_id": "abc",
            "crs_authid": "EPSG:2180",
            "crs_name": "ETRF2000-PL / CS92",
            "standard_time_variants": False,
            "time_variants": (25.0,),
            "well_attributes": {"id": 7, "nazwa": "S-1"},
        }
        self.single = {
            "geometry": [(-100, -20), (50, -20), (50, 20), (-100, 20), (-100, -20)],
            "zone_type": "uniform_flow",
            "T_dimensionless": 2.5,
            "Qo": 1.5,
            "To": 3650.0,
            "Ls": 50.0,
            "Lu": 100.0,
            "Ydiv": 20.0,
            "R": None,
            "delta": None,
            "time_years": 25.0,
        }
        self.bundle = {"variants": [self.single], "multi_variant": False}

    def test_result_variants(self):
        self.assertEqual(result_variants(self.bundle), [self.single])
        self.assertEqual(result_variants(self.single), [self.single])

    def test_json_round_trip(self):
        document = build_document("Studnia_S1_25_lat", self.params, self.bundle)
        self.assertEqual(document["schema"], SCHEMA_NAME)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test.gcz.json")
            save_document(path, document)
            loaded = load_document(path)
        self.assertEqual(loaded["calculation_name"], "Studnia_S1_25_lat")
        self.assertEqual(loaded["input_parameters"]["crs_authid"], "EPSG:2180")
        self.assertEqual(loaded["source"]["well_attributes"]["nazwa"], "S-1")
        self.assertEqual(len(loaded["calculation"]["variants"]), 1)

    def test_invalid_schema_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"schema": "other", "schema_version": 1, "input_parameters": {}}, handle)
            with self.assertRaises(ValueError):
                load_document(path)

    def test_summary_contains_required_dimensions_and_units(self):
        text = build_summary_text("Studnia_S1_25_lat", self.params, self.bundle, "pl")
        self.assertIn("góra=100,00 m".replace(",", "."), text.replace(",", "."))
        self.assertIn("dół=50,00 m".replace(",", "."), text.replace(",", "."))
        self.assertIn("ha", text)
        self.assertIn("km²", text)

    def test_summary_contains_well_attributes(self):
        text = build_summary_text("Studnia_S1_25_lat", self.params, self.bundle, "pl")
        self.assertIn("Dane studni:", text)
        self.assertIn("nazwa: S-1", text)

    def test_html_report_contains_well_data_and_intermediate_results(self):
        report = build_report_html("Studnia_S1_25_lat", self.params, self.bundle, language="pl")
        self.assertIn("Dane studni", report)
        self.assertIn("S-1", report)
        self.assertIn("Wyniki pośrednie geometrii", report)
        self.assertIn("Ydiv — asymptotyczna półszerokość [m]", report)

    def test_html_report_contains_equations_map_and_limitations(self):
        html = build_report_html(
            "Studnia_S1_25_lat",
            self.params,
            self.bundle,
            language="pl",
            map_data_uri="data:image/png;base64,AA==",
            warnings=["test warning"],
        )
        self.assertIn("Q₀ = k · i · H", html)
        self.assertIn("data:image/png;base64,AA==", html)
        self.assertIn("Ograniczenia metody", html)
        self.assertIn("Podstawy metodyczne i źródła", html)
        self.assertIn("Grubb, S. (1993)", html)
        self.assertIn("Strefa dopływu w jednorodnym polu przepływu", html)
        self.assertNotIn("Łódkowa", html)
        self.assertIn("test warning", html)

    def test_zero_flow_json_is_strict_and_report_uses_infinity_symbol(self):
        zero = dict(self.single)
        zero.update({
            "zone_type": "centric_circular", "Qo": 0.0, "To": None,
            "T_dimensionless": 0.0, "reference_time_infinite": True,
            "ambient_flow_zero": True, "lu_approximation_warning": False,
        })
        bundle = {"variants": [zero], "multi_variant": False}
        params = dict(self.params)
        params.update({"I": 0.0, "flow_direction": 0.0})
        document = build_document("zero", params, bundle)
        encoded = json.dumps(document, allow_nan=False)
        self.assertNotIn("Infinity", encoded)
        report = build_report_html("zero", params, bundle, language="pl")
        self.assertIn("T₀ → ∞", report)
        self.assertIn("nie dotyczy — I = 0", report)

    def test_report_warns_when_lu_approximation_is_not_strictly_conservative(self):
        warned = dict(self.single)
        warned["T_dimensionless"] = 5.0
        warned["lu_approximation_warning"] = True
        report = build_report_html(
            "warned", self.params, {"variants": [warned], "multi_variant": False}, language="pl"
        )
        self.assertIn("T̃ &gt; 2,85", report)
        self.assertIn("nie jest w tym zakresie ściśle konserwatywne", report)


if __name__ == "__main__":
    unittest.main()
