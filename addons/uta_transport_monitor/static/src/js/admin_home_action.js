/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { runGeorutexEntrance, animateGeorutexCounters } from "./georutex_motion";

export class GeoRutexAdminHomeAction extends Component {
    static template = "uta_transport_monitor.GeoRutexAdminHomeAction";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.drawer = useService("georutex_drawer");

        this.rootRef = useRef("adminHomeRoot");
        this.mapRef = useRef("adminMapCanvas");
        this.trendChartRef = useRef("adminTrendCanvas");

        this._map = null;
        this._markersLayer = null;
        this._markersById = new Map();
        this._trendChart = null;
        this._refreshTimer = null;
        this._revertMotion = null;
        this._revertCounters = null;
        this._hasCenteredMap = false;

        this._onWindowResize = () => {
            if (this._trendChart && typeof this._trendChart.resize === "function") {
                this._trendChart.resize();
            }
            if (this._map) {
                this._map.invalidateSize({ pan: false });
            }
        };

        this.state = useState({
            isLoading: true,
            isSyncing: false,
            error: "",
            userName: "",
            localDateLabel: "",
            localTimeLabel: "",
            vehicleFilter: "all",
            vehicleSearch: "",
            selectedVehicleId: null,
            incidentFilter: "all",
            tripFilter: "all",
            tripSearch: "",
            stats: {
                vehicles_total: 0,
                vehicles_tracked: 0,
                vehicles_online: 0,
                vehicles_stale: 0,
                vehicles_offline: 0,
                vehicles_simulated: 0,
                routes_active: 0,
                stops_total: 0,
                trips_today: 0,
                trips_active: 0,
                incidents_open: 0,
                incidents_critical: 0,
                positions_total: 0,
            },
            kpis: {
                mt01: { display_value: "N/A", value: null, sample_size: 0, is_na: true },
                mt02: { display_value: "N/A", value: null, sample_size: 0, is_na: true },
            },
            dailyTrends: { labels: [], gross_compliance: [], punctuality: [] },
            liveVehicles: [],
            routes: [],
            traccar: {
                last_fix_local: "Sin registros",
                online_ratio: "0 / 0",
                has_signal: false,
            },
            recentTrips: [],
            recentIncidents: [],
            setupSteps: [],
            canConfigure: false,
        });

        onMounted(async () => {
            this._initMap();
            await this.loadAdminHome(false);
            this._revertMotion = runGeorutexEntrance(this.rootRef.el, [
                { selector: ".grx-ops-kpi-band", y: 10, duration: 0.32, stagger: 0 },
                { selector: ".grx-surface-panel", y: 12, duration: 0.36, stagger: 0.045 },
            ]);
            this._revertCounters = animateGeorutexCounters(this.rootRef.el);
            window.addEventListener("resize", this._onWindowResize);
            this._refreshTimer = window.setInterval(() => {
                void this.loadAdminHome(false, true);
            }, 30000);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onWindowResize);
            if (this._refreshTimer) {
                window.clearInterval(this._refreshTimer);
                this._refreshTimer = null;
            }
            if (this._revertMotion) {
                this._revertMotion();
                this._revertMotion = null;
            }
            if (this._revertCounters) {
                this._revertCounters();
                this._revertCounters = null;
            }
            if (this._trendChart) {
                if (typeof this._trendChart.dispose === "function") this._trendChart.dispose();
                this._trendChart = null;
            }
            if (this._map) {
                this._map.remove();
                this._map = null;
                this._markersLayer = null;
                this._markersById.clear();
            }
        });
    }

    get fleetOnlinePct() {
        const tracked = this.state.stats.vehicles_tracked || 0;
        if (!tracked) return 0;
        return Math.min(100, Math.round(((this.state.stats.vehicles_online || 0) / tracked) * 100));
    }

    get filteredVehicles() {
        let list = this.state.liveVehicles || [];
        if (this.state.vehicleFilter === "fresh") {
            list = list.filter((v) => v.freshness === "fresh" || v.freshness === "online");
        } else if (this.state.vehicleFilter === "offline") {
            list = list.filter((v) => v.freshness !== "fresh" && v.freshness !== "online");
        }
        const q = (this.state.vehicleSearch || "").trim().toLowerCase();
        if (q) {
            list = list.filter((v) =>
                [v.name, v.license_plate, v.driver_name]
                    .filter(Boolean)
                    .some((f) => String(f).toLowerCase().includes(q))
            );
        }
        return list;
    }

    get positionedVehicleCount() {
        return (this.state.liveVehicles || []).filter((v) => v.has_coordinates).length;
    }

    get filteredIncidents() {
        const list = this.state.recentIncidents || [];
        if (this.state.incidentFilter === "open") {
            return list.filter((i) => i.is_open);
        }
        return list;
    }

    get filteredTrips() {
        let list = this.state.recentTrips || [];
        if (this.state.tripFilter !== "all") {
            list = list.filter((t) => t.state === this.state.tripFilter);
        }
        const q = (this.state.tripSearch || "").trim().toLowerCase();
        if (q) {
            list = list.filter((t) =>
                [t.name, t.route_name, t.route_code, t.vehicle_name, t.driver_name]
                    .filter(Boolean)
                    .some((field) => String(field).toLowerCase().includes(q))
            );
        }
        return list;
    }

    get hasTrendData() {
        const tr = this.state.dailyTrends;
        if (!tr || !Array.isArray(tr.labels) || !tr.labels.length) return false;
        return [tr.gross_compliance, tr.punctuality].some(
            (s) => Array.isArray(s) && s.some((v) => v !== null && v !== undefined)
        );
    }

    _initMap() {
        if (!this.mapRef.el || typeof window.L === "undefined") return;
        this._map = window.L.map(this.mapRef.el, {
            zoomControl: true,
            attributionControl: true,
            scrollWheelZoom: false,
        }).setView([-1.249, -78.625], 13);

        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this._map);

        this._markersLayer = window.L.layerGroup().addTo(this._map);
        window.setTimeout(() => {
            if (this._map) this._map.invalidateSize();
        }, 180);
    }

    _renderMapMarkers() {
        if (!this._map || !this._markersLayer || typeof window.L === "undefined") return;
        this._markersLayer.clearLayers();
        this._markersById.clear();

        const points = [];
        for (const v of this.filteredVehicles) {
            const lat = Number(v.latitude);
            const lon = Number(v.longitude);
            if (!v.has_coordinates || !Number.isFinite(lat) || !Number.isFinite(lon)) continue;

            const statusCls =
                v.freshness === "fresh" || v.freshness === "online"
                    ? "fresh"
                    : v.freshness === "stale"
                    ? "stale"
                    : "offline";

            const icon = window.L.divIcon({
                className: "custom-div-icon",
                html: `<div class="georutex-live-bus-marker ${statusCls}">${
                    statusCls === "fresh" ? '<div class="georutex-pulse-ring"></div>' : ""
                }<i class="fa fa-bus"></i></div>`,
                iconSize: [36, 36],
                iconAnchor: [18, 18],
            });

            const marker = window.L.marker([lat, lon], { icon }).addTo(this._markersLayer);
            const popupDiv = document.createElement("div");
            popupDiv.className = "grx-map-popup";
            popupDiv.innerHTML =
                `<strong>${this._escapeHtml(v.name)}</strong><br/>` +
                `<span>Placa: ${this._escapeHtml(v.license_plate || "S/P")}</span><br/>` +
                `<span>Conductor: ${this._escapeHtml(v.driver_name || "Sin asignar")}</span><br/>` +
                `<span>Velocidad: ${Math.round(Number(v.speed) || 0)} km/h</span><br/>` +
                `<small>${this._escapeHtml(v.fix_time_local || "")}</small>`;
            marker.bindPopup(popupDiv);
            this._markersById.set(v.vehicle_id, marker);
            points.push([lat, lon]);
        }

        if (points.length && !this._hasCenteredMap) {
            this._map.fitBounds(window.L.latLngBounds(points), { padding: [36, 36], maxZoom: 15 });
            this._hasCenteredMap = true;
        }
    }

    _escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    _renderTrendChart() {
        if (this._trendChart) {
            if (typeof this._trendChart.dispose === "function") this._trendChart.dispose();
            this._trendChart = null;
        }
        if (!this.hasTrendData || !this.trendChartRef.el || !window.echarts) return;
        const tr = this.state.dailyTrends;
        this._trendChart = window.echarts.init(this.trendChartRef.el);
        this._trendChart.setOption({
            tooltip: {
                trigger: "axis",
                backgroundColor: "#111827",
                borderColor: "#111827",
                textStyle: { color: "#ffffff", fontSize: 12 },
            },
            legend: {
                bottom: 0,
                data: ["Cumplimiento (MT-01)", "Puntualidad (MT-02)"],
                textStyle: { fontSize: 12, color: "#475569" },
            },
            grid: { left: 42, right: 16, top: 18, bottom: 36 },
            xAxis: {
                type: "category",
                boundaryGap: false,
                data: tr.labels,
                axisLine: { lineStyle: { color: "#e5e7eb" } },
                axisLabel: { fontSize: 11, color: "#64748b" },
            },
            yAxis: {
                type: "value",
                min: 0,
                max: 100,
                axisLabel: { formatter: "{value}%", fontSize: 11, color: "#64748b" },
                splitLine: { lineStyle: { color: "#f1f5f9" } },
            },
            series: [
                {
                    name: "Cumplimiento (MT-01)",
                    type: "line",
                    smooth: 0.35,
                    symbolSize: 7,
                    data: tr.gross_compliance,
                    itemStyle: { color: "#1a56db" },
                    lineStyle: { width: 2.5 },
                    areaStyle: {
                        color: {
                            type: "linear",
                            x: 0,
                            y: 0,
                            x2: 0,
                            y2: 1,
                            colorStops: [
                                { offset: 0, color: "rgba(26, 86, 219, 0.16)" },
                                { offset: 1, color: "rgba(26, 86, 219, 0.01)" },
                            ],
                        },
                    },
                },
                {
                    name: "Puntualidad (MT-02)",
                    type: "line",
                    smooth: 0.35,
                    symbolSize: 7,
                    data: tr.punctuality,
                    itemStyle: { color: "#0bbcd7" },
                    lineStyle: { width: 2.5 },
                },
            ],
        });
    }

    onVehicleSearchInput() {
        this._renderMapMarkers();
    }

    setVehicleFilter(filterKey) {
        this.state.vehicleFilter = filterKey;
        this._renderMapMarkers();
    }

    focusVehicle(v) {
        this.state.selectedVehicleId = v.vehicle_id;
        if (!this._map) return;
        if (v.has_coordinates) {
            this._map.flyTo([Number(v.latitude), Number(v.longitude)], 15, { duration: 0.65 });
            const marker = this._markersById.get(v.vehicle_id);
            if (marker) marker.openPopup();
        } else {
            this.notification.add(
                `${v.name} aún no reporta coordenadas GPS.`,
                { type: "info", sticky: false }
            );
        }
    }

    recenterMap() {
        if (!this._map) return;
        const pts = this.filteredVehicles
            .filter((v) => v.has_coordinates)
            .map((v) => [Number(v.latitude), Number(v.longitude)]);
        if (pts.length) {
            this._map.fitBounds(window.L.latLngBounds(pts), { padding: [36, 36], maxZoom: 15 });
        } else {
            this._map.setView([-1.249, -78.625], 13);
        }
    }

    async loadAdminHome(showNotice = false, silent = false) {
        if (!silent) {
            this.state.isLoading = true;
            this.state.error = "";
        }
        try {
            const payload = await this.orm.call(
                "transport.trip",
                "get_admin_home_data",
                []
            );
            this.state.userName = payload.user_name || "Administrador";
            this.state.localDateLabel = payload.local_date_label || "";
            this.state.localTimeLabel = payload.local_time_label || "";
            this.state.stats = payload.stats || this.state.stats;
            this.state.kpis = payload.kpis || this.state.kpis;
            this.state.dailyTrends = payload.daily_trends || this.state.dailyTrends;
            this.state.liveVehicles = payload.live_vehicles || [];
            this.state.routes = payload.routes || [];
            this.state.traccar = payload.traccar || this.state.traccar;
            this.state.recentTrips = payload.recent_trips || [];
            this.state.recentIncidents = payload.recent_incidents || [];
            this.state.setupSteps = payload.setup_steps || [];
            this.state.canConfigure = Boolean(payload.can_configure);
            this.state.error = "";

            this._renderMapMarkers();
            window.setTimeout(() => this._renderTrendChart(), 60);

            if (showNotice) {
                this.notification.add("Centro de operaciones actualizado.", {
                    type: "info",
                    sticky: false,
                });
            }
        } catch (err) {
            console.error("GeoRutexAdminHome load error:", err);
            const msg = String((err && err.message) || "");
            if (msg.toLowerCase().includes("session") || (err && err.name === "SessionExpiredError")) {
                window.location.href = "/georutex/acceso";
                return;
            }
            if (!silent) {
                this.state.error =
                    "No se pudo conectar con el servidor para cargar el panel operativo. Reintenta en unos segundos.";
            }
        } finally {
            if (!silent) {
                this.state.isLoading = false;
            }
        }
    }

    async syncTraccarFleet() {
        if (this.state.isSyncing) return;
        this.state.isSyncing = true;
        try {
            const res = await this.orm.call(
                "transport.trip",
                "action_admin_sync_traccar",
                []
            );
            const msg =
                res.error_count > 0
                    ? `Sincronizados ${res.synced_count}/${res.tracked_count} vehículos (${res.error_count} con aviso).`
                    : `Sincronización GPS completada (${res.synced_count} vehículos).`;
            this.notification.add(msg, {
                type: res.error_count > 0 ? "warning" : "success",
                sticky: false,
            });
            await this.loadAdminHome(false);
        } catch (err) {
            console.error("GeoRutexAdminHome sync error:", err);
            this.notification.add(
                "No se pudo completar la sincronización GPS.",
                { type: "danger", sticky: false }
            );
        } finally {
            this.state.isSyncing = false;
        }
    }

    get setupDoneCount() {
        return this.state.setupSteps.filter((step) => step.done).length;
    }

    get showSetupGuide() {
        return (
            this.state.canConfigure &&
            this.state.setupSteps.length > 0 &&
            this.setupDoneCount < this.state.setupSteps.length
        );
    }

    get nextSetupKey() {
        const next = this.state.setupSteps.find((step) => !step.done);
        return next ? next.key : null;
    }

    runSetupStep(step) {
        const handlers = {
            fleet: () => this.openFleet(),
            routes: () => this.openRoutes(),
            new_trip: () => this.openNewTrip(),
            sync: () => this.syncTraccarFleet(),
        };
        const handler = handlers[step.action];
        if (handler) {
            handler();
        }
    }

    openNewTrip() {
        this.drawer.openRecord({
            resModel: "transport.trip",
            title: "Programar nuevo recorrido",
            subtitle: "Asigna vehículo, conductor, ruta aprobada y horario previsto.",
            eyebrow: "Programación operativa",
            width: 600,
            allowOpenFull: false,
            saveNotice: "Recorrido programado correctamente.",
            onRecordSaved: async () => {
                await this.loadAdminHome(false);
            },
        });
    }

    openNewIncident() {
        this.drawer.openRecord({
            resModel: "transport.incident",
            title: "Registrar incidencia",
            subtitle: "Documenta una novedad operacional asociada a un recorrido.",
            eyebrow: "Incidencias",
            context: { default_source: "manual" },
            width: 560,
            allowOpenFull: false,
            saveNotice: "Incidencia registrada correctamente.",
            onRecordSaved: async () => {
                await this.loadAdminHome(false);
            },
        });
    }

    openFleet() {
        this.actionService.doAction("uta_transport_monitor.action_transport_monitored_fleet");
    }

    openRoutes() {
        this.actionService.doAction("uta_transport_monitor.action_transport_route");
    }

    openRouteDetail(routeId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Ruta de Transporte",
            res_model: "transport.route",
            res_id: routeId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    openTrips() {
        this.actionService.doAction("uta_transport_monitor.action_transport_trip");
    }

    openLiveMap() {
        this.actionService.doAction("uta_transport_monitor.action_transport_live_fleet_map");
    }

    openDashboard() {
        this.actionService.doAction("uta_transport_monitor.action_transport_dashboard");
    }

    openPositions() {
        this.actionService.doAction("uta_transport_monitor.action_transport_vehicle_position");
    }

    openIncidents() {
        this.actionService.doAction("uta_transport_monitor.action_transport_incident");
    }

    openTripDetail(tripId) {
        this.drawer.openRecord({
            resModel: "transport.trip",
            resId: tripId,
            title: "Vista rápida de recorrido",
            subtitle: "Consulta estado, horarios o abre el detalle completo con mapa.",
            eyebrow: "Recorridos",
            width: 620,
            allowOpenFull: true,
            saveNotice: "Recorrido actualizado.",
            onRecordSaved: async () => {
                await this.loadAdminHome(false);
            },
        });
    }

    openIncidentDetail(incidentId) {
        this.drawer.openRecord({
            resModel: "transport.incident",
            resId: incidentId,
            title: "Incidencia operacional",
            subtitle: "Revisa la evidencia, justificación y resolución del evento.",
            eyebrow: "Incidencias",
            width: 580,
            allowOpenFull: true,
            saveNotice: "Incidencia actualizada.",
            onRecordSaved: async () => {
                await this.loadAdminHome(false);
            },
        });
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

    getFreshnessDotClass(freshness) {
        if (freshness === "fresh" || freshness === "online") return "is-green is-pulse";
        if (freshness === "stale") return "is-amber";
        return "is-red";
    }
}

registry
    .category("actions")
    .add("uta_transport_admin_home", GeoRutexAdminHomeAction);
