"""Tests for demo dataset safety guards and scoped record cleanup.

Verifies that cleanup operations refuse execution on operational databases
and strictly preserve operational trips and real telemetry when running.
"""

from datetime import datetime
from odoo.tests import common
from ..services.demo_safety import (
    validate_target_database,
    cleanup_demo_dataset,
)


class TestDemoSafety(common.TransactionCase):
    """Test suite for demo seeding safety boundaries and scoped unlinking."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.pos_model = self.env["transport.vehicle.position"]
        self.partner_driver = self.env.ref(
            "uta_transport_monitor.demo_driver_carlos"
        )
        self.route = self.env.ref("uta_transport_monitor.demo_route_1")
        self.vehicle_real = self.env.ref(
            "uta_transport_monitor.demo_vehicle_01_real"
        )
        self.vehicle_sim = self.env.ref(
            "uta_transport_monitor.demo_vehicle_02_sim"
        )

    def test_01_operational_database_rejection(self):
        """Refuse execution immediately when targeting operational database."""
        with self.assertRaises(ValueError):
            validate_target_database("georutex")

        with self.assertRaises(ValueError):
            cleanup_demo_dataset(self.env, db_name="georutex")

    def test_02_scoped_cleanup_preserves_operational_data(self):
        """Ensure cleanup unlinks ONLY demo-scoped records, keeping ops intact.
        """
        version = self.route.current_version_id
        if not version:
            version = self.env["transport.route.version"].search([
                ("route_id", "=", self.route.id)
            ], limit=1)
        if not version or version.state != "approved":
            version = self.env["transport.route.version"].create({
                "route_id": self.route.id,
                "version_number": 99,
                "stop_radius_m": 40.0,
                "route_corridor_m": 50.0,
            })
            for i in range(1, 5):
                stype = (
                    "origin" if i == 1
                    else ("destination" if i == 4 else "checkpoint")
                )
                self.env["transport.route.stop"].create({
                    "route_version_id": version.id,
                    "sequence": i * 10,
                    "name": f"Control {i}",
                    "latitude": -1.26 + (i * 0.005),
                    "longitude": -78.62,
                    "planned_offset_seconds": (i - 1) * 300,
                    "stop_type": stype,
                })
            version.action_approve()

        now = datetime(2026, 11, 20, 10, 0, 0)
        end_time = datetime(2026, 11, 20, 10, 30, 0)

        # 1. Create an operational trip with non-demo name and real telemetry
        ops_trip = self.trip_model.create({
            "name": "REC-OPERATIONAL-2026-ROUTE1",
            "vehicle_id": self.vehicle_real.id,
            "route_id": self.route.id,
            "route_version_id": version.id,
            "driver_id": self.partner_driver.id,
            "scheduled_start_utc": now,
            "scheduled_end_utc": end_time,
            "source_type": "real",
            "state": "completed",
        })
        ops_pos = self.pos_model.create({
            "trip_id": ops_trip.id,
            "vehicle_id": self.vehicle_real.id,
            "latitude": -1.2693,
            "longitude": -78.6272,
            "speed": 30.0,
            "fix_time": now,
            "source": "real",
            "is_valid": True,
        })

        # 2. Create a demo trip with REC-DEMO prefix and simulated telemetry
        demo_trip = self.trip_model.create({
            "name": "REC-DEMO-SAMPLE-GUARDTEST",
            "vehicle_id": self.vehicle_sim.id,
            "route_id": self.route.id,
            "route_version_id": version.id,
            "driver_id": self.partner_driver.id,
            "scheduled_start_utc": now,
            "scheduled_end_utc": end_time,
            "source_type": "simulated",
            "state": "completed",
        })
        demo_pos = self.pos_model.create({
            "trip_id": demo_trip.id,
            "vehicle_id": self.vehicle_sim.id,
            "latitude": -1.2690,
            "longitude": -78.6270,
            "speed": 35.0,
            "fix_time": now,
            "source": "simulated",
            "is_valid": True,
        })
        # Telemetry with source='real' attached to the demo trip (edge case)
        demo_pos_real = self.pos_model.create({
            "trip_id": demo_trip.id,
            "vehicle_id": self.vehicle_real.id,
            "latitude": -1.2685,
            "longitude": -78.6265,
            "speed": 28.0,
            "fix_time": now,
            "source": "real",
            "is_valid": True,
        })

        # 3. Execute scoped cleanup for demo database
        res = cleanup_demo_dataset(self.env, db_name="georutex_demo")

        self.assertGreaterEqual(res["trips_deleted"], 1)
        self.assertGreaterEqual(res["positions_deleted"], 1)

        # 4. Assert demo trip and simulated demo pos are unlinked
        self.assertFalse(demo_trip.exists())
        self.assertFalse(demo_pos.exists())

        # 5. Assert real telemetry linked to demo trip is STRICTLY PRESERVED
        self.assertTrue(
            demo_pos_real.exists(),
            "La telemetría real (source='real') vinculada a un recorrido demo "
            "no debe ser eliminada por la limpieza.",
        )

        # 6. Assert operational trip and operational telemetry are PRESERVED
        self.assertTrue(
            ops_trip.exists(),
            "El viaje operacional no debe ser eliminado por la limpieza demo.",
        )
        self.assertTrue(
            ops_pos.exists(),
            "La telemetría real del viaje operacional no debe ser eliminada.",
        )
