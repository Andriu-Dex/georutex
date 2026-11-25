"""Operational notification center model with strict per-user RBAC and deduplication."""

from datetime import timezone
import zoneinfo
from odoo import api, fields, models


ECUADOR_TZ = zoneinfo.ZoneInfo("America/Guayaquil")


class TransportNotification(models.Model):
    """Per-user operational notifications triggered by real GeoRutex business events."""

    _name = "transport.notification"
    _description = "Notificación Operacional GeoRutex"
    _order = "create_date desc, id desc"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Destinatario",
        required=True,
        ondelete="cascade",
        index=True,
    )
    title = fields.Char(string="Título", required=True)
    message = fields.Text(string="Mensaje", required=True)
    category = fields.Selection(
        selection=[
            ("trip_assigned", "Recorrido asignado"),
            ("trip_updated", "Actualización de jornada"),
            ("trip_cancelled", "Recorrido cancelado"),
            ("incident_reported", "Incidencia reportada"),
            ("incident_reviewed", "Revisión de incidencia"),
            ("evaluation_ready", "Evaluación disponible"),
        ],
        string="Categoría",
        required=True,
        default="trip_updated",
        index=True,
    )
    severity = fields.Selection(
        selection=[
            ("info", "Informativa"),
            ("success", "Confirmación"),
            ("warning", "Atención"),
            ("danger", "Prioritaria"),
        ],
        string="Severidad",
        required=True,
        default="info",
    )
    res_model = fields.Char(string="Modelo relacionado")
    res_id = fields.Integer(string="ID relacionado")
    is_read = fields.Boolean(string="Leída", default=False, index=True)
    dedup_key = fields.Char(string="Clave de deduplicación", index=True)

    @api.model
    def notify_users(
        self,
        users,
        title,
        message,
        category="trip_updated",
        severity="info",
        res_model=False,
        res_id=False,
        dedup_key=False,
    ):
        """Create deduplicated operational notifications for target users."""
        if not users:
            return self.browse()
        created = self.browse()
        sudo_model = self.sudo()
        for user in users:
            if not user or not user.active:
                continue
            if dedup_key:
                existing = sudo_model.search(
                    [
                        ("user_id", "=", user.id),
                        ("dedup_key", "=", dedup_key),
                        ("is_read", "=", False),
                    ],
                    limit=1,
                )
                if existing:
                    continue
            created |= sudo_model.create(
                {
                    "user_id": user.id,
                    "title": title,
                    "message": message,
                    "category": category,
                    "severity": severity,
                    "res_model": res_model or False,
                    "res_id": int(res_id) if res_id else 0,
                    "dedup_key": dedup_key or False,
                }
            )
        return created

    @api.model
    def get_my_notifications(self, unread_only=False, limit=30):
        """Return notifications strictly for the current authenticated user."""
        domain = [("user_id", "=", self.env.uid)]
        if unread_only:
            domain.append(("is_read", "=", False))
        records = self.search(domain, limit=min(int(limit or 30), 50))
        unread_count = self.search_count(
            [("user_id", "=", self.env.uid), ("is_read", "=", False)]
        )
        items = []
        for rec in records:
            local_time = ""
            if rec.create_date:
                dt_utc = rec.create_date.replace(tzinfo=timezone.utc)
                local_time = dt_utc.astimezone(ECUADOR_TZ).strftime("%d/%m %H:%M")
            items.append(
                {
                    "id": rec.id,
                    "title": rec.title,
                    "message": rec.message,
                    "category": rec.category,
                    "severity": rec.severity,
                    "res_model": rec.res_model or "",
                    "res_id": rec.res_id or 0,
                    "is_read": bool(rec.is_read),
                    "time_local": local_time,
                }
            )
        return {
            "unread_count": unread_count,
            "items": items,
        }

    @api.model
    def action_mark_read(self, notif_id):
        rec = self.search(
            [("id", "=", int(notif_id)), ("user_id", "=", self.env.uid)], limit=1
        )
        if rec and not rec.is_read:
            rec.write({"is_read": True})
        return True

    @api.model
    def action_mark_all_read(self):
        unread = self.search(
            [("user_id", "=", self.env.uid), ("is_read", "=", False)]
        )
        if unread:
            unread.write({"is_read": True})
        return len(unread)
