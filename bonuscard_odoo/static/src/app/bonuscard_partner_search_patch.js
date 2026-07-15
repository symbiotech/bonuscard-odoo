/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ResPartner } from "@point_of_sale/app/models/res_partner";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

const BONUSCARD_POS_SEARCH_FIELD = "bonuscard_pos_search";

patch(ResPartner.prototype, {
    get searchString() {
        const base = super.searchString;
        if (this.bonuscard_recruitment_code) {
            return `${base} ${this.bonuscard_recruitment_code}`.trim();
        }
        return base;
    },

    exactMatch(searchWord) {
        if (super.exactMatch(searchWord)) {
            return true;
        }
        return (
            !!this.bonuscard_recruitment_code &&
            this.bonuscard_recruitment_code.toLowerCase() === searchWord.toLowerCase()
        );
    },
});

patch(PartnerList.prototype, {
    _getSearchFields(query) {
        const searchFields = super._getSearchFields(...arguments);
        if (!searchFields.includes(BONUSCARD_POS_SEARCH_FIELD)) {
            searchFields.push(BONUSCARD_POS_SEARCH_FIELD);
        }
        return searchFields;
    },
});
