# Informe de Ejecución Técnica — Fase 2: Modelado y Gestión Operacional

**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Módulo Odoo:** `uta_transport_monitor` (v16.0.2.0.0)  
**Fecha:** 2026-11-01  
**Referencia:** `instruction.md` / `docs/requirements.md` (Fase 2, Secciones 6, 7 y 13) / `docs/architecture.md`  
**Estado:** `COMPLETADO Y VERIFICADO`  

---

## 1. Resumen Ejecutivo

Conforme a las directrices de `instruction.md`, se evaluaron y ejecutaron satisfactoriamente las actividades de la **Fase 2: Modelado y gestión operacional**. Previo a la construcción de los nuevos modelos, se ejecutó un endurecimiento técnico de la integración previa (entropía de 64 bits en `uniqueId`, clasificación estricta de origen físico `is_physical_accredited`, bloqueo de concurrencia y deduplicación por `traccar_position_id`).

Posteriormente, se materializó la arquitectura de gestión operacional en Odoo 16:
1. **Catálogo y versión de rutas:** Rutas comerciales con origen, destino, sentido y trazado (`transport.route`), con versionado inmutable y parámetros canónicos congelables (`transport.route.version`).
2. **Puntos de control geográficos:** Paradas obligatorias (`transport.route.stop`) con geocercas configurables, validación de coordenadas WGS84 y obligatoriedad de al menos 4 puntos para aprobación.
3. **Programación y prevención de solapamientos:** Recorridos operacionales (`transport.trip`) con detección estricta de conflictos simultáneos para el mismo vehículo o conductor, congelamiento inmutable de parámetros (`parameter_snapshot_json`) y generación automática de visitas programadas (`transport.stop.visit`).
4. **Seguridad y vistas adaptadas:** Vistas administrativas completas en español, Kanban ergonómico para conductores ("Mis Recorridos") y reglas por registro (`ir.rule`) con resolución limpia para usuarios multi-rol.
5. **Datos demostrativos:** 2 vehículos (`BUS-01` real acreditado y `BUS-02` simulado), 3 rutas de referencia en Ambato (Huachi - Ingahurco, Huachi - Querochaca, Circunvalación Centro) con al menos 4 puntos de control explícitos cada una.

Toda la implementación fue validada en el entorno aislado `georutex_test`, ejecutando 15 pruebas unitarias Pytest y 25 pruebas nativas de Odoo (35 tests estadísticos) con 100 % de aprobación y 0 advertencias de estilo en Flake8.

---

## 2. Verificaciones Técnicas Iniciales y Endurecimiento de Fase 1

En cumplimiento de la Sección 2 de `instruction.md`, se auditaron y corrigieron los siguientes aspectos críticos:

| Aspecto Evaluado | Condición Previa | Ajuste Implementado | Verificación / Test |
|---|---|---|---|
| **Fortaleza de identificadores** | Token de 4 bytes (32 bits, 8 hex) | Aumento a `secrets.token_hex(8).upper()` (64 bits de entropía criptográfica, formato `UTA-BUS-` + 16 hex). Restricción `@api.constrains` de unicidad en vehículos activos para `traccar_device_id` y `traccar_unique_id` (RF-08). | `test_generate_secure_unique_id`<br>`test_traccar_device_uniqueness_constraint` |
| **Procedencia de posiciones GPS** | Clasificación derivada de simulación genérica | Incorporación del campo `is_physical_accredited` en `fleet.vehicle`. Una posición **únicamente** se clasifica como `real` si el vehículo cuenta con acreditación física formal y la telemetría no contiene flags de `mock` o `simulated`. | `test_unaccredited_vehicle_is_tagged_simulated`<br>`test_mock_attributes_tagged_simulated` |
| **Deduplicación y concurrencia** | Búsqueda simple por tiempo | Deduplicación compuesta por `traccar_position_id` y `(traccar_device_id, fix_time)`. Bloqueo transaccional de fila `SELECT ... FOR UPDATE NOWAIT` en el vehículo durante la sincronización para evitar colisiones de hilos concurrentes. | `test_sync_idempotency_and_telemetry_update` |
| **Seguridad de reglas multi-grupo** | Posible conflicto si usuario pertenece a múltiples grupos | Redefinición exhaustiva de reglas por registro en `security/rules.xml` para posiciones, recorridos y visitas de parada; validación de herencia ORM de grupos para usuarios que combinan `Conductor` y `Analista`. | `test_multi_group_security_resolution`<br>`test_driver_record_rule_isolation` |
| **Exposición de servicios** | Exposición de puertos | Conexiones de base de datos Postgres (5433) y consola Traccar (8082) enlazadas estrictamente a `127.0.0.1`. Únicamente el puerto receptor OsmAnd (5055) y la interfaz de usuario de Odoo (8069) quedan accesibles externamente. | Auditoría de `compose.yaml` |

---

## 3. Arquitectura y Modelos Implementados (Fase 2)

Se respetó la separación estricta de responsabilidades entre `domain/`, `models/`, `services/`, `views/` y `security/` descrita en `docs/architecture.md`:

```
addons/uta_transport_monitor/
├── domain/
│   └── geo.py                          # Funciones puras: Haversine, bearing, velocidad, distancias de polilínea
├── models/
│   ├── fleet_vehicle.py                # Extensión de fleet.vehicle: acreditación, unicidad y recorridos
│   ├── transport_route.py              # transport.route: Rutas comerciales (origen, destino, sentido)
│   ├── transport_route_version.py      # transport.route.version: Parámetros canónicos y polilínea GeoJSON
│   ├── transport_route_stop.py         # transport.route.stop: Puntos de control geográficos y geocercas
│   ├── transport_trip.py               # transport.trip: Recorridos operacionales, snapshot y estados
│   ├── transport_stop_visit.py         # transport.stop.visit: Visitas y horarios programados
│   └── transport_position.py           # transport.vehicle.position: Telemetrías GPS vinculadas a viajes
├── security/
│   ├── groups.xml                      # Categoría y grupos: Manager, Analyst, Driver
│   ├── ir.model.access.csv             # Permisos CRUD por modelo y grupo
│   └── rules.xml                       # Reglas por registro (aislamiento de conductor y acceso global)
├── views/
│   ├── transport_route_views.xml       # Formularios y listados de rutas
│   ├── transport_route_version_views.xml # Gestión de versiones, parámetros y paradas
│   ├── transport_trip_views.xml        # Listado, Kanban para conductores ("Mis Recorridos") y formulario
│   ├── fleet_vehicle_views.xml         # Formulario de flota con acreditación física y smart buttons
│   └── menu_views.xml                  # Organización de menús (Operaciones, Rutas y Flota, Telemetría)
├── data/
│   ├── ir_sequence_data.xml            # Secuencia para códigos REC-YYYY-NNNN
│   └── ir_cron_data.xml                # Sincronización automática de GPS
└── demo/
    └── transport_demo_data.xml         # Datos de demostración (2 vehículos, 3 rutas, 12 paradas)
```

### 3.1. Detalle de Modelos de Negocio

#### `transport.route` (Ruta de Transporte)
- **Campos principales:** `code` (único, indexado), `name`, `description`, `origin_name`, `destination_name`, `direction` (`outbound`, `inbound`, `circular`, `other`), `active`, `current_version_id`.
- **Restricciones:** Unicidad de código; validación de origen y destino distintos salvo sentido circular.
- **Acciones:** `action_view_versions`, `action_view_trips`.

#### `transport.route.version` (Versión de Ruta y Parámetros)
- **Campos principales:** `route_id`, `version_number`, `state` (`draft`, `approved`, `archived`), `reference_polyline` (GeoJSON), `estimated_distance_m`, `active_for_new_trips`, `approved_at`, `approved_by_id`.
- **Parámetros canónicos persistidos (Sección 7.1):**
  - `stop_radius_m`: 30.0 m (radio de proximidad).
  - `route_corridor_m`: 40.0 m (semiancho de corredor).
  - `lateness_tolerance_s`: 300 s (tolerancia de puntualidad).
  - `gps_gap_threshold_s`: 180 s (umbral de pérdida de señal).
  - `minimum_consecutive_deviation_points`: 2 puntos.
  - `minimum_deviation_duration_s`: 10 s.
  - `geo_accuracy_max_m`: 100.0 m.
- **Reglas de aprobación (RF-09, RF-10):** Requiere al menos 4 puntos de control obligatorios y polilínea válida de al menos 2 vértices.
- **Inmutabilidad histórica (RF-14):** Al contar con viajes asociados (`trip_count > 0`), se bloquea la modificación de parámetros críticos o la alteración de paradas.

#### `transport.route.stop` (Punto de Control / Parada)
- **Campos principales:** `route_version_id`, `sequence`, `name`, `latitude`, `longitude`, `radius_m`, `required`, `stop_type` (`origin`, `checkpoint`, `destination`), `planned_offset_seconds`, `notes`.
- **Restricciones:** Coordenadas WGS84 (`lat` [-90, 90], `lon` [-180, 180]), radio > 0 m, tiempo programado ≥ 0 s, unicidad de secuencia en la misma versión.

#### `transport.trip` (Recorrido Operacional)
- **Campos principales:** `name` (secuencia automática), `vehicle_id`, `driver_id`, `driver_user_id`, `route_id`, `route_version_id`, `source_type` (`real`, `simulated`), `state` (`draft`, `scheduled`, `in_progress`, `completed`, `incomplete`, `cancelled`, `insufficient_data`).
- **Tiempos programados y reales:** `scheduled_start_utc`, `scheduled_end_utc`, `actual_start_utc`, `actual_end_utc`, `scheduled_distance_m`, `actual_distance_m`.
- **Congelamiento de Parámetros (RF-14):** Al confirmar programación (`action_schedule`), genera un snapshot inmutable en JSON (`parameter_snapshot_json`) y genera los registros de visitas (`transport.stop.visit`) proyectando las horas estimadas de paso según los offsets.
- **Prevención de conflictos de asignación (RF-12):** Validación ORM estricta que impide solapamientos en intervalos `[scheduled_start_utc, scheduled_end_utc]` para el mismo vehículo o para el mismo conductor.

#### `transport.stop.visit` (Visita a Parada por Recorrido)
- **Campos principales:** `trip_id`, `route_stop_id`, `sequence`, `stop_name`, `stop_type`, `required`, `latitude`, `longitude`, `radius_m`, `scheduled_at_utc`, `first_arrival_utc`, `departure_utc`, `status` (`pending`, `on_time`, `late`, `missed`, `not_determinable`), `delay_s`, `min_distance_m`.

---

## 4. UI/UX y Accesibilidad

Se diseñó la interfaz de usuario priorizando la ergonomía, la claridad visual y la accesibilidad para dispositivos móviles y escritorios de despachadores:

1. **Vistas de Recorridos Adaptadas para Conductores:**
   - Menú dedicado **"Mis Recorridos"** con filtro predeterminado hacia el usuario logueado (`driver_user_id = uid`).
   - Vista **Kanban móvil** con tarjetas legibles, iconos con atributos `title` descriptivos para lectores de pantalla, colores semánticos por estado (`bg-success`, `bg-warning text-dark`, `bg-primary`, `bg-secondary`) y badges de origen (`Simulado` vs `GPS Real`).
2. **Formularios con Statusbar y Cintas Visuales:**
   - Cintas visuales de advertencia (`web_ribbon`) en amarillo para datos simulados y verde para versiones aprobadas.
   - Botoneras inteligentes (*smart buttons*) con conteo en vivo de paradas, recorridos y telemetrías GPS.
   - Pestaña de auditoría con JSON inmutable de parámetros canónicos para despachadores y analistas.

---

## 5. Datos Demostrativos Acreditados (Ambato, Ecuador)

Se registraron en `demo/transport_demo_data.xml` las entidades mínimas requeridas por el marco académico:

- **2 Vehículos Monitoreados:**
  - `BUS-01` (Placa `TBA-1001`): Origen físico acreditado (`is_physical_accredited = True`), fuente `real`, dispositivo Traccar 101 (`UTA-BUS-DEMO0101`).
  - `BUS-02` (Placa `TBA-1002`): Vehículo de simulación (`is_simulated = True`), fuente `simulated`, dispositivo Traccar 102 (`UTA-BUS-DEMO0102`).
- **3 Rutas Comerciales con Versión 1 Aprobada:**
  - `RUT-01-HUA-ING`: Campus Huachi → Campus Ingahurco (4.20 km estimados).
  - `RUT-02-HUA-QUE`: Campus Huachi → Campus Querochaca (12.50 km estimados).
  - `RUT-03-CIR-CEN`: Circunvalación Centro - Huachi (5.80 km estimados).
- **12 Puntos de Control Explícitos (4 por cada ruta):**
  - Cada versión cuenta con puntos geodésicos reales en Ambato (ej. Redondel Huachi Chico, Parque Cevallos, Paso Lateral Sur, Benítez, Miraflores, Socavón), con secuencias de 10 a 40 y offsets programados.

---

## 6. Resultados de Verificación y Pruebas Automatizadas

### 6.1. Suite Pytest de Dominio (`tests/unit/`)
- **Comando ejecutado:** `pytest tests/unit --cov=odoo.addons.uta_transport_monitor`
- **Resultados:** 15 pruebas aprobadas en 0.88 s.
- **Cobertura de dominio:** 100 % en `domain/geo.py` (cálculo de distancias Haversine, bearing, velocidad y distancias de polilíneas GeoJSON).

### 6.2. Suite Nativa Odoo (`addons/uta_transport_monitor/tests/`)
- **Comando ejecutado:** `odoo -d georutex_test -u uta_transport_monitor --test-enable --stop-after-init --log-level=test`
- **Base de datos:** `georutex_test` aislada en PostgreSQL (`tmpfs`).
- **Resultados:** 25 métodos de prueba (35 tests agregados) ejecutados en 1.47 s, con 2636 queries ejecutadas, **0 fallos, 0 errores**.

| Módulo de Prueba | Casos Ejecutados | Aspecto Evaluado | Resultado |
|---|:---:|---|:---:|
| `test_smoke.py` | 1 | Instalación de addon y disponibilidad de Fleet | `APROBADO` |
| `test_route_and_version.py` | 6 | Unicidad de código, validación origen/destino, parámetros canónicos, mínimo 4 controles para aprobación, distancia de polilínea e inmutabilidad con viajes | `APROBADO` |
| `test_trip_scheduling.py` | 6 | Snapshot de parámetros, orden cronológico de horas, bloqueo de solapamiento en vehículos, viajes no solapados el mismo día, bloqueo de solapamiento en conductores y ciclo de vida de estados | `APROBADO` |
| `test_security_roles.py` | 4 | Privilegios completos de Manager, modo solo lectura de Analyst, aislamiento por registro para Conductor ("Mis Recorridos") y compatibilidad multi-rol (Driver + Analyst) | `APROBADO` |
| `test_gps_sync.py` | 8 | Idempotencia, actualización de última posición, velocidad en km/h, clasificación de simulación, etiquetado de vehículos no acreditados, filtrado de atributos `mock`, cálculo de estado y unicidad de identificador | `APROBADO` |

### 6.3. Análisis Estático de Código (Flake8)
- **Comando ejecutado:** `flake8 /mnt/extra-addons/uta_transport_monitor /workspace/tests`
- **Resultado:** 0 errores de estilo o longitud de línea.

---

## 7. Cumplimiento de Requisitos y Trazabilidad

| ID Requisito | Descripción Funcional / No Funcional | Estado en Fase 2 |
|---|---|:---:|
| **RF-07** | Registrar vehículos vinculados a Fleet | `CUBIERTO` |
| **RF-08** | Asociar dispositivo único a vehículo sin colisiones | `CUBIERTO` |
| **RF-09** | Crear múltiples rutas con origen, destino y sentido | `CUBIERTO` |
| **RF-10** | Administrar paradas y controles con secuencia obligatoria (≥ 4 por ruta) | `CUBIERTO` |
| **RF-11** | Definir horarios y tolerancias configurables desde Odoo | `CUBIERTO` |
| **RF-12** | Asignar recorridos fechados previniendo solapamientos simultáneos | `CUBIERTO` |
| **RF-13** | Ciclo de vida y estados operacionales del recorrido | `CUBIERTO` |
| **RF-14** | Versionar rutas y congelar snapshot de parámetros históricos | `CUBIERTO` |
| **RNF-04** | Integridad referencial e idempotencia de datos | `CUBIERTO` |
| **RNF-05** | Seguridad basada en roles (Manager, Conductor, Analista) y reglas de registro | `CUBIERTO` |
| **RNF-07** | Consistencia temporal en UTC con programación local | `CUBIERTO` |

---

## 8. Puertas de Validación Humana y Limitaciones Reales

Conforme al principio ético de `AGENTS.md` (no fabricar evidencia física externa):

1. **Validación GPS celular en red móvil (`EVI-01-04`):** Permanece en estado `PENDIENTE DE VALIDACIÓN EXTERNA`. No se marcará como superada hasta que un operador humano con Traccar Client en un teléfono físico con datos móviles (Wi-Fi apagada) transmita posiciones reales al túnel/receptor público configurado.
2. **Evaluación de Incidencias y Métricas Dinámicas:** Reservadas rigurosamente para las Fases 4 y 5. En esta Fase 2 se modelaron las estructuras operacionales necesarias sin adelantar cálculos artificiales.

---

## 9. Estado de Preparación para Fase 3

El sistema cuenta con la base de datos de producción `georutex` actualizada, los modelos operacionales en funcionamiento y las suites de pruebas limpias. El entorno se encuentra 100 % preparado para iniciar la **Fase 3: Sincronización, historial y mapas**, orientada a:
- Asociación automática de telemetrías a recorridos en su ventana temporal sin contaminación entre viajes.
- Visualización de mapa integrado de posiciones y polilínea en Odoo.
- Monitoreo de frescura de señal y alarmas de desconexión.

