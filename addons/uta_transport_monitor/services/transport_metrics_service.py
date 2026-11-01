"""Transport metrics orchestrator and dashboard service for GeoRutex (Phase 5).

Aggregates operational and software quality indicators (MT-01..08, MCS-01..04)
for native Odoo 16 views and interactive Owl client actions.
"""

import logging
from collections import defaultdict
from datetime import datetime, time
import pytz
from odoo import api, fields, models
from ..domain.metrics import (
    calculate_mt01_route_compliance,
    calculate_mt02_punctuality,
    calculate_mt03_average_delay,
    calculate_mt04_stops_completed,
    calculate_mt05_route_deviation,
    calculate_mt06_distance_difference,
    calculate_mt07_trip_duration,
    calculate_mt08_incidents,
)

_logger = logging.getLogger(__name__)


class TransportMetricsService(models.AbstractModel):
    _name = "transport.metrics.service"
    _description = "Servicio de Métricas de Transporte y Dashboard (Phase 5)"

    @api.model
    def _build_trip_domain(self, filters=None):
        """Build ORM search domain from dashboard filters dictionary."""
        filters = filters or {}
        domain = []

        # Filter by source_type: 'real', 'simulated', 'combined'
        source_type = filters.get("source_type", "combined")
        if source_type in ("real", "simulated"):
            domain.append(("source_type", "=", source_type))

        # Filter by route
        route_id = filters.get("route_id")
        if route_id:
            domain.append(("route_id", "=", int(route_id)))

        # Filter by vehicle
        vehicle_id = filters.get("vehicle_id")
        if vehicle_id:
            domain.append(("vehicle_id", "=", int(vehicle_id)))

        # Filter by dates in America/Guayaquil converted to UTC
        tz = pytz.timezone("America/Guayaquil")
        date_from = filters.get("date_from")
        if date_from:
            d_from = fields.Date.from_string(date_from)
            dt_from = tz.localize(datetime.combine(d_from, time.min))
            utc_from = dt_from.astimezone(pytz.utc).replace(tzinfo=None)
            domain.append(("scheduled_start_utc", ">=", utc_from))

        date_to = filters.get("date_to")
        if date_to:
            d_to = fields.Date.from_string(date_to)
            dt_to = tz.localize(datetime.combine(d_to, time.max))
            utc_to = dt_to.astimezone(pytz.utc).replace(tzinfo=None)
            domain.append(("scheduled_start_utc", "<=", utc_to))

        return domain

    @api.model
    def get_dashboard_metrics(self, filters=None):
        """Calculate and return all 12 indicators plus chart structures."""
        filters = filters or {}
        source_type = filters.get("source_type", "combined")
        period_str = self._format_period_label(filters)

        # 1. Fetch filtered trips
        trip_domain = self._build_trip_domain(filters)
        trips = self.env["transport.trip"].search(trip_domain)

        # 2. Extract trip evaluation data
        trips_eval_data = []
        all_stops_eval_data = []
        all_trip_ids = trips.ids

        for trip in trips:
            eval_rec = trip.last_evaluation_id
            gross_ok = eval_rec.is_compliant_gross if eval_rec else False
            adj_ok = eval_rec.is_compliant_adjusted if eval_rec else False

            if eval_rec:
                integrity = eval_rec.integrity_status
                start_punc = eval_rec.start_punctuality
                arr_punc = eval_rec.arrival_punctuality
                s_delay = eval_rec.start_delay_s
                a_delay = eval_rec.arrival_delay_s
                max_dev = eval_rec.max_deviation_distance_m
                dev_c = eval_rec.deviation_count
                dev_d = eval_rec.deviation_duration_s
            else:
                integrity = (
                    "completed" if trip.state == "completed" else "incomplete"
                )
                start_punc = "indeterminate"
                arr_punc = "indeterminate"
                s_delay = 0
                a_delay = 0
                max_dev = 0.0
                dev_c = 0
                dev_d = 0

            t_data = {
                "trip_id": trip.id,
                "name": trip.name,
                "state": trip.state,
                "source_type": trip.source_type,
                "scheduled_start_utc": trip.scheduled_start_utc,
                "scheduled_end_utc": trip.scheduled_end_utc,
                "actual_start_utc": trip.actual_start_utc,
                "actual_end_utc": trip.actual_end_utc,
                "scheduled_distance_m": trip.scheduled_distance_m,
                "actual_distance_m": trip.actual_distance_m,
                "is_compliant_gross": gross_ok,
                "is_compliant_adjusted": adj_ok,
                "integrity_status": integrity,
                "start_punctuality": start_punc,
                "arrival_punctuality": arr_punc,
                "start_delay_s": s_delay,
                "arrival_delay_s": a_delay,
                "max_deviation_distance_m": max_dev,
                "deviation_count": dev_c,
                "deviation_duration_s": dev_d,
            }
            trips_eval_data.append(t_data)

            # Checkpoint visits
            for sv in trip.stop_visit_ids:
                s_id = sv.route_stop_id.id if sv.route_stop_id else sv.id
                all_stops_eval_data.append({
                    "stop_id": s_id,
                    "stop_type": sv.stop_type,
                    "required": sv.required,
                    "status": sv.status,
                    "delay_s": sv.delay_s,
                })

        # 3. Fetch incidents related to filtered trips
        inc_domain = []
        if all_trip_ids:
            inc_domain = [("trip_id", "in", all_trip_ids)]
        elif filters.get("route_id") or filters.get("vehicle_id"):
            inc_domain = [("id", "=", 0)]

        incidents_recs = self.env["transport.incident"].search(inc_domain)
        incidents_data = [
            {
                "id": inc.id,
                "name": inc.name,
                "incident_type": inc.incident_type,
                "source": inc.source,
                "state": inc.state,
                "trip_id": inc.trip_id.id,
            }
            for inc in incidents_recs
        ]

        executed_count = sum(
            1 for t in trips_eval_data
            if t["state"] in ("completed", "in_progress")
        )

        # 4. Compute MT-01 through MT-08 pure metrics
        mt01 = calculate_mt01_route_compliance(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt02 = calculate_mt02_punctuality(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt03 = calculate_mt03_average_delay(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt04 = calculate_mt04_stops_completed(
            all_stops_eval_data, source_type=source_type, period=period_str
        )
        mt05 = calculate_mt05_route_deviation(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt06 = calculate_mt06_distance_difference(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt07 = calculate_mt07_trip_duration(
            trips_eval_data, source_type=source_type, period=period_str
        )
        mt08 = calculate_mt08_incidents(
            incidents_data,
            executed_trip_count=executed_count,
            source_type=source_type,
            period=period_str,
        )

        # 5. Compute Software Quality Metrics MCS-01 through MCS-04
        if not self.env.context.get("in_quality_benchmark"):
            quality_service = self.env["transport.software.quality.service"]
            mcs_metrics = quality_service.compute_all_quality_metrics()
        else:
            mcs_metrics = {
                f"MCS-0{i}": {"is_na": True, "value": None, "sample_size": 0}
                for i in range(1, 5)
            }

        # 6. Build chart datasets
        charts = self._build_chart_data(trips, incidents_recs)

        # 7. Summary cards
        gross_compliant = mt01.get("secondary", {}).get(
            "gross_compliant_count", mt01.get("numerator", 0)
        )
        adj_compliant = mt01.get("numerator", 0)
        non_compliant = max(0, mt01.get("denominator", 0) - adj_compliant)
        summary = {
            "total_trips": len(trips),
            "executed_trips": executed_count,
            "compliant_trips": adj_compliant,
            "compliant_trips_gross": gross_compliant,
            "compliant_trips_adjusted": adj_compliant,
            "non_compliant_trips": non_compliant,
            "total_incidents": len(incidents_recs),
            "source_type": source_type,
        }

        return {
            "kpis": {
                "MT-01": mt01,
                "MT-02": mt02,
                "MT-03": mt03,
                "MT-04": mt04,
                "MT-05": mt05,
                "MT-06": mt06,
                "MT-07": mt07,
                "MT-08": mt08,
                "MCS-01": mcs_metrics["MCS-01"],
                "MCS-02": mcs_metrics["MCS-02"],
                "MCS-03": mcs_metrics["MCS-03"],
                "MCS-04": mcs_metrics["MCS-04"],
            },
            "charts": charts,
            "summary": summary,
            "filters_applied": filters,
        }

    @api.model
    def _format_period_label(self, filters):
        d_from = filters.get("date_from")
        d_to = filters.get("date_to")
        if d_from and d_to:
            return f"{d_from} a {d_to}"
        if d_from:
            return f"Desde {d_from}"
        if d_to:
            return f"Hasta {d_to}"
        return "Histórico Completo"

    @api.model
    def _build_chart_data(self, trips, incidents):
        """Prepare Chart.js compatible structures for trends and breakdowns."""
        tz = pytz.timezone("America/Guayaquil")

        # 1. Daily compliance and punctuality trends
        daily_trips = defaultdict(list)
        for t in trips:
            if t.scheduled_start_utc:
                utc_dt = pytz.utc.localize(t.scheduled_start_utc)
                local_dt = utc_dt.astimezone(tz)
                day_key = local_dt.strftime("%Y-%m-%d")
                daily_trips[day_key].append(t)

        sorted_days = sorted(daily_trips.keys())
        trend_labels = []
        trend_gross_compliance = []
        trend_adj_compliance = []
        trend_punctuality = []

        for day in sorted_days:
            day_t_list = daily_trips[day]
            t_evals = []
            for t in day_t_list:
                ev = t.last_evaluation_id
                t_evals.append({
                    "integrity_status": (
                        ev.integrity_status if ev else "completed"
                    ),
                    "state": t.state,
                    "is_compliant_gross": (
                        ev.is_compliant_gross if ev else False
                    ),
                    "is_compliant_adjusted": (
                        ev.is_compliant_adjusted if ev else False
                    ),
                    "actual_start_utc": t.actual_start_utc,
                    "actual_end_utc": t.actual_end_utc,
                    "start_punctuality": (
                        ev.start_punctuality if ev else "indeterminate"
                    ),
                    "arrival_punctuality": (
                        ev.arrival_punctuality if ev else "indeterminate"
                    ),
                })

            m1 = calculate_mt01_route_compliance(t_evals)
            m2 = calculate_mt02_punctuality(t_evals)

            trend_labels.append(day)
            trend_gross_compliance.append(m1.get("value") or 0.0)
            adj_v = m1.get("secondary", {}).get("adjusted_value") or 0.0
            trend_adj_compliance.append(adj_v)
            trend_punctuality.append(m2.get("value") or 0.0)

        # 2. Incident breakdown by type
        inc_types_count = defaultdict(int)
        for inc in incidents:
            inc_types_count[inc.incident_type] += 1

        inc_labels = list(inc_types_count.keys())
        inc_counts = [inc_types_count[k] for k in inc_labels]

        # 3. Route comparison table
        routes_dict = defaultdict(list)
        for t in trips:
            if t.route_id:
                routes_dict[t.route_id.name].append(t)

        route_comparison = []
        for r_name, r_trips in routes_dict.items():
            r_evals = []
            for t in r_trips:
                ev = t.last_evaluation_id
                r_evals.append({
                    "integrity_status": (
                        ev.integrity_status if ev else "completed"
                    ),
                    "state": t.state,
                    "is_compliant_gross": (
                        ev.is_compliant_gross if ev else False
                    ),
                    "is_compliant_adjusted": (
                        ev.is_compliant_adjusted if ev else False
                    ),
                })

            m1 = calculate_mt01_route_compliance(r_evals)
            adj_v = m1.get("secondary", {}).get("adjusted_value")
            route_comparison.append({
                "route_name": r_name,
                "total_trips": len(r_trips),
                "compliance_gross_pct": m1.get("value"),
                "compliance_adj_pct": adj_v,
            })

        return {
            "daily_trends": {
                "labels": trend_labels,
                "gross_compliance": trend_gross_compliance,
                "adjusted_compliance": trend_adj_compliance,
                "punctuality": trend_punctuality,
            },
            "incidents_by_type": {
                "labels": inc_labels,
                "counts": inc_counts,
            },
            "route_comparison": route_comparison,
        }
