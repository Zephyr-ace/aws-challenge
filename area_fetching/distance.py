"""Distance calculation utilities for the find_areas pipeline."""

import logging
from math import asin, cos, radians, sin, sqrt

logger = logging.getLogger("find_areas")

EARTH_RADIUS_KM = 6371.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth.

    Uses the Haversine formula with an Earth radius of 6371.0 km.

    Args:
        lat1: Latitude of the first point in degrees.
        lon1: Longitude of the first point in degrees.
        lat2: Latitude of the second point in degrees.
        lon2: Longitude of the second point in degrees.

    Returns:
        Distance in kilometres.
    """
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    distance = 2 * EARTH_RADIUS_KM * asin(sqrt(a))
    logger.debug(
        "haversine(%.4f, %.4f, %.4f, %.4f) = %.4f km",
        lat1,
        lon1,
        lat2,
        lon2,
        distance,
    )
    return distance


def point_to_segment_distance_km(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Calculate the minimum distance from point P to segment AB.

    Uses Equirectangular projection to convert lat/lon into a local
    Cartesian coordinate system, projects P onto segment AB, clamps the
    projection parameter *t* to [0, 1], converts back to lat/lon and
    returns the Haversine distance.

    Args:
        px: Latitude of point P in degrees.
        py: Longitude of point P in degrees.
        ax: Latitude of segment endpoint A in degrees.
        ay: Longitude of segment endpoint A in degrees.
        bx: Latitude of segment endpoint B in degrees.
        by: Longitude of segment endpoint B in degrees.

    Returns:
        Distance in kilometres from P to the nearest point on segment AB.
    """
    # Degenerate case: A and B are identical → point-to-point distance
    if ax == bx and ay == by:
        logger.debug(
            "point_to_segment_distance_km: degenerate segment A==B, "
            "falling back to haversine(P, A)"
        )
        return haversine(px, py, ax, ay)

    # Local Equirectangular projection relative to P as origin
    cos_lat = cos(radians(px))

    # Convert A and B to km offsets relative to P
    ax_km = (ay - py) * cos_lat * 111.32
    ay_km = (ax - px) * 111.32
    bx_km = (by - py) * cos_lat * 111.32
    by_km = (bx - px) * 111.32

    # Vector AB
    abx = bx_km - ax_km
    aby = by_km - ay_km

    # Vector AP (P is at the origin)
    apx = -ax_km
    apy = -ay_km

    ab_sq = abx * abx + aby * aby

    # Projection parameter t, clamped to [0, 1]
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_sq))

    # Nearest point on the segment in local coordinates
    nearest_x = ax_km + t * abx
    nearest_y = ay_km + t * aby

    # Convert back to lat/lon
    nearest_lon = py + nearest_x / (cos_lat * 111.32)
    nearest_lat = px + nearest_y / 111.32

    distance = haversine(px, py, nearest_lat, nearest_lon)

    logger.debug(
        "point_to_segment_distance_km("
        "P=(%.4f, %.4f), A=(%.4f, %.4f), B=(%.4f, %.4f)) "
        "t=%.4f, nearest=(%.4f, %.4f), dist=%.4f km",
        px, py, ax, ay, bx, by,
        t, nearest_lat, nearest_lon, distance,
    )
    return distance


def min_distance_to_power_line(
    area_lat: float,
    area_lon: float,
    power_line_geometry: list[dict],
) -> float:
    """Calculate the minimum distance from an area to a power line polyline.

    Iterates over all segments of the polyline and returns the minimum
    point-to-segment distance using :func:`point_to_segment_distance_km`.

    Args:
        area_lat: Latitude of the area centre in degrees.
        area_lon: Longitude of the area centre in degrees.
        power_line_geometry: List of dicts with ``"lat"`` and ``"lon"`` keys
            representing the nodes of the polyline.

    Returns:
        Minimum distance in kilometres, or ``float("inf")`` if the geometry
        has fewer than 2 nodes.
    """
    if len(power_line_geometry) < 2:
        logger.debug(
            "min_distance_to_power_line: geometry has %d node(s), returning inf",
            len(power_line_geometry),
        )
        return float("inf")

    min_dist = float("inf")
    for i in range(len(power_line_geometry) - 1):
        node_a = power_line_geometry[i]
        node_b = power_line_geometry[i + 1]
        dist = point_to_segment_distance_km(
            area_lat, area_lon,
            node_a["lat"], node_a["lon"],
            node_b["lat"], node_b["lon"],
        )
        min_dist = min(min_dist, dist)

    logger.debug(
        "min_distance_to_power_line(%.4f, %.4f, %d segments) = %.4f km",
        area_lat,
        area_lon,
        len(power_line_geometry) - 1,
        min_dist,
    )
    return min_dist
