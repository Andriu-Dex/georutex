{
    "name": "GeoRutex — Monitoreo y Evaluación de Rutas",
    "summary": "Monitoreo GPS y evaluación de rutas de transporte",
    "description": """
GeoRutex — Sistema de Monitoreo y Evaluación de Rutas
=====================================================
Módulo Odoo 16 Community para:
- Extensión de Fleet con trazabilidad y dispositivos GPS Traccar.
- Adaptador REST desacoplado para Traccar Server.
- Gestión de rutas, versiones y puntos de control geográficos.
- Programación de recorridos operacionales y prevención de conflictos.
- Sincronización idempotente manual y programada de posiciones.
- Historial de telemetrías y estado de conexión en tiempo real.
    """,
    "version": "16.0.2.0.0",
    "category": "Fleet/Transport",
    "author": "GeoRutex Team",
    "license": "LGPL-3",
    "depends": [
        "base",
        "fleet",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/ir_sequence_data.xml",
        "views/transport_position_views.xml",
        "views/transport_route_views.xml",
        "views/transport_route_version_views.xml",
        "views/transport_trip_views.xml",
        "views/fleet_vehicle_views.xml",
        "views/menu_views.xml",
        "data/ir_cron_data.xml",
    ],
    "demo": [
        "demo/transport_demo_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
