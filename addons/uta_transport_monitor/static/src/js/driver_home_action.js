/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { runGeorutexEntrance } from "./georutex_motion";

export class GeoRutexDriverHomeAction extends Component {
    static template = "uta_transport_monitor.GeoRutexDriverHomeAction";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.rootRef = useRef("driverHomeRoot");
        this.mapRef = useRef("driverMapCanvas");

        this._map = null;
        this._layerGroup = null;
        this._stopMarkers = new Map();
        this._refreshTimer = null;
        this._revertMotion = null;
        this._hasFittedMap = false;

        this.state = useState({
            isLoading: true,
            isTransitioning: false,
            error: "",
            driverName: "",
            driverEmail: "",
            localDateLabel: "",
            localTimeLabel: "",
            tripFilter: "all",
            selectedStopId: null,
            stats: {
                total_trips: 0,
                active_trips: 0,
                completed_trips: 0,
                pending_incidents: 0,
                total_incidents: 0,
            },
            featuredTrip: null,
            vehicles: [],
            trips: [],
            incidents: [],
        });

        onMounted(async () => {
            this._initMap();
            await this.loadDriverHome(false);
            this._revertMotion = runGeorutexEntrance(this.rootRef.el, [
                { selector: ".drv-stat-tile", y: 12, duration: 0.38, stagger: 0.04 },
            ]);
            this._refreshTimer = window.setInterval(() => {
                void this.loadDriverHome(false, true);
            }, 30000);
        });

        onWillUnmount(() => {
            if (this._refreshTimer) {
                window.clearInterval(this._refreshTimer);
                this._refreshTimer = null;
            }
            if (this._revertMotion) {
                this._revertMotion();
                this._revertMotion = null;
            }
            if (this._map) {
                this._map.remove();
                this._map = null;
                this._layerGroup = null;
                this._stopMarkers.clear();
            }
        });
    }

    get primaryVehicle() {
        return this.state.vehicles.length ? this.state.vehicles[0] : null;
    }

    get gpsStatusInfo() {
        const v = this.primaryVehicle;
        if (!v) {
            return { label: "Sin unidad vinculada", dot: "is-amber", tone: "is-muted", lastFix: "Sin registro" };
        }
        if (v.freshness === "online" || v.freshness === "fresh") {
            return { label: "GPS En vivo", dot: "is-green is-animated", tone: "is-green", lastFix: v.last_gps_time_local };
        }
        if (v.freshness === "stale") {
            return { label: "Señal reciente", dot: "is-amber", tone: "is-amber", lastFix: v.last_gps_time_local };
        }
        return { label: "Sin señal GPS", dot: "is-red", tone: "is-red", lastFix: v.last_gps_time_local };
    }

    get currentSpeedDisplay() {
        if (this.state.featuredTrip && this.state.featuredTrip.vehicle_speed_display !== "N/A") {
            return this.state.featuredTrip.vehicle_speed_display;
        }
        const v = this.primaryVehicle;
        if (v && v.has_speed) {
            return `${v.speed} km/h`;
        }
        return "N/A";
    }

    get filteredTrips() {
        const list = this.state.trips || [];
        if (this.state.tripFilter === "active") {
            return list.filter((t) => t.state === "in_progress" || t.state === "scheduled");
        }
        if (this.state.tripFilter === "completed") {
            return list.filter((t) => t.state === "completed");
        }
        return list;
    }

    get hasMapPoints() {
        const ft = this.state.featuredTrip;
        const v = this.primaryVehicle;
        const hasStops = Boolean(ft && (ft.stops || []).some((s) => s.has_coords));
        const hasVeh = Boolean((ft && ft.vehicle_has_coords) || (v && v.has_coordinates));
        return hasStops || hasVeh;
    }

    _initMap() {
        if (!this.mapRef.el || typeof window.L === "undefined") return;
        this._map = window.L.map(this.mapRef.el, {
            zoomControl: true,
            attributionControl: true,
        }).setView([-1.249, -78.625], 13);

        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this._map);

        this._layerGroup = window.L.layerGroup().addTo(this._map);
        window.setTimeout(() => {
            if (this._map) this._map.invalidateSize();
        }, 180);
    }

    _renderMap() {
        if (!this._map || !this._layerGroup || typeof window.L === "undefined") return;
        this._layerGroup.clearLayers();
        this._stopMarkers.clear();

        const boundsPts = [];
        const ft = this.state.featuredTrip;

        // 1. Reference route polyline
        if (ft && Array.isArray(ft.reference_polyline) && ft.reference_polyline.length >= 2) {
            window.L.polyline(ft.reference_polyline, {
                color: "#066fd1",
                weight: 4,
                opacity: 0.85,
            }).addTo(this._layerGroup);
            ft.reference_polyline.forEach((pt) => boundsPts.push(pt));
        }

        // 2. Route checkpoints
        if (ft && Array.isArray(ft.stops)) {
            ft.stops.forEach((st) => {
                if (!st.has_coords) return;
                const lat = Number(st.latitude);
                const lon = Number(st.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
                const cls = st.visited
                    ? "georutex-stop-marker georutex-stop-origin"
                    : st.order === ft.next_stop_order
                    ? "georutex-stop-marker"
                    : "georutex-stop-marker";
                const icon = window.L.divIcon({
                    className: "custom-div-icon",
                    html: `<div class="${cls}" style="${st.visited ? "" : st.order === ft.next_stop_order ? "background:#066fd1;" : "background:#64748b;"}">${st.order}</div>`,
                    iconSize: [28, 28],
                    iconAnchor: [14, 14],
                });
                const marker = window.L.marker([lat, lon], { icon }).addTo(this._layerGroup);
                marker.bindPopup(
                    `<strong>${st.order}. ${st.name}</strong><br/>` +
                    `<span>${st.visited ? `Visitada (${st.arrival_local || "OK"})` : "Pendiente de paso"}</span>`
                );
                this._stopMarkers.set(st.id, marker);
                boundsPts.push([lat, lon]);
            });
        }

        // 3. Assigned vehicle live position
        const vehLat = ft && ft.vehicle_has_coords ? Number(ft.vehicle_lat) : (this.primaryVehicle && this.primaryVehicle.has_coordinates ? Number(this.primaryVehicle.latitude) : null);
        const vehLon = ft && ft.vehicle_has_coords ? Number(ft.vehicle_lon) : (this.primaryVehicle && this.primaryVehicle.has_coordinates ? Number(this.primaryVehicle.longitude) : null);
        if (vehLat !== null && vehLon !== null && Number.isFinite(vehLat) && Number.isFinite(vehLon)) {
            const busIcon = window.L.divIcon({
                className: "custom-div-icon",
                html: '<div class="georutex-live-bus-marker fresh"><div class="georutex-pulse-ring"></div><i class="fa fa-bus"></i></div>',
                iconSize: [36, 36],
                iconAnchor: [18, 18],
            });
            const m = window.L.marker([vehLat, vehLon], { icon: busIcon }).addTo(this._layerGroup);
            const vName = (this.primaryVehicle && this.primaryVehicle.name) || (ft && ft.vehicle_name) || "Mi Unidad";
            m.bindPopup(`<strong>${vName}</strong><br/><span>Velocidad: ${this.currentSpeedDisplay}</span>`);
            boundsPts.push([vehLat, vehLon]);
        }

        if (boundsPts.length && !this._hasFittedMap) {
            this._map.fitBounds(window.L.latLngBounds(boundsPts), { padding: [32, 32], maxZoom: 15 });
            this._hasFittedMap = true;
        }
    }

    focusStop(stop) {
        this.state.selectedStopId = stop.id;
        if (!this._map || !stop.has_coords) return;
        this._map.flyTo([Number(stop.latitude), Number(stop.longitude)], 16, { duration: 0.7 });
        const marker = this._stopMarkers.get(stop.id);
        if (marker) marker.openPopup();
    }

    recenterMap() {
        this._hasFittedMap = false;
        this._renderMap();
    }

    async loadDriverHome(showNotice = false, silent = false) {
        if (!silent) {
            this.state.isLoading = true;
            this.state.error = "";
        }
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
            this.state.featuredTrip = payload.featured_trip || null;
            this.state.vehicles = payload.vehicles || [];
            this.state.trips = payload.trips || [];
            this.state.incidents = payload.incidents || [];
            this.state.error = "";

            this._renderMap();

            if (showNotice) {
                this.notification.add("Jornada operativa actualizada.", {
                    type: "info",
                    sticky: false,
                });
            }
        } catch (err) {
            console.error("GeoRutexDriverHome load error:", err);
            const msg = String((err && err.message) || "");
            if (msg.toLowerCase().includes("session") || (err && err.name === "SessionExpiredError")) {
                window.location.href = "/georutex/acceso";
                return;
            }
            if (!silent) {
                this.state.error =
                    "No se pudo conectar con el servidor para cargar tu jornada. Reintenta en unos segundos.";
            }
        } finally {
            if (!silent) {
                this.state.isLoading = false;
            }
        }
    }

    async transitionTrip(tripId, targetAction) {
        if (this.state.isTransitioning) return;
        this.state.isTransitioning = true;
        try {
            await this.orm.call(
                "transport.trip",
                "action_driver_transition_trip",
                [tripId, targetAction]
            );
            this.notification.add(
                targetAction === "start"
                    ? "Recorrido iniciado correctamente."
                    : "Recorrido finalizado correctamente.",
                { type: "success", sticky: false }
            );
            await this.loadDriverHome(false);
        } catch (err) {
            console.error("GeoRutexDriverHome transition error:", err);
            this.notification.add(
                "No se pudo cambiar el estado del recorrido.",
                { type: "danger", sticky: false }
            );
        } finally {
            this.state.isTransitioning = false;
        }
    }

    openNewIncident(tripId = false) {
        const context = { default_source: "manual" };
        if (tripId) context.default_trip_id = tripId;
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
        this.actionService.doAction("uta_transport_monitor.action_transport_incident");
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
        this.actionService.doAction("uta_transport_monitor.action_transport_trip_my_driver");
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
        this.actionService.doAction("uta_transport_monitor.action_transport_live_fleet_map");
    }

    getStateBadgeClass(stateCode) {
        const map = {
            draft: "is-muted",
            scheduled: "is-blue",
            in_progress: "is-amber",
            completed: "is-green",
            cancelled: "is-muted",
        };
        return map[stateCode] || "is-muted";
    }

    getSeverityBadgeClass(sev) {
        const map = {
            critical: "is-red",
            high: "is-red",
            medium: "is-amber",
            low: "is-blue",
        };
        return map[sev] || "is-muted";
    }
}

registry
    .category("actions")
    .add("uta_transport_driver_home", GeoRutexDriverHomeAction);
