"""Smoke test for Odoo addons_path registration and canonical import.

Verifies:
1. The addon is registered under odoo.addons.uta_transport_monitor.
2. The pure domain module can be imported without error.
3. No ORM or database connection is needed to use domain functions.
"""

import pytest


@pytest.mark.smoke
@pytest.mark.unit
def test_canonical_domain_import():
    """Verify that domain.geo is importable via canonical odoo.addons path."""
    from odoo.addons.uta_transport_monitor.domain import geo

    assert hasattr(geo, "haversine_distance")
    assert hasattr(geo, "is_within_radius")
    assert hasattr(geo, "initial_bearing")
    assert hasattr(geo, "calculate_speed_kmh")
    assert hasattr(geo, "is_valid_coordinate")
