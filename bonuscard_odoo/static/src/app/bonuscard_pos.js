/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async setPartnerToCurrentOrder(partner) {
        await super.setPartnerToCurrentOrder(...arguments);
        if (!partner) {
            return;
        }
        if (partner.bonuscard_status && partner.bonuscard_status !== "not_checked") {
            return;
        }
        try {
            const result = await this.data.call("res.partner", "get_bonuscard_status_for_pos", [
                partner.id,
            ]);
            partner.bonuscard_status = result.status;
            partner.bonuscard_recruitment_code = result.recruitment_code;
            partner.bonuscard_last_lookup_note = result.note;
            if (result.status === "linked") {
                this.notification.add(
                    _t("Bonuscard member detected: %s", result.recruitment_code),
                    { type: "success" }
                );
            } else if (result.status === "not_found") {
                this.notification.add(_t("Customer is not linked to Bonuscard."), {
                    type: "warning",
                });
            } else if (result.status === "ambiguous") {
                this.notification.add(_t("Bonuscard returned multiple customer matches."), {
                    type: "warning",
                });
            } else if (result.status === "error") {
                this.notification.add(result.note || _t("Bonuscard lookup failed."), {
                    type: "danger",
                });
            }
        } catch {
            this.notification.add(_t("Bonuscard lookup failed."), { type: "danger" });
        }
    },
});
