"""Native Odoo 16 tests for GPS synchronization service."""

from unittest.mock import MagicMock, patch
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "gps_sync")
class TestGpsSync(TransactionCase):
    """Test case for GPS synchronization orchestration and idempotency."""

    def setUp(self):
        super().setUp()
        brand = self.env["fleet.vehicle.model.brand"].create(
            {"name": "Mercedes-Benz"}
        )
        model = self.env["fleet.vehicle.model"].create(
            {"name": "Sprinter", "brand_id": brand.id}
        )
        self.vehicle = self.env["fleet.vehicle"].create(
            {
                "model_id": model.id,
                "license_plate": "ABC-1234",
                "traccar_device_id": 99,
                "traccar_unique_id": "TEST-BUS-99",
                "gps_tracking_enabled": True,
                "is_simulated": False,
            }
        )
        self.sync_service = self.env["transport.gps.sync.service"]

    def test_sync_idempotency_and_telemetry_update(self):
        """Verify idempotency and speed in km/h."""
        mock_positions = [
            {
                "id": 101,
                "deviceId": 99,
                "fixTime": "2026-11-01T06:00:00Z",
                "serverTime": "2026-11-01T06:00:01Z",
                "latitude": -1.2693,
                "longitude": -78.6272,
                "speed": 20.0,  # 20 knots = 37.04 km/h
                "altitude": 2570.0,
                "valid": True,
                "protocol": "osmand",
            },
            {
                "id": 102,
                "deviceId": 99,
                "fixTime": "2026-11-01T06:01:00Z",
                "serverTime": "2026-11-01T06:01:01Z",
                "latitude": -1.2650,
                "longitude": -78.6250,
                "speed": 30.0,  # 30 knots = 55.56 km/h
                "altitude": 2575.0,
                "valid": True,
                "protocol": "osmand",
            },
        ]

        mock_client = MagicMock()
        mock_client.get_positions.return_value = mock_positions

        model_cls = type(self.sync_service)
        with patch.object(
            model_cls, "_get_traccar_client", return_value=mock_client
        ):
            # 1. First synchronization pass: creates 2 records
            created_first = self.sync_service.sync_vehicle_positions(
                self.vehicle
            )
            self.assertEqual(created_first, 2)
            self.assertEqual(len(self.vehicle.position_ids), 2)

            # Check vehicle last telemetry update (converted to km/h)
            self.assertAlmostEqual(self.vehicle.last_gps_latitude, -1.2650)
            self.assertAlmostEqual(self.vehicle.last_gps_longitude, -78.6250)
            # 30 knots * 1.852 = 55.56 km/h
            self.assertAlmostEqual(
                self.vehicle.last_gps_speed, 55.56, places=1
            )
            # Check real source tagging
            self.assertEqual(self.vehicle.position_ids[0].source, "real")

            # 2. Second pass: creates 0 records (idempotency)
            created_second = self.sync_service.sync_vehicle_positions(
                self.vehicle
            )
            self.assertEqual(created_second, 0)
            self.assertEqual(len(self.vehicle.position_ids), 2)

    def test_simulated_vehicle_source_classification(self):
        """Verify that simulated vehicles tag telemetries as simulated."""
        sim_vehicle = self.env["fleet.vehicle"].create(
            {
                "model_id": self.vehicle.model_id.id,
                "license_plate": "SIM-9999",
                "traccar_device_id": 199,
                "traccar_unique_id": "SIM-BUS-199",
                "is_simulated": True,
            }
        )
        mock_positions = [
            {
                "id": 201,
                "deviceId": 199,
                "fixTime": "2026-11-01T07:00:00Z",
                "latitude": -1.2700,
                "longitude": -78.6300,
                "speed": 10.0,
                "valid": True,
            }
        ]
        mock_client = MagicMock()
        mock_client.get_positions.return_value = mock_positions

        model_cls = type(self.sync_service)
        with patch.object(
            model_cls, "_get_traccar_client", return_value=mock_client
        ):
            self.sync_service.sync_vehicle_positions(sim_vehicle)
            self.assertEqual(len(sim_vehicle.position_ids), 1)
            self.assertEqual(sim_vehicle.position_ids[0].source, "simulated")

    def test_gps_connection_status_computation(self):
        """Test status transitions (unlinked, offline, online)."""
        unlinked_vehicle = self.env["fleet.vehicle"].create(
            {
                "model_id": self.vehicle.model_id.id,
                "license_plate": "XYZ-9999",
                "traccar_device_id": False,
                "traccar_unique_id": False,
            }
        )
        unlinked_vehicle._compute_gps_status()
        self.assertEqual(unlinked_vehicle.gps_connection_status, "unlinked")

        self.vehicle._compute_gps_status()
        self.assertEqual(self.vehicle.gps_connection_status, "offline")

    def test_generate_secure_unique_id(self):
        """Test non-predictable unique ID generation."""
        self.vehicle.action_generate_secure_unique_id()
        self.assertTrue(self.vehicle.traccar_unique_id.startswith("UTA-BUS-"))
        self.assertEqual(len(self.vehicle.traccar_unique_id), 16)
