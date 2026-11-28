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
        string="Parada de referencia",
        ondelete="set null",
    )
    sequence = fields.Integer(
        string="Secuencia",
        required=True,
    )
    stop_name = fields.Char(
        string="Nombre del control / parada",
        required=True,
    )
    stop_type = fields.Selection(
        selection=[
            ("origin", "Punto de origen / salida"),
            ("checkpoint", "Control intermedio"),
            ("destination", "Punto de destino / llegada"),
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
        string="Latitud prevista",
        digits=(10, 6),
    )
    longitude = fields.Float(
        string="Longitud prevista",
        digits=(10, 6),
    )
    radius_m = fields.Float(
        string="Radio de geocerca (m)",
        default=30.0,
    )
    scheduled_at_utc = fields.Datetime(
        string="Hora prevista de paso",
        help="Hora programada de paso por este punto (almacenada en UTC, mostrada en hora local).",
    )
    first_arrival_utc = fields.Datetime(
        string="Primer arribo validado",
        help="Primer instante verificado de llegada dentro del radio de geocerca.",
    )
    departure_utc = fields.Datetime(
        string="Salida validada",
        help="Instante verificado de salida del radio de geocerca.",
    )
    status = fields.Selection(
        selection=[
            ("pending", "Pendiente de ejecución"),
            ("on_time", "Visitada puntual"),
            ("late", "Visitada con retraso"),
            ("missed", "Omitida"),
            ("not_determinable", "No determinable / sin evidencia"),
            ("indeterminate", "Indeterminada / evidencia insuficiente"),
        ],
        string="Estado de cumplimiento",
        default="pending",
        required=True,
        index=True,
    )
    delay_s = fields.Integer(
        string="Retraso observado (s)",
        help="Segundos de retraso respecto a la hora programada (0 si llegó a tiempo).",
    )
    min_distance_m = fields.Float(
        string="Distancia mínima al punto (m)",
        digits=(8, 2),
    )
    notes = fields.Text(
        string="Observaciones / evidencia",
    )
