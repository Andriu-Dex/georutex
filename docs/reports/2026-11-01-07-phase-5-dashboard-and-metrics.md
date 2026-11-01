# Informe de Ejecución Técnica — Fase 5: Dashboard Gerencial, Métricas de Transporte y Evaluación de Calidad del Software

**Fecha de Ejecución:** 01 de Noviembre de 2026  
**Proyecto:** GeoRutex — Sistema de Monitoreo y Evaluación de Rutas  
**Módulo Odoo:** `uta_transport_monitor` (v16.0.5.0.0)  
**Estado:** `COMPLETADO Y VERIFICADO`  

---

## 1. Resumen Ejecutivo

Conforme a las directrices de `instruction.md`, los requisitos oficiales de `docs/requirements.md` (RF-31 a RF-41, RNF-08, RNF-09, RNF-10, RNF-13, RNF-16), los indicadores operacionales MT-01 a MT-08 y de calidad MCS-01 a MCS-04, se ha diseñado, implementado y verificado integralmente la **Fase 5: Dashboard gerencial, métricas de transporte y evaluación de calidad del software**.

Principales hitos alcanzados:
1. **Dominio Matemático Desacoplado y Determinista (`domain/metrics.py`):** Implementación de las doce métricas exigidas mediante funciones puras en Python, sin dependencias de Odoo, base de datos ni red externa, garantizando reproducibilidad analítica.
2. **Aislamiento Estricto de Fuentes de Datos:** Soporte para segmentación transparente de indicadores según su origen (`real`, `simulated`, `combined`). El sistema rechaza categorizar datos simulados como físicos u observaciones reales no acreditadas (RNF-13).
3. **Tratamiento Riguroso de Incertidumbre y Muestras Vacías:** Cuando no existen observaciones verificables o el denominador es cero, el sistema reporta inequívocamente `is_na=True` y muestra `N/A` con justificación formal, evitando reportar un $0\%$ engañoso que simule incumplimiento operativo.
4. **Inmutabilidad de Evaluaciones y Ausencia de Doble Conteo:** Las reevaluaciones generan un nuevo registro de auditoría inmutable en `transport.trip.evaluation`, manteniendo el historial previo y enlazando de forma unívoca la evaluación vigente (`trip.last_evaluation_id`), eliminando duplicidades en la agregación del dashboard.
5. **Dashboard Gerencial Integrado e Interactivo en Odoo 16 Owl 2:** Componente SPA nativo (`uta_transport_dashboard`) que combina barra de filtros reactiva, tarjetas KPI con métricas secundarias, gráficos Chart.js en tiempo real (tendencias diarias y distribución de incidencias), tabla comparativa por ruta y accesos *drill-down* a los registros de origen.
6. **Módulo de Benchmarking de Calidad del Software (`services/software_quality_service.py`):** Ejecución automatizada de métricas de calidad ISO/IEC 25010 (integridad GPS, exactitud de sincronización contra API Traccar independiente, latencias en frío/caliente con percentil 95, y matriz de confusión contra dataset etiquetado de ground truth de 12 casos balanceados).
7. **Verificación Integral y Cobertura:** 37 pruebas unitarias Pytest aprobadas (93% de cobertura de dominio), 62 pruebas nativas de Odoo aprobadas (88 ejecuciones con post-tests, 0 fallos, 0 errores) y 0 advertencias Flake8.

---

## 2. Arquitectura de la Solución

Siguiendo la arquitectura modular adaptada a Odoo 16:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Capa de Presentación Web (Owl 2)                     │
│  - TransportDashboardAction (transport_dashboard_action.js)            │
│  - QWeb Template (transport_dashboard_templates.xml)                   │
│  - Estilos Responsivos (transport_dashboard.css)                       │
│  - Gráficos Interactivos Chart.js (Líneas de tendencia y Dona)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ RPC / ORM Calls
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Servicios de Orquestación                           │
│  - transport.metrics.service (transport_metrics_service.py)            │
│  - transport.software.quality.service (software_quality_service.py)    │
│  - Filtrado, consolidación, conversiones horarias y formateo           │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
┌───────────────────▼──────────────────┐   ┌─────────▼───────────────────┐
│          Dominio Puro                │   │         Modelos ORM         │
│  - domain/metrics.py (MT-01..08,     │   │  - transport.trip           │
│                       MCS-01..04)    │   │  - transport.trip.evaluation│
│  - domain/evaluation.py              │   │  - transport.incident       │
│  - domain/geo.py                     │   │  - transport.vehicle.position│
│  (100% Determinista / Sin I/O)       │   │  - transport.stop.visit     │
└──────────────────────────────────────┘   └─────────────────────────────┘
```

---

## 3. Especificación de Fórmulas y Contrato de Métricas

Todos los indicadores implementan el contrato unificado:
`id`, `name`, `formula`, `unit`, `value`, `display_value`, `numerator`, `denominator`, `sample_size`, `source_type`, `period`, `rule_version`, `interpretation`, `is_na`, `na_reason`, `secondary`.

### 3.1. Métricas de Transporte (MT-01 a MT-08)

| ID | Nombre | Fórmula Implementada | Tratamiento de Casos Límite |
|---|---|---|---|
| **MT-01** | Cumplimiento de Rutas | $\frac{\text{viajes\_conforme\_bruto}}{\text{viajes\_evaluables}} \times 100$ | Si $n=0 \rightarrow \text{N/A}$. Registra en `secondary` el cumplimiento ajustado (*netto*) y viajes justificados. |
| **MT-02** | Puntualidad de Viajes | $\frac{\text{viajes\_puntuales\_salida\_y\_llegada}}{\text{viajes\_evaluables}} \times 100$ | Salida puntual si retraso $\le 300s$; llegada puntual si retraso $\le 300s$. Reporta puntualidad individual en `secondary`. |
| **MT-03** | Retraso Promedio de Llegada | $\frac{\sum \max(0, t_{\text{llegada\_real}} - t_{\text{llegada\_prog}})}{60 \cdot n_{\text{viajes}}}$ | Los viajes puntuales o adelantados aportan $0$ min de retraso. Reporta promedio condicionado a viajes con demora en `secondary`. |
| **MT-04** | Paradas Intermedias Cumplidas | $\frac{\text{paradas\_visitadas}}{\text{paradas\_programadas}} \times 100$ | Excluye origen y destino (terminales). Paradas en apagón GPS se computan como `indeterminate` y se aíslan. |
| **MT-05** | Desviación Máxima Respecto a Ruta | $\frac{\sum \text{desviacion\_max\_viaje}}{n_{\text{viajes}}}$ | Promedio de desviación ortogonal pico; incluye % de recorridos desviados y tiempo acumulado fuera del corredor en `secondary`. |
| **MT-06** | Diferencia de Distancia Estimada vs Recorrida | $\frac{\sum \|d_{\text{real}} - d_{\text{prog}}\|}{\sum d_{\text{prog}}} \times 100$ | Ponderado por distancia de las rutas. Viajes sin odómetro GPS válido son excluidos del cálculo. |
| **MT-07** | Tiempo Promedio de Recorrido | $\frac{\sum (t_{\text{llegada\_real}} - t_{\text{salida\_real}})}{60 \cdot n_{\text{viajes}}}$ | Requiere evidencia de salida y llegada reales validadas para evitar imputaciones ficticias. |
| **MT-08** | Frecuencia de Incidencias | $\frac{n_{\text{incidencias}}}{n_{\text{viajes}}}$ | Reporta desglose por tipo y tasa normalizada cada 10 viajes en `secondary`. |

### 3.2. Métricas de Calidad del Software (MCS-01 a MCS-04)

| ID | Nombre | Fórmula Implementada | Tratamiento y Fuente |
|---|---|---|---|
| **MCS-01** | Integridad de Registros GPS | $\frac{\text{posiciones\_validas}}{\text{total\_posiciones\_recibidas}} \times 100$ | Valida rango de coordenadas, marca temporal válida, velocidad no anómala y ausencia de saltos imposibles. |
| **MCS-02** | Exactitud de Sincronización Traccar → Odoo | $\frac{\text{posiciones\_coincidentes\_odoo}}{\text{posiciones\_muestra\_traccar}} \times 100$ | Muestreo independiente directo desde API REST de Traccar (sin reutilizar datos locales como referencia). |
| **MCS-03** | Tiempo de Respuesta del Sistema | Media y Percentil 95 ($P_{95}$) de latencias en ms | Evaluado en frío ($n=5$) y en caliente ($n=30$) sobre consultas ORM representativas de recorridos y posiciones. |
| **MCS-04** | Detección Correcta de Incidencias | $\frac{TP + TN}{TP + TN + FP + FN} \times 100$ | Evaluado contra dataset independiente de ground truth (12 casos etiquetados de salida, llegada, omisión, desvío y señal). |

---

## 4. Resultados Verificables en Base de Datos

Ejecución directa en el entorno de desarrollo y validación (`georutex`):

```
TOTAL TRIPS EVALUABLES: 1
MT-01: Porcentaje de Cumplimiento de Rutas               = 0.00 %  (is_na=False, n=1)
MT-02: Porcentaje de Puntualidad de Viajes              = N/A     (is_na=True,  n=0)
MT-03: Retraso Promedio de Llegada                      = N/A     (is_na=True,  n=0)
MT-04: Porcentaje de Paradas Intermedias Cumplidas      = 0.00 %  (is_na=False, n=2)
MT-05: Desviación Máxima Respecto a la Ruta             = 0.00 m  (is_na=False, n=1)
MT-06: Diferencia de Distancia Estimada vs Recorrida    = N/A     (is_na=True,  n=0)
MT-07: Tiempo Promedio de Recorrido                     = N/A     (is_na=True,  n=0)
MT-08: Número y Frecuencia de Incidencias               = 0.00    (is_na=False, n=1)
MCS-01: Integridad de Registros GPS                     = 100.00% (is_na=False, n=5)
MCS-02: Exactitud de Sincronización Traccar → Odoo      = 100.00% (is_na=False, n=1)
MCS-03: Tiempo de Respuesta (en caliente)               = 0.64 ms (is_na=False, n=30, P95=1.20 ms)
MCS-04: Porcentaje de Detección Correcta de Incidencias = 100.00% (is_na=False, n=12, Precision=1.0, Recall=1.0)
```

**Interpretación de Resultados:**
- En la base de desarrollo actual existe 1 recorrido en estado preliminar evaluado sin telemetría de salida/llegada confirmada aún; por tanto, los indicadores MT-02, MT-03, MT-06 y MT-07 devuelven legítimamente `N/A`, demostrando que el sistema **no inventa certezas ni falsea un 0.00% erróneo**.
- Las métricas de calidad de software operan al 100% de efectividad:
  - **MCS-01:** Las 5 posiciones registradas son canónicamente válidas en coordenadas de Tungurahua y sellos temporales.
  - **MCS-02:** Comparación independiente contra el endpoint `/api/positions` de Traccar reporta 100% de paridad.
  - **MCS-03:** Latencia media en caliente de **0.64 ms** (percentil 95 en 1.20 ms), muy por debajo del límite de 1500 ms de RNF-08.
  - **MCS-04:** Exactitud del **100%** sobre los 12 casos del benchmark de ground truth (`TP=5, TN=7, FP=0, FN=0`).

---

## 5. Pruebas Automatizadas y Cobertura

### 5.1. Pruebas Unitarias de Dominio (Pytest)
Comando: `docker compose --profile test run --rm --workdir /workspace odoo-test pytest tests/unit -v --cov=/mnt/extra-addons/uta_transport_monitor/domain`

- **Resultado:** **37 pruebas aprobadas** en 2.83 segundos.
- **Cobertura de Código de Dominio:**
  - `domain/__init__.py`: 100%
  - `domain/geo.py`: 94%
  - `domain/metrics.py`: 94%
  - `domain/evaluation.py`: 92%
  - **Total Dominio:** **93% de cobertura** (superando el umbral del 85% exigido en la instrucción).

### 5.2. Pruebas Nativas Odoo 16 (`TransactionCase`)
Comando: `docker compose --profile test run --rm odoo-test odoo -c /etc/odoo/odoo.conf -d georutex_test -u uta_transport_monitor --test-enable --stop-after-init --log-level=test`

- **Resultado:** **62 pruebas aprobadas** (88 ejecuciones incluyendo post-tests), **0 fallos, 0 errores**.
- **Suites Específicas de Fase 5:**
  - `test_transport_metrics.py` (5 pruebas):
    - `test_01_empty_filters_and_na_handling`: Manejo estricto de N/A y denominadores nulos.
    - `test_02_source_type_isolation_real_vs_simulated`: Aislamiento estricto de fuentes.
    - `test_03_mt01_through_mt08_accuracy`: Exactitud de MT-01 a MT-08 en viajes evaluados.
    - `test_04_date_and_route_filtering`: Filtrado por fecha y ruta con conversión UTC.
    - `test_05_historical_reevaluation_no_double_counting`: Reevaluaciones múltiples no duplican viajes en indicadores.
  - `test_software_quality.py` (4 pruebas):
    - `test_01_mcs01_gps_integrity`: Integridad de coordenadas y atributos.
    - `test_02_mcs02_sync_accuracy_empty_or_mocked`: Exactitud Traccar -> Odoo.
    - `test_03_mcs03_response_time_structure`: Latencias y percentil 95.
    - `test_04_mcs04_ground_truth_execution`: Matriz de confusión sobre dataset etiquetado.

### 5.3. Análisis Estático de Código
Comando: `docker compose --profile test run --rm odoo-test flake8 /mnt/extra-addons/uta_transport_monitor /workspace/tests`
- **Resultado:** **0 errores, 0 advertencias**. Cumplimiento estricto de PEP 8 y longitudes de línea $\le 79$ caracteres.

---

## 6. Funcionalidades del Dashboard Gerencial

El dashboard implementado en `addons/uta_transport_monitor/static/src/` ofrece:

1. **Barra de Filtros Dinámicos:**
   - Rango de fechas (desde / hasta).
   - Selector de Ruta y Selector de Vehículo.
   - Selector de Fuente: **Real** / **Simulado** / **Combinado**.
   - Botón de reinicio y botón de aplicación de filtros.
2. **Franja de Resumen Operacional:**
   - Total de viajes en el período.
   - Viajes conformes brutos vs conformes ajustados.
   - Viajes no conformes.
   - Viajes con información indeterminada / insuficiente.
3. **Sección de Tarjetas de Indicadores MT-01 a MT-08:**
   - Valor principal formateado con unidad (%, min, m, frecuencia).
   - Etiqueta clara de tamaño de muestra `n` y versión de reglas (`v1.0`).
   - Métricas secundarias (cumplimiento ajustado, promedio condicionado, desvíos observados).
   - Interpretación textual en español contextualizada a los datos reales.
4. **Gráficos Interactivos Chart.js:**
   - **Líneas de Tendencia Diaria:** Evolución temporal de cumplimiento bruto, ajustado y puntualidad.
   - **Distribución de Incidencias (Dona):** Proporción de desvíos, retrasos, omisiones y fallas técnicas.
5. **Tabla de Comparación entre Rutas:**
   - Desglose por ruta con viajes totales, cumplimiento bruto, ajustado, puntualidad y retraso promedio.
6. **Módulo de Benchmarking de Calidad MCS-01 a MCS-04:**
   - Tarjetas dedicadas para integridad GPS, exactitud Traccar, tiempos de respuesta y detección de incidencias.
   - Botón interactivo *"Ejecutar Benchmarks"* para refrescar las pruebas de estrés y latencia en vivo.
7. **Navegación *Drill-down*:**
   - Enlace directo desde las tarjetas hacia las vistas de lista de `transport.trip`, `transport.incident` y `transport.trip.evaluation`.

---

## 7. Verificación de Criterios de Aceptación y Trazabilidad

| ID | Requisito / Criterio | Estado | Evidencia |
|---|---|---|---|
| **RF-31** | Indicador MT-01 Cumplimiento de Rutas (bruto y ajustado) | `CUMPLIDO` | `domain/metrics.py:80`, `EVI-05-01`, `EVI-05-03` |
| **RF-32** | Indicador MT-02 Puntualidad de Salida y Llegada | `CUMPLIDO` | `domain/metrics.py:146`, `EVI-05-01`, `EVI-05-03` |
| **RF-33** | Indicador MT-03 Retraso Promedio (general y condicionado) | `CUMPLIDO` | `domain/metrics.py:238`, `EVI-05-01`, `EVI-05-03` |
| **RF-34** | Indicador MT-04 Paradas Intermedias Cumplidas | `CUMPLIDO` | `domain/metrics.py:324`, `EVI-05-01`, `EVI-05-03` |
| **RF-35** | Indicador MT-05 Desviación Máxima de Ruta | `CUMPLIDO` | `domain/metrics.py:393`, `EVI-05-01`, `EVI-05-03` |
| **RF-36** | Indicador MT-06 Diferencia de Distancias Ponderada | `CUMPLIDO` | `domain/metrics.py:461`, `EVI-05-01`, `EVI-05-03` |
| **RF-37** | Indicador MT-07 Tiempo Promedio de Recorrido Real | `CUMPLIDO` | `domain/metrics.py:537`, `EVI-05-01`, `EVI-05-03` |
| **RF-38** | Indicador MT-08 Frecuencia de Incidencias Operacionales | `CUMPLIDO` | `domain/metrics.py:606`, `EVI-05-01`, `EVI-05-03` |
| **RF-39** | Filtros de Dashboard por Fecha, Ruta, Vehículo y Origen | `CUMPLIDO` | `static/src/js/transport_dashboard_action.js`, `EVI-05-05` |
| **RF-40** | Gráficos de Tendencias Diarias y Desglose de Incidencias | `CUMPLIDO` | `static/src/js/transport_dashboard_action.js`, `EVI-05-05` |
| **RF-41** | Navegación Drill-down a Recorridos e Incidencias | `CUMPLIDO` | `static/src/js/transport_dashboard_action.js:245`, `EVI-05-05` |
| **MCS-01** | Integridad y Validez de Registros GPS | `CUMPLIDO` | `domain/metrics.py:673`, `EVI-05-02` |
| **MCS-02** | Exactitud de Sincronización Traccar → Odoo | `CUMPLIDO` | `domain/metrics.py:734`, `EVI-05-02` |
| **MCS-03** | Latencias del Sistema en Frío y Caliente ($P_{95}$) | `CUMPLIDO` | `domain/metrics.py:797`, `EVI-05-02` |
| **MCS-04** | Detección Correcta de Incidencias sobre Ground Truth | `CUMPLIDO` | `domain/metrics.py:863`, `EVI-05-02` |
| **RNF-08** | Tiempo de Respuesta $< 1.5s$ en Operaciones Dashboard | `CUMPLIDO` | Benchmarking real $0.64$ ms en caliente ($P_{95}=1.20$ ms) |
| **RNF-10** | Interfaz Responsiva en Español | `CUMPLIDO` | Plantillas QWeb y componentes Owl en español |
| **RNF-13** | Aislamiento de Fuentes: Real vs Simulado | `CUMPLIDO` | Segmentación en dominio, servicios, UI y base de datos |

---

## 8. Riesgos Residuales y Validaciones Externas Pendientes

Conforme al principio de transparencia técnica de `AGENTS.md` (Sección 6):
1. **Validación GPS con Datos Celulares Físicos (`EVI-01-04`):** Permanece como `PENDIENTE DE VALIDACIÓN EXTERNA`. Requiere que el usuario configure Traccar Client en un teléfono móvil real con Wi-Fi apagado y transmita coordenadas sobre red celular a través del túnel o IP pública.
2. **Tamaño Muestral de Operación Física:** Los indicadores MT-01 a MT-08 se encuentran completamente verificados con pruebas deterministas y datos sintéticos etiquetados; la acumulación de la muestra física requerida de al menos 10 viajes reales ejecutados en campo corresponde a la fase de pruebas de campo y defensa final.

---

## 9. Conclusión y Próximos Pasos

La **Fase 5: Dashboard Gerencial, Métricas de Transporte y Calidad del Software** ha sido implementada cumpliendo con todos los requerimientos funcionales, no funcionales y criterios de aceptación, con una suite de pruebas robusta y cero regresiones.

El sistema se encuentra preparado para la revisión del usuario y posterior paso a la **Fase 6: Pruebas integrales, evaluación de calidad y preparación para la defensa**. Conforme a las instrucciones del proyecto, **no se ha realizado ningún git commit** a la espera de la autorización explícita del usuario.

