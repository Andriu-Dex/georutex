"""Commercial transport route management model for GeoRutex."""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TransportRoute(models.Model):
    """Catalog of transport routes with origin, destination, and direction."""

    _name = "transport.route"
    _description = "Ruta de Transporte"
    _order = "name asc, id desc"

    name = fields.Char(
        string="Nombre de la Ruta",
        required=True,
        index=True,
        help="Nombre descriptivo de la ruta (ej. 'Ruta 1: Huachi').",
    )
    code = fields.Char(
        string="Código de Ruta",
        required=True,
        index=True,
        help="Código único de identificación operacional (ej. 'RUT-01-IDA').",
    )
    description = fields.Text(
        string="Descripción Operacional",
    )
    origin_name = fields.Char(
        string="Punto de Origen",
        required=True,
        help="Nombre de la cabecera u origen (ej. 'Campus Huachi').",
    )
    destination_name = fields.Char(
        string="Punto de Destino",
        required=True,
        help="Nombre del destino final (ej. 'Campus Ingahurco').",
    )
    direction = fields.Selection(
        selection=[
            ("outbound", "Ida"),
            ("inbound", "Vuelta"),
            ("circular", "Circular"),
            ("other", "Especial / Otro"),
        ],
        string="Sentido del Trayecto",
        default="outbound",
        required=True,
    )
    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    current_version_id = fields.Many2one(
        comodel_name="transport.route.version",
        string="Versión Vigente",
        domain="[('route_id', '=', id), ('state', '=', 'approved')]",
        help="Versión aprobada utilizada para programar nuevos recorridos.",
    )
    version_ids = fields.One2many(
        comodel_name="transport.route.version",
        inverse_name="route_id",
        string="Versiones de Ruta",
    )
    version_count = fields.Integer(
        string="Nº Versiones",
        compute="_compute_counts",
    )
    trip_ids = fields.One2many(
        comodel_name="transport.trip",
        inverse_name="route_id",
        string="Recorridos",
    )
    trip_count = fields.Integer(
        string="Nº Recorridos",
        compute="_compute_counts",
    )

    _sql_constraints = [
        (
            "unique_route_code",
            "unique(code)",
            "El código de la ruta debe ser único.",
        )
    ]

    def _compute_counts(self):
        for route in self:
            route.version_count = len(route.version_ids)
            route.trip_count = len(route.trip_ids)

    @api.constrains("origin_name", "destination_name", "direction")
    def _check_origin_destination(self):
        for route in self:
            if (
                route.origin_name
                and route.destination_name
                and route.origin_name.strip().lower()
                == route.destination_name.strip().lower()
                and route.direction != "circular"
            ):
                raise ValidationError(
                    "El origen y destino no pueden ser iguales salvo que el "
                    "sentido sea 'Circular'."
                )

    def action_view_versions(self):
        """View route versions associated with this route."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "uta_transport_monitor.action_transport_route_version"
        )
        action["domain"] = [("route_id", "=", self.id)]
        action["context"] = {"default_route_id": self.id}
        return action

    def action_view_trips(self):
        """View operational trips associated with this route."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "uta_transport_monitor.action_transport_trip"
        )
        action["domain"] = [("route_id", "=", self.id)]
        action["context"] = {"default_route_id": self.id}
        return action
