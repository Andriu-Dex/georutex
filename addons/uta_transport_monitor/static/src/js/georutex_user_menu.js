/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import "@web/webclient/user_menu/user_menu_items";

const userMenuRegistry = registry.category("user_menuitems");

// Remove Odoo-branded and unnecessary entries from the top-right user menu
["documentation", "support", "shortcuts", "odoo_account", "separator"].forEach(
    (key) => {
        if (userMenuRegistry.contains(key)) {
            userMenuRegistry.remove(key);
        }
    }
);

// Replace "Preferences" with clean GeoRutex credentials/profile item
if (userMenuRegistry.contains("profile")) {
    userMenuRegistry.remove("profile");
}
userMenuRegistry.add(
    "profile",
    function georutexProfileItem(env) {
        return {
            type: "item",
            id: "georutex_profile",
            description: "Mi perfil y credenciales",
            callback: async () => {
                if (env.services.georutex_drawer) {
                    await env.services.georutex_drawer.openPreferences(env.services.user.userId);
                    return;
                }
                const actionDescription = await env.services.orm.call(
                    "res.users",
                    "action_get"
                );
                actionDescription.res_id = env.services.user.userId;
                env.services.action.doAction(actionDescription);
            },
            sequence: 10,
        };
    },
    { force: true }
);

// Replace "Log out" to route through GeoRutex's Spanish logout endpoint
if (userMenuRegistry.contains("log_out")) {
    userMenuRegistry.remove("log_out");
}
userMenuRegistry.add(
    "log_out",
    function georutexLogoutItem() {
        return {
            type: "item",
            id: "georutex_logout",
            description: "Cerrar sesión",
            href: "/georutex/cerrar-sesion",
            callback: () => {
                browser.location.href = "/georutex/cerrar-sesion";
            },
            sequence: 90,
        };
    },
    { force: true }
);
