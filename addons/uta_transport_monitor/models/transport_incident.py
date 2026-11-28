"""Incident reporting and justification workflow model (Phase 4).

Complies with RF-27, RF-28, RF-29:
- Automatic detection from evaluation engine (delays, missed stops, gaps).
- Manual operational reporting (traffic, accidents, road blocks, weather).
- Segregated roles: drivers CANNOT approve their own justifications.
- Non-destructive adjustments: approval preserves gross compliance.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


MODEL_INCIDENT = "transport.incident"
MODEL_USERS = "res.users"
GROUP_MANAGER = "uta_transport_monitor.group_transport_manager"
GROUP_ANALYST = "uta_transport_monitor.group_transport_analyst"


class TransportIncident(models.Model):
    """Operational incident recorded during a trip execution."""

    _name = MODEL_INCIDENT
    _description = "Incidencia Operacional de Transporte"
    _order = "timestamp_utc desc, id desc"

    name = fields.Char(
        string="Código de incidencia",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default="Nuevo",
    )
    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido asociado",
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
        comodel_name=MODEL_USERS,
        string="Usuario conductor",
        related="trip_id.driver_user_id",
        store=True,
        readonly=True,
    )

    incident_type = fields.Selection(
        selection=[
            # Automatic types (RF-27)
            ("delay_start", "Retraso en salida"),
            ("delay_arrival", "Retraso en llegada"),
            ("delay_checkpoint", "Retraso en punto de control"),
            ("stop_missed", "Omisión de parada obligatoria"),
            ("route_deviation", "Desvío del corredor de ruta"),
            ("gps_loss", "Pérdida de señal GPS"),
            # Manual operational types (RF-28)
            ("traffic_congestion", "Congestión vehicular severa"),
            ("accident", "Accidente de tránsito"),
            ("road_block", "Cierre o bloqueo de vía"),
            ("vehicle_breakdown", "Avería mecánica"),
            ("weather", "Condiciones climáticas adversas"),
            ("other", "Otra eventualidad"),
        ],
        string="Tipo de incidencia",
        required=True,
        index=True,
        default="other",
    )
    source = fields.Selection(
        selection=[
            ("automatic", "Detección automática (motor de reglas)"),
            ("manual", "Reporte manual (operador / conductor)"),
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
            ("pending", "Pendiente / registrada"),
            ("justified", "Justificada (aprobada)"),
            ("rejected", "Justificación rechazada"),
            ("confirmed", "Confirmada / sin justificar"),
        ],
        string="Estado de resolución",
        required=True,
        default="pending",
        index=True,
    )

    stop_id = fields.Many2one(
        comodel_name="transport.route.stop",
        string="Parada afectada",
        ondelete="set null",
        help="Parada o punto de control relacionado si aplica.",
    )
    timestamp_utc = fields.Datetime(
        string="Fecha y hora del evento (UTC)",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    latitude = fields.Float(
        string="Latitud del evento",
        digits=(10, 6),
    )
    longitude = fields.Float(
        string="Longitud del evento",
        digits=(10, 6),
    )
    rule_applied = fields.Char(
        string="Regla de evaluación aplicada",
        help="Regla de control que originó la incidencia.",
    )
    evidence_data = fields.Text(
        string="Datos de evidencia técnica",
        help="Detalles numéricos, métricas y coordenadas de la infracción.",
    )
    description = fields.Text(
        string="Descripción del incidente",
        help="Descripción operacional del evento.",
    )

    # Justification fields (RF-29)
    justification_notes = fields.Text(
        string="Descargo / justificación",
        help="Motivo alegado para justificar la incidencia.",
    )
    justification_submitted_by = fields.Many2one(
        comodel_name=MODEL_USERS,
        string="Justificación enviada por",
        readonly=True,
    )
    justification_submitted_at = fields.Datetime(
        string="Fecha de justificación",
        readonly=True,
    )
    reviewed_by = fields.Many2one(
        comodel_name=MODEL_USERS,
        string="Revisado por",
        readonly=True,
    )
    reviewed_at = fields.Datetime(
        string="Fecha de revisión",
        readonly=True,
    )
    review_notes = fields.Text(
        string="Resolución de revisión",
        help="Comentarios del revisor sobre la justificación.",
    )

    @api.model
    def _next_incident_code(self):
        return (
            self.env["ir.sequence"].next_by_code(MODEL_INCIDENT)
            or "INC-NUEVO"
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Assign incident sequence only on persisted creation (avoids wasting codes on cancel)."""
        for vals in vals_list:
            if not vals.get("trip_id"):
                raise UserError(
                    "Debe seleccionar un recorrido asociado para registrar una incidencia."
                )
            if not vals.get("name") or vals.get("name") in ("Nuevo", "Borrador", "INC-NUEVO"):
                vals["name"] = self._next_incident_code()
        records = super().create(vals_list)
        # Notify operational managers and analysts on real manual incident reports
        notif_model = self.env["transport.notification"]
        mgr_group = self.env.ref(GROUP_MANAGER, raise_if_not_found=False)
        ana_group = self.env.ref(GROUP_ANALYST, raise_if_not_found=False)
        recipients = (mgr_group.users if mgr_group else self.env[MODEL_USERS]) | (
            ana_group.users if ana_group else self.env[MODEL_USERS]
        )
        for rec in records.filtered(lambda r: r.source == "manual"):
            target_users = recipients - self.env.user
            if target_users:
                notif_model.notify_users(
                    target_users,
                    title=f"Nueva incidencia reportada ({rec.name})",
                    message=f"{rec.route_id.name or rec.trip_id.name}: {dict(self._fields['incident_type'].selection).get(rec.incident_type, rec.incident_type)}.",
                    category="incident_reported",
                    severity="danger" if rec.severity in ("high", "critical") else "warning",
                    res_model=MODEL_INCIDENT,
                    res_id=rec.id,
                    dedup_key=f"inc_new_{rec.id}",
                )
        return records

    def action_open_justify_wizard(self):
        """Open quick modal wizard to submit justification."""
        self.ensure_one()
        return {
            "name": f"Justificar Incidencia — {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "transport.incident.justify.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_incident_id": self.id,
            },
        }

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
        is_manager = self.env.user.has_group(GROUP_MANAGER)
        is_analyst = self.env.user.has_group(GROUP_ANALYST)

        if not (is_manager or is_analyst):
            raise AccessError(
                "Los conductores no tienen "
                "permiso para aprobar justificaciones. Se requiere rol de "
                "Analista o Administrador."
            )

        if (
            self.justification_submitted_by
            and self.justification_submitted_by == self.env.user
            and not is_manager
        ):
            raise AccessError(
                "El usuario no puede "
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

        if self.trip_id.driver_user_id:
            self.env["transport.notification"].notify_users(
                self.trip_id.driver_user_id,
                title=f"Justificación aprobada ({self.name})",
                message=f"Tu justificación para el recorrido {self.route_id.name or self.trip_id.name} fue aprobada.",
                category="incident_reviewed",
                severity="success",
                res_model=MODEL_INCIDENT,
                res_id=self.id,
                dedup_key=f"inc_rev_{self.id}_approved",
            )

        return True

    def action_reject_justification(self):
        """Reject justification with segregation of duties (RF-29)."""
        self.ensure_one()
        is_manager = self.env.user.has_group(GROUP_MANAGER)
        is_analyst = self.env.user.has_group(GROUP_ANALYST)

        if not (is_manager or is_analyst):
            raise AccessError(
                "Se requiere rol de "
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
