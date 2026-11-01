"""Native Odoo 16 tests for security roles and record rules."""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "security_roles")
class TestSecurityRoles(TransactionCase):
    """Test case for Role-Based Access Control and multi-group rules."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]
        self.position_model = self.env["transport.vehicle.position"]

        # Base Route and Version
        self.route = self.route_model.create({
            "name": "Ruta de Permisos",
            "code": "RUT-PERM-01",
            "origin_name": "Huachi",
            "destination_name": "Ingahurco",
            "direction": "outbound",
        })

        self.version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })
        for i in range(1, 5):
            self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": -1.26 + (i * 0.01),
                "longitude": -78.62,
            })
        self.version.action_approve()

        # Vehicles
        brand = self.env["fleet.vehicle.model.brand"].create(
            {"name": "TestBrand"}
        )
        model = self.env["fleet.vehicle.model"].create(
            {"name": "TestModel", "brand_id": brand.id}
        )

        # Partners
        self.partner_driver_a = self.env["res.partner"].create({
            "name": "Conductor A", "is_company": False
        })
        self.partner_driver_b = self.env["res.partner"].create({
            "name": "Conductor B", "is_company": False
        })

        self.vehicle_a = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "SEC-001",
            "driver_id": self.partner_driver_a.id,
        })
        self.vehicle_b = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "SEC-002",
            "driver_id": self.partner_driver_b.id,
        })

        # Users with distinct role groups
        grp_driver = self.env.ref(
            "uta_transport_monitor.group_transport_driver"
        )
        grp_analyst = self.env.ref(
            "uta_transport_monitor.group_transport_analyst"
        )
        grp_mgr = self.env.ref("uta_transport_monitor.group_transport_manager")
        grp_internal = self.env.ref("base.group_user")

        self.user_driver_a = self.env["res.users"].create({
            "name": "User Driver A",
            "login": "driver_a",
            "email": "driver_a@uta.edu.ec",
            "partner_id": self.partner_driver_a.id,
            "groups_id": [(6, 0, [grp_internal.id, grp_driver.id])],
        })

        self.user_driver_b = self.env["res.users"].create({
            "name": "User Driver B",
            "login": "driver_b",
            "email": "driver_b@uta.edu.ec",
            "partner_id": self.partner_driver_b.id,
            "groups_id": [(6, 0, [grp_internal.id, grp_driver.id])],
        })

        self.user_analyst = self.env["res.users"].create({
            "name": "User Analyst",
            "login": "analyst",
            "email": "analyst@uta.edu.ec",
            "groups_id": [(6, 0, [grp_internal.id, grp_analyst.id])],
        })

        self.user_manager = self.env["res.users"].create({
            "name": "User Manager",
            "login": "manager",
            "email": "manager@uta.edu.ec",
            "groups_id": [(6, 0, [grp_internal.id, grp_mgr.id])],
        })

        # Multi-group user (Driver + Analyst)
        self.user_multi = self.env["res.users"].create({
            "name": "User Multi Role",
            "login": "multi_role",
            "email": "multi@uta.edu.ec",
            "partner_id": self.partner_driver_a.id,
            "groups_id": [(6, 0, [
                grp_internal.id,
                grp_driver.id,
                grp_analyst.id,
            ])],
        })

        # Create trips for Driver A and Driver B
        self.trip_a = self.trip_model.create({
            "vehicle_id": self.vehicle_a.id,
            "driver_id": self.partner_driver_a.id,
            "driver_user_id": self.user_driver_a.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 08:00:00",
            "scheduled_end_utc": "2026-11-02 09:00:00",
        })
        self.trip_a.action_schedule()

        self.trip_b = self.trip_model.create({
            "vehicle_id": self.vehicle_b.id,
            "driver_id": self.partner_driver_b.id,
            "driver_user_id": self.user_driver_b.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 10:00:00",
            "scheduled_end_utc": "2026-11-02 11:00:00",
        })
        self.trip_b.action_schedule()

    def test_manager_full_access(self):
        """Manager has full create, read, write permissions."""
        trips = self.trip_model.with_user(self.user_manager).search([])
        self.assertIn(self.trip_a.id, trips.ids)
        self.assertIn(self.trip_b.id, trips.ids)

        # Manager can create new trip
        new_trip = self.trip_model.with_user(self.user_manager).create({
            "vehicle_id": self.vehicle_a.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 14:00:00",
            "scheduled_end_utc": "2026-11-02 15:00:00",
        })
        self.assertTrue(new_trip.id)

    def test_analyst_read_only_access(self):
        """Analyst can read all trips but cannot create or write."""
        trips = self.trip_model.with_user(self.user_analyst).search([])
        self.assertIn(self.trip_a.id, trips.ids)
        self.assertIn(self.trip_b.id, trips.ids)

        # Analyst cannot create trip
        with self.assertRaises(AccessError):
            self.trip_model.with_user(self.user_analyst).create({
                "vehicle_id": self.vehicle_a.id,
                "route_id": self.route.id,
                "route_version_id": self.version.id,
                "scheduled_start_utc": "2026-11-02 16:00:00",
                "scheduled_end_utc": "2026-11-02 17:00:00",
            })

    def test_driver_record_rule_isolation(self):
        """Driver can ONLY see their own assigned trips."""
        trips_a = self.trip_model.with_user(self.user_driver_a).search([])
        self.assertIn(self.trip_a.id, trips_a.ids)
        self.assertNotIn(self.trip_b.id, trips_a.ids)

        trips_b = self.trip_model.with_user(self.user_driver_b).search([])
        self.assertIn(self.trip_b.id, trips_b.ids)
        self.assertNotIn(self.trip_a.id, trips_b.ids)

    def test_multi_group_security_resolution(self):
        """User with Driver + Analyst roles sees all trips via analyst."""
        multi_trips = self.trip_model.with_user(self.user_multi).search([])
        self.assertIn(self.trip_a.id, multi_trips.ids)
        self.assertIn(self.trip_b.id, multi_trips.ids)
