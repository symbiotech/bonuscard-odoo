/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";

patch(ControlButtons.prototype, {
    clickBonuscardCode() {
        // Same dialog pattern as pos_loyalty Enter Code (dialog.add + getPayload).
        // Avoid makeAwaitable here: ControlButtonsPopup closes on any click, and
        // awaiting a second dialog from that teardown has crashed Owl on SaaS.
        this.dialog.add(TextInputPopup, {
            title: _t("Bonuscard Discount Code"),
            placeholder: _t("Enter discount code"),
            rows: 1,
            getPayload: async (code) => {
                const trimmed = String(code || "").trim();
                if (!trimmed) {
                    return;
                }
                await this.pos.activateBonuscardDiscountCode(trimmed);
            },
        });
    },
});
