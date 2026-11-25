"""Expose GeoRutex role flags in Odoo web session info for UI restrictions."""

from odoo import models


class IrHttp(models.AbstractModel):
    """Attach role capability flags to frontend session metadata."""

    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        is_system = user.has_group("base.group_system")
        is_manager = user.has_group(
            "uta_transport_monitor.group_transport_manager"
        )
        is_analyst = user.has_group(
            "uta_transport_monitor.group_transport_analyst"
        )
        is_driver = user.has_group(
            "uta_transport_monitor.group_transport_driver"
        )
        is_driver_only = bool(
            is_driver and not (is_system or is_manager or is_analyst)
        )
        is_analyst_only = bool(is_analyst and not (is_system or is_manager))

        if is_system or is_manager:
            role_key = "admin"
            role_label = "Administrador"
        elif is_analyst:
            role_key = "analyst"
            role_label = "Analista"
        elif is_driver:
            role_key = "driver"
            role_label = "Conductor"
        else:
            role_key = "user"
            role_label = "Usuario"

        info["georutex_can_manage_apps"] = bool(is_system)
        info["georutex_is_manager"] = bool(is_system or is_manager)
        info["georutex_is_driver_only"] = is_driver_only
        info["georutex_is_analyst_only"] = is_analyst_only
        info["georutex_role"] = role_key
        info["georutex_role_label"] = role_label
        return info
