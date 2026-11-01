"""Software quality metrics service for GeoRutex (Phase 5).

Orchestrates execution and benchmark data gathering for MCS-01 through MCS-04
according to canonical definitions in docs/requirements.md Section 8.2.
"""

import json
import logging
import os
import time
from odoo import api, models
from ..domain.metrics import (
    calculate_mcs01_gps_integrity,
    calculate_mcs02_sync_accuracy,
    calculate_mcs03_response_time,
    calculate_mcs04_incident_detection,
)

_logger = logging.getLogger(__name__)


class TransportSoftwareQualityService(models.AbstractModel):
    _name = "transport.software.quality.service"
    _description = "Servicio de Evaluación de Calidad de Software (MCS-01..04)"

    @api.model
    def compute_all_quality_metrics(self):
        """Compute latest snapshot of all 4 software quality metrics."""
        return {
            "MCS-01": self.compute_mcs01_gps_integrity(),
            "MCS-02": self.compute_mcs02_sync_accuracy(),
            "MCS-03": self.compute_mcs03_response_times(),
            "MCS-04": self.compute_mcs04_incident_detection(),
        }

    @api.model
    def compute_mcs01_gps_integrity(self, source_type="combined"):
        """Calculate MCS-01 GPS telemetry integrity from position records."""
        pos_model = self.env["transport.vehicle.position"]
        domain = []
        if source_type in ("real", "simulated"):
            domain.append(("source", "=", source_type))

        total_count = pos_model.search_count(domain)
        if total_count == 0:
            return calculate_mcs01_gps_integrity(
                total_received=0,
                accepted=0,
                rejected_reasons={},
                source_type=source_type,
            )

        valid_domain = list(domain) + [("is_valid", "=", True)]
        valid_count = pos_model.search_count(valid_domain)

        # Classify rejection reasons
        invalid_domain = list(domain) + [("is_valid", "=", False)]
        invalid_positions = pos_model.search(invalid_domain, limit=1000)

        reasons = {
            "accuracy_exceeded": 0,
            "invalid_coordinates": 0,
            "traccar_invalid_flag": 0,
            "other_rejection": 0,
        }
        for p in invalid_positions:
            if p.accuracy and p.accuracy > 100.0:
                reasons["accuracy_exceeded"] += 1
            elif (
                p.latitude < -90.0
                or p.latitude > 90.0
                or p.longitude < -180.0
                or p.longitude > 180.0
            ):
                reasons["invalid_coordinates"] += 1
            else:
                reasons["other_rejection"] += 1

        return calculate_mcs01_gps_integrity(
            total_received=total_count,
            accepted=valid_count,
            rejected_reasons=reasons,
            source_type=source_type,
        )

    @api.model
    def compute_mcs02_sync_accuracy(self):
        """Calculate MCS-02 by comparing stored points with Traccar API."""
        vehicles = self.env["fleet.vehicle"].search([
            ("traccar_device_id", "!=", False)
        ], limit=5)

        if not vehicles:
            return calculate_mcs02_sync_accuracy(
                expected_count=0,
                matched_count=0,
            )

        sync_service = self.env["transport.gps.sync.service"]
        client = sync_service._get_traccar_client()
        pos_model = self.env["transport.vehicle.position"]

        total_expected = 0
        total_matched = 0

        for v in vehicles:
            try:
                # Query Traccar API independently for positions
                raw_positions = client.get_positions(
                    device_id=v.traccar_device_id,
                )
                if not raw_positions:
                    continue
                # Take sample of up to 20
                if len(raw_positions) > 20:
                    raw_positions = raw_positions[-20:]

                total_expected += len(raw_positions)
                for raw in raw_positions:
                    t_pos_id = raw.get("id")
                    if t_pos_id:
                        matched = pos_model.search_count([
                            ("traccar_position_id", "=", t_pos_id)
                        ])
                        if matched > 0:
                            total_matched += 1
            except Exception as e:
                _logger.warning(
                    "Error querying independent Traccar for %s: %s",
                    v.name,
                    e,
                )

        diff_count = total_expected - total_matched
        return calculate_mcs02_sync_accuracy(
            expected_count=total_expected,
            matched_count=total_matched,
            discrepancy_details={"missing_in_odoo": diff_count},
        )

    @api.model
    def compute_mcs03_response_times(self, cold_repeats=5, warm_repeats=30):
        """Measure system response times for cold and warm operations."""
        trip_model = self.env["transport.trip"]
        pos_model = self.env["transport.vehicle.position"]

        # 1. Cold measurements
        cold_latencies = []
        for _ in range(cold_repeats):
            t_start = time.perf_counter()
            _ = trip_model.search_read(
                [("state", "!=", "cancelled")],
                fields=["name", "state", "evaluation_status", "driver_id"],
                limit=50,
            )
            t_end = time.perf_counter()
            cold_latencies.append((t_end - t_start) * 1000.0)

        # 2. Warm measurements (>= 30 for valid p95 calculation)
        warm_latencies = []
        for _ in range(warm_repeats):
            t_start = time.perf_counter()
            _ = pos_model.search_read(
                [("is_valid", "=", True)],
                fields=["latitude", "longitude", "fix_time", "speed"],
                limit=100,
            )
            t_end = time.perf_counter()
            warm_latencies.append((t_end - t_start) * 1000.0)

        # Return warm as primary with cold metrics in secondary
        res_warm = calculate_mcs03_response_time(warm_latencies, is_cold=False)
        res_cold = calculate_mcs03_response_time(cold_latencies, is_cold=True)

        res_warm["secondary"]["cold_measurements"] = res_cold
        return res_warm

    @api.model
    def compute_mcs04_incident_detection(self):
        """Evaluate labeled ground truth dataset against domain detectors."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(
                os.path.dirname(current_dir),
                "data",
                "incident_ground_truth.json",
            ),
            "/workspace/tests/fixtures/incident_ground_truth.json",
            os.path.abspath(
                os.path.join(
                    current_dir,
                    "..",
                    "..",
                    "..",
                    "tests",
                    "fixtures",
                    "incident_ground_truth.json",
                )
            ),
        ]

        fixture_path = None
        for path in candidates:
            if os.path.exists(path):
                fixture_path = path
                break

        if not fixture_path:
            _logger.warning("Fixture not found in candidates: %s", candidates)
            return calculate_mcs04_incident_detection([])

        try:
            with open(fixture_path, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except Exception as e:
            _logger.error("Error loading fixture %s: %s", fixture_path, e)
            return calculate_mcs04_incident_detection([])

        evaluated_cases = []
        for c in cases:
            t = c.get("incident_type")
            scen = c.get("scenario_data", {})
            detected = False

            if t == "delay_start":
                sched_off = scen.get("scheduled_start_offset_s", 0)
                act_off = scen.get("actual_start_offset_s", 0)
                tol = scen.get("lateness_tolerance_s", 300)
                delay = act_off - sched_off
                detected = delay > tol

            elif t == "delay_arrival":
                sched_off = scen.get("scheduled_end_offset_s", 0)
                act_off = scen.get("actual_end_offset_s", 0)
                tol = scen.get("lateness_tolerance_s", 300)
                delay = act_off - sched_off
                detected = delay > tol

            elif t == "stop_omitted":
                dist = scen.get("closest_distance_m", 0.0)
                rad = scen.get("stop_radius_m", 30.0)
                has_gap = scen.get("has_gps_gap", False)
                detected = (dist > rad) and not has_gap

            elif t == "route_deviation":
                corr = scen.get("corridor_m", 40.0)
                max_d = scen.get("max_distance_m", 0.0)
                pts = scen.get("point_count", 0)
                dur = scen.get("duration_s", 0)
                acc = scen.get("accuracy_m", 5.0)
                # Section 7.5.2 rule: (max_d - acc) > corr with >= 2 points
                detected = (
                    ((max_d - acc) > corr) and (pts >= 2) and (dur >= 10)
                )

            elif t == "gps_loss":
                dur = scen.get("gap_duration_s", 0)
                thresh = scen.get("gap_threshold_s", 180)
                detected = dur > thresh

            evaluated_cases.append({
                "case_id": c.get("case_id"),
                "incident_type": t,
                "expected_has_incident": c.get("expected_has_incident"),
                "detected_has_incident": detected,
            })

        return calculate_mcs04_incident_detection(evaluated_cases)
