"""Regression tests for Pre-Phase 4 Consistency Review.

Validates:
1. Distance transfer from route version to trip on create() & action_schedule.
2. Auto-computation of estimated distance upon route version approval.
3. Temporal coherence: UTC textual formatting & earliest fix reconciliation.
4. Schedule overdue evaluation on in-progress trips.
5. RBAC security enforcement on live fleet map & vehicle map for drivers.
6. GPS connection status vs telemetry freshness consistency.
"""

from datetime import datetime, timedelta
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPrePhase4Consistency(TransactionCase):
    """Test suite covering Pre-Phase 4 consistency review requirements."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_user = cls.env.ref("base.user_admin")
        cls.driver_partner = cls.env["res.partner"].create({
            "name": "Conductor Consistencia",
            "email": "driver.consistency@uta.edu.ec",
        })
        cls.driver_user = cls.env["res.users"].create({
            "name": "Conductor User",
            "login": "driver_consistency",
            "partner_id": cls.driver_partner.id,
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("uta_transport_monitor.group_transport_driver").id,
            ])],
        })

        cls.brand = cls.env["fleet.vehicle.model.brand"].create({
            "name": "Marca Test",
        })
        cls.model = cls.env["fleet.vehicle.model"].create({
            "name": "Modelo Test",
            "brand_id": cls.brand.id,
        })

        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "CON-1001",
            "driver_id": cls.driver_partner.id,
            "traccar_unique_id": "UTA-BUS-CONSIST-01",
            "gps_tracking_enabled": True,
            "is_simulated": True,
        })

        cls.other_vehicle = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "CON-1002",
            "gps_tracking_enabled": True,
            "is_simulated": True,
        })

        cls.route = cls.env["transport.route"].create({
            "name": "Ruta Consistencia",
            "code": "RUT-CONS-01",
            "origin_name": "Origen Test",
            "destination_name": "Destino Test",
            "direction": "outbound",
        })

        # Coordinates roughly 4.2 km apart in Ambato
        polyline = (
            "[[-78.6272, -1.2618], [-78.6250, -1.2580], "
            "[-78.6265, -1.2425], [-78.6225, -1.2335]]"
        )
        cls.route_version = cls.env["transport.route.version"].create({
            "route_id": cls.route.id,
            "version_number": 1,
            "reference_polyline": polyline,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })

        # Create 4 mandatory stops for approval (RF-10)
        for i in range(1, 5):
            stop_type = "checkpoint"
            if i == 1:
                stop_type = "origin"
            elif i == 4:
                stop_type = "destination"

            cls.env["transport.route.stop"].create({
                "route_version_id": cls.route_version.id,
                "sequence": i * 10,
                "name": f"Parada {i}",
                "stop_type": stop_type,
                "latitude": -1.2618 + (i * 0.007),
                "longitude": -78.6272 + (i * 0.001),
                "radius_m": 30.0,
                "required": True,
            })

    def test_01_route_version_auto_distance_on_approve(self):
        """Verify action_approve auto-calculates distance if empty."""
        self.assertEqual(self.route_version.estimated_distance_m, 0.0)
        self.route_version.action_approve()
        self.assertEqual(self.route_version.state, "approved")
        self.assertGreater(self.route_version.estimated_distance_m, 3000.0)

    def test_02_scheduled_distance_transfer_on_create_and_schedule(self):
        """Verify scheduled_distance_m is auto-transferred to trip."""
        if self.route_version.state != "approved":
            self.route_version.action_approve()

        base_time = datetime.utcnow()
        trip = self.env["transport.trip"].create({
            "route_id": self.route.id,
            "route_version_id": self.route_version.id,
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver_partner.id,
            "scheduled_start_utc": base_time + timedelta(hours=1),
            "scheduled_end_utc": base_time + timedelta(hours=2),
        })
        # Verifies create() transfer
        self.assertEqual(
            trip.scheduled_distance_m,
            self.route_version.estimated_distance_m,
        )

        # Also verifies action_schedule idempotency
        trip.action_schedule()
        self.assertEqual(trip.state, "scheduled")
        self.assertEqual(
            trip.scheduled_distance_m,
            self.route_version.estimated_distance_m,
        )

    def test_03_temporal_coherence_utc_and_local_formatting(self):
        """Verify fix_time_utc displays unambiguous UTC text."""
        test_dt = datetime(2026, 11, 1, 13, 15, 0)  # 13:15 UTC = 08:15 ECT
        pos = self.env["transport.vehicle.position"].create({
            "vehicle_id": self.vehicle.id,
            "fix_time": test_dt,
            "latitude": -1.2618,
            "longitude": -78.6272,
            "speed": 35.0,
            "source": "simulated",
        })
        self.assertEqual(pos.fix_time_utc, "2026-11-01 13:15:00 UTC")
        self.assertIn("08:15:00 ECT", pos.fix_time_local)

    def test_04_trip_start_reconciliation_with_earliest_gps_fix(self):
        """Verify trip actual_start_utc matches earliest associated fix."""
        if self.route_version.state != "approved":
            self.route_version.action_approve()

        base_time = datetime(2026, 11, 1, 10, 0, 0)
        trip = self.env["transport.trip"].create({
            "route_id": self.route.id,
            "route_version_id": self.route_version.id,
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver_partner.id,
            "scheduled_start_utc": base_time,
            "scheduled_end_utc": base_time + timedelta(hours=1),
        })
        trip.action_schedule()

        # GPS fix arrived at 10:05 UTC
        pos = self.env["transport.vehicle.position"].create({
            "vehicle_id": self.vehicle.id,
            "trip_id": trip.id,
            "fix_time": base_time + timedelta(minutes=5),
            "latitude": -1.2618,
            "longitude": -78.6272,
            "speed": 0.0,
            "association_status": "associated",
        })

        # Manual action_start clicked later at 10:20 UTC
        trip.action_start()
        # Must reflect the actual earliest fix (10:05), not late click (10:20)
        self.assertEqual(trip.actual_start_utc, pos.fix_time)

    def test_05_schedule_overdue_flag_on_in_progress_trip(self):
        """Verify is_schedule_overdue flags past trips without closing them."""
        if self.route_version.state != "approved":
            self.route_version.action_approve()

        past_start = datetime.utcnow() - timedelta(hours=3)
        past_end = datetime.utcnow() - timedelta(hours=1)
        trip = self.env["transport.trip"].create({
            "route_id": self.route.id,
            "route_version_id": self.route_version.id,
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver_partner.id,
            "scheduled_start_utc": past_start,
            "scheduled_end_utc": past_end,
        })
        trip.action_schedule()
        trip.action_start()

        self.assertEqual(trip.state, "in_progress")
        self.assertTrue(trip.is_schedule_overdue)

    def test_06_driver_rbac_on_live_fleet_positions(self):
        """Verify driver role can only see their vehicle on live fleet map."""
        driver_env = self.env["fleet.vehicle"].with_user(self.driver_user)
        live_data = driver_env.get_live_fleet_positions()

        vehicle_ids = [v["vehicle_id"] for v in live_data]
        self.assertIn(self.vehicle.id, vehicle_ids)
        self.assertNotIn(self.other_vehicle.id, vehicle_ids)

    def test_07_driver_rbac_denied_on_other_vehicle_map_data(self):
        """Verify driver cannot call get_vehicle_live_map_data on others."""
        other_vehicle_as_driver = self.other_vehicle.with_user(
            self.driver_user
        )
        with self.assertRaises(AccessError):
            other_vehicle_as_driver.get_vehicle_live_map_data()

    def test_08_gps_status_and_freshness_separation(self):
        """Verify separation between hardware link and telemetry freshness."""
        v = self.vehicle
        now = datetime.utcnow()

        # Case 1: Fresh telemetry within 2 minutes
        v.write({"last_gps_fix_time": now - timedelta(minutes=2)})
        self.assertEqual(v.gps_freshness_state, "fresh")
        self.assertEqual(v.gps_connection_status, "online")

        # Case 2: Stale telemetry (10 minutes ago)
        v.write({"last_gps_fix_time": now - timedelta(minutes=10)})
        self.assertEqual(v.gps_freshness_state, "stale")
        self.assertEqual(v.gps_connection_status, "recent")

        # Case 3: Offline telemetry (> 15 minutes, but < 1 hour)
        v.write({"last_gps_fix_time": now - timedelta(minutes=25)})
        self.assertEqual(v.gps_freshness_state, "offline")
        self.assertEqual(v.gps_connection_status, "recent")
