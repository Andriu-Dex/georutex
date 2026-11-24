"""Idempotent Odoo 16 startup wrapper for GeoRutex.

Waits for PostgreSQL, initializes georutex with Spanish (Ecuador) language
support if needed, installs or upgrades uta_transport_monitor automatically
when the manifest version changes, and hands off execution to the official
Odoo entrypoint.
"""
import ast
import os
import subprocess
import sys
import time

import psycopg2

PRIMARY_ADDON = "uta_transport_monitor"
MANIFEST_PATH = f"/mnt/extra-addons/{PRIMARY_ADDON}/__manifest__.py"
DEFAULT_LANG = "es_EC"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def wait_for_postgres(
    host: str, port: int, user: str, password: str, timeout: int = 30
) -> None:
    """Wait until PostgreSQL accepts connections."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname="postgres",
                connect_timeout=5,
            )
            conn.close()
            return
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(
        f"PostgreSQL at {host}:{port} not ready after {timeout}s: {last_error}"
    )


def read_manifest_version() -> str:
    """Return the version declared in uta_transport_monitor/__manifest__.py."""
    if not os.path.exists(MANIFEST_PATH):
        return ""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        data = ast.literal_eval(handle.read())
    return str(data.get("version") or "")


def inspect_database_state(
    host: str, port: int, user: str, password: str, db_name: str
):
    """Return (initialized, addon_state, addon_version, lang_active)."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name,
            connect_timeout=5,
        )
    except psycopg2.OperationalError:
        return (False, None, None, False)

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.ir_module_module') IS NOT NULL"
            )
            row = cur.fetchone()
            if not (row and row[0]):
                return (False, None, None, False)

            cur.execute(
                "SELECT state, latest_version "
                "FROM ir_module_module WHERE name = %s",
                (PRIMARY_ADDON,),
            )
            mod_row = cur.fetchone()
            addon_state = mod_row[0] if mod_row else None
            addon_version = mod_row[1] if mod_row else None

            cur.execute(
                "SELECT active FROM res_lang WHERE code = %s",
                (DEFAULT_LANG,),
            )
            lang_row = cur.fetchone()
            lang_active = bool(lang_row and lang_row[0])
            return (True, addon_state, addon_version, lang_active)
    finally:
        conn.close()


def run_odoo_maintenance(
    db_name: str, flag: str, modules: str, load_lang: bool = False
) -> None:
    """Run one-shot Odoo install (-i) or upgrade (-u) and stop after init."""
    cmd = [
        "/entrypoint.sh",
        "odoo",
        "-d",
        db_name,
        flag,
        modules,
        "--without-demo=all",
        "--stop-after-init",
    ]
    if load_lang:
        cmd.extend(["--load-language", DEFAULT_LANG])
    subprocess.run(cmd, check=True)


def set_default_spanish_for_users(
    host: str, port: int, user: str, password: str, db_name: str
) -> None:
    """Ensure active internal users without Spanish use es_EC and Ecuador TZ."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name,
            connect_timeout=5,
        )
    except psycopg2.OperationalError:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE res_partner SET lang = %s, tz = COALESCE(tz, %s) "
                    "WHERE id IN (SELECT partner_id FROM res_users WHERE active = TRUE) "
                    "AND (lang IS NULL OR lang = 'en_US')",
                    (DEFAULT_LANG, "America/Guayaquil"),
                )
    finally:
        conn.close()


def sync_smtp_server(
    host: str, port: int, user: str, password: str, db_name: str
) -> None:
    """Create or update Odoo's GeoRutex SMTP server when SMTP_HOST is configured."""
    smtp_host = _env("SMTP_HOST", "").strip()
    if not smtp_host:
        return
    smtp_port = int(_env("SMTP_PORT", "587"))
    smtp_encryption = _env("SMTP_ENCRYPTION", "starttls").strip() or "starttls"
    if smtp_encryption not in ("none", "starttls", "ssl"):
        smtp_encryption = "starttls"
    smtp_user = _env("SMTP_USER", "").strip() or None
    smtp_pass = _env("SMTP_PASSWORD", "") or None
    smtp_from = _env("SMTP_FROM", "").strip() or smtp_user

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name,
            connect_timeout=5,
        )
    except psycopg2.OperationalError:
        return

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM ir_mail_server WHERE name = %s LIMIT 1",
                    ("GeoRutex SMTP",),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE ir_mail_server SET smtp_host=%s, smtp_port=%s, "
                        "smtp_encryption=%s, smtp_user=%s, smtp_pass=%s, "
                        "from_filter=%s, active=TRUE, sequence=5 WHERE id=%s",
                        (
                            smtp_host,
                            smtp_port,
                            smtp_encryption,
                            smtp_user,
                            smtp_pass,
                            smtp_from,
                            row[0],
                        ),
                    )
                else:
                    cur.execute(
                        "INSERT INTO ir_mail_server "
                        "(name, smtp_host, smtp_port, smtp_encryption, "
                        "smtp_user, smtp_pass, from_filter, smtp_authentication, "
                        "active, sequence, create_uid, write_uid, create_date, write_date) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'login', TRUE, 5, 1, 1, NOW(), NOW())",
                        (
                            "GeoRutex SMTP",
                            smtp_host,
                            smtp_port,
                            smtp_encryption,
                            smtp_user,
                            smtp_pass,
                            smtp_from,
                        ),
                    )
        print(
            f"[georutex-entrypoint] Synced outgoing SMTP server ({smtp_host}:{smtp_port}).",
            flush=True,
        )
    finally:
        conn.close()


def main() -> None:
    host = _env("HOST", "postgres")
    port = int(_env("PORT", "5432"))
    user = _env("USER", "odoo")
    password = _env("PASSWORD", "odoo")
    db_name = _env("DB_NAME", "georutex")
    init_modules = _env("ODOO_INIT_MODULES", f"base,{PRIMARY_ADDON}")
    force_upgrade = _env("ODOO_AUTO_UPGRADE", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    args = sys.argv[1:] or ["odoo"]

    wait_for_postgres(host, port, user, password)

    initialized, addon_state, addon_version, lang_active = (
        inspect_database_state(host, port, user, password, db_name)
    )
    manifest_version = read_manifest_version()

    if not initialized:
        print(
            f"[georutex-entrypoint] Initializing database '{db_name}' "
            f"with modules: {init_modules} ({DEFAULT_LANG})",
            flush=True,
        )
        run_odoo_maintenance(db_name, "-i", init_modules, load_lang=True)
        set_default_spanish_for_users(host, port, user, password, db_name)
        print(
            f"[georutex-entrypoint] Database '{db_name}' initialized.",
            flush=True,
        )
    elif addon_state != "installed":
        print(
            f"[georutex-entrypoint] Installing '{PRIMARY_ADDON}' "
            f"into database '{db_name}'...",
            flush=True,
        )
        run_odoo_maintenance(
            db_name, "-i", PRIMARY_ADDON, load_lang=not lang_active
        )
        set_default_spanish_for_users(host, port, user, password, db_name)
        print(
            f"[georutex-entrypoint] Module '{PRIMARY_ADDON}' installed.",
            flush=True,
        )
    elif (
        force_upgrade
        or not lang_active
        or (manifest_version and addon_version != manifest_version)
    ):
        print(
            f"[georutex-entrypoint] Upgrading '{PRIMARY_ADDON}' in "
            f"'{db_name}' ({addon_version} -> {manifest_version}, "
            f"lang_active={lang_active})...",
            flush=True,
        )
        run_odoo_maintenance(
            db_name, "-u", PRIMARY_ADDON, load_lang=not lang_active
        )
        set_default_spanish_for_users(host, port, user, password, db_name)
        print(
            f"[georutex-entrypoint] Module '{PRIMARY_ADDON}' upgraded.",
            flush=True,
        )
    else:
        print(
            f"[georutex-entrypoint] Database '{db_name}' ready "
            f"({PRIMARY_ADDON} {addon_version}, {DEFAULT_LANG}).",
            flush=True,
        )

    sync_smtp_server(host, port, user, password, db_name)
    os.execv("/entrypoint.sh", ["/entrypoint.sh", *args])


if __name__ == "__main__":
    main()
