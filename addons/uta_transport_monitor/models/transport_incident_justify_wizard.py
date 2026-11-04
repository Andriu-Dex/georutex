"""Transient wizard for fast and user-friendly incident justifications."""

from odoo import fields, models
from odoo.exceptions import UserError


class TransportIncidentJustifyWizard(models.TransientModel):
    """Wizard to allow drivers and operators to submit incident justifications quickly."""

    _name = "transport.incident.justify.wizard"
    _description = "Asistente de Justificación Rápida de Incidencias"

    incident_id = fields.Many2one(
        comodel_name="transport.incident",
        string="Incidencia",
        required=True,
        readonly=True,
    )
    trip_id = fields.Many2one(
        comodel_name="transport.trip",
        string="Recorrido",
        related="incident_id.trip_id",
        readonly=True,
    )
    incident_type = fields.Selection(
        string="Tipo de Incidencia",
        related="incident_id.incident_type",
        readonly=True,
    )
    justification_category = fields.Selection(
        selection=[
            ("congestion", "Congestión vehicular severa / Tráfico"),
            ("road_block", "Cierre o bloqueo de vía por obras"),
            ("mechanical", "Avería o problema mecánico / eléctrico"),
            ("emergency", "Emergencia médica o asistencia a pasajero"),
            ("weather", "Condiciones climáticas adversas"),
            ("other", "Otra eventualidad justificada"),
        ],
        string="Motivo Principal",
        required=True,
        default="congestion",
    )
    justification_notes = fields.Text(
        string="Explicación / Detalle Operativo",
        required=True,
        help="Detalle los hechos ocurridos para revisión del gestor de transporte.",
    )

    def action_confirm_justification(self):
        """Save notes and submit justification on the incident record."""
        self.ensure_one()
        incident = self.incident_id
        if incident.state in ("justified", "rejected"):
            raise UserError(
                "No se puede justificar una incidencia que ya ha sido resuelta (Aprobada o Rechazada)."
            )

        cat_label = dict(
            self._fields["justification_category"].selection
        ).get(self.justification_category, "")
        full_text = f"[{cat_label}] {self.justification_notes.strip()}"

        incident.write({
            "justification_notes": full_text,
            "justification_submitted_by": self.env.user.id,
            "justification_submitted_at": fields.Datetime.now(),
            "state": "pending",
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Justificación Enviada",
                "message": (
                    f"El descargo para la incidencia '{incident.name}' fue "
                    "registrado correctamente y queda pendiente de revisión."
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
