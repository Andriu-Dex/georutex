/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, onWillUnmount, useRef, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class TripMapWidget extends Component {
    static template = "uta_transport_monitor.TripMapWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.mapRef = useRef("mapContainer");
        this.map = null;
        this.layers = {
            reference: null,
            stops: null,
            trajectory: null,
            latest: null,
        };

        onMounted(() => {
            this.initMap();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });

        useEffect(
            () => {
                if (this.map && this.props.record && this.props.record.resId) {
                    this.loadTripData(this.props.record.resId);
                }
            },
            () => [
                this.props.record && this.props.record.resId,
                this.props.record && this.props.record.data.position_count,
            ]
        );
    }

    initMap() {
        if (!this.mapRef.el || this.map) return;
        if (typeof window.L === "undefined") {
            console.error("Leaflet library not loaded");
            return;
        }

        // Center default at Ambato, Ecuador: [-1.249, -78.625]
        this.map = window.L.map(this.mapRef.el).setView([-1.249, -78.625], 13);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);

        if (this.props.record && this.props.record.resId) {
            this.loadTripData(this.props.record.resId);
        }
    }

    async loadTripData(tripId) {
        try {
            const data = await this.orm.call("transport.trip", "get_map_data", [[tripId]]);
            this.renderTripMap(data);
        } catch (error) {
            console.error("Error loading trip map data:", error);
        }
    }

    renderTripMap(data) {
        if (!this.map || !data) return;

        Object.keys(this.layers).forEach((key) => {
            if (this.layers[key]) {
                this.layers[key].remove();
                this.layers[key] = null;
            }
        });

        const bounds = [];

        // 1. Reference route polyline (Blue)
        if (data.reference_polyline && data.reference_polyline.length > 0) {
            this.layers.reference = window.L.polyline(data.reference_polyline, {
                color: "#1976D2",
                weight: 5,
                opacity: 0.75,
                dashArray: "6, 8",
            }).addTo(this.map);
            this.layers.reference.bindPopup(`<strong>Ruta Programada:</strong> ${data.route_name}`);
            data.reference_polyline.forEach((pt) => bounds.push(pt));
        }

        // 2. Route Checkpoints & Stops
        if (data.stops && data.stops.length > 0) {
            const stopGroup = window.L.layerGroup().addTo(this.map);
            data.stops.forEach((s) => {
                if (!s.latitude || !s.longitude) return;
                const pos = [s.latitude, s.longitude];
                bounds.push(pos);

                let pinClass = "georutex-stop-marker";
                if (s.stop_type === "origin") pinClass += " georutex-stop-origin";
                else if (s.stop_type === "destination") pinClass += " georutex-stop-destination";

                const icon = window.L.divIcon({
                    className: "custom-div-icon",
                    html: `<div class="${pinClass}">${s.sequence}</div>`,
                    iconSize: [26, 26],
                    iconAnchor: [13, 13],
                });

                const marker = window.L.marker(pos, { icon }).addTo(stopGroup);
                marker.bindTooltip(`Parada ${s.sequence}: ${s.name}`, {
                    direction: "top",
                    offset: [0, -14],
                });
                marker.bindPopup(`
                    <div style="font-size: 12px; line-height: 1.4;">
                        <strong>Control ${s.sequence}: ${s.name}</strong><br/>
                        <b>Tipo:</b> ${s.stop_type}<br/>
                        <b>Radio geocerca:</b> ${s.radius_m} m<br/>
                        <b>Estado visita:</b> ${s.status}<br/>
                        ${s.scheduled_at ? `<b>Programado:</b> ${s.scheduled_at}` : ""}
                    </div>
                `);

                if (s.radius_m) {
                    window.L.circle(pos, {
                        radius: s.radius_m,
                        color: s.stop_type === "origin" ? "#2E7D32" : (s.stop_type === "destination" ? "#C62828" : "#1976D2"),
                        weight: 1,
                        fillOpacity: 0.15,
                    }).addTo(stopGroup);
                }
            });
            this.layers.stops = stopGroup;
        }

        // 3. Recorded GPS trajectory (Purple line)
        if (data.positions && data.positions.length > 0) {
            const gpsCoords = data.positions.map((p) => [p.latitude, p.longitude]);
            gpsCoords.forEach((pt) => bounds.push(pt));

            this.layers.trajectory = window.L.polyline(gpsCoords, {
                color: "#7B1FA2",
                weight: 4,
                opacity: 0.85,
            }).addTo(this.map);

            const ptsGroup = window.L.layerGroup().addTo(this.map);
            data.positions.forEach((p, idx) => {
                const circle = window.L.circleMarker([p.latitude, p.longitude], {
                    radius: 3,
                    color: "#7B1FA2",
                    fillColor: p.source === "real" ? "#2E7D32" : "#E65100",
                    fillOpacity: 0.9,
                    weight: 1,
                }).addTo(ptsGroup);

                circle.bindPopup(`
                    <div style="font-size: 11px;">
                        <strong>Punto #${idx + 1}</strong><br/>
                        <b>Hora UTC:</b> ${p.fix_time_utc}<br/>
                        <b>Hora Local:</b> ${p.fix_time_local}<br/>
                        <b>Velocidad:</b> ${p.speed} km/h<br/>
                        <b>Origen:</b> ${p.source.toUpperCase()}<br/>
                    </div>
                `);
            });

            // 4. Latest position bus marker
            if (data.latest_position) {
                const lp = data.latest_position;
                const busIcon = window.L.divIcon({
                    className: "custom-div-icon",
                    html: `
                        <div class="georutex-live-bus-marker ${data.freshness}">
                            <i class="fa fa-bus" style="font-size: 14px;"></i>
                            <div class="georutex-pulse-ring"></div>
                        </div>
                    `,
                    iconSize: [32, 32],
                    iconAnchor: [16, 16],
                });

                this.layers.latest = window.L.marker([lp.latitude, lp.longitude], { icon: busIcon }).addTo(this.map);
                this.layers.latest.bindPopup(`
                    <div style="font-size: 12px; line-height: 1.4;">
                        <strong>${data.vehicle_name} (${data.vehicle_plate})</strong><br/>
                        <b>Conductor:</b> ${data.driver_name}<br/>
                        <b>Velocidad:</b> ${lp.speed} km/h<br/>
                        <b>Última captura:</b> ${lp.fix_time_local}<br/>
                        <b>Origen:</b> ${lp.source.toUpperCase()}<br/>
                        <b>Estado señal:</b> ${data.freshness.toUpperCase()}
                    </div>
                `);
            }
        }

        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [30, 30] });
        }
    }

    onFitBounds() {
        if (this.map && this.layers.reference) {
            this.map.fitBounds(this.layers.reference.getBounds(), { padding: [20, 20] });
        } else if (this.map && this.layers.trajectory) {
            this.map.fitBounds(this.layers.trajectory.getBounds(), { padding: [20, 20] });
        }
    }
}

export class VehicleMapWidget extends Component {
    static template = "uta_transport_monitor.VehicleMapWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.mapRef = useRef("vehicleMapContainer");
        this.map = null;
        this.layers = {
            trail: null,
            marker: null,
        };

        onMounted(() => {
            this.initMap();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });

        useEffect(
            () => {
                if (this.map && this.props.record && this.props.record.resId) {
                    this.loadVehicleData(this.props.record.resId);
                }
            },
            () => [
                this.props.record && this.props.record.resId,
                this.props.record && this.props.record.data.last_gps_fix_time,
            ]
        );
    }

    initMap() {
        if (!this.mapRef.el || this.map) return;
        if (typeof window.L === "undefined") return;

        this.map = window.L.map(this.mapRef.el).setView([-1.249, -78.625], 13);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);

        if (this.props.record && this.props.record.resId) {
            this.loadVehicleData(this.props.record.resId);
        }
    }

    async loadVehicleData(vehicleId) {
        try {
            const data = await this.orm.call("fleet.vehicle", "get_vehicle_live_map_data", [[vehicleId]]);
            this.renderVehicleMap(data);
        } catch (error) {
            console.error("Error loading vehicle map data:", error);
        }
    }

    renderVehicleMap(data) {
        if (!this.map || !data) return;

        Object.keys(this.layers).forEach((key) => {
            if (this.layers[key]) {
                this.layers[key].remove();
                this.layers[key] = null;
            }
        });

        const bounds = [];

        // Trail of recent positions
        if (data.history_trail && data.history_trail.length > 0) {
            const trailCoords = data.history_trail.map((p) => [p.latitude, p.longitude]);
            trailCoords.forEach((pt) => bounds.push(pt));

            this.layers.trail = window.L.polyline(trailCoords, {
                color: "#0288D1",
                weight: 3,
                opacity: 0.6,
                dashArray: "4, 6",
            }).addTo(this.map);
        }

        // Current / latest position
        if (data.latitude && data.longitude) {
            const pos = [data.latitude, data.longitude];
            bounds.push(pos);

            const busIcon = window.L.divIcon({
                className: "custom-div-icon",
                html: `
                    <div class="georutex-live-bus-marker ${data.freshness}">
                        <i class="fa fa-bus" style="font-size: 14px;"></i>
                        <div class="georutex-pulse-ring"></div>
                    </div>
                `,
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            });

            this.layers.marker = window.L.marker(pos, { icon: busIcon }).addTo(this.map);
            this.layers.marker.bindPopup(`
                <div style="font-size: 12px; line-height: 1.4;">
                    <strong>${data.name} (${data.license_plate})</strong><br/>
                    <b>Conductor:</b> ${data.driver_name}<br/>
                    <b>Velocidad:</b> ${data.speed} km/h<br/>
                    <b>Hora local:</b> ${data.fix_time_local}<br/>
                    <b>Estado de señal:</b> ${data.freshness.toUpperCase()}<br/>
                    <b>Tipo:</b> ${data.is_simulated ? "SIMULADO" : (data.is_physical_accredited ? "REAL ACREDITADO" : "NO ACREDITADO")}
                </div>
            `);
        }

        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [40, 40] });
        }
    }
}

registry.category("fields").add("trip_map_widget", TripMapWidget);
registry.category("fields").add("vehicle_map_widget", VehicleMapWidget);

