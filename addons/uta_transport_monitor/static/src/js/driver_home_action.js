/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class GeoRutexDriverHomeAction extends Component {
    static template = "uta_transport_monitor.GeoRutexDriverHomeAction";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            isLoading: true,
            error: "",
            driverName: "",
            driverEmail: "",
            localDateLabel: "",
            localTimeLabel: "",
            stats: {
                total_trips: 0,
                active_trips: 0,
                completed_trips: 0,
                pending_incidents: 0,
                total_incidents: 0,
            },
            vehicles: [],
            trips: [],
            incidents: [],
        });

        onMounted(() => {
            void this.loadDriverHome(false);
        });
    }

    async loadDriverHome(showNotice = false) {
        this.state.isLoading = true;
        this.state.error = "";
        try {
            const payload = await this.orm.call(
                "transport.trip",
                "get_driver_home_data",
                []
            );
            this.state.driverName = payload.driver_name || "Conductor";
            this.state.driverEmail = payload.driver_email || "";
            this.state.localDateLabel = payload.local_date_label || "";
            this.state.localTimeLabel = payload.local_time_label || "";
            this.state.stats = payload.stats || this.state.stats;
            this.state.vehicles = payload.vehicles || [];
            this.state.trips = payload.trips || [];
            this.state.incidents = payload.incidents || [];
            if (showNotice) {
                this.notification.add("Panel del conductor actualizado.", {
                    type: "info",
                    sticky: false,
                });
            }
        } catch (err) {
            console.error("GeoRutexDriverHome load error:", err);
            this.state.error =
                "No se pudieron cargar los datos de tu jornada. Intenta actualizar.";
        } finally {
            this.state.isLoading = false;
        }
    }

    openNewIncident(tripId = false) {
        const context = { default_source: "manual" };
        if (tripId) {
            context.default_trip_id = tripId;
        }
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Nueva Incidencia Operacional",
            res_model: "transport.incident",
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
            context,
        });
    }

    openAllIncidents() {
        this.actionService.doAction(
            "uta_transport_monitor.action_transport_incident"
        );
    }

    openIncidentDetail(incidentId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Incidencia Operacional",
            res_model: "transport.incident",
            res_id: incidentId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    openMyTrips() {
        this.actionService.doAction(
            "uta_transport_monitor.action_transport_trip_my_driver"
        );
    }

    openTripDetail(tripId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Detalle del Recorrido",
            res_model: "transport.trip",
            res_id: tripId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    openLiveMap() {
        this.actionService.doAction(
            "uta_transport_monitor.action_transport_live_fleet_map"
        );
    }

    getStateBadgeClass(stateCode) {
        const map = {
            draft: "bg-secondary",
            scheduled: "bg-primary",
            in_progress: "bg-info text-dark",
            completed: "bg-dark",
            cancelled: "bg-secondary",
        };
        return map[stateCode] || "bg-secondary";
    }

    getSeverityBadgeClass(sev) {
        const map = {
            critical: "bg-danger",
            high: "bg-danger",
            medium: "bg-warning text-dark",
            low: "bg-info text-dark",
        };
        return map[sev] || "bg-secondary";
    }
}

registry
    .category("actions")
    .add("uta_transport_driver_home", GeoRutexDriverHomeAction);
