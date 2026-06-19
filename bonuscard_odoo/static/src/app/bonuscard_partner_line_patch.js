/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

PartnerLine.props = {
    ...PartnerLine.props,
    onClickRegisterBonuscard: { type: Function, optional: true },
};

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
        this.action = useService("action");
    },

    async registerPartnerToBonuscard(partner) {
        if (!partner || !partner.id) {
            return;
        }

        try {
            const result = await this.pos.data.call("res.partner", "action_register_to_bonuscard", [[partner.id]]);
            if (result?.type?.startsWith("ir.actions.") && this.action?.doAction) {
                await this.action.doAction(result);
            } else if (result?.type === "ir.actions.client") {
                const params = result.params || {};
                this.notification.add(params.message || _t("Customer registered successfully."), {
                    type: params.type || "success",
                    sticky: params.sticky || false,
                });
            } else if (result?.message) {
                this.notification.add(result.message, { type: result.type || "success", sticky: result.sticky || false });
            } else {
                this.notification.add(_t("Bonuscard registration completed."), { type: "success" });
            }

            partner.bonuscard_status = "linked";
        
        } catch (error) {
            this.notification.add(error.message || _t("Bonuscard registration failed."), { type: "danger", sticky: false });
        }
    },
});
