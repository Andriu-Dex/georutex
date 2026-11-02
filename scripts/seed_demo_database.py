"""
Seed isolated demonstration database (georutex_demo) with 10 executed trips,
1 cancelled trip, 3 role users, and fully evaluated metrics and incidents.
"""
from datetime import datetime, timedelta
import odoo
from odoo import api, SUPERUSER_ID
from odoo.tools import config

def run_seed():
    db_name = "georutex_demo"
    config.parse_config([
        "-c", "/etc/odoo/odoo.conf",
        "--db_host=postgres",
        "--db_user=odoo",
        "--db_password=odoo_dev_password",
        "-d", db_name
    ])
    registry = odoo.registry(db_name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        print("=== INICIANDO SEEDING DE BASE DEMO: georutex_demo ===")

        # 1. Configurar Roles y Usuarios
        group_driver = env.ref("uta_transport_monitor.group_transport_driver")
        group_analyst = env.ref("uta_transport_monitor.group_transport_analyst")
        group_manager = env.ref("uta_transport_monitor.group_transport_manager")

        # Conductor Carlos Morales
        partner_carlos = env.ref("uta_transport_monitor.demo_driver_carlos")
        user_driver = env["res.users"].search([("login", "=", "conductor")])
        if not user_driver:
            user_driver = env["res.users"].create({
                "name": "Carlos Morales (Conductor)",
                "login": "conductor",
                "password": "conductor",
                "partner_id": partner_carlos.id,
                "groups_id": [(6, 0, [group_driver.id, env.ref("base.group_user").id])],
            })
        else:
            user_driver.write({
                "password": "conductor",
                "partner_id": partner_carlos.id,
                "groups_id": [(6, 0, [group_driver.id, env.ref("base.group_user").id])],
            })
        print(f"Usuario Conductor: {user_driver.login} (ID {user_driver.id})")

        # Gestor / Analista de Transporte
        user_analyst = env["res.users"].search([("login", "=", "analista")])
        if not user_analyst:
            user_analyst = env["res.users"].create({
                "name": "Lic. Ana Gómez (Analista de Rutas)",
                "login": "analista",
                "password": "analista",
                "email": "analista@uta.edu.ec",
                "groups_id": [(6, 0, [group_analyst.id, env.ref("base.group_user").id])],
            })
        else:
            user_analyst.write({
                "password": "analista",
                "groups_id": [(6, 0, [group_analyst.id, env.ref("base.group_user").id])],
            })
        print(f"Usuario Analista: {user_analyst.login} (ID {user_analyst.id})")

        user_manager = env["res.users"].search([("login", "=", "gestor")])
        if not user_manager:
            user_manager = env["res.users"].create({
                "name": "Ing. Patricio Silva (Gestor de Rutas)",
                "login": "gestor",
                "password": "gestor",
                "email": "gestor@uta.edu.ec",
                "groups_id": [(6, 0, [group_manager.id, env.ref("base.group_user").id])],
            })
        else:
            user_manager.write({
                "password": "gestor",
                "groups_id": [(6, 0, [group_manager.id, env.ref("base.group_user").id])],
            })
        print(f"Usuario Gestor: {user_manager.login} (ID {user_manager.id})")

        # Administrador (Mitchell Admin)
        user_admin = env["res.users"].search([("login", "=", "admin")])
        if user_admin:
            user_admin.write({
                "password": "admin",
                "groups_id": [(4, group_manager.id)],
            })
            print(f"Usuario Admin: {user_admin.login} (ID {user_admin.id})")

        # 2. Vehículos y Rutas Demo
        v_real = env.ref("uta_transport_monitor.demo_vehicle_01_real")
        v_sim = env.ref("uta_transport_monitor.demo_vehicle_02_sim")
        v_real.write({"driver_id": partner_carlos.id})

        r1 = env.ref("uta_transport_monitor.demo_route_1")
        r2 = env.ref("uta_transport_monitor.demo_route_2")
        r3 = env.ref("uta_transport_monitor.demo_route_3")

        trip_model = env["transport.trip"]
        pos_model = env["transport.vehicle.position"]
        inc_model = env["transport.incident"]
        eval_service = env["transport.trip.evaluation.service"]

        # Limpiar recorridos anteriores de demo si existen
        existing_demo_trips = trip_model.search([("name", "=like", "REC-DEMO-%")])
        if existing_demo_trips:
            print(f"Eliminando {len(existing_demo_trips)} recorridos demo anteriores...")
            existing_demo_trips.unlink()

        # 3. Definición de los 10 Recorridos de Demostración + 1 Cancelado
        base_t = datetime(2026, 11, 15, 7, 0, 0)
        trips_spec = [
            ("REC-DEMO-01-COMPLIANT-TBA1001", v_real, r1, 0, "compliant"),
            ("REC-DEMO-02-COMPLIANT-TBA1002", v_sim, r2, 1, "compliant"),
            ("REC-DEMO-03-DELAY-START-TBA1001", v_real, r3, 2, "delay_start"),
            ("REC-DEMO-04-DELAY-ARRIVAL-TBA1002", v_sim, r1, 3, "delay_arrival"),
            ("REC-DEMO-05-DEVIATION-TBA1001", v_real, r2, 4, "route_deviation"),
            ("REC-DEMO-06-STOP-OMITTED-TBA1002", v_sim, r3, 5, "stop_omitted"),
            ("REC-DEMO-07-GPS-GAP-TBA1001", v_real, r1, 6, "gps_gap"),
            ("REC-DEMO-08-INDETERMINATE-TBA1002", v_sim, r2, 7, "indeterminate"),
            ("REC-DEMO-09-JUSTIFIED-TBA1001", v_real, r3, 8, "justified"),
            ("REC-DEMO-10-COMPLIANT-RET-TBA1002", v_sim, r1, 9, "compliant"),
        ]

        created_trips = []
        for code, veh, route, h_offset, outcome in trips_spec:
            ver = route.current_version_id
            stops = ver.stop_ids.sorted("sequence")
            max_offset_s = max(s.planned_offset_seconds for s in stops) if stops else 1800
            dur_s = max_offset_s

            start_dt = base_t + timedelta(hours=h_offset)
            end_dt = start_dt + timedelta(seconds=dur_s)
            source = "simulated" if veh.is_simulated else "real"

            trip = trip_model.create({
                "name": code,
                "vehicle_id": veh.id,
                "route_id": route.id,
                "route_version_id": ver.id,
                "driver_id": veh.driver_id.id if veh.driver_id else partner_carlos.id,
                "driver_user_id": user_driver.id if veh.driver_id == partner_carlos else None,
                "scheduled_start_utc": start_dt,
                "scheduled_end_utc": end_dt,
                "source_type": source,
                "state": "draft",
            })
            trip.action_schedule()
            trip.action_start()

            act_start = start_dt
            act_end = end_dt
            if outcome == "delay_start":
                act_start = start_dt + timedelta(minutes=10)
            elif outcome in ("delay_arrival", "justified"):
                act_end = end_dt + timedelta(minutes=15)

            act_dist = (ver.estimated_distance_m or 4200.0) + (150.0 if outcome != "compliant" else 20.0)
            trip.write({
                "actual_start_utc": act_start,
                "actual_end_utc": act_end,
                "manual_start_utc": act_start,
                "manual_end_utc": act_end,
                "scheduled_distance_m": ver.estimated_distance_m or 4200.0,
                "actual_distance_m": act_dist,
                "state": "completed",
            })

            if outcome != "indeterminate":
                for s_idx in range(len(stops)):
                    st_curr = stops[s_idx]
                    if s_idx == 0:
                        t_curr = act_start
                    elif s_idx == len(stops) - 1:
                        t_curr = act_end
                    else:
                        t_curr = act_start + timedelta(seconds=st_curr.planned_offset_seconds)

                    lat = st_curr.latitude
                    lon = st_curr.longitude

                    if outcome == "stop_omitted" and s_idx == 1:
                        lat += 0.0060  # Desplazar 660m para no entrar en radio de parada

                    # Punto principal en parada
                    pos_model.create({
                        "trip_id": trip.id,
                        "vehicle_id": veh.id,
                        "latitude": lat,
                        "longitude": lon,
                        "speed": 35.0,
                        "fix_time": t_curr,
                        "source": source,
                        "is_valid": True,
                    })

                    # Punto de salida del origen para registrar salida del radio
                    if s_idx == 0:
                        pos_model.create({
                            "trip_id": trip.id,
                            "vehicle_id": veh.id,
                            "latitude": lat + 0.0006,
                            "longitude": lon,
                            "speed": 25.0,
                            "fix_time": act_start + timedelta(minutes=2),
                            "source": source,
                            "is_valid": True,
                        })

                    # Puntos intermedios hacia la siguiente parada (cada 60s)
                    if s_idx < len(stops) - 1:
                        st_next = stops[s_idx + 1]
                        if s_idx + 1 == len(stops) - 1:
                            t_next = act_end
                        else:
                            t_next = act_start + timedelta(seconds=st_next.planned_offset_seconds)

                        interval_s = int((t_next - t_curr).total_seconds())

                        if outcome == "gps_gap" and s_idx == 1:
                            # Salto de telemetría de 300 segundos (> 180s threshold)
                            # Generamos un único punto adelantado 300 segundos para crear el gap
                            pos_model.create({
                                "trip_id": trip.id,
                                "vehicle_id": veh.id,
                                "latitude": lat + 0.0005,
                                "longitude": lon + 0.0005,
                                "speed": 40.0,
                                "fix_time": t_curr + timedelta(seconds=300),
                                "source": source,
                                "is_valid": True,
                            })
                            continue

                        n_inter = max(1, interval_s // 60)
                        step_time = interval_s / float(n_inter)
                        for step_i in range(1, n_inter):
                            frac = step_i / float(n_inter)
                            i_lat = lat + frac * (st_next.latitude - lat)
                            i_lon = lon + frac * (st_next.longitude - lon)
                            i_time = t_curr + timedelta(seconds=int(step_i * step_time))

                            # En caso de desvío de ruta, desviar 3 puntos consecutivos fuera del corredor
                            if outcome == "route_deviation" and s_idx == 1:
                                i_lat += 0.0035  # ~380m fuera del corredor

                            pos_model.create({
                                "trip_id": trip.id,
                                "vehicle_id": veh.id,
                                "latitude": i_lat,
                                "longitude": i_lon,
                                "speed": 40.0,
                                "fix_time": i_time,
                                "source": source,
                                "is_valid": True,
                            })

            # Ejecutar evaluación mediante el motor formal
            eval_service.evaluate_trip(trip)

            # Para el recorrido 9: registrar y aprobar justificación formal
            if outcome == "justified":
                inc = inc_model.search([("trip_id", "=", trip.id), ("incident_type", "=", "delay_arrival")], limit=1)
                if not inc:
                    inc = inc_model.search([("trip_id", "=", trip.id)], limit=1)
                if inc:
                    inc.write({
                        "justification_notes": "Retraso atribuible a congestión vehicular extraordinaria por trabajos en la vía.",
                    })
                    inc.with_user(user_manager).action_approve_justification()
                    eval_service.evaluate_trip(trip)

            created_trips.append(trip)
            print(f"Recorrido creado y evaluado: {code} -> {trip.evaluation_status} (Bruto: {trip.last_evaluation_id.is_compliant_gross}, Ajustado: {trip.last_evaluation_id.is_compliant_adjusted})")

        # 4. Crear Recorrido 11 Cancelado (Demuestra exclusión de denominador)
        t_cancel = trip_model.create({
            "name": "REC-DEMO-11-CANCELLED-TBA1002",
            "vehicle_id": v_sim.id,
            "route_id": r2.id,
            "route_version_id": r2.current_version_id.id,
            "driver_id": partner_carlos.id,
            "scheduled_start_utc": base_t + timedelta(hours=10),
            "scheduled_end_utc": base_t + timedelta(hours=10, minutes=30),
            "source_type": "simulated",
            "state": "cancelled",
        })
        print(f"Recorrido cancelado creado: {t_cancel.name} (Estado: {t_cancel.state})")

        cr.commit()
        print("=== SEEDING COMPLETADO EXITOSAMENTE CON 10 RECORRIDOS EJECUTADOS + 1 CANCELADO ===")

if __name__ == "__main__":
    run_seed()
