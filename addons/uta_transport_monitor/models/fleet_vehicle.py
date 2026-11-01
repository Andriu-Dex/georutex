"""Extension of Fleet vehicle model with GPS tracking capabilities."""

from datetime import timedelta, timezone
import secrets
import zoneinfo
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class FleetVehicle(models.Model):
    """Extend fleet.vehicle with Traccar device bindings and telemetries."""

    _inherit = "fleet.vehicle"

    traccar_device_id = fields.Integer(
        string="ID Dispositivo Traccar",
        index=True,
        help="ID numérico asignado al dispositivo en Traccar Server.",
    )
    traccar_unique_id = fields.Char(
        string="Identificador Único (uniqueId)",
        index=True,
        help="Código único o identificador de Traccar Client (OsmAnd / IMEI).",
    )
    gps_tracking_enabled = fields.Boolean(
        string="Rastreo GPS Activo",
        default=True,
        help="Habilita sincronización programada de telemetría para el bus.",
    )
    is_simulated = fields.Boolean(
        string="Vehículo de Simulación",
        default=False,
        help="Si está activo, las telemetrías se marcan como simuladas.",
    )
    is_physical_accredited = fields.Boolean(
        string="Origen Físico Acreditado",
        default=False,
        help="Acredita formalmente que este vehículo cuenta con validación "
             "de hardware físico o transmisión móvil certificada.",
    )
    trip_ids = fields.One2many(
        comodel_name="transport.trip",
        inverse_name="vehicle_id",
        string="Recorridos",
    )
    trip_count = fields.Integer(
        string="Nº Recorridos",
        compute="_compute_trip_count",
    )
    gps_connection_status = fields.Selection(
        selection=[
            ("online", "En línea (< 5 min)"),
            ("recent", "Reciente (< 1 hora)"),
            ("offline", "Sin señal (> 1 hora)"),
            ("unlinked", "No vinculado"),
        ],
        string="Estado de Conexión GPS",
        compute="_compute_gps_status",
        store=False,
    )
    gps_freshness_state = fields.Selection(
        selection=[
            ("fresh", "En vivo (< 3 min)"),
            ("stale", "Sin reporte reciente (3-15 min)"),
            ("offline", "Sin señal (> 15 min)"),
            ("no_data", "Sin posiciones registradas"),
            ("unlinked", "No vinculado"),
        ],
        string="Frescura de Señal GPS",
        compute="_compute_gps_status",
        store=False,
    )
    last_gps_age_seconds = fields.Integer(
        string="Antigüedad GPS (segundos)",
        compute="_compute_gps_status",
    )
    last_gps_time_local = fields.Char(
        string="Última Hora GPS (Ecuador)",
        compute="_compute_last_gps_time_local",
    )
    last_gps_fix_time = fields.Datetime(
        string="Última Posición GPS (UTC)",
        readonly=True,
    )
    last_gps_latitude = fields.Float(
        string="Última Latitud",
        digits=(10, 6),
        readonly=True,
    )
    last_gps_longitude = fields.Float(
        string="Última Longitud",
        digits=(10, 6),
        readonly=True,
    )
    last_gps_speed = fields.Float(
        string="Última Velocidad (km/h)",
        digits=(6, 2),
        readonly=True,
    )
    position_ids = fields.One2many(
        comodel_name="transport.vehicle.position",
        inverse_name="vehicle_id",
        string="Historial de Posiciones",
    )
    position_count = fields.Integer(
        string="Nº de Posiciones",
        compute="_compute_position_count",
    )

    def _compute_position_count(self):
        for vehicle in self:
            vehicle.position_count = len(vehicle.position_ids)

    def _compute_trip_count(self):
        for vehicle in self:
            vehicle.trip_count = len(vehicle.trip_ids)

    @api.constrains("traccar_device_id", "traccar_unique_id", "active")
    def _check_traccar_device_uniqueness(self):
        """Enforce RF-08: No two active vehicles can share device bindings."""
        for vehicle in self:
            if not vehicle.active:
                continue
            if vehicle.traccar_device_id:
                clashing = self.search([
                    ("id", "!=", vehicle.id),
                    ("active", "=", True),
                    ("traccar_device_id", "=", vehicle.traccar_device_id),
                ], limit=1)
                if clashing:
                    raise ValidationError(
                        f"El ID Traccar {vehicle.traccar_device_id} ya está "
                        f"asignado a '{clashing.name}' (RF-08)."
                    )
            if vehicle.traccar_unique_id:
                clashing = self.search([
                    ("id", "!=", vehicle.id),
                    ("active", "=", True),
                    ("traccar_unique_id", "=", vehicle.traccar_unique_id),
                ], limit=1)
                if clashing:
                    raise ValidationError(
                        f"El identificador '{vehicle.traccar_unique_id}' "
                        f"ya está asignado a '{clashing.name}' (RF-08)."
                    )

    @api.depends("last_gps_fix_time", "traccar_device_id", "traccar_unique_id")
    def _compute_gps_status(self):
        now = fields.Datetime.now()
        for vehicle in self:
            if not vehicle.traccar_device_id and not vehicle.traccar_unique_id:
                vehicle.gps_connection_status = "unlinked"
                vehicle.gps_freshness_state = "unlinked"
                vehicle.last_gps_age_seconds = 0
            elif not vehicle.last_gps_fix_time:
                vehicle.gps_connection_status = "offline"
                vehicle.gps_freshness_state = "no_data"
                vehicle.last_gps_age_seconds = 0
            else:
                elapsed = now - vehicle.last_gps_fix_time
                age_secs = int(elapsed.total_seconds())
                vehicle.last_gps_age_seconds = max(0, age_secs)
                if elapsed <= timedelta(minutes=5):
                    vehicle.gps_connection_status = "online"
                elif elapsed <= timedelta(hours=1):
                    vehicle.gps_connection_status = "recent"
                else:
                    vehicle.gps_connection_status = "offline"

                # RF-06: Freshness evaluation against gap threshold (180s)
                if age_secs <= 180:
                    vehicle.gps_freshness_state = "fresh"
                elif age_secs <= 900:
                    vehicle.gps_freshness_state = "stale"
                else:
                    vehicle.gps_freshness_state = "offline"

    @api.depends("last_gps_fix_time")
    def _compute_last_gps_time_local(self):
        tz_guayaquil = zoneinfo.ZoneInfo("America/Guayaquil")
        for vehicle in self:
            if vehicle.last_gps_fix_time:
                utc_aware = vehicle.last_gps_fix_time.replace(
                    tzinfo=timezone.utc
                )
                local_dt = utc_aware.astimezone(tz_guayaquil)
                vehicle.last_gps_time_local = local_dt.strftime(
                    "%Y-%m-%d %H:%M:%S ECT"
                )
            else:
                vehicle.last_gps_time_local = "Sin registro"

    def action_generate_secure_unique_id(self):
        """Generate non-predictable uniqueId with 128-bit entropy (RF-08)."""
        for vehicle in self:
            token = secrets.token_hex(16).upper()
            vehicle.traccar_unique_id = f"UTA-BUS-{token}"

    @api.model
    def get_live_fleet_positions(self):
        """Return live telemetry for tracked vehicles (RF-15, RF-16)."""
        user = self.env.user
        is_manager_or_analyst = (
            user.has_group("uta_transport_monitor.group_transport_manager")
            or user.has_group("uta_transport_monitor.group_transport_analyst")
        )

        domain = [
            ("gps_tracking_enabled", "=", True),
            ("active", "=", True),
        ]
        if not is_manager_or_analyst:
            if user.partner_id:
                domain = [
                    "&",
                    ("gps_tracking_enabled", "=", True),
                    "|",
                    ("driver_id", "=", user.partner_id.id),
                    ("trip_ids.driver_id", "=", user.partner_id.id),
                ]
            else:
                return []

        vehicles = self.sudo().search(domain)
        results = []
        for v in vehicles:
            results.append({
                "vehicle_id": v.id,
                "name": v.name,
                "license_plate": v.license_plate or "",
                "driver_name": (
                    v.driver_id.name if v.driver_id else "Sin conductor"
                ),
                "latitude": v.last_gps_latitude or 0.0,
                "longitude": v.last_gps_longitude or 0.0,
                "speed": v.last_gps_speed or 0.0,
                "fix_time_utc": (
                    v.last_gps_fix_time.strftime("%Y-%m-%d %H:%M:%S")
                    if v.last_gps_fix_time
                    else None
                ),
                "fix_time_local": v.last_gps_time_local or "Sin datos",
                "freshness": v.gps_freshness_state or "no_data",
                "age_seconds": v.last_gps_age_seconds or 0,
                "is_simulated": v.is_simulated,
                "is_physical_accredited": v.is_physical_accredited,
                "has_coordinates": bool(
                    v.last_gps_latitude and v.last_gps_longitude
                ),
            })
        return results

    def get_vehicle_live_map_data(self):
        """Return map telemetry and recent history points for this vehicle."""
        self.ensure_one()
        user = self.env.user
        is_manager_or_analyst = (
            user.has_group("uta_transport_monitor.group_transport_manager")
            or user.has_group("uta_transport_monitor.group_transport_analyst")
        )
        if not is_manager_or_analyst:
            is_own_vehicle = (
                self.driver_id == user.partner_id
                or self.env["transport.trip"].search_count([
                    ("vehicle_id", "=", self.id),
                    "|",
                    ("driver_user_id", "=", user.id),
                    ("driver_id", "=", user.partner_id.id),
                ]) > 0
            )
            if not is_own_vehicle:
                raise AccessError(
                    "No tiene permisos para consultar la telemetría "
                    "de este vehículo."
                )

        recent_positions = self.env["transport.vehicle.position"].search([
            ("vehicle_id", "=", self.id),
        ], order="fix_time desc", limit=50)

        history_trail = []
        for p in reversed(recent_positions):
            history_trail.append({
                "id": p.id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "speed": p.speed,
                "fix_time_utc": p.fix_time.strftime("%Y-%m-%d %H:%M:%S"),
                "fix_time_local": p.fix_time_local,
                "source": p.source,
                "is_valid": p.is_valid,
            })

        return {
            "vehicle_id": self.id,
            "name": self.name,
            "license_plate": self.license_plate or "",
            "driver_name": (
                self.driver_id.name if self.driver_id else "Sin conductor"
            ),
            "latitude": self.last_gps_latitude or 0.0,
            "longitude": self.last_gps_longitude or 0.0,
            "speed": self.last_gps_speed or 0.0,
            "fix_time_utc": (
                self.last_gps_fix_time.strftime("%Y-%m-%d %H:%M:%S")
                if self.last_gps_fix_time
                else None
            ),
            "fix_time_local": self.last_gps_time_local or "Sin datos",
            "freshness": self.gps_freshness_state or "no_data",
            "age_seconds": self.last_gps_age_seconds or 0,
            "is_simulated": self.is_simulated,
            "is_physical_accredited": self.is_physical_accredited,
            "history_trail": history_trail,
        }

    def action_test_traccar_connection(self):
        """Test API connectivity and confirm bound device existence."""
        self.ensure_one()
        sync_service = self.env["transport.gps.sync.service"]
        client = sync_service._get_traccar_client()
        try:
            server_info = client.test_connection()
            version = server_info.get("version", "Desconocida")
            device_msg = ""
            if self.traccar_device_id:
                try:
                    device = client.get_device(self.traccar_device_id)
                    dev_name = device.get("name")
                    device_msg = f" Dispositivo '{dev_name}' verificado."
                except Exception as exc:
                    device_msg = (
                        f" Alerta: Dispositivo {self.traccar_device_id} "
                        f"no encontrado: {exc}"
                    )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Conexión Exitosa con Traccar",
                    "message": (
                        f"Servidor Traccar v{version} responde.{device_msg}"
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }
        except Exception as exc:
            raise UserError(f"Error de conexión con Traccar: {exc}")

    def action_sync_gps_positions(self):
        """Trigger an on-demand GPS synchronization for this vehicle."""
        self.ensure_one()
        sync_service = self.env["transport.gps.sync.service"]
        count = sync_service.sync_vehicle_positions(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sincronización GPS Completa",
                "message": (
                    f"Se sincronizaron {count} nuevas posiciones para "
                    f"{self.name}."
                ),
                "type": "info",
                "sticky": False,
            },
        }

    def action_view_positions(self):
        """Open the list of GPS positions associated with this vehicle."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "uta_transport_monitor.action_transport_vehicle_position"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        return action

    def action_view_trips(self):
        """Open the list of operational trips associated with this vehicle."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "uta_transport_monitor.action_transport_trip"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
