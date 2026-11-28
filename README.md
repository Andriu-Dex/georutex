# GeoRutex — Sistema de Monitoreo y Evaluación de Rutas

Plataforma para programar recorridos de una flota, recibir su posición GPS desde el teléfono del conductor (Traccar Client) y evaluar automáticamente puntualidad, paradas, desvíos y pérdidas de señal, con indicadores y panel de análisis.

**Componentes:** Odoo 16 Community + Fleet (aplicación, módulo `uta_transport_monitor`), PostgreSQL 15 (base de datos de Odoo), Traccar 6.5 (receptor GPS) y Docker Compose.

```
Teléfono (Traccar Client) ──HTTPS──► túnel/proxy ──► Traccar :5055 ──API :8082 (interna)──► Odoo :8069 ──► PostgreSQL
Navegador ─────────────────HTTPS──► túnel/proxy ──────────────────────────────────────────► Odoo :8069
```

---

## 1. Requisitos

- Docker Desktop (Windows/macOS) o Docker Engine + Compose v2 (Linux).
- Git.
- Para publicar en internet sin coste: [Tailscale](https://tailscale.com) (Funnel), cuenta gratuita.
- Teléfono con [Traccar Client](https://www.traccar.org/client/) (Android/iOS).

## 2. Configuración (`.env`)

```bash
cp .env.example .env
```

Completar como mínimo (nunca subir `.env` a Git):

| Variable | Descripción |
|---|---|
| `POSTGRES_PASSWORD` | Contraseña de la base de datos. |
| `ODOO_ADMIN_PASSWORD` | Contraseña inicial del usuario administrador de Odoo. |
| `ODOO_BIND_ADDRESS` | `127.0.0.1` si se publica con túnel/proxy; `0.0.0.0` solo en desarrollo. |
| `TRACCAR_API_USERNAME` / `TRACCAR_API_PASSWORD` | Usuario administrador de Traccar (lo usa Odoo para leer posiciones y registrar dispositivos). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Correo saliente (invitaciones y recuperación de contraseña). Con Gmail usar una *clave de aplicación*. |
| `GRX_DOMAIN`, `GPS_DOMAIN` | Solo para el despliegue con Caddy en un servidor (sección 4.3). |

Los umbrales de evaluación (radio de parada, tolerancia de retraso, corredor, etc.) **no** van en `.env`: se configuran en cada ruta dentro de la aplicación.

## 3. Levantar en local (desarrollo)

```bash
docker compose up -d
docker compose ps          # odoo debe quedar "healthy" (la primera vez tarda 1–3 min)
```

- Aplicación: <http://localhost:8069/georutex/acceso>
- Usuario inicial: el administrador definido en la base (contraseña = `ODOO_ADMIN_PASSWORD`).

El contenedor de Odoo crea la base `georutex` en español (Ecuador) la primera vez e instala/actualiza el módulo automáticamente cuando cambia su versión.

## 4. Publicar en internet

### 4.1 Opción gratuita vigente: Tailscale Funnel (desde una PC)

1. Instalar Tailscale, iniciar sesión y activar **HTTPS** y **Funnel** en el panel de administración.
2. En `.env`: `ODOO_BIND_ADDRESS=127.0.0.1`.
3. Levantar en modo túnel (Odoo con `--proxy-mode` y sin gestor de bases de datos):

   ```bash
   docker compose -f compose.yaml -f compose.tunnel.yaml up -d
   ```

4. Publicar:

   ```powershell
   tailscale funnel --bg 8069                 # https://<equipo>.<tailnet>.ts.net        -> Odoo
   tailscale funnel --bg --https=8443 5055    # https://<equipo>.<tailnet>.ts.net:8443   -> receptor GPS
   tailscale funnel status
   ```

5. En Odoo, como administrador: *Ajustes → Técnico → Parámetros del sistema* → `web.base.url` = URL pública (y `web.base.url.freeze` = `True`) para que los enlaces de los correos sean correctos.

Limitación: el sistema está disponible solo mientras la PC esté encendida, sin suspensión y con Docker abierto.

### 4.2 Alternativa: Cloudflare Tunnel

Ver `infra/cloudflare/cloudflared.example.yaml`. Requiere dominio propio en Cloudflare para una URL fija; usar también `compose.tunnel.yaml`.

### 4.3 Alternativa: servidor/VM con HTTPS propio (Caddy)

Con una VM con IP pública (p. ej. Oracle Cloud Always Free): abrir solo 22, 80 y 443, definir `GRX_DOMAIN` y `GPS_DOMAIN` (sin dominio propio: `<ip-con-guiones>.sslip.io` y `gps.<ip-con-guiones>.sslip.io`) y:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Caddy obtiene los certificados de Let's Encrypt automáticamente.

### Reglas de seguridad

- **Nunca** publicar 8082 (administración de Traccar), 8069 directo ni PostgreSQL.
- Solo se exponen la aplicación (HTTPS) y el receptor GPS (HTTPS).
- No subir `.env`, respaldos ni trazas GPS reales a Git.

## 5. Primer uso

La pantalla de inicio muestra una lista de **Primeros pasos**:

1. **Vehículos:** crear la unidad y pulsar «Generar identificador» (formato `GRX-…`).
2. **Dispositivo:** registrar ese identificador en Traccar (si Traccar responde *Unknown device*, crear el dispositivo con el mismo identificador en la API/administración de Traccar).
3. **Rutas:** crear la ruta, abrir «Definir paradas y trazado», poner origen, destino y al menos 2 controles intermedios, «Calcular trazado vial» y «Aprobar versión».
4. **Recorridos:** crear el recorrido (unidad, conductor, ruta, hora) y «Confirmar programación».
5. **GPS:** al salir, «Iniciar recorrido»; al llegar, «Finalizar recorrido» y «Evaluar recorrido».

### Traccar Client (teléfono)

| Campo | Valor |
|---|---|
| Identificador del dispositivo | El `GRX-…` del vehículo |
| URL del servidor | `https://<equipo>.<tailnet>.ts.net:8443` (o `https://GPS_DOMAIN`) |
| Frecuencia | 10–15 s |
| Precisión | Alta |

Desactivar el ahorro de batería para la app y permitir ubicación «siempre».

## 6. Datos simulados

Para métricas e indicadores se generan recorridos **simulados**, siempre etiquetados como tales (el panel separa Real / Simulado / Combinado). Requiere rutas aprobadas, vehículos activos y usuarios conductores.

```bash
# Generar 150 recorridos repartidos en los últimos 30 días
docker exec -i -e GRX_SIM_COUNT=150 -e GRX_SIM_DAYS=30 georutex-odoo sh -c \
  'odoo shell -c /etc/odoo/odoo.conf --db_host=$HOST --db_user=$USER --db_password=$PASSWORD -d georutex --no-http' < scripts/simulate_trips.py

# Borrar todos los simulados (no toca los reales)
docker exec -i -e GRX_SIM_PURGE=all georutex-odoo sh -c \
  'odoo shell -c /etc/odoo/odoo.conf --db_host=$HOST --db_user=$USER --db_password=$PASSWORD -d georutex --no-http' < scripts/simulate_trips.py
```

## 7. Pruebas

```bash
# Pruebas unitarias del dominio (Pytest)
docker compose --profile test run --rm --no-deps odoo-test \
  python3 -m pytest -c /workspace/pytest.ini /workspace/tests/unit -q --no-cov

# Pruebas nativas de Odoo (base temporal; se borra al final)
docker exec georutex-odoo sh -c 'odoo -c /etc/odoo/odoo.conf --db_host=$HOST --db_user=$USER --db_password=$PASSWORD \
  -d georutex_test --db-filter=^georutex_test$ -i uta_transport_monitor --test-enable \
  --test-tags /uta_transport_monitor --stop-after-init --http-port 8070'
docker exec georutex-postgres sh -c 'dropdb -U $POSTGRES_USER georutex_test'
```

En Git Bash (Windows) anteponer `MSYS_NO_PATHCONV=1` al comando de Pytest.

## 8. Respaldo y restauración

```bash
docker exec georutex-postgres sh -c 'pg_dump -U $POSTGRES_USER -Fc georutex -f /tmp/georutex.dump'
docker cp georutex-postgres:/tmp/georutex.dump ./georutex.dump
docker exec georutex-odoo tar czf /tmp/filestore.tgz -C /var/lib/odoo/filestore georutex
docker cp georutex-odoo:/tmp/filestore.tgz ./filestore.tgz
```

Restaurar: `pg_restore -U $POSTGRES_USER -d georutex --no-owner` dentro del contenedor de PostgreSQL y descomprimir el filestore en `/var/lib/odoo/filestore`. Guardar los respaldos fuera del repositorio.

## 9. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `ports are not available` / `Only one usage of each socket address` (Windows) | Cerrar Docker Desktop, `wsl --shutdown`, reabrir Docker Desktop. |
| `localhost:8069` no carga pero el contenedor está *healthy* (Windows) | Mismo procedimiento (relay de WSL bloqueado). |
| Vehículo en «Esperando primera señal» | Revisar identificador y URL en Traccar Client; en los logs de Traccar (`docker logs georutex-traccar`) *Unknown device* significa que falta registrar el dispositivo. |
| «Probar conexión GPS» falla | Revisar `TRACCAR_API_USERNAME/PASSWORD` en `.env` y reiniciar Odoo. |
| Los correos no llegan | Revisar variables `SMTP_*` y que la clave sea de aplicación. |

## 10. Documentación

- `docs/original_requirements.pdf` — enunciado original (fuente de mayor prioridad).
- `docs/requirements.md` — requisitos, indicadores y criterios de aceptación.
- `docs/architecture.md` — arquitectura, integración y despliegue.
- `AGENTS.md` — convenciones de desarrollo.
