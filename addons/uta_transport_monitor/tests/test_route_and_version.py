"""Native Odoo 16 tests for routes, versions, and checkpoints."""

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_route")
class TestRouteAndVersion(TransactionCase):
    """Test case for route management, versions, and checkpoints."""

    def setUp(self):
        super().setUp()
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]

        # Create base test route
        self.route = self.route_model.create({
            "name": "Ruta de Prueba Huachi - Ingahurco",
            "code": "RUT-TEST-01",
            "origin_name": "Campus Huachi",
            "destination_name": "Campus Ingahurco",
            "direction": "outbound",
        })

    def test_route_code_uniqueness(self):
        """RF-09: Route code must be unique across the catalog."""
        with self.assertRaises(Exception):
            self.route_model.create({
                "name": "Ruta Duplicada",
                "code": "RUT-TEST-01",
                "origin_name": "Campus Huachi",
                "destination_name": "Campus Ingahurco",
            })

    def test_route_origin_destination_validation(self):
        """Origin and destination cannot be identical unless circular."""
        with self.assertRaises(ValidationError):
            self.route_model.create({
                "name": "Ruta Invalida",
                "code": "RUT-TEST-INV",
                "origin_name": "Campus Huachi",
                "destination_name": "Campus Huachi",
                "direction": "outbound",
            })

        # Circular route with identical origin/destination is allowed
        circular_route = self.route_model.create({
            "name": "Ruta Circular",
            "code": "RUT-TEST-CIRC",
            "origin_name": "Campus Huachi",
            "destination_name": "Campus Huachi",
            "direction": "circular",
        })
        self.assertTrue(circular_route.id)

    def test_canonical_parameters_validation(self):
        """Section 7.1: Canonical parameters sanity checks."""
        # Non-positive stop_radius_m raises ValidationError
        with self.assertRaises(ValidationError):
            self.version_model.create({
                "route_id": self.route.id,
                "version_number": 1,
                "stop_radius_m": 0.0,
            })

        # Negative lateness_tolerance_s raises ValidationError
        with self.assertRaises(ValidationError):
            self.version_model.create({
                "route_id": self.route.id,
                "version_number": 1,
                "lateness_tolerance_s": -10,
            })

    def test_version_approval_requires_minimum_checkpoints(self):
        """RF-10: Route approval requires at least 4 checkpoints / stops."""
        version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })

        # Add only 3 checkpoints
        for i in range(1, 4):
            self.stop_model.create({
                "route_version_id": version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": -1.26 + (i * 0.01),
                "longitude": -78.62,
                "stop_type": "checkpoint",
            })

        # Attempt to approve with 3 stops must fail
        with self.assertRaises(ValidationError):
            version.action_approve()

        # Add 4th checkpoint
        self.stop_model.create({
            "route_version_id": version.id,
            "sequence": 40,
            "name": "Punto 4 Destino",
            "latitude": -1.23,
            "longitude": -78.62,
            "stop_type": "destination",
        })

        # Now approval succeeds
        version.action_approve()
        self.assertEqual(version.state, "approved")
        self.assertTrue(version.approved_at)
        self.assertEqual(self.route.current_version_id.id, version.id)

    def test_polyline_distance_calculation(self):
        """Test calculation of distance from polyline JSON."""
        poly = (
            "[[-78.6272, -1.2618], [-78.6250, -1.2580], [-78.6225, -1.2335]]"
        )
        version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "reference_polyline": poly,
        })
        version.action_compute_distance_from_polyline()
        self.assertGreater(version.estimated_distance_m, 3000.0)

    def test_checkpoint_coordinate_and_sequence_validation(self):
        """Checkpoints must validate coordinates and sequence uniqueness."""
        version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
        })

        # Invalid latitude out of [-90, 90]
        with self.assertRaises(ValidationError):
            self.stop_model.create({
                "route_version_id": version.id,
                "sequence": 10,
                "name": "Punto Fuera de Rango",
                "latitude": 95.0,
                "longitude": -78.62,
            })

        # Duplicate sequence within the same version
        self.stop_model.create({
            "route_version_id": version.id,
            "sequence": 10,
            "name": "Punto 1",
            "latitude": -1.26,
            "longitude": -78.62,
        })
        with self.assertRaises(Exception):
            self.stop_model.create({
                "route_version_id": version.id,
                "sequence": 10,
                "name": "Punto 1 Duplicado",
                "latitude": -1.25,
                "longitude": -78.62,
            })

    def test_approved_version_with_trips_immutability(self):
        """RF-14: Versions with trips cannot be edited destructively."""
        version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })
        for i in range(1, 5):
            self.stop_model.create({
                "route_version_id": version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": -1.26 + (i * 0.01),
                "longitude": -78.62,
            })
        version.action_approve()

        # Create fleet vehicle and schedule trip
        brand = self.env["fleet.vehicle.model.brand"].create(
            {"name": "TestBrand"}
        )
        model = self.env["fleet.vehicle.model"].create(
            {"name": "TestModel", "brand_id": brand.id}
        )
        vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "IMM-001",
        })

        trip = self.env["transport.trip"].create({
            "vehicle_id": vehicle.id,
            "route_id": self.route.id,
            "route_version_id": version.id,
            "scheduled_start_utc": "2026-11-02 10:00:00",
            "scheduled_end_utc": "2026-11-02 11:00:00",
        })
        trip.action_schedule()

        # Attempt to modify frozen parameters on version must raise UserError
        with self.assertRaises(UserError):
            version.write({"route_corridor_m": 80.0})

        # Attempt to add new stop to frozen version must raise UserError
        with self.assertRaises(UserError):
            self.stop_model.create({
                "route_version_id": version.id,
                "sequence": 50,
                "name": "Punto Nuevo Ilegal",
                "latitude": -1.20,
                "longitude": -78.62,
            })
