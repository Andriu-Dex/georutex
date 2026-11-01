"""Trip evaluation orchestration service for GeoRutex (Phase 4).

Coordinates extraction of frozen parameters, GPS positions, checkpoints,
calls pure mathematical domain functions, and idempotently persists:
- Departure and arrival inference (RF-20).
- Stop visits punctuality and min distance (RF-22, RF-23).
- Corridor deviations (RF-24).
- Telemetry gaps (RF-25).
- Audit evaluation record (RF-26, RF-30).
- Non-duplicating automatic incident generation (RF-27, RF-28, RF-29).
"""

import json
import logging
from odoo import api, fields, models
from ..domain.evaluation import (
    detect_gps_gaps,
    detect_route_deviations,
    evaluate_stop_visits,
    evaluate_trip_actual_times,
    evaluate_trip_compliance,
)

_logger = logging.getLogger(__name__)


class TransportTripEvaluationService(models.AbstractModel):
    """Orchestration service for automated trip evaluation."""

    _name = "transport.trip.evaluation.service"
    _description = "Servicio de Evaluación de Recorridos"

    @api.model
    def evaluate_trip(self, trip):
        """Execute full evaluation on a trip record idempotently.

        :param trip: `transport.trip` record.
        :return: `transport.trip.evaluation` record.
        """
        trip.ensure_one()
        _logger.info(
            "Iniciando evaluación para recorrido %s (ID %s)",
            trip.name,
            trip.id,
        )

        # 1. Parse frozen parameters snapshot or fallback to route version
        params = self._get_evaluation_parameters(trip)

        # 2. Extract and format valid GPS positions
        positions_raw = trip.position_ids.sorted(
            key=lambda p: (p.fix_time, p.id)
        )
        positions = []
        for p in positions_raw:
            positions.append({
                "latitude": p.latitude,
                "longitude": p.longitude,
                "speed": p.speed or 0.0,
                "altitude": p.altitude or 0.0,
                "accuracy": p.accuracy,
                "fix_time": p.fix_time,
                "is_valid": p.is_valid,
            })

        # 3. Extract origin, destination, and checkpoints
        origin_stop = None
        destination_stop = None
        stops = []

        # Use stop visits attached to trip, sorted by sequence
        for sv in trip.stop_visit_ids.sorted("sequence"):
            route_stop_id = sv.route_stop_id.id if sv.route_stop_id else False
            s_dict = {
                "id": sv.id,
                "route_stop_id": route_stop_id,
                "sequence": sv.sequence,
                "name": sv.stop_name,
                "stop_type": sv.stop_type,
                "required": sv.required,
                "latitude": sv.latitude,
                "longitude": sv.longitude,
                "radius_m": sv.radius_m or params.get("stop_radius_m", 30.0),
                "scheduled_at_utc": sv.scheduled_at_utc,
            }
            stops.append(s_dict)
            if sv.stop_type == "origin" and not origin_stop:
                origin_stop = s_dict
            elif sv.stop_type == "destination":
                destination_stop = s_dict

        # 4. Extract reference polyline coordinates
        polyline_coords = self._get_polyline_coordinates(trip)

        # 5. Call pure domain functions
        # 5.1 Determine actual start and end times (RF-20)
        times_eval = evaluate_trip_actual_times(
            positions=positions,
            origin_stop=origin_stop,
            destination_stop=destination_stop,
            default_radius_m=params.get("stop_radius_m", 30.0),
            accuracy_max_m=params.get("geo_accuracy_max_m", 100.0),
        )

        trip_write_vals = {}
        if times_eval["actual_start_utc"]:
            trip_write_vals["actual_start_utc"] = times_eval[
                "actual_start_utc"
            ]
        if times_eval["actual_end_utc"]:
            trip_write_vals["actual_end_utc"] = times_eval["actual_end_utc"]
        if times_eval["first_gps_fix_utc"] and not trip.first_gps_fix_utc:
            trip_write_vals["first_gps_fix_utc"] = times_eval[
                "first_gps_fix_utc"
            ]
        trip_write_vals["actual_start_evidence"] = times_eval["start_evidence"]
        trip_write_vals["actual_end_evidence"] = times_eval["end_evidence"]
        trip.write(trip_write_vals)

        # 5.2 Evaluate stop visits (RF-22, RF-23)
        stops_eval = evaluate_stop_visits(
            stops=stops,
            positions=positions,
            default_stop_radius_m=params.get("stop_radius_m", 30.0),
            default_lateness_tolerance_s=params.get(
                "lateness_tolerance_s", 300
            ),
            accuracy_max_m=params.get("geo_accuracy_max_m", 100.0),
            gap_threshold_s=params.get("gps_gap_threshold_s", 180),
        )

        # Update transport.stop.visit records
        for s_res in stops_eval:
            sv_rec = trip.stop_visit_ids.browse(s_res["stop_id"])
            if sv_rec:
                sv_vals = {
                    "status": s_res["status"],
                    "delay_s": s_res["delay_s"],
                    "min_distance_m": s_res.get("min_distance_m") or 0.0,
                    "notes": s_res.get("evidence_note") or "",
                }
                if s_res.get("first_arrival_utc"):
                    sv_vals["first_arrival_utc"] = s_res["first_arrival_utc"]
                sv_rec.write(sv_vals)

        # 5.3 Detect route deviations (RF-24)
        deviations = detect_route_deviations(
            positions=positions,
            polyline_coords=polyline_coords,
            corridor_m=params.get("route_corridor_m", 40.0),
            min_consecutive_points=params.get(
                "minimum_consecutive_deviation_points", 2
            ),
            min_duration_s=params.get("minimum_deviation_duration_s", 10),
            accuracy_max_m=params.get("geo_accuracy_max_m", 100.0),
        )

        # 5.4 Detect GPS gaps (RF-25)
        gaps = detect_gps_gaps(
            positions=positions,
            gap_threshold_s=params.get("gps_gap_threshold_s", 180),
        )

        # 5.5 Aggregate compliance evaluation (RF-26)
        trip_info = {
            "scheduled_start_utc": trip.scheduled_start_utc,
            "scheduled_end_utc": trip.scheduled_end_utc,
            "actual_start_utc": trip.actual_start_utc,
            "actual_end_utc": trip.actual_end_utc,
            "position_count": len(positions),
            "state": trip.state,
        }
        compliance = evaluate_trip_compliance(
            trip_info=trip_info,
            stops_eval=stops_eval,
            deviations=deviations,
            gaps=gaps,
            parameter_snapshot=params,
        )

        # 6. Idempotently generate and link incidents (RF-27, RF-28, RF-30)
        self._sync_automatic_incidents(
            trip=trip,
            compliance=compliance,
            stops_eval=stops_eval,
            deviations=deviations,
            gaps=gaps,
        )

        # 7. Check if justified incidents cover non-compliance (RF-29)
        is_compliant_adjusted = compliance["is_compliant_gross"]
        if (
            not is_compliant_adjusted
            and compliance["integrity_status"] != "insufficient_data"
        ):
            # Check if all unexcused issues have approved justifications
            all_incidents = trip.incident_ids
            unjustified = all_incidents.filtered(
                lambda i: i.state not in ("justified",)
            )
            if not unjustified and all_incidents:
                is_compliant_adjusted = True

        # 8. Create or update evaluation audit record (RF-26, RF-30)
        evaluation = self._persist_evaluation_record(
            trip=trip,
            params=params,
            compliance=compliance,
            is_compliant_adjusted=is_compliant_adjusted,
            incidents=trip.incident_ids,
        )

        # 9. Update trip state and evaluation status
        trip_status_vals = {}
        if compliance["integrity_status"] == "insufficient_data":
            trip_status_vals["evaluation_status"] = "indeterminate"
            if trip.state in ("scheduled", "in_progress", "draft"):
                trip_status_vals["state"] = "insufficient_data"
        elif is_compliant_adjusted:
            trip_status_vals["evaluation_status"] = "compliant"
            if trip.state == "in_progress" and trip.actual_end_utc:
                trip_status_vals["state"] = "completed"
        else:
            trip_status_vals["evaluation_status"] = "non_compliant"
            if trip.state == "in_progress" and not trip.actual_end_utc:
                trip_status_vals["state"] = "incomplete"
            elif trip.state == "in_progress" and trip.actual_end_utc:
                trip_status_vals["state"] = "completed"

        trip.write(trip_status_vals)

        return evaluation

    @api.model
    def _get_evaluation_parameters(self, trip):
        """Extract evaluation snapshot or build from route version."""
        if trip.parameter_snapshot_json:
            try:
                return json.loads(trip.parameter_snapshot_json)
            except Exception as e:
                _logger.warning("Error parsing parameter_snapshot_json: %s", e)

        ver = trip.route_version_id
        return {
            "route_version_id": ver.id,
            "version_number": ver.version_number,
            "route_code": ver.route_id.code,
            "stop_radius_m": ver.stop_radius_m or 30.0,
            "route_corridor_m": ver.route_corridor_m or 40.0,
            "lateness_tolerance_s": ver.lateness_tolerance_s or 300,
            "gps_gap_threshold_s": ver.gps_gap_threshold_s or 180,
            "minimum_consecutive_deviation_points": (
                ver.minimum_consecutive_deviation_points or 2
            ),
            "minimum_deviation_duration_s": (
                ver.minimum_deviation_duration_s or 10
            ),
            "geo_accuracy_max_m": ver.geo_accuracy_max_m or 100.0,
        }

    @api.model
    def _get_polyline_coordinates(self, trip):
        """Extract polyline coordinate list [[lon, lat], ...] from version."""
        ref_polyline = []
        if trip.route_version_id and trip.route_version_id.reference_polyline:
            try:
                data = json.loads(trip.route_version_id.reference_polyline)
                raw_coords = (
                    data.get("coordinates")
                    if isinstance(data, dict)
                    and data.get("type") == "LineString"
                    else data
                )
                if isinstance(raw_coords, list):
                    for pt in raw_coords:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            # Preserve GeoJSON order [lon, lat]
                            ref_polyline.append([float(pt[0]), float(pt[1])])
            except Exception as e:
                _logger.warning("Error parsing reference_polyline: %s", e)
        return ref_polyline

    @api.model
    def _sync_automatic_incidents(
        self, trip, compliance, stops_eval, deviations, gaps
    ):
        """Idempotently create automatic incidents without duplicates."""
        incident_model = self.env["transport.incident"]
        existing_incidents = incident_model.search([
            ("trip_id", "=", trip.id),
            ("source", "=", "automatic"),
        ])

        # 1. Start Delay incident
        if compliance.get("start_punctuality") == "late":
            existing = existing_incidents.filtered(
                lambda i: i.incident_type == "delay_start"
            )
            if not existing:
                incident_model.create({
                    "trip_id": trip.id,
                    "incident_type": "delay_start",
                    "source": "automatic",
                    "severity": "medium",
                    "timestamp_utc": (
                        trip.actual_start_utc or trip.scheduled_start_utc
                    ),
                    "rule_applied": "RF-20 / RF-21: Retraso en salida",
                    "description": (
                        f"Salida tardía de origen con retraso de "
                        f"{compliance.get('start_delay_s')}s."
                    ),
                })

        # 2. Arrival Delay incident
        if compliance.get("arrival_punctuality") == "late":
            existing = existing_incidents.filtered(
                lambda i: i.incident_type == "delay_arrival"
            )
            if not existing:
                incident_model.create({
                    "trip_id": trip.id,
                    "incident_type": "delay_arrival",
                    "source": "automatic",
                    "severity": "medium",
                    "timestamp_utc": (
                        trip.actual_end_utc or trip.scheduled_end_utc
                    ),
                    "rule_applied": "RF-20 / RF-21: Retraso en llegada",
                    "description": (
                        f"Llegada tardía a destino con retraso de "
                        f"{compliance.get('arrival_delay_s')}s."
                    ),
                })

        # 3. Checkpoint delays and missed stops
        for s in stops_eval:
            sv_rec = trip.stop_visit_ids.browse(s["stop_id"])
            route_stop = sv_rec.route_stop_id if sv_rec else False

            if s["status"] == "missed" and s.get("required"):
                existing = existing_incidents.filtered(
                    lambda i: (
                        i.incident_type == "stop_missed"
                        and i.stop_id == route_stop
                    )
                )
                if not existing:
                    incident_model.create({
                        "trip_id": trip.id,
                        "incident_type": "stop_missed",
                        "source": "automatic",
                        "severity": "high",
                        "stop_id": route_stop.id if route_stop else False,
                        "timestamp_utc": (
                            s.get("scheduled_at_utc")
                            or trip.scheduled_start_utc
                        ),
                        "latitude": s.get("latitude", 0.0),
                        "longitude": s.get("longitude", 0.0),
                        "rule_applied": "RF-22 / RF-23: Parada omitida",
                        "description": (
                            f"Parada obligatoria '{s['stop_name']}' omitida. "
                            f"Distancia mín: {s.get('min_distance_m')}m."
                        ),
                    })

            elif s["status"] == "late":
                existing = existing_incidents.filtered(
                    lambda i: (
                        i.incident_type == "delay_checkpoint"
                        and i.stop_id == route_stop
                    )
                )
                if not existing:
                    incident_model.create({
                        "trip_id": trip.id,
                        "incident_type": "delay_checkpoint",
                        "source": "automatic",
                        "severity": "low",
                        "stop_id": route_stop.id if route_stop else False,
                        "timestamp_utc": (
                            s.get("first_arrival_utc")
                            or trip.scheduled_start_utc
                        ),
                        "latitude": s.get("latitude", 0.0),
                        "longitude": s.get("longitude", 0.0),
                        "rule_applied": "RF-22: Retraso en control",
                        "description": (
                            f"Retraso de {s['delay_s']}s en punto de control "
                            f"'{s['stop_name']}'."
                        ),
                    })

        # 4. Route deviations
        for dev in deviations:
            t_start = dev["start_time"]
            matched = False
            dev_incidents = existing_incidents.filtered(
                lambda i: i.incident_type == "route_deviation"
            )
            for ex in dev_incidents:
                if abs((ex.timestamp_utc - t_start).total_seconds()) <= 60:
                    matched = True
                    break

            if not matched:
                dur = dev["duration_s"]
                pts = dev["point_count"]
                max_d = dev["max_distance_m"]
                incident_model.create({
                    "trip_id": trip.id,
                    "incident_type": "route_deviation",
                    "source": "automatic",
                    "severity": "high",
                    "timestamp_utc": t_start,
                    "latitude": dev["start_latitude"],
                    "longitude": dev["start_longitude"],
                    "rule_applied": "RF-24: Desvío del corredor de ruta",
                    "description": (
                        f"Desvío de corredor por {dur}s ({pts} puntos). "
                        f"Distancia máxima observada: {max_d}m."
                    ),
                    "evidence_data": json.dumps(dev, default=str),
                })

        # 5. GPS Gaps
        for gap in gaps:
            t_start = gap["start_time"]
            matched = False
            gap_incidents = existing_incidents.filtered(
                lambda i: i.incident_type == "gps_loss"
            )
            for ex in gap_incidents:
                if abs((ex.timestamp_utc - t_start).total_seconds()) <= 60:
                    matched = True
                    break

            if not matched:
                thresh = trip.gps_gap_threshold_s or 180
                incident_model.create({
                    "trip_id": trip.id,
                    "incident_type": "gps_loss",
                    "source": "automatic",
                    "severity": "medium",
                    "timestamp_utc": t_start,
                    "latitude": gap["gap_latitude"],
                    "longitude": gap["gap_longitude"],
                    "rule_applied": "RF-25: Pérdida prolongada de señal GPS",
                    "description": (
                        f"Interrupción de telemetría por {gap['duration_s']}s "
                        f"(umbral permitido: {thresh}s)."
                    ),
                    "evidence_data": json.dumps(gap, default=str),
                })

        return incident_model.search([("trip_id", "=", trip.id)])

    @api.model
    def _persist_evaluation_record(
        self, trip, params, compliance, is_compliant_adjusted, incidents
    ):
        """Persist immutable trip evaluation audit record."""
        eval_model = self.env["transport.trip.evaluation"]

        eval_vals = {
            "trip_id": trip.id,
            "evaluation_date": fields.Datetime.now(),
            "rules_version": "v1.0.0-phase4",
            "parameter_snapshot_json": json.dumps(params, indent=2),
            "integrity_status": compliance["integrity_status"],
            "is_compliant_gross": compliance["is_compliant_gross"],
            "is_compliant_adjusted": is_compliant_adjusted,
            "start_punctuality": compliance["start_punctuality"],
            "start_delay_s": compliance["start_delay_s"],
            "arrival_punctuality": compliance["arrival_punctuality"],
            "arrival_delay_s": compliance["arrival_delay_s"],
            "stops_total": compliance["stops_total"],
            "stops_on_time": compliance["stops_on_time"],
            "stops_late": compliance["stops_late"],
            "stops_missed": compliance["stops_missed"],
            "stops_indeterminate": compliance["stops_indeterminate"],
            "deviation_count": compliance["deviation_count"],
            "deviation_duration_s": compliance["deviation_duration_s"],
            "max_deviation_distance_m": compliance["max_deviation_distance_m"],
            "gps_gap_count": compliance["gps_gap_count"],
            "gps_gap_duration_s": compliance["gps_gap_duration_s"],
            "evaluation_summary": compliance["evaluation_summary"],
            "incident_ids": [(6, 0, incidents.ids)],
        }

        return eval_model.create(eval_vals)
