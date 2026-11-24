"""Extension of res.users to provision GeoRutex driver accounts on signup."""

from odoo import api, models
from odoo.addons.auth_signup.models.res_partner import SignupError

from ..domain.auth_validation import (
    normalize_email,
    validate_email,
    validate_full_name,
    validate_strong_password,
)


class ResUsers(models.Model):
    """Provision self-registered accounts as GeoRutex internal drivers."""

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
    def _signup_create_user(self, values):
        """Validate payload and create least-privilege internal Driver user.

        Odoo's default auth_signup clones the portal template user
        (base.group_portal, share=True), which redirects to
        /web/login_successful when website/portal is not installed and blocks
        access to GeoRutex.

        Self-registered accounts are validated strictly (Title Case letters-only
        name, valid email, strong password) and promoted exclusively to Internal
        User (base.group_user) + Conductor (group_transport_driver) in Spanish
        (es_EC / America/Guayaquil).
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
