"""Native Odoo 16 tests for trip scheduling and lifecycle."""

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_trip")
class TestTripScheduling(TransactionCase):
    """Test case for trips, assignment overlaps, snapshots, and lifecycle."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]

        # 1. Base route with approved version and 4 checkpoints
        self.route = self.route_model.create({
            "name": "Ruta Troncal Huachi - Ingahurco",
            "code": "RUT-TRONCAL-01",
            "origin_name": "Campus Huachi",
            "destination_name": "Campus Ingahurco",
            "direction": "outbound",
        })

        self.version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 35.0,
            "route_corridor_m": 45.0,
            "lateness_tolerance_s": 240,
            "gps_gap_threshold_s": 150,
            "estimated_distance_m": 4500.0,
        })

        for i in range(1, 5):
            stype = (
                "origin" if i == 1
                else ("destination" if i == 4 else "checkpoint")
            )
            self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Control {i}",
                "latitude": -1.26 + (i * 0.01),
                "longitude": -78.62,
                "planned_offset_seconds": (i - 1) * 300,
                "stop_type": stype,
            })

        self.version.action_approve()

        # 2. Vehicles and Drivers
        brand = self.env["fleet.vehicle.model.brand"].create(
            {"name": "Mercedes"}
        )
        model = self.env["fleet.vehicle.model"].create(
            {"name": "Sprinter", "brand_id": brand.id}
        )

        self.driver_1 = self.env["res.partner"].create({
            "name": "Conductor Test 1",
            "is_company": False,
        })
        self.driver_2 = self.env["res.partner"].create({
            "name": "Conductor Test 2",
            "is_company": False,
        })

        self.vehicle_1 = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "UTA-001",
            "driver_id": self.driver_1.id,
        })
        self.vehicle_2 = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "UTA-002",
            "driver_id": self.driver_2.id,
        })

    def test_trip_scheduling_and_parameter_snapshot(self):
        """RF-14: Scheduling freezes parameters and creates visits."""
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 08:00:00",
            "scheduled_end_utc": "2026-11-02 09:00:00",
        })

        self.assertEqual(trip.state, "draft")
        self.assertFalse(trip.parameter_snapshot_json)
        self.assertEqual(len(trip.stop_visit_ids), 0)

        # Transition to scheduled
        trip.action_schedule()

        self.assertEqual(trip.state, "scheduled")
        self.assertTrue(trip.parameter_snapshot_json)
        self.assertEqual(trip.stop_radius_m, 35.0)
        self.assertEqual(trip.route_corridor_m, 45.0)
        self.assertEqual(trip.lateness_tolerance_s, 240)
        self.assertEqual(trip.gps_gap_threshold_s, 150)

        # Verify stop visits were generated
        self.assertEqual(len(trip.stop_visit_ids), 4)
        origin_visit = trip.stop_visit_ids[0]
        self.assertEqual(origin_visit.stop_name, "Control 1")
        self.assertEqual(origin_visit.status, "pending")

    def test_scheduled_times_chronological_validation(self):
        """Scheduled start must strictly precede scheduled end."""
        with self.assertRaises(ValidationError):
            self.trip_model.create({
                "vehicle_id": self.vehicle_1.id,
                "route_id": self.route.id,
                "route_version_id": self.version.id,
                "scheduled_start_utc": "2026-11-02 10:00:00",
                "scheduled_end_utc": "2026-11-02 09:00:00",
            })

    def test_vehicle_assignment_overlap_conflict(self):
        """RF-12: The same vehicle cannot have overlapping trips."""
        trip1 = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 08:00:00",
            "scheduled_end_utc": "2026-11-02 09:00:00",
        })
        trip1.action_schedule()

        # Overlapping trip on same vehicle (08:30 - 09:30)
        trip2 = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_2.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 08:30:00",
            "scheduled_end_utc": "2026-11-02 09:30:00",
        })

        with self.assertRaises(ValidationError):
            trip2.action_schedule()

    def test_non_overlapping_trips_same_vehicle_succeed(self):
        """RF-12: A vehicle can perform non-overlapping trips on same day."""
        # Morning trip: 08:00 - 09:00
        trip1 = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 08:00:00",
            "scheduled_end_utc": "2026-11-02 09:00:00",
        })
        trip1.action_schedule()

        # Afternoon trip: 13:00 - 14:00 (non-overlapping)
        trip2 = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 13:00:00",
            "scheduled_end_utc": "2026-11-02 14:00:00",
        })
        trip2.action_schedule()
        self.assertEqual(trip2.state, "scheduled")

    def test_driver_assignment_overlap_conflict(self):
        """RF-12: A driver cannot be assigned to overlapping trips."""
        trip1 = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 10:00:00",
            "scheduled_end_utc": "2026-11-02 11:30:00",
        })
        trip1.action_schedule()

        # Different vehicle, but same driver in overlapping window
        trip2 = self.trip_model.create({
            "vehicle_id": self.vehicle_2.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 11:00:00",
            "scheduled_end_utc": "2026-11-02 12:00:00",
        })

        with self.assertRaises(ValidationError):
            trip2.action_schedule()

    def test_trip_operational_lifecycle(self):
        """RF-13: Operational state transitions and restrictions."""
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle_1.id,
            "driver_id": self.driver_1.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-11-02 15:00:00",
            "scheduled_end_utc": "2026-11-02 16:00:00",
        })

        # Cannot jump from draft to completed
        with self.assertRaises(UserError):
            trip.action_complete()

        # Valid lifecycle: draft -> scheduled -> in_progress -> completed
        trip.action_schedule()
        self.assertEqual(trip.state, "scheduled")

        trip.action_start()
        self.assertEqual(trip.state, "in_progress")
        self.assertTrue(trip.actual_start_utc)

        trip.action_complete()
        self.assertEqual(trip.state, "completed")
        self.assertTrue(trip.actual_end_utc)

        # Cannot cancel or revert completed trip
        with self.assertRaises(UserError):
            trip.action_cancel()
        with self.assertRaises(UserError):
            trip.action_set_to_draft()
