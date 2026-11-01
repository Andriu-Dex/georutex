"""Native Odoo 16 tests for historical GPS synchronization and idempotency."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.uta_transport_monitor.integrations.traccar_client import (
    TraccarConnectionError,
)

CLIENT_PATCH = (
    "odoo.addons.uta_transport_monitor.services.gps_sync."
    "TransportGpsSyncService._get_traccar_client"
)


@tagged("post_install", "-at_install", "transport_history_sync")
class TestGpsHistorySync(TransactionCase):
    """Test suite for range synchronization, deduplication, and resilience."""

    def setUp(self):
        super().setUp()
        self.sync_service = self.env["transport.gps.sync.service"]
        self.vehicle_model = self.env["fleet.vehicle"]
        self.pos_model = self.env["transport.vehicle.position"]

        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Hino"})
        model = self.env["fleet.vehicle.model"].create({
            "name": "AK8J",
            "brand_id": brand.id,
        })
        self.vehicle = self.vehicle_model.create({
            "model_id": model.id,
            "license_plate": "TBA-8802",
            "traccar_device_id": 505,
            "traccar_unique_id": "UTA-BUS-HIST01",
            "gps_tracking_enabled": True,
            "is_simulated": True,
        })

    @patch(CLIENT_PATCH)
    def test_range_sync_idempotency(self, mock_client_factory):
        """Syncing same historical range twice stores points once (CP-05)."""
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client

        raw_positions = [
            {
                "id": 9001,
                "deviceId": 505,
                "fixTime": "2026-11-01T10:00:00Z",
                "serverTime": "2026-11-01T10:00:02Z",
                "latitude": -1.2501,
                "longitude": -78.6251,
                "speed": 15.0,  # knots -> 27.78 km/h
                "altitude": 2570.0,
                "valid": True,
                "attributes": {"accuracy": 5.0},
            },
            {
                "id": 9002,
                "deviceId": 505,
                "fixTime": "2026-11-01T10:01:00Z",
                "serverTime": "2026-11-01T10:01:02Z",
                "latitude": -1.2510,
                "longitude": -78.6255,
                "speed": 18.0,
                "altitude": 2572.0,
                "valid": True,
                "attributes": {"accuracy": 4.5},
            },
        ]
        mock_client.get_positions.return_value = raw_positions

        # First synchronization
        count_first = self.sync_service.sync_vehicle_positions(
            self.vehicle,
            from_time="2026-11-01T10:00:00Z",
            to_time="2026-11-01T10:05:00Z",
        )
        self.assertEqual(count_first, 2)
        total_stored = self.pos_model.search_count([
            ("vehicle_id", "=", self.vehicle.id),
        ])
        self.assertEqual(total_stored, 2)

        # Second synchronization with the exact same data
        count_second = self.sync_service.sync_vehicle_positions(
            self.vehicle,
            from_time="2026-11-01T10:00:00Z",
            to_time="2026-11-01T10:05:00Z",
        )
        self.assertEqual(count_second, 0)
        total_after = self.pos_model.search_count([
            ("vehicle_id", "=", self.vehicle.id),
        ])
        self.assertEqual(total_after, 2, "No duplicate records (CP-05)")

    @patch(CLIENT_PATCH)
    def test_connection_error_graceful_handling(self, mock_client_factory):
        """Connection failure logs error and preserves data (CP-14)."""
        # Pre-seed one existing position
        self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": datetime(2026, 11, 1, 9, 0, 0),
            "latitude": -1.25,
            "longitude": -78.62,
            "speed": 10.0,
            "source": "simulated",
        })

        mock_client = MagicMock()
        mock_client.get_positions.side_effect = TraccarConnectionError(
            "Connection refused to Traccar"
        )
        mock_client_factory.return_value = mock_client

        # Attempt synchronization
        count = self.sync_service.sync_vehicle_positions(self.vehicle)
        self.assertEqual(count, 0)

        # Existing record is intact
        existing = self.pos_model.search([
            ("vehicle_id", "=", self.vehicle.id),
        ])
        self.assertEqual(len(existing), 1)
        self.assertEqual(existing.speed, 10.0)
