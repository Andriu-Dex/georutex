"""Incident reporting and justification workflow model (Phase 4).

Complies with RF-27, RF-28, RF-29:
- Automatic detection from evaluation engine (delays, missed stops, gaps).
- Manual operational reporting (traffic, accidents, road blocks, weather).
- Segregated roles: drivers CANNOT approve their own justifications.
- Non-destructive adjustments: approval preserves gross compliance.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TransportIncident(models.Model):
    """Operational incident recorded during a trip execution."""

    _name = "transport.incident"
    _description = "Incidencia Operacional de Transporte"
    _order = "timestamp_utc desc, id desc"

    name = fields.Char(
        string="Código de Incidencia",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: self._default_name(),
    )
    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido Asociado",
        required=True,
        ondelete="cascade",
        index=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Vehículo",
        related="trip_id.vehicle_id",
        store=True,
        readonly=True,
    )
    route_id = fields.Many2one(
        comodel_name="transport.route",
        string="Ruta",
        related="trip_id.route_id",
        store=True,
        readonly=True,
    )
    driver_id = fields.Many2one(
        comodel_name="res.partner",
        string="Conductor",
        related="trip_id.driver_id",
        store=True,
        readonly=True,
    )
    driver_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Usuario Conductor",
        related="trip_id.driver_user_id",
        store=True,
        readonly=True,
    )

    incident_type = fields.Selection(
        selection=[
            # Automatic types (RF-27)
            ("delay_start", "Retraso en Salida"),
            ("delay_arrival", "Retraso en Llegada"),
            ("delay_checkpoint", "Retraso en Punto de Control"),
            ("stop_missed", "Omisión de Parada Obligatoria"),
            ("route_deviation", "Desvío del Corredor de Ruta"),
            ("gps_loss", "Pérdida de Señal GPS (Gap)"),
            # Manual operational types (RF-28)
            ("traffic_congestion", "Congestión Vehicular Severa"),
            ("accident", "Accidente de Tránsito"),
            ("road_block", "Cierre o Bloqueo de Vía"),
            ("vehicle_breakdown", "Avería Mecánica"),
            ("weather", "Condiciones Climáticas Adversas"),
            ("other", "Otra Eventualidad"),
        ],
        string="Tipo de Incidencia",
        required=True,
        index=True,
        default="other",
    )
    source = fields.Selection(
        selection=[
            ("automatic", "Detección Automática (Motor de Reglas)"),
            ("manual", "Reporte Manual (Operador / Conductor)"),
        ],
        string="Origen",
        required=True,
        default="manual",
        index=True,
    )
    severity = fields.Selection(
        selection=[
            ("low", "Baja"),
            ("medium", "Media"),
            ("high", "Alta"),
            ("critical", "Crítica"),
        ],
        string="Severidad",
        required=True,
        default="medium",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pendiente / Registrada"),
            ("justified", "Justificada (Aprobada)"),
            ("rejected", "Justificación Rechazada"),
            ("confirmed", "Confirmada / Sin Justificar"),
        ],
        string="Estado de Resolución",
        required=True,
        default="pending",
        index=True,
    )

    stop_id = fields.Many2one(
        comodel_name="transport.route.stop",
        string="Parada Afectada",
        ondelete="set null",
        help="Parada o punto de control relacionado si aplica.",
    )
    timestamp_utc = fields.Datetime(
        string="Fecha y Hora del Evento (UTC)",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    latitude = fields.Float(
        string="Latitud del Evento",
        digits=(10, 6),
    )
    longitude = fields.Float(
        string="Longitud del Evento",
        digits=(10, 6),
    )
    rule_applied = fields.Char(
        string="Regla de Evaluación Aplicada",
        help="Identificador de regla canónica evaluada (e.g. RF-24).",
    )
    evidence_data = fields.Text(
        string="Datos de Evidencia Técnica",
        help="Detalles numéricos, métricas y coordenadas de la infracción.",
    )
    description = fields.Text(
        string="Descripción del Incidente",
        help="Descripción operacional del evento.",
    )

    # Justification fields (RF-29)
    justification_notes = fields.Text(
        string="Descargo / Justificación",
        help="Motivo alegado para justificar la incidencia.",
    )
    justification_submitted_by = fields.Many2one(
        comodel_name="res.users",
        string="Justificación Enviada Por",
        readonly=True,
    )
    justification_submitted_at = fields.Datetime(
        string="Fecha de Justificación",
        readonly=True,
    )
    reviewed_by = fields.Many2one(
        comodel_name="res.users",
        string="Revisado Por",
        readonly=True,
    )
    reviewed_at = fields.Datetime(
        string="Fecha de Revisión",
        readonly=True,
    )
    review_notes = fields.Text(
        string="Resolución de Revisión",
        help="Comentarios del revisor sobre la justificación.",
    )

    @api.model
    def _default_name(self):
        return (
            self.env["ir.sequence"].next_by_code("transport.incident")
            or "INC-NUEVO"
        )

    def action_submit_justification(self):
        """Submit justification notes from driver or operator."""
        self.ensure_one()
        if not self.justification_notes:
            raise UserError(
                "Debe ingresar el texto del descargo antes de enviar."
            )
        self.write({
            "justification_submitted_by": self.env.user.id,
            "justification_submitted_at": fields.Datetime.now(),
            "state": "pending",
        })
        return True

    def action_approve_justification(self):
        """Approve justification with segregation of duties (RF-29).

        A driver CANNOT approve their own justifications.
        """
        self.ensure_one()
        is_manager = self.env.user.has_group(
            "uta_transport_monitor.group_transport_manager"
        )
        is_analyst = self.env.user.has_group(
            "uta_transport_monitor.group_transport_analyst"
        )

        if not (is_manager or is_analyst):
            raise AccessError(
                "Segregación de funciones (RF-29): Los conductores no tienen "
                "permiso para aprobar justificaciones. Se requiere rol de "
                "Analista o Administrador."
            )

        if (
            self.justification_submitted_by
            and self.justification_submitted_by == self.env.user
            and not is_manager
        ):
            raise AccessError(
                "Segregación de funciones (RF-29): El usuario no puede "
                "aprobar su propio descargo operacional."
            )

        self.write({
            "state": "justified",
            "reviewed_by": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })

        # Re-evaluate trip adjusted compliance
        if self.trip_id.evaluation_ids:
            latest = self.trip_id.evaluation_ids.sorted("id", reverse=True)[0]
            latest.compute_adjusted_compliance()

        return True

    def action_reject_justification(self):
        """Reject justification with segregation of duties (RF-29)."""
        self.ensure_one()
        is_manager = self.env.user.has_group(
            "uta_transport_monitor.group_transport_manager"
        )
        is_analyst = self.env.user.has_group(
            "uta_transport_monitor.group_transport_analyst"
        )

        if not (is_manager or is_analyst):
            raise AccessError(
                "Segregación de funciones (RF-29): Se requiere rol de "
                "Analista o Administrador para rechazar justificaciones."
            )

        self.write({
            "state": "rejected",
            "reviewed_by": self.env.user.id,
            "reviewed_at": fields.Datetime.now(),
        })

        if self.trip_id.evaluation_ids:
            latest = self.trip_id.evaluation_ids.sorted("id", reverse=True)[0]
            latest.compute_adjusted_compliance()

        return True

    def action_confirm_incident(self):
        """Mark incident as confirmed without accepted justification."""
        self.ensure_one()
        self.write({"state": "confirmed"})
        return True
