"""Native tests for automatic trip scheduling, planned durations, and time consistency."""

from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_trip")
class TestTripScheduleAutomation(TransactionCase):
    """Test suite for automated trip schedule calculations, midnight rollover, and overrides."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]

        # Base route RUT-PF-001
        self.route = self.route_model.create({
            "name": "Circuito de Prueba Física Huachi",
            "code": "RUT-PF-001",
            "origin_name": "Santa Rosa Park",
            "destination_name": "Campus Huachi",
            "direction": "outbound",
        })

        # Version 1 with 4 stops: 0s, 1080s, 1440s, 1800s (30 minutes total)
        self.version_1 = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
            "estimated_distance_m": 7860.0,
        })

        self.stops_v1 = [
            self.stop_model.create({
                "route_version_id": self.version_1.id,
                "sequence": 10,
                "name": "Santa Rosa Park — acceso vial",
                "stop_type": "origin",
                "latitude": -1.282294,
                "longitude": -78.663491,
                "planned_offset_seconds": 0,
            }),
            self.stop_model.create({
                "route_version_id": self.version_1.id,
                "sequence": 20,
                "name": "Redondel de Huachi Chico",
                "stop_type": "checkpoint",
                "latitude": -1.275550,
                "longitude": -78.630674,
                "planned_offset_seconds": 1080,
            }),
            self.stop_model.create({
                "route_version_id": self.version_1.id,
                "sequence": 30,
                "name": "Mall de los Andes",
                "stop_type": "checkpoint",
                "latitude": -1.265074,
                "longitude": -78.627664,
                "planned_offset_seconds": 1440,
            }),
            self.stop_model.create({
                "route_version_id": self.version_1.id,
                "sequence": 40,
                "name": "UTA — Campus Huachi",
                "stop_type": "destination",
                "latitude": -1.268609,
                "longitude": -78.625949,
                "planned_offset_seconds": 1800,
            }),
        ]
        self.version_1.action_approve()

        # Fleet vehicle & Driver
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Mercedes"})
        model = self.env["fleet.vehicle.model"].create({
            "name": "Sprinter",
            "brand_id": brand.id,
        })
        self.driver = self.env["res.partner"].create({
            "name": "Conductor Carlos Morales",
            "is_company": False,
        })
        self.vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "TBA-1001",
            "driver_id": self.driver.id,
        })

        # Users for RBAC tests
        self.user_manager = self.env["res.users"].create({
            "name": "Gestor de Rutas Test",
            "login": "manager_schedule_test",
            "email": "mgr_sched@uta.edu.ec",
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_manager").id])],
        })
        self.user_driver = self.env["res.users"].create({
            "name": "Conductor Simple Test",
            "login": "driver_schedule_test",
            "email": "driver_sched@uta.edu.ec",
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_driver").id])],
        })

    def test_01_duration_calculated_from_destination_stop(self):
        """Verify version duration is 1800s and trip end is start + 1800s."""
        self.assertEqual(self.version_1.planned_duration_s, 1800)
        self.assertEqual(self.version_1.planned_duration_display, "30 min")

        # Create trip specifying only start time (07:09:16)
        start_dt = datetime(2026, 11, 4, 7, 9, 16)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_dt,
        })

        # scheduled_end_utc must automatically be 07:39:16
        expected_end = datetime(2026, 11, 4, 7, 39, 16)
        self.assertEqual(trip.scheduled_end_utc, expected_end)
        self.assertEqual(trip.scheduled_duration_s, 1800)
        self.assertEqual(trip.scheduled_duration_display, "30 min")

    def test_02_recalculation_on_start_time_change(self):
        """Verify modifying scheduled start automatically recalculates scheduled end."""
        start_1 = datetime(2026, 11, 4, 7, 9, 16)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_1,
        })
        self.assertEqual(trip.scheduled_end_utc, datetime(2026, 11, 4, 7, 39, 16))

        # Change start time to 08:15:00
        start_2 = datetime(2026, 11, 4, 8, 15, 0)
        trip.write({"scheduled_start_utc": start_2})
        self.assertEqual(trip.scheduled_end_utc, datetime(2026, 11, 4, 8, 45, 0))

    def test_03_recalculation_on_version_change(self):
        """Verify changing route version recalculates duration and end time."""
        # Create Version 2 with duration of 2400s (40 min)
        v2 = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 2,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
            "estimated_distance_m": 10200.0,
        })
        offsets = [0, 800, 1600, 2400]
        for i, off in enumerate(offsets, start=1):
            stype = "origin" if i == 1 else ("destination" if i == 4 else "checkpoint")
            self.stop_model.create({
                "route_version_id": v2.id,
                "sequence": i * 10,
                "name": f"Punto v2-{i}",
                "stop_type": stype,
                "latitude": -1.26 + (i * 0.005),
                "longitude": -78.62,
                "planned_offset_seconds": off,
            })
        v2.action_approve()
        self.assertEqual(v2.planned_duration_s, 2400)

        # Trip starts with v1 (30 min)
        start_dt = datetime(2026, 11, 4, 7, 0, 0)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_dt,
        })
        self.assertEqual(trip.scheduled_end_utc, datetime(2026, 11, 4, 7, 30, 0))

        # Switch to v2 (40 min)
        trip.write({"route_version_id": v2.id})
        self.assertEqual(trip.scheduled_end_utc, datetime(2026, 11, 4, 7, 40, 0))
        self.assertEqual(trip.scheduled_duration_s, 2400)

    def test_04_non_progressive_or_negative_offsets_rejected_on_approve(self):
        """Verify non-progressive or negative stop offsets raise ValidationError."""
        v_invalid = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 3,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })
        # Checkpoint 3 has 800s, but checkpoint 2 has 1200s (non-progressive)
        self.stop_model.create({
            "route_version_id": v_invalid.id,
            "sequence": 10,
            "name": "P1",
            "stop_type": "origin",
            "latitude": -1.26,
            "longitude": -78.62,
            "planned_offset_seconds": 0,
        })
        self.stop_model.create({
            "route_version_id": v_invalid.id,
            "sequence": 20,
            "name": "P2",
            "stop_type": "checkpoint",
            "latitude": -1.25,
            "longitude": -78.62,
            "planned_offset_seconds": 1200,
        })
        self.stop_model.create({
            "route_version_id": v_invalid.id,
            "sequence": 30,
            "name": "P3",
            "stop_type": "checkpoint",
            "latitude": -1.24,
            "longitude": -78.62,
            "planned_offset_seconds": 800,  # Non-progressive!
        })
        self.stop_model.create({
            "route_version_id": v_invalid.id,
            "sequence": 40,
            "name": "P4",
            "stop_type": "destination",
            "latitude": -1.23,
            "longitude": -78.62,
            "planned_offset_seconds": 1800,
        })

        with self.assertRaises(ValidationError) as cm:
            v_invalid.action_approve()
        self.assertIn("Tiempos no progresivos", str(cm.exception))

    def test_05_stop_visits_match_scheduled_times(self):
        """Verify stop visits generated on schedule have exact progressive times."""
        start_dt = datetime(2026, 11, 4, 7, 9, 16)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_dt,
        })
        trip.action_schedule()

        visits = trip.stop_visit_ids.sorted("sequence")
        self.assertEqual(len(visits), 4)

        # Stop 1 (Origin, 0s): 07:09:16
        self.assertEqual(visits[0].scheduled_at_utc, datetime(2026, 11, 4, 7, 9, 16))
        # Stop 2 (Control 1, 1080s): 07:27:16
        self.assertEqual(visits[1].scheduled_at_utc, datetime(2026, 11, 4, 7, 27, 16))
        # Stop 3 (Control 2, 1440s): 07:33:16
        self.assertEqual(visits[2].scheduled_at_utc, datetime(2026, 11, 4, 7, 33, 16))
        # Stop 4 (Destination, 1800s): 07:39:16
        self.assertEqual(visits[3].scheduled_at_utc, datetime(2026, 11, 4, 7, 39, 16))
        self.assertEqual(visits[3].scheduled_at_utc, trip.scheduled_end_utc)

    def test_06_midnight_crossing_scheduling(self):
        """Verify scheduling crossing midnight computes correct date and time."""
        # Starts at 23:45:00 on Nov 4, finishes at 00:15:00 on Nov 5
        start_dt = datetime(2026, 11, 4, 23, 45, 0)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_dt,
        })
        expected_end = datetime(2026, 11, 5, 0, 15, 0)
        self.assertEqual(trip.scheduled_end_utc, expected_end)

        trip.action_schedule()
        visits = trip.stop_visit_ids.sorted("sequence")
        self.assertEqual(visits[-1].scheduled_at_utc, expected_end)

    def test_07_manual_override_permissions_and_reason(self):
        """Verify manual override requires manager role and justification."""
        start_dt = datetime(2026, 11, 4, 7, 9, 16)
        trip = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version_1.id,
            "scheduled_start_utc": start_dt,
            "is_manual_duration_override": True,
            "scheduled_end_utc": datetime(2026, 11, 4, 7, 52, 16),  # 43 min
        })

        # Attempt to schedule without justification must fail
        with self.assertRaises(ValidationError):
            trip.with_user(self.user_manager).action_schedule()

        # Non-manager cannot authorize manual override
        trip.manual_duration_override_reason = "Contingencia por cierre vial"
        with self.assertRaises(UserError):
            trip.with_user(self.user_driver).action_schedule()

        # Manager with justification succeeds
        trip.with_user(self.user_manager).action_schedule()
        self.assertEqual(trip.state, "scheduled")
        self.assertEqual(trip.manual_duration_override_user_id.id, self.user_manager.id)
        self.assertEqual(trip.scheduled_end_utc, datetime(2026, 11, 4, 7, 52, 16))

