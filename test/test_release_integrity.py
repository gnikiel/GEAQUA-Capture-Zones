# -*- coding: utf-8 -*-
"""Pre-publication integrity checks for GEAQUA Capture Zones v0.39."""

import configparser
import os
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PLUGIN_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from GEAQUA_Capture_Zones.version import (  # noqa: E402
    PLUGIN_AUTHORS,
    PLUGIN_ID,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    WINDOW_TITLE,
)
from GEAQUA_Capture_Zones.calculation_io import SCHEMA_NAME  # noqa: E402


class TestReleaseIntegrity(unittest.TestCase):
    def _source(self, relative_path):
        with open(os.path.join(PLUGIN_DIR, relative_path), encoding="utf-8") as handle:
            return handle.read()

    def test_identity_and_version(self):
        self.assertEqual(PLUGIN_ID, "GEAQUA_Capture_Zones")
        self.assertEqual(PLUGIN_NAME, "GEAQUA Capture Zones")
        self.assertEqual(PLUGIN_VERSION, "0.39")
        self.assertEqual(WINDOW_TITLE, "GEAQUA Capture Zones v0.39")
        self.assertEqual(PLUGIN_AUTHORS, "Maciej Nikiel & Grzegorz Nikiel")

    def test_public_repository_links(self):
        metadata = (Path(PLUGIN_DIR) / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn("homepage=https://github.com/gnikiel/GEAQUA-Capture-Zones", metadata)
        self.assertIn("repository=https://github.com/gnikiel/GEAQUA-Capture-Zones", metadata)
        self.assertIn("tracker=https://github.com/gnikiel/GEAQUA-Capture-Zones/issues", metadata)
        self.assertIn("experimental=True", metadata)
        self.assertIn("qgisMaximumVersion=4.99", metadata)
        self.assertIn("hasProcessingProvider=False", metadata)

    def test_metadata_matches_runtime_identity(self):
        parser = configparser.ConfigParser()
        parser.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
        self.assertEqual(parser.get("general", "name"), PLUGIN_NAME)
        self.assertEqual(parser.get("general", "version"), PLUGIN_VERSION)
        self.assertEqual(parser.get("general", "author"), PLUGIN_AUTHORS)
        self.assertEqual(parser.get("general", "qgisMinimumVersion"), "3.22")
        self.assertEqual(parser.get("general", "qgisMaximumVersion"), "4.99")

    def test_qgis_entry_point_uses_new_plugin_class(self):
        source = self._source("__init__.py")
        self.assertIn("from .capture_zones_plugin import GEAQUACaptureZonesPlugin", source)
        self.assertIn("return GEAQUACaptureZonesPlugin(iface)", source)
        main = self._source("capture_zones_plugin.py")
        self.assertIn("class GEAQUACaptureZonesPlugin", main)

    def test_ui_title_and_language_defaults(self):
        root = ET.parse(os.path.join(PLUGIN_DIR, "ui", "capture_zone_dialog.ui")).getroot()
        title = root.find("./widget/property[@name='windowTitle']/string")
        self.assertIsNotNone(title)
        self.assertEqual(title.text, WINDOW_TITLE)
        dialog = self._source("ui/capture_zone_dialog.py")
        self.assertIn('self.comboLanguage.addItem("Polski", "pl")', dialog)
        self.assertIn('self.comboLanguage.addItem("English", "en")', dialog)
        self.assertIn("self.comboLanguage.setCurrentIndex(0)", dialog)

    def test_modeless_scrollable_dialog_and_toolbar_action(self):
        main = self._source("capture_zones_plugin.py")
        dialog = self._source("ui/capture_zone_dialog.py")
        self.assertIn("self.iface.addToolBarIcon(action)", main)
        self.assertIn("self.iface.addPluginToMenu", main)
        self.assertIn("self.dlg.show()", main)
        self.assertIn("QT_NON_MODAL", main)
        self.assertNotIn("exec_()", main[main.index("    def run(self):"):])
        self.assertIn("QScrollArea", dialog)
        self.assertIn("setWidgetResizable(True)", dialog)

    def test_preview_does_not_create_or_delete_project_layers(self):
        main = self._source("capture_zones_plugin.py")
        preview = main[main.index("    def clear_preview"):main.index("    def create_capture_zone_layer")]
        self.assertIn("QgsRubberBand", main)
        self.assertIn("band.reset(QGIS_GEOMETRY_POLYGON)", preview)
        self.assertNotIn("removeMapLayer", main)
        self.assertNotIn("removeMapLayers", main)

    def test_current_modules_and_files_are_named_cleanly(self):
        required = (
            "capture_zones_plugin.py",
            "algorithms/ceric_haitjema.py",
            "ui/capture_zone_dialog.py",
            "ui/capture_zone_dialog.ui",
            "test/test_ceric_haitjema.py",
        )
        for relative in required:
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN_DIR, relative)), relative)

    def test_project_schema_and_extension_are_new(self):
        self.assertEqual(SCHEMA_NAME, "geaqua_capture_zones_project")
        dialog = self._source("ui/capture_zone_dialog.py")
        translations = self._source("translations.py")
        self.assertIn(".gcz.json", dialog)
        self.assertIn("*.gcz.json", translations)
        self.assertNotIn("LEGACY_SCHEMA", self._source("calculation_io.py"))

    def test_primary_method_source_is_ceric_haitjema(self):
        combined = "\n".join([
            self._source("README.md"),
            self._source("METHODOLOGY.md"),
            self._source("ui/capture_zone_dialog.py"),
            self._source("calculation_io.py"),
            self._source("algorithms/ceric_haitjema.py"),
        ])
        self.assertIn("Ceric", combined)
        self.assertIn("Haitjema", combined)
        self.assertIn("10.1111/j.1745-6584.2005.0035.x", combined)
        self.assertNotIn("Kraemer", combined)

    def test_no_legacy_names_or_implementation_references(self):
        legacy_tokens = [
            "w" + "hpa",
            "w" + "haem",
            "simple_" + "w" + "hpa",
            "well_head_" + "protection_area",
        ]
        banned = re.compile("|".join(legacy_tokens), re.IGNORECASE)
        offenders = []
        for root, dirs, files in os.walk(PLUGIN_DIR):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for filename in files:
                rel = os.path.relpath(os.path.join(root, filename), PLUGIN_DIR)
                if banned.search(rel):
                    offenders.append(rel)
                    continue
                if os.path.splitext(filename)[1].lower() in {".png", ".pyc"}:
                    continue
                try:
                    content = self._source(rel)
                except UnicodeDecodeError:
                    continue
                if banned.search(content):
                    offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_qt5_qt6_compatibility_layer_is_used(self):
        dialog = self._source("ui/capture_zone_dialog.py")
        main = self._source("capture_zones_plugin.py")
        compat = self._source("qt_compat.py")
        self.assertIn('enum_member(QSizePolicy, "Policy", "Expanding")', compat)
        self.assertIn('enum_member(QDialogButtonBox, "StandardButton", "Ok")', compat)
        self.assertIn('enum_member(QPrinter, "OutputFormat", "PdfFormat")', compat)
        self.assertIn("QSIZEPOLICY_EXPANDING", dialog)
        self.assertIn("QPRINTER_PDF_FORMAT", main)
        self.assertNotIn("from PyQt5", dialog + main)
        self.assertNotIn("from PyQt6", dialog + main)

    def test_package_has_no_cache_or_compiled_files(self):
        bad = []
        for root, dirs, files in os.walk(PLUGIN_DIR):
            for directory in dirs:
                if directory == "__pycache__":
                    bad.append(os.path.join(root, directory))
            for filename in files:
                if filename.endswith((".pyc", ".pyo")):
                    bad.append(os.path.join(root, filename))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
