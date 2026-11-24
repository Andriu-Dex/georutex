"""Operational trip scheduling and lifecycle management model for GeoRutex."""

from datetime import timedelta, timezone
import json
import zoneinfo
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .transport_route_version import format_duration_spanish
from ..domain.geo import haversine_distance, is_valid_coordinate


class TransportTrip(models.Model):
    """Operational trip instance for a vehicle on a route."""

    _name = "transport.trip"
    _description = "Recorrido Operacional de Transporte"
    _order = "scheduled_start_utc desc, id desc"

    name = fields.Char(
        string="Código de Recorrido",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: self._default_name(),
    )
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Vehículo Asignado",
        required=True,
        index=True,
        domain="[('active', '=', True)]",
        help="Vehículo asignado para ejecutar este recorrido.",
    )
    driver_id = fields.Many2one(
        comodel_name="res.partner",
        string="Conductor (Contacto)",
        domain="[('is_company', '=', False)]",
        help="Conductor asignado al recorrido.",
    )
    driver_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario Conductor",
        index=True,
        help="Usuario del sistema Odoo para control de permisos de conductor.",
    )
    route_id = fields.Many2one(
        comodel_name="transport.route",
        string="Ruta",
        required=True,
        index=True,
    )
    route_version_id = fields.Many2one(
        comodel_name="transport.route.version",
        string="Versión de Ruta",
        required=True,
        domain="[('route_id', '=', route_id), ('state', '=', 'approved')]",
        help="Versión aprobada y congelada con los parámetros a evaluar.",
    )
    source_type = fields.Selection(
        selection=[
            ("real", "Datos Reales / GPS"),
            ("simulated", "Simulado"),
        ],
        string="Tipo de Datos",
        default="real",
        required=True,
        index=True,
        help="Diferencia inequívocamente datos reales de simulados.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("scheduled", "Programado"),
            ("in_progress", "En Curso"),
            ("completed", "Finalizado"),
            ("incomplete", "Incompleto"),
            ("cancelled", "Cancelado"),
            ("insufficient_data", "Datos Insuficientes"),
        ],
        string="Estado del Recorrido",
        default="draft",
        required=True,
        index=True,
    )

    # Scheduled timestamps and distance (stored in UTC, displayed in local time)
    scheduled_start_utc = fields.Datetime(
        string="Inicio Programado",
        required=True,
        index=True,
        help="Fecha y hora planificada de salida del recorrido (almacenada en UTC, mostrada en hora local).",
    )
    scheduled_end_utc = fields.Datetime(
        string="Fin Previsto / Llegada",
        required=True,
        index=True,
        help="Fecha y hora planificada de llegada calculada automáticamente según los tiempos de la ruta (almacenada en UTC, mostrada en hora local).",
    )
    scheduled_distance_m = fields.Float(
        string="Distancia Programada (m)",
        digits=(10, 2),
        help="Distancia geométrica planificada del recorrido en metros.",
    )
    scheduled_duration_s = fields.Integer(
        string="Duración Programada (s)",
        compute="_compute_durations",
        store=True,
        help="Tiempo estimado de viaje según los puntos de control de la versión de ruta.",
    )
    scheduled_duration_display = fields.Char(
        string="Duración Programada",
        compute="_compute_durations",
        store=True,
        help="Tiempo programado de viaje en formato legible (ej. '30 min 00 s').",
    )
    road_estimated_duration_s = fields.Integer(
        string="Estimación Red Vial (s)",
        compute="_compute_durations",
        store=True,
        help="Tiempo estimado por enrutamiento vial OSRM sin considerar congestión.",
    )
    road_estimated_duration_display = fields.Char(
        string="Estimación Red Vial",
        compute="_compute_durations",
        store=True,
        help="Estimación vial en formato legible (no es predicción de tráfico en vivo).",
    )

    # Exceptional manual duration override (Section 4)
    is_manual_duration_override = fields.Boolean(
        string="Ajuste Excepcional de Horario",
        default=False,
        help="Habilita a un gestor autorizado a modificar la hora final independientemente de la duración estándar de la ruta.",
    )
    manual_duration_override_reason = fields.Text(
        string="Justificación del Ajuste Excepcional",
        help="Justificación operativa obligatoria para el ajuste manual del horario.",
    )
    manual_duration_override_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Ajuste Autorizado Por",
        readonly=True,
    )

    # Actual observed timestamps and distance
    manual_start_utc = fields.Datetime(
        string="Inicio Manual",
        readonly=True,
        help="Instante de inicio manual por operador o conductor.",
    )
    manual_end_utc = fields.Datetime(
        string="Fin Manual",
        readonly=True,
        help="Instante de finalización manual por operador o conductor.",
    )
    first_gps_fix_utc = fields.Datetime(
        string="Primer Fix GPS",
        readonly=True,
        help="Primer registro de telemetría GPS asociado al recorrido.",
    )
    actual_start_utc = fields.Datetime(
        string="Salida Real Verificada",
        readonly=True,
        help="Primer instante verificado de salida de origen (RF-20).",
    )
    actual_end_utc = fields.Datetime(
        string="Llegada Real Verificada",
        readonly=True,
        help="Primer instante verificado de llegada a destino (RF-20).",
    )
    actual_start_evidence = fields.Char(
        string="Evidencia Salida Real",
        readonly=True,
        help="Criterio técnico de inferencia de salida de origen.",
    )
    actual_end_evidence = fields.Char(
        string="Evidencia Llegada Real",
        readonly=True,
        help="Criterio técnico de inferencia de llegada a destino.",
    )
    actual_distance_m = fields.Float(
        string="Distancia Real Recorrida (m)",
        digits=(10, 2),
        readonly=True,
    )
    actual_duration_s = fields.Integer(
        string="Duración Real Observada (s)",
        compute="_compute_durations",
        store=True,
        help="Tiempo transcurrido observado entre la salida verificada y la llegada a destino.",
    )
    actual_duration_display = fields.Char(
        string="Duración Real Observada",
        compute="_compute_durations",
        store=True,
        help="Duración real observada en formato legible.",
    )
    is_schedule_overdue = fields.Boolean(
        string="Horario Programado Vencido",
        compute="_compute_schedule_overdue",
        help="Indica que la hora de fin expiró y el viaje sigue en curso.",
    )

    # Evaluation and incidents (Phase 4, RF-26 through RF-30)
    evaluation_ids = fields.One2many(
        comodel_name="transport.trip.evaluation",
        inverse_name="trip_id",
        string="Historial de Evaluaciones",
    )
    evaluation_count = fields.Integer(
        string="Nº Evaluaciones",
        compute="_compute_evaluation_metrics",
        store=True,
    )
    last_evaluation_id = fields.Many2one(
        comodel_name="transport.trip.evaluation",
        string="Última Evaluación",
        compute="_compute_evaluation_metrics",
        store=True,
    )
    evaluation_status = fields.Selection(
        selection=[
            ("unevaluated", "Sin Evaluar"),
            ("compliant", "Conforme"),
            ("non_compliant", "No Conforme"),
            ("indeterminate", "Indeterminado / Insuficiente"),
        ],
        string="Estado de Evaluación",
        default="unevaluated",
        compute="_compute_evaluation_metrics",
        store=True,
        index=True,
    )
    incident_ids = fields.One2many(
        comodel_name="transport.incident",
        inverse_name="trip_id",
        string="Incidencias Registradas",
    )
    incident_count = fields.Integer(
        string="Nº Incidencias",
        compute="_compute_incident_count",
    )

    # Frozen parameter snapshot (RF-14 & Section 7.1)
    parameter_snapshot_json = fields.Text(
        string="Snapshot de Parámetros de Evaluación",
        readonly=True,
        help="Copia inmutable de parámetros canónicos al programar el viaje.",
    )
    stop_radius_m = fields.Float(
        string="Radio Parada Congelado (m)",
        readonly=True,
    )
    route_corridor_m = fields.Float(
        string="Corredor Ruta Congelado (m)",
        readonly=True,
    )
    lateness_tolerance_s = fields.Integer(
        string="Tolerancia Retraso Congelada (s)",
        readonly=True,
    )
    gps_gap_threshold_s = fields.Integer(
        string="Umbral Gap GPS Congelado (s)",
        readonly=True,
    )

    # Telemetry and checkpoint visits
    position_ids = fields.One2many(
        comodel_name="transport.vehicle.position",
        inverse_name="trip_id",
        string="Posiciones GPS Asociadas",
    )
    position_count = fields.Integer(
        string="Nº Posiciones GPS",
        compute="_compute_position_count",
    )
    stop_visit_ids = fields.One2many(
        comodel_name="transport.stop.visit",
        inverse_name="trip_id",
        string="Visitas a Paradas Programadas",
    )
    stop_visit_count = fields.Integer(
        string="Nº Paradas",
        compute="_compute_stop_visit_count",
    )
    notes = fields.Text(
        string="Observaciones Operacionales",
    )

    @api.model
    def _default_name(self):
        return (
            self.env["ir.sequence"].next_by_code("transport.trip")
            or "REC-NUEVO"
        )

    @api.depends("state", "scheduled_end_utc")
    def _compute_schedule_overdue(self):
        now = fields.Datetime.now()
        for trip in self:
            trip.is_schedule_overdue = bool(
                trip.state == "in_progress"
                and trip.scheduled_end_utc
                and trip.scheduled_end_utc < now
            )

    @api.depends(
        "route_version_id",
        "route_version_id.planned_duration_s",
        "scheduled_start_utc",
        "scheduled_end_utc",
        "scheduled_distance_m",
        "actual_start_utc",
        "actual_end_utc",
        "first_gps_fix_utc",
        "state",
        "is_manual_duration_override",
    )
    def _compute_durations(self):
        for trip in self:
            # 1. Scheduled duration from version or start/end difference
            ver_dur = trip.route_version_id.planned_duration_s if trip.route_version_id else 0
            if ver_dur > 0 and not trip.is_manual_duration_override:
                trip.scheduled_duration_s = ver_dur
            elif trip.scheduled_start_utc and trip.scheduled_end_utc:
                trip.scheduled_duration_s = max(
                    0, int((trip.scheduled_end_utc - trip.scheduled_start_utc).total_seconds())
                )
            else:
                trip.scheduled_duration_s = 0
            trip.scheduled_duration_display = format_duration_spanish(trip.scheduled_duration_s)

            # 2. Road estimated duration (~30 km/h = 8.33 m/s urban baseline reference)
            dist_m = trip.scheduled_distance_m or (
                trip.route_version_id.estimated_distance_m if trip.route_version_id else 0.0
            )
            if dist_m > 0:
                road_secs = int(dist_m / 8.33)
                trip.road_estimated_duration_s = road_secs
                trip.road_estimated_duration_display = format_duration_spanish(road_secs)
            else:
                trip.road_estimated_duration_s = 0
                trip.road_estimated_duration_display = "No disponible"

            # 3. Actual observed duration from GPS telemetry
            if trip.actual_start_utc and trip.actual_end_utc:
                act_secs = max(
                    0, int((trip.actual_end_utc - trip.actual_start_utc).total_seconds())
                )
                trip.actual_duration_s = act_secs
                trip.actual_duration_display = format_duration_spanish(act_secs)
            elif trip.first_gps_fix_utc and trip.actual_end_utc:
                act_secs = max(
                    0, int((trip.actual_end_utc - trip.first_gps_fix_utc).total_seconds())
                )
                trip.actual_duration_s = act_secs
                trip.actual_duration_display = format_duration_spanish(act_secs)
            else:
                trip.actual_duration_s = 0
                if trip.state == "in_progress":
                    trip.actual_duration_display = "En curso"
                elif trip.state == "completed":
                    trip.actual_duration_display = "Sin telemetría suficiente"
                else:
                    trip.actual_duration_display = "Pendiente de ejecución"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            v_id = vals.get("route_version_id")
            start = vals.get("scheduled_start_utc")
            end = vals.get("scheduled_end_utc")
            override = vals.get("is_manual_duration_override")

            if v_id:
                ver = self.env["transport.route.version"].browse(v_id)
                if not vals.get("scheduled_distance_m") and ver and ver.estimated_distance_m:
                    vals["scheduled_distance_m"] = ver.estimated_distance_m

                dur = ver.planned_duration_s if ver else 0
                # If start is provided and end is NOT provided, auto-calculate end
                if start and not end and dur > 0 and not override:
                    start_dt = fields.Datetime.from_string(start) if isinstance(start, str) else start
                    vals["scheduled_end_utc"] = start_dt + timedelta(seconds=dur)
                elif start and end and dur > 0:
                    start_dt = fields.Datetime.from_string(start) if isinstance(start, str) else start
                    end_dt = fields.Datetime.from_string(end) if isinstance(end, str) else end
                    actual_diff = int((end_dt - start_dt).total_seconds())
                    if actual_diff != dur and not override:
                        vals["is_manual_duration_override"] = True
                        if not vals.get("manual_duration_override_reason"):
                            vals["manual_duration_override_reason"] = (
                                "Ajuste manual de horario ingresado en creación."
                            )

            if not vals.get("source_type") and vals.get("vehicle_id"):
                v = self.env["fleet.vehicle"].browse(vals["vehicle_id"])
                if v and v.is_simulated:
                    vals["source_type"] = "simulated"

        return super().create(vals_list)

    def write(self, vals):
        for trip in self:
            if trip.state == "draft":
                override = vals.get(
                    "is_manual_duration_override", trip.is_manual_duration_override
                )
                start = vals.get("scheduled_start_utc", trip.scheduled_start_utc)
                ver_id = vals.get("route_version_id", trip.route_version_id.id)
                ver = (
                    self.env["transport.route.version"].browse(ver_id)
                    if ver_id
                    else False
                )
                dur = ver.planned_duration_s if ver else 0

                # Recalculate scheduled_end_utc on start/version change when not overridden
                if (
                    ("scheduled_start_utc" in vals or "route_version_id" in vals)
                    and "scheduled_end_utc" not in vals
                    and not override
                    and start
                    and dur > 0
                ):
                    start_dt = (
                        fields.Datetime.from_string(start)
                        if isinstance(start, str)
                        else start
                    )
                    vals["scheduled_end_utc"] = start_dt + timedelta(seconds=dur)

        res = super().write(vals)

        # Synchronize existing stop visits times if scheduled_start_utc or scheduled_end_utc changed
        if "scheduled_start_utc" in vals or "scheduled_end_utc" in vals:
            for trip in self:
                if trip.stop_visit_ids and trip.scheduled_start_utc:
                    for visit in trip.stop_visit_ids:
                        if visit.route_stop_id.stop_type == "origin":
                            visit.scheduled_at_utc = trip.scheduled_start_utc
                        elif visit.route_stop_id.stop_type == "destination":
                            visit.scheduled_at_utc = trip.scheduled_end_utc
                        elif visit.route_stop_id.planned_offset_seconds:
                            visit.scheduled_at_utc = trip.scheduled_start_utc + timedelta(
                                seconds=visit.route_stop_id.planned_offset_seconds
                            )

        return res

    def _compute_position_count(self):
        for trip in self:
            trip.position_count = len(trip.position_ids)

    def _compute_stop_visit_count(self):
        for trip in self:
            trip.stop_visit_count = len(trip.stop_visit_ids)

    @api.depends(
        "evaluation_ids",
        "evaluation_ids.is_compliant_adjusted",
        "evaluation_ids.integrity_status",
    )
    def _compute_evaluation_metrics(self):
        for trip in self:
            evals = trip.evaluation_ids.sorted("id", reverse=True)
            trip.evaluation_count = len(evals)
            if evals:
                latest = evals[0]
                trip.last_evaluation_id = latest
                if latest.integrity_status == "insufficient_data":
                    trip.evaluation_status = "indeterminate"
                elif latest.is_compliant_adjusted:
                    trip.evaluation_status = "compliant"
                else:
                    trip.evaluation_status = "non_compliant"
            else:
                trip.last_evaluation_id = False
                trip.evaluation_status = "unevaluated"

    def _compute_incident_count(self):
        for trip in self:
            trip.incident_count = len(trip.incident_ids)

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            if self.vehicle_id.driver_id and not self.driver_id:
                self.driver_id = self.vehicle_id.driver_id
            if self.vehicle_id.is_simulated:
                self.source_type = "simulated"

    @api.onchange("driver_id")
    def _onchange_driver_id(self):
        if self.driver_id:
            user = self.env["res.users"].search(
                [("partner_id", "=", self.driver_id.id)], limit=1
            )
            if user:
                self.driver_user_id = user

    @api.onchange("vehicle_id", "driver_id", "scheduled_start_utc", "scheduled_end_utc")
    def _onchange_check_availability(self):
        if not (self.scheduled_start_utc and self.scheduled_end_utc):
            return
        if self.vehicle_id:
            domain = [
                ("vehicle_id", "=", self.vehicle_id.id),
                ("state", "in", ["draft", "scheduled", "in_progress"]),
                ("scheduled_start_utc", "<", self.scheduled_end_utc),
                ("scheduled_end_utc", ">", self.scheduled_start_utc),
            ]
            if self._origin and self._origin.id:
                domain.append(("id", "!=", self._origin.id))
            conflict = self.search(domain, limit=1)
            if conflict:
                return {
                    "warning": {
                        "title": "Aviso de Disponibilidad de Vehículo",
                        "message": (
                            f"El vehículo '{self.vehicle_id.display_name}' ya tiene programado "
                            f"el recorrido {conflict.name} ({conflict.scheduled_start_utc} a {conflict.scheduled_end_utc})."
                        ),
                    }
                }
        if self.driver_id:
            domain = [
                ("driver_id", "=", self.driver_id.id),
                ("state", "in", ["draft", "scheduled", "in_progress"]),
                ("scheduled_start_utc", "<", self.scheduled_end_utc),
                ("scheduled_end_utc", ">", self.scheduled_start_utc),
            ]
            if self._origin and self._origin.id:
                domain.append(("id", "!=", self._origin.id))
            conflict = self.search(domain, limit=1)
            if conflict:
                return {
                    "warning": {
                        "title": "Aviso de Disponibilidad de Conductor",
                        "message": (
                            f"El conductor '{self.driver_id.name}' ya tiene programado "
                            f"el recorrido {conflict.name} ({conflict.scheduled_start_utc} a {conflict.scheduled_end_utc})."
                        ),
                    }
                }

    @api.onchange("route_id")
    def _onchange_route_id(self):
        if self.route_id:
            if self.route_id.current_version_id:
                self.route_version_id = self.route_id.current_version_id
            else:
                approved = self.env["transport.route.version"].search([
                    ("route_id", "=", self.route_id.id),
                    ("state", "=", "approved"),
                ], limit=1)
                self.route_version_id = approved

    @api.onchange("route_version_id")
    def _onchange_route_version_id(self):
        if self.route_version_id:
            self.scheduled_distance_m = (
                self.route_version_id.estimated_distance_m or 0.0
            )
            dur = self.route_version_id.planned_duration_s
            if self.scheduled_start_utc and dur > 0 and not self.is_manual_duration_override:
                self.scheduled_end_utc = self.scheduled_start_utc + timedelta(seconds=dur)

    @api.onchange("scheduled_start_utc")
    def _onchange_scheduled_start_utc(self):
        if self.scheduled_start_utc and self.route_version_id:
            dur = self.route_version_id.planned_duration_s
            if dur > 0 and not self.is_manual_duration_override:
                self.scheduled_end_utc = self.scheduled_start_utc + timedelta(seconds=dur)

    @api.onchange("is_manual_duration_override")
    def _onchange_is_manual_duration_override(self):
        if not self.is_manual_duration_override and self.scheduled_start_utc and self.route_version_id:
            dur = self.route_version_id.planned_duration_s
            if dur > 0:
                self.scheduled_end_utc = self.scheduled_start_utc + timedelta(seconds=dur)
            self.manual_duration_override_reason = False

    @api.constrains(
        "scheduled_start_utc",
        "scheduled_end_utc",
        "is_manual_duration_override",
        "manual_duration_override_reason",
    )
    def _check_scheduled_times(self):
        for trip in self:
            if trip.scheduled_start_utc and trip.scheduled_end_utc:
                if trip.scheduled_start_utc >= trip.scheduled_end_utc:
                    raise ValidationError(
                        "El inicio programado debe ser estrictamente "
                        "anterior al fin programado."
                    )
            if trip.is_manual_duration_override and trip.state != "draft":
                if not trip.manual_duration_override_reason:
                    raise ValidationError(
                        "Debe especificar una justificación obligatoria para "
                        "el ajuste excepcional de horario."
                    )

    @api.constrains("route_id", "route_version_id")
    def _check_route_version_consistency(self):
        for trip in self:
            if trip.route_version_id.route_id != trip.route_id:
                raise ValidationError(
                    f"La versión '{trip.route_version_id.name}' no "
                    f"pertenece a la ruta '{trip.route_id.name}'."
                )
            if (
                trip.state != "draft"
                and trip.route_version_id.state != "approved"
            ):
                raise ValidationError(
                    "No se puede programar viaje con versión no aprobada."
                )

    @api.constrains(
        "vehicle_id",
        "driver_id",
        "driver_user_id",
        "scheduled_start_utc",
        "scheduled_end_utc",
        "state",
    )
    def _check_assignment_conflicts(self):
        """Enforce RF-12: Prevent overlapping vehicle or driver trips."""
        active_states = ["scheduled", "in_progress"]
        for trip in self:
            if trip.state not in active_states:
                continue
            if not trip.scheduled_start_utc or not trip.scheduled_end_utc:
                continue

            # 1. Check vehicle overlap
            vehicle_conflict = self.search([
                ("id", "!=", trip.id),
                ("vehicle_id", "=", trip.vehicle_id.id),
                ("state", "in", active_states),
                ("scheduled_start_utc", "<", trip.scheduled_end_utc),
                ("scheduled_end_utc", ">", trip.scheduled_start_utc),
            ], limit=1)
            if vehicle_conflict:
                v_name = trip.vehicle_id.name
                c_name = vehicle_conflict.name
                c_start = vehicle_conflict.scheduled_start_utc
                c_end = vehicle_conflict.scheduled_end_utc
                raise ValidationError(
                    f"Conflicto (RF-12): El vehículo '{v_name}' ya tiene "
                    f"el recorrido '{c_name}' en [{c_start} - {c_end}]."
                )

            # 2. Check driver overlap (by partner or user)
            if trip.driver_id:
                driver_conflict = self.search([
                    ("id", "!=", trip.id),
                    ("driver_id", "=", trip.driver_id.id),
                    ("state", "in", active_states),
                    ("scheduled_start_utc", "<", trip.scheduled_end_utc),
                    ("scheduled_end_utc", ">", trip.scheduled_start_utc),
                ], limit=1)
                if driver_conflict:
                    d_name = trip.driver_id.name
                    c_name = driver_conflict.name
                    c_start = driver_conflict.scheduled_start_utc
                    c_end = driver_conflict.scheduled_end_utc
                    raise ValidationError(
                        f"Conflicto (RF-12): El conductor '{d_name}' ya tiene "
                        f"el recorrido '{c_name}' en [{c_start} - {c_end}]."
                    )

            # 3. Check Traccar device overlap (CP-27, RF-08, RF-12)
            dev_id = trip.vehicle_id.traccar_device_id
            if dev_id:
                device_conflict = self.search([
                    ("id", "!=", trip.id),
                    ("vehicle_id.traccar_device_id", "=", dev_id),
                    ("state", "in", active_states),
                    ("scheduled_start_utc", "<", trip.scheduled_end_utc),
                    ("scheduled_end_utc", ">", trip.scheduled_start_utc),
                ], limit=1)
                if (
                    device_conflict
                    and device_conflict.vehicle_id != trip.vehicle_id
                ):
                    raise ValidationError(
                        f"Conflicto de Dispositivo (RF-08/12): El dispositivo "
                        f"Traccar {dev_id} ya está asignado a "
                        f"'{device_conflict.vehicle_id.name}' en el recorrido "
                        f"'{device_conflict.name}'."
                    )

    def _freeze_parameter_snapshot(self):
        """Freeze canonical evaluation parameters into snapshot (RF-14)."""
        for trip in self:
            ver = trip.route_version_id
            snapshot = {
                "route_version_id": ver.id,
                "version_number": ver.version_number,
                "route_code": ver.route_id.code,
                "stop_radius_m": ver.stop_radius_m,
                "route_corridor_m": ver.route_corridor_m,
                "lateness_tolerance_s": ver.lateness_tolerance_s,
                "gps_gap_threshold_s": ver.gps_gap_threshold_s,
                "minimum_consecutive_deviation_points": (
                    ver.minimum_consecutive_deviation_points
                ),
                "minimum_deviation_duration_s": (
                    ver.minimum_deviation_duration_s
                ),
                "geo_accuracy_max_m": ver.geo_accuracy_max_m,
                "frozen_at_utc": fields.Datetime.now().isoformat(),
            }
            trip.write({
                "parameter_snapshot_json": json.dumps(snapshot, indent=2),
                "stop_radius_m": ver.stop_radius_m,
                "route_corridor_m": ver.route_corridor_m,
                "lateness_tolerance_s": ver.lateness_tolerance_s,
                "gps_gap_threshold_s": ver.gps_gap_threshold_s,
            })

    def _generate_scheduled_stop_visits(self):
        """Create planned stop visit records from route checkpoints."""
        self.ensure_one()
        self.stop_visit_ids.filtered(lambda v: v.status == "pending").unlink()

        visits_to_create = []
        for stop in self.route_version_id.stop_ids.sorted("sequence"):
            sched_time = False
            if stop.stop_type == "origin":
                sched_time = self.scheduled_start_utc
            elif stop.stop_type == "destination":
                sched_time = self.scheduled_end_utc
            elif self.scheduled_start_utc and stop.planned_offset_seconds:
                sched_time = self.scheduled_start_utc + timedelta(
                    seconds=stop.planned_offset_seconds
                )

            rad = stop.radius_m or self.route_version_id.stop_radius_m
            visits_to_create.append({
                "trip_id": self.id,
                "route_stop_id": stop.id,
                "sequence": stop.sequence,
                "stop_name": stop.name,
                "stop_type": stop.stop_type,
                "required": stop.required,
                "latitude": stop.latitude,
                "longitude": stop.longitude,
                "radius_m": rad,
                "scheduled_at_utc": sched_time,
                "status": "pending",
            })

        if visits_to_create:
            self.env["transport.stop.visit"].create(visits_to_create)

    def _reconcile_gps_times(self):
        """Ensure telemetry timestamps and first fix are tracked."""
        for trip in self:
            if trip.position_ids:
                fixes = trip.position_ids.mapped("fix_time")
                earliest = min(fixes)
                latest = max(fixes)
                vals = {}
                if (
                    not trip.first_gps_fix_utc
                    or trip.first_gps_fix_utc > earliest
                ):
                    vals["first_gps_fix_utc"] = earliest
                if trip.state in ("in_progress", "completed"):
                    if (
                        not trip.actual_start_utc
                        or trip.actual_start_utc > earliest
                    ):
                        vals["actual_start_utc"] = earliest
                        vals["actual_start_evidence"] = "reconciled_earliest"
                if trip.state == "completed":
                    if (
                        not trip.actual_end_utc
                        or trip.actual_end_utc < latest
                    ):
                        vals["actual_end_utc"] = latest
                        vals["actual_end_evidence"] = "reconciled_latest"
                if vals:
                    trip.write(vals)

    # State transition actions
    def action_schedule(self):
        """Transition from draft to scheduled and generate stop visits."""
        for trip in self:
            if trip.state != "draft":
                raise UserError(
                    f"Solo se pueden programar recorridos en Borrador "
                    f"(actual: {trip.state})."
                )
            if trip.route_version_id.state != "approved":
                raise UserError(
                    "La versión de ruta asignada debe estar aprobada."
                )

            # Manual override validation and auditing (Section 4)
            if trip.is_manual_duration_override:
                is_manager = self.env.user.has_group(
                    "uta_transport_monitor.group_transport_manager"
                ) or self.env.is_admin()
                if not is_manager:
                    raise UserError(
                        "Solo los usuarios con rol de Gestor de Transporte "
                        "pueden autorizar ajustes excepcionales de horario."
                    )
                if not trip.manual_duration_override_reason:
                    raise ValidationError(
                        "Debe especificar una justificación obligatoria para "
                        "el ajuste excepcional de horario."
                    )
                trip.manual_duration_override_user_id = self.env.user.id
            else:
                # Ensure scheduled_end_utc matches scheduled_start_utc + duration
                if trip.scheduled_duration_s > 0 and trip.scheduled_start_utc:
                    expected_end = trip.scheduled_start_utc + timedelta(
                        seconds=trip.scheduled_duration_s
                    )
                    if trip.scheduled_end_utc != expected_end:
                        trip.scheduled_end_utc = expected_end

            if (
                not trip.scheduled_distance_m
                and trip.route_version_id.estimated_distance_m
            ):
                trip.scheduled_distance_m = (
                    trip.route_version_id.estimated_distance_m
                )
            trip._freeze_parameter_snapshot()
            trip._generate_scheduled_stop_visits()
            trip.write({"state": "scheduled"})
        return True

    def action_start(self):
        """Transition from scheduled to in_progress."""
        for trip in self:
            if trip.state != "scheduled":
                raise UserError(
                    f"Solo recorridos en Programado pueden iniciarse "
                    f"(actual: {trip.state})."
                )
            now = fields.Datetime.now()
            vals = {
                "state": "in_progress",
                "manual_start_utc": now,
            }
            earliest_pos = self.env["transport.vehicle.position"].search([
                ("trip_id", "=", trip.id),
            ], order="fix_time asc", limit=1)
            if earliest_pos:
                vals["first_gps_fix_utc"] = earliest_pos.fix_time
                vals["actual_start_utc"] = earliest_pos.fix_time
                vals["actual_start_evidence"] = "first_valid_fix_fallback"
            elif not trip.actual_start_utc:
                vals["actual_start_utc"] = now
                vals["actual_start_evidence"] = "manual_start_fallback"
            trip.write(vals)
        return True

    def action_complete(self):
        """Transition from in_progress to completed."""
        for trip in self:
            if trip.state != "in_progress":
                raise UserError(
                    f"Solo recorridos En Curso pueden finalizarse "
                    f"(actual: {trip.state})."
                )
            now = fields.Datetime.now()
            vals = {
                "state": "completed",
                "manual_end_utc": now,
            }
            latest_pos = self.env["transport.vehicle.position"].search([
                ("trip_id", "=", trip.id),
            ], order="fix_time desc", limit=1)
            if latest_pos:
                vals["actual_end_utc"] = latest_pos.fix_time
                vals["actual_end_evidence"] = "last_valid_fix_fallback"
            elif not trip.actual_end_utc:
                vals["actual_end_utc"] = now
                vals["actual_end_evidence"] = "manual_end_fallback"
            trip.write(vals)
        return True

    def action_evaluate_trip(self):
        """Trigger automated evaluation engine for this trip (Phase 4)."""
        self.ensure_one()
        eval_service = self.env["transport.trip.evaluation.service"]
        evaluation = eval_service.evaluate_trip(self)
        status_label = (
            "Conforme"
            if evaluation.is_compliant_adjusted
            else "No Conforme"
        )
        msg_type = "info" if evaluation.is_compliant_adjusted else "warning"
        msg = (
            f"Dictamen: {status_label}. "
            f"Paradas: {evaluation.stops_on_time}/{evaluation.stops_total}. "
            f"Desvíos: {evaluation.deviation_count}. "
            f"Gaps GPS: {evaluation.gps_gap_count}."
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": f"Evaluación Completada: {self.name}",
                "message": msg,
                "type": msg_type,
                "sticky": False,
            },
        }

    def action_cancel(self):
        """Cancel a trip, permitted from draft or scheduled."""
        for trip in self:
            if trip.state in ("completed", "incomplete"):
                raise UserError(
                    f"No es posible cancelar un recorrido en {trip.state}."
                )
            trip.write({"state": "cancelled"})
        return True

    def action_set_to_draft(self):
        """Revert scheduled or cancelled trip to draft."""
        for trip in self:
            if trip.state not in ("scheduled", "cancelled"):
                raise UserError(
                    f"No se puede revertir un recorrido en {trip.state}."
                )
            trip.write({"state": "draft"})
        return True

    def action_sync_trip_gps(self):
        """Sync telemetry for this trip's time window and associate points."""
        self.ensure_one()
        trip_service = self.env["transport.trip.service"]
        count = trip_service.sync_trip_gps_telemetry(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sincronización de Recorrido",
                "message": (
                    f"Se procesaron {count} nuevas posiciones para el "
                    f"recorrido {self.name}."
                ),
                "type": "info",
                "sticky": False,
            },
        }

    def action_report_incident(self):
        """Open right-side editable incident card prelinked to this trip."""
        self.ensure_one()
        return {
            "name": f"Reportar Incidencia — {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "transport.incident",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_trip_id": self.id,
                "default_source": "manual",
            },
        }

    @api.model
    def get_driver_home_data(self):
        """Return real operational home payload for the logged-in driver.

        Strictly uses standard ORM access (respecting ir.rule isolation) so a
        driver only receives their own trips, assigned vehicles, and incidents.
        """
        tz_ec = zoneinfo.ZoneInfo("America/Guayaquil")
        now_ec = fields.Datetime.now().replace(tzinfo=timezone.utc).astimezone(
            tz_ec
        )
        user = self.env.user

        def _fmt_ec(dt_val):
            if not dt_val:
                return "Sin horario"
            return (
                dt_val.replace(tzinfo=timezone.utc)
                .astimezone(tz_ec)
                .strftime("%d/%m/%Y %H:%M")
            )

        # Own trips (record-rule filtered for drivers)
        own_domain = []
        if user.has_group("uta_transport_monitor.group_transport_driver") and not (
            user.has_group("uta_transport_monitor.group_transport_manager")
            or user.has_group("uta_transport_monitor.group_transport_analyst")
        ):
            own_domain = [
                "|",
                ("driver_user_id", "=", user.id),
                ("driver_id", "=", user.partner_id.id),
            ]

        all_trips = self.search(own_domain, order="scheduled_start_utc desc, id desc")
        state_labels = dict(self._fields["state"].selection)
        trips_payload = []
        for trip in all_trips[:8]:
            trips_payload.append({
                "id": trip.id,
                "name": trip.name,
                "route_name": trip.route_id.name if trip.route_id else "Sin ruta",
                "route_code": trip.route_id.code if trip.route_id else "",
                "origin_name": trip.route_id.origin_name if trip.route_id else "",
                "destination_name": (
                    trip.route_id.destination_name if trip.route_id else ""
                ),
                "vehicle_name": (
                    trip.vehicle_id.name if trip.vehicle_id else "Sin vehículo"
                ),
                "scheduled_start_local": _fmt_ec(trip.scheduled_start_utc),
                "scheduled_end_local": _fmt_ec(trip.scheduled_end_utc),
                "state": trip.state,
                "state_label": state_labels.get(trip.state, trip.state),
                "source_type": trip.source_type,
                "position_count": trip.position_count,
                "incident_count": trip.incident_count,
            })

        # Own vehicles (record-rule filtered) with real GPS coordinates & speed
        vehicles = self.env["fleet.vehicle"].search(
            [("active", "=", True)], limit=5
        )
        freshness_labels = dict(
            self.env["fleet.vehicle"]._fields["gps_freshness_state"].selection
        )
        vehicles_payload = []
        for veh in vehicles:
            vehicles_payload.append({
                "id": veh.id,
                "name": veh.name,
                "license_plate": veh.license_plate or "",
                "freshness": veh.gps_freshness_state or "no_data",
                "freshness_label": freshness_labels.get(
                    veh.gps_freshness_state, "Sin datos"
                ),
                "last_gps_time_local": veh.last_gps_time_local or "Sin registro",
                "speed": round(float(veh.last_gps_speed or 0.0), 1),
                "has_speed": bool(veh.last_gps_fix_time),
                "latitude": veh.last_gps_latitude or 0.0,
                "longitude": veh.last_gps_longitude or 0.0,
                "has_coordinates": bool(
                    veh.last_gps_latitude and veh.last_gps_longitude
                ),
                "is_simulated": veh.is_simulated,
            })

        # Own incidents (record-rule filtered)
        inc_model = self.env["transport.incident"]
        all_incidents = inc_model.search([], order="timestamp_utc desc, id desc")
        inc_type_labels = dict(inc_model._fields["incident_type"].selection)
        inc_sev_labels = dict(inc_model._fields["severity"].selection)
        inc_state_labels = dict(inc_model._fields["state"].selection)
        incidents_payload = []
        for inc in all_incidents[:6]:
            incidents_payload.append({
                "id": inc.id,
                "name": inc.name,
                "trip_name": inc.trip_id.name if inc.trip_id else "Sin recorrido",
                "incident_type": inc.incident_type,
                "incident_type_label": inc_type_labels.get(
                    inc.incident_type, inc.incident_type
                ),
                "severity": inc.severity,
                "severity_label": inc_sev_labels.get(inc.severity, inc.severity),
                "state": inc.state,
                "state_label": inc_state_labels.get(inc.state, inc.state),
                "timestamp_local": _fmt_ec(inc.timestamp_utc),
                "description": inc.description or "",
            })

        days_es = [
            "Lunes", "Martes", "Miércoles", "Jueves",
            "Viernes", "Sábado", "Domingo",
        ]
        months_es = [
            "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        ]
        date_label = (
            f"{days_es[now_ec.weekday()]}, {now_ec.day} de "
            f"{months_es[now_ec.month]} de {now_ec.year}"
        )

        # Featured trip (active in_progress or next scheduled) with real telemetry & map data
        featured = (
            all_trips.filtered(lambda t: t.state == "in_progress")[:1]
            or all_trips.filtered(lambda t: t.state == "scheduled")[:1]
            or all_trips[:1]
        )
        featured_payload = False
        if featured:
            trip = featured[0]
            # Map stop visits using real transport.stop.visit fields (route_stop_id, first_arrival_utc, status)
            visits_by_stop = {
                v.route_stop_id.id: v for v in trip.stop_visit_ids if v.route_stop_id
            }
            stops_list = []
            visited_count = 0
            next_stop = None
            raw_stops = (
                trip.route_version_id.stop_ids.sorted(
                    key=lambda s: (s.sequence, s.id)
                )
                if trip.route_version_id
                else self.env["transport.route.stop"]
            )
            for idx, st in enumerate(raw_stops, start=1):
                visit = visits_by_stop.get(st.id)
                is_visited = bool(
                    visit and (visit.first_arrival_utc or visit.status in ("on_time", "late"))
                )
                if is_visited:
                    visited_count += 1
                stop_entry = {
                    "id": st.id,
                    "order": idx,
                    "name": st.name,
                    "stop_type": st.stop_type,
                    "latitude": st.latitude or 0.0,
                    "longitude": st.longitude or 0.0,
                    "has_coords": bool(st.latitude and st.longitude),
                    "visited": is_visited,
                    "status": visit.status if visit else "pending",
                    "delay_s": visit.delay_s if visit else 0,
                    "scheduled_local": (
                        _fmt_ec(visit.scheduled_at_utc) if visit and visit.scheduled_at_utc else ""
                    ),
                    "arrival_local": (
                        _fmt_ec(visit.first_arrival_utc) if visit and visit.first_arrival_utc else ""
                    ),
                }
                if not is_visited and next_stop is None:
                    next_stop = stop_entry
                stops_list.append(stop_entry)

            total_stops = len(stops_list)
            remaining_stops = max(0, total_stops - visited_count)
            progress_pct = (
                int(round((visited_count / total_stops) * 100))
                if total_stops
                else (100 if trip.state == "completed" else 0)
            )

            # Real distance traveled in km (from actual_distance_m or haversine over position_ids)
            distance_km = None
            if trip.actual_distance_m and trip.actual_distance_m > 0:
                distance_km = round(trip.actual_distance_m / 1000.0, 2)
            elif len(trip.position_ids) >= 2:
                pts = trip.position_ids.sorted(key=lambda p: (p.fix_time, p.id))
                total_m = 0.0
                prev_pt = None
                for pt in pts:
                    if is_valid_coordinate(pt.latitude, pt.longitude):
                        if prev_pt is not None:
                            total_m += haversine_distance(
                                prev_pt.latitude, prev_pt.longitude,
                                pt.latitude, pt.longitude,
                            )
                        prev_pt = pt
                if total_m > 0:
                    distance_km = round(total_m / 1000.0, 2)

            # Real elapsed time from actual_start_utc / manual_start_utc
            start_ref = trip.actual_start_utc or trip.manual_start_utc
            end_ref = trip.actual_end_utc or trip.manual_end_utc
            if start_ref:
                ref_end_dt = end_ref or fields.Datetime.now()
                elapsed_sec = max(0, int((ref_end_dt - start_ref).total_seconds()))
                hrs, rem = divmod(elapsed_sec, 3600)
                mins = rem // 60
                elapsed_display = f"{hrs}h {mins}m" if hrs else f"{mins} min"
            else:
                elapsed_display = "Sin iniciar"

            # Real punctuality indicator from evaluation or observed stop delays
            eval_labels = dict(self._fields["evaluation_status"].selection)
            if trip.evaluation_status and trip.evaluation_status != "unevaluated":
                punctuality_label = eval_labels.get(trip.evaluation_status, "Sin evaluar")
                punctuality_tone = (
                    "green" if trip.evaluation_status == "compliant"
                    else ("red" if trip.evaluation_status == "non_compliant" else "amber")
                )
            else:
                delays = [s["delay_s"] for s in stops_list if s["visited"] and s["delay_s"] is not None]
                if delays:
                    max_delay_min = int(round(max(delays) / 60.0))
                    punctuality_label = (
                        "Puntual" if max_delay_min <= 2 else f"+{max_delay_min} min retraso"
                    )
                    punctuality_tone = "green" if max_delay_min <= 2 else "amber"
                else:
                    punctuality_label = "Sin evaluar"
                    punctuality_tone = "muted"

            # Real reference polyline from route_version_id
            ref_polyline = []
            if trip.route_version_id and trip.route_version_id.reference_polyline:
                try:
                    raw_poly = json.loads(trip.route_version_id.reference_polyline)
                    coords = (
                        raw_poly.get("coordinates")
                        if isinstance(raw_poly, dict) and raw_poly.get("type") == "LineString"
                        else raw_poly
                    )
                    if isinstance(coords, list):
                        for pt in coords:
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                                ref_polyline.append([pt[1], pt[0]])
                except Exception:
                    ref_polyline = []

            veh = trip.vehicle_id
            featured_payload = {
                "id": trip.id,
                "name": trip.name,
                "route_name": trip.route_id.name if trip.route_id else "Sin ruta",
                "route_code": trip.route_id.code if trip.route_id else "",
                "origin_name": trip.route_id.origin_name if trip.route_id else "",
                "destination_name": (
                    trip.route_id.destination_name if trip.route_id else ""
                ),
                "vehicle_name": veh.name if veh else "Sin vehículo",
                "license_plate": veh.license_plate if veh else "",
                "vehicle_speed_display": (
                    f"{round(float(veh.last_gps_speed or 0.0), 1)} km/h"
                    if veh and veh.last_gps_fix_time
                    else "N/A"
                ),
                "vehicle_lat": veh.last_gps_latitude if veh and veh.last_gps_latitude else 0.0,
                "vehicle_lon": veh.last_gps_longitude if veh and veh.last_gps_longitude else 0.0,
                "vehicle_has_coords": bool(veh and veh.last_gps_latitude and veh.last_gps_longitude),
                "vehicle_freshness": veh.gps_freshness_state if veh else "no_data",
                "scheduled_start_local": _fmt_ec(trip.scheduled_start_utc),
                "scheduled_end_local": _fmt_ec(trip.scheduled_end_utc),
                "state": trip.state,
                "state_label": state_labels.get(trip.state, trip.state),
                "source_type": trip.source_type,
                "position_count": trip.position_count,
                "incident_count": trip.incident_count,
                "stops": stops_list,
                "next_stop_name": next_stop["name"] if next_stop else ("Recorrido completo" if total_stops else "Sin paradas"),
                "next_stop_order": next_stop["order"] if next_stop else total_stops,
                "visited_stops": visited_count,
                "remaining_stops": remaining_stops,
                "total_stops": total_stops,
                "progress_pct": progress_pct,
                "distance_display": f"{distance_km} km" if distance_km is not None else "N/A",
                "elapsed_display": elapsed_display,
                "punctuality_label": punctuality_label,
                "punctuality_tone": punctuality_tone,
                "reference_polyline": ref_polyline,
                "can_start": trip.state in ("draft", "scheduled"),
                "can_complete": trip.state == "in_progress",
            }

        return {
            "driver_name": user.name,
            "driver_email": user.email or user.login,
            "local_date_label": date_label,
            "local_time_label": now_ec.strftime("%H:%M ECT"),
            "stats": {
                "total_trips": len(all_trips),
                "active_trips": len(
                    all_trips.filtered(
                        lambda t: t.state in ("scheduled", "in_progress")
                    )
                ),
                "completed_trips": len(
                    all_trips.filtered(lambda t: t.state == "completed")
                ),
                "pending_incidents": len(
                    all_incidents.filtered(lambda i: i.state == "pending")
                ),
                "total_incidents": len(all_incidents),
            },
            "featured_trip": featured_payload,
            "vehicles": vehicles_payload,
            "trips": trips_payload,
            "incidents": incidents_payload,
        }

    @api.model
    def action_driver_transition_trip(self, trip_id, target_action):
        """Allow an assigned driver (or manager) to start/complete their own trip safely."""
        trip = self.browse(int(trip_id)).exists()
        if not trip:
            raise UserError("El recorrido seleccionado no existe.")
        user = self.env.user
        is_manager = user.has_group("uta_transport_monitor.group_transport_manager")
        is_owner = (
            trip.driver_user_id.id == user.id
            or (trip.driver_id and trip.driver_id.id == user.partner_id.id)
        )
        if not (is_manager or is_owner):
            raise UserError("No tienes permisos para cambiar el estado de este recorrido.")
        if target_action == "start":
            trip.sudo().action_start()
        elif target_action == "complete":
            trip.sudo().action_complete()
        else:
            raise UserError("Acción de recorrido no soportada.")
        return {"ok": True, "state": trip.state}

    @api.model
    def get_admin_home_data(self):
        """Return real fleet, map, KPI, route, trip, incident, and Traccar data for Admin Ops Center."""
        user = self.env.user
        if not (
            user.has_group("base.group_system")
            or user.has_group("uta_transport_monitor.group_transport_manager")
            or user.has_group("uta_transport_monitor.group_transport_analyst")
        ):
            raise UserError("Acceso restringido al centro de control de flota.")

        tz_ec = zoneinfo.ZoneInfo("America/Guayaquil")
        now_utc = fields.Datetime.now().replace(tzinfo=timezone.utc)
        now_ec = now_utc.astimezone(tz_ec)

        def _fmt_ec(dt_val):
            if not dt_val:
                return "Sin horario"
            return (
                dt_val.replace(tzinfo=timezone.utc)
                .astimezone(tz_ec)
                .strftime("%d/%m/%Y %H:%M")
            )

        Vehicle = self.env["fleet.vehicle"]
        Route = self.env["transport.route"]
        Stop = self.env["transport.route.stop"]
        Incident = self.env["transport.incident"]
        Position = self.env["transport.vehicle.position"]

        all_vehicles = Vehicle.search([("active", "=", True)])
        tracked_vehicles = all_vehicles.filtered(lambda v: v.gps_tracking_enabled)
        online_vehicles = tracked_vehicles.filtered(
            lambda v: v.gps_freshness_state in ("online", "fresh")
        )
        stale_vehicles = tracked_vehicles.filtered(
            lambda v: v.gps_freshness_state == "stale"
        )
        offline_vehicles = tracked_vehicles.filtered(
            lambda v: v.gps_freshness_state not in ("online", "fresh", "stale")
        )
        simulated_vehicles = all_vehicles.filtered(lambda v: v.is_simulated)

        active_routes = Route.search([("active", "=", True)], order="code asc, name asc")
        stops_total = Stop.search_count([])

        today_start_ec = now_ec.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_ec.astimezone(timezone.utc).replace(tzinfo=None)
        trips_today = self.search(
            [("scheduled_start_utc", ">=", today_start_utc)]
        )
        active_trips = self.search([("state", "in", ("scheduled", "in_progress"))])
        recent_trips = self.search([], order="scheduled_start_utc desc, id desc", limit=20)

        open_incidents = Incident.search(
            [("state", "in", ("pending", "reported", "under_review"))]
        )
        critical_incidents = open_incidents.filtered(
            lambda i: i.severity in ("critical", "high")
        )
        recent_incidents = Incident.search([], order="timestamp_utc desc, id desc", limit=10)

        total_positions = Position.search_count([])
        last_pos = Position.search([], order="fix_time desc, id desc", limit=1)

        # Real MT-01, MT-02 & daily trend metrics from transport.metrics.service
        mt01 = {"display_value": "N/A", "value": None, "sample_size": 0, "is_na": True}
        mt02 = {"display_value": "N/A", "value": None, "sample_size": 0, "is_na": True}
        daily_trends = {"labels": [], "gross_compliance": [], "punctuality": []}
        try:
            metrics_payload = self.env["transport.metrics.service"].get_dashboard_metrics(
                {"source_type": "combined"}
            )
            kpis_map = metrics_payload.get("kpis") or {}
            if "MT-01" in kpis_map:
                mt01 = kpis_map["MT-01"]
            if "MT-02" in kpis_map:
                mt02 = kpis_map["MT-02"]
            charts_map = metrics_payload.get("charts") or {}
            if charts_map.get("daily_trends"):
                daily_trends = charts_map["daily_trends"]
        except Exception:
            _logger.exception("Admin home metrics lookup fallback to N/A")

        # Live fleet positions for the protagonist Leaflet map & vehicle panel
        live_vehicles = []
        try:
            live_vehicles = Vehicle.get_live_fleet_positions()
        except Exception:
            _logger.exception("Admin home live fleet positions fallback")

        state_labels = dict(self._fields["state"].selection)
        inc_type_labels = dict(Incident._fields["incident_type"].selection)
        inc_sev_labels = dict(Incident._fields["severity"].selection)
        inc_state_labels = dict(Incident._fields["state"].selection)

        days_es = [
            "Lunes", "Martes", "Miércoles", "Jueves",
            "Viernes", "Sábado", "Domingo",
        ]
        months_es = [
            "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        ]
        date_label = (
            f"{days_es[now_ec.weekday()]}, {now_ec.day} de "
            f"{months_es[now_ec.month]} de {now_ec.year}"
        )

        routes_payload = []
        for rt in active_routes[:8]:
            active_ver = rt.version_ids.filtered(lambda v: v.state == "approved")[:1]
            if not active_ver:
                active_ver = rt.version_ids[:1]
            routes_payload.append({
                "id": rt.id,
                "code": rt.code or "",
                "name": rt.name,
                "origin_name": rt.origin_name or "",
                "destination_name": rt.destination_name or "",
                "stop_count": len(active_ver.stop_ids) if active_ver else 0,
            })

        return {
            "user_name": user.name,
            "local_date_label": date_label,
            "local_time_label": now_ec.strftime("%H:%M ECT"),
            "stats": {
                "vehicles_total": len(all_vehicles),
                "vehicles_tracked": len(tracked_vehicles),
                "vehicles_online": len(online_vehicles),
                "vehicles_stale": len(stale_vehicles),
                "vehicles_offline": len(offline_vehicles),
                "vehicles_simulated": len(simulated_vehicles),
                "routes_active": len(active_routes),
                "stops_total": stops_total,
                "trips_today": len(trips_today),
                "trips_active": len(active_trips),
                "incidents_open": len(open_incidents),
                "incidents_critical": len(critical_incidents),
                "positions_total": total_positions,
            },
            "kpis": {
                "mt01": {
                    "display_value": mt01.get("display_value", "N/A"),
                    "value": mt01.get("value"),
                    "sample_size": mt01.get("sample_size", 0),
                    "is_na": bool(mt01.get("is_na", True)),
                },
                "mt02": {
                    "display_value": mt02.get("display_value", "N/A"),
                    "value": mt02.get("value"),
                    "sample_size": mt02.get("sample_size", 0),
                    "is_na": bool(mt02.get("is_na", True)),
                },
            },
            "daily_trends": daily_trends,
            "live_vehicles": live_vehicles,
            "routes": routes_payload,
            "traccar": {
                "last_fix_local": (
                    _fmt_ec(last_pos.fix_time) if last_pos else "Sin registros"
                ),
                "online_ratio": (
                    f"{len(online_vehicles)} / {len(tracked_vehicles)}"
                    if tracked_vehicles
                    else "0 / 0"
                ),
                "has_signal": bool(online_vehicles),
            },
            "recent_trips": [
                {
                    "id": t.id,
                    "name": t.name,
                    "route_name": t.route_id.name if t.route_id else "Sin ruta",
                    "route_code": t.route_id.code if t.route_id else "",
                    "vehicle_name": t.vehicle_id.name if t.vehicle_id else "Sin vehículo",
                    "driver_name": (
                        t.driver_user_id.name
                        if t.driver_user_id
                        else (t.driver_id.name if t.driver_id else "Sin conductor")
                    ),
                    "scheduled_start_local": _fmt_ec(t.scheduled_start_utc),
                    "state": t.state,
                    "state_label": state_labels.get(t.state, t.state),
                    "source_type": t.source_type,
                    "position_count": t.position_count,
                }
                for t in recent_trips
            ],
            "recent_incidents": [
                {
                    "id": inc.id,
                    "name": inc.name,
                    "trip_name": inc.trip_id.name if inc.trip_id else "Sin recorrido",
                    "incident_type_label": inc_type_labels.get(
                        inc.incident_type, inc.incident_type
                    ),
                    "severity": inc.severity,
                    "severity_label": inc_sev_labels.get(inc.severity, inc.severity),
                    "state": inc.state,
                    "state_label": inc_state_labels.get(inc.state, inc.state),
                    "is_open": inc.state in ("pending", "reported", "under_review"),
                    "timestamp_local": _fmt_ec(inc.timestamp_utc),
                }
                for inc in recent_incidents
            ],
        }

    @api.model
    def action_admin_sync_traccar(self):
        """Trigger fleet-wide Traccar GPS sync for transport managers."""
        if not (
            self.env.user.has_group("base.group_system")
            or self.env.user.has_group("uta_transport_monitor.group_transport_manager")
        ):
            raise UserError("Solo los administradores de transporte pueden sincronizar la flota.")
        tracked = self.env["fleet.vehicle"].search(
            [("active", "=", True), ("gps_tracking_enabled", "=", True)]
        )
        synced = 0
        errors = []
        for vehicle in tracked:
            try:
                vehicle.action_sync_gps_positions()
                synced += 1
            except Exception as exc:
                errors.append(f"{vehicle.name}: {exc}")
        return {
            "tracked_count": len(tracked),
            "synced_count": synced,
            "error_count": len(errors),
            "errors": errors[:3],
        }

    def get_map_data(self):
        """Return structured GeoJSON and telemetry payload for Leaflet map."""
        self.ensure_one()
        ref_polyline = []
        if self.route_version_id and self.route_version_id.reference_polyline:
            try:
                data = json.loads(self.route_version_id.reference_polyline)
                raw_coords = (
                    data.get("coordinates")
                    if isinstance(data, dict)
                    and data.get("type") == "LineString"
                    else data
                )
                if isinstance(raw_coords, list):
                    for pt in raw_coords:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            ref_polyline.append([pt[1], pt[0]])
            except Exception:
                ref_polyline = []

        stops_data = []
        for stop in self.stop_visit_ids.sorted(key=lambda s: s.sequence):
            stops_data.append({
                "id": stop.id,
                "name": stop.stop_name,
                "sequence": stop.sequence,
                "stop_type": stop.stop_type,
                "latitude": stop.latitude,
                "longitude": stop.longitude,
                "radius_m": stop.radius_m,
                "required": stop.required,
                "scheduled_at": (
                    stop.scheduled_at_utc.strftime("%Y-%m-%d %H:%M:%S")
                    if stop.scheduled_at_utc
                    else ""
                ),
                "status": stop.status,
            })

        positions_data = []
        latest_pos = None
        for pos in self.position_ids.sorted(key=lambda p: (p.fix_time, p.id)):
            pt_dict = {
                "id": pos.id,
                "latitude": pos.latitude,
                "longitude": pos.longitude,
                "speed": pos.speed,
                "altitude": pos.altitude,
                "accuracy": pos.accuracy,
                "fix_time_utc": pos.fix_time.strftime("%Y-%m-%d %H:%M:%S"),
                "fix_time_local": pos.fix_time_local or "",
                "source": pos.source,
                "is_valid": pos.is_valid,
            }
            positions_data.append(pt_dict)
            latest_pos = pt_dict

        return {
            "trip_id": self.id,
            "name": self.name,
            "state": self.state,
            "source_type": self.source_type,
            "vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "vehicle_name": self.vehicle_id.name if self.vehicle_id else "",
            "vehicle_plate": (
                self.vehicle_id.license_plate if self.vehicle_id else ""
            ),
            "driver_name": (
                self.driver_id.name if self.driver_id else "Sin conductor"
            ),
            "route_name": self.route_id.name if self.route_id else "",
            "route_code": self.route_id.code if self.route_id else "",
            "scheduled_start": (
                self.scheduled_start_utc.strftime("%Y-%m-%d %H:%M:%S")
                if self.scheduled_start_utc
                else ""
            ),
            "scheduled_end": (
                self.scheduled_end_utc.strftime("%Y-%m-%d %H:%M:%S")
                if self.scheduled_end_utc
                else ""
            ),
            "reference_polyline": ref_polyline,
            "stops": stops_data,
            "positions": positions_data,
            "position_count": len(positions_data),
            "latest_position": latest_pos,
            "freshness": (
                self.vehicle_id.gps_freshness_state
                if self.vehicle_id
                else "no_data"
            ),
            "is_physical_accredited": (
                self.vehicle_id.is_physical_accredited
                if self.vehicle_id
                else False
            ),
        }
