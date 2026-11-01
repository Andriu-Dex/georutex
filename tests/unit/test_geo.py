"""Unit tests for deterministic geospatial calculations in domain.geo."""

import math
import pytest
from odoo.addons.uta_transport_monitor.domain import geo


@pytest.mark.unit
def test_valid_coordinates():
    assert geo.is_valid_coordinate(0.0, 0.0) is True
    assert geo.is_valid_coordinate(-1.2693, -78.6272) is True
    assert geo.is_valid_coordinate(90.0, 180.0) is True
    assert geo.is_valid_coordinate(-90.0, -180.0) is True

    # Out of bounds
    assert geo.is_valid_coordinate(90.1, 0.0) is False
    assert geo.is_valid_coordinate(-90.1, 0.0) is False
    assert geo.is_valid_coordinate(0.0, 180.1) is False
    assert geo.is_valid_coordinate(0.0, -180.1) is False

    # NaN / Inf / non-numeric
    assert geo.is_valid_coordinate(float("nan"), 0.0) is False
    assert geo.is_valid_coordinate(0.0, float("inf")) is False
    assert geo.is_valid_coordinate("invalid", 0.0) is False  # type: ignore


@pytest.mark.unit
def test_haversine_identical_points():
    dist = geo.haversine_distance(-1.2693, -78.6272, -1.2693, -78.6272)
    assert dist == 0.0


@pytest.mark.unit
def test_haversine_known_distance_ambato():
    # Campus Huachi (-1.2693, -78.6272) to Parque Montalvo (-1.2417, -78.6297)
    # Distance is approximately ~3.08 km (within 3050 - 3120 m)
    dist = geo.haversine_distance(-1.2693, -78.6272, -1.2417, -78.6297)
    assert 3050.0 <= dist <= 3120.0


@pytest.mark.unit
def test_haversine_invalid_coordinates_raises():
    with pytest.raises(ValueError):
        geo.haversine_distance(100.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        geo.haversine_distance(0.0, 0.0, 0.0, 200.0)


@pytest.mark.unit
def test_is_within_radius():
    center_lat, center_lon = -1.2693, -78.6272
    # Nearby point (~50m away)
    near_lat = center_lat + 0.0003
    near_lon = center_lon
    dist = geo.haversine_distance(near_lat, near_lon, center_lat, center_lon)
    assert dist < 100.0

    assert (
        geo.is_within_radius(near_lat, near_lon, center_lat, center_lon, 100.0)
        is True
    )
    assert (
        geo.is_within_radius(near_lat, near_lon, center_lat, center_lon, 10.0)
        is False
    )

    with pytest.raises(ValueError):
        geo.is_within_radius(near_lat, near_lon, center_lat, center_lon, -5.0)


@pytest.mark.unit
def test_initial_bearing():
    # Due North: lat increases, lon constant
    bearing_north = geo.initial_bearing(0.0, 0.0, 10.0, 0.0)
    assert math.isclose(bearing_north, 0.0, abs_tol=1e-5)

    # Due East: lat constant, lon increases
    bearing_east = geo.initial_bearing(0.0, 0.0, 0.0, 10.0)
    assert math.isclose(bearing_east, 90.0, abs_tol=1e-5)

    # Due South: lat decreases, lon constant
    bearing_south = geo.initial_bearing(10.0, 0.0, 0.0, 0.0)
    assert math.isclose(bearing_south, 180.0, abs_tol=1e-5)

    # Due West: lat constant, lon decreases
    bearing_west = geo.initial_bearing(0.0, 10.0, 0.0, 0.0)
    assert math.isclose(bearing_west, 270.0, abs_tol=1e-5)

    # Invalid coordinates
    with pytest.raises(ValueError):
        geo.initial_bearing(95.0, 0.0, 0.0, 0.0)


@pytest.mark.unit
def test_calculate_speed_kmh():
    # 1000 meters in 36 seconds = 100 km/h
    speed = geo.calculate_speed_kmh(1000.0, 36.0)
    assert math.isclose(speed, 100.0, rel_tol=1e-4)

    # Zero distance
    assert geo.calculate_speed_kmh(0.0, 60.0) == 0.0

    # Non-positive duration
    assert geo.calculate_speed_kmh(100.0, 0.0) == 0.0
    assert geo.calculate_speed_kmh(100.0, -10.0) == 0.0


@pytest.mark.unit
def test_calculate_polyline_distance():
    coords_lat_lon = [
        (-1.2618, -78.6272),
        (-1.2580, -78.6250),
        (-1.2425, -78.6265),
    ]
    dist1 = geo.haversine_distance(-1.2618, -78.6272, -1.2580, -78.6250)
    dist2 = geo.haversine_distance(-1.2580, -78.6250, -1.2425, -78.6265)
    total = geo.calculate_polyline_distance(
        coords_lat_lon, is_geojson=False
    )
    assert math.isclose(total, dist1 + dist2, rel_tol=1e-5)

    coords_geojson = [
        [-78.6272, -1.2618],
        [-78.6250, -1.2580],
        [-78.6265, -1.2425],
    ]
    total_geojson = geo.calculate_polyline_distance(
        coords_geojson, is_geojson=True
    )
    assert math.isclose(total, total_geojson, rel_tol=1e-5)

    with pytest.raises(ValueError):
        geo.calculate_polyline_distance(
            [[-78.6272, -1.2618]], is_geojson=True
        )
    with pytest.raises(ValueError):
        geo.calculate_polyline_distance("not-a-list")  # type: ignore
