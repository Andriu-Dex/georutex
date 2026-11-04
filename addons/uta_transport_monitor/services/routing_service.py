"""Decoupled road routing provider service for GeoRutex.

Calculates road-network driving polylines between route stops with strict
timeouts and graceful fallback to direct geospatial interpolation.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple
from ..domain.geo import calculate_polyline_distance, is_valid_coordinate

_logger = logging.getLogger(__name__)

DEFAULT_ROUTING_URL = "https://router.project-osrm.org"
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_USER_AGENT = "GeoRutex-UTA-Fleet-Monitor/1.0"


class RoutingService:
    """Road routing service adapter with offline-first resilience."""

    @classmethod
    def calculate_road_route(
        cls,
        stops_data: List[Dict[str, Any]],
        provider_url: str = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Compute road network geometry connecting ordered stops.

        :param stops_data: List of dicts containing 'latitude' and 'longitude'.
        :param provider_url: Base URL of the OSRM or compatible routing provider.
        :param timeout: HTTP connection and read timeout in seconds.
        :param enabled: Whether external routing provider is active.
        :return: Dict with keys:
            - 'success': bool
            - 'coordinates': list of [lon, lat] GeoJSON coordinates
            - 'distance_m': float (estimated road or direct distance)
            - 'provider': str ('osrm' or 'direct_interpolation')
            - 'fallback': bool
            - 'message': str
        """
        # 1. Validate stops input
        valid_stops: List[Tuple[float, float]] = []
        for stop in stops_data:
            lat = stop.get("latitude")
            lon = stop.get("longitude")
            if lat is not None and lon is not None and is_valid_coordinate(lat, lon):
                valid_stops.append((float(lat), float(lon)))

        if len(valid_stops) < 2:
            return {
                "success": False,
                "coordinates": [],
                "distance_m": 0.0,
                "provider": "none",
                "fallback": False,
                "message": "Se requieren al menos 2 puntos válidos para calcular el trazado.",
            }

        target_url = (provider_url or DEFAULT_ROUTING_URL).strip().rstrip("/")

        # 2. Attempt road network routing via configured provider
        if enabled and target_url:
            try:
                # OSRM expects coordinates in format: {lon1},{lat1};{lon2},{lat2};...
                coords_str = ";".join(
                    f"{lon:.6f},{lat:.6f}" for lat, lon in valid_stops
                )
                endpoint = (
                    f"{target_url}/route/v1/driving/{coords_str}"
                    f"?overview=full&geometries=geojson"
                )
                req = urllib.request.Request(
                    endpoint,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        payload = json.loads(response.read().decode("utf-8"))
                        if payload.get("code") == "Ok" and payload.get("routes"):
                            best_route = payload["routes"][0]
                            geometry = best_route.get("geometry", {})
                            coords = geometry.get("coordinates", [])
                            distance = float(best_route.get("distance", 0.0))
                            if coords and len(coords) >= 2:
                                _logger.info(
                                    "Routing successful via OSRM (%d points, %.2f m)",
                                    len(coords),
                                    distance,
                                )
                                return {
                                    "success": True,
                                    "coordinates": coords,
                                    "distance_m": round(distance, 2),
                                    "provider": "osrm",
                                    "fallback": False,
                                    "message": (
                                        f"Trazado vial calculado exitosamente "
                                        f"({len(coords)} puntos, {round(distance / 1000.0, 2)} km)."
                                    ),
                                }
            except Exception as exc:
                _logger.warning(
                    "OSRM road routing unavailable (%s). Falling back to direct interpolation.",
                    exc,
                )

        # 3. Graceful fallback: direct straight-line polyline interpolation
        fallback_coords = [[lon, lat] for lat, lon in valid_stops]
        direct_distance = calculate_polyline_distance(
            fallback_coords, is_geojson=True
        )
        _logger.info(
            "Direct polyline fallback generated (%d points, %.2f m)",
            len(fallback_coords),
            direct_distance,
        )
        return {
            "success": True,
            "coordinates": fallback_coords,
            "distance_m": round(direct_distance, 2),
            "provider": "direct_interpolation",
            "fallback": True,
            "message": (
                "Servicio de red vial no disponible o sin conexión. "
                "Trazado generado mediante interpolación directa entre paradas."
            ),
        }

