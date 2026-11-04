"""Operational trip scheduling and lifecycle management model for GeoRutex."""

from datetime import datetime, timedelta
import json
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .transport_route_version import format_duration_spanish


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
        tracking=True,
        help="Habilita a un gestor autorizado a modificar la hora final independientemente de la duración estándar de la ruta.",
    )
    manual_duration_override_reason = fields.Text(
        string="Justificación del Ajuste Excepcional",
        tracking=True,
        help="Justificación operativa obligatoria para el ajuste manual del horario.",
    )
    manual_duration_override_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Ajuste Autorizado Por",
        readonly=True,
        tracking=True,
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
