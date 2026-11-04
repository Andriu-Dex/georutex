"""Unit and ORM tests for route editor, stop types, and approval validation."""

import json
from unittest.mock import patch
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from ..services.routing_service import RoutingService


@tagged("post_install", "-at_install", "transport_route")
class TestRouteEditorAndStopTypes(TransactionCase):
    """Test suite verifying stop classification, road routing, and approval validation."""

    def setUp(self):
        super().setUp()
        self.route_model = self.env["transport.route"]
        self.version_model = self.env["transport.route.version"]
        self.stop_model = self.env["transport.route.stop"]

        self.route = self.route_model.create({
            "name": "Ruta de Prueba Editor Cartográfico",
            "code": "RUT-EDITOR-01",
            "origin_name": "Campus Huachi",
            "destination_name": "Campus Querochaca",
            "direction": "outbound",
        })

        self.version = self.version_model.create({
            "route_id": self.route.id,
            "version_number": 1,
            "stop_radius_m": 30.0,
            "route_corridor_m": 40.0,
            "lateness_tolerance_s": 300,
            "gps_gap_threshold_s": 180,
        })

    def test_01_stop_type_editable_in_draft(self):
        """Verify stop types are freely editable in draft mode."""
        stop1 = self.stop_model.create({
            "route_version_id": self.version.id,
            "sequence": 10,
            "name": "Parada Inicial",
            "latitude": -1.2618,
            "longitude": -78.6272,
            "stop_type": "origin",
        })
        self.assertEqual(stop1.stop_type, "origin")

        # Edit type to checkpoint
        stop1.with_context(skip_auto_classify=True).write({
            "stop_type": "checkpoint"
        })
        self.assertEqual(stop1.stop_type, "checkpoint")

        # Edit back to origin
        stop1.with_context(skip_auto_classify=True).write({
            "stop_type": "origin"
        })
        self.assertEqual(stop1.stop_type, "origin")

    def test_02_stop_type_auto_classification(self):
        """Verify auto-classification sets 1st=origin, last=dest, middle=checkpoint."""
        stops = []
        coords = [
            (-1.2618, -78.6272),
            (-1.2580, -78.6250),
            (-1.2425, -78.6265),
            (-1.2335, -78.6225),
        ]
        for i, (lat, lon) in enumerate(coords, start=1):
            s = self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": lat,
                "longitude": lon,
            })
            stops.append(s)

        # Trigger explicit auto-classification action
        action_res = self.version.action_auto_classify_stops()
        self.assertEqual(action_res["type"], "ir.actions.client")

        sorted_stops = self.version.stop_ids.sorted("sequence")
        self.assertEqual(sorted_stops[0].stop_type, "origin")
        self.assertEqual(sorted_stops[1].stop_type, "checkpoint")
        self.assertEqual(sorted_stops[2].stop_type, "checkpoint")
        self.assertEqual(sorted_stops[3].stop_type, "destination")

    def test_03_reordering_and_deletion_auto_classification(self):
        """Verify deleting or reordering points preserves coherent classification."""
        coords = [
            (-1.2618, -78.6272),
            (-1.2580, -78.6250),
            (-1.2425, -78.6265),
            (-1.2335, -78.6225),
            (-1.2200, -78.6200),
        ]
        stops = []
        for i, (lat, lon) in enumerate(coords, start=1):
            s = self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": lat,
                "longitude": lon,
            })
            stops.append(s)

        # Initial state: 5 stops. stops[0]=origin, stops[4]=destination
        self.assertEqual(stops[0].stop_type, "origin")
        self.assertEqual(stops[4].stop_type, "destination")

        # Delete the destination stop (Punto 5)
        stops[4].unlink()
        remaining = self.version.stop_ids.sorted("sequence")
        self.assertEqual(len(remaining), 4)
        # New last stop (Punto 4) should now be classified as destination
        self.assertEqual(remaining[-1].stop_type, "destination")
        self.assertEqual(remaining[0].stop_type, "origin")

    def test_04_approval_validation_failures(self):
        """Verify action_approve enforces all origin, destination, and checkpoint rules."""
        coords = [
            (-1.2618, -78.6272),
            (-1.2580, -78.6250),
            (-1.2425, -78.6265),
            (-1.2335, -78.6225),
        ]
        stops = []
        for i, (lat, lon) in enumerate(coords, start=1):
            s = self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": lat,
                "longitude": lon,
            })
            stops.append(s)

        # Case A: Intermediate point set to origin -> 2 origins
        stops[1].with_context(skip_auto_classify=True).write({
            "stop_type": "origin"
        })
        with self.assertRaises(ValidationError) as cm:
            self.version.action_approve()
        self.assertIn("exactamente 1 punto de tipo 'Origen'", str(cm.exception))

        # Reset stops[1] back to checkpoint
        stops[1].with_context(skip_auto_classify=True).write({
            "stop_type": "checkpoint"
        })

        # Case B: First point set to checkpoint -> 0 origins
        stops[0].with_context(skip_auto_classify=True).write({
            "stop_type": "checkpoint"
        })
        with self.assertRaises(ValidationError) as cm:
            self.version.action_approve()
        self.assertIn("exactamente 1 punto de tipo 'Origen'", str(cm.exception))

        # Case C: First point destination, last point origin -> Inverted
        stops[0].with_context(skip_auto_classify=True).write({
            "stop_type": "destination"
        })
        stops[3].with_context(skip_auto_classify=True).write({
            "stop_type": "origin"
        })
        with self.assertRaises(ValidationError) as cm:
            self.version.action_approve()
        self.assertIn("debe ser el primer punto", str(cm.exception))

        # Case D: Intermediate point set to destination -> 2 destinations
        self.version.auto_classify_stops()
        stops[2].with_context(skip_auto_classify=True).write({
            "stop_type": "destination"
        })
        with self.assertRaises(ValidationError) as cm:
            self.version.action_approve()
        self.assertIn("exactamente 1 punto de tipo 'Destino'", str(cm.exception))

    def test_05_approval_success_and_immutability(self):
        """Verify approval succeeds when valid and strictly freezes version."""
        coords = [
            (-1.2618, -78.6272),
            (-1.2580, -78.6250),
            (-1.2425, -78.6265),
            (-1.2335, -78.6225),
        ]
        for i, (lat, lon) in enumerate(coords, start=1):
            self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": i * 10,
                "name": f"Punto {i}",
                "latitude": lat,
                "longitude": lon,
            })
        self.version.auto_classify_stops()

        # Approval succeeds
        self.version.action_approve()
        self.assertEqual(self.version.state, "approved")
        self.assertTrue(self.version.reference_polyline)
        self.assertGreater(self.version.estimated_distance_m, 0.0)

        # Immutability: cannot modify stops on approved version
        with self.assertRaises(UserError):
            self.version.stop_ids[0].write({"name": "Modificación Ilegal"})

        with self.assertRaises(UserError):
            self.stop_model.create({
                "route_version_id": self.version.id,
                "sequence": 50,
                "name": "Punto Extra Ilegal",
                "latitude": -1.22,
                "longitude": -78.62,
            })

        with self.assertRaises(UserError):
            self.version.stop_ids[0].unlink()

        # Immutability: cannot modify frozen parameters
        with self.assertRaises(UserError):
            self.version.write({"route_corridor_m": 80.0})

    def test_06_decoupled_routing_service_and_fallback(self):
        """Verify RoutingService fallback on unreachable provider."""
        stops_data = [
            {"latitude": -1.2618, "longitude": -78.6272, "name": "P1"},
            {"latitude": -1.2580, "longitude": -78.6250, "name": "P2"},
            {"latitude": -1.2335, "longitude": -78.6225, "name": "P3"},
        ]

        # Call with invalid URL to simulate offline/failure
        result = RoutingService.calculate_road_route(
            stops_data=stops_data,
            provider_url="http://invalid-unreachable-osrm-host:9999",
            timeout=0.1,
            enabled=True,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["provider"], "direct_interpolation")
        self.assertEqual(len(result["coordinates"]), 3)
        # GeoJSON coordinates order must be [lon, lat]
        self.assertAlmostEqual(result["coordinates"][0][0], -78.6272)
        self.assertAlmostEqual(result["coordinates"][0][1], -1.2618)
        self.assertGreater(result["distance_m"], 1000.0)

    def test_07_route_editor_rpc_api(self):
        """Verify RPC methods exposed to Owl RouteEditorWidget."""
        data = self.version.get_route_editor_data()
        self.assertEqual(data["id"], self.version.id)
        self.assertTrue(data["is_draft"])
        self.assertEqual(len(data["stops"]), 0)

        # Add stop via editor API
        data_after_add = self.version.save_route_editor_stop({
            "name": "Parada Inicial RPC",
            "stop_type": "origin",
            "latitude": -1.2618,
            "longitude": -78.6272,
            "radius_m": 35.0,
            "planned_offset_seconds": 0,
            "required": True,
        })
        self.assertEqual(len(data_after_add["stops"]), 1)
        self.assertEqual(data_after_add["stops"][0]["name"], "Parada Inicial RPC")
        stop_id = data_after_add["stops"][0]["id"]

        # Add second stop
        data2 = self.version.save_route_editor_stop({
            "name": "Parada Final RPC",
            "stop_type": "destination",
            "latitude": -1.2335,
            "longitude": -78.6225,
            "radius_m": 30.0,
            "planned_offset_seconds": 600,
            "required": True,
        })
        self.assertEqual(len(data2["stops"]), 2)

        # Delete first stop
        data3 = self.version.delete_route_editor_stop(stop_id)
        self.assertEqual(len(data3["stops"]), 1)

