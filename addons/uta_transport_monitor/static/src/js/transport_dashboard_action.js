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

        this.trendChart = null;
        this.incidentChart = null;

        this.state = useState({
            isLoading: true,
            filters: {
                date_from: "",
                date_to: "",
                route_id: "",
                vehicle_id: "",
                source_type: "combined", // 'real', 'simulated', 'combined'
            },
            availableRoutes: [],
            availableVehicles: [],
            kpis: {},
            charts: {},
            summary: {},
            qualityRunning: false,
        });

        onMounted(async () => {
            await this.loadFilterOptions();
            await this.loadDashboardData();
        });

        onWillUnmount(() => {
            this.destroyCharts();
        });
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

            // Render charts next tick after DOM update
            setTimeout(() => {
                this.renderCharts();
            }, 50);
        } catch (err) {
            console.error("Error loading dashboard metrics:", err);
            this.notification.add("Error al cargar métricas del panel.", {
                type: "danger",
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

        // 1. Daily Trends Chart (Lines)
        if (this.trendChartRef.el && this.state.charts.daily_trends) {
            const trends = this.state.charts.daily_trends;
            const ctx = this.trendChartRef.el.getContext("2d");
            this.trendChart = new window.Chart(ctx, {
                type: "line",
                data: {
                    labels: trends.labels.length ? trends.labels : ["Sin datos"],
                    datasets: [
                        {
                            label: "Cumplimiento Bruto (%)",
                            data: trends.gross_compliance.length ? trends.gross_compliance : [0],
                            borderColor: "#0288D1",
                            backgroundColor: "rgba(2, 136, 209, 0.1)",
                            fill: true,
                            tension: 0.3,
                        },
                        {
                            label: "Cumplimiento Ajustado (%)",
                            data: trends.adjusted_compliance.length ? trends.adjusted_compliance : [0],
                            borderColor: "#2E7D32",
                            backgroundColor: "transparent",
                            borderDash: [5, 5],
                            tension: 0.3,
                        },
                        {
                            label: "Puntualidad de Viajes (%)",
                            data: trends.punctuality.length ? trends.punctuality : [0],
                            borderColor: "#E65100",
                            backgroundColor: "transparent",
                            tension: 0.3,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            ticks: { callback: (val) => val + "%" },
                        },
                    },
                    plugins: {
                        legend: { position: "top" },
                    },
                },
            });
        }

        // 2. Incidents by Type Chart (Doughnut / Bar)
        if (this.incidentChartRef.el && this.state.charts.incidents_by_type) {
            const inc = this.state.charts.incidents_by_type;
            const ctx = this.incidentChartRef.el.getContext("2d");
            const hasData = inc.counts && inc.counts.some((c) => c > 0);

            const labels = hasData ? inc.labels : ["Sin incidencias"];
            const counts = hasData ? inc.counts : [0];
            const colors = [
                "#D32F2F", "#F57C00", "#7B1FA2", "#1976D2",
                "#388E3C", "#0288D1", "#C2185B", "#795548"
            ];

            this.incidentChart = new window.Chart(ctx, {
                type: "doughnut",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            data: counts,
                            backgroundColor: colors.slice(0, labels.length),
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "right" },
                    },
                },
            });
        }
    }

    async onSourceTypeChange(type) {
        this.state.filters.source_type = type;
        await this.loadDashboardData();
    }

    async onFilterSubmit(e) {
        if (e) e.preventDefault();
        await this.loadDashboardData();
    }

    async onResetFilters() {
        this.state.filters.date_from = "";
        this.state.filters.date_to = "";
        this.state.filters.route_id = "";
        this.state.filters.vehicle_id = "";
        this.state.filters.source_type = "combined";
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
            });
        } catch (err) {
            console.error("Error running quality benchmarks:", err);
            this.notification.add("Error al ejecutar benchmarks de calidad.", {
                type: "danger",
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

