"""Unit tests for pure domain evaluation functions in GeoRutex (Phase 4 & 5).

Executes deterministically in Pytest without Odoo ORM or database.
Tests RF-20 through RF-26 rules and edge cases with >= 85% domain coverage.
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
        # Still inside origin (10m)
        {
            "fix_time": t0 + timedelta(minutes=2),
            "latitude": -1.26185,
            "longitude": -78.62725,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Departs origin (> 30m) -> RF-20 actual start
        {
            "fix_time": t0 + timedelta(minutes=5),
            "latitude": -1.2600,
            "longitude": -78.6260,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Arrives at destination (< 30m) -> RF-20 actual end
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
    assert res["first_gps_fix_utc"] == t0
    assert res["start_evidence"] == "origin_geofence_departure"
    assert res["end_evidence"] == "destination_geofence_arrival"


def test_evaluate_trip_actual_times_edge_cases():
    """Test edge cases: empty positions, accuracy, stay, fallback outside."""
    origin = {"latitude": -1.2618, "longitude": -78.6272, "radius_m": 30.0}
    dest = {"latitude": -1.2335, "longitude": -78.6225, "radius_m": 30.0}

    # 1. Empty positions
    res = evaluate_trip_actual_times([], origin, dest)
    assert res["actual_start_utc"] is None
    assert res["start_evidence"] == "no_data"

    # 2. Inaccurate positions filtered out
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    inacc = [{
        "fix_time": t0,
        "latitude": -1.2618,
        "longitude": -78.6272,
        "accuracy": 150.0,
        "is_valid": True,
    }]
    res = evaluate_trip_actual_times(inacc, origin, dest, accuracy_max_m=100.0)
    assert res["start_evidence"] == "insufficient_accuracy"

    # 3. Stays inside origin geofence throughout
    stay = [
        {
            "fix_time": t0,
            "latitude": -1.2618,
            "longitude": -78.6272,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=5),
            "latitude": -1.26181,
            "longitude": -78.62721,
            "accuracy": 5.0,
            "is_valid": True,
        },
    ]
    res = evaluate_trip_actual_times(stay, origin, dest)
    assert res["actual_start_utc"] is None
    assert res["start_evidence"] == "still_at_origin"
    assert res["end_evidence"] == "destination_not_reached"

    # 4. Bus starts outside origin with moving speed >= 5 km/h
    outside_moving = [
        {
            "fix_time": t0,
            "latitude": -1.2500,
            "longitude": -78.6200,
            "speed": 15.0,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=1),
            "latitude": -1.2400,
            "longitude": -78.6210,
            "speed": 20.0,
            "accuracy": 5.0,
            "is_valid": True,
        },
    ]
    res = evaluate_trip_actual_times(outside_moving, origin, dest)
    assert res["actual_start_utc"] == t0
    assert res["start_evidence"] == "first_moving_fix_outside_origin"

    # 5. Bus starts outside stationary (speed 0)
    outside_stat = [{
        "fix_time": t0,
        "latitude": -1.2500,
        "longitude": -78.6200,
        "speed": 0.0,
        "accuracy": 5.0,
        "is_valid": True,
    }]
    res = evaluate_trip_actual_times(outside_stat, origin, dest)
    assert res["actual_start_utc"] == t0
    assert res["start_evidence"] == "first_valid_fix_fallback"

    # 6. No origin defined
    res = evaluate_trip_actual_times(outside_stat, None, None)
    assert res["actual_start_utc"] == t0
    assert res["start_evidence"] == "first_valid_fix_no_origin"


def test_evaluate_stop_visits_on_time_late_missed():
    """Verify RF-22/23: on_time, late, missed, and gap handling."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    stops = [
        {
            "id": 1,
            "sequence": 1,
            "name": "Parada 1",
            "latitude": -1.2600,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "scheduled_at_utc": t0 + timedelta(minutes=10),
            "required": True,
        },
        {
            "id": 2,
            "sequence": 2,
            "name": "Parada 2",
            "latitude": -1.2500,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "scheduled_at_utc": t0 + timedelta(minutes=20),
            "required": True,
        },
        {
            "id": 3,
            "sequence": 3,
            "name": "Parada 3",
            "latitude": -1.2400,
            "longitude": -78.6200,
            "radius_m": 30.0,
            "scheduled_at_utc": t0 + timedelta(minutes=30),
            "required": True,
        },
    ]

    positions = [
        # Parada 1: visited at 08:12 (2 min late, tolerance 5 min) -> on_time
        {
            "fix_time": t0 + timedelta(minutes=12),
            "latitude": -1.2600,
            "longitude": -78.6200,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Parada 2: visited at 08:28 (8 min late, > tolerance 5 min) -> late
        {
            "fix_time": t0 + timedelta(minutes=28),
            "latitude": -1.2500,
            "longitude": -78.6200,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Intermediate points without gaps (every 2 min <= 180s)
        {
            "fix_time": t0 + timedelta(minutes=30),
            "latitude": -1.2450,
            "longitude": -78.6250,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(minutes=32),
            "latitude": -1.2400,
            "longitude": -78.6250,
            "accuracy": 5.0,
            "is_valid": True,
        },
        # Parada 3: not visited, trace bypasses at ~556m away at 08:34
        {
            "fix_time": t0 + timedelta(minutes=34),
            "latitude": -1.2400,
            "longitude": -78.6250,
            "accuracy": 5.0,
            "is_valid": True,
        },
    ]

    eval_stops = evaluate_stop_visits(
        stops,
        positions,
        default_lateness_tolerance_s=300,
        gap_threshold_s=180,
    )

    assert len(eval_stops) == 3
    assert eval_stops[0]["status"] == "on_time"
    assert eval_stops[0]["delay_s"] == 120
    assert eval_stops[1]["status"] == "late"
    assert eval_stops[1]["delay_s"] == 480
    assert eval_stops[2]["status"] == "missed"


def test_evaluate_stop_visits_edge_cases():
    """Verify stop evaluation with invalid coords, no fixes, and gap."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    stops = [
        {
            "id": 1,
            "sequence": 1,
            "latitude": 999.0,
            "longitude": 999.0,
            "required": True,
        },
        {
            "id": 2,
            "sequence": 2,
            "latitude": -1.2500,
            "longitude": -78.6200,
            "scheduled_at_utc": t0,
            "required": True,
        },
    ]

    # Invalid coordinates
    res = evaluate_stop_visits(stops, [])
    assert res[0]["status"] == "indeterminate"
    assert res[1]["status"] == "indeterminate"

    # Gap across scheduled stop window
    t_sched = t0 + timedelta(minutes=10)
    stop_gap = [{
        "id": 3,
        "latitude": -1.2500,
        "longitude": -78.6200,
        "scheduled_at_utc": t_sched,
        "required": True,
    }]
    positions_gap = [
        {
            "fix_time": t_sched - timedelta(minutes=10),
            "latitude": -1.2600,
            "longitude": -78.6200,
            "is_valid": True,
        },
        # Gap of 1200 seconds (> 180s) spanning t_sched
        {
            "fix_time": t_sched + timedelta(minutes=10),
            "latitude": -1.2400,
            "longitude": -78.6200,
            "is_valid": True,
        },
    ]
    res_gap = evaluate_stop_visits(
        stop_gap,
        positions_gap,
        gap_threshold_s=180,
        default_lateness_tolerance_s=300,
    )
    assert res_gap[0]["status"] == "indeterminate"


def test_detect_route_deviations_and_noise_filtering():
    """Verify route deviations are confirmed only when cluster >= 2 points."""
    polyline = [
        [-78.6272, -1.2618],
        [-78.6250, -1.2580],
        [-78.6230, -1.2540],
    ]
    t0 = datetime(2026, 11, 1, 9, 0, 0)
    positions = [
        # Point on route
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


def test_detect_route_deviations_accuracy_filtering_and_terminal():
    """Verify Section 7.5.2: (d_i - a_i > corridor_m) and terminal cluster."""
    polyline = [
        [-78.6200, -1.2500],
        [-78.6250, -1.2500],
    ]
    t0 = datetime(2026, 11, 1, 9, 0, 0)

    # Point at -1.25045 (~50m away from polyline).
    # Accuracy 20m -> 50 - 20 = 30m <= 40m corridor -> NOT outside!
    positions_uncertain = [
        {
            "fix_time": t0,
            "latitude": -1.25045,
            "longitude": -78.6220,
            "accuracy": 20.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(seconds=20),
            "latitude": -1.25045,
            "longitude": -78.6230,
            "accuracy": 20.0,
            "is_valid": True,
        },
    ]
    devs = detect_route_deviations(
        positions_uncertain,
        polyline,
        corridor_m=40.0,
        min_consecutive_points=2,
    )
    assert len(devs) == 0  # Inaccuracy prevents false deviation

    # Terminal cluster (deviating until the end of the trace)
    positions_terminal = [
        {
            "fix_time": t0,
            "latitude": -1.2500,
            "longitude": -78.6200,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(seconds=30),
            "latitude": -1.2600,
            "longitude": -78.6220,
            "accuracy": 5.0,
            "is_valid": True,
        },
        {
            "fix_time": t0 + timedelta(seconds=60),
            "latitude": -1.2600,
            "longitude": -78.6230,
            "accuracy": 5.0,
            "is_valid": True,
        },
    ]
    devs_terminal = detect_route_deviations(
        positions_terminal,
        polyline,
        corridor_m=40.0,
        min_consecutive_points=2,
        min_duration_s=10,
    )
    assert len(devs_terminal) == 1
    assert devs_terminal[0]["point_count"] == 2


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

    # Less than 2 positions -> empty
    assert detect_gps_gaps([]) == []
    assert detect_gps_gaps([positions[0]]) == []


def test_evaluate_trip_compliance_non_compliant_and_cancelled():
    """Verify trip compliance fails if stops missed, deviated, or cancelled."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trip_info = {
        "scheduled_start_utc": t0,
        "scheduled_end_utc": t0 + timedelta(hours=1),
        "actual_start_utc": t0,
        "actual_end_utc": t0 + timedelta(hours=1),
        "position_count": 50,
        "state": "in_progress",
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

    # Cancelled trip state
    trip_cancelled = dict(trip_info, state="cancelled")
    res_canc = evaluate_trip_compliance(
        trip_cancelled, stops_eval, deviations, gaps, params
    )
    assert res_canc["integrity_status"] == "cancelled"
    assert res_canc["is_compliant_gross"] is False

    # Early start and arrival
    trip_early = {
        "scheduled_start_utc": t0,
        "scheduled_end_utc": t0 + timedelta(hours=1),
        "actual_start_utc": t0 - timedelta(minutes=10),  # 600s early > 300s
        "actual_end_utc": t0 + timedelta(minutes=30),     # 1800s early
        "position_count": 50,
    }
    res_early = evaluate_trip_compliance(
        trip_early, [{"status": "on_time", "required": True}], [], [], params
    )
    assert res_early["start_punctuality"] == "early"
    assert res_early["arrival_punctuality"] == "early"
