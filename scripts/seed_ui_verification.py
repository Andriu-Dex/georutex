#!/usr/bin/env python3
"""
Non-destructive, idempotent simulated seed for verifying the GeoRutex authenticated UI.

- Marks ALL generated telemetry and trips strictly as `simulated` (never masquerades as real GPS).
- Uses distinct `SIM-UI-*` prefixes so records are easy to identify and remove cleanly.
- Never modifies existing real operational records or the `admin` user's password.
- Covers all 3 roles (Admin, Analyst, Active Driver, Unassigned Driver), 3 routes (4 stops each),
  3 monitored vehicles (online, stale, offline), trips across all states (in_progress, scheduled,
  completed/evaluated across multiple days), and incidents (pending, justified, automatic).

Usage (inside Odoo container via `odoo shell`):
    docker exec -i -e GRX_SEED_PASSWORD='<your-local-seed-pass>' georutex-odoo odoo shell -c /etc/odoo/odoo.conf -d georutex --no-http < scripts/seed_ui_verification.py

To remove ONLY the simulated records created by this script:
    docker exec -i -e GRX_SEED_CLEANUP=1 georutex-odoo odoo shell -c /etc/odoo/odoo.conf -d georutex --no-http < scripts/seed_ui_verification.py
"""

from datetime import datetime, timedelta, timezone
import json
import os


SEED_TAG = "SIM-UI"
MODEL_POSITION = "transport.vehicle.position"
MODEL_INCIDENT = "transport.incident"
MODEL_TRIP = "transport.trip"
MODEL_USERS = "res.users"
OP_LIKE = "=like"

ANALYST_LOGIN = "analista.ui@georutex.local"
DRIVER_ACTIVE_LOGIN = "conductor.activo@georutex.local"
DRIVER_IDLE_LOGIN = "conductor.espera@georutex.local"

STOP_CAMPUS_HUACHI = "Campus Huachi"
STOP_CAMPUS_INGAHURCO = "Campus Ingahurco"


def _utc_now_naive():
    """Return current UTC datetime as naive (Odoo 16 Datetime field convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_seed_credential():
    """Read local seed credential from environment without hardcoding secrets."""
    secret = os.environ.get("GRX_SEED_PASSWORD", "").strip()
    if not secret:
        raise RuntimeError(
            "GRX_SEED_PASSWORD environment variable is required to seed UI test accounts."
        )
    return secret


def _cleanup_seed_records(env):
    """Delete strictly records created by this UI seed (prefixed with SIM-UI)."""
    eval_model = env["transport.trip.evaluation"]
    inc_model = env[MODEL_INCIDENT]
    pos_model = env[MODEL_POSITION]
    trip_model = env[MODEL_TRIP]
    ver_model = env["transport.route.version"]
    route_model = env["transport.route"]
    veh_model = env["fleet.vehicle"]

    trips = trip_model.search([("name", OP_LIKE, f"{SEED_TAG}-%")])
    if trips:
        eval_model.search([("trip_id", "in", trips.ids)]).unlink()
        inc_model.search([("trip_id", "in", trips.ids)]).unlink()
        pos_model.search([("trip_id", "in", trips.ids), ("source", "=", "simulated")]).unlink()
        trips.sudo().write({"state": "draft"})
        trips.sudo().unlink()

    vehicles = veh_model.search([("license_plate", OP_LIKE, f"{SEED_TAG}-%")])
    if vehicles:
        pos_model.search([("vehicle_id", "in", vehicles.ids), ("source", "=", "simulated")]).unlink()
        vehicles.sudo().unlink()

    routes = route_model.search([("code", OP_LIKE, f"{SEED_TAG}-%")])
    if routes:
        ver_model.search([("route_id", "in", routes.ids)]).sudo().unlink()
        routes.sudo().unlink()

    seed_logins = [ANALYST_LOGIN, DRIVER_ACTIVE_LOGIN, DRIVER_IDLE_LOGIN]
    users = env[MODEL_USERS].with_context(active_test=False).search([("login", "in", seed_logins)])
    if users:
        users.write({"active": False})

    env.cr.commit()
    print(json.dumps({"action": "cleanup", "status": "ok", "tag": SEED_TAG}))


def _ensure_user(env, name, login, group_xmlid, credential, extra_groups=None):
    group_user = env.ref("base.group_user")
    target_group = env.ref(group_xmlid)
    group_ids = [group_user.id, target_group.id]
    for g_xml in (extra_groups or []):
        group_ids.append(env.ref(g_xml).id)

    users_model = env[MODEL_USERS].with_context(active_test=False, no_reset_password=True)
    user = users_model.search([("login", "=", login)], limit=1)
    vals = {
        "name": name,
        "login": login,
        "email": login,
        "password": credential,
        "active": True,
        "lang": env.user.lang or "en_US",
        "tz": "America/Guayaquil",
        "groups_id": [(6, 0, group_ids)],
    }
    if user:
        user.write(vals)
    else:
        user = users_model.create(vals)
    return user


def _ensure_route_with_version(env, code, name, origin, destination, stops_spec):
    route_model = env["transport.route"]
    ver_model = env["transport.route.version"]
    stop_model = env["transport.route.stop"]

    route = route_model.search([("code", "=", code)], limit=1)
    if not route:
        route = route_model.create({
            "code": code,
            "name": name,
            "origin_name": origin,
            "destination_name": destination,
            "direction": "outbound",
            "active": True,
        })

    ver = ver_model.search([("route_id", "=", route.id), ("state", "=", "approved")], limit=1)
    if not ver:
        ver = ver_model.create({
            "route_id": route.id,
            "version_number": 1,
            "state": "draft",
            "estimated_distance_m": 5400.0,
        })
        for idx, (s_name, lat, lon, offset_s, s_type) in enumerate(stops_spec, start=1):
            stop_model.create({
                "route_version_id": ver.id,
                "sequence": idx * 10,
                "name": s_name,
                "latitude": lat,
                "longitude": lon,
                "radius_m": 60.0,
                "planned_offset_seconds": offset_s,
                "stop_type": s_type,
                "required": True,
            })
        ver.action_approve()

    return route, ver


def _ensure_vehicle(env, brand_model, plate, unit_name, driver_partner, traccar_uid, lat, lon, speed, minutes_ago):
    veh_model = env["fleet.vehicle"]
    pos_model = env[MODEL_POSITION]

    veh = veh_model.search([("license_plate", "=", plate)], limit=1)
    vals = {
        "model_id": brand_model.id,
        "license_plate": plate,
        "operational_name": unit_name,
        "driver_id": driver_partner.id if driver_partner else False,
        "gps_tracking_enabled": True,
        "is_simulated": True,
        "traccar_unique_id": traccar_uid,
    }
    if veh:
        veh.write(vals)
    else:
        veh = veh_model.create(vals)

    fix_dt = _utc_now_naive() - timedelta(minutes=minutes_ago)
    pos_model.create({
        "vehicle_id": veh.id,
        "latitude": lat,
        "longitude": lon,
        "speed": speed,
        "fix_time": fix_dt,
        "source": "simulated",
    })
    return veh


def _seed_users(env, credential):
    """Ensure Admin has manager group and create/update simulated role test users."""
    group_manager = env.ref("uta_transport_monitor.group_transport_manager")
    admin_user = env[MODEL_USERS].search([("login", "=", "admin")], limit=1)
    if admin_user and group_manager not in admin_user.groups_id:
        admin_user.write({"groups_id": [(4, group_manager.id)]})

    analyst_user = _ensure_user(
        env,
        "Sofía Morales",
        ANALYST_LOGIN,
        "uta_transport_monitor.group_transport_analyst",
        credential,
    )
    driver_active_user = _ensure_user(
        env,
        "Carlos Paredes",
        DRIVER_ACTIVE_LOGIN,
        "uta_transport_monitor.group_transport_driver",
        credential,
    )
    _ensure_user(
        env,
        "Elena Ríos",
        DRIVER_IDLE_LOGIN,
        "uta_transport_monitor.group_transport_driver",
        credential,
    )
    return admin_user, analyst_user, driver_active_user


def _seed_vehicles(env, admin_user, driver_active_user):
    """Ensure fleet brand/model and 3 simulated monitored vehicles."""
    brand = env["fleet.vehicle.model.brand"].search([("name", "=", "GeoBus")], limit=1)
    if not brand:
        brand = env["fleet.vehicle.model.brand"].create({"name": "GeoBus"})
    vmodel = env["fleet.vehicle.model"].search(
        [("name", "=", "Urbano 40"), ("brand_id", "=", brand.id)], limit=1
    )
    if not vmodel:
        vmodel = env["fleet.vehicle.model"].create({"name": "Urbano 40", "brand_id": brand.id})

    v_online = _ensure_vehicle(
        env, vmodel, f"{SEED_TAG}-1001", "Unidad Norte 01",
        driver_active_user.partner_id, "SIM-UI-DEV-1001",
        -1.2465, -78.6255, 32.0, minutes_ago=1,
    )
    v_stale = _ensure_vehicle(
        env, vmodel, f"{SEED_TAG}-2002", "Unidad Sur 02",
        admin_user.partner_id if admin_user else False, "SIM-UI-DEV-2002",
        -1.2640, -78.6365, 21.0, minutes_ago=7,
    )
    v_offline = _ensure_vehicle(
        env, vmodel, f"{SEED_TAG}-3003", "Unidad Intercampus 03",
        False, "SIM-UI-DEV-3003",
        -1.2395, -78.6180, 0.0, minutes_ago=95,
    )
    return v_online, v_stale, v_offline


def _seed_routes(env):
    """Ensure 3 approved routes with 4 stops each."""
    r1, v1 = _ensure_route_with_version(
        env,
        f"{SEED_TAG}-R01",
        "Ruta 01 — Corredor Norte",
        "Terminal Norte",
        STOP_CAMPUS_HUACHI,
        [
            ("Terminal Norte", -1.2382, -78.6195, 0, "origin"),
            ("Parque Cevallos", -1.2440, -78.6240, 480, "checkpoint"),
            ("Av. Bolivariana", -1.2515, -78.6290, 960, "checkpoint"),
            (STOP_CAMPUS_HUACHI, -1.2685, -78.6260, 1500, "destination"),
        ],
    )
    r2, v2 = _ensure_route_with_version(
        env,
        f"{SEED_TAG}-R02",
        "Ruta 02 — Corredor Sur",
        "Estación Sur",
        STOP_CAMPUS_INGAHURCO,
        [
            ("Estación Sur", -1.2750, -78.6380, 0, "origin"),
            ("Redondel Huachi", -1.2650, -78.6330, 420, "checkpoint"),
            ("Av. Atahualpa", -1.2545, -78.6285, 900, "checkpoint"),
            (STOP_CAMPUS_INGAHURCO, -1.2412, -78.6210, 1440, "destination"),
        ],
    )
    r3, v3 = _ensure_route_with_version(
        env,
        f"{SEED_TAG}-R03",
        "Ruta 03 — Circuito Intercampus",
        STOP_CAMPUS_INGAHURCO,
        STOP_CAMPUS_HUACHI,
        [
            (STOP_CAMPUS_INGAHURCO, -1.2412, -78.6210, 0, "origin"),
            ("Av. Cevallos Centro", -1.2455, -78.6265, 360, "checkpoint"),
            ("Mall de los Andes", -1.2580, -78.6310, 840, "checkpoint"),
            (STOP_CAMPUS_HUACHI, -1.2685, -78.6260, 1320, "destination"),
        ],
    )
    return (r1, v1), (r2, v2), (r3, v3)


def _seed_positions_for_stops(pos_model, trip, stops, start_dt, delay_s=0, deviate_idx=None, omit_idx=None):
    """Create simulated GPS positions along route stops with optional delay/deviation."""
    for idx, st in enumerate(stops):
        if omit_idx is not None and idx == omit_idx:
            continue
        lat = st.latitude
        lon = st.longitude
        if deviate_idx is not None and idx == deviate_idx:
            lat += 0.0045
            lon += 0.0045
        fix_dt = start_dt + timedelta(seconds=st.planned_offset_seconds + delay_s)
        pos_model.create({
            "vehicle_id": trip.vehicle_id.id,
            "trip_id": trip.id,
            "association_status": "associated",
            "latitude": lat,
            "longitude": lon,
            "speed": 28.0 if idx < len(stops) - 1 else 0.0,
            "fix_time": fix_dt,
            "source": "simulated",
        })


def _apply_historical_trip_mode(pos_model, trip, ver, st_dt, end_dt, mode):
    """Populate telemetry and completion state for a historical verification trip."""
    stops = ver.stop_ids.sorted("sequence")
    base_dist = ver.estimated_distance_m or 5400.0
    mode_config = {
        "compliant": (20, 20, 0.0, None),
        "justified_delay": (720, 720, 120.0, None),
        "deviation": (90, 240, 650.0, 1),
    }
    if mode not in mode_config:
        trip.write({
            "actual_start_utc": False,
            "actual_end_utc": False,
            "actual_distance_m": 0.0,
            "state": "completed",
        })
        return

    start_delay, end_delay, extra_dist, deviate_idx = mode_config[mode]
    _seed_positions_for_stops(pos_model, trip, stops, st_dt, delay_s=start_delay, deviate_idx=deviate_idx)
    trip.write({
        "actual_start_utc": st_dt + timedelta(seconds=start_delay),
        "actual_end_utc": end_dt + timedelta(seconds=end_delay),
        "actual_distance_m": base_dist + extra_dist,
        "state": "completed",
    })


def _justify_trip_incidents(env, trip, driver_active_user, analyst_user, now_utc):
    """Mark automatic incidents on a delayed trip as justified and re-evaluate."""
    inc_model = env[MODEL_INCIDENT]
    eval_service = env["transport.trip.evaluation.service"]
    auto_incs = inc_model.search([("trip_id", "=", trip.id)])
    for inc in auto_incs:
        inc.write({
            "justification_notes": "Congestión severa por cierre temporal en Av. Cevallos.",
            "justification_submitted_by": driver_active_user.id,
            "justification_submitted_at": now_utc - timedelta(days=1),
            "review_notes": "Verificado con reporte de tránsito municipal.",
            "reviewed_by": analyst_user.id,
            "reviewed_at": now_utc - timedelta(hours=18),
            "state": "justified",
        })
    eval_service.evaluate_trip(trip)


def _seed_historical_trips(env, now_utc, vehicles, routes, users):
    """Seed completed and evaluated simulated trips across recent days."""
    v_online, v_stale, v_offline = vehicles
    (r1, v1), (r2, v2), (r3, v3) = routes
    admin_user, analyst_user, driver_active_user = users

    trip_model = env[MODEL_TRIP]
    pos_model = env[MODEL_POSITION]
    eval_service = env["transport.trip.evaluation.service"]

    historical_specs = [
        (f"{SEED_TAG}-TRIP-03", 3, 2, v_online, r1, v1, driver_active_user, "compliant"),
        (f"{SEED_TAG}-TRIP-04", 2, 3, v_stale, r2, v2, admin_user, "compliant"),
        (f"{SEED_TAG}-TRIP-05", 2, 1, v_online, r3, v3, driver_active_user, "justified_delay"),
        (f"{SEED_TAG}-TRIP-06", 1, 2, v_stale, r2, v2, admin_user, "deviation"),
        (f"{SEED_TAG}-TRIP-07", 0, 3, v_online, r1, v1, driver_active_user, "compliant"),
        (f"{SEED_TAG}-TRIP-08", 1, 4, v_offline, r3, v3, admin_user, "insufficient_gps"),
    ]

    evaluated_count = 0
    for code, days_ago, h_ago, veh, route, ver, d_user, mode in historical_specs:
        st_dt = now_utc - timedelta(days=days_ago, hours=h_ago)
        stops = ver.stop_ids.sorted("sequence")
        dur_s = max((s.planned_offset_seconds for s in stops), default=1500)
        end_dt = st_dt + timedelta(seconds=dur_s)
        trip = trip_model.create({
            "name": code,
            "vehicle_id": veh.id,
            "route_id": route.id,
            "route_version_id": ver.id,
            "driver_id": d_user.partner_id.id if d_user else False,
            "driver_user_id": d_user.id if d_user else False,
            "scheduled_start_utc": st_dt,
            "scheduled_end_utc": end_dt,
            "source_type": "simulated",
            "state": "draft",
        })
        trip.action_schedule()
        trip.action_start()
        _apply_historical_trip_mode(pos_model, trip, ver, st_dt, end_dt, mode)

        if eval_service.evaluate_trip(trip):
            evaluated_count += 1
        if mode == "justified_delay":
            _justify_trip_incidents(env, trip, driver_active_user, analyst_user, now_utc)

    return len(historical_specs), evaluated_count


def run_ui_seed(env):
    """Run cleanup or full idempotent simulated UI seed."""
    if os.environ.get("GRX_SEED_CLEANUP") == "1":
        _cleanup_seed_records(env)
        return

    credential = _get_seed_credential()
    _cleanup_seed_records(env)

    users = _seed_users(env, credential)
    admin_user, _analyst_user, driver_active_user = users
    vehicles = _seed_vehicles(env, admin_user, driver_active_user)
    v_online = vehicles[0]
    routes = _seed_routes(env)
    (r1, v1), _r2_pair, (r3, v3) = routes

    trip_model = env[MODEL_TRIP]
    pos_model = env[MODEL_POSITION]
    inc_model = env[MODEL_INCIDENT]
    now_utc = _utc_now_naive().replace(second=0, microsecond=0)

    active_start = now_utc - timedelta(minutes=12)
    t_active = trip_model.create({
        "name": f"{SEED_TAG}-TRIP-01",
        "vehicle_id": v_online.id,
        "route_id": r1.id,
        "route_version_id": v1.id,
        "driver_id": driver_active_user.partner_id.id,
        "driver_user_id": driver_active_user.id,
        "scheduled_start_utc": active_start,
        "scheduled_end_utc": active_start + timedelta(minutes=25),
        "source_type": "simulated",
        "state": "draft",
    })
    t_active.action_schedule()
    t_active.action_start()
    _seed_positions_for_stops(pos_model, t_active, v1.stop_ids.sorted("sequence")[:2], active_start)

    sched_start = now_utc + timedelta(hours=2)
    t_sched = trip_model.create({
        "name": f"{SEED_TAG}-TRIP-02",
        "vehicle_id": v_online.id,
        "route_id": r3.id,
        "route_version_id": v3.id,
        "driver_id": driver_active_user.partner_id.id,
        "driver_user_id": driver_active_user.id,
        "scheduled_start_utc": sched_start,
        "scheduled_end_utc": sched_start + timedelta(minutes=22),
        "source_type": "simulated",
        "state": "draft",
    })
    t_sched.action_schedule()

    hist_count, evaluated_count = _seed_historical_trips(env, now_utc, vehicles, routes, users)

    inc_model.create({
        "trip_id": t_active.id,
        "incident_type": "traffic_congestion",
        "source": "manual",
        "severity": "medium",
        "timestamp_utc": now_utc - timedelta(minutes=5),
        "description": "Tráfico denso a la altura del Parque Cevallos por obras viales.",
        "evidence_data": "Reporte enviado por conductor desde unidad SIM-UI-1001.",
        "state": "pending",
    })

    env.cr.commit()
    print(json.dumps({
        "action": "seed",
        "status": "ok",
        "tag": SEED_TAG,
        "vehicles": 3,
        "routes": 3,
        "trips": 2 + hist_count,
        "evaluations": evaluated_count,
        "users": {
            "analyst": ANALYST_LOGIN,
            "driver_active": DRIVER_ACTIVE_LOGIN,
            "driver_idle": DRIVER_IDLE_LOGIN,
        },
    }, ensure_ascii=False))


_odoo_env = globals().get("env")
if _odoo_env is not None:
    run_ui_seed(_odoo_env)
