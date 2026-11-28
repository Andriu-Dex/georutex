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
