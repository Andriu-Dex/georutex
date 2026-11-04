# Informe Técnico: Mejoras Integrales de Usabilidad Operacional

**Fecha:** 2026-11-04  
**Referencia:** `EVI-07-05`  
**Módulos Afectados:** `uta_transport_monitor` (Modelos, Vistas, Wizards y Componentes Owl/JS)  
**Requisitos Vinculados:** RF-09 a RF-38, RNF-05, RNF-10, RNF-12, RNF-16  

---

## 1. Justificación y Objetivos

A partir de la retroalimentación del flujo de usuario y el uso práctico del software, se identificaron varios puntos de fricción donde el operador o conductor experimentaba demoras o sobrecarga cognitiva innecesaria:
1. **Definición de paradas en segundos:** Obligaba al planificador a convertir minutos a segundos mentalmente (ej. multiplicar 18 min por 60 para ingresar 1080 s).
2. **Asignación a ciegas de flota:** Al programar recorridos, el operador debía seleccionar manualmente el conductor aunque el vehículo ya tuviera conductor asignado en flota, y los solapamientos solo se detectaban al intentar guardar.
3. **Monitoreo pasivo en mapas:** Para observar el avance de un vehículo en un recorrido en curso, el supervisor debía refrescar el navegador o hacer clic repetidamente en sincronizar.
4. **Fricción en descargos de incidencias:** El conductor debía editar el registro técnico de la incidencia para escribir descargos, sin categorías preestablecidas.
5. **Selección tediosa de fechas en Dashboard:** Requería abrir selectores de calendario manuales para consultas rutinarias ("¿cómo va la operación hoy o esta semana?").

---

## 2. Paquete de Mejoras Implementadas

### 2.1. Gestión de Paradas y Desplazamientos en Minutos
- **Modelo `transport.route.stop`:**
  - Se introdujo `planned_offset_minutes` con cálculo e inversa bidireccional:
    $$\text{planned\_offset\_minutes} = \frac{\text{planned\_offset\_seconds}}{60.0}$$
  - Se añadió `planned_offset_display` formateado en texto amigable (`"18 min"`, `"24 min 30 s"`).
  - En la vista tipo lista de paradas de la versión de ruta, ahora se edita directamente el tiempo en minutos, visualizándose la columna formateada, manteniendo los segundos en segundo plano para compatibilidad matemática del motor de evaluación.
  - En el **Editor Cartográfico Visual** (`route_editor_widget.js`), los popups de marcadores ahora reflejan el tiempo en minutos: `${Math.round(s/60)} min (${s} s)`.

### 2.2. Asistente Operacional de Flota y Alerta en Tiempo Real
- **Modelo `transport.trip`:**
  - `@api.onchange("vehicle_id")`: Si el vehículo tiene conductor habitual (`vehicle_id.driver_id`), se autoasigna automáticamente al recorrido sin pasos adicionales.
  - `@api.onchange("vehicle_id", "driver_id", "scheduled_start_utc", "scheduled_end_utc")`: Evalúa instantáneamente en el navegador si el vehículo o conductor ya poseen otro viaje programado o en curso en esa ventana horaria. En caso de conflicto, despliega un aviso dialogado inmediato antes de que el usuario guarde el registro.

### 2.3. Monitoreo en Vivo (Live Polling Reactivo)
- **Componentes `trip_map_widget.js` y `trip_map_widget.xml`:**
  - Se añadió el botón **"Activar En Vivo / En Vivo (15s)"** en la barra de herramientas del mapa del recorrido.
  - Al activarse, consulta periódicamente (`setInterval` de 15 segundos) la telemetría actualizada mediante la llamada ORM desacoplada `get_map_data`.
  - La actualización preserva el nivel de zoom y encuadre del usuario (`isAutoRefresh = true`), actualizando suavemente el marcador del bus y extendiendo la polilínea de trayectoria sin parpadeos.
  - El temporizador se destruye de forma segura en `onWillUnmount` para evitar fugas de memoria.

### 2.4. Asistente Rápido de Justificación de Incidencias
- **Modelo Transitorio `transport.incident.justify.wizard`:**
  - Permite a conductores y supervisores justificar cualquier incidencia no resuelta con un diálogo modal de un solo paso.
  - Ofrece motivos categorizados estandarizados:
    1. *Congestión vehicular severa / Tráfico*
    2. *Cierre o bloqueo de vía por obras*
    3. *Avería o problema mecánico / eléctrico*
    4. *Emergencia médica o asistencia a pasajero*
    5. *Condiciones climáticas adversas*
    6. *Otra eventualidad justificada*
  - Campo de texto libre para detalle operativo.
  - Botón directo `"Justificar"` (icono `fa-commenting-o`) integrado en:
    - La vista de lista de incidencias operacionales.
    - El formulario de incidencia.
    - La pestaña de incidencias del recorrido operacional.
  - **Segregación de funciones blindada:** El asistente no vulnera las reglas de negocio; los conductores no pueden autoaprobar sus propias justificaciones (exclusivo para Analistas y Gestores).

### 2.5. Filtros Rápidos de Período en Dashboard Owl 2
- **Componentes `transport_dashboard_action.js` y `transport_dashboard_templates.xml`:**
  - Se agregaron botones de acceso directo: **[Hoy]**, **[Esta Semana]**, **[Este Mes]** y **[Todo el Historial]**.
  - Al presionar un botón, calcula dinámicamente las fechas de inicio y fin en formato ISO y ejecuta el filtrado reactivo de KPIs y gráficas en una sola acción.

---

## 3. Pruebas Automatizadas y Verificación

Se creó la suite nativa `TestUsabilityEnhancements` en `addons/uta_transport_monitor/tests/test_usability_enhancements.py`:
1. `test_01_stop_minutes_offset_sync`: Sincronización bidireccional entre minutos decimales y segundos, y consistencia del formateo legible.
2. `test_02_trip_onchange_vehicle_driver_availability`: Autoasignación de conductor y emisión de advertencia de conflicto de vehículo/conductor.
3. `test_03_incident_justify_wizard`: Apertura de asistente modal, registro de justificación categorizada, transición a estado `pending` y validación estricta de segregación de funciones (conductor bloqueado para aprobarse a sí mismo).

### Resultados de Ejecución
- **Entorno de pruebas (`georutex_test`):**
  - Suite de usabilidad: 3 pruebas ejecutadas, **0 fallos, 0 errores**.
  - Suite completa del módulo: **90 pruebas nativas (128 ejecuciones con post-tests), 0 fallos, 0 errores (100% de éxito)** en 26.10 s.
- **Base Operacional (`georutex`):**
  - Módulo actualizado satisfactoriamente en 1.73 s y servicio reiniciado.

