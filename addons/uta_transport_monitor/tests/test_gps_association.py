"""Native Odoo 16 tests for GPS position to trip association and map data."""

from datetime import datetime
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_gps_assoc")
class TestGpsAssociation(TransactionCase):
    """Test suite for position-to-trip association and map payload."""

    def setUp(self):
        super().setUp()
        self.trip_model = self.env["transport.trip"]
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]
        self.pos_model = self.env["transport.vehicle.position"]
        self.trip_service = self.env["transport.trip.service"]

        # Setup route and approved version
        self.route = self.route_model.create({
            "name": "Ruta Piloto Ambato",
            "code": "RUT-PILOTO-01",
            "origin_name": "Origen Huachi",
            "destination_name": "Destino Ingahurco",
            "direction": "outbound",
        })
        self.version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "reference_polyline": (
                "[[-78.6272, -1.2618], [-78.6250, -1.2580], "
                "[-78.6265, -1.2425], [-78.6225, -1.2335]]"
            ),
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
                "latitude": -1.26 + (i * 0.005),
                "longitude": -78.625,
                "stop_type": stype,
                "radius_m": 30.0,
                "planned_offset_seconds": (i - 1) * 300,
            })
        self.version.action_approve()

        # Setup vehicle and driver
        brand = self.env["fleet.vehicle.model.brand"].create({
            "name": "Scania",
        })
        model = self.env["fleet.vehicle.model"].create({
            "name": "K360",
            "brand_id": brand.id,
        })
        self.driver = self.env["res.partner"].create({
            "name": "Conductor Operacional A",
            "email": "driver.a@uta.edu.ec",
        })
        self.vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "TBA-9901",
            "driver_id": self.driver.id,
            "traccar_unique_id": "UTA-BUS-TEST01",
            "is_simulated": True,
        })

        # Scheduled trip: 08:00 to 09:00 UTC
        self.trip_1 = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 1, 8, 0, 0),
            "scheduled_end_utc": datetime(2026, 11, 1, 9, 0, 0),
            "source_type": "simulated",
        })
        self.trip_1.action_schedule()

    def test_single_trip_association_within_window(self):
        """Position within scheduled window gets status='associated'."""
        pos = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 8, 25, 0),
            "latitude": -1.255,
            "longitude": -78.625,
            "speed": 35.5,
            "accuracy": 4.2,
            "source": "simulated",
        })

        self.trip_service.associate_positions_to_trips(pos)
        pos.invalidate_recordset()
        self.assertEqual(pos.trip_id.id, self.trip_1.id)
        self.assertEqual(pos.association_status, "associated")
        self.assertEqual(self.trip_1.position_count, 1)

    def test_position_outside_window_remains_unassigned(self):
        """Position before or after trip window remains unassigned."""
        # 1. Before trip window
        pos_before = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 7, 45, 0),
            "latitude": -1.26,
            "longitude": -78.62,
            "speed": 0.0,
            "source": "simulated",
        })
        # 2. After trip window
        pos_after = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 9, 15, 0),
            "latitude": -1.23,
            "longitude": -78.62,
            "speed": 20.0,
            "source": "simulated",
        })

        self.trip_service.associate_positions_to_trips(pos_before | pos_after)
        pos_before.invalidate_recordset()
        pos_after.invalidate_recordset()

        self.assertFalse(pos_before.trip_id)
        self.assertEqual(pos_before.association_status, "unassigned")
        self.assertFalse(pos_after.trip_id)
        self.assertEqual(pos_after.association_status, "unassigned")
        self.assertEqual(self.trip_1.position_count, 0)

    def test_consecutive_trips_boundary_isolation(self):
        """Consecutive trips on same vehicle partition points accurately."""
        # Trip 2: immediately follows Trip 1: 09:00 to 10:00 UTC
        trip_2 = self.trip_model.create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 1, 9, 0, 0),
            "scheduled_end_utc": datetime(2026, 11, 1, 10, 0, 0),
            "source_type": "simulated",
        })
        trip_2.action_schedule()

        # Points in Trip 1
        p1 = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 8, 30, 0),
            "latitude": -1.258,
            "longitude": -78.625,
            "speed": 28.0,
            "source": "simulated",
        })
        # Point in Trip 2
        p2 = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 9, 30, 0),
            "latitude": -1.240,
            "longitude": -78.623,
            "speed": 32.0,
            "source": "simulated",
        })

        self.trip_service.associate_positions_to_trips(p1 | p2)
        p1.invalidate_recordset()
        p2.invalidate_recordset()

        self.assertEqual(p1.trip_id.id, self.trip_1.id)
        self.assertEqual(p1.association_status, "associated")
        self.assertEqual(p2.trip_id.id, trip_2.id)
        self.assertEqual(p2.association_status, "associated")

    def test_get_map_data_payload_structure(self):
        """Verify that get_map_data() delivers complete structures."""
        # Add 2 GPS positions to trip_1
        self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "trip_id": self.trip_1.id,
            "association_status": "associated",
            "fix_time": datetime(2026, 11, 1, 8, 10, 0),
            "latitude": -1.261,
            "longitude": -78.627,
            "speed": 22.0,
            "source": "simulated",
        })
        self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "trip_id": self.trip_1.id,
            "association_status": "associated",
            "fix_time": datetime(2026, 11, 1, 8, 20, 0),
            "latitude": -1.255,
            "longitude": -78.625,
            "speed": 34.0,
            "source": "simulated",
        })

        payload = self.trip_1.get_map_data()

        # Check top-level keys
        self.assertEqual(payload["trip_id"], self.trip_1.id)
        self.assertEqual(payload["name"], self.trip_1.name)
        self.assertEqual(payload["vehicle_name"], self.vehicle.name)
        self.assertEqual(payload["route_code"], "RUT-PILOTO-01")
        self.assertEqual(payload["position_count"], 2)

        # Check reference polyline
        self.assertTrue(len(payload["reference_polyline"]) >= 4)
        # Leaflet format is [lat, lon]
        self.assertAlmostEqual(payload["reference_polyline"][0][0], -1.2618)
        self.assertAlmostEqual(payload["reference_polyline"][0][1], -78.6272)

        # Check stops
        self.assertEqual(len(payload["stops"]), 4)
        origin_stop = payload["stops"][0]
        self.assertEqual(origin_stop["stop_type"], "origin")
        self.assertEqual(origin_stop["radius_m"], 30.0)

        # Check positions
        self.assertEqual(len(payload["positions"]), 2)
        pos0 = payload["positions"][0]
        self.assertEqual(pos0["speed"], 22.0)
        self.assertIn("ECT", pos0["fix_time_local"])

        # Check latest position
        self.assertIsNotNone(payload["latest_position"])
        self.assertEqual(payload["latest_position"]["speed"], 34.0)
