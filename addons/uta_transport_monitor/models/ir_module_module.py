"""Restrict Odoo Apps installation/upgrade actions to System Administrators."""

from odoo import models
from odoo.exceptions import AccessError


class IrModuleModule(models.Model):
    """Enforce server-side restriction preventing non-admins from managing apps."""

    _inherit = "ir.module.module"

    def _check_georutex_app_admin(self):
        """Raise AccessError unless current user is System Administrator."""
        if not self.env.is_superuser() and not self.env.user.has_group(
            "base.group_system"
        ):
            raise AccessError(
                "Acceso denegado: solo el administrador del sistema puede "
                "administrar, instalar o desinstalar aplicaciones en GeoRutex."
            )

    def button_install(self):
        self._check_georutex_app_admin()
        return super().button_install()

    def button_immediate_install(self):
        self._check_georutex_app_admin()
        return super().button_immediate_install()

    def button_upgrade(self):
        self._check_georutex_app_admin()
        return super().button_upgrade()

    def button_immediate_upgrade(self):
        self._check_georutex_app_admin()
        return super().button_immediate_upgrade()

    def button_uninstall(self):
        self._check_georutex_app_admin()
        return super().button_uninstall()

    def button_immediate_uninstall(self):
        self._check_georutex_app_admin()
        return super().button_immediate_uninstall()
