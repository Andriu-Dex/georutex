"""Unit tests for pure domain metrics engine (MT-01..MT-08 & MCS-01..MCS-04).

Executes deterministically in Pytest without Odoo ORM or database.
Tests all twelve canonical metrics and edge cases (empty data, N/A).
"""

from datetime import datetime, timedelta
from odoo.addons.uta_transport_monitor.domain.metrics import (
    calculate_mcs01_gps_integrity,
    calculate_mcs02_sync_accuracy,
    calculate_mcs03_response_time,
    calculate_mcs04_incident_detection,
    calculate_mt01_route_compliance,
    calculate_mt02_punctuality,
    calculate_mt03_average_delay,
    calculate_mt04_stops_completed,
    calculate_mt05_route_deviation,
    calculate_mt06_distance_difference,
    calculate_mt07_trip_duration,
    calculate_mt08_incidents,
)


def test_mt01_route_compliance_normal_and_empty():
    """Verify MT-01 calculates gross and adjusted percentages properly."""
    # 1. Empty data -> N/A
    res_empty = calculate_mt01_route_compliance([])
    assert res_empty["is_na"] is True
    assert res_empty["display_value"] == "N/A"
    assert res_empty["denominator"] == 0

    # 2. Normal data: 10 trips (8 compliant gross, 9 compliant adjusted)
    trips = []
    for i in range(10):
        trips.append({
            "integrity_status": "completed",
            "state": "completed",
            "is_compliant_gross": i < 8,
            "is_compliant_adjusted": i < 9,
        })
    # Add 1 cancelled trip (should be excluded from denominator)
    trips.append({
        "integrity_status": "cancelled",
        "state": "cancelled",
        "is_compliant_gross": False,
        "is_compliant_adjusted": False,
    })
    # Add 1 insufficient data trip (should be excluded from denominator)
    trips.append({
        "integrity_status": "insufficient_data",
        "state": "completed",
        "is_compliant_gross": False,
        "is_compliant_adjusted": False,
    })

    res = calculate_mt01_route_compliance(trips)
    assert res["is_na"] is False
    assert res["denominator"] == 10  # Cancelled and insufficient_data excluded
    assert res["value"] == 80.0
    assert res["secondary"]["adjusted_value"] == 90.0
    assert res["secondary"]["non_compliant_count"] == 2
    assert res["secondary"]["justified_count"] == 1
    assert res["secondary"]["indeterminate_count"] == 1


def test_mt02_punctuality_departure_and_arrival():
    """Verify MT-02 requires both punctual departure AND arrival."""
    res_empty = calculate_mt02_punctuality([])
    assert res_empty["is_na"] is True

    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trips = [
        # 1: Both on time
        {
            "actual_start_utc": t0,
            "actual_end_utc": t0 + timedelta(minutes=20),
            "start_punctuality": "on_time",
            "arrival_punctuality": "on_time",
            "state": "completed",
        },
        # 2: Departure early, arrival on time
        {
            "actual_start_utc": t0 - timedelta(minutes=2),
            "actual_end_utc": t0 + timedelta(minutes=20),
            "start_punctuality": "early",
            "arrival_punctuality": "on_time",
            "state": "completed",
        },
        # 3: Departure late, arrival on time (NOT punctual trip)
        {
            "actual_start_utc": t0 + timedelta(minutes=10),
            "actual_end_utc": t0 + timedelta(minutes=20),
            "start_punctuality": "late",
            "arrival_punctuality": "on_time",
            "state": "completed",
        },
        # 4: Both late
        {
            "actual_start_utc": t0 + timedelta(minutes=10),
            "actual_end_utc": t0 + timedelta(minutes=40),
            "start_punctuality": "late",
            "arrival_punctuality": "late",
            "state": "completed",
        },
    ]

    res = calculate_mt02_punctuality(trips)
    assert res["denominator"] == 4
    assert res["numerator"] == 2  # Trips 1 and 2
    assert res["value"] == 50.0
    assert res["secondary"]["departure_punctual_count"] == 2
    assert res["secondary"]["arrival_punctual_count"] == 3


def test_mt03_average_delay_gross_and_conditional():
    """Verify MT-03 calculates general gross delay and conditional delay."""
    res_empty = calculate_mt03_average_delay([])
    assert res_empty["is_na"] is True

    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trips = [
        # Trip 1: on time (delay 0s)
        {
            "actual_end_utc": t0,
            "scheduled_end_utc": t0,
            "arrival_delay_s": 0,
            "state": "completed",
        },
        # Trip 2: on time (early, delay 0s)
        {
            "actual_end_utc": t0 - timedelta(minutes=5),
            "scheduled_end_utc": t0,
            "arrival_delay_s": -300,
            "state": "completed",
        },
        # Trip 3: 6 minutes late (360s)
        {
            "actual_end_utc": t0 + timedelta(minutes=6),
            "scheduled_end_utc": t0,
            "arrival_delay_s": 360,
            "state": "completed",
        },
        # Trip 4: 12 minutes late (720s)
        {
            "actual_end_utc": t0 + timedelta(minutes=12),
            "scheduled_end_utc": t0,
            "arrival_delay_s": 720,
            "state": "completed",
        },
    ]

    res = calculate_mt03_average_delay(trips)
    # Total delay = 0 + 0 + 6 + 12 = 18 min.
    # General gross average = 18 / 4 = 4.5 min.
    assert res["value"] == 4.5
    # Conditional average (strictly late: trips 3 & 4) = 18 / 2 = 9.0 min.
    assert res["secondary"]["conditional_avg_delay_min"] == 9.0
    assert res["secondary"]["strictly_late_trip_count"] == 2


def test_mt04_stops_completed_excludes_terminals():
    """Verify MT-04 only evaluates intermediate checkpoints, not terminals."""
    res_empty = calculate_mt04_stops_completed([])
    assert res_empty["is_na"] is True

    stops = [
        # Origin terminal (excluded)
        {"stop_type": "origin", "status": "on_time", "required": True},
        # Checkpoint 1 (visited on time)
        {"stop_type": "checkpoint", "status": "on_time", "required": True},
        # Checkpoint 2 (visited late -> counts as visited)
        {"stop_type": "checkpoint", "status": "late", "required": True},
        # Checkpoint 3 (missed -> counts in denom, not numer)
        {"stop_type": "checkpoint", "status": "missed", "required": True},
        # Checkpoint 4 (indeterminate -> excluded from denom)
        {
            "stop_type": "checkpoint",
            "status": "indeterminate",
            "required": True,
        },
        # Checkpoint 5 (not_determinable -> excluded from denom)
        {
            "stop_type": "checkpoint",
            "status": "not_determinable",
            "required": True,
        },
        # Checkpoint 6 (pending -> excluded from denom)
        {
            "stop_type": "checkpoint",
            "status": "pending",
            "required": True,
        },
        # Destination terminal (excluded)
        {"stop_type": "destination", "status": "on_time", "required": True},
    ]

    res = calculate_mt04_stops_completed(stops)
    # Denominator: 3 checkpoints (1 on_time, 1 late, 1 missed).
    assert res["denominator"] == 3
    # Numerator: 2 visited (on_time + late)
    assert res["numerator"] == 2
    assert round(res["value"], 2) == 66.67
    assert res["secondary"]["indeterminate_count"] == 2


def test_mt05_route_deviation_aggregation():
    """Verify MT-05 calculates avg max deviation, % trips, outside time."""
    trips = [
        {
            "integrity_status": "completed",
            "state": "completed",
            "max_deviation_distance_m": 10.0,
            "deviation_count": 0,
            "deviation_duration_s": 0,
        },
        {
            "integrity_status": "completed",
            "state": "completed",
            "max_deviation_distance_m": 80.0,
            "deviation_count": 1,
            "deviation_duration_s": 120,
        },
        # Trip with insufficient telemetry (excluded from denominator)
        {
            "integrity_status": "insufficient_data",
            "state": "completed",
            "max_deviation_distance_m": 0.0,
            "deviation_count": 0,
            "deviation_duration_s": 0,
        },
    ]

    res = calculate_mt05_route_deviation(trips)
    # Avg max distance = (10 + 80) / 2 = 45.0 m
    assert res["value"] == 45.0
    # % deviated = 1 / 2 = 50.0%
    assert res["secondary"]["deviated_trips_pct"] == 50.0
    # Total outside time = 120s / 60 = 2.0 min
    assert res["secondary"]["total_outside_time_min"] == 2.0
    assert res["secondary"]["indeterminate_count"] == 1


def test_mt06_distance_difference_weighted():
    """Verify MT-06 weighted aggregated percentage and MAE."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trips = [
        # Trip 1: planned 10,000m (10km), real 10,500m (+500m)
        {
            "scheduled_distance_m": 10000.0,
            "actual_distance_m": 10500.0,
            "actual_start_utc": t0,
            "actual_end_utc": t0 + timedelta(minutes=30),
            "state": "completed",
        },
        # Trip 2: planned 20,000m (20km), real 19,000m (-1000m)
        {
            "scheduled_distance_m": 20000.0,
            "actual_distance_m": 19000.0,
            "actual_start_utc": t0,
            "actual_end_utc": t0 + timedelta(minutes=60),
            "state": "completed",
        },
    ]

    res = calculate_mt06_distance_difference(trips)
    # Total planned = 30km. Total real = 29.5km. Diff = -0.5km (-1.67%)
    assert round(res["value"], 2) == -1.67
    assert res["secondary"]["diff_km"] == -0.5
    # Absolute errors: 0.5km, 1.0km -> MAE = 1.5 / 2 = 0.75 km
    assert res["secondary"]["mae_km"] == 0.75


def test_mt07_trip_duration_average():
    """Verify MT-07 computes real duration and comparison against planned."""
    t0 = datetime(2026, 11, 1, 8, 0, 0)
    trips = [
        # Trip 1: planned 30 min, real 35 min (+5 min)
        {
            "scheduled_start_utc": t0,
            "scheduled_end_utc": t0 + timedelta(minutes=30),
            "actual_start_utc": t0,
            "actual_end_utc": t0 + timedelta(minutes=35),
            "state": "completed",
        },
        # Trip 2: planned 50 min, real 45 min (-5 min)
        {
            "scheduled_start_utc": t0,
            "scheduled_end_utc": t0 + timedelta(minutes=50),
            "actual_start_utc": t0,
            "actual_end_utc": t0 + timedelta(minutes=45),
            "state": "completed",
        },
    ]

    res = calculate_mt07_trip_duration(trips)
    # Real durations: 35 min, 45 min -> Avg = 40.0 min
    assert res["value"] == 40.0
    # Planned durations: 30 min, 50 min -> Avg = 40.0 min
    assert res["secondary"]["planned_avg_duration_min"] == 40.0
    assert res["secondary"]["duration_difference_min"] == 0.0


def test_mt08_incidents_frequency_per_10():
    """Verify MT-08 counts and frequency per 10 executed trips."""
    incidents = [
        {
            "incident_type": "delay_start",
            "source": "automatic",
            "state": "reported",
        },
        {
            "incident_type": "route_deviation",
            "source": "automatic",
            "state": "justified",
        },
        {
            "incident_type": "traffic",
            "source": "manual",
            "state": "reported",
        },
    ]

    res = calculate_mt08_incidents(incidents, executed_trip_count=5)
    # Freq per 10 = (3 * 10) / 5 = 6.0
    assert res["value"] == 6.0
    assert res["numerator"] == 3
    assert res["denominator"] == 5
    assert res["secondary"]["breakdown_by_type"]["delay_start"] == 1
    assert res["secondary"]["breakdown_by_origin"]["automatic"] == 2
    assert res["secondary"]["breakdown_by_origin"]["manual"] == 1


def test_mcs01_gps_integrity():
    """Verify MCS-01 calculates valid position percentage and rejection."""
    reasons = {"invalid_coordinates": 5, "accuracy_exceeded": 15}
    res = calculate_mcs01_gps_integrity(
        total_received=1000,
        accepted=980,
        rejected_reasons=reasons,
    )
    assert res["value"] == 98.0
    assert res["secondary"]["rejected_count"] == 20


def test_mcs02_sync_accuracy():
    """Verify MCS-02 compares sample matches against independent expected."""
    res = calculate_mcs02_sync_accuracy(
        expected_count=500,
        matched_count=495,
        discrepancy_details={"missing_in_odoo": 5},
    )
    assert res["value"] == 99.0
    assert res["secondary"]["missing_count"] == 5


def test_mcs03_response_time_mean_and_p95():
    """Verify MCS-03 calculates mean, p50, and requires n>=30 for p95."""
    # 1. n < 30 -> p95 is N/A
    latencies_small = [120.0, 150.0, 200.0]
    res_small = calculate_mcs03_response_time(latencies_small, is_cold=True)
    assert round(res_small["value"], 2) == 156.67
    assert res_small["secondary"]["p95_ms"] is None
    assert "insuficiente" in res_small["secondary"]["p95_display"]

    # 2. n = 40 (warm) -> p95 is calculated
    latencies_large = [float(i * 10) for i in range(1, 41)]  # 10..400 ms
    res_large = calculate_mcs03_response_time(latencies_large, is_cold=False)
    # p95 index = ceil(0.95 * 40) - 1 = 38 - 1 = 37 -> value 380.0 ms
    assert res_large["secondary"]["p95_ms"] == 380.0
    assert res_large["secondary"]["min_ms"] == 10.0
    assert res_large["secondary"]["max_ms"] == 400.0


def test_mcs04_incident_detection_confusion_matrix():
    """Verify MCS-04 calculates accuracy, precision, recall on labeled data."""
    ground_truth = [
        # VP: expected True, detected True
        {
            "case_id": "C1",
            "incident_type": "delay_start",
            "expected_has_incident": True,
            "detected_has_incident": True,
        },
        # VN: expected False, detected False
        {
            "case_id": "C2",
            "incident_type": "delay_start",
            "expected_has_incident": False,
            "detected_has_incident": False,
        },
        # FP: expected False, detected True
        {
            "case_id": "C3",
            "incident_type": "route_deviation",
            "expected_has_incident": False,
            "detected_has_incident": True,
        },
        # FN: expected True, detected False
        {
            "case_id": "C4",
            "incident_type": "route_deviation",
            "expected_has_incident": True,
            "detected_has_incident": False,
        },
        # VP
        {
            "case_id": "C5",
            "incident_type": "stop_omitted",
            "expected_has_incident": True,
            "detected_has_incident": True,
        },
    ]

    res = calculate_mcs04_incident_detection(ground_truth)
    # VP=2, VN=1, FP=1, FN=1 -> Total = 5
    # Accuracy = (2 + 1) / 5 = 60.0%
    # Precision = 2 / (2 + 1) = 66.67%
    # Recall = 2 / (2 + 1) = 66.67%
    assert res["value"] == 60.0
    assert res["secondary"]["precision_pct"] == 66.67
    assert res["secondary"]["recall_pct"] == 66.67
    assert res["secondary"]["confusion_matrix"]["vp"] == 2
    assert res["secondary"]["confusion_matrix"]["vn"] == 1
    assert "delay_start" in res["secondary"]["by_incident_type"]
