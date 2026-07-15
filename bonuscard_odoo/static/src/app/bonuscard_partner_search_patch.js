/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ResPartner } from "@point_of_sale/app/models/res_partner";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

const BONUSCARD_POS_SEARCH_FIELD = "bonuscard_pos_search";

function normalizePhone(value) {
    return (value || "").replace(/[+\s()-]/g, "");
}

patch(ResPartner.prototype, {
    get searchString() {
        if (this._searchString) {
            return this._searchString;
        }

        const fields = [
            "name",
            "barcode",
            "phone",
            "email",
            "vat",
            "parent_name",
            "pos_contact_address",
            "bonuscard_recruitment_code",
        ];
        this._searchString = fields
            .map((field) => {
                if (field === "phone" && this[field]) {
                    return normalizePhone(this[field]);
                }
                return this[field] || "";
            })
            .filter(Boolean)
            .join(" ");
        return this._searchString;
    },

    exactMatch(searchWord) {
        if (super.exactMatch(searchWord)) {
            return true;
        }
        const normalizedSearch = normalizePhone(searchWord);
        if (this.phone && normalizePhone(this.phone) === normalizedSearch) {
            return true;
        }
        if (
            this.bonuscard_recruitment_code &&
            this.bonuscard_recruitment_code.toLowerCase() === searchWord.toLowerCase()
        ) {
            return true;
        }
        return false;
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
