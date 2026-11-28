"""Deterministic GPS track synthesis for labelled simulated trips.

Pure functions (no Odoo, no I/O). Tracks follow the route's reference polyline
and the planned stop offsets, then apply one operational scenario so the real
evaluation engine can detect it. The caller is responsible for labelling the
output as simulated.
"""

from datetime import timedelta
import math

from .geo import haversine_distance

SCENARIO_ON_TIME = "on_time"
SCENARIO_LATE = "late"
SCENARIO_MISSED_STOP = "missed_stop"
SCENARIO_DEVIATION = "deviation"
SCENARIO_INCOMPLETE = "incomplete"
SCENARIO_GPS_LOSS = "gps_loss"

SCENARIOS = (
    SCENARIO_ON_TIME,
    SCENARIO_LATE,
    SCENARIO_MISSED_STOP,
    SCENARIO_DEVIATION,
    SCENARIO_INCOMPLETE,
    SCENARIO_GPS_LOSS,
)

DEFAULT_MIX = {
    SCENARIO_ON_TIME: 0.55,
    SCENARIO_LATE: 0.17,
    SCENARIO_MISSED_STOP: 0.08,
    SCENARIO_DEVIATION: 0.08,
    SCENARIO_INCOMPLETE: 0.05,
    SCENARIO_GPS_LOSS: 0.07,
}

METERS_PER_DEGREE_LAT = 111320.0


def pick_scenario(rng, mix=None):
    """Choose a scenario according to the weighted mix."""
    mix = mix or DEFAULT_MIX
    names = [name for name in SCENARIOS if mix.get(name, 0) > 0]
    weights = [mix[name] for name in names]
    return rng.choices(names, weights=weights, k=1)[0]


def _cumulative_distances(points):
    """Return cumulative meters along ``points`` given as (lat, lon)."""
    cumulative = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine_distance(lat1, lon1, lat2, lon2))
    return cumulative


def _point_at(points, cumulative, distance):
    """Interpolate (lat, lon, segment_index) at ``distance`` meters along the line."""
    if distance <= 0:
        return points[0][0], points[0][1], 0
    for index in range(1, len(cumulative)):
        if cumulative[index] >= distance:
            span = cumulative[index] - cumulative[index - 1] or 1.0
            ratio = (distance - cumulative[index - 1]) / span
            lat1, lon1 = points[index - 1]
            lat2, lon2 = points[index]
            return lat1 + (lat2 - lat1) * ratio, lon1 + (lon2 - lon1) * ratio, index - 1
    return points[-1][0], points[-1][1], len(points) - 2


def _offset(lat, lon, segment, points, meters):
    """Shift a point ``meters`` perpendicular (left) to the local segment."""
    lat1, lon1 = points[segment]
    lat2, lon2 = points[min(segment + 1, len(points) - 1)]
    cos_lat = math.cos(math.radians(lat)) or 1e-9
    east = (lon2 - lon1) * cos_lat
    north = lat2 - lat1
    norm = math.hypot(east, north) or 1.0
    perp_east, perp_north = -north / norm, east / norm
    return (
        lat + perp_north * meters / METERS_PER_DEGREE_LAT,
        lon + perp_east * meters / (METERS_PER_DEGREE_LAT * cos_lat),
    )


def _along_distance(points, cumulative, lat, lon, minimum=0.0):
    """Meters along the line of the projection of (lat, lon), at or after ``minimum``.

    Projecting onto segments (not vertices) matters on simplified polylines,
    where vertices on long straight roads can be hundreds of meters apart.
    """
    cos_lat = math.cos(math.radians(lat)) or 1e-9
    best = None
    for index in range(len(points) - 1):
        (lat1, lon1), (lat2, lon2) = points[index], points[index + 1]
        dx, dy = (lon2 - lon1) * cos_lat, lat2 - lat1
        px, py = (lon - lon1) * cos_lat, lat - lat1
        length_sq = dx * dx + dy * dy
        ratio = 0.0 if not length_sq else max(0.0, min(1.0, (px * dx + py * dy) / length_sq))
        along = cumulative[index] + (cumulative[index + 1] - cumulative[index]) * ratio
        if along < minimum:
            continue
        gap = math.hypot(px - ratio * dx, py - ratio * dy)
        if best is None or gap < best[0]:
            best = (gap, along)
    return best[1] if best else minimum


def _stop_anchors(points, cumulative, stops, total_duration_s):
    """Map planned stop offsets to distances so timing follows the schedule."""
    anchors = [(0.0, 0.0)]
    for stop in sorted(stops, key=lambda item: item["offset_s"]):
        distance = _along_distance(points, cumulative, stop["lat"], stop["lon"], anchors[-1][0])
        offset_s = float(stop["offset_s"])
        if distance > anchors[-1][0] and offset_s > anchors[-1][1]:
            anchors.append((distance, offset_s))
    if cumulative[-1] > anchors[-1][0]:
        anchors.append((cumulative[-1], max(float(total_duration_s), anchors[-1][1] + 1)))
    return anchors


def _planned_seconds_at(anchors, distance):
    """Piecewise-linear planned elapsed time at ``distance`` meters."""
    for (d1, t1), (d2, t2) in zip(anchors, anchors[1:]):
        if distance <= d2:
            ratio = (distance - d1) / ((d2 - d1) or 1.0)
            return t1 + (t2 - t1) * ratio
    return anchors[-1][1]


def build_track(
    polyline_lonlat,
    stops,
    start_utc,
    scheduled_duration_s,
    scenario,
    rng,
    interval_s=15,
):
    """Synthesize a GPS track for one trip.

    :param polyline_lonlat: reference polyline as [[lon, lat], ...] (GeoJSON order).
    :param stops: list of dicts with ``lat``, ``lon``, ``offset_s`` and ``stop_type``.
    :param start_utc: naive UTC datetime of the scheduled departure.
    :param scheduled_duration_s: planned trip duration in seconds.
    :param scenario: one of ``SCENARIOS``.
    :param rng: ``random.Random`` instance (seeded by the caller for reproducibility).
    :return: list of dicts with ``latitude``, ``longitude``, ``fix_time``,
        ``speed_kmh`` and ``accuracy``.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    points = [(float(lat), float(lon)) for lon, lat in polyline_lonlat]
    if len(points) < 2:
        raise ValueError("Polyline needs at least two points.")
    cumulative = _cumulative_distances(points)
    total_m = cumulative[-1]
    anchors = _stop_anchors(points, cumulative, stops, scheduled_duration_s)

    start_delay_s = rng.uniform(-45, 90)
    pace = rng.uniform(0.97, 1.03)
    if scenario == SCENARIO_LATE:
        if rng.random() < 0.5:
            start_delay_s = rng.uniform(420, 900)
        else:
            pace = rng.uniform(1.25, 1.5)

    end_m = total_m
    if scenario == SCENARIO_INCOMPLETE:
        end_m = total_m * rng.uniform(0.4, 0.75)

    detour = None
    if scenario == SCENARIO_DEVIATION:
        center = total_m * rng.uniform(0.3, 0.7)
        half = max(total_m * rng.uniform(0.06, 0.1), 250.0)
        detour = (center - half, center + half, rng.uniform(150, 300))
    elif scenario == SCENARIO_MISSED_STOP:
        checkpoints = [s for s in stops if s.get("stop_type") == "checkpoint"] or stops[1:-1]
        if checkpoints:
            target = rng.choice(checkpoints)
            center = _along_distance(points, cumulative, target["lat"], target["lon"])
            detour = (center - 300.0, center + 300.0, rng.uniform(180, 260))

    gap = None
    if scenario == SCENARIO_GPS_LOSS:
        gap_start = scheduled_duration_s * rng.uniform(0.25, 0.65)
        gap = (gap_start, gap_start + rng.uniform(300, 540))

    track = []
    distance = 0.0
    previous = None
    while distance <= end_m:
        planned = _planned_seconds_at(anchors, distance) * pace
        lat, lon, segment = _point_at(points, cumulative, distance)
        if detour and detour[0] <= distance <= detour[1]:
            ramp = math.sin(math.pi * (distance - detour[0]) / (detour[1] - detour[0]))
            lat, lon = _offset(lat, lon, segment, points, detour[2] * min(1.0, ramp * 1.6))
        lat += rng.gauss(0, 4.0) / METERS_PER_DEGREE_LAT
        lon += rng.gauss(0, 4.0) / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat)))
        fix_time = start_utc + timedelta(seconds=start_delay_s + planned)
        in_gap = gap and gap[0] <= planned <= gap[1]
        if not in_gap:
            speed = 0.0
            if previous:
                seconds = (fix_time - previous["fix_time"]).total_seconds()
                if seconds > 0:
                    meters = haversine_distance(previous["latitude"], previous["longitude"], lat, lon)
                    speed = round(meters / seconds * 3.6, 1)
            point = {
                "latitude": round(lat, 7),
                "longitude": round(lon, 7),
                "fix_time": fix_time.replace(microsecond=0),
                "speed_kmh": speed,
                "accuracy": round(abs(rng.gauss(6, 2)) + 2, 1),
            }
            if not previous or point["fix_time"] > previous["fix_time"]:
                track.append(point)
                previous = point
        if distance >= end_m:
            break
        step_m = max(total_m / max(scheduled_duration_s * pace, 1) * interval_s, 1.0)
        next_distance = min(distance + step_m * rng.uniform(0.6, 1.4), end_m)
        # Emit a fix at each stop: at road speed one sampling step can exceed the
        # stop radius and would turn a compliant run into a missed stop.
        crossed = [d for d, _ in anchors if distance < d < next_distance]
        distance = crossed[0] if crossed else next_distance
    return track
