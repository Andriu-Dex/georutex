"""Unit tests for TraccarClient HTTP adapter using unittest.mock."""

import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest
from odoo.addons.uta_transport_monitor.integrations.traccar_client import (
    TraccarAuthError,
    TraccarClient,
    TraccarConnectionError,
)


@pytest.fixture
def traccar_client():
    return TraccarClient(
        base_url="http://mock-traccar:8082",
        username="admin",
        password="secret_password",
        timeout=5,
    )


@pytest.mark.unit
def test_traccar_client_auth_header(traccar_client):
    header = traccar_client._build_auth_header()
    assert header.startswith("Basic ")


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_test_connection_success(mock_urlopen, traccar_client):
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps({"version": "6.5"}).encode()
    fake_response.__enter__.return_value = fake_response
    mock_urlopen.return_value = fake_response

    res = traccar_client.test_connection()
    assert res.get("version") == "6.5"


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_auth_error_raises_traccar_auth_error(mock_urlopen, traccar_client):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="http://mock-traccar:8082/api/devices",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=MagicMock(read=lambda: b"Unauthorized"),
    )

    with pytest.raises(TraccarAuthError):
        traccar_client.get_devices()


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_connection_error_raises(mock_urlopen, traccar_client):
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    with pytest.raises(TraccarConnectionError):
        traccar_client.test_connection()


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_get_device_by_unique_id(mock_urlopen, traccar_client):
    devices = [{"id": 10, "name": "Bus 10", "uniqueId": "BUS-10"}]
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(devices).encode()
    fake_response.__enter__.return_value = fake_response
    mock_urlopen.return_value = fake_response

    device = traccar_client.get_device_by_unique_id("BUS-10")
    assert device is not None
    assert device["id"] == 10

    # Device not found
    fake_response.read.return_value = json.dumps([]).encode()
    assert traccar_client.get_device_by_unique_id("NOT-FOUND") is None


@pytest.mark.unit
@patch("urllib.request.urlopen")
def test_get_positions(mock_urlopen, traccar_client):
    positions = [
        {"id": 1, "deviceId": 10, "latitude": -1.2693, "longitude": -78.6272}
    ]
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(positions).encode()
    fake_response.__enter__.return_value = fake_response
    mock_urlopen.return_value = fake_response

    res = traccar_client.get_positions(device_id=10)
    assert len(res) == 1
    assert res[0]["latitude"] == -1.2693
