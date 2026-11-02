"""Demo dataset safety guards and scoped cleanup services.

Protects operational and production environments (e.g. 'georutex')
from accidental destructive actions, restricting demo data resets strictly
to authorized demo databases and scoping unlinking to demo records.
"""

import logging
from typing import Dict, Any

_logger = logging.getLogger(__name__)

# Strictly permitted databases for destructive demo dataset resetting
ALLOWED_DEMO_DATABASES = frozenset({"georutex_demo"})
DEMO_TRIP_PREFIX = "REC-DEMO-"


def validate_target_database(db_name: str) -> None:
    """Validate that destructive demo dataset operations run only on demo DBs.

    :param db_name: Technical name of target PostgreSQL database.
    :raises ValueError: If db_name is empty, operational ('georutex'), or
                        any non-whitelisted database environment.
    """
    if not db_name or not isinstance(db_name, str):
        raise ValueError(
            "Operación rechazada: Nombre de base de datos no especificado o "
            "inválido."
        )

    normalized = db_name.strip()
    if normalized not in ALLOWED_DEMO_DATABASES:
        _logger.critical(
            "Intento de ejecución de limpieza demo bloqueado en base no "
            "autorizada: '%s'. Bases permitidas: %s",
            normalized,
            sorted(ALLOWED_DEMO_DATABASES),
        )
        raise ValueError(
            f"Operación destructiva denegada: la base de datos '{normalized}' "
            f"no está autorizada para limpieza o sembrado de demostración. "
            f"Solo se permite en entornos demostrativos aislados: "
            f"{sorted(ALLOWED_DEMO_DATABASES)}"
        )


def cleanup_demo_dataset(env: Any, db_name: str) -> Dict[str, int]:
    """Safely cleanup ONLY records belonging to the synthetic demo dataset.

    Enforces:
    1. Strict database authorization (refuses 'georutex' or production).
    2. Strict record scoping:
       - Trips: ONLY trips with name matching 'REC-DEMO-%'.
       - Positions: ONLY positions with source='simulated' linked to demo trips
         OR designated demo vehicles. Real GPS fixes (source='real') are NEVER
         touched under any circumstances, even if linked to a demo trip.
       - Incidents: ONLY incidents explicitly linked to demo trips.

    :param env: Odoo Environment.
    :param db_name: Technical name of the active database.
    :return: Dictionary with counts of deleted records per model.
    """
    validate_target_database(db_name)

    trip_model = env["transport.trip"]
    pos_model = env["transport.vehicle.position"]
    inc_model = env["transport.incident"]

    # 1. Scope demo trips by formal demonstration prefix
    demo_trips = trip_model.search([
        ("name", "=like", f"{DEMO_TRIP_PREFIX}%")
    ])
    demo_trip_ids = demo_trips.ids

    # 2. Scope demo positions:
    # Strictly require source='simulated' AND (linked to demo trips OR demo vehicles).
    # GUARD: Under NO circumstances delete real telemetry (source='real'),
    # even if accidentally linked to a demo trip prefix.
    v_real = env.ref(
        "uta_transport_monitor.demo_vehicle_01_real",
        raise_if_not_found=False,
    )
    v_sim = env.ref(
        "uta_transport_monitor.demo_vehicle_02_sim",
        raise_if_not_found=False,
    )
    demo_veh_ids = [v.id for v in (v_real, v_sim) if v]

    pos_domain = []
    if demo_trip_ids and demo_veh_ids:
        pos_domain = [
            "&",
            ("source", "=", "simulated"),
            "|",
            ("trip_id", "in", demo_trip_ids),
            ("vehicle_id", "in", demo_veh_ids),
        ]
    elif demo_trip_ids:
        pos_domain = [
            ("source", "=", "simulated"),
            ("trip_id", "in", demo_trip_ids),
        ]
    elif demo_veh_ids:
        pos_domain = [
            ("source", "=", "simulated"),
            ("vehicle_id", "in", demo_veh_ids),
        ]
    else:
        # If neither exists, do not touch any positions
        pos_domain = [("id", "=", 0)]

    demo_positions = pos_model.search(pos_domain)
    pos_count = len(demo_positions)
    if demo_positions:
        _logger.info(
            "Eliminando %d posiciones acotadas del dataset demo...",
            pos_count,
        )
        demo_positions.unlink()

    # 3. Scope demo incidents: strictly linked to demo trips
    inc_count = 0
    if demo_trip_ids:
        demo_incidents = inc_model.search([("trip_id", "in", demo_trip_ids)])
        inc_count = len(demo_incidents)
        if demo_incidents:
            _logger.info(
                "Eliminando %d incidencias acotadas del dataset demo...",
                inc_count,
            )
            demo_incidents.unlink()

    # 4. Scope demo trips
    trip_count = len(demo_trips)
    if demo_trips:
        _logger.info(
            "Eliminando %d recorridos acotados del dataset demo...",
            trip_count,
        )
        demo_trips.unlink()

    return {
        "positions_deleted": pos_count,
        "incidents_deleted": inc_count,
        "trips_deleted": trip_count,
    }

