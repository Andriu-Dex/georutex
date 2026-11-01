# Informe de Cierre — Fase 1: Revisión Técnica y Endurecimiento

**Fecha:** 2026-11-01  
**Entrega:** `2026-11-01-02-phase-1-technical-review-and-hardening.md`  
**Módulo técnico:** `uta_transport_monitor` (Odoo 16 Community)  
**Autoría:** GeoRutex Engineering Team  
**Estado:** `COMPLETADO (Listo para iniciar Fase 2)`

---

## 1. Objetivo

Realizar la auditoría técnica y cierre riguroso de la **Fase 1** conforme a `instruction.md`, resolviendo los 8 puntos de verificación requeridos antes de dar paso al modelado operacional de la Fase 2:
1. Asegurar la clasificación estricta de telemetrías (`real` vs `simulated`).
2. Configurar la seguridad perimetral del receptor OsmAnd (puerto 5055), documentar la topología de Cloudflare Tunnel e implementar identificadores de dispositivo no predecibles.
3. Verificar el aislamiento de pruebas nativas de Odoo contra el servicio `postgres-test` y la base `georutex_test`.
4. Documentar el digest y compatibilidad de la imagen `traccar/traccar:6.5`.
5. Corregir y verificar la conversión de unidades de velocidad (nudos a km/h) y marcas de tiempo UTC.
6. Probar la idempotencia ante concurrencia, reintentos y marcas de tiempo coincidentes.
7. Implementar y validar reglas por registro (aislamiento para conductores) y permisos ACL.
8. Verificar consultas de rangos históricos en la API de Traccar 6.5.

---

## 2. Fuentes y Requisitos Aplicados

- `AGENTS.md`: Separación de responsabilidades, no alteración de Git sin autorización, aislamiento de pruebas en contenedores Odoo y política de privacidad de evidencias.
- `docs/requirements.md`:
  - `RF-01`: Captura GPS, timestamps UTC y velocidad en km/h.
  - `RF-02`: Vinculación vehículo-dispositivo con identificadores seguros.
  - `RNF-01`, `RNF-02`: Desacoplamiento por capas y consumo vía API REST.
  - `RNF-04`: Restricción de acceso para conductores.
  - `RNF-08`: Pruebas de regresión unitarias e integración en entorno descartable.
  - `RNF-11`: Docker Compose y orquestación reproducible.
  - `RNF-14`: Saneamiento de datos e inmutabilidad de la verdad operativa.
- `docs/architecture.md`: Contratos de red y topología de pruebas sobre base descartable.

---

## 3. Cambios Implementados

### 3.1. Clasificación de Origen (`models/fleet_vehicle.py` y `services/gps_sync.py`)
- Se añadió el campo `is_simulated = fields.Boolean(default=False)` al modelo `fleet.vehicle`.
- En `services/gps_sync.py`, la telemetría se clasifica automáticamente como `simulated` si el vehículo está marcado como simulado, si los atributos del paquete Traccar indican simulación o si el protocolo es `simulated`. Si no se cumple ninguna de estas condiciones, se clasifica como `real`.

### 3.2. Seguridad OsmAnd y Cloudflare Tunnel (`infra/cloudflare/cloudflared.example.yaml`)
- Se documentó la topología perimetral en `infra/cloudflare/cloudflared.example.yaml`:
  - **Único puerto expuesto públicamente:** `5055` (receptor HTTP OsmAnd) mediante túnel seguro.
  - **Puertos estrictamente locales:** `8082` (consola web y API REST de Traccar) y `5432`/`5433` (PostgreSQL) vinculados a `127.0.0.1`.
- Se implementó `action_generate_secure_unique_id()` en `fleet.vehicle`, generando identificadores criptográficamente seguros mediante `secrets.token_hex(4).upper()` (`UTA-BUS-XXXXXXXX`) para evitar identificadores secuenciales predecibles.

### 3.3. Aislamiento de Pruebas (`compose.yaml` y perfiles)
- Se configuró el servicio `postgres-test` con volumen volátil `tmpfs` y base de datos `georutex_test`.
- Las pruebas nativas de Odoo se ejecutan apuntando a `HOST=postgres-test`, garantizando que la base de datos de desarrollo `georutex` permanezca intacta y sin contaminación de fixtures.

### 3.4. Imagen de Traccar y Digest
- Imagen oficial fijada: `traccar/traccar:6.5`.
- **RepoDigest comprobado:** `traccar/traccar@sha256:e569632fe9d6dfef3152e8602992508cfe5bc3ea2f24ae4220e8445af3679a60`.
- **Arquitectura:** Linux `amd64`, Java Runtime embebido con base de datos H2 persistente en `/opt/traccar/data`.
- **Evaluación:** Estable, compatible con la API REST utilizada (`/api/devices`, `/api/positions`) y sin fallos de migración Liquibase.

### 3.5. Corrección de Unidades de Velocidad y Marcas de Tiempo
- **Hallazgo técnico:** La API de Traccar almacena y retorna la velocidad cruda (`speed`) en **nudos (knots)**, independientemente de la configuración de la interfaz de usuario.
- **Corrección:** Se incorporó el factor de conversión oficial en `services/gps_sync.py`:
  $$\text{speed\_kmh} = \text{round}(\text{raw\_speed} \times 1.852, 2)$$
- Las marcas temporales se reciben en ISO-8601 UTC desde Traccar y se normalizan a fecha/hora UTC ingenua para el ORM de Odoo, mostrándose en el huso `America/Guayaquil` según el contexto del usuario.

### 3.6. Idempotencia y Concurrencia
- La restricción SQL `unique(traccar_device_id, fix_time)` en `transport.vehicle.position` asegura que ninguna combinación de dispositivo y hora se duplique.
- En `services/gps_sync.py`, la creación se ejecuta dentro de un `self.env.cr.savepoint()`, evitando que una colisión de clave por concurrencia aborte la transacción del lote completo.
- Se verificó que marcas temporales idénticas en dispositivos diferentes son permitidas sin conflicto.

### 3.7. Reglas por Registro y Seguridad (`security/rules.xml`)
- Se implementó la regla `rule_transport_position_driver`:
  - Los usuarios pertenecientes al grupo `group_transport_driver` únicamente pueden consultar posiciones del vehículo donde `vehicle_id.driver_id == user.partner_id`.
- Se implementó la regla `rule_transport_position_global` otorgando acceso completo a administradores y analistas.

### 3.8. Consultas Históricas en Traccar
- Se validó el comportamiento del endpoint `/api/positions?deviceId=X&from=...&to=...`:
  - Retorna posiciones históricas dentro de la ventana temporal especificada.
  - Retorna lista vacía ante ventanas sin actividad.
  - Retorna la posición más reciente cuando se omite el rango de fechas.

---

## 4. Validaciones Ejecutadas y Resultados

| Prueba | Comando / Entorno | Resultado |
|---|---|---|
| **Linter PEP 8** | `flake8 addons/uta_transport_monitor tests` | **0 errores** |
| **Pytest Unitario** | `docker compose run --rm odoo-test` | **14 PASADAS** en 0.87s (88% cobertura) |
| **Pruebas Nativas Odoo (Aisladas)** | `docker compose run --rm -e HOST=postgres-test odoo odoo -d georutex_test ...` | **7 PASADAS** en 0.14s sobre `postgres-test` (0 fallos, 0 errores). |
| **Idempotencia y Conversión km/h** | `test_sync_idempotency_and_telemetry_update` | **PASADA**. 30 nudos convertidos a 55.56 km/h; 0 duplicados en re-sincronización. |
| **Aislamiento Conductor (Regla por Registro)** | `test_driver_record_rule_isolation` | **PASADA**. Chofer solo visualiza posiciones de su vehículo asignado. |
| **Generador de ID Seguro** | `test_generate_secure_unique_id` | **PASADA**. IDs no predecibles generados (`UTA-BUS-XXXXXXXX`). |
| **Clasificación Simulado** | `test_simulated_vehicle_source_classification` | **PASADA**. Telemetría marcada estrictamente como `simulated`. |
| **Integración Histórica Traccar 6.5** | Peticiones HTTP directas con ventanas temporales | **PASADA**. Filtrado correcto por rango `from`/`to`. |

---

## 5. Pendientes que Requieren Intervención Humana

- **Validación física con datos móviles (Traccar Client):**
  - Mantenida como `PENDIENTE DE VALIDACIÓN EXTERNA` (`EVI-01-04` en `evidence/INDEX.md`).
  - No se simularon trazas para suplir la prueba real. Requiere conectar un smartphone con datos móviles hacia el túnel de ingreso del puerto 5055.

---

## 6. Estado para Fase 2

La Fase 1 queda **técnicamente cerrada y blindada**. No se realizaron commits automáticos en Git. El entorno se encuentra preparado para avanzar a la **Fase 2 (Modelado y gestión operacional de rutas, paradas y horarios)**.

