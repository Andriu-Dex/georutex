/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

const openMenuKey = "georutex.openMenuXmlid";
const selectedMenuKey = "georutex.selectedMenuXmlid";
const sidebarHiddenKey = "georutex.sidebarHidden";
let reopeningMenuXmlid = null;
let syncScheduled = false;

function getWebClient() {
    return document.querySelector(".o_web_client");
}

function getMenuSections() {
    return document.querySelector(".o_main_navbar .o_menu_sections");
}

function applySidebarVisibility() {
    const webClient = getWebClient();
    const toggle = document.querySelector(".o_georutex_sidebar_toggle");
    if (!webClient || !toggle) return;

    const isHidden = window.sessionStorage.getItem(sidebarHiddenKey) === "true";
    webClient.classList.toggle("o_georutex_sidebar_hidden", isHidden);
    toggle.setAttribute("aria-expanded", String(!isHidden));
    toggle.setAttribute(
        "aria-label",
        isHidden ? "Mostrar menú lateral" : "Ocultar menú lateral"
    );
    toggle.setAttribute(
        "title",
        isHidden ? "Mostrar menú lateral" : "Ocultar menú lateral"
    );
}

function ensureSidebarToggle() {
    const navbar = document.querySelector(".o_main_navbar");
    if (!navbar) return;

    let toggle = navbar.querySelector(".o_georutex_sidebar_toggle");
    if (!toggle) {
        toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "o_georutex_sidebar_toggle";

        const icon = document.createElement("i");
        icon.className = "fa fa-bars";
        icon.setAttribute("aria-hidden", "true");
        toggle.appendChild(icon);

        const brand = navbar.querySelector(".o_menu_brand");
        if (brand && brand.parentElement === navbar) {
            navbar.insertBefore(toggle, brand);
        } else {
            const appMenu = navbar.querySelector(".o_navbar_apps_menu");
            if (appMenu && appMenu.parentElement === navbar) {
                appMenu.insertAdjacentElement("afterend", toggle);
            } else {
                navbar.appendChild(toggle);
            }
        }
    }

    const menuSections = getMenuSections();
    if (menuSections) {
        menuSections.id = menuSections.id || "georutex-navigation";
        toggle.setAttribute("aria-controls", menuSections.id);
    }

    applySidebarVisibility();
}

function localizeFormStatusButtons() {
    const setAttributeIfChanged = (element, name, value) => {
        if (element.getAttribute(name) !== value) {
            element.setAttribute(name, value);
        }
    };
    const setButtonLabel = (button, label) => {
        let text = button.querySelector(".o_georutex_form_button_text");
        if (!text) {
            text = document.createElement("span");
            text.className = "o_georutex_form_button_text";
            button.appendChild(text);
        }
        if (text.textContent !== label) {
            text.textContent = label;
        }
    };
    document
        .querySelectorAll(".o_form_status_indicator .o_form_button_save")
        .forEach((button) => {
            setAttributeIfChanged(button, "aria-label", _t("Save manually"));
            setAttributeIfChanged(button, "title", _t("Save manually"));
            setAttributeIfChanged(button, "data-tooltip", _t("Save manually"));
            setButtonLabel(button, _t("Save"));
        });
    document
        .querySelectorAll(".o_form_status_indicator .o_form_button_cancel")
        .forEach((button) => {
            setAttributeIfChanged(button, "aria-label", _t("Discard changes"));
            setAttributeIfChanged(button, "title", _t("Discard changes"));
            setAttributeIfChanged(button, "data-tooltip", _t("Discard changes"));
            setButtonLabel(button, _t("Discard"));
        });
}

function hideNewFormBreadcrumb() {
    const formView = document.querySelector(".o_action_manager .o_form_view");
    const activeBreadcrumb = document.querySelector(
        ".o_control_panel .breadcrumb-item.active"
    );
    if (!activeBreadcrumb) return;

    const isNewLabel =
        formView && activeBreadcrumb.textContent.trim().toLowerCase() === "new";
    activeBreadcrumb.classList.toggle(
        "o_georutex_new_form_breadcrumb",
        Boolean(isNewLabel)
    );
}

function getDropdownToggle(dropdown) {
    return dropdown && dropdown.querySelector(":scope > .dropdown-toggle");
}

function applySelectedMenu(menuSections) {
    const selectedXmlid = window.sessionStorage.getItem(selectedMenuKey);
    const entries = menuSections.querySelectorAll(".o_nav_entry, .dropdown-item");
    entries.forEach((entry) => {
        entry.classList.toggle(
            "active",
            Boolean(selectedXmlid) && entry.dataset.menuXmlid === selectedXmlid
        );
    });
}

function openRememberedMenu(menuSections) {
    const openXmlid = window.sessionStorage.getItem(openMenuKey);
    if (!openXmlid || reopeningMenuXmlid === openXmlid) return;

    const dropdowns = menuSections.querySelectorAll(":scope > .o-dropdown");
    const dropdown = Array.from(dropdowns).find((candidate) => {
        const toggle = getDropdownToggle(candidate);
        return toggle && toggle.dataset.menuXmlid === openXmlid;
    });
    if (!dropdown || dropdown.classList.contains("show")) return;

    const toggle = getDropdownToggle(dropdown);
    if (!toggle) return;

    reopeningMenuXmlid = openXmlid;
    toggle.click();
    window.setTimeout(() => {
        if (reopeningMenuXmlid === openXmlid) {
            reopeningMenuXmlid = null;
            scheduleMenuSync();
        }
    }, 180);
}

function syncMenuState() {
    ensureSidebarToggle();
    localizeFormStatusButtons();
    hideNewFormBreadcrumb();
    const menuSections = getMenuSections();
    if (!menuSections) return;

    openRememberedMenu(menuSections);
    applySelectedMenu(menuSections);
}

function scheduleMenuSync() {
    if (syncScheduled) return;
    syncScheduled = true;
    window.requestAnimationFrame(() => {
        syncScheduled = false;
        syncMenuState();
    });
}

document.addEventListener(
    "click",
    (event) => {
        const sidebarToggle = event.target.closest(".o_georutex_sidebar_toggle");
        if (sidebarToggle) {
            event.preventDefault();
            const webClient = getWebClient();
            if (webClient) {
                const isHidden = !webClient.classList.contains(
                    "o_georutex_sidebar_hidden"
                );
                window.sessionStorage.setItem(
                    sidebarHiddenKey,
                    String(isHidden)
                );
                applySidebarVisibility();
            }
            return;
        }

        const menuSections = getMenuSections();
        if (!menuSections || !menuSections.contains(event.target)) return;

        const directEntry = event.target.closest(".o_nav_entry");
        if (directEntry && menuSections.contains(directEntry)) {
            window.sessionStorage.removeItem(openMenuKey);
            if (directEntry.dataset.menuXmlid) {
                window.sessionStorage.setItem(
                    selectedMenuKey,
                    directEntry.dataset.menuXmlid
                );
            }
            scheduleMenuSync();
            return;
        }

        const dropdown = event.target.closest(".o-dropdown");
        if (!dropdown || !menuSections.contains(dropdown) || dropdown.classList.contains("o_menu_sections_more")) {
            return;
        }

        const menuItem = event.target.closest(".dropdown-item");
        if (menuItem && dropdown.contains(menuItem)) {
            const toggle = getDropdownToggle(dropdown);
            if (toggle && toggle.dataset.menuXmlid) {
                window.sessionStorage.setItem(openMenuKey, toggle.dataset.menuXmlid);
            }
            if (menuItem.dataset.menuXmlid) {
                window.sessionStorage.setItem(selectedMenuKey, menuItem.dataset.menuXmlid);
            }
            scheduleMenuSync();
            return;
        }

        const toggle = event.target.closest(".dropdown-toggle");
        if (toggle && dropdown.contains(toggle) && toggle.dataset.menuXmlid) {
            if (reopeningMenuXmlid === toggle.dataset.menuXmlid) return;
            if (dropdown.classList.contains("show")) {
                window.sessionStorage.removeItem(openMenuKey);
            } else {
                window.sessionStorage.setItem(openMenuKey, toggle.dataset.menuXmlid);
                const selectedXmlid = window.sessionStorage.getItem(selectedMenuKey);
                if (selectedXmlid !== toggle.dataset.menuXmlid) {
                    window.sessionStorage.removeItem(selectedMenuKey);
                }
            }
            scheduleMenuSync();
            return;
        }
    },
    true
);

const menuObserver = new MutationObserver(scheduleMenuSync);
if (document.body) {
    menuObserver.observe(document.body, { childList: true, subtree: true });
}
window.addEventListener("hashchange", scheduleMenuSync);
scheduleMenuSync();
