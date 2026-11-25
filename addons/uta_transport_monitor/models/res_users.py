"""Extension of res.users for GeoRutex driver signup and branded auth emails."""

import logging

from odoo import _, api, models
from odoo.addons.auth_signup.models.res_partner import SignupError, now
from odoo.exceptions import UserError

from ..domain.auth_validation import (
    normalize_email,
    validate_email,
    validate_full_name,
    validate_strong_password,
)
from .email_verification import mask_email

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Provision self-registered drivers and send branded GeoRutex auth emails."""

    _inherit = "res.users"

    @api.model
    def _georutex_default_spanish_lang(self):
        """Return active Spanish locale code (preferring es_EC over es_ES)."""
        active_langs = (
            self.env["res.lang"]
            .sudo()
            .search([("code", "in", ["es_EC", "es_ES"]), ("active", "=", True)])
            .mapped("code")
        )
        if "es_EC" in active_langs:
            return "es_EC"
        if "es_ES" in active_langs:
            return "es_ES"
        return False

    @api.model
    def _georutex_build_reset_url(self, user):
        """Return dynamic GeoRutex password reset URL preserving base domain and token."""
        raw_url = user.signup_url or ""
        if "/web/reset_password" in raw_url:
            return raw_url.replace(
                "/web/reset_password", "/georutex/recuperar-acceso", 1
            )
        return raw_url

    def action_reset_password(self):
        """Prepare 24h single-use reset token and send GeoRutex branded email."""
        if self.env.context.get("install_mode", False):
            return
        if self.filtered(lambda user: not user.active):
            raise UserError(
                _("No es posible restablecer la contraseña de una cuenta inactiva.")
            )

        create_mode = bool(self.env.context.get("create_user"))
        expiration = False if create_mode else now(days=+1)
        self.mapped("partner_id").signup_prepare(
            signup_type="reset", expiration=expiration
        )

        template = False
        if create_mode:
            template = self.env.ref(
                "uta_transport_monitor.mail_template_georutex_set_password",
                raise_if_not_found=False,
            ) or self.env.ref(
                "auth_signup.set_password_email", raise_if_not_found=False
            )
        if not template:
            template = self.env.ref(
                "uta_transport_monitor.mail_template_georutex_reset_password",
                raise_if_not_found=False,
            ) or self.env.ref("auth_signup.reset_password_email")

        smtp_server = self.env["ir.mail_server"].sudo().search(
            [("active", "=", True)], order="sequence asc", limit=1
        )
        base_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "")
            .rstrip("/")
        )

        email_values = {
            "email_cc": False,
            "auto_delete": True,
            "message_type": "user_notification",
            "recipient_ids": [],
            "partner_ids": [],
            "scheduled_date": False,
        }
        if smtp_server:
            email_from = (
                smtp_server.from_filter
                or smtp_server.smtp_user
                or self.env.company.email
            )
            if email_from:
                email_values["email_from"] = email_from
            email_values["mail_server_id"] = smtp_server.id

        for user in self:
            if not user.email:
                raise UserError(
                    _("No se pudo enviar el correo: el usuario no tiene correo registrado.")
                )
            per_user_values = dict(email_values, email_to=user.email)
            reset_url = self._georutex_build_reset_url(user)
            with self.env.cr.savepoint():
                force_send = not self.env.context.get("import_file", False)
                template.sudo().with_context(
                    georutex_base_url=base_url,
                    georutex_reset_url=reset_url,
                ).send_mail(
                    user.id,
                    force_send=force_send,
                    raise_exception=True,
                    email_values=per_user_values,
                )
            _logger.info(
                "GeoRutex password reset email dispatched for %s",
                mask_email(user.email),
            )

    @api.model
    def _signup_create_user(self, values):
        """Validate payload and create least-privilege internal Driver user.

        Self-registered accounts are validated strictly (legitimate full name,
        valid email, strong password) and promoted exclusively to Internal User
        (base.group_user) + Conductor (group_transport_driver) in Spanish.
        """
        values = dict(values)
        if "partner_id" not in values:
            name = (values.get("name") or "").strip()
            ok, err = validate_full_name(name)
            if not ok:
                raise SignupError(err)
            values["name"] = name

            login = normalize_email(values.get("login") or "")
            ok, err = validate_email(login)
            if not ok:
                raise SignupError(err)
            values["login"] = login
            values["email"] = login

            password = values.get("password") or ""
            if password:
                ok, err = validate_strong_password(password)
                if not ok:
                    raise SignupError(err)

        user = super()._signup_create_user(values)
        group_portal = self.env.ref(
            "base.group_portal", raise_if_not_found=False
        )
        group_internal = self.env.ref(
            "base.group_user", raise_if_not_found=False
        )
        group_driver = self.env.ref(
            "uta_transport_monitor.group_transport_driver",
            raise_if_not_found=False,
        )

        group_commands = []
        if group_portal:
            group_commands.append((3, group_portal.id))
        if group_internal:
            group_commands.append((4, group_internal.id))
        if group_driver:
            group_commands.append((4, group_driver.id))

        update_vals = {"tz": "America/Guayaquil"}
        if group_commands:
            update_vals["groups_id"] = group_commands
        spanish_lang = self._georutex_default_spanish_lang()
        if spanish_lang:
            update_vals["lang"] = spanish_lang

        user.sudo().write(update_vals)
        return user
