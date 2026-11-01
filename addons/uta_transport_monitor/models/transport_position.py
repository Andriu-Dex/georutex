"""Model for storing raw GPS telemetries from Traccar or simulated fixtures."""

from datetime import timezone
import zoneinfo
from odoo import api, fields, models


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
    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido Asignado",
        ondelete="set null",
        index=True,
        help="Recorrido operacional al que se vincula esta posición.",
    )
    association_status = fields.Selection(
        selection=[
            ("unassigned", "Sin Asignar"),
            ("associated", "Asociado"),
            ("ambiguous", "Ambiguo / En Conflicto"),
        ],
        string="Estado de Asociación",
        default="unassigned",
        required=True,
        index=True,
        help="Trazabilidad sobre la asignación del punto al recorrido.",
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
    fix_time_local = fields.Char(
        string="Hora Local (Ecuador)",
        compute="_compute_fix_time_local",
        store=False,
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
    accuracy = fields.Float(
        string="Precisión (m)",
        digits=(6, 2),
        help="Incertidumbre horizontal HDOP/precisión estimada.",
    )
    heading = fields.Float(
        string="Rumbo (°)",
        digits=(5, 1),
    )
    is_valid = fields.Boolean(
        string="Posición Válida",
        default=True,
    )
    source = fields.Selection(
        selection=[
            ("real", "Datos Reales / GPS"),
            ("simulated", "Simulado"),
            ("unverified", "No Verificado"),
        ],
        string="Origen de Datos",
        default="unverified",
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

    @api.depends("fix_time")
    def _compute_fix_time_local(self):
        tz_guayaquil = zoneinfo.ZoneInfo("America/Guayaquil")
        for rec in self:
            if rec.fix_time:
                utc_aware = rec.fix_time.replace(tzinfo=timezone.utc)
                local_dt = utc_aware.astimezone(tz_guayaquil)
                rec.fix_time_local = local_dt.strftime("%Y-%m-%d %H:%M:%S ECT")
            else:
                rec.fix_time_local = ""

    def _compute_name(self):
        for rec in self:
            v_name = rec.vehicle_id.name if rec.vehicle_id else "S/V"
            fix = (
                rec.fix_time.strftime("%Y-%m-%d %H:%M:%S")
                if rec.fix_time
                else "-"
            )
            rec.name = f"{v_name} @ {fix}"
