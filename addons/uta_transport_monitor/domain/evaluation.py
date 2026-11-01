"""Deterministic evaluation engine domain functions for GeoRutex (Phase 4).

Pure Python implementation using standard libraries.
Zero Odoo ORM, network, or database dependencies are permitted in this module.
Complies with RF-20 through RF-26, canonical parameter definitions
(Section 7.1), and academic rubric evaluation criteria.
"""

from datetime import timedelta
from typing import Any, Dict, List, Optional
from .geo import (
    distance_to_polyline,
    haversine_distance,
    is_valid_coordinate,
)


def evaluate_trip_actual_times(
    positions: List[Dict[str, Any]],
    origin_stop: Optional[Dict[str, Any]],
    destination_stop: Optional[Dict[str, Any]],
    default_radius_m: float = 30.0,
    accuracy_max_m: float = 100.0,
) -> Dict[str, Any]:
    """Infer actual departure and arrival times from verified GPS telemetry.

    Complies with RF-20:
    - actual_start_utc: First verified departure from origin stop radius.
    - actual_end_utc: First verified arrival at destination stop radius.

    :param positions: Chronologically sorted list of position dictionaries.
    :param origin_stop: Dict with latitude, longitude, and optional radius_m.
    :param destination_stop: Dict with destination lat, lon, and radius.
    :param default_radius_m: Fallback radius in meters.
    :param accuracy_max_m: Maximum acceptable horizontal GPS accuracy.
    :return: Dict with actual_start_utc, actual_end_utc, and audit details.
    """
    result: Dict[str, Any] = {
        "actual_start_utc": None,
        "actual_end_utc": None,
        "first_gps_fix_utc": None,
        "start_evidence": "no_data",
        "end_evidence": "no_data",
        "valid_position_count": 0,
    }

    if not positions:
        return result

    # Filter positions with acceptable accuracy
    valid_positions = [
        p
        for p in positions
        if p.get("is_valid", True)
        and (
            p.get("accuracy") is None
            or p.get("accuracy", 0.0) <= accuracy_max_m
        )
        and is_valid_coordinate(
            p.get("latitude", 0.0), p.get("longitude", 0.0)
        )
    ]

    result["valid_position_count"] = len(valid_positions)
    if not valid_positions:
        result["start_evidence"] = "insufficient_accuracy"
        return result

    result["first_gps_fix_utc"] = valid_positions[0]["fix_time"]

    # 1. Determine actual_start_utc (RF-20)
    if origin_stop and is_valid_coordinate(
        origin_stop.get("latitude", 0.0), origin_stop.get("longitude", 0.0)
    ):
        o_lat = origin_stop["latitude"]
        o_lon = origin_stop["longitude"]
        o_radius = origin_stop.get("radius_m") or default_radius_m

        was_inside_origin = False
        departure_time = None

        for pos in valid_positions:
            dist = haversine_distance(
                pos["latitude"], pos["longitude"], o_lat, o_lon
            )
            if dist <= o_radius:
                was_inside_origin = True
            elif was_inside_origin and dist > o_radius:
                departure_time = pos["fix_time"]
                result["start_evidence"] = "origin_geofence_departure"
                break

        if departure_time:
            result["actual_start_utc"] = departure_time
        elif was_inside_origin:
            # Bus stayed inside origin geofence through the recorded window
            result["start_evidence"] = "still_at_origin"
        else:
            # Did not start inside geofence: take first fix moving > 5 km/h
            moving = [
                p for p in valid_positions if p.get("speed", 0.0) >= 5.0
            ]
            if moving:
                result["actual_start_utc"] = moving[0]["fix_time"]
                result["start_evidence"] = "first_moving_fix_outside_origin"
            else:
                result["actual_start_utc"] = valid_positions[0]["fix_time"]
                result["start_evidence"] = "first_valid_fix_fallback"
    else:
        # No explicit origin stop defined: fallback to first valid fix
        result["actual_start_utc"] = valid_positions[0]["fix_time"]
        result["start_evidence"] = "first_valid_fix_no_origin"

    # 2. Determine actual_end_utc (RF-20)
    start_time = result["actual_start_utc"]
    if destination_stop and is_valid_coordinate(
        destination_stop.get("latitude", 0.0),
        destination_stop.get("longitude", 0.0),
    ):
        d_lat = destination_stop["latitude"]
        d_lon = destination_stop["longitude"]
        d_radius = destination_stop.get("radius_m") or default_radius_m

        for pos in valid_positions:
            # Arrival must occur at or after verified departure
            if start_time and pos["fix_time"] < start_time:
                continue
            dist = haversine_distance(
                pos["latitude"], pos["longitude"], d_lat, d_lon
            )
            if dist <= d_radius:
                result["actual_end_utc"] = pos["fix_time"]
                result["end_evidence"] = "destination_geofence_arrival"
                break

        if not result["actual_end_utc"]:
            result["end_evidence"] = "destination_not_reached"

    return result


def evaluate_stop_visits(
    stops: List[Dict[str, Any]],
    positions: List[Dict[str, Any]],
    default_stop_radius_m: float = 30.0,
    default_lateness_tolerance_s: int = 300,
    accuracy_max_m: float = 100.0,
    gap_threshold_s: int = 180,
) -> List[Dict[str, Any]]:
    """Evaluate checkpoint and stop visits against operational schedule.

    Complies with RF-22 and RF-23:
    - on_time: Arrival within stop radius and delay <= lateness_tolerance_s.
    - late: Arrival within stop radius but delay > lateness_tolerance_s.
    - missed: Bus continued on route without entering stop geofence.
    - indeterminate: Insufficient GPS telemetry or gap across the stop window.

    :param stops: List of stop checkpoint dictionaries.
    :param positions: Chronologically sorted list of GPS position dictionaries.
    :param default_stop_radius_m: Default stop geofence radius in meters.
    :param default_lateness_tolerance_s: Punctuality tolerance in seconds.
    :param accuracy_max_m: Maximum horizontal accuracy threshold.
    :param gap_threshold_s: Telemetry gap threshold in seconds.
    :return: List of evaluated stop visit dictionaries.
    """
    valid_positions = [
        p
        for p in positions
        if p.get("is_valid", True)
        and (
            p.get("accuracy") is None
            or p.get("accuracy", 0.0) <= accuracy_max_m
        )
        and is_valid_coordinate(
            p.get("latitude", 0.0), p.get("longitude", 0.0)
        )
    ]

    evaluated_stops: List[Dict[str, Any]] = []

    for stop in stops:
        s_id = stop.get("id")
        s_seq = stop.get("sequence", 0)
        s_name = stop.get("name", f"Parada {s_seq}")
        s_type = stop.get("stop_type", "checkpoint")
        s_required = stop.get("required", True)
        s_sched = stop.get("scheduled_at_utc")
        radius = stop.get("radius_m") or default_stop_radius_m
        lat = stop.get("latitude", 0.0)
        lon = stop.get("longitude", 0.0)

        item: Dict[str, Any] = {
            "stop_id": s_id,
            "sequence": s_seq,
            "stop_name": s_name,
            "stop_type": s_type,
            "required": s_required,
            "scheduled_at_utc": s_sched,
            "first_arrival_utc": None,
            "delay_s": 0,
            "status": "pending",
            "min_distance_m": None,
            "evidence_note": "",
        }

        if not is_valid_coordinate(lat, lon):
            item["status"] = "indeterminate"
            item["evidence_note"] = "Coordenadas de parada inválidas."
            evaluated_stops.append(item)
            continue

        if not valid_positions:
            item["status"] = "indeterminate"
            item["evidence_note"] = "Sin posiciones GPS válidas registradas."
            evaluated_stops.append(item)
            continue

        min_dist = float("inf")
        arrival_fix = None

        for pos in valid_positions:
            dist = haversine_distance(
                pos["latitude"], pos["longitude"], lat, lon
            )
            if dist < min_dist:
                min_dist = dist
            if dist <= radius and arrival_fix is None:
                arrival_fix = pos

        item["min_distance_m"] = round(min_dist, 2)

        if arrival_fix:
            arr_time = arrival_fix["fix_time"]
            item["first_arrival_utc"] = arr_time

            if s_sched:
                delay = int((arr_time - s_sched).total_seconds())
                item["delay_s"] = delay
                if delay <= default_lateness_tolerance_s:
                    item["status"] = "on_time"
                    item["evidence_note"] = (
                        f"Visita puntual dentro de tolerancia ({delay}s)."
                    )
                else:
                    item["status"] = "late"
                    item["evidence_note"] = (
                        f"Visita con retraso de {delay}s "
                        f"(tolerancia: {default_lateness_tolerance_s}s)."
                    )
            else:
                item["status"] = "on_time"
                item["evidence_note"] = (
                    "Visita confirmada sin hora programada."
                )
        else:
            # Geofence was not entered: determine if missed or indeterminate
            if s_sched:
                # Check for GPS coverage around scheduled window
                window_start = s_sched - timedelta(
                    seconds=default_lateness_tolerance_s
                )
                window_end = s_sched + timedelta(
                    seconds=default_lateness_tolerance_s * 2
                )

                fixes_in_window = [
                    p
                    for p in valid_positions
                    if window_start <= p["fix_time"] <= window_end
                ]

                # Check if there is an uninterrupted GPS gap across the window
                has_major_gap = False
                sorted_fixes = sorted(
                    valid_positions, key=lambda p: p["fix_time"]
                )
                for i in range(len(sorted_fixes) - 1):
                    f1 = sorted_fixes[i]["fix_time"]
                    f2 = sorted_fixes[i + 1]["fix_time"]
                    if (f2 - f1).total_seconds() > gap_threshold_s:
                        if f1 <= s_sched <= f2:
                            has_major_gap = True
                            break

                if has_major_gap or not fixes_in_window:
                    item["status"] = "indeterminate"
                    item["evidence_note"] = (
                        "Evidencia GPS insuficiente o gap durante la "
                        "ventana prevista de visita."
                    )
                else:
                    item["status"] = "missed"
                    item["evidence_note"] = (
                        f"Parada omitida. Distancia mínima alcanzada: "
                        f"{round(min_dist, 1)}m (radio: {radius}m)."
                    )
            else:
                item["status"] = "missed"
                item["evidence_note"] = (
                    f"No se registró paso por el radio de parada ({radius}m)."
                )

        evaluated_stops.append(item)

    return evaluated_stops


def detect_route_deviations(
    positions: List[Dict[str, Any]],
    polyline_coords: list,
    corridor_m: float = 40.0,
    min_consecutive_points: int = 2,
    min_duration_s: int = 10,
    accuracy_max_m: float = 100.0,
) -> List[Dict[str, Any]]:
    """Detect spatial corridor deviations along reference polyline (RF-24).

    Distinguishes real route deviations from isolated GPS noise/multipath.
    A deviation requires at least min_consecutive_points and min_duration_s
    outside corridor_m with horizontal accuracy <= accuracy_max_m.

    :param positions: Chronologically sorted list of GPS position dictionaries.
    :param polyline_coords: Reference polyline coordinates list.
    :param corridor_m: Half-width allowed corridor in meters (default 40m).
    :param min_consecutive_points: Consecutive samples threshold (default 2).
    :param min_duration_s: Minimum continuous duration threshold in seconds.
    :param accuracy_max_m: Maximum acceptable GPS accuracy (filters noise).
    :return: List of confirmed deviation event dictionaries.
    """
    if not polyline_coords or len(polyline_coords) < 2 or not positions:
        return []

    valid_positions = [
        p
        for p in positions
        if p.get("is_valid", True)
        and (
            p.get("accuracy") is None
            or p.get("accuracy", 0.0) <= accuracy_max_m
        )
        and is_valid_coordinate(
            p.get("latitude", 0.0), p.get("longitude", 0.0)
        )
    ]

    if len(valid_positions) < min_consecutive_points:
        return []

    # Tag each valid position with its distance to polyline
    tagged_positions = []
    for p in valid_positions:
        dist = distance_to_polyline(
            p["latitude"], p["longitude"], polyline_coords, is_geojson=True
        )
        accuracy = p.get("accuracy")
        # Section 7.5.2: d_i - a_i > route_corridor_m with accuracy
        if accuracy is not None and accuracy > 0:
            is_outside = (dist - accuracy) > corridor_m
        else:
            is_outside = dist > corridor_m

        tagged_positions.append({
            "pos": p,
            "distance_m": dist,
            "is_outside": is_outside,
        })

    # Cluster consecutive outside points
    confirmed_deviations: List[Dict[str, Any]] = []
    current_cluster: List[Dict[str, Any]] = []

    for item in tagged_positions:
        if item["is_outside"]:
            current_cluster.append(item)
        else:
            if len(current_cluster) >= min_consecutive_points:
                t_start = current_cluster[0]["pos"]["fix_time"]
                t_end = current_cluster[-1]["pos"]["fix_time"]
                duration = int((t_end - t_start).total_seconds())

                if duration >= min_duration_s:
                    max_d = max(x["distance_m"] for x in current_cluster)
                    p_first = current_cluster[0]["pos"]
                    confirmed_deviations.append({
                        "start_time": t_start,
                        "end_time": t_end,
                        "duration_s": duration,
                        "point_count": len(current_cluster),
                        "max_distance_m": round(max_d, 2),
                        "start_latitude": p_first["latitude"],
                        "start_longitude": p_first["longitude"],
                    })
            current_cluster = []

    # Check terminal cluster at the end of the trace
    if len(current_cluster) >= min_consecutive_points:
        t_start = current_cluster[0]["pos"]["fix_time"]
        t_end = current_cluster[-1]["pos"]["fix_time"]
        duration = int((t_end - t_start).total_seconds())
        if duration >= min_duration_s:
            max_d = max(x["distance_m"] for x in current_cluster)
            p_first = current_cluster[0]["pos"]
            confirmed_deviations.append({
                "start_time": t_start,
                "end_time": t_end,
                "duration_s": duration,
                "point_count": len(current_cluster),
                "max_distance_m": round(max_d, 2),
                "start_latitude": p_first["latitude"],
                "start_longitude": p_first["longitude"],
            })

    return confirmed_deviations


def detect_gps_gaps(
    positions: List[Dict[str, Any]],
    gap_threshold_s: int = 180,
) -> List[Dict[str, Any]]:
    """Detect telemetry loss gaps exceeding canonical threshold (RF-25).

    :param positions: Chronologically sorted list of GPS position dictionaries.
    :param gap_threshold_s: Telemetry loss threshold in seconds (default 180s).
    :return: List of detected GPS gap event dictionaries.
    """
    if len(positions) < 2:
        return []

    sorted_fixes = sorted(positions, key=lambda p: p["fix_time"])
    gaps: List[Dict[str, Any]] = []

    for idx in range(len(sorted_fixes) - 1):
        f1 = sorted_fixes[idx]
        f2 = sorted_fixes[idx + 1]
        delta_s = int((f2["fix_time"] - f1["fix_time"]).total_seconds())

        if delta_s > gap_threshold_s:
            gaps.append({
                "start_time": f1["fix_time"],
                "end_time": f2["fix_time"],
                "duration_s": delta_s,
                "gap_latitude": f1.get("latitude", 0.0),
                "gap_longitude": f1.get("longitude", 0.0),
            })

    return gaps


def evaluate_trip_compliance(
    trip_info: Dict[str, Any],
    stops_eval: List[Dict[str, Any]],
    deviations: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    parameter_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Aggregate overall trip compliance evaluation verdict (RF-26).

    :param trip_info: Trip operational metadata dictionary.
    :param stops_eval: List of stop evaluation results.
    :param deviations: List of confirmed route deviations.
    :param gaps: List of detected GPS telemetry gaps.
    :param parameter_snapshot: Frozen parameters dictionary.
    :return: Comprehensive evaluation result dictionary.
    """
    lateness_tol = parameter_snapshot.get("lateness_tolerance_s", 300)

    # 1. Punctuality analysis
    sched_start = trip_info.get("scheduled_start_utc")
    sched_end = trip_info.get("scheduled_end_utc")
    actual_start = trip_info.get("actual_start_utc")
    actual_end = trip_info.get("actual_end_utc")

    start_delay_s = 0
    start_punctuality = "indeterminate"
    if sched_start and actual_start:
        start_delay_s = int((actual_start - sched_start).total_seconds())
        if start_delay_s < -lateness_tol:
            start_punctuality = "early"
        elif start_delay_s <= lateness_tol:
            start_punctuality = "on_time"
        else:
            start_punctuality = "late"

    end_delay_s = 0
    arrival_punctuality = "indeterminate"
    if sched_end and actual_end:
        end_delay_s = int((actual_end - sched_end).total_seconds())
        if end_delay_s < -lateness_tol:
            arrival_punctuality = "early"
        elif end_delay_s <= lateness_tol:
            arrival_punctuality = "on_time"
        else:
            arrival_punctuality = "late"
    elif actual_start and not actual_end:
        arrival_punctuality = "incomplete"

    # 2. Checkpoints breakdown
    total_stops = len(stops_eval)
    on_time_stops = sum(1 for s in stops_eval if s["status"] == "on_time")
    late_stops = sum(1 for s in stops_eval if s["status"] == "late")
    missed_stops = sum(1 for s in stops_eval if s["status"] == "missed")
    indet_stops = sum(1 for s in stops_eval if s["status"] == "indeterminate")
    req_missed = sum(
        1 for s in stops_eval if s["status"] == "missed" and s["required"]
    )

    # 3. Deviations & gaps totals
    dev_count = len(deviations)
    dev_duration = sum(d["duration_s"] for d in deviations)
    max_dev_dist = max((d["max_distance_m"] for d in deviations), default=0.0)

    gap_count = len(gaps)
    gap_duration = sum(g["duration_s"] for g in gaps)

    # 4. Integrity classification (RF-26)
    trip_state = trip_info.get("state")
    pos_count = trip_info.get("position_count", 0)
    if trip_state == "cancelled":
        integrity_status = "cancelled"
    elif pos_count < 2 or indet_stops == total_stops:
        integrity_status = "insufficient_data"
    elif actual_end:
        integrity_status = "completed"
    elif actual_start:
        integrity_status = "incomplete"
    else:
        integrity_status = "insufficient_data"

    # 5. Gross compliance verdict (RF-31)
    # A trip is compliant gross if:
    # - Integrity is completed
    # - No required checkpoints were missed
    # - No unexcused route deviations
    # - Start and arrival were not severely late (> tolerance)
    is_compliant_gross = True
    non_compliance_reasons = []

    if integrity_status != "completed":
        is_compliant_gross = False
        non_compliance_reasons.append(
            f"Integridad no completada ({integrity_status})."
        )
    if req_missed > 0:
        is_compliant_gross = False
        non_compliance_reasons.append(
            f"{req_missed} paradas obligatorias omitidas."
        )
    if dev_count > 0:
        is_compliant_gross = False
        non_compliance_reasons.append(
            f"{dev_count} desvíos de ruta confirmados."
        )
    if start_punctuality == "late":
        is_compliant_gross = False
        non_compliance_reasons.append(
            f"Salida tardía con {start_delay_s}s de retraso."
        )
    if arrival_punctuality == "late":
        is_compliant_gross = False
        non_compliance_reasons.append(
            f"Llegada tardía con {end_delay_s}s de retraso."
        )

    summary = (
        "Recorrido Conforme"
        if is_compliant_gross
        else f"No Conforme: {'; '.join(non_compliance_reasons)}"
    )

    return {
        "integrity_status": integrity_status,
        "is_compliant_gross": is_compliant_gross,
        # is_compliant_adjusted will update with justifications
        "is_compliant_adjusted": is_compliant_gross,
        "start_punctuality": start_punctuality,
        "start_delay_s": start_delay_s,
        "arrival_punctuality": arrival_punctuality,
        "arrival_delay_s": end_delay_s,
        "stops_total": total_stops,
        "stops_on_time": on_time_stops,
        "stops_late": late_stops,
        "stops_missed": missed_stops,
        "stops_indeterminate": indet_stops,
        "deviation_count": dev_count,
        "deviation_duration_s": dev_duration,
        "max_deviation_distance_m": max_dev_dist,
        "gps_gap_count": gap_count,
        "gps_gap_duration_s": gap_duration,
        "evaluation_summary": summary,
    }
