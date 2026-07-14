/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductInfoPopup } from "@point_of_sale/app/components/popups/product_info_popup/product_info_popup";

patch(ProductInfoPopup.prototype, {
    get bonuscardCatalogVariant() {
        const variants = this.props.productTemplate.product_variant_ids || [];
        return variants.length === 1 ? variants[0] : null;
    },
    get bonuscardCatalogStatus() {
        const templateStatus = this.props.productTemplate.bonuscard_catalog_status;
        if (templateStatus) {
            return templateStatus;
        }
        return this.bonuscardCatalogVariant?.bonuscard_catalog_status || "not_set";
    },
    get showBonuscardCatalogStatus() {
        const templateStatus = this.props.productTemplate.bonuscard_catalog_status;
        if (templateStatus) {
            return true;
        }
        if (templateStatus === false) {
            return false;
        }
        return Boolean(this.bonuscardCatalogVariant);
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
