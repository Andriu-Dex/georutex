"""Trip management and GPS telemetry association service for GeoRutex.

Orchestrates deterministic, idempotent association of GPS positions to
operational trips according to vehicle, temporal window, and lifecycle state.
"""

import logging
from odoo import api, models

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

        trip_model = self.env["transport.trip"]
        # Candidate trips must belong to the vehicle and be in an active state
        candidate_domain = [
            ("vehicle_id", "=", position.vehicle_id.id),
            ("state", "in", ["scheduled", "in_progress", "completed"]),
            ("scheduled_start_utc", "<=", position.fix_time),
            ("scheduled_end_utc", ">=", position.fix_time),
        ]
        matching_trips = trip_model.search(candidate_domain)

        if len(matching_trips) == 1:
            return matching_trips[0], "associated"
        elif len(matching_trips) > 1:
            _logger.warning(
                "Ambiguous trip match for position %s at %s: matched %s",
                position.id,
                position.fix_time,
                matching_trips.ids,
            )
            return None, "ambiguous"
        else:
            return None, "unassigned"

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

        # Determine time window
        start_dt = trip.scheduled_start_utc
        end_dt = trip.scheduled_end_utc
        if not start_dt or not end_dt:
            return 0

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
