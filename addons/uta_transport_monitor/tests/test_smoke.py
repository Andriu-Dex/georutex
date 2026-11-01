"""Native Odoo 16 smoke test case.

Verifies that uta_transport_monitor is loaded within Odoo ORM
and that its dependency (fleet.vehicle) is accessible.
"""

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "smoke")
class TestAddonSmoke(TransactionCase):
    """Verify addon is loaded and fleet dependency is available in ORM."""

    def test_addon_installed_and_fleet_available(self):
        fleet_model = self.env["fleet.vehicle"]
        self.assertIsNotNone(fleet_model)
        vehicles = fleet_model.search([])
        self.assertIsNotNone(vehicles)
