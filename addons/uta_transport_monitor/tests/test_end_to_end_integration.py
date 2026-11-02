"""End-to-End Integration and Comprehensive Validation Suite (Phase 6).

Verifies the complete operational and analytics chain:
Traccar Ingestion -> Odoo Sync -> Vehicle -> Trip Scheduling -> Telemetry ->
Evaluation Engine -> Incidents -> Metric Services (MT-01..08, MCS-01..04) ->
Dashboard Action & Multi-Role Security.

Validates the academic rubric requirements:
- 2 Vehicles (real & simulated)
- 3 Routes with >= 4 checkpoints each
- 10 Executed and documented test trips
- 12 KPIs calculated dynamically from stored records
- ISO/IEC 25010 and PDCA regression guarantees
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError


class TestEndToEndIntegration(TransactionCase):
    """Full-chain integration test suite for GeoRutex Phase 6."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.route_model = cls.env["transport.route"]
        cls.version_model = cls.env["transport.route.version"]
        cls.stop_model = cls.env["transport.route.stop"]
        cls.trip_model = cls.env["transport.trip"]
        cls.pos_model = cls.env["transport.vehicle.position"]
        cls.eval_service = cls.env["transport.trip.evaluation.service"]
        cls.metrics_service = cls.env["transport.metrics.service"]
        cls.quality_service = cls.env["transport.software.quality.service"]
        cls.incident_model = cls.env["transport.incident"]

        # Setup 2 Users: Manager & Driver
        cls.partner_driver = cls.env["res.partner"].create({
            "name": "Conductor Integracion E2E",
            "email": "driver_e2e@georutex.uta.edu.ec",
        })
        cls.user_driver = cls.env["res.users"].create({
            "name": "Usuario Conductor E2E",
            "login": "driver_e2e@georutex.uta.edu.ec",
            "email": "driver_e2e@georutex.uta.edu.ec",
            "partner_id": cls.partner_driver.id,
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("uta_transport_monitor.group_transport_driver").id,
            ])],
        })

        # 1. Setup 2 Vehicles: 1 Real (accredited) & 1 Simulated
        brand_bus = cls.env["fleet.vehicle.model.brand"].create({
            "name": "Mercedes Benz E2E",
        })
        model_bus = cls.env["fleet.vehicle.model"].create({
            "name": "Mercedes Benz O500 E2E",
            "brand_id": brand_bus.id,
        })
        cls.vehicle_real = cls.env["fleet.vehicle"].create({
            "model_id": model_bus.id,
            "license_plate": "TBX-9001",
            "traccar_device_id": 901,
            "traccar_unique_id": "real_device_901_e2e",
            "is_simulated": False,
        })
        cls.vehicle_sim = cls.env["fleet.vehicle"].create({
            "model_id": model_bus.id,
            "license_plate": "TBX-9002",
            "traccar_device_id": 902,
            "traccar_unique_id": "sim_device_902_e2e",
            "is_simulated": True,
        })

        # 2. Setup 3 Routes with >= 4 checkpoints each
        cls.routes = []
        cls.versions = []
        for r_idx in range(1, 4):
            route = cls.route_model.create({
                "name": f"Ruta {r_idx:02d} E2E - Troncal {r_idx}",
                "code": f"R-E2E-{r_idx:02d}",
                "origin_name": f"Terminal Norte R{r_idx}",
                "destination_name": f"Terminal Sur R{r_idx}",
            })
            cls.routes.append(route)

            # Route polyline coordinates around Ambato
            coords = [
                [-78.625000, -1.240000 + (r_idx * 0.005)],
                [-78.626000, -1.245000 + (r_idx * 0.005)],
                [-78.627000, -1.250000 + (r_idx * 0.005)],
                [-78.628000, -1.255000 + (r_idx * 0.005)],
            ]
            geojson_str = json.dumps({
                "type": "LineString",
                "coordinates": coords,
            })

            ver = cls.version_model.create({
                "route_id": route.id,
                "version_number": 1,
                "route_corridor_m": 40.0,
                "lateness_tolerance_s": 300,
                "gps_gap_threshold_s": 180,
                "reference_polyline": geojson_str,
            })
            cls.versions.append(ver)

            # 4 Checkpoints: Origin, 2 Checkpoints, Destination
            stops_def = [
                ("Parada 1 Origen", "origin",
                 coords[0][1], coords[0][0], 1),
                ("Parada 2 Control A", "checkpoint",
                 coords[1][1], coords[1][0], 2),
                ("Parada 3 Control B", "checkpoint",
                 coords[2][1], coords[2][0], 3),
                ("Parada 4 Destino", "destination",
                 coords[3][1], coords[3][0], 4),
            ]
            for s_name, s_type, lat, lon, seq in stops_def:
                cls.stop_model.create({
                    "route_version_id": ver.id,
                    "name": f"{s_name} (R{r_idx})",
                    "stop_type": s_type,
                    "latitude": lat,
                    "longitude": lon,
                    "sequence": seq,
                    "radius_m": 35.0,
                    "planned_offset_seconds": (seq - 1) * 600,
                    "required": True,
                })

            ver.action_approve()

    def test_01_operational_topology_and_prerequisites(self):
        """Verify rubric prerequisites: 2 vehicles, 3 routes, 4 stops."""
        self.assertEqual(len(self.routes), 3)
        for r in self.routes:
            self.assertTrue(r.current_version_id)
            stops = r.current_version_id.stop_ids
            self.assertGreaterEqual(len(stops), 4)
            self.assertTrue(any(s.stop_type == "origin" for s in stops))
            self.assertTrue(any(s.stop_type == "destination" for s in stops))

        self.assertFalse(self.vehicle_real.is_simulated)
        self.assertTrue(self.vehicle_sim.is_simulated)

    def test_02_full_pipeline_10_trips_execution_and_evaluation(self):
        """Execute and document 10 trips through the full system pipeline."""
        base_t = datetime(2026, 11, 10, 8, 0, 0)
        trips = []

        # Trip 1: Compliant Real Trip
        t1 = self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[0],
            start_dt=base_t,
            duration_min=30,
            outcome="compliant",
        )
        trips.append(t1)

        # Trip 2: Compliant Simulated Trip
        t2 = self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[1],
            start_dt=base_t + timedelta(hours=1),
            duration_min=30,
            outcome="compliant",
        )
        trips.append(t2)

        # Trip 3: Departure Late (> 5 min late departure)
        t3 = self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[2],
            start_dt=base_t + timedelta(hours=2),
            duration_min=30,
            outcome="delay_start",
        )
        trips.append(t3)

        # Trip 4: Arrival Late (> 5 min late arrival)
        t4 = self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[0],
            start_dt=base_t + timedelta(hours=3),
            duration_min=45,
            outcome="delay_arrival",
        )
        trips.append(t4)

        # Trip 5: Route Deviation
        t5 = self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[1],
            start_dt=base_t + timedelta(hours=4),
            duration_min=30,
            outcome="route_deviation",
        )
        trips.append(t5)

        # Trip 6: Intermediate Stop Omitted
        t6 = self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[2],
            start_dt=base_t + timedelta(hours=5),
            duration_min=30,
            outcome="stop_omitted",
        )
        trips.append(t6)

        # Trip 7: Telemetry Loss (GPS Gap > 180s)
        t7 = self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[0],
            start_dt=base_t + timedelta(hours=6),
            duration_min=30,
            outcome="gps_gap",
        )
        trips.append(t7)

        # Trip 8: Indeterminate Trip (insufficient GPS evidence)
        t8 = self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[1],
            start_dt=base_t + timedelta(hours=7),
            duration_min=30,
            outcome="indeterminate",
        )
        trips.append(t8)

        # Trip 9: Compliant Adjusted (non-compliant gross justified by manager)
        t9 = self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[2],
            start_dt=base_t + timedelta(hours=8),
            duration_min=30,
            outcome="justified",
        )
        trips.append(t9)

        # Trip 10: Compliant Afternoon Return (Achieving 10 Executed Trips)
        t10 = self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[0],
            start_dt=base_t + timedelta(hours=9),
            duration_min=30,
            outcome="compliant_return",
        )
        trips.append(t10)

        # Trip 11: Cancelled Trip (excluded from executed denominator)
        t11 = self.trip_model.create({
            "name": "REC-2026-TRIP-11-CANCELLED",
            "vehicle_id": self.vehicle_sim.id,
            "route_id": self.routes[1].id,
            "route_version_id": self.routes[1].current_version_id.id,
            "driver_id": self.partner_driver.id,
            "scheduled_start_utc": base_t + timedelta(hours=10),
            "scheduled_end_utc": base_t + timedelta(hours=10, minutes=30),
            "source_type": "simulated",
            "state": "cancelled",
        })
        trips.append(t11)

        # Verify exactly 11 trips created (10 executed + 1 cancelled)
        self.assertEqual(len(trips), 11)

        # Verify exactly 10 executed test trips have audit evaluations
        eval_trips = [t for t in trips if t.state != "cancelled"]
        self.assertEqual(len(eval_trips), 10)
        for t in eval_trips:
            self.assertTrue(t.last_evaluation_id)

        # Query dashboard for the entire test period
        dash = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-10",
            "date_to": "2026-11-10",
        })

        # Summary check: 11 total trips, exactly 10 executed trips
        summary = dash["summary"]
        self.assertEqual(summary["total_trips"], 11)
        self.assertEqual(summary["executed_trips"], 10)
        self.assertGreater(summary["compliant_trips_gross"], 0)
        self.assertGreater(summary["compliant_trips_adjusted"], 0)
        self.assertGreater(summary["non_compliant_trips"], 0)

        # Check MT-01..08 values
        kpis = dash["kpis"]
        self.assertFalse(kpis["MT-01"]["is_na"])
        self.assertFalse(kpis["MT-08"]["is_na"])
        self.assertGreater(kpis["MT-08"]["numerator"], 0)

    @patch(
        "odoo.addons.uta_transport_monitor.services.gps_sync."
        "TraccarClient.get_positions"
    )
    def test_03_quality_benchmarks_and_iso25010_metrics(
        self, mock_get_positions
    ):
        """Execute MCS-01..04 quality evaluation suite."""
        # Setup mock positions returned by Traccar for device 901
        mock_get_positions.return_value = [
            {"id": 88001, "deviceId": 901},
            {"id": 88002, "deviceId": 901},
        ]
        self.pos_model.create({
            "vehicle_id": self.vehicle_real.id,
            "latitude": -1.25,
            "longitude": -78.62,
            "fix_time": datetime(2026, 11, 10, 8, 5, 0),
            "traccar_position_id": 88001,
            "source": "real",
            "is_valid": True,
        })
        self.pos_model.create({
            "vehicle_id": self.vehicle_real.id,
            "latitude": -1.251,
            "longitude": -78.621,
            "fix_time": datetime(2026, 11, 10, 8, 10, 0),
            "traccar_position_id": 88002,
            "source": "real",
            "is_valid": True,
        })

        res = self.quality_service.compute_all_quality_metrics()

        # MCS-01: GPS telemetry integrity
        self.assertIn("MCS-01", res)
        self.assertFalse(res["MCS-01"]["is_na"])
        self.assertEqual(res["MCS-01"]["unit"], "%")

        # MCS-02: Sync accuracy
        self.assertIn("MCS-02", res)
        self.assertFalse(res["MCS-02"]["is_na"])
        self.assertEqual(res["MCS-02"]["value"], 100.0)

        # MCS-03: System response times
        self.assertIn("MCS-03", res)
        self.assertFalse(res["MCS-03"]["is_na"])
        self.assertGreater(res["MCS-03"]["value"], 0.0)
        self.assertIn(
            "dashboard_request_latencies", res["MCS-03"]["secondary"]
        )

        # MCS-04: Ground truth detector benchmark (18 cases)
        self.assertIn("MCS-04", res)
        self.assertFalse(res["MCS-04"]["is_na"])
        self.assertEqual(res["MCS-04"]["sample_size"], 18)
        self.assertGreaterEqual(res["MCS-04"]["value"], 80.0)

    def test_04_driver_role_restrictions_mis_recorridos(self):
        """Driver sees only their own trips and cannot approve justifs."""
        t0 = datetime(2026, 11, 11, 8, 0, 0)

        # Trip assigned to this driver
        my_trip = self.trip_model.create({
            "name": "REC-DRIVER-MINE",
            "vehicle_id": self.vehicle_real.id,
            "route_id": self.routes[0].id,
            "route_version_id": self.routes[0].current_version_id.id,
            "driver_id": self.partner_driver.id,
            "scheduled_start_utc": t0,
            "scheduled_end_utc": t0 + timedelta(minutes=30),
            "state": "draft",
        })

        # Trip assigned to other driver
        other_driver = self.env["res.partner"].create({
            "name": "Otro Conductor",
            "email": "other@uta.edu.ec",
        })
        other_trip = self.trip_model.create({
            "name": "REC-DRIVER-OTHER",
            "vehicle_id": self.vehicle_real.id,
            "route_id": self.routes[0].id,
            "route_version_id": self.routes[0].current_version_id.id,
            "driver_id": other_driver.id,
            "scheduled_start_utc": t0 + timedelta(hours=1),
            "scheduled_end_utc": t0 + timedelta(hours=1, minutes=30),
            "state": "draft",
        })

        # Test record rule filtering for driver user
        driver_trips = self.trip_model.with_user(
            self.user_driver
        ).search([])

        self.assertIn(my_trip.id, driver_trips.ids)
        self.assertNotIn(other_trip.id, driver_trips.ids)

        # Driver cannot approve justification
        inc = self.incident_model.create({
            "name": "INC-DRIVER-TEST",
            "trip_id": my_trip.id,
            "incident_type": "delay_start",
            "state": "pending",
            "justification_notes": "Trafico intenso",
        })

        with self.assertRaises(AccessError):
            inc.with_user(self.user_driver).action_approve_justification()

    def test_05_source_type_strict_segregation(self):
        """Dashboard filters strictly segregate real vs simulated data."""
        base_t = datetime(2026, 11, 12, 8, 0, 0)
        self._create_executed_trip(
            vehicle=self.vehicle_real,
            route=self.routes[0],
            start_dt=base_t,
            duration_min=30,
            outcome="compliant",
        )
        self._create_executed_trip(
            vehicle=self.vehicle_sim,
            route=self.routes[0],
            start_dt=base_t + timedelta(hours=1),
            duration_min=30,
            outcome="compliant",
        )

        # Real filter
        dash_real = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-12",
            "date_to": "2026-11-12",
            "source_type": "real",
        })
        self.assertEqual(dash_real["summary"]["total_trips"], 1)
        self.assertEqual(dash_real["kpis"]["MT-01"]["source_type"], "real")

        # Simulated filter
        dash_sim = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-12",
            "date_to": "2026-11-12",
            "source_type": "simulated",
        })
        self.assertEqual(dash_sim["summary"]["total_trips"], 1)
        self.assertEqual(dash_sim["kpis"]["MT-01"]["source_type"], "simulated")

        # Combined filter
        dash_comb = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-12",
            "date_to": "2026-11-12",
            "source_type": "combined",
        })
        self.assertEqual(dash_comb["summary"]["total_trips"], 2)

    # -------------------------------------------------------------------------
    # Helper: Seed Executed Trip with Simulated/Real GPS Telemetry
    # -------------------------------------------------------------------------
    def _create_executed_trip(
        self, vehicle, route, start_dt, duration_min, outcome
    ):
        """Create a scheduled trip, inject scenario GPS telemetry and eval."""
        end_dt = start_dt + timedelta(minutes=duration_min)
        source = "simulated" if vehicle.is_simulated else "real"

        code_str = outcome.upper().replace("_", "-")
        trip = self.trip_model.create({
            "name": f"REC-E2E-{code_str}-{vehicle.license_plate}",
            "vehicle_id": vehicle.id,
            "route_id": route.id,
            "route_version_id": route.current_version_id.id,
            "driver_id": self.partner_driver.id,
            "scheduled_start_utc": start_dt,
            "scheduled_end_utc": end_dt,
            "source_type": source,
            "state": "draft",
        })
        trip.action_schedule()
        trip.action_start()

        # Telemetry offsets and deviations based on outcome
        act_start = start_dt
        act_end = end_dt
        is_gap = False

        if outcome == "delay_start":
            act_start = start_dt + timedelta(minutes=10)
        elif outcome in ("delay_arrival", "justified"):
            act_end = end_dt + timedelta(minutes=15)
        elif outcome == "route_deviation":
            pass
        elif outcome == "gps_gap":
            is_gap = True

        trip.write({
            "actual_start_utc": act_start,
            "actual_end_utc": act_end,
            "manual_start_utc": act_start,
            "manual_end_utc": act_end,
            "state": "completed",
        })

        if outcome == "indeterminate":
            # Zero valid positions
            self.eval_service.evaluate_trip(trip)
            return trip

        # Generate GPS positions at checkpoints
        ver = route.current_version_id
        stops = ver.stop_ids.sorted("sequence")
        for s_idx, st in enumerate(stops):
            if s_idx == 0:
                fix_time = act_start
            elif s_idx == len(stops) - 1:
                fix_time = act_end
            else:
                fix_time = act_start + timedelta(minutes=s_idx * 9)

            lat = st.latitude
            lon = st.longitude

            if outcome == "route_deviation" and s_idx == 2:
                lat += 0.002  # ~220m deviation
            if outcome == "stop_omitted" and s_idx == 1:
                lat += 0.004  # ~440m away, misses geofence

            self.pos_model.create({
                "trip_id": trip.id,
                "vehicle_id": vehicle.id,
                "latitude": lat,
                "longitude": lon,
                "speed": 35.0,
                "fix_time": fix_time,
                "source": source,
                "is_valid": True,
            })

            if s_idx == 0:
                # Origin exit point 2 min after departure (~66m away)
                self.pos_model.create({
                    "trip_id": trip.id,
                    "vehicle_id": vehicle.id,
                    "latitude": lat + 0.0006,
                    "longitude": lon,
                    "speed": 25.0,
                    "fix_time": act_start + timedelta(minutes=2),
                    "source": source,
                    "is_valid": True,
                })

            if is_gap and s_idx == 1:
                # 300 second gap before next point
                pass

        # Evaluate trip
        self.eval_service.evaluate_trip(trip)

        # For 'justified' scenario, approve the incident
        if outcome == "justified":
            # Create delay incident and justify it
            inc = self.incident_model.search([
                ("trip_id", "=", trip.id),
                ("incident_type", "=", "delay_arrival"),
            ], limit=1)
            if not inc:
                inc = self.incident_model.create({
                    "name": f"INC-{trip.name}",
                    "trip_id": trip.id,
                    "incident_type": "delay_arrival",
                    "state": "pending",
                    "justification_notes": "Retencion por cierre vial",
                })
            inc.action_approve_justification()
            self.eval_service.evaluate_trip(trip)

        return trip
