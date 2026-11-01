"""Native Odoo 16 tests for software quality service (MCS-01..04, Phase 5).

Executes in TransactionCase against georutex_test database.
Validates GPS integrity, sync check, latency profiling, and labeled data.
"""

from datetime import datetime
from odoo.tests.common import TransactionCase


class TestSoftwareQuality(TransactionCase):
    """Test suite for transport.software.quality.service (MCS-01..04)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.quality_service = cls.env["transport.software.quality.service"]
        cls.model = cls.env["fleet.vehicle.model"].create({
            "name": "Bus Quality Test",
            "brand_id": cls.env["fleet.vehicle.model.brand"].create({
                "name": "UTA Quality Brand"
            }).id,
        })
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": cls.model.id,
            "license_plate": "TBA-7777",
            "vin_sn": "QUALITY123456789",
            "is_simulated": True,
        })

    def test_01_mcs01_gps_integrity(self):
        """Verify MCS-01 calculates valid vs rejected positions correctly."""
        t0 = datetime(2026, 11, 1, 10, 0, 0)
        pos_model = self.env["transport.vehicle.position"]

        # 1. Valid position
        pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": t0,
            "latitude": -1.250000,
            "longitude": -78.620000,
            "accuracy": 5.0,
            "is_valid": True,
            "source": "simulated",
        })
        # 2. Inaccurate position (> 100m)
        pos_model.create({
            "vehicle_id": self.vehicle.id,
            "fix_time": t0,
            "latitude": -1.250000,
            "longitude": -78.620000,
            "accuracy": 150.0,
            "is_valid": False,
            "source": "simulated",
        })

        res = self.quality_service.compute_mcs01_gps_integrity(
            source_type="simulated"
        )
        self.assertFalse(res["is_na"])
        self.assertGreaterEqual(res["sample_size"], 2)
        reasons = res["secondary"]["rejected_reasons"]
        self.assertIn("accuracy_exceeded", reasons)

    def test_02_mcs02_sync_accuracy_empty_or_mocked(self):
        """Verify MCS-02 structure when no Traccar device is configured."""
        res = self.quality_service.compute_mcs02_sync_accuracy()
        self.assertIn("Exactitud de Sincronización", res["name"])
        self.assertIn(res["unit"], "%")

    def test_03_mcs03_response_time_structure(self):
        """Verify MCS-03 executes profiling and returns valid stats."""
        res = self.quality_service.compute_mcs03_response_times(
            cold_repeats=2, warm_repeats=35
        )
        self.assertFalse(res["is_na"])
        self.assertEqual(res["unit"], "ms")
        self.assertGreater(res["value"], 0.0)

        # Warm with 35 repeats must calculate p95
        self.assertIsNotNone(res["secondary"]["p95_ms"])
        self.assertGreater(res["secondary"]["p95_ms"], 0.0)

        # Cold measurements in secondary
        cold = res["secondary"]["cold_measurements"]
        self.assertFalse(cold["is_na"])
        self.assertEqual(cold["sample_size"], 2)

        # Full dashboard request latencies in secondary
        dash_lat = res["secondary"]["dashboard_request_latencies"]
        self.assertIn("cold_ms", dash_lat)
        self.assertIn("warm_mean_ms", dash_lat)
        self.assertGreater(dash_lat["sample_size"], 0)

    def test_04_mcs04_ground_truth_execution(self):
        """Verify MCS-04 evaluates the independent labeled dataset fixture."""
        res = self.quality_service.compute_mcs04_incident_detection()
        self.assertFalse(res["is_na"])
        self.assertEqual(res["sample_size"], 18)  # 18 cases in fixture

        # Check accuracy, precision, and recall are non-empty
        self.assertGreaterEqual(res["value"], 80.0)
        self.assertGreaterEqual(res["secondary"]["precision_pct"], 80.0)
        self.assertGreaterEqual(res["secondary"]["recall_pct"], 80.0)

        matrix = res["secondary"]["confusion_matrix"]
        self.assertGreater(matrix["vp"], 0)
        self.assertGreater(matrix["vn"], 0)

        # Check breakdown by incident type
        by_type = res["secondary"]["by_incident_type"]
        self.assertIn("delay_start", by_type)
        self.assertIn("delay_arrival", by_type)
        self.assertIn("stop_omitted", by_type)
        self.assertIn("route_deviation", by_type)
        self.assertIn("gps_loss", by_type)

    def test_05_quality_benchmarks_security_and_non_mutation(self):
        """Driver cannot run benchmarks and benchmarks mutate 0 records."""
        from odoo.exceptions import AccessError

        # Create driver user
        driver_user = self.env["res.users"].create({
            "name": "Benchmark Driver",
            "login": "driver_bench@uta.edu.ec",
            "email": "driver_bench@uta.edu.ec",
            "groups_id": [(6, 0, [
                self.env.ref("base.group_user").id,
                self.env.ref(
                    "uta_transport_monitor.group_transport_driver"
                ).id,
            ])],
        })

        # Calling as driver raises AccessError
        with self.assertRaises(AccessError):
            self.quality_service.with_user(
                driver_user
            ).compute_all_quality_metrics()

        # Manager can run and operational counts remain strictly identical
        trips_before = self.env["transport.trip"].search_count([])
        incidents_before = self.env["transport.incident"].search_count([])

        res = self.quality_service.compute_all_quality_metrics()
        self.assertIn("MCS-01", res)
        self.assertIn("MCS-04", res)

        trips_after = self.env["transport.trip"].search_count([])
        incidents_after = self.env["transport.incident"].search_count([])

        self.assertEqual(trips_before, trips_after)
        self.assertEqual(incidents_before, incidents_after)
