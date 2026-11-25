/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class LiveFleetMapAction extends Component {
    static template = "uta_transport_monitor.LiveFleetMapAction";

    get isDriverOnly() {
        return Boolean(session.georutex_is_driver_only);
    }

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("liveMapContainer");
        this.map = null;
        this.markers = {};
        this.refreshTimer = null;

        this._onWindowResize = () => {
            if (this.map) {
                this.map.invalidateSize({ pan: false });
            }
        };

        this.state = useState({
            vehicles: [],
            filter: "all",
            search: "",
            selectedVehicleId: null,
            isLoading: false,
            autoRefresh: true,
            lastUpdated: "",
            hasLoadError: false,
        });

        onMounted(() => {
            this.initMap();
            void this.loadFleetData();
            if (this.state.autoRefresh) {
                this.startAutoRefresh();
            }
            window.addEventListener("resize", this._onWindowResize);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onWindowResize);
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

        this.map = window.L.map(this.mapRef.el).setView([-1.249, -78.625], 13);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);
        window.setTimeout(() => {
            if (this.map) this.map.invalidateSize();
        }, 160);
    }

    startAutoRefresh() {
        this.stopAutoRefresh();
        this.refreshTimer = setInterval(() => {
            if (this.state.autoRefresh) {
                void this.loadFleetData(false);
            }
        }, 30000);
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
            this.state.hasLoadError = false;
            this.updateMarkers();
            if (showNotice) {
                this.notification.add("Posiciones de flota actualizadas.", {
                    type: "info",
                    sticky: false,
                });
            }
        } catch (error) {
            console.error("Error loading live fleet data:", error);
            if (!this.state.hasLoadError) {
                this.notification.add("No se pudieron cargar las posiciones GPS.", {
                    type: "danger",
                    sticky: false,
                });
            }
            this.state.hasLoadError = true;
        } finally {
            this.state.isLoading = false;
        }
    }

    get filteredVehicles() {
        let list = this.state.vehicles || [];
        if (this.state.filter === "fresh") {
            list = list.filter((v) => v.freshness === "fresh" || v.freshness === "online");
        } else if (this.state.filter === "stale") {
            list = list.filter((v) => v.freshness === "stale");
        } else if (this.state.filter === "offline") {
            list = list.filter((v) => v.freshness !== "fresh" && v.freshness !== "online" && v.freshness !== "stale");
        }
        const q = (this.state.search || "").trim().toLowerCase();
        if (q) {
            list = list.filter((v) =>
                [v.name, v.license_plate, v.driver_name]
                    .filter(Boolean)
                    .some((f) => String(f).toLowerCase().includes(q))
            );
        }
        return list;
    }

    get positionedCount() {
        return this.filteredVehicles.filter((v) => v.has_coordinates).length;
    }

    _escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    updateMarkers() {
        if (!this.map || typeof window.L === "undefined") return;

        Object.keys(this.markers).forEach((vId) => {
            this.markers[vId].remove();
            delete this.markers[vId];
        });

        const bounds = [];

        this.filteredVehicles.forEach((v) => {
            if (!v.has_coordinates) return;
            const pos = [Number(v.latitude), Number(v.longitude)];
            if (!Number.isFinite(pos[0]) || !Number.isFinite(pos[1])) return;
            bounds.push(pos);

            const statusCls =
                v.freshness === "fresh" || v.freshness === "online"
                    ? "fresh"
                    : v.freshness === "stale"
                    ? "stale"
                    : "offline";

            const busIcon = window.L.divIcon({
                className: "custom-div-icon",
                html: `
                    <div class="georutex-live-bus-marker ${statusCls}">
                        ${statusCls === "fresh" ? '<div class="georutex-pulse-ring"></div>' : ""}
                        <i class="fa fa-bus" style="font-size: 15px;"></i>
                    </div>
                `,
                iconSize: [36, 36],
                iconAnchor: [18, 18],
            });

            const marker = window.L.marker(pos, { icon: busIcon }).addTo(this.map);
            const sourceLabel = v.is_simulated
                ? "Simulado"
                : v.is_physical_accredited
                ? "Real acreditado"
                : "No acreditado";
            const statusLabel =
                statusCls === "fresh" ? "En línea" : statusCls === "stale" ? "Reciente" : "Sin señal";

            marker.bindPopup(`
                <div style="font-size: 13px; line-height: 1.45;">
                    <strong style="font-size: 14px;">${this._escapeHtml(v.name)}</strong><br/>
                    <b>Placa:</b> ${this._escapeHtml(v.license_plate || "S/P")}<br/>
                    <b>Conductor:</b> ${this._escapeHtml(v.driver_name)}<br/>
                    <b>Velocidad:</b> ${Math.round(Number(v.speed) || 0)} km/h<br/>
                    <b>Último reporte:</b> ${this._escapeHtml(v.fix_time_local)}<br/>
                    <b>Señal:</b> ${statusLabel} · <b>Origen:</b> ${sourceLabel}
                </div>
            `);

            this.markers[v.vehicle_id] = marker;
        });

        if (bounds.length > 0 && !this.state.selectedVehicleId) {
            this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
        }
    }

    recenterAll() {
        this.state.selectedVehicleId = null;
        this.updateMarkers();
    }

    selectVehicle(vehicle) {
        this.state.selectedVehicleId = vehicle.vehicle_id;
        if (!this.map || !vehicle.has_coordinates) {
            this.notification.add(`${vehicle.name} aún no tiene coordenadas registradas.`, {
                type: "info",
                sticky: false,
            });
            return;
        }

        const pos = [Number(vehicle.latitude), Number(vehicle.longitude)];
        this.map.flyTo(pos, 16, { duration: 0.65 });

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
