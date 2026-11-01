"""Extension of Fleet vehicle model with GPS tracking capabilities."""

from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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
        store=True,
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

    def _compute_gps_status(self):
        now = fields.Datetime.now()
        for vehicle in self:
            if not vehicle.traccar_device_id and not vehicle.traccar_unique_id:
                vehicle.gps_connection_status = "unlinked"
            elif not vehicle.last_gps_fix_time:
                vehicle.gps_connection_status = "offline"
            else:
                elapsed = now - vehicle.last_gps_fix_time
                if elapsed <= timedelta(minutes=5):
                    vehicle.gps_connection_status = "online"
                elif elapsed <= timedelta(hours=1):
                    vehicle.gps_connection_status = "recent"
                else:
                    vehicle.gps_connection_status = "offline"

    def action_generate_secure_unique_id(self):
        """Generate non-predictable uniqueId with 64-bit entropy."""
        import secrets
        for vehicle in self:
            token = secrets.token_hex(8).upper()
            vehicle.traccar_unique_id = f"UTA-BUS-{token}"

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
