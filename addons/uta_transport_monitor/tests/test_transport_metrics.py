"""Native Odoo 16 tests for transport metrics service (MT-01..08, Phase 5).

Executes in TransactionCase against georutex_test database.
Validates metric accuracy, source isolation, filter handling, and idempotency.
"""

import json
from datetime import datetime, timedelta
from odoo.tests.common import TransactionCase


class TestTransportMetrics(TransactionCase):
    """Test suite for transport.metrics.service and MT-01..08 indicators."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.metrics_service = cls.env["transport.metrics.service"]
        cls.eval_service = cls.env["transport.trip.evaluation.service"]

        cls.model = cls.env["fleet.vehicle.model"].create({
            "name": "Bus Test Metrics",
            "brand_id": cls.env["fleet.vehicle.model.brand"].create({
                "name": "UTA Brand Metrics"
            }).id,
        })

        cls.partner_driver = cls.env["res.partner"].create({
            "name": "Conductor Metrics Test",
        })
        cls.vehicle_sim = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "TBA-5555",
            "vin_sn": "METRICS1234567890",
            "driver_id": cls.partner_driver.id,
            "traccar_device_id": 9905,
            "traccar_unique_id": "metrics-bus-01",
            "is_simulated": True,
        })
        cls.vehicle_real = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "TBA-5556",
            "vin_sn": "METRICSREAL123456",
            "driver_id": cls.partner_driver.id,
            "traccar_device_id": 9906,
            "traccar_unique_id": "metrics-bus-02",
            "is_simulated": False,
            "is_physical_accredited": True,
        })

        # Route and Version
        coords = [
            [-78.620000, -1.250000],
            [-78.624500, -1.250000],
            [-78.629000, -1.250000],
        ]
        cls.route = cls.env["transport.route"].create({
            "name": "Ruta Metricas Test",
            "code": "R-MET-01",
            "origin_name": "Terminal Huachi",
            "destination_name": "Campus Ingahurco",
        })
        cls.route_version = cls.env["transport.route.version"].create({
            "route_id": cls.route.id,
            "version_number": 1,
            "state": "approved",
            "reference_polyline": json.dumps({
                "type": "LineString",
                "coordinates": coords,
            }),
            "estimated_distance_m": 1000.0,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })

        # Stops
        cls.stop_origin = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Origen Huachi",
            "sequence": 1,
            "stop_type": "origin",
            "latitude": -1.250000,
            "longitude": -78.620000,
            "radius_m": 30.0,
            "required": True,
        })
        cls.stop_mid = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Control Central",
            "sequence": 2,
            "stop_type": "checkpoint",
            "latitude": -1.250000,
            "longitude": -78.624500,
            "radius_m": 30.0,
            "planned_offset_seconds": 600,
            "required": True,
        })
        cls.stop_dest = cls.env["transport.route.stop"].create({
            "route_version_id": cls.route_version.id,
            "name": "Destino Ingahurco",
            "sequence": 3,
            "stop_type": "destination",
            "latitude": -1.250000,
            "longitude": -78.629000,
            "radius_m": 30.0,
            "planned_offset_seconds": 1200,
            "required": True,
        })

    def _create_and_eval_trip(
        self, vehicle, base_time, is_late=False, is_cancelled=False
    ):
        """Helper to create positions and evaluate trip."""
        trip = self.env["transport.trip"].create({
            "vehicle_id": vehicle.id,
            "driver_id": self.partner_driver.id,
            "route_id": self.route.id,
            "route_version_id": self.route_version.id,
            "scheduled_start_utc": base_time,
            "scheduled_end_utc": base_time + timedelta(minutes=20),
            "source_type": "simulated" if vehicle.is_simulated else "real",
        })
        trip.action_schedule()

        if is_cancelled:
            trip.action_cancel()
            return trip

        trip.action_start()

        # Generate GPS positions (compliant or late)
        delay_off = (
            timedelta(minutes=10) if is_late else timedelta(minutes=0)
        )
        t_dep = base_time + timedelta(minutes=2) + delay_off

        lons = [-78.620000, -78.620900, -78.624500, -78.629000]
        times = [
            base_time + delay_off,
            t_dep,
            base_time + timedelta(minutes=10) + delay_off,
            base_time + timedelta(minutes=20) + delay_off,
        ]

        for lon, t_fix in zip(lons, times):
            self.env["transport.vehicle.position"].create({
                "trip_id": trip.id,
                "vehicle_id": vehicle.id,
                "fix_time": t_fix,
                "latitude": -1.250000,
                "longitude": lon,
                "speed": 20.0,
                "accuracy": 5.0,
                "source": trip.source_type,
                "is_valid": True,
            })

        self.eval_service.evaluate_trip(trip)
        return trip

    def test_01_empty_filters_and_na_handling(self):
        """Empty filters with no matching trips return clean N/A structures."""
        # Query for a non-existent route ID
        res = self.metrics_service.get_dashboard_metrics({"route_id": 999999})

        kpis = res["kpis"]
        self.assertTrue(kpis["MT-01"]["is_na"])
        self.assertEqual(kpis["MT-01"]["display_value"], "N/A")
        self.assertEqual(kpis["MT-01"]["denominator"], 0)

        self.assertTrue(kpis["MT-02"]["is_na"])
        self.assertTrue(kpis["MT-03"]["is_na"])
        self.assertTrue(kpis["MT-04"]["is_na"])
        self.assertTrue(kpis["MT-05"]["is_na"])
        self.assertTrue(kpis["MT-06"]["is_na"])
        self.assertTrue(kpis["MT-07"]["is_na"])

        self.assertEqual(res["summary"]["total_trips"], 0)

    def test_02_source_type_isolation_real_vs_simulated(self):
        """Verify strict isolation by real vs simulated vs combined."""
        t0 = datetime(2026, 11, 2, 8, 0, 0)
        # 1 simulated trip
        self._create_and_eval_trip(self.vehicle_sim, t0)
        # 1 real trip
        self._create_and_eval_trip(self.vehicle_real, t0 + timedelta(hours=1))

        # Query simulated only
        res_sim = self.metrics_service.get_dashboard_metrics({
            "source_type": "simulated"
        })
        self.assertEqual(res_sim["summary"]["total_trips"], 1)
        self.assertEqual(res_sim["kpis"]["MT-01"]["sample_size"], 1)

        # Query real only
        res_real = self.metrics_service.get_dashboard_metrics({
            "source_type": "real"
        })
        self.assertEqual(res_real["summary"]["total_trips"], 1)
        self.assertEqual(res_real["kpis"]["MT-01"]["sample_size"], 1)

        # Query combined (all)
        res_comb = self.metrics_service.get_dashboard_metrics({
            "source_type": "combined"
        })
        self.assertEqual(res_comb["summary"]["total_trips"], 2)
        self.assertEqual(res_comb["kpis"]["MT-01"]["sample_size"], 2)

    def test_03_mt01_through_mt08_accuracy(self):
        """Verify calculation accuracy of MT-01..08."""
        t0 = datetime(2026, 11, 3, 8, 0, 0)
        # Trip 1: Compliant (simulated)
        self._create_and_eval_trip(self.vehicle_sim, t0, is_late=False)
        # Trip 2: Late by 10 min (simulated) -> generates delay_start
        self._create_and_eval_trip(
            self.vehicle_sim, t0 + timedelta(hours=2), is_late=True
        )

        res = self.metrics_service.get_dashboard_metrics({
            "route_id": self.route.id,
            "source_type": "simulated",
        })
        kpis = res["kpis"]

        # MT-01: 1 compliant out of 2 executed -> 50%
        self.assertEqual(kpis["MT-01"]["value"], 50.0)
        self.assertEqual(kpis["MT-01"]["numerator"], 1)
        self.assertEqual(kpis["MT-01"]["denominator"], 2)

        # MT-02: Trip 1 punctual, Trip 2 late -> 50%
        self.assertEqual(kpis["MT-02"]["value"], 50.0)

        # MT-03: Trip 1 delay 0, Trip 2 delay 10 -> Gross avg = 5.0 min
        self.assertEqual(kpis["MT-03"]["value"], 5.0)

        # MT-04: Intermediate checkpoint visited on both trips -> 100%
        self.assertEqual(kpis["MT-04"]["value"], 100.0)
        self.assertEqual(kpis["MT-04"]["denominator"], 2)

        # MT-08: At least 1 incident (delay_start on trip2)
        self.assertGreaterEqual(kpis["MT-08"]["numerator"], 1)
        self.assertEqual(kpis["MT-08"]["denominator"], 2)

    def test_04_date_and_route_filtering(self):
        """Verify date range filter in America/Guayaquil limits results."""
        t0 = datetime(2026, 11, 5, 14, 0, 0)  # 09:00 Guayaquil (UTC-5)
        self._create_and_eval_trip(self.vehicle_sim, t0)

        # Query matching date
        res_match = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-05",
            "date_to": "2026-11-05",
            "route_id": self.route.id,
        })
        self.assertEqual(res_match["summary"]["total_trips"], 1)

        # Query non-matching date
        res_nomatch = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-06",
            "date_to": "2026-11-06",
            "route_id": self.route.id,
        })
        self.assertEqual(res_nomatch["summary"]["total_trips"], 0)

    def test_05_historical_reevaluation_no_double_counting(self):
        """Re-evaluating a trip does not duplicate count in dashboard."""
        t0 = datetime(2026, 11, 7, 8, 0, 0)
        trip = self._create_and_eval_trip(self.vehicle_sim, t0)

        # Re-evaluate trip 2 more times (total 3 evaluation records)
        self.eval_service.evaluate_trip(trip)
        self.eval_service.evaluate_trip(trip)
        self.assertEqual(len(trip.evaluation_ids), 3)

        # Dashboard metrics must count trip exactly ONCE
        res = self.metrics_service.get_dashboard_metrics({
            "date_from": "2026-11-07",
            "date_to": "2026-11-07",
        })
        self.assertEqual(res["summary"]["total_trips"], 1)
        self.assertEqual(res["kpis"]["MT-01"]["denominator"], 1)
