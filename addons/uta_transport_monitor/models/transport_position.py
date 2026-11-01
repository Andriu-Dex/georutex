"""Model for storing raw GPS telemetries from Traccar or simulated fixtures."""

from odoo import fields, models


class TransportVehiclePosition(models.Model):
    """Historical vehicle positions received from GPS tracker."""

    _name = "transport.vehicle.position"
    _description = "Posición GPS de Vehículo"
    _order = "fix_time desc, id desc"

    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
        store=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Vehículo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    traccar_device_id = fields.Integer(
        string="ID Dispositivo Traccar",
        index=True,
    )
    traccar_position_id = fields.Integer(
        string="ID Posición Traccar",
        index=True,
    )
    fix_time = fields.Datetime(
        string="Hora GPS (UTC)",
        required=True,
        index=True,
    )
    server_time = fields.Datetime(
        string="Hora Servidor (UTC)",
    )
    latitude = fields.Float(
        string="Latitud",
        digits=(10, 6),
        required=True,
    )
    longitude = fields.Float(
        string="Longitud",
        digits=(10, 6),
        required=True,
    )
    speed = fields.Float(
        string="Velocidad (km/h)",
        digits=(6, 2),
    )
    altitude = fields.Float(
        string="Altitud (m)",
        digits=(6, 2),
    )
    is_valid = fields.Boolean(
        string="Posición Válida",
        default=True,
    )
    source = fields.Selection(
        selection=[
            ("real", "Datos Reales / GPS"),
            ("simulated", "Simulado"),
        ],
        string="Origen de Datos",
        default="real",
        required=True,
        index=True,
    )
    protocol = fields.Char(
        string="Protocolo",
        default="osmand",
    )

    _sql_constraints = [
        (
            "unique_device_fix_time",
            "unique(traccar_device_id, fix_time)",
            "La posición para este dispositivo y hora ya existe.",
        )
    ]

    def _compute_name(self):
        for rec in self:
            v_name = rec.vehicle_id.name if rec.vehicle_id else "S/V"
            fix = (
                rec.fix_time.strftime("%Y-%m-%d %H:%M:%S")
                if rec.fix_time
                else "-"
            )
            rec.name = f"{v_name} @ {fix}"
