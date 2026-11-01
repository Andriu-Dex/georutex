"""Pure domain metrics engine for GeoRutex (Phase 5).

Calculates MT-01 through MT-08 (Transport Metrics) and MCS-01 through MCS-04
(Software Quality Metrics) strictly according to canonical formulas in
docs/requirements.md Section 8 and Section 7.

Zero Odoo ORM, network, or database dependencies are permitted in this module.
"""

import math
from typing import Any, Dict, List, Optional


def _format_metric_result(
    metric_id: str,
    name: str,
    formula: str,
    unit: str,
    value: Optional[float],
    numerator: Optional[float],
    denominator: Optional[float],
    sample_size: int,
    source_type: str,
    period: str,
    rule_version: str,
    interpretation: str,
    is_na: bool = False,
    na_reason: Optional[str] = None,
    secondary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build canonical common contract dictionary for any KPI."""
    if is_na or value is None:
        display_val = "N/A"
        is_na = True
    elif unit == "%":
        display_val = f"{value:.2f} %"
    elif unit in ("min", "m", "km", "ms"):
        display_val = f"{value:.2f} {unit}"
    elif unit in ("qty", "inc/10"):
        display_val = f"{value:.2f}"
    else:
        display_val = f"{value}"

    return {
        "id": metric_id,
        "name": name,
        "formula": formula,
        "unit": unit,
        "value": None if is_na else round(value, 4),
        "display_value": display_val,
        "numerator": numerator,
        "denominator": denominator,
        "sample_size": sample_size,
        "source_type": source_type,
        "period": period,
        "rule_version": rule_version,
        "interpretation": interpretation,
        "is_na": is_na,
        "na_reason": na_reason,
        "secondary": secondary or {},
    }


# ==============================================================================
# MT-01: Porcentaje de Cumplimiento de Rutas
# ==============================================================================

def calculate_mt01_route_compliance(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-01 gross and adjusted route compliance.

    :param trips_eval: List of trip evaluation summaries.
    :return: Common contract KPI dictionary with gross and adjusted values.
    """
    # Exclude draft, scheduled, cancelled, or insufficient data
    evaluable = [
        t for t in trips_eval
        if t.get("integrity_status") in ("completed", "incomplete")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-01",
            name="Porcentaje de Cumplimiento de Rutas",
            formula=(
                "100 * viajes_con_ruta_conforme / viajes_ejecutados_evaluables"
            ),
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes ejecutados evaluables en el período.",
            is_na=True,
            na_reason="Denominador nulo: sin viajes ejecutados evaluables.",
        )

    num_gross = sum(1 for t in evaluable if t.get("is_compliant_gross"))
    num_adj = sum(1 for t in evaluable if t.get("is_compliant_adjusted"))

    pct_gross = (num_gross / denom) * 100.0
    pct_adj = (num_adj / denom) * 100.0

    interp = (
        f"Cumplimiento bruto: {pct_gross:.1f}% ({num_gross}/{denom} viajes). "
        f"Ajustado: {pct_adj:.1f}% ({num_adj}/{denom} viajes)."
    )

    return _format_metric_result(
        metric_id="MT-01",
        name="Porcentaje de Cumplimiento de Rutas",
        formula=(
            "100 * viajes_con_ruta_conforme / viajes_ejecutados_evaluables"
        ),
        unit="%",
        value=pct_gross,
        numerator=num_gross,
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "adjusted_value": round(pct_adj, 2),
            "adjusted_display": f"{pct_adj:.2f} %",
            "adjusted_numerator": num_adj,
            "non_compliant_count": denom - num_gross,
            "justified_count": num_adj - num_gross,
        },
    )


# ==============================================================================
# MT-02: Porcentaje de Puntualidad
# ==============================================================================

def calculate_mt02_punctuality(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-02 trip punctuality (punctual departure AND arrival).

    :param trips_eval: List of trip evaluation records.
    :return: Common contract KPI dictionary.
    """
    # Verified actual start AND verified actual arrival
    evaluable = [
        t for t in trips_eval
        if t.get("actual_start_utc") and t.get("actual_end_utc")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-02",
            name="Porcentaje de Puntualidad de Viajes",
            formula=(
                "100 * viajes_salida_y_llegada_puntuales / "
                "viajes_inicio_fin_verificados"
            ),
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes con inicio y fin GPS verificados.",
            is_na=True,
            na_reason="Denominador nulo: sin viajes con inicio y fin GPS.",
        )

    num_punctual = 0
    start_punctual = 0
    arrival_punctual = 0

    for t in evaluable:
        s_ok = t.get("start_punctuality") in ("on_time", "early")
        a_ok = t.get("arrival_punctuality") in ("on_time", "early")
        if s_ok:
            start_punctual += 1
        if a_ok:
            arrival_punctual += 1
        if s_ok and a_ok:
            num_punctual += 1

    pct = (num_punctual / denom) * 100.0
    pct_start = (start_punctual / denom) * 100.0
    pct_arrival = (arrival_punctual / denom) * 100.0

    interp = (
        f"{num_punctual} de {denom} viajes fueron puntuales en salida y "
        f"llegada ({pct:.1f}%). Puntualidad salida: {pct_start:.1f}%, "
        f"llegada: {pct_arrival:.1f}%."
    )

    return _format_metric_result(
        metric_id="MT-02",
        name="Porcentaje de Puntualidad de Viajes",
        formula=(
            "100 * viajes_salida_y_llegada_puntuales / "
            "viajes_inicio_fin_verificados"
        ),
        unit="%",
        value=pct,
        numerator=num_punctual,
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "departure_punctuality_pct": round(pct_start, 2),
            "departure_punctual_count": start_punctual,
            "arrival_punctuality_pct": round(pct_arrival, 2),
            "arrival_punctual_count": arrival_punctual,
        },
    )


# ==============================================================================
# MT-03: Retraso Promedio de Llegada
# ==============================================================================

def calculate_mt03_average_delay(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-03 average arrival delay in minutes.

    Gross delay = max(0, actual_end - scheduled_end).
    Punctual/early trips contribute 0 to the gross average.
    """
    evaluable = [
        t for t in trips_eval
        if t.get("actual_end_utc")
        and t.get("scheduled_end_utc")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-03",
            name="Retraso Promedio de Llegada",
            formula="sum(max(0, actual_end - sched_end)) / (60 * n_viajes)",
            unit="min",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes con llegada verificable en el período.",
            is_na=True,
            na_reason="Denominador nulo: sin llegadas verificadas.",
        )

    delays_s = []
    strictly_late_delays_s = []

    for t in evaluable:
        d_s = max(0, int(t.get("arrival_delay_s", 0)))
        delays_s.append(d_s)
        if d_s > 0:
            strictly_late_delays_s.append(d_s)

    total_delay_min = sum(delays_s) / 60.0
    avg_delay_min = total_delay_min / denom

    cond_denom = len(strictly_late_delays_s)
    cond_avg_min = (
        (sum(strictly_late_delays_s) / 60.0) / cond_denom
        if cond_denom > 0
        else 0.0
    )

    interp = (
        f"Retraso medio general de {avg_delay_min:.2f} min sobre {denom} "
        f"viajes. {cond_denom} llegadas con demora (promedio condicionado: "
        f"{cond_avg_min:.2f} min)."
    )

    return _format_metric_result(
        metric_id="MT-03",
        name="Retraso Promedio de Llegada",
        formula="sum(max(0, actual_end - sched_end)) / (60 * n_viajes)",
        unit="min",
        value=avg_delay_min,
        numerator=round(total_delay_min, 2),
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "conditional_avg_delay_min": round(cond_avg_min, 2),
            "strictly_late_trip_count": cond_denom,
            "on_time_trip_count": denom - cond_denom,
        },
    )


# ==============================================================================
# MT-04: Porcentaje de Paradas Cumplidas
# ==============================================================================

def calculate_mt04_stops_completed(
    stops_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-04 intermediate checkpoint completion percentage.

    Origin and destination are start/end terminals, not intermediate stops.
    """
    # Exclude origin and destination; only evaluate checkpoints
    evaluable = [
        s for s in stops_eval
        if s.get("stop_type") in ("checkpoint", "regular")
        and s.get("required", True)
        and s.get("status") != "indeterminate"
    ]
    denom = len(evaluable)
    indet_count = sum(
        1 for s in stops_eval
        if s.get("stop_type") in ("checkpoint", "regular")
        and s.get("status") == "indeterminate"
    )

    if denom == 0:
        return _format_metric_result(
            metric_id="MT-04",
            name="Porcentaje de Paradas Intermedias Cumplidas",
            formula=(
                "100 * paradas_intermedias_visitadas / "
                "paradas_intermedias_programadas"
            ),
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin paradas intermedias evaluables en el período.",
            is_na=True,
            na_reason="Denominador nulo: sin paradas evaluables.",
            secondary={"indeterminate_count": indet_count},
        )

    visited_count = sum(
        1 for s in evaluable if s.get("status") in ("on_time", "late")
    )
    missed_count = sum(1 for s in evaluable if s.get("status") == "missed")
    pct = (visited_count / denom) * 100.0

    interp = (
        f"{visited_count} de {denom} paradas intermedias visitadas "
        f"({pct:.1f}%). {missed_count} omitidas, "
        f"{indet_count} indeterminadas por falta de señal."
    )

    return _format_metric_result(
        metric_id="MT-04",
        name="Porcentaje de Paradas Intermedias Cumplidas",
        formula=(
            "100 * paradas_intermedias_visitadas / "
            "paradas_intermedias_programadas"
        ),
        unit="%",
        value=pct,
        numerator=visited_count,
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "visited_count": visited_count,
            "missed_count": missed_count,
            "indeterminate_count": indet_count,
        },
    )


# ==============================================================================
# MT-05: Desviación Respecto a la Ruta Programada
# ==============================================================================

def calculate_mt05_route_deviation(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-05 average max polyline distance and deviation metrics."""
    evaluable = [
        t for t in trips_eval
        if t.get("integrity_status") in ("completed", "incomplete")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-05",
            name="Desviación Máxima Respecto a la Ruta",
            formula="sum(max_distancia_viaje) / n_viajes",
            unit="m",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes con datos de trazado evaluables.",
            is_na=True,
            na_reason="Denominador nulo: sin viajes con trazado evaluable.",
        )

    max_distances = [
        float(t.get("max_deviation_distance_m", 0.0)) for t in evaluable
    ]
    avg_max_m = sum(max_distances) / denom

    deviated_trips = sum(
        1 for t in evaluable if t.get("deviation_count", 0) > 0
    )
    pct_deviated = (deviated_trips / denom) * 100.0

    total_outside_s = sum(
        t.get("deviation_duration_s", 0) for t in evaluable
    )
    total_outside_min = total_outside_s / 60.0
    avg_outside_min = total_outside_min / denom

    interp = (
        f"Separación máxima promedio respecto al trazado: {avg_max_m:.1f} m. "
        f"{deviated_trips} de {denom} viajes ({pct_deviated:.1f}%) con "
        f"desvíos ({total_outside_min:.1f} min fuera)."
    )

    return _format_metric_result(
        metric_id="MT-05",
        name="Desviación Máxima Respecto a la Ruta",
        formula="sum(max_distancia_viaje) / n_viajes",
        unit="m",
        value=avg_max_m,
        numerator=round(sum(max_distances), 2),
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "deviated_trips_count": deviated_trips,
            "deviated_trips_pct": round(pct_deviated, 2),
            "total_outside_time_min": round(total_outside_min, 2),
            "avg_outside_time_min": round(avg_outside_min, 2),
        },
    )


# ==============================================================================
# MT-06: Diferencia entre Distancia Estimada y Recorrida
# ==============================================================================

def calculate_mt06_distance_difference(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-06 weighted aggregated distance difference and MAE.

    Only evaluates trips with positive planned distance and verified start/end.
    """
    evaluable = [
        t for t in trips_eval
        if t.get("scheduled_distance_m", 0.0) > 0
        and t.get("actual_distance_m", 0.0) > 0
        and t.get("actual_start_utc")
        and t.get("actual_end_utc")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-06",
            name="Diferencia de Distancia Estimada vs Recorrida",
            formula="100 * (sum(D_real) - sum(D_plan)) / sum(D_plan)",
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes con distancias válidas verificadas.",
            is_na=True,
            na_reason="Denominador nulo: sin distancias verificadas.",
        )

    sum_real_m = sum(t["actual_distance_m"] for t in evaluable)
    sum_plan_m = sum(t["scheduled_distance_m"] for t in evaluable)

    diff_m = sum_real_m - sum_plan_m
    diff_km = diff_m / 1000.0
    diff_pct = (diff_m / sum_plan_m) * 100.0 if sum_plan_m > 0 else 0.0

    # Mean Absolute Error in km
    abs_errors_km = [
        abs(t["actual_distance_m"] - t["scheduled_distance_m"]) / 1000.0
        for t in evaluable
    ]
    mae_km = sum(abs_errors_km) / denom

    interp = (
        f"Diferencia: {diff_pct:+.2f}% ({diff_km:+.2f} km sobre "
        f"{sum_plan_m / 1000.0:.2f} km plan en {denom} viajes). "
        f"MAE: {mae_km:.2f} km."
    )

    return _format_metric_result(
        metric_id="MT-06",
        name="Diferencia de Distancia Estimada vs Recorrida",
        formula="100 * (sum(D_real) - sum(D_plan)) / sum(D_plan)",
        unit="%",
        value=diff_pct,
        numerator=round(diff_km, 3),
        denominator=round(sum_plan_m / 1000.0, 3),
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "diff_km": round(diff_km, 3),
            "mae_km": round(mae_km, 3),
            "sum_real_km": round(sum_real_m / 1000.0, 3),
            "sum_plan_km": round(sum_plan_m / 1000.0, 3),
        },
    )


# ==============================================================================
# MT-07: Tiempo Promedio de Recorrido
# ==============================================================================

def calculate_mt07_trip_duration(
    trips_eval: List[Dict[str, Any]],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-07 average trip duration in minutes using actual times."""
    evaluable = [
        t for t in trips_eval
        if t.get("actual_start_utc")
        and t.get("actual_end_utc")
        and t.get("scheduled_start_utc")
        and t.get("scheduled_end_utc")
        and t.get("state") not in ("draft", "scheduled", "cancelled")
    ]
    denom = len(evaluable)
    if denom == 0:
        return _format_metric_result(
            metric_id="MT-07",
            name="Tiempo Promedio de Recorrido",
            formula="sum(actual_end - actual_start) / (60 * n_viajes)",
            unit="min",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin viajes con inicio y fin verificados.",
            is_na=True,
            na_reason="Denominador nulo: sin tiempos de viaje verificados.",
        )

    actual_durations_min = [
        (t["actual_end_utc"] - t["actual_start_utc"]).total_seconds() / 60.0
        for t in evaluable
    ]
    planned_durations_min = [
        (t["scheduled_end_utc"] - t["scheduled_start_utc"]).total_seconds()
        / 60.0
        for t in evaluable
    ]

    avg_actual_min = sum(actual_durations_min) / denom
    avg_planned_min = sum(planned_durations_min) / denom
    diff_avg_min = avg_actual_min - avg_planned_min

    interp = (
        f"Duración real de {avg_actual_min:.1f} min en {denom} viajes "
        f"(programada: {avg_planned_min:.1f} min; dif: {diff_avg_min:+.1f} "
        f"min)."
    )

    return _format_metric_result(
        metric_id="MT-07",
        name="Tiempo Promedio de Recorrido",
        formula="sum(actual_end - actual_start) / (60 * n_viajes)",
        unit="min",
        value=avg_actual_min,
        numerator=round(sum(actual_durations_min), 2),
        denominator=denom,
        sample_size=denom,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "planned_avg_duration_min": round(avg_planned_min, 2),
            "duration_difference_min": round(diff_avg_min, 2),
        },
    )


# ==============================================================================
# MT-08: Número y Frecuencia de Incidencias
# ==============================================================================

def calculate_mt08_incidents(
    incidents: List[Dict[str, Any]],
    executed_trip_count: int,
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MT-08 incident count and frequency per 10 executed trips."""
    total_incidents = len(incidents)

    if executed_trip_count <= 0:
        freq_per_10 = None
        is_na = True
        na_reason = "Sin recorridos ejecutados para calcular frecuencia."
        interp = (
            f"{total_incidents} incidencias registradas. Frecuencia no "
            f"calculable por ausencia de recorridos ejecutados."
        )
    else:
        freq_per_10 = (total_incidents * 10.0) / executed_trip_count
        is_na = False
        na_reason = None
        interp = (
            f"{total_incidents} incidencias ({freq_per_10:.2f} por cada 10 "
            f"recorridos sobre {executed_trip_count} viajes ejecutados)."
        )

    by_type: Dict[str, int] = {}
    by_origin: Dict[str, int] = {"automatic": 0, "manual": 0}
    by_state: Dict[str, int] = {}

    for inc in incidents:
        t = inc.get("incident_type", "other")
        by_type[t] = by_type.get(t, 0) + 1

        orig = inc.get("source", "automatic")
        by_origin[orig] = by_origin.get(orig, 0) + 1

        st = inc.get("state", "draft")
        by_state[st] = by_state.get(st, 0) + 1

    return _format_metric_result(
        metric_id="MT-08",
        name="Número y Frecuencia de Incidencias",
        formula="10 * total_incidencias / viajes_ejecutados",
        unit="inc/10",
        value=freq_per_10,
        numerator=total_incidents,
        denominator=executed_trip_count,
        sample_size=executed_trip_count,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        is_na=is_na,
        na_reason=na_reason,
        secondary={
            "total_incident_count": total_incidents,
            "breakdown_by_type": by_type,
            "breakdown_by_origin": by_origin,
            "breakdown_by_state": by_state,
        },
    )


# ==============================================================================
# MCS-01: Integridad y Validez de Registros GPS
# ==============================================================================

def calculate_mcs01_gps_integrity(
    total_received: int,
    accepted: int,
    rejected_reasons: Dict[str, int],
    source_type: str = "combined",
    period: str = "Todo el período",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MCS-01 GPS telemetry integrity percentage."""
    if total_received <= 0:
        return _format_metric_result(
            metric_id="MCS-01",
            name="Integridad de Registros GPS",
            formula="100 * posiciones_aceptadas / posiciones_recibidas",
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin registros GPS sometidos a validación.",
            is_na=True,
            na_reason="Denominador nulo: sin posiciones recibidas.",
            secondary={"rejected_reasons": rejected_reasons},
        )

    pct = (accepted / total_received) * 100.0
    rejected = total_received - accepted
    interp = (
        f"Integridad del {pct:.2f}% ({accepted} de {total_received} "
        f"posiciones aceptadas). {rejected} rechazadas."
    )

    return _format_metric_result(
        metric_id="MCS-01",
        name="Integridad de Registros GPS",
        formula="100 * posiciones_aceptadas / posiciones_recibidas",
        unit="%",
        value=pct,
        numerator=accepted,
        denominator=total_received,
        sample_size=total_received,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "accepted_count": accepted,
            "rejected_count": rejected,
            "rejected_reasons": rejected_reasons,
        },
    )


# ==============================================================================
# MCS-02: Exactitud de Sincronización Traccar -> Odoo
# ==============================================================================

def calculate_mcs02_sync_accuracy(
    expected_count: int,
    matched_count: int,
    discrepancy_details: Optional[Dict[str, int]] = None,
    source_type: str = "combined",
    period: str = "Muestra independiente",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MCS-02 synchronization accuracy against independent query."""
    if expected_count <= 0:
        return _format_metric_result(
            metric_id="MCS-02",
            name="Exactitud de Sincronización Traccar → Odoo",
            formula="100 * posiciones_emparejadas / posiciones_esperadas",
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin muestra independiente disponible para cotejo.",
            is_na=True,
            na_reason="Muestra independiente vacía o no ejecutada.",
        )

    pct = (matched_count / expected_count) * 100.0
    missing = expected_count - matched_count
    interp = (
        f"Exactitud de sincronización del {pct:.2f}% ({matched_count} de "
        f"{expected_count} posiciones verificadas idénticas)."
    )

    return _format_metric_result(
        metric_id="MCS-02",
        name="Exactitud de Sincronización Traccar → Odoo",
        formula="100 * posiciones_emparejadas / posiciones_esperadas",
        unit="%",
        value=pct,
        numerator=matched_count,
        denominator=expected_count,
        sample_size=expected_count,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "matched_count": matched_count,
            "missing_count": missing,
            "discrepancies": discrepancy_details or {},
        },
    )


# ==============================================================================
# MCS-03: Tiempo de Respuesta del Sistema
# ==============================================================================

def calculate_mcs03_response_time(
    latencies_ms: List[float],
    is_cold: bool = False,
    source_type: str = "medicion_real",
    period: str = "Sesión de prueba",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MCS-03 latency in ms (mean, p50, and p95 if n >= 30)."""
    n = len(latencies_ms)
    mode_str = "en frío" if is_cold else "en caliente"

    if n == 0:
        return _format_metric_result(
            metric_id="MCS-03",
            name=f"Tiempo de Respuesta ({mode_str})",
            formula="mean(latencias_ms); p95(latencias_ms) si n >= 30",
            unit="ms",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation=f"Sin mediciones de latencia {mode_str}.",
            is_na=True,
            na_reason="Sin muestras de latencia registradas.",
        )

    sorted_lat = sorted(latencies_ms)
    avg_ms = sum(sorted_lat) / n
    min_ms = sorted_lat[0]
    max_ms = sorted_lat[-1]

    mid = n // 2
    p50_ms = (
        sorted_lat[mid]
        if n % 2 != 0
        else (sorted_lat[mid - 1] + sorted_lat[mid]) / 2.0
    )

    if n >= 30:
        p95_idx = int(math.ceil(0.95 * n)) - 1
        p95_idx = max(0, min(p95_idx, n - 1))
        p95_ms = sorted_lat[p95_idx]
        p95_display = f"{p95_ms:.2f} ms"
    else:
        p95_ms = None
        p95_display = f"N/A (muestra insuficiente n={n} < 30)"

    interp = (
        f"Latencia {mode_str}: promedio {avg_ms:.1f} ms, mediana "
        f"{p50_ms:.1f} ms, p95: {p95_display} sobre {n} repeticiones "
        f"(mín {min_ms:.1f} ms, máx {max_ms:.1f} ms)."
    )

    return _format_metric_result(
        metric_id="MCS-03",
        name=f"Tiempo de Respuesta ({mode_str})",
        formula="mean(latencias_ms); p95 = ceil(0.95*n) si n >= 30",
        unit="ms",
        value=avg_ms,
        numerator=round(sum(sorted_lat), 2),
        denominator=n,
        sample_size=n,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "mode": mode_str,
            "min_ms": round(min_ms, 2),
            "max_ms": round(max_ms, 2),
            "p50_ms": round(p50_ms, 2),
            "p95_ms": None if p95_ms is None else round(p95_ms, 2),
            "p95_display": p95_display,
        },
    )


# ==============================================================================
# MCS-04: Detección Correcta de Incidencias (Dataset Etiquetado)
# ==============================================================================

def calculate_mcs04_incident_detection(
    ground_truth_cases: List[Dict[str, Any]],
    source_type: str = "dataset_independiente",
    period: str = "Prueba de regresión",
    rule_version: str = "v1.0",
) -> Dict[str, Any]:
    """Calculate MCS-04 accuracy, precision, and sensitivity.

    Each case in ground_truth_cases must provide:
    - case_id: str
    - incident_type: str
    - expected_has_incident: bool
    - detected_has_incident: bool
    """
    total = len(ground_truth_cases)
    if total == 0:
        return _format_metric_result(
            metric_id="MCS-04",
            name="Porcentaje de Detección Correcta de Incidencias",
            formula="100 * (VP + VN) / (VP + VN + FP + FN)",
            unit="%",
            value=None,
            numerator=0,
            denominator=0,
            sample_size=0,
            source_type=source_type,
            period=period,
            rule_version=rule_version,
            interpretation="Sin casos de validación etiquetados disponibles.",
            is_na=True,
            na_reason="Dataset de validación vacío.",
        )

    vp = 0
    vn = 0
    fp = 0
    fn = 0
    by_type: Dict[str, Dict[str, int]] = {}

    for c in ground_truth_cases:
        t = c.get("incident_type", "general")
        if t not in by_type:
            by_type[t] = {"vp": 0, "vn": 0, "fp": 0, "fn": 0}

        exp = bool(c.get("expected_has_incident"))
        det = bool(c.get("detected_has_incident"))

        if exp and det:
            vp += 1
            by_type[t]["vp"] += 1
        elif not exp and not det:
            vn += 1
            by_type[t]["vn"] += 1
        elif not exp and det:
            fp += 1
            by_type[t]["fp"] += 1
        elif exp and not det:
            fn += 1
            by_type[t]["fn"] += 1

    accuracy = ((vp + vn) / total) * 100.0 if total > 0 else 0.0
    precision = (vp / (vp + fp)) * 100.0 if (vp + fp) > 0 else 0.0
    recall = (vp / (vp + fn)) * 100.0 if (vp + fn) > 0 else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    # Detailed metrics per incident type
    type_metrics: Dict[str, Any] = {}
    for t_name, counts in by_type.items():
        t_tot = sum(counts.values())
        t_acc = (
            ((counts["vp"] + counts["vn"]) / t_tot) * 100.0
            if t_tot > 0
            else 0.0
        )
        t_prec = (
            (counts["vp"] / (counts["vp"] + counts["fp"])) * 100.0
            if (counts["vp"] + counts["fp"]) > 0
            else 0.0
        )
        t_rec = (
            (counts["vp"] / (counts["vp"] + counts["fn"])) * 100.0
            if (counts["vp"] + counts["fn"]) > 0
            else 0.0
        )
        type_metrics[t_name] = {
            "counts": counts,
            "accuracy_pct": round(t_acc, 2),
            "precision_pct": round(t_prec, 2),
            "recall_pct": round(t_rec, 2),
        }

    interp = (
        f"Exactitud del {accuracy:.1f}% sobre {total} casos etiquetados "
        f"(VP={vp}, VN={vn}, FP={fp}, FN={fn}). Precisión: {precision:.1f}%, "
        f"Sensibilidad: {recall:.1f}%."
    )

    return _format_metric_result(
        metric_id="MCS-04",
        name="Porcentaje de Detección Correcta de Incidencias",
        formula="100 * (VP + VN) / (VP + VN + FP + FN)",
        unit="%",
        value=accuracy,
        numerator=(vp + vn),
        denominator=total,
        sample_size=total,
        source_type=source_type,
        period=period,
        rule_version=rule_version,
        interpretation=interp,
        secondary={
            "precision_pct": round(precision, 2),
            "recall_pct": round(recall, 2),
            "f1_score_pct": round(f1, 2),
            "confusion_matrix": {"vp": vp, "vn": vn, "fp": fp, "fn": fn},
            "by_incident_type": type_metrics,
        },
    )
