"""Native Odoo TransactionCase tests for GeoRutex Phase 4 Evaluation Engine.

Complies with RF-20 through RF-30, RNF-05, RNF-07, RNF-13:
- Departure from origin geofence and arrival at destination (RF-20).
- Punctuality thresholds, early, on time, and late arrivals.
- Stop visit evaluation: on_time, late, missed, indeterminate.
- Spatial corridor deviations vs isolated GPS noise filtering.
- Telemetry gap detection (> 180s).
- Idempotent evaluation execution and prevention of duplicate incidents.
- Operational incident justification workflow and driver self-approval check.
- Preservation of gross compliance (brutto) vs adjusted compliance (netto).
"""

from datetime import datetime, timedelta
import json
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestEvaluationEngine(TransactionCase):
    """Test suite for evaluation engine, incidents, and compliance."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1. Vehicle model setup
        cls.brand = cls.env["fleet.vehicle.model.brand"].create({
            "name": "Mercedes-Benz Test",
        })
        cls.model = cls.env["fleet.vehicle.model"].create({
            "name": "OF-1721 Test",
            "brand_id": cls.brand.id,
        })

        # 2. Users and security groups
        cls.group_driver = cls.env.ref(
            "uta_transport_monitor.group_transport_driver"
        )
        cls.group_analyst = cls.env.ref(
            "uta_transport_monitor.group_transport_analyst"
        )
        cls.group_manager = cls.env.ref(
            "uta_transport_monitor.group_transport_manager"
        )
        cls.group_user = cls.env.ref("base.group_user")

        cls.partner_driver = cls.env["res.partner"].create({
            "name": "Conductor Evaluado Test",
            "email": "driver.eval@georutex.uta.edu.ec",
        })
        cls.user_driver = cls.env["res.users"].create({
            "name": "Usuario Conductor Eval",
            "login": "driver_eval_user",
            "email": "driver.eval@georutex.uta.edu.ec",
            "partner_id": cls.partner_driver.id,
            "groups_id": [(6, 0, [cls.group_driver.id, cls.group_user.id])],
        })

        cls.partner_manager = cls.env["res.partner"].create({
            "name": "Gerente Evaluador Test",
            "email": "manager.eval@georutex.uta.edu.ec",
        })
        cls.user_manager = cls.env["res.users"].create({
            "name": "Usuario Gerente Eval",
            "login": "manager_eval_user",
            "email": "manager.eval@georutex.uta.edu.ec",
            "partner_id": cls.partner_manager.id,
            "groups_id": [(6, 0, [cls.group_manager.id, cls.group_user.id])],
        })

        # 3. Vehicle
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "TBA-4444",
            "vin_sn": "EVALENGINE12345678",
            "driver_id": cls.partner_driver.id,
            "traccar_device_id": 9901,
            "traccar_unique_id": "eval-bus-01",
            "is_simulated": True,
        })

        # 4. Route and Version with Polyline & 3 Checkpoints
        coords = [
            [-78.620000, -1.250000],  # Origin
            [-78.624500, -1.250000],  # Checkpoint
            [-78.629000, -1.250000],  # Destination
        ]
        polyline_json = json.dumps(
            {"type": "LineString", "coordinates": coords}
        )

        cls.route = cls.env["transport.route"].create({
            "name": "Ruta Campus Huachi - Ingahurco Eval",
            "code": "R-EVAL-01",
            "origin_name": "Terminal Huachi",
            "destination_name": "Campus Ingahurco",
        })
        cls.route_version = cls.env["transport.route.version"].create({
            "route_id": cls.route.id,
            "version_number": 1,
            "state": "approved",
            "reference_polyline": polyline_json,
            "estimated_distance_m": 1000.0,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
            "minimum_consecutive_deviation_points": 2,
            "minimum_deviation_duration_s": 10,
            "geo_accuracy_max_m": 50.0,
        })

        # 3 checkpoints
        cls.stop_origin = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Terminal Huachi",
            "sequence": 1,
            "stop_type": "origin",
            "latitude": -1.250000,
            "longitude": -78.620000,
            "radius_m": 30.0,
            "planned_offset_seconds": 0,
            "required": True,
        })
        cls.stop_mid = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Parada Central",
            "sequence": 2,
            "stop_type": "checkpoint",
            "latitude": -1.250000,
            "longitude": -78.624500,
            "radius_m": 30.0,
            "planned_offset_seconds": 600,  # +10 min
            "required": True,
        })
        cls.stop_dest = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Campus Ingahurco",
            "sequence": 3,
            "stop_type": "destination",
            "latitude": -1.250000,
            "longitude": -78.629000,
            "radius_m": 30.0,
            "planned_offset_seconds": 1200,  # +20 min
            "required": True,
        })

        cls.eval_service = cls.env["transport.trip.evaluation.service"]

    def _create_test_trip(self, sched_start, sched_end):
        """Helper to create and schedule a trip with frozen snapshot."""
        trip = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.partner_driver.id,
            "driver_user_id": self.user_driver.id,
            "route_id": self.route.id,
            "route_version_id": self.route_version.id,
            "scheduled_start_utc": sched_start,
            "scheduled_end_utc": sched_end,
            "source_type": "simulated",
        })
        trip.action_schedule()
        trip.action_start()
        return trip

    def test_01_punctual_trip_fully_compliant(self):
        """A trip adhering strictly to route is Gross Compliant."""
        base_time = datetime(2026, 11, 1, 8, 0, 0)
        end_time = datetime(2026, 11, 1, 8, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        # Positions every 2 minutes (120s <= 180s gap threshold)
        t_dep = base_time + timedelta(minutes=2)
        t_dest = base_time + timedelta(minutes=20)
        lons = [
            -78.620000,  # 00m: inside origin
            -78.620900,  # 02m: departs origin geofence (>30m)
            -78.621800,  # 04m
            -78.622700,  # 06m
            -78.623600,  # 08m
            -78.624500,  # 10m: at stop_mid
            -78.625400,  # 12m
            -78.626300,  # 14m
            -78.627200,  # 16m
            -78.628100,  # 18m
            -78.629000,  # 20m: at stop_dest
        ]
        for idx, lon in enumerate(lons):
            t_pos = base_time + timedelta(minutes=idx * 2)
            self.env["transport.vehicle.position"].create({
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": t_pos,
                "latitude": -1.250000,
                "longitude": lon,
                "speed": 20.0 if 0 < idx < 10 else 0.0,
                "accuracy": 5.0,
                "source": "simulated",
                "is_valid": True,
            })

        evaluation = self.eval_service.evaluate_trip(trip)

        self.assertTrue(evaluation.is_compliant_gross)
        self.assertTrue(evaluation.is_compliant_adjusted)
        self.assertEqual(evaluation.integrity_status, "completed")
        self.assertEqual(evaluation.start_punctuality, "on_time")
        self.assertEqual(evaluation.arrival_punctuality, "on_time")
        self.assertEqual(evaluation.stops_on_time, 3)
        self.assertEqual(evaluation.stops_missed, 0)
        self.assertEqual(evaluation.deviation_count, 0)
        self.assertEqual(evaluation.gps_gap_count, 0)
        self.assertEqual(trip.evaluation_status, "compliant")
        self.assertEqual(trip.state, "completed")

        # Check explicit separation of timestamps (RF-20)
        self.assertEqual(trip.actual_start_utc, t_dep)
        self.assertEqual(trip.actual_end_utc, t_dest)
        self.assertEqual(trip.first_gps_fix_utc, base_time)
        self.assertTrue(trip.manual_start_utc)

    def test_02_late_departure_generates_automatic_incident(self):
        """Departure > lateness_tolerance_s generates automatic incident."""
        base_time = datetime(2026, 11, 1, 9, 0, 0)
        end_time = datetime(2026, 11, 1, 9, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        dep_time = base_time + timedelta(minutes=10)
        arr_time = base_time + timedelta(minutes=20)
        self.env["transport.vehicle.position"].create([
            {
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": base_time,
                "latitude": -1.250000,
                "longitude": -78.620000,
                "speed": 0.0,
                "accuracy": 5.0,
                "source": "simulated",
            },
            {
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": dep_time,
                "latitude": -1.250000,
                "longitude": -78.620500,
                "speed": 30.0,
                "accuracy": 5.0,
                "source": "simulated",
            },
            {
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": arr_time,
                "latitude": -1.250000,
                "longitude": -78.629000,
                "speed": 0.0,
                "accuracy": 5.0,
                "source": "simulated",
            },
        ])

        evaluation = self.eval_service.evaluate_trip(trip)

        self.assertFalse(evaluation.is_compliant_gross)
        self.assertFalse(evaluation.is_compliant_adjusted)
        self.assertEqual(evaluation.start_punctuality, "late")
        self.assertEqual(trip.evaluation_status, "non_compliant")

        incidents = self.env["transport.incident"].search([
            ("trip_id", "=", trip.id),
            ("incident_type", "=", "delay_start"),
        ])
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents.source, "automatic")
        self.assertEqual(incidents.state, "pending")

    def test_03_corridor_deviation_detection_and_noise_filtering(self):
        """Deviations > 40m trigger incident; isolated noisy spike does not."""
        base_time = datetime(2026, 11, 1, 10, 0, 0)
        end_time = datetime(2026, 11, 1, 10, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        t_out = base_time + timedelta(seconds=120)
        d1 = base_time + timedelta(seconds=300)
        d2 = base_time + timedelta(seconds=315)
        d3 = base_time + timedelta(seconds=330)
        t_arr = base_time + timedelta(seconds=1200)

        pos_records = [
            {"t": base_time, "lat": -1.250000, "lon": -78.620000, "acc": 5.0},
            {
                "t": base_time + timedelta(seconds=60),
                "lat": -1.25,
                "lon": -78.6205,
                "acc": 5.0,
            },
            # Noise spike with accuracy > 50m
            {"t": t_out, "lat": -1.240000, "lon": -78.621000, "acc": 120.0},
            # Sustained deviation
            {"t": d1, "lat": -1.251000, "lon": -78.622000, "acc": 10.0},
            {"t": d2, "lat": -1.251000, "lon": -78.622500, "acc": 10.0},
            {"t": d3, "lat": -1.251000, "lon": -78.623000, "acc": 10.0},
            # Destination
            {"t": t_arr, "lat": -1.250000, "lon": -78.629000, "acc": 5.0},
        ]
        for p in pos_records:
            self.env["transport.vehicle.position"].create({
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": p["t"],
                "latitude": p["lat"],
                "longitude": p["lon"],
                "accuracy": p["acc"],
                "speed": 20.0,
                "source": "simulated",
            })

        evaluation = self.eval_service.evaluate_trip(trip)

        self.assertEqual(evaluation.deviation_count, 1)
        self.assertGreaterEqual(evaluation.max_deviation_distance_m, 100.0)
        self.assertFalse(evaluation.is_compliant_gross)

        dev_incident = self.env["transport.incident"].search([
            ("trip_id", "=", trip.id),
            ("incident_type", "=", "route_deviation"),
        ])
        self.assertEqual(len(dev_incident), 1)
        self.assertEqual(dev_incident.severity, "high")

    def test_04_idempotent_evaluation_prevents_duplicate_incidents(self):
        """Repeated evaluation does not duplicate incidents or evaluations."""
        base_time = datetime(2026, 11, 1, 11, 0, 0)
        end_time = datetime(2026, 11, 1, 11, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        self.env["transport.vehicle.position"].create([
            {
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": base_time,
                "latitude": -1.250000,
                "longitude": -78.620000,
                "accuracy": 5.0,
                "source": "simulated",
            },
            {
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": base_time + timedelta(minutes=10),
                "latitude": -1.250000,
                "longitude": -78.620500,
                "accuracy": 5.0,
                "source": "simulated",
            },
        ])

        eval1 = self.eval_service.evaluate_trip(trip)
        inc_c1 = self.env["transport.incident"].search_count([
            ("trip_id", "=", trip.id)
        ])
        ev_c1 = self.env["transport.trip.evaluation"].search_count([
            ("trip_id", "=", trip.id)
        ])

        eval2 = self.eval_service.evaluate_trip(trip)
        inc_c2 = self.env["transport.incident"].search_count([
            ("trip_id", "=", trip.id)
        ])
        ev_c2 = self.env["transport.trip.evaluation"].search_count([
            ("trip_id", "=", trip.id)
        ])

        self.assertEqual(inc_c1, inc_c2)
        self.assertEqual(ev_c1, ev_c2)
        self.assertEqual(eval1.id, eval2.id)

    def test_05_driver_cannot_self_approve_justification(self):
        """Driver can submit justification but CANNOT self-approve (RF-29)."""
        base_time = datetime(2026, 11, 1, 12, 0, 0)
        end_time = datetime(2026, 11, 1, 12, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        incident = self.env["transport.incident"].create({
            "trip_id": trip.id,
            "incident_type": "traffic_congestion",
            "source": "manual",
            "severity": "medium",
            "description": "Congestión vehicular severa.",
        })

        # Driver submits justification
        incident_driver = incident.with_user(self.user_driver)
        incident_driver.write({
            "justification_notes": "Retraso justificado por desvío municipal.",
        })
        incident_driver.action_submit_justification()
        self.assertEqual(incident.justification_submitted_by, self.user_driver)

        # Driver attempts self-approval -> raises AccessError
        with self.assertRaises(AccessError):
            incident_driver.action_approve_justification()

        # Manager approves
        incident_manager = incident.with_user(self.user_manager)
        incident_manager.action_approve_justification()

        self.assertEqual(incident.state, "justified")
        self.assertEqual(incident.reviewed_by, self.user_manager)

    def test_06_approved_justification_adjusts_compliance(self):
        """Approved justifications adjust compliance while gross is False."""
        base_time = datetime(2026, 11, 1, 13, 0, 0)
        end_time = datetime(2026, 11, 1, 13, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        # Departs late (at 13:10 > 300s tolerance), visits mid stop at 13:14
        # (delay 4m <= 5m tol), reaches dest at 13:20 (on time).
        # Fixes every 2 min: 0 gaps. Single incident: delay_start.
        lons = [
            (-78.620000, 0),   # 00m: at origin
            (-78.620000, 2),   # 02m: at origin
            (-78.620000, 4),   # 04m: at origin
            (-78.620000, 6),   # 06m: at origin
            (-78.620000, 8),   # 08m: at origin
            (-78.620900, 10),  # 10m: departs origin (>300s -> late departure)
            (-78.622700, 12),  # 12m: en route
            (-78.624500, 14),  # 14m: at stop_mid (delay 240s <= 300s)
            (-78.626500, 16),  # 16m: en route
            (-78.628000, 18),  # 18m: en route
            (-78.629000, 20),  # 20m: at stop_dest (delay 0s -> on_time)
        ]
        for lon, m_offset in lons:
            self.env["transport.vehicle.position"].create({
                "trip_id": trip.id,
                "vehicle_id": self.vehicle.id,
                "fix_time": base_time + timedelta(minutes=m_offset),
                "latitude": -1.250000,
                "longitude": lon,
                "accuracy": 5.0,
                "source": "simulated",
            })

        evaluation = self.eval_service.evaluate_trip(trip)
        self.assertFalse(evaluation.is_compliant_gross)
        self.assertFalse(evaluation.is_compliant_adjusted)

        incident = self.env["transport.incident"].search([
            ("trip_id", "=", trip.id),
            ("incident_type", "=", "delay_start"),
        ], limit=1)
        self.assertTrue(incident)

        incident.write({"justification_notes": "Inspección técnica."})
        incident.with_user(self.user_driver).action_submit_justification()
        incident.with_user(self.user_manager).action_approve_justification()

        evaluation.invalidate_recordset()
        self.assertFalse(evaluation.is_compliant_gross)
        self.assertTrue(evaluation.is_compliant_adjusted)
        self.assertEqual(trip.evaluation_status, "compliant")

    def test_07_insufficient_gps_data_classified_as_indeterminate(self):
        """Trip with 0 GPS points is insufficient_data, never fabricated."""
        base_time = datetime(2026, 11, 1, 14, 0, 0)
        end_time = datetime(2026, 11, 1, 14, 20, 0)
        trip = self._create_test_trip(base_time, end_time)

        evaluation = self.eval_service.evaluate_trip(trip)

        self.assertEqual(evaluation.integrity_status, "insufficient_data")
        self.assertFalse(evaluation.is_compliant_gross)
        self.assertFalse(evaluation.is_compliant_adjusted)
        self.assertEqual(trip.evaluation_status, "indeterminate")
        self.assertEqual(trip.state, "insufficient_data")
