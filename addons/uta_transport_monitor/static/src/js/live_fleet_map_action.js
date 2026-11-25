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
        this._driverRouteLayer = null;
        this._hasFittedOnce = false;
        this.refreshTimer = null;

        this._onWindowResize = () => {
            if (this.map) {
                this.map.invalidateSize({ pan: false });
            }
        };

        this.state = useState({
            vehicles: [],
            driverTrip: null,
            driverVehicles: [],
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
            const promises = [
                this.orm.call("fleet.vehicle", "get_live_fleet_positions", []),
            ];
            if (this.isDriverOnly) {
                promises.push(this.orm.call("transport.trip", "get_driver_home_data", []));
            }
            const [data, driverPayload] = await Promise.all(promises);
            this.state.vehicles = data || [];
            if (driverPayload) {
                this.state.driverTrip = driverPayload.featured_trip || null;
                this.state.driverVehicles = driverPayload.vehicles || [];
            }
            this.state.lastUpdated = new Date().toLocaleTimeString();
            this.state.hasLoadError = false;
            this.updateMarkers();
            if (this.isDriverOnly) {
                this._renderDriverRouteOverlay();
            }
            if (showNotice) {
                this.notification.add("Posiciones actualizadas.", {
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

    formatSpeed(v) {
        if (!v || !v.has_coordinates || (v.freshness !== "fresh" && v.freshness !== "online")) {
            return "Sin datos";
        }
        return `${Math.round(v.speed || 0)} km/h`;
    }

    get driverPrimaryVehicle() {
        return this.state.driverVehicles.length ? this.state.driverVehicles[0] : (this.state.vehicles[0] || null);
    }

    get driverConnectivityLabel() {
        const v = this.driverPrimaryVehicle;
        if (!v) return "Sin unidad vinculada";
        if (v.freshness === "fresh" || v.freshness === "online") return "GPS en línea";
        if (v.freshness === "stale") return "Señal reciente (histórica)";
        return "Sin señal GPS";
    }

    get driverSpeedDisplay() {
        const v = this.driverPrimaryVehicle;
        if (v && (v.freshness === "fresh" || v.freshness === "online") && v.has_speed) {
            return `${Math.round(v.speed || 0)} km/h`;
        }
        return "Sin datos";
    }

    get driverLastFixLabel() {
        const v = this.driverPrimaryVehicle;
        if (!v) return "Sin registro";
        return v.last_gps_time_local || v.fix_time_local || "Sin registro";
    }

    get hasAnyMapGeometry() {
        if (this.positionedCount > 0) return true;
        const ft = this.state.driverTrip;
        return Boolean(ft && (ft.stops || []).some((s) => s.has_coords));
    }

    _renderDriverRouteOverlay() {
        if (!this.map || typeof window.L === "undefined") return;
        if (this._driverRouteLayer) {
            this.map.removeLayer(this._driverRouteLayer);
            this._driverRouteLayer = null;
        }
        const ft = this.state.driverTrip;
        if (!ft) return;
        const layer = window.L.layerGroup().addTo(this.map);
        this._driverRouteLayer = layer;
        const boundsPts = [];
        const stopPts = [];

        (ft.stops || []).forEach((st) => {
            if (!st.has_coords) return;
            const latlng = [Number(st.latitude), Number(st.longitude)];
            stopPts.push(latlng);
            boundsPts.push(latlng);
            const isNext = !st.visited && st.order === ft.next_stop_order;
            const color = st.visited ? "#15803d" : (isNext ? "#1854e6" : "#64748b");
            const marker = window.L.circleMarker(latlng, {
                radius: isNext ? 9 : 7,
                color: "#ffffff",
                weight: 2,
                fillColor: color,
                fillOpacity: 1,
            }).addTo(layer);
            marker.bindTooltip(`${st.order}. ${st.name}`);
        });

        if (Array.isArray(ft.planned_path) && ft.planned_path.length > 1) {
            window.L.polyline(ft.planned_path, {
                color: "#1854e6",
                weight: 4,
                opacity: 0.78,
                dashArray: "7 6",
            }).addTo(layer);
            ft.planned_path.forEach((p) => boundsPts.push(p));
        } else if (stopPts.length > 1) {
            window.L.polyline(stopPts, {
                color: "#1854e6",
                weight: 3.5,
                opacity: 0.75,
                dashArray: "7 6",
            }).addTo(layer);
        }

        if (Array.isArray(ft.recorded_path) && ft.recorded_path.length > 1) {
            window.L.polyline(ft.recorded_path, {
                color: "#06b6d4",
                weight: 4,
                opacity: 0.9,
            }).addTo(layer);
            ft.recorded_path.forEach((p) => boundsPts.push(p));
        }

        if (boundsPts.length && !this._hasFittedOnce) {
            this.map.fitBounds(window.L.latLngBounds(boundsPts), { padding: [36, 36], maxZoom: 15 });
            this._hasFittedOnce = true;
        }
    }

    focusDriverStop(st) {
        if (!this.map || !st || !st.has_coords) return;
        this.map.setView([Number(st.latitude), Number(st.longitude)], 16, { animate: true });
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
