"""Trip management and GPS telemetry association service for GeoRutex.

Orchestrates deterministic, idempotent association of GPS positions to
operational trips according to vehicle, temporal window, and lifecycle state.
"""

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class TransportTripService(models.AbstractModel):
    """Orchestration service for trip operations and GPS association."""

    _name = "transport.trip.service"
    _description = "Servicio de Gestión y Asociación de Recorridos"

    @api.model
    def find_matching_trip_for_position(self, position):
        """Find the operational trip corresponding to a GPS position.

        Returns a tuple: (trip_or_none, status_string)
        - ('associated', trip) if exactly one trip matches.
        - ('unassigned', None) if no trip matches the vehicle and window.
        - ('ambiguous', None) if multiple trips match the window.
        """
        if not position.vehicle_id or not position.fix_time:
            return None, "unassigned"

        matching_trips = self.find_trips_for_fix(
            position.vehicle_id.id, position.fix_time
        )
        if len(matching_trips) == 1:
            return matching_trips, "associated"
        if len(matching_trips) > 1:
            _logger.warning(
                "Ambiguous trip match for position %s at %s: matched %s",
                position.id,
                position.fix_time,
                matching_trips.ids,
            )
            return None, "ambiguous"
        return None, "unassigned"

    @staticmethod
    def trip_accepts_fix(trip, fix_time):
        """Whether ``fix_time`` belongs to ``trip``'s operating window.

        A late trip keeps receiving positions after its scheduled end while it
        is in progress, and a completed trip keeps those up to its actual end;
        otherwise late arrivals could never be detected. A trip started early
        accepts positions from its actual start.
        """
        starts = [t for t in (trip.scheduled_start_utc, trip.actual_start_utc) if t]
        if not starts or fix_time < min(starts):
            return False
        if trip.scheduled_end_utc and fix_time <= trip.scheduled_end_utc:
            return True
        if trip.state == "in_progress":
            return True
        return bool(trip.actual_end_utc and fix_time <= trip.actual_end_utc)

    @api.model
    def find_trips_for_fix(self, vehicle_id, fix_time):
        """Return the trip(s) of ``vehicle_id`` that ``fix_time`` belongs to.

        When several trips accept the fix (e.g. an overrun trip and the next
        scheduled one), trips whose scheduled window contains it take priority.
        """
        candidates = self.env["transport.trip"].search([
            ("vehicle_id", "=", vehicle_id),
            ("state", "in", ["scheduled", "in_progress", "completed"]),
            "|",
            ("scheduled_start_utc", "<=", fix_time),
            ("actual_start_utc", "<=", fix_time),
        ]).filtered(lambda trip: self.trip_accepts_fix(trip, fix_time))
        if len(candidates) > 1:
            in_window = candidates.filtered(
                lambda trip: trip.scheduled_end_utc
                and fix_time <= trip.scheduled_end_utc
            )
            if len(in_window) == 1:
                return in_window
        return candidates

    @api.model
    def associate_positions_to_trips(self, positions=None):
        """Associate a set of positions (or all unassigned) to trips.

        Preserves traceability:
        - Sets association_status ('associated', 'unassigned', 'ambiguous').
        - Updates trip_id strictly when exactly one unambiguous match exists.
        """
        position_model = self.env["transport.vehicle.position"]
        if positions is None:
            positions = position_model.search([
                ("association_status", "in", ["unassigned", "ambiguous"]),
            ])

        stats = {"associated": 0, "unassigned": 0, "ambiguous": 0}
        for pos in positions:
            matched_trip, status = self.find_matching_trip_for_position(pos)
            vals = {
                "association_status": status,
                "trip_id": matched_trip.id if matched_trip else False,
            }
            pos.sudo().write(vals)
            stats[status] += 1

        return stats

    @api.model
    def sync_trip_gps_telemetry(self, trip):
        """Synchronize telemetry from Traccar for a trip's time window.

        Retrieves historical positions for the trip's scheduled (or actual)
        window, saves them idempotently, and associates them to the trip.
        """
        trip.ensure_one()
        vehicle = trip.vehicle_id
        if not vehicle:
            return 0

        # Determine time window; late trips extend beyond the scheduled end.
        start_dt = trip.scheduled_start_utc
        end_dt = trip.scheduled_end_utc
        if not start_dt or not end_dt:
            return 0
        if trip.manual_start_utc:
            start_dt = min(start_dt, trip.manual_start_utc)
        if trip.state == "in_progress":
            end_dt = max(end_dt, fields.Datetime.now())
        elif trip.actual_end_utc:
            end_dt = max(end_dt, trip.actual_end_utc)

        # Format ISO 8601 strings with Z
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        gps_service = self.env["transport.gps.sync.service"]
        new_count = gps_service.sync_vehicle_positions(
            vehicle=vehicle,
            from_time=start_iso,
            to_time=end_iso,
            target_trip=trip,
        )

        # Associate any positions for this vehicle within the window
        positions_in_window = self.env["transport.vehicle.position"].search([
            ("vehicle_id", "=", vehicle.id),
            ("fix_time", ">=", start_dt),
            ("fix_time", "<=", end_dt),
        ])
        self.associate_positions_to_trips(positions_in_window)

        return new_count
