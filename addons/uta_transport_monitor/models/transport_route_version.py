"""Route versioning and frozen operational parameters for GeoRutex."""

import json
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from ..domain.geo import calculate_polyline_distance


class TransportRouteVersion(models.Model):
    """Frozen geometric layout and operational tolerances for route."""

    _name = "transport.route.version"
    _description = "Versión de Ruta y Parámetros de Control"
    _order = "route_id asc, version_number desc"

    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
        store=True,
    )
    route_id = fields.Many2one(
        comodel_name="transport.route",
        string="Ruta",
        required=True,
        ondelete="cascade",
        index=True,
    )
    version_number = fields.Integer(
        string="Número de Versión",
        default=1,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Borrador"),
            ("approved", "Aprobada"),
            ("archived", "Archivada"),
        ],
        string="Estado",
        default="draft",
        required=True,
        index=True,
    )
    reference_polyline = fields.Text(
        string="Polilínea de Referencia (GeoJSON / Coordenadas)",
        help="Cadena JSON de coordenadas [[lon, lat], ...] o LineString.",
    )
    estimated_distance_m = fields.Float(
        string="Distancia Programada (m)",
        digits=(10, 2),
        help="Distancia geométrica estimada del recorrido en metros.",
    )

    # Canonical evaluation parameters (docs/requirements.md Section 7.1)
    stop_radius_m = fields.Float(
        string="Radio de Parada (m) [stop_radius_m]",
        default=30.0,
        required=True,
        help="Radio de proximidad para puntos de control.",
    )
    route_corridor_m = fields.Float(
        string="Ancho de Corredor (m) [route_corridor_m]",
        default=40.0,
        required=True,
        help="Semiancho máximo permitido alrededor de la polilínea.",
    )
    lateness_tolerance_s = fields.Integer(
        string="Tolerancia Retraso (s) [lateness_tolerance_s]",
        default=300,
        required=True,
        help="Segundos de tolerancia de puntualidad para paradas e inicio.",
    )
    gps_gap_threshold_s = fields.Integer(
        string="Umbral Gap GPS (s) [gps_gap_threshold_s]",
        default=180,
        required=True,
        help="Tiempo máximo admisible sin telemetría antes de registrar gap.",
    )
    minimum_consecutive_deviation_points = fields.Integer(
        string="Puntos Desvío Consecutivos",
        default=2,
        required=True,
        help="Muestras consecutivas fuera de corredor para confirmar desvío.",
    )
    minimum_deviation_duration_s = fields.Integer(
        string="Duración Mínima Desvío (s)",
        default=10,
        required=True,
        help="Duración mínima fuera del corredor para confirmar desvío.",
    )
    geo_accuracy_max_m = fields.Float(
        string="Precisión Máxima GPS (m)",
        default=100.0,
        required=True,
        help="Umbral de exactitud horizontal aceptable para desvíos.",
    )

    # Auditing and approvals
    approved_at = fields.Datetime(
        string="Fecha de Aprobación",
        readonly=True,
    )
    approved_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Aprobado Por",
        readonly=True,
    )
    active_for_new_trips = fields.Boolean(
        string="Habilitada para Nuevos Recorridos",
        default=False,
    )

    # Child checkpoints and operational trips
    stop_ids = fields.One2many(
        comodel_name="transport.route.stop",
        inverse_name="route_version_id",
        string="Puntos de Control / Paradas",
    )
    stop_count = fields.Integer(
        string="Nº Puntos de Control",
        compute="_compute_counts",
    )
    trip_ids = fields.One2many(
        comodel_name="transport.trip",
        inverse_name="route_version_id",
        string="Recorridos Ejecutados / Programados",
    )
    trip_count = fields.Integer(
        string="Nº Recorridos",
        compute="_compute_counts",
    )

    _sql_constraints = [
        (
            "unique_route_version",
            "unique(route_id, version_number)",
            "Ya existe esta versión para la ruta seleccionada.",
        )
    ]

    @api.depends("route_id.name", "version_number")
    def _compute_name(self):
        for ver in self:
            r_name = ver.route_id.name if ver.route_id else "Ruta"
            ver.name = f"{r_name} (v{ver.version_number})"

    def _compute_counts(self):
        for ver in self:
            ver.stop_count = len(ver.stop_ids)
            ver.trip_count = len(ver.trip_ids)

    @api.constrains(
        "stop_radius_m",
        "route_corridor_m",
        "lateness_tolerance_s",
        "gps_gap_threshold_s",
        "geo_accuracy_max_m",
    )
    def _check_canonical_parameters(self):
        """Validate physical sanity of canonical parameters per Section 7.1."""
        for ver in self:
            if ver.stop_radius_m <= 0:
                raise ValidationError(
                    "El radio de parada (stop_radius_m) debe ser mayor a 0 m."
                )
            if ver.route_corridor_m <= 0:
                raise ValidationError(
                    "El corredor (route_corridor_m) debe ser mayor a 0 m."
                )
            if ver.lateness_tolerance_s < 0:
                raise ValidationError(
                    "La tolerancia de retraso no puede ser negativa."
                )
            if ver.gps_gap_threshold_s <= 0:
                raise ValidationError(
                    "El umbral de gap GPS debe ser mayor a 0 s."
                )
            if ver.geo_accuracy_max_m <= 0:
                raise ValidationError(
                    "La precisión máxima admisible debe ser mayor a 0 m."
                )

    def write(self, vals):
        """Protect approved versions with trips from changes (RF-14)."""
        critical_fields = {
            "reference_polyline",
            "stop_radius_m",
            "route_corridor_m",
            "lateness_tolerance_s",
            "gps_gap_threshold_s",
        }
        for ver in self:
            if ver.state == "approved" and ver.trip_count > 0:
                modified_critical = critical_fields.intersection(vals.keys())
                if modified_critical:
                    fields_str = ", ".join(modified_critical)
                    raise UserError(
                        f"No es posible modificar los parámetros congelados "
                        f"({fields_str}) de una versión aprobada con "
                        f"{ver.trip_count} recorridos programados (RF-14)."
                    )
        return super().write(vals)

    def unlink(self):
        for ver in self:
            if ver.state == "approved" or ver.trip_count > 0:
                raise UserError(
                    f"No es posible eliminar la versión '{ver.name}' porque "
                    f"está aprobada o cuenta con {ver.trip_count} recorridos "
                    f"asociados. Archívela en su lugar (RF-14)."
                )
        return super().unlink()

    def action_compute_distance_from_polyline(self):
        """Compute estimated distance in meters from reference polyline."""
        self.ensure_one()
        if not self.reference_polyline:
            raise UserError("No se ha registrado una polilínea de referencia.")
        try:
            data = json.loads(self.reference_polyline)
            coords = (
                data.get("coordinates")
                if isinstance(data, dict) and data.get("type") == "LineString"
                else data
            )
            dist = calculate_polyline_distance(coords, is_geojson=True)
            self.estimated_distance_m = round(dist, 2)
            km_val = round(dist / 1000.0, 2)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Distancia Calculada",
                    "message": (
                        f"Distancia calculada: {self.estimated_distance_m} m "
                        f"({km_val} km)."
                    ),
                    "type": "info",
                    "sticky": False,
                },
            }
        except Exception as exc:
            raise UserError(
                f"Error al analizar la polilínea GeoJSON: {exc}."
            )

    def action_approve(self):
        """Approve route version and validate criteria (RF-09, RF-10)."""
        self.ensure_one()
        # RF-10: Must have at least 4 explicit checkpoints/stops
        if len(self.stop_ids) < 4:
            raise ValidationError(
                f"Aprobar ruta requiere al menos 4 puntos (RF-10). "
                f"Actualmente cuenta con {len(self.stop_ids)}."
            )

        # Validate polyline if present
        if self.reference_polyline:
            try:
                data = json.loads(self.reference_polyline)
                is_ls = (
                    isinstance(data, dict)
                    and data.get("type") == "LineString"
                )
                coords = data.get("coordinates") if is_ls else data
                if not isinstance(coords, list) or len(coords) < 2:
                    raise ValidationError(
                        "La polilínea debe tener al menos 2 puntos."
                    )
            except json.JSONDecodeError:
                raise ValidationError(
                    "La polilínea de referencia no es un JSON válido."
                )

        self.write(
            {
                "state": "approved",
                "approved_at": fields.Datetime.now(),
                "approved_by_id": self.env.user.id,
                "active_for_new_trips": True,
            }
        )
        # Set as current version on parent route
        self.route_id.write({"current_version_id": self.id})
        return True

    def action_archive(self):
        """Archive this route version so it cannot be used for new trips."""
        self.ensure_one()
        self.write({
            "state": "archived",
            "active_for_new_trips": False,
        })
        if self.route_id.current_version_id == self:
            self.route_id.write({"current_version_id": False})
        return True

    def action_set_to_draft(self):
        """Revert version to draft if no trips have been scheduled."""
        self.ensure_one()
        if self.trip_count > 0:
            raise UserError(
                f"No es posible regresar a borrador una versión que ya tiene "
                f"{self.trip_count} recorridos asociados."
            )
        self.write({
            "state": "draft",
            "active_for_new_trips": False,
        })
        if self.route_id.current_version_id == self:
            self.route_id.write({"current_version_id": False})
        return True
