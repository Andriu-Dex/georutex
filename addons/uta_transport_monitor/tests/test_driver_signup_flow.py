"""Native Odoo 16 tests for Spanish endpoints, auth validation, and driver flow."""

import re

from odoo.addons.auth_signup.models.res_partner import SignupError
from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install", "driver_signup_flow")
class TestDriverSignupFlow(TransactionCase):
    """Verify self-signup, Apps restrictions, fleet isolation, and incident editing."""

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        self.group_driver = self.env.ref(
            "uta_transport_monitor.group_transport_driver"
        )
        self.group_analyst = self.env.ref(
            "uta_transport_monitor.group_transport_analyst"
        )
        self.group_manager = self.env.ref(
            "uta_transport_monitor.group_transport_manager"
        )
        self.group_portal = self.env.ref("base.group_portal")
        self.group_internal = self.env.ref("base.group_user")
        self.group_system = self.env.ref("base.group_system")

    def test_01_signup_provisions_internal_driver_not_portal(self):
        """Self-signup creates an internal Conductor user, preventing /web/login_successful."""
        login, _password = self.env["res.users"].sudo().signup(
            {
                "name": "Conductor Autoregistro",
                "login": "conductor.signup@uta.edu.ec",
                "password": "TestPassword!2026",
            }
        )
        user = self.env["res.users"].sudo().search([("login", "=", login)])
        self.assertEqual(len(user), 1)
        self.assertFalse(user.share)
        self.assertTrue(user._is_internal())
        self.assertEqual(user.tz, "America/Guayaquil")

        # Least-privilege role verification
        self.assertIn(self.group_internal, user.groups_id)
        self.assertIn(self.group_driver, user.groups_id)
        self.assertNotIn(self.group_portal, user.groups_id)
        self.assertNotIn(self.group_analyst, user.groups_id)
        self.assertNotIn(self.group_manager, user.groups_id)
        self.assertNotIn(self.group_system, user.groups_id)

    def test_02_signup_rejects_invalid_names_emails_and_weak_passwords(self):
        """Server-side signup blocks lowercase/symbol names and letters-only passwords."""
        with self.assertRaises(SignupError):
            self.env["res.users"].sudo().signup(
                {
                    "name": "juan perez",
                    "login": "bad.name@uta.edu.ec",
                    "password": "TestPassword!2026",
                }
            )
        with self.assertRaises(SignupError):
            self.env["res.users"].sudo().signup(
                {
                    "name": "Juan123 Perez!",
                    "login": "bad.chars@uta.edu.ec",
                    "password": "TestPassword!2026",
                }
            )
        with self.assertRaises(SignupError):
            self.env["res.users"].sudo().signup(
                {
                    "name": "Juan Pérez",
                    "login": "weak.pwd@uta.edu.ec",
                    "password": "SoloLetrasSinNumeros",
                }
            )

    def test_03_driver_lands_on_georutex_without_apps_menu(self):
        """GeoRutex is first root app, Mis Recorridos first, and Apps menu is hidden & blocked."""
        login, _ = self.env["res.users"].sudo().signup(
            {
                "name": "Conductor Menu Home",
                "login": "conductor.home@uta.edu.ec",
                "password": "TestPassword!2026",
            }
        )
        user = self.env["res.users"].sudo().search([("login", "=", login)])

        root_menus = (
            self.env["ir.ui.menu"]
            .with_user(user)
            .search([("parent_id", "=", False)], order="sequence, id")
        )
        georutex_root = self.env.ref(
            "uta_transport_monitor.menu_georutex_root"
        )
        apps_menu = self.env.ref("base.menu_management")
        self.assertTrue(root_menus)
        self.assertEqual(root_menus[0], georutex_root)
        # Apps menu must NOT be visible to drivers
        self.assertNotIn(apps_menu, root_menus)

        # ORM-level module installation restriction
        sample_mod = self.env["ir.module.module"].sudo().search([], limit=1)
        with self.assertRaises(AccessError):
            sample_mod.with_user(user).button_immediate_install()

        root_children = (
            self.env["ir.ui.menu"]
            .with_user(user)
            .search([("parent_id", "=", georutex_root.id)], order="sequence, id")
        )
        driver_home_menu = self.env.ref(
            "uta_transport_monitor.menu_georutex_driver_home"
        )
        self.assertTrue(root_children)
        self.assertEqual(root_children[0], driver_home_menu)

        ops_menu = self.env.ref(
            "uta_transport_monitor.menu_georutex_operations"
        )
        ops_children = (
            self.env["ir.ui.menu"]
            .with_user(user)
            .search([("parent_id", "=", ops_menu.id)], order="sequence, id")
        )
        my_trips_menu = self.env.ref(
            "uta_transport_monitor.menu_georutex_my_trips"
        )
        self.assertTrue(ops_children)
        self.assertEqual(ops_children[0], my_trips_menu)

        # Verify bespoke Driver Home RPC works and isolates own data
        home_data = (
            self.env["transport.trip"].with_user(user).get_driver_home_data()
        )
        self.assertEqual(home_data["driver_name"], "Conductor Menu Home")
        self.assertEqual(home_data["stats"]["total_trips"], 0)

    def test_04_driver_fleet_isolation_and_full_incident_editing(self):
        """Driver reads own vehicle, edits full manual incident, cannot self-approve."""
        login_a, _ = self.env["res.users"].sudo().signup(
            {
                "name": "Conductor Alpha",
                "login": "drv.signup.a@uta.edu.ec",
                "password": "TestPassword!2026",
            }
        )
        login_b, _ = self.env["res.users"].sudo().signup(
            {
                "name": "Conductor Beta",
                "login": "drv.signup.b@uta.edu.ec",
                "password": "TestPassword!2026",
            }
        )
        user_a = self.env["res.users"].sudo().search([("login", "=", login_a)])
        user_b = self.env["res.users"].sudo().search([("login", "=", login_b)])
        user_analyst = self.env["res.users"].create(
            {
                "name": "Analista Flota",
                "login": "analyst.fleet@uta.edu.ec",
                "email": "analyst.fleet@uta.edu.ec",
                "groups_id": [(6, 0, [self.group_analyst.id])],
            }
        )

        brand = self.env["fleet.vehicle.model.brand"].create(
            {"name": "SignupBrand"}
        )
        model = self.env["fleet.vehicle.model"].create(
            {"name": "SignupModel", "brand_id": brand.id}
        )
        veh_a = self.env["fleet.vehicle"].create(
            {
                "model_id": model.id,
                "license_plate": "SGN-001",
                "driver_id": user_a.partner_id.id,
            }
        )
        veh_b = self.env["fleet.vehicle"].create(
            {
                "model_id": model.id,
                "license_plate": "SGN-002",
                "driver_id": user_b.partner_id.id,
            }
        )

        # Driver A sees ONLY veh_a and cannot write
        drv_a_vehicles = self.env["fleet.vehicle"].with_user(user_a).search([])
        self.assertIn(veh_a.id, drv_a_vehicles.ids)
        self.assertNotIn(veh_b.id, drv_a_vehicles.ids)
        with self.assertRaises(AccessError):
            veh_a.with_user(user_a).write({"license_plate": "HACK-001"})

        # Analyst sees ALL vehicles read-only and cannot write
        analyst_vehicles = (
            self.env["fleet.vehicle"].with_user(user_analyst).search([])
        )
        self.assertIn(veh_a.id, analyst_vehicles.ids)
        self.assertIn(veh_b.id, analyst_vehicles.ids)
        with self.assertRaises(AccessError):
            veh_a.with_user(user_analyst).write({"license_plate": "HACK-002"})

        # Create route + trip for Driver A and verify Driver A can create & edit full incident
        route = self.env["transport.route"].create(
            {
                "name": "Ruta Incidencia Conductor",
                "code": "RUT-INC-DRV",
                "origin_name": "Huachi",
                "destination_name": "Ingahurco",
            }
        )
        ver = self.env["transport.route.version"].create(
            {"route_id": route.id, "version_number": 1}
        )
        for i in range(1, 5):
            self.env["transport.route.stop"].create(
                {
                    "route_version_id": ver.id,
                    "sequence": i * 10,
                    "name": f"Parada {i}",
                    "latitude": -1.25 + (i * 0.004),
                    "longitude": -78.62,
                }
            )
        ver.action_approve()
        trip_a = self.env["transport.trip"].create(
            {
                "vehicle_id": veh_a.id,
                "driver_id": user_a.partner_id.id,
                "driver_user_id": user_a.id,
                "route_id": route.id,
                "route_version_id": ver.id,
                "scheduled_start_utc": "2026-11-25 12:00:00",
                "scheduled_end_utc": "2026-11-25 13:00:00",
            }
        )
        trip_a.action_schedule()

        incident = self.env["transport.incident"].with_user(user_a).create(
            {
                "trip_id": trip_a.id,
                "incident_type": "traffic_congestion",
                "source": "manual",
                "severity": "medium",
                "description": "Tráfico intenso en Av. Cevallos",
                "evidence_data": "Reporte radial 08:15",
                "justification_notes": "Retraso por cierre vial",
            }
        )
        # Driver modifies all editable fields of their manual incident
        incident.with_user(user_a).write(
            {
                "incident_type": "road_block",
                "severity": "high",
                "latitude": -1.254,
                "longitude": -78.621,
                "rule_applied": "RF-28",
                "description": "Bloqueo total por obra municipal",
                "evidence_data": "Confirmado con control de tráfico",
                "justification_notes": "Desvío autorizado por agente",
            }
        )
        self.assertEqual(incident.severity, "high")
        self.assertEqual(incident.incident_type, "road_block")
        self.assertEqual(incident.evidence_data, "Confirmado con control de tráfico")

        # Driver still CANNOT approve their own justification (RF-29)
        with self.assertRaises(AccessError):
            incident.with_user(user_a).action_approve_justification()


@tagged("post_install", "-at_install", "driver_signup_flow")
class TestDriverSignupHttpRedirect(HttpCase):
    """Verify representative GeoRutex endpoints, OTP flow, and /web redirect."""

    def _extract_csrf(self, html_text):
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
        self.assertTrue(match, "CSRF token not found in form")
        return match.group(1)

    def test_01_default_routes_redirect_to_georutex_endpoints(self):
        """/, /web/login, /web/signup, and /web/reset_password redirect to /georutex/*."""
        r_root = self.url_open("/", allow_redirects=False)
        self.assertEqual(r_root.status_code, 302)
        self.assertIn("/georutex/acceso", r_root.headers.get("Location", ""))

        r_login = self.url_open("/web/login", allow_redirects=False)
        self.assertEqual(r_login.status_code, 302)
        self.assertIn("/georutex/acceso", r_login.headers.get("Location", ""))

        r_signup = self.url_open("/web/signup", allow_redirects=False)
        self.assertEqual(r_signup.status_code, 302)
        self.assertIn(
            "/georutex/registro-conductor", r_signup.headers.get("Location", "")
        )

        r_reset = self.url_open("/web/reset_password", allow_redirects=False)
        self.assertEqual(r_reset.status_code, 302)
        self.assertIn(
            "/georutex/recuperar-acceso", r_reset.headers.get("Location", "")
        )

    def test_02_login_checks_email_existence_in_spanish(self):
        """Login with unregistered email returns clear Spanish message."""
        page = self.url_open("/georutex/acceso")
        self.assertEqual(page.status_code, 200)
        csrf_token = self._extract_csrf(page.text)

        resp = self.url_open(
            "/georutex/acceso",
            data={
                "csrf_token": csrf_token,
                "login": "no.existe.jam@uta.edu.ec",
                "password": "TestPassword!2026",
            },
            allow_redirects=False,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("No existe una cuenta registrada", resp.text)

    def test_03_signup_otp_verification_and_login_to_web(self):
        """POST /georutex/registro-conductor requires 6-digit OTP then activates login to /web."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        page = self.url_open("/georutex/registro-conductor")
        self.assertEqual(page.status_code, 200)
        csrf_token = self._extract_csrf(page.text)

        # Weak password (letters only) must be rejected
        bad_resp = self.url_open(
            "/georutex/registro-conductor",
            data={
                "csrf_token": csrf_token,
                "login": "conductor.debil@uta.edu.ec",
                "name": "Carlos Méndez",
                "password": "SoloLetrasPassword",
                "confirm_password": "SoloLetrasPassword",
                "redirect": "",
            },
            allow_redirects=False,
        )
        self.assertEqual(bad_resp.status_code, 200)
        self.assertIn("La contraseña no es segura", bad_resp.text)

        # Valid registration redirects to /georutex/verificar-correo
        email = "conductor.http.otp@uta.edu.ec"
        csrf_token_2 = self._extract_csrf(bad_resp.text)
        reg_resp = self.url_open(
            "/georutex/registro-conductor",
            data={
                "csrf_token": csrf_token_2,
                "login": email,
                "name": "Carlos Méndez",
                "password": "TestPassword!2026",
                "confirm_password": "TestPassword!2026",
                "redirect": "",
            },
            allow_redirects=False,
        )
        self.assertEqual(reg_resp.status_code, 303)
        self.assertIn(
            "/georutex/verificar-correo", reg_resp.headers.get("Location", "")
        )

        # User is inactive until 6-digit numeric code is verified
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("login", "=", email)], limit=1)
        )
        self.assertTrue(user)
        self.assertFalse(user.active)

        # Create a known 6-digit code via ORM to test verification endpoint cleanly
        otp_rec, plain_code = self.env[
            "transport.email.verification"
        ].create_and_send_otp(user, email, user.name)
        self.assertEqual(len(plain_code), 6)
        self.assertTrue(plain_code.isdigit())
        self.assertIn(
            otp_rec.delivery_status,
            ("sent", "smtp_not_configured", "failed"),
        )

        # Open verification page and submit the 6-digit code
        verify_page = self.url_open(f"/georutex/verificar-correo?email={email}")
        self.assertEqual(verify_page.status_code, 200)
        verify_csrf = self._extract_csrf(verify_page.text)

        verify_resp = self.url_open(
            "/georutex/verificar-correo",
            data={
                "csrf_token": verify_csrf,
                "email": email,
                "code": plain_code,
            },
            allow_redirects=False,
        )
        self.assertEqual(verify_resp.status_code, 303)
        self.assertIn(
            "/georutex/acceso", verify_resp.headers.get("Location", "")
        )

        # Login with verified driver redirects to /web (NEVER /web/login_successful)
        login_page = self.url_open(verify_resp.headers["Location"])
        self.assertEqual(login_page.status_code, 200)
        login_csrf = self._extract_csrf(login_page.text)
        login_resp = self.url_open(
            "/georutex/acceso",
            data={
                "csrf_token": login_csrf,
                "login": email,
                "password": "TestPassword!2026",
            },
            allow_redirects=False,
        )
        self.assertEqual(login_resp.status_code, 303)
        location = login_resp.headers.get("Location", "")
        self.assertNotIn("/web/login_successful", location)
        self.assertTrue(
            location.endswith("/web") or "/web?" in location,
            f"Expected redirect to /web, got: {location}",
        )
