/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, "uta_transport_monitor.createReturnToList", {
    async saveButtonClicked(params = {}) {
        const save = this._super.bind(this);
        const isNewRecord = this.model.root.isVirtual;
        const saved = await save(params);

        if (saved && isNewRecord && !this.env.inDialog) {
            this.env.config.historyBack();
        }

        return saved;
    },
});
