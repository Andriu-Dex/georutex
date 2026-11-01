/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class LiveFleetMapAction extends Component {
    static template = "uta_transport_monitor.LiveFleetMapAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("liveMapContainer");
        this.map = null;
        this.markers = {};
        this.refreshTimer = null;

        this.state = useState({
            vehicles: [],
            filter: "all", // all, fresh, stale, offline
            selectedVehicleId: null,
            isLoading: false,
            autoRefresh: true,
            lastUpdated: "",
        });

        onMounted(() => {
            this.initMap();
            this.loadFleetData();
            if (this.state.autoRefresh) {
                this.startAutoRefresh();
            }
        });

        onWillUnmount(() => {
            this.stopAutoRefresh();
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    initMap() {
        if (!this.mapRef.el || this.map) return;
        if (typeof window.L === "undefined") {
            console.error("Leaflet library not loaded");
            return;
        }

        // Center default at Ambato, Ecuador
        this.map = window.L.map(this.mapRef.el).setView([-1.249, -78.625], 13);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        this.refreshTimer = setInterval(() => {
            if (this.state.autoRefresh) {
                this.loadFleetData(false);
            }
        }, 30000); // 30 seconds interval
    }

    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    toggleAutoRefresh() {
        this.state.autoRefresh = !this.state.autoRefresh;
        if (this.state.autoRefresh) {
            this.startAutoRefresh();
        } else {
            this.stopAutoRefresh();
        }
    }

    async loadFleetData(showNotice = false) {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call("fleet.vehicle", "get_live_fleet_positions", []);
            this.state.vehicles = data || [];
            this.state.lastUpdated = new Date().toLocaleTimeString();
            this.updateMarkers();
            if (showNotice) {
                this.notification.add("Datos de flota actualizados correctamente", { type: "info" });
            }
        } catch (error) {
            console.error("Error loading live fleet data:", error);
        } finally {
            this.state.isLoading = false;
        }
    }

    get filteredVehicles() {
        if (this.state.filter === "all") {
            return this.state.vehicles;
        }
        return this.state.vehicles.filter((v) => v.freshness === this.state.filter);
    }

    updateMarkers() {
        if (!this.map) return;

        // Remove old markers
        Object.keys(this.markers).forEach((vId) => {
            this.markers[vId].remove();
            delete this.markers[vId];
        });

        const bounds = [];

        this.filteredVehicles.forEach((v) => {
            if (!v.has_coordinates) return;
            const pos = [v.latitude, v.longitude];
            bounds.push(pos);

            const busIcon = window.L.divIcon({
                className: "custom-div-icon",
                html: `
                    <div class="georutex-live-bus-marker ${v.freshness}">
                        <i class="fa fa-bus" style="font-size: 14px;"></i>
                        <div class="georutex-pulse-ring"></div>
                    </div>
                `,
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            });

            const marker = window.L.marker(pos, { icon: busIcon }).addTo(this.map);
            marker.bindPopup(`
                <div style="font-size: 12px; line-height: 1.4;">
                    <strong style="font-size: 13px;">${v.name}</strong><br/>
                    <b>Placa:</b> ${v.license_plate || "S/P"}<br/>
                    <b>Conductor:</b> ${v.driver_name}<br/>
                    <b>Velocidad:</b> ${v.speed} km/h<br/>
                    <b>Hora local:</b> ${v.fix_time_local}<br/>
                    <b>Estado de señal:</b> <span class="badge ${v.freshness === 'fresh' ? 'bg-success' : 'bg-warning'}">${v.freshness.toUpperCase()}</span><br/>
                    <b>Tipo:</b> ${v.is_simulated ? "Simulado" : (v.is_physical_accredited ? "Real Acreditado" : "No Acreditado")}
                </div>
            `);

            this.markers[v.vehicle_id] = marker;
        });

        if (bounds.length > 0 && !this.state.selectedVehicleId) {
            this.map.fitBounds(bounds, { padding: [40, 40] });
        }
    }

    selectVehicle(vehicle) {
        this.state.selectedVehicleId = vehicle.vehicle_id;
        if (!this.map || !vehicle.has_coordinates) return;

        const pos = [vehicle.latitude, vehicle.longitude];
        this.map.setView(pos, 16, { animate: true });

        const marker = this.markers[vehicle.vehicle_id];
        if (marker) {
            marker.openPopup();
        }
    }

    setFilter(filterName) {
        this.state.filter = filterName;
        this.updateMarkers();
    }
}

registry.category("actions").add("uta_transport_live_fleet_map", LiveFleetMapAction);

