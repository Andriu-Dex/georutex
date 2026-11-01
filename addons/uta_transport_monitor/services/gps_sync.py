"""GPS synchronization orchestration service for GeoRutex.

Bridges Traccar Client data with Odoo Fleet vehicles and historical positions,
guaranteeing idempotency, UTC timestamp integrity, and safe error handling.
"""

from datetime import datetime, timezone
import logging
import os
from odoo import models
from ..integrations.traccar_client import TraccarClient, TraccarError

_logger = logging.getLogger(__name__)


class TransportGpsSyncService(models.AbstractModel):
    """Orchestration service for scheduled and manual GPS synchronization."""

    _name = "transport.gps.sync.service"
    _description = "Servicio de Sincronización GPS"

    def _get_traccar_client(self) -> TraccarClient:
        """Instantiate TraccarClient using system parameters or defaults."""
        params = self.env["ir.config_parameter"].sudo()
        base_url = params.get_param(
            "traccar.api_base_url",
            os.environ.get("TRACCAR_API_BASE_URL", "http://traccar:8082"),
        )
        username = params.get_param(
            "traccar.api_username",
            os.environ.get("TRACCAR_API_USERNAME", "admin"),
        )
        password = params.get_param(
            "traccar.api_password",
            os.environ.get("TRACCAR_API_PASSWORD", "admin"),
        )
        return TraccarClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=10,
        )

    def _parse_utc_datetime(self, iso_string: str) -> datetime:
        """Parse ISO string and convert to naive UTC datetime for Odoo."""
        cleaned = iso_string.replace("Z", "+00:00")
        dt_aware = datetime.fromisoformat(cleaned)
        dt_utc = dt_aware.astimezone(timezone.utc)
        return dt_utc.replace(tzinfo=None)

    def sync_vehicle_positions(
        self, vehicle, from_time=None, to_time=None
    ) -> int:
        """Synchronize positions for a single vehicle."""
        vehicle.ensure_one()
        client = self._get_traccar_client()

        device_id = vehicle.traccar_device_id
        if not device_id and vehicle.traccar_unique_id:
            device = client.get_device_by_unique_id(vehicle.traccar_unique_id)
            if device and "id" in device:
                device_id = device["id"]
                vehicle.sudo().write({"traccar_device_id": device_id})

        if not device_id:
            _logger.warning("Vehicle %s has no Traccar binding.", vehicle.name)
            return 0

        try:
            raw_positions = client.get_positions(
                device_id=device_id,
                from_time=from_time,
                to_time=to_time,
            )
        except TraccarError as exc:
            _logger.error(
                "Error fetching positions for %s: %s", vehicle.name, exc
            )
            return 0

        position_model = self.env["transport.vehicle.position"].sudo()
        new_count = 0
        latest_position = None

        for pos in raw_positions:
            fix_time_str = pos.get("fixTime")
            if not fix_time_str:
                continue

            fix_time = self._parse_utc_datetime(fix_time_str)
            pos_id = pos.get("id")

            existing = position_model.search(
                [
                    ("traccar_device_id", "=", device_id),
                    ("fix_time", "=", fix_time),
                ],
                limit=1,
            )
            if existing:
                continue

            server_time_str = pos.get("serverTime")
            server_time = (
                self._parse_utc_datetime(server_time_str)
                if server_time_str
                else fix_time
            )

            created = position_model.create(
                {
                    "vehicle_id": vehicle.id,
                    "traccar_device_id": device_id,
                    "traccar_position_id": pos_id,
                    "fix_time": fix_time,
                    "server_time": server_time,
                    "latitude": pos.get("latitude", 0.0),
                    "longitude": pos.get("longitude", 0.0),
                    "speed": pos.get("speed", 0.0),
                    "altitude": pos.get("altitude", 0.0),
                    "is_valid": pos.get("valid", True),
                    "source": "real",
                    "protocol": pos.get("protocol", "osmand"),
                }
            )
            new_count += 1

            if not latest_position or fix_time > latest_position["fix_time"]:
                latest_position = {
                    "fix_time": fix_time,
                    "latitude": created.latitude,
                    "longitude": created.longitude,
                    "speed": created.speed,
                }

        if latest_position:
            vehicle.sudo().write(
                {
                    "last_gps_fix_time": latest_position["fix_time"],
                    "last_gps_latitude": latest_position["latitude"],
                    "last_gps_longitude": latest_position["longitude"],
                    "last_gps_speed": latest_position["speed"],
                }
            )

        return new_count

    def sync_all_vehicles(self) -> int:
        """Scheduled job to synchronize all active tracked vehicles."""
        vehicles = self.env["fleet.vehicle"].search(
            [("gps_tracking_enabled", "=", True)]
        )
        total_created = 0
        for vehicle in vehicles:
            try:
                total_created += self.sync_vehicle_positions(vehicle)
            except Exception as exc:
                _logger.error(
                    "Unexpected error syncing vehicle %s: %s",
                    vehicle.name,
                    exc,
                )
        _logger.info(
            "GPS sync completed: %d new positions stored.", total_created
        )
        return total_created
