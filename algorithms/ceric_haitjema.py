"""Analytical time-of-travel capture-zone approximation.

The module implements the three approximate capture-zone geometries described
by Ceric and Haitjema (2005) for a single fully penetrating pumping well in a
homogeneous, isotropic aquifer with uniform regional groundwater flow:

* centric circular zone for small dimensionless travel time,
* eccentric circular zone for the transitional range,
* zone bounded by the steady-state dividing streamline for dominant regional flow.

The steady-state dividing-streamline formulation is consistent with Grubb
(1993), while the underlying uniform-flow isochrone solution follows Bear and
Jacobs (1965). The equations describe advective groundwater travel under the
stated conceptual-model assumptions and do not represent contaminant fate or
transport processes such as dispersion, sorption or decay.

Copyright (C) 2025–2026 Maciej Nikiel & Grzegorz Nikiel
License: GNU General Public License v2 or later
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import math
DAYS_PER_YEAR = 365.25
CLASSIFICATION_TOLERANCE = 1e-12

try:
    from ..qgis_logger import get_logger
    logger = get_logger(__name__)
except (ImportError, ValueError):
    # Fallback for standalone usage (tests and direct module execution).
    import logging
    logger = logging.getLogger(__name__)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


@dataclass
class CaptureZoneParameters:
    """
    Input parameters for the capture-zone calculation.

    Attributes:
        k: Hydraulic conductivity [m/d]
        m: Aquifer thickness [m]
        n: Effective porosity [-]
        Q: Well discharge [m³/d]
        hydraulic_gradient: Hydraulic gradient [-]
        t: Protection time [years]
        flow_direction: Angle from North [degrees, clockwise]
        well_x: Well X coordinate [m]
        well_y: Well Y coordinate [m]
    """
    k: float
    m: float
    n: float
    Q: float
    I: float
    t: float
    flow_direction: float
    well_x: float
    well_y: float


def validate_parameters(params: CaptureZoneParameters) -> None:
    """
    Validate input parameters for physical consistency.

    Args:
        params: CaptureZoneParameters object containing all inputs

    Raises:
        ValueError: If any parameter is invalid
    """
    # Check positive values (except coordinates)
    if params.k <= 0:
        raise ValueError(f"Hydraulic conductivity must be positive, got {params.k}")

    if params.m <= 0:
        raise ValueError(f"Aquifer thickness must be positive, got {params.m}")

    if params.Q <= 0:
        raise ValueError(f"Well discharge must be positive, got {params.Q}")

    if params.I < 0:
        raise ValueError(f"Hydraulic gradient cannot be negative, got {params.I}")

    if params.t <= 0:
        raise ValueError(f"Protection time must be positive, got {params.t}")

    # Check porosity range
    if not (0 < params.n < 1):
        raise ValueError(f"Effective porosity must be between 0 and 1, got {params.n}")

    # Check flow direction range
    if not (0 <= params.flow_direction <= 360):
        raise ValueError(f"Flow direction must be between 0 and 360 degrees, got {params.flow_direction}")

    # Check reasonable hydraulic gradient
    if params.I >= 1.0:
        raise ValueError(f"Hydraulic gradient should be less than 1.0, got {params.I}")

    logger.info("Parameter validation successful")


def calculate_ambient_flow(k: float, hydraulic_gradient: float, m: float) -> float:
    """
    Calculate ambient flow per unit width.

    This represents the natural groundwater flow in the aquifer before
    pumping influence.

    Args:
        k: Hydraulic conductivity [m/d]
        hydraulic_gradient: Hydraulic gradient [-]
        m: Aquifer thickness [m]

    Returns:
        Qo: Ambient flow per unit width [m²/d]

    Formula:
        Qo = k × hydraulic_gradient × m
    """
    Qo = k * hydraulic_gradient * m
    logger.debug(f"Ambient flow Qo = {Qo:.3f} m²/d")
    return Qo


def calculate_reference_time(n: float, m: float, Q: float, Qo: float) -> float:
    """
    Calculate reference time for the well-aquifer system.

    This is a characteristic time scale that determines the relative
    importance of well pumping versus ambient flow.

    Args:
        n: Effective porosity [-]
        m: Aquifer thickness [m]
        Q: Well discharge [m³/d]
        Qo: Ambient flow per unit width [m²/d]

    Returns:
        To: Reference time [days]

    Formula:
        To = (n × m × Q) / (2π × Qo²)
    """
    if Qo == 0:
        logger.debug("Reference time To tends to infinity because Qo = 0")
        return math.inf

    To = (n * m * Q) / (2 * math.pi * Qo**2)
    logger.debug(
        "Reference time To = %.1f days (%.2f years)",
        To,
        To / DAYS_PER_YEAR,
    )
    return To


def calculate_dimensionless_time(t_years: float, To: float) -> float:
    """
    Calculate dimensionless time parameter.

    This parameter determines which zone type (Centric Circle,
    Eccentric Circle, or Well in Uniform Flow) should be used.

    Args:
        t_years: Protection time [years]
        To: Reference time [days]

    Returns:
        T_tilde: Dimensionless time parameter [-]

    Formula:
        T̃ = t / To
        where t is converted from years to days
    """
    t_days = t_years * DAYS_PER_YEAR
    if math.isinf(To):
        return 0.0
    if To <= 0 or not math.isfinite(To):
        raise ValueError(f"Reference time must be positive and finite, got {To}")
    T_tilde = t_days / To
    logger.debug(f"Dimensionless time T̃ = {T_tilde:.3f}")
    return T_tilde


def determine_zone_type(T_tilde: float) -> str:
    """
    Determine appropriate capture zone type based on dimensionless time.

    Args:
        T_tilde: Dimensionless time parameter [-]

    Returns:
        Zone type: "centric_circular", "eccentric_circular", or "uniform_flow"

    Classification:
        - T̃ ≤ 0.1: Centric Circle (well dominates)
        - 0.1 < T̃ ≤ 1: Eccentric Circle (transition)
        - T̃ > 1: Well in Uniform Flow (ambient flow dominates)
    """
    # The tolerance prevents a value analytically equal to a decision threshold
    # from changing class solely because of floating-point round-off.
    if T_tilde <= 0.1 + CLASSIFICATION_TOLERANCE:
        zone_type = "centric_circular"
    elif T_tilde <= 1.0 + CLASSIFICATION_TOLERANCE:
        zone_type = "eccentric_circular"
    else:
        zone_type = "uniform_flow"

    logger.info(f"Zone type determined: {zone_type} (T̃ = {T_tilde:.3f})")
    return zone_type


def generate_centric_circular_zone(
    Q: float,
    t_days: float,
    m: float,
    n: float,
    num_points: int = 360
) -> List[Tuple[float, float]]:
    """
    Generate geometry for centric circular capture zone.

    Used when T̃ ≤ 0.1, meaning well pumping dominates over ambient flow.
    Creates a circular zone centered at the origin (well location).

    Args:
        Q: Well discharge [m³/d]
        t_days: Protection time [days]
        m: Aquifer thickness [m]
        n: Effective porosity [-]
        num_points: Number of points to generate circle (default: 360)

    Returns:
        List of (x, y) coordinate tuples forming a closed polygon

    Formula:
        R = 1.1543 × √(Q × t / (π × m × n))
    """
    # Calculate radius
    R = 1.1543 * math.sqrt((Q * t_days) / (math.pi * m * n))
    logger.debug(f"Centric circular zone: R = {R:.1f} m")

    # Generate circle points
    coords = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = R * math.cos(angle)
        y = R * math.sin(angle)
        coords.append((x, y))

    # Close the polygon
    coords.append(coords[0])

    return coords


def generate_eccentric_circular_zone(
    Q: float,
    Qo: float,
    T_tilde: float,
    num_points: int = 360
) -> List[Tuple[float, float]]:
    """
    Generate geometry for eccentric circular capture zone.

    Used when 0.1 < T̃ ≤ 1, representing transition between well-dominated
    and ambient-flow-dominated regimes. Creates a circular zone with center
    offset upstream.

    Args:
        Q: Well discharge [m³/d]
        Qo: Ambient flow per unit width [m²/d]
        T_tilde: Dimensionless time parameter [-]
        num_points: Number of points to generate circle (default: 360)

    Returns:
        List of (x, y) coordinate tuples forming a closed polygon

    Formulas:
        Ls = Q / (2π × Qo)           [stagnation point distance]
        R = Ls × [1.161 + ln(0.39 + T̃)]  [radius]
        δ = Ls × [0.00278 + 0.652 × T̃]   [eccentricity/offset]
    """
    # Calculate parameters
    Ls = Q / (2 * math.pi * Qo)
    R = Ls * (1.161 + math.log(0.39 + T_tilde))
    delta = Ls * (0.00278 + 0.652 * T_tilde)

    logger.debug(f"Eccentric circular zone: Ls = {Ls:.1f} m, R = {R:.1f} m, δ = {delta:.1f} m")

    # Generate circle centered at (-delta, 0) - offset upstream
    coords = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = -delta + R * math.cos(angle)
        y = R * math.sin(angle)
        coords.append((x, y))

    # Close the polygon
    coords.append(coords[0])

    return coords


def polygon_signed_area(coords: List[Tuple[float, float]]) -> float:
    """Return the signed area of a closed polygon coordinate ring.

    A positive value means counter-clockwise vertex order. The function accepts
    both explicitly closed and open rings; open rings are closed internally.
    """
    if len(coords) < 3:
        return 0.0

    ring = coords if coords[0] == coords[-1] else [*coords, coords[0]]
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(ring, ring[1:])
    )


def _orientation(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float]
) -> int:
    """Return orientation of three points: -1 clockwise, 0 collinear, 1 CCW.

    The tolerance is scaled to the local vector products rather than to the
    full polygon extent. This avoids false intersections between very short
    neighbouring segments in large polygons.
    """
    term_1 = (b[0] - a[0]) * (c[1] - a[1])
    term_2 = (b[1] - a[1]) * (c[0] - a[0])
    cross = term_1 - term_2
    tolerance = 1e-14 * max(abs(term_1), abs(term_2), 1.0)
    if abs(cross) <= tolerance:
        return 0
    return 1 if cross > 0 else -1

def _point_on_segment(
    a: Tuple[float, float],
    b: Tuple[float, float],
    p: Tuple[float, float],
    tolerance: float
) -> bool:
    """Check whether point *p* lies on segment a-b within tolerance."""
    return (
        min(a[0], b[0]) - tolerance <= p[0] <= max(a[0], b[0]) + tolerance
        and min(a[1], b[1]) - tolerance <= p[1] <= max(a[1], b[1]) + tolerance
    )


def _segments_intersect(
    a1: Tuple[float, float],
    a2: Tuple[float, float],
    b1: Tuple[float, float],
    b2: Tuple[float, float],
    coordinate_tolerance: float
) -> bool:
    """Return True when two closed line segments intersect or overlap."""
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if o1 != o2 and o3 != o4:
        return True

    if o1 == 0 and _point_on_segment(a1, a2, b1, coordinate_tolerance):
        return True
    if o2 == 0 and _point_on_segment(a1, a2, b2, coordinate_tolerance):
        return True
    if o3 == 0 and _point_on_segment(b1, b2, a1, coordinate_tolerance):
        return True
    if o4 == 0 and _point_on_segment(b1, b2, a2, coordinate_tolerance):
        return True

    return False


def find_self_intersections(
    coords: List[Tuple[float, float]]
) -> List[Tuple[int, int]]:
    """Find pairs of non-adjacent polygon segments that intersect.

    Segment indices refer to pairs ``coords[i] -> coords[i + 1]``. Adjacent
    segments, including the first and last segment of a closed ring, are not
    treated as self-intersections because they share a legitimate vertex.
    """
    if len(coords) < 4:
        return []

    ring = coords if coords[0] == coords[-1] else [*coords, coords[0]]
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    coordinate_tolerance = 1e-12 * span

    segment_count = len(ring) - 1
    intersections: List[Tuple[int, int]] = []

    for i in range(segment_count):
        a1, a2 = ring[i], ring[i + 1]
        for j in range(i + 1, segment_count):
            # Consecutive segments share a valid polygon vertex.
            if j == i + 1:
                continue
            # First and last segments are also adjacent in a closed ring.
            if i == 0 and j == segment_count - 1:
                continue

            b1, b2 = ring[j], ring[j + 1]
            if _segments_intersect(
                a1, a2, b1, b2, coordinate_tolerance
            ):
                intersections.append((i, j))

    return intersections


def validate_polygon_coordinates(coords: List[Tuple[float, float]]) -> None:
    """Validate a single-ring polygon before it is passed to QGIS.

    Raises:
        ValueError: if the ring is open, degenerate, non-finite, contains
            duplicate consecutive vertices, or self-intersects.
    """
    if not coords or len(coords) < 4:
        raise ValueError("Polygon must contain at least four coordinates")

    if coords[0] != coords[-1]:
        raise ValueError("Polygon coordinate ring is not closed")

    if any(not (math.isfinite(x) and math.isfinite(y)) for x, y in coords):
        raise ValueError("Polygon contains non-finite coordinates")

    for index, (first, second) in enumerate(zip(coords, coords[1:])):
        if first == second:
            raise ValueError(f"Polygon contains duplicate consecutive vertex at segment {index}")

    intersections = find_self_intersections(coords)
    if intersections:
        first_pair = intersections[0]
        raise ValueError(
            "Polygon self-intersects between segments "
            f"{first_pair[0]} and {first_pair[1]}"
        )

    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    bbox_area = max((max(xs) - min(xs)) * (max(ys) - min(ys)), 1.0)
    area = polygon_signed_area(coords)
    if abs(area) <= 1e-12 * bbox_area:
        raise ValueError("Polygon has zero or near-zero area")


def _uniform_flow_boundary_x(y: float, Ls: float) -> float:
    """Evaluate x = y / tan(y/Ls), using the analytical limit at y = 0."""
    if abs(y) <= 1e-14 * max(Ls, 1.0):
        return Ls
    return y / math.tan(y / Ls)


def _solve_uniform_flow_clip_y(Ls: float, Lu: float) -> float:
    """Solve y/tan(y/Ls) = -Lu on the upper branch by bisection."""
    # The required root lies between πLs/2 (x = 0) and πLs (x -> -∞).
    lower = 0.5 * math.pi * Ls
    upper = math.pi * Ls * (1.0 - 1e-12)

    def residual(y: float) -> float:
        return _uniform_flow_boundary_x(y, Ls) + Lu

    lower_value = residual(lower)
    upper_value = residual(upper)
    if lower_value <= 0 or upper_value >= 0:
        raise ValueError("Could not bracket the well-in-uniform-flow clipping intersection")

    for _ in range(100):
        midpoint = 0.5 * (lower + upper)
        value = residual(midpoint)
        if value > 0:
            lower = midpoint
        else:
            upper = midpoint

    return 0.5 * (lower + upper)


def generate_uniform_flow_zone(
    Q: float,
    Qo: float,
    T_tilde: float,
    num_points: int = 200
) -> List[Tuple[float, float]]:
    """Generate a finite, valid Well in Uniform Flow capture-zone polygon.

    The infinite analytical dividing streamline is clipped at the time-related
    upstream distance ``x = -Lu``. The implementation first solves the exact
    intersection of the upper and lower streamline branches with that line,
    then joins those two points with one upstream closing segment. No part of
    the streamline beyond the intersection is retained.

    Args:
        Q: Well discharge [m³/d]
        Qo: Ambient flow per unit width [m²/d]
        T_tilde: Dimensionless time parameter; must be greater than 1
        num_points: Approximate total number of boundary vertices

    Returns:
        Closed counter-clockwise polygon ring in local coordinates.

    Formulas:
        Ls = Q / (2π × Qo)
        Ydiv = Q / (2 × Qo) = πLs (asymptotic half-width)
        Lu = Ls × [T̃ + ln(e + T̃)]
        x = y / tan(y / Ls)
    """
    if Q <= 0 or Qo <= 0:
        raise ValueError("Q and Qo must be positive")
    if T_tilde <= 1.0:
        raise ValueError("Well in Uniform Flow zone requires dimensionless time greater than 1")
    if num_points < 8:
        raise ValueError("Well in Uniform Flow zone requires at least 8 points")

    Ls = Q / (2 * math.pi * Qo)
    Ydiv = Q / (2 * Qo)
    Lu = Ls * (T_tilde + math.log(math.e + T_tilde))
    y_clip = _solve_uniform_flow_clip_y(Ls, Lu)

    logger.debug(
        "Well in Uniform Flow zone: Ls = %.1f m, Ydiv = %.1f m, Lu = %.1f m, "
        "clip half-width = %.1f m",
        Ls, Ydiv, Lu, y_clip
    )

    # Generate the upper streamline from the downstream stagnation point to
    # its exact intersection with x = -Lu. Cosine spacing increases resolution
    # near both ends without creating duplicate vertices.
    points_per_branch = max(4, num_points // 2)
    upper: List[Tuple[float, float]] = []
    for index in range(points_per_branch + 1):
        linear_ratio = index / points_per_branch
        ratio = 0.5 - 0.5 * math.cos(math.pi * linear_ratio)
        y = ratio * y_clip
        x = _uniform_flow_boundary_x(y, Ls)
        if index == points_per_branch:
            # Enforce the analytical clipping coordinate exactly, avoiding
            # tiny floating-point discrepancies between upper and lower ends.
            x = -Lu
        upper.append((x, y))

    lower = [(x, -y) for x, y in reversed(upper)]
    coords = upper + lower

    # The final mirrored stagnation point closes the ring exactly.
    if coords[-1] != coords[0]:
        coords.append(coords[0])

    validate_polygon_coordinates(coords)
    return coords

def rotate_coordinates(
    coords: List[Tuple[float, float]],
    angle_degrees: float
) -> List[Tuple[float, float]]:
    """
    Rotate coordinates by specified angle.

    Args:
        coords: List of (x, y) coordinate tuples
        angle_degrees: Rotation angle [degrees, clockwise from North]

    Returns:
        List of rotated (x, y) coordinate tuples

    Note:
        In standard mathematical convention, North is +Y axis.
        Flow direction is measured clockwise from North.
        We need to rotate the coordinates to align local +X axis with flow direction.

        The transformation maps:
        - Local coordinate system: flow toward +X, well at origin
        - Global coordinate system: rotated by flow_direction
    """
    # Convert angle from degrees to radians
    # Flow direction is clockwise from North (+Y axis)
    # Standard rotation is counter-clockwise, so we need to adjust
    # Rotation angle for standard math: 90° - flow_direction
    theta = math.radians(90 - angle_degrees)

    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)

    rotated = []
    for x, y in coords:
        # Apply rotation matrix
        x_new = x * cos_theta - y * sin_theta
        y_new = x * sin_theta + y * cos_theta
        rotated.append((x_new, y_new))

    return rotated


def translate_coordinates(
    coords: List[Tuple[float, float]],
    dx: float,
    dy: float
) -> List[Tuple[float, float]]:
    """
    Translate coordinates by specified offset.

    Args:
        coords: List of (x, y) coordinate tuples
        dx: Translation in x direction [m]
        dy: Translation in y direction [m]

    Returns:
        List of translated (x, y) coordinate tuples
    """
    translated = [(x + dx, y + dy) for x, y in coords]
    return translated


def calculate_capture_zone(params: CaptureZoneParameters) -> Dict:
    """
    Calculate one analytical time-of-travel capture zone.

    This function orchestrates the entire calculation process:
    1. Validates input parameters
    2. Calculates hydraulic parameters (Qo, To, T̃)
    3. Determines appropriate zone type
    4. Generates zone geometry in local coordinates
    5. Rotates geometry to align with flow direction
    6. Translates geometry to well position

    Args:
        params: CaptureZoneParameters object with all input data

    Returns:
        Dictionary containing:
            - geometry: List of (x, y) coordinates forming closed polygon
            - zone_type: Type of capture zone
            - T_dimensionless: Dimensionless time parameter
            - Qo: Ambient flow [m²/d]
            - To: Reference time [days]
            - Ls: Stagnation point distance [m] (or None)
            - Lu: Upgradient extent [m] (or None)
            - Ydiv: Asymptotic half-width [m] (or None)
            - lu_approximation_warning: True when Equation (18) is no longer strictly conservative
            - R: Radius for circular zones [m] (or None)
            - delta: Eccentricity for eccentric circular [m] (or None)
            - num_points: Number of vertices in geometry

    Raises:
        ValueError: If input parameters are invalid

    Example:
        >>> params = CaptureZoneParameters(
        ...     k=8.64, m=41.0, n=0.2, Q=2640.0, I=0.002809,
        ...     t=25.0, flow_direction=111.67,
        ...     well_x=503830.0, well_y=310661.0
        ... )
        >>> result = calculate_capture_zone(params)
        >>> print(result['zone_type'])
        'uniform_flow'
    """
    logger.info("Starting capture-zone calculation")

    # Step 1: Validate parameters
    validate_parameters(params)

    # Step 2: Calculate hydraulic parameters
    Qo = calculate_ambient_flow(params.k, params.I, params.m)
    To = calculate_reference_time(params.n, params.m, params.Q, Qo)
    T_tilde = calculate_dimensionless_time(params.t, To)

    # Step 3: Determine zone type
    zone_type = determine_zone_type(T_tilde)

    # Step 4: Generate geometry in local coordinates
    # Local system: well at origin, flow toward +X axis
    t_days = params.t * DAYS_PER_YEAR

    # Initialize result parameters
    Ls = None
    Lu = None
    Ydiv = None
    R = None
    delta = None

    if zone_type == "centric_circular":
        coords = generate_centric_circular_zone(params.Q, t_days, params.m, params.n)
        # Calculate R for output
        R = 1.1543 * math.sqrt((params.Q * t_days) / (math.pi * params.m * params.n))

    elif zone_type == "eccentric_circular":
        coords = generate_eccentric_circular_zone(params.Q, Qo, T_tilde)
        # Calculate parameters for output
        Ls = params.Q / (2 * math.pi * Qo)
        R = Ls * (1.161 + math.log(0.39 + T_tilde))
        delta = Ls * (0.00278 + 0.652 * T_tilde)

    else:  # uniform_flow
        coords = generate_uniform_flow_zone(params.Q, Qo, T_tilde)
        # Calculate parameters for output
        Ls = params.Q / (2 * math.pi * Qo)
        Ydiv = params.Q / (2 * Qo)
        Lu = Ls * (T_tilde + math.log(math.e + T_tilde))

    logger.info(f"Generated {len(coords)} vertices for {zone_type} zone")

    # Step 5: Rotate to align with flow direction
    coords = rotate_coordinates(coords, params.flow_direction)

    # Step 6: Translate to well position
    coords = translate_coordinates(coords, params.well_x, params.well_y)

    # Step 7: Mandatory geometry validation before returning data to QGIS.
    # Rotation and translation preserve topology, but validating the final
    # coordinates also catches non-finite values caused by extreme inputs.
    validate_polygon_coordinates(coords)

    # Prepare result dictionary
    result = {
        'geometry': coords,
        'zone_type': zone_type,
        'T_dimensionless': T_tilde,
        'Qo': Qo,
        'To': None if math.isinf(To) else To,
        'Ls': Ls,
        'Lu': Lu,
        'Ydiv': Ydiv,
        'time_days': t_days,
        'days_per_year': DAYS_PER_YEAR,
        'ambient_flow_zero': Qo == 0,
        'reference_time_infinite': math.isinf(To),
        'lu_approximation_warning': bool(zone_type == 'uniform_flow' and T_tilde > 2.85),
        'R': R,
        'delta': delta,
        'num_points': len(coords)
    }

    logger.info("Capture-zone calculation completed successfully")

    return result


# Example usage
if __name__ == "__main__":
    """
    Example demonstrating the analytical capture-zone calculation.

    For comprehensive tests, see: test/test_ceric_haitjema.py
    Run tests with: python -m unittest test.test_ceric_haitjema
    """
    print("Ceric–Haitjema Capture-Zone Method — Example Usage")
    print("=" * 60)

    # Example: Well in Uniform Flow zone from documentation
    params = CaptureZoneParameters(
        k=8.64,           # Hydraulic conductivity [m/d]
        m=41.0,           # Aquifer thickness [m]
        n=0.2,            # Effective porosity [-]
        Q=2640.0,         # Well discharge [m³/d]
        I=0.002809,       # Hydraulic gradient [-]
        t=25.0,           # Protection time [years]
        flow_direction=111.67,  # Flow direction [degrees from North]
        well_x=503830.0,  # Well X coordinate [m]
        well_y=310661.0   # Well Y coordinate [m]
    )

    try:
        result = calculate_capture_zone(params)

        print(f"\nZone Type: {result['zone_type']}")
        print(f"Dimensionless Time (T̃): {result['T_dimensionless']:.3f}")
        print(f"Ambient Flow (Qo): {result['Qo']:.3f} m²/d")

        if result['Ls']:
            print(f"Stagnation Point (Ls): {result['Ls']:.1f} m")
        if result['Ydiv']:
            print(f"Asymptotic Half-Width (Ydiv): {result['Ydiv']:.1f} m")
        if result['Lu']:
            print(f"Upgradient Extent (Lu): {result['Lu']:.1f} m")
        if result['R']:
            print(f"Radius (R): {result['R']:.1f} m")

        print(f"\nGeometry: {result['num_points']} vertices")
        print("First 3 coordinates:")
        for i, (x, y) in enumerate(result['geometry'][:3]):
            print(f"  {i+1}. ({x:.2f}, {y:.2f})")

        print("\n✓ Calculation successful!")
        print("\nFor comprehensive testing, run:")
        print("  python -m unittest test.test_ceric_haitjema")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
