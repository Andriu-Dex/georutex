# Informe Técnico: Revisión Funcional, Visual y de Consistencia Previa a la Fase 4

- **Fecha:** 2026-11-01
- **Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas
- **Módulo Odoo:** `uta_transport_monitor` (v16.0.3.1.0)
- **Ámbito:** Revisión y consolidación de consistencia temporal, geométrica, de estados, UI/UX y seguridad previa a la Fase 4

---

## 1. Resumen Ejecutivo

Conforme a las directivas de `instruction.md` y las reglas de `AGENTS.md`, se llevó a cabo una auditoría técnica profunda y la corrección integral de las inconsistencias observadas durante la demostración en navegador, sin alterar la arquitectura modular por capas ni introducir dependencias no autorizadas.

Se resolvieron con éxito:
1. **La aparente duplicidad horaria entre «Hora GPS (UTC)» y «Hora Local (Ecuador)»**, originada por la conversión automática que efectúa el cliente web de Odoo 16 sobre cualquier campo de tipo `fields.Datetime`.
2. **La discordancia temporal en `REC-2026-0001`**, donde posiciones GPS asociadas aparecían previas a la hora real de inicio (`actual_start_utc`), implementando reconciliación automática con el primer instante físico verificado.
3. **La distancia programada en 0,00 metros en recorridos**, garantizando la transferencia automática desde `route_version_id.estimated_distance_m` en `.create()` y `.action_schedule()`, así como el cálculo automático de distancias sobre polilíneas GeoJSON al aprobar versiones de ruta.
4. **La separación formal entre estado de conexión de hardware y frescura de telemetría**, eliminando la advertencia de registro de Odoo sobre campos calculados (`compute_sudo` inconsistente) y añadiendo el indicador visual de viaje con horario vencido (`is_schedule_overdue`) sin forzar cierres prematuros sin evidencia.
5. **Mejoras responsivas de UI/UX y mapas Leaflet**, adaptando dimensiones para escritorio y móviles, previniendo truncamiento en tarjetas de vehículos, incorporando tooltips a marcadores de paradas, asegurando la atribución de OpenStreetMap y priorizando vehículos monitoreados en el menú de GeoRutex.
6. **Aislamiento estricto de seguridad RBAC**, restringiendo a nivel de método ORM las consultas de telemetría y mapas en vivo para el rol Conductor (`group_transport_driver`).
7. **Localización al español**, consolidando el catálogo `i18n/es.po` para todas las entidades y vistas.
8. **Validación completa:** 46 pruebas nativas en `georutex_test` (0 fallos, 0 errores), 15 pruebas unitarias Pytest (100% cobertura en dominio geoespacial) y 0 errores en Flake8.

---

## 2. Diagnóstico y Soluciones por Área

### 2.1. Coherencia Temporal (UTC vs. Hora Local)

#### Causa Raíz Identificada
- En PostgreSQL, Odoo persiste los campos `fields.Datetime` como marcas de tiempo ingenuas (*naive*) en UTC puro (ej. `2026-11-01 13:05:00`).
- En el cliente web de Odoo 16 (JavaScript / Owl), cualquier campo declarado como `fields.Datetime` es interceptado por el componente `DateTimeField`, el cual aplica automáticamente el desfase de la zona horaria del usuario en sesión (`user.tz`, ej. `America/Guayaquil` UTC-5).
- En la versión previa, `fix_time` estaba etiquetado como `Hora GPS (UTC)`, pero en pantalla el navegador mostraba `08:05:00`. Simultáneamente, `fix_time_local` calculaba y mostraba `08:05:00 ECT`. Esto provocaba que ambas columnas exhibieran aparentemente la misma hora local (08:05), generando la percepción errónea de una falla de almacenamiento o conversión.

#### Correcciones Implementadas
- En `models/transport_position.py`:
  - Se añadió el campo computado `fix_time_utc = fields.Char(string="Hora GPS (UTC)", compute="_compute_fix_time_utc", store=False)`, el cual formatea explícitamente la cadena `YYYY-MM-DD HH:MM:SS UTC` sin admitir transformaciones por parte de Luxon/Moment en el navegador.
  - Se redefinió la etiqueta de `fix_time` como `Fecha/Hora GPS` con texto de ayuda que aclara su representación en la zona horaria del usuario.
  - Se preservó `fix_time_local` formateado como `YYYY-MM-DD HH:MM:SS ECT`.
- En `views/transport_position_views.xml` y `views/transport_trip_views.xml`:
  - Se sustituyó la columna visible por `fix_time_utc` junto a `fix_time_local`, dejando `fix_time` como campo secundario u opcional. Ahora el usuario observa inequívocamente:
    - **Hora GPS (UTC):** `2026-11-01 13:05:00 UTC`
    - **Hora Local (Ecuador):** `2026-11-01 08:05:00 ECT`

#### Discordancia en `REC-2026-0001`
- **Causa:** Al pulsar «Iniciar Recorrido», `action_start()` asignaba ciegamente `actual_start_utc = fields.Datetime.now()`. Si el botón era presionado a las 13:43 UTC mientras el bus ya venía transmitiendo telemetría desde las 13:05 UTC, se producía la incoherencia de tener puntos GPS anteriores a la hora de salida registrada.
- **Solución:**
  - Se refactorizó `action_start()` en `models/transport_trip.py` para consultar si existen posiciones GPS ya asociadas; de ser así, toma la menor de ellas (`earliest_pos.fix_time`).
  - Se incorporó el método `_reconcile_gps_times()` en `transport.trip`, invocado automáticamente en `services/gps_sync.py` al asociar nuevos lotes de puntos. Si existen fijaciones GPS anteriores a `actual_start_utc`, se sincroniza automáticamente con el primer instante verificado (RF-20).
  - Se ejecutó la reconciliación en la base de datos de desarrollo sobre `REC-2026-0001`, ajustando su inicio real de `13:43:56` a las `13:05:00 UTC`.

---

### 2.2. Distancias y Geometría

#### Causa Raíz de Distancia Programada en 0,00 m
- El valor `scheduled_distance_m` se transfería únicamente dentro del método `_onchange_route_version_id()`.
- En Odoo, los métodos decorados con `@api.onchange` solo se disparan ante interacción directa del usuario en formularios web; **no se ejecutan** durante llamadas programáticas `.create()`, scripts de carga ni inserciones desde demo data.
- Por tanto, cualquier viaje creado mediante código o fixtures mantenía el valor por defecto `0.00`.

#### Correcciones Implementadas
- En `models/transport_trip.py`:
  - Se sobreescribió `@api.model_create_multi def create(...)` para que, en caso de no especificarse `scheduled_distance_m`, copie automáticamente `route_version_id.estimated_distance_m`.
  - En `action_schedule()`, se añadió verificación de respaldo: si `scheduled_distance_m` está en cero o nulo, se actualiza a partir de la versión aprobada.
- En `models/transport_route_version.py`:
  - En `action_approve()`, se automatizó el cálculo de `estimated_distance_m` mediante `calculate_polyline_distance` si la versión posee polilínea GeoJSON y aún no se había calculado.
- Se actualizó el recorrido `REC-2026-0001` en `georutex`, quedando fijado en `4200.00 m` (4,20 km).
- Se garantizó en `get_map_data()` y en las consultas ORM la ordenación cronológica estricta `fix_time ASC, id ASC`.

---

### 2.3. Estados GPS y Recorridos Operacionales

#### Unificación y Diferenciación de Estados
Se clarificaron y desacoplaron conceptualmente dos dimensiones que previamente generaban solapamiento:
1. **Estado de Conexión de Hardware (`gps_connection_status`):**
   - Refleja el enlace físico/lógico del equipo con Traccar Server (`online` < 5 min, `recent` < 1 h, `offline` > 1 h, `unlinked` sin hardware configurado).
2. **Frescura de Señal de Telemetría (`gps_freshness_state`):**
   - Evalúa el flujo de datos contra los umbrales de negocio (RF-06, umbral gap 180s):
     - `fresh`: Fix recibido hace <= 180 s (en vivo).
     - `stale`: Fix recibido entre 180 s y 900 s (sin reporte reciente).
     - `offline`: Sin reporte por > 900 s (15 min).
     - `no_data`: Equipo vinculado sin coordenadas registradas.
     - `unlinked`: Vehículo sin vinculación a Traccar.

#### Eliminación de Advertencia de Registro
- `gps_connection_status` se declaró con `store=False`, unificándolo con `gps_freshness_state` y `last_gps_age_seconds` bajo el decorador `@api.depends("last_gps_fix_time", "traccar_device_id", "traccar_unique_id")`.
- Esto eliminó por completo el error de Odoo: `fleet.vehicle: inconsistent 'compute_sudo' for computed fields` y garantiza que el estado sea siempre un cálculo en tiempo real respecto al instante actual.

#### Tratamiento de Recorridos «En Curso» con Horario Vencido
- Se introdujo el campo computado `is_schedule_overdue = fields.Boolean("Horario Programado Vencido")` en `transport.trip`.
- Cuando `state == 'in_progress'` y `scheduled_end_utc < now`, se despliega un banner de advertencia operacional en la vista formulario:
  > *"Atención Operacional: El horario programado para este recorrido ha concluido pero el viaje continúa En Curso a la espera de confirmación de llegada a destino o telemetría GPS suficiente."*
- Se preserva el principio fundamental de **no cerrar arbitrariamente recorridos** sin evidencia de llegada a destino o intervención explícita del despachador.

---

### 2.4. Mejoras de Interfaz (UI/UX) y Mapas Leaflet

1. **Diseño Responsivo:**
   - En `static/src/css/transport_map.css`, se incorporaron consultas `@media (max-width: 768px)`:
     - El contenedor de mapa individual y de recorrido ajusta su altura automáticamente a `380px` en pantallas móviles y `520px` en escritorio.
     - La vista general de flota en vivo (`LiveFleetMapAction`) conmuta de disposición horizontal a vertical en móviles (`flex-direction: column`), limitando la barra lateral a `280px` de altura y permitiendo interacción completa con el mapa sin desbordamiento.
2. **Corrección de Truncamiento:**
   - Se ajustó `.o_georutex_vehicle_card_title` con `min-width: 0`, `gap: 8px` y selector `span.name` con `text-overflow: ellipsis`, permitiendo que nombres largos de unidades convivan armoniosamente con las insignias de estado.
3. **Numeración y Tooltips en Paradas:**
   - Se eliminaron bordes y fondos residuales en `.custom-div-icon`.
   - Se configuraron marcadores de paradas Leaflet con `.bindTooltip("Parada {seq}: {nombre}", { direction: "top", offset: [0, -14] })`, mostrando el nombre del control al pasar el cursor sin necesidad de hacer clic.
4. **Priorización de Flota Monitoreada:**
   - Se creó la acción de ventana `action_transport_monitored_fleet` con contexto predeterminado `search_default_filter_gps_monitored: 1`.
   - En el menú de GeoRutex «Vehículos Monitoreados», se muestran prioritariamente los buses con rastreo activo, sin alterar ni sobreescribir la acción original del módulo `fleet`.
5. **Atribución de OpenStreetMap:**
   - Se revisó y estilizó el control de atribución `.leaflet-control-attribution` asegurando texto legible, fondo semitransparente discreto y cumplimiento de los términos de licencia de OSM.
6. **Localización al Español:**
   - Se generó el archivo de traducciones `i18n/es.po` cubriendo todas las entidades, menús, estados y acciones del addon.

---

### 2.5. Seguridad, Permisos y Aislamiento de Datos

1. **Seguridad RBAC en Endpoints de Mapa:**
   - En `fleet.vehicle.get_live_fleet_positions()`: Si el usuario autenticado pertenece únicamente al grupo Conductor (`group_transport_driver`), la consulta se restringe estrictamente a los vehículos asignados a su persona (`driver_id` o viajes activos).
   - En `fleet.vehicle.get_vehicle_live_map_data()`: Se verifica que el conductor sea el titular asignado; de lo contrario, se eleva `AccessError` bloqueando la extracción de coordenadas no autorizadas.
2. **Aislamiento de Datos Demostrativos vs. GPS Físico:**
   - Los vehículos demostrativos (`TBA-1001`, `TBA-1002`) conservan `is_simulated = True` y `is_physical_accredited = False`.
   - La prueba física de datos móviles con celular (`EVI-01-04`) se mantiene en estado `PENDIENTE DE VALIDACIÓN EXTERNA` sin suplantación de resultados.

---

## 3. Pruebas y Verificación

### 3.1. Diferencia entre Casos de Prueba Documentados y Métodos de Prueba Ejecutados

En respuesta a la directiva de la inspección:
- **Casos de prueba documentados en especificación (Sección 11 de `requirements.md`):** Se definen **20 casos de prueba funcionales/límite** de alto nivel (`CP-01` a `CP-20`).
- **Métodos ejecutables implementados:** Se cuenta con un total de **61 métodos de prueba ejecutables**:
  - **46 métodos en la suite nativa de Odoo (`TransactionCase`):** Evalúan modelos ORM, restricciones SQL, reglas por registro, transiciones de estado, idempotencia y seguridad RBAC en la base aislada `georutex_test`.
  - **15 métodos en la suite Pytest de Dominio (`tests/unit/`):** Evalúan algoritmos puros en memoria (Haversine, rumbos, velocidades, polilíneas GeoJSON y cliente REST con mocks).
- **Razón técnica de la diferencia:** Cada caso de prueba de especificación (`CP-xx`) agrupa múltiples escenarios atómicos (ej. caso positivo, caso con solapamiento, caso con tipología incorrecta, borde temporal y revocación de permisos).

### 3.2. Resultados de Ejecución

| Suite / Herramienta | Entorno | Comando | Resultado |
|---|---|---|---|
| **Linter PEP 8 / Flake8** | Contenedor de pruebas | `docker compose --profile test run --rm odoo-test flake8 /mnt/extra-addons/uta_transport_monitor /workspace/tests` | **0 errores, 0 advertencias** (100% limpio) |
| **Pytest Dominio (`tests/unit/`)** | Contenedor de pruebas | `docker compose --profile test run --rm odoo-test` | **15 PASADAS** en 1.64 s (100% cobertura en `domain/geo.py`, 86% global) |
| **Suite Nativa Odoo 16** | Base aislada `georutex_test` | `docker exec -i georutex-odoo odoo -d georutex_test -u uta_transport_monitor --test-enable --stop-after-init` | **46 PASADAS** (66 pruebas estadísticas en 2.66 s, 0 fallos, 0 errores) |
| **Base de Desarrollo (`georutex`)** | Contenedor `georutex-odoo` | Actualización de módulo `-u uta_transport_monitor` | **EXITOSO** (Tablas, vistas y secuencias migradas limpiamente) |
| **Servicio HTTP Odoo** | Puerto local 8069 | `http://localhost:8069` | **HTTP 200 OK** |

---

## 4. Estado de Preparación para la Fase 4

El sistema GeoRutex queda formalmente estabilizado, con consistencia temporal y geométrica verificada, mapas interactivos completamente responsivos, reglas de seguridad reforzadas y una suite integral de 61 pruebas automatizadas aprobadas.

Se cuenta con las condiciones óptimas para iniciar la **Fase 4: Motor de evaluación, detección de incidentes y penalizaciones** cuando el usuario lo disponga.

