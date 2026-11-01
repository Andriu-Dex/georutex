# Catálogo de Evidencias — GeoRutex

> **Nota de confidencialidad y control:**
> Este índice saneado es el **único archivo** del directorio `evidence/` versionado en el repositorio Git.
> Conforme a `AGENTS.md` (Sección 4, 6 y 7) y `docs/requirements.md` (Sección 12.3), las trazas GPS directas, capturas sin anonimizar, credenciales de entorno y registros brutos se consideran **privados por defecto** y deben resguardarse en almacenamiento local seguro o entregarse mediante canales privados autorizados.

| ID Evidencia | Fecha | Tipo | Requisito / Control | Estado | Canal / Ubicación Privada | Descripción Saneada |
|---|---|---|---|---|---|---|
| `EVI-00-01` | 2026-11-01 | Inspección de entorno | RNF-11, RNF-14 | `COMPLETADO` | Local / Log de inspección | Verificación de herramientas host: Windows, Docker 29.2.1, Compose v5.0.2, detección de puerto 5432 ocupado y mapeo seguro a puerto 5433. |
| `EVI-00-02` | 2026-11-01 | Test de humo | RNF-08, RNF-11 | `COMPLETADO` | Contenedor Odoo 16 / Pytest | Verificación de importación canónica `from odoo.addons.uta_transport_monitor.domain import geo` con `addons_path` registrado. |
| `EVI-00-03` | 2026-11-01 | Análisis de conector | RNF-01, RNF-02 | `COMPLETADO` | Documento de análisis Fase 0 | Evaluación técnica de conectores existentes (traccar-odoo v19) y justificación de adaptador desacoplado en Odoo 16. |

