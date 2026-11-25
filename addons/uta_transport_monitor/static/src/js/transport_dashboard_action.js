/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { runGeorutexEntrance, animateGeorutexCounters } from "./georutex_motion";

const INCIDENT_TYPE_LABELS = {
    delay_start: "Retraso en salida",
    delay_arrival: "Retraso en llegada",
    delay_checkpoint: "Retraso en parada",
    stop_missed: "Parada omitida",
    route_deviation: "Desvío de ruta",
    gps_loss: "Pérdida de GPS",
    traffic_congestion: "Congestión vial",
    accident: "Accidente",
    road_block: "Cierre de vía",
    vehicle_breakdown: "Avería mecánica",
    weather: "Clima adverso",
    other: "Otra eventualidad",
};

export class TransportDashboardAction extends Component {
    static template = "uta_transport_monitor.TransportDashboardAction";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.rootRef = useRef("analyticsRoot");
        this.trendChartRef = useRef("trendChartCanvas");
        this.incidentChartRef = useRef("incidentChartCanvas");
        this.mt01GaugeRef = useRef("mt01GaugeBox");
        this.mt02GaugeRef = useRef("mt02GaugeBox");
        this.routeChartRef = useRef("routeChartBox");
        this.mapPreviewRef = useRef("mapPreviewCanvas");

        this.trendChart = null;
        this.incidentChart = null;
        this.mt01Gauge = null;
        this.mt02Gauge = null;
        this.routeChart = null;
        this._revertMotion = null;
        this._revertCounters = null;
        this._onWindowResize = () => {
            this._resizeEcharts();
            if (this.mapPreview) {
                this.mapPreview.invalidateSize({ pan: false });
            }
        };
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
                source_type: "combined",
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
            this._revertMotion = runGeorutexEntrance(this.rootRef.el, [
                { selector: ".grx-ana-headline-band", y: 10, duration: 0.32, stagger: 0 },
                { selector: ".grx-surface-panel", y: 12, duration: 0.36, stagger: 0.045 },
            ]);
            this._revertCounters = animateGeorutexCounters(this.rootRef.el);
            this.mapRefreshTimer = setInterval(() => {
                void this.loadLiveMapPositions();
            }, 30000);
            window.addEventListener("resize", this._onWindowResize);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onWindowResize);
            if (this.mapRefreshTimer) {
                clearInterval(this.mapRefreshTimer);
                this.mapRefreshTimer = null;
            }
            if (this.chartRenderTimer) {
                clearTimeout(this.chartRenderTimer);
                this.chartRenderTimer = null;
            }
            if (this._revertMotion) {
                this._revertMotion();
                this._revertMotion = null;
            }
            if (this._revertCounters) {
                this._revertCounters();
                this._revertCounters = null;
            }
            this.destroyCharts();
            if (this.mapPreview) {
                this.mapPreview.remove();
                this.mapPreview = null;
                this.mapPreviewMarkers = null;
            }
        });
    }

    get hasActiveFilters() {
        const f = this.state.filters;
        return Boolean(
            f.date_from ||
            f.date_to ||
            f.route_id ||
            f.vehicle_id ||
            f.source_type !== "combined"
        );
    }

    get hasDailyTrendData() {
        const trends = this.state.charts.daily_trends;
        if (!trends || !Array.isArray(trends.labels) || !trends.labels.length) {
            return false;
        }
        return [trends.gross_compliance, trends.adjusted_compliance, trends.punctuality].some(
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
            { id: "MCS-02", title: "Sincronización GPS", tone: "blue" },
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
        }, 160);
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
                            className: "custom-div-icon",
                            html: '<div class="georutex-live-bus-marker fresh" style="width:30px;height:30px;"><i class="fa fa-bus" style="font-size:13px;"></i></div>',
                            iconSize: [30, 30],
                            iconAnchor: [15, 15],
                        }),
                    }
                ).addTo(this.mapPreviewMarkers);
                const label = document.createElement("span");
                label.textContent = vehicle.name || "Unidad";
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
        if (metric.source_type) details.push(`Fuente: ${this.getMetricSource(metric)}`);
        if (metric.sample_size !== undefined) details.push(`Muestra n: ${metric.sample_size}`);
        if (metric.numerator !== undefined) details.push(`Numerador: ${metric.numerator}`);
        if (metric.denominator !== undefined) details.push(`Denominador: ${metric.denominator}`);
        if (metric.rule_version) details.push(`Regla: ${metric.rule_version}`);
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
            return "Sin fuente";
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
            const [routes, vehicles] = await Promise.all([
                this.orm.searchRead("transport.route", [], ["id", "name", "code"], { order: "name asc" }),
                this.orm.searchRead("fleet.vehicle", [], ["id", "name", "license_plate", "is_simulated"], { order: "name asc" }),
            ]);
            this.state.availableRoutes = routes;
            this.state.availableVehicles = vehicles;
        } catch (err) {
            console.error("Error loading filter options:", err);
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
            }, 60);
        } catch (err) {
            console.error("Error loading dashboard metrics:", err);
            this.notification.add("Error al cargar métricas del análisis.", {
                type: "danger",
                sticky: false,
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    _resizeEcharts() {
        [this.trendChart, this.incidentChart, this.mt01Gauge, this.mt02Gauge, this.routeChart].forEach((c) => {
            if (c && typeof c.resize === "function") c.resize();
        });
    }

    destroyCharts() {
        [
            ["trendChart", this.trendChart],
            ["incidentChart", this.incidentChart],
            ["mt01Gauge", this.mt01Gauge],
            ["mt02Gauge", this.mt02Gauge],
            ["routeChart", this.routeChart],
        ].forEach(([key, inst]) => {
            if (inst) {
                if (typeof inst.dispose === "function") inst.dispose();
                this[key] = null;
            }
        });
    }

    _initGaugeChart(el, metric, accentColor, subtitle) {
        if (!el || !window.echarts || !metric || metric.is_na) return null;
        const val = Math.max(0, Math.min(100, Number(metric.value) || 0));
        const chart = window.echarts.init(el);
        chart.setOption({
            tooltip: {
                trigger: "item",
                backgroundColor: "#111827",
                borderColor: "#111827",
                textStyle: { color: "#ffffff", fontSize: 12 },
                formatter: () =>
                    `${subtitle}<br/>Valor: <b>${val.toFixed(1)}%</b><br/>Muestra n = ${metric.sample_size || 0}`,
            },
            series: [
                {
                    type: "gauge",
                    startAngle: 205,
                    endAngle: -25,
                    min: 0,
                    max: 100,
                    radius: "92%",
                    progress: {
                        show: true,
                        width: 11,
                        roundCap: true,
                        itemStyle: { color: accentColor },
                    },
                    pointer: { show: false },
                    axisLine: { lineStyle: { width: 11, color: [[1, "#eef2f6"]] } },
                    axisTick: { show: false },
                    splitLine: { show: false },
                    axisLabel: { show: false },
                    title: {
                        show: true,
                        offsetCenter: [0, "34%"],
                        fontSize: 11,
                        color: "#64748b",
                    },
                    detail: {
                        valueAnimation: true,
                        offsetCenter: [0, "-2%"],
                        fontSize: 20,
                        fontWeight: 700,
                        color: "#111827",
                        formatter: () => `${val.toFixed(1)}%`,
                    },
                    data: [{ value: val, name: `n = ${metric.sample_size || 0}` }],
                },
            ],
        });
        return chart;
    }

    renderCharts() {
        this.destroyCharts();
        if (!window.echarts) return;

        // 1. MT-01 & MT-02 Gauges
        this.mt01Gauge = this._initGaugeChart(
            this.mt01GaugeRef.el,
            this.state.kpis["MT-01"],
            "#1a56db",
            "MT-01 · Cumplimiento de rutas"
        );
        this.mt02Gauge = this._initGaugeChart(
            this.mt02GaugeRef.el,
            this.state.kpis["MT-02"],
            "#15803d",
            "MT-02 · Puntualidad general"
        );

        // 2. Daily Trend Area/Line Chart (Gross, Adjusted, Punctuality)
        if (this.trendChartRef.el && this.hasDailyTrendData) {
            const trends = this.state.charts.daily_trends;
            this.trendChart = window.echarts.init(this.trendChartRef.el);
            this.trendChart.setOption({
                tooltip: {
                    trigger: "axis",
                    backgroundColor: "#111827",
                    borderColor: "#111827",
                    textStyle: { color: "#ffffff", fontSize: 12 },
                },
                legend: {
                    top: 0,
                    data: ["Cumplimiento bruto", "Cumplimiento ajustado", "Puntualidad"],
                    textStyle: { color: "#475569", fontSize: 12 },
                },
                grid: { left: 44, right: 18, top: 38, bottom: 28 },
                xAxis: {
                    type: "category",
                    boundaryGap: false,
                    data: trends.labels,
                    axisLine: { lineStyle: { color: "#e5e7eb" } },
                    axisLabel: { color: "#64748b", fontSize: 11 },
                },
                yAxis: {
                    type: "value",
                    min: 0,
                    max: 100,
                    axisLabel: { color: "#64748b", fontSize: 11, formatter: "{value}%" },
                    splitLine: { lineStyle: { color: "#f1f5f9" } },
                },
                series: [
                    {
                        name: "Cumplimiento bruto",
                        type: "line",
                        smooth: 0.35,
                        symbolSize: 7,
                        data: trends.gross_compliance,
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
                        name: "Cumplimiento ajustado",
                        type: "line",
                        smooth: 0.35,
                        symbolSize: 6,
                        data: trends.adjusted_compliance,
                        itemStyle: { color: "#0bbcd7" },
                        lineStyle: { width: 2, type: "dashed" },
                    },
                    {
                        name: "Puntualidad",
                        type: "line",
                        smooth: 0.35,
                        symbolSize: 7,
                        data: trends.punctuality,
                        itemStyle: { color: "#15803d" },
                        lineStyle: { width: 2.2 },
                    },
                ],
            });
        }

        // 3. Route Comparison Horizontal Bar Chart
        const routeComp = this.state.charts.route_comparison || [];
        if (this.routeChartRef.el && routeComp.length) {
            this.routeChart = window.echarts.init(this.routeChartRef.el);
            this.routeChart.setOption({
                tooltip: {
                    trigger: "axis",
                    axisPointer: { type: "shadow" },
                    backgroundColor: "#111827",
                    borderColor: "#111827",
                    textStyle: { color: "#ffffff", fontSize: 12 },
                },
                legend: { top: 0, data: ["Bruto %", "Ajustado %"], textStyle: { fontSize: 11, color: "#475569" } },
                grid: { left: 116, right: 20, top: 32, bottom: 22 },
                xAxis: {
                    type: "value",
                    max: 100,
                    axisLabel: { formatter: "{value}%", fontSize: 11, color: "#64748b" },
                    splitLine: { lineStyle: { color: "#f1f5f9" } },
                },
                yAxis: {
                    type: "category",
                    data: routeComp.map((r) => r.route_name),
                    axisLine: { lineStyle: { color: "#e5e7eb" } },
                    axisLabel: { fontSize: 11, width: 102, overflow: "truncate", color: "#334155" },
                },
                series: [
                    {
                        name: "Bruto %",
                        type: "bar",
                        barMaxWidth: 14,
                        itemStyle: { color: "#1a56db", borderRadius: [0, 4, 4, 0] },
                        data: routeComp.map((r) => r.compliance_gross_pct ?? 0),
                    },
                    {
                        name: "Ajustado %",
                        type: "bar",
                        barMaxWidth: 14,
                        itemStyle: { color: "#0bbcd7", borderRadius: [0, 4, 4, 0] },
                        data: routeComp.map((r) => r.compliance_adj_pct ?? 0),
                    },
                ],
            });
        }

        // 4. Incidents Distribution Donut Chart (with clean Spanish labels)
        if (this.incidentChartRef.el && this.hasIncidentChartData) {
            const inc = this.state.charts.incidents_by_type;
            const palette = ["#fc0154", "#f59e0b", "#1a56db", "#0bbcd7", "#15803d", "#6366f1"];
            this.incidentChart = window.echarts.init(this.incidentChartRef.el);
            this.incidentChart.setOption({
                tooltip: {
                    trigger: "item",
                    backgroundColor: "#111827",
                    borderColor: "#111827",
                    textStyle: { color: "#ffffff", fontSize: 12 },
                    formatter: "{b}: <b>{c}</b> ({d}%)",
                },
                legend: {
                    orient: "vertical",
                    right: 6,
                    top: "middle",
                    textStyle: { fontSize: 11, color: "#475569" },
                },
                color: palette,
                series: [
                    {
                        name: "Incidencias",
                        type: "pie",
                        radius: ["48%", "76%"],
                        center: ["34%", "50%"],
                        itemStyle: { borderColor: "#ffffff", borderWidth: 2, borderRadius: 4 },
                        label: { show: false },
                        data: inc.labels.map((lbl, idx) => ({
                            name: INCIDENT_TYPE_LABELS[lbl] || lbl,
                            value: inc.counts[idx] || 0,
                        })),
                    },
                ],
            });
        }
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
            this.notification.add("Medición de calidad técnica completada.", {
                type: "success",
                sticky: false,
            });
        } catch (err) {
            console.error("Error running quality benchmarks:", err);
            this.notification.add("No se pudo ejecutar la medición técnica.", {
                type: "danger",
                sticky: false,
            });
        } finally {
            this.state.qualityRunning = false;
        }
    }

    openTripsList(filterType = "all") {
        const domain = [];
        if (this.state.filters.route_id) {
            domain.push(["route_id", "=", parseInt(this.state.filters.route_id, 10)]);
        }
        if (this.state.filters.vehicle_id) {
            domain.push(["vehicle_id", "=", parseInt(this.state.filters.vehicle_id, 10)]);
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
            domain,
        });
    }

    openIncidentsList() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Incidencias Operacionales",
            res_model: "transport.incident",
            views: [[false, "list"], [false, "form"]],
            domain: [],
        });
    }

    getMetricProgressPct(metric) {
        if (!metric || metric.is_na || metric.unit !== "%") {
            return 0;
        }
        const numeric = Number(metric.value);
        if (!Number.isFinite(numeric)) {
            return 0;
        }
        return Math.min(100, Math.max(0, numeric));
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
