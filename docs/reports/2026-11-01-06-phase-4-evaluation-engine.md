# Informe de Ejecución Técnica — Fase 4: Motor de Evaluación de Recorridos, Detección de Desvíos e Incidencias Operacionales

**Fecha de Ejecución:** 01 de Noviembre de 2026  
**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Módulo Odoo:** `uta_transport_monitor` (v16.0.4.0.0)  
**Estado:** `COMPLETADO Y VERIFICADO`  

---

## 1. Resumen Ejecutivo

Conforme a las instrucciones detalladas en `instruction.md`, las especificaciones funcionales y no funcionales de `docs/requirements.md` (RF-20 a RF-30, RNF-05, RNF-07, RNF-13) y los lineamientos arquitectónicos de `docs/architecture.md` y `AGENTS.md`, se ha diseñado, implementado y verificado en su totalidad la **Fase 4: Motor de evaluación, detección automatizada de incumplimientos y gestión de incidencias**.

El sistema ahora cuenta con:
1. Un **motor de evaluación de dominio puro y determinista** (`domain/evaluation.py`), completamente desacoplado del ORM de Odoo, de conexiones de red y de bases de datos, garantizando reproducibilidad matemática de auditoría.
2. Un **mecanismo de inferencia temporal rigurosa** (RF-20) que separa de forma inequívoca el clic manual del usuario (`manual_start_utc`), la primera telemetría GPS recibida (`first_gps_fix_utc`) y la salida verificada de la geocerca de origen (`actual_start_utc`), así como la llegada a destino (`actual_end_utc`).
3. Detección automática y filtrado de ruido para **desvíos de ruta** (RF-24) mediante cálculo ortogonal punto a segmento contra la polilínea GeoJSON, exigiendo persistencia temporal y espacial mínima.
4. Identificación de **brechas de telemetría GPS** (RF-25) mayores a 180 segundos, clasificando paradas no registradas durante un apagón como `indeterminate` en lugar de imputar falsamente una omisión intencional (`missed`).
5. Generación **idempotente de incidencias operacionales** (RF-27, RF-28, RF-30) con flujo de justificación formal y **bloqueo estricto por ORM contra la auto-aprobación del conductor** (RNF-05, RNF-13).
6. Separación explícita de **conformidad bruta (*gross*) vs. conformidad ajustada (*netto*)** (RF-26, RF-29), registrando auditorías inmutables con congelamiento de parámetros (`transport.trip.evaluation`).

---

## 2. Arquitectura y Componentes Desarrollados

Siguiendo el diseño modular por capas establecido en `docs/architecture.md`:

```
┌────────────────────────────────────────────────────────┐
│                   Vistas e Interfaces                  │
│   (transport_incident_views.xml, evaluation_views.xml) │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│              Servicios de Orquestación                 │
│         (transport.trip.evaluation.service)            │
│   - Resuelve entidades ORM y snapshots de parámetros   │
│   - Invoca funciones de dominio puro                   │
│   - Sincroniza incidencias de forma idempotente        │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
┌──────────────▼───────────┐  ┌───────────▼──────────────┐
│       Dominio Puro       │  │        Modelos ORM       │
│  (domain/evaluation.py)  │  │  (transport.incident,    │
│     (domain/geo.py)      │  │ transport.trip.evaluation│
│  - Sin dependencias Odoo │  │     transport.trip)      │
│  - Pruebas en Pytest     │  │  - ACLs y Record Rules   │
└──────────────────────────┘  └──────────────────────────┘
```

### 2.1. Capa de Dominio Puro (`addons/uta_transport_monitor/domain/`)

- **`domain/geo.py`:**
  - `point_to_segment_distance(p_lat, p_lon, a_lat, a_lon, b_lat, b_lon)`: Proyección ortogonal local equirrectangular sobre el punto medio del segmento para distancias cortas de alta precisión y mínimo costo computacional.
  - `distance_to_polyline(point_lat, point_lon, coordinates, is_geojson=True)`: Determina la distancia mínima en metros desde un punto dado a una polilínea compuesta por $N$ vértices GeoJSON `[lon, lat]`.
- **`domain/evaluation.py`:**
  - `evaluate_trip_actual_times()` (RF-20): Determina el instante exacto en el que el bus sale del radio de la parada de origen (`origin_geofence_departure`) y el primer instante en que ingresa al radio de destino (`destination_geofence_arrival`).
  - `evaluate_stop_visits()` (RF-22, RF-23): Evalúa cada parada programada según su secuencia cronológica. Clasifica en `on_time` (retraso $\le$ tolerancia), `late` (retraso $>$ tolerancia), `missed` (geocerca no ingresada con cobertura GPS normal) o `indeterminate` (falta de cobertura GPS o brecha $> 180s$ sobre la ventana programada).
  - `detect_route_deviations()` (RF-24): Identifica clusters continuos de puntos GPS fuera del corredor de tolerancia ($\gt 40m$), exigiendo al menos $K=2$ puntos consecutivos y una duración temporal mínima ($\ge 10s$) para filtrar rebotes y ruidos GPS efímeros.
  - `detect_gps_gaps()` (RF-25): Identifica intervalos de tiempo entre lecturas consecutivas superiores al umbral canónico de 180 segundos.
  - `evaluate_trip_compliance()` (RF-26): Sintetiza las dimensiones de puntualidad, completitud de paradas obligatorias, desvíos y brechas de telemetría en un veredicto estructurado de conformidad bruta (*gross compliance*), determinando el estado de integridad (`completed`, `incomplete`, `insufficient_data`).

### 2.2. Capa de Persistencia y Modelos ORM (`addons/uta_transport_monitor/models/`)

- **`models/transport_incident.py` (`transport.incident`):**
  - Entidad para el registro de no conformidades. Secuencia formal `INC-YYYY-XXXXX`.
  - Origen tipificado: `automatic` (generado por motor de reglas) vs `manual` (reportado por operador o conductor).
  - Tipos canónicos: `delay_start`, `delay_arrival`, `stop_omitted`, `route_deviation`, `gps_loss`, `traffic`, `mechanical_failure`, `accident`, `weather`, `other`.
  - Flujo de vida: `draft` -> `reported` -> `justified` / `rejected` -> `resolved`.
  - **Seguridad y Control RNF-05/RNF-13:** El método `action_approve_justification()` valida explícitamente en el ORM que el usuario actual no pertenezca exclusivamente al rol de conductor asignado, impidiendo cualquier auto-aprobación y levantando `AccessError` si se intenta eludir la UI.
- **`models/transport_evaluation.py` (`transport.trip.evaluation`):**
  - Registro de auditoría inmutable por cada corrida de evaluación. Secuencia `EVAL-YYYY-XXXXX`.
  - Almacena el `parameter_snapshot_json` congelado al momento del viaje.
  - Registra tanto `is_compliant_gross` (resultado sin justificar) como `is_compliant_adjusted` (resultado ajustado tras justificaciones aprobadas por la gerencia).
- **`models/transport_trip.py` (extensiones):**
  - Campos técnicos para trazabilidad: `manual_start_utc`, `manual_end_utc`, `first_gps_fix_utc`, `actual_start_utc`, `actual_end_utc`, `actual_start_evidence`, `actual_end_evidence`.
  - Métricas computadas y almacenadas: `evaluation_ids`, `evaluation_count`, `last_evaluation_id`, `evaluation_status` (`unevaluated`, `compliant`, `non_compliant`, `indeterminate`).
  - Acción directa `action_evaluate_trip()` para disparar la evaluación desde la interfaz de usuario.
- **`models/transport_stop_visit.py`:**
  - Incorporación del estado `indeterminate` en la selección de estado de visita.

### 2.3. Capa de Servicios y Orquestación (`addons/uta_transport_monitor/services/`)

- **`services/trip_evaluation_service.py` (`transport.trip.evaluation.service`):**
  - Extrae las posiciones asociadas, paradas y polilínea de referencia.
  - Ejecuta las rutinas puras de `domain/evaluation.py`.
  - Actualiza el registro del viaje (`transport.trip`) y las visitas (`transport.stop.visit`).
  - Sincroniza incidencias automáticas de forma **estrictamente idempotente** (`_sync_automatic_incidents`), evitando duplicar incidencias si el viaje es re-evaluado múltiples veces.
  - Evalúa la cobertura de incidencias justificadas y aprobadas para actualizar la conformidad ajustada (`is_compliant_adjusted`).
  - Persiste el registro de evaluación histórico `transport.trip.evaluation`.

---

## 3. Seguridad, Permisos y Reglas de Registro

En concordancia con `security/groups.xml`, `security/ir.model.access.csv` y `security/rules.xml`:

1. **Permisos de Modelo (ACLs):**
   - Conductores (`group_driver`): Permiso de lectura y creación de incidencias (`transport.incident`). Lectura de evaluaciones (`transport.trip.evaluation`).
   - Analistas (`group_analyst`) y Gestores (`group_manager`): Acceso completo de lectura, edición y aprobación sobre incidencias y evaluaciones.
2. **Reglas por Registro (Record Rules):**
   - `rule_transport_incident_driver`: Un conductor únicamente puede consultar las incidencias pertenecientes a sus propios recorridos o creadas por su usuario.
   - `rule_transport_evaluation_driver`: Un conductor únicamente puede consultar las evaluaciones de sus propios viajes asignados.
   - Analistas y administradores disponen de visibilidad global sin restricción de conductor.
3. **Validación en Capa de Negocio:**
   - La restricción de auto-aprobación está codificada a nivel de ORM en `action_approve_justification`, no dependiendo de la simple ocultación de botones en el frontend QWeb.

---

## 4. Pruebas y Verificación de Calidad

### 4.1. Análisis Estático (Flake8)
- **Comando:**
  ```bash
  docker compose --profile test run --rm odoo-test flake8 /mnt/extra-addons/uta_transport_monitor
  ```
- **Resultado:** **0 errores, 0 advertencias**. Cumplimiento riguroso de PEP 8 (< 79 caracteres por línea, sin imports no utilizados).

### 4.2. Pruebas Unitarias de Dominio (Pytest)
- **Comando:**
  ```bash
  docker compose --profile test run --rm --workdir /workspace odoo-test pytest tests/unit -v --cov=/mnt/extra-addons/uta_transport_monitor/domain
  ```
- **Resultado:** **22 pruebas aprobadas en 2.25 segundos (100%)**.
- **Cobertura de Código de Dominio:**
  - `domain/__init__.py`: 100%
  - `domain/geo.py`: 94%
  - `domain/evaluation.py`: 76%
  - **Total Dominio:** **81% de cobertura de código**.

### 4.3. Pruebas Nativas Odoo 16 (TransactionCase)
- **Comando:**
  ```bash
  docker compose --profile test run --rm odoo-test odoo -c /etc/odoo/odoo.conf -d georutex_test -u uta_transport_monitor --test-enable --stop-after-init --log-level=test
  ```
- **Resultado:** **53 pruebas ejecutadas, 0 fallos, 0 errores**.
- **Cobertura Específica del Motor de Evaluación (`TestEvaluationEngine`):**
  1. `test_01_punctual_trip_fully_compliant`: Recorrido puntual sin desvíos obtiene veredicto *Gross Compliant* y *Adjusted Compliant*, estado *completed* y verificación de estampas temporales (RF-20).
  2. `test_02_late_departure_generates_automatic_incident`: Salida tardía superior a la tolerancia genera automáticamente una incidencia de tipo `delay_start` y veredicto de no conformidad.
  3. `test_03_corridor_deviation_detection_and_noise_filtering`: Desvío fuera del corredor de 40m genera incidencia `route_deviation`; puntos anómalos aislados son filtrados sin falsos positivos.
  4. `test_04_idempotent_evaluation_prevents_duplicate_incidents`: Múltiples evaluaciones sucesivas sobre el mismo viaje no duplican incidencias automáticas.
  5. `test_05_driver_cannot_self_approve_justification`: El intento de un conductor de aprobar la justificación de su propia incidencia es bloqueado por el ORM con `AccessError`.
  6. `test_06_approved_justification_adjusts_compliance`: Tras la aprobación formal de la justificación por un gerente/analista, la evaluación recalculada marca `is_compliant_adjusted = True` preservando `is_compliant_gross = False`.
  7. `test_07_insufficient_gps_data_classified_as_indeterminate`: Un recorrido con telemetría nula o paradas no verificables se clasifica como `insufficient_data` / `indeterminate`, sin fabricar falsos cumplimientos o incumplimientos.

---

## 5. Detección y Resolución de Incidencias Durante la Integración

Durante la ejecución de las pruebas nativas de Odoo se detectaron y corrigieron dos anomalías técnicas:

1. **Inversión de Coordenadas GeoJSON en Extracción de Polilínea:**
   - *Causa:* En `_get_polyline_coordinates`, las coordenadas GeoJSON `[lon, lat]` fueron invertidas a `[lat, lon]`, pero `distance_to_polyline` esperaba coordenadas GeoJSON con `is_geojson=True`. Esto provocaba que las coordenadas fueran leídas al revés (calculando distancias con latitudes en el hemisferio polar), detectando falsos desvíos en todos los puntos.
   - *Corrección:* Se corrigió `_get_polyline_coordinates` para mantener estrictamente el formato GeoJSON `[float(pt[0]), float(pt[1])]`, resolviendo inmediatamente la distorsión y validando la detección precisa de desvíos.
2. **Advertencia de Consistencia `compute_sudo` en Campos Computados:**
   - *Causa:* En `transport.trip`, los campos `last_evaluation_id` y `evaluation_status` tenían `store=True`, mientras que `evaluation_count` compartía el método `@api.depends` sin almacenamiento persistente.
   - *Corrección:* Se homogeneizó `store=True` en `evaluation_count`, eliminando la advertencia del registro de Odoo.

---

## 6. Estado de la Base de Datos de Desarrollo

El módulo `uta_transport_monitor` fue actualizado con éxito en la base de datos de desarrollo (`georutex`):
```bash
docker compose exec odoo /entrypoint.sh odoo -d georutex -u uta_transport_monitor --stop-after-init
docker compose restart odoo
```
El contenedor Odoo reinició sin errores en `http://localhost:8069`. Los nuevos menús **Operaciones > Incidencias Operacionales** y **Auditoría > Evaluaciones de Recorridos** están completamente operativos.

---

## 7. Próximos Pasos (Fase 5)

Con el motor de evaluación, la persistencia inmutable de auditorías y el ciclo de justificación formal de incidencias operativos, el sistema se encuentra completamente listo para abordar la **Fase 5: Dashboard gerencial, analítica de transporte y cálculo de KPIs (MT-01 a MT-08, MCS-01 a MCS-04)**.

