"""Unit tests for pure domain evaluation functions in GeoRutex (Phase 4).

Executes deterministically in Pytest without Odoo ORM or database.
Tests RF-20 through RF-26 rules and edge cases.
"""

from datetime import datetime, timedelta
from odoo.addons.uta_transport_monitor.domain.evaluation import (
    detect_gps_gaps,
    detect_route_deviations,
    evaluate_stop_visits,
    evaluate_trip_actual_times,
    evaluate_trip_compliance,
)
from odoo.addons.uta_transport_monitor.domain.geo import (
    distance_to_polyline,
    point_to_segment_distance,
)


def test_point_to_segment_distance_exact():
    """Verify orthogonal distance from point to a horizontal segment."""
    # Segment from (-1.0, -78.0) to (-1.0, -77.0) along latitude -1.0
    # Query point at (-0.99, -77.5) which is ~1.11 km north of midpoint
    d = point_to_segment_distance(
        -0.99, -77.5,
        -1.0, -78.0,
        -1.0, -77.0,
    )
    # 0.01 degree latitude is ~1111 meters
    assert 1100.0 < d < 1120.0


def test_distance_to_polyline():
    """Verify distance_to_polyline against GeoJSON coordinates."""
    polyline = [
        [-78.6272, -1.2618],
        [-78.6250, -1.2580],
        [-78.6265, -1.2425],
    ]
    # Point exactly on segment 1
    d = distance_to_polyline(-1.2618, -78.6272, polyline, is_geojson=True)
    assert d < 1.0


def test_evaluate_trip_actual_times_departure_and_arrival():
    """Test RF-20 start when leaving origin and end when entering dest."""
    origin = {"latitude": -1.2618, "longitude": -78.6272, "radius_m": 30.0}
    dest = {"latitude": -1.2335, "longitude": -78.6225, "radius_m": 30.0}

    t0 = datetime(2026, 11, 1, 8, 0, 0)
    positions = [
        # Inside origin
        {
            "fix_time": t0,
            "latitude": -1.2618,
            "longitude": -78.6272,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=2),
            "latitude": -1.26182,
            "longitude": -78.62721,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Departs origin (> 30m away)
        {
            "fix_time": t0 + timedelta(minutes=5),
            "latitude": -1.2580,
            "longitude": -78.6250,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # En route
        {
            "fix_time": t0 + timedelta(minutes=15),
            "latitude": -1.2450,
            "longitude": -78.6260,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Enters destination
        {
            "fix_time": t0 + timedelta(minutes=25),
            "latitude": -1.2335,
            "longitude": -78.6225,
            "accuracy": 5.0,
            "is_valid": True,
        },
    ]

    res = evaluate_trip_actual_times(
        positions, origin, dest, default_radius_m=30.0
    )
    assert res["actual_start_utc"] == t0 + timedelta(minutes=5)
    assert res["actual_end_utc"] == t0 + timedelta(minutes=25)
    assert res["start_evidence"] == "origin_geofence_departure"
    assert res["end_evidence"] == "destination_geofence_arrival"


def test_evaluate_stop_visits_on_time_late_missed():
    """Test checkpoint evaluations under lateness tolerances."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    stops = [
        {
            "id": 1,
            "sequence": 10,
            "name": "Parada 1",
            "stop_type": "checkpoint",
            "latitude": -1.2500,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "required": True,
            "scheduled_at_utc": t0 + timedelta(minutes=10),
        },
        {
            "id": 2,
            "sequence": 20,
            "name": "Parada 2 (Late)",
            "stop_type": "checkpoint",
            "latitude": -1.2400,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "required": True,
            "scheduled_at_utc": t0 + timedelta(minutes=20),
        },
        {
            "id": 3,
            "sequence": 30,
            "name": "Parada 3 (Missed)",
            "stop_type": "checkpoint",
            "latitude": -1.2300,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "required": True,
            "scheduled_at_utc": t0 + timedelta(minutes=30),
        },
    ]

    positions = [
        # Visited stop 1 on time (+1 min delay <= 300s)
        {
            "fix_time": t0 + timedelta(minutes=11),
            "latitude": -1.2500,
            "longitude": -78.6200,
            "is_valid": True,
        },
        # Visited stop 2 late (+15 min delay = 900s > 300s)
        {
            "fix_time": t0 + timedelta(minutes=35),
            "latitude": -1.2400,
            "longitude": -78.6200,
            "is_valid": True,
        },
        # Continuous stream around stop 3 window staying 2.2 km away
        {
            "fix_time": t0 + timedelta(minutes=28),
            "latitude": -1.2100,
            "longitude": -78.6200,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=30),
            "latitude": -1.2100,
            "longitude": -78.6200,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=32),
            "latitude": -1.2100,
            "longitude": -78.6200,
            "is_valid": True,
        },
    ]

    eval_results = evaluate_stop_visits(
        stops,
        positions,
        default_stop_radius_m=30.0,
        default_lateness_tolerance_s=300,
    )
    assert eval_results[0]["status"] == "on_time"
    assert eval_results[1]["status"] == "late"
    assert eval_results[2]["status"] == "missed"


def test_detect_route_deviations_and_noise_filtering():
    """Verify route deviations are detected and isolated noise filtered."""
    polyline = [
        [-78.6272, -1.2618],
        [-78.6250, -1.2580],
        [-78.6265, -1.2425],
    ]
    t0 = datetime(2026, 11, 1, 9, 0, 0)

    positions = [
        # Normal point on route
        {
            "fix_time": t0,
            "latitude": -1.2618,
            "longitude": -78.6272,
            "is_valid": True,
        },
        # Isolated noisy spike (500m away, 1 point) -> filtered
        {
            "fix_time": t0 + timedelta(seconds=10),
            "latitude": -1.2660,
            "longitude": -78.6320,
            "is_valid": True,
        },
        # Returns to route
        {
            "fix_time": t0 + timedelta(seconds=20),
            "latitude": -1.2618,
            "longitude": -78.6272,
            "is_valid": True,
        },
        # Real deviation: 3 points outside corridor (>40m) for 40s
        {
            "fix_time": t0 + timedelta(seconds=60),
            "latitude": -1.2700,
            "longitude": -78.6350,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(seconds=80),
            "latitude": -1.2720,
            "longitude": -78.6360,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(seconds=100),
            "latitude": -1.2710,
            "longitude": -78.6355,
            "is_valid": True,
        },
        # Back on route
        {
            "fix_time": t0 + timedelta(seconds=120),
            "latitude": -1.2618,
            "longitude": -78.6272,
            "is_valid": True,
        },
    ]

    deviations = detect_route_deviations(
        positions,
        polyline,
        corridor_m=40.0,
        min_consecutive_points=2,
        min_duration_s=10,
    )
    assert len(deviations) == 1
    assert deviations[0]["point_count"] == 3
    assert deviations[0]["duration_s"] == 40
    assert deviations[0]["max_distance_m"] > 40.0


def test_detect_gps_gaps():
    """Verify telemetry gaps exceeding 180 seconds are detected."""
    t0 = datetime(2026, 11, 1, 10, 0, 0)
    t1 = t0 + timedelta(seconds=60)
    t2 = t0 + timedelta(seconds=360)
    positions = [
        {"fix_time": t0, "latitude": -1.2600, "longitude": -78.6200},
        {"fix_time": t1, "latitude": -1.2605, "longitude": -78.6205},
        # 300 seconds gap (> 180s)
        {"fix_time": t2, "latitude": -1.2650, "longitude": -78.6250},
    ]

    gaps = detect_gps_gaps(positions, gap_threshold_s=180)
    assert len(gaps) == 1
    assert gaps[0]["duration_s"] == 300


def test_evaluate_trip_compliance_non_compliant():
    """Verify trip compliance fails if mandatory stops missed or deviated."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trip_info = {
        "scheduled_start_utc": t0,
        "scheduled_end_utc": t0 + timedelta(hours=1),
        "actual_start_utc": t0,
        "actual_end_utc": t0 + timedelta(hours=1),
        "position_count": 50,
    }
    stops_eval = [
        {"status": "on_time", "required": True},
        {"status": "missed", "required": True},
    ]
    deviations = [{"duration_s": 50, "max_distance_m": 120.0}]
    gaps = []
    params = {"lateness_tolerance_s": 300}

    res = evaluate_trip_compliance(
        trip_info, stops_eval, deviations, gaps, params
    )
    assert res["is_compliant_gross"] is False
    assert res["stops_missed"] == 1
    assert res["deviation_count"] == 1
    assert "No Conforme" in res["evaluation_summary"]
