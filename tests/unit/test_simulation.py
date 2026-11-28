"""Unit tests for simulated GPS track synthesis in domain.simulation."""

from datetime import datetime
import random

import pytest
from odoo.addons.uta_transport_monitor.domain import geo, simulation

# Straight north-south line of ~4.4 km near Ambato, GeoJSON [lon, lat].
POLYLINE = [[-78.6200, -1.2700 + i * 0.004] for i in range(11)]
STOPS = [
    {"lat": -1.2700, "lon": -78.6200, "offset_s": 0, "stop_type": "origin"},
    {"lat": -1.2620, "lon": -78.6200, "offset_s": 360, "stop_type": "checkpoint"},
    {"lat": -1.2540, "lon": -78.6200, "offset_s": 720, "stop_type": "checkpoint"},
    {"lat": -1.2300, "lon": -78.6200, "offset_s": 1200, "stop_type": "destination"},
]
START = datetime(2026, 11, 2, 12, 0, 0)


def _track(scenario, seed=7):
    return simulation.build_track(
        POLYLINE, STOPS, START, 1200, scenario, random.Random(seed)
    )


def _max_offset_m(track):
    return max(
        geo.distance_to_polyline(p["latitude"], p["longitude"], POLYLINE) for p in track
    )


@pytest.mark.unit
def test_on_time_track_follows_route_and_schedule():
    track = _track(simulation.SCENARIO_ON_TIME)
    times = [p["fix_time"] for p in track]
    assert times == sorted(times) and len(set(times)) == len(times)
    assert _max_offset_m(track) < 25
    duration = (times[-1] - START).total_seconds()
    assert 1100 <= duration <= 1350
    last = track[-1]
    assert geo.haversine_distance(last["latitude"], last["longitude"], -1.2300, -78.6200) < 25


@pytest.mark.unit
def test_fast_on_time_track_emits_a_fix_inside_every_stop_radius():
    track = simulation.build_track(
        POLYLINE, STOPS, START, 300, simulation.SCENARIO_ON_TIME, random.Random(3), interval_s=30
    )
    for stop in STOPS:
        nearest = min(
            geo.haversine_distance(p["latitude"], p["longitude"], stop["lat"], stop["lon"])
            for p in track
        )
        assert nearest < 25


@pytest.mark.unit
def test_stops_between_sparse_vertices_are_still_visited():
    sparse = [POLYLINE[0], POLYLINE[-1]]
    track = simulation.build_track(
        sparse, STOPS, START, 1200, simulation.SCENARIO_ON_TIME, random.Random(5), interval_s=30
    )
    for stop in STOPS:
        arrival = min(
            track,
            key=lambda p: geo.haversine_distance(p["latitude"], p["longitude"], stop["lat"], stop["lon"]),
        )
        assert geo.haversine_distance(arrival["latitude"], arrival["longitude"], stop["lat"], stop["lon"]) < 25
        assert abs((arrival["fix_time"] - START).total_seconds() - stop["offset_s"]) < 120


@pytest.mark.unit
def test_build_track_is_reproducible_with_same_seed():
    assert _track(simulation.SCENARIO_LATE, 3) == _track(simulation.SCENARIO_LATE, 3)


@pytest.mark.unit
def test_late_track_arrives_later_than_tolerance():
    durations = [
        (_track(simulation.SCENARIO_LATE, seed)[-1]["fix_time"] - START).total_seconds()
        for seed in range(6)
    ]
    assert min(durations) > 1200 + 300


@pytest.mark.unit
def test_deviation_and_missed_stop_leave_the_corridor():
    assert _max_offset_m(_track(simulation.SCENARIO_DEVIATION)) > 120
    missed = _track(simulation.SCENARIO_MISSED_STOP)
    for stop in STOPS[1:3]:
        nearest = min(
            geo.haversine_distance(p["latitude"], p["longitude"], stop["lat"], stop["lon"])
            for p in missed
        )
        if nearest > 100:
            break
    else:
        pytest.fail("No checkpoint was skipped")


@pytest.mark.unit
def test_incomplete_track_stops_before_destination():
    last = _track(simulation.SCENARIO_INCOMPLETE)[-1]
    assert geo.haversine_distance(last["latitude"], last["longitude"], -1.2300, -78.6200) > 1000


@pytest.mark.unit
def test_gps_loss_track_contains_a_long_gap():
    times = [p["fix_time"] for p in _track(simulation.SCENARIO_GPS_LOSS)]
    longest = max((b - a).total_seconds() for a, b in zip(times, times[1:]))
    assert longest > 240


@pytest.mark.unit
def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        simulation.build_track(POLYLINE, STOPS, START, 1200, "unknown", random.Random(1))
    with pytest.raises(ValueError):
        simulation.build_track(POLYLINE[:1], STOPS, START, 1200, "on_time", random.Random(1))


@pytest.mark.unit
def test_pick_scenario_respects_mix():
    rng = random.Random(1)
    picks = {simulation.pick_scenario(rng, {"late": 1.0}) for _ in range(20)}
    assert picks == {"late"}
