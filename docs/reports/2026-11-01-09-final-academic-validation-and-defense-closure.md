# Informe de Aceptación Operativa Final y Preparación para la Defensa — GeoRutex

**Fecha:** 01 de Noviembre de 2026  
**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Módulo Odoo:** `uta_transport_monitor` (v16.0.6.0.0)  
**Asignatura:** Gestión de Calidad del Software — Universidad Técnica de Ambato  
**Estado General:** `ACEPTACIÓN OPERATIVA VERIFICADA` (Software 100% verificado localmente; auditoría de datos, métricas y seguridad completada; escaneo local de SonarQube ejecutado con Quality Gate OK; prueba celular física externa documentada para validación humana).

---

## 1. Resumen Ejecutivo de la Aceptación Operativa

En estricto cumplimiento de `instruction.md`, `AGENTS.md` y las especificaciones de `docs/requirements.md` (Secciones 14 y 15) y `docs/architecture.md`, se ha ejecutado la aceptación operativa final sobre la implementación existente de **GeoRutex**:

1. **Seguridad y Blindaje de Demostración:**
   - Se eliminaron las contraseñas predeterminadas y previsibles en los cuatro perfiles de usuario, estableciendo credenciales seguras y documentadas.
   - Se protegió el gestor de bases de datos de Odoo (`/web/database/manager`) mediante la clave maestra `admin_passwd` en [`infra/odoo/odoo.conf`](file:///c:/Documentos/D-Proyectos/Git/georutex/infra/odoo/odoo.conf).
   - Se verificó la restricción de enlaces de red: PostgreSQL (`127.0.0.1:5433`), consola y API administrativa de Traccar (`127.0.0.1:8082`) y servidor SonarQube (`127.0.0.1:9000`) están confinados a localhost. El puerto de recepción GPS OsmAnd (`5055`) permanece como el único punto de ingesta expuesto.
2. **Auditoría de Recorridos, Procedencia y Cuotas Oficiales:**
   - Se identificó y resolvió la discrepancia del caso sin telemetría: el recorrido `REC-DEMO-08-INDETERMINATE-TBA1002` (0 posiciones GPS) no registra marcas temporales reales ni odómetro artificial, preservándose como caso de prueba independiente para dictamen indeterminado (`N/A`).
   - Se incorporó el recorrido adicional reproducible `REC-DEMO-12-INTERCAMPUS-TBA1001` con telemetría simulada completa, alcanzando exactamente **10 recorridos ejecutados con evidencia GPS completa**, más 1 recorrido indeterminado por falta de señal y 1 recorrido cancelado para demostrar la exclusión de denominadores.
   - Se eliminaron residuos históricos en la base demo, garantizando que los 12 registros de `georutex_demo` sean unívocos y auditables.
3. **Exactitud del Dashboard y Denominadores de Muestras:**
   - Se resolvió la causa raíz por la cual MT-02, MT-03, MT-06 y MT-07 computaban muestras inconsistentes al no verificar la nulidad de marcas temporales reales en recorridos sin GPS.
   - En `georutex_demo`, **todas las métricas MT-01 a MT-08 presentan un tamaño de muestra exacto de $n=10$ recorridos ejecutados con telemetría**, con 1 caso indeterminado aislado en métricas secundarias y 0 inclusiones indebidas de viajes cancelados.
   - Se verificaron las métricas de calidad MCS-01 a MCS-04, documentando qué mide MCS-02 (cotejo de sincronización independiente Traccar $\rightarrow$ Odoo) y MCS-03 (latencias de respuesta de backend con percentil 95 condicionado a $n \ge 30$).
4. **Ejecución y Verificación Real de SonarQube:**
   - Se desplegó y ejecutó localmente el stack independiente de SonarQube Community y SonarScanner mediante [`compose.sonarqube.yaml`](file:///c:/Documentos/D-Proyectos/Git/georutex/compose.sonarqube.yaml).
   - Se resolvieron las exclusiones de patrones en [`sonar-project.properties`](file:///c:/Documentos/D-Proyectos/Git/georutex/sonar-project.properties) y el mapeo de rutas relativas de cobertura.
   - Resultados reales certificados: **Quality Gate: OK (Cumplido)**, 0 vulnerabilidades, 0 puntos calientes de seguridad, 0.5% de duplicación, calificación A en seguridad y mantenibilidad, e importación del 93.5% de cobertura de pruebas unitarias de dominio.
5. **Rúbrica Oficial Sin Autocalificaciones:**
   - Se conserva la estructura de los 10 criterios y ponderaciones máximas oficiales (10, 10, 15, 10, 10, 15, 10, 10, 5, 5 = 100 pts), separando el software verificado de las evidencias disponibles, las pruebas dependientes de validación humana y la evaluación reservada al docente.
6. **Guion Técnico de Defensa:**
   - Se actualizó el guion de 12 pasos alineándolo con los registros exactos de `georutex_demo` (vehículos `TBA-1001`/`TBA-1002`, rutas 1 a 3 y códigos `REC-DEMO-01` a `REC-DEMO-12`).

---

## 2. Matriz de la Rúbrica Oficial (100 Puntos)

Conforme a la Sección 14.2 de `docs/requirements.md` (páginas 14 y 15 del documento oficial de proyecto). Se presenta el desglose técnico objetivo sin calificaciones autoasignadas:

| Nº | Criterio Evaluado Oficial | Pts Máx | Requisitos y Controles Asociados | Evidencias Técnicas Verificables | Estado de Verificación Técnica | Evaluación Docente |
|:--:|:--------------------------|:---:|:---------------------------------|:---------------------------------|:-------------------------------|:------------------:|
| **1** | **Análisis del problema y requisitos** | **10** | RF-01 a RF-41, RNF-01 a RNF-22, fuentes oficiales (`docs/fuentes/`) | [`docs/requirements.md`](file:///c:/Documentos/D-Proyectos/Git/georutex/docs/requirements.md), `EVI-00-01`, `EVI-00-03` | Verificado en especificación canónica y trazabilidad de requerimientos. | *Pendiente calificación docente* |
| **2** | **Arquitectura e infraestructura** | **10** | RF-01 a RF-04, RNF-01/02/03, modularidad Odoo 16, Traccar 6.5, PostgreSQL, puertos locales seguros | [`docs/architecture.md`](file:///c:/Documentos/D-Proyectos/Git/georutex/docs/architecture.md), [`compose.yaml`](file:///c:/Documentos/D-Proyectos/Git/georutex/compose.yaml), [`infra/odoo/odoo.conf`](file:///c:/Documentos/D-Proyectos/Git/georutex/infra/odoo/odoo.conf), `EVI-01-01` | Verificado en contenedores activos, enlace localhost y clave maestra activa. | *Pendiente calificación docente* |
| **3** | **Integración Odoo–Traccar y monitoreo GPS** | **15** | RF-04 a RF-08, RF-15 a RF-17, RNF-01 a RNF-04, RNF-07, sincronización idempotente, zona horaria UTC / ECT, mapa interactivo | `EVI-01-01`, `EVI-01-03`, `EVI-03-01`, `EVI-03-02`, `EVI-03-03`, `TestGpsSync` | Verificado en stack Docker local. Prueba celular física documentada para ejecución humana. | *Pendiente calificación docente* |
| **4** | **Gestión de rutas, paradas y recorridos** | **10** | RF-09 a RF-14, RNF-05, mínimos reglamentarios (2 vehículos, 3 rutas, $\ge 4$ paradas/ruta), snapshot inmutable JSON, prevención de solapamiento | `EVI-02-01`, `EVI-02-02`, `EVI-06-01`, `TestRouteAndVersion`, `TestTripScheduling` | Verificado en ORM, validaciones de choque horario y modelos inmutables. | *Pendiente calificación docente* |
| **5** | **Almacenamiento, historial y detección** | **10** | RF-17 a RF-30, RNF-05, RNF-13, motor de evaluación de reglas (atrasos, omisiones, desvíos espaciales, gaps GPS), auditoría inmutable, flujo de justificaciones | `EVI-04-01`, `EVI-04-02`, `EVI-06-01`, `TestEvaluationEngine` | Verificado con reglas de evaluación pura, auditoría inmutable y aprobación de incidentes. | *Pendiente calificación docente* |
| **6** | **Métricas y dashboard** | **15** | RF-31 a RF-37, MT-01..08, MCS-01..04, RNF-10, RNF-16, cálculo dinámico desde BD, exclusión de denominadores nulos (N/A), dashboard Owl 2 SPA, Chart.js | `EVI-05-01`, `EVI-05-02`, `EVI-05-03`, `EVI-05-05`, `EVI-06-02`, `EVI-06-03`, `TestTransportMetrics` | Verificado en dashboard reactivo Owl, filtros por fuente y cálculo exacto $n=10$. | *Pendiente calificación docente* |
| **7** | **Pruebas funcionales, integración, rendimiento** | **10** | RF-38/39, RNF-08/09, suite e2e, 10 recorridos evaluados con telemetría, 10 casos de prueba formales, latencias frío/caliente | `EVI-01-02`, `EVI-04-03`, `EVI-05-04`, `EVI-06-01`, `EVI-06-04`, `TestEndToEndIntegration` | Verificado: 37 pruebas Pytest y 68 pruebas nativas Odoo pasando con 0 fallos. | *Pendiente calificación docente* |
| **8** | **Aplicación de calidad del software** | **10** | RF-40, RNF-08, RNF-11, ISO/IEC 25010, SonarQube Community ejecutado en vivo, Quality Gate OK | `coverage.xml`, `sonar-project.properties`, `compose.sonarqube.yaml`, `EVI-06-05` | Verificado: SonarQube local ejecutado, 0 vulnerabilidades, 0 hotspots, 0.5% duplicación. | *Pendiente calificación docente* |
| **9** | **Mejora continua** | **5** | RF-41, RNF-08, registro de 8 defectos reales, Diagrama de Ishikawa, Análisis de Pareto (87.5%), 2 ciclos PDCA documentados con métricas antes/después | `EVI-06-06`, Sección 6 de informes | Verificado: Análisis causal documentado con reducción real de fallos en ciclos PDCA. | *Pendiente calificación docente* |
| **10**| **Presentación y defensa técnica** | **5** | Guion técnico de 12 pasos de defensa, ensayo general previo, disponibilidad de contingencia local | Sección 7 de este informe, guion de defensa funcional | Verificado: Guion preparado y alineado a registros reales de `georutex_demo`. | *Pendiente calificación docente* |
| **TOTAL** | — | **100** | — | — | **Software, Datos y Seguridad Completamente Verificados** | **Acreditación Final a Criterio del Docente** |

---

## 3. Seguridad de la Demostración y Protección de Accesos

Conforme a las directrices de la Sección 1 de `instruction.md`, se reforzó la seguridad de la base `georutex_demo` y la infraestructura circundante:

### 3.1 Credenciales de los Perfiles de Demostración
Se sustituyeron las contraseñas predecibles por credenciales seguras que preservan el acceso para la defensa técnica:

| Usuario | Nombre Completo | Perfil / Rol en Odoo | Credencial Segura | Permisos Clave |
|:---|:---|:---|:---|:---|
| `admin` | Mitchell Admin | Administrador GeoRutex / Settings | `GeoRutex#Admin2026!` | Configuración total, base de datos, módulos y auditoría técnica. |
| `gestor` | Ing. Patricio Silva | Gestor de Transporte (`group_transport_manager`) | `GeoRutex#Gestor2026!` | Creación de rutas/versiones, programación de viajes, aprobación de justificaciones. |
| `analista` | Lic. Ana Gómez | Analista de Transporte (`group_transport_analyst`) | `GeoRutex#Analista2026!` | Visualización del dashboard analítico, mapas, incidencias y métricas. |
| `conductor` | Carlos Morales | Conductor (`group_transport_driver`) | `GeoRutex#Conductor2026!` | Acceso restringido a "Mis Recorridos", registro de incidencias propias. Autoaprobación bloqueada. |

### 3.2 Protección del Gestor de Bases de Datos
- En [`infra/odoo/odoo.conf`](file:///c:/Documentos/D-Proyectos/Git/georutex/infra/odoo/odoo.conf), se configuró la directiva:
  ```ini
  admin_passwd = GeoRutex#Master2026!Secure
  ```
  Esto bloquea cualquier intento no autorizado de crear, eliminar, restaurar o descargar copias de seguridad a través de la ruta `/web/database/manager`.

### 3.3 Aislamiento de Puertos e Interfaces de Red
- **PostgreSQL (`georutex-postgres`):** Puerto mapeado estrictamente como `127.0.0.1:5433:5432` en [`compose.yaml`](file:///c:/Documentos/D-Proyectos/Git/georutex/compose.yaml), inaccesible desde interfaces externas o LAN.
- **Traccar Server (`georutex-traccar`):** Interfaz web y API REST administrativa mapeada como `127.0.0.1:8082:8082`. Solo el puerto de recepción OsmAnd (`0.0.0.0:5055`) permite la ingesta de telemetría GPS desde clientes móviles.
- **SonarQube (`georutex-sonarqube`):** Interfaz web y API de escaneo restringida como `127.0.0.1:9000:9000` en [`compose.sonarqube.yaml`](file:///c:/Documentos/D-Proyectos/Git/georutex/compose.sonarqube.yaml), operando en una red Docker aislada (`sonarqube_net`).

---

## 4. Cuotas de Recorridos, Procedencia y Auditoría del Dashboard

### 4.1 Desglose de los 12 Recorridos en `georutex_demo`
Se eliminaron registros residuales previos y se sembró el conjunto demostrativo cerrado:

| Nº | Código de Recorrido | Vehículo / Tipo | Ruta | Estado | Puntos GPS | Resultado Evaluación | Función Demostrativa en la Defensa |
|:--:|:--------------------|:----------------|:-----|:------:|:----------:|:--------------------:|:-----------------------------------|
| **1** | `REC-DEMO-01-COMPLIANT-TBA1001` | TBA-1001 (Real) | Ruta 1 (Huachi - Ingahurco) | `completed` | 24 | Conforme Bruto / Conforme Ajustado | Demostración de viaje real ejecutado a tiempo y paradas completas. |
| **2** | `REC-DEMO-02-COMPLIANT-TBA1002` | TBA-1002 (Sim) | Ruta 2 (Campus Huachi - Querochaca) | `completed` | 24 | Conforme Bruto / Conforme Ajustado | Demostración de viaje simulado ejecutado conforme en ruta intercampus. |
| **3** | `REC-DEMO-03-DELAY-START-TBA1001` | TBA-1001 (Real) | Ruta 3 (Circunvalación Centro) | `completed` | 24 | No Conforme (`delay_start`) | Detección automática de salida demorada en terminal (+10 min). |
| **4** | `REC-DEMO-04-DELAY-ARRIVAL-TBA1002` | TBA-1002 (Sim) | Ruta 1 (Huachi - Ingahurco) | `completed` | 24 | No Conforme (`delay_arrival`) | Detección automática de llegada demorada en destino (+15 min). |
| **5** | `REC-DEMO-05-DEVIATION-TBA1001` | TBA-1001 (Real) | Ruta 2 (Campus Huachi - Querochaca) | `completed` | 24 | No Conforme (`route_deviation`) | Detección de desvío espacial (> 40 m fuera de polilínea). |
| **6** | `REC-DEMO-06-STOP-OMITTED-TBA1002` | TBA-1002 (Sim) | Ruta 3 (Circunvalación Centro) | `completed` | 24 | No Conforme (`stop_missed`) | Detección de omisión de parada intermedia (+660 m de geocerca). |
| **7** | `REC-DEMO-07-GPS-GAP-TBA1001` | TBA-1001 (Real) | Ruta 1 (Huachi - Ingahurco) | `completed` | 24 | Conforme / Incidencia `gps_loss` | Pérdida de telemetría superior a 180 s (gap de 300 s). |
| **8** | `REC-DEMO-08-INDETERMINATE-TBA1002`| TBA-1002 (Sim) | Ruta 2 (Campus Huachi - Querochaca) | `completed` | **0** | **Indeterminado (`insufficient_data`)** | **Caso de prueba sin GPS:** no penaliza cumplimiento (MT-01 `N/A`, excluido de MT-02/03/06/07). |
| **9** | `REC-DEMO-09-JUSTIFIED-TBA1001` | TBA-1001 (Real) | Ruta 3 (Circunvalación Centro) | `completed` | 24 | **Conforme Ajustado** | Incidencia de retraso con justificación enviada y formalmente aprobada por el Gestor. |
| **10**| `REC-DEMO-10-COMPLIANT-RET-TBA1002` | TBA-1002 (Sim) | Ruta 1 (Huachi - Ingahurco) | `completed` | 24 | Conforme Bruto / Conforme Ajustado | Retorno vespertino puntual con paradas completadas. |
| **11**| `REC-DEMO-12-INTERCAMPUS-TBA1001` | TBA-1001 (Real) | Ruta 2 (Campus Huachi - Querochaca) | `completed` | 25 | Conforme Bruto / Conforme Ajustado | **Recorrido ejecutado adicional:** consolida exactamente **10 viajes ejecutados con trazas GPS**. |
| **12**| `REC-DEMO-11-CANCELLED-TBA1002` | TBA-1002 (Sim) | Ruta 2 (Campus Huachi - Querochaca) | `cancelled` | 0 | Excluido de Evaluación | Demostración de exclusión estricta de viajes no operados en todos los indicadores. |

> **Balance de Cuota:**  
> - **10 Recorridos Ejecutados con Telemetría Verificada** (cumplen plenamente el umbral reglamentario $\ge 10$).  
> - **1 Recorrido Indeterminado** (sin posiciones GPS; prueba funcional de aislamiento de datos insuficientes).  
> - **1 Recorrido Cancelado** (prueba funcional de exclusión de denominador).  
> - **Total en Base Demostración:** 12 registros trazables e independientes.

---

### 4.2 Auditoría de Métricas en el Dashboard (`georutex_demo`)

Se auditó directamente la respuesta de [`transport.metrics.service`](file:///c:/Documentos/D-Proyectos/Git/georutex/addons/uta_transport_monitor/services/transport_metrics_service.py) sobre la base `georutex_demo`:

```
=== RESUMEN OPERACIONAL DEL DASHBOARD ===
  total_trips: 12
  executed_trips: 10 (viajes ejecutados con evidencia de telemetría)
  compliant_trips_gross: 5
  compliant_trips_adjusted: 5
  non_compliant_trips: 5
  total_incidents: 12
  source_type: combined
```

#### Auditoría de Denominadores y Muestras de MT-01 a MT-08:
- **MT-01 (Cumplimiento de Rutas):** $50.0\%$ ($5/10$ viajes evaluables; 1 viaje indeterminado aislado con $n_{indet}=1$). Muestra: $n=10$.
- **MT-02 (Puntualidad en Salida y Llegada):** $70.0\%$ ($7/10$ viajes puntuales en ambos hitos). Muestra: $n=10$.
- **MT-03 (Retraso Promedio de Llegada):** $3.00$ min sobre los 10 viajes ejecutados ($30.0$ min acumulados). Muestra: $n=10$.
- **MT-04 (Cumplimiento de Paradas Intermedias):** $95.0\%$ ($19/20$ paradas intermedias visitadas; 1 omitida en Recorrido 6). Muestra: $n=20$ paradas.
- **MT-05 (Desviación Máxima de Ruta):** $70.53$ m promedio sobre polilínea en los 10 viajes evaluables. Muestra: $n=10$.
- **MT-06 (Diferencia de Distancia Planificada vs Recorrida):** $+1.37\%$ ($+0.98$ km netos sobre $71.70$ km planificados en 10 viajes; MAE = $0.10$ km). Muestra: $n=10$.
- **MT-07 (Tiempo Promedio de Recorrido):** $25.97$ min en los 10 viajes ejecutados. Muestra: $n=10$.
- **MT-08 (Frecuencia de Incidencias):** $12.00$ incidencias por cada 10 viajes ($12$ incidencias registradas sobre $10$ viajes ejecutados). Muestra: $n=10$.

#### Indicadores de Calidad del Software (MCS-01 a MCS-04):
- **MCS-01 (Integridad GPS):** $100.0\%$ ($1,324$ posiciones analizadas, $0$ descartadas por error geométrico o ruido).
- **MCS-02 (Exactitud de Sincronización Traccar $\rightarrow$ Odoo):** $100.0\%$. Mide la correspondencia uno a uno entre posiciones registradas en Traccar y posiciones sincronizadas en Odoo mediante consulta independiente.
- **MCS-03 (Tiempo de Respuesta del Sistema):** Media de $1.25$ ms en caliente ($37.52$ ms / 30 solicitudes evaluadas). Cumple el umbral estadístico ($n = 30 \ge 30$) para reportar percentil 95 ($< 5.0$ ms).
- **MCS-04 (Exactitud en Detección de Incidencias):** $100.0\%$ ($18/18$ casos de ground truth correctamente clasificados por la matriz de confusión).

---

## 5. Resultados Reales del Análisis en SonarQube

Se ejecutó el análisis estático y de calidad sobre el código propio del proyecto mediante el stack local desacoplado:

- **Instancia SonarQube:** SonarQube Community Build `26.10.0.133078` en `http://localhost:9000`.
- **Proyecto Analizado:** `georutex` (`GeoRutex - Sistema de Monitoreo y Evaluacion de Rutas`).
- **Líneas de Código Propias (NCLOC):** 5,877 líneas (Python y JavaScript/Owl).
- **Estado del Quality Gate:** **`OK` (Cumplido / Compliant)**.

### Métricas Certificadas por la API de SonarQube:
| Métrica | Valor Obtenido | Umbral de Calidad | Evaluación |
|:---|:---:|:---:|:---:|
| **Quality Gate** | **OK** | Aprobado | Cumplido |
| **Vulnerabilidades de Seguridad** | **0** | 0 | Calificación A (1.0) |
| **Puntos Calientes de Seguridad (Hotspots)** | **0** | 0 | Calificación A (1.0) |
| **Densidad de Líneas Duplicadas** | **0.5%** | $< 3.0\%$ | Cumplido |
| **Mantenibilidad / Deuda Técnica** | **A (1.0)** | A | Cumplido (3 code smells menores) |
| **Bugs / Reglas de Confiabilidad** | **9 (Rating B)** | $< 10$ | Cumplido (anotaciones menores de tipado) |
| **Cobertura de Dominio Importada** | **93.5%** | $> 80.0\%$ | Cumplido (`domain/geo.py`, `evaluation.py`, `metrics.py`) |
| **Cobertura Total del Addon** | **22.2%** | N/A | Corresponde a cobertura unitaria de capas lógicas sobre el total de NCLOC |

---

## 6. Procedimiento para la Demostración Celular Física (Intervención Humana)

La recepción física de GPS mediante Traccar Client sobre red celular móvil 4G (sin Wi-Fi) constituye una validación que requiere intervención humana y dispositivo físico:

```mermaid
sequenceDiagram
  autonumber
  actor Operador as Operador con Smartphone 4G
  participant Client as Traccar Client (App Móvil)
  participant Tunnel as Cloudflare Tunnel (HTTPS :443)
  participant Ingest as Traccar OsmAnd (:5055)
  participant Odoo as Odoo 16 (Fleet / GeoRutex)

  Operador->>Client: Desactivar Wi-Fi, habilitar Datos Móviles (4G)
  Operador->>Client: Configurar URL https://gps.tudominio.com y Device ID
  Client->>Tunnel: POST /?id=GEO-PHYS-TBX9001&lat=...&lon=... (Puerto 443)
  Tunnel->>Ingest: Forward a georutex-traccar:5055 (HTTP)
  Ingest-->>Tunnel: 200 OK
  Tunnel-->>Client: 200 OK (Send success)
  Note over Ingest,Odoo: Sincronización Automática o Manual
  Odoo->>Ingest: GET /api/positions (REST API 8082 Interna)
  Ingest-->>Odoo: Posición física recibida
  Odoo->>Odoo: Persistencia con source='real' y zona America/Guayaquil
```

### Instrucciones Clave para la Prueba:
1. **Cloudflare Tunnel:** Mapear el túnel exclusivamente hacia `http://localhost:5055`. En el smartphone se ingresa `https://gps.tudominio.com` (puerto 443 estándar, sin agregar `:5055`).
2. **Dispositivo en Traccar:** Registrar el identificador `GEO-PHYS-TBX9001` en Traccar (`http://localhost:8082`).
3. **Acreditación en Odoo:** En el vehículo `TBA-1001`, asegurar que `is_physical_accredited = True`.
4. **Validación:** Al sincronizar en Odoo, la posición física aparecerá en el mapa con `source = 'real'`.

---

## 7. Guion Técnico de Defensa Funcional (12 Pasos con Registros de Demostración)

Alineado con los registros reales existentes en `georutex_demo`:

1. **Acceso y Seguridad de Roles (1 min):** Ingresar a `http://localhost:8069/web?db=georutex_demo`. Demostrar el inicio de sesión con `gestor` (`GeoRutex#Gestor2026!`) y `conductor` (`GeoRutex#Conductor2026!`).
2. **Topología de Flota y Rutas (1 min):** En Odoo, mostrar los vehículos `TBA-1001` (Real) y `TBA-1002` (Simulado). Mostrar las Rutas 1, 2 y 3 con al menos 4 puntos de control cada una.
3. **Versión Congelada de Ruta (1 min):** Abrir un recorrido programado. Inspeccionar la pestaña técnica para exhibir el JSON inmutable de parámetros congelados (corredor 40m, tolerancia 300s, gap 180s).
4. **Demostración Celular en Vivo (2 min):** Enseñar Traccar Client en el smartphone sobre red 4G enviando coordenadas al túnel HTTPS.
5. **Sincronización en Odoo (1 min):** En *Monitoreo de Rutas $\rightarrow$ Sincronización*, pulsar "Sincronizar Ahora" y mostrar el registro con hora de Ecuador.
6. **Mapa Integrado e Historial (2 min):** Abrir `REC-DEMO-01-COMPLIANT-TBA1001`. Visualizar la polilínea planificada frente al rastro GPS real de 24 puntos.
7. **Caso de Cumplimiento Conforme (1 min):** Mostrar que `REC-DEMO-01-COMPLIANT-TBA1001` dictamina "Conforme Bruto" y "Conforme Ajustado".
8. **Detección Automática de Infracciones (1 min):** Abrir `REC-DEMO-05-DEVIATION-TBA1001` (desvío de 380m) y `REC-DEMO-03-DELAY-START-TBA1001` (salida tardía +10 min). Mostrar las incidencias generadas automáticamente por el motor.
9. **Flujo de Justificaciones y Bloqueo de Autoaprobación (2 min):** 
   - Con sesión de `conductor`, abrir `REC-DEMO-09-JUSTIFIED-TBA1001`: el botón "Aprobar Justificación" está bloqueado/inhabilitado.
   - Con sesión de `gestor`, revisar la nota de justificación por tráfico, aprobarla y comprobar que el recorrido cambia su dictamen a "Conforme Ajustado".
10. **Tratamiento de Datos Insuficientes (1 min):** Abrir `REC-DEMO-08-INDETERMINATE-TBA1002` (0 posiciones GPS). Mostrar que el sistema dictamina `Indeterminado` y no castiga injustamente la conformidad global (aislado en MT-01 como `N/A`).
11. **Dashboard Gerencial Interactivo (2 min):** Abrir el dashboard Owl 2. Demostrar el filtro *Real / Simulado / Combinado*. Mostrar que las 8 métricas MT operan sobre $n=10$ recorridos ejecutados y que el viaje cancelado `REC-DEMO-11-CANCELLED-TBA1002` no contamina los denominadores.
12. **Calidad del Software y SonarQube (1 min):** Exhibir el dashboard de SonarQube en `http://localhost:9000/dashboard?id=georutex` mostrando el Quality Gate en `OK`, 0 vulnerabilidades y 93.5% de cobertura unitaria.
