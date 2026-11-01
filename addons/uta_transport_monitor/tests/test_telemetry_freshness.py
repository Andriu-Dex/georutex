"""Native Odoo 16 tests for telemetry freshness and timezone."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from odoo.fields import Datetime
from odoo.tests.common import TransactionCase, tagged

CLIENT_PATCH = (
    "odoo.addons.uta_transport_monitor.services.gps_sync."
    "TransportGpsSyncService._get_traccar_client"
)


@tagged("post_install", "-at_install", "transport_freshness")
class TestTelemetryFreshness(TransactionCase):
    """Test suite for freshness, origin tagging, and local time."""

    def setUp(self):
        super().setUp()
        self.vehicle_model = self.env["fleet.vehicle"]
        self.pos_model = self.env["transport.vehicle.position"]
        self.sync_service = self.env["transport.gps.sync.service"]

        brand = self.env["fleet.vehicle.model.brand"].create({
            "name": "Mercedes",
        })
        model = self.env["fleet.vehicle.model"].create({
            "name": "Sprinter",
            "brand_id": brand.id,
        })
        self.vehicle = self.vehicle_model.create({
            "model_id": model.id,
            "license_plate": "TBA-7703",
            "traccar_device_id": 707,
            "traccar_unique_id": "UTA-BUS-FRESH01",
            "gps_tracking_enabled": True,
            "is_simulated": False,
            "is_physical_accredited": False,
        })

    def test_freshness_state_transitions(self):
        """Verify freshness transitions based on elapsed time (CP-24)."""
        now = Datetime.now()

        # 1. No positions: 'no_data'
        self.vehicle._compute_gps_status()
        self.assertEqual(self.vehicle.gps_freshness_state, "no_data")

        # 2. Position 1 minute ago: 'fresh' (< 3 min)
        self.vehicle.write({"last_gps_fix_time": now - timedelta(minutes=1)})
        self.vehicle._compute_gps_status()
        self.assertEqual(self.vehicle.gps_freshness_state, "fresh")
        self.assertTrue(self.vehicle.last_gps_age_seconds <= 120)

        # 3. Position 8 minutes ago: 'stale' (3-15 min)
        self.vehicle.write({"last_gps_fix_time": now - timedelta(minutes=8)})
        self.vehicle._compute_gps_status()
        self.assertEqual(self.vehicle.gps_freshness_state, "stale")

        # 4. Position 25 minutes ago: 'offline' (> 15 min)
        self.vehicle.write({"last_gps_fix_time": now - timedelta(minutes=25)})
        self.vehicle._compute_gps_status()
        self.assertEqual(self.vehicle.gps_freshness_state, "offline")

        # 5. Unlinked vehicle: 'unlinked'
        unlinked = self.vehicle_model.create({
            "model_id": self.vehicle.model_id.id,
            "license_plate": "TBA-UNLINK",
            "traccar_device_id": False,
            "traccar_unique_id": False,
        })
        unlinked._compute_gps_status()
        self.assertEqual(unlinked.gps_freshness_state, "unlinked")

    def test_unique_id_128_bit_entropy(self):
        """Action generates uniqueId with at least 128-bit entropy."""
        self.vehicle.action_generate_secure_unique_id()
        unique_id = self.vehicle.traccar_unique_id
        self.assertTrue(unique_id.startswith("UTA-BUS-"))
        hex_token = unique_id.replace("UTA-BUS-", "")
        # 32 hexadecimal characters = 16 bytes = 128 bits
        self.assertEqual(len(hex_token), 32)
        int(hex_token, 16)  # Verify valid hex string

    def test_timezone_conversion_to_ecuador_local(self):
        """UTC datetime is converted to America/Guayaquil (UTC-5) (CP-06)."""
        # UTC: 18:00:00 -> Ecuador (UTC-5): 13:00:00
        utc_time = datetime(2026, 11, 1, 18, 0, 0)
        self.vehicle.write({"last_gps_fix_time": utc_time})
        self.vehicle._compute_last_gps_time_local()
        self.assertIn("13:00:00 ECT", self.vehicle.last_gps_time_local)

        # Also verify transport.vehicle.position local time
        pos = self.pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": utc_time,
            "latitude": -1.25,
            "longitude": -78.62,
            "source": "simulated",
        })
        pos._compute_fix_time_local()
        self.assertIn("13:00:00 ECT", pos.fix_time_local)

    @patch(CLIENT_PATCH)
    def test_strict_origin_tagging(self, mock_client_factory):
        """Only accredited physical vehicles produce 'real' positions."""
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        mock_client.get_positions.return_value = [{
            "id": 9901,
            "deviceId": 707,
            "fixTime": "2026-11-01T12:00:00Z",
            "serverTime": "2026-11-01T12:00:01Z",
            "latitude": -1.25,
            "longitude": -78.62,
            "speed": 10.0,
            "valid": True,
            "protocol": "osmand",
            "attributes": {},
        }]

        # 1. Unaccredited vehicle -> produces 'unverified'
        self.vehicle.write({
            "is_physical_accredited": False,
            "is_simulated": False,
        })
        self.sync_service.sync_vehicle_positions(self.vehicle)
        pos1 = self.pos_model.search([("traccar_position_id", "=", 9901)])
        self.assertEqual(pos1.source, "unverified")

        # 2. Simulated vehicle -> produces 'simulated'
        mock_client.get_positions.return_value = [{
            "id": 9902,
            "deviceId": 707,
            "fixTime": "2026-11-01T12:05:00Z",
            "serverTime": "2026-11-01T12:05:01Z",
            "latitude": -1.25,
            "longitude": -78.62,
            "speed": 10.0,
            "valid": True,
            "protocol": "osmand",
            "attributes": {},
        }]
        self.vehicle.write({
            "is_physical_accredited": False,
            "is_simulated": True,
        })
        self.sync_service.sync_vehicle_positions(self.vehicle)
        pos2 = self.pos_model.search([("traccar_position_id", "=", 9902)])
        self.assertEqual(pos2.source, "simulated")

        # 3. Accredited physical vehicle -> produces 'real'
        mock_client.get_positions.return_value = [{
            "id": 9903,
            "deviceId": 707,
            "fixTime": "2026-11-01T12:10:00Z",
            "serverTime": "2026-11-01T12:10:01Z",
            "latitude": -1.25,
            "longitude": -78.62,
            "speed": 10.0,
            "valid": True,
            "protocol": "osmand",
            "attributes": {},
        }]
        self.vehicle.write({
            "is_physical_accredited": True,
            "is_simulated": False,
        })
        self.sync_service.sync_vehicle_positions(self.vehicle)
        pos3 = self.pos_model.search([("traccar_position_id", "=", 9903)])
        self.assertEqual(pos3.source, "real")
