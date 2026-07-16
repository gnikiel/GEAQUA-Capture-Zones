# -*- coding: utf-8 -*-
"""
Test suite for Ceric–Haitjema analytical method Algorithm

Tests the Ceric–Haitjema analytical capture-zone implementation
including parameter validation, hydraulic calculations, and geometry generation.

Copyright (C) 2025 by Maciej Nikiel & Grzegorz Nikiel
License: GNU General Public License v2
"""

import unittest
import math
import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithms.ceric_haitjema import (
    DAYS_PER_YEAR,
    CaptureZoneParameters,
    validate_parameters,
    calculate_ambient_flow,
    calculate_reference_time,
    calculate_dimensionless_time,
    determine_zone_type,
    generate_centric_circular_zone,
    generate_eccentric_circular_zone,
    generate_uniform_flow_zone,
    polygon_signed_area,
    find_self_intersections,
    validate_polygon_coordinates,
    rotate_coordinates,
    translate_coordinates,
    calculate_capture_zone
)


class TestParameterValidation(unittest.TestCase):
    """Test parameter validation function."""

    def test_valid_parameters(self):
        """Test that valid parameters pass validation."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.005,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        # Should not raise any exception
        validate_parameters(params)

    def test_negative_hydraulic_conductivity(self):
        """Test that negative hydraulic conductivity raises ValueError."""
        params = CaptureZoneParameters(
            k=-10.0, m=30.0, n=0.25, Q=2000.0, I=0.005,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaises(ValueError) as context:
            validate_parameters(params)
        self.assertIn("Hydraulic conductivity must be positive", str(context.exception))

    def test_invalid_porosity_too_high(self):
        """Test that porosity > 1 raises ValueError."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=1.5, Q=2000.0, I=0.005,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaises(ValueError) as context:
            validate_parameters(params)
        self.assertIn("Effective porosity must be between 0 and 1", str(context.exception))

    def test_invalid_porosity_zero(self):
        """Test that porosity = 0 raises ValueError."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.0, Q=2000.0, I=0.005,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaises(ValueError) as context:
            validate_parameters(params)
        self.assertIn("Effective porosity must be between 0 and 1", str(context.exception))

    def test_invalid_flow_direction(self):
        """Test that flow direction > 360 raises ValueError."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.005,
            t=10.0, flow_direction=400.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaises(ValueError) as context:
            validate_parameters(params)
        self.assertIn("Flow direction must be between 0 and 360", str(context.exception))

    def test_zero_gradient_is_valid(self):
        """Zero gradient represents no ambient flow and must be accepted."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.0,
            t=10.0, flow_direction=0.0, well_x=1000.0, well_y=2000.0
        )
        validate_parameters(params)

    def test_negative_gradient_is_invalid(self):
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=-0.001,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            validate_parameters(params)

    def test_invalid_gradient(self):
        """Test that gradient >= 1.0 raises ValueError."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=1.5,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )
        with self.assertRaises(ValueError) as context:
            validate_parameters(params)
        self.assertIn("Hydraulic gradient should be less than 1.0", str(context.exception))


class TestHydraulicCalculations(unittest.TestCase):
    """Test core hydraulic calculation functions."""

    def test_calculate_ambient_flow(self):
        """Test ambient flow calculation."""
        k = 8.64  # m/d
        I = 0.002809  # -
        m = 41.0  # m
        Qo = calculate_ambient_flow(k, I, m)
        # Expected: 8.64 × 0.002809 × 41 = 0.995
        self.assertAlmostEqual(Qo, 0.995, places=2)

    def test_calculate_reference_time(self):
        """Test reference time calculation."""
        n = 0.2
        m = 41.0
        Q = 2640.0
        Qo = 0.995
        To = calculate_reference_time(n, m, Q, Qo)
        # Expected: (0.2 × 41 × 2640) / (2π × 0.995²) ≈ 3479.7 days
        self.assertAlmostEqual(To, 3479.7, places=0)

    def test_zero_ambient_flow_limit(self):
        """For Qo=0, T0 tends to infinity and T-tilde equals zero."""
        To = calculate_reference_time(n=0.25, m=20.0, Q=1000.0, Qo=0.0)
        self.assertTrue(math.isinf(To))
        self.assertEqual(calculate_dimensionless_time(25.0, To), 0.0)

    def test_calculate_dimensionless_time(self):
        """Test dimensionless time calculation."""
        t_years = 25.0
        To = 3479.7
        T_tilde = calculate_dimensionless_time(t_years, To)
        # Expected using 365.25 days/year.
        expected = 25.0 * DAYS_PER_YEAR / To
        self.assertAlmostEqual(T_tilde, expected, places=12)

    def test_determine_zone_type_centric(self):
        """Test zone type determination for centric circular."""
        T_tilde = 0.05
        zone_type = determine_zone_type(T_tilde)
        self.assertEqual(zone_type, "centric_circular")

    def test_determine_zone_type_eccentric(self):
        """Test zone type determination for eccentric circular."""
        T_tilde = 0.5
        zone_type = determine_zone_type(T_tilde)
        self.assertEqual(zone_type, "eccentric_circular")

    def test_determine_zone_type_uniform_flow(self):
        """Test zone type determination for uniform-flow."""
        T_tilde = 2.0
        zone_type = determine_zone_type(T_tilde)
        self.assertEqual(zone_type, "uniform_flow")


class TestGeometryGeneration(unittest.TestCase):
    """Test zone geometry generation functions."""

    def test_centric_circular_zone_basic(self):
        """Test centric circular zone generation."""
        Q = 1000.0
        t_days = DAYS_PER_YEAR
        m = 20.0
        n = 0.25
        coords = generate_centric_circular_zone(Q, t_days, m, n, num_points=8)

        # Check that we have 9 points (8 + closing point)
        self.assertEqual(len(coords), 9)

        # Check that polygon is closed
        self.assertEqual(coords[0], coords[-1])

        # Check that first point is at expected radius
        x, y = coords[0]
        R_expected = 1.1543 * math.sqrt((Q * t_days) / (math.pi * m * n))
        R_actual = math.sqrt(x**2 + y**2)
        self.assertAlmostEqual(R_actual, R_expected, places=1)

    def test_eccentric_circular_zone_basic(self):
        """Test eccentric circular zone generation."""
        Q = 2000.0
        Qo = 1.5
        T_tilde = 0.5
        coords = generate_eccentric_circular_zone(Q, Qo, T_tilde, num_points=8)

        # Check that we have 9 points (8 + closing point)
        self.assertEqual(len(coords), 9)

        # Check that polygon is closed
        self.assertEqual(coords[0], coords[-1])

    def test_uniform_flow_zone_basic(self):
        """Test uniform-flow zone generation."""
        Q = 2640.0
        Qo = 0.995
        T_tilde = 2.622
        coords = generate_uniform_flow_zone(Q, Qo, T_tilde, num_points=100)

        # Check that we have coordinates
        self.assertGreater(len(coords), 10)

        # Check that polygon is closed
        self.assertEqual(coords[0], coords[-1])

    def test_uniform_flow_zone_parameters(self):
        """Test uniform-flow zone calculated parameters."""
        Q = 2640.0
        Qo = 0.995
        T_tilde = 2.622

        # Calculate expected parameters
        Ls_expected = Q / (2 * math.pi * Qo)
        Ydiv_expected = Q / (2 * Qo)

        self.assertAlmostEqual(Ls_expected, 422.3, places=0)
        self.assertAlmostEqual(Ydiv_expected, 1326.6, places=0)


class TestGeometryValidation(unittest.TestCase):
    """Test topology and clipping of generated polygon rings."""

    def test_rejects_self_intersecting_bow_tie(self):
        """A bow-tie polygon must be rejected before it reaches QGIS."""
        coords = [
            (0.0, 0.0),
            (2.0, 2.0),
            (0.0, 2.0),
            (2.0, 0.0),
            (0.0, 0.0),
        ]
        self.assertTrue(find_self_intersections(coords))
        with self.assertRaisesRegex(ValueError, "self-intersects"):
            validate_polygon_coordinates(coords)

    def test_rejects_open_ring(self):
        """An open coordinate ring must not be accepted as a polygon."""
        with self.assertRaisesRegex(ValueError, "not closed"):
            validate_polygon_coordinates([
                (0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)
            ])

    def test_uniform_flow_zone_valid_for_representative_times(self):
        """Uniform-flow zones remain simple from just above T=1 to long travel times."""
        for T_tilde in [1.000001, 1.01, 1.1, 2.0, 2.622, 5.0, 10.0, 20.0, 50.0]:
            with self.subTest(T_tilde=T_tilde):
                coords = generate_uniform_flow_zone(
                    Q=2640.0,
                    Qo=0.995,
                    T_tilde=T_tilde,
                    num_points=200,
                )
                validate_polygon_coordinates(coords)
                self.assertEqual(find_self_intersections(coords), [])
                self.assertGreater(polygon_signed_area(coords), 0.0)

    def test_uniform_flow_zone_uses_exactly_one_upstream_closing_segment(self):
        """Only the two clipping intersections may lie on x = -Lu."""
        Q = 2640.0
        Qo = 0.995
        T_tilde = 2.622
        coords = generate_uniform_flow_zone(Q, Qo, T_tilde, num_points=200)
        Ls = Q / (2 * math.pi * Qo)
        Lu = Ls * (T_tilde + math.log(math.e + T_tilde))
        tolerance = 1e-8 * max(Lu, 1.0)

        clipping_vertices = [
            (x, y) for x, y in coords[:-1] if abs(x + Lu) <= tolerance
        ]
        self.assertEqual(len(clipping_vertices), 2)
        self.assertAlmostEqual(clipping_vertices[0][1], -clipping_vertices[1][1], places=8)

        # The downstream end is the analytical stagnation point x = Ls, y = 0.
        downstream = max(coords[:-1], key=lambda point: point[0])
        self.assertAlmostEqual(downstream[0], Ls, places=8)
        self.assertAlmostEqual(downstream[1], 0.0, places=8)
        self.assertAlmostEqual(min(x for x, _ in coords), -Lu, places=8)

    def test_uniform_flow_zone_is_symmetric_about_flow_axis(self):
        """Upper and lower boundaries must be mirror images."""
        coords = generate_uniform_flow_zone(2640.0, 0.995, 2.622, num_points=100)
        points = coords[:-1]
        upper = [(x, y) for x, y in points if y >= 0.0]
        lower = [(x, y) for x, y in points if y < 0.0]
        # The downstream stagnation point lies on the symmetry axis and is
        # stored once; every other upper point has a lower mirror image.
        self.assertEqual(len(upper) - 1, len(lower))
        for (x_upper, y_upper), (x_lower, y_lower) in zip(upper[1:], reversed(lower)):
            self.assertAlmostEqual(x_upper, x_lower, places=9)
            self.assertAlmostEqual(y_upper, -y_lower, places=9)


class TestCoordinateTransformations(unittest.TestCase):
    """Test coordinate transformation functions."""

    def test_rotate_coordinates_90_degrees(self):
        """Test rotation by 90 degrees."""
        coords = [(1.0, 0.0), (0.0, 1.0)]
        # Rotate 90 degrees clockwise from North
        # This should rotate the coordinate system
        rotated = rotate_coordinates(coords, 90.0)

        self.assertEqual(len(rotated), 2)
        # 90° from North aligns local +X with global +X.
        self.assertAlmostEqual(rotated[0][0], 1.0, places=12)
        self.assertAlmostEqual(rotated[0][1], 0.0, places=12)
        self.assertAlmostEqual(rotated[1][0], 0.0, places=12)
        self.assertAlmostEqual(rotated[1][1], 1.0, places=12)

    def test_translate_coordinates(self):
        """Test coordinate translation."""
        coords = [(0.0, 0.0), (10.0, 20.0)]
        dx, dy = 100.0, 200.0
        translated = translate_coordinates(coords, dx, dy)

        self.assertEqual(len(translated), 2)
        self.assertEqual(translated[0], (100.0, 200.0))
        self.assertEqual(translated[1], (110.0, 220.0))

    def test_rotate_then_translate(self):
        """Test combined rotation and translation."""
        coords = [(10.0, 0.0)]
        # Flow direction 0° means flow toward North (+Y axis)
        # Point (10, 0) in local coords (flow toward +X) rotates to (0, 10) in global
        rotated = rotate_coordinates(coords, 0.0)
        translated = translate_coordinates(rotated, 100.0, 200.0)

        self.assertEqual(len(translated), 1)
        # After rotation (10,0) -> (0,10), then translate by (100,200) -> (100,210)
        self.assertAlmostEqual(translated[0][0], 100.0, places=1)
        self.assertAlmostEqual(translated[0][1], 210.0, places=1)


class TestCompleteCalculation(unittest.TestCase):
    """Test complete capture zone calculation workflow."""

    def test_uniform_flow_case_from_documentation(self):
        """Test complete calculation for uniform-flow zone (from documentation)."""
        params = CaptureZoneParameters(
            k=8.64,
            m=41.0,
            n=0.2,
            Q=2640.0,
            I=0.002809,
            t=25.0,
            flow_direction=111.67,
            well_x=503830.0,
            well_y=310661.0
        )

        result = calculate_capture_zone(params)

        # Check zone type
        self.assertEqual(result['zone_type'], 'uniform_flow')

        # Check calculated parameters (with tolerance for rounding)
        self.assertAlmostEqual(result['Qo'], 0.995, places=2)
        self.assertAlmostEqual(result['Ls'], 422.3, places=0)
        self.assertAlmostEqual(result['Ydiv'], 1326.6, places=0)

        # Check that geometry was generated
        self.assertGreater(len(result['geometry']), 50)

        # Check that geometry is closed and topologically valid after rotation
        # and translation to the well coordinates.
        self.assertEqual(result['geometry'][0], result['geometry'][-1])
        validate_polygon_coordinates(result['geometry'])
        self.assertEqual(find_self_intersections(result['geometry']), [])

    def test_centric_circular_case(self):
        """Test complete calculation for centric circular zone."""
        params = CaptureZoneParameters(
            k=50.0,
            m=20.0,
            n=0.25,
            Q=1000.0,
            I=0.0001,
            t=1.0,
            flow_direction=0.0,
            well_x=0.0,
            well_y=0.0
        )

        result = calculate_capture_zone(params)

        # Check zone type
        self.assertEqual(result['zone_type'], 'centric_circular')

        # Check that T_tilde is small
        self.assertLess(result['T_dimensionless'], 0.1)

        # Check that R was calculated
        self.assertIsNotNone(result['R'])
        self.assertGreater(result['R'], 0)

    def test_eccentric_circular_case(self):
        """Test complete calculation for eccentric circular zone."""
        params = CaptureZoneParameters(
            k=5.0,
            m=25.0,
            n=0.3,
            Q=1500.0,
            I=0.01,
            t=3.0,
            flow_direction=180.0,
            well_x=5000.0,
            well_y=3000.0
        )

        result = calculate_capture_zone(params)

        # Check zone type (should be eccentric or uniform-flow depending on calculated T_tilde)
        self.assertIn(result['zone_type'], ['eccentric_circular', 'uniform_flow'])

        # Check that geometry was generated
        self.assertGreater(len(result['geometry']), 10)

    def test_result_structure(self):
        """Test that result contains all expected keys."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.005,
            t=10.0, flow_direction=45.0, well_x=1000.0, well_y=2000.0
        )

        result = calculate_capture_zone(params)

        # Check required keys
        required_keys = [
            'geometry', 'zone_type', 'T_dimensionless',
            'Qo', 'To', 'num_points'
        ]
        for key in required_keys:
            self.assertIn(key, result)

        # Check optional keys exist (even if None)
        optional_keys = ['Ls', 'Lu', 'Ydiv', 'R', 'delta']
        for key in optional_keys:
            self.assertIn(key, result)

    def test_lu_approximation_warning_threshold(self):
        """Equation (18) must be flagged above the Ceric–Haitjema 2.85 limit."""
        common = dict(k=10.0, m=20.0, n=0.25, Q=1000.0, t=25.0,
                      flow_direction=0.0, well_x=0.0, well_y=0.0)
        # Select gradients from the closed-form T-tilde relation.
        def result_for(target):
            t_days = common["t"] * DAYS_PER_YEAR
            qo = math.sqrt(target * common["n"] * common["m"] * common["Q"] / (2 * math.pi * t_days))
            params = CaptureZoneParameters(I=qo / (common["k"] * common["m"]), **common)
            return calculate_capture_zone(params)
        self.assertFalse(result_for(2.85)["lu_approximation_warning"])
        self.assertTrue(result_for(2.850001)["lu_approximation_warning"])


class TestZeroAmbientFlowCalculation(unittest.TestCase):
    def test_zero_gradient_produces_centric_circle(self):
        params = CaptureZoneParameters(
            k=10.0, m=20.0, n=0.25, Q=1000.0, I=0.0,
            t=5.0, flow_direction=237.0, well_x=100.0, well_y=200.0
        )
        result = calculate_capture_zone(params)
        self.assertEqual(result["zone_type"], "centric_circular")
        self.assertEqual(result["Qo"], 0.0)
        self.assertIsNone(result["To"])
        self.assertEqual(result["T_dimensionless"], 0.0)
        self.assertTrue(result["ambient_flow_zero"])
        self.assertTrue(result["reference_time_infinite"])
        expected_r = 1.1543 * math.sqrt(
            params.Q * params.t * DAYS_PER_YEAR / (math.pi * params.m * params.n)
        )
        self.assertAlmostEqual(result["R"], expected_r, places=10)
        validate_polygon_coordinates(result["geometry"])


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_very_small_gradient(self):
        """Test with very small hydraulic gradient."""
        params = CaptureZoneParameters(
            k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.00001,
            t=1.0, flow_direction=0.0, well_x=0.0, well_y=0.0
        )

        result = calculate_capture_zone(params)
        # Should produce centric circular due to very small ambient flow
        self.assertEqual(result['zone_type'], 'centric_circular')

    def test_boundary_T_tilde_exactly_0_1(self):
        """Test boundary case where T_tilde is exactly 0.1."""
        # This is tricky to set up exactly, but we can test near the boundary
        # The algorithm should handle T_tilde = 0.1 as centric_circular
        T_tilde = 0.1
        zone_type = determine_zone_type(T_tilde)
        self.assertEqual(zone_type, 'centric_circular')

    def test_boundary_T_tilde_exactly_1_0(self):
        """Test boundary case where T_tilde is exactly 1.0."""
        T_tilde = 1.0
        zone_type = determine_zone_type(T_tilde)
        self.assertEqual(zone_type, 'eccentric_circular')

    def test_all_flow_directions(self):
        """Test that all flow directions work (0, 90, 180, 270)."""
        flow_directions = [0.0, 90.0, 180.0, 270.0]

        for flow_dir in flow_directions:
            params = CaptureZoneParameters(
                k=10.0, m=30.0, n=0.25, Q=2000.0, I=0.005,
                t=5.0, flow_direction=flow_dir, well_x=0.0, well_y=0.0
            )

            result = calculate_capture_zone(params)
            # Should successfully generate geometry
            self.assertGreater(len(result['geometry']), 10)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
