/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TransportDashboardAction extends Component {
    static template = "uta_transport_monitor.TransportDashboardAction";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.trendChartRef = useRef("trendChartCanvas");
        this.incidentChartRef = useRef("incidentChartCanvas");
        this.mapPreviewRef = useRef("mapPreviewCanvas");

        this.trendChart = null;
        this.incidentChart = null;
        this.mapPreview = null;
        this.mapPreviewMarkers = null;
        this.mapPreviewHasInitialView = false;
        this.mapRefreshTimer = null;
        this.chartRenderTimer = null;

        this.state = useState({
            isLoading: true,
            filtersOpen: false,
            activePreset: "all",
            filters: {
                date_from: "",
                date_to: "",
                route_id: "",
                vehicle_id: "",
                source_type: "combined", // 'real', 'simulated', 'combined'
            },
            availableRoutes: [],
            availableVehicles: [],
            liveMapStatus: "loading",
            livePositionCount: 0,
            liveMapError: "",
            kpis: {},
            charts: {},
            summary: {},
            qualityRunning: false,
        });

        onMounted(async () => {
            this.initMapPreview();
            await Promise.all([
                this.loadFilterOptions(),
                this.loadDashboardData(),
                this.loadLiveMapPositions(),
            ]);
            this.mapRefreshTimer = setInterval(() => {
                this.loadLiveMapPositions();
            }, 30000);
        });

        onWillUnmount(() => {
            if (this.mapRefreshTimer) {
                clearInterval(this.mapRefreshTimer);
                this.mapRefreshTimer = null;
            }
            if (this.chartRenderTimer) {
                clearTimeout(this.chartRenderTimer);
                this.chartRenderTimer = null;
            }
            this.destroyCharts();
            if (this.mapPreview) {
                this.mapPreview.remove();
                this.mapPreview = null;
                this.mapPreviewMarkers = null;
            }
        });
    }

    get hasDailyTrendData() {
        const trends = this.state.charts.daily_trends;
        if (!trends || !Array.isArray(trends.labels) || !trends.labels.length) {
            return false;
        }
        return [trends.gross_compliance, trends.punctuality].some(
            (series) => Array.isArray(series) && series.some((value) => value !== null && value !== undefined)
        );
    }

    get hasIncidentChartData() {
        const incidents = this.state.charts.incidents_by_type;
        return Boolean(
            incidents &&
            Array.isArray(incidents.labels) &&
            Array.isArray(incidents.counts) &&
            incidents.counts.some((count) => count > 0)
        );
    }

    get transportMetricCards() {
        return [
            { id: "MT-01", title: "Cumplimiento de rutas", tone: "blue" },
            { id: "MT-02", title: "Puntualidad", tone: "green" },
            { id: "MT-03", title: "Retraso promedio", tone: "amber" },
            { id: "MT-04", title: "Paradas visitadas", tone: "blue" },
            { id: "MT-05", title: "Desviación de ruta", tone: "red" },
            { id: "MT-06", title: "Diferencia de distancia", tone: "violet" },
            { id: "MT-07", title: "Duración promedio", tone: "blue" },
            { id: "MT-08", title: "Frecuencia de incidencias", tone: "red" },
        ].map((item) => ({
            ...item,
            metric: this.state.kpis[item.id] || {},
        }));
    }

    get qualityMetricCards() {
        return [
            { id: "MCS-01", title: "Integridad GPS", tone: "green" },
            { id: "MCS-02", title: "Sincronización Traccar", tone: "blue" },
            { id: "MCS-03", title: "Tiempo de respuesta", tone: "violet" },
            { id: "MCS-04", title: "Detección de incidencias", tone: "amber" },
        ].map((item) => ({
            ...item,
            metric: this.state.kpis[item.id] || {},
        }));
    }

    initMapPreview() {
        if (!this.mapPreviewRef.el || typeof window.L === "undefined") {
            this.state.liveMapStatus = "error";
            this.state.liveMapError = "El mapa no está disponible en este momento.";
            this.notification.add(this.state.liveMapError, {
                type: "danger",
                sticky: false,
            });
            return;
        }

        this.mapPreview = window.L.map(this.mapPreviewRef.el, {
            zoomControl: false,
            attributionControl: true,
        }).setView([-1.249, -78.625], 12);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(this.mapPreview);
        this.mapPreviewMarkers = window.L.layerGroup().addTo(this.mapPreview);
        window.setTimeout(() => {
            if (this.mapPreview) {
                this.mapPreview.invalidateSize();
            }
        }, 150);
    }

    async loadLiveMapPositions() {
        if (!this.mapPreview || !this.mapPreviewMarkers) {
            return;
        }
        try {
            const vehicles = await this.orm.call(
                "fleet.vehicle",
                "get_live_fleet_positions",
                []
            );
            const positions = (vehicles || []).filter((vehicle) => {
                const latitude = Number(vehicle.latitude);
                const longitude = Number(vehicle.longitude);
                return vehicle.has_coordinates &&
                    Number.isFinite(latitude) &&
                    Number.isFinite(longitude) &&
                    latitude >= -90 && latitude <= 90 &&
                    longitude >= -180 && longitude <= 180;
            });

            this.mapPreviewMarkers.clearLayers();
            positions.forEach((vehicle) => {
                const marker = window.L.marker(
                    [Number(vehicle.latitude), Number(vehicle.longitude)],
                    {
                        icon: window.L.divIcon({
                            className: "georutex-preview-marker",
                            html: '<span class="fa fa-bus" aria-hidden="true"></span>',
                            iconSize: [34, 34],
                            iconAnchor: [17, 17],
                        }),
                    }
                ).addTo(this.mapPreviewMarkers);
                const label = document.createElement("span");
                label.textContent = vehicle.name || "Vehículo UTA";
                marker.bindTooltip(label);
            });

            this.state.livePositionCount = positions.length;
            this.state.liveMapStatus = positions.length ? "ready" : "empty";
            this.state.liveMapError = "";
            if (positions.length && !this.mapPreviewHasInitialView) {
                const bounds = window.L.latLngBounds(
                    positions.map((vehicle) => [
                        Number(vehicle.latitude),
                        Number(vehicle.longitude),
                    ])
                );
                this.mapPreview.fitBounds(bounds, { padding: [24, 24], maxZoom: 14 });
                this.mapPreviewHasInitialView = true;
            }
        } catch (err) {
            console.error("Error loading dashboard map positions:", err);
            if (this.state.liveMapStatus !== "error") {
                this.notification.add("No se pudieron actualizar las posiciones GPS.", {
                    type: "danger",
                    sticky: false,
                });
            }
            this.state.liveMapStatus = "error";
            this.state.liveMapError = "No se pudieron actualizar las posiciones GPS.";
        }
    }

    getMetricTooltip(metric) {
        if (!metric) {
            return "Sin información de la métrica.";
        }
        const details = [];
        if (metric.formula) details.push(`Fórmula: ${metric.formula}`);
        if (metric.unit) details.push(`Unidad: ${metric.unit}`);
        if (metric.period) details.push(`Período: ${metric.period}`);
        if (metric.source_type) details.push(`Fuente: ${metric.source_type}`);
        if (metric.sample_size !== undefined) details.push(`Muestra n: ${metric.sample_size}`);
        if (metric.numerator !== undefined) details.push(`Numerador: ${metric.numerator}`);
        if (metric.denominator !== undefined) details.push(`Denominador: ${metric.denominator}`);
        if (metric.rule_version) details.push(`Versión de regla: ${metric.rule_version}`);
        if (metric.na_reason) details.push(`Sin resultado: ${metric.na_reason}`);
        if (metric.interpretation) details.push(`Interpretación: ${metric.interpretation}`);
        return details.join("\n");
    }

    getMetricSecondary(metricId, metric) {
        const secondary = metric && metric.secondary ? metric.secondary : {};
        if (metric && metric.is_na && metricId !== "MT-08") {
            return "";
        }
        const value = (key) => (
            secondary[key] === null || secondary[key] === undefined
                ? "N/A"
                : secondary[key]
        );
        switch (metricId) {
            case "MT-01":
                return secondary.adjusted_display ? `Ajustado ${secondary.adjusted_display}` : "";
            case "MT-02":
                return `Salida ${value("departure_punctuality_pct")}% · llegada ${value("arrival_punctuality_pct")}%`;
            case "MT-03":
                return `En tardíos: ${value("conditional_avg_delay_min")} min`;
            case "MT-04":
                return `Visitadas ${value("visited_count")} · omitidas ${value("missed_count")}`;
            case "MT-05":
                return `Viajes desviados: ${value("deviated_trips_pct")}%`;
            case "MT-06":
                return `MAE ${value("mae_km")} km`;
            case "MT-07":
                return `Plan ${value("planned_avg_duration_min")} min`;
            case "MT-08":
                return `${value("total_incident_count")} incidencias`;
            default:
                return "";
        }
    }

    getMetricSource(metric) {
        if (!metric || !metric.source_type) {
            return "Fuente no disponible";
        }
        const sourceLabels = {
            real: "Real",
            simulated: "Simulado",
            combined: "Combinado",
        };
        return sourceLabels[metric.source_type] || metric.source_type;
    }

    getMetricSegmentClass(metric, segment) {
        if (!metric || metric.is_na || metric.value === null || metric.value === undefined) {
            return "";
        }
        if (metric.unit === "%") {
            const percentage = Math.max(0, Math.min(100, Number(metric.value) || 0));
            return segment <= Math.ceil(percentage / 20) ? "is-filled" : "";
        }
        return "is-filled";
    }

    async loadFilterOptions() {
        try {
            const routes = await this.orm.searchRead(
                "transport.route",
                [],
                ["id", "name", "code"],
                { order: "name asc" }
            );
            const vehicles = await this.orm.searchRead(
                "fleet.vehicle",
                [],
                ["id", "name", "license_plate", "is_simulated"],
                { order: "name asc" }
            );
            this.state.availableRoutes = routes;
            this.state.availableVehicles = vehicles;
        } catch (err) {
            console.error("Error loading filter options:", err);
            this.notification.add("No se pudieron cargar las opciones de filtro.", {
                type: "warning",
                sticky: false,
            });
        }
    }

    async loadDashboardData() {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call(
                "transport.metrics.service",
                "get_dashboard_metrics",
                [this.state.filters]
            );

            this.state.kpis = data.kpis || {};
            this.state.charts = data.charts || {};
            this.state.summary = data.summary || {};

            if (this.chartRenderTimer) {
                clearTimeout(this.chartRenderTimer);
            }
            this.chartRenderTimer = setTimeout(() => {
                this.chartRenderTimer = null;
                this.renderCharts();
            }, 50);
        } catch (err) {
            console.error("Error loading dashboard metrics:", err);
            this.notification.add("Error al cargar métricas del panel.", {
                type: "danger",
                sticky: false,
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    destroyCharts() {
        if (this.trendChart) {
            this.trendChart.destroy();
            this.trendChart = null;
        }
        if (this.incidentChart) {
            this.incidentChart.destroy();
            this.incidentChart = null;
        }
    }

    renderCharts() {
        this.destroyCharts();
        if (!window.Chart) {
            console.warn("Chart.js not available in window context.");
            return;
        }

        if (this.trendChartRef.el && this.hasDailyTrendData) {
            const trends = this.state.charts.daily_trends;
            const ctx = this.trendChartRef.el.getContext("2d");
            this.trendChart = new window.Chart(ctx, {
                type: "line",
                data: {
                    labels: trends.labels,
                    datasets: [
                        {
                            label: "Cumplimiento de rutas",
                            data: trends.gross_compliance,
                            borderColor: "#243d70",
                            backgroundColor: "rgba(29, 78, 216, 0.08)",
                            pointBackgroundColor: "#243d70",
                            pointRadius: 3,
                            fill: true,
                            lineTension: 0.35,
                            spanGaps: false,
                        },
                        {
                            label: "Puntualidad",
                            data: trends.punctuality,
                            borderColor: "#246c38",
                            backgroundColor: "transparent",
                            pointBackgroundColor: "#246c38",
                            pointRadius: 3,
                            lineTension: 0.35,
                            spanGaps: false,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        xAxes: [{
                            ticks: {
                                fontSize: 13,
                                fontColor: "#64748b",
                            },
                        }],
                        yAxes: [{
                            ticks: {
                                min: 0,
                                max: 100,
                                fontSize: 13,
                                fontColor: "#64748b",
                                callback: (val) => val + "%",
                            },
                            scaleLabel: {
                                display: true,
                                labelString: "Porcentaje",
                            },
                        }],
                    },
                    legend: {
                        position: "top",
                        labels: { usePointStyle: true, boxWidth: 10, fontSize: 14 },
                    },
                    tooltips: {
                        mode: "index",
                        intersect: false,
                        titleFontSize: 14,
                        bodyFontSize: 14,
                        callbacks: {
                            label: (item, chartData) => {
                                const label = chartData.datasets[item.datasetIndex].label || "";
                                return item.yLabel === null || item.yLabel === undefined
                                    ? `${label}: Sin muestra`
                                    : `${label}: ${item.yLabel}%`;
                            },
                        },
                    },
                },
            });
        }

        if (this.incidentChartRef.el && this.hasIncidentChartData) {
            const inc = this.state.charts.incidents_by_type;
            const ctx = this.incidentChartRef.el.getContext("2d");
            const colors = [
                "#dc2626", "#f59e0b", "#7c3aed", "#243d70",
                "#246c38", "#0ea5e9", "#db2777", "#78716c",
            ];

            this.incidentChart = new window.Chart(ctx, {
                type: "doughnut",
                data: {
                    labels: inc.labels,
                    datasets: [
                        {
                            data: inc.counts,
                            backgroundColor: colors.slice(0, inc.labels.length),
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {
                        position: "right",
                        labels: { usePointStyle: true, boxWidth: 10, fontSize: 13 },
                    },
                },
            });
        }
    }

    onDetailsToggle() {
        window.setTimeout(() => {
            if (this.incidentChart) {
                this.incidentChart.resize();
            }
        }, 0);
    }

    async onSourceTypeChange(type) {
        this.state.filters.source_type = type;
        await this.loadDashboardData();
    }

    toggleFilterPanel() {
        this.state.filtersOpen = !this.state.filtersOpen;
    }

    async refreshDashboard() {
        await Promise.all([
            this.loadDashboardData(),
            this.loadLiveMapPositions(),
        ]);
    }

    openLiveMap() {
        this.actionService.doAction("uta_transport_monitor.action_transport_live_fleet_map");
    }

    openMetric(metricId) {
        if (metricId === "MT-08") {
            this.openIncidentsList();
            return;
        }
        this.openTripsList(metricId === "MT-01" ? "compliant" : "all");
    }

    async setDatePreset(preset) {
        const now = new Date();
        const formatDate = (d) => {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${y}-${m}-${day}`;
        };

        if (preset === "today") {
            const todayStr = formatDate(now);
            this.state.filters.date_from = todayStr;
            this.state.filters.date_to = todayStr;
        } else if (preset === "week") {
            const dayOfWeek = now.getDay() || 7;
            const monday = new Date(now);
            monday.setDate(now.getDate() - dayOfWeek + 1);
            this.state.filters.date_from = formatDate(monday);
            this.state.filters.date_to = formatDate(now);
        } else if (preset === "month") {
            const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
            this.state.filters.date_from = formatDate(firstOfMonth);
            this.state.filters.date_to = formatDate(now);
        } else if (preset === "all") {
            this.state.filters.date_from = "";
            this.state.filters.date_to = "";
        }
        this.state.activePreset = preset;
        this.state.filtersOpen = false;
        await this.loadDashboardData();
    }

    async onFilterSubmit(e) {
        if (e) e.preventDefault();
        this.state.activePreset = "";
        this.state.filtersOpen = false;
        await this.loadDashboardData();
    }

    async onResetFilters() {
        this.state.filters.date_from = "";
        this.state.filters.date_to = "";
        this.state.filters.route_id = "";
        this.state.filters.vehicle_id = "";
        this.state.filters.source_type = "combined";
        this.state.activePreset = "all";
        this.state.filtersOpen = false;
        await this.loadDashboardData();
    }

    async onRunQualityBenchmarks() {
        this.state.qualityRunning = true;
        try {
            const qData = await this.orm.call(
                "transport.software.quality.service",
                "compute_all_quality_metrics",
                []
            );
            this.state.kpis["MCS-01"] = qData["MCS-01"];
            this.state.kpis["MCS-02"] = qData["MCS-02"];
            this.state.kpis["MCS-03"] = qData["MCS-03"];
            this.state.kpis["MCS-04"] = qData["MCS-04"];
            this.notification.add("Benchmarks de calidad ejecutados con éxito.", {
                type: "success",
                sticky: false,
            });
        } catch (err) {
            console.error("Error running quality benchmarks:", err);
            this.notification.add("Error al ejecutar benchmarks de calidad.", {
                type: "danger",
                sticky: false,
            });
        } finally {
            this.state.qualityRunning = false;
        }
    }

    // Drill-down actions
    openTripsList(filterType = "all") {
        let domain = [];
        if (this.state.filters.route_id) {
            domain.push(["route_id", "=", parseInt(this.state.filters.route_id)]);
        }
        if (this.state.filters.vehicle_id) {
            domain.push(["vehicle_id", "=", parseInt(this.state.filters.vehicle_id)]);
        }
        if (this.state.filters.source_type !== "combined") {
            domain.push(["source_type", "=", this.state.filters.source_type]);
        }
        if (filterType === "compliant") {
            domain.push(["evaluation_status", "=", "compliant"]);
        } else if (filterType === "non_compliant") {
            domain.push(["evaluation_status", "=", "non_compliant"]);
        }

        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Recorridos del Período",
            res_model: "transport.trip",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }

    openIncidentsList() {
        let domain = [];
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Incidencias Operacionales",
            res_model: "transport.incident",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }

    openEvaluationsList() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Auditoría de Evaluaciones",
            res_model: "transport.trip.evaluation",
            views: [[false, "list"], [false, "form"]],
        });
    }
}

registry.category("actions").add("uta_transport_dashboard", TransportDashboardAction);

