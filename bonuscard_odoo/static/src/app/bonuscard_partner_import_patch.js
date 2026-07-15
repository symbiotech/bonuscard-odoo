/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

function extractRpcErrorMessage(error) {
    if (!error) {
        return _t("No Bonuscard customer found.");
    }
    if (error.message && error.message !== "Odoo Server Error") {
        return error.message;
    }
    if (error.data?.message && error.data.message !== "Odoo Server Error") {
        return error.data.message;
    }
    if (error.data?.arguments?.[0]) {
        return String(error.data.arguments[0]);
    }
    return _t("No Bonuscard customer found.");
}

patch(PartnerList.prototype, {
    async searchPartner() {
        const partners = await super.searchPartner(...arguments);
        if (this._bonuscardShouldTryImport(partners)) {
            return this._bonuscardImportPartnerFromSearch();
        }
        return partners;
    },

    _bonuscardShouldTryImport(partners) {
        const query = this.state.query?.trim();
        if (!query || partners?.length) {
            return false;
        }
        const visibleInitial = this.getPartners(this.state.initialPartners).length;
        const visibleLoaded = this.getPartners(this.state.loadedPartners).length;
        return visibleInitial === 0 && visibleLoaded === 0;
    },

    async _bonuscardImportPartnerFromSearch() {
        const query = this.state.query.trim();
        try {
            this.state.loading = true;
            const result = await this.pos.data.callRelated(
                "res.partner",
                "import_partner_from_bonuscard_for_pos",
                [this.pos.config.id, query]
            );
            const partners = result["res.partner"] || [];
            for (const partner of partners) {
                if (!this.loadedPartnerIds.has(partner.id)) {
                    this.loadedPartnerIds.add(partner.id);
                    this.state.loadedPartners.push(partner);
                }
            }
            if (partners.length) {
                this.notification.add(
                    sprintf(_t('Bonuscard customer "%s" added.'), query),
                    { type: "success" }
                );
            }
            return partners;
        } catch (error) {
            this.notification.add(extractRpcErrorMessage(error), {
                type: "warning",
                sticky: false,
            });
            logPosMessage(
                "Bonuscard",
                "_bonuscardImportPartnerFromSearch",
                "Bonuscard customer import failed.",
                false,
                [{ query, error }]
            );
            return [];
        } finally {
            this.state.loading = false;
        }
    },
});
