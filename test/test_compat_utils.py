# -*- coding: utf-8 -*-
"""Tests for Qt5/Qt6-style enum resolution without importing Qt."""

import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from compat_utils import enum_member, first_enum_member  # noqa: E402


class TestCompatUtils(unittest.TestCase):
    def test_prefers_scoped_qt6_member(self):
        class Owner:
            Expanding = "legacy"

            class Policy:
                Expanding = "scoped"

        self.assertEqual(enum_member(Owner, "Policy", "Expanding"), "scoped")

    def test_falls_back_to_flat_qt5_member(self):
        class Owner:
            Expanding = "legacy"

        self.assertEqual(enum_member(Owner, "Policy", "Expanding"), "legacy")

    def test_first_available_candidate(self):
        class Old:
            PointGeometry = 1

        class New:
            class GeometryType:
                Point = 2

        self.assertEqual(
            first_enum_member(
                (object, "GeometryType", "Point"),
                (New, "GeometryType", "Point"),
                (Old, None, "PointGeometry"),
            ),
            2,
        )

    def test_missing_member_raises_clear_error(self):
        with self.assertRaises(AttributeError):
            enum_member(object, "Policy", "Expanding")


if __name__ == "__main__":
    unittest.main()
