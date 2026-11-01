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
