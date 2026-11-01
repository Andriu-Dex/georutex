"""Trip evaluation record model for GeoRutex (Phase 4).

Complies with RF-26 and RF-30:
- Immutable snapshot of parameters and rules version at evaluation time.
- Preserves both gross compliance (brutto) and adjusted compliance (netto).
- Stores checkpoint metrics, deviations, telemetry loss, and punctuality.
- Idempotent execution and auditable traceability.
"""

from odoo import api, fields, models


class TransportTripEvaluation(models.Model):
    """Audit and evaluation record for a completed or evaluated trip."""

    _name = "transport.trip.evaluation"
    _description = "Evaluación de Cumplimiento de Recorrido"
    _order = "evaluation_date desc, id desc"

    name = fields.Char(
        string="Código de Evaluación",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: self._default_name(),
    )
    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido Evaluado",
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
    route_version_id = fields.Many2one(
        comodel_name="transport.route.version",
        string="Versión de Ruta",
        related="trip_id.route_version_id",
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
    evaluation_date = fields.Datetime(
        string="Fecha de Evaluación",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    evaluator_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Evaluador / Usuario",
        default=lambda self: self.env.user,
        readonly=True,
    )
    rules_version = fields.Char(
        string="Versión de Reglas",
        default="v1.0.0-phase4",
        required=True,
        readonly=True,
    )
    parameter_snapshot_json = fields.Text(
        string="Snapshot de Parámetros Congelados",
        readonly=True,
    )

    # Compliance verdicts (RF-26, RF-31)
    integrity_status = fields.Selection(
        selection=[
            ("completed", "Completado"),
            ("incomplete", "Incompleto"),
            ("insufficient_data", "Datos Insuficientes"),
        ],
        string="Estado de Integridad",
        required=True,
        default="completed",
        index=True,
    )
    is_compliant_gross = fields.Boolean(
        string="Conforme Bruto (Sin Ajustes)",
        readonly=True,
        help="Evaluación matemática estricta antes de justificaciones.",
    )
    is_compliant_adjusted = fields.Boolean(
        string="Conforme Ajustado (Con Justificaciones)",
        readonly=True,
        help="Evaluación considerando justificaciones operacionales.",
    )

    # Operational metrics
    start_punctuality = fields.Selection(
        selection=[
            ("early", "Anticipado"),
            ("on_time", "Puntual"),
            ("late", "Tardío"),
            ("indeterminate", "Indeterminado"),
        ],
        string="Puntualidad en Salida",
        default="indeterminate",
    )
    start_delay_s = fields.Integer(
        string="Diferencia Salida (s)",
        help="Diferencia en segundos respecto a la salida programada.",
    )
    arrival_punctuality = fields.Selection(
        selection=[
            ("early", "Anticipado"),
            ("on_time", "Puntual"),
            ("late", "Tardío"),
            ("incomplete", "Incompleto"),
            ("indeterminate", "Indeterminado"),
        ],
        string="Puntualidad en Llegada",
        default="indeterminate",
    )
    arrival_delay_s = fields.Integer(
        string="Diferencia Llegada (s)",
        help="Diferencia en segundos respecto a la llegada programada.",
    )

    # Checkpoint counts
    stops_total = fields.Integer(string="Total Paradas / Controles")
    stops_on_time = fields.Integer(string="Paradas Puntuales")
    stops_late = fields.Integer(string="Paradas con Retraso")
    stops_missed = fields.Integer(string="Paradas Omitidas")
    stops_indeterminate = fields.Integer(string="Paradas Indeterminadas")

    # Spatial and telemetry counts
    deviation_count = fields.Integer(string="Nº Desvíos Confirmados")
    deviation_duration_s = fields.Integer(string="Duración Total Desvíos (s)")
    max_deviation_distance_m = fields.Float(
        string="Distancia Máxima de Desvío (m)",
        digits=(8, 2),
    )
    gps_gap_count = fields.Integer(string="Nº Pérdidas de Señal (Gaps)")
    gps_gap_duration_s = fields.Integer(string="Duración Total Gaps GPS (s)")

    evaluation_summary = fields.Text(
        string="Dictamen y Detalle de Evaluación",
    )

    # Incidents relation
    incident_ids = fields.Many2many(
        comodel_name="transport.incident",
        relation="transport_trip_evaluation_incident_rel",
        column1="evaluation_id",
        column2="incident_id",
        string="Incidencias Asociadas",
    )

    @api.model
    def _default_name(self):
        return (
            self.env["ir.sequence"].next_by_code("transport.trip.evaluation")
            or "EVAL-NUEVO"
        )

    def compute_adjusted_compliance(self):
        """Recompute adjusted compliance based on approved justifications."""
        for ev in self:
            if ev.is_compliant_gross:
                ev.write({"is_compliant_adjusted": True})
                if ev.trip_id:
                    ev.trip_id.write({"evaluation_status": "compliant"})
                continue

            if ev.integrity_status == "insufficient_data":
                ev.write({"is_compliant_adjusted": False})
                if ev.trip_id:
                    ev.trip_id.write({"evaluation_status": "indeterminate"})
                continue

            # Check unexcused causes
            # Non-compliant automatic incidents
            unjustified_incidents = ev.incident_ids.filtered(
                lambda inc: inc.state not in ("justified",)
            )

            if unjustified_incidents:
                ev.write({"is_compliant_adjusted": False})
                if ev.trip_id:
                    ev.trip_id.write({"evaluation_status": "non_compliant"})
            else:
                # All non-compliance incidents were approved as justified
                ev.write({"is_compliant_adjusted": True})
                if ev.trip_id:
                    ev.trip_id.write({"evaluation_status": "compliant"})
