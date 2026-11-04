/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, onWillUnmount, useRef, useEffect, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class RouteEditorWidget extends Component {
    static template = "uta_transport_monitor.RouteEditorWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapRef = useRef("mapContainer");
        this.map = null;
        this.markerLayerGroup = null;
        this.geofenceLayerGroup = null;
        this.polylineLayer = null;
        this.corridorLayer = null;

        this.state = useState({
            loading: false,
            isDraft: true,
            addMode: true,
            showCorridor: true,
            showGeofences: true,
            corridorWidth: 40,
            stops: [],
            estimatedDistance: 0,
            referencePolylineCoords: [],
            modalOpen: false,
            currentEditStop: {
                id: false,
                name: "",
                stop_type: "checkpoint",
                latitude: -1.249,
                longitude: -78.625,
                radius_m: 30.0,
                planned_offset_seconds: 0,
                required: true,
            },
        });

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
                if (this.props.record && this.props.record.resId) {
                    void this.loadRouteData(this.props.record.resId);
                }
            },
            () => [this.props.record && this.props.record.resId]
        );
    }

    initMap() {
        if (!this.mapRef.el || this.map) return;
        if (typeof window.L === "undefined") {
            console.error("Leaflet library not loaded");
            return;
        }

        // Center default at Ambato, Ecuador: [-1.249, -78.625]
        this.map = window.L.map(this.mapRef.el).setView([-1.249, -78.625], 14);
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);

        this.markerLayerGroup = window.L.layerGroup().addTo(this.map);
        this.geofenceLayerGroup = window.L.layerGroup().addTo(this.map);

        // Map click handler for adding stops
        this.map.on("click", (e) => {
            if (this.state.isDraft && this.state.addMode && !this.state.loading) {
                const lat = parseFloat(e.latlng.lat.toFixed(6));
                const lon = parseFloat(e.latlng.lng.toFixed(6));
                void this.addNewStopAtCoordinates(lat, lon);
            }
        });

        if (this.props.record && this.props.record.resId) {
            void this.loadRouteData(this.props.record.resId);
        }
    }

    async loadRouteData(resId) {
        if (!resId) return;
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "get_route_editor_data",
                [[resId]]
            );
            this.updateFromEditorData(data);
        } catch (error) {
            console.error("Error loading route editor data:", error);
            this.notification.add(
                "Error al cargar los datos del editor de ruta: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    updateFromEditorData(data) {
        if (!data) return;
        this.state.isDraft = data.is_draft;
        this.state.corridorWidth = data.route_corridor_m || 40;
        this.state.estimatedDistance = data.estimated_distance_m || 0;
        this.state.referencePolylineCoords = data.reference_polyline_coords || [];
        this.state.stops = data.stops || [];

        // If not draft, disable add mode
        if (!this.state.isDraft) {
            this.state.addMode = false;
        }

        this.renderMapLayers();
    }

    renderMapLayers() {
        if (!this.map) return;

        // Clear existing vector layers
        this.markerLayerGroup.clearLayers();
        this.geofenceLayerGroup.clearLayers();
        if (this.polylineLayer) {
            this.polylineLayer.remove();
            this.polylineLayer = null;
        }
        if (this.corridorLayer) {
            this.corridorLayer.remove();
            this.corridorLayer = null;
        }

        const bounds = [];

        // 1. Render corridor buffer if active
        if (
            this.state.showCorridor &&
            this.state.referencePolylineCoords.length >= 2
        ) {
            this.corridorLayer = window.L.polyline(this.state.referencePolylineCoords, {
                color: "#90CAF9",
                weight: Math.max(12, Math.min(30, this.state.corridorWidth / 2)),
                opacity: 0.35,
                lineCap: "round",
                lineJoin: "round",
            }).addTo(this.map);
        }

        // 2. Render road polyline
        if (this.state.referencePolylineCoords.length >= 2) {
            this.polylineLayer = window.L.polyline(this.state.referencePolylineCoords, {
                color: "#1976D2",
                weight: 4,
                opacity: 0.85,
            }).addTo(this.map);

            this.state.referencePolylineCoords.forEach((pt) => bounds.push(pt));
        }

        // 3. Render stops & geofences
        const stopsCount = this.state.stops.length;
        this.state.stops.forEach((stop, index) => {
            const pos = [stop.latitude, stop.longitude];
            bounds.push(pos);

            let markerClass = "georutex-stop-checkpoint";
            let colorHex = "#1976D2";
            let typeLabel = "Control Intermedio";
            let iconInner = `${index + 1}`;

            if (stop.stop_type === "origin") {
                markerClass = "georutex-stop-origin";
                colorHex = "#2E7D32";
                typeLabel = "Origen / Salida";
                iconInner = '<i class="fa fa-flag" style="font-size: 11px;"></i>';
            } else if (stop.stop_type === "destination") {
                markerClass = "georutex-stop-destination";
                colorHex = "#C62828";
                typeLabel = "Destino / Llegada";
                iconInner = '<i class="fa fa-flag-checkered" style="font-size: 11px;"></i>';
            }

            // DivIcon pin
            const markerIcon = window.L.divIcon({
                className: "custom-div-icon",
                html: `
                    <div class="georutex-editor-stop-pin ${markerClass}" title="${stop.name}">
                        <span>${iconInner}</span>
                    </div>
                `,
                iconSize: [28, 28],
                iconAnchor: [14, 14],
            });

            const marker = window.L.marker(pos, {
                icon: markerIcon,
                draggable: this.state.isDraft,
            });

            // Popup
            marker.bindPopup(`
                <div style="min-width: 180px; font-size: 12px; line-height: 1.4;">
                    <strong>#${index + 1} - ${stop.name}</strong><br/>
                    <b>Tipo:</b> ${typeLabel}<br/>
                    <b>Coordenadas:</b> ${stop.latitude.toFixed(5)}, ${stop.longitude.toFixed(5)}<br/>
                    <b>Radio:</b> ${stop.radius_m} m | <b>Tiempo:</b> ${Math.round((stop.planned_offset_seconds || 0) / 60)} min (${stop.planned_offset_seconds || 0} s)<br/>
                    ${this.state.isDraft ? '<small class="text-muted">Arrastre el marcador para mover la parada</small>' : ''}
                </div>
            `);

            // Drag event handler
            if (this.state.isDraft) {
                marker.on("dragend", (e) => {
                    const newLatLng = e.target.getLatLng();
                    void this.onMarkerDragged(stop, newLatLng.lat, newLatLng.lng);
                });
            }

            this.markerLayerGroup.addLayer(marker);

            // Geofence Circle
            if (this.state.showGeofences && stop.radius_m > 0) {
                const circle = window.L.circle(pos, {
                    radius: stop.radius_m,
                    color: colorHex,
                    fillColor: colorHex,
                    fillOpacity: 0.15,
                    weight: 1.5,
                });
                this.geofenceLayerGroup.addLayer(circle);
            }
        });

        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
        }
    }

    async addNewStopAtCoordinates(lat, lon) {
        if (!this.props.record || !this.props.record.resId) {
            this.notification.add(
                "Guarde la versión en borrador antes de añadir paradas interactivas.",
                { type: "warning" }
            );
            return;
        }

        const count = this.state.stops.length;
        let defaultName = `Punto de Control ${count + 1}`;
        let defaultType = "checkpoint";

        if (count === 0) {
            defaultName = "Parada Origen";
            defaultType = "origin";
        } else if (count === 1) {
            defaultName = "Parada Destino";
            defaultType = "destination";
        }

        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "save_route_editor_stop",
                [
                    [this.props.record.resId],
                    {
                        name: defaultName,
                        stop_type: defaultType,
                        latitude: lat,
                        longitude: lon,
                        radius_m: 30.0,
                        planned_offset_seconds: count * 300,
                        required: true,
                    },
                ]
            );
            this.updateFromEditorData(data);
            await this.props.record.load();
            this.notification.add(
                `Punto '${defaultName}' añadido exitosamente.`,
                { type: "success" }
            );
        } catch (error) {
            console.error("Error adding stop:", error);
            this.notification.add(
                "Error al añadir el punto de control: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onMarkerDragged(stop, newLat, newLon) {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "save_route_editor_stop",
                [
                    [this.props.record.resId],
                    {
                        id: stop.id,
                        name: stop.name,
                        stop_type: stop.stop_type,
                        latitude: parseFloat(newLat.toFixed(6)),
                        longitude: parseFloat(newLon.toFixed(6)),
                        radius_m: stop.radius_m,
                        planned_offset_seconds: stop.planned_offset_seconds,
                        required: stop.required,
                    },
                ]
            );
            this.updateFromEditorData(data);
            await this.props.record.load();
            this.notification.add(
                `Ubicación de '${stop.name}' actualizada y trazado recalculado.`,
                { type: "info" }
            );
        } catch (error) {
            console.error("Error updating marker position:", error);
            this.notification.add(
                "Error al actualizar la ubicación: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onCalculateRoadRoute() {
        if (!this.props.record || !this.props.record.resId) return;
        this.state.loading = true;
        try {
            const resultAction = await this.orm.call(
                "transport.route.version",
                "action_calculate_road_route",
                [[this.props.record.resId]]
            );
            await this.loadRouteData(this.props.record.resId);
            await this.props.record.load();
            if (resultAction && resultAction.params) {
                this.notification.add(resultAction.params.message, {
                    type: resultAction.params.type || "success",
                });
            }
        } catch (error) {
            console.error("Error calculating road route:", error);
            this.notification.add(
                "Error al calcular trazado vial: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onAutoClassify() {
        if (!this.props.record || !this.props.record.resId) return;
        this.state.loading = true;
        try {
            const resultAction = await this.orm.call(
                "transport.route.version",
                "action_auto_classify_stops",
                [[this.props.record.resId]]
            );
            await this.loadRouteData(this.props.record.resId);
            await this.props.record.load();
            if (resultAction && resultAction.params) {
                this.notification.add(resultAction.params.message, {
                    type: resultAction.params.type || "success",
                });
            }
        } catch (error) {
            console.error("Error auto-classifying stops:", error);
            this.notification.add(
                "Error al auto-clasificar paradas: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async moveStopUp(index) {
        if (index <= 0) return;
        const newOrder = [...this.state.stops.map((s) => s.id)];
        const temp = newOrder[index];
        newOrder[index] = newOrder[index - 1];
        newOrder[index - 1] = temp;
        await this.reorderStops(newOrder);
    }

    async moveStopDown(index) {
        if (index >= this.state.stops.length - 1) return;
        const newOrder = [...this.state.stops.map((s) => s.id)];
        const temp = newOrder[index];
        newOrder[index] = newOrder[index + 1];
        newOrder[index + 1] = temp;
        await this.reorderStops(newOrder);
    }

    async reorderStops(orderedIds) {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "reorder_route_editor_stops",
                [[this.props.record.resId], orderedIds]
            );
            this.updateFromEditorData(data);
            await this.props.record.load();
            this.notification.add(
                "Orden de paradas actualizado y auto-clasificado.",
                { type: "success" }
            );
        } catch (error) {
            console.error("Error reordering stops:", error);
            this.notification.add(
                "Error al reordenar paradas: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async deleteStop(stopId) {
        if (!confirm("¿Desea eliminar este punto de control?")) return;
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "delete_route_editor_stop",
                [[this.props.record.resId], stopId]
            );
            this.updateFromEditorData(data);
            await this.props.record.load();
            this.notification.add("Punto de control eliminado.", { type: "info" });
        } catch (error) {
            console.error("Error deleting stop:", error);
            this.notification.add(
                "Error al eliminar el punto: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    focusStop(stop) {
        if (!this.map) return;
        this.map.flyTo([stop.latitude, stop.longitude], 16, { animate: true });
    }

    toggleAddMode() {
        this.state.addMode = !this.state.addMode;
    }

    toggleCorridor() {
        this.state.showCorridor = !this.state.showCorridor;
        this.renderMapLayers();
    }

    toggleGeofences() {
        this.state.showGeofences = !this.state.showGeofences;
        this.renderMapLayers();
    }

    onFitBounds() {
        const bounds = [];
        this.state.stops.forEach((s) => bounds.push([s.latitude, s.longitude]));
        this.state.referencePolylineCoords.forEach((pt) => bounds.push(pt));
        if (bounds.length > 0 && this.map) {
            this.map.fitBounds(bounds, { padding: [40, 40] });
        }
    }

    openNewStopModal() {
        this.state.currentEditStop = {
            id: false,
            name: `Punto de Control ${this.state.stops.length + 1}`,
            stop_type: this.state.stops.length === 0 ? "origin" : "checkpoint",
            latitude: -1.249,
            longitude: -78.625,
            radius_m: 30.0,
            planned_offset_seconds: this.state.stops.length * 300,
            required: true,
        };
        this.state.modalOpen = true;
    }

    editStopModal(stop) {
        this.state.currentEditStop = {
            id: stop.id,
            name: stop.name,
            stop_type: stop.stop_type,
            latitude: stop.latitude,
            longitude: stop.longitude,
            radius_m: stop.radius_m,
            planned_offset_seconds: stop.planned_offset_seconds,
            required: stop.required,
        };
        this.state.modalOpen = true;
    }

    closeModal() {
        this.state.modalOpen = false;
    }

    async saveStopFromModal() {
        const s = this.state.currentEditStop;
        if (!s.name || !s.latitude || !s.longitude) {
            this.notification.add("Por favor complete nombre y coordenadas válidas.", {
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "transport.route.version",
                "save_route_editor_stop",
                [
                    [this.props.record.resId],
                    {
                        id: s.id || false,
                        name: s.name,
                        stop_type: s.stop_type,
                        latitude: parseFloat(s.latitude),
                        longitude: parseFloat(s.longitude),
                        radius_m: parseFloat(s.radius_m),
                        planned_offset_seconds: parseInt(s.planned_offset_seconds),
                        required: !!s.required,
                    },
                ]
            );
            this.updateFromEditorData(data);
            await this.props.record.load();
            this.state.modalOpen = false;
            this.notification.add("Punto de control guardado exitosamente.", {
                type: "success",
            });
        } catch (error) {
            console.error("Error saving stop from modal:", error);
            this.notification.add(
                "Error al guardar punto: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("fields").add("route_editor_widget", RouteEditorWidget);

