{
    "name": "GeoRutex — Monitoreo y Evaluación de Rutas",
    "summary": "Monitoreo GPS y evaluación de rutas de transporte",
    "description": """
GeoRutex — Sistema de Monitoreo y Evaluación de Rutas
=====================================================
Módulo Odoo 16 Community para:
- Extensión de Fleet con trazabilidad y dispositivos GPS.
- Gestión de rutas, paradas, controles de paso y ventanas de tiempo.
- Sincronización desacoplada con Traccar Server vía API REST.
- Evaluación determinista de cumplimiento de trayectos, paradas y horarios.
- Registro y justificación de incidencias operacionales.
- Métricas dinámicas y tablero de control de transporte.
    """,
    "version": "16.0.1.0.0",
    "category": "Fleet/Transport",
    "author": "GeoRutex Team",
    "license": "LGPL-3",
    "depends": [
        "base",
        "fleet",
    ],
    "data": [],
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
}
