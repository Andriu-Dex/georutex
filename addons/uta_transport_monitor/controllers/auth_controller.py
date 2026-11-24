"""Representative GeoRutex Spanish endpoints, OTP verification, and validations."""

import logging
import socket

from werkzeug.urls import url_encode

from odoo import http
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.session import Session
from odoo.addons.web.controllers.utils import ensure_db, is_user_internal
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import config as odoo_config

from ..domain.auth_validation import (
    normalize_email,
    validate_email,
    validate_signup_payload,
    validate_strong_password,
)
from ..models.email_verification import mask_email

_logger = logging.getLogger(__name__)

GEORUTEX_HOME_ROUTE = "/georutex/inicio"
GEORUTEX_LOGIN_ROUTE = "/georutex/acceso"
GEORUTEX_SIGNUP_ROUTE = "/georutex/registro-conductor"
GEORUTEX_VERIFY_ROUTE = "/georutex/verificar-correo"
GEORUTEX_RESEND_ROUTE = "/georutex/reenviar-codigo"
GEORUTEX_RESET_ROUTE = "/georutex/recuperar-acceso"
GEORUTEX_LOGOUT_ROUTE = "/georutex/cerrar-sesion"
GEORUTEX_PANEL_ROUTE = "/georutex/panel"

GEORUTEX_PROTECTED_SECTIONS = {
    "centro-control": (
        "uta_transport_monitor.action_transport_admin_home",
        "uta_transport_monitor.menu_georutex_admin_home",
        ("uta_transport_monitor.group_transport_manager",),
    ),
    "inicio-conductor": (
        "uta_transport_monitor.action_transport_driver_home",
        "uta_transport_monitor.menu_georutex_driver_home",
        (
            "uta_transport_monitor.group_transport_driver",
            "uta_transport_monitor.group_transport_manager",
        ),
    ),
    "dashboard": (
        "uta_transport_monitor.action_transport_dashboard",
        "uta_transport_monitor.menu_georutex_dashboard_main",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "mapa-en-vivo": (
        "uta_transport_monitor.action_transport_live_fleet_map",
        "uta_transport_monitor.menu_georutex_live_fleet_map",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
            "uta_transport_monitor.group_transport_driver",
        ),
    ),
    "recorridos": (
        "uta_transport_monitor.action_transport_trip",
        "uta_transport_monitor.menu_georutex_trips",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "incidencias": (
        "uta_transport_monitor.action_transport_incident",
        "uta_transport_monitor.menu_georutex_incidents",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
            "uta_transport_monitor.group_transport_driver",
        ),
    ),
    "evaluaciones": (
        "uta_transport_monitor.action_transport_trip_evaluation",
        "uta_transport_monitor.menu_georutex_evaluations",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "rutas": (
        "uta_transport_monitor.action_transport_route",
        "uta_transport_monitor.menu_georutex_routes",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "versiones-ruta": (
        "uta_transport_monitor.action_transport_route_version",
        "uta_transport_monitor.menu_georutex_route_versions",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "flota": (
        "uta_transport_monitor.action_transport_monitored_fleet",
        "uta_transport_monitor.menu_georutex_fleet",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
    "telemetria": (
        "uta_transport_monitor.action_transport_vehicle_position",
        "uta_transport_monitor.menu_georutex_positions",
        (
            "uta_transport_monitor.group_transport_manager",
            "uta_transport_monitor.group_transport_analyst",
        ),
    ),
}


def _build_url_with_query(path, params=None):
    """Append non-empty query parameters to a route path."""
    if not params:
        return path
    filtered = {k: v for k, v in params.items() if v not in (None, "")}
    if not filtered:
        return path
    return f"{path}?{url_encode(filtered)}"


def _security_headers(response):
    """Apply standard clickjacking protection headers to auth responses."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response


def _is_email_domain_resolvable(email: str) -> bool:
    """Verify via DNS that the email domain exists for SMTP delivery.

    Skipped in automated test mode so offline test suites remain deterministic.
    """
    if odoo_config.get("test_enable"):
        return True
    domain = (email or "").split("@", 1)[-1].strip().lower()
    if not domain:
        return False
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False
    except OSError:
        return True


class GeoRutexAuthController(AuthSignupHome):
    """Representative GeoRutex routes with strict validation and 6-digit OTP."""

    def _login_redirect(self, uid, redirect=None):
        """Redirect authenticated users to /web (never /web/login_successful)."""
        if request.session.uid and not redirect:
            if is_user_internal(request.session.uid):
                return "/web"
        if redirect and "/web/login_successful" in redirect:
            return "/web"
        return super()._login_redirect(uid, redirect=redirect)

    def _render_public_home(self):
        """Render the public GSAP-powered GeoRutex landing page before login."""
        ensure_db()
        is_authenticated = bool(request.session.uid)
        user_name = ""
        if is_authenticated:
            try:
                user_name = request.env.user.name or ""
            except Exception:
                user_name = ""
        response = request.render(
            "uta_transport_monitor.georutex_public_home",
            {
                "is_authenticated": is_authenticated,
                "user_name": user_name,
                "login_url": GEORUTEX_LOGIN_ROUTE,
                "signup_url": GEORUTEX_SIGNUP_ROUTE,
                "panel_url": GEORUTEX_PANEL_ROUTE,
                "logout_url": GEORUTEX_LOGOUT_ROUTE,
            },
        )
        response = _security_headers(response)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @http.route("/", type="http", auth="none", sitemap=False)
    def index(self, s_action=None, db=None, **kw):
        """Serve the public GeoRutex Home before login, or redirect authenticated users."""
        if request.session.uid and kw.get("vista") != "publica":
            return request.redirect_query(
                "/web", query=request.params, code=302
            )
        return self._render_public_home()

    @http.route(
        [GEORUTEX_HOME_ROUTE, "/inicio"],
        type="http",
        auth="none",
        sitemap=False,
    )
    def georutex_public_home(self, **kw):
        """Explicit public GeoRutex General Home route."""
        return self._render_public_home()

    @http.route(
        GEORUTEX_PANEL_ROUTE,
        type="http",
        auth="none",
        sitemap=False,
    )
    def georutex_panel_redirect(self, **kw):
        """Representative GeoRutex panel entry point."""
        if request.session.uid:
            return request.redirect("/web", code=302)
        return request.redirect(GEORUTEX_LOGIN_ROUTE, code=302)

    @http.route(
        "/georutex/<string:section_slug>",
        type="http",
        auth="user",
        sitemap=False,
    )
    def georutex_protected_section(self, section_slug, **kw):
        """Role-protected server-side router for clean /georutex/<section> URLs."""
        spec = GEORUTEX_PROTECTED_SECTIONS.get(section_slug)
        if not spec:
            return request.redirect("/web", code=302)
        action_xmlid, menu_xmlid, allowed_groups = spec
        user = request.env.user
        is_allowed = user.has_group("base.group_system") or any(
            user.has_group(grp) for grp in allowed_groups
        )
        if not is_allowed:
            return request.redirect("/web", code=302)
        action = request.env.ref(action_xmlid, raise_if_not_found=False)
        menu = request.env.ref(menu_xmlid, raise_if_not_found=False)
        if action and menu:
            return request.redirect(
                f"/web#action={action.id}&menu_id={menu.id}", code=302
            )
        return request.redirect("/web", code=302)

    @http.route(
        "/georutex/mis-recorridos",
        type="http",
        auth="user",
        sitemap=False,
    )
    def georutex_my_trips_shortcut(self, **kw):
        """Direct GeoRutex endpoint opening the driver's Mis Recorridos view."""
        menu = request.env.ref(
            "uta_transport_monitor.menu_georutex_root",
            raise_if_not_found=False,
        )
        action = request.env.ref(
            "uta_transport_monitor.action_transport_trip_my_driver",
            raise_if_not_found=False,
        )
        if menu and action:
            return request.redirect(
                f"/web#action={action.id}&menu_id={menu.id}&model=transport.trip&view_type=kanban",
                code=302,
            )
        return request.redirect("/web", code=302)

    @http.route(
        "/georutex/incidencias/nueva",
        type="http",
        auth="user",
        sitemap=False,
    )
    def georutex_new_incident_shortcut(self, **kw):
        """Direct GeoRutex endpoint opening the right-side editable incident card."""
        menu = request.env.ref(
            "uta_transport_monitor.menu_georutex_root",
            raise_if_not_found=False,
        )
        action = request.env.ref(
            "uta_transport_monitor.action_transport_incident",
            raise_if_not_found=False,
        )
        if menu and action:
            target = (
                f"/web#action={action.id}&menu_id={menu.id}"
                "&model=transport.incident&view_type=form"
            )
            return request.redirect(target, code=302)
        return request.redirect("/web", code=302)

    @http.route(
        ["/web/login", "/iniciar-sesion", "/ingresar"],
        type="http",
        auth="none",
        sitemap=False,
    )
    def web_login(self, redirect=None, **kw):
        """Redirect legacy/Odoo login URLs to /georutex/acceso on GET."""
        if (
            request.httprequest.method == "GET"
            and request.httprequest.path != GEORUTEX_LOGIN_ROUTE
        ):
            if request.session.uid:
                return request.redirect(
                    self._login_redirect(request.session.uid, redirect=redirect)
                )
            query = dict(request.httprequest.args)
            return request.redirect(
                _build_url_with_query(GEORUTEX_LOGIN_ROUTE, query), code=302
            )
        return self._handle_georutex_login(redirect=redirect, **kw)

    @http.route(
        GEORUTEX_LOGIN_ROUTE,
        type="http",
        auth="none",
        sitemap=False,
    )
    def georutex_login(self, redirect=None, **kw):
        """Primary GeoRutex login endpoint."""
        return self._handle_georutex_login(redirect=redirect, **kw)

    def _handle_georutex_login(self, redirect=None, **kw):
        """Validate email existence, verification status, and credentials."""
        ensure_db()
        if request.httprequest.method == "POST":
            raw_login = (request.params.get("login") or "").strip()
            raw_password = request.params.get("password") or ""

            if not raw_login or not raw_password:
                return self._render_login_state(
                    error="Debe ingresar su correo electrónico y contraseña.",
                    redirect=redirect,
                )

            users_model = request.env["res.users"].sudo()
            matched_user = users_model.search(
                [("login", "=", raw_login), ("active", "=", True)], limit=1
            )
            if not matched_user:
                normalized = normalize_email(raw_login)
                matched_user = users_model.search(
                    [("login", "=ilike", normalized), ("active", "=", True)],
                    limit=1,
                )

            if not matched_user:
                # Check if account exists but is awaiting 6-digit email verification
                normalized = normalize_email(raw_login)
                pending_user = users_model.with_context(
                    active_test=False
                ).search(
                    [("login", "=ilike", normalized), ("active", "=", False)],
                    limit=1,
                )
                if pending_user:
                    has_otp = (
                        request.env["transport.email.verification"]
                        .sudo()
                        .search_count([
                            ("email", "=", normalized),
                            ("verified", "=", False),
                        ])
                        > 0
                    )
                    if has_otp:
                        return self._render_login_state(
                            error=(
                                "Tu cuenta aún requiere verificación numérica de correo. "
                                "Ingresa el código de 6 dígitos enviado a tu correo."
                            ),
                            verify_email=normalized,
                            redirect=redirect,
                        )

                is_valid_mail, mail_err = validate_email(raw_login)
                if not is_valid_mail and raw_login.lower() != "admin":
                    return self._render_login_state(
                        error=mail_err, redirect=redirect
                    )
                return self._render_login_state(
                    error=(
                        "No existe una cuenta registrada con el correo "
                        "electrónico ingresado. Verifica tus datos o crea "
                        "una cuenta nueva."
                    ),
                    redirect=redirect,
                )

            request.params["login"] = matched_user.login
            response = super().web_login(redirect=redirect, **kw)
            if (
                hasattr(response, "qcontext")
                and isinstance(response.qcontext, dict)
                and response.qcontext.get("error")
            ):
                response.qcontext["error"] = (
                    "La contraseña ingresada es incorrecta. "
                    "Verifica e inténtalo nuevamente."
                )
            return response

        response = super().web_login(redirect=redirect, **kw)
        if (
            request.httprequest.args.get("verified") == "1"
            and hasattr(response, "qcontext")
            and isinstance(response.qcontext, dict)
        ):
            response.qcontext["message"] = (
                "¡Correo verificado correctamente! Tu cuenta de conductor "
                "ya está activa. Inicia sesión para entrar a GeoRutex."
            )
        return response

    def _render_login_state(
        self, error=None, message=None, verify_email=None, redirect=None
    ):
        """Render the GeoRutex login template with Spanish state messages."""
        values = {
            k: v
            for k, v in request.params.items()
            if k in ("login", "redirect", "db")
        }
        if error:
            values["error"] = error
        if message:
            values["message"] = message
        if verify_email:
            values["georutex_verify_url"] = _build_url_with_query(
                GEORUTEX_VERIFY_ROUTE, {"email": verify_email}
            )
        values["redirect"] = redirect
        values["databases"] = http.db_list() if http.db_filter else []
        values["signup_enabled"] = (
            request.env["res.users"]._get_signup_invitation_scope() == "b2c"
        )
        values["reset_password_enabled"] = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("auth_signup.reset_password")
            == "True"
        )
        return _security_headers(request.render("web.login", values))

    @http.route(
        ["/web/signup", "/crear-cuenta", "/registro"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def web_auth_signup(self, *args, **kw):
        """Redirect legacy/Odoo signup URLs to /georutex/registro-conductor on GET."""
        if (
            request.httprequest.method == "GET"
            and request.httprequest.path != GEORUTEX_SIGNUP_ROUTE
        ):
            query = dict(request.httprequest.args)
            return request.redirect(
                _build_url_with_query(GEORUTEX_SIGNUP_ROUTE, query), code=302
            )
        return self._handle_georutex_signup(*args, **kw)

    @http.route(
        GEORUTEX_SIGNUP_ROUTE,
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def georutex_signup(self, *args, **kw):
        """Primary GeoRutex driver registration endpoint."""
        return self._handle_georutex_signup(*args, **kw)

    def _handle_georutex_signup(self, *args, **kw):
        """Validate payload, create pending driver account, and send 6-digit OTP via SMTP."""
        if request.httprequest.method == "POST":
            qcontext = self.get_auth_signup_qcontext()
            if not qcontext.get("token") and not qcontext.get("signup_enabled"):
                return request.not_found()

            name = (qcontext.get("name") or "").strip()
            email = normalize_email(qcontext.get("login") or "")
            password = qcontext.get("password") or ""
            confirm_password = qcontext.get("confirm_password") or ""

            valid, error_msg = validate_signup_payload(
                name=name,
                email=email,
                password=password,
                confirm_password=confirm_password,
            )
            if not valid:
                qcontext["error"] = error_msg
                qcontext["name"] = name
                qcontext["login"] = email
                return _security_headers(
                    request.render("auth_signup.signup", qcontext)
                )

            if not _is_email_domain_resolvable(email):
                qcontext["error"] = (
                    "El dominio del correo electrónico no existe o no puede "
                    "recibir correos por SMTP. Use un correo real "
                    "(ej. @gmail.com, @hotmail.com, @outlook.com o @uta.edu.ec)."
                )
                qcontext["name"] = name
                qcontext["login"] = email
                return _security_headers(
                    request.render("auth_signup.signup", qcontext)
                )

            # Check existing active or inactive user
            users_sudo = request.env["res.users"].sudo().with_context(
                active_test=False
            )
            existing = users_sudo.search([("login", "=ilike", email)], limit=1)
            if existing:
                if existing.active:
                    qcontext["error"] = (
                        "Ya existe una cuenta activa registrada con este correo "
                        "electrónico. Inicia sesión o recupera tu acceso."
                    )
                    qcontext["name"] = name
                    qcontext["login"] = email
                    return _security_headers(
                        request.render("auth_signup.signup", qcontext)
                    )
                # Pending unverified account: refresh password, name, and resend OTP
                existing.write({"name": name, "password": password})
                request.env["transport.email.verification"].create_and_send_otp(
                    existing, email, name
                )
                return request.redirect(
                    _build_url_with_query(
                        GEORUTEX_VERIFY_ROUTE, {"email": email}
                    ),
                    code=303,
                )

            try:
                values = {
                    "login": email,
                    "name": name,
                    "password": password,
                    "email": email,
                }
                request.env["res.users"].sudo().signup(values, qcontext.get("token"))
                new_user = (
                    request.env["res.users"]
                    .sudo()
                    .search([("login", "=", email)], limit=1)
                )
                if new_user:
                    # Keep account inactive until 6-digit numeric email code is verified
                    new_user.sudo().write({"active": False})
                    request.env[
                        "transport.email.verification"
                    ].create_and_send_otp(new_user, email, name)
                return request.redirect(
                    _build_url_with_query(
                        GEORUTEX_VERIFY_ROUTE, {"email": email}
                    ),
                    code=303,
                )
            except Exception as exc:
                _logger.error("GeoRutex signup error: %s", exc)
                qcontext["error"] = str(exc) or "No se pudo completar el registro."
                qcontext["name"] = name
                qcontext["login"] = email
                return _security_headers(
                    request.render("auth_signup.signup", qcontext)
                )

        return super().web_auth_signup(*args, **kw)

    @http.route(
        GEORUTEX_VERIFY_ROUTE,
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def georutex_verify_email(self, email=None, code=None, **kw):
        """Render and process 6-digit numeric email verification (OTP)."""
        ensure_db()
        normalized = normalize_email(email or request.params.get("email") or "")
        otp_model = request.env["transport.email.verification"].sudo()
        latest_otp = (
            otp_model.search(
                [("email", "=", normalized)],
                order="id desc",
                limit=1,
            )
            if normalized
            else otp_model.browse()
        )

        qcontext = {
            "email": normalized,
            "masked_email": mask_email(normalized),
            "delivery_status": latest_otp.delivery_status if latest_otp else "",
            "delivery_error": latest_otp.delivery_error if latest_otp else "",
            "resent": request.httprequest.args.get("resent") == "1",
            "error": None,
            "message": None,
        }

        if request.httprequest.method == "POST":
            submitted_code = (
                code
                or request.params.get("code")
                or "".join(
                    request.params.get(f"digit_{i}", "") for i in range(1, 7)
                )
            )
            ok, msg, user = otp_model.verify_code(normalized, submitted_code)
            if ok and user:
                return request.redirect(
                    _build_url_with_query(
                        GEORUTEX_LOGIN_ROUTE,
                        {"verified": "1", "login": user.login},
                    ),
                    code=303,
                )
            qcontext["error"] = msg

        return _security_headers(
            request.render(
                "uta_transport_monitor.georutex_verify_email", qcontext
            )
        )

    @http.route(
        GEORUTEX_RESEND_ROUTE,
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
    )
    def georutex_resend_code(self, email=None, **kw):
        """Generate and resend a fresh 6-digit numeric OTP code via SMTP."""
        ensure_db()
        normalized = normalize_email(email or request.params.get("email") or "")
        if normalized:
            user = (
                request.env["res.users"]
                .sudo()
                .with_context(active_test=False)
                .search(
                    [("login", "=ilike", normalized), ("active", "=", False)],
                    limit=1,
                )
            )
            if user:
                request.env["transport.email.verification"].create_and_send_otp(
                    user, normalized, user.name
                )
        return request.redirect(
            _build_url_with_query(
                GEORUTEX_VERIFY_ROUTE, {"email": normalized, "resent": "1"}
            ),
            code=303,
        )

    @http.route(
        ["/web/reset_password", "/recuperar-contrasena"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def web_auth_reset_password(self, *args, **kw):
        """Redirect legacy password reset URLs to /georutex/recuperar-acceso."""
        if (
            request.httprequest.method == "GET"
            and request.httprequest.path != GEORUTEX_RESET_ROUTE
        ):
            query = dict(request.httprequest.args)
            return request.redirect(
                _build_url_with_query(GEORUTEX_RESET_ROUTE, query), code=302
            )
        return self._handle_georutex_reset_password(*args, **kw)

    @http.route(
        GEORUTEX_RESET_ROUTE,
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def georutex_reset_password(self, *args, **kw):
        """Primary GeoRutex password recovery endpoint."""
        return self._handle_georutex_reset_password(*args, **kw)

    def _handle_georutex_reset_password(self, *args, **kw):
        """Validate email existence and strong password during reset."""
        if request.httprequest.method == "POST":
            qcontext = self.get_auth_signup_qcontext()
            if qcontext.get("token"):
                pwd = qcontext.get("password") or ""
                confirm = qcontext.get("confirm_password") or ""
                ok, err = validate_strong_password(pwd)
                if not ok:
                    qcontext["error"] = err
                    return _security_headers(
                        request.render("auth_signup.reset_password", qcontext)
                    )
                if pwd != confirm:
                    qcontext["error"] = "Las contraseñas ingresadas no coinciden."
                    return _security_headers(
                        request.render("auth_signup.reset_password", qcontext)
                    )
            else:
                login = normalize_email(qcontext.get("login") or "")
                ok, err = validate_email(login)
                if not ok:
                    qcontext["error"] = err
                    return _security_headers(
                        request.render("auth_signup.reset_password", qcontext)
                    )
                exists = (
                    request.env["res.users"]
                    .sudo()
                    .search(
                        [("login", "=ilike", login), ("active", "=", True)],
                        limit=1,
                    )
                )
                if not exists:
                    qcontext["error"] = (
                        "No existe ninguna cuenta activa asociada a ese "
                        "correo electrónico."
                    )
                    return _security_headers(
                        request.render("auth_signup.reset_password", qcontext)
                    )
                request.params["login"] = exists.login
        try:
            return super().web_auth_reset_password(*args, **kw)
        except UserError as exc:
            qcontext = self.get_auth_signup_qcontext()
            qcontext["error"] = str(exc)
            return _security_headers(
                request.render("auth_signup.reset_password", qcontext)
            )


class GeoRutexSessionController(Session):
    """Representative GeoRutex logout endpoint redirecting to /georutex/acceso."""

    @http.route(
        [GEORUTEX_LOGOUT_ROUTE, "/cerrar-sesion"],
        type="http",
        auth="none",
        sitemap=False,
    )
    def georutex_logout(self, redirect=GEORUTEX_HOME_ROUTE):
        """Log out and redirect to /georutex/inicio."""
        request.session.logout(keep_db=True)
        return request.redirect(redirect or GEORUTEX_HOME_ROUTE, code=303)

    @http.route("/web/session/logout", type="http", auth="none")
    def logout(self, redirect="/web"):
        """Override default logout to return to /georutex/inicio."""
        target = redirect
        if target in ("/web", "/web/login", "/iniciar-sesion", "/", None, ""):
            target = GEORUTEX_HOME_ROUTE
        return super().logout(redirect=target)
