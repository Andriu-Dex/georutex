"""Stop visit evaluation and scheduling records for GeoRutex trips."""

from odoo import fields, models


class TransportStopVisit(models.Model):
    """Presence and punctuality at a checkpoint for a trip."""

    _name = "transport.stop.visit"
    _description = "Visita y Cumplimiento de Parada por Recorrido"
    _order = "trip_id asc, sequence asc, id asc"

    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido",
        required=True,
        ondelete="cascade",
        index=True,
    )
    route_stop_id = fields.Many2one(
        comodel_name="transport.route.stop",
        string="Parada de Referencia",
        ondelete="set null",
    )
    sequence = fields.Integer(
        string="Secuencia",
        required=True,
    )
    stop_name = fields.Char(
        string="Nombre del Control / Parada",
        required=True,
    )
    stop_type = fields.Selection(
        selection=[
            ("origin", "Punto de Origen / Salida"),
            ("checkpoint", "Control Intermedio"),
            ("destination", "Punto de Destino / Llegada"),
        ],
        string="Tipo",
        default="checkpoint",
        required=True,
    )
    required = fields.Boolean(
        string="Obligatoria",
        default=True,
    )
    latitude = fields.Float(
        string="Latitud Prevista",
        digits=(10, 6),
    )
    longitude = fields.Float(
        string="Longitud Prevista",
        digits=(10, 6),
    )
    radius_m = fields.Float(
        string="Radio de Geocerca (m)",
        default=30.0,
    )
    scheduled_at_utc = fields.Datetime(
        string="Hora Prevista de Paso (UTC)",
    )
    first_arrival_utc = fields.Datetime(
        string="Primer Arribo Validado (UTC)",
    )
    departure_utc = fields.Datetime(
        string="Salida Validada (UTC)",
    )
    status = fields.Selection(
        selection=[
            ("pending", "Pendiente de Ejecución"),
            ("on_time", "Visitada Puntual"),
            ("late", "Visitada con Retraso"),
            ("missed", "Omitida"),
            ("not_determinable", "No Determinable / Sin Evidencia"),
        ],
        string="Estado de Cumplimiento",
        default="pending",
        required=True,
        index=True,
    )
    delay_s = fields.Integer(
        string="Retraso Observado (s)",
        help="Retraso observado en segundos: max(0, t_real - t_prog).",
    )
    min_distance_m = fields.Float(
        string="Distancia Mínima al Punto (m)",
        digits=(8, 2),
    )
    notes = fields.Text(
        string="Observaciones / Evidencia",
    )
