"""Checkpoint and stop definition model for route versions in GeoRutex."""

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from ..domain.geo import is_valid_coordinate


class TransportRouteStop(models.Model):
    """Geographic checkpoint or bus stop belonging to a route version."""

    _name = "transport.route.stop"
    _description = "Punto de Control / Parada de Ruta"
    _order = "route_version_id asc, sequence asc, id asc"

    route_version_id = fields.Many2one(
        comodel_name="transport.route.version",
        string="Versión de Ruta",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Secuencia",
        default=10,
        required=True,
        help="Orden secuencial obligatorio de paso por este control.",
    )
    name = fields.Char(
        string="Nombre del Control / Parada",
        required=True,
        help="Nombre identificativo de la parada (ej. 'Parada 1').",
    )
    latitude = fields.Float(
        string="Latitud",
        digits=(10, 6),
        required=True,
        help="Latitud geográfica en formato WGS84 decimal [-90, 90].",
    )
    longitude = fields.Float(
        string="Longitud",
        digits=(10, 6),
        required=True,
        help="Longitud geográfica en formato WGS84 decimal [-180, 180].",
    )
    radius_m = fields.Float(
        string="Radio de Proximidad (m)",
        default=30.0,
        required=True,
        help="Radio de geocerca en metros para registrar presencia o visita.",
    )
    required = fields.Boolean(
        string="Obligatoria",
        default=True,
        help="Si está marcado, omitir este punto cuenta como incumplimiento.",
    )
    stop_type = fields.Selection(
        selection=[
            ("origin", "Punto de Origen / Salida"),
            ("checkpoint", "Control Intermedio"),
            ("destination", "Punto de Destino / Llegada"),
        ],
        string="Tipo de Control",
        default="checkpoint",
        required=True,
    )
    planned_offset_seconds = fields.Integer(
        string="Tiempo Programado de Arribo (s)",
        default=0,
        help="Segundos estimados desde la salida del viaje hasta este punto.",
    )
    notes = fields.Text(
        string="Notas / Referencias",
    )

    _sql_constraints = [
        (
            "unique_version_sequence",
            "unique(route_version_id, sequence)",
            "No puede haber dos puntos con la misma secuencia en la ruta.",
        )
    ]

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for stop in self:
            if not is_valid_coordinate(stop.latitude, stop.longitude):
                raise ValidationError(
                    f"Coordenadas inválidas para '{stop.name}': "
                    f"({stop.latitude}, {stop.longitude}). "
                    f"Deben estar en WGS84: lat [-90, 90], lon [-180, 180]."
                )

    @api.constrains("radius_m", "planned_offset_seconds")
    def _check_parameters(self):
        for stop in self:
            if stop.radius_m <= 0:
                raise ValidationError(
                    f"El radio de proximidad de '{stop.name}' debe ser > 0 m."
                )
            if stop.planned_offset_seconds < 0:
                raise ValidationError(
                    f"El tiempo programado de '{stop.name}' no puede ser < 0."
                )

    @api.model_create_multi
    def create(self, vals_list):
        versions_to_classify = set()
        is_install = (
            self.env.context.get("install_mode")
            or self.env.context.get("import_compat")
        )
        for vals in vals_list:
            v_id = vals.get("route_version_id")
            if v_id:
                version = self.env["transport.route.version"].browse(v_id)
                if (
                    version.state == "approved"
                    and (version.trip_count > 0 or version.approved_at)
                    and not is_install
                ):
                    raise UserError(
                        "No se pueden agregar paradas a una versión aprobada. "
                        "Cree una nueva versión (RF-14)."
                    )
                if version.state == "draft":
                    versions_to_classify.add(version)

        records = super().create(vals_list)

        if not self.env.context.get("skip_auto_classify") and not is_install:
            for ver in versions_to_classify:
                ver.with_context(skip_auto_classify=True).auto_classify_stops()

        return records

    def write(self, vals):
        is_install = (
            self.env.context.get("install_mode")
            or self.env.context.get("import_compat")
            or self.env.context.get("skip_auto_classify")
        )
        for stop in self:
            ver = stop.route_version_id
            if (
                ver.state == "approved"
                and (ver.trip_count > 0 or ver.approved_at)
                and not is_install
            ):
                raise UserError(
                    "No se pueden modificar paradas de una versión aprobada. "
                    "Cree una nueva versión (RF-14)."
                )

        res = super().write(vals)

        # If sequence changed (reordered), auto-update stop classifications
        if "sequence" in vals and not is_install:
            versions = self.mapped("route_version_id").filtered(
                lambda v: v.state == "draft"
            )
            for ver in versions:
                ver.with_context(skip_auto_classify=True).auto_classify_stops()

        return res

    def unlink(self):
        is_install = (
            self.env.context.get("install_mode")
            or self.env.context.get("import_compat")
        )
        versions_to_classify = set()
        for stop in self:
            ver = stop.route_version_id
            if (
                ver.state == "approved"
                and (ver.trip_count > 0 or ver.approved_at)
                and not is_install
            ):
                raise UserError(
                    "No se pueden eliminar paradas de una versión aprobada. "
                    "Cree una nueva versión (RF-14)."
                )
            if ver.state == "draft":
                versions_to_classify.add(ver)

        res = super().unlink()

        if not self.env.context.get("skip_auto_classify") and not is_install:
            for ver in versions_to_classify:
                if ver.exists():
                    ver.with_context(skip_auto_classify=True).auto_classify_stops()

        return res
