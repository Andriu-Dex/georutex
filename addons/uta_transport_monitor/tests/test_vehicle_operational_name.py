"""Tests for fleet vehicle operational name and unit identification.

Verifies that:
1. Setting operational_name enriches vehicle.name with the bracketed alias.
2. Clearing operational_name falls back seamlessly to standard Odoo format.
3. Native name_search resolves vehicles by operational_name as well as plate.
"""

from odoo.tests import common


class TestVehicleOperationalName(common.TransactionCase):
    """Test suite for vehicle operational unit naming and resolution."""

    def setUp(self):
        super().setUp()
        self.brand = self.env["fleet.vehicle.model.brand"].create({
            "name": "Mercedes-Benz Test",
        })
        self.model = self.env["fleet.vehicle.model"].create({
            "name": "Sprinter Test",
            "brand_id": self.brand.id,
        })

    def test_01_operational_name_enriches_vehicle_name(self):
        """Ensure vehicle name includes bracketed unit name when provided."""
        vehicle = self.env["fleet.vehicle"].create({
            "model_id": self.model.id,
            "license_plate": "TBA-9001",
            "operational_name": "Bus 01 — UTA Huachi",
        })

        expected_prefix = "[Bus 01 — UTA Huachi]"
        self.assertIn(
            expected_prefix,
            vehicle.name,
            "El nombre del vehículo debe contener el nombre operativo entre corchetes.",
        )
        self.assertIn("TBA-9001", vehicle.name)
        self.assertIn("Sprinter Test", vehicle.name)

    def test_02_clearing_operational_name_falls_back(self):
        """Ensure clearing operational_name restores default Odoo format."""
        vehicle = self.env["fleet.vehicle"].create({
            "model_id": self.model.id,
            "license_plate": "TBA-9002",
            "operational_name": "Bus 02 — UTA Querochaca",
        })
        self.assertIn("[Bus 02 — UTA Querochaca]", vehicle.name)

        vehicle.write({"operational_name": False})
        self.assertNotIn("[", vehicle.name)
        self.assertIn("TBA-9002", vehicle.name)
        self.assertIn("Sprinter Test", vehicle.name)

    def test_03_name_search_by_operational_name(self):
        """Ensure native autocomplete / search finds vehicle by unit alias."""
        vehicle = self.env["fleet.vehicle"].create({
            "model_id": self.model.id,
            "license_plate": "TBA-9003",
            "operational_name": "Unidad Expreso 14",
        })

        # Search by operational name fragment
        results = self.env["fleet.vehicle"].name_search("Expreso 14")
        result_ids = [r[0] for r in results]
        self.assertIn(
            vehicle.id,
            result_ids,
            "La búsqueda por nombre operativo debe localizar el vehículo.",
        )

        # Search by license plate fragment
        results_plate = self.env["fleet.vehicle"].name_search("9003")
        result_ids_plate = [r[0] for r in results_plate]
        self.assertIn(
            vehicle.id,
            result_ids_plate,
            "La búsqueda por placa debe seguir funcionando.",
        )

