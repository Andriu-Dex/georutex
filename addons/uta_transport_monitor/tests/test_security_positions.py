"""Native Odoo 16 tests for record rules on positions and map security."""

from datetime import datetime
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_security_pos")
class TestSecurityPositions(TransactionCase):
    """Test suite for position record rules and authorization boundaries."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]
        self.pos_model = self.env["transport.vehicle.position"]
        self.vehicle_model = self.env["fleet.vehicle"]

        # Setup route and version
        self.route = self.route_model.create({
            "name": "Ruta Seguridad",
            "code": "RUT-SEC-01",
            "origin_name": "Origen",
            "destination_name": "Destino",
        })
        self.version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
        })
        for i in range(1, 5):
            stype = (
                "origin" if i == 1
                else ("destination" if i == 4 else "checkpoint")
            )
            self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": -1.25 + (i * 0.005),
                "longitude": -78.62,
                "stop_type": stype,
            })
        self.version.action_approve()

        # Groups
        self.group_driver = self.env.ref(
            "uta_transport_monitor.group_transport_driver"
        )
        self.group_analyst = self.env.ref(
            "uta_transport_monitor.group_transport_analyst"
        )

        # Users
        self.user_driver_a = self.env["res.users"].create({
            "name": "Conductor Alpha",
            "login": "driver_alpha@uta.edu.ec",
            "email": "driver_alpha@uta.edu.ec",
            "groups_id": [(6, 0, [self.group_driver.id])],
        })
        self.user_driver_b = self.env["res.users"].create({
            "name": "Conductor Beta",
            "login": "driver_beta@uta.edu.ec",
            "email": "driver_beta@uta.edu.ec",
            "groups_id": [(6, 0, [self.group_driver.id])],
        })
        self.user_analyst = self.env["res.users"].create({
            "name": "Analista Monitoreo",
            "login": "analyst_sec@uta.edu.ec",
            "email": "analyst_sec@uta.edu.ec",
            "groups_id": [(6, 0, [self.group_analyst.id])],
        })

        # Vehicles
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Volvo"})
        model = self.env["fleet.vehicle.model"].create({
            "name": "B12R",
            "brand_id": brand.id,
        })
        self.vehicle_a = self.vehicle_model.create({
            "model_id": model.id,
            "license_plate": "TBA-SEC-A",
            "driver_id": self.user_driver_a.partner_id.id,
            "is_simulated": True,
        })
        self.vehicle_b = self.vehicle_model.create({
            "model_id": model.id,
            "license_plate": "TBA-SEC-B",
            "driver_id": self.user_driver_b.partner_id.id,
            "is_simulated": True,
        })

        # Trip A for Driver A
        self.trip_a = self.trip_model.create({
            "vehicle_id": self.vehicle_a.id,
            "driver_id": self.user_driver_a.partner_id.id,
            "driver_user_id": self.user_driver_a.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 1, 8, 0, 0),
            "scheduled_end_utc": datetime(2026, 11, 1, 9, 0, 0),
            "source_type": "simulated",
        })
        self.trip_a.action_schedule()

        # Position associated to Trip A
        self.pos_a = self.pos_model.create({
            "vehicle_id": self.vehicle_a.id,
            "trip_id": self.trip_a.id,
            "association_status": "associated",
            "fix_time": datetime(2026, 11, 1, 8, 30, 0),
            "latitude": -1.252,
            "longitude": -78.621,
            "speed": 25.0,
            "source": "simulated",
        })

        # Trip B for Driver B
        self.trip_b = self.trip_model.create({
            "vehicle_id": self.vehicle_b.id,
            "driver_id": self.user_driver_b.partner_id.id,
            "driver_user_id": self.user_driver_b.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 1, 10, 0, 0),
            "scheduled_end_utc": datetime(2026, 11, 1, 11, 0, 0),
            "source_type": "simulated",
        })
        self.trip_b.action_schedule()

        # Position associated to Trip B
        self.pos_b = self.pos_model.create({
            "vehicle_id": self.vehicle_b.id,
            "trip_id": self.trip_b.id,
            "association_status": "associated",
            "fix_time": datetime(2026, 11, 1, 10, 30, 0),
            "latitude": -1.254,
            "longitude": -78.622,
            "speed": 30.0,
            "source": "simulated",
        })

    def test_driver_can_only_read_own_trip_positions(self):
        """Driver sees position of Trip A, cannot see Trip B (CP-12)."""
        pos_model_as_driver_a = self.pos_model.with_user(self.user_driver_a)
        positions = pos_model_as_driver_a.search([])

        self.assertIn(self.pos_a.id, positions.ids)
        self.assertNotIn(self.pos_b.id, positions.ids)

    def test_driver_cannot_call_get_map_data_on_other_driver_trip(self):
        """Driver A calling get_map_data() on Trip B raises AccessError."""
        trip_b_as_driver_a = self.trip_model.with_user(
            self.user_driver_a
        ).browse(self.trip_b.id)
        with self.assertRaises(AccessError):
            trip_b_as_driver_a.get_map_data()

    def test_analyst_can_read_all_positions_and_map_data(self):
        """Analyst has global read visibility on all positions and trips."""
        pos_model_as_analyst = self.pos_model.with_user(self.user_analyst)
        positions = pos_model_as_analyst.search([])
        self.assertIn(self.pos_a.id, positions.ids)
        self.assertIn(self.pos_b.id, positions.ids)

        trip_a_as_analyst = self.trip_model.with_user(
            self.user_analyst
        ).browse(self.trip_a.id)
        payload = trip_a_as_analyst.get_map_data()
        self.assertEqual(payload["trip_id"], self.trip_a.id)
