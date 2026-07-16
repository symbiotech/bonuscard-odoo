/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(ControlButtons.prototype, {
    async clickBonuscardCode() {
        const code = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("Bonuscard Discount Code"),
            placeholder: _t("Enter discount code"),
            rows: 1,
        });
        if (!code || !String(code).trim()) {
            return;
        }
        await this.pos.activateBonuscardDiscountCode(String(code).trim());
    },
});
