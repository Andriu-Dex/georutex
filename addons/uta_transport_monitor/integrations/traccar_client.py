"""Traccar REST API integration adapter for GeoRutex.

Handles authenticated communication with Traccar Server, normalization,
timeouts, and typed exceptions. Completely decoupled from Odoo ORM.
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)


class TraccarError(Exception):
    """Base exception for Traccar integration errors."""
    pass


class TraccarConnectionError(TraccarError):
    """Raised when connection to Traccar server fails or times out."""
    pass


class TraccarAuthError(TraccarError):
    """Raised when authentication credentials are rejected (401/403)."""
    pass


class TraccarApiError(TraccarError):
    """Raised when Traccar returns an unexpected HTTP or API error response."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class TraccarClient:
    """Synchronous HTTP client for Traccar REST API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: int = 10,
    ):
        """Initialize Traccar client."""
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._auth_header = self._build_auth_header()

    def _build_auth_header(self) -> str:
        raw_token = f"{self.username}:{self.password}".encode("utf-8")
        b64_token = base64.b64encode(raw_token).decode("ascii")
        return f"Basic {b64_token}"

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Perform an authenticated HTTP request to Traccar."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        headers = {
            "Authorization": self._auth_header,
            "Accept": "application/json",
            "User-Agent": "GeoRutex-Odoo16-Connector/1.0",
        }
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return None
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise TraccarAuthError(
                    f"Authentication failed for {self.username}: "
                    f"HTTP {exc.code}"
                ) from exc
            error_body = exc.read().decode("utf-8", errors="replace")
            raise TraccarApiError(
                f"Traccar API error {exc.code} on {endpoint}: {error_body}",
                status_code=exc.code,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TraccarConnectionError(
                f"Failed to connect to Traccar at {self.base_url}: {exc}"
            ) from exc

    def test_connection(self) -> Dict[str, Any]:
        """Test API connectivity and return server metadata."""
        return self._request("/api/server")

    def get_devices(self) -> List[Dict[str, Any]]:
        """Retrieve all devices accessible to the authenticated account."""
        devices = self._request("/api/devices")
        return devices if isinstance(devices, list) else []

    def get_device(self, device_id: int) -> Dict[str, Any]:
        """Retrieve a specific device by its numeric Traccar ID."""
        params = {"id": device_id}
        devices = self._request("/api/devices", params=params)
        if isinstance(devices, list) and devices:
            return devices[0]
        raise TraccarApiError(f"Device with ID {device_id} not found.", 404)

    def get_device_by_unique_id(
        self, unique_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find a device by its client unique identifier."""
        params = {"uniqueId": unique_id}
        devices = self._request("/api/devices", params=params)
        if isinstance(devices, list) and devices:
            return devices[0]
        return None

    def get_positions(
        self,
        device_id: Optional[int] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve GPS positions for a device within a time window."""
        params: Dict[str, Any] = {}
        if device_id:
            params["deviceId"] = device_id
        if from_time and to_time:
            params["from"] = from_time
            params["to"] = to_time

        positions = self._request("/api/positions", params=params)
        return positions if isinstance(positions, list) else []
