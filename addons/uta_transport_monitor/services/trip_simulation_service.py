"""Generate labelled simulated trips that run through the real GPS pipeline.

Trips are created against existing vehicles, approved routes and driver users,
their synthetic positions are ingested with the same code path as Traccar data
(``transport.gps.sync.service._ingest_positions``) and evaluated by the real
engine, so every KPI is computed rather than written.
"""

from datetime import datetime, timedelta, timezone
import random
import zoneinfo

from odoo import api, models
from odoo.exceptions import UserError

from ..domain.simulation import build_track, pick_scenario

LOCAL_TZ = zoneinfo.ZoneInfo("America/Guayaquil")
SERVICE_START_HOUR = 6
SERVICE_END_HOUR = 20
TURNAROUND = timedelta(minutes=15)


class TransportTripSimulationService(models.AbstractModel):
    _name = "transport.trip.simulation.service"
    _description = "Simulador de recorridos"

    @api.model
    def _check_access(self):
        if not (
            self.env.su
            or self.env.user.has_group("base.group_system")
            or self.env.user.has_group("uta_transport_monitor.group_transport_manager")
        ):
            raise UserError("Solo los administradores pueden generar recorridos simulados.")

    @api.model
    def _simulation_inputs(self):
        versions = self.env["transport.route.version"].search(
            [("state", "=", "approved")]
        ).filtered(lambda v: v.reference_polyline and len(v.stop_ids) >= 4)
        vehicles = self.env["fleet.vehicle"].search([("active", "=", True)])
        drivers = self.env.ref("uta_transport_monitor.group_transport_driver").users.filtered("active")
        missing = []
        if not versions:
            missing.append("una ruta aprobada con trazado y al menos 4 paradas")
        if not vehicles:
            missing.append("un vehículo activo")
        if not drivers:
            missing.append("un usuario conductor")
        if missing:
            raise UserError("Para simular recorridos falta: " + ", ".join(missing) + ".")
        return versions, vehicles, drivers

    @api.model
    def plan_trips(self, count, days, seed, batch, mix=None):
        """Return non-overlapping trip specs spread over the past ``days`` days."""
        self._check_access()
        versions, vehicles, drivers = self._simulation_inputs()
        rng = random.Random(seed)
        today_local = datetime.now(LOCAL_TZ).date()
        busy_until = {}
        specs = []
        attempts = 0
        while len(specs) < count and attempts < count * 20:
            attempts += 1
            version = rng.choice(versions)
            vehicle = rng.choice(vehicles)
            driver = rng.choice(drivers)
            day = today_local - timedelta(days=rng.randint(1, days))
            minute = rng.randrange(SERVICE_START_HOUR * 60, SERVICE_END_HOUR * 60, 5)
            start_local = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ) + timedelta(minutes=minute)
            start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
            duration = timedelta(seconds=max(version.planned_duration_s or 0, 600))
            end_utc = start_utc + duration * 1.6 + TURNAROUND
            keys = (("vehicle", vehicle.id), ("driver", driver.id))
            if any(
                start < end_utc and start_utc < end
                for key in keys
                for start, end in busy_until.get(key, [])
            ):
                continue
            for key in keys:
                busy_until.setdefault(key, []).append((start_utc, end_utc))
            specs.append({
                "version_id": version.id,
                "vehicle_id": vehicle.id,
                "driver_user_id": driver.id,
                "start_utc": start_utc,
                "scenario": pick_scenario(rng, mix),
                "seed": rng.randrange(1 << 30),
                "batch": batch,
            })
        specs.sort(key=lambda spec: spec["start_utc"])
        return specs

    @api.model
    def simulate_trip(self, spec):
        """Create, feed and evaluate one simulated trip from a ``plan_trips`` spec."""
        self._check_access()
        Trip = self.env["transport.trip"]
        version = self.env["transport.route.version"].browse(spec["version_id"])
        vehicle = self.env["fleet.vehicle"].browse(spec["vehicle_id"])
        driver = self.env["res.users"].browse(spec["driver_user_id"])
        trip = Trip.create({
            "vehicle_id": vehicle.id,
            "driver_id": driver.partner_id.id,
            "driver_user_id": driver.id,
            "route_id": version.route_id.id,
            "route_version_id": version.id,
            "scheduled_start_utc": spec["start_utc"],
            "source_type": "simulated",
            "simulation_batch": spec["batch"],
        })
        trip.action_schedule()

        polyline = self.env["transport.trip.evaluation.service"]._get_polyline_coordinates(trip)
        stops = [
            {
                "lat": stop.latitude,
                "lon": stop.longitude,
                "offset_s": stop.planned_offset_seconds,
                "stop_type": stop.stop_type,
            }
            for stop in version.stop_ids
        ]
        track = build_track(
            polyline,
            stops,
            trip.scheduled_start_utc,
            trip.scheduled_duration_s or version.planned_duration_s,
            spec["scenario"],
            random.Random(spec["seed"]),
        )
        payloads = [
            {
                "fixTime": point["fix_time"].isoformat() + "Z",
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                # Traccar reports knots; the ingestion converts back to km/h.
                "speed": point["speed_kmh"] / 1.852,
                "accuracy": point["accuracy"],
                "valid": True,
                "protocol": "simulated",
                "attributes": {"simulated": True},
            }
            for point in track
        ]
        self.env["transport.gps.sync.service"]._ingest_positions(
            vehicle,
            vehicle.traccar_device_id or 0,
            payloads,
            target_trip=trip,
            update_vehicle_state=False,
            force_target_trip=True,
        )
        trip.action_start()
        trip.action_complete()
        # Lifecycle actions stamp "now" as manual declarations; a simulated
        # historical trip has no manual declaration.
        trip.write({"manual_start_utc": False, "manual_end_utc": False})
        self.env["transport.trip.evaluation.service"].evaluate_trip(trip)
        return trip

    @api.model
    def purge(self, batch=None):
        """Delete simulator-generated trips (optionally one batch) and their records."""
        self._check_access()
        domain = [("source_type", "=", "simulated"), ("simulation_batch", "!=", False)]
        if batch:
            domain.append(("simulation_batch", "=", batch))
        trips = self.env["transport.trip"].sudo().search(domain)
        count = len(trips)
        self.env["transport.incident"].sudo().search([("trip_id", "in", trips.ids)]).unlink()
        self.env["transport.trip.evaluation"].sudo().search([("trip_id", "in", trips.ids)]).unlink()
        self.env["transport.vehicle.position"].sudo().search([("trip_id", "in", trips.ids)]).unlink()
        trips.mapped("stop_visit_ids").unlink()
        trips.unlink()
        return count
