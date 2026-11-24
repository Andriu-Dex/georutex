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
        info["georutex_can_manage_apps"] = bool(is_system)
        info["georutex_is_driver_only"] = bool(
            is_driver and not (is_system or is_manager or is_analyst)
        )
        return info
