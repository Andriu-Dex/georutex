"""Tests for the labelled trip simulator running through the real pipeline."""

import json

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_simulation")
class TestTripSimulation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.service = self.env["transport.trip.simulation.service"]
        route = self.env["transport.route"].create({
            "name": "Ruta Simulación",
            "code": "RUT-SIM-001",
            "origin_name": "Origen",
            "destination_name": "Destino",
        })
        polyline = [[-78.62, -1.27 + i * 0.002] for i in range(11)]
        self.version = self.env["transport.route.version"].create({
            "route_id": route.id,
            "version_number": 1,
            "reference_polyline": json.dumps(polyline),
            "estimated_distance_m": 2200.0,
        })
        stops = [
            ("Origen", "origin", -1.270, 0),
            ("Control 1", "checkpoint", -1.264, 300),
            ("Control 2", "checkpoint", -1.256, 700),
            ("Destino", "destination", -1.250, 1000),
        ]
        for sequence, (name, stop_type, lat, offset) in enumerate(stops, start=1):
            self.env["transport.route.stop"].create({
                "route_version_id": self.version.id,
                "sequence": sequence * 10,
                "name": name,
                "stop_type": stop_type,
                "latitude": lat,
                "longitude": -78.62,
                "planned_offset_seconds": offset,
            })
        self.version.action_approve()
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Marca Sim"})
        model = self.env["fleet.vehicle.model"].create({"name": "Modelo Sim", "brand_id": brand.id})
        self.vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "SIM-0001",
            "is_physical_accredited": True,
        })
        self.driver = self.env["res.users"].create({
            "name": "Conductor Sim",
            "login": "driver_sim_test",
            "email": "driver_sim@example.com",
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_driver").id])],
        })

    def _run(self, count, mix=None):
        specs = self.service.plan_trips(count, 10, seed=11, batch="TEST-BATCH", mix=mix)
        return self.env["transport.trip"].concat(*[self.service.simulate_trip(s) for s in specs])

    def test_01_simulated_trips_are_labelled_and_evaluated(self):
        trips = self._run(4)
        self.assertEqual(len(trips), 4)
        self.assertEqual(set(trips.mapped("source_type")), {"simulated"})
        self.assertEqual(set(trips.mapped("state")), {"completed"})
        positions = trips.mapped("position_ids")
        self.assertTrue(positions)
        self.assertEqual(set(positions.mapped("source")), {"simulated"})
        for trip in trips:
            self.assertEqual(len(trip.evaluation_ids), 1)
            self.assertFalse(trip.manual_start_utc)
        # Simulated history must not overwrite the live vehicle position.
        self.assertFalse(self.vehicle.last_gps_fix_time)

    def test_02_late_scenario_is_detected_by_real_engine(self):
        trips = self._run(2, mix={"late": 1.0})
        incident_types = set(trips.mapped("incident_ids.incident_type"))
        self.assertTrue(incident_types & {"delay_arrival", "delay_start", "delay_checkpoint"})

    def test_03_purge_removes_only_simulator_batches(self):
        real_trip = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.version.route_id.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-01-05 13:00:00",
        })
        self._run(2)
        removed = self.service.purge("TEST-BATCH")
        self.assertEqual(removed, 2)
        self.assertTrue(real_trip.exists())
        self.assertFalse(self.env["transport.vehicle.position"].search([("source", "=", "simulated")]))

    def test_04_requires_configured_inputs_and_manager_role(self):
        self.version.action_archive()
        with self.assertRaises(UserError):
            self.service.plan_trips(1, 5, seed=1, batch="X")
        analyst = self.env["res.users"].create({
            "name": "Analista Sim",
            "login": "analyst_sim_test",
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_analyst").id])],
        })
        with self.assertRaises(UserError):
            self.service.with_user(analyst).purge()

    def test_05_late_real_trip_keeps_positions_after_scheduled_end(self):
        """Regression: a real trip running late still owns positions past its scheduled end."""
        from datetime import timedelta

        trip = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.version.route_id.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-01-05 13:00:00",
        })
        trip.action_schedule()
        trip.action_start()
        late_fix = trip.scheduled_end_utc + timedelta(minutes=12)
        payload = [{
            "id": 990001,
            "fixTime": late_fix.isoformat() + "Z",
            "latitude": -1.25,
            "longitude": -78.62,
            "speed": 0,
            "valid": True,
        }]
        sync = self.env["transport.gps.sync.service"]
        sync._ingest_positions(self.vehicle, 77, payload)
        self.assertEqual(trip.position_ids.mapped("fix_time"), [late_fix])

        trip.action_complete()
        self.assertEqual(trip.actual_end_utc, late_fix)
        trip_service = self.env["transport.trip.service"]
        self.assertTrue(trip_service.trip_accepts_fix(trip, late_fix))
        self.assertFalse(
            trip_service.trip_accepts_fix(trip, late_fix + timedelta(minutes=5))
        )

    def _real_trip(self):
        trip = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "route_id": self.version.route_id.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": "2026-01-05 13:00:00",
        })
        trip.action_schedule()
        return trip

    def test_06_early_started_trip_accepts_fixes_before_schedule(self):
        """Regression: positions after an early start belong to the trip."""
        from datetime import datetime

        trip = self._real_trip()
        trip.write({"state": "in_progress", "actual_start_utc": datetime(2026, 1, 5, 12, 55)})
        early_fix = datetime(2026, 1, 5, 12, 57)
        trip_service = self.env["transport.trip.service"]
        self.assertTrue(trip_service.trip_accepts_fix(trip, early_fix))
        self.assertFalse(trip_service.trip_accepts_fix(trip, datetime(2026, 1, 5, 12, 50)))
        self.assertIn(trip, trip_service.find_trips_for_fix(self.vehicle.id, early_fix))

    def test_07_complete_and_evaluate_pull_full_history_for_real_trips(self):
        """Regression: periodic syncs only fetch the latest fix, so closing a real trip fetches its window."""
        from unittest.mock import patch

        trip = self._real_trip()
        trip.action_start()
        service_cls = type(self.env["transport.trip.service"])
        with patch.object(service_cls, "sync_trip_gps_telemetry", return_value=0) as sync:
            trip.action_complete()
            trip.action_evaluate_trip()
        self.assertEqual(sync.call_count, 2)

    def test_08_reevaluation_replaces_stale_incidents_and_keeps_justified(self):
        """Regression: re-evaluating drops pending automatic incidents but not justified ones."""
        trip = self._run(1, mix={"late": 1.0})
        automatic = trip.incident_ids.filtered(lambda i: i.source == "automatic")
        self.assertTrue(automatic)
        justified = automatic[0]
        justified.justification_submitted_at = "2026-01-06 10:00:00"
        stale = automatic - justified

        trip.action_evaluate_trip()

        self.assertTrue(justified.exists())
        self.assertFalse(stale.exists())
        regenerated = trip.incident_ids.filtered(lambda i: i.source == "automatic")
        self.assertLessEqual(len(regenerated), len(automatic))
