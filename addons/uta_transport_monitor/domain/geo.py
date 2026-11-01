"""Deterministic geospatial calculation functions for GeoRutex.

Pure Python implementation using standard math module.
NO Odoo ORM, HTTP, or database dependencies are permitted in this module.
"""

import math

# Mean Earth radius in meters (WGS84 spherical approximation)
EARTH_RADIUS_METERS: float = 6371000.0


def is_valid_coordinate(latitude: float, longitude: float) -> bool:
    """Validate latitude and longitude bounds."""
    if not isinstance(latitude, (int, float)) or not isinstance(
        longitude, (int, float)
    ):
        return False
    if math.isnan(latitude) or math.isnan(longitude):
        return False
    if math.isinf(latitude) or math.isinf(longitude):
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def haversine_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate great-circle distance between two points in meters.

    Uses the Haversine formula.

    :param lat1: Latitude of point 1 in degrees.
    :param lon1: Longitude of point 1 in degrees.
    :param lat2: Latitude of point 2 in degrees.
    :param lon2: Longitude of point 2 in degrees.
    :return: Distance in meters.
    :raises ValueError: If coordinates are out of valid geographic bounds.
    """
    if not (
        is_valid_coordinate(lat1, lon1) and is_valid_coordinate(lat2, lon2)
    ):
        raise ValueError(
            f"Invalid coordinates: ({lat1}, {lon1}) -> ({lat2}, {lon2})"
        )

    # Identical coordinates check to avoid floating point imprecision
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp 'a' to [0.0, 1.0] to guard against floating-point errors
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c


def is_within_radius(
    point_lat: float,
    point_lon: float,
    center_lat: float,
    center_lon: float,
    radius_m: float,
) -> bool:
    """Check whether a point is within radius_m from a center point.

    :param point_lat: Latitude of point.
    :param point_lon: Longitude of point.
    :param center_lat: Latitude of center.
    :param center_lon: Longitude of center.
    :param radius_m: Radius threshold in meters (must be non-negative).
    :return: True if distance <= radius_m, False otherwise.
    """
    if radius_m < 0:
        raise ValueError(f"Radius cannot be negative: {radius_m}")
    dist = haversine_distance(point_lat, point_lon, center_lat, center_lon)
    return dist <= radius_m


def initial_bearing(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate initial compass bearing in degrees [0, 360)."""
    if not (
        is_valid_coordinate(lat1, lon1) and is_valid_coordinate(lat2, lon2)
    ):
        raise ValueError(
            f"Invalid coordinates: ({lat1}, {lon1}) -> ({lat2}, {lon2})"
        )

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    )

    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return bearing_deg


def calculate_speed_kmh(
    distance_meters: float, duration_seconds: float
) -> float:
    """Calculate speed in kilometers per hour given distance and duration.

    :param distance_meters: Distance in meters.
    :param duration_seconds: Time elapsed in seconds.
    :return: Speed in km/h. Returns 0.0 if duration is 0 or negative.
    """
    if duration_seconds <= 0.0 or distance_meters <= 0.0:
        return 0.0
    speed_mps = distance_meters / duration_seconds
    return speed_mps * 3.6


def calculate_polyline_distance(
    coordinates: list, is_geojson: bool = False
) -> float:
    """Calculate cumulative distance along a sequence of coordinate points.

    :param coordinates: List of coordinate pairs.
    :param is_geojson: True if [lon, lat] (GeoJSON), False if (lat, lon).
    :return: Cumulative distance in meters.
    :raises ValueError: If fewer than 2 points or coordinates invalid.
    """
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError(
            "Polyline must contain at least 2 coordinate points."
        )

    total_distance = 0.0
    for idx in range(len(coordinates) - 1):
        pt1 = coordinates[idx]
        pt2 = coordinates[idx + 1]

        if is_geojson:
            lon1, lat1 = pt1[0], pt1[1]
            lon2, lat2 = pt2[0], pt2[1]
        else:
            lat1, lon1 = pt1[0], pt1[1]
            lat2, lon2 = pt2[0], pt2[1]

        total_distance += haversine_distance(lat1, lon1, lat2, lon2)

    return total_distance


def point_to_segment_distance(
    p_lat: float,
    p_lon: float,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> float:
    """Calculate minimum orthogonal distance from point P to line segment AB.

    Uses equirectangular metric projection centered on the segment, which is
    accurate to millimeters over urban transit scales (< 50 km).

    :param p_lat: Latitude of query point.
    :param p_lon: Longitude of query point.
    :param a_lat: Latitude of segment start point.
    :param a_lon: Longitude of segment start point.
    :param b_lat: Latitude of segment end point.
    :param b_lon: Longitude of segment end point.
    :return: Minimum distance in meters from point P to segment AB.
    """
    if not (
        is_valid_coordinate(p_lat, p_lon)
        and is_valid_coordinate(a_lat, a_lon)
        and is_valid_coordinate(b_lat, b_lon)
    ):
        raise ValueError(
            "Invalid coordinates provided to point_to_segment_distance."
        )

    # Identical endpoints fallback
    if a_lat == b_lat and a_lon == b_lon:
        return haversine_distance(p_lat, p_lon, a_lat, a_lon)

    # Local equirectangular projection centered on segment midpoint
    mid_lat_rad = math.radians((a_lat + b_lat) / 2.0)
    cos_lat = math.cos(mid_lat_rad)
    deg_to_m = (math.pi / 180.0) * EARTH_RADIUS_METERS

    dx = (b_lon - a_lon) * cos_lat * deg_to_m
    dy = (b_lat - a_lat) * deg_to_m
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq <= 1e-9:
        return haversine_distance(p_lat, p_lon, a_lat, a_lon)

    px = (p_lon - a_lon) * cos_lat * deg_to_m
    py = (p_lat - a_lat) * deg_to_m

    t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
    nx = t * dx
    ny = t * dy

    return math.hypot(px - nx, py - ny)


def distance_to_polyline(
    point_lat: float,
    point_lon: float,
    coordinates: list,
    is_geojson: bool = True,
) -> float:
    """Calculate minimum distance from a point to a polyline.

    :param point_lat: Latitude of point.
    :param point_lon: Longitude of point.
    :param coordinates: List of coordinate pairs.
    :param is_geojson: True if [lon, lat] (GeoJSON), False if (lat, lon).
    :return: Minimum distance in meters to the polyline.
    :raises ValueError: If coordinates list is invalid or contains < 2 points.
    """
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError("Polyline must contain at least 2 coordinate points.")

    min_dist = float("inf")
    for idx in range(len(coordinates) - 1):
        pt1 = coordinates[idx]
        pt2 = coordinates[idx + 1]

        if is_geojson:
            lon1, lat1 = pt1[0], pt1[1]
            lon2, lat2 = pt2[0], pt2[1]
        else:
            lat1, lon1 = pt1[0], pt1[1]
            lat2, lon2 = pt2[0], pt2[1]

        d = point_to_segment_distance(
            point_lat, point_lon, lat1, lon1, lat2, lon2
        )
        if d < min_dist:
            min_dist = d

    return min_dist
