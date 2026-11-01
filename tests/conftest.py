"""Pytest configuration and environment initialization for GeoRutex.

Initializes Odoo configuration so that addons located in addons_path
(such as /mnt/extra-addons) are registered into odoo.addons.__path__
before tests run, using Odoo's official configuration mechanism.
"""

import os
import odoo


def pytest_configure(config):
    """Register Odoo addons_path before collecting and executing tests."""
    config_file = os.environ.get("ODOO_RC", "/etc/odoo/odoo.conf")
    if os.path.exists(config_file):
        odoo.tools.config.parse_config(["-c", config_file])
    else:
        default_path = (
            "/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons"
        )
        addons_path = os.environ.get("ODOO_ADDONS_PATH", default_path)
        odoo.tools.config.parse_config(["--addons-path", addons_path])
