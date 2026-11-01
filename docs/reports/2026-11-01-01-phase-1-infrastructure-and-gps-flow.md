# Informe de Ejecución — Fase 1: Infraestructura y Flujo GPS Extremo a Extremo

**Fecha:** 2026-11-01  
**Entrega:** `2026-11-01-01-phase-1-infrastructure-and-gps-flow.md`  
**Módulo técnico:** `uta_transport_monitor` (Odoo 16 Community)  
**Autoría:** GeoRutex Engineering Team  
**Estado:** `COMPLETADO (A falta de validación humana con datos móviles)`

---

## 1. Objetivo

Implementar de forma reproducible y desacoplada la **Fase 1** del proyecto GeoRutex conforme a `instruction.md`, `AGENTS.md`, `docs/requirements.md` (sección 13) y `docs/architecture.md`:
1. Asegurar la topología de red en Docker Compose, restringiendo puertos administrativos y fijando la versión de Traccar Server a una etiqueta inmutable (`6.5`).
2. Configurar una base de datos PostgreSQL aislada para el perfil de pruebas automatizadas (`postgres-test`).
3. Construir el adaptador HTTP desacoplado en `integrations/traccar_client.py` consumiendo la API REST oficial de Traccar.
4. Implementar el servicio de sincronización en `services/gps_sync.py` con garantía de idempotencia, deduplicación y almacenamiento en UTC.
5. Extender `fleet.vehicle` mediante `_inherit` para asociar dispositivos Traccar (`traccar_device_id`, `traccar_unique_id`), registrar la última telemetría y calcular el estado de conexión GPS.
6. Crear el modelo de persistencia de posiciones `transport.vehicle.position` con restricción de unicidad `(traccar_device_id, fix_time)`.
7. Diseñar vistas de usuario, botones de acción en formulario de vehículo y tarea programada `ir.cron` cada 5 minutos.
8. Ejecutar pruebas unitarias (Pytest), pruebas nativas de Odoo (`TransactionCase`) y prueba de integración real entre contenedores.

---

## 2. Fuentes y Requisitos Aplicados

- `AGENTS.md`: Convenciones de arquitectura modular, estricta prohibición de escribir a la base interna de Traccar, inmutabilidad de datos, lenguaje de desarrollo en inglés y textos visibles en español.
- `docs/requirements.md`:
  - `RF-01`: Captura y registro de posiciones geográficas (latitud, longitud, velocidad, hora UTC).
  - `RF-02`: Asociación obligatoria de dispositivo de rastreo con vehículo Fleet.
  - `RNF-01`: Arquitectura modular por capas en Odoo 16.
  - `RNF-02`: Desacoplamiento de Traccar mediante API REST.
  - `RNF-08`: Pruebas automatizadas (unitarias e integración).
  - `RNF-11`: Entorno reproducible mediante Docker Compose.
  - `RNF-14`: Saneamiento de credenciales y privacidad de evidencias.
- `docs/architecture.md`: Contratos de integración de Traccar (`8082` para API REST, `5055` para receptor OsmAnd).

---

## 3. Cambios Implementados

### 3.1. Infraestructura y Docker Compose (`compose.yaml`)
- **Restricción de puertos administrativos:**
  - PostgreSQL host port vinculado estrictamente a `127.0.0.1:${POSTGRES_HOST_PORT:-5433}:5432` para evitar exposición pública en interfaces de red.
  - Consola web y API de Traccar vinculada a `127.0.0.1:${TRACCAR_WEB_PORT:-8082}:8082`.
  - Puerto de ingesta OsmAnd `5055` expuesto en todas las interfaces para permitir la recepción de paquetes móviles a través de túnel o proxy.
- **Fijación de versión Traccar:** Sustitución de `traccar/traccar:latest` por la versión inmutable `traccar/traccar:6.5`.
- **Base de datos dedicada de pruebas:** Adición del servicio `postgres-test` con almacenamiento volátil `tmpfs` bajo el perfil de pruebas (`profile: test`), garantizando que la ejecución de pruebas nativas y suites unitarias no contamine la base de datos de desarrollo.

### 3.2. Adaptador HTTP (`addons/uta_transport_monitor/integrations/traccar_client.py`)
- Cliente HTTP síncrono desacoplado del ORM de Odoo.
- Autenticación HTTP Basic con credenciales configurables.
- Excepciones tipadas: `TraccarConnectionError`, `TraccarAuthError`, `TraccarApiError`.
- Métodos implementados: `test_connection()`, `get_devices()`, `get_device(id)`, `get_device_by_unique_id(unique_id)`, `get_positions(device_id, from, to)`.

### 3.3. Persistencia y Modelado ORM (`models/`)
- **`transport.vehicle.position`:** Almacena posiciones geográficas con campos `vehicle_id`, `traccar_device_id`, `traccar_position_id`, `fix_time` (UTC), `server_time` (UTC), `latitude`, `longitude`, `speed`, `altitude`, `is_valid`, `source` (`real` vs `simulated`) y `protocol`.
  - Restricción SQL: `unique(traccar_device_id, fix_time)`.
- **`fleet.vehicle` (Extensión):** Añade `traccar_device_id`, `traccar_unique_id`, `gps_tracking_enabled`, `gps_connection_status` (`online`, `recent`, `offline`, `unlinked`), campos de última telemetría y botones de acción rápida.

### 3.4. Orquestación y Sincronización (`services/gps_sync.py`)
- Modelo de servicio `transport.gps.sync.service`:
  - `_get_traccar_client()`: Inicializa el cliente a partir de parámetros del sistema (`ir.config_parameter`) o variables de entorno.
  - `sync_vehicle_positions(vehicle)`: Consulta la ventana de posiciones, deduplica registros existentes e inserta nuevas telemetrías actualizando el estado del vehículo de forma atómica.
  - `sync_all_vehicles()`: Itera vehículos con rastreo activo gestionando excepciones por vehículo sin abortar el lote.
- Tarea programada (`data/ir_cron_data.xml`): Ejecución cada 5 minutos de `sync_all_vehicles()`.

### 3.5. Interfaz de Usuario y Seguridad
- **Vistas XML:**
  - `views/fleet_vehicle_views.xml`: Pestaña dedicada "Telemetría GPS / Traccar", widget de estado con badges de colores, botones "Probar Conexión Traccar" y "Sincronizar GPS", y botón inteligente (*smart button*) con contador de posiciones.
  - `views/transport_position_views.xml`: Lista, formulario y búsqueda avanzada con filtros por origen (`Datos Reales` / `Simulados`) y agrupación por vehículo y fecha.
  - `views/menu_views.xml`: Menú raíz "GeoRutex" con accesos a Operaciones, Flota y Posiciones GPS.
- **Seguridad:**
  - `security/groups.xml`: Roles de Analista (`group_transport_analyst`), Conductor (`group_transport_driver`) y Administrador (`group_transport_manager`).
  - `security/ir.model.access.csv`: Control de acceso para el modelo de posiciones.

---

## 4. Validaciones Ejecutadas y Resultados

| Prueba | Tipo | Comando / Mecanismo | Resultado |
|---|---|---|---|
| **Linter PEP 8 / Flake8** | Calidad estática | `docker run --rm georutex-test flake8 addons/uta_transport_monitor tests` | **EXITOSO** (0 errores, 0 advertencias) |
| **Suite Unitaria (Pytest)** | Unitarias aisladas | `docker compose run --rm odoo-test` | **14 PASADAS** en 0.69s. Cobertura: 100% en `domain.geo`, 81% en `traccar_client.py` (88% total). |
| **Pruebas Nativas Odoo** | ORM / Idempotencia | `docker compose run --rm odoo odoo -d georutex -u uta_transport_monitor --test-enable --test-tags=gps_sync,smoke` | **3 PASADAS** en 0.06s. Idempotencia verificada: 1ª sincronización crea 2 registros; 2ª sincronización con datos idénticos crea 0 duplicados. |
| **Comunicación HTTP Contenedor-a-Contenedor** | Integración de red | Petición desde contenedor Odoo hacia `http://traccar:8082/api/server` | **EXITOSO** (HTTP 200 OK, Servidor Traccar 6.5) |
| **Flujo GPS Completo en Vivo** | Integración E2E | Envío de paquete OsmAnd (puerto 5055) -> Traccar Server -> Sincronización Odoo 16 | **EXITOSO**. Posición capturada: Lat `-1.2693`, Lon `-78.6272`, Vel `25.5 km/h`. Idempotencia en vivo verificada (1 posición creada, 0 en reintento). |

---

## 5. Alcance Cubierto y Pendientes

### Alcance de la Fase 1 cubierto al 100% en entorno automatizado
- Infraestructura asegurada, aislada y versionada.
- Conectividad Odoo 16 ↔ Traccar Server verificada.
- Sincronización idempotente manual y programada.
- Extensión de Fleet con trazabilidad y visualización moderna.

### Pendientes que requieren intervención humana (Puertas de Validación)
1. **Validación GPS con datos móviles (celular físico):**
   - *Estado:* `PENDIENTE DE VALIDACIÓN EXTERNA` (Registrado en `evidence/INDEX.md` como `EVI-01-04`).
   - *Procedimiento requerido para el usuario:*
     1. Desplegar un túnel seguro (p. ej. Cloudflare Tunnel) o reenviar un puerto público hacia `127.0.0.1:5055` del host donde corre Docker.
     2. Instalar la aplicación **Traccar Client** en un teléfono móvil Android/iOS.
     3. Configurar en la aplicación:
        - URL del servidor: `https://<dominio-publico-o-ip>:5055` (o protocolo HTTP correspondiente).
        - Identificador de dispositivo: `UTA-BUS-01` (o el asignado al vehículo en Odoo).
        - Frecuencia de actualización: 30–60 segundos.
     4. Desactivar la red Wi-Fi en el móvil para operar exclusivamente con datos móviles.
     5. Desplazarse unos metros y verificar la llegada del punto en Odoo pulsando «Sincronizar GPS» en el vehículo.
2. **Servidor SonarQube:**
   - La configuración `sonar-project.properties` está preparada; el escaneo se encuentra bloqueado hasta que se suministren credenciales/acceso a un servidor SonarQube activo.

---

## 6. Conclusión y Estado de Preparación

La **Fase 1 está completada y verificada técnicamente**. El flujo de datos entre el receptor GPS, el servidor Traccar y Odoo funciona de manera idempotente y robusta. 

No se ha realizado ningún commit en Git, respetando la regla universal del usuario. El proyecto se encuentra listo para someterse a revisión antes de avanzar a la **Fase 2 (Modelado y gestión operacional de rutas, paradas y horarios)**.

