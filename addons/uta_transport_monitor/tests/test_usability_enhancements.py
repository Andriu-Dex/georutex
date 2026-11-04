"""Tests for usability enhancements across the operational flow."""

from datetime import datetime
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "transport_usability")
class TestUsabilityEnhancements(TransactionCase):
    """Verify stop minutes conversion, driver autofill, availability warnings, and justify wizard."""

    def setUp(self):
        super().setUp()
        self.route = self.env["transport.route"].create({
            "name": "Ruta Usabilidad Test",
            "code": "RUT-UX-001",
            "origin_name": "Origen UX",
            "destination_name": "Destino UX",
        })
        self.version = self.env["transport.route.version"].create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
            "estimated_distance_m": 5000.0,
        })
        # 4 stops per RF-10
        self.stop1 = self.env["transport.route.stop"].create({
            "route_version_id": self.version.id,
            "sequence": 10,
            "name": "Origen UX",
            "stop_type": "origin",
            "latitude": -1.250,
            "longitude": -78.620,
            "planned_offset_seconds": 0,
        })
        self.stop2 = self.env["transport.route.stop"].create({
            "route_version_id": self.version.id,
            "sequence": 20,
            "name": "Control 1 UX",
            "stop_type": "checkpoint",
            "latitude": -1.252,
            "longitude": -78.622,
            "planned_offset_seconds": 600,
        })
        self.stop3 = self.env["transport.route.stop"].create({
            "route_version_id": self.version.id,
            "sequence": 30,
            "name": "Control 2 UX",
            "stop_type": "checkpoint",
            "latitude": -1.254,
            "longitude": -78.624,
            "planned_offset_seconds": 1200,
        })
        self.stop4 = self.env["transport.route.stop"].create({
            "route_version_id": self.version.id,
            "sequence": 40,
            "name": "Destino UX",
            "stop_type": "destination",
            "latitude": -1.256,
            "longitude": -78.626,
            "planned_offset_seconds": 1800,
        })
        self.version.action_approve()
        self.driver_partner = self.env["res.partner"].create({
            "name": "Conductor Operativo UX",
            "is_company": False,
        })
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Mercedes UX"})
        model = self.env["fleet.vehicle.model"].create({
            "name": "Sprinter UX",
            "brand_id": brand.id,
        })
        self.vehicle = self.env["fleet.vehicle"].create({
            "model_id": model.id,
            "license_plate": "TBA-9999",
            "driver_id": self.driver_partner.id,
        })
        self.user_driver = self.env["res.users"].create({
            "name": "Usuario Conductor UX",
            "login": "driver_ux_test",
            "email": "driver_ux@uta.edu.ec",
            "partner_id": self.driver_partner.id,
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_driver").id])],
        })
        self.user_manager = self.env["res.users"].create({
            "name": "Usuario Gestor UX",
            "login": "manager_ux_test",
            "email": "manager_ux@uta.edu.ec",
            "groups_id": [(6, 0, [self.env.ref("uta_transport_monitor.group_transport_manager").id])],
        })

    def test_01_stop_minutes_offset_sync(self):
        """Verify planned_offset_minutes synchronizes bidirectionally with seconds."""
        v_draft = self.env["transport.route.version"].create({
            "route_id": self.route.id,
            "version_number": 2,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })
        stop = self.env["transport.route.stop"].create({
            "route_version_id": v_draft.id,
            "sequence": 10,
            "name": "Parada UX 1",
            "stop_type": "origin",
            "latitude": -1.25,
            "longitude": -78.62,
            "planned_offset_minutes": 18.0,
        })
        self.assertEqual(stop.planned_offset_seconds, 1080)
        self.assertEqual(stop.planned_offset_display, "18 min")

        # Update via seconds
        stop.write({"planned_offset_seconds": 1800})
        self.assertEqual(stop.planned_offset_minutes, 30.0)
        self.assertEqual(stop.planned_offset_display, "30 min")

        # Decimal minutes (24.5 min = 1470 s = 24 min 30 s)
        stop.write({"planned_offset_minutes": 24.5})
        self.assertEqual(stop.planned_offset_seconds, 1470)
        self.assertEqual(stop.planned_offset_display, "24 min 30 s")

    def test_02_trip_onchange_vehicle_driver_availability(self):
        """Verify vehicle onchange auto-assigns vehicle driver and warns on time conflicts."""
        # Existing trip
        t1 = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver_partner.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 4, 8, 0, 0),
            "scheduled_end_utc": datetime(2026, 11, 4, 8, 30, 0),
        })
        t1.action_schedule()

        # New draft trip with onchange simulation
        new_trip = self.env["transport.trip"].new({
            "vehicle_id": self.vehicle.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 4, 8, 15, 0),
            "scheduled_end_utc": datetime(2026, 11, 4, 8, 45, 0),
        })
        # Trigger vehicle onchange
        new_trip._onchange_vehicle_id()
        self.assertEqual(new_trip.driver_id.id, self.driver_partner.id)

        # Trigger availability warning
        res = new_trip._onchange_check_availability()
        self.assertIsNotNone(res)
        self.assertIn("warning", res)
        self.assertIn("Aviso de Disponibilidad", res["warning"]["title"])

    def test_03_incident_justify_wizard(self):
        """Verify quick incident justification wizard workflow."""
        trip = self.env["transport.trip"].create({
            "vehicle_id": self.vehicle.id,
            "driver_id": self.driver_partner.id,
            "driver_user_id": self.user_driver.id,
            "route_id": self.route.id,
            "route_version_id": self.version.id,
            "scheduled_start_utc": datetime(2026, 11, 4, 9, 0, 0),
        })
        trip.action_schedule()

        incident = self.env["transport.incident"].create({
            "trip_id": trip.id,
            "incident_type": "delay_start",
            "source": "automatic",
            "severity": "medium",
            "state": "pending",
            "description": "Salida demorada por tráfico en redondel",
        })

        # Launch wizard action
        act = incident.with_user(self.user_driver).action_open_justify_wizard()
        self.assertEqual(act["res_model"], "transport.incident.justify.wizard")

        # Fill and confirm wizard as driver
        wizard = self.env["transport.incident.justify.wizard"].with_user(self.user_driver).create({
            "incident_id": incident.id,
            "justification_category": "congestion",
            "justification_notes": "Avenida cerrada por operativo municipal de tránsito.",
        })
        wizard.action_confirm_justification()

        self.assertEqual(incident.state, "pending")
        self.assertIn("Congestión vehicular", incident.justification_notes)
        self.assertIn("Avenida cerrada por operativo", incident.justification_notes)
        self.assertEqual(incident.justification_submitted_by.id, self.user_driver.id)

        # Segregation of duties: driver CANNOT approve their own justification
        with self.assertRaises(AccessError):
            incident.with_user(self.user_driver).action_approve_justification()

        # Manager approves
        incident.with_user(self.user_manager).action_approve_justification()
        self.assertEqual(incident.state, "justified")
        self.assertEqual(incident.reviewed_by.id, self.user_manager.id)
