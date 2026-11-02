# Informe Técnico de Seguridad: Aislamiento Operacional y Protección del Sembrador de Demostración

**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Fecha:** 2026-11-01  
**Referencia:** Corrección preventiva de seguridad sobre `scripts/seed_demo_database.py`  
**Estado:** Verificado y Aprobado  

---

## 1. Contexto y Análisis de Riesgo

Durante la auditoría preventiva de código, se detectó una vulnerabilidad operacional en el script de aprovisionamiento de datos demostrativos ([`scripts/seed_demo_database.py`](file:///c:/Documentos/D-Proyectos/Git/georutex/scripts/seed_demo_database.py)), que utilizaba la llamada incondicional:

```python
pos_model.search([]).unlink()
inc_model.search([]).unlink()
existing_demo_trips.unlink()
```

### Riesgos Identificados:
1. **Destrucción Accidental de Datos Operacionales:** Si el script fuese ejecutado por error apuntando a la base de datos operativa (`georutex`) o producción, la instrucción `search([]).unlink()` eliminaría de forma irrecuperable todas las posiciones históricas y operativas del sistema.
2. **Pérdida de Evidencia Celular Real:** Incluso dentro de una base de pruebas, un borrado incondicional eliminaría posiciones reales transmitidas mediante red móvil 4G (`source = 'real'`) en vehículos físicos como `TBA-1001`.
3. **Falta de Guardas de Entorno:** No existía una barrera a nivel de base de datos que impidiera invocar la lógica destructiva en entornos no autorizados.

---

## 2. Medidas Preventivas y Arquitectura de Blindaje

Se diseñó e integró el servicio de seguridad [`demo_safety.py`](file:///c:/Documentos/D-Proyectos/Git/georutex/addons/uta_transport_monitor/services/demo_safety.py) en la capa de servicios de GeoRutex, implementando dos niveles estrictos de defensa:

### 2.1 Barrera a Nivel de Base de Datos (`validate_target_database`)
- Se configuró la lista blanca inmutable:
  ```python
  ALLOWED_DEMO_DATABASES = frozenset({"georutex_demo"})
  ```
- Antes de realizar cualquier conexión, lectura o escritura, el sistema valida el nombre de la base de datos de destino.
- Si se especifica `georutex`, `georutex_prod`, `postgres` o cualquier base ajena a la lista blanca, la ejecución se interrumpe de inmediato mediante `ValueError` y genera un log de nivel `CRITICAL`.

### 2.2 Ámbito Restringido de Limpieza (`cleanup_demo_dataset`)
Se reemplazó cualquier llamada a `search([])` por consultas estrictamente acotadas por dominio:
- **Recorridos:** Se filtran exclusivamente por el prefijo formal de demostración:
  ```python
  demo_trips = trip_model.search([("name", "=like", "REC-DEMO-%")])
  ```
  Cualquier viaje operacional (ej. `REC-OPERATIONAL-...`) queda excluido y protegido.
- **Telemetría GPS:** Únicamente se seleccionan posiciones vinculadas a los viajes demo identificados, o posiciones marcadas explícitamente con `source = 'simulated'` en vehículos de demostración:
  ```python
  pos_domain = [
      "|",
      ("trip_id", "in", demo_trip_ids),
      "&",
      ("vehicle_id", "in", demo_veh_ids),
      ("source", "=", "simulated"),
  ]
  ```
  La telemetría física real (`source = 'real'`) y la perteneciente a otros vehículos nunca se selecciona ni se elimina.
- **Incidencias:** Únicamente incidencias asociadas a los viajes demo identificados (`trip_id in demo_trip_ids`).

---

## 3. Preservación y Reproducibilidad de `georutex_demo`

Tras aplicar el mecanismo de borrado acotado, se ejecutó el sembrador y se verificó que la base de datos `georutex_demo` conserva íntegramente sus registros e indicadores:

```
=== RESUMEN DE INTEGRIDAD POST-LIMPIEZA ===
  Total de recorridos: 12
  Recorridos ejecutados: 10
  Recorrido indeterminado: 1 (REC-DEMO-08, 0 posiciones GPS)
  Recorrido cancelado: 1 (REC-DEMO-11, excluido de denominadores)
  Posiciones GPS totales: 281
  Posiciones huérfanas: 0
```

### Indicadores Confirmados:
- **MT-01 (Cumplimiento de Rutas):** 50.0% Bruto ($5/10$) / 60.0% Ajustado ($6/10$, incorporando la justificación aprobada en `REC-DEMO-09`).
- **MCS-01 (Integridad GPS):** 100.0% ($281/281$ posiciones válidas).
- **MCS-02 (Exactitud Traccar $\rightarrow$ Odoo):** `is_na = True` (`N/A`) con motivo explícito por muestra independiente $< 2$.
- **MT-02 a MT-08:** Muestras de denominadores consistentes sobre $n=10$ viajes evaluables.

---

## 4. Evidencia de Pruebas Automatizadas

Se implementaron dos suites de pruebas específicas para certificar el bloqueo de operaciones destructivas fuera de entornos autorizados:

### 4.1 Pruebas Unitarias Pytest (`tests/unit/test_demo_safety.py`)
12 casos de prueba ejecutados con éxito:
1. `test_validate_target_database_rejects_operational_database`: Rechazo de `georutex`.
2. `test_validate_target_database_rejects_unauthorized_environments`: Rechazo parametrizado de `postgres`, `georutex_prod`, `production`, `georutex_test`, cadenas vacías, `None` y tipos no válidos.
3. `test_validate_target_database_accepts_authorized_demo_db`: Aceptación de `georutex_demo`.
4. `test_cleanup_demo_dataset_blocks_operational_database`: Confirmación de que ningún modelo es consultado ni alterado al apuntar a `georutex`.
5. `test_cleanup_demo_dataset_scoped_search_domains`: Comprobación de que las búsquedas se ejecutan con filtros específicos y nunca con dominios vacíos.

### 4.2 Pruebas Nativas Odoo 16 (`addons/uta_transport_monitor/tests/test_demo_safety.py`)
2 casos de prueba en transacción real Odoo:
1. `test_01_operational_database_rejection`: Rechazo dentro del ORM de Odoo.
2. `test_02_scoped_cleanup_preserves_operational_data`: Coexistencia de un viaje operacional con telemetría real (`source='real'`) y un viaje sintético (`source='simulated'`). Comprobación fehaciente de que la limpieza demo purga el viaje sintético pero **preserva intactos el viaje operacional y su telemetría real**.

### 4.3 Matriz de Verificación Global

| Herramienta / Suite | Alcance | Resultado |
|:---|:---|:---:|
| **Pytest Unitario** | 49 pruebas unitarias de dominio y seguridad | **49 / 49 Pasaron (0 fallos)** |
| **Flake8 Linter** | Código fuente del addon y suites de prueba | **0 Errores de estilo** |
| **Odoo Native Test Suite** | 70 pruebas transaccionales en `georutex_test` | **70 / 70 Pasaron (0 fallos, 0 errores)** |
| **Prueba en Vivo de Bloqueo** | Intento de ejecución con `db_name='georutex'` | **Bloqueado con ValueError** |
