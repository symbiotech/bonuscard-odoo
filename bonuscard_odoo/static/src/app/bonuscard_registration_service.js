/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";

export class BonuscardRegistrationService {
    constructor(env, { notification, action }) {
        this.env = env;
        this.notification = notification;
        this.action = action;
    }

    async registerPartnerToBonuscard(partner, pos) {
        if (!partner || !partner.id || !pos) {
            return;
        }

        if (!partner.phone) {
            this.notification.add(
                _t("A phone number is required to register a customer with Bonuscard."),
                { type: "warning", sticky: false }
            );
            return;
        }

        try {
            const result = await pos.data.call("res.partner", "action_register_to_bonuscard", [[partner.id]]);
            if (result?.type?.startsWith("ir.actions.") && this.action?.doAction) {
                await this.action.doAction(result);
            } else if (result?.message) {
                this.notification.add(result.message, {
                    type: result.type || "success",
                    sticky: result.sticky || false,
                });
            } else {
                this.notification.add(_t("Bonuscard registration completed."), { type: "success" });
            }

            const statusResult = await pos.data.call(
                "res.partner",
                "get_bonuscard_status_for_pos",
                [partner.id]
            );
            partner.bonuscard_status = statusResult.status;
            partner.bonuscard_recruitment_code = statusResult.recruitment_code;
            partner.bonuscard_last_lookup_note = statusResult.note;
        } catch (error) {
            const errorMessage = this._extractErrorMessage(error);
            this.notification.add(errorMessage, { type: "danger", sticky: false });
            logPosMessage(
                "Bonuscard",
                "registerPartnerToBonuscard",
                "Bonuscard registration failed.",
                false,
                [{ partnerId: partner?.id, error }]
            );
        }
    }

    _extractErrorMessage(error) {
        // Try to extract meaningful error message from various Odoo error formats
        if (!error) {
            return _t("Bonuscard registration failed.");
        }

        // Direct error message
        if (error.message && error.message !== "Odoo Server Error") {
            return error.message;
        }

        // Odoo RPC error data
        if (error.data?.message && error.data.message !== "Odoo Server Error") {
            return error.data.message;
        }

        // Odoo exception arguments (first argument usually contains the error text)
        if (error.data?.arguments?.[0]) {
            return String(error.data.arguments[0]);
        }

        // Fallback message
        return _t("Bonuscard registration failed.");
    }
}
