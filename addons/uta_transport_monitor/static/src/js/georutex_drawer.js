/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { View } from "@web/views/view";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useChildRef, useService } from "@web/core/utils/hooks";

function prefersReducedMotion() {
    return Boolean(
        window.matchMedia &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
}

/**
 * Models compatible with right-side Drawer creation/editing inside GeoRutex.
 * Justified full-page exceptions (NOT in this map):
 * - transport.route.version (requires wide Leaflet cartographic editor)
 * - transport.trip.evaluation (generated strictly by evaluation engine, create=false)
 * - transport.vehicle.position (automated GPS telemetry history)
 */
export const DRAWER_MODEL_CONFIG = {
    "transport.incident": {
        createTitle: "Reportar incidencia",
        editTitle: "Incidencia operacional",
        subtitle: "Registra la novedad asociada al recorrido para su seguimiento.",
        eyebrow: "Incidencias",
        width: 560,
        createSaveLabel: "Enviar reporte",
        editSaveLabel: "Guardar cambios",
        saveNotice: "Incidencia guardada correctamente.",
        defaultContext: { default_source: "manual" },
    },
    "transport.route": {
        createTitle: "Crear ruta",
        editTitle: "Detalle de ruta",
        subtitle: "Define el nombre, código, sentido y puntos de origen y destino.",
        eyebrow: "Rutas",
        width: 560,
        createSaveLabel: "Crear ruta",
        editSaveLabel: "Guardar cambios",
        saveNotice: "Ruta guardada correctamente.",
        defaultContext: {},
    },
    "fleet.vehicle": {
        createTitle: "Registrar vehículo",
        editTitle: "Vehículo monitoreado",
        subtitle: "Configura la unidad operativa y su vinculación de rastreo GPS.",
        eyebrow: "Vehículos",
        width: 580,
        createSaveLabel: "Registrar vehículo",
        editSaveLabel: "Guardar cambios",
        saveNotice: "Vehículo guardado correctamente.",
        defaultContext: { default_gps_tracking_enabled: true },
    },
    "transport.trip": {
        createTitle: "Programar recorrido",
        editTitle: "Recorrido operacional",
        subtitle: "Asigna vehículo, conductor, ruta aprobada y horario previsto.",
        eyebrow: "Recorridos",
        width: 600,
        createSaveLabel: "Programar recorrido",
        editSaveLabel: "Guardar cambios",
        saveNotice: "Recorrido guardado correctamente.",
        defaultContext: {},
    },
};

function isGeoRutexShellActive() {
    const wc = document.querySelector(".o_web_client");
    return Boolean(wc && wc.classList.contains("grx-app-active"));
}

/**
 * Reusable Right-Side Drawer (Sheet) deeply integrated with Odoo 16 Form View & ORM.
 */
export class GeoRutexDrawerDialog extends Component {
    setup() {
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.modalRef = useChildRef();
        this.drawerRef = useRef("drawerRoot");
        this._tl = null;
        this._footerObserver = null;
        this._isClosing = false;
        this._isSaving = false;
        this._recordDirty = false;

        const buttonTemplate = this.props.buttonTemplate || "web.FormViewDialog.ToOne.buttons";

        this.viewProps = {
            type: "form",
            buttonTemplate,
            context: this.props.context || {},
            display: { controlPanel: false },
            mode: this.props.mode || "edit",
            resId: this.props.resId || false,
            resModel: this.props.resModel,
            viewId: this.props.viewId || false,
            preventCreate: Boolean(this.props.preventCreate),
            preventEdit: Boolean(this.props.preventEdit),
            discardRecord: async () => {
                if (this.props.onRecordDiscarded) {
                    await this.props.onRecordDiscarded();
                }
                this._recordDirty = false;
                await this.animatedClose(true);
            },
            saveRecord: async (record, { saveAndNew } = {}) => {
                if (this._isSaving) return false;
                this._isSaving = true;
                try {
                    const saved = await record.save({ stayInEdition: true, noReload: true });
                    if (saved) {
                        this._recordDirty = false;
                        if (this.props.saveNotice) {
                            this.notification.add(this.props.saveNotice, {
                                type: "success",
                                sticky: false,
                            });
                        }
                        if (this.props.onRecordSaved) {
                            await this.props.onRecordSaved(record);
                        }
                        if (saveAndNew) {
                            const context = Object.assign({}, this.props.context || {});
                            Object.keys(context).forEach((k) => {
                                if (k.startsWith("default_")) {
                                    delete context[k];
                                }
                            });
                            await record.model.load({ resId: null, context });
                        } else {
                            await this.animatedClose(true);
                        }
                    }
                    return saved;
                } finally {
                    this._isSaving = false;
                }
            },
        };

        this._onKeyDown = (ev) => {
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                void this.animatedClose(false);
            }
        };

        this._onInputChange = (ev) => {
            if (ev && ev.isTrusted) {
                this._recordDirty = true;
            }
        };

        this._polishFooterButtons = () => {
            const modalEl = this.modalRef.el;
            if (!modalEl) return;
            const footer = modalEl.querySelector(".modal-footer");
            if (!footer) return;
            if (footer.childElementCount > 1) {
                const defaultBtn = footer.querySelector("button.o-default-button");
                if (defaultBtn) defaultBtn.classList.add("d-none");
            }
            const saveBtn = footer.querySelector(".o_form_button_save");
            if (saveBtn && this.props.saveLabel && saveBtn.textContent.trim() !== this.props.saveLabel) {
                saveBtn.textContent = this.props.saveLabel;
            }
            const cancelBtn = footer.querySelector(".o_form_button_cancel");
            if (cancelBtn && cancelBtn.textContent.trim() !== "Cancelar") {
                cancelBtn.textContent = "Cancelar";
            }
        };

        onMounted(() => {
            const modalEl = this.modalRef.el;
            if (modalEl) {
                modalEl.classList.add("grx-drawer-modal");
                if (this.props.width) {
                    modalEl.style.setProperty("--grx-drawer-w", `${this.props.width}px`);
                }
                const footer = modalEl.querySelector(".modal-footer");
                if (footer) {
                    this._polishFooterButtons();
                    this._footerObserver = new MutationObserver(() => this._polishFooterButtons());
                    this._footerObserver.observe(footer, { childList: true, subtree: true });
                }
                modalEl.addEventListener("input", this._onInputChange, true);
                modalEl.addEventListener("change", this._onInputChange, true);

                // Animate Drawer entrance with GSAP Timeline
                const dialogEl = modalEl.querySelector(".modal-dialog");
                const bodyEl = modalEl.querySelector(".modal-body");
                if (window.gsap && dialogEl && !prefersReducedMotion()) {
                    this._tl = window.gsap.timeline({
                        defaults: { ease: "power3.out" },
                    });
                    this._tl
                        .fromTo(
                            modalEl,
                            { backgroundColor: "rgba(17, 24, 39, 0)" },
                            { backgroundColor: "rgba(17, 24, 39, 0.34)", duration: 0.22 },
                            0
                        )
                        .fromTo(
                            dialogEl,
                            { xPercent: 100 },
                            { xPercent: 0, duration: 0.3, clearProps: "transform" },
                            0
                        );
                    if (bodyEl) {
                        this._tl.fromTo(
                            bodyEl,
                            { y: 10, opacity: 0 },
                            { y: 0, opacity: 1, duration: 0.22, clearProps: "transform,opacity" },
                            0.08
                        );
                    }
                } else {
                    modalEl.style.backgroundColor = "rgba(17, 24, 39, 0.34)";
                }

                const focusTarget =
                    modalEl.querySelector(".grx-drawer-close-btn") || modalEl;
                window.setTimeout(() => {
                    this._polishFooterButtons();
                    if (focusTarget && typeof focusTarget.focus === "function") {
                        focusTarget.focus({ preventScroll: true });
                    }
                }, 60);
            }
            window.addEventListener("keydown", this._onKeyDown, true);
        });

        onWillUnmount(() => {
            window.removeEventListener("keydown", this._onKeyDown, true);
            if (this._footerObserver) {
                this._footerObserver.disconnect();
                this._footerObserver = null;
            }
            const modalEl = this.modalRef.el;
            if (modalEl) {
                modalEl.removeEventListener("input", this._onInputChange, true);
                modalEl.removeEventListener("change", this._onInputChange, true);
            }
            if (this._tl) {
                this._tl.kill();
                this._tl = null;
            }
            // Guarantee main page scroll is never left locked after closing Drawer
            window.requestAnimationFrame(() => {
                if (!document.querySelector(".modal.d-block")) {
                    document.body.classList.remove("modal-open");
                    document.body.style.overflow = "";
                }
            });
        });
    }

    get canOpenFullRecord() {
        return Boolean(this.props.allowOpenFull && this.props.resId);
    }

    async openFullRecord() {
        const { resModel, resId, title } = this.props;
        await this.animatedClose(true);
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name: title || "Registro",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    async animatedClose(force = false) {
        if (this._isClosing) return;
        const modalEl = this.modalRef.el;
        const isDirty = !force && this._recordDirty;
        if (isDirty) {
            const confirmed = window.confirm(
                "Tienes cambios sin guardar en este panel. ¿Deseas descartarlos y cerrar?"
            );
            if (!confirmed) {
                return;
            }
        }
        this._isClosing = true;

        const dialogEl = modalEl && modalEl.querySelector(".modal-dialog");
        if (window.gsap && modalEl && dialogEl && !prefersReducedMotion()) {
            await new Promise((resolve) => {
                const closeTl = window.gsap.timeline({
                    onComplete: resolve,
                });
                closeTl
                    .to(dialogEl, { xPercent: 100, duration: 0.22, ease: "power2.in" }, 0)
                    .to(modalEl, { backgroundColor: "rgba(17, 24, 39, 0)", duration: 0.18 }, 0);
            });
        }
        this.props.close();
    }
}

GeoRutexDrawerDialog.components = { Dialog, View };
GeoRutexDrawerDialog.template = "uta_transport_monitor.GeoRutexDrawerDialog";
GeoRutexDrawerDialog.props = {
    close: Function,
    resModel: String,
    resId: { type: [Number, Boolean], optional: true },
    title: { type: String, optional: true },
    subtitle: { type: String, optional: true },
    eyebrow: { type: String, optional: true },
    saveLabel: { type: String, optional: true },
    context: { type: Object, optional: true },
    viewId: { type: [Number, Boolean], optional: true },
    mode: {
        optional: true,
        validate: (m) => ["edit", "readonly"].includes(m),
    },
    width: { type: Number, optional: true },
    allowOpenFull: { type: Boolean, optional: true },
    preventCreate: { type: Boolean, optional: true },
    preventEdit: { type: Boolean, optional: true },
    saveNotice: { type: String, optional: true },
    buttonTemplate: { type: String, optional: true },
    onRecordSaved: { type: Function, optional: true },
    onRecordDiscarded: { type: Function, optional: true },
};
GeoRutexDrawerDialog.defaultProps = {
    resId: false,
    title: "Detalle",
    subtitle: "",
    eyebrow: "GeoRutex",
    saveLabel: "Guardar cambios",
    width: 560,
    allowOpenFull: true,
    preventCreate: false,
    preventEdit: false,
    onRecordSaved: () => {},
};

/**
 * Global OWL Service: `useService("georutex_drawer")`
 */
export const georutexDrawerService = {
    dependencies: ["dialog", "orm", "user"],
    start(env, { dialog, orm, user }) {
        return {
            openRecord(options) {
                const cfg = DRAWER_MODEL_CONFIG[options.resModel] || {};
                const isNew = !options.resId;
                return dialog.add(GeoRutexDrawerDialog, {
                    resModel: options.resModel,
                    resId: options.resId || false,
                    title:
                        options.title ||
                        (isNew ? cfg.createTitle : cfg.editTitle) ||
                        "Registro",
                    subtitle: options.subtitle !== undefined ? options.subtitle : cfg.subtitle || "",
                    eyebrow: options.eyebrow || cfg.eyebrow || "GeoRutex",
                    saveLabel:
                        options.saveLabel ||
                        (isNew ? cfg.createSaveLabel : cfg.editSaveLabel) ||
                        "Guardar cambios",
                    context: Object.assign({}, cfg.defaultContext || {}, options.context || {}),
                    viewId: options.viewId || false,
                    mode: options.mode || "edit",
                    width: options.width || cfg.width || 560,
                    allowOpenFull: options.allowOpenFull !== false && !isNew,
                    preventCreate: Boolean(options.preventCreate),
                    preventEdit: Boolean(options.preventEdit),
                    saveNotice: options.saveNotice || cfg.saveNotice || "",
                    onRecordSaved: options.onRecordSaved,
                    onRecordDiscarded: options.onRecordDiscarded,
                });
            },
            async openPreferences(userId = null) {
                const targetUid = userId || user.userId;
                const actionDesc = await orm.call("res.users", "action_get", []);
                const viewId =
                    (actionDesc && actionDesc.view_id && actionDesc.view_id[0]) ||
                    (actionDesc && actionDesc.views && actionDesc.views[0] && actionDesc.views[0][0]) ||
                    false;
                return dialog.add(GeoRutexDrawerDialog, {
                    resModel: "res.users",
                    resId: targetUid,
                    viewId,
                    title: "Perfil y preferencias",
                    subtitle: "Cuenta, idioma, zona horaria, notificaciones y seguridad",
                    eyebrow: "Mi cuenta",
                    saveLabel: "Guardar cambios",
                    width: 540,
                    allowOpenFull: false,
                    saveNotice: "Preferencias actualizadas correctamente.",
                });
            },
        };
    },
};

registry.category("services").add("georutex_drawer", georutexDrawerService);

/**
 * Unify "Nuevo" button on GeoRutex List Views for compatible models ONLY.
 * Never affects foreign Odoo apps or non-compatible models.
 */
patch(ListController.prototype, "uta_transport_monitor.listCreateInDrawer", {
    async createRecord(params = {}) {
        const resModel = this.props && this.props.resModel;
        const cfg = resModel && DRAWER_MODEL_CONFIG[resModel];
        const drawer = this.env && this.env.services && this.env.services.georutex_drawer;
        if (cfg && drawer && isGeoRutexShellActive() && !this.editable) {
            const ctx = Object.assign(
                {},
                (this.props && this.props.context) || {},
                cfg.defaultContext || {}
            );
            drawer.openRecord({
                resModel,
                context: ctx,
                onRecordSaved: async () => {
                    await this.model.root.load();
                    this.render(true);
                },
            });
            return;
        }
        return this._super(params);
    },
});

/**
 * Unify "Nuevo" button on GeoRutex Kanban Views for compatible models ONLY.
 */
patch(KanbanController.prototype, "uta_transport_monitor.kanbanCreateInDrawer", {
    async createRecord(group) {
        const resModel = this.props && this.props.resModel;
        const cfg = resModel && DRAWER_MODEL_CONFIG[resModel];
        const drawer = this.env && this.env.services && this.env.services.georutex_drawer;
        if (cfg && drawer && isGeoRutexShellActive()) {
            const ctx = Object.assign(
                {},
                (this.model && this.model.root && this.model.root.context) || {},
                cfg.defaultContext || {}
            );
            drawer.openRecord({
                resModel,
                context: ctx,
                onRecordSaved: async () => {
                    await this.model.root.load();
                    this.model.useSampleModel = false;
                    this.render(true);
                },
            });
            return;
        }
        return this._super(group);
    },
});
