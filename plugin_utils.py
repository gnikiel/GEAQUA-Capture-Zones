# -*- coding: utf-8 -*-
"""Pure-Python helpers used by GEAQUA Capture Zones."""

from typing import Iterable, Set

DAYS_PER_YEAR = 365.25

PREFERRED_POLISH_CRS: Set[str] = {
    "EPSG:2176",
    "EPSG:2177",
    "EPSG:2178",
    "EPSG:2179",
    "EPSG:2180",
}


def normalize_authid(authid: str) -> str:
    """Return a normalized authority identifier such as ``EPSG:2180``."""
    return (authid or "").strip().upper()


def is_preferred_polish_crs(authid: str) -> bool:
    """Check whether a CRS is one of the preferred Polish metric systems."""
    return normalize_authid(authid) in PREFERRED_POLISH_CRS


def sanitize_layer_component(value: str, fallback: str = "studnia") -> str:
    """Create a compact QGIS layer-name component without unsafe punctuation."""
    text = (value or "").strip()
    cleaned = []
    previous_was_separator = False

    for char in text:
        if char.isalnum():
            cleaned.append(char)
            previous_was_separator = False
        elif not previous_was_separator:
            cleaned.append("_")
            previous_was_separator = True

    result = "".join(cleaned).strip("_")
    return result or fallback


def format_time_component(time_years: float) -> str:
    """Format a travel time for use in a layer name."""
    value = float(time_years)
    if value.is_integer():
        return str(int(value))
    return (f"{value:.6f}".rstrip("0").rstrip(".")).replace(".", "_")


def build_layer_base_name(source_layer_name: str, time_years: float) -> str:
    """Build a descriptive base layer name for a calculated capture zone."""
    source = sanitize_layer_component(source_layer_name)
    time_part = format_time_component(time_years)
    return f"GEAQUA_CZ_{source}_{time_part}lat"


def make_unique_layer_name(base_name: str, existing_names: Iterable[str]) -> str:
    """Append a numeric suffix when a layer name already exists in a project."""
    existing = set(existing_names)
    if base_name not in existing:
        return base_name

    suffix = 2
    while f"{base_name}_{suffix}" in existing:
        suffix += 1
    return f"{base_name}_{suffix}"


def polygon_area(coordinates):
    """Return the absolute shoelace area of a polygon coordinate sequence."""
    coords = list(coordinates or [])
    if len(coords) < 3:
        return 0.0
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return abs(0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(coords, coords[1:])
    ))


def assess_zone_scale(calculation_result, input_params):
    """Assess whether a calculated zone is unusually large.

    The check is intentionally advisory. It compares the maximum bounding-box
    dimension with two physically meaningful reference distances:
    the pumping-dominated radial scale and the natural advective travel
    distance. It also applies high absolute thresholds. The function returns
    ``None`` for ordinary results or a diagnostics dictionary for a warning.
    """
    import math

    coordinates = list((calculation_result or {}).get("geometry") or [])
    if len(coordinates) < 3:
        return None

    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    # Measure extents along and across the declared groundwater-flow axis.
    # This is rotation-invariant for the calculated zone and remains O(n).
    ux, uy = flow_axis_unit_vector(input_params.get("flow_direction", 0.0))
    along = [x * ux + y * uy for x, y in coordinates]
    across = [-x * uy + y * ux for x, y in coordinates]
    max_dimension = max(max(along) - min(along), max(across) - min(across))
    area_m2 = polygon_area(coordinates)

    try:
        k = float(input_params["k"])
        m = float(input_params["m"])
        n = float(input_params["n"])
        q = float(input_params["Q"])
        gradient = float(input_params["I"])
        years = float(input_params["t"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None

    if min(k, m, n, q, years) <= 0 or gradient < 0:
        return None

    days = years * DAYS_PER_YEAR
    pumping_scale = math.sqrt((q * days) / (math.pi * m * n))
    advective_distance = (k * gradient / n) * days
    reference_scale = max(pumping_scale, advective_distance, 1.0)
    ratio = max_dimension / reference_scale
    area_km2 = area_m2 / 1_000_000.0

    reasons = []
    if max_dimension >= 20_000.0:
        reasons.append("absolute_dimension")
    if area_km2 >= 100.0:
        reasons.append("absolute_area")
    if max_dimension >= 5_000.0 and ratio >= 8.0:
        reasons.append("relative_dimension")

    if not reasons:
        return None

    return {
        "width_m": width,
        "height_m": height,
        "max_dimension_m": max_dimension,
        "area_m2": area_m2,
        "area_km2": area_km2,
        "pumping_scale_m": pumping_scale,
        "advective_distance_m": advective_distance,
        "reference_scale_m": reference_scale,
        "dimension_ratio": ratio,
        "reasons": tuple(reasons),
    }


def flow_axis_unit_vector(flow_direction_degrees):
    """Return the global unit vector of flow for azimuth clockwise from North."""
    import math
    angle = math.radians(float(flow_direction_degrees))
    return math.sin(angle), math.cos(angle)


def local_axis_extents(calculation_result):
    """Return positive upstream and downstream extents from the well in metres."""
    result = calculation_result or {}
    zone_type = result.get("zone_type")

    if zone_type == "centric_circular":
        radius = max(float(result.get("R") or 0.0), 0.0)
        return radius, radius

    if zone_type == "eccentric_circular":
        radius = max(float(result.get("R") or 0.0), 0.0)
        delta = max(float(result.get("delta") or 0.0), 0.0)
        return radius + delta, max(radius - delta, radius * 0.1)

    if zone_type == "uniform_flow":
        upstream = max(float(result.get("Lu") or 0.0), 0.0)
        downstream = max(float(result.get("Ls") or 0.0), 0.0)
        return upstream, downstream

    return 0.0, 0.0


def build_direction_graphics(calculation_result, input_params):
    """Build map coordinates for the arrow and upstream/downstream labels."""
    well_x = float(input_params["well_x"])
    well_y = float(input_params["well_y"])
    ux, uy = flow_axis_unit_vector(input_params["flow_direction"])
    upstream, downstream = local_axis_extents(calculation_result)

    # Fallback to the geometry projection when a zone-specific parameter is
    # unavailable. This also protects preview rendering from partial results.
    if upstream <= 0 or downstream <= 0:
        projections = []
        for x, y in (calculation_result or {}).get("geometry", []):
            projections.append((x - well_x) * ux + (y - well_y) * uy)
        if projections:
            upstream = max(upstream, abs(min(projections)))
            downstream = max(downstream, max(projections))

    upstream = max(upstream, 1.0)
    downstream = max(downstream, 1.0)

    arrow_start = (
        well_x - ux * upstream * 0.55,
        well_y - uy * upstream * 0.55,
    )
    arrow_end = (
        well_x + ux * downstream * 0.75,
        well_y + uy * downstream * 0.75,
    )
    upstream_label = (
        well_x - ux * upstream * 0.72,
        well_y - uy * upstream * 0.72,
    )
    downstream_label = (
        well_x + ux * downstream * 0.58,
        well_y + uy * downstream * 0.58,
    )

    return {
        "well": (well_x, well_y),
        "arrow_start": arrow_start,
        "arrow_end": arrow_end,
        "upstream_label": upstream_label,
        "downstream_label": downstream_label,
        "upstream_extent_m": upstream,
        "downstream_extent_m": downstream,
    }

STANDARD_TIME_VARIANTS = (1.0, 5.0, 10.0, 25.0, 50.0)


def build_calculation_name(source_layer_name: str, time_years=None, standard_variants: bool = False) -> str:
    """Build the editable default calculation/layer name shown in the dialog."""
    source = sanitize_layer_component(source_layer_name or "S1", fallback="S1")
    if not source.lower().startswith("studnia"):
        source = f"Studnia_{source}"
    if standard_variants:
        return f"{source}_warianty_1_5_10_25_50_lat"
    value = 25.0 if time_years in (None, "") else float(time_years)
    return f"{source}_{format_time_component(value)}_lat"


def zone_dimensions(calculation_result, input_params):
    """Measure upstream, downstream, total length and maximum width in flow axes.

    Measurements are derived directly from the final rotated/transformed polygon,
    which makes them consistent for all three analytical zone types.
    """
    coordinates = list((calculation_result or {}).get("geometry") or [])
    if not coordinates:
        return {
            "upstream_m": 0.0,
            "downstream_m": 0.0,
            "length_m": 0.0,
            "width_m": 0.0,
        }
    well_x = float((input_params or {}).get("well_x", 0.0))
    well_y = float((input_params or {}).get("well_y", 0.0))
    ux, uy = flow_axis_unit_vector((input_params or {}).get("flow_direction", 0.0))
    along = []
    across = []
    for x, y in coordinates:
        dx = float(x) - well_x
        dy = float(y) - well_y
        along.append(dx * ux + dy * uy)
        across.append(-dx * uy + dy * ux)
    upstream = max(0.0, -min(along))
    downstream = max(0.0, max(along))
    width = max(across) - min(across)
    return {
        "upstream_m": upstream,
        "downstream_m": downstream,
        "length_m": upstream + downstream,
        "width_m": width,
    }
