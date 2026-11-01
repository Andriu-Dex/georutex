"""Operational trip scheduling and lifecycle management model for GeoRutex."""

from datetime import timedelta
import json
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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

    # Scheduled timestamps and distance (stored in UTC)
    scheduled_start_utc = fields.Datetime(
        string="Inicio Programado (UTC)",
        required=True,
        index=True,
    )
    scheduled_end_utc = fields.Datetime(
        string="Fin Programado (UTC)",
        required=True,
        index=True,
    )
    scheduled_distance_m = fields.Float(
        string="Distancia Programada (m)",
        digits=(10, 2),
    )

    # Actual observed timestamps and distance
    actual_start_utc = fields.Datetime(
        string="Inicio Real (UTC)",
        readonly=True,
        help="Primer instante verificado de salida de origen (RF-20).",
    )
    actual_end_utc = fields.Datetime(
        string="Fin Real (UTC)",
        readonly=True,
        help="Primer instante verificado de llegada a destino (RF-20).",
    )
    actual_distance_m = fields.Float(
        string="Distancia Real Recorrida (m)",
        digits=(10, 2),
        readonly=True,
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

    def _compute_position_count(self):
        for trip in self:
            trip.position_count = len(trip.position_ids)

    def _compute_stop_visit_count(self):
        for trip in self:
            trip.stop_visit_count = len(trip.stop_visit_ids)

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

    @api.constrains("scheduled_start_utc", "scheduled_end_utc")
    def _check_scheduled_times(self):
        for trip in self:
            if trip.scheduled_start_utc and trip.scheduled_end_utc:
                if trip.scheduled_start_utc >= trip.scheduled_end_utc:
                    raise ValidationError(
                        "El inicio programado debe ser estrictamente "
                        "anterior al fin programado."
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
        for stop in self.route_version_id.stop_ids:
            sched_time = False
            if self.scheduled_start_utc and stop.planned_offset_seconds:
                sched_time = self.scheduled_start_utc + timedelta(
                    seconds=stop.planned_offset_seconds
                )
            elif self.scheduled_start_utc and stop.stop_type == "origin":
                sched_time = self.scheduled_start_utc
            elif self.scheduled_end_utc and stop.stop_type == "destination":
                sched_time = self.scheduled_end_utc

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
            vals = {"state": "in_progress"}
            if not trip.actual_start_utc:
                vals["actual_start_utc"] = fields.Datetime.now()
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
            vals = {"state": "completed"}
            if not trip.actual_end_utc:
                vals["actual_end_utc"] = fields.Datetime.now()
            trip.write(vals)
        return True

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
