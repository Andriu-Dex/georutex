# Informe Técnico: Programación Automática de Horarios y Consistencia de Duración

**Fecha:** 2026-11-04  
**Referencia:** `EVI-07-04` / `instruction.md`  
**Módulos Afectados:** `uta_transport_monitor` (`transport.trip`, `transport.route.version`, `transport.stop.visit`)  
**Requisitos Vinculados:** RF-11, RF-12, RF-14, RF-20, RNF-05, RNF-07  

---

## 1. Contexto y Problema Detectado

En la versión original del módulo, al programar un recorrido en `transport.trip`, el operador ingresaba manualmente tanto la fecha/hora de inicio (`scheduled_start_utc`) como la fecha/hora de fin (`scheduled_end_utc`). Esta libertad generaba dos problemas críticos de usabilidad y consistencia:
1. **Inconsistencia de duración:** Por ejemplo, en la ruta de prueba física `RUT-PF-001 (v1)`, los puntos de control definen desplazamientos acumulados de 0, 1080, 1440 y 1800 segundos (duración planificada de 30 minutos). Sin embargo, el formulario permitía fijar un fin arbitrario (e.g. 43 minutos en el registro de calibración `REC-2026-0103`), creando una discrepancia entre la duración total del viaje y los tiempos previstos de arribo de los puntos de control.
2. **Fricción cognitiva del usuario:** El usuario debía calcular manualmente en su mente los minutos a sumar a la hora de salida, además de lidiar con etiquetas confusas como `(UTC)` en campos donde Odoo ya convierte automáticamente a la hora local de Ecuador (`America/Guayaquil`).

---

## 2. Solución Arquitectónica e Implementación

Conforme a las directrices de `AGENTS.md` e `instruction.md`, se implementó una solución desacoplada, consistente tanto a nivel de interfaz de usuario como en el ciclo de vida del ORM:

### 2.1. Fuente Única de Verdad en `transport.route.version`
- **Campos calculados:**
  - `planned_duration_s` (Integer): Segundos transcurridos desde el inicio (0s) hasta el punto de parada de tipo `destination`.
  - `planned_duration_display` (Char, stored): Representación legible en español (ej. `"30 min"` o `"1 h 15 min 30 s"`).
- **Validación de Aprobación (`action_approve`):**
  - Se exige que todos los `planned_offset_seconds` sean mayores o iguales a cero y estrictamente crecientes a lo largo de la secuencia de paradas. Se rechaza la aprobación con mensaje de error claro si existen desfases retrógrados o negativos.

### 2.2. Automatización y Consistencia Temporal en `transport.trip`
- **Cálculo Automático por Defecto:**
  - Al seleccionar una versión de ruta aprobada o cambiar la hora de salida (`scheduled_start_utc`), `scheduled_end_utc` se calcula automáticamente:
    $$\text{scheduled\_end\_utc} = \text{scheduled\_start\_utc} + \Delta t_{\text{planned\_duration\_s}}$$
  - Para `RUT-PF-001`, una salida a las `07:09:16` genera de forma inmediata una llegada prevista a las `07:39:16`.
- **Sincronización en Cascada de Visitas a Paradas (`transport.stop.visit`):**
  - Al crearse o reprogramarse el viaje en estado borrador, las visitas generadas asignan a cada control su hora prevista exacta:
    $$\text{scheduled\_at\_utc}_i = \text{scheduled\_start\_utc} + \text{offset}_i$$
  - Origen: `07:09:16` (+0s)
  - Control 1 (Redondel): `07:27:16` (+1080s)
  - Control 2 (Mall): `07:33:16` (+1440s)
  - Destino (UTA Huachi): `07:39:16` (+1800s)
- **Persistencia en ORM (`create`, `write`, `action_schedule`):**
  - La sincronización no depende únicamente del evento `@api.onchange` del navegador, sino que está blindada en `create()` y `write()`, soportando llamadas RPC, importaciones y scripts sin degradación de integridad.
- **Soporte de Cruce de Medianoche:**
  - Mediante aritmética de objetos `datetime` y `timedelta` de Python, las salidas nocturnas (ej. 23:45:00) calculan correctamente la fecha y hora de llegada del día siguiente (00:15:00).
- **Ajustes Excepcionales Controlados (Sección 4):**
  - El campo `scheduled_end_utc` permanece de solo lectura salvo que se active `is_manual_duration_override = True`.
  - Solo usuarios con rol **Gestor de Transporte** (`group_transport_manager`) pueden autorizar y confirmar un viaje con ajuste manual.
  - Se exige obligatoriamente un texto justificativo (`manual_duration_override_reason`) y se registra automáticamente el auditor (`manual_duration_override_user_id`).
- **Diferenciación de Métricas en Interfaz:**
  - Se separan nítidamente:
    1. **Duración Programada de Ruta:** Calculada a partir de los controles de la versión aprobada.
    2. **Estimación Red Vial:** Calculada por el motor OSRM a velocidad nominal (~30 km/h en Ambato), aclarando explícitamente en el tooltip que no constituye una predicción de tráfico en tiempo real.
    3. **Duración Real Observada:** Calculada a partir de los fixes GPS efectivos cuando existe telemetría suficiente (RF-20).
- **Limpieza de Etiquetas de Zona Horaria:**
  - Se eliminaron las etiquetas estáticas `(UTC)` de las vistas y modelos de viaje y paradas, sustituyéndolas por `"Hora Local de Ecuador"`, permitiendo que el cliente web de Odoo presente la hora convertida a `America/Guayaquil` de forma natural.

### 2.3. Salvaguarda de Registros Históricos
- El recorrido histórico `REC-2026-0103` (43 minutos) fue verificado en la base operacional `georutex`: se mantuvo inalterado con sus valores originales intactos (`scheduled_start_utc = 2026-11-04 12:09:16`, `scheduled_end_utc = 2026-11-04 12:52:16`).

---

## 3. Pruebas Automatizadas y Verificación

Se desarrolló la suite nativa `TestTripScheduleAutomation` en `addons/uta_transport_monitor/tests/test_trip_schedule_automation.py` cubriendo los 7 escenarios exigidos:

1. `test_01_duration_calculated_from_destination_stop`: Comprobación del cálculo automático de 30 min (1800s) y fin previsto `07:39:16` para salida `07:09:16`.
2. `test_02_recalculation_on_start_time_change`: Recálculo reactivo del fin al modificar la hora de inicio de 07:09:16 a 08:15:00.
3. `test_03_recalculation_on_version_change`: Recálculo reactivo al conmutar entre versiones con distintas duraciones (v1 de 30 min a v2 de 40 min).
4. `test_04_non_progressive_or_negative_offsets_rejected_on_approve`: Rechazo con `ValidationError` al intentar aprobar versiones con tiempos no progresivos o negativos.
5. `test_05_stop_visits_match_scheduled_times`: Coincidencia exacta de tiempos en cascada entre las visitas a paradas generadas y los desplazamientos previstos.
6. `test_06_midnight_crossing_scheduling`: Cálculo sin desbordamiento de fecha cruzando la medianoche (23:45:00 $\to$ 00:15:00 del día siguiente).
7. `test_07_manual_override_permissions_and_reason`: Restricción de ajuste manual a gestores, exigencia de justificación y auditoría de usuario.

### Resultados de Ejecución
- **Entorno de pruebas (`georutex_test`):**
  - Suite de Recorridos (`transport_trip`): 13 pruebas ejecutadas, **0 fallos, 0 errores**.
  - Suite Completa del Addon: 87 pruebas nativas ejecutadas (123 ejecuciones totales con post-tests), **0 fallos, 0 errores (100% de éxito)** en 23.88 segundos.
- **Base Operacional (`georutex`):**
  - Módulo actualizado satisfactoriamente en 1.66s.
  - Demostración en Odoo Shell:
    ```text
    TRIP: REC-2026-0105 START: 2026-11-05 12:09:16 AUTO-END: 2026-11-05 12:39:16 DUR_DISP: 30 min
    STOPS:
    Santa Rosa Park — acceso vial 2026-11-05 12:09:16 (+0 min)
    Redondel de Huachi Chico 2026-11-05 12:27:16 (+18 min)
    Mall de los Andes 2026-11-05 12:33:16 (+24 min)
    UTA — Campus Huachi 2026-11-05 12:39:16 (+30 min)
    ```

