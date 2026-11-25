/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
import { onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { animateGeorutexEmptyStates, animateGeorutexPopover } from "./georutex_motion";

const GEORUTEX_ROOT_XMLID = "uta_transport_monitor.menu_georutex_root";
const SIDEBAR_COLLAPSED_KEY = "grx.sidebar.collapsed";
const CLOSED_GROUPS_KEY = "grx.sidebar.closedGroups";
const SELECTED_XMLID_KEY = "georutex.selectedMenuXmlid";

const MENU_ICONS = {
    "uta_transport_monitor.menu_georutex_admin_home": "fa-th-large",
    "uta_transport_monitor.menu_georutex_driver_home": "fa-home",
    "uta_transport_monitor.menu_georutex_dashboard_main": "fa-bar-chart",
    "uta_transport_monitor.menu_georutex_my_trips": "fa-road",
    "uta_transport_monitor.menu_georutex_live_fleet_map": "fa-map-marker",
    "uta_transport_monitor.menu_georutex_trips": "fa-road",
    "uta_transport_monitor.menu_georutex_incidents": "fa-exclamation-triangle",
    "uta_transport_monitor.menu_georutex_evaluations": "fa-check-square-o",
    "uta_transport_monitor.menu_georutex_routes": "fa-map-signs",
    "uta_transport_monitor.menu_georutex_route_versions": "fa-code-fork",
    "uta_transport_monitor.menu_georutex_fleet": "fa-bus",
    "uta_transport_monitor.menu_georutex_positions": "fa-crosshairs",
    "uta_transport_monitor.menu_georutex_operations": "fa-sliders",
    "uta_transport_monitor.menu_georutex_routes_cat": "fa-map-o",
    "uta_transport_monitor.menu_georutex_monitoring": "fa-signal",
};

const CLEAN_MENU_LABELS = {
    "uta_transport_monitor.menu_georutex_admin_home": "Centro de operaciones",
    "uta_transport_monitor.menu_georutex_dashboard_main": "Análisis del servicio",
    "uta_transport_monitor.menu_georutex_live_fleet_map": "Mapa en vivo",
    "uta_transport_monitor.menu_georutex_trips": "Recorridos",
    "uta_transport_monitor.menu_georutex_incidents": "Incidencias",
    "uta_transport_monitor.menu_georutex_evaluations": "Evaluaciones",
    "uta_transport_monitor.menu_georutex_routes": "Rutas",
    "uta_transport_monitor.menu_georutex_route_versions": "Versiones de ruta",
    "uta_transport_monitor.menu_georutex_fleet": "Vehículos",
    "uta_transport_monitor.menu_georutex_positions": "Historial GPS",
    "uta_transport_monitor.menu_georutex_operations": "Operaciones",
    "uta_transport_monitor.menu_georutex_routes_cat": "Rutas y flota",
    "uta_transport_monitor.menu_georutex_monitoring": "Telemetría GPS",
};

const DRIVER_MENU_LABELS = {
    "uta_transport_monitor.menu_georutex_driver_home": "Mi jornada",
    "uta_transport_monitor.menu_georutex_my_trips": "Mis recorridos",
    "uta_transport_monitor.menu_georutex_live_fleet_map": "Mi mapa",
    "uta_transport_monitor.menu_georutex_incidents": "Mis incidencias",
};

const MENU_XMLID_TO_CLEAN_PATH = {
    "uta_transport_monitor.menu_georutex_admin_home": "/georutex/centro-control",
    "uta_transport_monitor.menu_georutex_driver_home": "/georutex/inicio-conductor",
    "uta_transport_monitor.menu_georutex_dashboard_main": "/georutex/dashboard",
    "uta_transport_monitor.menu_georutex_my_trips": "/georutex/mis-recorridos",
    "uta_transport_monitor.menu_georutex_live_fleet_map": "/georutex/mapa-en-vivo",
    "uta_transport_monitor.menu_georutex_trips": "/georutex/recorridos",
    "uta_transport_monitor.menu_georutex_incidents": "/georutex/incidencias",
    "uta_transport_monitor.menu_georutex_evaluations": "/georutex/evaluaciones",
    "uta_transport_monitor.menu_georutex_routes": "/georutex/rutas",
    "uta_transport_monitor.menu_georutex_route_versions": "/georutex/versiones-ruta",
    "uta_transport_monitor.menu_georutex_fleet": "/georutex/flota",
    "uta_transport_monitor.menu_georutex_positions": "/georutex/telemetria",
};

function readClosedGroups() {
    try {
        const raw = window.localStorage.getItem(CLOSED_GROUPS_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch (_err) {
        return [];
    }
}

function writeClosedGroups(list) {
    try {
        window.localStorage.setItem(CLOSED_GROUPS_KEY, JSON.stringify(list));
    } catch (_err) {
        // Ignore storage quota errors
    }
}

function isMobileViewport() {
    return window.innerWidth < 992;
}

function applyShellClasses(collapsed, mobileOpen, isGeoRutexApp) {
    const webClient = document.querySelector(".o_web_client");
    if (!webClient) return;

    const canManageApps = Boolean(session.georutex_can_manage_apps);
    const isDriverOnly = Boolean(session.georutex_is_driver_only);
    const isAnalystOnly = Boolean(session.georutex_is_analyst_only);

    webClient.classList.toggle("o_georutex_no_apps_menu", !canManageApps);
    webClient.classList.toggle("o_georutex_driver_mode", isDriverOnly);
    webClient.classList.toggle("o_georutex_analyst_mode", isAnalystOnly);
    webClient.classList.toggle("grx-app-active", Boolean(isGeoRutexApp));
    webClient.classList.toggle(
        "grx-sb-collapsed",
        Boolean(isGeoRutexApp) && Boolean(collapsed) && !isMobileViewport()
    );
    webClient.classList.toggle(
        "grx-sb-mobile-open",
        Boolean(isGeoRutexApp) && Boolean(mobileOpen) && isMobileViewport()
    );
}

function syncCleanBrowserUrl(activeXmlid, isGeoRutexApp) {
    if (!isGeoRutexApp || !window.history || !window.history.replaceState) return;
    const currentPath = window.location.pathname || "";
    if (!currentPath.startsWith("/web") && !currentPath.startsWith("/georutex/")) {
        return;
    }
    let cleanPath = (activeXmlid && MENU_XMLID_TO_CLEAN_PATH[activeXmlid]) || null;
    if (!cleanPath) {
        if (document.querySelector(".grx-driver-home")) {
            cleanPath = "/georutex/inicio-conductor";
        } else if (document.querySelector(".grx-admin-home")) {
            cleanPath = "/georutex/centro-control";
        } else if (document.querySelector(".grx-analytics-page")) {
            cleanPath = "/georutex/dashboard";
        } else if (document.querySelector(".o_georutex_live_fleet_view")) {
            cleanPath = "/georutex/mapa-en-vivo";
        }
    }
    if (cleanPath && (window.location.pathname !== cleanPath || window.location.hash)) {
        try {
            window.history.replaceState(window.history.state, "", cleanPath);
        } catch (_err) {
            // Ignore restricted history updates
        }
    }
}

function localizeFallbackUiButtons() {
    document
        .querySelectorAll(".o_list_button_add, .o-kanban-button-new")
        .forEach((button) => {
            if (button.textContent.trim().toLowerCase() === "new") {
                button.textContent = "Nuevo";
            }
        });
    document
        .querySelectorAll(".o_form_status_indicator .o_form_button_save")
        .forEach((button) => {
            if (!button.getAttribute("title")) {
                button.setAttribute("title", _t("Guardar"));
            }
        });
}

function findMenuByIdOrXmlid(sections, menuId, xmlid) {
    for (const sec of sections || []) {
        if ((menuId && sec.id === menuId) || (xmlid && sec.xmlid === xmlid)) {
            return sec;
        }
        if (sec.childrenTree && sec.childrenTree.length) {
            const found = findMenuByIdOrXmlid(sec.childrenTree, menuId, xmlid);
            if (found) return found;
        }
    }
    return null;
}

patch(NavBar.prototype, "uta_transport_monitor.georutexApplicationShell", {
    setup() {
        this._super(...arguments);
        this.titleService = useService("title");

        let initialCollapsed = false;
        try {
            const saved = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
            if (saved !== null) {
                initialCollapsed = saved === "true";
            } else {
                initialCollapsed = window.innerWidth >= 992 && window.innerWidth < 1180;
            }
        } catch (_err) {
            initialCollapsed = false;
        }

        const initialXmlid = window.sessionStorage.getItem(SELECTED_XMLID_KEY) || "";

        this.grxNav = useState({
            collapsed: initialCollapsed,
            mobileOpen: false,
            closedGroups: readClosedGroups(),
            activeMenuId: null,
            activeXmlid: initialXmlid,
            roleLabel: session.georutex_role_label || "Operación",
            openForeignDropdownId: null,
        });

        this._grxOnResize = () => {
            if (!isMobileViewport() && this.grxNav.mobileOpen) {
                this.grxNav.mobileOpen = false;
            }
            applyShellClasses(this.grxNav.collapsed, this.grxNav.mobileOpen, this.isGeoRutexApp());
        };

        this._grxOnKeyDown = (ev) => {
            if (ev.key === "Escape") {
                if (this.grxNav.mobileOpen) {
                    this.closeMobileSidebar();
                }
                if (this.grxNav.openForeignDropdownId !== null) {
                    this.grxNav.openForeignDropdownId = null;
                }
            }
        };

        this._grxOnDocumentClick = (ev) => {
            if (
                this.grxNav.openForeignDropdownId !== null &&
                !ev.target.closest(".grx-foreign-dropdown")
            ) {
                this.grxNav.openForeignDropdownId = null;
            }
            // Subtle GSAP entrance on navbar dropdowns / systray popovers
            const toggler = ev.target.closest(
                ".o_main_navbar .o_navbar_apps_menu .dropdown-toggle, " +
                ".o_main_navbar .o_menu_systray .o_MessagingMenu_toggler, " +
                ".o_main_navbar .o_menu_systray .o_ActivityMenuView_dropdownToggle, " +
                ".o_main_navbar .o_user_menu .dropdown-toggle"
            );
            if (toggler) {
                window.requestAnimationFrame(() => {
                    const menu = document.querySelector(
                        ".o_main_navbar .dropdown-menu.show, " +
                        ".o_main_navbar .o_MessagingMenu_dropdownMenu, " +
                        ".o_main_navbar .o_ActivityMenuView_dropdownMenu"
                    );
                    if (menu) {
                        animateGeorutexPopover(menu);
                    }
                });
            }
        };

        this._grxSyncActiveFromHash = () => {
            const isGrx = this.isGeoRutexApp();
            if (isGrx) {
                const hash = window.location.hash || "";
                const m = hash.match(/menu_id=(\d+)/);
                if (m) {
                    const idNum = parseInt(m[1], 10);
                    this.grxNav.activeMenuId = idNum;
                    const matched = findMenuByIdOrXmlid(this.currentAppSections, idNum, null);
                    if (matched && matched.xmlid) {
                        this.grxNav.activeXmlid = matched.xmlid;
                        window.sessionStorage.setItem(SELECTED_XMLID_KEY, matched.xmlid);
                    }
                } else {
                    let inferredXmlid = "";
                    if (document.querySelector(".grx-admin-home")) {
                        inferredXmlid = "uta_transport_monitor.menu_georutex_admin_home";
                    } else if (document.querySelector(".grx-driver-home")) {
                        inferredXmlid = "uta_transport_monitor.menu_georutex_driver_home";
                    } else if (document.querySelector(".grx-analytics-page")) {
                        inferredXmlid = "uta_transport_monitor.menu_georutex_dashboard_main";
                    } else if (document.querySelector(".o_georutex_live_fleet_view")) {
                        inferredXmlid = "uta_transport_monitor.menu_georutex_live_fleet_map";
                    }
                    if (inferredXmlid) {
                        this.grxNav.activeXmlid = inferredXmlid;
                        const matched = findMenuByIdOrXmlid(
                            this.currentAppSections,
                            null,
                            inferredXmlid
                        );
                        if (matched) this.grxNav.activeMenuId = matched.id;
                    } else if (!this.grxNav.activeMenuId && this.currentAppSections.length) {
                        const firstLeaf = this.currentAppSections[0];
                        if (firstLeaf && !firstLeaf.childrenTree.length) {
                            this.grxNav.activeMenuId = firstLeaf.id;
                            if (firstLeaf.xmlid) {
                                this.grxNav.activeXmlid = firstLeaf.xmlid;
                            }
                        }
                    }
                }
            } else {
                this.grxNav.mobileOpen = false;
                this.grxNav.openForeignDropdownId = null;
            }
            applyShellClasses(this.grxNav.collapsed, this.grxNav.mobileOpen, isGrx);
            localizeFallbackUiButtons();
            syncCleanBrowserUrl(this.grxNav.activeXmlid, isGrx);
            this._grxSyncBrowserTitle(isGrx);
            window.requestAnimationFrame(() => animateGeorutexEmptyStates(document));
        };

        onMounted(() => {
            applyShellClasses(this.grxNav.collapsed, this.grxNav.mobileOpen, this.isGeoRutexApp());
            this._grxSyncActiveFromHash();
            this._grxDismissBootSplash();
            window.addEventListener("resize", this._grxOnResize);
            window.addEventListener("keydown", this._grxOnKeyDown);
            window.addEventListener("hashchange", this._grxSyncActiveFromHash);
            document.addEventListener("click", this._grxOnDocumentClick, true);
            this.env.bus.on("ACTION_MANAGER:UI-UPDATED", this, this._grxSyncActiveFromHash);
            this.env.bus.on("MENUS:APP-CHANGED", this, this._grxSyncActiveFromHash);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._grxOnResize);
            window.removeEventListener("keydown", this._grxOnKeyDown);
            window.removeEventListener("hashchange", this._grxSyncActiveFromHash);
            document.removeEventListener("click", this._grxOnDocumentClick, true);
            this.env.bus.off("ACTION_MANAGER:UI-UPDATED", this, this._grxSyncActiveFromHash);
            this.env.bus.off("MENUS:APP-CHANGED", this, this._grxSyncActiveFromHash);
        });
    },

    _grxSyncBrowserTitle(isGrx) {
        if (!this.titleService) return;
        if (!isGrx) {
            this.titleService.setParts({ zopenerp: "Odoo" });
            return;
        }
        const activeXmlid = this.grxNav.activeXmlid;
        const sectionTitle =
            (session.georutex_is_driver_only && DRIVER_MENU_LABELS[activeXmlid]) ||
            CLEAN_MENU_LABELS[activeXmlid] ||
            "";
        if (sectionTitle) {
            this.titleService.setParts({ zopenerp: `GeoRutex · ${sectionTitle}`, action: null });
        } else {
            this.titleService.setParts({ zopenerp: "GeoRutex" });
        }
    },

    _grxDismissBootSplash() {
        const splash = document.getElementById("grx-boot-splash");
        if (!splash) return;
        const reduced = Boolean(
            window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );
        if (window.gsap && !reduced) {
            window.gsap.to(splash, {
                opacity: 0,
                duration: 0.24,
                ease: "power2.out",
                onComplete: () => splash.remove(),
            });
        } else {
            splash.remove();
        }
    },

    isGeoRutexApp() {
        const app = this.currentApp;
        if (!app) return false;
        return app.xmlid === GEORUTEX_ROOT_XMLID;
    },

    getGeoRutexRootApp() {
        const apps = (this.menuService && this.menuService.getApps()) || [];
        return apps.find((a) => a.xmlid === GEORUTEX_ROOT_XMLID) || null;
    },

    async adapt() {
        // Both GeoRutex vertical sidebar and foreign horizontal sections render all items directly without "More" overflow
        if (this.currentAppSectionsExtra && this.currentAppSectionsExtra.length) {
            this.currentAppSectionsExtra = [];
            this.render();
        }
    },

    getMenuDisplayName(menu) {
        if (!menu) return "";
        if (session.georutex_is_driver_only && menu.xmlid && DRIVER_MENU_LABELS[menu.xmlid]) {
            return DRIVER_MENU_LABELS[menu.xmlid];
        }
        if (menu.xmlid && CLEAN_MENU_LABELS[menu.xmlid]) {
            return CLEAN_MENU_LABELS[menu.xmlid];
        }
        return menu.name || "";
    },

    getMenuIcon(menu) {
        if (!menu) return "fa-circle-o";
        if (menu.xmlid && MENU_ICONS[menu.xmlid]) {
            return MENU_ICONS[menu.xmlid];
        }
        const name = (menu.name || "").toLowerCase();
        if (name.includes("inicio") || name.includes("centro") || name.includes("jornada")) return "fa-th-large";
        if (name.includes("análisis") || name.includes("dashboard") || name.includes("resumen")) return "fa-bar-chart";
        if (name.includes("mapa")) return "fa-map-marker";
        if (name.includes("recorrido") || name.includes("viaje")) return "fa-road";
        if (name.includes("incidencia")) return "fa-exclamation-triangle";
        if (name.includes("evaluaci")) return "fa-check-square-o";
        if (name.includes("versi")) return "fa-code-fork";
        if (name.includes("ruta")) return "fa-map-signs";
        if (name.includes("vehículo") || name.includes("flota")) return "fa-bus";
        if (name.includes("posici") || name.includes("telemetr") || name.includes("gps")) return "fa-crosshairs";
        if (name.includes("usuario") || name.includes("empresa")) return "fa-users";
        if (name.includes("ajuste") || name.includes("técnic") || name.includes("config")) return "fa-cog";
        return "fa-angle-right";
    },

    isMenuActive(menu) {
        if (!menu) return false;
        if (this.grxNav.activeMenuId && menu.id === this.grxNav.activeMenuId) {
            return true;
        }
        if (this.grxNav.activeXmlid && menu.xmlid === this.grxNav.activeXmlid) {
            return true;
        }
        return false;
    },

    isGroupOpen(section) {
        if (!section) return true;
        const key = section.xmlid || String(section.id);
        return !this.grxNav.closedGroups.includes(key);
    },

    toggleForeignDropdown(sectionId) {
        this.grxNav.openForeignDropdownId =
            this.grxNav.openForeignDropdownId === sectionId ? null : sectionId;
    },

    selectForeignMenu(menu) {
        this.grxNav.openForeignDropdownId = null;
        this.onNavBarDropdownItemSelection(menu);
    },

    returnToGeoRutex() {
        const grxApp = this.getGeoRutexRootApp();
        if (grxApp) {
            this.onNavBarDropdownItemSelection(grxApp);
        }
    },

    toggleGeoRutexGroup(section) {
        if (!section) return;
        const key = section.xmlid || String(section.id);
        const list = [...this.grxNav.closedGroups];
        const idx = list.indexOf(key);
        const opening = idx >= 0;
        if (opening) {
            list.splice(idx, 1);
        } else {
            list.push(key);
        }
        this.grxNav.closedGroups = list;
        writeClosedGroups(list);

        if (
            opening &&
            window.gsap &&
            !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
        ) {
            window.requestAnimationFrame(() => {
                const head = document.querySelector(
                    `.grx-sb-group-head[data-menu-xmlid="${section.xmlid}"]`
                );
                const items =
                    head && head.parentElement && head.parentElement.querySelectorAll(".grx-sb-item");
                if (items && items.length) {
                    window.gsap.fromTo(
                        items,
                        { y: -6, opacity: 0 },
                        {
                            y: 0,
                            opacity: 1,
                            duration: 0.2,
                            stagger: 0.025,
                            ease: "power2.out",
                            clearProps: "transform,opacity",
                        }
                    );
                }
            });
        }
    },

    toggleGeoRutexSidebar() {
        if (!this.isGeoRutexApp()) return;
        const reduced = Boolean(
            window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
        );
        if (isMobileViewport()) {
            this.grxNav.mobileOpen = !this.grxNav.mobileOpen;
            applyShellClasses(this.grxNav.collapsed, this.grxNav.mobileOpen, true);
            if (this.grxNav.mobileOpen && window.gsap && !reduced) {
                const sb = document.getElementById("grx-sidebar-nav");
                if (sb) {
                    window.gsap.fromTo(
                        sb,
                        { x: -26, opacity: 0.7 },
                        {
                            x: 0,
                            opacity: 1,
                            duration: 0.24,
                            ease: "power2.out",
                            clearProps: "transform,opacity",
                        }
                    );
                }
            }
            return;
        }

        const icons = document.querySelectorAll("#grx-sidebar-nav .grx-sb-icon");
        if (window.gsap && window.Flip && !reduced && !window._grxFlipRegistered) {
            try {
                window.gsap.registerPlugin(window.Flip);
                window._grxFlipRegistered = true;
            } catch (_err) {
                // Ignore duplicate registration
            }
        }
        const flipState =
            window.Flip && icons.length && !reduced ? window.Flip.getState(icons) : null;

        this.grxNav.collapsed = !this.grxNav.collapsed;
        try {
            window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(this.grxNav.collapsed));
        } catch (_err) {
            // Ignore storage errors
        }
        applyShellClasses(this.grxNav.collapsed, false, true);
        if (flipState) {
            window.requestAnimationFrame(() => {
                try {
                    window.Flip.from(flipState, {
                        duration: 0.26,
                        ease: "power2.out",
                        simple: true,
                    });
                } catch (_err) {
                    // Safe fallback
                }
            });
        }
        // Notify Leaflet maps and ECharts panels after sidebar transition finishes
        window.setTimeout(() => {
            window.dispatchEvent(new Event("resize"));
        }, 280);
    },

    closeMobileSidebar() {
        this.grxNav.mobileOpen = false;
        applyShellClasses(this.grxNav.collapsed, false, this.isGeoRutexApp());
    },

    onGeoRutexBrandClick(app) {
        if (!app) return;
        if (this.isGeoRutexApp()) {
            const firstSection = this.currentAppSections && this.currentAppSections[0];
            if (firstSection && !firstSection.childrenTree.length) {
                this.selectGeoRutexMenu(firstSection);
                return;
            }
        }
        this.onNavBarDropdownItemSelection(app);
    },

    selectGeoRutexMenu(menu, parentGroup = null) {
        if (!menu) return;
        this.grxNav.activeMenuId = menu.id;
        if (menu.xmlid) {
            this.grxNav.activeXmlid = menu.xmlid;
            window.sessionStorage.setItem(SELECTED_XMLID_KEY, menu.xmlid);
        }
        if (parentGroup) {
            const key = parentGroup.xmlid || String(parentGroup.id);
            if (this.grxNav.closedGroups.includes(key)) {
                this.grxNav.closedGroups = this.grxNav.closedGroups.filter((k) => k !== key);
                writeClosedGroups(this.grxNav.closedGroups);
            }
        }
        if (this.grxNav.mobileOpen) {
            this.closeMobileSidebar();
        }
        this.onNavBarDropdownItemSelection(menu);
        window.setTimeout(() => syncCleanBrowserUrl(this.grxNav.activeXmlid, this.isGeoRutexApp()), 80);
    },
});
