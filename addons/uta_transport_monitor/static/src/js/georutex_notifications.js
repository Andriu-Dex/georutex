/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { animateGeorutexPopover } from "./georutex_motion";

export class GeoRutexNotificationBell extends Component {
    static template = "uta_transport_monitor.GeoRutexNotificationBell";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.rootRef = useRef("notifRoot");
        this.panelRef = useRef("notifPanel");
        this._pollTimer = null;

        this.state = useState({
            open: false,
            filter: "all",
            isLoading: false,
            unreadCount: 0,
            items: [],
        });

        this._onDocClick = (ev) => {
            if (this.state.open && this.rootRef.el && !this.rootRef.el.contains(ev.target)) {
                this.state.open = false;
            }
        };

        this._onKeyDown = (ev) => {
            if (ev.key === "Escape" && this.state.open) {
                this.state.open = false;
            }
        };

        onMounted(() => {
            void this.loadNotifications();
            document.addEventListener("click", this._onDocClick, true);
            window.addEventListener("keydown", this._onKeyDown);
            this._pollTimer = window.setInterval(() => {
                void this.loadNotifications(true);
            }, 60000);
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this._onDocClick, true);
            window.removeEventListener("keydown", this._onKeyDown);
            if (this._pollTimer) {
                window.clearInterval(this._pollTimer);
                this._pollTimer = null;
            }
        });
    }

    async loadNotifications(silent = false) {
        if (!silent) this.state.isLoading = true;
        try {
            const res = await this.orm.call(
                "transport.notification",
                "get_my_notifications",
                [this.state.filter === "unread", 30]
            );
            this.state.unreadCount = (res && res.unread_count) || 0;
            this.state.items = (res && res.items) || [];
        } catch (_err) {
            // Silently ignore if user does not belong to GeoRutex groups
        } finally {
            if (!silent) this.state.isLoading = false;
        }
    }

    async togglePanel() {
        this.state.open = !this.state.open;
        if (this.state.open) {
            await this.loadNotifications(false);
            window.requestAnimationFrame(() => {
                if (this.panelRef.el) {
                    animateGeorutexPopover(this.panelRef.el);
                }
            });
        }
    }

    async setFilter(filter) {
        this.state.filter = filter;
        await this.loadNotifications(false);
    }

    async markAllRead() {
        try {
            await this.orm.call("transport.notification", "action_mark_all_read", []);
            await this.loadNotifications(false);
        } catch (_err) {
            this.notification.add("No se pudieron actualizar las notificaciones.", { type: "warning" });
        }
    }

    async openNotification(item) {
        try {
            if (!item.is_read) {
                await this.orm.call("transport.notification", "action_mark_read", [item.id]);
            }
            this.state.open = false;
            await this.loadNotifications(true);
            if (item.res_model && item.res_id) {
                await this.actionService.doAction({
                    type: "ir.actions.act_window",
                    name: item.title,
                    res_model: item.res_model,
                    res_id: item.res_id,
                    views: [[false, "form"]],
                    view_mode: "form",
                    target: "current",
                });
            }
        } catch (_err) {
            this.notification.add(
                "El registro asociado ya no se encuentra disponible o autorizado para tu perfil.",
                { type: "warning", sticky: false }
            );
        }
    }
}

registry.category("systray").add(
    "uta_transport_monitor.GeoRutexNotificationBell",
    { Component: GeoRutexNotificationBell },
    { sequence: 15 }
);
