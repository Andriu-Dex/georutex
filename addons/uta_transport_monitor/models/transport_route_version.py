"""Route versioning and frozen operational parameters for GeoRutex."""

import json
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from ..domain.geo import calculate_polyline_distance
from ..services.routing_service import RoutingService

_logger = logging.getLogger(__name__)


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
        """Protect approved versions from modifications (RF-14)."""
        is_install = (
            self.env.context.get("install_mode")
            or self.env.context.get("import_compat")
        )
        critical_fields = {
            "reference_polyline",
            "stop_radius_m",
            "route_corridor_m",
            "lateness_tolerance_s",
            "gps_gap_threshold_s",
            "minimum_consecutive_deviation_points",
            "minimum_deviation_duration_s",
            "geo_accuracy_max_m",
            "route_id",
            "version_number",
        }
        for ver in self:
            if (
                ver.state == "approved"
                and (ver.trip_count > 0 or ver.approved_at)
                and not is_install
            ):
                modified_critical = critical_fields.intersection(vals.keys())
                if modified_critical:
                    fields_str = ", ".join(modified_critical)
                    raise UserError(
                        f"No es posible modificar los parámetros congelados "
                        f"({fields_str}) de una versión aprobada (RF-14). "
                        f"Cree una nueva versión para modificar el trazado o tolerancias."
                    )
        return super().write(vals)

    def unlink(self):
        is_install = (
            self.env.context.get("install_mode")
            or self.env.context.get("import_compat")
        )
        for ver in self:
            if (
                (ver.state == "approved" or ver.trip_count > 0)
                and (ver.trip_count > 0 or ver.approved_at)
                and not is_install
            ):
                raise UserError(
                    f"No es posible eliminar la versión '{ver.name}' porque "
                    f"está aprobada o cuenta con {ver.trip_count} recorridos "
                    f"asociados. Archívela en su lugar (RF-14)."
                )
        return super().unlink()

    def auto_classify_stops(self):
        """Classify stops: 1st as origin, last as destination, middle as checkpoint."""
        for ver in self:
            if ver.state != "draft":
                continue
            stops = ver.stop_ids.sorted(key=lambda s: (s.sequence, s.id))
            count = len(stops)
            if count == 0:
                continue
            if count == 1:
                stops[0].with_context(skip_auto_classify=True).write({
                    "stop_type": "origin"
                })
            else:
                stops[0].with_context(skip_auto_classify=True).write({
                    "stop_type": "origin"
                })
                stops[-1].with_context(skip_auto_classify=True).write({
                    "stop_type": "destination"
                })
                for s in stops[1:-1]:
                    s.with_context(skip_auto_classify=True).write({
                        "stop_type": "checkpoint"
                    })

    def action_auto_classify_stops(self):
        """Action button to classify stops in sequence."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                "Solo se pueden auto-clasificar paradas en versiones en borrador."
            )
        self.auto_classify_stops()
        stops = self.stop_ids.sorted(key=lambda s: (s.sequence, s.id))
        origins = len(stops.filtered(lambda s: s.stop_type == "origin"))
        checkpoints = len(stops.filtered(lambda s: s.stop_type == "checkpoint"))
        destinations = len(stops.filtered(lambda s: s.stop_type == "destination"))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Paradas Clasificadas",
                "message": (
                    f"Auto-clasificación completada: {origins} Origen, "
                    f"{checkpoints} Controles Intermedios, {destinations} Destino."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_calculate_road_route(self):
        """Compute road route from ordered stops using decoupled routing service."""
        self.ensure_one()
        stops = self.stop_ids.sorted(key=lambda s: (s.sequence, s.id))
        if len(stops) < 2:
            raise UserError(
                "Se requieren al menos 2 puntos de control para calcular el trazado vial."
            )

        stops_data = [
            {"latitude": s.latitude, "longitude": s.longitude, "name": s.name}
            for s in stops
        ]

        icp = self.env["ir.config_parameter"].sudo()
        provider_url = icp.get_param(
            "georutex.routing_provider_url", "https://router.project-osrm.org"
        )
        enabled = icp.get_param("georutex.routing_provider_enabled", "True") == "True"
        timeout = float(icp.get_param("georutex.routing_timeout_s", "3.0"))

        res = RoutingService.calculate_road_route(
            stops_data=stops_data,
            provider_url=provider_url,
            timeout=timeout,
            enabled=enabled,
        )

        if not res.get("success"):
            raise UserError(res.get("message", "Error al calcular el trazado vial."))

        geojson_geom = {
            "type": "LineString",
            "coordinates": res["coordinates"],
        }
        self.write({
            "reference_polyline": json.dumps(geojson_geom),
            "estimated_distance_m": res["distance_m"],
        })

        notif_type = "warning" if res.get("fallback") else "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Trazado Vial Calculado",
                "message": res["message"],
                "type": notif_type,
                "sticky": False,
            },
        }

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
        stops = self.stop_ids.sorted(key=lambda s: (s.sequence, s.id))
        # 1. Minimum 4 stops (RF-10)
        if len(stops) < 4:
            raise ValidationError(
                f"Aprobar la ruta requiere al menos 4 puntos de control (RF-10). "
                f"Actualmente cuenta con {len(stops)}."
            )

        # 2. Origin check: exactly 1 origin and must be first in sequence
        origin_stops = stops.filtered(lambda s: s.stop_type == "origin")
        if len(origin_stops) != 1:
            raise ValidationError(
                f"La versión de ruta debe tener exactamente 1 punto de tipo 'Origen' (RF-10). "
                f"Actualmente cuenta con {len(origin_stops)}. "
                f"Utilice 'Auto-clasificar Paradas' o ajuste el tipo en la lista."
            )
        if stops[0] != origin_stops[0]:
            raise ValidationError(
                f"El punto de tipo 'Origen' ('{origin_stops[0].name}') debe ser el "
                f"primer punto en la secuencia de la ruta (secuencia {stops[0].sequence} vs {origin_stops[0].sequence})."
            )

        # 3. Destination check: exactly 1 destination and must be last in sequence
        destination_stops = stops.filtered(lambda s: s.stop_type == "destination")
        if len(destination_stops) != 1:
            raise ValidationError(
                f"La versión de ruta debe tener exactamente 1 punto de tipo 'Destino' (RF-10). "
                f"Actualmente cuenta con {len(destination_stops)}. "
                f"Utilice 'Auto-clasificar Paradas' o ajuste el tipo en la lista."
            )
        if stops[-1] != destination_stops[0]:
            raise ValidationError(
                f"El punto de tipo 'Destino' ('{destination_stops[0].name}') debe ser el "
                f"último punto en la secuencia de la ruta (secuencia {stops[-1].sequence} vs {destination_stops[0].sequence})."
            )

        # 4. Intermediate checkpoints: at least 2 checkpoints between origin and destination
        intermediate_stops = stops[1:-1]
        if len(intermediate_stops) < 2:
            raise ValidationError(
                "La ruta debe contar con al menos 2 puntos de control intermedios entre "
                "el origen y el destino (RF-10)."
            )
        non_checkpoints = intermediate_stops.filtered(lambda s: s.stop_type != "checkpoint")
        if non_checkpoints:
            names = ", ".join(non_checkpoints.mapped("name"))
            raise ValidationError(
                f"Los puntos intermedios deben tener tipo 'Control Intermedio'. "
                f"Verifique los siguientes puntos: {names}."
            )

        # 5. Geometry validation and auto-generation if missing
        if not self.reference_polyline:
            self.action_calculate_road_route()

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
                        "La polilínea de referencia debe contener al menos 2 coordenadas."
                    )
                if not self.estimated_distance_m:
                    dist = calculate_polyline_distance(coords, is_geojson=True)
                    self.estimated_distance_m = round(dist, 2)
            except json.JSONDecodeError:
                raise ValidationError(
                    "La polilínea de referencia no es un JSON válido."
                )

        self.write({
            "state": "approved",
            "approved_at": fields.Datetime.now(),
            "approved_by_id": self.env.user.id,
            "active_for_new_trips": True,
        })
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

    # -------------------------------------------------------------------------
    # Visual Route Editor RPC API
    # -------------------------------------------------------------------------

    def get_route_editor_data(self):
        """Fetch complete geometric and stop state for visual map editor."""
        self.ensure_one()
        stops = self.stop_ids.sorted(key=lambda s: (s.sequence, s.id))
        stops_list = []
        for s in stops:
            stops_list.append({
                "id": s.id,
                "name": s.name,
                "sequence": s.sequence,
                "stop_type": s.stop_type,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "radius_m": s.radius_m,
                "planned_offset_seconds": s.planned_offset_seconds,
                "required": s.required,
                "notes": s.notes or "",
            })

        leaflet_coords = []
        if self.reference_polyline:
            try:
                data = json.loads(self.reference_polyline)
                raw_coords = (
                    data.get("coordinates")
                    if isinstance(data, dict) and data.get("type") == "LineString"
                    else data
                )
                if isinstance(raw_coords, list):
                    for pt in raw_coords:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                            leaflet_coords.append([pt[1], pt[0]])
            except Exception:
                leaflet_coords = []

        return {
            "id": self.id,
            "name": self.name,
            "route_name": self.route_id.name if self.route_id else "",
            "state": self.state,
            "is_draft": self.state == "draft",
            "stop_count": len(stops),
            "estimated_distance_m": self.estimated_distance_m or 0.0,
            "stop_radius_m": self.stop_radius_m,
            "route_corridor_m": self.route_corridor_m,
            "lateness_tolerance_s": self.lateness_tolerance_s,
            "reference_polyline_geojson": self.reference_polyline or "",
            "reference_polyline_coords": leaflet_coords,
            "stops": stops_list,
        }

    def save_route_editor_stop(self, stop_vals):
        """Create or update a stop from visual editor and return updated data."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError("Solo se pueden editar paradas en versiones en borrador.")

        stop_id = stop_vals.get("id")
        name = stop_vals.get("name") or "Nuevo Control"
        lat = float(stop_vals.get("latitude", 0.0))
        lon = float(stop_vals.get("longitude", 0.0))
        radius = float(stop_vals.get("radius_m") or self.stop_radius_m or 30.0)
        offset = int(stop_vals.get("planned_offset_seconds") or 0)
        required = bool(stop_vals.get("required", True))
        stop_type = stop_vals.get("stop_type")

        if stop_id:
            stop = self.env["transport.route.stop"].browse(stop_id)
            if stop.exists() and stop.route_version_id == self:
                write_vals = {
                    "name": name,
                    "latitude": lat,
                    "longitude": lon,
                    "radius_m": radius,
                    "planned_offset_seconds": offset,
                    "required": required,
                }
                if stop_type:
                    write_vals["stop_type"] = stop_type
                stop.write(write_vals)
        else:
            max_seq = max([s.sequence for s in self.stop_ids], default=0)
            create_vals = {
                "route_version_id": self.id,
                "name": name,
                "sequence": max_seq + 10,
                "latitude": lat,
                "longitude": lon,
                "radius_m": radius,
                "planned_offset_seconds": offset,
                "required": required,
            }
            if stop_type:
                create_vals["stop_type"] = stop_type
            self.env["transport.route.stop"].create(create_vals)

        # Recalculate route if >= 2 stops
        if len(self.stop_ids) >= 2:
            try:
                self.action_calculate_road_route()
            except Exception as e:
                _logger.warning("Auto route calculation on stop save failed: %s", e)

        return self.get_route_editor_data()

    def delete_route_editor_stop(self, stop_id):
        """Delete stop from visual editor and return updated data."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError("Solo se pueden eliminar paradas en versiones en borrador.")
        stop = self.env["transport.route.stop"].browse(stop_id)
        if stop.exists() and stop.route_version_id == self:
            stop.unlink()
        if len(self.stop_ids) >= 2:
            try:
                self.action_calculate_road_route()
            except Exception as e:
                _logger.warning("Auto route calculation on stop delete failed: %s", e)
        return self.get_route_editor_data()

    def reorder_route_editor_stops(self, stop_ids):
        """Reorder stops based on list of stop IDs from visual editor."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError("Solo se pueden reordenar paradas en versiones en borrador.")
        seq = 10
        for s_id in stop_ids:
            stop = self.env["transport.route.stop"].browse(s_id)
            if stop.exists() and stop.route_version_id == self:
                stop.write({"sequence": seq})
                seq += 10
        self.auto_classify_stops()
        if len(self.stop_ids) >= 2:
            try:
                self.action_calculate_road_route()
            except Exception as e:
                _logger.warning("Auto route calculation on reorder failed: %s", e)
        return self.get_route_editor_data()
