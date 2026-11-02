"""Unit tests for demo dataset safety guards and scoped cleanup services.

Verifies that destructive demo seeding and cleanup operations:
1. Are strictly rejected on operational ('georutex') and production databases.
2. Are permitted strictly on designated demo databases ('georutex_demo').
3. Scope search and unlinking to demo datasets, never blanket searches.
"""

from unittest.mock import MagicMock
import pytest

from odoo.addons.uta_transport_monitor.services.demo_safety import (
    validate_target_database,
    cleanup_demo_dataset,
    ALLOWED_DEMO_DATABASES,
    DEMO_TRIP_PREFIX,
)


def test_validate_target_database_rejects_operational_database():
    """Ensure operational database 'georutex' is strictly rejected."""
    with pytest.raises(ValueError, match="Operación destructiva denegada"):
        validate_target_database("georutex")


@pytest.mark.parametrize("invalid_db", [
    "postgres",
    "georutex_prod",
    "production",
    "georutex_test",
    "",
    "   ",
    None,
    123,
])
def test_validate_target_database_rejects_unauthorized_environments(
    invalid_db
):
    """Ensure arbitrary or production DB names are strictly blocked."""
    with pytest.raises(ValueError):
        validate_target_database(invalid_db)


def test_validate_target_database_accepts_authorized_demo_db():
    """Ensure 'georutex_demo' is accepted without raising exceptions."""
    validate_target_database("georutex_demo")
    assert "georutex_demo" in ALLOWED_DEMO_DATABASES


def test_cleanup_demo_dataset_blocks_operational_database():
    """Ensure cleanup immediately rejects 'georutex' before querying models."""
    mock_env = MagicMock()
    with pytest.raises(ValueError, match="Operación destructiva denegada"):
        cleanup_demo_dataset(mock_env, db_name="georutex")

    # Assert that no model was accessed or searched
    assert mock_env.__getitem__.call_count == 0


def test_cleanup_demo_dataset_scoped_search_domains():
    """Ensure cleanup searches strictly by REC-DEMO- prefix and scopes."""
    mock_env = MagicMock()

    mock_trip_model = MagicMock()
    mock_pos_model = MagicMock()
    mock_inc_model = MagicMock()

    def get_model(name):
        if name == "transport.trip":
            return mock_trip_model
        if name == "transport.vehicle.position":
            return mock_pos_model
        if name == "transport.incident":
            return mock_inc_model
        return MagicMock()

    mock_env.__getitem__.side_effect = get_model

    # Mock demo vehicles
    mock_v_real = MagicMock(id=101)
    mock_v_sim = MagicMock(id=102)

    def ref_side_effect(xml_id, raise_if_not_found=False):
        if "real" in xml_id:
            return mock_v_real
        if "sim" in xml_id:
            return mock_v_sim
        return None

    mock_env.ref.side_effect = ref_side_effect

    # Mock search results as recordsets
    mock_demo_trip = MagicMock(id=501)
    mock_demo_trips = MagicMock()
    mock_demo_trips.ids = [501]
    mock_demo_trips.__len__.return_value = 1
    mock_demo_trips.__iter__.return_value = iter([mock_demo_trip])
    mock_trip_model.search.return_value = mock_demo_trips

    mock_demo_positions = MagicMock()
    mock_demo_positions.__len__.return_value = 1
    mock_pos_model.search.return_value = mock_demo_positions

    mock_demo_incidents = MagicMock()
    mock_demo_incidents.__len__.return_value = 1
    mock_inc_model.search.return_value = mock_demo_incidents

    result = cleanup_demo_dataset(mock_env, db_name="georutex_demo")

    # 1. Verify trip search domain was strictly scoped by DEMO_TRIP_PREFIX
    trip_search_call = mock_trip_model.search.call_args[0][0]
    assert trip_search_call == [("name", "=like", f"{DEMO_TRIP_PREFIX}%")]

    # 2. Verify position search domain was scoped and strictly requires simulated
    pos_search_call = mock_pos_model.search.call_args[0][0]
    assert pos_search_call != []
    assert ("source", "=", "simulated") in pos_search_call
    assert ("trip_id", "in", [501]) in pos_search_call or any(
        isinstance(item, tuple) and item[0] == "trip_id"
        for item in pos_search_call
    )

    # 3. Verify unlinking occurred strictly on scoped recordsets
    mock_pos_model.search.return_value.unlink.assert_called_once()
    mock_inc_model.search.return_value.unlink.assert_called_once()
    mock_trip_model.search.return_value.unlink.assert_called_once()

    assert result["positions_deleted"] == 1
    assert result["incidents_deleted"] == 1
    assert result["trips_deleted"] == 1


@pytest.mark.parametrize(
    "has_trips,has_vehicles",
    [
        (True, True),
        (True, False),
        (False, True),
    ],
)
def test_cleanup_demo_dataset_strictly_enforces_simulated_source(
    has_trips, has_vehicles
):
    """Ensure source='simulated' is enforced across all branch conditions.

    Even if a position is linked to a demo trip (REC-DEMO-), real telemetry
    (source='real') must NEVER be included in the deletion domain.
    """
    mock_env = MagicMock()
    mock_trip_model = MagicMock()
    mock_pos_model = MagicMock()
    mock_inc_model = MagicMock()

    mock_env.__getitem__.side_effect = lambda name: {
        "transport.trip": mock_trip_model,
        "transport.vehicle.position": mock_pos_model,
        "transport.incident": mock_inc_model,
    }.get(name, MagicMock())

    if has_vehicles:
        mock_env.ref.side_effect = lambda x, **kw: (
            MagicMock(id=101) if "real" in x else MagicMock(id=102)
        )
    else:
        mock_env.ref.return_value = None

    mock_demo_trips = MagicMock()
    if has_trips:
        mock_demo_trips.ids = [501]
        mock_demo_trips.__len__.return_value = 1
    else:
        mock_demo_trips.ids = []
        mock_demo_trips.__len__.return_value = 0
    mock_trip_model.search.return_value = mock_demo_trips

    mock_pos_model.search.return_value = MagicMock(__len__=lambda s: 0)
    mock_inc_model.search.return_value = MagicMock(__len__=lambda s: 0)

    cleanup_demo_dataset(mock_env, db_name="georutex_demo")

    pos_domain = mock_pos_model.search.call_args[0][0]
    assert ("source", "=", "simulated") in pos_domain
