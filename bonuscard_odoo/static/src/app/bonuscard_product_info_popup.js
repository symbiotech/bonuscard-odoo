/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductInfoPopup } from "@point_of_sale/app/components/popups/product_info_popup/product_info_popup";

patch(ProductInfoPopup.prototype, {
    get bonuscardCatalogStatus() {
        return this.props.productTemplate.bonuscard_catalog_status;
    },
    get showBonuscardCatalogStatus() {
        return Boolean(this.bonuscardCatalogStatus);
    },
    get bonuscardCatalogLabel() {
        const labels = {
            not_set: _t("Not Set"),
            in_catalog: _t("In Bonuscard Catalog"),
            not_in_catalog: _t("Not in Bonuscard Catalog"),
        };
        return labels[this.bonuscardCatalogStatus] || this.bonuscardCatalogStatus;
    },
    get bonuscardCatalogBadgeClass() {
        if (this.bonuscardCatalogStatus === "in_catalog") {
            return "text-bg-success";
        }
        if (this.bonuscardCatalogStatus === "not_in_catalog") {
            return "text-bg-secondary";
        }
        return "text-bg-warning";
    },
});
