# Informe de Ejecución Técnica — Fase 3: Sincronización, Historial y Visualización Cartográfica

**Fecha de Ejecución:** 01 de Noviembre de 2026  
**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Módulo Odoo:** `uta_transport_monitor` (v16.0.3.0.0)  
**Estado:** `COMPLETADO Y VERIFICADO`  

---

## 1. Resumen Ejecutivo

Conforme a las instrucciones de `instruction.md` y las especificaciones de `docs/requirements.md` (Secciones 5, 6, 7 y 13) y `docs/architecture.md`, se ha completado e integrado en su totalidad la **Fase 3: Sincronización, historial y visualización de recorridos GPS**.

El sistema ahora cuenta con un pipeline determinista de asociación de posiciones GPS a recorridos operacionales basado en ventanas temporales estrictas, un mecanismo de sincronización histórica de rangos con reintentos exponenciales e idempotencia absoluta contra Traccar Server, un motor de evaluación de frescura de señal GPS (en vivo, sin reporte reciente, sin señal, sin datos, no vinculado), e interfaces cartográficas interactivas nativas en Odoo 16 impulsadas por **Leaflet 1.9.4** y OpenStreetMap (sin dependencias de SaaS comerciales ni iframes).

---

## 2. Ajustes y Fortalecimiento Previo Implementados (Sección 2 de `instruction.md`)

Antes de introducir las capacidades cartográficas y de asociación de la Fase 3, se realizaron los siguientes saneamientos técnicos sobre la base existente:

1. **Saneamiento de Datos Demostrativos:** Se eliminó la acreditación física prematura del vehículo de demostración (`BUS-01`), marcándolo expresamente como `is_physical_accredited = False` e `is_simulated = True`. Ningún dato sintético o de prueba se clasifica como real.
2. **Desacoplamiento de IDs Numéricos Traccar en Fixtures:** Se removieron los identificadores numéricos fijos (`101`, `102`) del XML demo, preservando la resolución dinámica mediante `uniqueId` a través de la API REST de Traccar.
3. **Entropía Criptográfica de 128 Bits:** Se actualizó el generador de identificadores únicos en `fleet.vehicle` (`action_generate_secure_unique_id`) para utilizar 16 bytes de entropía (`secrets.token_hex(16).upper()`), produciendo tokens de 32 caracteres hexadecimales (`UTA-BUS-` + 32 hex = 40 caracteres) imposibles de predecir.
4. **Inmutabilidad Reforzada en Versiones Aprobadas:** Se implementó `unlink()` en `transport.route.version` bloqueando la eliminación de versiones aprobadas o con viajes asociados (RF-14).
5. **Detección de Conflictos de Asignación por Dispositivo:** Se añadió en `transport.trip` la restricción de que dos vehículos distintos que compartan temporalmente un mismo `traccar_device_id` no pueden tener recorridos activos simultáneos (CP-27, RF-08, RF-12). Los recorridos consecutivos adyacentes (`A.end == B.start`) se permiten sin falsos bloqueos.

---

## 3. Arquitectura y Componentes Desarrollados

### 3.1. Capa de Modelos y Persistencia (`models/`)

- **`models/transport_position.py` (`transport.vehicle.position`):**
  - Incorporación del estado de asociación: `association_status` (`unassigned`, `associated`, `ambiguous`).
  - Clasificación de origen ampliada: `source` (`real`, `simulated`, `unverified`).
  - Métricas de calidad y telemetría: `accuracy` (precisión horizontal en metros), `heading` (rumbo en grados), `altitude` (altitud en metros).
  - Cálculo de hora local: `fix_time_local` computado en tiempo real en la zona horaria `America/Guayaquil` (UTC-5) para interfaces y popups.
- **`models/fleet_vehicle.py` (`fleet.vehicle`):**
  - Máquina de estados de frescura GPS: `gps_freshness_state` (`fresh` < 3 min, `stale` 3-15 min, `offline` > 15 min, `no_data`, `unlinked`).
  - Campos de diagnóstico: `last_gps_age_seconds` y `last_gps_time_local`.
  - Métodos ORM seguros: `get_live_fleet_positions()` para el monitoreo global y `get_vehicle_live_map_data()` para la ficha individual del bus.
- **`models/transport_trip.py` (`transport.trip`):**
  - Método ORM `get_map_data()`: Genera el payload estructurado para Leaflet conteniendo la polilínea GeoJSON planificada de la ruta, las paradas con radio y secuencia, y el rastro cronológico de telemetrías GPS con hora local y velocidad.
  - Acción de sincronización bajo demanda: `action_sync_trip_gps()`.

### 3.2. Capa de Servicios y Orquestación (`services/`)

- **`services/trip_service.py` (`transport.trip.service`):**
  - `find_matching_trip_for_position()`: Identifica si un punto GPS pertenece a un viaje programado, en curso o finalizado para el vehículo correspondiente.
  - `associate_positions_to_trips()`: Asigna masivamente posiciones sin asociar garantizando trazabilidad: asigna cuando el viaje es único e inequívoco, y etiqueta como `ambiguous` si se detecta concurrencia anómala.
  - `sync_trip_gps_telemetry()`: Recupera el rango histórico de Traccar correspondiente a la ventana `[scheduled_start_utc, scheduled_end_utc]` del viaje e invoca la asociación automática.
- **`services/gps_sync.py` (`transport.gps.sync.service`):**
  - Soporte de sincronización por rangos ISO 8601 (`from_time`, `to_time`).
  - Bloqueo por fila `SELECT id FROM fleet_vehicle WHERE id = %s FOR UPDATE NOWAIT` para serializar sincronizaciones concurrentes (CP-23).
  - Deduplicación estricta por `traccar_position_id` y tupla `(traccar_device_id, fix_time)`.
  - Conversión de velocidad de nudos a km/h (`speed * 1.852`).
  - Clasificación estricta: `real` únicamente si el vehículo tiene acreditación física confirmada y ni el hardware ni el protocolo reportan simulación.

### 3.3. Capa de Integración Externa (`integrations/`)

- **`integrations/traccar_client.py` (`TraccarClient`):**
  - Cliente HTTP nativo desacoplado de ORM.
  - Mecanismo de resiliencia (RNF-09): 3 reintentos con backoff exponencial (`0.3 * 2^attempt`) ante caídas de red o errores HTTP 5xx.
  - Timeout estricto de 5 segundos por solicitud.
  - Formateo de fechas ISO 8601 con sufijo 'Z' para la API de Traccar.

### 3.4. Capa de Visualización Cartográfica e Interfaces (`static/` y `views/`)

- **Biblioteca Cartográfica Vendorizada:**
  - `static/lib/leaflet/`: Leaflet 1.9.4 (`leaflet.js`, `leaflet.css`, imágenes y archivo de licencia BSD-2). Excluido de SonarQube conforme a `sonar-project.properties`.
- **Componentes Owl 2 en JavaScript:**
  - `TripMapWidget` (`static/src/js/trip_map_widget.js`): Widget integrado en el formulario del recorrido (`transport.trip`) que dibuja la ruta planificada en azul (`#1976D2`), las paradas obligatorias numeradas con sus geocercas circulares de 30 metros, y la traza GPS registrada en púrpura (`#7B1FA2`) con marcador animado en la última posición conocida.
  - `VehicleMapWidget`: Widget integrado en la pestaña "Ubicación en Vivo" del vehículo en Fleet mostrando su posición actual y el rastro reciente de telemetrías.
  - `LiveFleetMapAction` (`static/src/js/live_fleet_map_action.js`): Vista de cliente a pantalla completa (`uta_transport_live_fleet_map`) con panel lateral de filtrado (Todos, En Vivo, Sin Reporte), auto-refresco cada 30 segundos y centrado animado en el vehículo seleccionado.
- **Estilos y Plantillas QWeb:**
  - `static/src/css/transport_map.css`: Diseño moderno y accesible, marcadores con pulso animado para buses en vivo, insignias de estado de alta legibilidad.
  - `static/src/xml/trip_map_widget.xml` y `static/src/xml/live_fleet_map_templates.xml`: Plantillas Owl estructuradas.
- **Vistas XML y Menús Actualizados:**
  - `transport_trip_views.xml`: Pestaña "Mapa del Recorrido" y pestaña "Telemetrías GPS Asociadas".
  - `fleet_vehicle_views.xml`: Pestaña "Ubicación en Vivo", insignias de frescura y hora local.
  - `menu_views.xml`: Nuevo elemento de menú `GeoRutex` -> `Operaciones` -> `Mapa en Vivo`.

---

## 4. Control de Acceso y Seguridad de Telemetría (Sección 7 de `AGENTS.md`)

- **Regla por Registro de Posiciones (`rule_transport_position_driver`):**
  Se fortaleció la regla de lectura para conductores asegurando que, cuando un punto GPS está asociado a un viaje, **únicamente el conductor asignado a dicho viaje puede consultar la posición**. Si el punto está sin asignar, solo el conductor asignado al vehículo puede verlo.
- **Protección de Métodos ORM:** El método `get_map_data()` respeta el modelo de seguridad de Odoo; si un conductor intenta invocarlo sobre un viaje que no le pertenece, el ORM genera un error `AccessError` (probado en `test_security_positions.py`).

---

## 5. Resultados de Pruebas Automatizadas

### 5.1. Análisis Estático de Código (Flake8)
- **Comando:** `docker compose --profile test run --rm -w /workspace odoo-test flake8 /mnt/extra-addons/uta_transport_monitor /workspace/tests`
- **Resultado:** **0 errores, 0 advertencias**. Cumplimiento estricto de PEP 8 (< 79 caracteres por línea).

### 5.2. Suite Unitaria Pytest (Dominio y Cliente)
- **Comando:** `docker compose --profile test run --rm -w /workspace odoo-test pytest tests/unit --cov=odoo.addons.uta_transport_monitor`
- **Resultado:** **15 pruebas unitarias aprobadas en 4.48s** (100% de cobertura en funciones de dominio geoespacial `domain/geo.py`).

### 5.3. Suite Nativa Odoo 16 (`georutex_test`)
- **Comando:** `docker compose --profile test run --rm -w /workspace odoo-test odoo -d georutex_test -u uta_transport_monitor --test-enable --stop-after-init --log-level=test`
- **Resultado:** **38 métodos de prueba ejecutados, 0 fallidos, 0 errores en 2.24s** (56 estadísticas de prueba en total).

| Módulo de Prueba | Métodos | Casos Verificados |
|---|---|---|
| `test_smoke.py` | 1 | Carga de módulos, herencia de Fleet, arranque Odoo |
| `test_route_and_version.py` | 6 | Rutas, inmutabilidad, cálculo de polilíneas, 4 controles |
| `test_trip_scheduling.py` | 6 | Estados, snapshot de parámetros, prevención solapamientos |
| `test_security_roles.py` | 4 | Grupos Manager, Analyst, Driver y permisos multi-rol |
| `test_gps_sync.py` | 6 | Concurrencia, deduplicación, atributos mock, unicidad de IDs |
| `test_gps_association.py` | 4 | Asociación en ventana, puntos fuera de rango, viajes consecutivos, payload Leaflet |
| `test_gps_history_sync.py` | 2 | Idempotencia de sincronización por rango (CP-05), tolerancia a caídas de Traccar (CP-14) |
| `test_telemetry_freshness.py` | 4 | Transiciones de frescura (CP-24), entropía 128-bit, hora local Ecuador (CP-06), aislamiento 'real' vs 'simulated' |
| `test_security_positions.py` | 3 | Aislamiento estricto de posiciones por conductor (CP-12), bloqueo ORM de mapas ajenos |

---

## 6. Estado de la Base de Datos y Servicios

1. **Base de Datos de Pruebas (`georutex_test`):** Probada y verificada de manera aislada con 38 pruebas nativas exitosas.
2. **Base de Datos de Desarrollo (`georutex`):** Actualizada limpiamente a la versión `16.0.3.0.0` con todas las tablas, vistas y secuencias sincronizadas.
3. **Servicio Odoo (`georutex-odoo`):** Reiniciado y respondiendo con HTTP 200 en `http://localhost:8069`.

---

## 7. Catálogo de Evidencias (Índice Saneado)

Se registraron en `evidence/INDEX.md` los siguientes identificadores correspondientes a la Fase 3:

- `EVI-03-01`: Asociación Posición-Recorrido (`test_gps_association.py`).
- `EVI-03-02`: Sincronización Histórica e Idempotencia (`test_gps_history_sync.py`).
- `EVI-03-03`: Frescura de Señal y Entropía 128-bit (`test_telemetry_freshness.py`).
- `EVI-03-04`: Seguridad de Telemetría y Mapas (`test_security_positions.py`).
- `EVI-01-04`: Validación celular GPS física se mantiene como `PENDIENTE DE VALIDACIÓN EXTERNA` hasta contar con la prueba móvil en campo con Wi-Fi apagada.

---

## 8. Conclusión y Preparación para la Fase 4

La Fase 3 queda completamente implementada, verificada y libre de regresiones. El sistema cuenta con la base de telemetrías e infraestructura cartográfica requerida para abordar la **Fase 4: Motor de evaluación, detección de incidentes y penalizaciones** cuando se indique.

