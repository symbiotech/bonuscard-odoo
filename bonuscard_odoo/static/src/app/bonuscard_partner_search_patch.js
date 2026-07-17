/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ResPartner } from "@point_of_sale/app/models/res_partner";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

const BONUSCARD_POS_SEARCH_FIELD = "bonuscard_pos_search";
const BONUSCARD_APP_BARCODE_PREFIX = "999000";
const BONUSCARD_APP_BARCODE_ID_WIDTH = 6;

function ean13CheckDigit(first12Digits) {
    if (!/^\d{12}$/.test(first12Digits)) {
        return "";
    }
    let total = 0;
    for (let index = 0; index < 12; index++) {
        const digit = Number(first12Digits[index]);
        total += index % 2 ? digit * 3 : digit;
    }
    return String((10 - (total % 10)) % 10);
}

function extractBonuscardIdFromAppBarcode(value) {
    const digits = String(value || "").replace(/\D/g, "");
    const expectedLen = BONUSCARD_APP_BARCODE_PREFIX.length + BONUSCARD_APP_BARCODE_ID_WIDTH + 1;
    if (digits.length !== expectedLen || !digits.startsWith(BONUSCARD_APP_BARCODE_PREFIX)) {
        return "";
    }
    const body = digits.slice(0, -1);
    const check = digits.slice(-1);
    if (ean13CheckDigit(body) !== check) {
        return "";
    }
    const rawId = digits.slice(
        BONUSCARD_APP_BARCODE_PREFIX.length,
        BONUSCARD_APP_BARCODE_PREFIX.length + BONUSCARD_APP_BARCODE_ID_WIDTH
    );
    const memberId = Number(rawId);
    if (!memberId) {
        return "";
    }
    return String(memberId);
}

patch(ResPartner.prototype, {
    get searchString() {
        const base = super.searchString;
        const extras = [];
        if (this.bonuscard_recruitment_code) {
            extras.push(this.bonuscard_recruitment_code);
        }
        if (this.bonuscard_internal_id) {
            extras.push(String(this.bonuscard_internal_id));
        }
        return extras.length ? `${base} ${extras.join(" ")}`.trim() : base;
    },

    exactMatch(searchWord) {
        if (super.exactMatch(searchWord)) {
            return true;
        }
        const needle = (searchWord || "").toLowerCase();
        if (
            this.bonuscard_recruitment_code &&
            this.bonuscard_recruitment_code.toLowerCase() === needle
        ) {
            return true;
        }
        if (
            this.bonuscard_internal_id &&
            String(this.bonuscard_internal_id) === String(searchWord || "").trim()
        ) {
            return true;
        }
        const extractedId = extractBonuscardIdFromAppBarcode(searchWord);
        return (
            !!extractedId &&
            !!this.bonuscard_internal_id &&
            String(this.bonuscard_internal_id) === extractedId
        );
    },
});

patch(PartnerList.prototype, {
    _getSearchFields(query) {
        const searchFields = super._getSearchFields(query);
        if (!searchFields.includes(BONUSCARD_POS_SEARCH_FIELD)) {
            searchFields.push(BONUSCARD_POS_SEARCH_FIELD);
        }
        return searchFields;
    },
});
