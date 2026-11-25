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
- Motor de evaluación de recorridos y gestión de incidencias.
- Dashboard gerencial interactivo y cálculo de métricas MT-01..08 y MCS-01..04.
- Pruebas integrales extremo a extremo y evaluación de calidad ISO/IEC 25010.
    """,
    "version": "16.0.9.12.0",
    "category": "Fleet/Transport",
    "author": "GeoRutex Team",
    "license": "LGPL-3",
    "depends": [
        "base",
        "fleet",
        "web",
        "auth_signup",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "security/menu_restrictions.xml",
        "data/auth_signup_data.xml",
        "data/mail_template_data.xml",
        "data/ir_sequence_data.xml",
        "views/dashboard_views.xml",
        "views/transport_position_views.xml",
        "views/transport_route_views.xml",
        "views/transport_route_version_views.xml",
        "views/transport_incident_views.xml",
        "views/transport_evaluation_views.xml",
        "views/transport_trip_views.xml",
        "views/fleet_vehicle_views.xml",
        "views/menu_views.xml",
        "views/public_home_templates.xml",
        "views/login_templates.xml",
        "data/ir_cron_data.xml",
    ],
    "demo": [
        "demo/transport_demo_data.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            "uta_transport_monitor/static/src/scss/georutex_primary_variables.scss",
        ],
        "uta_transport_monitor.assets_auth": [
            "uta_transport_monitor/static/src/css/georutex_tokens.css",
            "uta_transport_monitor/static/src/scss/georutex_auth.scss",
            "uta_transport_monitor/static/lib/gsap/gsap.min.js",
            "uta_transport_monitor/static/lib/gsap/SplitText.min.js",
            "uta_transport_monitor/static/lib/gsap/DrawSVGPlugin.min.js",
            "uta_transport_monitor/static/lib/gsap/MotionPathPlugin.min.js",
            "uta_transport_monitor/static/lib/gsap/Flip.min.js",
            "uta_transport_monitor/static/src/js/georutex_auth.js",
        ],
        "uta_transport_monitor.assets_public_home": [
            "web/static/src/libs/fontawesome/css/font-awesome.css",
            "uta_transport_monitor/static/src/css/georutex_tokens.css",
            "uta_transport_monitor/static/src/css/georutex_public_home.css",
            "uta_transport_monitor/static/lib/gsap/gsap.min.js",
            "uta_transport_monitor/static/lib/gsap/ScrollTrigger.min.js",
            "uta_transport_monitor/static/lib/gsap/SplitText.min.js",
            "uta_transport_monitor/static/lib/gsap/DrawSVGPlugin.min.js",
            "uta_transport_monitor/static/lib/gsap/MotionPathPlugin.min.js",
            "uta_transport_monitor/static/lib/gsap/Flip.min.js",
            "uta_transport_monitor/static/src/js/georutex_public_home.js",
        ],
        "web.assets_backend": [
            "uta_transport_monitor/static/lib/leaflet/leaflet.css",
            "uta_transport_monitor/static/lib/leaflet/leaflet.js",
            "uta_transport_monitor/static/lib/gsap/gsap.min.js",
            "uta_transport_monitor/static/lib/gsap/Flip.min.js",
            "uta_transport_monitor/static/lib/gsap/DrawSVGPlugin.min.js",
            "uta_transport_monitor/static/lib/echarts/echarts.min.js",
            "uta_transport_monitor/static/src/css/transport_map.css",
            "uta_transport_monitor/static/src/css/georutex_tokens.css",
            "uta_transport_monitor/static/src/css/georutex_platform.css",
            "web/static/lib/Chart/Chart.js",
            "uta_transport_monitor/static/src/js/georutex_motion.js",
            "uta_transport_monitor/static/src/js/georutex_drawer.js",
            "uta_transport_monitor/static/src/js/custom_georutex_nav.js",
            "uta_transport_monitor/static/src/js/georutex_user_menu.js",
            "uta_transport_monitor/static/src/js/custom_georutex_forms.js",
            "uta_transport_monitor/static/src/js/admin_home_action.js",
            "uta_transport_monitor/static/src/js/driver_home_action.js",
            "uta_transport_monitor/static/src/js/trip_map_widget.js",
            "uta_transport_monitor/static/src/js/route_editor_widget.js",
            "uta_transport_monitor/static/src/js/live_fleet_map_action.js",
            (
                "uta_transport_monitor/static/src/js/"
                "transport_dashboard_action.js"
            ),
            "uta_transport_monitor/static/src/xml/georutex_drawer_templates.xml",
            "uta_transport_monitor/static/src/xml/georutex_navbar_templates.xml",
            "uta_transport_monitor/static/src/xml/admin_home_templates.xml",
            "uta_transport_monitor/static/src/xml/driver_home_templates.xml",
            "uta_transport_monitor/static/src/xml/trip_map_widget.xml",
            "uta_transport_monitor/static/src/xml/route_editor_widget.xml",
            (
                "uta_transport_monitor/static/src/xml/"
                "live_fleet_map_templates.xml"
            ),
            (
                "uta_transport_monitor/static/src/xml/"
                "transport_dashboard_templates.xml"
            ),
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
